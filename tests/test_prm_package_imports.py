from __future__ import annotations


def test_research_planner_can_load_without_application_import_cycle():
    from prm.research_planner import assess_research_gaps

    assert callable(assess_research_gaps)


def test_package_keeps_lazy_application_export():
    from prm import PersonalResearchAssistant

    assert PersonalResearchAssistant.__name__ == "PersonalResearchAssistant"
