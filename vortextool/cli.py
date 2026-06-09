"""vortex CLI 入口。本阶段只实现 cfg 组；image/run 为后续 Phase。"""
from __future__ import annotations

import argparse
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vortex")
    sub = parser.add_subparsers(dest="group", required=True)
    cfg = sub.add_parser("cfg", help="配置组")
    cfg_sub = cfg.add_subparsers(dest="action", required=True)
    cfg_sub.add_parser("gen").set_defaults(func=_gen)
    cfg_sub.add_parser("check").set_defaults(func=_check)
    cfg_sub.add_parser("list").set_defaults(func=_list)
    cfg_sub.add_parser("ports").set_defaults(func=_ports)
    args = parser.parse_args(argv)
    try:
        return args.func()
    except RegistryError as e:
        print(f"✗ registry.yml 无效 (invalid): {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
