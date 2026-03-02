"""Core data models and exceptions (02_interface_contracts.md)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator, Mapping, Protocol, TypeAlias

# ---------------------------------------------------------
# JSON-safe type definitions
# ---------------------------------------------------------
JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]

# ---------------------------------------------------------
# Exceptions
# ---------------------------------------------------------


class KonkonError(Exception):
    """konkon db base exception."""


class BuildError(KonkonError):
    """Error during build phase."""


class QueryError(KonkonError):
    """Error during query phase."""


class ConfigError(KonkonError):
    """Configuration error (invalid backend, file conflicts, etc.)."""


# ---------------------------------------------------------
# Data models
# ---------------------------------------------------------


@dataclass(frozen=True)
class RawRecord:
    """A single raw record from Raw DB (shallow immutability via frozen=True)."""

    id: str
    created_at: datetime  # UTC-aware
    content: str
    meta: Mapping[str, JSONValue] = field(default_factory=dict)
    updated_at: datetime | None = None  # UTC-aware; None → same as created_at

    @property
    def source_uri(self) -> str | None:
        value = self.meta.get("source_uri")
        return value if isinstance(value, str) else None

    @property
    def content_type(self) -> str | None:
        value = self.meta.get("content_type")
        return value if isinstance(value, str) else None


class RawDataAccessor(Protocol):
    """ACL #1: Safe data supplier that hides Raw DB schema."""

    def __iter__(self) -> Iterator[RawRecord]: ...
    def __len__(self) -> int: ...
    def since(self, timestamp: datetime) -> "RawDataAccessor": ...


@dataclass(frozen=True)
class QueryRequest:
    """ACL #3: Normalized search request from Serving layer."""

    query: str
    params: Mapping[str, JSONValue] = field(default_factory=dict)


@dataclass(frozen=True)
class QueryResult:
    """ACL #3: Normalized result to Serving layer."""

    content: str
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)
