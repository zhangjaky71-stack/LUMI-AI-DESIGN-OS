"""PostgreSQL persistence adapters for LUMI domain contracts.

Import ``lumi_api.persistence.models`` before consuming ``Base.metadata`` so all
P0 mappings and query-driven indexes are registered.
"""

from .base import Base

__all__ = ["Base"]
