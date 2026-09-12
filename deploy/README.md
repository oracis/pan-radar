# PanRadar 部署到阿里云（ECS + 纯 Python systemd）

适用：把 pan-radar 作为一个常驻 Web 服务跑在阿里云 ECS 上，域名 `pan.ydtgo.top`，
对外提供网盘资源搜索。零依赖（仅 Python 标准库），进程由 systemd 托管。

> 你说「参照我已有的网站」——本手册的 TLS/证书部分请**套用你现有站点的证书与自动续期机制**
> （你三个站点 susuper/concert/book.ydtgo.top 在 OSS 上、证书定期自动续期）。下面给出两种 TLS 方案，
> 选与你现有套路一致的那一种即可。

---

## 1. 准备 ECS
- 镜像：Ubuntu 22.04 LTS（或其它带 `python3` 的 Linux）
- 确认 `python3 --version` ≥ 3.8（标准库 `http.server` 即可，无需 pip）
- **安全组**：入方向放行 `80/tcp`、`443/tcp`，以及 `8931/tcp`（仅当用 CDN/SLB 直连回源时才需暴露公网；
  用 nginx 反代则只放行 80/443，8931 仅本机监听）

## 2. 域名解析
- 阿里云「云解析 DNS」给 `pan.ydtgo.top` 加一条 **A 记录** → ECS 公网 IP
- 等待生效：`ping pan.ydtgo.top` 解析到该 IP

## 3. 上传代码
方式 A（推荐，已从 GitHub 推送）：
```bash
git clone https://github.com/oracis/pan-radar.git /tmp/pan-radar
```
方式 B（从本机 scp）：
```bash
scp -r /本地/pan-radar  root@<ECS公网IP>:/tmp/pan-radar
```

## 4. 安装并启动服务
```bash
cd /tmp/pan-radar
sudo bash deploy/install.sh
```
脚本会：建 `panradar` 用户 → 拷贝到 `/opt/panradar` → 装 systemd 单元 → 起服务 → 放行防火墙。
自检：
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8931/   # 期望 200
journalctl -u panradar -n 50 --no-pager                          # 看日志
```

## 5. TLS / 对外暴露（二选一，套用你现有证书机制）

### 方案 A：阿里云 CDN / SLB 终结 TLS（推荐，最贴合「已有网站」套路）
1. 在 CDN 或 SLB 上绑定域名 `pan.ydtgo.top`，上传/关联你**已有的 SSL 证书**（与你其它站点共用自动续期）。
2. 回源地址填 ECS 公网 IP + 端口 `8931`。
3. 因为回源走公网 IP，需要让 Python 监听 `0.0.0.0`：
   ```bash
   # 编辑 /etc/systemd/system/panradar.service，把 --host 127.0.0.1 改为 0.0.0.0
   sudo sed -i 's/--host 127.0.0.1/--host 0.0.0.0/' /etc/systemd/system/panradar.service
   sudo systemctl daemon-reload && sudo systemctl restart panradar
   ```
4. 安全组只放行 `8931/tcp`（或限定 CDN 回源 IP 段），`80/443` 由 CDN/SLB 接管。

### 方案 B：ECS 上 nginx + certbot 反代（证书走 Let's Encrypt，或换成你的阿里云证书）
```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx
sudo cp /tmp/pan-radar/deploy/nginx-pan.ydtgo.top.conf /etc/nginx/sites-available/pan.ydtgo.top
sudo ln -sf /etc/nginx/sites-available/pan.ydtgo.top /etc/nginx/sites-enabled/
# 用你已有的证书机制替换下面这行的证书路径，或先 certbot 申请：
sudo certbot --nginx -d pan.ydtgo.top
sudo nginx -t && sudo systemctl reload nginx
```
Python 保持 `127.0.0.1:8931`（nginx 反代），安全组只需放行 `80/443`。

## 6. 验证
- 浏览器打开 `https://pan.ydtgo.top/` → 应能搜索（搜「风间影月」走顺藤摸瓜应能出结果）
- 更新：`cd /opt/panradar && git pull && sudo systemctl restart panradar`
- 监控：`systemctl status panradar`、`journalctl -u panradar -f`

## 备注
- 出网：PanRadar 需要访问 PanSou 等上游。若 ECS 出网需走代理，取消 `panradar.service`
  里 `HTTP_PROXY/HTTPS_PROXY` 两行注释并填你的代理（注意：之前在本地「绕过代理」是另一种场景，
  ECS 上按你网络实际决定）。
- 数据：缓存库在 `/opt/panradar/data/panradar.db`，重启不丢；如要清缓存删该文件即可。
