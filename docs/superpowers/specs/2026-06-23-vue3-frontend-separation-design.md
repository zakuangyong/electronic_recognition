# Vue3 前后端分离改造设计

## 背景

当前项目采用 `FastAPI + 多页面静态 HTML + 原生 JS` 的实现方式。后端同时承担页面托管、静态资源分发、业务 API 与识别结果跳转职责，前端页面包括：

- 识别工作台 `/`
- 知识库管理 `/knowledge`
- 图纸检索 `/search`

现有实现已经形成稳定的页面样式、交互逻辑和识别 pipeline 集成方式，但前端缺少组件化、状态管理、构建体系与独立部署能力。目标是在 **保持现有 pipeline、页面显示样式和核心交互逻辑不变** 的前提下，将架构升级为：

- 前端：独立部署的 `Vue3` 应用
- 后端：仅提供纯 API 的 `FastAPI` 服务
- 开发模式：前后端分别启动、分别调试

## 目标

- 将当前原生前端迁移为独立的 `Vue3` 应用
- 保持现有页面视觉层级、布局结构、核心字段展示和用户操作流程不变
- 后端不再提供前端页面路由和静态站点资源
- 路由允许按 Vue 应用重新规划
- 保持现有识别 pipeline、搜索能力、知识库存储和结果文件组织方式不变
- 为后续独立部署、组件复用、前端测试和接口演进建立清晰边界

## 非目标

- 不重写或修改识别 pipeline 的业务逻辑
- 不改变搜索索引、知识库存储和结果产物的数据来源
- 不进行 UI 风格重设计
- 不在此次改造中引入新的业务页面
- 不强制一次性清理所有旧 API 字段，迁移期允许兼容字段并存

## 现状摘要

### 前端现状

- 页面入口：`/`、`/knowledge`、`/search`
- 资源组织：`src/electronic_recognition/static/`
- 运行方式：每页一个 `HTML + JS + 可选 CSS`
- 状态管理：页面内 `state` 对象 + 手动 DOM 更新
- 渲染方式：`innerHTML` 拼接、模板节点复制、事件手动绑定

### 后端现状

- `FastAPI` 同时提供页面、静态资源、业务 API、上传与结果接口
- API 与前端调用天然绑定为同源相对路径
- 后端部分接口直接拼接前端页面 URL，例如结果页跳转地址

### 现有必须保留的行为

- 工作台上传、轮询、步骤日志与结果展示流程
- 识别结果恢复与按页锚点定位
- 搜索页检索模式、健康状态、demo query、重建索引、调试展示
- 知识库管理页的单元件/组合元件切换、编辑、校验、试运行、图片上传
- 现有视觉结构、区域划分、主要交互顺序和数据字段语义

## 方案对比

### 方案 A：Vue3 SPA + FastAPI 纯 API

- 前端目录：项目根下新增 `web/`
- 前端技术：`Vue3 + Vite + TypeScript + Vue Router + Pinia`
- 后端职责：仅保留 API 与资源文件接口
- 开发方式：前端和后端分别启动

优点：

- 完全符合前后端分离目标
- 组件化与状态管理最自然
- 后续部署、鉴权、CDN、接口版本化更清晰
- 公共组件、类型定义、测试体系更容易建立

缺点：

- 一次性迁移范围较大
- 需要补充 CORS、前端环境变量、前端路由与资源 URL 规范

结论：**推荐**

### 方案 B：Vue3 多页面应用 + FastAPI 纯 API

- 前端仍独立，但按多个 Vue 页面而非单 SPA 组织

优点：

- 更贴近当前每页独立的心智模型

缺点：

- 共享状态与公共组件组织分散
- 结果页跳转与路由体验较弱
- 长期收益低于 SPA

### 方案 C：渐进式局部 Vue 化，再二次拆分前后端

优点：

- 单次改动范围较小

缺点：

- 要维护两次架构迁移
- 与“彻底独立部署”的目标不一致

## 选型结论

采用 **方案 A：Vue3 SPA + FastAPI 纯 API**。

## 总体架构

### 前端

前端新建独立应用目录 `web/`，采用如下技术栈：

- `Vue3`
- `Vite`
- `TypeScript`
- `Vue Router`
- `Pinia`

前端负责：

- 页面路由
- 页面跳转
- 页面状态与视图渲染
- API 调用与错误提示
- 文件上传与轮询调度
- 结果页恢复与锚点处理

### 后端

后端保留现有 `FastAPI` 应用，但职责收缩为：

- 业务 API
- 识别任务发起与轮询
- 结果数据读取
- 文件与图片资源提供
- 搜索、知识库、规则、配置等数据接口

后端不再负责：

- 返回 HTML 页面
- 挂载前端静态站点
- 拼接前端页面地址

## 路由设计

### 前端路由

Vue 应用重新规划页面路径：

- `/`：重定向到 `/workbench`
- `/workbench`：识别工作台
- `/results/:resultId`：结果详情页
- `/knowledge`：知识库管理
- `/search`：图纸检索

说明：

- `ResultView` 支持 `#page-{n}` 形式的锚点定位
- `WorkbenchView` 用于新建任务与即时结果展示
- `ResultView` 用于打开已有结果并恢复页面状态

### 后端路径

后端保留纯 API 路由，建议统一收敛为：

- `/api/config`
- `/api/analyze`
- `/api/results/*`
- `/api/search/*`
- `/api/knowledge/*`
- `/api/custom-rules/*`

兼容期允许保留旧的 `/analyze`，待前端切换完成后统一收口到 `/api/analyze`。

## API 契约原则

### 总原则

- 后端返回“数据事实”
- 前端负责“页面导航”
- 文件资源 URL 由后端提供
- 页面 URL 不由后端拼接

### 需要调整的字段

#### 搜索结果

现状：

- 后端返回 `preview_url`

调整方向：

- 后端返回 `result_id`
- 后端返回 `matched_pages`
- 前端根据路由规则自行生成 `/results/:resultId#page-n`

兼容策略：

- 迁移期先同时保留 `preview_url` 与 `result_id/matched_pages`
- Vue 前端切换完成后再移除 `preview_url`

#### 识别提交结果

现状：

- `/analyze` 返回 `result_url`、`steps_url`

调整方向：

- 返回 `result_id`
- 返回用于轮询的 API 地址或直接约定固定 API 规则
- 前端不再依赖页面 URL 字段

兼容策略：

- 迁移期允许旧字段并存

#### 知识库图片字段

以下字段仍可保留为资源 URL：

- `image_url`
- `variant_image_urls`

原因：

- 它们本质是后端托管的文件资源，不属于页面导航语义

## 前端目录设计

建议新增目录结构如下：

```text
web/
  src/
    app/
      main.ts
      router.ts
      stores/
      styles/
    views/
      WorkbenchView.vue
      ResultView.vue
      KnowledgeView.vue
      SearchView.vue
    components/
      common/
      workbench/
      search/
      knowledge/
    composables/
    api/
    types/
    utils/
```

说明：

- `app/`：应用入口、路由、全局状态、全局样式
- `views/`：页面级视图
- `components/`：共享组件与业务组件
- `composables/`：可复用交互逻辑
- `api/`：按领域拆分的接口调用层
- `types/`：后端响应模型与前端视图模型
- `utils/`：纯函数工具

## 页面与组件拆分

### WorkbenchView

保留当前工作台的信息架构与功能流转，建议拆分：

- `WorkbenchHeader`
- `UploadPanel`
- `TaskStatusCard`
- `StepTimeline`
- `ResultTabs`
- `PreviewCanvas`
- `PreviewOverlay`
- `ComponentGroupList`
- `CombinationCardList`
- `TitleBlockPanel`
- `ControlSignalsPanel`
- `TableInfoPanel`

### ResultView

`ResultView` 与 `WorkbenchView` 共享大部分结果展示组件，差异在于：

- `WorkbenchView` 负责新任务上传与发起
- `ResultView` 负责按 `resultId` 恢复已有结果
- `ResultView` 负责处理锚点页码定位

### SearchView

建议拆分：

- `SearchToolbar`
- `SearchModeSwitch`
- `SearchFilters`
- `SearchHealthPanel`
- `DemoQueryPanel`
- `SearchResultList`
- `SearchResultCard`
- `SearchDebugPanel`

### KnowledgeView

建议拆分：

- `KnowledgeToolbar`
- `KnowledgeListPanel`
- `ComponentEditor`
- `RuleEditor`
- `RuleMemberEditor`
- `ImageUploader`
- `RuleTestPanel`

## Composables 设计

建议抽离以下可复用逻辑：

- `useAnalyzeTask`
- `useResultPolling`
- `useResultLoader`
- `useSearch`
- `useSearchHealth`
- `useKnowledgeCatalog`
- `useComponentEditor`
- `useRuleEditor`

目标：

- 将上传、轮询、结果恢复、知识库编辑、搜索请求等逻辑从视图中拆离
- 保持组件关注渲染与局部交互

## 样式迁移原则

- 保持现有视觉结构、层级和布局逻辑不变
- 优先复用已有样式变量、配色、按钮、面板、空态样式表达
- 先实现“样式等价”，不做视觉重设计
- 可将现有 `styles.css`、`search.css`、`knowledge.css` 中的稳定样式迁移为：
  - 全局基础样式
  - 页面级样式
  - 组件局部样式

## 后端改造边界

### 保持不变

- 识别 pipeline
- 搜索索引和检索逻辑
- 知识库存储与规则存储
- 结果文件目录与 `result.json / manifest / steps/*.json` 组织

### 调整范围

- 将 Web 服务层从“页面 + API”调整为“纯 API”
- 拆分当前集中式 `api.py`

建议按领域拆为：

- `analyze`
- `results`
- `search`
- `knowledge`
- `custom_rules`
- `config`

### 删除或废弃项

- 页面路由 `/`
- 页面路由 `/knowledge`
- 页面路由 `/search`
- `/static` 前端资源挂载
- 后端中任何面向前端页面的 URL 拼接逻辑

## 配置与部署

### 开发期

- 后端示例地址：`http://localhost:8892`
- 前端示例地址：`http://localhost:5173`
- 前端通过 `VITE_API_BASE_URL` 指向后端 API 服务
- 后端开启 CORS，允许前端开发地址访问

### 生产期

- 前端独立构建并独立部署
- 后端作为 API 服务独立部署
- 由环境变量和反向代理控制前后端联通

## 迁移阶段

### 阶段 1：前端基础壳

- 创建 `web/` 应用
- 建立 `Vite + Vue3 + TypeScript + Router + Pinia`
- 建立 API client、全局样式与基础布局

### 阶段 2：迁移 Search 与 Knowledge

优先迁移原因：

- API 边界清晰
- 页面职责相对集中
- 风险低于工作台和结果页

交付目标：

- 搜索页功能等价
- 知识库页功能等价

### 阶段 3：迁移 Workbench 与 Result

这是复杂度最高的阶段，涉及：

- 上传
- 轮询
- 结果恢复
- 预览叠加
- 页码锚点
- 多页签结果展示

交付目标：

- 新建任务流程等价
- 历史结果打开等价
- 搜索跳转到结果页等价

### 阶段 4：后端收口与清理

- 移除旧页面路由
- 移除静态资源挂载
- 移除旧页面 URL 拼接字段
- 清理旧静态前端文件

## 兼容策略

采用“先兼容、后收口”的方式：

- 第一阶段允许新旧字段并存
- 优先采用“加字段不减字段”
- 避免前后端必须同一天切换
- Vue 前端稳定后再移除旧页面路由与旧跳转字段

示例：

- 搜索结果同时返回 `preview_url` 与 `result_id/matched_pages`
- `/analyze` 同时返回旧字段与新字段

## 测试设计

### 后端测试

- 补充 API 契约测试
- 覆盖新旧字段兼容
- 覆盖 CORS 与关键响应结构
- 保留现有 pipeline、搜索、知识库测试，确保业务逻辑不回归

### 前端测试

- 组件测试：
  - 状态切换
  - 结果渲染
  - 表单校验
  - 列表过滤
- 视图级测试：
  - 检索提交与结果展示
  - 知识库编辑与规则校验
  - 结果页恢复与 `#page-n` 定位
- API client 测试：
  - 上传
  - 轮询
  - 错误处理
  - 重试逻辑

### 联调验收

前后端分开启动，验证以下闭环：

- 上传图纸并完成识别
- 打开历史结果
- 搜索结果跳转到结果页
- 知识库编辑、校验、试运行与图片上传

验收标准是“用户流程等价”，不是仅仅完成技术替换。

## 风险与控制

### 风险 1：Workbench / Result 迁移复杂度高

原因：

- 同时涉及上传、轮询、恢复、预览、锚点与多面板结果展示

控制策略：

- 排在搜索和知识库之后迁移
- 先抽通用结果展示组件，再合并到两个视图

### 风险 2：后端返回字段与前端导航职责混杂

控制策略：

- 明确后端只返回数据与文件资源
- 页面跳转全部由前端路由生成
- 通过类型定义和契约测试固化边界

### 风险 3：迁移期间需要同时兼容旧前端

控制策略：

- 采用兼容字段并存策略
- 用分阶段切换避免硬切换

## 成功标准

- 页面样式和视觉结构与现有实现基本一致
- 页面交互流程和字段展示一致
- 搜索、知识库、识别工作台、结果恢复、页码跳转行为一致
- 前端可独立构建、独立部署、独立启动
- 后端不再依赖静态 HTML/JS/CSS 提供页面
- 前后端可在本地分别启动并完成完整业务联调
