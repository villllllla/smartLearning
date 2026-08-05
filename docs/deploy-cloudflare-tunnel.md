# 部署：Cloudflare Tunnel（本机出站，过渡方案）

把本机的生产栈通过 Cloudflare Tunnel 暴露到公网。服务器**不开任何入站端口**，
cloudflared 主动出站连到 Cloudflare 边缘，TLS 和 DDoS 防护由边缘提供。

链路：`浏览器 → Cloudflare 边缘 → cloudflared(本机) → nginx:80 → backend:8000`

> 注意 nginx 是链路的一部分：它提供前端静态页、安全响应头，并设置
> `X-Forwarded-For`。**不要像旧的 ngrok 脚本那样直接打到 8000**，那会绕过这些。

## 部署实况

| 项 | 值 |
|---|---|
| 公网地址 | `https://sl.zz34zz.uk` |
| 隧道名 / UUID | `smartlearning` / `d7e0e506-6ac8-42a6-ba75-047624c14deb` |
| 隧道配置 | `C:\Users\zz34z\.cloudflared\config.yml` |
| 隧道凭证 | `C:\Users\zz34z\.cloudflared\d7e0e506-6ac8-42a6-ba75-047624c14deb.json` |
| 域名注册商 | Cloudflare Registrar（域名已在账号内，无需改 NS） |

### 已完成（2026-08-01）

- 生产栈跑通：鉴权强制、API schema 不外泄、安全响应头、限流按 IP 生效
- `.env.cloud` 已生成（密钥沿用 dev，故库里已加密的 Provider Key 仍可解开）
- `docker-compose.prod.yml`：nginx 只绑 `127.0.0.1:80`，数据绑挂 `./backend/data`
- 隧道已建、DNS CNAME 已绑、`tunnel ingress validate` 通过
- 公网验证：`/` 200、`/api/health` 200、`/api/todos` 401、`/openapi.json` 走 SPA 兜底
- 公网登录链路验证：`POST /api/auth/login` 200 → JWT → `/api/wiki` 1 条、`/api/providers` 2 个
- 已禁用睡眠：`standby-timeout-ac=0`、`hibernate-timeout-ac=0`
- 前端登录路由 bug 已修（`/login` 曾被短接成跳回 `/wiki`，导致开启鉴权后无限重定向白屏）

### 待办（需要你手动做）

**1. 注册成 Windows 服务** —— 目前隧道是前台进程，**重启后不会自启**。
在**管理员** PowerShell 里跑：

```powershell
cd D:\Project\smartLearning
Get-Process cloudflared* -ErrorAction SilentlyContinue | Stop-Process -Force   # 先停掉前台实例
.\cloudflared-windows-amd64.exe --config C:\Users\zz34z\.cloudflared\config.yml service install
Get-Service cloudflared    # 确认 Status=Running, StartType=Automatic
```

服务以 LocalSystem 运行，其 home 目录与当前用户不同——所以 `config.yml` 里的
`credentials-file` 必须是绝对路径（已经是）。装完若服务起不来，多半是它没读到
配置，用 `--config` 显式指定即可。

**2. 切飞书 webhook** —— 飞书开放平台 → 事件订阅 → 请求地址改为：

```
https://sl.zz34zz.uk/api/integrations/feishu/events
```

`.env.cloud` 里飞书的 APP_ID / APP_SECRET / VERIFICATION_TOKEN / ALLOWED_OPEN_IDS
已从 `backend/.env` 复用，无需重填。`SL_FEISHU_ENCRYPT_KEY` 目前为空——只影响
事件体加密，**不影响**校验（VERIFICATION_TOKEN 已设，不会走 fail-open 分支）。

**3. 改掉管理员密码** —— 当前密码是脚本生成的，明文存在 `.env.cloud` 里。

### 9.（可选）Cloudflare Access 前置登录

给整个 hostname 加一层 Cloudflare 侧登录，等于在应用鉴权之前再加一道。

⚠️ **必须给飞书 webhook 开 bypass**，否则飞书服务器无法完成 Access 登录，
机器人会全线失效：

- Application 覆盖 `sl.你的域名`
- 加一条 Bypass policy，路径 `/api/integrations/feishu/*`，Everyone

## 日常操作

```powershell
# 起停生产栈
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml logs -f backend

# 隧道状态
Get-Service cloudflared
```

## 坑位备忘

**同一个 SQLite 文件**：生产栈绑挂 `./backend/data`，和 dev 后端是同一个库。
**不要同时跑**（dev uvicorn + 容器），SQLite 会锁冲突。开发前先 `down`。

**登录口令**：库里 `admin@local` 的口令是你自己在 dev 改过的那个，沿用即可。
`.env.cloud` 里的 `SL_AUTH_BOOTSTRAP_ADMIN_PASSWORD` 只在「库里仍是仓库默认口令」
时才会自动替换，正常情况下不会触发。

**RAG 已关闭**：生产镜像 `pip install -e .` 不带 `[rag]` extra，没有
sentence-transformers/torch。要在公网用 RAG，改走 API 侧 embedding
（`SL_EMBEDDING_PROVIDER=openai_compatible`），别给镜像装 torch。

**限流的客户端 IP**：`SL_TRUST_PROXY_HEADERS=true` 时按 `CF-Connecting-IP` →
`X-Forwarded-For` 末位取值。nginx 会透传 `CF-Connecting-IP`，所以**能直接连到
nginx 的人可以伪造它**绕过限流——这也是 compose 里把端口绑死在 `127.0.0.1`
的原因之一。若哪天把 80 端口放开给局域网/公网，必须改成在 nginx 层强制重写
该头，而不是透传。

**备份**：库在 `backend/data/smartlearning.db`。已有一份
`smartlearning.db.backup-20260801-170752`。定期复制一份，容器化不等于有备份。
