# ydtgo.top 证书管理（Let's Encrypt）

## 这个脚本管什么

一张**通配证书** `ydtgo.top + *.ydtgo.top`，覆盖域名下所有子域，并自动分发到
OSS 自定义域名和 FC 自定义域名。

| 域名 | 载体 | 说明 |
| --- | --- | --- |
| `ydtgo.top` | OSS `susuper-ticket-hk`（香港） | 原先 CNAME 到 OSS 海外入口、用 OSS 默认证书，主机名不匹配 |
| `pan.ydtgo.top` | FC `panradar-svc/panradar`（香港） | PanRadar 站点 |
| book / concert / susuper / yiying | OSS 香港桶 | 已有证书由上游自动续期，本脚本不接管，但通配证书可兜底 |

证书有效期 90 天，`cert_manager.py` 做四件事：

1. 读本地证书，剩余 > 30 天直接退出（可以放心每天跑）
2. 用 **DNS-01** 自动验证（自动写/删阿里云 DNS 的 `_acme-challenge` TXT）
3. 上传到阿里云证书服务（CAS），拿到 `cert_id`
4. 分发：OSS 绑自定义域名 + 证书、FC 更新自定义域名证书

## 安装

```bash
pip install acme cryptography oss2 \
            alibabacloud_alidns20150109 alibabacloud_cas20200407 alibabacloud_fc_open20210406
```

凭证走环境变量（**不要写进仓库**）：

```powershell
setx ALIBABA_CLOUD_ACCESS_KEY_ID "<你的AK>"
setx ALIBABA_CLOUD_ACCESS_KEY_SECRET "<你的SK>"
```

（重开终端后生效）

## 用法

```bash
python deploy/le/cert_manager.py                      # 剩余 > 30 天会跳过
python deploy/le/cert_manager.py --force              # 强制重新签发
python deploy/le/cert_manager.py --days 15            # 换阈值
python deploy/le/cert_manager.py --targets cert,cas   # 只签发并上传，不动线上
python deploy/le/cert_manager.py --targets oss,fc     # 用本地已有证书重新分发
python deploy/le/cert_manager.py --targets oss --fix-cname   # 顺带把 CNAME 指到标准 OSS 域名
```

## 挂 Windows 计划任务（每天 04:00）

```cmd
schtasks /create /tn "YdtgoCertRenew" /tr "\"C:\Users\DELL\.workbuddy\binaries\python\envs\default\Scripts\python.exe\" \"<仓库路径>\deploy\le\cert_manager.py\"" /sc daily /st 04:00 /f
```

查看 / 删除：

```cmd
schtasks /query /tn "YdtgoCertRenew"
schtasks /delete /tn "YdtgoCertRenew" /f
```

> 若把仓库挪到别的目录，记得同步改计划任务里的路径。

## 踩过的坑

这几条都是实际撞出来的，改脚本前先看一眼：

- **CAS 免费证书额度会耗尽**（`InsufficientQuota`），所以走 Let's Encrypt 而不是阿里云免费证书。
- **`list_user_certificate_order` 查不到"上传型"证书**，所以旧 `cert_id` 只能记在
  本地 `state.json`，续期时靠它删旧证书，否则 CAS 里会越堆越多。
- **私钥要传统 RSA PEM**（`BEGIN RSA PRIVATE KEY`），PKCS8 会被 FC 拒：
  `'private key' has to be in PEM format`。
- **OSS 的 `Force` 字段必须是字符串 `'true'`**，传 `1` 会报 `MalformedXML`，
  而且这个错误会盖住真正的 `NeedVerifyDomainOwnership`，非常容易误判。
- **绑定 OSS 自定义域名要先验证归属**：写 `_dnsauth.<域>` TXT = `create_bucket_cname_token()`
  返回的 token，等 TXT 生效再 `put_bucket_cname`。已绑定后再取 token 会返回
  `NoNeedCreateCnameToken`，属正常。
- **OSS 证书下发有 3~5 分钟延迟**，绑完立刻测会看到旧证书，别急着回滚。
- **OSS 按 Host 头匹配自定义域名**，CNAME 指向 OSS 海外入口（`*.thepacificphs.com`）时
  自定义证书不生效，必须 CNAME 到标准域名 `<bucket>.oss-<region>.aliyuncs.com`。
- **ACME 账号已存在时返回 409**，异常里带账号 URL（`e.location`），取出来接着用即可。
- DNS TXT 生效等待 70 秒；OSS 归属验证的 TXT 会轮询公共 DNS 确认生效再继续。

## 文件位置

凭据和证书都在仓库外：

```
C:\Users\DELL\.panradar-acme\
├─ account.key                      # ACME 账号密钥
└─ ydtgo-top-wildcard\
   ├─ fullchain.pem
   ├─ privkey.pem
   └─ state.json                    # 记录 CAS cert_id
```
