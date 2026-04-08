"""Shared build-state types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, Protocol

from konkon.core.models import JSONValue


@dataclass(frozen=True)
class BuildStateSnapshot:
    """Snapshot of build progress for a logical build pipeline."""

    build_state_key: str
    last_checkpoint: datetime | None = None
    last_build_at: datetime | None = None
    last_tombstone_at: datetime | None = None
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)


class BuildStateStore(Protocol):
    """Persistence contract for build checkpoints."""

    def read(self) -> BuildStateSnapshot: ...

    def write_success(
        self,
        *,
        build_started_at: datetime,
        completed_at: datetime,
    ) -> None: ...
