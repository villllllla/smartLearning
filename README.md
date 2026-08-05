# SmartLearning · 智能知识管理与面试训练平台

PRD v1.0 一期实现仓库。完整产品设计文档见 [`docs/PRD.md`](docs/PRD.md)（17 章 + 2 附录,数据模型 / API / Prompt 模板 / 验收清单全部在内,作为后续迭代的事实标准）。

## 目录结构

```
smartLearning/
├── backend/                    # FastAPI + SQLAlchemy + SQLite
│   ├── app/
│   │   ├── api/                # 路由层（按模块拆分）
│   │   ├── core/               # 配置、加密、日志
│   │   ├── db/                 # SQLAlchemy session、base
│   │   ├── models/             # ORM 模型（与 PRD §6 实体一一对应）
│   │   ├── schemas/            # Pydantic Schema
│   │   ├── services/           # 业务服务（解析 md、调用模型、评分等）
│   │   ├── prompts/            # 默认 Prompt 模板（v1 文本）
│   │   └── main.py
│   ├── alembic/                # 数据库迁移
│   ├── data/                   # 运行期数据（uploads/wikis/attachments/sqlite）
│   ├── pyproject.toml
│   └── README.md
├── frontend/                   # React + Vite + TS + Tailwind + shadcn/ui
│   ├── src/
│   │   ├── pages/              # 知识 / 对话 / 题库 / 练习 / 设置
│   │   ├── components/         # 通用组件（含 shadcn 派生）
│   │   ├── api/                # 前端 API 客户端
│   │   ├── lib/                # utils
│   │   └── App.tsx
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   └── package.json
├── docker-compose.yml
└── README.md
```

## 一期 MVP 进度（对应 PRD §13 验收清单）

| 验收项 | 状态 |
|---|---|
| 拖拽多文件 .md / .zip 上传并解析 | ✅ .md 直传；.zip 自动提取同目录图片/附件并把相对路径改写为 `/api/wiki/{id}/assets/...` |
| Wiki 详情/版本历史/分支/合并 | ✅ 详情 + main 编辑 + 命名分支 + 提交 (CAS 防丢失) + 三栏冲突合并 (base/ours/theirs 逐 hunk 选择，可自定义文本) |
| 配置本地+云端 Provider 并切换对话 | ✅ Provider/Model CRUD + 连通性 + Chat 内可切模型 |
| 对话支持图片附件 + vision 提示 | ✅ 上传 → 模型 supports_vision=false 时后端返回 400 文案 |
| Chat 多会话 + SSE 流式 + 停止 | ✅ |
| Prompt 模板版本化 + 设为当前 | ✅ 设置页可按 4 个 scene 列版本/新建/设为当前/复制为新版/带变量预览渲染；同页设默认模型 + temperature/max_tokens |
| 单篇生成 N 候选题 + 预览勾选 + 冻结 prompt/model/commit | ✅ N 可调 1–30，候选页支持勾选 / 行内编辑 / 丢弃 / 入库 |
| 题库筛选（标签 AND/OR、来源 wiki、难度、类型、错题） | ✅ 全部支持；每条带最近一次 grade 徽标 + 作答历史抽屉 |
| 练习页 + 4 维评分 + 改进建议 | ✅ Setup → Run → 立即评分；顺序/随机/错题三种模式 |
| S/A/B/C 评级规则（服务端硬门槛） | ✅ `ScoringDefaults.grade` 单一 source-of-truth |
| 同题最近 N 次 | ✅ `GET /api/bank/questions/{id}/attempts?limit=10`；题库可展开作答历史抽屉；评分服务按 `app_settings.practice_history_keep_n` 滚动裁剪 |
| 数据导出（题库 JSON/CSV、Wiki zip） | ✅ `GET /api/data/export/bank`、`GET /api/data/export/wikis`；CSV 带 BOM 兼容 Excel；zip 含 manifest.json 和提交历史 |
| 数据清理（chats/attempts/candidates/questions/all） | ✅ `POST /api/data/clear`；前端高风险 scope 需输入 `DELETE` 二次确认 |
| 主题（明/暗/跟随系统） | ✅ Tailwind class 模式；侧栏快捷切换 + 设置页持久化；首次启动从后端 settings 拉取 |
| 练习偏好（默认题量 / 单题秒数 / 默认难度&类型 / 历史 N） | ✅ `/api/settings` 全字段读写；练习设置页一进来即按偏好预填 |
| 移动端 H5 ≥ 360px | ✅ 外壳 + 知识 / Chat / 题库 / 练习已适配 |
| 多租户 + 登录鉴权 | ✅ JWT 登录；Wiki/题库/对话/设置等按 `tenant_id` 隔离；可选注册新租户 |

## 快速启动

### 方式一：本地开发

后端 Python 项目在 **`backend/`**（那里有 `pyproject.toml`）。`pip install -e .` 必须在 **`backend` 目录**执行；若在仓库根目录且虚拟环境建在根目录，请用：`pip install -e ./backend`。

```bash
# 1) 后端（推荐：虚拟环境建在 backend 下）
cd backend
python -m venv .venv
.venv\Scripts\activate          # PowerShell: .venv\Scripts\Activate.ps1
pip install -e .
alembic upgrade head             # 初始化数据库 + 注入默认 Prompt
uvicorn app.main:app --reload --port 8000

# 若你已把 .venv 建在仓库根目录 D:\Project\smartLearning：
# cd D:\Project\smartLearning
# pip install -e .\backend

# 2) 前端（新终端；**必须在 frontend 目录**，根目录没有 package.json）
cd frontend
npm install
npm run dev                       # http://localhost:5173

# 若你当前在仓库根目录且不想切换目录：
# npm install --prefix frontend
# npm run dev --prefix frontend
```

### 方式二：docker-compose

```bash
docker-compose up --build
# 前端 http://localhost:5173 ，后端 http://localhost:8000
```

### 方式三：部署生产栈

```powershell
.\deploy.ps1    # 构建 → 备份数据库 → 重启 → 健康检查（失败自动回滚）
```

CI（GitHub Actions：ruff / pytest / tsc / 镜像冒烟）和这条部署命令的完整说明见
[docs/ci-cd.md](docs/ci-cd.md)。

### 登录与多租户

默认开启登录鉴权（`SL_AUTH_ENABLED=true`）。迁移 `0007` 会创建默认租户与管理员：

- 邮箱：`admin@local`
- 密码：`changeme123`（部署后请尽快修改）

前端访问任意页面会先跳转 `/login`；登录成功后 JWT 保存在浏览器 `localStorage`，后续 API 自动带 `Authorization: Bearer …`。

| 变量 | 说明 |
|------|------|
| `SL_AUTH_ENABLED` | `true` 开启鉴权（默认）；本地调试可设 `false` 跳过登录 |
| `SL_AUTH_TOKEN_EXPIRE_HOURS` | JWT 有效期（默认 168 小时） |
| `SL_AUTH_ALLOW_REGISTER` | `true` 允许 `/register` 自助创建新租户 |
| `SL_AUTH_BOOTSTRAP_ADMIN_*` | 首次启动空库时自动创建的管理员邮箱/密码 |

穿透公网时仍可使用 **`SL_BOT_API_TOKEN`**（请求头 `X-SL-Token` 或 Bearer）以机器身份访问默认租户，供飞书 Bot / 脚本使用。

## 这一轮跑通的全链路

1. **设置 → 模型与 Provider** 添加并启用一个 Provider（OpenAI 兼容 / Ollama / Anthropic 任意一个），至少加一个 Model 并设为默认。
2. **知识 → 上传** 直接拖 .md，或把 .md + 同目录图片打成 zip 一起拖（推荐：从 Typora/Obsidian/VS Code 导出的笔记天然是这种结构）。上传后端会：
   - zip 里每个 .md 生成一篇 wiki，相对图片/链接（`![](images/foo.png)`、`<img src="...">`、`[link](docs/x.pdf)` 等）按其相对 zip 内位置去匹配实际文件；
   - 命中的资产落到 `backend/data/wikis/<wiki_id>/_assets/<原始路径>`，markdown 里的引用改写为 `/api/wiki/<wiki_id>/assets/<原始路径>`；外链 (http/https) 与 data: 协议不动；
   - 未命中的引用在上传结果里以「N 条引用未匹配」黄色提示，但原文本不会被破坏（用户可以后续编辑修正）。

   进入详情后点 **生成面试题** → 弹窗里选「题量策略」：
   - **由模型决定（推荐，默认）**：服务端注入「请根据内容自行决定题量，下限 3 条，上限 N 条」directive；信息密度高就多出、内容稀薄就少出，不再凑数。可调上限保护 `max_n`（默认 30），防止超长文档导致模型一次性产出过多；
   - **固定题数**：服务端注入「必须恰好为 N 条」，等同 PRD §6.3.2 老行为。

   生成完成后自动跳到 `/bank/candidates/<batch_id>` 候选预览页：
   - 每条单独勾选 / 行内编辑（题干、答案、难度、类型、标签）/ 丢弃；
   - 「入库已勾选」一次性写入 `Question`，并冻结 `prompt_template_id` / `model_id` / `source_commit_id`。
3. **题库**：左侧筛选栏支持难度 / 类型 / 标签（OR/AND 切换）/ 来源 wiki / 只看错题；每条卡片带最近 grade 徽标和「作答历史」抽屉。
4. **练习**：`/practice` 设置题集（顺序 / 随机 / 错题模式 + 每题秒数）→ 出题 → `/practice/run` 逐题作答；提交即调评分模型，立刻得到 4 维分数 + 改进建议 + 标准答案对照；走完得到 S/A/B/C 总结表。
5. **对话**：左侧「新建会话」，输入框支持 Shift+Enter 换行 / Enter 发送，可上传图片附件（仅 supports_vision=true 的模型可用），消息流式渲染、可中途「停止」。
6. **设置 → Prompt 模板**：4 个 scene（chat_general / wiki_to_questions / answer_scoring / wiki_summary）每个一组版本；可基于当前版本「复制为新版」并修改 → 「设为当前」；任何编辑都会创建新版本，**老版本不会被改动**，所以已生成的题目和评分记录里冻结的 `prompt_template_id` 一直能复现到当时的输入；带变量「预览渲染」可代入示例值看到模型实际收到的 prompt。同页可为每个 scene 单独指定默认模型 + `temperature` / `max_tokens`，覆盖全局解析规则。
7. **Wiki 分支与合并**：
   - 详情页右上角「分支下拉 + ＋ 新建分支」从任意分支拉新分支（默认从 main，命名允许 `[A-Za-z0-9_-./]`，禁止再叫 `main`）；
   - 切到非 main 分支后点「编辑」→ 直接改 Markdown → 「提交」创建新 commit，附带提交说明；提交时若有别的会话已经把 HEAD 推到了新版本会被服务器以 409 拒绝并提示刷新（乐观并发，不会覆盖别人的工作）；
   - 在分支上点「合并到 main」打开三栏面板：每个差异块 (hunk) 列出 base / ours=main / theirs=branch 三个候选，可点按钮选中其一，或展开「自定义解决文本」直接覆盖；干净 hunk 默认折叠展示已自动采用的结果；
   - 后端短路了三种 fast-forward（ours==base、theirs==base、ours==theirs），无需用户选；冲突全部解决后才允许提交合并，merge 写入的是 main 上一条新的 commit（其 `parent` = 当前 main HEAD），并立即更新 wiki 元数据。
8. **设置 → 数据与外观**：
   - 主题三档（浅 / 深 / 跟随系统）即点即生效；侧栏角落有快捷开关；偏好保存到 `app_settings.appearance_theme` 后跨设备复用；
   - 练习偏好：默认题量、单题时间（可清为「不限」）、默认难度 / 类型、保留历史 N（评分写入后自动滚动删除超出 N 的老记录）；
   - 一键导出：题库 JSON（完整字段、含冻结的 prompt/model id）/ 题库 CSV（UTF-8 with BOM，Excel 直接打开）/ Wiki 包 zip（每篇 `<slug>-<id>.md` + `manifest.json`，含分支 / commit 历史）；
   - 危险区清理：分 5 个 scope（对话 / 作答 / 候选题 / 题库 / 全部业务数据）；高风险 scope 必须输入 `DELETE` 二次确认；不会触碰模型 / Provider / Prompt / Wiki 与本页设置。

## 关键设计要点

- **Prompt 与功能绑定**：`PromptTemplate` 按 scene 多版本，`FunctionBinding` 指向当前生效版本；生成/评分时把 `prompt_template_id` 与 `model_id` **冻结**到 `Question` / `AnswerAttempt`，保证可复现（PRD §6.2.3 / §6.3.3 / §6.4.4）。
- **Wiki 版本**：Git‑like 极小集——`main` + 命名分支 + commit + 三栏冲突合并 (`backend/app/services/merge.py` 是纯函数行级 3-way merge，6 个用例覆盖 fast-forward / disjoint / 同改 / 真冲突 / 删 vs 改；UI 端把 hunk 渲染为 base/ours/theirs 三栏并允许自定义文本)。一期不做 rebase / cherry-pick / 远程仓库（PRD §6.1.2）。
- **私有化优先**：默认监听 `127.0.0.1`，云端 Provider 默认关闭；API Key 用 Fernet 服务端加密存储（PRD §9）。Fernet 密钥的种子优先取 `SL_SECRET_KEY` 环境变量，若不存在则首次启动生成一份随机种子并持久化到 `backend/data/.secret_key`，后续重启始终读取它；这样开发环境也不会因为每次重启换种子而把 provider API Key「弄丢」。生产环境仍建议显式设置 `SL_SECRET_KEY`。若 `.secret_key` 被误删（或换设备没带走），旧密文会变成 `InvalidToken` 永久无法解密，UI 上表现为「Key 消失了」——此时只能重新填一次。
- **JSON 容错**：模型返回非 JSON 时一次自动「让模型修复」，仍失败则向用户报错（PRD §11 / §9）。
- **AppSettings 单例表**：`app_settings.id = 1` 由 0002 迁移种子化，任何字段缺省都有显式默认；评分服务直接读它来做历史滚动裁剪，不需要 cron。
- **题量自适应**：`wiki_to_questions` 默认模板从硬编码 `数组长度 = {N}` 改为 `{COUNT_DIRECTIVE}`，由 `generation_service._count_directive(n, max_n)` 在运行时计算；`n=None` 走「按内容决定（3..max_n）」、`n=int` 走「必须恰好 N 条」。0003 迁移仅替换**字节级**等于旧 v1 默认文本的行（自定义版本和已编辑的 v1 都不会被动）；老模板里的 `{N}` 占位符在自动模式下被注入完整 directive 句子，老句式仍读起来通顺。模型若违反上限，服务端在落库前再裁剪一次。

## 飞书 Bot 遥控（可选）

通过飞书私聊机器人，在本机运行的 SmartLearning 上：**抽题 / 查答案 / 与大模型对话**。需将后端暴露到公网 HTTPS（推荐 [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) 或 ngrok），并在飞书开放平台配置事件订阅。

### 安全说明

- 穿透等于把本机 API 暴露到公网。除飞书 Webhook 外，建议设置 **`SL_BOT_API_TOKEN`**，前端/脚本请求需带请求头 `X-SL-Token: <token>`。本地 `npm run dev` 时 Vite 会从 `backend/.env` 自动注入该头；也可在 `frontend/.env.local` 设置 `VITE_SL_BOT_TOKEN`（与后端值相同）并重启前端。
- 必须配置 **`SL_FEISHU_ALLOWED_OPEN_IDS`**（逗号分隔的飞书用户 `open_id` 白名单），非白名单用户无法触发命令。
- Webhook 会校验 **`SL_FEISHU_VERIFICATION_TOKEN`**（与飞书后台「Verification Token」一致）；若开启加密，还需 **`SL_FEISHU_ENCRYPT_KEY`**。

### 环境变量（`backend/.env` 或系统环境）

| 变量 | 说明 |
|------|------|
| `SL_FEISHU_BOT_ENABLED` | `true` 启用飞书集成 |
| `SL_FEISHU_APP_ID` / `SL_FEISHU_APP_SECRET` | 飞书应用凭证 |
| `SL_FEISHU_VERIFICATION_TOKEN` | 事件订阅 Verification Token |
| `SL_FEISHU_ENCRYPT_KEY` | 可选，开启「加密」时填写 |
| `SL_FEISHU_ALLOWED_OPEN_IDS` | 允许使用的用户 `open_id`，逗号分隔 |
| `SL_BOT_API_TOKEN` | 可选，穿透时保护 `/api/*` |

### 飞书应用配置摘要

1. [飞书开放平台](https://open.feishu.cn/app) 创建企业自建应用，启用 **机器人**。
2. 权限：`im:message`（接收与发送消息）。
3. **事件订阅** → 请求地址：`https://<你的隧道域名>/api/integrations/feishu/events`  
   订阅 `im.message.receive_v1`；先保存 Verification Token 到 `SL_FEISHU_VERIFICATION_TOKEN`。
4. 发布应用后，在飞书里与机器人私聊；首次可在飞书管理后台或事件日志中查看自己的 **`open_id`**，写入白名单。
5. 本机：`cd backend && alembic upgrade head && uvicorn app.main:app --reload --port 8000`  
   隧道示例（Cloudflare quick tunnel）：`cloudflared tunnel --url http://127.0.0.1:8000`

### 使用方式（Agent 自然语言）

**所有文本消息** 会先由模型做语义识别，再调用题库/对话接口（使用与 Web 对话相同的 `chat_general` 模型配置）。**无需确认**，说「给我 5 道题」会直接抽题。

示例：

- `给我 5 道 Redis 场景题`
- `来 3 道困难八股` / `错题 5 道`
- `答案 12` / `下一题`
- `解释一下 CAP 定理`（一般对话）
- `新建对话`（清空 LLM 上下文）

交互卡片上的按钮仍走快捷指令，不经过 Agent。

迁移：`alembic upgrade head` 会创建 `bot_sessions` 表（revision `0004`）。

## Obsidian 文件夹同步（可选）

将 Obsidian 库目录中的 `.md` 自动同步为 SmartLearning **Wiki（main 分支）**；相对路径图片会复制到 `data/wikis/<id>/_assets/` 并改写链接。

### 配置（`backend/.env`）

| 变量 | 说明 |
|------|------|
| `SL_OBSIDIAN_SYNC_ENABLED` | `true` 启用 |
| `SL_OBSIDIAN_VAULT_PATH` | Obsidian 库根目录绝对路径 |
| `SL_OBSIDIAN_SYNC_DEBOUNCE_SECONDS` | 监听防抖秒数，默认 5 |
| `SL_OBSIDIAN_SYNC_ON_START` | worker 启动时是否先全量扫描 |
| `SL_OBSIDIAN_SYNC_DEDUPE_AFTER` | 全量扫描后是否自动归并相似题 |
| `SL_OBSIDIAN_SYNC_IGNORE_DIRS` | 额外忽略的文件夹名，逗号分隔 |

### 使用

1. 配置 `.env` 后重启 `uvicorn`。
2. **监听进程**（单独终端）：
   ```powershell
   cd backend
   .\.venv\Scripts\Activate.ps1
   pip install -e .   # 含 watchdog
   python scripts/obsidian_sync_worker.py
   ```
3. Web：**设置 → 数据与外观 → Obsidian 文件夹同步** →「立即全量同步」；或调用 `POST /api/sync/obsidian/scan`。

映射状态保存在 `backend/data/obsidian_sync/state.json`（vault 内相对路径 → `wiki_id`）。

全量扫描会先为**仅有标题、缺少 `main` 分支**的历史 Wiki 自动补建 `main`（`wikis_repaired`），再按 vault 文件写入正文。若列表里 `current_main_commit_id` 仍为空，说明 vault 中对应 `.md` 尚未成功导入（路径未映射、同步报错或标题重复无法绑定）。

### 模型超时（`backend/.env`）

| 变量 | 默认 | 说明 |
|------|------|------|
| `SL_MODEL_REQUEST_TIMEOUT_SECONDS` | `180` | 对话 / 出题 / JSON 生成等 LLM 调用超时（秒） |
| `SL_MODEL_PROBE_TIMEOUT_SECONDS` | `20` | Provider「连通性测试」拉模型列表的超时（秒） |

连通性测试在列表接口通过后，会用第一个已启用模型发一条极短补全（与真实出题同路径），用于发现 **ReadTimeout / 代理** 等问题。

### 时区参考表（定时推题）

迁移 `0011` 创建 `timezone_refs` 表并种子化约 56 个主要 IANA 时区（亚洲 / 欧洲 / 美洲等）。Web「设置 → 定时推送」时区字段为下拉选择；接口 `GET /api/timezones` 返回分组列表。保存推送配置时服务端校验 `timezone` 必须存在于该表。

## Wiki RAG（bge-small-zh）

对话时可从本地 Wiki **检索相关片段** 注入 LLM，并在回答下方列出 **可点击的 `/wiki/<id>` 链接**。

### 安装与建索引

```powershell
cd backend
pip install -e ".[rag]"
alembic upgrade head
# 首次会下载 BAAI/bge-small-zh-v1.5 到本地缓存
```

Web：**设置 → 数据与外观 → Wiki 知识库 RAG → 重建全部 Wiki 向量索引**  
或：`POST /api/rag/rebuild`

### 使用

- **对话**页勾选「使用 Wiki 知识库 (RAG)」后发送问题
- 飞书 `chat` 工具默认同样启用 RAG（`SL_RAG_DEFAULT_IN_CHAT=true`）
- Obsidian 同步写入 Wiki 后若 `SL_RAG_AUTO_INDEX=true` 会自动更新该篇索引

调试检索：`POST /api/rag/query` body `{ "query": "Redis 持久化" }`

## 路线图

- 一期：本仓库（私有化、单用户本地、Web + H5）
- 集成扩展：飞书 Bot 遥控（本机 + 穿透）
- 二期：账号/邀请/共享、Wiki 多人 PR/Review、微信小程序（Taro）
- 三期：OCR、知识图谱、自动归并相似题、掌握度推荐
