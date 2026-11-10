# IncidentPilot 实施总纲

> 最后更新：2026-11-10  
> 当前阶段：Phase 2（演示微服务 + 可观测性 + 故障注入）  
> 仓库：https://github.com/CW5201/IncidentPilot

## 1. 项目目标

打通一条可复现、可审计的 AI SRE 闭环：

```text
告警接入 → 事件归一化 → 故障关联 → Agent 调查 → 多源证据分析
→ 根因判断 → 修复方案 → 人工审批 → 安全执行 → 恢复验证 → 故障报告
```

核心原则：

- AI 负责分析与决策建议；
- 确定性程序负责权限校验与执行；
- 高风险操作必须人工审批；
- 所有调查、审批、执行、验证动作可审计、可回放。

## 2. 阶段总览

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| Phase 0 | PRD、架构、数据模型、Agent 工作流、MCP、API、前端、基础设施、安全测试、路线图 | 已完成 |
| Phase 1 | 后端基础、认证、告警接入、Incident、Outbox、RabbitMQ、Docker Compose core、测试 | 已完成并提交 |
| Phase 2 | Order/Payment/Inventory 演示服务、Prometheus/Grafana/Loki/Tempo、Alertmanager、chaos-controller、7 个故障场景 | 进行中 |
| Phase 3 | LangGraph Agent 执行引擎、MCP 工具、SSE、Checkpoint | 未开始 |
| Phase 4 | RAG、BGE-M3、Milvus、混合检索、多源根因 | 未开始 |
| Phase 5 | 审批与安全修复、恢复验证、报告 | 未开始 |
| Phase 6 | 前端、评测中心、演示与文档收尾 | 未开始 |

详细任务见 `docs/09-roadmap-risks.md`。

## 3. Phase 2 已完成

### 3.1 代码

- `demo-services/`
  - FastAPI 共享镜像，通过 `SERVICE_NAME` 启动 order / payment / inventory；
  - SQLAlchemy async + PostgreSQL `demo` schema；
  - Redis（经 toxiproxy）；
  - Prometheus 指标：HTTP、SQLAlchemy pool、`redis_up`、`chaos_active`；
  - OTel FastAPI / HTTPX / SQLAlchemy / Redis 自动埋点；
  - JSON 结构化日志，自动带 `trace_id`；
  - `/health`、`/metrics`、`/internal/chaos/*`。
- `demo-services/chaos_controller/`
  - 7 个场景：`db_pool_exhaustion`、`redis_connection_failure`、`upstream_timeout`、`error_burst`、`cpu_burn`、`instance_unavailable`、`bad_release`；
  - `X-Chaos-Token` 鉴权；
  - TTL 自动停止；
  - toxiproxy 代理管理；
  - Docker socket 暂停/恢复容器；
  - `GET /scenarios`、`GET /state`、`POST /scenarios/{name}/start|stop`。
- `infrastructure/`
  - `prometheus/` 抓取配置 + 告警规则；
  - `alertmanager/` Webhook 路由 + Bearer Token；
  - `loki/`、`tempo/`、`otel/`、`alloy/`、`grafana/`；
  - Grafana 数据源与 `IncidentPilot Demo Overview` Dashboard。
- `docker-compose.yml`
  - 新增 `demo`、`obs` profiles；
  - 新增 order / order-b / payment / inventory / chaos-controller / toxiproxy；
  - 新增 Prometheus / Alertmanager / Loki / Tempo / OTel Collector / Alloy / Grafana / exporters；
  - 新增 `obs`、`demo` 网络与数据卷。
- 后端
  - `/metrics` 指标；
  - Webhook 同时支持 `X-Webhook-Token` 与 `Authorization: Bearer`，适配 Alertmanager。

### 3.2 验证

- 后端测试：10 passed；
- ruff / mypy：通过；
- Compose 配置：`docker compose config --quiet` 通过。

## 4. Phase 2 剩余工作

### 4.1 镜像拉取（当前阻塞点）

Docker 默认镜像源 `docker.xuanyuan.me` 对部分镜像返回 403，需使用备用源：

```powershell
docker pull docker.1ms.run/<image>:<tag>
docker tag docker.1ms.run/<image>:<tag> <image>:<tag>
```

已确认可用镜像：

- `prom/prometheus:v2.55.1`
- `prom/alertmanager:v0.28.0`
- `grafana/loki:3.3.2`
- `grafana/tempo:2.6.1`
- `grafana/grafana:11.3.0`
- `otel/opentelemetry-collector-contrib:0.111.0`
- `ghcr.io/shopify/toxiproxy:2.11.0`

待完成：

- `grafana/alloy:v1.6.1`
- `prometheuscommunity/postgres-exporter:v0.16.0`
- `oliver006/redis_exporter:v1.67.0`

注意：`docker-compose.yml` 中 OTel Collector 版本需从 `0.115.0` 改为 `0.111.0`（0.115.0 在当前镜像源不可用）。

### 4.2 启动与联调

```powershell
docker compose --profile demo --profile obs up -d --build
docker compose ps
```

逐项验证：

- [ ] 三个 demo 服务 `/health` 正常；
- [ ] Prometheus targets 全部 UP；
- [ ] Grafana 能看到指标、日志、Trace；
- [ ] Alertmanager 能推送告警到后端 Webhook；
- [ ] 重复 Webhook 不重复建 Incident；
- [ ] chaos-controller 7 个场景可启动、可停止、TTL 生效；
- [ ] 每个场景产生预期指标 / 日志 / Trace；
- [ ] 告警自动创建 Incident；
- [ ] 端到端脚本：注入 → 告警 → Incident。

### 4.3 脚本与文档

- [ ] `scripts/demo-e2e.ps1`：启动场景、等待告警、查询 Incident、停止场景；
- [ ] `scripts/seed-demo.ps1`：创建演示订单与库存数据；
- [ ] `docs/10-demo-sop.md`：7 个场景的演示 SOP；
- [ ] 更新 `README.md` Phase 2 快速启动与访问地址；
- [ ] 更新 `docs/09-roadmap-risks.md` Phase 2 勾选状态。

## 5. Phase 2 演示入口

| 服务 | 地址 | 说明 |
| --- | --- | --- |
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | Targets / Alerts |
| Alertmanager | http://localhost:9093 | 告警状态 |
| Order | http://localhost:8001/docs | 订单 API |
| Payment | http://localhost:8002/docs | 支付 API |
| Inventory | http://localhost:8003/docs | 库存 API |
| Backend | http://localhost:8080/docs | IncidentPilot API |
| Toxiproxy API | http://localhost:8474 | 代理状态 |

## 6. 常用命令

```powershell
# 仅核心栈
docker compose up -d --build

# 核心 + 演示 + 可观测性
docker compose --profile demo --profile obs up -d --build

# 查看状态
docker compose ps

# 查看日志
docker compose logs -f order-service
docker compose logs -f chaos-controller
docker compose logs -f prometheus

# 触发场景（chaos-controller 不暴露宿主端口）
docker compose exec chaos-controller curl -fsS -X POST `
  http://localhost:8010/scenarios/db_pool_exhaustion/start `
  -H "X-Chaos-Token: dev-chaos-token" `
  -H "Content-Type: application/json" `
  -d '{"duration_seconds":120}'

# 停止场景
docker compose exec chaos-controller curl -fsS -X POST `
  http://localhost:8010/scenarios/db_pool_exhaustion/stop `
  -H "X-Chaos-Token: dev-chaos-token"
```

> 正式演示由后端代理调用 chaos-controller；宿主机调试使用 `docker compose exec`。

## 7. 已知问题

| 问题 | 影响 | 处理 |
| --- | --- | --- |
| Docker Hub 镜像源 403 | 部分 obs 镜像拉取失败 | 使用 `docker.1ms.run` 拉取后重新 tag |
| OTel Collector 0.115.0 不可用 | 容器无法启动 | 改用 `0.111.0` |
| chaos-controller 未映射宿主端口 | 宿主机不能直接调用 | 演示通过后端代理，或临时增加 `8010:8010` |
| Alloy Docker 日志采集依赖 Docker socket | Windows Docker Desktop 需允许挂载 | 已挂载 `/var/run/docker.sock` |
| Grafana Tempo 面板格式可能需微调 | Trace 面板可能为空 | 启动后在 Grafana Explore 验证 Tempo 查询 |

## 8. 下一阶段入口

Phase 2 验证完成后：

1. 提交 Phase 2；
2. 进入 Phase 3：MCP 公共库、Prometheus/Loki/Tempo MCP、LangGraph 状态机、LLM 客户端、调查节点、Checkpoint；
3. 首个闭环场景仍为数据库连接池耗尽。
