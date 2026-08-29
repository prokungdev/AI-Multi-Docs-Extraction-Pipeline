"""Output export strategy adapters and registry (Application Layer)."""

from .base import BaseOutputExporter
from .express_adapter import ExpressExpenseExporter
from .json_adapter import JsonConfigExporter
from .registry import (
    register_exporter,
    get_exporter,
    list_exporters,
)

__all__ = [
    "BaseOutputExporter",
    "ExpressExpenseExporter",
    "JsonConfigExporter",
    "register_exporter",
    "get_exporter",
    "list_exporters",
]
