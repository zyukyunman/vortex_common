"""加载并校验 registry.yml 为内存模型。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


class RegistryError(ValueError):
    """registry.yml 校验失败。"""


@dataclass(frozen=True)
class Service:
    name: str
    port: int
    role: str
    health: str
    repo: str
    ref: str | None
    submodules: bool = False


@dataclass(frozen=True)
class Common:
    tz: str
    default_bind_addr: str
    network: str
    image_base: str
    image_app: str
    workspace_host_root: str
    state_host_root: str
    container_workspace: str
    container_state: str


@dataclass(frozen=True)
class Registry:
    common: Common
    services: tuple[Service, ...]

    def service(self, name: str) -> Service:
        for s in self.services:
            if s.name == name:
                return s
        raise KeyError(name)


def load_registry(path: Path) -> Registry:
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise RegistryError(f"registry.yml 解析失败 (YAML error): {e}") from e
    if not isinstance(data, dict):
        raise RegistryError("registry.yml 顶层必须是映射 (mapping)，含 common 与 services")
    try:
        c = data["common"]
        common = Common(
            tz=c["tz"],
            default_bind_addr=str(c["default_bind_addr"]),
            network=c["network"],
            image_base=c["image"]["base"],
            image_app=c["image"]["app"],
            workspace_host_root=c["workspace_host_root"],
            state_host_root=c["state_host_root"],
            container_workspace=c["container"]["workspace"],
            container_state=c["container"]["state"],
        )
        services = tuple(
            Service(
                name=s["name"],
                port=_parse_port(s["port"], s.get("name", "?")),
                role=s["role"],
                health=s["health"],
                repo=s["repo"],
                ref=(s.get("ref") or None),
                submodules=bool(s.get("submodules", False)),
            )
            for s in data["services"]
        )
    except (KeyError, TypeError) as e:
        raise RegistryError(f"registry.yml 结构缺失或类型错误 (missing/invalid key): {e}") from e
    _validate(services)
    return Registry(common=common, services=services)


def _parse_port(value: object, svc_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RegistryError(f"服务 {svc_name} 端口须为整数 (port must be int): {value!r}")
    if not (1 <= value <= 65535):
        raise RegistryError(f"服务 {svc_name} 端口越界 1..65535 (out of range): {value}")
    return value


def _validate(services: tuple[Service, ...]) -> None:
    names = [s.name for s in services]
    if len(set(names)) != len(names):
        raise RegistryError(f"重复服务名 (duplicate names): {names}")
    ports = [s.port for s in services]
    if len(set(ports)) != len(ports):
        raise RegistryError(f"重复端口 (duplicate ports): {ports}")
    if ports != sorted(ports):
        raise RegistryError(f"端口未升序 (ports not sorted): {ports}")
