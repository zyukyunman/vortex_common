# Vortex 配置基石（vortex cfg + registry）实施计划 — Phase 0

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 vortex_common 建立配置单一真值源 `registry.yml` 与生成/校验工具 `vortex cfg`，产出 `vortex.generated.env` / `versions.yml` / 文档表 / 架构图，作为后续全仓整改的基石。

**Architecture:** `registry.yml`（手改唯一真值源）→ Python 包 `vortextool`（registry 解析 + generate + check）→ `bin/vortex` CLI 入口（cfg 组）。生成物带 `# DO NOT EDIT` 头、`vortex cfg check` 把"生成物最新 + 不变量"挂闸门。本阶段只交付 `cfg` 组；`image`/`run` 组与 per-repo 整改是后续 Phase。

**Tech Stack:** Python 3.12 + PyYAML（仅开发/运维机用，不进镜像构建路径）、pytest、uv（与其它仓一致）。

> 本计划所在仓 = `vortex_common`，绝对路径根 `/Users/zyukyunman/Documents/vortex/vortex_common`。
> 设计依据 spec：`/Users/zyukyunman/Documents/vortex/vortex_common/docs/superpowers/specs/2026-06-09-vortex-config-architecture-design.md`。

---

## 总路线图（5 个 Phase，本计划只覆盖 Phase 0）

| Phase | 范围 | 何时细化成计划 |
|------|------|--------------|
| **0（本计划）** | `registry.yml` + `vortextool`（registry/generate/check）+ `bin/vortex cfg` + 生成物 + ADR-003 | 现在 |
| 1 | `vortex` 的 `image`（base/pull/build/push 包脚本）+ `run`（up/down/logs/deploy）组；common `deploy/docker-compose.yml`/`Dockerfile`(遍历)/`vortexctl`(source 生成 env、删 legacy 导出) 对齐；`pull-code` 加拷 env | foundation 落地后 |
| 2 | 各仓配置整改：data/qmt/backtest 的 `.env`/`.env.example`/`docker-compose.yml`/`Dockerfile`/`deploy/run.sh`/`CLAUDE.md`/文件头更正 | foundation+CLI 落地后 |
| 3 | 文档整改：common port 表、各仓 README/docs、in-app 文档站（`data/service/docs_page.py`、`backtest/web/guide.html`）、trader 全套 + 拓扑图、顶层导航 + overview + 4 张架构图 | Phase 2 后 |
| 4 | 测试硬编码路径清理、`vortex cfg check` 挂 pre-commit/CI、清除裸 `docker compose up`、§12 全量验收门禁 | Phase 3 后 |

> 端口 renumber 不是独立步骤：registry 从一开始就用新号（8765/8766/8767/8768），compose 在 Phase 2 改成 `${VORTEX_<SVC>_PORT}` 取值后，端口值唯一来自 registry —— 改 registry 即原子生效。

---

## 文件结构（Phase 0 创建/修改）

| 文件 | 职责 |
|------|------|
| `config/registry.yml` | 单一真值源（创建） |
| `pyproject.toml` | vortextool 包 + 依赖（pyyaml）+ 开发依赖（pytest）（创建） |
| `vortextool/__init__.py` | 包标识（创建） |
| `vortextool/registry.py` | 加载 + 校验 registry.yml → 内存模型（创建） |
| `vortextool/generate.py` | 从模型渲染 4 个生成物的字符串（创建） |
| `vortextool/check.py` | 不变量校验（端口/生成物最新/.env.example 干净）（创建） |
| `vortextool/cli.py` | 子命令分派（cfg gen/check/list/ports）（创建） |
| `bin/vortex` | CLI 薄入口，调用 `vortextool.cli:main`（创建） |
| `tests/test_registry.py` `tests/test_generate.py` `tests/test_check.py` | 单测（创建） |
| `config/vortex.generated.env` | 生成物（由 gen 产出并提交） |
| `deploy/versions.yml` | 改由 gen 产出（覆盖现有手写版，保持 awk 结构） |
| `docs/reference/services.md` `docs/reference/architecture.md` | 生成物 |
| `docs/adr/ADR-003-unified-config-architecture.md` | 决策记录（创建） |

---

## Task 1: 包脚手架（uv + pyproject + 空包）

**Files:**
- Create: `pyproject.toml`
- Create: `vortextool/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: 创建 pyproject.toml**

```toml
[project]
name = "vortextool"
version = "0.1.0"
description = "Vortex 配置真值源生成/校验工具（registry.yml → env/versions/docs）"
requires-python = ">=3.11"
dependencies = ["pyyaml>=6"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["vortextool"]
```

- [ ] **Step 2: 创建空包标识**

`vortextool/__init__.py`:
```python
"""Vortex 配置真值源工具：registry.yml → 生成/校验。"""
__all__ = []
```

`tests/__init__.py`: （空文件）

- [ ] **Step 3: 同步环境并确认 pytest 可跑**

Run: `cd /Users/zyukyunman/Documents/vortex/vortex_common && uv sync --extra dev && uv run pytest -q`
Expected: pytest 启动，收集 0 项（no tests ran），退出码 0 或 5（无测试）。确认工具链就绪。

- [ ] **Step 4: Commit**

```bash
cd /Users/zyukyunman/Documents/vortex/vortex_common
git add pyproject.toml vortextool/__init__.py tests/__init__.py
git commit -m "chore(vortextool): 包脚手架（uv + pyproject + pytest）

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: registry.yml 真值源 + 加载/校验模型

**Files:**
- Create: `config/registry.yml`
- Create: `vortextool/registry.py`
- Test: `tests/test_registry.py`

- [ ] **Step 1: 写 registry.yml（真值源）**

`config/registry.yml`:
```yaml
# Vortex 配置单一真值源。手改这里 → `vortex cfg gen` 重生全部派生物。
# 容器内路径固定（ADR-002）；宿主机根为相对 HOME 约定，由 `vortex run` 运行时解析。
common:
  tz: Asia/Shanghai
  default_bind_addr: "127.0.0.1"
  network: vortex-net
  image:
    base: vortex-base
    app: vortex
  workspace_host_root: "${HOME}/vortex/workspace"
  state_host_root: "${HOME}/vortex/state"
  container:
    workspace: /workspace
    state: /state

services:
  - name: vortex_data
    port: 8765
    role: 数据底座
    health: /api/health
    repo: https://github.com/zyukyunman/vortex_data.git
    ref: main
  - name: vortex_backtest
    port: 8766
    role: 回测
    health: /health
    repo: https://github.com/zyukyunman/vortex_backtest.git
    ref: main
  - name: vortex_qmt
    port: 8767
    role: 实盘
    health: /health
    repo: https://github.com/zyukyunman/vortex_qmt.git
    ref: main
    submodules: true
  - name: vortex_trader
    port: 8768
    role: 预留
    health: /health
    repo: https://github.com/zyukyunman/vortex_trader.git
    ref: null
```

- [ ] **Step 2: 写失败测试 tests/test_registry.py**

```python
from pathlib import Path
import pytest
from vortextool.registry import load_registry, RegistryError

REPO = Path(__file__).resolve().parent.parent
REAL = REPO / "config" / "registry.yml"


def test_loads_real_registry():
    reg = load_registry(REAL)
    names = [s.name for s in reg.services]
    assert names == ["vortex_data", "vortex_backtest", "vortex_qmt", "vortex_trader"]
    assert reg.service("vortex_data").port == 8765
    assert reg.service("vortex_qmt").submodules is True
    assert reg.service("vortex_trader").ref is None      # 预留 = 空
    assert reg.common.tz == "Asia/Shanghai"
    assert reg.common.network == "vortex-net"


def test_rejects_duplicate_ports(tmp_path):
    p = tmp_path / "r.yml"
    p.write_text(
        "common: {tz: X, default_bind_addr: '127.0.0.1', network: n, "
        "image: {base: b, app: a}, workspace_host_root: w, state_host_root: s, "
        "container: {workspace: /workspace, state: /state}}\n"
        "services:\n"
        "  - {name: a, port: 8765, role: r, health: /h, repo: u, ref: main}\n"
        "  - {name: b, port: 8765, role: r, health: /h, repo: u, ref: main}\n",
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="重复端口|duplicate"):
        load_registry(p)


def test_rejects_unsorted_ports(tmp_path):
    p = tmp_path / "r.yml"
    p.write_text(
        "common: {tz: X, default_bind_addr: '127.0.0.1', network: n, "
        "image: {base: b, app: a}, workspace_host_root: w, state_host_root: s, "
        "container: {workspace: /workspace, state: /state}}\n"
        "services:\n"
        "  - {name: a, port: 8766, role: r, health: /h, repo: u, ref: main}\n"
        "  - {name: b, port: 8765, role: r, health: /h, repo: u, ref: main}\n",
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="升序|sorted"):
        load_registry(p)
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd /Users/zyukyunman/Documents/vortex/vortex_common && uv run pytest tests/test_registry.py -v`
Expected: FAIL（`ModuleNotFoundError: vortextool.registry`）。

- [ ] **Step 4: 实现 vortextool/registry.py**

```python
"""加载并校验 registry.yml 为内存模型。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class RegistryError(ValueError):
    """registry.yml 校验失败。"""


@dataclass(frozen=True)
class Service:
    name: str
    port: int
    role: str
    health: str
    repo: str
    ref: str | None
    submodules: bool = False


@dataclass(frozen=True)
class Common:
    tz: str
    default_bind_addr: str
    network: str
    image_base: str
    image_app: str
    workspace_host_root: str
    state_host_root: str
    container_workspace: str
    container_state: str


@dataclass(frozen=True)
class Registry:
    common: Common
    services: tuple[Service, ...]

    def service(self, name: str) -> Service:
        for s in self.services:
            if s.name == name:
                return s
        raise KeyError(name)


def load_registry(path: Path) -> Registry:
    data: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    c = data["common"]
    common = Common(
        tz=c["tz"],
        default_bind_addr=str(c["default_bind_addr"]),
        network=c["network"],
        image_base=c["image"]["base"],
        image_app=c["image"]["app"],
        workspace_host_root=c["workspace_host_root"],
        state_host_root=c["state_host_root"],
        container_workspace=c["container"]["workspace"],
        container_state=c["container"]["state"],
    )
    services = tuple(
        Service(
            name=s["name"],
            port=int(s["port"]),
            role=s["role"],
            health=s["health"],
            repo=s["repo"],
            ref=(s.get("ref") or None),
            submodules=bool(s.get("submodules", False)),
        )
        for s in data["services"]
    )
    _validate(services)
    return Registry(common=common, services=services)


def _validate(services: tuple[Service, ...]) -> None:
    ports = [s.port for s in services]
    if len(set(ports)) != len(ports):
        raise RegistryError(f"重复端口 (duplicate ports): {ports}")
    if ports != sorted(ports):
        raise RegistryError(f"端口未升序 (ports not sorted): {ports}")
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd /Users/zyukyunman/Documents/vortex/vortex_common && uv run pytest tests/test_registry.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
cd /Users/zyukyunman/Documents/vortex/vortex_common
git add config/registry.yml vortextool/registry.py tests/test_registry.py
git commit -m "feat(vortextool): registry.yml 真值源 + 加载/校验模型

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: 生成 vortex.generated.env

**Files:**
- Create: `vortextool/generate.py`
- Test: `tests/test_generate.py`

- [ ] **Step 1: 写失败测试（追加到 tests/test_generate.py）**

```python
from pathlib import Path
from vortextool.registry import load_registry
from vortextool.generate import render_env

REPO = Path(__file__).resolve().parent.parent
REG = load_registry(REPO / "config" / "registry.yml")


def test_env_has_ports_and_bind_for_each_service():
    env = render_env(REG)
    assert "VORTEX_DATA_PORT=8765" in env
    assert "VORTEX_BACKTEST_PORT=8766" in env
    assert "VORTEX_QMT_PORT=8767" in env
    assert "VORTEX_TRADER_PORT=8768" in env
    # 每服务一个绑定地址，默认来自 common.default_bind_addr
    assert "VORTEX_DATA_BIND_ADDR=127.0.0.1" in env
    assert "VORTEX_QMT_BIND_ADDR=127.0.0.1" in env


def test_env_has_common_scalars_and_donotedit_header():
    env = render_env(REG)
    assert env.splitlines()[0].startswith("# DO NOT EDIT")
    assert "TZ=Asia/Shanghai" in env
    assert "VORTEX_NETWORK=vortex-net" in env
    assert "VORTEX_IMAGE_BASE=vortex-base" in env
    assert "VORTEX_IMAGE_APP=vortex" in env


def test_env_excludes_host_var_and_abs_paths():
    env = render_env(REG)
    assert "_HOST=" not in env          # 容器监听是不变量，不进生成 env（spec §2.5）
    assert "/Users/" not in env         # 机器无关：不烤宿主机绝对路径（spec §2.6）
    assert "HOST_ROOT" not in env       # 宿主机根由 vortex run 运行时解析
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/zyukyunman/Documents/vortex/vortex_common && uv run pytest tests/test_generate.py -v`
Expected: FAIL（`ModuleNotFoundError: vortextool.generate`）。

- [ ] **Step 3: 实现 render_env（vortextool/generate.py）**

```python
"""从 Registry 模型渲染各生成物字符串。"""
from __future__ import annotations

from .registry import Registry

HEADER = "# DO NOT EDIT — generated by `vortex cfg gen` from config/registry.yml"


def render_env(reg: Registry) -> str:
    c = reg.common
    lines = [
        HEADER,
        f"TZ={c.tz}",
        f"VORTEX_NETWORK={c.network}",
        f"VORTEX_IMAGE_BASE={c.image_base}",
        f"VORTEX_IMAGE_APP={c.image_app}",
        "",
    ]
    for s in reg.services:
        up = s.name.removeprefix("vortex_").upper()
        lines.append(f"VORTEX_{up}_PORT={s.port}")
        lines.append(f"VORTEX_{up}_BIND_ADDR={c.default_bind_addr}")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/zyukyunman/Documents/vortex/vortex_common && uv run pytest tests/test_generate.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/zyukyunman/Documents/vortex/vortex_common
git add vortextool/generate.py tests/test_generate.py
git commit -m "feat(vortextool): 生成 vortex.generated.env（端口/绑定/TZ/网络，无 _HOST/无绝对路径）

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: 生成 versions.yml（窄字段 + 空 ref 裸空，awk 兼容）

**Files:**
- Modify: `vortextool/generate.py`
- Test: `tests/test_generate.py`（追加）

- [ ] **Step 1: 写失败测试（追加到 tests/test_generate.py）**

```python
from vortextool.generate import render_versions
import re


def test_versions_narrow_fields_and_submodules():
    out = render_versions(REG)
    assert out.splitlines()[0].startswith("# DO NOT EDIT")
    assert "- name: vortex_data" in out
    assert "repo: https://github.com/zyukyunman/vortex_data.git" in out
    assert "ref: main" in out
    assert "submodules: true" in out          # 仅 qmt
    # 窄字段：不泄漏 port/role/health 进被 awk 扫描的文件
    assert "port:" not in out
    assert "role:" not in out
    assert "health:" not in out


def test_versions_empty_ref_is_bare_not_quoted():
    out = render_versions(REG)
    # trader 预留：必须是裸空 `ref:`，绝不能 `ref: ""`（awk 不剥引号会去 clone 名为 "" 的分支）
    assert re.search(r"name: vortex_trader[\s\S]*?\n\s*ref:\s*\n", out + "\n")
    assert 'ref: ""' not in out
    assert "ref: ''" not in out
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/zyukyunman/Documents/vortex/vortex_common && uv run pytest tests/test_generate.py -k versions -v`
Expected: FAIL（`cannot import name 'render_versions'`）。

- [ ] **Step 3: 实现 render_versions（追加到 vortextool/generate.py）**

```python
def render_versions(reg: Registry) -> str:
    lines = [
        HEADER,
        "# pull-code.sh / build-release.sh 用 awk 解析本文件，字段固定 name/repo/ref/submodules。",
        "services:",
    ]
    for s in reg.services:
        lines.append(f"  - name: {s.name}")
        lines.append(f"    repo: {s.repo}")
        # 空 ref 投影为裸空（不带引号）：预留服务，构建/拉取时跳过。
        lines.append(f"    ref: {s.ref}" if s.ref else "    ref:")
        if s.submodules:
            lines.append("    submodules: true")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/zyukyunman/Documents/vortex/vortex_common && uv run pytest tests/test_generate.py -k versions -v`
Expected: 2 passed.

- [ ] **Step 5: 用真实 awk 解析器验证兼容（关键回归）**

Run:
```bash
cd /Users/zyukyunman/Documents/vortex/vortex_common
uv run python -c "from pathlib import Path; from vortextool.registry import load_registry; from vortextool.generate import render_versions; Path('/tmp/_v.yml').write_text(render_versions(load_registry(Path('config/registry.yml'))))"
awk '
  function flush(){ if(name!=""){ printf "%s|%s|%s|%s\n", name, repo, ref, subm } name="";repo="";ref="";subm="" }
  /^[[:space:]]*#/        { next }
  /^[[:space:]]*-[[:space:]]*name:/ { flush(); name=$0; sub(/^[[:space:]]*-[[:space:]]*name:[[:space:]]*/,"",name); gsub(/[[:space:]\r]/,"",name); next }
  /^[[:space:]]*repo:/    { repo=$0; sub(/^[[:space:]]*repo:[[:space:]]*/,"",repo); gsub(/[[:space:]\r]/,"",repo); next }
  /^[[:space:]]*ref:/     { ref=$0;  sub(/^[[:space:]]*ref:[[:space:]]*/,"",ref);   gsub(/[[:space:]\r]/,"",ref);  next }
  /^[[:space:]]*submodules:/ { subm=$0; sub(/^[[:space:]]*submodules:[[:space:]]*/,"",subm); gsub(/[[:space:]\r]/,"",subm); next }
  END{ flush() }
' /tmp/_v.yml
```
Expected（trader 的 ref 字段为空 → 第 3 段空）：
```
vortex_data|https://github.com/zyukyunman/vortex_data.git|main|
vortex_backtest|https://github.com/zyukyunman/vortex_backtest.git|main|
vortex_qmt|https://github.com/zyukyunman/vortex_qmt.git|main|true
vortex_trader|https://github.com/zyukyunman/vortex_trader.git||
```
确认 `vortex_trader` 行 ref 段为空（pull-code 的 `[ -z "$ref" ]` 会判真 → 跳过），而非 `""`。

- [ ] **Step 6: Commit**

```bash
cd /Users/zyukyunman/Documents/vortex/vortex_common
git add vortextool/generate.py tests/test_generate.py
git commit -m "feat(vortextool): 生成 versions.yml（窄字段 + 空 ref 裸空，验证 awk 兼容）

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: 生成 services.md + architecture.md（文档表 + 拓扑图）

**Files:**
- Modify: `vortextool/generate.py`
- Test: `tests/test_generate.py`（追加）

- [ ] **Step 1: 写失败测试（追加）**

```python
from vortextool.generate import render_services_md, render_architecture_md


def test_services_md_table_has_all_services():
    md = render_services_md(REG)
    assert md.splitlines()[0].startswith("# ")        # 标题
    for name, port in [("vortex_data", "8765"), ("vortex_backtest", "8766"),
                       ("vortex_qmt", "8767"), ("vortex_trader", "8768")]:
        assert name in md and port in md
    assert "数据底座" in md and "预留" in md


def test_architecture_md_is_mermaid_with_nodes():
    md = render_architecture_md(REG)
    assert "```mermaid" in md
    assert "vortex-data" in md and ":8765" in md
    assert "vortex-trader" in md and ":8768" in md
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/zyukyunman/Documents/vortex/vortex_common && uv run pytest tests/test_generate.py -k "services_md or architecture" -v`
Expected: FAIL（import 错误）。

- [ ] **Step 3: 实现两个渲染函数（追加到 vortextool/generate.py）**

```python
def render_services_md(reg: Registry) -> str:
    lines = [
        "# 服务总表（生成）",
        "",
        HEADER,
        "",
        "| 服务 | 端口（内外一致） | 角色 | 健康检查 | 仓库 |",
        "|------|------|------|---------|------|",
    ]
    for s in reg.services:
        lines.append(f"| {s.name} | {s.port} | {s.role} | `{s.health}` | {s.repo} |")
    return "\n".join(lines) + "\n"


def render_architecture_md(reg: Registry) -> str:
    nodes = "\n".join(
        f'    {s.name.replace("vortex_", "")}["{s.name.replace("_", "-")} :{s.port}<br/>{s.role}"]'
        for s in reg.services
    )
    return (
        "# 系统拓扑（生成）\n\n"
        f"{HEADER}\n\n"
        "```mermaid\n"
        "graph TB\n"
        f'  subgraph host["宿主机 · {reg.common.network}"]\n'
        f"{nodes}\n"
        "  end\n"
        '  qmt -- QMTClient --> win["Windows · qmt-bridge :8000"]\n'
        "```\n"
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/zyukyunman/Documents/vortex/vortex_common && uv run pytest tests/test_generate.py -k "services_md or architecture" -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/zyukyunman/Documents/vortex/vortex_common
git add vortextool/generate.py tests/test_generate.py
git commit -m "feat(vortextool): 生成 services.md 文档表 + architecture.md 拓扑图

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: check —— 不变量校验（生成物最新 + .env.example 干净）

**Files:**
- Create: `vortextool/check.py`
- Test: `tests/test_check.py`

- [ ] **Step 1: 写失败测试 tests/test_check.py**

```python
from pathlib import Path
from vortextool.registry import load_registry
from vortextool.check import check_generated_fresh, scan_forbidden_keys

REPO = Path(__file__).resolve().parent.parent
REG = load_registry(REPO / "config" / "registry.yml")


def test_generated_fresh_detects_stale(tmp_path):
    # 写一个过期的 env，断言被判过期
    stale = tmp_path / "vortex.generated.env"
    stale.write_text("# DO NOT EDIT\nVORTEX_DATA_PORT=9999\n", encoding="utf-8")
    problems = check_generated_fresh(REG, env_path=stale,
                                     versions_path=tmp_path / "versions.yml",
                                     services_path=tmp_path / "s.md",
                                     architecture_path=tmp_path / "a.md")
    assert any("vortex.generated.env" in p for p in problems)


def test_scan_forbidden_keys_flags_port_and_path(tmp_path):
    example = tmp_path / ".env.example"
    example.write_text(
        "VORTEX_DATA_PORT=8765\n"
        "VORTEX_WORKSPACE_MOUNT=./workspace\n"
        "VORTEX_DATA_PUBLIC_PORT=8765\n"
        "TZ=Asia/Shanghai\n"
        "TUSHARE_TOKEN=\n",                 # 允许：服务特化密钥
        encoding="utf-8",
    )
    hits = scan_forbidden_keys(example)
    keys = {h.key for h in hits}
    assert "VORTEX_DATA_PORT" in keys       # 端口禁
    assert "VORTEX_WORKSPACE_MOUNT" in keys  # 路径禁
    assert "VORTEX_DATA_PUBLIC_PORT" in keys # PUBLIC_PORT 禁
    assert "TZ" in keys                      # TZ 禁
    assert "TUSHARE_TOKEN" not in keys       # 密钥允许
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/zyukyunman/Documents/vortex/vortex_common && uv run pytest tests/test_check.py -v`
Expected: FAIL（`ModuleNotFoundError: vortextool.check`）。

- [ ] **Step 3: 实现 vortextool/check.py**

```python
"""配置不变量校验（防漂移闸门）。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .registry import Registry
from .generate import (
    render_env, render_versions, render_services_md, render_architecture_md,
)

# .env / .env.example 中禁止出现的键（这些归 common 公共层）
_FORBIDDEN_RE = re.compile(
    r"^\s*(VORTEX_\w*_PORT|VORTEX_\w*_PUBLIC_PORT|VORTEX_\w*_BIND_ADDR|TZ"
    r"|VORTEX_\w*_HOST|VORTEX_\w*MOUNT|VORTEX_\w*HOST_ROOT|VORTEX_WORKSPACE|VORTEX_STATE)\s*="
)


@dataclass(frozen=True)
class ForbiddenHit:
    key: str
    line: str


def scan_forbidden_keys(env_file: Path) -> list[ForbiddenHit]:
    hits: list[ForbiddenHit] = []
    for raw in Path(env_file).read_text(encoding="utf-8").splitlines():
        if raw.lstrip().startswith("#"):
            continue
        m = _FORBIDDEN_RE.match(raw)
        if m:
            hits.append(ForbiddenHit(key=m.group(1), line=raw.strip()))
    return hits


def check_generated_fresh(reg: Registry, *, env_path: Path, versions_path: Path,
                          services_path: Path, architecture_path: Path) -> list[str]:
    problems: list[str] = []
    for path, rendered in [
        (env_path, render_env(reg)),
        (versions_path, render_versions(reg)),
        (services_path, render_services_md(reg)),
        (architecture_path, render_architecture_md(reg)),
    ]:
        actual = Path(path).read_text(encoding="utf-8") if Path(path).exists() else None
        if actual != rendered:
            problems.append(f"{Path(path).name} 过期或缺失 → 重跑 `vortex cfg gen`")
    return problems
```

- [ ] **Step 4: 运行确认通过**

Run: `cd /Users/zyukyunman/Documents/vortex/vortex_common && uv run pytest tests/test_check.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/zyukyunman/Documents/vortex/vortex_common
git add vortextool/check.py tests/test_check.py
git commit -m "feat(vortextool): check —— 生成物最新 + .env 禁用键扫描

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: CLI 入口（vortex cfg gen/check/list/ports）

**Files:**
- Create: `vortextool/cli.py`
- Create: `bin/vortex`
- Test: `tests/test_cli.py`

- [ ] **Step 1: 写失败测试 tests/test_cli.py**

```python
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parent.parent


def _run(*args):
    return subprocess.run(
        [sys.executable, "-m", "vortextool.cli", *args],
        cwd=REPO, capture_output=True, text=True,
    )


def test_cfg_ports_lists_assignments():
    r = _run("cfg", "ports")
    assert r.returncode == 0
    assert "vortex_data" in r.stdout and "8765" in r.stdout
    assert "vortex_trader" in r.stdout and "8768" in r.stdout


def test_cfg_gen_then_check_clean(tmp_path):
    # gen 写真实生成物到仓内，check 立刻应通过（生成物最新）
    assert _run("cfg", "gen").returncode == 0
    r = _run("cfg", "check")
    assert r.returncode == 0, r.stdout + r.stderr
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/zyukyunman/Documents/vortex/vortex_common && uv run pytest tests/test_cli.py -v`
Expected: FAIL（`No module named vortextool.cli`）。

- [ ] **Step 3: 实现 vortextool/cli.py**

```python
"""vortex CLI 入口。本阶段只实现 cfg 组；image/run 为后续 Phase。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .registry import load_registry
from .generate import (
    render_env, render_versions, render_services_md, render_architecture_md,
)
from .check import check_generated_fresh  # scan_forbidden_keys 在 Phase 2 接入

REPO = Path(__file__).resolve().parent.parent
REG_PATH = REPO / "config" / "registry.yml"
ENV_PATH = REPO / "config" / "vortex.generated.env"
VERSIONS_PATH = REPO / "deploy" / "versions.yml"
SERVICES_PATH = REPO / "docs" / "reference" / "services.md"
ARCH_PATH = REPO / "docs" / "reference" / "architecture.md"


def _gen() -> int:
    reg = load_registry(REG_PATH)
    for path, text in [
        (ENV_PATH, render_env(reg)),
        (VERSIONS_PATH, render_versions(reg)),
        (SERVICES_PATH, render_services_md(reg)),
        (ARCH_PATH, render_architecture_md(reg)),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"  写 {path.relative_to(REPO)}")
    return 0


def _check() -> int:
    reg = load_registry(REG_PATH)   # load 内含端口唯一/升序校验
    problems = check_generated_fresh(
        reg, env_path=ENV_PATH, versions_path=VERSIONS_PATH,
        services_path=SERVICES_PATH, architecture_path=ARCH_PATH,
    )
    # 注：各仓 .env.example 禁用键扫描在 Phase 2（清理那些文件后）接入 _check，
    # 避免 Phase 0 期间旧文件未清而误红。scan_forbidden_keys 已实现+单测（Task 6）。
    if problems:
        print("✗ check 失败：", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print("✓ check 通过")
    return 0


def _list() -> int:
    reg = load_registry(REG_PATH)
    for s in reg.services:
        print(f"{s.name:18} :{s.port}  {s.role}  ref={s.ref or '(预留)'}")
    return 0


def _ports() -> int:
    reg = load_registry(REG_PATH)
    for s in reg.services:
        print(f"{s.port}  {s.name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vortex")
    sub = parser.add_subparsers(dest="group", required=True)
    cfg = sub.add_parser("cfg", help="配置组")
    cfg_sub = cfg.add_subparsers(dest="action", required=True)
    for name in ("gen", "check", "list", "ports"):
        cfg_sub.add_parser(name)
    args = parser.parse_args(argv)
    if args.group == "cfg":
        return {"gen": _gen, "check": _check, "list": _list, "ports": _ports}[args.action]()
    parser.error(f"未知组 {args.group}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 创建 bin/vortex 薄入口**

`bin/vortex`:
```bash
#!/usr/bin/env bash
# vortex —— 宿主机配置/镜像/运行总入口（区别于容器内 vortexctl）。
# 本阶段实现 cfg 组（gen/check/list/ports）。image/run 为后续 Phase。
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"   # vortex_common 仓根
exec uv --project "$HERE" run python -m vortextool.cli "$@"
```
Run: `chmod +x /Users/zyukyunman/Documents/vortex/vortex_common/bin/vortex`

- [ ] **Step 5: 运行确认通过**

Run: `cd /Users/zyukyunman/Documents/vortex/vortex_common && uv run pytest tests/test_cli.py -v`
Expected: 2 passed.

- [ ] **Step 6: 端到端冒烟**

Run: `cd /Users/zyukyunman/Documents/vortex/vortex_common && ./bin/vortex cfg ports && ./bin/vortex cfg check`
Expected: 打印端口表；check 通过（因 Step 5 的 gen 已写出最新生成物）。

- [ ] **Step 7: Commit**

```bash
cd /Users/zyukyunman/Documents/vortex/vortex_common
git add vortextool/cli.py bin/vortex tests/test_cli.py
git commit -m "feat(vortex): CLI 入口 cfg 组（gen/check/list/ports）

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: 落地生成物（提交首版生成文件）

**Files:**
- Create/overwrite: `config/vortex.generated.env`, `deploy/versions.yml`, `docs/reference/services.md`, `docs/reference/architecture.md`

- [ ] **Step 1: 生成全部派生物**

Run: `cd /Users/zyukyunman/Documents/vortex/vortex_common && ./bin/vortex cfg gen`
Expected: 打印写出 4 个文件路径。

- [ ] **Step 2: 核对 versions.yml 与旧版差异（确保 awk 字段没丢）**

Run: `cd /Users/zyukyunman/Documents/vortex/vortex_common && git diff deploy/versions.yml`
Expected: 仅头注释与格式变化 + trader ref 由旧的写法变为裸空；name/repo/ref/submodules 四字段齐全。
人工确认无误。

- [ ] **Step 3: check 通过**

Run: `cd /Users/zyukyunman/Documents/vortex/vortex_common && ./bin/vortex cfg check`
Expected: ✓ check 通过（Phase 0 的 check 只校验"生成物最新 + 端口唯一/升序"；各仓 .env.example 禁用键扫描在 Phase 2 接入，故此处不因旧文件误红）。

- [ ] **Step 4: Commit**

```bash
cd /Users/zyukyunman/Documents/vortex/vortex_common
git add config/vortex.generated.env deploy/versions.yml docs/reference/services.md docs/reference/architecture.md
git commit -m "feat(config): 生成首版 vortex.generated.env / versions.yml / 文档表 / 拓扑图

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: ADR-003 决策记录

**Files:**
- Create: `docs/adr/ADR-003-unified-config-architecture.md`

- [ ] **Step 1: 写 ADR-003**

`docs/adr/ADR-003-unified-config-architecture.md`（要点，照 spec §10）：
```markdown
# ADR-003: 统一配置架构

**状态：** Accepted
**日期：** 2026-06-10
**决策人：** @zyukyunman
**相关：** ADR-001（部署架构）、ADR-002（workspace/state 变量）、
spec docs/superpowers/specs/2026-06-09-vortex-config-architecture-design.md

## 决策
1. `config/registry.yml` 为配置单一真值源；`vortex cfg gen` 投影出 env/versions.yml/文档表/架构图。
2. 端口"一号到底、内外一致"：data 8765 / backtest 8766 / qmt 8767 / trader 8768；删 *_PUBLIC_PORT，保留 *_BIND_ADDR。
3. `vortex` CLI 三组 cfg/image/run（宿主机），区别于容器内 `vortexctl`。
4. compose `--env-file` 注入（服务 .env 先、common 后=权威）；裸 docker compose up 用 :? 报错导向 vortex run。
5. 容器监听 0.0.0.0 是不变量（不进生成 env）；宿主机根由 vortex run 运行时解析（不烤绝对路径）。
6. `vortex cfg check` 防漂移：端口唯一/升序、生成物最新、.env 无禁用键 —— 挂 pre-commit/CI。
7. 文档分层：system 级在 common（含生成的 reference + 架构图）、service 级在各仓。

## 后果
- 加服务 = 改 registry 一行 + `vortex cfg gen`。
- ADR-001/002 被本 ADR 补充（端口表以 registry 为准）。
```

- [ ] **Step 2: 在 ADR-001/002 顶部加补充指引**

在 `docs/adr/ADR-001-deployment-architecture.md` 和 `ADR-002-unified-workspace-env-vars.md` 的"相关"行追加：`、ADR-003（统一配置架构，端口表/真值源以其为准）`。

- [ ] **Step 3: Commit**

```bash
cd /Users/zyukyunman/Documents/vortex/vortex_common
git add docs/adr/ADR-003-unified-config-architecture.md docs/adr/ADR-001-deployment-architecture.md docs/adr/ADR-002-unified-workspace-env-vars.md
git commit -m "docs(adr): ADR-003 统一配置架构 + ADR-001/002 补充指引

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 0 验收

- [ ] `uv run pytest -q` 全绿（registry/generate/check/cli）。
- [ ] `./bin/vortex cfg gen` 幂等：连跑两次，`git status` 无变化。
- [ ] `./bin/vortex cfg ports` 打印 8765/8766/8767/8768。
- [ ] 生成的 `versions.yml` 经真实 awk 解析，trader 的 ref 段为空（不是 `""`）。
- [ ] `config/vortex.generated.env` 无 `_HOST=`、无 `/Users/`、无 `HOST_ROOT`。
- [ ] ADR-003 落地，ADR-001/002 加了指引。

**Phase 0 完成后**：基石就绪（真实的 `vortex.generated.env` 变量名、CLI 行为已确定），再据此细化 Phase 1（image/run + deploy 对齐）与 Phase 2-4，per-repo 整改即可引用真实变量名而非猜测。
