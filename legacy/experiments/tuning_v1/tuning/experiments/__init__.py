"""Experiments (simulations to tune). Importing this package registers every module in this folder: one file per experiment."""
import importlib
import pkgutil

for _m in pkgutil.iter_modules(__path__):
    if not _m.name.startswith("_"):
        importlib.import_module(f"{__name__}.{_m.name}")
