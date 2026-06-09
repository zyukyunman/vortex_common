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
