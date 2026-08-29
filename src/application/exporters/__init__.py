"""Output export strategy adapters and registry (Application Layer)."""

from .base import BaseOutputExporter
from .express_adapter import ExpressExpenseExporter
from .json_adapter import JsonConfigExporter
from .registry import (
    register_exporter,
    get_exporter,
    list_exporters,
)

from .base_target_adapter import BaseTargetAdapter
from .express_target_adapter import ExpressTargetAdapter
from .adapter_registry import TargetAdapterRegistry

__all__ = [
    "BaseOutputExporter",
    "ExpressExpenseExporter",
    "JsonConfigExporter",
    "register_exporter",
    "get_exporter",
    "list_exporters",
    "BaseTargetAdapter",
    "ExpressTargetAdapter",
    "TargetAdapterRegistry",
]
