from __future__ import annotations

import asyncio
from typing import cast
from uuid import uuid4

import asyncpg
import pytest

from lumi_worker_media.video_generation_artifacts import (
    _ensure_branch,
    _ensure_edge,
    _ensure_file,
    _ensure_provenance,
)


class _ConflictConnection:
    def __init__(self, fetch_values: list[object]) -> None:
        self.fetch_values = list(fetch_values)
        self.executed = 0

    async def execute(self, query: str, *args: object) -> None:
        del query, args
        self.executed += 1

    async def fetchval(self, query: str, *args: object) -> object:
        del query, args
        return self.fetch_values.pop(0)


def test_branch_identity_drift_fails_closed() -> None:
    async def run() -> None:
        connection = _ConflictConnection([None])
        with pytest.raises(RuntimeError, match="VIDEO_ARTIFACT_BRANCH_IDENTITY_CONFLICT"):
            await _ensure_branch(
                cast(asyncpg.Connection, connection),
                branch_id=uuid4(),
                organization_id=uuid4(),
                project_id=uuid4(),
                artifact_id=uuid4(),
            )
        assert connection.executed == 1

    asyncio.run(run())


def test_file_identity_drift_fails_closed() -> None:
    async def run() -> None:
        connection = _ConflictConnection([None])
        with pytest.raises(RuntimeError, match="VIDEO_ARTIFACT_FILE_CONFLICT"):
            await _ensure_file(
                cast(asyncpg.Connection, connection),
                file_id=uuid4(),
                organization_id=uuid4(),
                artifact_version_id=uuid4(),
                bucket="lumi-assets",
                object_key="generated/video/v1/org/project/shot.mp4",
                checksum="a" * 64,
                mime_type="video/mp4",
            )
        assert connection.executed == 1

    asyncio.run(run())


def test_provenance_identity_drift_fails_closed() -> None:
    async def run() -> None:
        connection = _ConflictConnection([None])
        with pytest.raises(RuntimeError, match="VIDEO_ARTIFACT_PROVENANCE_CONFLICT"):
            await _ensure_provenance(
                cast(asyncpg.Connection, connection),
                provenance_id=uuid4(),
                organization_id=uuid4(),
                artifact_version_id=uuid4(),
                source_id=uuid4(),
                operation="video.generate.shot",
                metadata={"provider": "openai"},
            )
        assert connection.executed == 1

    asyncio.run(run())


def test_edge_identity_drift_fails_closed_after_parent_validation() -> None:
    async def run() -> None:
        parent_id = uuid4()
        connection = _ConflictConnection([parent_id, None])
        with pytest.raises(RuntimeError, match="VIDEO_ARTIFACT_EDGE_CONFLICT"):
            await _ensure_edge(
                cast(asyncpg.Connection, connection),
                edge_id=uuid4(),
                organization_id=uuid4(),
                from_version_id=parent_id,
                to_version_id=uuid4(),
                edge_type="COMPOSED_FROM",
                metadata={"ordinal": 1},
            )
        assert connection.executed == 1

    asyncio.run(run())
