import os, sys, base64, json
from alibabacloud_fc_open20210406.client import Client as FCClient
from alibabacloud_fc_open20210406 import models as fc_models
from alibabacloud_tea_openapi import models as openapi_models
from alibabacloud_tea_util import models as util_models
from Tea.exceptions import TeaException

# 凭证从环境变量读取（勿硬编码进仓库）：
#   set ALIBABA_CLOUD_ACCESS_KEY_ID=...   set ALIBABA_CLOUD_ACCESS_KEY_SECRET=...
AK = os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_ID', '')
SK = os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_SECRET', '')
if not AK or not SK:
    sys.exit('请先设置 ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET 环境变量')
REGION = 'cn-shanghai'
SERVICE = 'panradar-svc'
FUNCTION = 'panradar'
CODE_ZIP = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'deploy', 'fc', 'code.zip')

config = openapi_models.Config(access_key_id=AK, access_key_secret=SK)
config.endpoint = 'fc.%s.aliyuncs.com' % REGION
client = FCClient(config)

def call(fn):
    try:
        return fn(), None
    except TeaException as e:
        return None, e
    except Exception as e:
        return None, e

def status_of(e):
    """从 SDK 异常里尽量抽出 HTTP 状态码（ClientException 的 status_code 不一定在属性上）"""
    for attr in ('status_code', 'statusCode'):
        v = getattr(e, attr, None)
        if v:
            try:
                return int(v)
            except Exception:
                pass
    d = getattr(e, 'data', None)
    if isinstance(d, dict):
        v = d.get('statusCode') or d.get('status_code')
        if v:
            try:
                return int(v)
            except Exception:
                pass
    import re
    m = re.search(r'statusCode[\":\s]*(\d{3})', str(e))
    if not m:
        m = re.search(r'code:\s*(\d{3})', str(e))
    if m:
        return int(m.group(1))
    return None

# 1) Service（internet_access 在服务级）：先建，已存在则更新
try:
    client.create_service(fc_models.CreateServiceRequest(
        service_name=SERVICE, description='PanRadar 网盘资源雷达', internet_access=True))
    print('[service] 已创建（含公网访问）')
except Exception as e:
    st = status_of(e)
    if st == 409:
        print('[service] 已存在，确保开启公网访问...')
        try:
            client.update_service(service_name=SERVICE,
                                  request=fc_models.UpdateServiceRequest(internet_access=True))
            print('[service] 已更新 internet_access=True')
        except Exception as e2:
            print('[service] 更新 internet_access 失败（非致命）:', e2)
    else:
        print('[service] 创建异常(status=%s): %s' % (st, e))
        raise

# 2) Function (custom runtime + zip)
with open(CODE_ZIP, 'rb') as f:
    zip_b64 = base64.b64encode(f.read()).decode('ascii')

env = {'PANRADAR_DATA_DIR': '/tmp/panradar'}
# 直接指定启动命令，绕开 FC 对 zip 内 bootstrap 可执行位的依赖（Windows 打 zip 经典坑）
crc = fc_models.CustomRuntimeConfig(command=['python3', 'panradar.py', '--host', '0.0.0.0', '--port', '9000', '--no-browser'])
fn_req = fc_models.CreateFunctionRequest(
    function_name=FUNCTION,
    runtime='custom',
    handler='dummy.handler',
    memory_size=512,
    timeout=120,
    ca_port=9000,
    custom_runtime_config=crc,
    code=fc_models.Code(zip_file=zip_b64),
    environment_variables=env,
)

# 先尝试更新；若服务/函数不存在(404)则创建
try:
    up = fc_models.UpdateFunctionRequest(
        runtime='custom', handler='dummy.handler', memory_size=512, timeout=120,
        ca_port=9000,
        custom_runtime_config=crc,
        code=fc_models.Code(zip_file=zip_b64),
        environment_variables=env,
    )
    client.update_function(service_name=SERVICE, function_name=FUNCTION, request=up)
    print('[function] 已更新')
except Exception as e:
    if status_of(e) == 404:
        print('[function] 不存在，创建中...')
        client.create_function(service_name=SERVICE, request=fn_req)
        print('[function] 已创建')
    else:
        raise

# 3) Trigger (HTTP)
TRIGGER = 'httpTrigger'
_, err = call(lambda: client.get_trigger(service_name=SERVICE, function_name=FUNCTION, trigger_name=TRIGGER))
if err and status_of(err) == 404:
    print('[trigger] 不存在，创建中...')
    treq = fc_models.CreateTriggerRequest(
        trigger_name=TRIGGER,
        trigger_type='http',
        trigger_config=json.dumps({'authType': 'anonymous',
                                   'methods': ['GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS']}),
    )
    resp = client.create_trigger(service_name=SERVICE, function_name=FUNCTION, request=treq)
    print('[trigger] 已创建. url=%s' % getattr(resp.body, 'url', None))
else:
    print('[trigger] 已存在，跳过')

# 再次读取触发器 URL
try:
    g = client.get_trigger(service_name=SERVICE, function_name=FUNCTION, trigger_name=TRIGGER)
    print('=== TRIGGER URL ===')
    print('url_internet:', getattr(g.body, 'url_internet', None))
    print('url_intranet:', getattr(g.body, 'url_intranet', None))
    print('domain_name :', getattr(g.body, 'domain_name', None))
except Exception as e:
    print('读取触发器 URL 失败:', e)

print('DONE')
