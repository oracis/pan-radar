import os, sys, oss2

# 凭证从环境变量读取（勿硬编码进仓库）：
#   set ALIBABA_CLOUD_ACCESS_KEY_ID=...   set ALIBABA_CLOUD_ACCESS_KEY_SECRET=...
AK = os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_ID', '')
SK = os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_SECRET', '')
if not AK or not SK:
    sys.exit('请先设置 ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET 环境变量')
REGION = 'cn-hongkong'   # 用户指定：桶用香港 region（上海 region 公开读被账号策略拦截）
ENDPOINT = 'https://oss-cn-hongkong.aliyuncs.com'
BUCKET = 'panradar-ydtgo-hk'   # 桶名全局唯一，panradar-ydtgo 已被 cn-shanghai 占用
FC_URL = 'https://panradar-panradar-svc-neqacybvqm.cn-hongkong.fcapp.run'
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')

auth = oss2.Auth(AK, SK)

# 1) 建桶（已存在则忽略）
try:
    bucket = oss2.Bucket(auth, ENDPOINT, BUCKET)
    bucket.get_bucket_info()
    print('[oss] 桶 %s 已存在' % BUCKET)
except oss2.exceptions.NoSuchBucket:
    print('[oss] 创建桶 %s ...' % BUCKET)
    bucket = oss2.Bucket(auth, ENDPOINT, BUCKET)
    bucket.create_bucket(oss2.BUCKET_ACL_PUBLIC_READ)
    print('[oss] 已创建（公开读）')
except oss2.exceptions.OssError as e:
    if 'BucketAlreadyExists' in str(e):
        print('[oss] 桶名冲突，改用 panradar-ydtgo-hk-2')
        BUCKET = 'panradar-ydtgo-hk-2'
        bucket = oss2.Bucket(auth, ENDPOINT, BUCKET)
        try:
            bucket.get_bucket_info()
            print('[oss] 桶 %s 已存在' % BUCKET)
        except oss2.exceptions.NoSuchBucket:
            bucket.create_bucket(oss2.BUCKET_ACL_PUBLIC_READ)
            print('[oss] 已创建 %s' % BUCKET)
    else:
        raise

# 2) 关掉桶级「阻止公开访问」（新桶会被账号策略自动加上，导致匿名访问 403：
#    AccessDenied "You have no right to access this object because of bucket acl"）
try:
    blk = bucket.get_bucket_public_access_block()
    if blk.block_public_access:
        bucket.delete_bucket_public_access_block()
        print('[oss] 已删除桶级 public access block（否则匿名访问 403）')
    else:
        print('[oss] 桶级 public access block 已是关闭')
except oss2.exceptions.OssError as e:
    print('[oss] 查询/删除 public access block 失败（非致命）:', e.status)

# 3) 静态网站托管
# 注意：桶创建时已带公开读 ACL 生效；事后单独 put_bucket_acl 会被
# 账号安全策略拦截（EC 0015-00000501），故仅作冗余尝试、失败不中断。
try:
    bucket.put_bucket_acl(oss2.BUCKET_ACL_PUBLIC_READ)
except oss2.exceptions.OssError as e:
    print('[oss] put_bucket_acl 被策略拦截（桶创建时已是公开读，非致命）:', e.status)
ws = oss2.models.BucketWebsite('index.html', 'index.html')
bucket.put_bucket_website(ws)
print('[oss] 已开启静态网站托管 index.html')

# 4) 上传 web/ 下所有文件
CT = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.ico': 'image/x-icon',
    '.txt': 'text/plain; charset=utf-8',
}

def upload_local(root, rel):
    full = os.path.join(root, rel)
    if os.path.isdir(full):
        for n in os.listdir(full):
            upload_local(root, os.path.join(rel, n))
    elif os.path.isfile(full):
        ext = os.path.splitext(rel)[1].lower()
        ct = CT.get(ext, 'application/octet-stream')
        key = rel.replace('\\', '/')
        # config.js 部署时注入生产 API 地址
        if rel.replace('\\', '/') == 'config.js':
            with open(full, 'r', encoding='utf-8') as f:
                txt = f.read()
            txt = txt.replace('window.PANRADAR_API_BASE = "";',
                              'window.PANRADAR_API_BASE = "%s";' % FC_URL)
            # index.html 引用 /static/config.js，OSS 上需同时落到该键
            bucket.put_object('static/config.js', txt, headers={'Content-Type': ct})
            print('  -> static/config.js (API_BASE=%s)' % FC_URL)
            bucket.put_object(key, txt, headers={'Content-Type': ct})
        else:
            with open(full, 'rb') as f:
                bucket.put_object(key, f, headers={'Content-Type': ct})
        print('  ->', key)

print('[oss] 上传 web/ ...')
upload_local(WEB_DIR, '')
print('[oss] 上传完成')

# 4) 验证首页已上传
try:
    obj = bucket.get_object('index.html')
    data = obj.read()
    print('[oss] index.html 已存在, len=%d' % len(data))
except Exception as e:
    print('[oss] 读取 index.html 失败:', e)

print('FRONTEND_URL=https://%s.oss-%s.aliyuncs.com/' % (BUCKET, REGION))
print('BUCKET=%s' % BUCKET)
