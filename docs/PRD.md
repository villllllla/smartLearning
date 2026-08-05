# 智能知识管理与面试训练平台 · 产品设计文档 (PRD v1.0)

## 0. 文档说明

- **目标读者**：后续的代码生成 AI / 工程实现者。
- **写作原则**：避免歧义、每个对象/字段/状态/接口均可落地；不强绑定具体技术栈，仅在「技术建议」一节给可选项。
- **范围**：本 PRD 描述**一期 MVP**（私有化、单用户本地）+ **二期路线图**（多人协作、云端、微信小程序）；**v2.0 平台化与社区化扩展**（分享/交易市场、求职目标与进展、AI 模拟面试、社区讨论区等）见 **§15**。
- **进度修正**：v1.0 中标注为「二期预留」的**账号体系 / 多租户 / 登录鉴权已在代码中实现**（`Tenant`/`User`、JWT、按 `tenant_id` 隔离），是 §15 平台化功能的地基。

---

## 1. 产品愿景与定位

打造一个**「知识 → 结构化题库 → 刻意练习 → 可追溯改进」闭环**的个人/小团队智能学习平台。

- 与普通 Wiki 的差异：Wiki 不只是「读」，而是**「能被结构化拆解为训练物料」**。
- 与普通刷题工具的差异：题目**来自用户自己的知识库**，可双向追溯到原文，避免「背题脱离上下文」。
- 与普通 AI 对话工具的差异：对话能力作为**底层能力**，可被「生成面试题」「评分」「拆解知识」等业务功能复用，且 prompt 与模型**可版本化、可绑定功能**。

---

## 2. 用户与场景

### 2.1 主要画像

- **P1 个人学习者（一期主力）**：在准备求职/晋升面试，已积累若干 Markdown 笔记，想用 AI 把笔记转成可训练的题库。
- **P2 小型工程/学习小组（二期）**：希望共享题库、分支式协作 Wiki。

### 2.2 核心场景（按使用频次降序）

1. 上传 Markdown 笔记，浏览/检索。
2. 选中一篇或多篇 wiki → 生成面试题 → 预览勾选入库。
3. 选择练习范围（标签 / 来源 / 随机 / 错题）→ 作答 → 拿到 S/A/B 评级 + 多维分数 + 改进建议。
4. 与 AI 对话（含图片），辅助理解 wiki 内容。
5. 查看错题与历史评分趋势，回到原 wiki 重新学习。

---

## 3. 一期范围（MVP）与分期路线图

依据你的确认：**A1 / B3 / C1 / D3 / E2 / F综合 / G2 / H 全要**。

### 3.1 一期 MVP（私有化 · 单用户本地）

| 模块 | 一期是否做 | 备注 |
|---|---|---|
| Wiki 管理（上传 md、列表、详情、删除、替换更新） | ✅ | 解析渲染 markdown |
| Wiki 版本与「分支/合并」 | ✅（最小可用 Git‑like） | 见 §6.1 |
| AI 对话（含图片、模型与 prompt 配置） | ✅ | 支持本地 + 云端模型 |
| 默认 Prompt 管理 + 与功能绑定 | ✅ | 含 prompt 版本号 |
| 面试题生成（预览勾选入库） | ✅ | 默认 12 题、八股 70% / 场景题 30% |
| 题库列表、标签筛选、详情、增删改 | ✅ | 题库集合（文件夹）概念引入 |
| 作答页（出题范围 + 评分 + 历史） | ✅ | S/A/B 综合等级 + 4 维分数 |
| 多端：Web 全功能 + 移动端 H5（H1‑H4 均覆盖） | ✅ | 一期不发布微信小程序 |
| 账号/多人协作 | ❌（仅预留数据字段与接口形态） | A1 单用户 |

### 3.2 二期（云上 + 协作）

- 引入账号体系（邮箱 / 邀请码）。
- 把 B3「分支/合并」从单机演进为多人协作（PR/Review/冲突解决 UI）。
- 题库集合按 G2 粒度共享、可见性（私有 / 链接共享 / 团队）。
- 微信小程序：以**轻量练习 + Wiki 阅读**为主，复用一期 H5 的 80% UI，需要公网 HTTPS 后端与微信合法域名。

### 3.3 三期（增强）

- OCR / 附件解析、知识图谱、自动归并近似题、按知识点掌握度推荐练习。

### 3.4 v2.0 平台化与社区化（新增方向，详见 §15）

- 从「私有化/单用户工具」演进为「**公网 SaaS + UGC 社区 + 内容交易市场 + AI 面试服务**」，采用**私有版 / 云社区版双形态**（feature flag 区分）。
- 主线：求职目标与进展追踪 → 社区讨论区 → 题目分享（免费→付费抽成）→ AI 模拟面试（文字→语音）。落地顺序与依赖见 §15.8。

---

## 4. 信息架构与导航

顶级导航（一期）：

1. **知识（Wiki）**
2. **对话（Chat）**
3. **题库（Bank）**
4. **练习（Practice）**
5. **设置（Settings）**：模型与 Provider、Prompt 模板、外观、数据导入导出

二期新增顶级或在「设置」内：**协作 / 团队 / 邀请**。

---

## 5. 核心用户故事（精选，作为验收基线）

- US‑01：作为用户，我可以一次性拖入多个 .md 文件，系统逐文件解析、入库，失败的明确报错。
- US‑02：作为用户，我可以为同一篇 wiki 创建一个分支版本，编辑后合并回主干；冲突时能看到差异并选择。
- US‑03：作为用户，我可以在 wiki 详情或列表多选后点击「生成面试题」，看到候选题列表，**逐题勾选**后入库。
- US‑04：作为用户，我可以按「来源文档 + 标签 + 错题」组合筛选题目并发起练习。
- US‑05：作为用户，作答后能看到 S/A/B 等级、4 维分数、改进建议、原标准答案对比。
- US‑06：作为用户，我可以查看某道题最近 N 次（默认 10）作答记录，默认展示最近一次。
- US‑07：作为用户，我可以在「设置 → Prompt 模板」里修改「生成面试题」和「评分」的 system prompt 并保留版本，不影响历史已生成的题目。
- US‑08：作为用户，我可以在 Web 上配置本地模型（如 Ollama）或云端模型（如 OpenAI 兼容协议），切换后聊天与功能能正常工作。
- US‑09：作为移动端用户，我可以完成 H1 刷题、H2 读 wiki、H3 增删改题目、H4 发起生成（结果同步到 Web 与移动端）。

---

## 6. 详细功能设计

### 6.1 知识管理（Wiki，含 Git‑like 分支）

#### 6.1.1 子页面
- 列表页：左侧目录树（按集合/文件夹），右侧文件列表，支持搜索（标题、正文全文）。
- 详情页：Markdown 渲染 + 右侧抽屉显示「版本历史」「关联题目」「分支」。
- 上传页：拖拽 / 选择本地 .md，多文件并行解析。

#### 6.1.2 「分支/合并」最小可用规则
- 每篇 wiki 有一个 `main` 分支，作为权威版本。
- 用户可基于任意版本 `checkout` 出一个命名分支（如 `draft-2026-05`）。
- 编辑保存生成 `commit`（记录 diff 与时间）。
- `merge`：以 main 为目标合并；若同一行被两侧修改，进入**冲突解决 UI**（左/右/手动三栏，最终保存为一次新的 commit）。
- 不需要实现 rebase、cherry-pick、远程仓库等高级能力（避免一期复杂度爆炸）。

#### 6.1.3 解析规则
- 仅识别 `.md` / `.markdown`（一期不接 docx/pdf）。
- 解析后保留原文（不重写），渲染时使用前端 markdown 渲染器。
- 自动提取：标题（首个 H1，否则文件名）、TOC、字数、内联图片引用（一期仅记录链接，不上传图床）。

#### 6.1.4 实体（核心字段）

```text
Wiki
  id, title, current_main_commit_id, owner_id(预留), collection_id,
  created_at, updated_at, deleted_at(软删除)

WikiBranch
  id, wiki_id, name, head_commit_id, created_at

WikiCommit
  id, wiki_id, branch_id, parent_commit_id, author_id(预留),
  message, content_md, content_hash, created_at

WikiCollection (文件夹)
  id, name, parent_id(nullable), owner_id(预留), visibility(预留: private|link|team)
```

#### 6.1.5 接口语义（REST 风格示意）
- `POST /wiki/upload`（multipart，支持多文件）
- `GET /wiki?collection_id=&q=`
- `GET /wiki/{id}`（默认返回 main 最新 commit）
- `GET /wiki/{id}/branches` / `POST /wiki/{id}/branches`
- `POST /wiki/{id}/commits`（在指定 branch 上提交）
- `POST /wiki/{id}/merge`（branch → main，返回是否冲突 + 冲突块）
- `DELETE /wiki/{id}`（软删）

---

### 6.2 大模型对话（Chat）

#### 6.2.1 能力
- 多会话；每会话独立选择**模型 + 功能 Prompt**（默认绑定到「通用对话」prompt 模板）。
- 消息支持文本 + 图片附件；图片是否真的传给模型，取决于所选模型的能力位（`supports_vision = true/false`）。
- 流式输出（SSE / WebSocket 二选一，技术建议见 §11）。

#### 6.2.2 Provider 与模型配置（D3：本地 + 云端共存）

Provider 抽象（与 OpenAI 兼容协议为主，便于一次接入多家）：

```text
ModelProvider
  id, name, type(enum: openai_compatible | ollama | anthropic | custom),
  base_url, api_key(加密存储), enabled, created_at

Model
  id, provider_id, name(如 gpt-4o-mini / qwen2.5:7b),
  supports_vision(bool), supports_streaming(bool),
  context_window(int), is_default(bool), enabled(bool)
```

> 一期内置 Provider 模板：`openai_compatible`（适配 OpenAI / DeepSeek / 通义 / 智谱等大多数厂商）、`ollama`（本地）、`anthropic`（可选）。  
> **默认关闭云端 Provider**，需用户在设置里显式启用并填写 Key，符合「私有化优先」。

#### 6.2.3 Prompt 模板管理（关键设计）

```text
PromptTemplate
  id, name, scene(enum: chat_general | wiki_to_questions | answer_scoring | wiki_summary),
  content, version_no, is_current(bool), notes, created_at

FunctionBinding (功能 → 当前生效 Prompt + 模型)
  id, scene, prompt_template_id, model_id, params_json(如 temperature, top_p)
```

规则：
- 同一 `scene` 只能有一个 `is_current=true`。
- 修改 prompt 会自动产出新版本（version_no +1），旧版本保留只读，确保**历史题目可复现**。
- 题目、评分结果会在生成时**冻结当时的 prompt_template_id 与 model_id**（见 §6.3、§6.4）。

#### 6.2.4 实体（会话与消息）

```text
Chat
  id, title, model_id, prompt_template_id, created_at

Message
  id, chat_id, role(enum: system|user|assistant), content_text,
  attachments_json(图片相对路径与元数据), token_usage_json, created_at
```

---

### 6.3 面试问答库

#### 6.3.1 生成入口
- 在 wiki 列表多选 → 「生成面试题」。
- 在 wiki 详情页右上 → 「生成面试题」。

#### 6.3.2 生成参数（用户每次可微调，默认值如下）

| 参数 | 默认值 | 说明 |
|---|---|---|
| 单篇题量 | 12 `[ASSUMPTION: E1 未指定]` | 单篇 wiki 一次生成的题数上限 |
| 题型比例 | 八股 70% / 场景题 30% | 八股=体系化概念；场景题=带追问链 |
| 难度分布 | 易 20% / 中 60% / 难 20% | 在 prompt 中要求模型尽量均衡 |
| 语言 | 中文 | 一期仅中文 |
| 去重策略 | 与已入库题目按题干 embedding/规则比对 | 一期最小实现：题干字符串相似度 ≥ 0.85 视为重复，标红可跳过 |

#### 6.3.3 预览与入库流程
1. 用户点「生成」→ 后端按 §11 调用模型 → 严格 JSON 解析。
2. 候选题进入**预览面板**（不写入正式题库表），用户逐题：
   - 勾选 / 反选 / 全选；
   - 直接编辑题干、标签、答案；
   - 标记「丢弃」；
3. 点击「入库」→ 持久化为正式题目，并冻结 `prompt_template_id`、`model_id`、`source_commit_id`。

#### 6.3.4 实体

```text
QuestionBankCollection (G2：可共享的题库集合)
  id, name, parent_id(nullable), owner_id(预留), visibility(预留)

Question
  id, collection_id, question_text, answer_standard, difficulty(enum: easy|medium|hard),
  source_wiki_id, source_commit_id, source_anchor(预留: 段落 hash),
  generated_by_prompt_id, generated_by_model_id,
  created_at, updated_at, deleted_at

Tag
  id, name, kind(enum: system|user)

QuestionTag
  question_id, tag_id

QuestionCandidate (预览面板临时表)
  id, batch_id, payload_json, picked(bool), edited(bool), created_at
```

#### 6.3.5 列表与详情
- 列表筛选：题库集合、标签（多选 AND/OR 切换）、来源 wiki、难度、是否错题（基于最近一次作答 < B 视为错题）。
- 详情：题干 / 标签 / 标准答案 / 来源 wiki（可点击跳转 §6.1 对应 commit）/ 历史作答列表 / 复制 / 编辑 / 删除（软删）。

#### 6.3.6 默认生成 Prompt（v1，可在设置改）

```text
[系统角色]
你是一名资深技术面试官 & 面试题命题专家。

[任务]
请基于下面给出的一篇 Markdown 文档，命制贴近真实面试场景的高频面试题。

[输出硬约束]
1. 仅输出一个 JSON 数组，不要任何前后缀文字、不要 markdown 代码块包裹。
2. 数组长度 = {N}（默认 12）。
3. 每一项严格遵守以下字段与类型：
   {
     "question": string,        // 面试题题干，10-80 字，避免直接复述原文长句
     "tag": string[],           // 1-4 个，技术/能力维度标签
     "answer": string,          // 结构：① 结论先行；② 关键要点（要点式）；③ 可被追问的方向
     "difficulty": "easy" | "medium" | "hard",
     "type": "concept" | "scenario",  // concept=八股/体系化；scenario=场景题/含追问
     "origin": string           // 来源文档标题（与传入一致）
   }
4. 题型比例：concept ≈ 70%，scenario ≈ 30%。
5. 难度比例：easy 20% / medium 60% / hard 20%。
6. 不得编造文档未涉及的事实；若文档信息不足以支撑一道高质量题，宁可少出，但仍保持数组结构合法（用占位标记 difficulty/type 仍合法）。
7. 题目之间避免语义重复，覆盖不同子主题。

[输入]
文档标题：{TITLE}
文档正文（markdown）：
{MARKDOWN}
```

JSON Schema（用于服务端校验）：

```json
{
  "type": "array",
  "items": {
    "type": "object",
    "required": ["question", "tag", "answer", "difficulty", "type", "origin"],
    "properties": {
      "question": { "type": "string", "minLength": 4 },
      "tag": { "type": "array", "items": { "type": "string" }, "minItems": 1, "maxItems": 6 },
      "answer": { "type": "string", "minLength": 10 },
      "difficulty": { "enum": ["easy", "medium", "hard"] },
      "type": { "enum": ["concept", "scenario"] },
      "origin": { "type": "string" }
    },
    "additionalProperties": false
  }
}
```

---

### 6.4 面试作答页面

#### 6.4.1 出题设置（Practice Setup）
- 范围（可叠加）：
  - 题库集合（必选，可多选）
  - 标签（多选，AND/OR 切换）
  - 来源 wiki（多选）
  - 模式：顺序 / 随机 / **错题回顾**
  - 错题定义：**最近一次作答评级 < B**（即 B/A/S 视为通过；S 为最佳）
- 数量：默认 10，可调（1–50）。
- 时间限制：可选（不限 / 30s / 60s / 120s 每题）。

#### 6.4.2 作答页
- 单题模式：题干 + 输入框（多行）/ 录音转写（二期）。
- 提交后立刻调评分模型，展示：
  - **综合等级 S / A / B / C**（C = 未达标，亦即「错题」）。
  - **4 维分数**（每维 0–100）：correctness（正确性）、completeness（完整性）、structure（表达结构）、depth（深度）。
  - **改进建议**（要点式 3–5 条）。
  - **对照标准答案**（折叠展开）。
- 评级规则（按你「F1 决定 + 综合参考」）：

```
final_grade =
  S  if correctness ≥ 90 AND avg(comp, struct, depth) ≥ 80
  A  if correctness ≥ 80 AND avg(comp, struct, depth) ≥ 65
  B  if correctness ≥ 65
  C  otherwise   (视为错题)
```

> 即「正确性是硬门槛」，其余三维作为加成；阈值集中放配置文件，便于后续微调。

#### 6.4.3 历史记录与展示
- 每次作答**追加一条**记录（保留最近 N 次，N 默认 10，可在设置改）。
- 题目详情默认展示**最近一次**评级与分数。
- 提供「趋势图」（最近 N 次 correctness 与综合等级的时间序列），用于自我观察。

#### 6.4.4 实体

```text
AnswerAttempt
  id, question_id, user_id(预留), user_answer_text,
  grade(enum: S|A|B|C),
  score_correctness, score_completeness, score_structure, score_depth,
  feedback_text, model_id, prompt_template_id,
  created_at
```

#### 6.4.5 评分 Prompt（v1）

```text
[系统角色]
你是一名严格、客观的技术面试官，负责对候选人的作答打分。

[评分维度与权重提示]
- correctness（正确性，0-100）：事实/概念是否正确；是硬门槛。
- completeness（完整性，0-100）：是否覆盖关键要点。
- structure（结构性，0-100）：是否结论先行、条理清晰。
- depth（深度，0-100）：是否涉及边界、权衡、追问方向。

[评分输出硬约束]
仅输出一个 JSON 对象，不要任何额外文字或代码块包裹：
{
  "score_correctness": number,    // 0-100 整数
  "score_completeness": number,
  "score_structure": number,
  "score_depth": number,
  "feedback": string[],           // 3-5 条改进建议，要点式，每条 ≤ 40 字
  "summary": string               // 一句话总评，≤ 60 字
}

[最终等级由服务端按规则计算，不需要你输出 grade]

[输入]
题目：{QUESTION}
标准答案（仅供参考，不要在 feedback 里直接复述）：{ANSWER_STANDARD}
候选人作答：{USER_ANSWER}
```

JSON Schema：

```json
{
  "type": "object",
  "required": ["score_correctness", "score_completeness", "score_structure", "score_depth", "feedback", "summary"],
  "properties": {
    "score_correctness": { "type": "integer", "minimum": 0, "maximum": 100 },
    "score_completeness": { "type": "integer", "minimum": 0, "maximum": 100 },
    "score_structure": { "type": "integer", "minimum": 0, "maximum": 100 },
    "score_depth": { "type": "integer", "minimum": 0, "maximum": 100 },
    "feedback": { "type": "array", "items": { "type": "string" }, "minItems": 1, "maxItems": 8 },
    "summary": { "type": "string" }
  },
  "additionalProperties": false
}
```

---

### 6.5 设置（Settings）

- **模型与 Provider**：增删改 Provider；为每个 Provider 拉取/手动维护可用模型；设置默认模型；测试连通性。
- **Prompt 模板**：每个 scene 一组（chat_general、wiki_to_questions、answer_scoring、wiki_summary）；版本列表 + 「设为当前」。
- **练习偏好**：错题阈值、保留历史次数 N、默认题量、默认题型/难度分布。
- **数据**：导出题库（JSON / CSV）、导出 wiki（zip 包含 .md 与版本元数据）、清空。
- **外观**：明/暗、语言（一期固定中文，预留 i18n）。

---

## 7. 多端体验拆解（H1‑H4 均要）

> 一期不发布微信小程序；移动端使用 **响应式 H5**（与 Web 同源）。二期再用 Taro / uni-app 输出微信小程序。

### 7.1 移动端布局原则
- 顶部 Tab：知识 / 题库 / 练习 / 我的（合并对话入口到「我的」或右上图标）。
- 单列优先，所有列表项点击进入详情；多选改为长按或顶部「编辑模式」。

### 7.2 移动端各功能取舍

| 功能 | Web | Mobile H5 一期 |
|---|---|---|
| H2 阅读 Wiki | 完整 | ✅ 完整（含 TOC、版本切换；分支/合并仅查看，不编辑） |
| H3 题目增删改 | 完整 | ✅ 完整（增删改、标签编辑） |
| H4 触发生成面试题 | 完整（含预览勾选） | ✅ 触发与预览勾选都可用，但建议默认按「单篇生成」简化界面 |
| H1 练习 | 完整 | ✅ 完整（练习是移动端最重要场景） |
| 对话 + 图片上传 | 完整 | ✅ 完整 |
| Wiki 上传 / 编辑 / 分支合并 | 完整 | 仅阅读 + 查看版本；写操作引导回 Web |
| 模型与 Prompt 配置 | 完整 | 只读查看（写操作回 Web，降低出错率） |

---

## 8. 权限与协作（A1 一期仅预留）

- 一期数据库层面已**保留** `owner_id`、`visibility` 等字段，但所有读写都以「本地单用户」短路。
- 二期开启：
  - 角色：Owner / Editor / Viewer（在 QuestionBankCollection、WikiCollection 上生效）。
  - 共享单元：**G2** —— 题库集合 / Wiki 集合（不到单条题目级别）。
  - Wiki 协作：升级 B3 为多人 PR 流程（创建分支 → 提交 → 发起合并请求 → 评审 → 合并）。

---

## 9. 非功能需求

- **性能**：上传 1MB md 文件解析 < 1s；列表分页 20 条；评分模型调用前端需有 Loading 与超时（默认 60s）。
- **可观测性**：每次模型调用记录 token usage、耗时、错误码（写入日志，不展示给用户）。
- **稳定性**：模型返回非 JSON 时，服务端尝试一次「修复重试」（让模型自我修正格式），仍失败则向用户报错并允许重试。
- **安全**：API Key 在服务端加密存储，不下发到前端；图片附件存本地目录，路径不直接暴露宿主机绝对路径。
- **数据**：所有删除均为软删；导出/导入需校验完整性（外键 + Schema）。
- **i18n**：文案集中化，一期中文，二期预留英文资源占位。
- **可访问性**：键盘可达 + Aria 标签（练习页尤其重要）。

---

## 10. 关键状态机（节选）

### 10.1 题目候选 → 入库

```
DRAFT_GENERATED  --user 勾选-->  PICKED  --点击入库-->  PERSISTED
DRAFT_GENERATED  --user 编辑-->  EDITED (仍 DRAFT)  --入库-->  PERSISTED
DRAFT_GENERATED  --丢弃-->       DISCARDED
PERSISTED        --软删-->        DELETED
```

### 10.2 Wiki 分支合并

```
BRANCH_OPEN  --commit-->  BRANCH_OPEN
BRANCH_OPEN  --merge 请求--> MERGING
MERGING      --无冲突-->     MERGED (写入 main 新 commit)
MERGING      --有冲突-->     CONFLICT  --用户解决-->  MERGED
MERGED       --可保留也可删除分支-->
```

### 10.3 作答

```
ASKED  --submit-->  SCORING  --模型成功-->  SCORED (落库 AnswerAttempt)
SCORING --模型失败-->  SCORE_FAILED (允许重试)
```

---

## 11. 技术建议（非强约束，供代码生成参考）

> 你后续如果接受这些默认值，代码生成阶段会更顺；若有偏好可一句话覆盖。

- **后端**：Python (FastAPI) 或 Node.js (NestJS)；优先 **FastAPI**（与 AI 生态契合好）。
- **数据库**：一期 **SQLite**（私有化部署友好）；二期切 PostgreSQL。
- **存储**：本地文件系统 `./data/uploads/`、`./data/wikis/`、`./data/attachments/`。
- **前端**：React + TypeScript + Vite + Tailwind + shadcn/ui；Markdown 渲染 `react-markdown` + `rehype-highlight`。
- **移动端**：一期与 Web 同源 H5（响应式）；二期 **Taro**（输出 H5 + 微信小程序）。
- **流式**：模型对话使用 SSE；生成/评分这类「一次性 JSON」走普通 HTTP。
- **模型接入抽象**：统一适配 OpenAI Chat Completions 协议；Ollama 走 `/api/chat`，由后端做协议归一化。
- **部署**：一期 `docker-compose` 或单二进制；后端默认监听 `127.0.0.1`，可配置为 `0.0.0.0`（用于内网 H5 访问）。
- **JSON 解析容错**：使用「严格 JSON 解析失败 → 让模型修复 → 仍失败抛错」三段式。

---

## 12. 风险与边界

- **R1（一期最大风险）**：模型输出格式漂移导致生成/评分失败。**缓解**：硬约束 prompt + JSON Schema 校验 + 一次自动修复重试 + 失败可手动重试。
- **R2**：本地模型质量参差，影响题库可用性。**缓解**：在「Provider 设置」标注「推荐用于生成题目的模型」；允许「生成用云端模型 + 对话用本地模型」分功能绑定。
- **R3**：Git‑like 分支合并若做大会拖累一期。**缓解**：严格收敛为「单分支基线 + 命名分支 + 三栏冲突合并」。
- **R4**：移动端 H4（触发生成）若做全套预览交互体验差。**缓解**：移动端默认「单篇生成」入口，预览改为「全选 / 反选 + 单题展开编辑」，不做多列复杂表格。
- **R5（二期）**：微信小程序合规与公网 HTTPS 必需。**缓解**：二期再做，本 PRD 已划清边界。

---

## 13. 验收清单（一期上线门槛）

- [ ] 能拖拽多文件 .md 上传并解析成功
- [ ] Wiki 详情可看到版本历史，可创建分支、提交、合并（含冲突 UI）
- [ ] 可配置至少 1 个本地模型 + 1 个云端模型 Provider，并切换正常对话
- [ ] 对话支持图片附件，且模型 `supports_vision=false` 时给出明确提示
- [ ] 「设置 → Prompt 模板」可新增版本并设为当前，旧版本只读保留
- [ ] 单篇 wiki 生成 12 道候选题，预览勾选入库；入库题目冻结 prompt/model/commit
- [ ] 题库列表可按标签（AND/OR）、来源、难度、错题筛选
- [ ] 练习页支持顺序/随机/错题模式；评分返回 4 维分数与改进建议
- [ ] 等级按规则 S/A/B/C 计算；同题保留最近 10 次记录，默认展示最近一次
- [ ] 移动端 H5 在常见手机宽度（≥ 360px）下完成 H1‑H4 全部主路径

---

## 14. 待你后续一句话覆盖的「默认假设」清单

- `[ASSUMPTION-E1]` 单篇生成默认 **12 题**。
- `[ASSUMPTION-E2]` 八股 / 场景题比例默认 **7 : 3**，难度 **2 : 6 : 2**。
- `[ASSUMPTION-N]` 每题作答历史保留 **最近 10 次**。
- `[ASSUMPTION-错题阈值]` 最近一次 **评级 < B**（即等级为 C）记为错题。
- `[ASSUMPTION-评分阈值]` 见 §6.4.2 公式，集中放配置。
- `[ASSUMPTION-技术栈]` 后端 FastAPI、前端 React+Vite+Tailwind+shadcn、SQLite、Taro 二期。

---

## 15. 平台化与社区化扩展（v2.0 规划）

> 本章为 PRD v1.0 之后的**重大方向扩展**，记录将产品从「私有化 / 单用户知识训练工具」演进为「**公网 SaaS + UGC 社区 + 内容交易市场 + AI 面试服务**」的设计。本章内容默认面向**云社区版**；私有版可整章关闭。

### 15.0 定位演进与总原则

#### 15.0.1 双形态定位（重要）

v1.0 的第一原则是「私有化优先、默认监听 `127.0.0.1`、云端 Provider 默认关闭」。社区化功能与之冲突，因此明确**两个发行形态**，共用同一代码库、用配置开关区分：

| 形态 | 目标用户 | 社区/交易/语音 | 部署 |
|---|---|---|---|
| **私有版（self-host）** | 个人 / 内网小组 | 默认**关闭** | 单机 / docker-compose，监听内网 |
| **云社区版（SaaS）** | 公开注册用户 | **开启** | 公网 HTTPS、多租户、对象存储、支付通道 |

- 用 `SL_EDITION=private|cloud` 或一组 feature flag（`SL_FEATURE_MARKETPLACE`、`SL_FEATURE_COMMUNITY`、`SL_FEATURE_VOICE_INTERVIEW` 等）控制启停，保证私有版「干净、可离线、可信」。

#### 15.0.2 已具备的地基（对 v1.0 的修正）

- **账号体系与多租户鉴权在 v1.0 文档里写为「二期预留」，现已在代码中实现**：`Tenant` / `User` 表、JWT 登录、`AuthMiddleware`、按 `tenant_id` 的数据隔离、`/api/auth/login|register|me`。本章所有功能均建立在此之上。
- 因此 §3.2 / §8 中「账号/协作仅预留字段」的描述应视为**已落地**；社区版进一步把「租户」概念从「团队/组织」扩展到「个人公开主页」。

#### 15.0.3 落地优先级（按依赖 + 风险 + 留存排序）

1. **创意②求职目标与进展**（§15.2）—— 风险最低、复用现有评分数据、强留存。**最先做**。
2. **创意④社区与分块讨论区**（§15.4）—— 建立 engagement，需先有审核与反垃圾。
3. **创意①题目分享（免费版）**（§15.1）—— 先验证内容供需，**不涉及资金**。
4. **创意①收费 + 平台抽成**（§15.1）—— 合规成本最高（支付分账/结算/发票/退款），市场跑通后再上。
5. **创意③AI 语音面试**（§15.3）—— 先做**文字版模拟面试 MVP**，语音作为增强（成本与延迟最高）。

---

### 15.1 创意①：面试题分享与交易市场

#### 15.1.1 价值与分析
- **价值**：建立「内容供给—消费」飞轮，是社区版的内容护城河与变现来源（平台抽成）。
- **复杂度**：免费分享复杂度中等；**收费交易复杂度高**（支付分账、结算账期、发票、退款、风控）。
- **建议**：分两步——先免费分享（验证供需与质量），再引入收费与抽成。

#### 15.1.2 共享单元与可见性
- 共享单元沿用 §8 的 **G2 粒度**：以 **题库集合（`QuestionBankCollection`）** 为上架/分享单位，而非单题，降低审核与定价复杂度。
- 可见性：`private`（仅自己）/ `unlisted`（带链接可见）/ `public_free`（公开免费）/ `public_paid`（公开付费）。

#### 15.1.3 商品与定价
```text
MarketListing (上架记录)
  id, tenant_id(卖家), collection_id, title, summary, cover_url,
  pricing_type(enum: free | paid),
  price_cents(int, 人民币分), currency(default 'CNY'),
  platform_fee_bps(int, 平台抽成基点, 如 1500=15%),
  status(enum: draft | in_review | listed | rejected | delisted),
  review_note, sales_count, rating_avg, rating_count,
  created_at, updated_at

MarketOrder (订单)
  id, listing_id, buyer_tenant_id, seller_tenant_id,
  amount_cents, platform_fee_cents, seller_net_cents,
  status(enum: created | paid | refunded | closed),
  pay_channel(enum: wechat | alipay | stripe),
  pay_txn_id, paid_at, refunded_at, created_at

Entitlement (购买后授权 / 访问权)
  id, buyer_tenant_id, listing_id, order_id,
  granted_at, revoked_at(nullable)

PayoutAccount (卖家结算账户, 收款方)
  id, tenant_id, channel, account_ref(脱敏), verified(bool)

SellerSettlement (结算单, 周期性)
  id, seller_tenant_id, period_start, period_end,
  gross_cents, fee_cents, net_cents, status, paid_at
```

#### 15.1.4 关键流程
1. 卖家把题库集合「上架」→ 进入 `in_review`（人工/规则审核：版权、低质、违禁）。
2. 审核通过 → `listed`，进入市场列表/搜索。
3. 买家下单 → 调用支付通道 → 回调 `paid` → 生成 `Entitlement`（**购买的是访问/复制授权，不是所有权**）。
4. 平台按 `platform_fee_bps` 计提抽成，余额计入卖家可结算金额；按结算周期生成 `SellerSettlement` 并打款。
5. 退款：限定窗口（如 7 天且未大量下载）；退款回收 `Entitlement`。

#### 15.1.5 接口（示意）
- `POST /api/market/listings`（上架）/ `GET /api/market/listings?q=&tag=&sort=`
- `POST /api/market/listings/{id}/submit`（提交审核）/ `POST .../review`（管理员）
- `POST /api/market/orders`（下单，返回支付参数）/ `POST /api/market/pay/callback/{channel}`（支付回调，验签）
- `GET /api/market/entitlements`（我购买的）
- `GET /api/market/settlements`（卖家结算）

#### 15.1.6 MVP 边界与风险
- **MVP**：先做 `free` + `unlisted/public_free`，跑通「分享—复制到我的题库」闭环，**暂不接支付**。
- **合规风险（高）**：需经营主体、ICP/支付商户号、分账资质、发票/税务；**版权与剽窃**（题目可能搬运自他处）需举报与下架机制；定价含税与对账。
- **质量风险**：评分/评论 + 抽样审核 + 反刷单（同一买家/IP、异常退款监控）。

---

### 15.2 创意②：求职目标与进展追踪

#### 15.2.1 价值与分析
- **价值**：把「零散刷题」升级为「**面向目标岗位的备考主线**」，是**留存与个性化推荐的核心**；几乎完全复用已有的 `AnswerAttempt` 评分数据，**ROI 最高、风险最低**。
- **建议**：作为社区版**第一个落地**功能。

#### 15.2.2 模型与能力
- **目标岗位**：用户选择/自定义目标岗位（如「后端开发-Java-中级」）。平台维护一套**岗位能力模型**：岗位 → 能力维度（标签/知识点）→ 期望掌握度。
- **当前进展**：基于该岗位关联标签下题目的**最近作答表现**（综合等级 / 4 维分数）聚合出「掌握度」，并给出**雷达图 + 弱项清单 + 推荐练习**。

```text
JobRole (岗位字典, 平台维护 + 允许自定义)
  id, name, family(方向), level(初/中/高), is_system(bool), tenant_id(自定义时归属)

JobRoleSkill (岗位 → 能力点)
  id, job_role_id, tag_id(关联现有 Tag), weight(权重), expected_mastery(0-100)

UserGoal (用户的求职目标)
  id, tenant_id, user_id, job_role_id,
  target_date(nullable), status(enum: active | achieved | archived), created_at

GoalProgressSnapshot (进展快照, 便于趋势)
  id, user_goal_id, overall_mastery(0-100),
  skill_breakdown_json, weak_tags_json, computed_at
```

- **掌握度算法（MVP，可配置）**：某能力点掌握度 = 该标签下题目最近一次作答的加权得分均值（correctness 为硬门槛，对齐 §6.4.2 评级规则）；岗位整体掌握度 = 各能力点按 `weight` 加权。
- **推荐**：弱项标签 → 直接生成一条「练习设置」（复用 §6.4.1 出题），形成「测—练—再测」闭环。

#### 15.2.3 接口（示意）
- `GET /api/job-roles?q=` / `POST /api/job-roles`（自定义）
- `POST /api/goals`（设定目标）/ `GET /api/goals/{id}/progress`
- `POST /api/goals/{id}/recommend-practice`（返回针对弱项的 PracticeSetup）

#### 15.2.4 风险
- 进展度量「可信度」是关键：题目覆盖不足时掌握度会失真，需展示「样本量/覆盖率」并对低覆盖给出提示。

---

### 15.3 创意③：AI 智能模拟面试（按岗位出题 + 语音）

#### 15.3.1 价值与分析
- **价值**：最强差异化体验——「**像真面试一样**」按岗位多轮追问、即时点评。
- **复杂度（高）**：实时语音（ASR + LLM + TTS）链路的**延迟、成本、稳定性**均是挑战。
- **建议**：分两层落地——
  - **MVP（文字版）**：复用 Chat + 评分能力，做「多轮、有追问、按岗位选题、最后给面试报告」的**文字模拟面试**。
  - **增强（语音版）**：在文字版稳定后接入实时语音。

#### 15.3.2 会话与编排
- 一场模拟面试 = 一个 `InterviewSession`，包含：开场 → 按 `UserGoal/JobRole` 抽题或现场生成题 → 用户作答 → **追问（基于回答深度自动决定是否追问）** → 下一题 → 结束生成**面试报告**（综合 + 分维 + 高频弱点 + 建议）。
- 出题来源：①题库（按岗位标签）；②即时生成（复用 §6.3 生成能力，按岗位/JD 定制）。

```text
InterviewSession
  id, tenant_id, user_id, job_role_id(nullable), mode(enum: text | voice),
  status(enum: ongoing | finished | aborted),
  question_plan_json, started_at, finished_at

InterviewTurn (每一问一答)
  id, session_id, seq, question_text, source(enum: bank | generated),
  user_answer_text, asr_audio_url(nullable),
  followups_json, score_json(复用 §6.4 4维), created_at

InterviewReport
  id, session_id, overall_grade, dimension_avg_json,
  strengths_json, weaknesses_json, advice_text, created_at
```

#### 15.3.3 语音链路（增强期技术建议）
- **ASR**（语音转文字）+ **LLM**（对话/追问/评分）+ **TTS**（文字转语音）三段；优先选支持 **Realtime / 流式** 的供应商以压低延迟。
- 端侧：WebRTC / MediaRecorder 采集；服务端做编排与限流。
- **成本控制**：单场时长上限、按 token/分钟计费监控、可降级为「半双工（按住说话）」以省实时通道成本。

#### 15.3.4 风险与合规
- **语音是个人敏感信息**：录音的收集/存储/留存期限需遵守《个人信息保护法》，明确**告知同意**、可删除、可不留存（默认只存转写文本、不存音频）。
- **成本与延迟**：实时语音单价高，需配额与套餐绑定（与 §15.1 变现联动）。

---

### 15.4 创意④：社区与分块讨论区

#### 15.4.1 价值与分析
- **价值**：UGC 粘性与冷启动内容来源；与题目/Wiki/岗位强关联的「**分块讨论**」比大而全论坛更聚焦。
- **「分块」定义**：讨论区**挂载到具体对象**（题目 / 题库集合 / Wiki / 岗位），而非独立板块，做到「就题论题」。

```text
Discussion (讨论主题/帖)
  id, tenant_id(作者), scope(enum: question | collection | wiki | job_role | global),
  target_id(对应对象 id, global 时为 null),
  title, body_md, tags_json, status(enum: open | locked | hidden),
  like_count, comment_count, created_at, updated_at

Comment (评论, 支持楼中楼)
  id, discussion_id, parent_comment_id(nullable), author_tenant_id,
  body_md, like_count, status, created_at

Reaction (点赞/收藏通用)
  id, target_type(enum: discussion | comment), target_id,
  user_tenant_id, kind(enum: like | bookmark), created_at

Report (举报)
  id, target_type, target_id, reporter_tenant_id, reason, status, created_at

Notification (通知: 被回复/被赞/被@)
  id, recipient_tenant_id, type, payload_json, read_at, created_at
```

#### 15.4.2 接口（示意）
- `GET /api/discussions?scope=question&target_id=123`
- `POST /api/discussions` / `POST /api/discussions/{id}/comments`
- `POST /api/reactions` / `POST /api/reports`
- `GET /api/notifications`（未读数 + 列表）

#### 15.4.3 MVP 边界与风险
- **MVP**：题目维度讨论 + 评论（单层即可）+ 点赞 + 举报；通知可后置。
- **风险（中-高）**：**内容安全合规**（违禁词/政治敏感/广告）、反垃圾（频控、新号限制）、运营冷启动（官方种子内容）；需后台审核队列与一键隐藏/封禁。

---

### 15.5 创意⑤+：扩展功能 Backlog（暂不展开，仅登记）

| 候选 | 说明 | 备注 |
|---|---|---|
| 排行榜 / 成就 / 积分 | 练习量、连续打卡、岗位掌握度榜 | 游戏化，提升留存 |
| 学习计划 / 打卡提醒 | 与 §15.2 目标联动，复用已实现的「定时推送」 | 低成本，可早做 |
| 简历诊断 | 上传简历 → AI 给岗位匹配与改进 | 与目标岗位联动 |
| 企业/真题专区 | 按公司聚合面经与题库 | 强版权/合规约束 |
| 学习小组 / 关注 / 私信 | 社交关系链 | 审核与隐私成本上升 |
| 会员订阅制 | 语音面试/高级报告打包售卖 | 与 §15.1、§15.3 变现统一 |
| 开放 API / MCP | 第三方接入题库与评分 | 面向开发者生态 |

> 原则：Backlog 仅登记，不进入承诺范围，避免范围蔓延（见 §15.9-R 范围风险）。

---

### 15.6 平台化数据模型增量（ER 概览）

```
User n—1 Tenant                       # 已实现
Tenant 1—n QuestionBankCollection     # 已实现，作为市场上架单元

# 创意①市场
QuestionBankCollection 1—1 MarketListing 1—n MarketOrder 1—1 Entitlement
Tenant(卖家) 1—1 PayoutAccount ; Tenant 1—n SellerSettlement

# 创意②目标与进展
JobRole 1—n JobRoleSkill (—1 Tag) ; User 1—n UserGoal (—1 JobRole) 1—n GoalProgressSnapshot

# 创意③模拟面试
User 1—n InterviewSession 1—n InterviewTurn ; InterviewSession 1—1 InterviewReport

# 创意④社区
Discussion 1—n Comment ; (Discussion|Comment) 1—n Reaction/Report ; User 1—n Notification
```

---

### 15.7 新增非功能需求（社区版专属）

- **支付与结算**：对接微信支付/支付宝/Stripe；支付回调**必须验签 + 幂等**；金额以**整数分**存储；分账与对账可追溯；退款有窗口与审计。
- **合规资质**：经营主体、ICP 备案、支付商户号、（含交易）增值税发票与税务；用户协议、隐私政策、内容协议上线前必备。
- **内容安全审核**：UGC（题目、讨论、评论、个人资料）接入文本审核（违禁/敏感/广告）；人工复审队列；一键隐藏/封禁/申诉。
- **个人信息保护（PIPL）**：明确收集范围与目的、获取**告知同意**；语音默认**只存转写文本**、不留原始音频（如留存须单独同意 + 留存期限 + 可删除）。
- **风控与反作弊**：频控、新账号限制、异常下单/退款监控、刷赞刷分识别。
- **成本可观测**：LLM / ASR / TTS 调用按租户计量计费，套餐与配额限制（与变现联动）。
- **可扩展性**：云版数据库切 PostgreSQL（见 §11）；附件/封面/音频走对象存储（S3 兼容），不再依赖本地磁盘。

---

### 15.8 分期落地建议与依赖关系

| 阶段 | 内容 | 依赖 |
|---|---|---|
| **v2.0-a** | 创意②目标与进展（§15.2）；学习计划复用已实现的定时推送 | 现有评分数据、多租户（均已具备） |
| **v2.0-b** | 创意④社区讨论 MVP（题目维度）+ 审核后台 | 账号体系、内容审核能力 |
| **v2.0-c** | 创意①分享（免费版）+「复制到我的题库」 | 题库集合可见性、举报/下架 |
| **v2.1** | 创意③文字版模拟面试 + 面试报告 | Chat/评分能力、目标岗位 |
| **v2.2** | 创意①收费 + 平台抽成 + 结算 | 支付资质、风控、对账 |
| **v2.3** | 创意③语音版模拟面试；会员订阅 | 实时语音供应商、计费配额、PIPL 合规 |

> 关键依赖链：**多租户/账号（已完成）→ 目标与进展 → 社区 → 免费分享 → 付费交易 / 语音面试**。资金与语音是「最后做、最重合规/成本」的两块。

---

### 15.9 平台化风险与边界（对 §12 的补充）

- **R6 定位漂移**：公网社区与「私有化优先」原则冲突。**缓解**：双形态 + feature flag，私有版默认全关。
- **R7 支付/财税合规（高）**：抽成涉及分账、发票、退款、对账。**缓解**：免费先行；收费上线前完成资质与对账；金额整数分 + 幂等回调。
- **R8 内容版权与安全**：分享题目可能搬运/侵权，UGC 可能违规。**缓解**：上架审核 + 举报下架 + 文本审核 + 人工复审。
- **R9 语音成本与隐私**：实时语音贵且涉敏感信息。**缓解**：文字版先行；语音默认不存音频；配额与套餐绑定。
- **R10 范围蔓延**：「等等」类需求易无限膨胀。**缓解**：Backlog 仅登记（§15.5），每期只承诺表格内范围。

---

## 附录 A：实体关系总览（文字版 ER）

```
WikiCollection 1—n Wiki 1—n WikiBranch 1—n WikiCommit
Wiki 1—n Question (source_wiki_id, source_commit_id)

QuestionBankCollection 1—n Question 1—n AnswerAttempt
Question n—n Tag (via QuestionTag)

ModelProvider 1—n Model
PromptTemplate (按 scene 分组，多版本)
FunctionBinding 1—1 (scene → current PromptTemplate + Model)
Chat 1—n Message
```

---

## 附录 B：默认 Prompt 与 JSON Schema

见 §6.3.6（生成）与 §6.4.5（评分）。两者都遵循：

1. 仅输出 JSON，无前后缀、无 ```代码块包裹。
2. 服务端用 JSON Schema 严格校验，失败触发一次「自我修复」重试。
3. 题目与作答记录会**冻结**当时使用的 `prompt_template_id` 与 `model_id`，保证可复现。
