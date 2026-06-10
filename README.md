# vortex_common

Vortex 各服务的**公共底座**：统一 Docker 基础镜像 `vortex-base`、**配置单一真值源 [`config/registry.yml`](config/registry.yml)**、`vortex` 总入口 CLI（cfg/image/run）、部署编排（[`deploy/`](deploy/)）。

## 🧭 系统导航

- **[系统架构总览](docs/architecture/overview.md)** —— 服务/端口、数据流、配置分层、构建发布全景（含架构图）。
- 配置真值源：[`config/registry.yml`](config/registry.yml)（改它 → `vortex cfg gen` 重生派生物）；[服务总表](docs/reference/services.md) · [系统拓扑](docs/reference/architecture.md)（均由 gen 生成）。
- 决策记录：[ADR-001 部署架构](docs/adr/ADR-001-deployment-architecture.md) · [ADR-002 workspace/state 变量](docs/adr/ADR-002-unified-workspace-env-vars.md) · [ADR-003 统一配置架构](docs/adr/ADR-003-unified-config-architecture.md)
- 运行：[部署与运行手册](deploy/CONFIG-AND-RUN.zh.md)。`vortex cfg ports` 看端口 · `vortex run up <svc>` 起单服务 · `vortex run deploy` 起全栈。
- 各服务仓：**vortex_data**(:8765) · **vortex_backtest**(:8766) · **vortex_qmt**(:8767) · **vortex_trader**(:8768 预留)，各仓 `README.md` + `CLAUDE.md`。

---

> 以下为 `vortex-base` 依赖底座说明（公共底座的一部分）。

各仓库（vortex_data / vortex_qmt / vortex_backtest …）需要的第三方库其实大量重叠
（pandas / pyarrow / fastapi / pydantic …）。与其每个仓库各维护一套依赖底座，不如
在这里整合**一个大家都 FROM 的 `vortex-base` 镜像**：依赖只下载一次、冻结进镜像，
下游应用镜像只叠加各自的代码，改代码秒级重建、零重下依赖。

---

## 目录结构

```
vortex_common/
├── docker/
│   ├── Dockerfile.base          # 统一基础镜像（python:3.12-slim + 全部共用依赖）
│   └── requirements-base.txt    # 共用第三方依赖清单（单一真值 / single source of truth）
└── scripts/
    ├── build-base-image.sh      # 构建 vortex-base 镜像（BuildKit + 离线兜底 + 多架构/推送）
    └── sync-requirements.py     # 依赖漂移校验：base 是否仍覆盖下游各仓库的声明
```

## 镜像里装了什么

底座 **`python:3.12-slim`**（三仓库 `requires-python` 均满足 `>=3.11`；vortex_backtest
本就跑在 3.12 上）。预装的共用依赖（取三仓库声明的**最高版本下限**）：

| 用途 | 包 | 谁在用 |
|------|----|--------|
| 数据/数值/存储 | `duckdb` `numpy` `pandas>=2.2` `pyarrow>=16` `pyyaml` `tushare` | data（pandas/pyarrow 兼 backtest） |
| Web 服务栈 | `fastapi>=0.128` `uvicorn[standard]` `pydantic>=2.7` | qmt / backtest |
| 测试 | `httpx` `pytest` | 三仓库 dev/test |
| 构建后端 | `hatchling`（data/qmt） `setuptools`（backtest） | —（放进 base，免应用层构建时联网下载） |

> **不放进 base 的**：`empyrical-reloaded` / `pytz`（仅 backtest 的 crosscheck 单测对拍用、缺失自动跳过，
> 按需在 backtest 本地装）。`qlib`/`backtrader` 已不在计划内、三仓也不再声明，故不纳入。
> base 全部依赖均为跨架构 wheel，**镜像 amd64/arm64 通用**。

依赖清单的唯一真值是 [`docker/requirements-base.txt`](docker/requirements-base.txt)。
**改依赖只改它**，再重建镜像。

## 构建镜像

```bash
scripts/build-base-image.sh                 # 构建 vortex-base:latest（日常）
scripts/build-base-image.sh --no-cache      # 不用缓存重建
scripts/build-base-image.sh --tag=v0.1.0    # 额外打版本 tag
scripts/build-base-image.sh --push          # 构建后推送（需先 docker login；可配 REGISTRY=ghcr.io/zyukyunman）
scripts/build-base-image.sh --platform=linux/amd64,linux/arm64 --push   # 多架构（buildx）
```

**离线友好**：默认底座 `python:3.12-slim`；当 Docker Hub 不可达且本地无该镜像时，
脚本自动复用「本地已有、含 Python 的镜像」作底座，完全不依赖 Hub。

## 下游仓库怎么用（迁移指引）

目标：各仓库的应用镜像把 `FROM` 改成 `vortex-base:latest`，并去掉自己重复维护的依赖底座。
共用依赖已在 base 内，应用层用 `pip install --no-deps .` 即可。先在本仓库构建好 base：

```bash
(cd ../vortex_common && scripts/build-base-image.sh)
```

### vortex_data
- `Dockerfile`：把 `ARG BASE_IMAGE=vortex-data-base:latest` 改成 `vortex-base:latest`，
  其余（`COPY` 代码 + `pip install --no-deps --no-build-isolation .`）不变。
- 可删除：本仓库的 `Dockerfile.base`、`requirements-base.txt`，以及整个 `scripts/build-image.sh`
  （依赖底座已上移到 common；本地构建/运行统一用 `docker compose up -d --build`，见 [通用迁移指南](docs/migration/README.md)）。

### vortex_qmt
- `Dockerfile`：`FROM vortex-data-base:latest` → `FROM vortex-base:latest`。
- 删除安装 `requirements-extra.txt` 的那一步——`fastapi/uvicorn/pydantic` 现已在 base 内。
  `qmt-bridge` 子模块仍按原样单独安装（`pip install --no-deps external/qmt-bridge`）。

### vortex_backtest
- `Dockerfile`：`FROM python:3.12-slim` → `FROM vortex-base:latest`；去掉
  `apt-get install build-essential`（运行期依赖均为预编译 wheel）；安装改为
  `pip install --no-deps .`。**与 data/qmt 完全同构、原生架构，无需 amd64。**
- qlib 已不在计划内：删除 `Dockerfile.qlib` / `Dockerfile.spike` / `scripts/build-qlib-image.sh`，
  并从 `pyproject.toml` 移除 `pyqlib`。详见 [通用迁移指南](docs/migration/README.md)。

> 注：本次只在 common 落地基础镜像与脚本，**未改动下游仓库**。上面是后续把各仓库切到
> `vortex-base` 的具体改法，可逐个迁移、逐个验证。

## 维护：依赖漂移校验

下游仓库以后加/改依赖时，用本脚本检查 base 是否仍然覆盖：

```bash
python scripts/sync-requirements.py            # 扫 ../vortex_{data,qmt,backtest} 并比对
python scripts/sync-requirements.py --quiet    # 仅在有「必须修」的漂移时输出（适合 CI）
```

- `[缺失]`/`[过低]`：某仓库需要的包 base 没装、或 base 下限低于仓库要求 → 改
  `requirements-base.txt` 后重建镜像（退出码 1）。
- `[豁免]`：`pyqlib` / `empyrical-reloaded` / `pytz` 有意不放 base，仅提示。
- 全部覆盖则退出码 0。

需要 Python 3.11+（`tomllib`；3.10 可 `pip install tomli`）。
