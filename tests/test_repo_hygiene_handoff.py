from pathlib import Path


def test_readme_product_links():
    text = Path("README.md").read_text(encoding="utf-8")
    for path in ("docs/operator_quickstart.md", "docs/runbooks/", "docs/prm_mature_product_roadmap.md"):
        assert path in text
    assert "PYTHONPATH=src python3 -m pytest tests/ -q" not in text


def test_prm_ux13_handoff_keeps_compatibility_surfaces_untouched():
    text = Path("docs/repo_hygiene_and_archive_plan.md").read_text(encoding="utf-8")
    assert "## PRM-UX-13 Simplification Handoff" in text
    assert "leave untouched" in text
    assert "No delete, move, archive, or rename is authorized" in text
