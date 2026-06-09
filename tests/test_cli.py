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


def test_cfg_gen_then_check_clean():
    assert _run("cfg", "gen").returncode == 0
    r = _run("cfg", "check")
    assert r.returncode == 0, r.stdout + r.stderr


import vortextool.cli as cli


def test_cfg_check_detects_stale(tmp_path, monkeypatch):
    # 把生成物路径指向 tmp 并写入过期内容 → check 应返回 1（registry 本身有效）
    monkeypatch.setattr(cli, "ENV_PATH", tmp_path / "vortex.generated.env")
    monkeypatch.setattr(cli, "VERSIONS_PATH", tmp_path / "versions.yml")
    monkeypatch.setattr(cli, "SERVICES_PATH", tmp_path / "services.md")
    monkeypatch.setattr(cli, "ARCH_PATH", tmp_path / "architecture.md")
    cli.ENV_PATH.write_text("stale\n", encoding="utf-8")
    assert cli.main(["cfg", "check"]) == 1


def test_malformed_registry_exits_2_cleanly(tmp_path, monkeypatch, capsys):
    bad = tmp_path / "bad.yml"
    bad.write_text("not a mapping\n", encoding="utf-8")
    monkeypatch.setattr(cli, "REG_PATH", bad)
    rc = cli.main(["cfg", "list"])
    assert rc == 2                          # 干净退出码，非 traceback
    assert "registry.yml 无效" in capsys.readouterr().err


def test_invalid_group_exits_2():
    r = _run("bogus")
    assert r.returncode == 2


def test_cfg_requires_action():
    r = _run("cfg")
    assert r.returncode == 2
