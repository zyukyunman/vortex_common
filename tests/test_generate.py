from pathlib import Path
from vortextool.registry import load_registry
from vortextool.generate import render_env
from vortextool.generate import render_versions
import re

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


def test_versions_narrow_fields_and_submodules():
    out = render_versions(REG)
    assert out.splitlines()[0].startswith("# DO NOT EDIT")
    assert "- name: vortex_data" in out
    assert "repo: https://github.com/zyukyunman/vortex_data.git" in out
    assert "ref: main" in out
    assert "submodules: true" in out          # 仅 qmt
    assert "port:" not in out
    assert "role:" not in out
    assert "health:" not in out


def test_versions_empty_ref_is_bare_not_quoted():
    out = render_versions(REG)
    assert re.search(r"name: vortex_trader[\s\S]*?\n\s*ref:\s*\n", out + "\n")
    assert 'ref: ""' not in out
    assert "ref: ''" not in out


from vortextool.generate import render_services_md, render_architecture_md


def test_services_md_table_has_all_services():
    md = render_services_md(REG)
    assert md.splitlines()[0].startswith("# ")
    for name, port in [("vortex_data", "8765"), ("vortex_backtest", "8766"),
                       ("vortex_qmt", "8767"), ("vortex_trader", "8768")]:
        assert name in md and port in md
    assert "数据底座" in md and "预留" in md


def test_architecture_md_is_mermaid_with_nodes():
    md = render_architecture_md(REG)
    assert "```mermaid" in md
    assert "vortex-data" in md and ":8765" in md
    assert "vortex-trader" in md and ":8768" in md
