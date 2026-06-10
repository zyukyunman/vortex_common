from pathlib import Path
from vortextool.registry import load_registry
from vortextool.check import check_generated_fresh, scan_forbidden_keys, check_repo_configs
from vortextool.generate import (
    render_env, render_versions, render_services_md, render_architecture_md,
)

REPO = Path(__file__).resolve().parent.parent
REG = load_registry(REPO / "config" / "registry.yml")


def test_generated_fresh_detects_stale(tmp_path):
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
        "TUSHARE_TOKEN=\n",
        encoding="utf-8",
    )
    hits = scan_forbidden_keys(example)
    keys = {h.key for h in hits}
    assert "VORTEX_DATA_PORT" in keys
    assert "VORTEX_WORKSPACE_MOUNT" in keys
    assert "VORTEX_DATA_PUBLIC_PORT" in keys
    assert "TZ" in keys
    assert "TUSHARE_TOKEN" not in keys


def test_generated_fresh_passes_when_current(tmp_path):
    env = tmp_path / "vortex.generated.env"
    versions = tmp_path / "versions.yml"
    services = tmp_path / "services.md"
    arch = tmp_path / "architecture.md"
    env.write_text(render_env(REG), encoding="utf-8")
    versions.write_text(render_versions(REG), encoding="utf-8")
    services.write_text(render_services_md(REG), encoding="utf-8")
    arch.write_text(render_architecture_md(REG), encoding="utf-8")
    problems = check_generated_fresh(REG, env_path=env, versions_path=versions,
                                     services_path=services, architecture_path=arch)
    assert problems == []


def test_export_prefixed_forbidden_key_is_flagged(tmp_path):
    f = tmp_path / ".env.example"
    f.write_text("export VORTEX_DATA_PORT=8765\n", encoding="utf-8")
    keys = {h.key for h in scan_forbidden_keys(f)}
    assert "VORTEX_DATA_PORT" in keys


def test_comment_lines_not_flagged(tmp_path):
    f = tmp_path / ".env.example"
    f.write_text("# VORTEX_DATA_PORT=8765\n   # TZ=X\n", encoding="utf-8")
    assert scan_forbidden_keys(f) == []


def test_check_repo_configs_clean(tmp_path):
    repo = tmp_path / "vortex_x"
    repo.mkdir()
    (repo / ".env.example").write_text("VORTEX_X_TOKEN=\n", encoding="utf-8")
    (repo / "docker-compose.yml").write_text('    ports:\n      - "${A_BIND}:${B_PORT}:${B_PORT}"\n', encoding="utf-8")
    assert check_repo_configs(tmp_path, ["vortex_x"]) == []


def test_check_repo_configs_flags_forbidden_env_and_public_port(tmp_path):
    repo = tmp_path / "vortex_x"
    repo.mkdir()
    (repo / ".env.example").write_text("VORTEX_X_PORT=8765\n", encoding="utf-8")
    (repo / "docker-compose.yml").write_text('      - "${A}:${VORTEX_X_PUBLIC_PORT}:${B}"\n', encoding="utf-8")
    problems = check_repo_configs(tmp_path, ["vortex_x"])
    assert any("VORTEX_X_PORT" in p for p in problems)
    assert any("PUBLIC_PORT" in p for p in problems)


def test_check_repo_configs_skips_missing(tmp_path):
    assert check_repo_configs(tmp_path, ["vortex_nonexist"]) == []


def test_check_repo_configs_extra_composes(tmp_path):
    bad = tmp_path / "deploy-compose.yml"
    bad.write_text('      - "${A}:${VORTEX_DATA_PUBLIC_PORT:-8765}:8765"\n', encoding="utf-8")
    problems = check_repo_configs(tmp_path, [], extra_composes=[bad])
    assert any("PUBLIC_PORT" in p for p in problems)
