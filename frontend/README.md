# Frontend (React + Vite)

## 启动

```bash
npm install
npm run dev          # http://localhost:5173
```

Vite 已配置代理:`/api/*` → `http://localhost:8000`(可用 `VITE_API_BASE` 覆盖)。

若 `backend/.env` 设置了 `SL_BOT_API_TOKEN`，开发代理会自动带上 `X-SL-Token`；也可复制 `frontend/.env.example` 为 `.env.local` 并设置 `VITE_SL_BOT_TOKEN`（改 token 后需重启 `npm run dev`）。

## 目录结构

- `src/api/` 与后端通信(typed fetch 封装)
- `src/components/ui/` shadcn 风格基础组件(button / card / dialog / input / select / textarea / label / badge / toast)
- `src/components/layout/` AppLayout(桌面侧栏 + 移动底部 Tab)、PageHeader
- `src/pages/wiki/` 知识库:列表 / 上传 / 详情
- `src/pages/settings/` 设置:Provider & 模型 CRUD + 连通性测试
- `src/lib/utils.ts` `cn()` / 时间格式化

## 路由

| 路径 | 说明 |
|---|---|
| `/wiki` | 知识库列表(搜索) |
| `/wiki/upload` | 拖拽多文件上传 |
| `/wiki/:id` | 详情:Markdown + TOC + 分支占位 |
| `/chat` | 占位(下个迭代:多会话 + 流式 + 图片) |
| `/bank` | 占位(下个迭代:筛选 + 生成预览) |
| `/practice` | 占位(下个迭代:作答 + 评分) |
| `/settings` | 模型与 Provider · Prompt 模板(占位) · 数据(占位) |

## 响应式断点

- `< md` (768px):顶部内容区 + 底部 Tab(5 个图标 + 文字)
- `≥ md`:左侧 56 宽侧栏导航
- `≥ lg`:Wiki 详情页右侧抽屉(TOC / 分支)展开

## UI 设计风格

参考 shadcn/ui:中性灰底、`primary` 蓝、圆角 `0.6rem`、`border-input` + 浅卡片阴影。
深色模式已通过 CSS 变量定义,但一期主题切换 UI 在「设置 → 数据与外观」(待实现)。
