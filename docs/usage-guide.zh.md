# Vortex 使用指南

> 从零到跑起来，以及跑起来之后该怎么用。
>
> **配置/端口以 [`config/registry.yml`](../config/registry.yml) + [ADR-003](adr/ADR-003-unified-config-architecture.md) 为准；启动/运维命令统一用 `vortex` CLI。**
>
> **本文定位**：覆盖三类使用场景——
> ① **正在改代码，要快速部署测试**（→ 跳到 [Dev-Loop](#dev-loop-正在改代码快速迭代)）；
> ② **首次从零部署**（→ [P0–P1](#p0-首次环境搭建全局一次性)）；
> ③ **服务跑起来后的日常运营与使用**（→ [P2–P5](#p2-日常数据运营)）。
>
> 部署配置细节见 [`deploy/CONFIG-AND-RUN.zh.md`](../deploy/CONFIG-AND-RUN.zh.md)；
> 设计决策见 [`docs/adr/`](adr/)。

---

## 系统地图（先建立这张图）

```
vortex_common/deploy/          ← 唯一生产部署入口（ADR-001）
├── pull-code.sh               → 拉各仓代码到 repos/<svc>，种 .env
├── build-release.sh           → 造组合镜像 vortex:latest
├── docker-compose.yml         → 定义四个服务的编排关系
└── versions.yml               → 各仓锁定的 git ref/tag

服务关系（依赖方向）：

  vortex-data  ──写──►  /workspace（共享数据卷）
  vortex-qmt             ↑
  vortex-backtest  ──读──┘   各服务自己的 /state（独立卷）

端口约定（内==外，单一编号，不再重映射；以 registry.yml + ADR-003 为准）：
  data      8765   (Dashboard + API)
  backtest  8766
  qmt       8767
  trader    8768   (预留)
```

**核心原则**：数据落在卷里，容器是无状态的。
`vortex run deploy` 重建容器不丢数据；`.env` 改完重建容器即生效，不重建镜像。

---

---

## Dev-Loop: 正在改代码，快速迭代

> **你在改代码，改完想马上跑起来看效果**。三种速度，按场景选一种。

### 速度 A：单仓 compose（最快，10–30 秒）

适合：只改当前仓、不需要跨服务联调。

```bash
cd vortex_backtest      # 换成你正在改的那个仓

# 改完代码后：
docker compose up -d --build
# Docker 用 layer cache：vortex-base 层不动，只重跑 pip install --no-deps .
# 通常 10–30 秒，比重装所有依赖快 10 倍
```

首次需要先有 `vortex-base` 镜像（P0 第1步）和填好 `.env`（P0 第3步）。之后改代码只需这一条命令。

---

### 速度 B：组合部署 + 本地代码（30–60 秒，能跨服务联调）

适合：需要 data + backtest 一起跑、改的是组合部署里的一个服务。

```bash
cd vortex_common/deploy

# 用本地目录的代码替代 repos/ 里的（不影响其他服务）
VORTEX_BACKTEST_SRC=/绝对路径/vortex_backtest \
  ./build-release.sh

vortex run up backtest    # 只重建 backtest，data 容器保持不动

# 支持多仓同时覆盖：
VORTEX_DATA_SRC=/绝对路径/vortex_data \
VORTEX_BACKTEST_SRC=/绝对路径/vortex_backtest \
  ./build-release.sh
```

`VORTEX_<SVC>_SRC` 变量名规则：`SVC` = 仓库名去掉 `vortex_` 后大写
（`vortex_data` → `DATA`，`vortex_backtest` → `BACKTEST`，`vortex_qmt` → `QMT`）。

---

### 速度 C：exec 进容器直接打补丁（秒级，临时，重建容器会丢）

适合：容器已跑，只想快速验证一个小改动，不想重建镜像。

```bash
# 把本地改好的文件复制进运行中的容器
docker compose cp vortex_backtest/your_module.py vortex-backtest:/app/services/vortex_backtest/your_module.py

# 或者进容器 shell 手动操作
docker compose exec vortex-backtest bash
# 容器内：
cd /app/services/vortex_backtest
pip install --no-deps --no-build-isolation .   # 重装本服务代码（不动第三方依赖）

# 改完重启服务进程（不重建容器，数据不丢）
docker compose restart vortex-backtest
```

> ⚠️  `docker compose cp` 和容器内的改动在 `docker compose up -d --build` 后会丢失。
> 确认改动正确后，用速度 A 或 B 固化进镜像。

---

### 开发迭代常用命令速查

```bash
# 改了代码后重建并重启（单仓，最常用）
docker compose up -d --build

# 只看最新日志（不 follow，看改动有没有生效）
docker compose logs --tail=50 vortex-backtest

# 重启容器（不重建镜像，适合改了 .env 生效或软重启）
docker compose restart vortex-backtest

# 进容器 shell 调试
docker compose exec vortex-backtest bash

# 看容器内实际读到的环境变量
docker compose exec vortex-backtest env | grep VORTEX
```

---

## P0. 首次环境搭建（全局一次性）

> 换机器、全新安装时走这一节。已有 `vortex-base` 镜像可跳过第1步。

### 第1步：构建基础镜像

```bash
cd vortex_common
scripts/build-base-image.sh
# 产出：vortex-base:latest（含所有第三方 Python 依赖，后续改代码不重装依赖）
```

耗时取决于网速（首次约3-10分钟）。之后改各仓业务代码只需秒级重建。

### 第2步：拉取各仓代码

```bash
cd vortex_common/deploy
./pull-code.sh
# 产出：repos/vortex_data/  repos/vortex_qmt/  repos/vortex_backtest/
#       + 首次从各仓 .env.example 种出 .env（让你填密钥）
```

### 第3步：填写密钥（最少只需填 data 的 token）

```bash
# 必填（数据服务核心凭证）
vi repos/vortex_data/.env
  TUSHARE_TOKEN=<你的 tushare pro token>
  # 对外暴露写接口时加：
  # VORTEX_DATA_DASHBOARD_TOKEN=<自定义，python3 -c "import secrets;print(secrets.token_hex(24))">

# 按需填（只跑数据/回测可先跳过）
vi repos/vortex_qmt/.env
  VORTEX_QMT_TOKEN=<写接口 token>
  QMT_BRIDGE_BASE_URL=http://<Windows IP>:8000
  QMT_BRIDGE_TOKEN=<桥接 token>
  QMT_ACCOUNT_ID=<账户 ID>
```

### 第4步：构建组合镜像

```bash
cd vortex_common/deploy
./build-release.sh
# 产出：vortex:latest（.env 不进镜像，运行时由 compose env_file 注入）
```

---

## P1. 启动数据服务（先只起这一个）

```bash
cd vortex_common/deploy
vortex run up data
docker compose ps                      # 等到 health: healthy（约30秒）
docker compose logs -f vortex-data     # 看启动日志
```

验证：

```bash
curl http://localhost:8765/api/health
# 或浏览器开 http://localhost:8765 查看 Dashboard
```

**首次启动会自动 init workspace**，无需手动初始化。之后 scheduler 按计划
（默认：交易日收盘后）自动抓取 Tushare 数据，落盘到 `/workspace/data/`（Parquet 分区）。

---

## P2. 日常数据运营

数据服务跑起来后，绝大多数时间**无需干预**——scheduler 自动采集。关注以下几点：

### 监控任务状态

```bash
# 命令行
curl http://localhost:8765/api/tasks | python3 -m json.tool

# 或浏览器 Dashboard
open http://localhost:8765
```

任务状态：`pending` → `running` → `success` / `failed`。
`failed` 任务下次调度会自动重试；也可通过 API 手动触发。

### 看日志

```bash
docker compose logs -f vortex-data         # 实时跟踪
docker compose logs --tail=200 vortex-data # 最近200行
```

### 磁盘管理

数据服务内置磁盘保护：可用空间低于 `min_free_gb`（默认设置中可配置）时自动暂停写入，
不自动删除已有数据。需要你手动清理或扩容。

```bash
df -h                                      # 查当前磁盘用量
docker volume ls                           # 列出 vortex 命名卷
```

### 凭证积分告警

Tushare 积分不足时，采集任务会出现 `blocked_credentials`。
检查积分后更新 `.env` 里的 `TUSHARE_TOKEN`，然后：

```bash
vortex run up data                         # 重建容器使新 token 生效
```

---

## P3. 使用数据（研究 / 回测）

### 方式一：直接读 Parquet（DuckDB）

最轻量，不依赖 backtest 服务，适合探索性分析：

```python
import duckdb

# workspace 路径（Docker named volume 挂载在容器内 /workspace；
# 单仓开发时宿主机路径通常是 vortex_data/workspace）
ws = "/path/to/vortex_workspace"

conn = duckdb.connect()
df = conn.execute(f"""
    SELECT * FROM read_parquet('{ws}/data/daily/**/*.parquet')
    WHERE ts_code = '000001.SZ'
    ORDER BY trade_date DESC
    LIMIT 20
""").df()
```

> 数据分区规则见 `vortex_data/docs/` 或 `vortex_data/CLAUDE.md §数据落盘`。

### 方式二：通过 backtest 服务跑回测

#### 1. 启动 backtest 服务

```bash
cd vortex_common/deploy
vortex run up backtest
docker compose ps vortex-backtest         # 等到 healthy
```

backtest 容器以只读模式挂载 data 的 workspace，无需 data 服务正在运行（只读文件即可）。

#### 2. 提交回测任务

```bash
# HTTP API（参数格式见 vortex_backtest/docs/）
curl -X POST http://localhost:8766/api/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "strategy": "momentum",
    "start": "2023-01-01",
    "end":   "2023-12-31",
    "universe": "hs300"
  }'
```

#### 3. 查询结果

```bash
curl http://localhost:8766/api/backtest/<task_id>
```

---

## P4. 升级代码版本

改服务代码或跟进新版本时的标准流程：

```bash
# 1. 更新版本锁定
vi vortex_common/deploy/versions.yml
  # 改对应仓库的 ref: <new-tag-or-commit>

# 2. 拉新代码（不覆盖你已填的 .env）
cd vortex_common/deploy
./pull-code.sh

# 3. 重建镜像
./build-release.sh

# 4. 滚动更新（容器重建，数据卷保留）
vortex run up data                        # 单服务
# vortex run deploy                        # 全栈
```

> 如果只改了配置（`.env`）而没改代码，跳过步骤1-3，直接 `vortex run up <svc>`。

---

## P5. 配置变更

| 改什么 | 操作 | 需要重建镜像？ |
|--------|------|-------------|
| token / URL（`.env`） | 改 `repos/<svc>/.env` → `vortex run up <svc>` | 否 |
| 端口对外暴露 | `VORTEX_DATA_BIND_ADDR=0.0.0.0 vortex run deploy`（端口由 registry 钉死，不再重映射） | 否 |
| 抓取计划 / lane | 通过 Dashboard API（运行时生效，不重启） | 否 |
| 业务代码 | 改 repos 代码 → `./build-release.sh` → `vortex run up <svc>` | 是 |
| 第三方依赖（requirements） | 改 `docker/requirements-base.txt` → `build-base-image.sh` → `build-release.sh` → `vortex run up <svc>` | 是（基础镜像也要重建） |

### 对外暴露（云服务器/局域网）

> **安全顺序**：先设 token，再开 0.0.0.0，避免裸暴露写接口。

```bash
# repos/vortex_data/.env 先加：
VORTEX_DATA_DASHBOARD_TOKEN=<你生成的 token>

# 然后（端口由 registry 钉死为 8765，内==外、不再重映射；只需把绑定地址放开到 0.0.0.0）
VORTEX_DATA_BIND_ADDR=0.0.0.0 \
vortex run deploy

# 再开云服务器安全组 8765 入站
```

---

## P6. 单仓本地开发

需要改某个服务代码并快速测试时，不必走完整 deploy 流程：

```bash
cd vortex_data                  # 以 data 为例

# 首次：从模板生成 .env 并填密钥
cp .env.example .env
vi .env                        # 填 TUSHARE_TOKEN

# 构建并启动（仅本仓容器，不依赖组合镜像）
docker compose up -d --build

# 查看
docker compose logs -f
```

单仓开发的 workspace/state 路径由 `vortex run` 注入（默认 `~/vortex/{workspace,state}`，
可用 `VORTEX_WORKSPACE_HOST_ROOT` / `VORTEX_STATE_HOST_ROOT` 覆盖；见 ADR-003）。
开发完毕后按 P4 流程合入组合部署。

---

## 速查：最常用命令

```bash
# 全在 vortex_common/deploy/ 下执行
./pull-code.sh                       # 拉/更新各仓代码
./build-release.sh                   # 造组合镜像
vortex run up data                   # 起/重建数据服务
vortex run deploy                    # 起全栈
docker compose ps                    # 健康状态
docker compose logs -f vortex-data   # 实时日志
docker compose restart vortex-data   # 软重启（不重建容器）
docker compose down                  # 停容器（数据卷保留）
```

---

## 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| `vortex run` 报 env file not found | 没先 `./pull-code.sh` | 先 pull-code |
| 抓数一直 `blocked_credentials` | `TUSHARE_TOKEN` 未填或积分不足 | 填/换 token 后 `vortex run up data` |
| 写操作返回 401 | 没设 `DASHBOARD_TOKEN` 或调用时未带 token | 设 token 后 `vortex run up <svc>` |
| 改了 `.env` 没生效 | 没在 `deploy/` 目录下跑，或没 `vortex run` | `cd deploy` 后重跑 `vortex run up <svc>` |
| 磁盘满了，数据停止写入 | 触发磁盘保护 | 扩容或清理后，服务自动恢复写入 |
| backtest 读不到数据 | workspace 卷里无 Parquet 或路径不对 | 确认 data 服务已运行并采集；检查 `VORTEX_WORKSPACE` 挂载 |

---

## 相关文档

- [`deploy/CONFIG-AND-RUN.zh.md`](../deploy/CONFIG-AND-RUN.zh.md) — 部署配置操作细节
- [`config/registry.yml`](../config/registry.yml) + [`docs/adr/ADR-003`](adr/ADR-003-unified-config-architecture.md) — 统一配置/端口真值源
- [`docs/adr/ADR-001`](adr/ADR-001-deployment-architecture.md) — 组合镜像/部署架构决策
- [`docs/adr/ADR-002`](adr/ADR-002-unified-workspace-env-vars.md) — Workspace 环境变量统一规范
- `vortex_data/CLAUDE.md` — 数据服务内部约定
