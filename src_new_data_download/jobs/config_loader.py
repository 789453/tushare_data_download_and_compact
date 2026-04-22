from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class StorageConfig:
    data_root: Path
    raw_root: Path
    catalog_root: Path
    state_path: Path


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    max_workers: int
    compression: str


@dataclass(frozen=True, slots=True)
class UniverseConfig:
    core_indices: list[str]
    core_index_dailybasic_supported: list[str]
    core_cffex_futures_prefix: list[str]
    core_cffex_options_prefix: list[str]
    core_fx_symbols: list[str]
    core_global_indices: list[str]


def _load_yaml(path: Path) -> dict:
    import yaml

    obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise ValueError(f"YAML 不是 dict: {path}")
    return obj


def load_storage_config(project_root: Path, *, path: Path | None = None) -> StorageConfig:
    p = path or (project_root / "config" / "storage.yaml")
    d = _load_yaml(p)
    data_root = project_root / str(d.get("data_root", "data"))
    raw_root = project_root / str(d.get("raw_root", "data/raw"))
    catalog_root = project_root / str(d.get("catalog_root", "data/catalog"))
    state_path = project_root / str(d.get("state_path", "data/state/download.state.json"))
    return StorageConfig(data_root=data_root, raw_root=raw_root, catalog_root=catalog_root, state_path=state_path)


def load_runtime_config(project_root: Path, *, path: Path | None = None) -> RuntimeConfig:
    p = path or (project_root / "config" / "runtime.yaml")
    d = _load_yaml(p)
    return RuntimeConfig(
        max_workers=int(d.get("max_workers", 4)),
        compression=str(d.get("compression", "zstd")),
    )


def load_universe_config(project_root: Path, *, path: Path | None = None) -> UniverseConfig:
    p = path or (project_root / "config" / "universe.yaml")
    d = _load_yaml(p)
    return UniverseConfig(
        core_indices=[str(x) for x in d.get("core_indices", [])],
        core_index_dailybasic_supported=[str(x) for x in d.get("core_index_dailybasic_supported", [])],
        core_cffex_futures_prefix=[str(x) for x in d.get("core_cffex_futures_prefix", [])],
        core_cffex_options_prefix=[str(x) for x in d.get("core_cffex_options_prefix", [])],
        core_fx_symbols=[str(x) for x in d.get("core_fx_symbols", [])],
        core_global_indices=[str(x) for x in d.get("core_global_indices", [])],
    )
