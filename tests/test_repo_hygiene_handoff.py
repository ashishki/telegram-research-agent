from pathlib import Path


def test_readme_product_links():
    text = Path("README.md").read_text(encoding="utf-8")
    for path in ("docs/operator_quickstart.md", "docs/runbooks/", "docs/prm_mature_product_roadmap.md"):
        assert path in text
