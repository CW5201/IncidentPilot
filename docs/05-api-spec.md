# API 设计（Phase 0）

版本：v0.1（待确认）
风格：REST + JSON + SSE
前缀：`/api/v1`
文档：FastAPI 自动生成 `/docs`、`/openapi.json`（内部接口不暴露）

---

## 1. 通用约定

### 1.1 认证

- 访问令牌：`Authorization: Bearer <access_token>`（JWT，15 分钟）；
- 刷新令牌：HttpOnly + Secure + SameSite=Lax Cookie（7 天，旋转 + 撤销）；
- SSE：前端使用 `fetch` + `ReadableStream`，可携带 Authorization 头（不使用 EventSource）；
- 服务间：`X-Internal-Token`（后端内部 API）、`X-Webhook-Token`（Alertmanager）。

### 1.2 响应格式

成功：

```json
{"data": {}, "meta": {"request_id": "req_...", "page": 1, "page_size": 20, "total": 100}}
```

失败：

```json
{
  "error": {
    "code": "INCIDENT_NOT_FOUND",
    "message": "Incident not found",
    "details": {},
    "request_id": "req_..."
  }
}
```

错误码（HTTP）：

| HTTP | code 示例 | 场景 |
| --- | --- | --- |
| 400 | `INVALID_ARGUMENT` | 参数非法 |
| 401 | `UNAUTHENTICATED` | 未登录/Token 过期 |
| 403 | `FORBIDDEN` | 角色不足/审批人冲突 |
| 404 | `*_NOT_FOUND` | 资源不存在 |
| 409 | `CONFLICT` / `ALREADY_DECIDED` | 重复操作/状态冲突 |
| 422 | `VALIDATION_ERROR` | Pydantic 校验失败 |
| 429 | `RATE_LIMITED` | 限流 |
| 502/503 | `UPSTREAM_ERROR` | MCP/LLM/监控不可用 |
| 500 | `INTERNAL_ERROR` | 未预期异常（隐藏细节，记录 request_id） |

### 1.3 分页与过滤

- `?page=1&page_size=20`（`page_size` 最大 100）；
- 时间过滤：`start` / `end`（ISO8601 UTC）；
- 排序：`sort=-started_at`（前缀 `-` 表示降序）；
- 列表默认按 `started_at DESC`。

### 1.4 幂等

- 写接口支持 `Idempotency-Key` 头（UUID）；
- 服务端在 Redis 保存 24 小时结果映射；
- 重复请求返回首次结果（200/201）并标注 `meta.idempotent_replay=true`；
- 审批决策不可重复：第二次返回 409 `ALREADY_DECIDED`。

### 1.5 限流

| 接口 | 限制 |
| --- | --- |
| `POST /auth/login` | 5 次/分钟/IP |
| `POST /webhooks/alertmanager` | 50 次/秒（令牌桶，允许突发 100） |
| 普通读接口 | 120 次/分钟/用户 |
| `POST /incidents/{id}/investigate` | 3 次/分钟/用户 |
| `POST /evaluations/runs` | 1 次/5 分钟/用户 |

---

## 2. 认证与用户

| 方法 | 路径 | 角色 | 说明 |
| --- | --- | --- | --- |
| POST | `/auth/login` | 公开 | 邮箱 + 密码，返回 access token，设置 refresh cookie |
| POST | `/auth/refresh` | 公开（cookie） | 旋转刷新令牌 |
| POST | `/auth/logout` | 登录 | 撤销 refresh token |
| GET | `/auth/me` | 登录 | 当前用户与权限 |
| POST | `/auth/change-password` | 登录 | 修改密码，撤销其他会话 |
| GET | `/users` | ADMIN | 用户列表 |
| POST | `/users` | ADMIN | 创建用户 |
| PATCH | `/users/{id}` | ADMIN | 角色/启用状态 |

---

## 3. 告警与事件

| 方法 | 路径 | 角色 | 说明 |
| --- | --- | --- | --- |
| POST | `/webhooks/alertmanager` | SERVICE | Alertmanager Webhook，幂等 |
| GET | `/alerts` | 登录 | 列表：`status`、`severity`、`service`、时间 |
| GET | `/alerts/{id}` | 登录 | 详情（含 raw payload） |
| GET | `/incidents` | 登录 | 列表：`status`、`severity`、`service`、时间、关键词 |
| POST | `/incidents` | SRE | 手动创建事件 |
| GET | `/incidents/{id}` | 登录 | 详情（含当前 Run/Plan/Verification 摘要） |
| GET | `/incidents/{id}/timeline` | 登录 | 时间线（分页） |
| GET | `/incidents/{id}/evidence` | 登录 | 证据列表（按来源过滤） |
| GET | `/incidents/{id}/report` | 登录 | 结构化报告 + Markdown 渲染 |
| POST | `/incidents/{id}/investigate` | SRE | 触发/重跑调查（幂等键） |
| POST | `/incidents/{id}/close` | SRE | 手动关闭（需理由，写审计） |
| PATCH | `/incidents/{id}/severity` | SRE | 调整严重度（写审计） |

Webhook 请求示例：

```http
POST /api/v1/webhooks/alertmanager
X-Webhook-Token: <shared-secret>
Content-Type: application/json
```

```json
{
  "version": "4",
  "status": "firing",
  "receiver": "incidentpilot",
  "groupKey": "{}/{service=\"order-service\"}:{alertname=\"HighErrorRate\"}",
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "HighErrorRate",
        "severity": "critical",
        "service": "order-service",
        "namespace": "demo",
        "instance": "order-service:8001"
      },
      "annotations": {
        "summary": "order-service 5xx rate > 5%",
        "description": "5xx rate is 18.4% for 5 minutes"
      },
      "startsAt": "2026-11-10T08:07:00Z",
      "endsAt": "0001-01-01T00:00:00Z",
      "fingerprint": "a1b2c3d4"
    }
  ]
}
```

响应：`202 Accepted`，`{"data": {"incident_id": "...", "created": true, "alert_ids": ["..."]}}`。

---

## 4. Agent 执行

| 方法 | 路径 | 角色 | 说明 |
| --- | --- | --- | --- |
| GET | `/agent-runs/{id}` | 登录 | Run 详情（状态、预算、耗时、Token、成本） |
| GET | `/agent-runs/{id}/steps` | 登录 | 节点步骤（分页/增量 `after_sequence`） |
| GET | `/agent-runs/{id}/tools` | 登录 | 工具调用记录（参数、结果摘要、耗时） |
| GET | `/agent-runs/{id}/events` | 登录 | **SSE 实时事件** |
| POST | `/agent-runs/{id}/cancel` | SRE | 请求取消 |
| POST | `/agent-runs/{id}/resume` | ADMIN | 手动恢复（故障修复后） |

Run 详情示例：

```json
{
  "data": {
    "id": "run_01J...",
    "incident_id": "inc_01J...",
    "status": "WAITING_APPROVAL",
    "graph_version": "v1",
    "model": "nvidia/nemotron-3.5-super-vl-120b-a12b",
    "iteration": 1,
    "followups": 0,
    "started_at": "2026-11-10T08:08:00Z",
    "duration_ms": 74210,
    "prompt_tokens": 18240,
    "completion_tokens": 3120,
    "reasoning_tokens": 2480,
    "cost_usd": 0.021,
    "budget": {"tool_calls": 12, "max_tool_calls": 30, "tokens": 21360, "max_tokens": 100000},
    "current_node": "approval_gate",
    "error": null
  }
}
```

---

## 5. SSE 协议

### 5.1 连接

```http
GET /api/v1/agent-runs/{run_id}/events
Authorization: Bearer <token>
Accept: text/event-stream
Last-Event-ID: 42
```

### 5.2 事件格式

```text
id: 43
event: tool.completed
data: {"run_id":"run_01J...","sequence":43,"node":"metrics_investigator","server":"prometheus","tool":"prom_service_snapshot","status":"OK","latency_ms":38,"evidence_ids":["ev_01J..."],"ts":"2026-11-10T08:09:12Z"}

```

### 5.3 事件类型

| event | 触发 | 关键字段 |
| --- | --- | --- |
| `run.started` | 图启动 | run_id, incident_id |
| `run.status` | 状态变化 | status, current_node |
| `node.started` | 节点开始 | node, iteration |
| `node.completed` | 节点结束 | node, duration_ms, summary |
| `node.retrying` | 节点重试 | node, attempt, error_code |
| `tool.started` | 工具调用开始 | server, tool, arguments_hash |
| `tool.completed` | 工具调用结束 | status, latency_ms, evidence_ids |
| `evidence.added` | 证据入库 | evidence_id, source_type, title |
| `hypothesis.updated` | 根因候选更新 | label, confidence |
| `plan.ready` | 方案生成 | plan_id, risk_level, actions |
| `approval.required` | 等待审批 | approval_id, plan_hash, expires_at |
| `approval.decided` | 审批完成 | decision, approver |
| `execution.started` | 执行开始 | action_id, action_type |
| `execution.completed` | 执行结束 | status, duration_ms |
| `verification.completed` | 验证完成 | verdict, checks |
| `run.completed` | 正常结束 | status, duration_ms |
| `run.failed` | 失败 | error_code, message |
| `heartbeat` | 15s 心跳 | ts |

### 5.4 回放与断线

1. 事件先写 `sse_events`（与步骤/证据同事务或紧随其后），再 Redis Publish；
2. 客户端重连带 `Last-Event-ID`；
3. 服务端先查库回放 `sequence > last_event_id`，再订阅 Redis；
4. 以 `sequence` 去重，保证至少一次投递下的顺序；
5. Run 已结束时回放完历史事件后发送 `run.completed` 并关闭；
6. 心跳注释 `: ping` 每 15s，防止代理超时。

Nginx：

```nginx
location /api/ {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600s;
    add_header X-Accel-Buffering no;
}
```

---

## 6. 修复与审批

| 方法 | 路径 | 角色 | 说明 |
| --- | --- | --- | --- |
| GET | `/incidents/{id}/plans` | 登录 | 方案版本列表 |
| GET | `/plans/{id}` | 登录 | 方案详情（动作、风险、验证计划） |
| POST | `/plans/{id}/request-approval` | SRE | 重新发起审批（仅 PENDING/REJECTED） |
| GET | `/approvals` | 登录 | 待审批/历史，`decision`、`risk_level` |
| GET | `/approvals/{id}` | 登录 | 审批详情 + 方案快照 |
| POST | `/approvals/{id}/decision` | SRE/ADMIN | `APPROVE` / `REJECT` |
| GET | `/executions` | 登录 | 执行历史 |
| GET | `/executions/{id}` | 登录 | 执行详情 + 输出 + 审计 |
| POST | `/executions/{id}/verify` | SRE | 手动触发复验 |
| GET | `/incidents/{id}/verifications` | 登录 | 验证历史 |
| GET | `/verifications/{id}` | 登录 | 验证详情（前后指标、判定依据） |

审批决策：

```json
{
  "decision": "APPROVE",
  "comment": "确认影响范围仅 demo 命名空间，同意重启",
  "plan_hash": "sha256:..."
}
```

校验：

- `plan_hash` 必须与当前方案一致（防止审批后被篡改）；
- 审批人角色满足风险等级；
- 审批未过期；
- 审批人 ≠ 申请人；
- 同一动作只能有一个有效决策。

---

## 7. 知识库

| 方法 | 路径 | 角色 | 说明 |
| --- | --- | --- | --- |
| POST | `/knowledge/documents` | SRE | 上传（multipart：file、title、service_scope、type） |
| GET | `/knowledge/documents` | 登录 | 列表（状态、版本、服务） |
| GET | `/knowledge/documents/{id}` | 登录 | 详情 + 版本历史 |
| POST | `/knowledge/documents/{id}/versions` | SRE | 上传新版本 |
| DELETE | `/knowledge/documents/{id}` | ADMIN | 归档（软删除）+ 删除向量 |
| POST | `/knowledge/documents/{id}/reindex` | SRE | 重建索引 |
| GET | `/knowledge/documents/{id}/chunks` | 登录 | 分页查看 Chunk |
| POST | `/knowledge/search` | 登录 | 检索测试（返回各阶段结果） |
| GET | `/knowledge/search/{log_id}` | 登录 | 检索详情 |
| GET | `/knowledge/index-status` | 登录 | 索引代数、文档数、Chunk 数、模型 |

检索请求：

```json
{
  "query": "数据库连接池耗尽 排查",
  "service": "order-service",
  "top_k": 5,
  "filters": {"doc_type": "SOP"},
  "debug": true
}
```

响应：

```json
{
  "data": {
    "results": [
      {
        "chunk_id": "chk_01J...",
        "document_id": "doc_01J...",
        "title": "订单服务数据库连接池 SOP",
        "version": 2,
        "section": "3.2 连接池耗尽",
        "page": 7,
        "content": "...",
        "score": 0.823,
        "citation": "kb://doc_01J.../v2#chunk-18"
      }
    ],
    "stages": {
      "bm25": {"count": 20, "latency_ms": 8},
      "vector": {"count": 20, "latency_ms": 21},
      "rrf": {"count": 20, "latency_ms": 1},
      "rerank": {"count": 5, "latency_ms": 180}
    }
  }
}
```

---

## 8. 监控与日志查询

| 方法 | 路径 | 角色 | 说明 |
| --- | --- | --- | --- |
| GET | `/services` | 登录 | 服务列表 + 当前健康 |
| GET | `/services/{id}` | 登录 | 服务详情（SLO、依赖、最近事件） |
| GET | `/services/{id}/metrics` | 登录 | 指标序列（逻辑指标名） |
| GET | `/services/{id}/health` | 登录 | 主动健康检查 |
| GET | `/logs` | 登录 | 日志查询（service/level/q/trace_id/时间） |
| GET | `/traces` | 登录 | Trace 搜索 |
| GET | `/traces/{trace_id}` | 登录 | Trace 详情（Span 树、关键路径） |
| GET | `/traces/dependencies` | 登录 | 服务依赖图 |
| GET | `/dashboard/overview` | 登录 | 概览：事件数、服务健康、Agent 统计、最近活动 |

这些接口与 MCP 工具共享查询构建器，避免两套逻辑；前端只读，不提供任意 PromQL。

---

## 9. MCP 管理

| 方法 | 路径 | 角色 | 说明 |
| --- | --- | --- | --- |
| GET | `/mcp/servers` | 登录 | Server 列表 + 健康 |
| GET | `/mcp/tools` | 登录 | 工具目录（权限、超时、Schema） |
| POST | `/mcp/tools/{id}/test` | ADMIN | 测试调用（仅 READ 工具） |
| GET | `/mcp/invocations` | 登录 | 调用审计（run/tool/status/时间） |

---

## 10. 评测中心

| 方法 | 路径 | 角色 | 说明 |
| --- | --- | --- | --- |
| GET | `/evaluations/cases` | 登录 | 评测用例 |
| POST | `/evaluations/cases` | ADMIN | 新建用例 |
| POST | `/evaluations/runs` | ADMIN | 启动评测（后台执行） |
| GET | `/evaluations/runs` | 登录 | 历史运行 |
| GET | `/evaluations/runs/{id}` | 登录 | 运行详情 + 指标 |
| GET | `/evaluations/runs/{id}/results` | 登录 | 逐用例结果 |
| POST | `/evaluations/runs/{id}/cancel` | ADMIN | 取消 |

---

## 11. 设置与审计

| 方法 | 路径 | 角色 | 说明 |
| --- | --- | --- | --- |
| GET | `/settings/models` | ADMIN | 模型配置（Key 脱敏） |
| POST | `/settings/models` | ADMIN | 新增配置（Key 加密存储） |
| PATCH | `/settings/models/{id}` | ADMIN | 修改 |
| POST | `/settings/models/{id}/test` | ADMIN | 连通性测试 |
| GET | `/settings/system` | ADMIN | 版本、功能开关、资源状态 |
| GET | `/audit-logs` | ADMIN | 审计查询（actor/resource/时间） |

---

## 12. 演示控制（仅 DEMO_MODE）

| 方法 | 路径 | 角色 | 说明 |
| --- | --- | --- | --- |
| GET | `/demo/scenarios` | ADMIN | 可用故障场景 + 当前状态 |
| POST | `/demo/scenarios/{name}/start` | ADMIN | 注入故障（代理到 chaos-controller） |
| POST | `/demo/scenarios/{name}/stop` | ADMIN | 停止故障 |
| GET | `/demo/state` | ADMIN | 当前注入状态、目标服务 |

安全：

- 仅当 `DEMO_MODE=true` 时注册路由；
- 需要 ADMIN；
- 后端代理时附加 `X-Chaos-Token`，chaos-controller 不暴露公网；
- 写审计 `demo.chaos.started/stopped`；
- Agent 工具目录不包含该接口。

---

## 13. 权限矩阵

| 能力 | VIEWER | SRE | ADMIN |
| --- | --- | --- | --- |
| 查看 Dashboard/Incident/证据/报告 | ✓ | ✓ | ✓ |
| 触发调查 | | ✓ | ✓ |
| 审批 LOW/MEDIUM | | ✓ | ✓ |
| 审批 HIGH | | | ✓ |
| 手动关闭事件 | | ✓ | ✓ |
| 上传/重建知识库 | | ✓ | ✓ |
| 删除文档 | | | ✓ |
| 管理模型/MCP/用户 | | | ✓ |
| 触发演示故障 | | | ✓ |
| 执行评测 | | | ✓ |
| 查看审计 | | | ✓ |

---

## 14. 内部接口（不对外）

| 方法 | 路径 | 认证 | 说明 |
| --- | --- | --- | --- |
| POST | `/internal/rag/search` | `X-Internal-Token` | Knowledge Base MCP 调用 |
| POST | `/internal/rag/documents/{id}/index` | `X-Internal-Token` | 索引回调 |
| POST | `/internal/verifications/{id}/recheck` | `X-Internal-Token` | 调度器复验 |
| GET | `/internal/health` | 无 | 容器健康检查 |
