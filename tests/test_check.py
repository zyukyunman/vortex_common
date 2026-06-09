from pathlib import Path
from vortextool.registry import load_registry
from vortextool.check import check_generated_fresh, scan_forbidden_keys

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
