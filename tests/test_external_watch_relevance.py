from external_watch.relevance import classify

PROFILE={
    "categories":["program","career","ai","isso","benefits","spouse_family"],
    "muted_sources":[], "paused":False,
    "program":"MS Financial Technology and Analytics",
    "career_goals":"AI internships; applied AI roles",
    "ai_interests":"agentic systems; RAG; evals; machine learning",
}


def test_generic_research_or_engineering_is_not_enough():
    item={"title":"Engineering Research Seminar","topics":["Research"],"departments":["Engineering"]}
    assert classify(item, PROFILE)["relevant"] is False


def test_registrar_academic_calendar_is_high_signal_program():
    item={"title":"Late Registration","topics":["Academic Calendar"],"departments":["Office of the Registrar"]}
    result=classify(item, PROFILE)
    assert result["relevant"] is True
    assert "program" in result["categories"]
    assert result["score"] >= 90


def test_ai_requires_specific_signal_or_profile_phrase():
    assert classify({"title":"Machine Learning Colloquium"}, PROFILE)["relevant"] is True
    assert classify({"title":"General Faculty Research Meeting"}, PROFILE)["relevant"] is False


def test_primary_documents_map_to_only_selected_source_category():
    assert classify({"source":"isso","material_text":"International Students and Scholars Office"}, PROFILE)["relevant"] is True
    assert classify({"source":"basic_needs","material_text":"Resource Hub"}, PROFILE)["relevant"] is True
