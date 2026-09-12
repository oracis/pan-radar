import os, oss2
AK = os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_ID', '')
SK = os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_SECRET', '')
if not AK or not SK:
    raise SystemExit('请先设置 ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET 环境变量')
try:
    auth = oss2.Auth(AK, SK)
    s = oss2.Service(auth, 'https://oss-cn-hangzhou.aliyuncs.com')
    bs = s.list_buckets()
    print("AK 有效，桶数量:", len(bs.buckets))
    for b in bs.buckets:
        print("  name=%s region=%s created=%s" % (b.name, b.location, b.creation_date))
except Exception as e:
    print("ERROR:", type(e).__name__, e)
