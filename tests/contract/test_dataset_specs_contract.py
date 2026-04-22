from __future__ import annotations

import importlib
import pkgutil

import pytest

import src_data_download.datasets as datasets_pkg
from src_data_download.core.dataset_spec import DatasetSpec


def _iter_dataset_specs():
    for m in pkgutil.iter_modules(datasets_pkg.__path__, datasets_pkg.__name__ + "."):
        mod = importlib.import_module(m.name)
        spec = getattr(mod, "SPEC", None)
        if isinstance(spec, DatasetSpec):
            yield m.name, spec


@pytest.mark.parametrize("name,spec", list(_iter_dataset_specs()))
def test_dataset_spec_contract(name: str, spec: DatasetSpec):
    spec.validate()
    for pk in spec.pk_cols:
        assert pk in (set(spec.required_fields) | set(spec.optional_fields))
