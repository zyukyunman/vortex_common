# Vortex 配置 Phase 1：vortex image/run 组 + common deploy 对齐 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `vortex` CLI 补上 `image`（base/pull/build/push，收编现有脚本）与 `run`（up/down/logs/deploy，compose 薄壳）两组，并把 common 的 `deploy/`（compose / Dockerfile / vortexctl / build-release）对齐到 registry 真值源——端口一号到底、生成 env 驱动插值、容器内 vortexctl 读同一份。

**Architecture:** `image`/`run` 组加进已存在的 `vortextool/cli.py`（Python，用 subprocess 调 docker/脚本），统一带 `--dry-run` 打印命令以便无 docker 单测。compose `ports:` 改三段同号 `${BIND}:${PORT}:${PORT}` + `:?` 必填、删 `*_PUBLIC_PORT`、端口取自 `--env-file` 注入的 `config/vortex.generated.env`。组合镜像 Dockerfile 遍历安装 + 烤入生成 env，vortexctl 启动时 source 它。

**Tech Stack:** Python 3.11+（cli）、bash（vortexctl/脚本）、docker compose v5（`docker compose config` 验证插值）。docker 实测可用。

> 仓 = `vortex_common`，绝对根 `/Users/zyukyunman/Documents/vortex/vortex_common`。Phase 0 已合并 main（registry + vortextool + bin/vortex cfg + 生成物 + ADR-003，25 pytest 绿）。
> 设计依据：spec §2.4/§2.5/§3/§8.1，ADR-003。本计划在 Phase 0 真实产物上细化。

---

## 关键事实（Phase 0 落地后的真实接口，本计划依赖）

- `config/vortex.generated.env` 含：`TZ`、`VORTEX_NETWORK`、`VORTEX_IMAGE_BASE/APP`、每服务 `VORTEX_<SVC>_PORT`（8765/8766/8767/8768）、`VORTEX_<SVC>_BIND_ADDR`（127.0.0.1）。**无** `_HOST`、**无**宿主机绝对路径。
- `bin/vortex` = `exec uv --project <repo> run python -m vortextool.cli "$@"`；`cli.py` 用 `set_defaults(func=...)` 分派，`main` 捕获 `RegistryError`→exit 2。
- 现有脚本签名：`scripts/build-base-image.sh [base] [--no-cache] [--tag=X] [--push] [--platform=X]`；`deploy/pull-code.sh [svc...]`；`deploy/build-release.sh [--tag=X] [--no-cache] [--push] [--keep-stage]`。
- `--env-file` 顺序（spec §2.5）：**服务 .env 先、common 生成 env 后**（末位优先=common 权威）。
- 容器内监听 `0.0.0.0` 是不变量（compose `environment:` 字面给）；宿主机 workspace/state 根由 `run` 运行时解析（默认 `$HOME/vortex/{workspace,state}`，prod 用命名卷不需要）。

---

## 文件结构（Phase 1 创建/修改）

| 文件 | 改动 |
|------|------|
| `vortextool/cli.py` | 加 `run` 组（up/down/logs/deploy）+ `image` 组（base/pull/build/push）+ `--dry-run`；抽出命令构造为可测函数 | 
| `tests/test_cli_run.py` `tests/test_cli_image.py` | 新建：命令构造 dry-run 测试 |
| `deploy/docker-compose.yml` | 端口取生成 env、三段同号 `:?`、删 PUBLIC_PORT、qmt 8810→8767/trader 8820→8768、TZ 取 env |
| `deploy/Dockerfile` | COPY/install 遍历（保 qmt-bridge + `--no-build-isolation`）、`COPY vortex.generated.env`、`EXPOSE 8765 8766 8767 8768` |
| `deploy/build-release.sh` | 构建前把 `../config/vortex.generated.env` 拷进 deploy 上下文供 Dockerfile COPY |
| `deploy/bin/vortexctl` | 启动时 source 烤入的生成 env；删 legacy 导出（QMT_STATE_DIR/DATA_WORKSPACE）；端口默认对齐 8765/66/67/68 |
| `.gitignore` | 忽略 `deploy/vortex.generated.env`（构建期拷贝产物，非真值源） |

---

## Task 1: `vortex run` 组（compose 薄壳 + --dry-run）

**Files:** Modify `vortextool/cli.py`; Create `tests/test_cli_run.py`.

设计：把"构造 compose 命令"抽成纯函数 `build_compose_argv(...)` 便于单测；`run` 各动作调它，`--dry-run` 打印不执行。

- [ ] **Step 1: 写失败测试 `tests/test_cli_run.py`**

```python
from pathlib import Path
import vortextool.cli as cli

COMMON = Path(cli.__file__).resolve().parent.parent          # vortex_common
GEN = COMMON / "config" / "vortex.generated.env"
PARENT = COMMON.parent                                        # .../vortex


def test_run_up_dev_argv_order_and_envfiles():
    argv = cli.build_compose_argv("up", "data", dry=True)
    # dev：在 vortex_data 仓内，--env-file 服务 .env 先、common 生成 env 后
    assert argv[:2] == ["docker", "compose"]
    i_svc = argv.index(str(PARENT / "vortex_data" / ".env"))
    i_common = argv.index(str(GEN))
    assert argv[argv.index("--env-file") ] == "--env-file"
    assert i_svc < i_common                                   # 服务先、common 后（末位权威）
    assert "up" in argv and "-d" in argv and "--build" in argv


def test_run_deploy_uses_generated_env():
    argv = cli.build_compose_argv("deploy", None, dry=True)
    assert "--env-file" in argv and str(GEN) in argv
    assert "up" in argv and "-d" in argv
    assert "--build" not in argv                              # prod 用已造好的组合镜像，不 --build


def test_run_up_resolves_host_root_abs(monkeypatch):
    monkeypatch.setenv("HOME", "/home/tester")
    env = cli.compose_env(monkeypatch_home=None)             # 见实现：返回注入 compose 的 env
    assert env["VORTEX_WORKSPACE_HOST_ROOT"] == "/home/tester/vortex/workspace"
    assert env["VORTEX_STATE_HOST_ROOT"] == "/home/tester/vortex/state"
    assert "~" not in env["VORTEX_WORKSPACE_HOST_ROOT"]
```

- [ ] **Step 2: 运行确认 FAIL** — `cd /Users/zyukyunman/Documents/vortex/vortex_common && uv run pytest tests/test_cli_run.py -v`（AttributeError: build_compose_argv）。

- [ ] **Step 3: 实现（加到 `vortextool/cli.py`）**

在文件顶部已有 import 下补：
```python
import os
import subprocess

PARENT = REPO.parent                                  # .../vortex（各服务仓的父目录）
GEN_ENV = ENV_PATH                                    # config/vortex.generated.env（Phase 0 已定义 ENV_PATH）
DEPLOY_DIR = REPO / "deploy"


def compose_env(monkeypatch_home: str | None = None) -> dict[str, str]:
    """compose 插值所需的运行时环境：宿主机 workspace/state 根解析为绝对路径（不烤进 committed env）。"""
    env = dict(os.environ)
    home = env.get("HOME", "")
    env.setdefault("VORTEX_WORKSPACE_HOST_ROOT", f"{home}/vortex/workspace")
    env.setdefault("VORTEX_STATE_HOST_ROOT", f"{home}/vortex/state")
    return env


def build_compose_argv(action: str, svc: str | None, *, dry: bool = False) -> list[str]:
    """构造 docker compose 命令。dev(up/down/logs <svc>)在各仓内双 --env-file；deploy 在 deploy/ 用生成 env。"""
    if action == "deploy":
        return [
            "docker", "compose",
            "--env-file", str(GEN_ENV),
            "up", "-d",
        ]
    # dev 单仓：服务 .env 先、common 生成 env 后（末位权威）
    repo = PARENT / f"vortex_{svc}"
    svc_env = repo / ".env"
    base = [
        "docker", "compose",
        "--env-file", str(svc_env),
        "--env-file", str(GEN_ENV),
    ]
    if action == "up":
        return base + ["up", "-d", "--build"]
    if action == "down":
        return base + ["down"]
    if action == "logs":
        return base + ["logs", "-f"]
    raise ValueError(f"未知 run 动作: {action}")


def _run_compose(action: str, svc: str | None, dry: bool) -> int:
    argv = build_compose_argv(action, svc, dry=dry)
    cwd = DEPLOY_DIR if action == "deploy" else (PARENT / f"vortex_{svc}")
    if dry:
        print(f"(cwd={cwd}) " + " ".join(argv))
        return 0
    return subprocess.run(argv, cwd=str(cwd)).returncode
```

- [ ] **Step 4: 把 run 组接进 `main`（在 cfg 注册之后、`args = parser.parse_args` 之前）**

```python
    run = sub.add_parser("run", help="运行组")
    run_sub = run.add_subparsers(dest="action", required=True)
    for name in ("up", "down", "logs"):
        p = run_sub.add_parser(name)
        p.add_argument("svc", choices=["data", "backtest", "qmt", "trader"])
        p.add_argument("--dry-run", action="store_true")
    dep = run_sub.add_parser("deploy")
    dep.add_argument("--dry-run", action="store_true")
```
并在分派处（`main` 末尾，`try` 块内）支持 run：
```python
    try:
        if args.group == "cfg":
            return args.func()
        if args.group == "run":
            svc = getattr(args, "svc", None)
            return _run_compose(args.action, svc, args.dry_run)
        ...
```
> 注意：保留 Phase 0 已有的 cfg 分派与 RegistryError 捕获；run 不读 registry，不触发 RegistryError，但放在同一 try 无害。

- [ ] **Step 5: 运行确认 PASS** — `uv run pytest tests/test_cli_run.py -v` → 3 passed；全套 `uv run pytest -q`（28 passed = 25 + 3）。

- [ ] **Step 6: dry-run 冒烟**
```bash
cd /Users/zyukyunman/Documents/vortex/vortex_common
./bin/vortex run up data --dry-run
./bin/vortex run deploy --dry-run
```
确认：up 打印 `docker compose --env-file .../vortex_data/.env --env-file .../config/vortex.generated.env up -d --build`（服务 .env 在前）；deploy 打印 `--env-file .../config/vortex.generated.env up -d`（无 --build）。粘贴输出。

- [ ] **Step 7: Commit**
```bash
git add vortextool/cli.py tests/test_cli_run.py
git commit -m "feat(vortex): run 组（up/down/logs/deploy，compose 薄壳 + --dry-run）

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `vortex image` 组（收编 base/pull/build/push）

**Files:** Modify `vortextool/cli.py`; Create `tests/test_cli_image.py`.

- [ ] **Step 1: 写失败测试 `tests/test_cli_image.py`**

```python
from pathlib import Path
import vortextool.cli as cli

COMMON = Path(cli.__file__).resolve().parent.parent


def test_image_base_wraps_script():
    argv = cli.build_image_argv("base", ["--no-cache"])
    assert argv[0] == str(COMMON / "scripts" / "build-base-image.sh")
    assert "--no-cache" in argv


def test_image_pull_and_build_wrap_deploy_scripts():
    assert cli.build_image_argv("pull", [])[0] == str(COMMON / "deploy" / "pull-code.sh")
    b = cli.build_image_argv("build", ["--tag=2026.06.10"])
    assert b[0] == str(COMMON / "deploy" / "build-release.sh")
    assert "--tag=2026.06.10" in b


def test_image_push_maps_to_build_release_push():
    argv = cli.build_image_argv("push", [])
    assert argv[0] == str(COMMON / "deploy" / "build-release.sh")
    assert "--push" in argv
```

- [ ] **Step 2: 运行确认 FAIL** — `uv run pytest tests/test_cli_image.py -v`.

- [ ] **Step 3: 实现（加到 `vortextool/cli.py`）**

```python
SCRIPTS_DIR = REPO / "scripts"

_IMAGE_SCRIPTS = {
    "base":  (SCRIPTS_DIR / "build-base-image.sh", []),
    "pull":  (DEPLOY_DIR / "pull-code.sh", []),
    "build": (DEPLOY_DIR / "build-release.sh", []),
    "push":  (DEPLOY_DIR / "build-release.sh", ["--push"]),
}


def build_image_argv(action: str, extra: list[str]) -> list[str]:
    script, fixed = _IMAGE_SCRIPTS[action]
    return [str(script), *fixed, *extra]


def _run_image(action: str, extra: list[str], dry: bool) -> int:
    argv = build_image_argv(action, extra)
    if dry:
        print(" ".join(argv))
        return 0
    return subprocess.run(argv).returncode
```

- [ ] **Step 4: 接进 `main`**（在 run 组注册后）：
```python
    image = sub.add_parser("image", help="镜像组")
    image_sub = image.add_subparsers(dest="action", required=True)
    for name in ("base", "pull", "build", "push"):
        p = image_sub.add_parser(name)
        p.add_argument("extra", nargs="*", help="透传给底层脚本的参数")
        p.add_argument("--dry-run", action="store_true")
```
分派（try 块内）：
```python
        if args.group == "image":
            return _run_image(args.action, args.extra, args.dry_run)
```
> argparse 注意：`--no-cache`/`--tag=X` 等要透传给脚本而非被 vortex 解析——用 `nargs="*"` 收集 `extra` 时，加 `parser.parse_known_args` 或让用户在 `--` 后传。简化：测试用显式 `extra` 列表调 `build_image_argv`；CLI 实际透传用 `image build -- --tag=X` 或在文档说明。**实现 `build_image_argv` 即可满足本任务测试**；CLI 末端透传细节在 Step 6 冒烟确认。

- [ ] **Step 5: 运行确认 PASS** — `uv run pytest tests/test_cli_image.py -v` → 3 passed；全套 `uv run pytest -q`（31 passed）。

- [ ] **Step 6: dry-run 冒烟**
```bash
cd /Users/zyukyunman/Documents/vortex/vortex_common
./bin/vortex image base --dry-run
./bin/vortex image build --dry-run -- --tag=2026.06.10   # 若 argparse 透传需要 --
```
确认打印 `.../scripts/build-base-image.sh`、`.../deploy/build-release.sh --tag=2026.06.10`。若 `--tag` 透传被 argparse 拦截，改用 `nargs=argparse.REMAINDER` 或 `parse_known_args`，并在 Step 6 修正后重测。粘贴输出。

- [ ] **Step 7: Commit**
```bash
git add vortextool/cli.py tests/test_cli_image.py
git commit -m "feat(vortex): image 组（base/pull/build/push，收编现有脚本）

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: 对齐 `deploy/docker-compose.yml`（端口取生成 env、三段同号、删 PUBLIC_PORT）

**Files:** Modify `deploy/docker-compose.yml`. 验证用 `docker compose config`（docker 已确认可用）。

逐服务改动（data/backtest/qmt/trader）：`environment:` 的 `VORTEX_<SVC>_PORT` 改 `${VORTEX_<SVC>_PORT:?run via vortex run}`；`ports:` 改 `"${VORTEX_<SVC>_BIND_ADDR:?run via vortex run}:${VORTEX_<SVC>_PORT}:${VORTEX_<SVC>_PORT}"`；删所有 `*_PUBLIC_PORT`；`TZ` 改 `${TZ}`；`VORTEX_<SVC>_HOST: 0.0.0.0` 字面保留；healthcheck 端口用 `${VORTEX_<SVC>_PORT}`。端口数值不再写字面（除 healthcheck 内 python 取 env）。

- [ ] **Step 1: 备份当前可解析基线（回归对照）**
```bash
cd /Users/zyukyunman/Documents/vortex/vortex_common/deploy
git show HEAD:deploy/docker-compose.yml > /tmp/compose.before.yml
```

- [ ] **Step 2: 改写 `deploy/docker-compose.yml`。** 四个 service 的 `environment` 与 `ports` 改为（以 data 为例，其余同构）：
```yaml
  vortex-data:
    image: *img
    command: ["vortexctl", "data"]
    container_name: vortex-data
    env_file:
      - repos/vortex_data/.env
    environment:
      VORTEX_WORKSPACE: /workspace
      VORTEX_DATA_HOST: 0.0.0.0                 # 容器内监听不变量（≠对外暴露）
      VORTEX_DATA_PORT: ${VORTEX_DATA_PORT:?run via vortex run}
      TZ: ${TZ:?run via vortex run}
    ports:
      - "${VORTEX_DATA_BIND_ADDR:?run via vortex run}:${VORTEX_DATA_PORT}:${VORTEX_DATA_PORT}"
    volumes:
      - vortex-workspace:/workspace
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.getenv('VORTEX_DATA_PORT','8765'), timeout=3).read()\""]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
```
对 qmt：`VORTEX_QMT_PORT` 默认值语义来自生成 env（=8767），删 `VORTEX_QMT_PUBLIC_PORT`，保留 `extra_hosts`、`VORTEX_STATE: /state`、`VORTEX_QMT_HOST: 0.0.0.0`。对 backtest：`${VORTEX_BACKTEST_PORT}`（=8766），保留 `:ro` workspace。对 trader：`${VORTEX_TRADER_PORT}`（=8768），保留 `profiles: ["trader"]`。删除文件顶部注释里 `*_PUBLIC_PORT` 的暴露示例，改为 `VORTEX_DATA_BIND_ADDR=0.0.0.0 vortex run deploy`。

- [ ] **Step 3: 用 docker compose config 验证插值（关键，端口来自生成 env）**
```bash
cd /Users/zyukyunman/Documents/vortex/vortex_common/deploy
docker compose --env-file ../config/vortex.generated.env config > /tmp/compose.rendered.yml 2>/tmp/compose.err || { echo "FAIL"; cat /tmp/compose.err; }
grep -E 'published|target|host_ip' /tmp/compose.rendered.yml
```
EXPECTED：每服务 published==target（同号），data 8765 / backtest 8766 / qmt 8767 / trader（profiles 默认不出现，加 `--profile trader` 才渲染——可单独 `docker compose --profile trader --env-file ... config` 验 8768）。host_ip 127.0.0.1。无 `PUBLIC_PORT` 残留、无 `is not set` 警告。粘贴关键行。

- [ ] **Step 4: 结构化断言（不依赖 docker，供 CI/复核）**
```bash
cd /Users/zyukyunman/Documents/vortex/vortex_common
! grep -q 'PUBLIC_PORT' deploy/docker-compose.yml && echo "✓ 无 PUBLIC_PORT"
grep -cE '\$\{VORTEX_\w+_PORT[^}]*\}:\$\{VORTEX_\w+_PORT\}' deploy/docker-compose.yml | xargs echo "三段同号端口行数(应≥4):"
! grep -qE ':\s*88(10|20)\b|:\s*8767\s*$' deploy/docker-compose.yml && echo "✓ 无旧端口字面" || echo "检查是否仅 healthcheck 默认值残留"
```

- [ ] **Step 5: Commit**
```bash
git add deploy/docker-compose.yml
git commit -m "feat(deploy): compose 端口取生成 env + 三段同号 + 删 PUBLIC_PORT（qmt 8810→8767/trader 8820→8768）

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: 对齐 `deploy/Dockerfile`（遍历安装 + 烤入生成 env + EXPOSE）+ build-release 拷贝 env

**Files:** Modify `deploy/Dockerfile`, `deploy/build-release.sh`, `.gitignore`.

- [ ] **Step 1: 改 `deploy/Dockerfile` 的 COPY/install 段为遍历（保 qmt-bridge + --no-build-isolation），并烤入生成 env、改 EXPOSE。**

把现有逐条 `COPY .stage/vortex_* ...` + 逐条 pip install 段替换为：
```dockerfile
# 1) 各服务源码（build-release.sh 已 clone 到 pinned tag）。trader 预留时为占位空目录。
COPY .stage/ /app/services/

# 2) 安装各服务（依赖已在 vortex-base，--no-deps；--no-build-isolation 避免联网取 build backend）。
RUN set -eux; \
    for d in /app/services/*/; do \
        [ -f "$d/pyproject.toml" ] && pip install --no-deps --no-build-isolation "$d"; \
    done; \
    # qmt-bridge 子模块是 external/ 下嵌套包，顶层 glob 扫不到，显式装。
    if [ -f /app/services/vortex_qmt/external/qmt-bridge/pyproject.toml ]; then \
        pip install --no-deps /app/services/vortex_qmt/external/qmt-bridge; \
    fi

# 2b) 烤入配置真值源生成的 env，供容器内 vortexctl source（端口/网络/TZ 默认值与 registry 一致）。
COPY vortex.generated.env /app/config/vortex.generated.env
```
并把 `EXPOSE 8765 8810 8767` 改为 `EXPOSE 8765 8766 8767 8768`。其余（ENV VORTEX_WORKSPACE/STATE、useradd、LABEL、CMD）不动。

- [ ] **Step 2: 改 `deploy/build-release.sh`：构建前把生成 env 拷进 deploy 上下文。** 在 `docker build` 调用前加：
```bash
# 烤入用的配置 env：从 common config/ 拷进构建上下文（deploy/），供 Dockerfile COPY。
cp ../config/vortex.generated.env ./vortex.generated.env
```
（放在 `echo ">> 构建 ${IMAGE}..."` 之前；该拷贝文件不入库，见 Step 3。）

- [ ] **Step 3: `.gitignore` 忽略构建期拷贝产物。** 追加一行：
```
deploy/vortex.generated.env
```

- [ ] **Step 4: 结构化验证（不做完整 build——重；完整 build 留 Task 6 集成）**
```bash
cd /Users/zyukyunman/Documents/vortex/vortex_common
grep -q 'for d in /app/services/\*/' deploy/Dockerfile && echo "✓ 遍历安装"
grep -q -- '--no-build-isolation' deploy/Dockerfile && echo "✓ 保留 --no-build-isolation"
grep -q 'external/qmt-bridge' deploy/Dockerfile && echo "✓ 保留 qmt-bridge 显式安装"
grep -q 'COPY vortex.generated.env /app/config/vortex.generated.env' deploy/Dockerfile && echo "✓ 烤入生成 env"
grep -q 'EXPOSE 8765 8766 8767 8768' deploy/Dockerfile && echo "✓ EXPOSE 对齐"
git check-ignore deploy/vortex.generated.env >/dev/null && echo "✓ 拷贝产物已 gitignore"
```

- [ ] **Step 5: Commit**
```bash
git add deploy/Dockerfile deploy/build-release.sh .gitignore
git commit -m "feat(deploy): 组合镜像遍历安装 + 烤入 vortex.generated.env + EXPOSE 对齐

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: 对齐 `deploy/bin/vortexctl`（source 生成 env + 删 legacy 导出 + 端口对齐）

**Files:** Modify `deploy/bin/vortexctl`; Create `tests/test_vortexctl.sh`（bash 测试，用 pytest 包一层调用）。

- [ ] **Step 1: 写失败测试 `tests/test_vortexctl.sh`**（验证 source 生成 env 后端口正确、无 legacy 导出）
```bash
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
VCTL="$HERE/deploy/bin/vortexctl"

# 造一个假的烤入 env 与假的 services 目录，验证 vortexctl source 后端口取自 env。
TMP="$(mktemp -d)"
mkdir -p "$TMP/config" "$TMP/services"
cat > "$TMP/config/vortex.generated.env" <<'EOF'
VORTEX_DATA_PORT=8765
VORTEX_QMT_PORT=8767
VORTEX_BACKTEST_PORT=8766
VORTEX_TRADER_PORT=8768
TZ=Asia/Shanghai
EOF

# vortexctl 应支持 VORTEX_GENERATED_ENV 覆盖 source 路径、VORTEX_SERVICES_DIR 覆盖服务目录。
out="$(VORTEX_GENERATED_ENV="$TMP/config/vortex.generated.env" VORTEX_SERVICES_DIR="$TMP/services" \
       VORTEX_DEBUG_PORTS=1 bash "$VCTL" list 2>&1 || true)"
echo "$out"
echo "$out" | grep -q 'VORTEX_QMT_PORT=8767' || { echo "FAIL: qmt 端口未取自生成 env"; exit 1; }
grep -q 'VORTEX_QMT_STATE_DIR' "$VCTL" && { echo "FAIL: 仍有 legacy VORTEX_QMT_STATE_DIR 导出"; exit 1; }
grep -q 'VORTEX_DATA_WORKSPACE' "$VCTL" && { echo "FAIL: 仍有 legacy VORTEX_DATA_WORKSPACE 导出"; exit 1; }
echo "PASS"
```
包一层 `tests/test_vortexctl.py`：
```python
import subprocess, sys
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
def test_vortexctl_sources_generated_env_and_no_legacy():
    r = subprocess.run(["bash", str(REPO / "tests" / "test_vortexctl.sh")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
```

- [ ] **Step 2: 运行确认 FAIL** — `uv run pytest tests/test_vortexctl.py -v`（当前 vortexctl 硬编码 8810、有 legacy 导出、不 source env）。

- [ ] **Step 3: 改 `deploy/bin/vortexctl`。** 在 `set -euo pipefail` 后、环境默认块前插入 source 生成 env：
```bash
# 端口/网络/TZ 默认值来自配置真值源生成的 env（烤入镜像 /app/config/）。可用 VORTEX_GENERATED_ENV 覆盖（测试用）。
GENERATED_ENV="${VORTEX_GENERATED_ENV:-/app/config/vortex.generated.env}"
[ -f "$GENERATED_ENV" ] && set -a && . "$GENERATED_ENV" && set +a
```
把端口默认行对齐（兜底值=registry 新值；source 成功时已被 env 覆盖）：
```bash
export VORTEX_DATA_PORT="${VORTEX_DATA_PORT:-8765}"
export VORTEX_QMT_PORT="${VORTEX_QMT_PORT:-8767}"        # 原 8810
export VORTEX_BACKTEST_PORT="${VORTEX_BACKTEST_PORT:-8766}"  # 原 8767
export VORTEX_TRADER_PORT="${VORTEX_TRADER_PORT:-8768}"  # 原 8820
```
**删除** legacy 导出两行：`export VORTEX_QMT_STATE_DIR=...` 与 `export VORTEX_DATA_WORKSPACE=...`（code 已标准优先读 `VORTEX_STATE`/`VORTEX_WORKSPACE`，vortexctl 已 export 这两个标准名，故 legacy 冗余可删）。`VORTEX_<SVC>_HOST="${...:-0.0.0.0}"` 与 `VORTEX_BACKTEST_STATE_DIR` 的处理：backtest builtin_start 用 `VORTEX_BACKTEST_STATE_DIR`——把它改成读 `VORTEX_STATE`（`mkdir -p "${VORTEX_STATE}"`），与 backtest/run.sh 的 Phase 2 整改一致。在 builtin_start 的 backtest 分支与 qmt 分支用 `${VORTEX_STATE}` 取代 `${VORTEX_*_STATE_DIR}`。
加调试钩子（测试用，末尾 main 前）：
```bash
if [ "${VORTEX_DEBUG_PORTS:-}" = "1" ]; then
  echo "VORTEX_DATA_PORT=${VORTEX_DATA_PORT} VORTEX_QMT_PORT=${VORTEX_QMT_PORT} VORTEX_BACKTEST_PORT=${VORTEX_BACKTEST_PORT} VORTEX_TRADER_PORT=${VORTEX_TRADER_PORT}"
fi
```

- [ ] **Step 4: 运行确认 PASS** — `uv run pytest tests/test_vortexctl.py -v` → 1 passed；全套 `uv run pytest -q`（32 passed = 31 + 1）。

- [ ] **Step 5: Commit**
```bash
git add deploy/bin/vortexctl tests/test_vortexctl.sh tests/test_vortexctl.py
git commit -m "feat(deploy): vortexctl source 生成 env + 删 legacy 导出 + 端口对齐(qmt 8767/backtest 8766/trader 8768)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: 集成冒烟（可选但推荐：组合镜像 build + deploy config 全栈）

**Files:** 无（仅验证）。仅在 `vortex-base` 镜像已存在时跑完整 build（重，约数分钟）。

- [ ] **Step 1: 确保 base 存在（缺则造，一次性）**
```bash
cd /Users/zyukyunman/Documents/vortex/vortex_common
docker image inspect vortex-base:latest >/dev/null 2>&1 || ./bin/vortex image base
```

- [ ] **Step 2: deploy compose 全栈插值验证（含 trader profile）**
```bash
cd deploy
docker compose --env-file ../config/vortex.generated.env config >/dev/null && echo "✓ 默认栈插值通过"
docker compose --profile trader --env-file ../config/vortex.generated.env config | grep -E 'target|published' && echo "✓ 含 trader(8768)"
```

- [ ] **Step 3:（可选，重）真造组合镜像并验 vortexctl 读到对齐端口**
```bash
cd /Users/zyukyunman/Documents/vortex/vortex_common
./bin/vortex image pull          # 拉各仓（需网络/凭据；本地已有 repos/ 则更新）
./bin/vortex image build --tag=phase1-smoke
docker run --rm vortex:phase1-smoke vortexctl list      # 应列出已装服务
docker run --rm vortex:phase1-smoke sh -c '. /app/config/vortex.generated.env; echo qmt=$VORTEX_QMT_PORT'  # 应 8767
```
若环境无网络/凭据拉私有仓，跳过 Step 3，记录"完整镜像验证待有凭据时补"。

- [ ] **Step 4: 记录结果**（不提交代码；把冒烟输出写进 commit message 或 PR 描述供追溯）。

---

## Self-Review（已对照 spec §2.4/§2.5/§3/§8.1）

- 覆盖：run 组（up/down/logs/deploy + --env-file 顺序 + HOST_ROOT 解析）✓；image 组（base/pull/build/push 收编）✓；compose 三段同号+删 PUBLIC_PORT+端口取 env+TZ ✓；Dockerfile 遍历+保 qmt-bridge/--no-build-isolation+烤入 env+EXPOSE ✓；vortexctl source env+删 legacy+端口对齐 ✓；build-release 拷 env ✓。
- 占位符：无 TBD；每步给了具体代码/编辑/命令与期望。
- 类型/名称一致：`build_compose_argv`/`build_image_argv`/`compose_env`/`_run_compose`/`_run_image` 跨 Task 1-2 与 main 分派一致；`GEN_ENV=ENV_PATH`、`PARENT=REPO.parent` 复用 Phase 0 的 `REPO`/`ENV_PATH`。
- 已知风险/留待：(a) `image` 组 argparse 透传 `--tag/--no-cache` 可能需 `parse_known_args`/`REMAINDER`——Task 2 Step 6 验证并修正；(b) `run up <svc>` 端到端要等 Phase 2 各仓 compose 对齐后才真能起（本 Phase 仅 dry-run + 命令构造可测）；(c) 完整组合镜像 build 依赖私有仓凭据，Task 6 Step 3 可跳过并记录。
- 不做（YAGNI）：compose 的 `networks: vortex-net` 显式块本 Phase 不加（服务现走默认网络可通；VORTEX_NETWORK 已在生成 env，留作后续需要时接）；各仓（data/qmt/backtest）自身 compose/.env 的对齐属 **Phase 2**，不在此。

## 验收

- [ ] `uv run pytest -q` 全绿（≈32：25 + run3 + image3 + vortexctl1，以实际为准）。
- [ ] `./bin/vortex run up data --dry-run` / `run deploy --dry-run` / `image base --dry-run` 打印正确命令（--env-file 顺序：服务先 common 后）。
- [ ] `cd deploy && docker compose --env-file ../config/vortex.generated.env config` 无错、published==target、无 PUBLIC_PORT、无 `is not set` 警告。
- [ ] `deploy/Dockerfile` 遍历安装 + 保 qmt-bridge/--no-build-isolation + 烤入 env + EXPOSE 8765 8766 8767 8768。
- [ ] `vortexctl` source 生成 env、端口对齐、无 legacy 导出（test_vortexctl 绿）。
- [ ] `deploy/vortex.generated.env` 被 gitignore（构建期拷贝产物，非真值源）。
