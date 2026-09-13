"""ydtgo.top 域名证书统一管理：签发 -> 上传 CAS -> 分发到 OSS / FC。

背景
----
- `ydtgo.top` 根域原先直接 CNAME 到 OSS 海外入口域名，用的是 OSS 默认证书
  （`*.oss-cn-hongkong.aliyuncs.com`），主机名不匹配，浏览器会报证书错误。
- 各子域散落在不同载体：根域 / book / concert / susuper / yiying 在 OSS 香港桶，
  pan 在 FC。统一用**一张通配证书** `ydtgo.top + *.ydtgo.top` 覆盖，续期只需跑一次。

依赖（仅本脚本用，pan-radar 本体仍是零依赖）：
    pip install acme cryptography oss2 \
                alibabacloud_alidns20150109 alibabacloud_cas20200407 alibabacloud_fc_open20210406

环境变量：
    ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET

用法：
    python cert_manager.py                       # 剩余 > 30 天则跳过
    python cert_manager.py --force               # 强制重新签发
    python cert_manager.py --days 15             # 改阈值
    python cert_manager.py --targets cert,cas    # 只签发并上传，不动 OSS/FC
    python cert_manager.py --targets oss,fc      # 用本地已有证书重新分发
    python cert_manager.py --targets oss --fix-cname   # 顺带把 CNAME 指向标准 OSS 域名

退出码：0 成功或无需续期；1 失败
"""
import os
import sys
import time
from datetime import datetime, timezone, timedelta

# ---------------- 配置 ----------------
ROOT = 'ydtgo.top'
EMAIL = 'oracis@gmail.com'

# 一张通配证书覆盖全部子域
CERT = {
    'name': 'ydtgo-top-wildcard',
    'domains': ['ydtgo.top', '*.ydtgo.top'],
    'cas_name': 'ydtgo-top-wildcard-le',
}

# 分发目标：OSS 自定义域名
OSS_TARGETS = [
    # 根域：原先 CNAME 到 OSS 海外入口、没绑证书，必须修
    {'bucket': 'susuper-ticket-hk', 'region': 'cn-hongkong', 'domain': 'ydtgo.top',
     'dns_rr': '@', 'fix_cname': True},
    # 赚钱案例库（ai-case-library）静态站
    {'bucket': 'ai-case-library', 'region': 'cn-hongkong', 'domain': 'case.ydtgo.top',
     'dns_rr': 'case', 'fix_cname': False},
]

# 分发目标：FC 自定义域名
FC_TARGETS = [
    {'region': 'cn-hongkong', 'domain': 'pan.ydtgo.top',
     'service': 'panradar-svc', 'function': 'panradar'},
]

FORCE = '--force' in sys.argv
FIX_CNAME = '--fix-cname' in sys.argv
THRESHOLD = 30
if '--days' in sys.argv:
    THRESHOLD = int(sys.argv[sys.argv.index('--days') + 1])
T_ARG = None
if '--targets' in sys.argv:
    T_ARG = [x.strip() for x in sys.argv[sys.argv.index('--targets') + 1].split(',')]


def DO(t):
    return T_ARG is None or t in T_ARG


AK = os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_ID', '')
SK = os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_SECRET', '')
if not AK or not SK:
    sys.exit('请先设置 ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET')

BASE = os.environ.get('PANRADAR_CERT_DIR') or os.path.join(
    os.path.expanduser('~'), '.panradar-acme')
CERT_DIR = os.path.join(BASE, CERT['name'])
os.makedirs(CERT_DIR, exist_ok=True)
FULLCHAIN = os.path.join(CERT_DIR, 'fullchain.pem')
PRIVKEY = os.path.join(CERT_DIR, 'privkey.pem')
ACCOUNT_KEY = os.path.join(BASE, 'account.key')
STATE = os.path.join(CERT_DIR, 'state.json')


def log(msg):
    print('[%s] %s' % (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), msg), flush=True)


def load_state():
    import json
    if os.path.exists(STATE):
        try:
            return json.load(open(STATE, encoding='utf-8'))
        except Exception:
            pass
    return {}


def save_state(**kw):
    import json
    s = load_state()
    s.update(kw)
    json.dump(s, open(STATE, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)


from cryptography.hazmat.primitives import serialization    # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa   # noqa: E402
from cryptography import x509                               # noqa: E402

from alibabacloud_tea_openapi import models as openapi_models       # noqa: E402
from alibabacloud_alidns20150109.client import Client as DnsClient  # noqa: E402
from alibabacloud_alidns20150109 import models as dns_models        # noqa: E402


def cfg(endpoint):
    c = openapi_models.Config(access_key_id=AK, access_key_secret=SK)
    c.endpoint = endpoint
    return c


dns = DnsClient(cfg('alidns.cn-hangzhou.aliyuncs.com'))


def days_left(path):
    if not os.path.exists(path):
        return -1
    cert = x509.load_pem_x509_certificate(open(path, 'rb').read())
    return (cert.not_valid_after_utc - datetime.now(timezone.utc)).days


def traditional_pem(key):
    """FC / CAS 只认传统 RSA PEM，PKCS8 会被拒"""
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()).decode()


def load_local():
    pem = open(FULLCHAIN, encoding='utf-8').read()
    key = serialization.load_pem_private_key(open(PRIVKEY, 'rb').read(), password=None)
    return pem, traditional_pem(key)


def wait_txt(rr, value, timeout=240):
    """轮询公共 DNS，确认 TXT 已生效再让 OSS 去校验"""
    import subprocess
    fqdn = ROOT if rr == '@' else rr + '.' + ROOT
    for _ in range(timeout // 20):
        try:
            out = subprocess.run(['nslookup', '-type=TXT', fqdn, '223.5.5.5'],
                                 capture_output=True, text=True, timeout=40).stdout
            if value in out:
                return True
        except Exception:
            pass
        time.sleep(20)
    return False


# ---------------- 签发 ----------------
def issue_cert():
    from cryptography.hazmat.primitives import hashes
    from cryptography.x509.oid import NameOID
    import josepy as jose
    from acme import client, messages, challenges

    added = []

    def add_txt(name, value):
        rr = name[: -len('.' + ROOT)] if name.endswith('.' + ROOT) else name
        rid = dns.add_domain_record(dns_models.AddDomainRecordRequest(
            domain_name=ROOT, rr=rr, type='TXT', value=value, ttl=600)).body.record_id
        added.append(rid)
        log('已添加 TXT %s' % rr)

    def cleanup():
        for rid in added:
            try:
                dns.delete_domain_record(dns_models.DeleteDomainRecordRequest(record_id=rid))
            except Exception:
                pass

    os.makedirs(BASE, exist_ok=True)
    if os.path.exists(ACCOUNT_KEY):
        acc_key = serialization.load_pem_private_key(
            open(ACCOUNT_KEY, 'rb').read(), password=None)
    else:
        acc_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        open(ACCOUNT_KEY, 'wb').write(acc_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))

    jwk = jose.JWKRSA(key=acc_key)
    net = client.ClientNetwork(jwk, user_agent='ydtgo-acme/1.0')
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
        # 账号已存在：ConflictError 带 location，用它恢复 kid
        net.account = messages.RegistrationResource(
            body=messages.Registration.from_data(email=EMAIL, terms_of_service_agreed=True),
            uri=loc)

    if os.path.exists(PRIVKEY):
        cert_key = serialization.load_pem_private_key(
            open(PRIVKEY, 'rb').read(), password=None)
    else:
        cert_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        open(PRIVKEY, 'wb').write(cert_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))

    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([
               x509.NameAttribute(NameOID.COMMON_NAME, CERT['domains'][0])]))
           .add_extension(x509.SubjectAlternativeName(
               [x509.DNSName(d) for d in CERT['domains']]), critical=False)
           .sign(cert_key, hashes.SHA256()))

    log('下单 %s' % CERT['domains'])
    order = acme.new_order(csr.public_bytes(serialization.Encoding.PEM))

    tasks = []
    for authz in order.authorizations:
        for ch in authz.body.challenges:
            if isinstance(ch.chall, challenges.DNS01):
                tasks.append((ch, ch.chall.validation_domain_name(
                    authz.body.identifier.value), ch.chall.validation(jwk)))

    try:
        for ch, name, value in tasks:
            add_txt(name, value)
        log('等待 DNS 生效 70 秒')
        time.sleep(70)
        for ch, name, value in tasks:
            acme.answer_challenge(ch, ch.chall.response(jwk))
        order = acme.poll_authorizations(order, datetime.now() + timedelta(seconds=600))
        final = acme.finalize_order(order, deadline=datetime.now() + timedelta(seconds=300))
    finally:
        cleanup()

    pem = final.fullchain_pem
    open(FULLCHAIN, 'w', encoding='utf-8').write(pem)
    crt = x509.load_pem_x509_certificate(pem.encode())
    log('新证书已签发，有效期至 %s' % crt.not_valid_after_utc)
    return pem, traditional_pem(cert_key)


# ---------------- 主流程 ----------------
left = days_left(FULLCHAIN)
log('当前证书剩余 %s 天（阈值 %s），路径 %s' % (left, THRESHOLD, FULLCHAIN))

if DO('cert'):
    if left > THRESHOLD and not FORCE:
        log('无需续期，退出')
        sys.exit(0)
    pem, privkey_pem = issue_cert()
else:
    if left < 0:
        sys.exit('本地没有证书（%s），请先跑一次完整签发' % FULLCHAIN)
    pem, privkey_pem = load_local()
    log('使用本地证书，剩余 %s 天' % left)

# ---------------- 上传 CAS ----------------
cert_id = None
if DO('cas'):
    from alibabacloud_cas20200407.client import Client as CasClient
    from alibabacloud_cas20200407 import models as cas_models

    cas = CasClient(cfg('cas.aliyuncs.com'))
    # 注意：list_user_certificate_order 查不到"上传型"证书，
    # 所以旧 cert_id 只能靠本地 state.json 记录
    old_id = load_state().get('cert_id')
    if old_id:
        try:
            cas.delete_user_certificate(cas_models.DeleteUserCertificateRequest(
                certificate_id=old_id))
            log('已删除 CAS 旧证书 %s' % old_id)
        except Exception as e:
            log('删除旧证书跳过: %s' % str(e)[:80])

    cert_id = cas.upload_user_certificate(cas_models.UploadUserCertificateRequest(
        name=CERT['cas_name'], cert=pem, key=privkey_pem)).body.cert_id
    save_state(cert_id=cert_id)
    log('已上传 CAS，cert_id = %s' % cert_id)
else:
    cert_id = load_state().get('cert_id')
    log('复用 CAS 证书 cert_id = %s' % cert_id)

# ---------------- 分发到 OSS ----------------
if DO('oss') and OSS_TARGETS:
    import oss2
    from oss2 import models as oss_models

    class _Cert(object):
        """oss2 的 cert 参数：需提供 cert_id / certificate / private_key 等字段的对象"""

        def __init__(self, cert_id):
            self.cert_id = str(cert_id) if cert_id else None
            self.certificate = None
            self.private_key = None
            self.previous_cert_id = None
            self.force = 'true'      # 必须是 'true'，用 1 会触发 MalformedXML
            self.delete_certificate = None

    for t in OSS_TARGETS:
        log('处理 OSS %s -> bucket %s' % (t['domain'], t['bucket']))
        bk = oss2.Bucket(oss2.Auth(AK, SK),
                         'https://oss-%s.aliyuncs.com' % t['region'], t['bucket'])

        rr_auth = '_dnsauth' if t['domain'] == ROOT else \
            '_dnsauth.' + t['domain'][: -len('.' + ROOT)]
        token = None
        try:
            token = bk.create_bucket_cname_token(t['domain']).token
            log('  取得归属验证 token')
        except Exception as e:
            log('  取 token 失败（已绑定时正常）: %s' % str(e)[:100])

        auth_rid = None
        if token:
            try:
                exist = dns.describe_domain_records(dns_models.DescribeDomainRecordsRequest(
                    domain_name=ROOT, rrkey_word='_dnsauth', page_number=1, page_size=50))
                for r in (exist.body.domain_records.record or []):
                    if r.rr == rr_auth:
                        dns.delete_domain_record(
                            dns_models.DeleteDomainRecordRequest(record_id=r.record_id))
                        log('  已清除旧 TXT %s' % rr_auth)
            except Exception:
                pass
            auth_rid = dns.add_domain_record(dns_models.AddDomainRecordRequest(
                domain_name=ROOT, rr=rr_auth, type='TXT', value=token,
                ttl=600)).body.record_id
            log('  已写入 TXT %s，等待生效' % rr_auth)
            if not wait_txt(rr_auth, token):
                log('  警告：TXT 迟迟未生效，仍会尝试绑定')

        ok = False
        for attempt in range(3):
            try:
                bk.put_bucket_cname(oss_models.PutBucketCnameRequest(
                    t['domain'], _Cert(cert_id)))
                log('  已绑定自定义域名（cert_id=%s）' % cert_id)
                ok = True
                break
            except Exception as e:
                log('  第 %d 次绑定失败: %s' % (attempt + 1, str(e)[:140]))
                time.sleep(45)

        if auth_rid:
            try:
                dns.delete_domain_record(
                    dns_models.DeleteDomainRecordRequest(record_id=auth_rid))
            except Exception:
                pass
        if not ok:
            continue

        # OSS 按 Host 头匹配自定义域名，所以 CNAME 不一定要改。
        # 只有确认绑定后证书仍不生效，才加 --fix-cname 指到标准 OSS 域名。
        if t.get('fix_cname') and FIX_CNAME:
            want = '%s.oss-%s.aliyuncs.com' % (t['bucket'], t['region'])
            try:
                recs = dns.describe_domain_records(dns_models.DescribeDomainRecordsRequest(
                    domain_name=ROOT, rrkey_word=t['dns_rr'],
                    page_number=1, page_size=50))
                for r in (recs.body.domain_records.record or []):
                    if r.rr == t['dns_rr'] and r.type == 'CNAME':
                        if r.value == want:
                            log('  CNAME 已正确: %s' % want)
                        else:
                            dns.update_domain_record(
                                dns_models.UpdateDomainRecordRequest(
                                    record_id=r.record_id, rr=t['dns_rr'],
                                    type='CNAME', value=want, ttl=600))
                            log('  CNAME 已修正: %s -> %s' % (r.value, want))
            except Exception as e:
                log('  CNAME 修正失败: %s' % str(e)[:140])

# ---------------- 分发到 FC ----------------
if DO('fc') and FC_TARGETS:
    from alibabacloud_fc_open20210406.client import Client as FCClient
    from alibabacloud_fc_open20210406 import models as fc_models

    class SimpleRoute(fc_models.RoutePolicy):
        """SDK 的 RoutePolicy 是新版 condition 结构，
        fc-open 2021-04-06 实际要 path/serviceName/functionName"""

        def __init__(self, path=None, service_name=None, function_name=None):
            self.path = path
            self.service_name = service_name
            self.function_name = function_name

        def validate(self):
            pass

        def to_map(self):
            return {'path': self.path, 'serviceName': self.service_name,
                    'functionName': self.function_name}

    for t in FC_TARGETS:
        fc = FCClient(cfg('fc.%s.aliyuncs.com' % t['region']))
        fc.update_custom_domain(t['domain'], fc_models.UpdateCustomDomainRequest(
            protocol='HTTP,HTTPS',
            route_config=fc_models.RouteConfig(
                routes=[SimpleRoute('/*', t['service'], t['function'])]),
            cert_config=fc_models.CertConfig(
                cert_name=CERT['cas_name'], certificate=pem, private_key=privkey_pem)))
        log('FC 自定义域名 %s 证书已更新' % t['domain'])

log('全部完成')
print('RENEW_OK')
