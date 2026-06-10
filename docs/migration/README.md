# Vortex 服务仓接入统一镜像 —— 通用迁移指南

> ⚠️ 本指南为 vortex-base 迁移期（ADR-001）历史文档。配置/端口/CLI 以 [ADR-003](../adr/ADR-003-unified-config-architecture.md) + config/registry.yml 为准。

面向每个服务仓（`vortex_data` / `vortex_qmt` / `vortex_backtest`，以及将来的 `vortex_trader`）。
各仓在自己的 session 里照这一份指南做调整即可——**通用步骤**对所有仓一致，少量**各仓差异**集中在 §3。

> 背景：共用第三方依赖已统一进 `vortex-base` 基础镜像（见 [vortex_common/README](../../README.md)）。
> **qlib 已不在计划内**，因此三仓彻底同构、原生架构通用，无 amd64/pyqlib 特殊处理。

## 0. 迁移完成后的统一形态

每个服务仓都收敛成同一个样子：

- 应用镜像 `FROM vortex-base:latest` → 只叠自己的代码 → `pip install --no-deps .`（依赖都在 base）。
- 在通用位置提供 `deploy/run.sh`（启动契约，被组合镜像的 `vortexctl` 调用）。
- 运行时一进程一容器（与 k8s 对齐），原生架构。

## 1. 前置：构建 vortex-base（一次）

```bash
(cd ../vortex_common && scripts/build-base-image.sh)     # → vortex-base:latest
```

## 2. 通用步骤（每个仓都做）

**① 改 `Dockerfile`：FROM 指向 vortex-base，安装改 `--no-deps`。** 模板（`<pkg>`/端口按本仓替换）：

```dockerfile
ARG BASE_IMAGE=vortex-base:latest
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Shanghai
# … 保留本仓原有的 VORTEX_*_HOST/PORT/目录 等 ENV

WORKDIR /app
COPY pyproject.toml README.md /app/
COPY <pkg> /app/<pkg>
RUN pip install --no-deps --no-build-isolation .     # 依赖在 base；build-backend(hatchling/setuptools)也在 base

VOLUME ["..."]
EXPOSE <port>
CMD ["vortex-<svc>", "serve"]      # 或本仓原有启动命令
```

**② 删掉本仓自己维护的依赖底座 / 多余装依赖步骤**（各仓不同，见 §3）。

**③ 新增 `deploy/run.sh`** 启动契约（见 §4）。

**④ 对齐 `docker-compose.yml`，并删除本仓的 `scripts/build-image.sh`**：compose 写
`image: vortex-<svc>:latest` + `build: { context: ., args: { BASE_IMAGE: ${BASE_IMAGE:-vortex-base:latest} } }`。
这样本地「构建 + 运行」统一一条 `docker compose up -d --build`（compose 直接用本仓 `Dockerfile` 构建本地代码）。

> **不必每仓再自带构建脚本。** 各仓旧的 `scripts/build-image.sh` 本就各不相同、且只是包了一层
> `docker build`——`docker compose up -d --build` 已等价覆盖，删掉即可。发布用的**组合镜像**由 common 的
> `deploy/pull-code.sh`（拉各仓）+ `deploy/build-release.sh`（造镜像）统一制造，与本仓脚本无关。前置 `vortex-base` 一次性建好：
> `(cd ../vortex_common && scripts/build-base-image.sh)`。

**⑤ 构建 + 验证**：`docker compose up -d --build && docker compose ps`（各服务 healthy），跑 `pytest`。

**⑥ 回 vortex_common 跑依赖校验**：`(cd ../vortex_common && python scripts/sync-requirements.py)` 应 0 漂移。

## 3. 各仓差异（只列与通用步骤不同处）

| 仓 | 原 FROM | 需删除 | 端口 | 备注 |
|----|---------|--------|------|------|
| **vortex_data** | `vortex-data-base:latest` | `Dockerfile.base`、`requirements-base.txt`、`scripts/build-image.sh`（整段建底座逻辑都不要了） | 8765 | qlib 导出特性（自包含 .bin）本就不依赖 pyqlib，与迁移无关 |
| **vortex_qmt** | `vortex-data-base:latest` | `requirements-extra.txt` + Dockerfile 里装它那步、`scripts/build-image.sh`（fastapi/uvicorn/pydantic 已在 base） | 8767 | qmt-bridge 子模块仍单独 `pip install --no-deps external/qmt-bridge`，**不进 base** |
| **vortex_backtest** | `python:3.12-slim` | `apt-get build-essential`；`Dockerfile.qlib`、`Dockerfile.spike`、`scripts/build-qlib-image.sh`、`scripts/build-image.sh`；`pyproject.toml` 的 `pyqlib`(spike extra) | 8766（规范，避开 data 的 8765） | 引擎去 qlib 是本仓代码工作；backtrader 见 §7 |

> 端口以 [ADR-003](../adr/ADR-003-unified-config-architecture.md) + config/registry.yml 为准（内==外、不再重映射）：data 8765 / backtest 8766 / qmt 8767 / trader 8768。
> backtest 注意：组合部署里端口规范为 **8766**，由部署侧 `VORTEX_BACKTEST_PORT` 注入（不改代码默认值也行）。

## 4. 启动契约 `deploy/run.sh`

组合镜像的 `vortexctl <svc>` 会**优先执行本仓 `deploy/run.sh`**（各仓自描述如何启动自己），
不存在则回退到 `vortexctl` 的内置默认命令——所以**不加也能跑**，加了则启动逻辑归本仓掌握。
新建可执行的 `deploy/run.sh`：

```bash
# vortex_data
#!/usr/bin/env bash
set -euo pipefail
ROOT="${VORTEX_WORKSPACE:-/workspace}"
vortex-data --root "$ROOT" init
exec vortex-data --root "$ROOT" server start --host "${VORTEX_DATA_HOST:-0.0.0.0}" --port "${VORTEX_DATA_PORT:-8765}"
```

```bash
# vortex_qmt
#!/usr/bin/env bash
set -euo pipefail
export VORTEX_STATE="${VORTEX_STATE:-/state}"; mkdir -p "$VORTEX_STATE"
exec vortex-qmt serve
```

```bash
# vortex_backtest
#!/usr/bin/env bash
set -euo pipefail
export VORTEX_STATE="${VORTEX_STATE:-/state}"
export VORTEX_WORKSPACE="${VORTEX_WORKSPACE:-/workspace}"; mkdir -p "$VORTEX_STATE"
exec vortex-backtest serve
```

## 5. 接入组合镜像（整合部署）

**配置约定（标准做法，各仓基本无需改动）**：配置归各仓所有，在**仓根放 `.env.example`**
（模板：URL/端口/风控等默认值填好、token 等密钥**留空**），并在本仓 `.gitignore` 里**保留忽略 `.env`**
（真 `.env` 含密钥、不入库）。三仓现在本就是这样——确认 `.env.example` 在仓根、字段齐全即可。
部署侧 `pull-code.sh` 拉仓后会**首次从 `.env.example` 拷出 `.env`** 供你填密钥；`.env` 被忽略，
后续更新不覆盖你的编辑。

**部署流程**（owner 在 `vortex_common/deploy/` 内做）：

1. 各仓确认 ref → 写进 `deploy/versions.yml`。
2. `./pull-code.sh` 把各仓拉到 `deploy/repos/<svc>`（并首次从各仓 `.env.example` 种出 `.env`）。
3. 编辑 `deploy/repos/<svc>/.env` 填密钥/凭证。
4. `./build-release.sh` 造组合镜像 `vortex:<tag>`（各仓 `.env` 不进镜像）。
5. `docker compose up -d`（在 `deploy/` 内）起全部服务。

架构见 [ADR-001](../adr/ADR-001-deployment-architecture.md)；操作见
[deploy/CONFIG-AND-RUN.zh.md](../../deploy/CONFIG-AND-RUN.zh.md) 与 [deploy/README](../../deploy/README.md)。

## 6. 本地调试（不走发版流程，不切路径）

改完代码临时自测——**不提交、不打 tag、不走 git**：

- **单服务（最常用）**：在本仓直接 `docker compose up -d --build`。compose 用本仓 `Dockerfile`
  构建本地工作区代码（含未提交改动）成 `vortex-<svc>:latest` 并跑起来——一条命令、无需任何脚本。
- **全栈**：在 vortex_common 用本地源覆盖打整组合镜像：
  `VORTEX_DATA_SRC=../vortex_data deploy/build-release.sh --tag=dev`（其余服务用 `deploy/repos/<svc>`，先跑过 `pull-code.sh`）。

## 7. 维护与跨仓清理

- 改完依赖回 vortex_common 跑 `python scripts/sync-requirements.py` 确认 base 仍覆盖。
- **backtrader / qlib**：均已不在计划内，三仓 `pyproject.toml` 也不再声明，base 不含。
  若某仓将来要用，在其 pyproject 声明后回 vortex_common 把对应包加进
  `docker/requirements-base.txt`（注意 3.12 兼容性）并重建 base；`sync-requirements.py`
  会在出现新声明而 base 未覆盖时提示 `[缺失]`。
- 各仓 design/docs 里残留的 `vortex-data-base` / qlib / amd64 等旧表述可顺手更新，避免误导。
