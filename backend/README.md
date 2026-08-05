# Backend (FastAPI)

## 启动

```powershell
cd D:\Project\smartLearning\backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

文档：<http://localhost:8000/docs>

## Windows 常见：`.venv` 删不掉、`Activate.ps1` 找不到、`venvlauncher` 复制失败

这些情况通常连在一起出现：**环境里已有半截文件，且 `.venv\\Scripts\\python.exe` / 一堆 `.pyd` 仍被某个进程加载**，于是 `pip` / `Remove-Item` / `py -m venv` 都会报「拒绝访问」或无法覆盖 `python.exe`。`Activate.ps1` 找不到多半是 **venv 从未创建完整**（`Scripts` 目录不全）。

### 1. 先彻底结束占用 `.venv` 的进程（必做）

在 **新开** PowerShell（不要在已激活、曾跑过 `uvicorn` 的会话里凑合）执行：

```powershell
# 结束明显相关的 Python（会关掉本机其它 Python 任务，请先保存工作）
Get-Process -Name python, pythonw -ErrorAction SilentlyContinue | Stop-Process -Force

# 更精确：命令行里带本项目 .venv 的进程
$p = 'smartLearning\backend\.venv'
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*$p*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
```

然后：**关掉 Cursor / VS Code 里所有使用该项目的集成终端**，若仍删不掉文件，可先**完全退出 Cursor** 再在系统自带 PowerShell 里删 `.venv`。

### 2. 再删 `.venv`，然后重建

```powershell
cd D:\Project\smartLearning\backend
Remove-Item -LiteralPath .venv -Recurse -Force
```

若 PowerShell 仍报「访问被拒绝」，在**已确认没有 Python 进程**后试一下 CMD（有时句柄释放更快）：

```cmd
cd /d D:\Project\smartLearning\backend
rmdir /s /q .venv
```

最后再建（建议先试 **Python 3.12**，比 3.14 少一些边角问题）：

```powershell
py -3.12 -m venv .venv
# 若没有 3.12:
# py -3 -m venv .venv

.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e .
```

检查：`Test-Path .\.venv\Scripts\Activate.ps1` 与 `Test-Path .\.venv\Scripts\python.exe` 都应为 `True`。

### 3. 仍删不掉文件夹：绕过方式（可先继续开发）

不必死磕项目里的 `.venv` 目录——在别处新建环境，再以可编辑安装指向本后端：

```powershell
mkdir D:\venvs -Force | Out-Null
py -3.12 -m venv D:\venvs\smartlearning-backend
& D:\venvs\smartlearning-backend\Scripts\Activate.ps1
pip install -U pip
pip install -e D:\Project\smartLearning\backend
```

之后在「活动」的 venv 里照常 `cd D:\Project\smartLearning\backend`，执行 `alembic upgrade head`、`uvicorn ...` 即可。等项目里 `.venv` 不再被锁后，再手动删掉 `backend\.venv`（或**重启电脑**后再删，一般即可）。

### 4. 其它

- **云盘 / OneDrive** 正在同步 `D:\Project\smartLearning` 时，.PYD 容易被锁；可暂停同步或把仓库挪到纯本地盘。
- **Defender 受控文件夹访问**：将 `python.exe` 或本仓库目录加入排除后再建 venv / `pip install`。
- **virtualenv**（在进程已杀干净的前提下）：`py -m pip install --user virtualenv` 后 `py -m virtualenv -p py .venv`。

### 5. 本地扩展报错：`pydantic_core._pydantic_core` / `_cffi_backend` / `rpds.rpds` 找不到

若干依赖带有 **Windows 原生扩展（`.pyd`）**。若安装被中断、或曾被「拒绝访问」截断，会变成：

- `ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'`
- `ModuleNotFoundError: No module named '_cffi_backend'`（`cryptography` / `cffi`）
- `ModuleNotFoundError: No module named 'rpds.rpds'`（`rpds-py`，`jsonschema` 的依赖）

在已激活的 venv 里**强制重装**对应包：

```powershell
cd D:\Project\smartLearning\backend
.\.venv\Scripts\Activate.ps1

# Pydantic
pip uninstall -y pydantic pydantic-core
pip install --no-cache-dir --force-reinstall pydantic pydantic-core

# Cryptography（API Key 加密）
pip uninstall -y cffi cryptography
pip install --no-cache-dir --force-reinstall cffi cryptography

# rpds-py（jsonschema 依赖,生成题用 JSON Schema 校验）
pip install --no-cache-dir --force-reinstall rpds-py
```

自检：

```powershell
python -c "from pydantic_core._pydantic_core import __version__ as v; print('pydantic_core', v)"
python -c "import _cffi_backend; from cryptography.fernet import Fernet; print('cryptography OK')"
python -c "from app.main import app; print(app.title)"
```

再执行 `alembic upgrade head`、`uvicorn app.main:app --reload --port 8000`。

若仍失败，多半是环境已污染，按上文 **删掉 `.venv` 后重建**，或改用 **Python 3.12** 的新 venv。**安装依赖时不要同时跑 `--reload`** 的 uvicorn（会锁 `.pyd`）。

## 关键路径

- `app/main.py` 应用入口、CORS、路由挂载
- `app/core/config.py` 配置（pydantic-settings）
- `app/core/security.py` API Key 对称加密（Fernet）
- `app/db/` Session、Base、依赖注入
- `app/models/` ORM 实体（按 PRD §6 命名）
- `app/api/` 路由（wiki、branches、providers、prompts、generation、bank、practice、chats、attachments、settings、data）
- `app/services/` 业务
  - `wiki_service.py` Markdown 上传 → Wiki/main commit
  - `wiki_import.py` `.zip` 包导入：扫所有 .md（含中文文件名 CP437/GBK 回退），按 markdown 内位置匹配本地资产，按需提取到 `data/wikis/<id>/_assets/`，并把 `![](rel)`、`<img src=...>`、`[link](rel)`、引用式 `[id]: rel` 全部改写为 `/api/wiki/<id>/assets/<rel>`
  - `branch_service.py` 分支 CRUD + commit (CAS by `expected_parent_commit_id`) + LCA + 三路归并编排
  - `merge.py` 纯函数三路归并：`difflib.SequenceMatcher` × 2 → 沿 base 取 hunk → clean / conflict 标注 + auto-merge
  - `provider_service.py` Provider 连通性测试
  - `generation_service.py` Wiki → 候选题（带 schema 校验 + 自我修复）→ 入库
  - `scoring_service.py` 作答 → LLM 评分 → 服务端 `ScoringDefaults.grade` 算出 S/A/B/C → 持久化 AnswerAttempt（冻结 prompt/model）→ 按 `app_settings.practice_history_keep_n` 滚动裁剪
  - `chat_service.py` 多会话 / 流式 / vision 检查
  - `prompt_service.py` Prompt 版本化（编辑=新版本）+ scene→prompt+model 的 binding 维护 + 变量预览渲染
  - `settings_service.py` `AppSettings` 单例行（id=1）读写
  - `llm/` LLM 抽象（`adapters.py` openai_compatible / ollama / anthropic；`client.py` scene 解析 + chat_json）
- `app/api/data.py` 题库 JSON/CSV 导出 + Wiki zip 导出 + 5 种 scope 清理
- `app/api/branches.py` 分支 / commit / `merge-preview` / `merge` 全套
- `app/services/obsidian_vault.py` + `obsidian_sync_service.py`：Obsidian 库 `.md` → Wiki；`scripts/obsidian_sync_worker.py` 监听
- `GET/POST /api/sync/obsidian/status|scan` 手动全量同步
- `app/prompts/` 默认 Prompt 模板（v1）
- `alembic/versions/0002_app_settings.py` AppSettings 单例表 + 默认行种子

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `SL_HOST` | `127.0.0.1` | 监听地址（H5 内网访问改 `0.0.0.0`） |
| `SL_PORT` | `8000` | 端口 |
| `SL_DATABASE_URL` | `sqlite:///./data/smartlearning.db` | SQLAlchemy URL |
| `SL_DATA_DIR` | `./data` | 上传/附件根目录 |
| `SL_SECRET_KEY` | 随机生成 | API Key 加密主密钥（生产请固化） |
| `SL_CORS_ORIGINS` | `http://localhost:5173` | 逗号分隔 |
