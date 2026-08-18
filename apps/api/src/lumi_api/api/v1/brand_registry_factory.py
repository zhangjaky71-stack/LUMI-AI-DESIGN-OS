from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from .brand_registry_adapter import PostgresBrandRegistryService


class PostgresBrandRegistryServiceFactory:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    @contextmanager
    def __call__(self) -> Iterator[PostgresBrandRegistryService]:
        session = self.session_factory()
        try:
            yield PostgresBrandRegistryService(session)
        finally:
            session.close()
