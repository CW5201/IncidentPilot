# 前端设计（Phase 0）

版本：v0.1（待确认）
技术：React 19 + TypeScript + Vite + Ant Design 5 + ECharts 5 + TanStack Query 5 + Zustand + React Router 7

---

## 1. 设计定位

专业的企业级 SRE / AIOps 控制台：

- 深色侧边导航 + 浅色内容区；
- 主色科技蓝 `#1677FF`；
- 信息密度适中，优先可读性与可操作性；
- 克制使用色彩：颜色只用于状态、严重度、风险与数据系列；
- 不使用大面积渐变、霓虹色、装饰性卡片、无意义插画；
- 所有数据来自真实 API，禁止假数据与无后端逻辑的按钮。

### 1.1 Design Tokens

| Token | 值 |
| --- | --- |
| `--color-primary` | `#1677FF` |
| `--color-bg-layout` | `#F5F7FA` |
| `--color-bg-container` | `#FFFFFF` |
| `--color-sider` | `#0F172A` |
| `--color-sider-text` | `#CBD5E1` |
| `--color-success` | `#16A34A` |
| `--color-warning` | `#D97706` |
| `--color-error` | `#DC2626` |
| `--color-text` | `#0F172A` |
| `--color-text-secondary` | `#64748B` |
| `--radius` | `6px` |
| `--space-unit` | `8px` |
| 字体 | `Inter, "PingFang SC", "Microsoft YaHei", sans-serif` |
| 数字 | `JetBrains Mono`（指标、ID、耗时） |

严重度/状态色：

| 状态 | 颜色 |
| --- | --- |
| SEV1 / CRITICAL | `#DC2626` |
| SEV2 / WARNING | `#D97706` |
| SEV3 / INFO | `#2563EB` |
| RESOLVED / RECOVERED | `#16A34A` |
| FAILED / NOT_RECOVERED | `#DC2626` |
| INSUFFICIENT_DATA | `#64748B` |

---

## 2. 布局与路由

```text
┌─────────────────────────────────────────────────────────────┐
│ 深色 Sider（240px，可折叠） │ Header（面包屑、环境标识、用户） │
│ ├ Dashboard                 ├───────────────────────────────┤
│ ├ 事件中心                   │                               │
│ ├ 服务监控                   │        内容区（浅色）          │
│ ├ 日志 / 调用链              │                               │
│ ├ 知识库                     │                               │
│ ├ MCP 工具                   │                               │
│ ├ 审批中心（角标）            │                               │
│ ├ 修复历史                   │                               │
│ ├ 评测中心                   │                               │
│ └ 系统设置                   │                               │
└─────────────────────────────────────────────────────────────┘
```

| 路由 | 页面 | 权限 | 关键 API |
| --- | --- | --- | --- |
| `/` | Dashboard | 登录 | `/dashboard/overview` |
| `/incidents` | Incident Center | 登录 | `/incidents` |
| `/incidents/:id` | Incident Detail | 登录 | `/incidents/{id}` 等 |
| `/incidents/:id/investigation` | Agent Investigation | 登录 | `/agent-runs/{id}` + SSE |
| `/services` | Service Monitoring | 登录 | `/services` |
| `/logs` | Log Explorer | 登录 | `/logs` |
| `/traces` | Trace Explorer | 登录 | `/traces` |
| `/knowledge` | Knowledge Base | 登录 | `/knowledge/*` |
| `/mcp` | MCP Tools | 登录 | `/mcp/*` |
| `/approvals` | Approval Center | SRE/ADMIN | `/approvals` |
| `/remediations` | Remediation History | 登录 | `/executions` |
| `/evaluations` | Evaluation Center | 登录 | `/evaluations/*` |
| `/settings` | System Settings | ADMIN | `/settings/*`、`/users`、`/audit-logs` |
| `/demo` | 演示控制（设置子页） | ADMIN | `/demo/*` |

路由守卫：未登录跳转登录页；无权限显示 403 页面，不隐藏后仍可调用。

---

## 3. 全局组件

| 组件 | 职责 |
| --- | --- |
| `AppLayout` | Sider + Header + 内容区 + 全局通知 |
| `SeverityTag` | 严重度/风险/状态统一颜色与文案 |
| `IncidentStatusBadge` | 状态机可视化（含当前节点） |
| `MetricChart` | ECharts 折线/面积图，支持基线对比、阈值线、时间窗刷选 |
| `EvidenceCard` | 证据摘要、来源图标、时间、可靠性、展开原文、引用复制 |
| `CitationLink` | `ev_...` / `kb://...` 跳转到证据或文档片段 |
| `AgentStepTimeline` | 节点时间线 + 状态 + 耗时 + 重试 |
| `ToolCallTable` | 工具、参数（脱敏/折叠）、耗时、状态、证据数 |
| `ApprovalDrawer` | 审批详情、风险、影响、回滚、确认 |
| `JsonViewer` | 折叠 JSON（Schema、原始 payload） |
| `AsyncBoundary` | loading / empty / error / forbidden 统一处理 |
| `TraceWaterfall` | Span 瀑布图（ECharts custom series） |
| `ServiceDependencyGraph` | 服务依赖图（ECharts graph） |
| `RiskBadge` | LOW/MEDIUM/HIGH |
| `Countdown` | 审批过期倒计时 |

---

## 4. Dashboard

区块：

1. **KPI 卡片**：活跃事件数、待审批数、今日已恢复数、Agent 平均调查时长；每张卡片显示环比与数据时间。
2. **服务健康矩阵**：Order / Payment / Inventory，展示 5xx、P95、CPU、实例数；点击进入 Service Monitoring。
3. **活跃事件列表**：严重度、服务、状态、持续时间、当前 Agent 节点。
4. **Agent 执行统计**：近 24h Run 数、成功率、平均工具调用数、Token 成本（来自真实 Run 数据）。
5. **最近活动**：告警、审批、执行、验证时间线。

交互：时间范围切换（1h/6h/24h/7d）；自动刷新 30s（可关闭）；空状态显示"当前无活跃事件"。

---

## 5. Incident Center

- 顶部筛选：状态（多选）、严重度、服务、时间范围、关键词；
- 表格列：编号、标题、服务、严重度、状态、开始时间、持续时长、根因、置信度、负责人；
- 行点击进入 Detail；
- 状态标签使用状态机色；
- 支持"手动创建事件"（SRE）与"触发调查"；
- 分页 + 排序 + URL 同步（可分享链接）；
- 空/错误/加载状态完整。

---

## 6. Incident Detail（核心页面）

### 6.1 页头

- 事件编号、标题、严重度、状态、服务、开始时间、持续时长；
- 右侧操作：触发/重跑调查（SRE）、关闭事件（SRE）、查看报告、复制链接；
- 若 `AWAITING_APPROVAL`，显示醒目审批入口与倒计时；
- 若 Run 进行中，显示当前节点与实时进度条。

### 6.2 标签页

| Tab | 内容 |
| --- | --- |
| 概览 | 告警摘要、影响服务、当前根因（置信度）、修复状态、验证结论、关键指标迷你图 |
| 证据 | 按来源分组的 EvidenceCard；筛选 METRIC/LOG/TRACE/CHANGE/KNOWLEDGE；证据关联图（时间轴） |
| Agent 调查 | AgentStepTimeline + ToolCallTable + 实时 SSE + 根因候选 + 不确定性 |
| 修复方案 | Plan 版本、动作列表、风险、前置条件、预期效果、回滚、验证计划；申请/重新审批 |
| 审批与执行 | 审批记录、执行结果、审计链接 |
| 恢复验证 | 前后指标对比图、检查项表格、判定结论、数据点数量 |
| 时间线 | 全量事件（告警、Agent、审批、执行、验证、人工操作） |

### 6.3 实时执行视图

```text
┌ Agent 调查 ───────────────────────────────────────────────┐
│ 状态：RUNNING  节点：metrics_investigator  第 1 轮  02:14  │
│ 预算：工具 8/30 · Token 21k/100k · 时限 12:00             │
│ ┌ 节点时间线 ──────────────────────────────────────────┐ │
│ │ ✓ alert_analyzer        1.2s                         │ │
│ │ ✓ planner               2.8s                         │ │
│ │ ◐ metrics_investigator  进行中（2 个工具）            │ │
│ │ ○ log_investigator      等待                          │ │
│ │ ...                                                   │ │
│ └───────────────────────────────────────────────────────┘ │
│ ┌ 工具调用 ────────────────────────────────────────────┐ │
│ │ prom_service_snapshot  order-service  38ms  OK  2 证据│ │
│ │ prom_query_range       http_error_rate 61ms OK  1 证据│ │
│ └───────────────────────────────────────────────────────┘ │
│ ┌ 证据流（实时） ──────────────────────────────────────┐ │
│ │ [METRIC] 5xx 18.4% vs 基线 0.3%        08:12:00      │ │
│ │ [LOG]    QueuePool limit reached ...   08:11:42      │ │
│ └───────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────┘
```

SSE 事件驱动更新：

- `node.started/completed` → 更新时间线；
- `tool.started/completed` → 插入工具表；
- `evidence.added` → 证据流 + 证据 Tab 角标；
- `plan.ready` → 修复方案 Tab 角标 + 通知；
- `approval.required` → 打开审批抽屉/通知；
- `verification.completed` → 刷新验证 Tab；
- `run.completed/failed` → 停止加载态，刷新 Incident 详情。

### 6.4 证据面板

- 证据卡片：来源、标题、服务、时间窗、可靠性、摘要、展开原文；
- 引用复制：`ev_...`；
- 关联：点击 Trace ID 打开 Trace Explorer；点击文档引用打开知识库片段；
- 证据覆盖度条：必选维度覆盖情况；
- 无效引用高亮（若后端标记）。

### 6.5 根因与方案

- 根因：主因标签、置信度进度条、证据引用列表、备选原因、不确定性、下一步建议；
- 方案：动作卡片（类型、目标、参数、风险、是否需要审批）、预期效果、验证计划、回滚；
- 审批按钮仅在权限与状态允许时出现；点击打开 Drawer，展示方案快照哈希与影响范围。

### 6.6 验证面板

- 前后对比图：5xx、P95、CPU、内存、错误日志量；
- 检查表：检查项、基线、修复后、阈值、结果；
- 判定横幅：RECOVERED / PARTIALLY / NOT / INSUFFICIENT_DATA；
- 数据点不足时明确提示，不显示绿色成功。

---

## 7. Agent Investigation 页面

独立路由复用 Incident Detail 的 Agent 组件，适合演示时全屏展示：

- 左侧节点图（LangGraph 结构 + 当前节点高亮）；
- 右侧实时日志/工具/证据；
- 底部预算与耗时；
- 支持暂停滚动（用户查看历史）与"回到最新"；
- 断线重连提示与"从最近事件恢复"。

---

## 8. Service Monitoring

- 服务卡片：健康、实例数、QPS、5xx、P95、CPU、内存；
- 选中服务：多指标图表（时间范围联动）、告警列表、最近事件、依赖图；
- 故障注入状态标识（仅 DEMO，ADMIN 可见）；
- 图表支持基线/阈值线、图例切换、导出 PNG；
- 数据来自 `/services/{id}/metrics`，与 MCP 共享查询构建器。

---

## 9. Log Explorer

- 查询表单：服务、级别、关键词、Trace ID、时间范围；
- 结果表格：时间、级别、服务、消息摘要、Trace ID；
- 点击行展开上下文（前后 N 行）；
- 点击 Trace ID 跳转 Trace Explorer；
- 支持复制查询链接；
- 空结果提示调整时间窗/关键词，不伪造数据；
- 大结果集分页/截断提示。

---

## 10. Trace Explorer

- 搜索：服务、状态、最小耗时、时间范围；
- 结果列表：Trace ID、入口、耗时、Span 数、错误标记；
- 详情：Span 瀑布图、关键路径高亮、错误 Span 红色、Span 属性抽屉；
- 关联日志：按 Trace ID 查询 Loki；
- 服务依赖图入口；
- 支持从 Incident 证据深链进入。

---

## 11. Knowledge Base

- 文档表格：标题、类型、服务范围、版本、状态、Chunk 数、更新时间；
- 上传：拖拽/选择文件，显示解析与索引进度（轮询或 SSE）；
- 文档详情：版本历史、元数据、Chunk 预览、删除/重建索引；
- 检索测试：查询 + 服务过滤 + TopK；结果展示 BM25/向量/RRF/Rerank 各阶段数量与耗时，最终结果带引用；
- 索引状态：模型名、维度、代数、文档/Chunk 数；
- 错误：解析失败显示原因与重试入口。

---

## 12. MCP Tools

- Server 卡片：名称、状态、工具数、最近健康检查；
- 工具表格：名称、权限、超时、描述、Schema 查看；
- 工具详情 Drawer：输入 Schema（JsonViewer）、输出结构、示例参数；
- 测试调用（ADMIN，仅 READ）：填写 JSON 参数 → 展示结果/错误/耗时；
- 调用审计：最近调用（Run、工具、状态、耗时）；
- 权限标识：READ 绿色、WRITE_LOW 橙色、WRITE_HIGH 红色。

---

## 13. Approval Center

- 待审批列表：风险等级、动作、目标、申请人、剩余时间、事件链接；
- 详情 Drawer：方案摘要、动作参数、预期影响、回滚、证据引用、方案哈希；
- 审批操作：通过/拒绝 + 必填意见；高风险二次确认（输入服务名）；
- 倒计时与过期状态；
- 审批后实时刷新列表与 Incident 状态；
- 无权限用户只读，不显示操作按钮。

---

## 14. Remediation History

- 执行列表：时间、事件、动作、目标、风险、状态、耗时、验证结论；
- 详情：执行输出、审计链、审批人、回滚信息、验证对比；
- 过滤：状态、动作类型、服务、时间；
- 失败执行突出显示错误与重试次数。

---

## 15. Evaluation Center

- 用例列表：名称、故障类型、期望根因、难度、启用状态；
- 运行配置：数据集版本、模型配置、重复次数；
- 运行历史：状态、指标、开始时间、耗时；
- 结果详情：逐用例预测 vs 期望、Top3、证据覆盖、工具选择/参数、完成率、修复成功、False Recovery；
- 指标卡：Top-1、Top-3、Evidence Accuracy、Tool Selection、Tool Argument、Completion、Remediation Success、False Recovery；
- 明确展示样本数 N、执行时间、模型，禁止伪造；
- 未运行状态显示"暂无数据"，不显示占位指标。

---

## 16. System Settings

标签页：

1. **模型配置**：Provider、Base URL、模型名、超时、温度、Key（脱敏）、测试连接、设为默认；
2. **用户管理**：列表、角色、启用/禁用、重置密码；
3. **MCP**：Server 地址、Token 状态（不显示明文）、健康检查；
4. **功能开关**：`AUTO_APPROVE_LOW_RISK`、`REMEDIATION_ENABLED`、`DEMO_MODE`（只读展示 + ADMIN 修改需确认）；
5. **演示控制**：7 个场景卡片（启动/停止/状态、持续时间、目标服务、预期指标），仅 DEMO_MODE；
6. **系统信息**：版本、构建时间、数据库迁移版本、队列积压、磁盘/内存；
7. **审计日志**：筛选与详情。

---

## 17. 数据层与 SSE Hook

### 17.1 数据获取

- TanStack Query 管理服务端状态：缓存、重试、失效；
- Query key 约定：`['incidents', filters]`、`['incident', id]`、`['run', id]`；
- SSE 事件触发 `invalidateQueries`（节点完成、证据新增、审批、验证）；
- 轮询仅用于无 SSE 的进度（知识库索引、评测运行）。

### 17.2 SSE Hook（设计）

```ts
function useRunStream(runId: string, enabled: boolean) {
  const [lastId, setLastId] = useState<number | null>(null);
  const [status, setStatus] = useState<'connecting'|'open'|'closed'>('closed');

  useEffect(() => {
    if (!enabled) return;
    const ctrl = new AbortController();
    let retry = 0;

    async function connect() {
      const res = await fetch(`/api/v1/agent-runs/${runId}/events`, {
        headers: {
          Accept: 'text/event-stream',
          Authorization: `Bearer ${getAccessToken()}`,
          ...(lastId ? { 'Last-Event-ID': String(lastId) } : {}),
        },
        signal: ctrl.signal,
      });
      // 解析 ReadableStream，按 \n\n 分帧
      // id: 更新 lastId；event/data: 分发到 handler
      // 断线：指数退避 1s/2s/4s/8s，最多 5 次，之后提示手动重连
    }
    connect();
    return () => ctrl.abort();
  }, [runId, enabled, lastId]);

  return { status };
}
```

要求：

- 不使用 EventSource（无法设置 Authorization）；
- 断线后从 `Last-Event-ID` 回放，不丢事件；
- 页面隐藏时保持连接或降频（可配置）；
- 终态事件后停止重连。

### 17.3 状态管理

- Zustand：当前用户、侧边栏折叠、主题、全局通知、演示模式标识；
- 不在 Zustand 存服务端实体，避免双份状态。

---

## 18. 状态与可访问性

每个数据区块必须实现：

| 状态 | 表现 |
| --- | --- |
| Loading | Skeleton，不用全屏 Spin 遮挡 |
| Empty | 说明 + 下一步操作（如"调整时间范围"） |
| Error | 错误码 + request_id + 重试按钮 |
| Forbidden | 403 说明 + 返回 |
| Partial | 部分图表失败不影响其他区块，单独提示 |

可访问性：

- 颜色不作为唯一信息载体（状态同时有文字/图标）；
- 键盘可操作抽屉/表格；
- 对比度符合 WCAG AA；
- 图表提供表格视图/文本摘要。

---

## 19. 禁止事项

1. 不写死数据、不伪造指标、不伪造评测结果；
2. 不提供没有后端实现的按钮；
3. 不在前端拼接 PromQL/LogQL；
4. 不把 Token/Key 写入 localStorage 明文（access token 存内存，refresh 用 HttpOnly Cookie）；
5. 不在前端做权限判断后假设安全（后端必须再次校验）；
6. 不用大面积渐变/霓虹色/装饰插画；
7. 不用"AI 魔法"式动效掩盖加载与错误。
