from prm.request_plan import build_request_plan
from prm.routing import decide_route


def test_archive_now_stays_local_and_does_not_create_public_query():
    route = decide_route("Что в моём архиве было про agent evals сейчас?").to_dict()
    plan = build_request_plan("Что в моём архиве было про agent evals сейчас?", route)

    assert plan["archive"]["execution"] == "local_only"
    assert plan["public_verification"]["requested"] is False
    assert plan["provider_egress"] is False


def test_current_public_fact_has_preview_but_capability_stays_off():
    route = decide_route("What is the current price of OpenAI API?").to_dict()
    plan = build_request_plan("What is the current price of OpenAI API?", route)

    assert plan["public_verification"]["requested"] is True
    assert plan["public_verification"]["consent_preview_required"] is True
    assert plan["public_verification"]["allowed"] is False
    assert plan["public_verification"]["max_calls"] == 0


def test_private_archive_context_is_never_constructed_as_public_query():
    route = decide_route("В моём Telegram архиве: текущая цена проекта X?").to_dict()
    plan = build_request_plan("В моём Telegram архиве: текущая цена проекта X?", route)

    assert plan["public_verification"]["query"] == ""
    assert plan["public_verification"]["query_redacted"] is True
