"""Target System Adapter Strategy Registry.

Provides central registration, dynamic lookup, and factory instantiation of
Destination ERP Target Adapters (e.g. Express OE, SAP, PEAK, HR Portal).
"""

from typing import Dict, Type, Optional, List
from src.infrastructure.core.constants import TargetSystemId
from .base_target_adapter import BaseTargetAdapter
from .express_target_adapter import ExpressTargetAdapter


class TargetAdapterRegistry:
    """
    Central Registry for ERP Destination Target Adapters.
    """
    _registry: Dict[str, Type[BaseTargetAdapter]] = {}

    @classmethod
    def register(cls, target_system_id: str, adapter_cls: Type[BaseTargetAdapter]) -> None:
        """Registers an adapter class for a target_system_id."""
        normalized_id = target_system_id.strip().upper()
        cls._registry[normalized_id] = adapter_cls

    @classmethod
    def get_adapter(cls, target_system_id: Optional[str] = None) -> BaseTargetAdapter:
        """
        Retrieves an instance of the target adapter strategy.
        Defaults to ExpressTargetAdapter if target_system_id is None or 'EXPRESS'.
        """
        sys_id = (target_system_id or TargetSystemId.EXPRESS.value).strip().upper()
        adapter_cls = cls._registry.get(sys_id)
        if not adapter_cls:
            raise KeyError(
                f"Target adapter strategy '{sys_id}' is not registered in TargetAdapterRegistry (Fail-Fast). "
                f"Available adapters: {list(cls._registry.keys())}"
            )
        return adapter_cls()

    @classmethod
    def list_adapters(cls) -> List[str]:
        """Lists all registered target system IDs."""
        return list(cls._registry.keys())


# Auto-register built-in adapters
TargetAdapterRegistry.register(TargetSystemId.EXPRESS.value, ExpressTargetAdapter)
TargetAdapterRegistry.register("EXPRESS", ExpressTargetAdapter)
