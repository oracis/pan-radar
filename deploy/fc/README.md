# PanRadar 部署到阿里云函数计算（FC）

## 当前线上形态

**OSS 静态前端（香港）+ FC 聚合层（香港）**，这是实测跑通并正在使用的方案：

| 组件 | 地址 | 说明 |
| --- | --- | --- |
| 静态前端 | `https://panradar-ydtgo-hk.oss-cn-hongkong.aliyuncs.com/` | 桶 `panradar-ydtgo-hk`，公开读 + 静态网站托管 |
| 聚合层 | `https://panradar-panradar-svc-neqacybvqm.cn-hongkong.fcapp.run` | 服务 `panradar-svc` / 函数 `panradar`，custom runtime + zip |

前端只调 FC 的 `/api/*`，后端已加 `Access-Control-Allow-Origin: *` 与 `OPTIONS` 预检，跨域无障碍。

**为什么必须由服务端聚合**：主源 `so.252035.xyz` 的 CORS 是开放的，但 `pansou.app` 无 CORS、
`misoso` / `hunhepan` 是 http（会被混合内容拦截）——浏览器拉不动，多源聚合只能在 FC 侧完成。

**为什么用香港**：上海桶的公开读会被账号安全策略拦截（`EC 0015-00000501`），
香港桶创建时带 `public-read` ACL 才生效；FC 迁到同地域省掉跨地域延迟。

---

## 一键部署（推荐，无需 Docker / Serverless Devs）

### 0. 前置条件

1. 阿里云 AccessKey（RAM，需「函数计算」+「OSS」权限），用环境变量传入，**不要写进仓库**：
   ```bash
   export ALIBABA_CLOUD_ACCESS_KEY_ID=...
   export ALIBABA_CLOUD_ACCESS_KEY_SECRET=...
   ```
   Windows PowerShell：
   ```powershell
   $env:ALIBABA_CLOUD_ACCESS_KEY_ID='...'
   $env:ALIBABA_CLOUD_ACCESS_KEY_SECRET='...'
   ```
2. Python 依赖（仅部署用，项目本体仍是零依赖）：
   ```bash
   pip install alibabacloud_fc_open20210406 alibabacloud_tea_openapi alibabacloud_tea_util oss2
   ```

### 1. 打包代码

```bash
python deploy/fc/_build_fc_code.py
```

产出 `deploy/fc/code.zip`（含 `panradar.py`、`config.json`、`bootstrap` 0755、`web/`）。
`bootstrap` 的可执行位在 Windows 打 zip 时常丢失，所以函数不依赖它 ——
`_deploy_fc.py` 用 `customRuntimeConfig.command` 直接拉起 `python3 panradar.py`，绕开这个经典坑。

### 2. 部署 FC 聚合层

```bash
python _deploy_fc.py
```

会创建（已存在则更新）service → function → http trigger，并打印：

```
url_internet: https://panradar-panradar-svc-neqacybvqm.cn-hongkong.fcapp.run
```

地域在脚本顶部改：`REGION = 'cn-hongkong'`。

### 3. 部署 OSS 静态前端

把第 2 步拿到的地址填进 `_deploy_oss.py` 的 `FC_URL`，然后：

```bash
python _deploy_oss.py
```

会建桶（香港）、删掉桶级 `public access block`、开静态网站托管、上传 `web/`，
并**在上传时把 `config.js` 里的 `API_BASE` 注入成 FC 地址**（同时落到 `config.js` 与 `static/config.js`）。

> 新桶会被账号策略自动加上「阻止公开访问」，不删掉的话匿名访问一律 403：
> `AccessDenied "You have no right to access this object because of bucket acl"`。

### 4. 验证

```bash
# 后端存活
curl -s -w "\nHTTP:%{http_code}\n" https://panradar-panradar-svc-neqacybvqm.cn-hongkong.fcapp.run/api/meta

# 端到端搜索（注意参数名是 main，不是 q）
curl -s "https://panradar-panradar-svc-neqacybvqm.cn-hongkong.fcapp.run/api/search?main=%E9%A3%8E%E9%97%B4%E5%BD%B1%E6%9C%88"

# 前端注入是否正确
curl -s https://panradar-ydtgo-hk.oss-cn-hongkong.aliyuncs.com/static/config.js
```

预期：搜索返回 `ok: true`，「风间影月」能聚类出「慕课网-Java高级工程师（风间影月）」。

---

## 注意事项（务必看）

- **首次搜索约 100 秒**：冷启动 + 4 源并发 + 重试，是正常的。FC `timeout: 120s` 刚好兜住，
  调小会直接超时。前端每秒刷新「已等待 N 秒」，别刷新页面。
- **API 参数名是 `main`**：`/api/search?main=关键词&author=&deep=1&clouds=quark,baidu&refresh=1`。
  用 `q` 会拿到 `{"ok": false, "error": "请输入课程名或作者名"}`。
- **缓存会随实例冷启动清空**：`PANRADAR_DATA_DIR=/tmp/panradar`，`/code` 只读；
  FC 冷启动会重置 `/tmp`，所以「⟳ 再挖一次」的累积效果只在同一个 warm 实例内有效。
  要跨实例持久得挂 NAS 或改用 OTS。
- **出公网必须开**：`internetAccess: true`，否则函数访问不到 PanSou 源。
- **改了前端必须强刷**：`Ctrl+F5`。浏览器缓存旧 JS 时，服务端已是新版、前端还在跑旧代码。
- **自定义域名未启用**：`pan.ydtgo.top` 目前没有解析到 OSS/FC，`curl` 返回 `000`。
  `s.yaml` 里预留了 `customDomains` 配置段（注释状态），有证书时取消注释即可。

---

## 备选：Serverless Devs（s.yaml）

不想用 OpenAPI 脚本时，可用 `deploy/fc/s.yaml`（同样是 custom runtime + zip，地域已改为 `cn-hongkong`）：

```bash
npm i -g @serverless-devs/s
s config add          # 填入 AccessKey，别名 default
python deploy/fc/_build_fc_code.py
s deploy -t deploy/fc/s.yaml
```

> `s.yaml` 里的 `customDomains` 段默认注释，需要 `pan.ydtgo.top` + 已有证书时再打开。

### 备选：Docker 自定义容器

`Dockerfile` 仍在（`python:3.12-slim`）。但当前线上版本**没有**走容器 —— zip 上传更轻、
不用维护 ACR 仓库，且 custom runtime 基础镜像自带 python3，够用。容器方案仅作退路保留。
