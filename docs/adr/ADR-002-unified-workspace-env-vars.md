# ADR-002: 统一 Workspace 与 State 环境变量

**状态：** Accepted
**日期：** 2026-06-07
**决策人：** @zyukyunman（owner）
**相关：** ADR-001（部署架构）、vortex_data/CLAUDE.md §配置分四层

---

## 背景（Context）

Vortex 各仓库在代码中各自定义了不同名字的环境变量来指向"数据工作区"和"服务状态目录"，
导致：

- compose 里的 `environment:` 块需要维护多套名字，容易写错
- 新仓库不知道读哪个变量，凭感觉起名（例如 backtest 里出现了硬编码的 macOS 路径）
- Dockerfile 已经写了 `ENV VORTEX_WORKSPACE=/workspace` 和 `ENV VORTEX_STATE=/state`，
  但各服务代码没有统一读取它们——Dockerfile 里的 ENV 实际上是死的

### 现状诊断：各服务读的变量名

| 服务 | 代码读的变量 | 实际含义 | 问题 |
|------|------------|---------|------|
| vortex_data `cli.py` | `VORTEX_DATA_ROOT` | 数据工作区根目录 | 名字服务特定，Dockerfile ENV 没用上 |
| vortex_data `.env.example` | `VORTEX_DATA_WORKSPACE` | 宿主机挂载路径（含义不同于上面！） | 同一概念两个变量名 |
| vortex_backtest `replay_engine.py` | `VORTEX_DATA_WORKSPACE` | 读 data 的工作区 | 和 data 自己的 WORKSPACE 概念混淆 |
| vortex_backtest `data_adapter.py` | **硬编码** `/Users/zyukyunman/Documents/vortex_workspace` | 同上 | 严重：macOS 路径写死进代码 |
| vortex_backtest `examples/*.py` | **硬编码** macOS 路径（`run_30_day_http_sample.py`、`quickstart.py` 共 3 处） | 同上 | 同样会让别人环境崩，需一并清理 |
| vortex_backtest `benchmark.py` | `VORTEX_INDEX_DATA_DIR` | 指数目录（= `workspace/data/index_daily`） | 可由 `VORTEX_WORKSPACE` 派生，不必单列 |
| vortex_backtest `app.py` | `VORTEX_BACKTEST_STATE_DIR` | 服务状态目录 | 服务特定名 |
| vortex_qmt `config.py` | `VORTEX_QMT_STATE_DIR` | 服务状态目录 | 服务特定名 |

### Dockerfile 已定义但未落地

`vortex_common/deploy/Dockerfile` 已经写了：

```dockerfile
ENV VORTEX_WORKSPACE=/workspace \
    VORTEX_STATE=/state
```

这是正确方向，但各服务代码都没读这两个标准变量——它们只存在于 Dockerfile
ENV 层，没有形成规范。

---

## 决策（Decision）

**以 Dockerfile 里已存在的 `VORTEX_WORKSPACE` 和 `VORTEX_STATE` 为唯一标准，
各服务代码统一读这两个变量，废弃各自的特化名字。**

### 两个核心概念（容器内路径固定）

```
/workspace   ← VORTEX_WORKSPACE（共享数据工作区）
/state       ← VORTEX_STATE    （本服务运行状态）
```

| 变量 | 容器内默认值 | 含义 | 谁写 | 谁读 |
|------|------------|------|------|------|
| `VORTEX_WORKSPACE` | `/workspace` | 市场数据 Parquet + 配置 profiles | vortex_data（读写） | vortex_backtest, vortex_trader（只读） |
| `VORTEX_STATE` | `/state` | 本服务的 SQLite、日志、任务队列 | 各服务自己（读写） | 本服务自己 |

> **vortex_data 的特殊性**：data 的状态（control.db、logs）放在 workspace 内部
> （`/workspace/state/`），不需要独立的 `/state` 卷。`VORTEX_STATE` 对 data 不适用，
> 跳过即可。

---

## 各服务代码迁移清单

### vortex_data

**`vortex_data/cli.py`**（`_default_root` 函数）

```python
# 当前
return Path(raw or os.environ.get("VORTEX_DATA_ROOT", "./workspace")).expanduser().resolve()

# 改为（读标准变量，保留旧名作兼容 fallback，30天后删）
return Path(
    raw
    or os.environ.get("VORTEX_WORKSPACE")
    or os.environ.get("VORTEX_DATA_ROOT")  # deprecated，兼容过渡
    or "./workspace"
).expanduser().resolve()
```

**`.env.example`**：删除 `VORTEX_DATA_ROOT` 和 `VORTEX_DATA_WORKSPACE` 条目（它们是宿主机挂载
路径的配置，搬到 compose volumes 的 host-path 变量，见下节）。

---

### vortex_backtest

**`vortex_backtest/data_adapter.py`**（最紧急，有硬编码路径）

```python
# 当前 ——  必须修，会让别人环境直接崩
DEFAULT_WORKSPACE = Path("/Users/zyukyunman/Documents/vortex_workspace")

# 改为
import os
DEFAULT_WORKSPACE = Path(os.environ.get("VORTEX_WORKSPACE", "/workspace"))
```

**`vortex_backtest/replay_engine.py`**

```python
# 当前
workspace = Path(os.getenv("VORTEX_DATA_WORKSPACE", str(DEFAULT_WORKSPACE)))

# 改为（去掉旧变量名）
workspace = Path(os.getenv("VORTEX_WORKSPACE", str(DEFAULT_WORKSPACE)))
```

**`vortex_backtest/app.py`**（`default_state_dir`）

```python
# 当前
env_value = os.getenv("VORTEX_BACKTEST_STATE_DIR")

# 改为（标准变量优先，旧名兼容过渡）
env_value = os.getenv("VORTEX_STATE") or os.getenv("VORTEX_BACKTEST_STATE_DIR")
```

**`vortex_backtest/examples/*.py`**（`run_30_day_http_sample.py`、`quickstart.py`，共 3 处硬编码 macOS 路径）

```python
# 当前
DEFAULT_WORKSPACE = Path("/Users/zyukyunman/Documents/vortex_workspace")
DEFAULT_WS = "/Users/zyukyunman/Documents/vortex/vortex_data/workspace"

# 改为
DEFAULT_WORKSPACE = Path(os.environ.get("VORTEX_WORKSPACE", "/workspace"))
```

**`vortex_backtest/benchmark.py`**（`index_data_dir`）

```python
# 当前：单列 VORTEX_INDEX_DATA_DIR 指向 workspace/data/index_daily
value = os.getenv("VORTEX_INDEX_DATA_DIR")

# 改为：由标准 VORTEX_WORKSPACE 派生（保留旧名兼容过渡）
ws = os.getenv("VORTEX_WORKSPACE")
value = os.getenv("VORTEX_INDEX_DATA_DIR") or (f"{ws}/data/index_daily" if ws else None)
```

---

### vortex_qmt

**`vortex_qmt/config.py`**

```python
# 当前
state_dir=Path(os.getenv("VORTEX_QMT_STATE_DIR", "./state")).expanduser(),

# 改为（标准变量优先，旧名兼容过渡）
state_dir=Path(
    os.getenv("VORTEX_STATE") or os.getenv("VORTEX_QMT_STATE_DIR") or "./state"
).expanduser(),
```

---

### vortex_trader（未来）

新仓库直接读 `VORTEX_WORKSPACE` 和 `VORTEX_STATE`，不需要引入服务特定变量名。

### 不在本 ADR 范围

- `VORTEX_BACKTEST_DOCS_ROOT`（backtest 文档站资源根）：与数据/状态无关，属文档资源路径，保持服务特定，不纳入本次统一。

---

## compose 更新

### 组合部署（vortex_common/deploy/docker-compose.yml）

`environment:` 块统一使用标准变量名（当前已有一部分，下面是对齐后的完整版）：

```yaml
services:
  vortex-data:
    environment:
      VORTEX_WORKSPACE: /workspace    # 标准名（替换当前的 VORTEX_DATA_ROOT 行）
      # VORTEX_STATE 对 data 不适用，state 在 /workspace/state/ 内部
    volumes:
      - vortex-workspace:/workspace

  vortex-qmt:
    environment:
      VORTEX_STATE: /state            # 标准名（替换当前的 VORTEX_QMT_STATE_DIR 行）
    volumes:
      - vortex-qmt-state:/state

  vortex-backtest:
    environment:
      VORTEX_WORKSPACE: /workspace    # 标准名（替换当前的 VORTEX_DATA_WORKSPACE 行）
      VORTEX_STATE: /state            # 标准名（替换当前的 VORTEX_BACKTEST_STATE_DIR 行）
    volumes:
      - vortex-workspace:/workspace:ro
      - vortex-backtest-state:/state

  vortex-trader:                      # 预留，直接用标准名
    environment:
      VORTEX_WORKSPACE: /workspace
      VORTEX_STATE: /state
    volumes:
      - vortex-workspace:/workspace:ro
      - vortex-trader-state:/state
```

> 变更量极小：只改 `environment:` 里的 key 名，values 和 volumes 不变。

---

### 单仓开发模式（各仓 docker-compose.yml）

单仓 dev 的核心问题是：**宿主机挂载路径不是容器内路径**，不应该用同一个变量名混用。

引入两个**宿主机侧变量**（只在 `.env` 和 compose volumes 里用，不进服务代码）：

| 变量 | 用途 | 典型值 |
|------|------|-------|
| `VORTEX_WORKSPACE_MOUNT` | 宿主机侧 workspace 目录（volume source） | `./workspace`（data 单仓）/ `../vortex_data/workspace`（backtest 单仓） |
| `VORTEX_STATE_MOUNT` | 宿主机侧 state 目录（volume source） | `./state` |

**vortex_data/docker-compose.yml**：

```yaml
environment:
  VORTEX_WORKSPACE: /workspace    # 容器内固定路径，标准名
  # 删除 VORTEX_DATA_ROOT、VORTEX_DATA_WORKSPACE
volumes:
  - ${VORTEX_WORKSPACE_MOUNT:-./workspace}:/workspace
```

**vortex_backtest/docker-compose.yml**：

```yaml
environment:
  VORTEX_WORKSPACE: /workspace    # 容器内固定路径，标准名
  VORTEX_STATE: /state
  # 删除 VORTEX_BACKTEST_WORKSPACE、VORTEX_BACKTEST_STATE_DIR
volumes:
  - ${VORTEX_WORKSPACE_MOUNT:-../vortex_data/workspace}:/workspace:ro
  - ${VORTEX_STATE_MOUNT:-./state}:/state
```

**vortex_qmt/docker-compose.yml**：

```yaml
environment:
  VORTEX_STATE: /state            # 标准名，替换 VORTEX_QMT_STATE_DIR
  # 其他保持不变
volumes:
  - ${VORTEX_STATE_MOUNT:-./state}:/state
```

---

### 各仓 .env.example 更新

**删除**以下旧变量（它们是容器内路径，不该出现在 .env 里）：
- `VORTEX_DATA_ROOT`
- `VORTEX_DATA_WORKSPACE`
- `VORTEX_BACKTEST_WORKSPACE`
- `VORTEX_BACKTEST_STATE_DIR`
- `VORTEX_QMT_STATE_DIR`

**新增**宿主机挂载路径变量（仅 data 和 backtest 单仓有意义）：

```bash
# vortex_data/.env.example 新增：
# workspace 在宿主机的挂载路径（单仓开发用）。
# 组合部署时由 vortex_common/deploy/docker-compose.yml 的 named volume 覆盖，无需填。
VORTEX_WORKSPACE_MOUNT=./workspace

# vortex_backtest/.env.example 新增：
# 单仓开发时，指向 vortex_data 的 workspace 目录（宿主机路径）。
# 组合部署时由 named volume vortex-workspace 覆盖，无需填。
VORTEX_WORKSPACE_MOUNT=../vortex_data/workspace
VORTEX_STATE_MOUNT=./state
```

---

## 变更范围总结

| 仓库 | 代码改动 | compose 改动 | .env.example 改动 |
|------|---------|------------|-----------------|
| vortex_data | `cli.py` 1处（读变量名） | `environment:` key 改名 | 删旧变量，加 `VORTEX_WORKSPACE_MOUNT` |
| vortex_backtest | `data_adapter.py`、`replay_engine.py`、`app.py`、`benchmark.py` 各1处 + `examples/` 3处硬编码 | `environment:` key 改名，volumes host 改变量名 | 删旧变量，加两个 `_MOUNT` 变量 |
| vortex_qmt | `config.py` 1处 | `environment:` key 改名 | 删旧变量，加 `VORTEX_STATE_MOUNT` |
| vortex_common | 无代码改动 | deploy/docker-compose.yml `environment:` key 改名 | 无 |

**影响评估：Low**。都是重命名，逻辑不变；兼容 fallback 保证切换期间老变量仍可用。

---

## 迁移顺序（推荐）

1. **先改 vortex_backtest `data_adapter.py`（紧急）**：消除硬编码 macOS 路径
2. 更新 vortex_common deploy/docker-compose.yml 的 environment key
3. 各仓代码改读标准变量（加 fallback 兼容旧名）
4. 各仓单仓 docker-compose.yml 和 .env.example 更新
5. 30天后删除 fallback 兼容代码和旧变量

---

## 变量名命名约定（供未来仓库参考）

```
VORTEX_WORKSPACE      容器内数据工作区路径（= /workspace，标准，各服务读）
VORTEX_STATE          容器内服务状态路径（= /state，标准，各服务读）
VORTEX_<SVC>_TOKEN    各服务的写接口鉴权 token（服务特定，.env 配置）
VORTEX_<SVC>_PORT     各服务监听端口（服务特定，.env 配置）
VORTEX_<SVC>_HOST     各服务监听地址（服务特定，.env 配置）
*_MOUNT               宿主机侧 volume 挂载源路径（仅 .env + compose volumes，不进服务代码）
```

新仓库在代码里**只读 `VORTEX_WORKSPACE` 和 `VORTEX_STATE`**，不引入新的服务特定 workspace/state 变量。
