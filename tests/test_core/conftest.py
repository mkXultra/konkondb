"""Shared test fixtures for core tests."""

import pytest
from pathlib import Path

from konkon.core.ingestion.raw_db import RawDB
from konkon.core.ingestion.json_db import JsonDB


@pytest.fixture(params=["sqlite", "json"])
def raw_db(request, tmp_path: Path):
    """Parametrized fixture: runs each test against both backends."""
    if request.param == "sqlite":
        db = RawDB(tmp_path / "raw.db")
    else:
        db = JsonDB(tmp_path / "raw.json")
    yield db
    db.close()
