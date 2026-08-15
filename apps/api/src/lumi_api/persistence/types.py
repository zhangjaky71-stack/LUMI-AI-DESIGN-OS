# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from sqlalchemy.types import UserDefinedType


class VectorType(UserDefinedType[list[float]]):
    """PostgreSQL pgvector type without coupling schema code to pgvector-python.

    Runtime adapters may register pgvector codecs later. The schema only requires
    the database extension and the SQL type itself.
    """

    cache_ok = True

    def __init__(self, dimensions: int | None = None) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_: object) -> str:
        return "vector" if self.dimensions is None else f"vector({self.dimensions})"
