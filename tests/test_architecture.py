"""Module boundary checks via tach."""

import subprocess


def test_module_boundaries():
    """Verify all module dependencies conform to tach.toml boundaries."""
    result = subprocess.run(
        ["tach", "check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
