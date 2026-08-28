#!/usr/bin/env python3
"""
Public smoke test: healthcheck basic behavior
"""
import json
import subprocess
import sys


def test_healthcheck():
    """Test that healthcheck passes and returns expected structure."""
    result = subprocess.run(
        [sys.executable, "-m", "workbench.healthcheck"],
        capture_output=True,
        text=True,
        cwd="."
    )
    assert result.returncode == 0, f"Healthcheck failed: {result.stderr}"

    data = json.loads(result.stdout)
    assert data["status"] == "pass"
    assert "checks" in data
    assert "python" in data["checks"]
    assert "paths" in data["checks"]
    assert "settings" in data["checks"]
    assert data["summary"]["passed"] == 3
    assert data["summary"]["failed"] == 0
    print("Healthcheck test PASSED")


if __name__ == "__main__":
    test_healthcheck()