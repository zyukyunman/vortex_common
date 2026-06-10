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


def test_seed_env_if_missing_creates_from_example(tmp_path):
    ex = tmp_path / ".env.example"
    ex.write_text("VORTEX_X_TOKEN=\n", encoding="utf-8")
    env = tmp_path / ".env"
    assert cli.seed_env_if_missing(env, ex) is True
    assert env.read_text(encoding="utf-8") == "VORTEX_X_TOKEN=\n"


def test_seed_env_noop_when_env_exists(tmp_path):
    ex = tmp_path / ".env.example"
    ex.write_text("A=1\n", encoding="utf-8")
    env = tmp_path / ".env"
    env.write_text("B=2\n", encoding="utf-8")
    assert cli.seed_env_if_missing(env, ex) is False
    assert env.read_text(encoding="utf-8") == "B=2\n"


def test_seed_env_noop_when_no_example(tmp_path):
    env = tmp_path / ".env"
    assert cli.seed_env_if_missing(env, tmp_path / ".env.example") is False
    assert not env.exists()
