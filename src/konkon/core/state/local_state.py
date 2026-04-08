"""Local file-backed build state for sqlite/json project mode."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from konkon.core.ingestion.backend import format_datetime, parse_datetime, validate_utc
from konkon.core.state.base import BuildStateSnapshot


class LocalBuildStateStore:
    """Compatibility wrapper over .konkon/last_build."""

    def __init__(self, path: Path, *, build_state_key: str) -> None:
        self._path = path
        self._build_state_key = build_state_key

    def read(self) -> BuildStateSnapshot:
        if not self._path.exists():
            return BuildStateSnapshot(build_state_key=self._build_state_key)
        text = self._path.read_text().strip()
        if not text:
            return BuildStateSnapshot(build_state_key=self._build_state_key)
        checkpoint = parse_datetime(text)
        return BuildStateSnapshot(
            build_state_key=self._build_state_key,
            last_checkpoint=checkpoint,
            last_build_at=checkpoint,
            last_tombstone_at=checkpoint,
        )

    def write_success(
        self,
        *,
        build_started_at: datetime,
        completed_at: datetime,
    ) -> None:
        validate_utc(build_started_at)
        validate_utc(completed_at)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(format_datetime(build_started_at))
