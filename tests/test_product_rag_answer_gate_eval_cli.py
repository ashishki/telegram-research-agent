import subprocess
import sys
from pathlib import Path


def test_answer_gate_cli_accepts_ephemeral_absolute_output_path(tmp_path):
    root = Path(__file__).parents[1]
    output = tmp_path / "answer-gate.json"
    result = subprocess.run(
        [
            sys.executable,
            "tools/product_rag_answer_gate_eval.py",
            "--root",
            ".",
            "--json",
            str(output),
        ],
        cwd=root,
        env={"PYTHONPATH": str(root / "src")},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert output.is_file()
    assert f"output={output}" in result.stdout
