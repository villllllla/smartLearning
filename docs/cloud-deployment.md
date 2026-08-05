# SmartLearning 云端部署指南

本部署方案使用 Docker Compose：

- `frontend`：前端执行 Vite 生产构建后，由 Nginx 在 `80` 端口提供静态资源。
- `backend`：FastAPI 服务，只暴露在 Compose 内部网络中。
- `smartlearning-data`：持久化保存 SQLite 数据库、上传文件、Wiki 资源和密钥缓存。

## 1. 准备云服务器

建议使用 Ubuntu 22.04/24.04，最低 2 核 CPU、4 GB 内存。如果开启本地 RAG 向量模型，建议使用更高内存配置。

安装 Docker：

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

在云厂商安全组中放行入站 TCP `80` 端口。如果后续要启用 HTTPS，也放行 `443` 端口。

## 2. 上传项目

从本机上传：

```bash
scp -r D:/Project/smartLearning user@your-server:/opt/smartLearning
```

如果项目已经托管到 Git，也可以直接在服务器上 clone 或 pull 仓库。

## 3. 配置密钥

在服务器上执行：

```bash
cd /opt/smartLearning
cp .env.cloud.example .env.cloud
openssl rand -base64 32
nano .env.cloud
```

将生成的随机字符串填入 `.env.cloud` 的 `SL_SECRET_KEY`。

如果你的域名是 `https://learn.example.com`，可以设置：

```env
SL_CORS_ORIGINS=https://learn.example.com
```

默认部署方式下，浏览器通过同域 `/api` 访问 Nginx，再由 Nginx 转发到后端，因此通常不会触发跨域问题。

## 4. 启动服务

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

健康检查：

```bash
curl http://127.0.0.1/api/health
```

浏览器访问：

```text
http://你的服务器IP/
```

## 5. 配置 HTTPS

推荐做法：将服务器接入 Cloudflare，并启用 "Full" TLS；或者在宿主机安装 Caddy / Nginx Proxy Manager，将公网 HTTPS 反向代理到 `http://127.0.0.1:80`。

如果使用外部反向代理，建议把当前 Compose 服务只绑定到本机：

```yaml
ports:
  - "127.0.0.1:80:80"
```

然后让外部反向代理转发到 `127.0.0.1:80`。

## 6. 当前部署信息

当前火山云 ECS 已部署实例：

| 项目 | 值 |
|---|---|
| 公网访问地址 | `http://124.174.100.169/` |
| 健康检查地址 | `http://124.174.100.169/api/health` |
| SSH 用户 | `root` |
| 本地私钥 | `D:\Data\Sceret\test.pem` |
| 服务器部署目录 | `/opt/smartLearning` |
| 生产配置文件 | `/opt/smartLearning/.env.cloud` |
| Compose 文件 | `/opt/smartLearning/docker-compose.prod.yml` |
| 持久化数据卷 | `smartlearning_smartlearning-data` |

连接服务器：

```powershell
ssh -i "D:\Data\Sceret\test.pem" root@124.174.100.169
```

进入项目目录：

```bash
cd /opt/smartLearning
```

## 7. 日常运维命令

以下命令默认在服务器的 `/opt/smartLearning` 目录下执行。

### 查看服务状态

```bash
docker compose -f docker-compose.prod.yml ps
```

查看容器资源占用：

```bash
docker stats smartlearning-backend smartlearning-frontend
```

查看镜像和数据卷：

```bash
docker images | grep smartlearning
docker volume ls | grep smartlearning
```

### 健康检查

服务器本机检查：

```bash
curl http://127.0.0.1/api/health
curl -I http://127.0.0.1/
```

公网检查：

```bash
curl http://124.174.100.169/api/health
curl -I http://124.174.100.169/
```

### 查看日志

查看日志：

```bash
docker compose -f docker-compose.prod.yml logs -f --tail=200
```

只看后端日志：

```bash
docker compose -f docker-compose.prod.yml logs -f --tail=200 backend
```

只看前端 Nginx 日志：

```bash
docker compose -f docker-compose.prod.yml logs -f --tail=200 frontend
```

### 启停服务

启动服务：

```bash
docker compose -f docker-compose.prod.yml up -d
```

停止服务但保留容器和数据卷：

```bash
docker compose -f docker-compose.prod.yml stop
```

停止并删除容器，保留数据卷：

```bash
docker compose -f docker-compose.prod.yml down
```

重启服务：

```bash
docker compose -f docker-compose.prod.yml restart
```

只重启后端：

```bash
docker compose -f docker-compose.prod.yml restart backend
```

### 更新部署

代码更新后重新构建并启动：

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

如果只是修改 `.env.cloud`，通常无需重新构建镜像，直接重启即可：

```bash
docker compose -f docker-compose.prod.yml up -d
```

如果 Compose 提示 `unknown flag: --build`，使用上面的分步 `build` + `up -d` 命令。

### 上传本地代码包

在本机 PowerShell 中打包并上传：

```powershell
$archive = Join-Path $env:TEMP "smartlearning-deploy.tar.gz"
if (Test-Path $archive) { Remove-Item $archive -Force }
tar -czf $archive `
  --exclude="smartLearning/frontend/node_modules" `
  --exclude="smartLearning/frontend/dist" `
  --exclude="smartLearning/backend/.venv" `
  --exclude="smartLearning/.venv" `
  --exclude="smartLearning/backend/data/*.db" `
  --exclude="smartLearning/backend/data/uploads" `
  --exclude="smartLearning/backend/data/wikis" `
  --exclude="smartLearning/backend/data/attachments" `
  --exclude="smartLearning/backend/data/obsidian_sync" `
  --exclude="smartLearning/.env.cloud" `
  --exclude="smartLearning/cloudflared-windows-amd64.exe" `
  -C "D:\Project" smartLearning

scp -i "D:\Data\Sceret\test.pem" $archive root@124.174.100.169:/tmp/smartlearning-deploy.tar.gz
```

在服务器上解压并更新：

```bash
mkdir -p /opt/smartLearning
tar -xzf /tmp/smartlearning-deploy.tar.gz -C /opt/smartLearning --strip-components=1
cd /opt/smartLearning
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

### 备份与恢复

备份数据：

```bash
docker run --rm -v smartlearning_smartlearning-data:/data -v "$PWD:/backup" alpine \
  tar czf /backup/smartlearning-data-$(date +%F).tar.gz -C /data .
```

恢复数据：

```bash
docker compose -f docker-compose.prod.yml down
docker run --rm -v smartlearning_smartlearning-data:/data -v "$PWD:/backup" alpine \
  sh -c "rm -rf /data/* && tar xzf /backup/smartlearning-data-YYYY-MM-DD.tar.gz -C /data"
docker compose -f docker-compose.prod.yml up -d
```

### 查看生产配置

查看 `.env.cloud`：

```bash
cat /opt/smartLearning/.env.cloud
```

修改生产配置：

```bash
nano /opt/smartLearning/.env.cloud
chmod 600 /opt/smartLearning/.env.cloud
docker compose -f docker-compose.prod.yml up -d
```

### Docker 镜像源

当前服务器已配置 Docker 镜像源：

```json
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.1ms.run"
  ]
}
```

查看镜像源：

```bash
docker info | sed -n '/Registry Mirrors:/,/Live Restore Enabled/p'
```

重新加载 Docker 配置：

```bash
systemctl daemon-reload
systemctl restart docker
```

### 常见排障

查看端口监听：

```bash
ss -lntp | grep -E ':80|:8000'
```

查看容器最近日志：

```bash
docker compose -f docker-compose.prod.yml logs --tail=100 backend
docker compose -f docker-compose.prod.yml logs --tail=100 frontend
```

后端健康检查不通过时，进入后端容器：

```bash
docker compose -f docker-compose.prod.yml exec backend sh
```

检查磁盘空间：

```bash
df -h
docker system df
```

清理未使用的 Docker 构建缓存和悬空镜像：

```bash
docker builder prune
docker image prune
```

不要执行 `docker volume prune`，除非你已经确认备份完成；它可能删除未挂载的数据卷。
