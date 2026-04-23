from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class StorageConfig:
    data_root: Path
    raw_root: Path
    catalog_root: Path
    meta_root: Path
    sqlite_path: Path
    duckdb_path: Path
    silver_root: Path
    audit_root: Path


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    max_workers: int
    compression: str


@dataclass(frozen=True, slots=True)
class StockImportLegacyConfig:
    enabled: bool
    source_root: Path
    files: dict[str, str]


@dataclass(frozen=True, slots=True)
class UniverseConfig:
    core_indices: list[str]
    core_index_dailybasic_supported: list[str]
    core_cffex_futures_selected: list[str]
    core_cffex_options_prefix: list[str]
    core_fx_selected: list[str]
    core_global_indices: list[str]
    stock_import_legacy: StockImportLegacyConfig


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
    return StorageConfig(
        data_root=project_root / str(d.get("data_root", "data")),
        raw_root=project_root / str(d.get("raw_root", "data/raw")),
        catalog_root=project_root / str(d.get("catalog_root", "data/catalog")),
        meta_root=project_root / str(d.get("meta_root", "data/meta")),
        sqlite_path=project_root / str(d.get("sqlite_path", "data/meta/control.sqlite3")),
        duckdb_path=project_root / str(d.get("duckdb_path", "data/meta/warehouse.duckdb")),
        silver_root=project_root / str(d.get("silver_root", "data/silver")),
        audit_root=project_root / str(d.get("audit_root", "data/audit")),
    )


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
    
    legacy_cfg = d.get("stock_import_legacy", {})
    stock_import_legacy = StockImportLegacyConfig(
        enabled=bool(legacy_cfg.get("enabled", False)),
        source_root=Path(str(legacy_cfg.get("source_root", ""))),
        files=legacy_cfg.get("files", {}),
    )

    return UniverseConfig(
        core_indices=[str(x) for x in d.get("core_indices", [])],
        core_index_dailybasic_supported=[str(x) for x in d.get("core_index_dailybasic_supported", [])],
        core_cffex_futures_selected=[str(x) for x in d.get("core_cffex_futures_selected", [])],
        core_cffex_options_prefix=[str(x) for x in d.get("core_cffex_options_prefix", [])],
        core_fx_selected=[str(x) for x in d.get("core_fx_selected", [])],
        core_global_indices=[str(x) for x in d.get("core_global_indices", [])],
        stock_import_legacy=stock_import_legacy,
    )
