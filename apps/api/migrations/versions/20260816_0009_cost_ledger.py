from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from alembic import op

revision = "20260816_0009"
down_revision = "20260816_0008"
branch_labels = None
depends_on = None

_SNAPSHOT_DIR = Path(__file__).with_name("20260816_0009_sql")
_UP_FILES = ("up_01.sql", "up_02.sql")
_DOWN_FILES = ("down_02.sql", "down_01.sql")
_BREAKPOINT = "-- statement-breakpoint"


def _statements(files: Iterable[str]) -> Iterable[str]:
    for filename in files:
        payload = (_SNAPSHOT_DIR / filename).read_text(encoding="utf-8")
        for statement in payload.split(_BREAKPOINT):
            normalized = statement.strip()
            if normalized:
                yield normalized


def _execute(files: Iterable[str]) -> None:
    connection = op.get_bind()
    for statement in _statements(files):
        connection.exec_driver_sql(statement)


def upgrade() -> None:
    _execute(_UP_FILES)


def downgrade() -> None:
    _execute(_DOWN_FILES)
