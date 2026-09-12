# PanRadar 部署到阿里云函数计算（FC）

## 为什么用 FC 而不是 ECS

- **Serverless，按请求计费**：空闲时为 0 成本，不养常驻虚拟机；比 ECS 轻得多。
- **自定义容器**：pan-radar 是零依赖 Python，用 `python:3.12-slim` 打镜像，直接跑现有 `panradar.py`，几乎不改代码。
- **可绑自定义域名 + 现有证书**：`pan.ydtgo.top` 走 FC 自定义域名，挂你已有的 SSL 证书。

---

## 前置条件

1. 阿里云账号 + **AccessKey（RAM，授予「函数计算」与「容器镜像服务」权限）**。
2. 本地安装 [Serverless Devs](https://www.serverless-devs.com/)：
   ```bash
   npm i -g @serverless-devs/s
   s config add        # 填入你的 AccessKey，起个别名（s.yaml 里写 default）
   ```
3. 本地安装 **Docker**（用于构建镜像）。
4. 控制台开通 **函数计算 FC** 与 **容器镜像服务 ACR（个人版即可）**，并在 ACR 建好命名空间与仓库 `panradar`。
5. 先在**云解析 DNS** 给 `pan.ydtgo.top` 加一条 A 记录，指向 FC 分配的公网 IP（部署后控制台可看到，或先部署再看）。

---

## 部署步骤

### 1. 构建并推送镜像

在仓库根目录执行（把 `<your-namespace>` 换成你的 ACR 命名空间）：

```bash
docker build -f deploy/fc/Dockerfile -t registry.cn-hangzhou.aliyuncs.com/<your-namespace>/panradar:latest .
docker push registry.cn-hangzhou.aliyuncs.com/<your-namespace>/panradar:latest
```

### 2. 改 `deploy/fc/s.yaml` 三处

- `region`：你的 FC 地域（如 `cn-hangzhou`）。
- `customContainerConfig.image`：第 1 步推送的镜像地址。
- `customDomains[0].certConfig.certName`：你现有的 SSL 证书名（在证书服务 / FC 控制台里查）。

### 3. 一条命令部署

```bash
s deploy -t deploy/fc/s.yaml
```

`s` 会创建函数、HTTP 触发器、并绑定 `pan.ydtgo.top`（带上你的证书）。

### 4. 验证

```bash
curl -s -o /dev/null -w "首页: %{http_code}\n" https://pan.ydtgo.top/
curl -s "https://pan.ydtgo.top/api/search?q=%E9%A3%8E%E9%97%B4%E5%BD%B1%E6%9C%88" | head -c 300
```

---

## 注意事项（务必看）

- **出公网访问**：`s.yaml` 已设 `internetAccess: true`，函数才能访问 PanSou 源（`so.252035.xyz` 等）。
  若你的 FC 建在 VPC 内，需额外给 VPC 配 **NAT 网关** 出网。
- **缓存持久性**：FC 的 `/code` 只读，缓存已通过环境变量 `PANRADAR_DATA_DIR=/tmp/panradar` 落到可写目录。
  但**函数实例冷启动会清空 `/tmp`**，所以「再挖一次」的累积缓存只在**同一个 warm 实例**生命周期内有效；
  跨实例 / 冷启动后缓存重置。对个人低频使用基本无感。若需跨实例持久，可挂 **NAS** 或改用 **OTS**，另行处理。
- **超时**：多源搜索含重试可能较久，已设 `timeout: 120s`；如仍不够，可在 `s.yaml` 调大（FC 上限 600s）。
- **单实例并发**：默认单实例串行处理；高并发可上调 `instanceConcurrency`（在 `s.yaml` 加 `instanceConcurrency: 8`）。

---

## 轻量替代：不用 Docker 的 zip 上传（Custom Runtime）

如果你不想碰 Docker，且确认 FC 自定义运行时基础镜像自带 `python3`，可用 zip 上传：

1. 把 `panradar.py` / `config.json` / `web/` / `deploy/fc/bootstrap` 打成一个包。
2. `bootstrap` 需 `chmod +x`（FC 以它为入口，监听 `$FC_SERVER_PORT`）。
3. `s.yaml` 改用：
   ```yaml
   runtime: custom
   customRuntimeConfig:
     port: 9000
     command: [bash, bootstrap]
   ```
4. 其余（触发器 / 自定义域名 / 证书）同上。

> ⚠️ 自定义运行时基础镜像**默认不含 Python**，需自行确认或补装，故**容器方案更稳**，推荐优先用上面的 Docker 流程。

---

## 推荐组合：OSS 静态前端 + FC 聚合层（多源，最轻）

静态走 OSS（和你三个现有站点同套路），多源搜索算力留在 FC（复用上面的 Docker 流程）。
实测 PanSou 主源 `so.252035.xyz` 的 CORS 是开放的，但其它源（pansou.app 无 CORS、misoso/hunhepan 是 http 会被混合内容拦截）
**浏览器不能直接跨域拉**，所以「多源聚合」必须由服务端（FC）完成，前端只调 FC 的 `/api/*`。
这既比纯 ECS 轻，又守住「示例必须搜到」的多源底线。

后端已对 `/api/*` 加了 `Access-Control-Allow-Origin: *` 和 `OPTIONS` 预检支持，OSS 页面跨域调用无障碍。

### 步骤

1. **FC 聚合层**（同上 Docker 流程）：构建/推送镜像、`s deploy -t deploy/fc/s.yaml`。
   给 FC 也绑一个自定义域名最省事，例如 `api.pan.ydtgo.top`（同一个证书）；
   或者直接用 FC 默认地址 `https://<uid>.<region>.fcapp.run`。
2. **OSS 静态前端**：把 `web/` 整个目录上传到 OSS bucket（开静态网站托管），
   用你现有的 CDN / 证书套路把 `pan.ydtgo.top` 指过来——和你另外两个站点一模一样。
3. **填 API 地址**：编辑 `web/config.js`，把
   ```js
   window.PANRADAR_API_BASE = "";
   ```
   改成你的 FC 地址，例如：
   ```js
   window.PANRADAR_API_BASE = "https://api.pan.ydtgo.top";
   ```
   改完重新上传 `config.js` 到 OSS。**本地直接跑 `panradar.py` 时留空即可（同源）。**
4. **验证**：浏览器打开 `https://pan.ydtgo.top/` → 搜索 → 网络面板里 `/api/search` 走的是
   `api.pan.ydtgo.top` 且带 `Access-Control-Allow-Origin` 响应头，结果正常返回。

> 进阶（可选，免跨域）：若你的 CDN 支持路径路由，可把 `pan.ydtgo.top/` 指 OSS、`pan.ydtgo.top/api/*`
> 指 FC，前端 `API_BASE` 留空（同源），连 CORS 都不需要。默认用上面的跨域方案更省事。
