"""Default-off OpenCode Go editorial transport for a local BriefDocument.

This is a product seam, not an activation: unless
``PRM_EDITORIAL_OPENCODE_ENABLED`` is explicitly enabled and a real key is
present, it refuses before any network use. It never chooses a provider by
itself, never reads a default database, and rechecks a typed PA-02 egress
reservation immediately before its one request. The selected archive evidence
(never the raw corpus) is sent for the editorial draft; the model output must
pass :meth:`BriefEditorial.from_dict`, which enforces verbatim source quotes
and rejects new numeric claims.

A configured key is not consent: the caller must supply an
``OpenCodeEditorialAccess`` built from an explicit operator action.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from prm.brief_editorial import BriefEditorial
from prm.briefs import BriefDocument
from prm.capabilities import (
    AuthorizationDecision,
    AuthorizationRequest,
    CapabilityDenied,
    CapabilityGrant,
    CapabilityRegistry,
    ProviderPolicy,
    require_authorized_egress,
)


OPENCODE_EDITORIAL_PROVIDER = "provider_opencode_go"
OPENCODE_EDITORIAL_CAPABILITY = "model.context_egress"
OPENCODE_EDITORIAL_OPERATION = "model_egress"
OPENCODE_EDITORIAL_DATA_CLASS = "private_archive"
OPENCODE_EDITORIAL_PURPOSE = "answer.context"
ENABLED_ENV = "PRM_EDITORIAL_OPENCODE_ENABLED"
MODEL_ENV = "PRM_EDITORIAL_OPENCODE_MODEL"
BASE_URL_ENV = "OPENCODE_GO_BASE_URL"
DEFAULT_BASE_URL = "https://opencode.ai/zen/go/v1"
DEFAULT_MODEL = "mimo-v2.6-pro"
MAX_EVIDENCE = 8

_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,511}$")

EDITORIAL_PROMPT = """You are the editor of one private weekly brief in Russian.
You receive JSON with a topic, period and selected evidence items
({evidence_ref, title, summary}). Write at most 5 editorial stories and return
compact JSON only: {"stories":[{"title","summary","explanation",
"plain_explanation","why_selected","next_step","caveat","anchors":[
{"evidence_ref","quote"}]}],"omitted_refs":[]}.
Rules: each evidence_ref is used or omitted exactly once; every quote is a
verbatim substring (>=16 chars) of that item's summary; never write a digit in
your own prose unless it appears in a chosen quote (safest: keep numbers inside
quotes); a title describes an event and never starts with '@'."""


@dataclass(frozen=True, slots=True)
class OpenCodeEditorialAccess:
    """Typed PA-02 egress access plus a re-reservable budget for retries.

    ``authorization`` is the first sealed reservation. ``registry`` and
    ``request_template`` let the transport reserve a *fresh* decision before
    every additional provider attempt, so a grant with a bounded request count
    cannot be exceeded by an internal retry loop.
    """

    authorization: AuthorizationDecision
    owner_ref: str
    connection_ref: str
    resource_ref: str
    registry: CapabilityRegistry | None = None
    request_template: AuthorizationRequest | None = None
    max_attempts: int = 1

    def __post_init__(self) -> None:
        decision = self.authorization
        if type(decision) is not AuthorizationDecision or not decision.allowed or decision.reservation is None:
            raise ValueError("editorial access requires a sealed allowed reservation")
        for name, value in (("owner_ref", self.owner_ref), ("connection_ref", self.connection_ref), ("resource_ref", self.resource_ref)):
            if not _REF.fullmatch(value):
                raise ValueError(f"invalid {name}")
        if (
            decision.owner_ref != self.owner_ref
            or decision.connection_ref != self.connection_ref
            or decision.resource_ref != self.resource_ref
            or decision.provider_ref != OPENCODE_EDITORIAL_PROVIDER
            or decision.capability != OPENCODE_EDITORIAL_CAPABILITY
            or decision.operation != OPENCODE_EDITORIAL_OPERATION
            or decision.data_class != OPENCODE_EDITORIAL_DATA_CLASS
            or decision.purpose != OPENCODE_EDITORIAL_PURPOSE
        ):
            raise ValueError("editorial access does not match the required typed scope")
        if not isinstance(self.max_attempts, int) or isinstance(self.max_attempts, bool) or not 1 <= self.max_attempts <= 8:
            raise ValueError("max_attempts is out of range")
        if self.max_attempts > 1 and (self.registry is None or self.request_template is None):
            raise ValueError("multi-attempt access requires a re-reservable budget")

    def reserve_attempt(self, *, now: datetime) -> AuthorizationDecision | None:
        """Return the first sealed decision, then a fresh one per extra attempt."""

        if self.registry is None or self.request_template is None:
            return self.authorization
        return self.registry.authorize_and_reserve(self.request_template, now=now)


def editorial_enabled() -> bool:
    return os.environ.get(ENABLED_ENV, "").strip().casefold() in {"1", "true", "yes"}


def _api_key() -> str:
    for env_name in ("OPENCODE_API_KEY",):
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    key_file = os.environ.get("OPENCODE_API_KEY_FILE", "").strip()
    if key_file and Path(key_file).is_file():
        return Path(key_file).read_text(encoding="utf-8").strip()
    return ""


def build_operator_editorial_access(
    *,
    owner_ref: str,
    connection_ref: str,
    resource_ref: str,
    consent: str,
    now: datetime | None = None,
    ttl_minutes: int = 10,
    attempts: int = 1,
    registry: CapabilityRegistry | None = None,
) -> OpenCodeEditorialAccess:
    """Compose the typed reservations from an explicit operator action.

    ``consent`` must be the exact literal acknowledgement so a mis-set flag or a
    stray import can never mint provider egress on its own. ``attempts`` bounds
    the grant's request count so a retry loop cannot exceed it.
    """

    if consent != "enable-opencode-editorial":
        raise ValueError("explicit editorial consent is required")
    if not isinstance(attempts, int) or isinstance(attempts, bool) or not 1 <= attempts <= 8:
        raise ValueError("attempts is out of range")
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    grant = CapabilityGrant(
        grant_id="grant_editorial_opencode",
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        capability=OPENCODE_EDITORIAL_CAPABILITY,
        resource_refs=(resource_ref,),
        operations=(OPENCODE_EDITORIAL_OPERATION,),
        data_classes=(OPENCODE_EDITORIAL_DATA_CLASS,),
        purpose=OPENCODE_EDITORIAL_PURPOSE,
        provider_policy=ProviderPolicy((OPENCODE_EDITORIAL_PROVIDER,), maximum_request_count=attempts),
        issued_at=moment - timedelta(minutes=1),
        expires_at=moment + timedelta(minutes=max(1, ttl_minutes)),
        revision=1,
    )
    active = registry or CapabilityRegistry((grant,))
    template = AuthorizationRequest(
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        capability=OPENCODE_EDITORIAL_CAPABILITY,
        resource_ref=resource_ref,
        operation=OPENCODE_EDITORIAL_OPERATION,
        data_class=OPENCODE_EDITORIAL_DATA_CLASS,
        provider_ref=OPENCODE_EDITORIAL_PROVIDER,
        purpose=OPENCODE_EDITORIAL_PURPOSE,
        operation_ref="operation_editorial_opencode",
    )
    decision = active.authorize_and_reserve(template, now=moment)
    return OpenCodeEditorialAccess(
        decision, owner_ref, connection_ref, resource_ref,
        registry=active, request_template=template, max_attempts=attempts,
    )


def _parse_json(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9]*\s*", "", cleaned)
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()
    for candidate in (cleaned, cleaned.replace("\r", " ").replace("\n", " ")):
        try:
            return json.loads(candidate)
        except Exception:
            match = re.search(r"\{.*\}", candidate, flags=re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    continue
    raise ValueError("unparsable_model_json")


def _validated_base_url() -> str:
    """Only the operator-owned https OpenCode Go host may receive the key."""

    from urllib.parse import urlparse

    url = (os.environ.get(BASE_URL_ENV, DEFAULT_BASE_URL) or DEFAULT_BASE_URL).rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "") not in {"opencode.ai", "api.opencode.ai"}:
        raise ValueError("provider base url must be https://opencode.ai")
    return url


def _call_model(*, prompt: str, payload: Mapping[str, Any], model: str, timeout: int) -> dict[str, Any]:
    try:
        base_url = _validated_base_url()
    except ValueError:
        return {"_error": "invalid_base_url"}
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
        ],
        "temperature": 0,
        "max_tokens": 9000,
        "response_format": {"type": "json_object"},
    }
    request = Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": "application/json",
            "User-Agent": "personal-assistant-editorial/1.0",
            "x-opencode-session": "personal-assistant-editorial",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=max(15, timeout)) as response:  # nosec B310
            return json.loads(response.read())
    except HTTPError as error:
        return {"_error": f"http_error_{error.code}"}
    except URLError as error:
        return {"_error": f"url_error_{type(error.reason).__name__}"}
    except Exception as error:  # pragma: no cover - network dependent
        return {"_error": type(error).__name__}


def _response_text(payload: Mapping[str, Any]) -> str | None:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get("message") if isinstance(choices[0], Mapping) else None
    content = message.get("content") if isinstance(message, Mapping) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [item.get("text") for item in content if isinstance(item, Mapping) and isinstance(item.get("text"), str)]
        return "".join(parts) or None
    return None


def _evidence_payload(document: BriefDocument, question: str) -> dict[str, Any]:
    return {
        "question": question,
        "topic": document.topic,
        "period": document.window.to_dict(),
        "evidence": [
            {"evidence_ref": item.evidence_ref, "title": item.title, "summary": item.summary}
            for item in document.evidence
        ],
    }


def synthesize_opencode_editorial(
    document: BriefDocument,
    *,
    question: str,
    access: OpenCodeEditorialAccess | None,
    model: str | None = None,
    timeout: int = 60,
    attempts: int = 3,
    persona: str = "",
) -> tuple[BriefEditorial | None, Mapping[str, object]]:
    """Draft and validate editorial stories; fail closed on every other path."""

    if not editorial_enabled():
        return None, {"status": "disabled", "provider_egress_attempted": False}
    if type(access) is not OpenCodeEditorialAccess:
        return None, {"status": "authorization_required", "provider_egress_attempted": False}
    if not document.evidence or len(document.evidence) > MAX_EVIDENCE:
        return None, {"status": "context_unavailable", "provider_egress_attempted": False}
    if not _api_key():
        return None, {"status": "provider_unavailable_or_denied", "provider_egress_attempted": False}
    payload = _evidence_payload(document, question)
    resolved_model = model or os.environ.get(MODEL_ENV, DEFAULT_MODEL)
    base_prompt = (persona.strip() + "\n\n" + EDITORIAL_PROMPT) if persona.strip() else EDITORIAL_PROMPT
    feedback = ""
    last: dict[str, object] = {"status": "provider_error", "provider_egress_attempted": True}
    total = min(max(1, int(attempts)), access.max_attempts)
    for attempt in range(1, total + 1):
        # Reserve a fresh, bounded PA-02 decision before every provider request.
        decision = access.authorization if attempt == 1 else access.reserve_attempt(now=datetime.now(timezone.utc))
        if decision is None:
            return None, {**last, "status": "reservation_exhausted", "attempts": attempt - 1}
        try:
            require_authorized_egress(
                decision,
                capability=OPENCODE_EDITORIAL_CAPABILITY,
                provider_ref=OPENCODE_EDITORIAL_PROVIDER,
                data_class=OPENCODE_EDITORIAL_DATA_CLASS,
                owner_ref=access.owner_ref,
                connection_ref=access.connection_ref,
                resource_ref=access.resource_ref,
                purpose=OPENCODE_EDITORIAL_PURPOSE,
            )
        except CapabilityDenied:
            return None, {"status": "provider_unavailable_or_denied", "provider_egress_attempted": False}
        response = _call_model(
            prompt=base_prompt + feedback,
            payload=payload,
            model=resolved_model,
            timeout=timeout,
        )
        if "_error" in response:
            last = {"status": "provider_error", "provider_egress_attempted": True, "error": response["_error"]}
            continue
        choices = response.get("choices")
        finish = str(choices[0].get("finish_reason")) if isinstance(choices, list) and choices else ""
        text = _response_text(response)
        if not text or finish == "length":
            last = {"status": "provider_empty_response", "provider_egress_attempted": True}
            continue
        try:
            if len(text) > 18000:
                raise ValueError("editorial response too large")
            editorial = BriefEditorial.from_dict(_parse_json(text), document.evidence)
            if not editorial.stories or any(not story.plain_explanation for story in editorial.stories):
                raise ValueError("editorial lacks a plain-language continuation")
        except (ValueError, TypeError, RecursionError) as error:
            last = {"status": "editorial_rejected", "provider_egress_attempted": True, "error": str(error)[:160]}
            feedback = (
                "\n\nYour previous reply failed validation: "
                + str(error)[:200]
                + ". Fix exactly this: quotes must be verbatim substrings of the item's "
                "summary (>=16 chars), any digit in your prose must appear in a quote, "
                "and every evidence_ref is used or omitted exactly once."
            )
            continue
        return editorial, {
            "status": "drafted",
            "provider_egress_attempted": True,
            "stories": len(editorial.stories),
            "attempts": attempt,
            "provider": OPENCODE_EDITORIAL_PROVIDER,
        }
    return None, {**last, "attempts": total}
