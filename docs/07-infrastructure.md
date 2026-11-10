# 基础设施与测试环境（Phase 0）

版本：v0.1（待确认）
目标机器：Windows + Docker Desktop（WSL2），16 GB RAM，AMD Ryzen 7 6800H

---

## 1. Compose Profiles 与资源策略

16 GB 机器无法舒适地同时运行"全部重型组件 + 本地大模型"。采用 profiles 分层启动，并给出内存预算。

| Profile | 组件 | 用途 | 预估内存 |
| --- | --- | --- | --- |
| `core`（默认） | postgres、redis、rabbitmq、backend、worker、scheduler、nginx | 业务闭环 | ~1.2 GB |
| `obs` | prometheus、alertmanager、grafana、loki、alloy、tempo、otel-collector | 可观测性 | ~1.4 GB |
| `demo` | order/payment/inventory、order-b、chaos-controller、postgres-exporter、redis-exporter、toxiproxy | 演示微服务 | ~0.8 GB |
| `mcp` | 6 个 MCP Server | 工具层 | ~0.5 GB |
| `rag` | rag-inference（容器模式） | 本地 BGE-M3 + Reranker | ~5.0 GB |
| `milvus` | etcd、minio、milvus-standalone | 向量库 | ~1.8 GB |
| `k8s` | k3d（外部脚本）+ mcp-kubernetes | 真实 K8s 调查/执行 | ~1.0 GB |
| `langfuse` | langfuse-web/worker、clickhouse、redis、minio、postgres | 自托管 LLM 观测（可选） | ~3.5 GB |

推荐组合：

```powershell
# 日常开发（模型跑在宿主机）
docker compose --profile obs --profile demo --profile mcp --profile milvus up -d --build

# 完整演示（模型跑在宿主机）
docker compose --profile obs --profile demo --profile mcp --profile milvus up -d --build

# 无宿主机 Python 时的容器推理（WSL 需分配 ≥ 12 GB）
docker compose --profile obs --profile demo --profile mcp --profile milvus --profile rag up -d --build
```

默认 `core` 服务不带 profile，始终启动。

---

## 2. 服务清单

### 2.1 基础服务

| 服务 | 镜像 | 端口（宿主） | 说明 |
| --- | --- | --- | --- |
| `postgres` | `postgres:16-alpine` | 5433 → 5432 | 业务库 + LangGraph Checkpoint + pgvector |
| `redis` | `redis:7-alpine` | 6380 → 6379 | 缓存、限流、SSE Pub/Sub、锁 |
| `rabbitmq` | `rabbitmq:4-management-alpine` | 5673 → 5672 / 15673 → 15672 | 调查任务、审批恢复、DLQ |
| `backend` | 本地构建 | 8000 | FastAPI API |
| `worker` | 本地构建 | — | RabbitMQ Consumer + LangGraph 执行 |
| `scheduler` | 本地构建 | — | Outbox 投递、审批超时、评测调度 |
| `nginx` | `nginx:1.27-alpine` | 8080 → 80 | 静态资源 + API 反代 + SSE |

### 2.2 可观测性

| 服务 | 镜像 | 端口 | 说明 |
| --- | --- | --- | --- |
| `prometheus` | `prom/prometheus:v2.55.1` | 9090 | 指标抓取与告警规则 |
| `alertmanager` | `prom/alertmanager:v0.28.0` | 9093 | 告警路由到 Webhook |
| `grafana` | `grafana/grafana:11.3.0` | 3000 | 预置 Dashboard |
| `loki` | `grafana/loki:3.3.2` | 3100 | 日志存储 |
| `alloy` | `grafana/alloy:v1.6.1` | 12345 | 容器日志采集 |
| `tempo` | `grafana/tempo:2.6.1` | 3200 / 4317 | Trace 存储 |
| `otel-collector` | `otel/opentelemetry-collector-contrib:0.115.0` | 4317 / 4318 | OTLP 接收与导出 |
| `postgres-exporter` | `prometheuscommunity/postgres-exporter:v0.16.0` | 9187 | 数据库指标 |
| `redis-exporter` | `oliver006/redis_exporter:v1.67.0` | 9121 | Redis 指标 |

### 2.3 演示微服务

| 服务 | 端口 | 说明 |
| --- | --- | --- |
| `order-service` | 8001 | 订单 API，调用 payment/inventory，使用 PostgreSQL + Redis |
| `order-service-b` | 8001（内网） | 预创建但默认停止，用于"扩容"动作 |
| `payment-service` | 8002 | 模拟支付网关，支持延迟/错误注入 |
| `inventory-service` | 8003 | 库存服务，数据库连接池重点观察对象 |
| `chaos-controller` | 8010（仅内网） | 故障注入编排，独立 Token |
| `toxiproxy` | 8474 / 8666 | 网络延迟/断连（Redis、payment 链路） |

### 2.4 MCP Server

| 服务 | 端口（内网） | 上游 |
| --- | --- | --- |
| `mcp-prometheus` | 8101 | prometheus:9090 |
| `mcp-loki` | 8102 | loki:3100 |
| `mcp-tempo` | 8103 | tempo:3200 |
| `mcp-kubernetes` | 8104 | k3d API（profile `k8s`） |
| `mcp-github` | 8105 | GitHub API / 本地 Git |
| `mcp-knowledge-base` | 8106 | backend:8000/internal/rag |

### 2.5 RAG 与向量库

| 服务 | 端口 | 说明 |
| --- | --- | --- |
| `rag-inference` | 8100 | 本地 BGE-M3 + Reranker（容器模式） |
| `milvus-standalone` | 19530 / 9091 | 向量库 |
| `etcd` | 2379 | Milvus 元数据 |
| `minio` | 9000 / 9001 | Milvus 对象存储 |

---

## 3. 网络与卷

```text
networks:
  edge:      nginx, frontend
  app:       backend, worker, scheduler, mcp-*, rag-inference
  data:      postgres, redis, rabbitmq, milvus, etcd, minio
  obs:       prometheus, alertmanager, loki, tempo, otel, alloy, grafana, demo services, backend
  demo:      demo services, chaos-controller, toxiproxy
```

- 仅 nginx 发布 80/8080；开发期 Vite 5173；
- Prometheus/Grafana/Alertmanager 默认仅内网，`docker-compose.override.yml` 可临时映射到宿主；
- MCP 与数据服务不发布端口；
- chaos-controller 仅 `demo` + `app`（供后端代理），不加入 `edge`。

卷：

| 卷 | 用途 |
| --- | --- |
| `pg_data` | PostgreSQL |
| `redis_data` | Redis AOF |
| `rabbit_data` | RabbitMQ |
| `prom_data` / `loki_data` / `tempo_data` / `grafana_data` | 可观测性 |
| `milvus_data` / `etcd_data` / `minio_data` | 向量库 |
| `kb_storage` | 原始文档与解析产物 |
| `bm25_index` | BM25 索引快照 |

模型目录只读挂载：

```yaml
volumes:
  - ${MODEL_DIR_HOST:-D:/mode}:/models:ro
```

要求 Docker Desktop 已共享 D 盘。

---

## 4. 可观测性数据流

```mermaid
flowchart LR
    SVC["Demo Services<br/>FastAPI + OTel SDK"] -->|"/metrics"| PROM["Prometheus"]
    BE["Backend / Worker"] -->|"/metrics"| PROM
    PGX["postgres-exporter"] --> PROM
    RDX["redis-exporter"] --> PROM
    PROM -->|"规则触发"| AM["Alertmanager"]
    AM -->|"Webhook"| API["Backend API"]

    SVC -->|"OTLP gRPC 4317"| OTEL["OTel Collector"]
    BE -->|"OTLP"| OTEL
    OTEL -->|"traces"| TEMPO["Tempo"]
    OTEL -->|"metrics"| PROM
    OTEL -->|"logs"| LOKI

    SVC -->|"stdout JSON"| ALLOY["Grafana Alloy"]
    BE -->|"stdout JSON"| ALLOY
    ALLOY -->|"push"| LOKI

    GRAF["Grafana"] --> PROM
    GRAF --> LOKI
    GRAF --> TEMPO
```

### 4.1 指标规范

- 统一标签：`service`、`namespace`、`instance`、`version`、`env`；
- 应用指标：`http_requests_total{status,route,method}`、`http_request_duration_seconds`、`sqlalchemy_pool_checked_out`、`sqlalchemy_pool_size`、`redis_up`、`chaos_active{scenario}`；
- 禁止高基数标签（用户 ID、Trace ID 不进指标）。

### 4.2 告警规则（示例）

| 规则 | 表达式（简化） | for | 严重度 |
| --- | --- | --- | --- |
| `HighErrorRate` | `sum(rate(http_requests_total{status=~"5.."}[2m])) by (service) / sum(rate(http_requests_total[2m])) by (service) > 0.05` | 2m | critical |
| `HighLatencyP95` | `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, service)) > 0.8` | 3m | warning |
| `DBPoolExhausted` | `sqlalchemy_pool_checked_out / sqlalchemy_pool_size > 0.9` | 1m | critical |
| `HighCPU` | `rate(process_cpu_seconds_total[2m]) > 0.85` | 3m | warning |
| `InstanceDown` | `up{job=~".*-service"} == 0` | 1m | critical |
| `RedisDown` | `redis_up == 0` | 1m | critical |
| `ServiceUnavailable` | `probe_success{job="blackbox"} == 0` | 1m | critical |

### 4.3 Alertmanager

```yaml
route:
  receiver: incidentpilot
  group_by: [service, alertname]
  group_wait: 10s
  group_interval: 30s
  repeat_interval: 1h
receivers:
  - name: incidentpilot
    webhook_configs:
      - url: http://backend:8000/api/v1/webhooks/alertmanager
        send_resolved: true
        http_config:
          authorization:
            type: Bearer
            credentials_file: /etc/alertmanager/webhook_token
```

### 4.4 Loki / Tempo / Grafana

- Alloy 通过 Docker service discovery 采集容器 stdout，标签 `service`、`container`、`compose_project`；
- 服务输出 JSON 日志：`timestamp`、`level`、`service`、`trace_id`、`span_id`、`message`、`request_id`；
- Tempo 本地存储，保留 7 天；OTel Collector 批量导出；
- Grafana 预置数据源与 4 个 Dashboard：系统概览、服务指标、Agent 执行、修复与验证。

---

## 5. 演示微服务与故障场景

### 5.1 服务职责

| 服务 | 职责 | 关键依赖 | 观测点 |
| --- | --- | --- | --- |
| Order | 创建/查询订单，编排支付与库存 | PostgreSQL、Redis、Payment、Inventory | 5xx、P95、下游调用耗时、缓存命中 |
| Payment | 模拟支付授权 | 外部网关（模拟） | 延迟、错误率、超时 |
| Inventory | 库存查询/扣减 | PostgreSQL（连接池重点） | 连接池、SQL 耗时、锁等待 |

所有服务：

- FastAPI + SQLAlchemy async + asyncpg；
- `prometheus-fastapi-instrumentator` + 自定义指标；
- OTel SDK（FastAPI/HTTPX/SQLAlchemy/Redis 自动埋点）；
- 结构化 JSON 日志，自动注入 `trace_id`；
- 健康检查 `/health`（含依赖检查）；
- `/metrics`；
- 故障注入开关仅由 chaos-controller 调用，不对外暴露。

### 5.2 七个故障场景

| # | 场景 | 触发方式 | 预期指标 | 预期日志 | 预期 Trace | 预期根因 | 修复动作 | 验证条件 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 数据库连接池耗尽 | `POST /chaos/db-pool-exhaustion`（hold 连接 + 高并发） | `sqlalchemy_pool_checked_out=5/5`、P95↑、5xx↑ | `QueuePool limit of size 5 overflow 10 reached`、`TimeoutError` | DB Span 等待、请求超时 | `DB_POOL_EXHAUSTION` | 重启/扩容、清理长事务 | 池使用率 < 80%、5xx < 1%、P95 恢复 |
| 2 | Redis 连接异常 | toxiproxy 断开或 chaos 开关 | `redis_up=0`、5xx↑ | `ConnectionError: Error connecting to Redis` | Redis Span 错误 | `REDIS_CONNECTION_FAILURE` | 重启服务/恢复网络 | `redis_up=1`、5xx < 1% |
| 3 | 上游超时 | toxiproxy 给 payment 加 3s 延迟 | order P95↑、payment Span 3s | `httpx.ReadTimeout`、`upstream timeout` | payment Span 占关键路径 | `UPSTREAM_TIMEOUT` | 扩容/重启/回滚 | P95 < 800ms、超时日志消失 |
| 4 | HTTP 500 突增 | `POST /chaos/error-burst`（30% 异常） | 5xx 18%、错误 Span↑ | `Unhandled exception` + 堆栈 | 错误 Span 集中在 order | `CODE_DEFECT` | 回滚版本 | 5xx < 1%、错误日志下降 70% |
| 5 | CPU 饱和 | `POST /chaos/cpu-burn`（90s） | CPU > 90%、P95↑ | 无明显错误，慢请求 | 全链路耗时上升 | `RESOURCE_SATURATION_CPU` | 扩容 | CPU < 70%、P95 恢复 |
| 6 | 实例不可用 | `POST /chaos/kill-instance`（暂停容器） | `up=0`、5xx↑ | 连接拒绝 | 调用失败 | `INSTANCE_UNAVAILABLE` | 重启实例 | `up=1`、健康检查 200 |
| 7 | 发布导致异常 | `POST /chaos/bad-release`（切换 v2-bad + 写发布记录） | 5xx↑、SQL 耗时↑ | `N+1 query detected` / 慢 SQL | DB Span 数量异常 | `BAD_RELEASE` | 回滚到 v1 | 5xx < 1%、SQL 耗时恢复 |

每个场景配套：

- 演示脚本（启动 → 等待告警 → 调查 → 审批 → 执行 → 验证）；
- 知识库 SOP 文档（供 RAG 检索）；
- 评测用例（期望根因、必选证据、期望工具、修复动作）；
- 自动停止 TTL（默认 10 分钟），防止忘记关闭。

### 5.3 隔离要求

1. chaos-controller 只在 `demo` 网络，仅 backend 通过内网调用；
2. `CHAOS_ENABLED=true` + `X-Chaos-Token` 双条件；
3. Agent 工具目录不包含任何 chaos 工具；
4. 所有注入写审计；
5. 生产/演示配置分离：`APP_ENV=demo` 才注册 `/demo/*` 与 chaos 代理；
6. 注入逻辑代码放在 `demo-services/`，不进入 `backend/app/remediation/`。

---

## 6. 本地模型部署

### 6.1 已验证结果

| 模型 | 路径 | 加载 | 输出 | 备注 |
| --- | --- | --- | --- | --- |
| BGE-M3 | `D:\mode\bge-m3-safetensors` | 2.3s（CPU） | 1024 维，L2 归一化 | `sentence-transformers` 5.6 加载成功；目录名为 safetensors，实际权重为 `pytorch_model.bin`，不影响加载 |
| BGE Reranker v2-m3 | `D:\mode\bge-reranker-v2-m3` | 2.0s（CPU） | 相关 0.982 / 不相关 0.029 | `CrossEncoder` 加载成功 |

### 6.2 推荐：宿主机推理服务（16 GB 最优）

- 独立进程，避免与 Milvus/可观测性争抢 WSL 内存；
- 后端容器通过 `host.docker.internal:8100` 访问；
- 启动：`scripts/start-inference.ps1`（使用本地 Python 3.11 + 已装 ST 5.6，或创建 3.12 venv）；
- 环境：`OMP_NUM_THREADS=6`、`TOKENIZERS_PARALLELISM=false`；
- 接口：`POST /embed`、`POST /rerank`、`GET /health`、`POST /warmup`；
- 批处理：embedding batch 16，rerank batch 8；
- 超时：embedding 30s，rerank 60s；
- 懒加载 Reranker，空闲 10 分钟释放（可选）；
- 预热：启动后加载 BGE-M3，Reranker 首次请求加载。

### 6.3 备选：容器推理

- `rag_inference/Dockerfile`：`python:3.12-slim` + CPU 版 torch + sentence-transformers；
- 挂载 `${MODEL_DIR_HOST}:/models:ro`；
- `mem_limit: 6g`；
- WSL 内存建议 ≥ 12 GB；
- 首次启动需下载 torch（约 200 MB CPU wheel）+ 依赖，模型不复制。

### 6.4 设备策略

- 默认 CPU：稳定、可复现；单查询 embedding 约 0.1–0.5s，rerank 20 条约 0.5–1.5s；
- 可选 GPU：需安装 CUDA 版 PyTorch；RTX 3060 4 GB 只能驻留一个模型，建议 embedding 用 GPU、rerank 用 CPU，或反之；
- 不在 Phase 1 引入 GPU 依赖，避免环境不稳定。

### 6.5 向量库策略

- 默认 Milvus standalone（满足企业技术栈）；
- `VectorStore` 端口 + 两个适配器：`MilvusVectorStore`、`PgVectorStore`；
- 低内存机器可设 `VECTOR_STORE=pgvector`，无需启动 Milvus；
- Embedding 模型与维度写入 `document_versions`，切换模型必须重建索引；
- 索引类型：HNSW（M=16, efConstruction=200），度量 `COSINE`。

### 6.6 LLM 接口验证（NVIDIA NIM）

请求地址：`https://integrate.api.nvidia.com/v1`
模型：`nvidia/nemotron-3.5-super-vl-120b-a12b`

| 测试 | 结果 |
| --- | --- |
| `/models` | 模型存在；同系列还有 `nemotron-3-super-120b-a12b`、`nemotron-3.5-lightning-30b-a3b` 可作 fallback |
| Chat Completions | 1.08s，返回精确 JSON |
| JSON 模式 | `response_format={"type":"json_object"}` 可用；`max_tokens=300` 时 301 个 reasoning token 导致 content 为空；提高到 1200 后正常 |
| Function Calling | 1.42s，`finish_reason=tool_calls`，参数正确 |
| 推理内容 | 返回 `reasoning_content`，必须剥离 |
| 结论 | 作为主模型可用；所有节点默认 `max_tokens=4096`，预算统计包含 `reasoning_tokens` |

安全：API Key 只写入本机 `.env`（已被 `.gitignore` 忽略），不写入代码、日志、文档或 Git；如 Key 曾在聊天/公开渠道出现，建议在 NVIDIA 控制台轮换。

---

## 7. 环境变量（.env.example 规划）

```dotenv
# App
APP_ENV=development            # development | demo | test | production
APP_NAME=IncidentPilot
SECRET_KEY=change-me
ENCRYPTION_KEY=change-me-32-bytes-base64
LOG_LEVEL=INFO
API_BASE_URL=http://localhost:8080
CORS_ORIGINS=http://localhost:5173,http://localhost:8080

# Database
DATABASE_URL=postgresql+asyncpg://incidentpilot:incidentpilot@postgres:5432/incidentpilot
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20

# Redis / MQ
REDIS_URL=redis://redis:6379/0
RABBITMQ_URL=amqp://incidentpilot:incidentpilot@rabbitmq:5672/
RABBITMQ_EXCHANGE=incidentpilot
RABBITMQ_DLQ=incidentpilot.dlq

# Auth
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
WEBHOOK_TOKEN=change-me
INTERNAL_TOKEN=change-me

# LLM (NVIDIA NIM, OpenAI-compatible)
LLM_PROVIDER=nvidia              # nvidia | qwen | deepseek | openai_compatible
LLM_BASE_URL=https://integrate.api.nvidia.com/v1
LLM_API_KEY=                     # 只放在 .env，禁止提交
LLM_MODEL=nvidia/nemotron-3.5-super-vl-120b-a12b
LLM_FALLBACK_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b
LLM_MAX_TOKENS=4096              # 必须覆盖 reasoning_tokens
LLM_TIMEOUT_SECONDS=180
LLM_MAX_RETRIES=2
LLM_MAX_CONCURRENCY=4
LLM_TEMPERATURE=0.1
LLM_STRIP_REASONING=true

# Agent
GRAPH_VERSION=v1
AGENT_MAX_TOOL_CALLS=30
AGENT_MAX_TOKENS=100000
AGENT_MAX_SECONDS=720
AGENT_MAX_FOLLOWUPS=2
AGENT_CONFIDENCE_THRESHOLD=0.65
CHECKPOINT_BACKEND=postgres

# MCP
MCP_TRANSPORT=streamable_http
AGENT_MCP_TOKEN=change-me
EXECUTOR_MCP_TOKEN=change-me
MCP_PROMETHEUS_URL=http://mcp-prometheus:8101
MCP_LOKI_URL=http://mcp-loki:8102
MCP_TEMPO_URL=http://mcp-tempo:8103
MCP_KUBERNETES_URL=http://mcp-kubernetes:8104
MCP_GITHUB_URL=http://mcp-github:8105
MCP_KB_URL=http://mcp-knowledge-base:8106

# Observability upstreams
PROMETHEUS_URL=http://prometheus:9090
LOKI_URL=http://loki:3100
TEMPO_URL=http://tempo:3200
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com

# RAG
VECTOR_STORE=milvus             # milvus | pgvector
MILVUS_URI=http://milvus-standalone:19530
MILVUS_COLLECTION=incidentpilot_kb
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIM=1024
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
RAG_INFERENCE_URL=http://host.docker.internal:8100
MODEL_DIR_HOST=D:/mode
BGE_M3_PATH=/models/bge-m3-safetensors
BGE_RERANKER_PATH=/models/bge-reranker-v2-m3
CHUNK_SIZE=600
CHUNK_OVERLAP=90
RETRIEVAL_TOP_K=20
RERANK_TOP_N=5

# GitHub / Change
GITHUB_TOKEN=
GITHUB_REPO=
GITHUB_MODE=local               # local | remote
LOCAL_GIT_REPO=./demo-services

# Remediation
REMEDIATION_ENABLED=false       # 默认关闭，演示时开启
AUTO_APPROVE_LOW_RISK=false
REMEDIATION_BACKEND=docker      # docker | k8s
DEMO_NAMESPACE=demo
MAX_SCALE_REPLICAS=3
APPROVAL_TTL_MINUTES=15
EXECUTION_TIMEOUT_SECONDS=120

# Demo
DEMO_MODE=false
CHAOS_ENABLED=false
CHAOS_TOKEN=change-me
CHAOS_URL=http://chaos-controller:8010

# Frontend
VITE_API_BASE_URL=/api/v1
VITE_SSE_HEARTBEAT_MS=15000
```

> 所有密钥只通过环境变量或加密存储，不进入 Git；`.env.example` 不含真实值。

---

## 8. 启动与初始化（Windows PowerShell）

```powershell
# 1. 启动 Docker Desktop（当前 daemon 未运行）
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
# 等待 Docker 就绪
docker info

# 2. 配置环境
Copy-Item .env.example .env
# 编辑 .env：填入 LLM_API_KEY、GITHUB_TOKEN（可选）

# 3. 启动基础 + 可观测性 + 演示 + MCP + Milvus
docker compose --profile obs --profile demo --profile mcp --profile milvus up -d --build

# 4. 数据库迁移与种子
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.cli seed

# 5. 宿主机启动本地模型推理
.\scripts\start-inference.ps1

# 6. 访问
# Web:        http://localhost:8080
# Grafana:    http://localhost:3000  (admin/admin)
# Prometheus: http://localhost:9090
# API Docs:   http://localhost:8080/docs
```

开发模式前端：

```powershell
cd frontend
npm install
npm run dev   # http://localhost:5173，代理 /api 到 8080
```

---

## 9. 资源预算（16 GB）

| 类别 | 预算 |
| --- | --- |
| Windows 系统 + IDE + 浏览器 | ~5.0 GB |
| WSL2 / Docker 容器（core+obs+demo+mcp+milvus） | ~6.0 GB |
| 宿主机 RAG 推理进程 | ~4.5 GB |
| 余量 | ~0.5 GB |

建议 `.wslconfig`：

```ini
[wsl2]
memory=10GB
processors=6
swap=4GB
```

若同时自托管 Langfuse 或使用容器推理，需 12 GB WSL，16 GB 机器会非常紧张；因此默认不启用这两个 profile。

---

## 10. 常见问题

| 问题 | 处理 |
| --- | --- |
| Docker daemon 未启动 | 启动 Docker Desktop，等待 `docker info` 成功 |
| WSL 内存不足 / 容器 OOM | 调整 `.wslconfig`，减少 profiles，RAG 用宿主机 |
| D 盘无法挂载到容器 | Docker Desktop → Settings → Resources → File Sharing 添加 D: |
| 端口冲突 | 修改 `.env` 中映射端口或停止占用进程 |
| Milvus 启动慢 | 等待 etcd/minio 健康后再启动 milvus；查看 `docker compose logs milvus-standalone` |
| 模型加载失败 | 检查路径、`sentence-transformers` 版本、`HF_HUB_OFFLINE=1` |
| Alertmanager 无法回调 | 确认 backend 在 `obs` 网络、Token 文件一致 |
| SSE 被缓冲 | 检查 Nginx `proxy_buffering off` 与 `X-Accel-Buffering: no` |
| 时间窗口无数据 | 确认容器时区为 UTC、Prometheus 抓取正常、服务有流量 |
| 宿主机推理无法访问 | 后端使用 `host.docker.internal`，Windows 防火墙放行 8100 |
