"""PanRadar 证书自动续期。

用途：Let's Encrypt 证书只有 90 天。本脚本通过 DNS-01 自动重新签发，
      并把新证书推到阿里云 FC 的自定义域名上，可挂 Windows 计划任务每天跑一次。

依赖（仅本脚本用，项目本体仍是零依赖）：
    pip install acme cryptography alibabacloud_alidns20150109 alibabacloud_fc_open20210406

环境变量：
    ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET

用法：
    python renew_cert.py            # 剩余有效期 > 30 天则直接跳过
    python renew_cert.py --force    # 强制续期
    python renew_cert.py --days 15  # 改阈值

退出码：0 成功或无需续期；1 失败
"""
import os, sys, time, json
from datetime import datetime, timezone, timedelta

# ---------------- 配置 ----------------
DOMAINS = ['pan.ydtgo.top', '*.pan.ydtgo.top']
FC_REGION = 'cn-hongkong'
FC_DOMAIN = 'pan.ydtgo.top'
FC_SERVICE = 'panradar-svc'
FC_FUNCTION = 'panradar'
CERT_NAME = 'pan-ydtgo-top-le'
EMAIL = 'oracis@gmail.com'

HERE = os.path.dirname(os.path.abspath(__file__))
CERT_DIR = os.environ.get('PANRADAR_CERT_DIR') or os.path.join(
    os.path.expanduser('~'), '.panradar-acme', 'pan.ydtgo.top')
os.makedirs(CERT_DIR, exist_ok=True)
FULLCHAIN = os.path.join(CERT_DIR, 'fullchain.pem')
PRIVKEY = os.path.join(CERT_DIR, 'privkey.pem')
ACCOUNT_KEY = os.path.join(CERT_DIR, '..', 'account.key')

FORCE = '--force' in sys.argv
THRESHOLD = 30
if '--days' in sys.argv:
    THRESHOLD = int(sys.argv[sys.argv.index('--days') + 1])

AK = os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_ID', '')
SK = os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_SECRET', '')
if not AK or not SK:
    sys.exit('请先设置 ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET')


def log(msg):
    print('[%s] %s' % (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), msg))


# ---------------- 1) 是否需要续期 ----------------
def days_left(path):
    if not os.path.exists(path):
        return -1
    from cryptography import x509
    cert = x509.load_pem_x509_certificate(open(path, 'rb').read())
    return (cert.not_valid_after_utc - datetime.now(timezone.utc)).days


left = days_left(FULLCHAIN)
log('当前证书剩余 %s 天（阈值 %s 天），路径 %s' % (left, THRESHOLD, FULLCHAIN))
if left > THRESHOLD and not FORCE:
    log('无需续期，退出')
    sys.exit(0)

# ---------------- 2) 签发 ----------------
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization, hashes
from cryptography import x509
from cryptography.x509.oid import NameOID
import josepy as jose
from acme import client, messages, challenges
from acme.errors import ConflictError

from alibabacloud_tea_openapi import models as openapi_models
from alibabacloud_alidns20150109.client import Client as DnsClient
from alibabacloud_alidns20150109 import models as dns_models


def fc_cfg(endpoint):
    c = openapi_models.Config(access_key_id=AK, access_key_secret=SK)
    c.endpoint = endpoint
    return c


dns = DnsClient(fc_cfg('alidns.cn-hangzhou.aliyuncs.com'))
DOMAIN_ROOT = 'ydtgo.top'

added = []


def add_txt(name, value):
    rr = name[: -len('.' + DOMAIN_ROOT)] if name.endswith('.' + DOMAIN_ROOT) else name
    r = dns.add_domain_record(dns_models.AddDomainRecordRequest(
        domain_name=DOMAIN_ROOT, rr=rr, type='TXT', value=value, ttl=600))
    added.append(r.body.record_id)
    log('已添加 TXT %s' % rr)


def del_txts():
    for rid in added:
        try:
            dns.delete_domain_record(dns_models.DeleteDomainRecordRequest(record_id=rid))
        except Exception:
            pass


os.makedirs(os.path.dirname(ACCOUNT_KEY), exist_ok=True)
if os.path.exists(ACCOUNT_KEY):
    acc_key = serialization.load_pem_private_key(open(ACCOUNT_KEY, 'rb').read(), password=None)
else:
    acc_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    open(ACCOUNT_KEY, 'wb').write(acc_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))

jwk = jose.JWKRSA(key=acc_key)
net = client.ClientNetwork(jwk, user_agent='panradar-acme/1.0')
directory = messages.Directory.from_json(
    net.get('https://acme-v02.api.letsencrypt.org/directory').json())
acme = client.ClientV2(directory, net)

try:
    reg = acme.new_account(messages.NewRegistration.from_data(
        email=EMAIL, terms_of_service_agreed=True))
    net.account = reg
except Exception as e:
    loc = getattr(e, 'location', None)
    if not loc:
        raise
    net.account = messages.RegistrationResource(
        body=messages.Registration.from_data(email=EMAIL, terms_of_service_agreed=True),
        uri=loc)

if os.path.exists(PRIVKEY):
    cert_key = serialization.load_pem_private_key(open(PRIVKEY, 'rb').read(), password=None)
else:
    cert_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    open(PRIVKEY, 'wb').write(cert_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))

csr = (x509.CertificateSigningRequestBuilder()
       .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, DOMAINS[0])]))
       .add_extension(x509.SubjectAlternativeName([x509.DNSName(d) for d in DOMAINS]),
                      critical=False)
       .sign(cert_key, hashes.SHA256()))

log('下单 %s' % DOMAINS)
order = acme.new_order(csr.public_bytes(serialization.Encoding.PEM))

tasks = []
for authz in order.authorizations:
    for ch in authz.body.challenges:
        if isinstance(ch.chall, challenges.DNS01):
            tasks.append((ch, ch.chall.validation_domain_name(authz.body.identifier.value),
                          ch.chall.validation(jwk)))

try:
    for ch, name, value in tasks:
        add_txt(name, value)
    log('等待 DNS 生效 70 秒')
    time.sleep(70)
    for ch, name, value in tasks:
        acme.answer_challenge(ch, ch.chall.response(jwk))
    deadline = datetime.now() + timedelta(seconds=600)
    order = acme.poll_authorizations(order, deadline)
    final = acme.finalize_order(order, deadline=datetime.now() + timedelta(seconds=300))
finally:
    del_txts()

pem = final.fullchain_pem
open(FULLCHAIN, 'w', encoding='utf-8').write(pem)
cert = x509.load_pem_x509_certificate(pem.encode())
log('新证书已签发，有效期至 %s' % cert.not_valid_after_utc)

# ---------------- 3) 推到 FC 自定义域名 ----------------
from alibabacloud_fc_open20210406.client import Client as FCClient
from alibabacloud_fc_open20210406 import models as fc_models

fc = FCClient(fc_cfg('fc.%s.aliyuncs.com' % FC_REGION))


class SimpleRoute(fc_models.RoutePolicy):
    """SDK 的 RoutePolicy 是新版 condition 结构，fc-open 2021-04-06 要 path/serviceName/functionName"""

    def __init__(self, path=None, service_name=None, function_name=None):
        self.path = path
        self.service_name = service_name
        self.function_name = function_name

    def validate(self):
        pass

    def to_map(self):
        return {'path': self.path, 'serviceName': self.service_name,
                'functionName': self.function_name}


_key = serialization.load_pem_private_key(open(PRIVKEY, 'rb').read(), password=None)
privkey_pem = _key.private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
    serialization.NoEncryption()).decode()

fc.update_custom_domain(FC_DOMAIN, fc_models.UpdateCustomDomainRequest(
    protocol='HTTP,HTTPS',
    route_config=fc_models.RouteConfig(
        routes=[SimpleRoute('/*', FC_SERVICE, FC_FUNCTION)]),
    cert_config=fc_models.CertConfig(cert_name=CERT_NAME, certificate=pem,
                                     private_key=privkey_pem)))
log('FC 自定义域名 %s 证书已更新' % FC_DOMAIN)
print('RENEW_OK')
