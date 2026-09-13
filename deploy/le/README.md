# PanRadar 证书自动续期（Let's Encrypt）

## 为什么需要这个

`pan.ydtgo.top` 用的是 Let's Encrypt 证书，**有效期只有 90 天**。
本目录下 `renew_cert.py` 做三件事：

1. 读本地证书，剩余有效期 > 30 天就直接退出（所以可以放心每天跑）
2. 用 **DNS-01** 自动完成验证（自动往阿里云 DNS 写/删 `_acme-challenge` TXT 记录）
3. 把新证书推到 FC 自定义域名 `pan.ydtgo.top`

证书覆盖 `pan.ydtgo.top` 与 `*.pan.ydtgo.top`（通配符，以后加 `api.pan.ydtgo.top` 之类不用重签）。

## 安装

```bash
pip install acme cryptography alibabacloud_alidns20150109 alibabacloud_fc_open20210406
```

凭证走环境变量（**不要写进仓库**）：

```powershell
setx ALIBABA_CLOUD_ACCESS_KEY_ID "<你的AK>"
setx ALIBABA_CLOUD_ACCESS_KEY_SECRET "<你的SK>"
```

（重开终端后生效）

## 手动跑一次

```bash
python deploy/le/renew_cert.py            # 剩余 > 30 天会跳过
python deploy/le/renew_cert.py --force    # 强制续期
python deploy/le/renew_cert.py --days 15  # 换阈值
```

## 挂 Windows 计划任务（每天 04:00）

```cmd
schtasks /create /tn "PanRadarCertRenew" /tr "\"C:\Users\DELL\.workbuddy\binaries\python\envs\default\Scripts\python.exe\" \"C:\Users\DELL\WorkBuddy\2026-09-11-15-10-58\pan-radar\deploy\le\renew_cert.py\"" /sc daily /st 04:00 /f
```

查看 / 删除：

```cmd
schtasks /query /tn "PanRadarCertRenew"
schtasks /delete /tn "PanRadarCertRenew" /f
```

> 若你把仓库挪到了别的目录，记得同步改计划任务里的路径。

## 几个实现细节

- **账号密钥**存在 `C:\Users\DELL\.panradar-acme\account.key`，证书在
  `C:\Users\DELL\.panradar-acme\pan.ydtgo.top\{fullchain.pem,privkey.pem}`。
  整个目录都在仓库外，不会被提交。
- **ACME 账号已存在时会返回 409**，异常里带着账号 URL，脚本从 `e.location` 取出继续用，
  不会重复建账号。
- **私钥要转成传统 RSA PEM**（`BEGIN RSA PRIVATE KEY`）再传给 FC，
  PKCS8 格式 FC 会报 `'private key' has to be in PEM format`。
- DNS 生效等待固定 70 秒。阿里云 DNS 通常几秒就生效，留足余量避免 LE 校验打空。
