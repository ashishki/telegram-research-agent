import subprocess


def test_prm_mat_eval_accepts_synthetic_routing_and_safety_manifests():
    result = subprocess.run(
        ["python3", "tools/prm_mat_eval.py", "--check", "all"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "prm_mat_eval: ok"
