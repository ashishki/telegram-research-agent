from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evals/external_watch/manifest.v1.json"


def test_external_watch_manifest_is_valid_but_not_launch_ready():
    completed = subprocess.run(
        [sys.executable, "tools/validate_external_watch_eval.py", "--manifest", str(MANIFEST), "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["errors"] == []
    assert result["readiness"]["case_count"] == 50
    assert result["readiness"]["shadow_ready"] is False
    assert result["readiness"]["launch_ready"] is False
