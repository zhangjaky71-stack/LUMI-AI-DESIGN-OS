from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from .canvas_document_adapter import PostgresCanvasDocumentService


class PostgresCanvasDocumentServiceFactory:
    """Create one SQLAlchemy Session per Canvas API request."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    @contextmanager
    def __call__(self) -> Iterator[PostgresCanvasDocumentService]:
        session = self.session_factory()
        try:
            yield PostgresCanvasDocumentService(session)
        finally:
            session.close()
