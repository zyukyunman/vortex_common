"""vortex CLI 入口。本阶段只实现 cfg 组；image/run 为后续 Phase。"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from .registry import load_registry, RegistryError
from .generate import (
    render_env, render_versions, render_services_md, render_architecture_md,
)
from .check import check_generated_fresh  # scan_forbidden_keys 在后续 Phase 接入

REPO = Path(__file__).resolve().parent.parent
REG_PATH = REPO / "config" / "registry.yml"
ENV_PATH = REPO / "config" / "vortex.generated.env"
VERSIONS_PATH = REPO / "deploy" / "versions.yml"
SERVICES_PATH = REPO / "docs" / "reference" / "services.md"
ARCH_PATH = REPO / "docs" / "reference" / "architecture.md"
PARENT = REPO.parent
GEN_ENV = ENV_PATH
DEPLOY_DIR = REPO / "deploy"


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
    # 注：各仓 .env.example 禁用键扫描在后续 Phase（清理那些文件后）接入。
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


def compose_env() -> dict[str, str]:
    """compose 插值所需运行时环境：宿主机 workspace/state 根解析为绝对路径（不烤进 committed env）。"""
    env = dict(os.environ)
    home = env.get("HOME", "")
    env.setdefault("VORTEX_WORKSPACE_HOST_ROOT", f"{home}/vortex/workspace")
    env.setdefault("VORTEX_STATE_HOST_ROOT", f"{home}/vortex/state")
    return env


def build_compose_argv(action: str, svc: str | None, *, dry: bool = False) -> list[str]:
    if action == "deploy":
        return ["docker", "compose", "--env-file", str(GEN_ENV), "up", "-d"]
    repo = PARENT / f"vortex_{svc}"
    base = ["docker", "compose", "--env-file", str(repo / ".env"), "--env-file", str(GEN_ENV)]
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
    return subprocess.run(argv, cwd=str(cwd), env=compose_env()).returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vortex")
    sub = parser.add_subparsers(dest="group", required=True)
    cfg = sub.add_parser("cfg", help="配置组")
    cfg_sub = cfg.add_subparsers(dest="action", required=True)
    cfg_sub.add_parser("gen").set_defaults(func=_gen)
    cfg_sub.add_parser("check").set_defaults(func=_check)
    cfg_sub.add_parser("list").set_defaults(func=_list)
    cfg_sub.add_parser("ports").set_defaults(func=_ports)
    run = sub.add_parser("run", help="运行组")
    run_sub = run.add_subparsers(dest="action", required=True)
    for name in ("up", "down", "logs"):
        p = run_sub.add_parser(name)
        p.add_argument("svc", choices=["data", "backtest", "qmt", "trader"])
        p.add_argument("--dry-run", action="store_true")
    dep = run_sub.add_parser("deploy")
    dep.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.group == "run":
            return _run_compose(args.action, getattr(args, "svc", None), args.dry_run)
        return args.func()
    except RegistryError as e:
        print(f"✗ registry.yml 无效 (invalid): {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
