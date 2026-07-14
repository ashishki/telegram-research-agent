"""Deterministic reader-value gates for Brief/Atlas report surfaces.

IRX-11 keeps this evaluator separate from the historical Markdown checks in
``output.report_quality``.  It inspects structured sidecars first, proves
semantic visual/HTML parity second, and returns independent dimensions instead
of one gameable aggregate score.
"""

from __future__ import annotations

import re
from collections import Counter
from html.parser import HTMLParser
from typing import Any, Mapping, Sequence

from output.report_quality import (
    READER_VALUE_POLICY_MODES,
    READER_VALUE_POLICY_VERSION,
    READER_VALUE_WARN_ONLY_V1,
    REPORT_QUALITY_V2_SCHEMA_VERSION,
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
)
from output.report_visuals import (
    ReportVisualValidationError,
    render_report_visual,
    validate_report_visual,
)
from output.reporting_period import ReportingPeriodError, resolve_reporting_period


QUALITY_DIMENSIONS = (
    "structural_validity",
    "evidence_validity",
    "editorial_quality",
    "personalization_quality",
    "visual_quality",
    "project_usefulness",
    "radar_completeness",
)
QUALITY_SURFACES = frozenset({"weekly_brief", "knowledge_atlas"})
QUALITY_STATUSES = frozenset({"pass", "warning", "fail", "not_applicable"})
QUALITY_SEVERITIES = frozenset({"none", SEVERITY_WARNING, SEVERITY_CRITICAL})
DELIVERY_DECISIONS = frozenset(
    {"allow", "allow_with_warnings", "require_partial", "block"}
)

_ROOT_FIELDS = {
    "schema_version",
    "policy_version",
    "policy_mode",
    "surface",
    "run_id",
    "reporting_week",
    "dimensions",
    "summary",
}
_DIMENSION_FIELDS = {"name", "status", "severity", "findings"}
_FINDING_FIELDS = {
    "code",
    "dimension",
    "severity",
    "affected_item",
    "evidence",
    "reader_impact_ru",
    "repair_hint_ru",
}
_SUMMARY_FIELDS = {
    "overall_status",
    "delivery_decision",
    "partial",
    "critical_count",
    "warning_count",
    "failed_dimensions",
}
_CODE_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+(?:[-‑][A-Za-zА-Яа-яЁё0-9]+)*")
_ALPHA_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+(?:[-‑][A-Za-zА-Яа-яЁё]+)*")
_INTERNAL_REF_RE = re.compile(
    r"\b(?:atom|brief|canonical[-_]thread|claim|evidence|feedback|permission|"
    r"project[-_]action|reaction|run|signal|source|thread):[A-Za-z0-9]",
    re.IGNORECASE,
)
_INTERNAL_ENUM_RE = re.compile(
    r"\b(?:build_allowed|context_only|decision_grade|focused_experiment|"
    r"no_candidate|primary_action|rank_changed|rank_unchanged)\b",
    re.IGNORECASE,
)
_INTERNAL_TARGET_ID_RE = re.compile(
    r"\b(?:action|read|try|feedback|missing-feedback)-\d+(?:-[a-z0-9]+)+\b",
    re.IGNORECASE,
)
_INTERNAL_RUN_ID_RE = re.compile(r"\btra-weekly-[A-Za-z0-9._-]+\b")
_INTERNAL_PATH_RE = re.compile(r"(?:^|\s)(?:/srv/|data/|docs/|src/|tests/)")
_GENERIC_ACTION_RE = re.compile(
    r"^(?:изучить|исследовать|проверить|проанализировать|продолжить наблюдение|"
    r"наблюдать|разобраться|сделать анализ|review|monitor|investigate)(?:\s+"
    r"(?:подробнее|дальше|сигнал|тему|это|вопрос))?[.!]?$",
    re.IGNORECASE,
)
_SHARED_MATURITY = {
    "single_source",
    "repeated_signal",
    "multi_channel",
    "primary_verified",
    "externally_corroborated",
    "decision_grade",
    "unknown",
}
_BRIEF_VISUALS = {
    "decision_matrix",
    "reaction_funnel",
    "project_impact",
    "radar_gate",
}
_ATLAS_VISUALS = {
    "knowledge_graph",
    "thread_timeline",
    "source_thread_heatmap",
    "evidence_maturity",
}
_MAX_HTML_CHARS = 4_000_000
_MAX_FINDINGS = 128
_MAX_INSPECTED_ITEMS = 200
_STYLE_BLOCK_RE = re.compile(
    r"<style\b[^>]*>(.*?)</style\s*>",
    re.IGNORECASE | re.DOTALL,
)
_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_CSS_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_CSS_IMPORT_RE = re.compile(r"@import\b[^;]*(?:;|$)", re.IGNORECASE)
_CSS_HIDDEN_DECL_RE = re.compile(
    r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)"
    r"(?:\s*!important)?\s*(?:;|$)",
    re.IGNORECASE,
)
_SIMPLE_CSS_SELECTOR_RE = re.compile(
    r"(?P<tag>[A-Za-z][A-Za-z0-9-]*|\*)?"
    r"(?P<qualifiers>(?:[.#][A-Za-z_][A-Za-z0-9_-]*)*)"
)
_CSS_QUALIFIER_RE = re.compile(r"([.#])([A-Za-z_][A-Za-z0-9_-]*)")

_HiddenCssSelector = tuple[str | None, str | None, frozenset[str]]


class ReaderQualityContractError(ValueError):
    """Raised when a ``report_quality.v2`` result is not internally valid."""


def _hidden_css_selectors(
    html: str,
) -> tuple[
    tuple[_HiddenCssSelector, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    selectors: list[_HiddenCssSelector] = []
    unsupported: list[str] = []
    imports: list[str] = []
    for style_match in _STYLE_BLOCK_RE.finditer(html):
        stylesheet = _CSS_COMMENT_RE.sub("", style_match.group(1))
        imports.extend(
            " ".join(match.group(0).split())[:180]
            for match in _CSS_IMPORT_RE.finditer(stylesheet)
        )
        for rule_match in _CSS_RULE_RE.finditer(stylesheet):
            if _CSS_HIDDEN_DECL_RE.search(rule_match.group(2)) is None:
                continue
            for raw_selector in rule_match.group(1).split(","):
                value = " ".join(raw_selector.split())
                parsed = _parse_hidden_css_selector(value)
                if parsed is None:
                    unsupported.append(value[:180] or "empty_selector")
                else:
                    selectors.append(parsed)
    return (
        tuple(dict.fromkeys(selectors)),
        tuple(sorted(set(unsupported))),
        tuple(sorted(set(imports))),
    )


def _parse_hidden_css_selector(value: str) -> _HiddenCssSelector | None:
    match = _SIMPLE_CSS_SELECTOR_RE.fullmatch(value)
    if match is None:
        return None
    tag = match.group("tag")
    if tag == "*":
        tag = None
    qualifiers = _CSS_QUALIFIER_RE.findall(match.group("qualifiers"))
    ids = [token for prefix, token in qualifiers if prefix == "#"]
    classes = frozenset(token for prefix, token in qualifiers if prefix == ".")
    if len(ids) > 1 or (tag is None and not ids and not classes):
        return None
    return (tag.casefold() if tag else None, ids[0] if ids else None, classes)


def _matches_hidden_css_selector(
    selector: _HiddenCssSelector,
    *,
    tag: str,
    element_id: str,
    classes: set[str],
) -> bool:
    expected_tag, expected_id, expected_classes = selector
    return (
        (expected_tag is None or expected_tag == tag.casefold())
        and (expected_id is None or expected_id == element_id)
        and expected_classes.issubset(classes)
    )


class _ReaderHtmlAudit(HTMLParser):
    _BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th"}
    _HIDDEN_TAGS = {"style", "script", "template", "title"}
    _VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(
        self,
        *,
        hidden_css_selectors: Sequence[_HiddenCssSelector] = (),
        unsupported_hidden_css: Sequence[str] = (),
        stylesheet_imports: Sequence[str] = (),
    ) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden_css_selectors = tuple(hidden_css_selectors)
        self.unsupported_hidden_css = tuple(unsupported_hidden_css)
        self.stylesheet_imports = tuple(stylesheet_imports)
        self.has_doctype = False
        self.lang = ""
        self.visible_parts: list[str] = []
        self.visual_markers: list[dict[str, str]] = []
        self.hidden_visual_markers: list[dict[str, str]] = []
        self.visible_visual_components: list[
            tuple[dict[str, str], tuple[tuple[object, ...], ...]]
        ] = []
        self.element_ids: Counter[str] = Counter()
        self.stylesheet_links: list[str] = []
        self.script_count = 0
        self.open_details = 0
        self.svg_count = 0
        self.partial_banner = False
        self.blank_table_cells = 0
        self.blocks: list[str] = []
        self._hidden_depth = 0
        self._attribute_visibility_stack: list[tuple[str, bool]] = []
        self._css_visibility_stack: list[tuple[str, bool]] = []
        self._details_stack: list[dict[str, int | bool]] = []
        self._summary_owner_stack: list[int | None] = []
        self._block_stack: list[tuple[str, list[str]]] = []
        self._visual_capture_stack: list[dict[str, Any]] = []

    def handle_decl(self, decl: str) -> None:
        if decl.strip().casefold().startswith("doctype html"):
            self.has_doctype = True

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = {str(key): str(value or "") for key, value in attrs}
        token = ("start", tag, tuple(sorted(values.items())))
        for capture in self._visual_capture_stack:
            capture["tokens"].append(token)
            if tag not in self._VOID_TAGS:
                capture["depth"] += 1
        if tag == "html":
            self.lang = values.get("lang", "")
        if tag == "script":
            self.script_count += 1
        if tag == "link" and "stylesheet" in {
            token.casefold() for token in values.get("rel", "").split()
        }:
            self.stylesheet_links.append(values.get("href", "missing")[:500])
        if values.get("id"):
            self.element_ids[values["id"]] += 1
        classes = set(values.get("class", "").split())
        style = values.get("style", "").casefold()
        attribute_hidden = (
            "hidden" in values
            or "inert" in values
            or values.get("aria-hidden", "").casefold() == "true"
            or re.search(
                r"(?:^|;)\s*display\s*:\s*none(?:\s*!important)?\s*(?:;|$)", style
            )
            is not None
            or re.search(
                r"(?:^|;)\s*visibility\s*:\s*hidden(?:\s*!important)?\s*(?:;|$)",
                style,
            )
            is not None
        )
        css_hidden = any(
            _matches_hidden_css_selector(
                selector,
                tag=tag,
                element_id=values.get("id", ""),
                classes=classes,
            )
            for selector in self.hidden_css_selectors
        )
        if tag not in self._VOID_TAGS:
            self._attribute_visibility_stack.append((tag, attribute_hidden))
            self._css_visibility_stack.append((tag, css_hidden))
        if tag in self._HIDDEN_TAGS:
            self._hidden_depth += 1
        if tag == "details":
            closed = "open" not in values
            self._details_stack.append({"closed": closed, "summary_depth": 0})
            if not closed:
                self.open_details += 1
        elif tag == "summary":
            owner = len(self._details_stack) - 1 if self._details_stack else None
            self._summary_owner_stack.append(owner)
            if owner is not None:
                self._details_stack[owner]["summary_depth"] = (
                    int(self._details_stack[owner]["summary_depth"]) + 1
                )
        current_visible = self._is_visual_visible() and not (
            tag in self._VOID_TAGS and (attribute_hidden or css_hidden)
        )
        if current_visible and (
            "brief-v2__partial" in classes or "run-status-partial" in classes
        ):
            self.partial_banner = True
        if tag == "svg" and current_visible:
            self.svg_count += 1
        if values.get("data-irx-visual") == "true":
            if current_visible:
                self.visual_markers.append(values)
                capture = {
                    "marker": dict(values),
                    "tokens": [token],
                    "depth": 0 if tag in self._VOID_TAGS else 1,
                }
                if capture["depth"]:
                    self._visual_capture_stack.append(capture)
                else:
                    self.visible_visual_components.append(
                        (dict(values), tuple(capture["tokens"]))
                    )
            else:
                self.hidden_visual_markers.append(values)
        if tag in self._BLOCK_TAGS and self._is_visible():
            self._block_stack.append((tag, []))

    def handle_endtag(self, tag: str) -> None:
        completed: list[dict[str, Any]] = []
        for capture in self._visual_capture_stack:
            capture["tokens"].append(("end", tag))
            if tag not in self._VOID_TAGS:
                capture["depth"] -= 1
            if capture["depth"] == 0:
                completed.append(capture)
        for capture in completed:
            self._visual_capture_stack.remove(capture)
            self.visible_visual_components.append(
                (dict(capture["marker"]), tuple(capture["tokens"]))
            )
        if tag in self._BLOCK_TAGS and self._block_stack:
            index = next(
                (
                    position
                    for position in range(len(self._block_stack) - 1, -1, -1)
                    if self._block_stack[position][0] == tag
                ),
                None,
            )
            if index is not None:
                block_tag, parts = self._block_stack.pop(index)
                text = " ".join(parts).strip()
                if text:
                    self.blocks.append(text)
                elif block_tag in {"td", "th"}:
                    self.blank_table_cells += 1
        if tag == "summary" and self._summary_owner_stack:
            owner = self._summary_owner_stack.pop()
            if owner is not None and owner < len(self._details_stack):
                self._details_stack[owner]["summary_depth"] = max(
                    0,
                    int(self._details_stack[owner]["summary_depth"]) - 1,
                )
        elif tag == "details" and self._details_stack:
            self._details_stack.pop()
        if tag in self._HIDDEN_TAGS and self._hidden_depth:
            self._hidden_depth -= 1
        if tag not in self._VOID_TAGS and self._attribute_visibility_stack:
            index = next(
                (
                    position
                    for position in range(
                        len(self._attribute_visibility_stack) - 1,
                        -1,
                        -1,
                    )
                    if self._attribute_visibility_stack[position][0] == tag
                ),
                None,
            )
            if index is not None:
                del self._attribute_visibility_stack[index:]
        if tag not in self._VOID_TAGS and self._css_visibility_stack:
            index = next(
                (
                    position
                    for position in range(len(self._css_visibility_stack) - 1, -1, -1)
                    if self._css_visibility_stack[position][0] == tag
                ),
                None,
            )
            if index is not None:
                del self._css_visibility_stack[index:]

    def handle_data(self, data: str) -> None:
        for capture in self._visual_capture_stack:
            capture["tokens"].append(("data", data))
        if not self._is_visible() or not data.strip():
            return
        clean = " ".join(data.split())
        self.visible_parts.append(clean)
        for _tag, parts in self._block_stack:
            parts.append(clean)

    def handle_comment(self, data: str) -> None:
        for capture in self._visual_capture_stack:
            capture["tokens"].append(("comment", data))

    def _is_visible(self) -> bool:
        return (
            self._hidden_depth == 0
            and not any(hidden for _tag, hidden in self._attribute_visibility_stack)
            and all(
                not bool(details["closed"]) or int(details["summary_depth"]) > 0
                for details in self._details_stack
            )
        )

    def _is_visual_visible(self) -> bool:
        return self._is_visible() and not any(
            hidden for _tag, hidden in self._css_visibility_stack
        )

    @property
    def visible_text(self) -> str:
        return " ".join(self.visible_parts)

    @property
    def visible_word_count(self) -> int:
        return len(_WORD_RE.findall(self.visible_text))


def reader_visible_word_count(rendered_html: str) -> int:
    """Return the IRX-11 initial-visible word count used by blocking gates."""

    html = str(rendered_html or "")
    if len(html) > _MAX_HTML_CHARS:
        raise ReaderQualityContractError("rendered HTML exceeds reader audit limit")
    hidden_css, unsupported_hidden_css, stylesheet_imports = _hidden_css_selectors(html)
    if unsupported_hidden_css or stylesheet_imports:
        raise ReaderQualityContractError(
            "rendered HTML uses CSS visibility rules that cannot be counted safely"
        )
    audit = _ReaderHtmlAudit(
        hidden_css_selectors=hidden_css,
        unsupported_hidden_css=unsupported_hidden_css,
        stylesheet_imports=stylesheet_imports,
    )
    try:
        audit.feed(html)
        audit.close()
    except (RecursionError, ValueError) as exc:
        raise ReaderQualityContractError("rendered HTML cannot be audited") from exc
    return audit.visible_word_count


def evaluate_reader_report_quality(
    sidecar: Mapping[str, Any],
    rendered_html: str,
    *,
    policy_mode: str,
    manifest: Mapping[str, Any] | None = None,
    surface: str | None = None,
) -> dict[str, Any]:
    """Evaluate one reader artifact without a model, clock, score, or mutation."""

    if policy_mode not in READER_VALUE_POLICY_MODES:
        raise ReaderQualityContractError(
            f"unsupported reader quality policy: {policy_mode}"
        )
    safe_sidecar: Mapping[str, Any] = sidecar if isinstance(sidecar, Mapping) else {}
    resolved_surface = _surface(safe_sidecar, surface)
    if resolved_surface not in QUALITY_SURFACES:
        raise ReaderQualityContractError(
            "reader quality surface must be weekly_brief or knowledge_atlas"
        )
    try:
        return _evaluate(
            safe_sidecar,
            str(rendered_html or ""),
            policy_mode=policy_mode,
            manifest=manifest if isinstance(manifest, Mapping) else None,
            surface=resolved_surface,
        )
    except Exception as exc:  # A gate failure is data, never a silent pass.
        finding = _finding(
            "structural_validity",
            "evaluator.failed",
            SEVERITY_CRITICAL,
            "report_quality.v2",
            [exc.__class__.__name__],
            "Проверка читательской ценности не завершилась, поэтому качеству выпуска нельзя доверять.",
            "Исправить детерминированный evaluator и повторить проверку на том же sidecar и HTML.",
        )
        report = _build_report(
            safe_sidecar,
            surface=resolved_surface,
            policy_mode=policy_mode,
            findings=[finding],
            not_applicable=(
                {"project_usefulness", "radar_completeness"}
                if resolved_surface == "knowledge_atlas"
                else set()
            ),
        )
        validate_reader_report_quality(report)
        return report


def validate_reader_report_quality(report: Mapping[str, Any]) -> None:
    """Validate exact fields, dimension independence, counts, and decision."""

    if not isinstance(report, Mapping):
        raise ReaderQualityContractError("reader quality report must be an object")
    _exact(report, _ROOT_FIELDS, "root")
    if report.get("schema_version") != REPORT_QUALITY_V2_SCHEMA_VERSION:
        raise ReaderQualityContractError("reader quality schema_version mismatch")
    if report.get("policy_version") != READER_VALUE_POLICY_VERSION:
        raise ReaderQualityContractError("reader quality policy_version mismatch")
    mode = report.get("policy_mode")
    if mode not in READER_VALUE_POLICY_MODES:
        raise ReaderQualityContractError("reader quality policy_mode mismatch")
    if report.get("surface") not in QUALITY_SURFACES:
        raise ReaderQualityContractError("reader quality surface is invalid")
    for field in ("run_id", "reporting_week"):
        if not isinstance(report.get(field), str) or len(str(report[field])) > 180:
            raise ReaderQualityContractError(f"reader quality {field} is invalid")

    dimensions = report.get("dimensions")
    if not isinstance(dimensions, list) or len(dimensions) != len(QUALITY_DIMENSIONS):
        raise ReaderQualityContractError("reader quality dimensions are incomplete")
    if [
        item.get("name") if isinstance(item, Mapping) else None for item in dimensions
    ] != list(QUALITY_DIMENSIONS):
        raise ReaderQualityContractError("reader quality dimension order mismatch")

    all_findings: list[Mapping[str, Any]] = []
    not_applicable_dimensions: set[str] = set()
    for dimension in dimensions:
        if not isinstance(dimension, Mapping):
            raise ReaderQualityContractError(
                "reader quality dimension must be an object"
            )
        _exact(dimension, _DIMENSION_FIELDS, f"dimension.{dimension.get('name')}")
        name = str(dimension["name"])
        if dimension.get("status") not in QUALITY_STATUSES:
            raise ReaderQualityContractError(f"{name} status is invalid")
        if dimension.get("severity") not in QUALITY_SEVERITIES:
            raise ReaderQualityContractError(f"{name} severity is invalid")
        findings = dimension.get("findings")
        if not isinstance(findings, list) or len(findings) > _MAX_FINDINGS:
            raise ReaderQualityContractError(f"{name} findings are invalid")
        for finding in findings:
            _validate_finding(finding, expected_dimension=name)
            all_findings.append(finding)
        expected_status, expected_severity = _dimension_state(findings)
        if dimension.get("status") == "not_applicable":
            not_applicable_dimensions.add(name)
            if findings or dimension.get("severity") != "none":
                raise ReaderQualityContractError(
                    f"{name} not_applicable dimension cannot contain findings"
                )
        elif (
            dimension.get("status") != expected_status
            or dimension.get("severity") != expected_severity
        ):
            raise ReaderQualityContractError(f"{name} aggregate mismatch")

    if len(all_findings) > _MAX_FINDINGS:
        raise ReaderQualityContractError("reader quality finding budget exceeded")
    expected_not_applicable = (
        {"project_usefulness", "radar_completeness"}
        if report.get("surface") == "knowledge_atlas"
        else set()
    )
    if not_applicable_dimensions != expected_not_applicable:
        raise ReaderQualityContractError(
            "reader quality not_applicable dimensions mismatch"
        )
    if [dict(item) for item in all_findings] != _dedupe_findings(all_findings):
        raise ReaderQualityContractError(
            "reader quality findings are duplicated or out of deterministic order"
        )

    summary = report.get("summary")
    if not isinstance(summary, Mapping):
        raise ReaderQualityContractError("reader quality summary must be an object")
    _exact(summary, _SUMMARY_FIELDS, "summary")
    if not isinstance(summary.get("partial"), bool):
        raise ReaderQualityContractError(
            "reader quality summary.partial must be boolean"
        )
    for field in ("critical_count", "warning_count"):
        count = summary.get(field)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ReaderQualityContractError(
                f"reader quality summary.{field} must be a non-negative integer"
            )
    critical_count = sum(
        finding["severity"] == SEVERITY_CRITICAL for finding in all_findings
    )
    warning_count = sum(
        finding["severity"] == SEVERITY_WARNING for finding in all_findings
    )
    failed_dimensions = [
        str(dimension["name"])
        for dimension in dimensions
        if dimension["status"] == "fail"
    ]
    expected_status = (
        "fail" if critical_count else "warning" if warning_count else "pass"
    )
    expected_decision = _delivery_decision(
        str(mode),
        partial=bool(summary["partial"]),
        critical_count=critical_count,
        warning_count=warning_count,
    )
    expected = {
        "overall_status": expected_status,
        "delivery_decision": expected_decision,
        "partial": bool(summary["partial"]),
        "critical_count": critical_count,
        "warning_count": warning_count,
        "failed_dimensions": failed_dimensions,
    }
    if dict(summary) != expected:
        raise ReaderQualityContractError("reader quality summary aggregate mismatch")


def _evaluate(
    sidecar: Mapping[str, Any],
    rendered_html: str,
    *,
    policy_mode: str,
    manifest: Mapping[str, Any] | None,
    surface: str,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    html = rendered_html
    if len(html) > _MAX_HTML_CHARS:
        _add(
            findings,
            _finding(
                "structural_validity",
                "html.byte_budget_exceeded",
                SEVERITY_CRITICAL,
                "rendered_html",
                [f"characters={len(html)}", f"limit={_MAX_HTML_CHARS}"],
                "Слишком большой HTML нельзя надёжно проверить или быстро прочитать.",
                "Сократить reader surface и вынести технические детали в закрытые раскрытия или Audit Explorer.",
            ),
        )
        html = html[:_MAX_HTML_CHARS]
    hidden_css, unsupported_hidden_css, stylesheet_imports = _hidden_css_selectors(html)
    audit = _ReaderHtmlAudit(
        hidden_css_selectors=hidden_css,
        unsupported_hidden_css=unsupported_hidden_css,
        stylesheet_imports=stylesheet_imports,
    )
    try:
        audit.feed(html)
        audit.close()
    except (RecursionError, ValueError) as exc:
        _add(
            findings,
            _finding(
                "structural_validity",
                "html.parse_failed",
                SEVERITY_CRITICAL,
                "rendered_html",
                [exc.__class__.__name__],
                "HTML не прошёл детерминированный разбор, поэтому его читательская форма неизвестна.",
                "Исправить HTML и повторить проверку до публикации.",
            ),
        )
    _common_findings(sidecar, audit, surface=surface, findings=findings)
    not_applicable: set[str] = set()
    if surface == "weekly_brief":
        _brief_findings(
            sidecar,
            html,
            audit,
            manifest=manifest,
            findings=findings,
        )
    elif surface == "knowledge_atlas":
        _atlas_findings(sidecar, html, audit, findings=findings)
        not_applicable.update({"project_usefulness", "radar_completeness"})
    else:
        _add(
            findings,
            _finding(
                "structural_validity",
                "surface.unknown",
                SEVERITY_CRITICAL,
                "surface",
                [
                    str(
                        sidecar.get("surface")
                        or sidecar.get("artifact_type")
                        or "missing"
                    )
                ],
                "Неизвестную читательскую поверхность нельзя оценить по правильным правилам.",
                "Передать явный surface weekly_brief или knowledge_atlas.",
            ),
        )
    report = _build_report(
        sidecar,
        surface=surface,
        policy_mode=policy_mode,
        findings=findings,
        not_applicable=not_applicable,
    )
    validate_reader_report_quality(report)
    return report


def _common_findings(
    sidecar: Mapping[str, Any],
    audit: _ReaderHtmlAudit,
    *,
    surface: str,
    findings: list[dict[str, Any]],
) -> None:
    declared = _surface(sidecar, None)
    if declared != surface:
        _add(
            findings,
            _finding(
                "structural_validity",
                "surface.identity_mismatch",
                SEVERITY_CRITICAL,
                "surface",
                [f"declared={declared}", f"evaluated={surface}"],
                "Отчёт проверяется правилами другой поверхности, поэтому результат недостоверен.",
                "Согласовать surface/artifact_type с выбранным quality policy.",
            ),
        )
    mode = str(sidecar.get("period_mode") or "")
    period = _period(sidecar)
    week = str(period.get("reporting_week") or sidecar.get("reporting_week") or "")
    generated_at = str(sidecar.get("generated_at") or "")
    if mode not in {"completed_iso_week", "explicit_iso_week"}:
        _add(
            findings,
            _finding(
                "structural_validity",
                "period.not_completed_week",
                SEVERITY_CRITICAL,
                "period_mode",
                [mode or "missing", week or "missing"],
                "Незавершённый или скользящий период нельзя выдавать за недельный reader report.",
                "Сформировать отчёт по последней полностью завершённой ISO-неделе или явно выбранной завершённой неделе.",
            ),
        )
    else:
        try:
            resolved = resolve_reporting_period(
                generated_at=generated_at,
                reporting_week=week if mode == "explicit_iso_week" else None,
                period_mode=mode,
            )
            expected = resolved.to_dict()
            for field in (
                "reporting_week",
                "analysis_period_start",
                "analysis_period_end",
            ):
                if str(period.get(field) or "") != expected[field]:
                    raise ReportingPeriodError(f"{field} mismatch")
        except (ReportingPeriodError, TypeError, ValueError) as exc:
            _add(
                findings,
                _finding(
                    "structural_validity",
                    "period.identity_invalid",
                    SEVERITY_CRITICAL,
                    "reporting_period",
                    [exc.__class__.__name__, str(exc)[:180]],
                    "Период, неделя и время генерации противоречат друг другу.",
                    "Пересобрать period identity через общий ReportingPeriod и не исправлять поля вручную.",
                ),
            )
    partial = _is_partial(sidecar)
    run_status = str(sidecar.get("run_status") or "")
    if run_status not in {"complete", "partial"}:
        _add(
            findings,
            _finding(
                "structural_validity",
                "status.run_status_invalid",
                SEVERITY_CRITICAL,
                "run_status",
                [run_status or "missing"],
                "Нельзя определить, является ли reader report полным или частичным.",
                "Передать terminal run_status complete/partial из authoritative run identity.",
            ),
        )
    if not isinstance(sidecar.get("partial"), bool):
        _add(
            findings,
            _finding(
                "structural_validity",
                "status.partial_type_invalid",
                SEVERITY_CRITICAL,
                "partial",
                [type(sidecar.get("partial")).__name__],
                "Строковое или отсутствующее partial-состояние может скрыть ограниченный выпуск.",
                "Передать точный boolean partial и согласовать его с terminal run_status.",
            ),
        )
    if run_status in {"complete", "partial"} and partial != (run_status == "partial"):
        _add(
            findings,
            _finding(
                "structural_validity",
                "status.partial_mismatch",
                SEVERITY_CRITICAL,
                "run_status",
                [f"run_status={run_status}", f"partial={partial}"],
                "Статус выпуска скрывает или выдумывает частичность данных.",
                "Согласовать run_status, partial и явные причины частичного выпуска.",
            ),
        )
    if not audit.has_doctype:
        _add(
            findings,
            _finding(
                "structural_validity",
                "html.standalone_missing",
                SEVERITY_CRITICAL,
                "rendered_html",
                ["doctype_missing"],
                "Артефакт не является самостоятельным HTML-документом.",
                "Рендерить полный документ с HTML doctype и локальными стилями.",
            ),
        )
    if audit.lang.casefold().split("-", 1)[0] != "ru":
        _add(
            findings,
            _finding(
                "editorial_quality",
                "language.document_not_russian",
                SEVERITY_CRITICAL,
                "html.lang",
                [audit.lang or "missing"],
                "Читатель и вспомогательные технологии не получают русский язык документа.",
                "Установить lang=ru и сохранить исключения только для имён продуктов, кода и источников.",
            ),
        )
    if audit.open_details:
        _add(
            findings,
            _finding(
                "structural_validity",
                "disclosure.open_by_default",
                SEVERITY_CRITICAL,
                "details[open]",
                [f"count={audit.open_details}"],
                "Технические или доказательные детали перегружают первый проход чтения.",
                "Убрать атрибут open; основные решения оставить вне раскрытий.",
            ),
        )
    if audit.unsupported_hidden_css:
        _add(
            findings,
            _finding(
                "visual_quality",
                "html.hidden_css_selector_unsupported",
                SEVERITY_CRITICAL,
                "style",
                list(audit.unsupported_hidden_css[:8]),
                "CSS скрывает элементы селектором, который детерминированная проверка не может связать с читательской поверхностью.",
                "Использовать простой class/id/tag selector для честного служебного скрытия либо удалить правило до quality evaluation.",
            ),
        )
    if audit.stylesheet_links or audit.stylesheet_imports or audit.script_count:
        presentation_evidence = [
            *(f"stylesheet_link={value}" for value in audit.stylesheet_links[:4]),
            *(f"css_import={value}" for value in audit.stylesheet_imports[:4]),
        ]
        if audit.script_count:
            presentation_evidence.append(f"script_count={audit.script_count}")
        _add(
            findings,
            _finding(
                "structural_validity",
                "html.external_presentation_forbidden",
                SEVERITY_CRITICAL,
                "rendered_html",
                presentation_evidence,
                "Внешний CSS или script может скрыть, заменить или изменить проверенную читательскую поверхность после статической проверки.",
                "Встроить детерминированные локальные стили без @import и удалить script/stylesheet links до публикации standalone HTML.",
            ),
        )
    duplicate_ids = sorted(
        element_id for element_id, count in audit.element_ids.items() if count > 1
    )
    if duplicate_ids:
        _add(
            findings,
            _finding(
                "structural_validity",
                "html.dom_id_duplicate",
                SEVERITY_CRITICAL,
                "rendered_html[id]",
                [
                    f"{element_id}:count={audit.element_ids[element_id]}"
                    for element_id in duplicate_ids[:8]
                ],
                "Повторяющиеся DOM/SVG ID ломают подписи, ссылки и доступность визуальных компонентов.",
                "Пересобрать документ с уникальными namespaced component_id и проверить все aria/id references.",
            ),
        )
    if audit.blank_table_cells:
        _add(
            findings,
            _finding(
                "structural_validity",
                "metrics.blank_cell",
                SEVERITY_CRITICAL,
                "table",
                [f"blank_cells={audit.blank_table_cells}"],
                "Пустые ячейки смешивают ноль, неизвестное и недоступное состояние.",
                "Заполнить ячейки явным нулём, неизвестным или недоступным состоянием.",
            ),
        )
    visible = audit.visible_text
    internal = _visible_internal_token(visible)
    if internal:
        _add(
            findings,
            _finding(
                "editorial_quality",
                "reader.internal_token_visible",
                SEVERITY_CRITICAL,
                "initial_visible_copy",
                [internal],
                "Внутренний идентификатор, enum или путь заставляет читателя разбирать реализацию.",
                "Перевести значение в читательский смысл и оставить технический токен только в sidecar/Audit Explorer.",
            ),
        )
    ratio, alpha_count = _russian_ratio(visible)
    if alpha_count >= 20 and ratio < 0.45:
        _add(
            findings,
            _finding(
                "editorial_quality",
                "language.russian_copy_insufficient",
                SEVERITY_CRITICAL,
                "initial_visible_copy",
                [f"russian_word_ratio={ratio:.3f}", f"alpha_words={alpha_count}"],
                "Основной текст нельзя быстро прочитать как русский операторский отчёт.",
                "Переписать навигацию, объяснения, действия, статусы и пустые состояния по-русски; не переводить код и имена продуктов искусственно.",
            ),
        )
    partial_copy_visible = (
        re.search(
            r"\b(?:частичн\w*|ограниченн\w*)\b",
            visible.casefold(),
        )
        is not None
    )
    if partial and (not audit.partial_banner or not partial_copy_visible):
        _add(
            findings,
            _finding(
                "structural_validity",
                "status.partial_banner_missing",
                SEVERITY_CRITICAL,
                "partial_banner",
                [
                    "partial=true",
                    f"visible_banner={audit.partial_banner}",
                    f"visible_partial_copy={partial_copy_visible}",
                ],
                "Ограниченный выпуск выглядит полным и может привести к чрезмерно сильному решению.",
                "Показать заметный factual partial banner до тезиса и назвать недоступные данные.",
            ),
        )


def _brief_findings(
    sidecar: Mapping[str, Any],
    html: str,
    audit: _ReaderHtmlAudit,
    *,
    manifest: Mapping[str, Any] | None,
    findings: list[dict[str, Any]],
) -> None:
    is_v2 = sidecar.get("schema_version") == "split_ai_report.v2"
    if not is_v2:
        _add(
            findings,
            _finding(
                "structural_validity",
                "brief.legacy_reader_surface",
                SEVERITY_CRITICAL,
                "schema_version",
                [str(sidecar.get("schema_version") or "missing")],
                "Legacy Brief не гарантирует недельный тезис, персонализацию, visuals и reader-safe copy.",
                "Оставить V1 в warn-only режиме и использовать отдельный split_ai_report.v2 preview до rollout gate.",
            ),
        )
    else:
        contract_valid = False
        try:
            from output.weekly_intelligence_brief_v2 import (
                render_weekly_intelligence_brief_v2_html,
                validate_weekly_intelligence_brief_v2,
            )

            validate_weekly_intelligence_brief_v2(sidecar, manifest=manifest)
            contract_valid = True
        except Exception as exc:
            errors = getattr(exc, "errors", ())
            evidence = [str(item)[:240] for item in list(errors)[:4]] or [
                exc.__class__.__name__
            ]
            _add(
                findings,
                _finding(
                    "structural_validity",
                    "brief.contract_invalid",
                    SEVERITY_CRITICAL,
                    "split_ai_report.v2",
                    evidence,
                    "Sidecar не соответствует закрытому Brief V2 contract и не может считаться полным reader report.",
                    "Исправить указанные поля в детерминированном builder, затем повторить contract и quality validation.",
                ),
            )
        if contract_valid:
            expected_html = render_weekly_intelligence_brief_v2_html(
                sidecar,
                manifest=manifest,
            )
            if html != expected_html:
                _add(
                    findings,
                    _finding(
                        "structural_validity",
                        "brief.html_parity_mismatch",
                        SEVERITY_CRITICAL,
                        "rendered_html",
                        [
                            f"actual_characters={len(html)}",
                            f"expected_characters={len(expected_html)}",
                        ],
                        "HTML не совпадает с детерминированным reader projection этого sidecar.",
                        "Перерендерить документ из неизменённого validated sidecar; не исправлять HTML вручную.",
                    ),
                )

    signals = _mapping_items(sidecar.get("signals"))
    if len(signals) > 3:
        _limit_finding(findings, "brief.signal_limit", "signals", len(signals), 3)
    thesis = _mapping(sidecar.get("weekly_thesis"))
    if not _text(thesis.get("title")) or not _text(
        thesis.get("plain_language_summary")
    ):
        _add(
            findings,
            _finding(
                "editorial_quality",
                "brief.thesis_missing",
                SEVERITY_CRITICAL,
                "weekly_thesis",
                ["title_or_summary_missing"],
                "Без одного явного тезиса выпуск превращается в список несвязанных карточек.",
                "Добавить один доказательный тезис, простое объяснение и личную значимость.",
            ),
        )
    thesis_refs = _strings(thesis.get("evidence_refs"))
    if is_v2 and thesis and not thesis_refs:
        _missing_evidence_finding(
            findings, "brief.thesis_evidence_missing", "weekly_thesis"
        )

    matrix = _mapping(sidecar.get("decision_matrix"))
    ignore_rows = _mapping_items(matrix.get("ignore"))
    has_defer = any(row.get("emphasis") == "explicit_defer" for row in ignore_rows)
    actions_value = sidecar.get("actions")
    actions_map = _mapping(actions_value)
    primary = _mapping(actions_map.get("primary"))
    secondary = _mapping_items(actions_map.get("secondary"))
    legacy_actions = (
        _mapping_items(actions_value) if isinstance(actions_value, list) else []
    )
    actions = ([primary] if primary else []) + secondary + legacy_actions
    if len(secondary) > 2 or len(actions) > 3:
        _limit_finding(findings, "brief.action_limit", "actions", len(actions), 3)
    if signals and not primary and is_v2:
        _add(
            findings,
            _finding(
                "editorial_quality",
                "brief.primary_action_missing",
                SEVERITY_CRITICAL,
                "actions.primary",
                [f"signals={len(signals)}"],
                "У выпуска с сигналами нет одного понятного следующего действия.",
                "Выбрать ровно одно основное действие из host-ordered act signal и сохранить критерии приёмки.",
            ),
        )
    if signals and not has_defer:
        _add(
            findings,
            _finding(
                "editorial_quality",
                "brief.defer_decision_missing",
                SEVERITY_CRITICAL,
                "decision_matrix.ignore",
                [f"ignore_items={len(ignore_rows)}"],
                "Без явного «не делать / отложить» отчёт подталкивает только к добавлению работы.",
                "Добавить одно доказательное explicit_defer решение в матрицу.",
            ),
        )
    action_titles = [
        _text(action.get("title")) for action in actions if _text(action.get("title"))
    ]
    normalized_titles = [_normalize_text(title) for title in action_titles]
    if len(normalized_titles) != len(set(normalized_titles)):
        _add(
            findings,
            _finding(
                "editorial_quality",
                "brief.action_duplicate",
                SEVERITY_CRITICAL,
                "actions",
                [f"duplicates={len(normalized_titles) - len(set(normalized_titles))}"],
                "Повторяющиеся действия создают ложное ощущение нескольких независимых решений.",
                "Оставить одно действие, а остальные карточки ссылать на него или дать им иной проверяемый результат.",
            ),
        )
    generic = [
        title for title in action_titles if _GENERIC_ACTION_RE.fullmatch(title.strip())
    ]
    if generic:
        _add(
            findings,
            _finding(
                "editorial_quality",
                "brief.action_generic",
                SEVERITY_CRITICAL,
                "actions",
                generic[:4],
                "Общий совет не сообщает, что именно сделать и как понять результат.",
                "Назвать объект изменения, ограниченный шаг и проверяемый критерий приёмки.",
            ),
        )
    action_bodies: list[tuple[str, str]] = []
    for index, action in enumerate(actions[:_MAX_INSPECTED_ITEMS]):
        for field in (
            "summary",
            "next_step",
            "suggested_change",
            "body",
            "description",
        ):
            value = _text(action.get(field))
            if value:
                action_bodies.append((f"actions[{index}].{field}", value))
        for criterion_index, criterion in enumerate(
            _strings(action.get("acceptance_criteria"))
        ):
            action_bodies.append(
                (
                    f"actions[{index}].acceptance_criteria[{criterion_index}]",
                    criterion,
                )
            )
    normalized_bodies: dict[str, list[str]] = {}
    for path, body in action_bodies:
        normalized_bodies.setdefault(_normalize_text(body), []).append(path)
    duplicate_bodies = [
        f"{normalized}:{','.join(paths[:4])}"
        for normalized, paths in sorted(normalized_bodies.items())
        if normalized and len(paths) > 1
    ]
    if duplicate_bodies:
        _add(
            findings,
            _finding(
                "editorial_quality",
                "brief.action_body_duplicate",
                SEVERITY_CRITICAL,
                "actions",
                duplicate_bodies[:6],
                "Уникальные заголовки скрывают одинаковое шаблонное содержание действий.",
                "Дать каждому действию собственный объект, ограниченный шаг и проверяемый результат.",
            ),
        )
    generic_bodies = [
        f"{path}:{body}"
        for path, body in action_bodies
        if _GENERIC_ACTION_RE.fullmatch(body.strip())
    ]
    if generic_bodies:
        _add(
            findings,
            _finding(
                "editorial_quality",
                "brief.action_body_generic",
                SEVERITY_CRITICAL,
                "actions",
                generic_bodies[:6],
                "Тело действия остаётся общим советом без наблюдаемого результата.",
                "Назвать конкретный объект, ограничение и критерий проверки результата.",
            ),
        )
    visible_normalized = _normalize_text(audit.visible_text)
    repeated_visible = [
        title
        for title in action_titles
        if len(_WORD_RE.findall(title)) >= 3
        and visible_normalized.count(_normalize_text(title)) > 1
    ]
    if repeated_visible:
        _add(
            findings,
            _finding(
                "editorial_quality",
                "brief.action_repeated_visible",
                SEVERITY_CRITICAL,
                "initial_visible_copy",
                repeated_visible[:4],
                "Одна и та же рекомендация занимает несколько читательских мест.",
                "Показывать полную формулировку один раз; в матрице и signal card использовать короткую ссылку на действие.",
            ),
        )
    for index, signal in enumerate(signals[:_MAX_INSPECTED_ITEMS]):
        if not _text(signal.get("do_not_do")):
            _add(
                findings,
                _finding(
                    "editorial_quality",
                    "brief.do_not_do_missing",
                    SEVERITY_CRITICAL,
                    f"signals[{index}].do_not_do",
                    [str(signal.get("signal_id") or index)],
                    "Сигнал не ограничивает действие и повышает риск лишней работы.",
                    "Добавить конкретное reader-facing «чего не делать» для этого сигнала.",
                ),
            )
        if not _strings(signal.get("evidence_refs")):
            _missing_evidence_finding(
                findings,
                "brief.signal_evidence_missing",
                f"signals[{index}]",
            )
    _brief_personalization(sidecar, findings=findings)
    _brief_projects(sidecar, findings=findings)
    _brief_radar(sidecar, manifest=manifest, findings=findings)
    _visual_findings(
        sidecar,
        html,
        audit,
        required_types=_BRIEF_VISUALS,
        minimum_meaningful=3,
        findings=findings,
    )
    count = audit.visible_word_count
    if count > 1_100:
        severity = SEVERITY_CRITICAL
        code = "brief.visible_length_critical"
        hint = "Сократить initial reader copy ниже 1 100 слов; детали перенести в закрытые disclosures."
    elif count > 900:
        severity = SEVERITY_WARNING
        code = "brief.visible_length_warning"
        hint = "Сжать initial reader copy к целевым 700–900 словам."
    elif is_v2 and count < 700:
        severity = SEVERITY_WARNING
        code = "brief.visible_length_short"
        hint = "Добавить недостающий читательский смысл, не заполняя выпуск общими советами."
    else:
        severity = ""
        code = ""
        hint = ""
    if severity:
        _add(
            findings,
            _finding(
                "editorial_quality",
                code,
                severity,
                "initial_visible_copy",
                [f"visible_words={count}", "target=700..900", "hard_max=1100"],
                "Объём выпуска не соответствует пяти–семиминутному reader surface.",
                hint,
            ),
        )
    metrics = _mapping(sidecar.get("content_metrics"))
    if metrics and metrics.get("visible_word_count") != count:
        _add(
            findings,
            _finding(
                "structural_validity",
                "html.word_count_parity_mismatch",
                SEVERITY_CRITICAL,
                "content_metrics.visible_word_count",
                [f"sidecar={metrics.get('visible_word_count')}", f"measured={count}"],
                "Sidecar сообщает другой объём, чем фактически видит читатель.",
                "Считать visible words из детерминированного HTML и записывать точное значение.",
            ),
        )


def _brief_personalization(
    sidecar: Mapping[str, Any],
    *,
    findings: list[dict[str, Any]],
) -> None:
    reaction = _mapping(sidecar.get("reaction_effect"))
    if not reaction:
        _add(
            findings,
            _finding(
                "personalization_quality",
                "personalization.reaction_receipt_missing",
                SEVERITY_CRITICAL,
                "reaction_effect",
                ["missing"],
                "Читатель не видит, использовались ли личные реакции и что означало их отсутствие.",
                "Добавить точный reaction_personalization receipt; ноль реакций описать как неизвестное, а не отрицательное состояние.",
            ),
        )
    else:
        try:
            from output.reaction_personalization import validate_reaction_effect

            validate_reaction_effect(reaction)
        except Exception as exc:
            _add(
                findings,
                _finding(
                    "personalization_quality",
                    "personalization.reaction_receipt_invalid",
                    SEVERITY_CRITICAL,
                    "reaction_effect",
                    [exc.__class__.__name__, str(exc)[:180]],
                    "Нельзя доказать, как личные реакции повлияли на выпуск.",
                    "Использовать точный manifest-bound reaction receipt без пересчёта в renderer.",
                ),
            )
        period = _period(sidecar)
        expected_identity = {
            "run_id": str(sidecar.get("run_id") or ""),
            "reporting_week": _reporting_week(sidecar),
            "analysis_period_start": str(period.get("analysis_period_start") or ""),
            "analysis_period_end": str(period.get("analysis_period_end") or ""),
        }
        identity_mismatches = [
            f"{field}:actual={reaction.get(field)}:expected={expected}"
            for field, expected in expected_identity.items()
            if field in reaction and str(reaction.get(field) or "") != expected
        ]
        if identity_mismatches:
            _add(
                findings,
                _finding(
                    "personalization_quality",
                    "personalization.reaction_identity_mismatch",
                    SEVERITY_CRITICAL,
                    "reaction_effect",
                    identity_mismatches,
                    "Персонализация относится к другому запуску или периоду.",
                    "Использовать exact run/period reaction receipt текущего sidecar без соседнего fallback.",
                ),
            )
        if reaction.get("snapshot_status") != "complete" or reaction.get("status") in {
            "partial",
            "unavailable",
        }:
            severity = SEVERITY_WARNING if _is_partial(sidecar) else SEVERITY_CRITICAL
            _add(
                findings,
                _finding(
                    "personalization_quality",
                    "personalization.reaction_unavailable",
                    severity,
                    "reaction_effect.snapshot_status",
                    [str(reaction.get("snapshot_status") or "missing")],
                    "Персонализация по реакциям неполна и не должна выглядеть как подтверждённый нулевой интерес.",
                    "Сохранить выпуск partial и явно назвать недоступный snapshot; не начислять отрицательный вес.",
                ),
            )
    feedback = _mapping(sidecar.get("feedback_effect"))
    if sidecar.get("schema_version") == "split_ai_report.v2" and not feedback:
        _add(
            findings,
            _finding(
                "personalization_quality",
                "personalization.feedback_receipt_missing",
                SEVERITY_CRITICAL,
                "feedback_effect",
                ["missing"],
                "Неизвестно, какие подтверждённые события обратной связи были учтены или оставлены без изменения.",
                "Добавить детерминированный feedback effect receipt с applied, unchanged и requires-code состояниями.",
            ),
        )


def _brief_projects(
    sidecar: Mapping[str, Any],
    *,
    findings: list[dict[str, Any]],
) -> None:
    actions = _mapping_items(sidecar.get("project_actions"))
    if sidecar.get("schema_version") != "split_ai_report.v2":
        legacy_rows = _mapping_items(
            _mapping(sidecar.get("decision_cockpit")).get("project_impact")
        )
        nonspecific = [
            str(index)
            for index, row in enumerate(legacy_rows)
            if not _text(row.get("project_name"))
            or not _text(row.get("affected_component"))
            or not _text(row.get("suggested_change") or row.get("suggested_change_ru"))
        ]
        if nonspecific:
            _add(
                findings,
                _finding(
                    "project_usefulness",
                    "project.legacy_impact_not_specific",
                    SEVERITY_CRITICAL,
                    "decision_cockpit.project_impact",
                    [f"nonspecific_rows={','.join(nonspecific[:8])}"],
                    "Общее совпадение с темой выдано за проектное действие без названного проекта и компонента.",
                    "Оставить честный ноль либо передать подтверждённое IRX-9 действие с проектом, компонентом, изменением, файлами и критериями.",
                ),
            )
    if len(actions) > 2:
        _limit_finding(
            findings, "project.action_limit", "project_actions", len(actions), 2
        )
    required_text = (
        "project_name",
        "affected_component",
        "suggested_change",
        "risk",
    )
    for index, action in enumerate(actions[:_MAX_INSPECTED_ITEMS]):
        missing = [field for field in required_text if not _text(action.get(field))]
        if not _strings(action.get("likely_files")):
            missing.append("likely_files")
        if not _strings(action.get("acceptance_criteria")):
            missing.append("acceptance_criteria")
        if missing:
            _add(
                findings,
                _finding(
                    "project_usefulness",
                    "project.action_not_specific",
                    SEVERITY_CRITICAL,
                    f"project_actions[{index}]",
                    missing,
                    "Проектное действие нельзя выполнить как ограниченную PR-sized задачу.",
                    "Назвать проект, компонент, изменение, нормализованные файлы, критерии приёмки и риск.",
                ),
            )
        if not _strings(action.get("evidence_refs")):
            _missing_evidence_finding(
                findings,
                "project.action_evidence_missing",
                f"project_actions[{index}]",
                dimension="project_usefulness",
            )


def _brief_radar(
    sidecar: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any] | None,
    findings: list[dict[str, Any]],
) -> None:
    radar = _mapping(sidecar.get("mvp_radar"))
    state = str(radar.get("reader_state") or "missing")
    authoritative = state in {"available", "no_candidate"}
    if authoritative:
        try:
            from output.mvp_radar_reader import validate_mvp_radar_reader_projection

            validate_mvp_radar_reader_projection(radar, manifest=manifest)
        except Exception as exc:
            _add(
                findings,
                _finding(
                    "radar_completeness",
                    "radar.authority_invalid",
                    SEVERITY_CRITICAL,
                    "mvp_radar",
                    [exc.__class__.__name__, str(exc)[:180]],
                    "Radar-досье не доказало принадлежность текущему запуску и не может разрешать действие.",
                    "Загрузить mvp_radar_reader.v1 через текущий manifest и exact binding/checksum validation.",
                ),
            )
        if str(radar.get("reporting_week") or "") and str(
            radar.get("reporting_week")
        ) != _reporting_week(sidecar):
            _add(
                findings,
                _finding(
                    "radar_completeness",
                    "radar.period_mismatch",
                    SEVERITY_CRITICAL,
                    "mvp_radar.reporting_week",
                    [str(radar.get("reporting_week")), _reporting_week(sidecar)],
                    "Решение Radar относится к другому периоду.",
                    "Использовать только exact same-run Radar reader для периода Brief.",
                ),
            )
    else:
        severity = SEVERITY_WARNING if _is_partial(sidecar) else SEVERITY_CRITICAL
        _add(
            findings,
            _finding(
                "radar_completeness",
                "radar.unavailable",
                severity,
                "mvp_radar.reader_state",
                [state],
                "Решение по кандидату отсутствует или недостоверно.",
                "Оставить выпуск явно partial и показать причину; не подставлять соседний или legacy Radar файл.",
            ),
        )
    decision = str(radar.get("reader_decision") or "")
    if decision in {"build_allowed", "focused_experiment"} and not _mapping_items(
        radar.get("matched_external_proof")
    ):
        _add(
            findings,
            _finding(
                "radar_completeness",
                "radar.permission_without_proof",
                SEVERITY_CRITICAL,
                "mvp_radar.reader_decision",
                [decision, "matched_external_proof=0"],
                "Build/experiment permission не подкреплено candidate-specific external proof.",
                "Сохранить producer decision investigate/reject либо добавить доказательства, прошедшие неизменённые Radar gates.",
            ),
        )


def _atlas_findings(
    sidecar: Mapping[str, Any],
    html: str,
    audit: _ReaderHtmlAudit,
    *,
    findings: list[dict[str, Any]],
) -> None:
    is_v2 = sidecar.get("schema_version") == "split_ai_report.v2"
    if not is_v2:
        _add(
            findings,
            _finding(
                "structural_validity",
                "atlas.legacy_audit_surface",
                SEVERITY_CRITICAL,
                "schema_version",
                [str(sidecar.get("schema_version") or "missing")],
                "Текущий подробный Atlas является техническим audit surface, а не двухминутной визуальной картой знаний.",
                "Сохранить его как Knowledge Audit Explorer и генерировать Atlas V2 рядом после IRX-7.",
            ),
        )
    elif sidecar.get("preview_profile") == "knowledge_atlas_v2.opt_in.v1":
        contract_valid = False
        try:
            from output.knowledge_atlas_report_v2 import (
                render_knowledge_atlas_v2_html,
                validate_knowledge_atlas_v2,
            )

            validate_knowledge_atlas_v2(sidecar)
            contract_valid = True
        except Exception as exc:
            errors = getattr(exc, "errors", ())
            evidence = [str(item)[:240] for item in list(errors)[:4]] or [
                exc.__class__.__name__
            ]
            _add(
                findings,
                _finding(
                    "structural_validity",
                    "atlas.contract_invalid",
                    SEVERITY_CRITICAL,
                    "split_ai_report.v2",
                    evidence,
                    "Sidecar не соответствует закрытому Atlas V2 contract и не может считаться канонической reader-картой.",
                    "Исправить детерминированную Atlas-проекцию и повторить contract/quality validation.",
                ),
            )
        if contract_valid:
            expected_html = render_knowledge_atlas_v2_html(sidecar)
            if html != expected_html:
                _add(
                    findings,
                    _finding(
                        "structural_validity",
                        "atlas.html_parity_mismatch",
                        SEVERITY_CRITICAL,
                        "rendered_html",
                        [
                            f"actual_characters={len(html)}",
                            f"expected_characters={len(expected_html)}",
                        ],
                        "HTML не совпадает с детерминированной reader-проекцией этого Atlas sidecar.",
                        "Перерендерить документ из неизменённого validated sidecar; не исправлять HTML вручную.",
                    ),
                )
    primary = _strings(
        sidecar.get("primary_thread_ids")
        if "primary_thread_ids" in sidecar
        else sidecar.get("primary_canonical_thread_ids")
    )
    threads = _mapping_items(sidecar.get("canonical_threads"))
    if len(primary) > 12:
        _limit_finding(
            findings,
            "atlas.primary_thread_limit",
            "primary_thread_ids",
            len(primary),
            12,
        )
    elif is_v2 and threads and len(primary) < 8:
        _add(
            findings,
            _finding(
                "structural_validity",
                "atlas.primary_thread_count_low",
                SEVERITY_WARNING,
                "primary_thread_ids",
                [f"count={len(primary)}", "target=8..12"],
                "Карта может не давать достаточно широкого обзора накопленного знания.",
                "Если данные позволяют, выбрать 8–12 канонических тем; честный малый набор оставить явно ограниченным.",
            ),
        )
    thread_ids = [
        _text(thread.get("canonical_thread_id") or thread.get("id"))
        for thread in threads
    ]
    duplicate_primary = sorted(
        {thread_id for thread_id in primary if primary.count(thread_id) > 1}
    )
    if duplicate_primary:
        _add(
            findings,
            _finding(
                "structural_validity",
                "atlas.primary_identity_duplicate",
                SEVERITY_CRITICAL,
                "primary_thread_ids",
                duplicate_primary[:8],
                "Один канонический узел занимает несколько мест в первичной карте.",
                "Удалить повторяющиеся primary_thread_ids, сохранив один стабильный canonical ref.",
            ),
        )
    duplicate_thread_ids = sorted(
        {
            thread_id
            for thread_id in thread_ids
            if thread_id and thread_ids.count(thread_id) > 1
        }
    )
    if duplicate_thread_ids:
        _add(
            findings,
            _finding(
                "structural_validity",
                "atlas.canonical_identity_duplicate",
                SEVERITY_CRITICAL,
                "canonical_threads",
                duplicate_thread_ids[:8],
                "Канонический реестр содержит неоднозначную идентичность темы.",
                "Оставить одну запись на canonical_thread_id и перенести aliases в audit projection.",
            ),
        )
    if is_v2 and (not threads or not primary):
        _add(
            findings,
            _finding(
                "structural_validity",
                "atlas.canonical_registry_missing",
                SEVERITY_CRITICAL,
                "canonical_threads",
                [f"threads={len(threads)}", f"primary={len(primary)}"],
                "Atlas не показывает устойчивые канонические идеи и может вернуться к entity fragmentation.",
                "Передать bounded canonical registry и exact primary_thread_ids из IRX-4 as-of projection.",
            ),
        )
    unknown_primary = sorted(set(primary).difference(thread_ids))
    if unknown_primary:
        _add(
            findings,
            _finding(
                "structural_validity",
                "atlas.primary_identity_unknown",
                SEVERITY_CRITICAL,
                "primary_thread_ids",
                unknown_primary[:8],
                "Первичный узел не разрешается в каноническом реестре.",
                "Исправить primary selection, не подменяя стабильный canonical_thread_id mutable raw slug.",
            ),
        )
    titles = [
        _text(thread.get("title_ru") or thread.get("title")) for thread in threads
    ]
    theses = [
        _text(thread.get("thesis") or thread.get("current_understanding"))
        for thread in threads
    ]
    _duplicate_atlas_text(titles, "title", findings=findings)
    _duplicate_atlas_text(theses, "thesis", findings=findings)
    _near_duplicate_titles(titles, findings=findings)
    for index, thread in enumerate(threads[:_MAX_INSPECTED_ITEMS]):
        thread_id = _text(thread.get("canonical_thread_id") or thread.get("id"))
        title = _text(thread.get("title_ru") or thread.get("title"))
        thesis = _text(thread.get("thesis") or thread.get("current_understanding"))
        if thread_id in set(primary) and (not title or not thesis):
            _add(
                findings,
                _finding(
                    "editorial_quality",
                    "atlas.primary_content_incomplete",
                    SEVERITY_CRITICAL,
                    f"canonical_threads[{index}]",
                    [
                        f"title_present={bool(title)}",
                        f"thesis_present={bool(thesis)}",
                    ],
                    "Первичная тема не объясняет читателю ни идею, ни текущее понимание.",
                    "Добавить уникальные русские title/thesis из canonical authority либо исключить запись из primary set.",
                ),
            )
        maturity = str(thread.get("evidence_maturity") or thread.get("maturity") or "")
        if maturity and maturity not in _SHARED_MATURITY:
            _add(
                findings,
                _finding(
                    "evidence_validity",
                    "atlas.maturity_label_unsupported",
                    SEVERITY_CRITICAL,
                    f"canonical_threads[{index}].evidence_maturity",
                    [maturity],
                    "Необъяснённая зрелость может завысить доверие к теме.",
                    "Использовать общий maturity enum и отдельно показать conclusion confidence.",
                ),
            )
            continue
        summary = _mapping(thread.get("evidence_summary"))
        independent = _int(
            thread.get("independent_source_count"),
            default=_int(summary.get("independent_source_count"), default=-1),
        )
        refs = _strings(thread.get("evidence_refs") or summary.get("evidence_refs"))
        if thread_id in set(primary) and not refs:
            _missing_evidence_finding(
                findings,
                "atlas.primary_evidence_missing",
                f"canonical_threads[{index}]",
            )
        if maturity in {"externally_corroborated", "decision_grade"} and (
            independent < 0 or not refs
        ):
            _add(
                findings,
                _finding(
                    "evidence_validity",
                    "atlas.maturity_basis_missing",
                    SEVERITY_CRITICAL,
                    f"canonical_threads[{index}]",
                    [
                        maturity,
                        f"independent_sources={independent}",
                        f"evidence_refs={len(refs)}",
                    ],
                    "Высокая зрелость заявлена без проверяемого основания.",
                    "Добавить authoritative evidence summary или понизить maturity до доказанного уровня.",
                ),
            )
        elif maturity in {"externally_corroborated", "decision_grade"} and (
            independent < 2 or len(refs) < 2
        ):
            _add(
                findings,
                _finding(
                    "evidence_validity",
                    "atlas.maturity_overstated",
                    SEVERITY_CRITICAL,
                    f"canonical_threads[{index}]",
                    [
                        maturity,
                        f"independent_sources={independent}",
                        f"evidence_refs={len(refs)}",
                    ],
                    "Тема выглядит более зрелой, чем подтверждают независимые источники.",
                    "Понизить maturity или добавить требуемые независимые доказательства без изменения confidence вручную.",
                ),
            )
        external_sources = _int(
            thread.get("external_source_count"),
            default=_int(summary.get("external_source_count"), default=-1),
        )
        decision_grade_evidence = _int(
            thread.get("decision_grade_evidence_count"),
            default=_int(
                summary.get("decision_grade_evidence_count"),
                default=-1,
            ),
        )
        maturity_authority_missing = (
            maturity == "externally_corroborated" and external_sources < 1
        ) or (
            maturity == "decision_grade"
            and (external_sources < 1 or decision_grade_evidence < 1)
        )
        if maturity_authority_missing:
            _add(
                findings,
                _finding(
                    "evidence_validity",
                    "atlas.maturity_authority_missing",
                    SEVERITY_CRITICAL,
                    f"canonical_threads[{index}]",
                    [
                        maturity,
                        f"external_sources={external_sources}",
                        f"decision_grade_evidence={decision_grade_evidence}",
                    ],
                    "Высокая зрелость не доказывает внешнюю или decision-grade природу источников.",
                    "Передать authoritative external_source_count и decision_grade_evidence_count из evidence contract либо понизить maturity.",
                ),
            )
    navigation = _mapping(sidecar.get("thread_navigation"))
    raw_threads = _mapping_items(navigation.get("threads"))
    if raw_threads and (not is_v2 or len(raw_threads) > 12):
        _add(
            findings,
            _finding(
                "structural_validity",
                "atlas.raw_detail_primary",
                SEVERITY_CRITICAL,
                "thread_navigation.threads",
                [f"expanded_raw_threads={len(raw_threads)}"],
                "Raw/entity thread detail остаётся основной поверхностью и создаёт повторяющийся шум.",
                "Перенести raw memberships и полные evidence panes в Audit Explorer; Atlas оставить canonical и progressive-disclosure.",
            ),
        )
    for field in ("expanded_thread_ids", "expanded_detail_ids", "expanded_details"):
        expanded = sidecar.get(field)
        if isinstance(expanded, (list, tuple)) and len(expanded) > 12:
            _limit_finding(
                findings,
                "atlas.expanded_detail_limit",
                field,
                len(expanded),
                12,
            )
    backlog = _mapping_items(sidecar.get("study_backlog"))
    backlog_labels = [
        _text(item.get("title_ru") or item.get("title") or item.get("reason_ru"))
        for item in backlog
    ]
    _duplicate_atlas_text(backlog_labels, "study_backlog", findings=findings)
    if is_v2:
        _atlas_visual_identity_findings(
            sidecar,
            primary=primary,
            thread_ids=thread_ids,
            findings=findings,
        )
        _atlas_maturity_visual_findings(
            sidecar,
            primary=primary,
            threads=threads,
            findings=findings,
        )
    _visual_findings(
        sidecar,
        html,
        audit,
        required_types=_ATLAS_VISUALS,
        minimum_meaningful=4,
        findings=findings,
    )
    if audit.visible_word_count > 1_500:
        _add(
            findings,
            _finding(
                "editorial_quality",
                "atlas.visible_length_critical",
                SEVERITY_CRITICAL,
                "initial_visible_copy",
                [f"visible_words={audit.visible_word_count}", "hard_max=1500"],
                "Atlas нельзя интерпретировать как быстрый обзор знаний.",
                "Сократить initial copy до 1 500 слов, а claims, sources, aliases и history свернуть или перенести в Audit Explorer.",
            ),
        )
    if not _mapping(sidecar.get("operator_interest")) and is_v2:
        _add(
            findings,
            _finding(
                "personalization_quality",
                "atlas.operator_interest_missing",
                SEVERITY_WARNING,
                "operator_interest",
                ["missing"],
                "Карта не отделяет слабое внимание по реакциям от подтверждённой обратной связи.",
                "Добавить отдельную агрегированную interest projection без вывода, что реакция означает понимание.",
            ),
        )


def _visual_findings(
    sidecar: Mapping[str, Any],
    html: str,
    audit: _ReaderHtmlAudit,
    *,
    required_types: set[str],
    minimum_meaningful: int,
    findings: list[dict[str, Any]],
) -> None:
    specs = _mapping_items(sidecar.get("visual_specs"))
    valid_types: list[str] = []
    valid_component_ids: list[str] = []
    meaningful_types: list[str] = []
    for index, spec in enumerate(specs[:_MAX_INSPECTED_ITEMS]):
        try:
            component_type = validate_report_visual(spec)
            result = render_report_visual(spec)
        except (ReportVisualValidationError, TypeError, ValueError) as exc:
            _add(
                findings,
                _finding(
                    "visual_quality",
                    "visual.spec_invalid",
                    SEVERITY_CRITICAL,
                    f"visual_specs[{index}]",
                    [exc.__class__.__name__, str(exc)[:180]],
                    "Компонент нельзя считать достоверной визуализацией данных.",
                    "Исправить closed report_visual schema и provenance до рендера.",
                ),
            )
            continue
        valid_component_ids.append(result.component_id)
        period = _period(sidecar)
        expected_identity = {
            "run_id": str(sidecar.get("run_id") or ""),
            "reporting_week": _reporting_week(sidecar),
            "analysis_period_start": str(period.get("analysis_period_start") or ""),
            "analysis_period_end": str(period.get("analysis_period_end") or ""),
        }
        identity_mismatches = [
            f"{field}:actual={spec.get(field)}:expected={expected}"
            for field, expected in expected_identity.items()
            if str(spec.get(field) or "") != expected
        ]
        if identity_mismatches:
            _add(
                findings,
                _finding(
                    "visual_quality",
                    "visual.identity_mismatch",
                    SEVERITY_CRITICAL,
                    f"visual_specs[{index}]",
                    identity_mismatches,
                    "Визуализация относится к другому запуску или периоду и искажает текущий выпуск.",
                    "Пересобрать spec из exact run/period sidecar без подстановки соседнего компонента.",
                ),
            )
            continue
        valid_types.append(component_type)
        expected_role = "supporting" if component_type == "evidence_badge" else "data"
        expected_fingerprint = _visual_component_fingerprint(result.html)
        matching_markers = [
            marker
            for marker in audit.visual_markers
            if marker.get("data-component") == component_type
            and marker.get("data-component-id") == result.component_id
            and marker.get("data-schema-version") == result.schema_version
            and marker.get("data-render-status") == result.render_status
            and marker.get("data-data-status") == result.data_status
            and marker.get("data-source-ref-count") == str(result.source_ref_count)
            and marker.get("data-visual-role") == expected_role
        ]
        matching_components = [
            marker
            for marker, fingerprint in audit.visible_visual_components
            if fingerprint == expected_fingerprint
            and marker.get("data-component") == component_type
            and marker.get("data-component-id") == result.component_id
            and marker.get("data-schema-version") == result.schema_version
            and marker.get("data-render-status") == result.render_status
            and marker.get("data-data-status") == result.data_status
            and marker.get("data-source-ref-count") == str(result.source_ref_count)
            and marker.get("data-visual-role") == expected_role
        ]
        matching_hidden_markers = [
            marker
            for marker in audit.hidden_visual_markers
            if marker.get("data-component") == component_type
            and marker.get("data-component-id") == result.component_id
            and marker.get("data-schema-version") == result.schema_version
            and marker.get("data-render-status") == result.render_status
            and marker.get("data-data-status") == result.data_status
            and marker.get("data-source-ref-count") == str(result.source_ref_count)
            and marker.get("data-visual-role") == expected_role
        ]
        exact_fragment_present = result.html in html
        initially_visible = (
            len(matching_markers) == 1
            and len(matching_components) == 1
            and not matching_hidden_markers
        )
        if (
            expected_role == "data"
            and spec.get("data_status") in {"available", "empty"}
            and result.render_status != "failed"
            and exact_fragment_present
            and initially_visible
        ):
            meaningful_types.append(component_type)
        elif not exact_fragment_present:
            _add(
                findings,
                _finding(
                    "visual_quality",
                    "visual.html_parity_mismatch",
                    SEVERITY_CRITICAL,
                    f"visual_specs[{index}]",
                    [component_type],
                    "HTML-маркер не доказывает, что читателю показан детерминированный data-bearing component.",
                    "Вставить byte-identical render_report_visual result для этого validated spec.",
                ),
            )
        elif not initially_visible:
            _add(
                findings,
                _finding(
                    "visual_quality",
                    "visual.initial_visibility_mismatch",
                    SEVERITY_CRITICAL,
                    f"visual_specs[{index}]",
                    [
                        component_type,
                        f"visible_markers={len(matching_markers)}",
                        f"matching_components={len(matching_components)}",
                        f"hidden_markers={len(matching_hidden_markers)}",
                    ],
                    "Компонент спрятан в template, закрытом disclosure или продублирован и не работает как reader visual.",
                    "Поместить один exact semantic component в начальную читательскую поверхность; технические копии удалить.",
                ),
            )
    missing = sorted(required_types.difference(valid_types))
    if missing:
        _add(
            findings,
            _finding(
                "visual_quality",
                "visual.required_kind_missing",
                SEVERITY_CRITICAL,
                "visual_specs",
                missing,
                "Отчёт не показывает обязательные отношения между решениями, источниками или состояниями.",
                "Добавить отсутствующие semantic component specs с честным available/empty/unavailable state.",
            ),
        )
    duplicates = sorted(
        {
            component_type
            for component_type in valid_types
            if valid_types.count(component_type) > 1
        }
    )
    if duplicates:
        _add(
            findings,
            _finding(
                "visual_quality",
                "visual.component_kind_duplicate",
                SEVERITY_CRITICAL,
                "visual_specs",
                duplicates,
                "Повтор одного типа компонента не создаёт дополнительной читательской связи.",
                "Оставить один validated component каждого обязательного типа и не считать варианты дважды.",
            ),
        )
    duplicate_component_ids = sorted(
        {
            component_id
            for component_id in valid_component_ids
            if valid_component_ids.count(component_id) > 1
        }
    )
    if duplicate_component_ids:
        _add(
            findings,
            _finding(
                "visual_quality",
                "visual.component_id_duplicate",
                SEVERITY_CRITICAL,
                "visual_specs.component_id",
                duplicate_component_ids[:8],
                "Несколько компонентов используют одну DOM/SVG identity и ломают подписи или внутренние ссылки.",
                "Назначить каждому visual spec уникальный стабильный component_id в пределах документа.",
            ),
        )
    meaningful_distinct = sorted(set(meaningful_types))
    if len(meaningful_distinct) < minimum_meaningful:
        severity = SEVERITY_WARNING if _is_partial(sidecar) else SEVERITY_CRITICAL
        _add(
            findings,
            _finding(
                "visual_quality",
                "visual.meaningful_count_low",
                severity,
                "visual_specs",
                [
                    f"meaningful={len(meaningful_distinct)}",
                    f"required={minimum_meaningful}",
                    f"svg_count={audit.svg_count}",
                ],
                "Декоративная графика или пустые контейнеры не объясняют данные выпуска.",
                "Показать требуемое число distinct validated available components; SVG сам по себе не засчитывать.",
            ),
        )
    marker_types = [marker.get("data-component", "") for marker in audit.visual_markers]
    if marker_types != valid_types:
        _add(
            findings,
            _finding(
                "visual_quality",
                "visual.marker_parity_mismatch",
                SEVERITY_CRITICAL,
                "rendered_html[data-irx-visual]",
                [f"specs={valid_types}", f"markers={marker_types}"],
                "Semantic markers не совпадают со структурированными visual specs.",
                "Рендерить markers только через shared report_visuals component output и сохранить порядок specs.",
            ),
        )
    metrics = _mapping(sidecar.get("content_metrics"))
    if metrics and metrics.get("meaningful_visual_count") != len(meaningful_distinct):
        _add(
            findings,
            _finding(
                "visual_quality",
                "visual.metrics_parity_mismatch",
                SEVERITY_CRITICAL,
                "content_metrics.meaningful_visual_count",
                [
                    f"sidecar={metrics.get('meaningful_visual_count')}",
                    f"measured={len(meaningful_distinct)}",
                ],
                "Sidecar завышает или занижает число реально показанных meaningful visuals.",
                "Считать метрику из validated specs и exact rendered component fragments.",
            ),
        )


def _visual_component_fingerprint(html: str) -> tuple[tuple[object, ...], ...]:
    parser = _ReaderHtmlAudit()
    parser.feed(html)
    parser.close()
    if len(parser.visible_visual_components) != 1:
        raise ReaderQualityContractError(
            "rendered visual must contain exactly one visible semantic component"
        )
    return parser.visible_visual_components[0][1]


def _build_report(
    sidecar: Mapping[str, Any],
    *,
    surface: str,
    policy_mode: str,
    findings: Sequence[Mapping[str, Any]],
    not_applicable: set[str],
) -> dict[str, Any]:
    ordered = _dedupe_findings(findings)
    dimensions: list[dict[str, Any]] = []
    for name in QUALITY_DIMENSIONS:
        rows = [dict(item) for item in ordered if item.get("dimension") == name]
        if name in not_applicable and not rows:
            status, severity = "not_applicable", "none"
        else:
            status, severity = _dimension_state(rows)
        dimensions.append(
            {
                "name": name,
                "status": status,
                "severity": severity,
                "findings": rows,
            }
        )
    critical_count = sum(item["severity"] == SEVERITY_CRITICAL for item in ordered)
    warning_count = sum(item["severity"] == SEVERITY_WARNING for item in ordered)
    partial = _is_partial(sidecar)
    summary = {
        "overall_status": (
            "fail" if critical_count else "warning" if warning_count else "pass"
        ),
        "delivery_decision": _delivery_decision(
            policy_mode,
            partial=partial,
            critical_count=critical_count,
            warning_count=warning_count,
        ),
        "partial": partial,
        "critical_count": critical_count,
        "warning_count": warning_count,
        "failed_dimensions": [
            str(item["name"]) for item in dimensions if item["status"] == "fail"
        ],
    }
    return {
        "schema_version": REPORT_QUALITY_V2_SCHEMA_VERSION,
        "policy_version": READER_VALUE_POLICY_VERSION,
        "policy_mode": policy_mode,
        "surface": surface,
        "run_id": str(sidecar.get("run_id") or ""),
        "reporting_week": _reporting_week(sidecar),
        "dimensions": dimensions,
        "summary": summary,
    }


def _finding(
    dimension: str,
    code: str,
    severity: str,
    affected_item: str,
    evidence: Sequence[object],
    reader_impact_ru: str,
    repair_hint_ru: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "dimension": dimension,
        "severity": severity,
        "affected_item": str(affected_item)[:240],
        "evidence": [" ".join(str(item).split())[:500] for item in evidence[:8]],
        "reader_impact_ru": " ".join(reader_impact_ru.split())[:800],
        "repair_hint_ru": " ".join(repair_hint_ru.split())[:800],
    }


def _validate_finding(value: object, *, expected_dimension: str) -> None:
    if not isinstance(value, Mapping):
        raise ReaderQualityContractError("reader quality finding must be an object")
    _exact(value, _FINDING_FIELDS, "finding")
    if not isinstance(value.get("code"), str) or not _CODE_RE.fullmatch(
        str(value["code"])
    ):
        raise ReaderQualityContractError("reader quality finding code is invalid")
    if value.get("dimension") != expected_dimension:
        raise ReaderQualityContractError("reader quality finding dimension mismatch")
    if value.get("severity") not in {SEVERITY_WARNING, SEVERITY_CRITICAL}:
        raise ReaderQualityContractError("reader quality finding severity is invalid")
    affected = value.get("affected_item")
    if not isinstance(affected, str) or not affected.strip() or len(affected) > 240:
        raise ReaderQualityContractError("reader quality affected_item is invalid")
    evidence = value.get("evidence")
    if (
        not isinstance(evidence, list)
        or not evidence
        or len(evidence) > 8
        or any(
            not isinstance(item, str) or not item.strip() or len(item) > 500
            for item in evidence
        )
    ):
        raise ReaderQualityContractError("reader quality finding evidence is invalid")
    for field in ("reader_impact_ru", "repair_hint_ru"):
        text = value.get(field)
        if (
            not isinstance(text, str)
            or not text.strip()
            or len(text) > 800
            or not _CYRILLIC_RE.search(text)
        ):
            raise ReaderQualityContractError(f"reader quality {field} is invalid")


def _dimension_state(findings: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    if any(item.get("severity") == SEVERITY_CRITICAL for item in findings):
        return "fail", SEVERITY_CRITICAL
    if any(item.get("severity") == SEVERITY_WARNING for item in findings):
        return "warning", SEVERITY_WARNING
    return "pass", "none"


def _delivery_decision(
    policy_mode: str,
    *,
    partial: bool,
    critical_count: int,
    warning_count: int,
) -> str:
    if policy_mode == READER_VALUE_WARN_ONLY_V1:
        return "allow_with_warnings" if critical_count or warning_count else "allow"
    if critical_count:
        return "block"
    if partial:
        return "require_partial"
    if warning_count:
        return "allow_with_warnings"
    return "allow"


def _surface(sidecar: Mapping[str, Any], explicit: str | None) -> str:
    value = str(
        explicit or sidecar.get("surface") or sidecar.get("artifact_type") or ""
    )
    aliases = {
        "weekly_intelligence_brief": "weekly_brief",
        "weekly_brief": "weekly_brief",
        "knowledge_atlas": "knowledge_atlas",
    }
    return aliases.get(value, "unknown")


def _period(sidecar: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = sidecar.get("reporting_period")
    if isinstance(nested, Mapping):
        return nested
    return {
        "reporting_week": sidecar.get("reporting_week") or sidecar.get("week_label"),
        "analysis_period_start": sidecar.get("analysis_period_start"),
        "analysis_period_end": sidecar.get("analysis_period_end"),
    }


def _reporting_week(sidecar: Mapping[str, Any]) -> str:
    return str(_period(sidecar).get("reporting_week") or "")[:32]


def _is_partial(sidecar: Mapping[str, Any]) -> bool:
    return sidecar.get("partial") is True or sidecar.get("run_status") == "partial"


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_items(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [
        item for item in value[: _MAX_INSPECTED_ITEMS + 1] if isinstance(item, Mapping)
    ]


def _strings(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [
        item.strip()
        for item in value[: _MAX_INSPECTED_ITEMS + 1]
        if isinstance(item, str) and item.strip()
    ]


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _int(value: object, *, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value


def _normalize_text(value: object) -> str:
    return " ".join(_WORD_RE.findall(str(value).casefold()))


def _russian_ratio(value: str) -> tuple[float, int]:
    words = _ALPHA_WORD_RE.findall(value)
    if not words:
        return 0.0, 0
    russian = sum(bool(_CYRILLIC_RE.search(word)) for word in words)
    return russian / len(words), len(words)


def _visible_internal_token(value: str) -> str | None:
    for pattern in (
        _INTERNAL_REF_RE,
        _INTERNAL_TARGET_ID_RE,
        _INTERNAL_RUN_ID_RE,
        _INTERNAL_ENUM_RE,
        _INTERNAL_PATH_RE,
    ):
        match = pattern.search(value)
        if match:
            return match.group(0)[:180]
    return None


def _exact(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ReaderQualityContractError(
            f"{path} fields mismatch: missing={sorted(expected - actual)} "
            f"unknown={sorted(actual - expected)}"
        )


def _add(findings: list[dict[str, Any]], finding: dict[str, Any]) -> None:
    if len(findings) < _MAX_FINDINGS:
        findings.append(finding)


def _dedupe_findings(findings: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    dimension_index = {name: index for index, name in enumerate(QUALITY_DIMENSIONS)}
    rows: dict[tuple[object, ...], dict[str, Any]] = {}
    for raw in findings[:_MAX_FINDINGS]:
        item = dict(raw)
        key = (
            item.get("dimension"),
            item.get("code"),
            item.get("affected_item"),
            tuple(item.get("evidence") or []),
        )
        rows.setdefault(key, item)
    return sorted(
        rows.values(),
        key=lambda item: (
            dimension_index.get(str(item.get("dimension")), len(dimension_index)),
            0 if item.get("severity") == SEVERITY_CRITICAL else 1,
            str(item.get("code")),
            str(item.get("affected_item")),
            tuple(item.get("evidence") or []),
        ),
    )


def _limit_finding(
    findings: list[dict[str, Any]],
    code: str,
    affected_item: str,
    actual: int,
    maximum: int,
) -> None:
    dimension = (
        "project_usefulness" if code.startswith("project.") else "structural_validity"
    )
    _add(
        findings,
        _finding(
            dimension,
            code,
            SEVERITY_CRITICAL,
            affected_item,
            [f"actual={actual}", f"maximum={maximum}"],
            "Слишком много первичных элементов делает reader surface непредсказуемым и несканируемым.",
            "Ограничить primary set на host side и перенести остальные элементы в collapsed registry или Audit Explorer.",
        ),
    )


def _missing_evidence_finding(
    findings: list[dict[str, Any]],
    code: str,
    affected_item: str,
    *,
    dimension: str = "evidence_validity",
) -> None:
    _add(
        findings,
        _finding(
            dimension,
            code,
            SEVERITY_CRITICAL,
            affected_item,
            ["evidence_refs=0"],
            "Читательское утверждение или действие нельзя проверить по источникам выпуска.",
            "Добавить resolvable evidence refs из bounded input либо удалить неподтверждённый вывод.",
        ),
    )


def _duplicate_atlas_text(
    values: Sequence[str],
    label: str,
    *,
    findings: list[dict[str, Any]],
) -> None:
    normalized = [_normalize_text(value) for value in values if _normalize_text(value)]
    duplicates = sorted({item for item in normalized if normalized.count(item) > 1})
    if not duplicates:
        return
    _add(
        findings,
        _finding(
            "editorial_quality",
            "atlas.duplicate_content",
            SEVERITY_CRITICAL,
            label,
            duplicates[:6],
            "Одинаковый reader content выглядит как несколько независимых тем.",
            "Объединить точные дубликаты на canonical layer и сохранить raw aliases только в Audit Explorer.",
        ),
    )


def _near_duplicate_titles(
    titles: Sequence[str],
    *,
    findings: list[dict[str, Any]],
) -> None:
    token_sets = [set(_normalize_text(title).split()) for title in titles]
    pairs: list[str] = []
    for left in range(len(token_sets)):
        for right in range(left + 1, len(token_sets)):
            union = token_sets[left] | token_sets[right]
            if len(union) < 3:
                continue
            similarity = len(token_sets[left] & token_sets[right]) / len(union)
            if similarity >= 0.8:
                pairs.append(f"{left}:{right}:{similarity:.2f}")
    if pairs:
        _add(
            findings,
            _finding(
                "editorial_quality",
                "atlas.near_duplicate_titles",
                SEVERITY_WARNING,
                "canonical_threads.title_ru",
                pairs[:8],
                "Похожие заголовки могут повторять entity fragmentation, но одной лексики недостаточно для автоматического merge.",
                "Передать пары canonical curator для проверки идеи и provenance; не объединять темы только по словам.",
            ),
        )


def _atlas_maturity_visual_findings(
    sidecar: Mapping[str, Any],
    *,
    primary: Sequence[str],
    threads: Sequence[Mapping[str, Any]],
    findings: list[dict[str, Any]],
) -> None:
    maturity_spec = next(
        (
            spec
            for spec in _mapping_items(sidecar.get("visual_specs"))
            if spec.get("schema_version") == "report_visual.evidence_maturity.v1"
        ),
        None,
    )
    if maturity_spec is None or maturity_spec.get("data_status") != "available":
        return
    by_id = {
        _text(thread.get("canonical_thread_id") or thread.get("id")): thread
        for thread in threads
    }
    expected = Counter(
        str(
            by_id[thread_id].get("evidence_maturity")
            or by_id[thread_id].get("maturity")
            or "unknown"
        )
        for thread_id in primary
        if thread_id in by_id
    )
    levels = _mapping_items(maturity_spec.get("levels"))
    actual = Counter(
        {
            str(level.get("key") or ""): _int(level.get("count"), default=-1)
            for level in levels
        }
    )
    keys = set(_SHARED_MATURITY)
    expected_counts = {key: expected.get(key, 0) for key in keys}
    actual_counts = {key: actual.get(key, 0) for key in keys}
    if (
        _int(maturity_spec.get("thread_count"), default=-1) != len(primary)
        or expected_counts != actual_counts
    ):
        _add(
            findings,
            _finding(
                "evidence_validity",
                "atlas.maturity_distribution_mismatch",
                SEVERITY_CRITICAL,
                "visual_specs[evidence_maturity]",
                [
                    f"primary={len(primary)}",
                    f"visual_thread_count={maturity_spec.get('thread_count')}",
                    f"expected={sorted(expected_counts.items())}",
                    f"actual={sorted(actual_counts.items())}",
                ],
                "Распределение зрелости не совпадает с первичными каноническими темами.",
                "Пересчитать levels только из authoritative maturity primary registry и сохранить точную population parity.",
            ),
        )


def _atlas_visual_identity_findings(
    sidecar: Mapping[str, Any],
    *,
    primary: Sequence[str],
    thread_ids: Sequence[str],
    findings: list[dict[str, Any]],
) -> None:
    known = set(thread_ids)
    primary_set = set(primary)
    for spec in _mapping_items(sidecar.get("visual_specs")):
        schema = str(spec.get("schema_version") or "")
        if schema == "report_visual.knowledge_graph.v1":
            rows = _mapping_items(spec.get("nodes"))
        elif schema == "report_visual.thread_timeline.v1":
            rows = _mapping_items(spec.get("series"))
        elif schema == "report_visual.source_thread_heatmap.v1":
            rows = _mapping_items(spec.get("threads"))
        else:
            continue
        visual_ids = {
            _text(row.get("canonical_thread_id"))
            for row in rows
            if _text(row.get("canonical_thread_id"))
        }
        unknown = sorted(visual_ids.difference(known))
        if unknown:
            _add(
                findings,
                _finding(
                    "evidence_validity",
                    "atlas.visual_thread_identity_unknown",
                    SEVERITY_CRITICAL,
                    schema,
                    unknown[:8],
                    "Визуализация показывает темы вне authoritative canonical registry этого Atlas.",
                    "Пересобрать component rows только из canonical_threads текущего run/as-of snapshot.",
                ),
            )
        if (
            spec.get("data_status") == "available"
            and primary_set
            and not visual_ids.intersection(primary_set)
        ):
            _add(
                findings,
                _finding(
                    "evidence_validity",
                    "atlas.visual_primary_identity_missing",
                    SEVERITY_CRITICAL,
                    schema,
                    [
                        f"visual_threads={len(visual_ids)}",
                        f"primary_threads={len(primary_set)}",
                    ],
                    "Компонент с данными не объясняет ни одной первичной темы reader Atlas.",
                    "Связать доступный component хотя бы с одной primary canonical theme или честно объявить unavailable/empty.",
                ),
            )
