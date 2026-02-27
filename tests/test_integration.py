"""Integration tests: init → insert → DB verification (Step 8)."""

import json
import sqlite3
from pathlib import Path

from click.testing import CliRunner

from konkon.cli import main
from konkon.core.ingestion.raw_db import RawDB
from konkon.core.instance import KONKON_DIR, RAW_DB_NAME


class TestInitInsertWorkflow:
    """End-to-end: konkon init → konkon insert → verify data in raw.db."""

    def test_init_insert_verify_record(self, tmp_path: Path):
        """init → insert text → record exists in raw.db with correct content."""
        runner = CliRunner()
        runner.invoke(main, ["init", str(tmp_path)])

        result = runner.invoke(
            main, ["-C", str(tmp_path), "insert", "hello world"]
        )
        assert result.exit_code == 0
        record_id = result.output.strip()

        # Verify directly via sqlite3
        db_path = tmp_path / KONKON_DIR / RAW_DB_NAME
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT id, content FROM raw_records WHERE id = ?",
            (record_id,),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == record_id
        assert row[1] == "hello world"

    def test_init_insert_with_metadata(self, tmp_path: Path):
        """init → insert with metadata → metadata stored correctly."""
        runner = CliRunner()
        runner.invoke(main, ["init", str(tmp_path)])

        result = runner.invoke(
            main,
            ["-C", str(tmp_path), "insert",
             "-m", "source=notes.md", "-m", "lang=en",
             "some content"],
        )
        assert result.exit_code == 0
        record_id = result.output.strip()

        conn = sqlite3.connect(str(tmp_path / KONKON_DIR / RAW_DB_NAME))
        row = conn.execute(
            "SELECT meta FROM raw_records WHERE id = ?",
            (record_id,),
        ).fetchone()
        conn.close()

        meta = json.loads(row[0])
        assert meta["source"] == "notes.md"
        assert meta["lang"] == "en"

    def test_init_insert_multiple_records_ordered(self, tmp_path: Path):
        """init → insert 3 records → all exist and are ordered by created_at."""
        runner = CliRunner()
        runner.invoke(main, ["init", str(tmp_path)])

        ids = []
        for text in ["first", "second", "third"]:
            result = runner.invoke(
                main, ["-C", str(tmp_path), "insert", text]
            )
            assert result.exit_code == 0
            ids.append(result.output.strip())

        # Read back via RawDB accessor to verify ordering
        db = RawDB(tmp_path / KONKON_DIR / RAW_DB_NAME)
        records = list(db.accessor())
        db.close()

        assert len(records) == 3
        assert [r.id for r in records] == ids
        assert [r.content for r in records] == ["first", "second", "third"]

    def test_insert_without_init_fails(self, tmp_path: Path):
        """insert without init → fails (no project)."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["-C", str(tmp_path), "insert", "hello"]
        )
        assert result.exit_code == 1
