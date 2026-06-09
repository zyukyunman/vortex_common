from pathlib import Path
import pytest
from vortextool.registry import load_registry, RegistryError

REPO = Path(__file__).resolve().parent.parent
REAL = REPO / "config" / "registry.yml"


def test_loads_real_registry():
    reg = load_registry(REAL)
    names = [s.name for s in reg.services]
    assert names == ["vortex_data", "vortex_backtest", "vortex_qmt", "vortex_trader"]
    assert reg.service("vortex_data").port == 8765
    assert reg.service("vortex_qmt").submodules is True
    assert reg.service("vortex_trader").ref is None      # 预留 = 空
    assert reg.common.tz == "Asia/Shanghai"
    assert reg.common.network == "vortex-net"


def test_rejects_duplicate_ports(tmp_path):
    p = tmp_path / "r.yml"
    p.write_text(
        "common: {tz: X, default_bind_addr: '127.0.0.1', network: n, "
        "image: {base: b, app: a}, workspace_host_root: w, state_host_root: s, "
        "container: {workspace: /workspace, state: /state}}\n"
        "services:\n"
        "  - {name: a, port: 8765, role: r, health: /h, repo: u, ref: main}\n"
        "  - {name: b, port: 8765, role: r, health: /h, repo: u, ref: main}\n",
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="重复端口|duplicate"):
        load_registry(p)


def test_rejects_unsorted_ports(tmp_path):
    p = tmp_path / "r.yml"
    p.write_text(
        "common: {tz: X, default_bind_addr: '127.0.0.1', network: n, "
        "image: {base: b, app: a}, workspace_host_root: w, state_host_root: s, "
        "container: {workspace: /workspace, state: /state}}\n"
        "services:\n"
        "  - {name: a, port: 8766, role: r, health: /h, repo: u, ref: main}\n"
        "  - {name: b, port: 8765, role: r, health: /h, repo: u, ref: main}\n",
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="升序|sorted"):
        load_registry(p)


def test_rejects_malformed_top_level(tmp_path):
    p = tmp_path / "r.yml"
    p.write_text("just a string, not a mapping\n", encoding="utf-8")
    with pytest.raises(RegistryError):
        load_registry(p)


def test_rejects_missing_keys(tmp_path):
    p = tmp_path / "r.yml"
    p.write_text("services: []\n", encoding="utf-8")   # 缺 common
    with pytest.raises(RegistryError):
        load_registry(p)


def test_rejects_duplicate_service_names(tmp_path):
    p = tmp_path / "r.yml"
    p.write_text(
        "common: {tz: X, default_bind_addr: '127.0.0.1', network: n, "
        "image: {base: b, app: a}, workspace_host_root: w, state_host_root: s, "
        "container: {workspace: /workspace, state: /state}}\n"
        "services:\n"
        "  - {name: dup, port: 8765, role: r, health: /h, repo: u, ref: main}\n"
        "  - {name: dup, port: 8766, role: r, health: /h, repo: u, ref: main}\n",
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="重复服务名|duplicate name"):
        load_registry(p)


def test_rejects_out_of_range_port(tmp_path):
    p = tmp_path / "r.yml"
    p.write_text(
        "common: {tz: X, default_bind_addr: '127.0.0.1', network: n, "
        "image: {base: b, app: a}, workspace_host_root: w, state_host_root: s, "
        "container: {workspace: /workspace, state: /state}}\n"
        "services:\n"
        "  - {name: a, port: 99999, role: r, health: /h, repo: u, ref: main}\n",
        encoding="utf-8",
    )
    with pytest.raises(RegistryError, match="越界|out of range"):
        load_registry(p)
