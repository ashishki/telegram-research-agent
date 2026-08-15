from assistant.retrieval_policy import build_query_rewrites, infer_job_type, select_retrieval_policy


def test_named_project_decision_uses_measured_fallback_vector_policy():
    policy = select_retrieval_policy(
        "Что из материалов про agent reliability применимо к Agent-Runtime-Grid?",
        project_name="Agent-Runtime-Grid",
    )

    assert policy.job_type == "named_project_decision"
    assert policy.vector_policy == "fallback_on_fts_miss"
    assert policy.require_project_name is True


def test_ambiguous_project_requires_clarification_before_retrieval():
    policy = select_retrieval_policy("Что из материалов применимо к моему проекту?")

    assert policy.job_type == "ambiguous_project"
    assert policy.candidate_limit == 0
    assert policy.query_strategy == "clarify_project_before_retrieval"


def test_query_rewrites_are_bounded_and_not_domain_dictionary():
    rewrites = build_query_rewrites("Сравни RAG retrieval vs citation verifier для проекта", job_type="comparison")

    assert rewrites[0].startswith("Сравни")
    assert len(rewrites) <= 4
    assert any("rag" in rewrite for rewrite in rewrites)
