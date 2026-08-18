from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from alembic import op

revision = "20260818_0023"
down_revision = "20260818_0022"
branch_labels = None
depends_on = None

_SNAPSHOT_DIR = Path(__file__).with_name("20260818_0023_sql")
_BREAKPOINT = "-- statement-breakpoint"


def _statements(filename: str) -> Iterable[str]:
    payload = (_SNAPSHOT_DIR / filename).read_text(encoding="utf-8")
    for statement in payload.split(_BREAKPOINT):
        normalized = statement.strip()
        if normalized:
            yield normalized


def _execute(filename: str) -> None:
    connection = op.get_bind()
    for statement in _statements(filename):
        connection.exec_driver_sql(statement)


def upgrade() -> None:
    _execute("up.sql")


def downgrade() -> None:
    _execute("down.sql")
