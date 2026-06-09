from pathlib import Path
import vortextool.cli as cli

COMMON = Path(cli.__file__).resolve().parent.parent
GEN = COMMON / "config" / "vortex.generated.env"
PARENT = COMMON.parent


def test_run_up_dev_argv_order_and_envfiles():
    argv = cli.build_compose_argv("up", "data", dry=True)
    assert argv[:2] == ["docker", "compose"]
    i_svc = argv.index(str(PARENT / "vortex_data" / ".env"))
    i_common = argv.index(str(GEN))
    assert i_svc < i_common
    assert "up" in argv and "-d" in argv and "--build" in argv


def test_run_deploy_uses_generated_env():
    argv = cli.build_compose_argv("deploy", None, dry=True)
    assert "--env-file" in argv and str(GEN) in argv
    assert "up" in argv and "-d" in argv
    assert "--build" not in argv


def test_run_up_resolves_host_root_abs(monkeypatch):
    monkeypatch.setenv("HOME", "/home/tester")
    env = cli.compose_env()
    assert env["VORTEX_WORKSPACE_HOST_ROOT"] == "/home/tester/vortex/workspace"
    assert env["VORTEX_STATE_HOST_ROOT"] == "/home/tester/vortex/state"
    assert "~" not in env["VORTEX_WORKSPACE_HOST_ROOT"]
