# CI/CD

## 形态与取舍

```
 push / PR
     │
     ▼
┌─────────────────────────────────────────┐
│ GitHub Actions（云端）                    │
│  backend   ruff check + pytest           │
│  frontend  tsc -b + vite build           │  ← 证明这个 commit 是好的
│  images    构建两个镜像 + /api/health 冒烟  │
└─────────────────────────────────────────┘
     │  绿了之后，你在本机手动触发
     ▼
┌─────────────────────────────────────────┐
│ .\deploy.ps1（本机）                      │
│  pull → build → 备份库 → 重启 → 健康检查    │  ← 把它送上线
│  健康检查不过 → 自动回滚到上一版镜像          │
└─────────────────────────────────────────┘
     │
     ▼
  cloudflared → nginx:80 → backend:8000 → https://sl.zz34zz.uk
```

**为什么 CD 不是自动的**：生产栈跑在这台 Windows 机器上，走 Cloudflare Tunnel
**出站**连接，不开任何入站端口（见 [deploy-cloudflare-tunnel.md](deploy-cloudflare-tunnel.md)）。
GitHub 的云端 runner 从外面够不到它。要做到 push 即部署，只能在这台机器上常驻一个
self-hosted runner——那等于让仓库里的代码在你机器上自动执行，攻击面明显变大。
所以这里的分工是：**CI 在云端把关，CD 在本机一条命令**。

## CI

配置：[`.github/workflows/ci.yml`](../.github/workflows/ci.yml)

**触发**：push 到 `main`、任何 PR、以及 Actions 页面手动触发（`workflow_dispatch`）。
同一分支上新的 push 会取消还在跑的旧 run（`concurrency`）。

| Job | 做什么 | 挡住什么 |
|---|---|---|
| `backend` | `pip install -e ".[dev]"` → `ruff check .` → `pytest -q` | 后端逻辑回归、lint 退化 |
| `frontend` | `npm ci` → `npm run build`（即 `tsc -b && vite build`） | TS 类型错误、构建失败 |
| `images` | 构建 backend/frontend 镜像，起后端容器打 `/api/health` | Dockerfile 坏掉、**镜像缺运行时依赖**、迁移在空库上跑不过 |

几个刻意的选择：

- **后端不装 `[rag]` extra**。它会拖进 torch（约 2GB），而且生产镜像本身也不装
  （见 deploy-cloudflare-tunnel.md「RAG 已关闭」）。CI 环境保持和生产一致，
  测试也就必须在没有 sentence-transformers 的情况下可跑。
- **`images` job 依赖前两个**（`needs`），lint/测试没过就不浪费时间构建镜像。
- **冒烟测试是真起容器**，不只是 `docker build`。它专门盯"镜像构建成功但起不来"
  这一类问题——缺依赖、迁移在全新数据库上失败，都会在这里暴露。

## CD

脚本：[`deploy.ps1`](../deploy.ps1)（仓库根目录）

```powershell
.\deploy.ps1                  # 常规部署
.\deploy.ps1 -SkipPull        # 不 pull，直接把当前工作区发上去
.\deploy.ps1 -TimeoutSeconds 180   # 健康检查等久一点
```

七个步骤：

1. **前置检查** —— Docker 在跑；`.env.cloud` 存在；**8000 端口上没有 dev 服务**。
   最后这条不是形式主义：dev uvicorn 和容器绑挂的是同一个 SQLite 文件，
   两个写入方会锁冲突甚至损坏数据。
2. **拉代码** —— `git pull --ff-only`。分叉或有本地改动就直接失败，不做自动合并。
3. **打 rollback 标签** —— 把当前 `smartlearning-backend:latest` /
   `smartlearning-frontend:latest` 额外打上 `:rollback`。
   **必须在 build 之前做**：build 会覆盖 `:latest`，这个标签是唯一让旧镜像
   不被回收的东西。
4. **构建镜像** —— 此时旧栈还在服务，所以停机时间从第 5 步才开始。
   构建失败的话旧栈原封不动，脚本直接退出。
5. **停栈 + 备份数据库** —— 顺序是有意的：停机后再拷贝，保证拿到的是一致的快照；
   而且必须在 `up` 之前，因为容器一启动就跑 `alembic upgrade head` 可能改表结构。
   备份写到 `backend/data/smartlearning.db.backup-<时间戳>`，只保留最近 10 份。
6. **起栈** —— `docker compose -f docker-compose.prod.yml up -d --remove-orphans`。
7. **健康检查** —— 轮询 `http://127.0.0.1/api/health`（**经过 nginx**，
   不是直连 8000，这样顺带验证了 nginx 那一跳）。默认最多等 120 秒。

**回滚**：健康检查超时的话，脚本先打印后端最后 50 行日志，然后把 `:rollback`
重新打回 `:latest` 并重启，最后以非 0 退出码结束。

> ⚠️ **回滚不撤销数据库迁移**。如果新版本已经跑过 `alembic upgrade head` 改了表结构，
> 镜像回滚了但库还是新结构，旧镜像不一定能正常工作。这种情况要手动恢复第 5 步的备份。
> 脚本在回滚时会明确提示这一点。

## 首次接入要做的事

CI 在 push 到 GitHub 后会自动开始跑，不需要额外配置——**没有用到任何 secrets**，
因为 CI 只做 lint / 测试 / 构建，不碰生产环境和真实凭据。

日常节奏：

```powershell
git checkout -b feat/xxx
# ... 改代码 ...
git push -u origin feat/xxx        # 开 PR，等 CI 绿
# 合并到 main 后：
git checkout main
.\deploy.ps1
```

本地想在 push 前先自查，跑的就是 CI 里那几条：

```powershell
cd backend;  .\.venv\Scripts\python.exe -m ruff check . ;  .\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend;  npm run build
```

## 已知欠账

搭这套流水线时暴露出来的问题，有些当场修了，有些明确记账推后：

**已修**（否则 CI 第一天就是红的）：

- `tests/test_push_schedule.py` 有 2 个测试挂着 —— 生产代码的 `is_due_now()` 已经
  改成从数据库按租户取时区、新增了必填的 `db` 参数，测试还在用 row 上那个已被忽略的
  `timezone` 字段。是测试陈旧，不是产品 bug。
- `chat_service.py` 的 `finally` 块里有个 `return`（ruff B012）。这是真问题：
  流式对话报错且没吐出任何文本时，那个 `return` 会**吞掉正在传播的异常**，
  调用方看到的是正常结束而不是错误。
- 另外 19 处 ruff 告警（未用导入、导入未排序、`raise ... from`、`zip(strict=)` 等）。

**未修，明确记账**：

- **E501 超长行 121 处**。在 `backend/pyproject.toml` 里显式 ignore 了 `E501`，
  旁边有注释说明这是存量欠账。逐步把这些行折好之后，删掉那一行 ignore，
  门禁就自动收紧了——不需要改 CI。
- **前端没有 eslint**。`package.json` 里有 `lint` 脚本，但仓库里既没有 eslint 配置文件，
  devDependencies 里也没装 eslint——那条脚本现在跑不起来。所以 CI 用
  `tsc -b`（类型检查）+ `vite build` 兜底，没有真正的 lint 门禁。
- **`zip(strict=False)`**。给 5 处 `zip()` 补参数时统一用了 `strict=False`，
  它完全保持原有行为。其中 embedding 那两处（`question_embedding_service.py`、
  `rag/index_service.py`）长度不相等时会**静默截断**，改成 `strict=True` 更安全，
  但那是行为变更，不该在搭 CI 时顺手做。
- **部署不自动触发**，理由见开头。

## 排查

**CI 上后端过了、本地跑挂了（或反过来）** —— 大概率是你本地 `.venv` 装了 `[rag]`
extra 而 CI 没装。用 `pip install -e ".[dev]"` 对齐，或者反过来确认测试没有
偷偷依赖 sentence-transformers。

**`images` job 的冒烟测试挂了** —— 看那一步的 `docker logs` 输出。最常见的两种：
后端 import 了一个生产镜像里没有的包（RAG 相关的最容易踩），或者某个 alembic
迁移在全新空库上跑不过。

**`deploy.ps1` 卡在第 1 步说 8000 被占** —— 你的 dev uvicorn 还开着。先停掉它，
它和容器共用同一个 SQLite 文件。

**部署回滚了，但站点还是坏的** —— 多半是迁移改了库结构（见上面那条警告）。
用第 5 步的备份恢复：

```powershell
docker compose -f docker-compose.prod.yml down
Copy-Item backend\data\smartlearning.db.backup-<时间戳> backend\data\smartlearning.db -Force
docker compose -f docker-compose.prod.yml up -d
```

## 相关文档

- [deploy-cloudflare-tunnel.md](deploy-cloudflare-tunnel.md) —— 隧道怎么建的、
  生产栈的安全加固、日常起停命令
- [cloud-deployment.md](cloud-deployment.md) —— 更早的云部署方案
