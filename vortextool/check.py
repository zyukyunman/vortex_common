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
    r"^\s*(?:export\s+)?(VORTEX_\w*_PORT|VORTEX_\w*_PUBLIC_PORT|VORTEX_\w*_BIND_ADDR|TZ"
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


def check_repo_configs(parent: Path, service_names: list[str],
                       extra_composes: list[Path] | None = None) -> list[str]:
    """扫各服务仓 .env.example(禁用键) + compose(无 PUBLIC_PORT)。缺失文件跳过（CI/隔离环境友好）。"""
    problems: list[str] = []
    composes = list(extra_composes or [])
    for name in service_names:
        repo = Path(parent) / name
        example = repo / ".env.example"
        if example.exists():
            for hit in scan_forbidden_keys(example):
                problems.append(
                    f"{example} 含禁用键 {hit.key}（端口/路径/TZ/绑定归 common）: {hit.line}"
                )
        composes.append(repo / "docker-compose.yml")
    for compose in composes:
        compose = Path(compose)
        if compose.exists() and "PUBLIC_PORT" in compose.read_text(encoding="utf-8"):
            problems.append(f"{compose} 含 PUBLIC_PORT（应删，端口由 registry 单源、内外一致）")
    return problems


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
