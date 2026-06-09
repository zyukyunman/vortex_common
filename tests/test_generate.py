from pathlib import Path
from vortextool.registry import load_registry
from vortextool.generate import render_env

REPO = Path(__file__).resolve().parent.parent
REG = load_registry(REPO / "config" / "registry.yml")


def test_env_has_ports_and_bind_for_each_service():
    env = render_env(REG)
    assert "VORTEX_DATA_PORT=8765" in env
    assert "VORTEX_BACKTEST_PORT=8766" in env
    assert "VORTEX_QMT_PORT=8767" in env
    assert "VORTEX_TRADER_PORT=8768" in env
    assert "VORTEX_DATA_BIND_ADDR=127.0.0.1" in env
    assert "VORTEX_QMT_BIND_ADDR=127.0.0.1" in env


def test_env_has_common_scalars_and_donotedit_header():
    env = render_env(REG)
    assert env.splitlines()[0].startswith("# DO NOT EDIT")
    assert "TZ=Asia/Shanghai" in env
    assert "VORTEX_NETWORK=vortex-net" in env
    assert "VORTEX_IMAGE_BASE=vortex-base" in env
    assert "VORTEX_IMAGE_APP=vortex" in env


def test_env_excludes_host_var_and_abs_paths():
    env = render_env(REG)
    assert "_HOST=" not in env          # 容器监听是不变量，不进生成 env
    assert "/Users/" not in env         # 机器无关：不烤宿主机绝对路径
    assert "HOST_ROOT" not in env       # 宿主机根由 vortex run 运行时解析
