from pathlib import Path


def test_prm_ux13_handoff_keeps_compatibility_surfaces_untouched():
    text = (Path(__file__).resolve().parents[1] / "docs" / "repo_hygiene_and_archive_plan.md").read_text(encoding="utf-8")

    assert "## PRM-UX-13 Simplification Handoff" in text
    assert "leave untouched" in text
    assert "No delete, move, archive, or rename is authorized" in text
