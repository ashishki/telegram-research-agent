import json
import sqlite3


def _parse_json_list(value: str | None) -> list:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _preview(values: list, *, limit: int = 6) -> str:
    if not values:
        return "none"
    rendered = [str(value) for value in values[:limit]]
    if len(values) > limit:
        rendered.append(f"+{len(values) - limit} more")
    return ", ".join(rendered)


def _scope_clause(
    *,
    week_label: str,
    project_name: str | None,
    topic_label: str | None,
    week_columns: tuple[str, str] = ("first_seen_week", "last_seen_week"),
) -> tuple[str, list[object]]:
    clauses = [f"({week_columns[0]} <= ? AND {week_columns[1]} >= ?)"]
    params: list[object] = [week_label, week_label]
    if project_name:
        clauses.append("project_name = ?")
        params.append(project_name)
    if topic_label:
        clauses.append("topic_label = ?")
        params.append(topic_label)
    return " AND ".join(clauses), params


def _claim_citations(connection: sqlite3.Connection, claim_id: int, *, limit: int = 3) -> list[str]:
    rows = connection.execute(
        """
        SELECT id, source_channel, message_url, posted_at
        FROM claim_occurrences
        WHERE claim_id = ?
        ORDER BY posted_at ASC, id ASC
        LIMIT ?
        """,
        (claim_id, max(1, int(limit or 3))),
    ).fetchall()
    return [
        f"occurrence_id={row['id']} channel={row['source_channel']} url={row['message_url'] or 'n/a'}"
        for row in rows
    ]


def render_channel_intelligence_report(
    connection: sqlite3.Connection,
    *,
    week_label: str,
    project_name: str | None = None,
    topic_label: str | None = None,
    limit: int = 5,
) -> str:
    """Render an operator-facing report from derived Channel Intelligence rows."""
    clean_limit = max(1, int(limit or 5))
    lines = [
        f"# Channel Intelligence Report - {week_label}",
        "",
        "source_of_truth: derived SQLite rows from channel_repeated_claims, claim_occurrences, channel_narratives, narrative_claim_links, source_observations, intelligence_entity_links, and project_intelligence_links",
        "refresh_rule: refresh rows with output.channel_intelligence helpers before rendering; this report does not create memory",
        f"scope: project={project_name or 'any'} topic={topic_label or 'any'}",
        "",
    ]

    narrative_where, narrative_params = _scope_clause(
        week_label=week_label,
        project_name=project_name,
        topic_label=topic_label,
    )
    narratives = connection.execute(
        f"""
        SELECT *
        FROM channel_narratives
        WHERE {narrative_where}
        ORDER BY status ASC, supporting_post_count DESC, id DESC
        LIMIT ?
        """,
        (*narrative_params, clean_limit),
    ).fetchall()
    lines.append("## Narratives")
    if not narratives:
        lines.append("- none")
    for row in narratives:
        evidence_ids = _parse_json_list(row["evidence_item_ids_json"])
        channels = _parse_json_list(row["source_channels_json"])
        weak_label = " [weak-evidence]" if row["status"] != "active" or len(evidence_ids) < 2 else ""
        claim_links = connection.execute(
            """
            SELECT claim_id, shared_evidence_count
            FROM narrative_claim_links
            WHERE narrative_id = ?
            ORDER BY claim_id ASC
            LIMIT ?
            """,
            (row["id"], clean_limit),
        ).fetchall()
        claim_link_text = "; ".join(
            f"claim_id={link['claim_id']} shared_evidence={link['shared_evidence_count']}"
            for link in claim_links
        ) or "none"
        lines.append(f"- narrative_id={row['id']}{weak_label}: {row['title']}")
        lines.append(
            f"  input_row_ids: narrative_id={row['id']} evidence_item_ids={_preview(evidence_ids)} claim_links={claim_link_text}"
        )
        lines.append(
            f"  support: status={row['status']} channels={_preview(channels)} linked_claim_count={row['linked_claim_count']}"
        )

    claim_where, claim_params = _scope_clause(
        week_label=week_label,
        project_name=project_name,
        topic_label=topic_label,
    )
    claims = connection.execute(
        f"""
        SELECT *
        FROM channel_repeated_claims
        WHERE {claim_where}
        ORDER BY status DESC, evidence_strength DESC, occurrence_count DESC, id DESC
        LIMIT ?
        """,
        (*claim_params, clean_limit),
    ).fetchall()
    lines.extend(["", "## Repeated Claims"])
    if not claims:
        lines.append("- none")
    for row in claims:
        evidence_ids = _parse_json_list(row["evidence_item_ids_json"])
        weak_label = " [weak-evidence]" if row["status"] != "repeated" or row["evidence_strength"] == "weak" else ""
        lines.append(f"- claim_id={row['id']}{weak_label}: {row['normalized_claim']}")
        lines.append(
            f"  input_row_ids: claim_id={row['id']} evidence_item_ids={_preview(evidence_ids)}"
        )
        lines.append(
            f"  counters: status={row['status']} strength={row['evidence_strength']} occurrences={row['occurrence_count']} channels={row['channel_count']}"
        )
        citations = _claim_citations(connection, int(row["id"]), limit=3)
        lines.append(f"  citations: {'; '.join(citations) if citations else 'none'}")

    source_clauses = ["week_label = ?"]
    source_params: list[object] = [week_label]
    if project_name:
        source_clauses.append("project_name = ?")
        source_params.append(project_name)
    if topic_label:
        source_clauses.append("topic_label = ?")
        source_params.append(topic_label)
    sources = connection.execute(
        f"""
        SELECT *
        FROM source_observations
        WHERE {' AND '.join(source_clauses)}
        ORDER BY evidence_count DESC, acted_on_count DESC, channel_username ASC
        LIMIT ?
        """,
        (*source_params, clean_limit),
    ).fetchall()
    lines.extend(["", "## Source Observations"])
    if not sources:
        lines.append("- none")
    for row in sources:
        weak_source = row["evidence_count"] == 0 or row["low_signal_count"] > (row["cited_count"] + row["acted_on_count"])
        weak_label = " [weak-evidence]" if weak_source else ""
        lines.append(f"- source_observation_id={row['id']}{weak_label}: {row['channel_username']}")
        lines.append(
            f"  input_row_ids: source_observation_id={row['id']} scope={row['scope_key']} raw_counter_inputs=counters_json"
        )
        lines.append(
            "  counters: "
            f"posts={row['post_count']} evidence={row['evidence_count']} cited={row['cited_count']} "
            f"acted_on={row['acted_on_count']} skipped={row['skipped_count']} rejected={row['rejected_count']} "
            f"low_signal={row['low_signal_count']} repeated_claims={row['repeated_claim_count']} useful={row['useful_count']}"
        )

    project_link_clauses = ["week_label = ?"]
    project_link_params: list[object] = [week_label]
    if project_name:
        project_link_clauses.append("project_name = ?")
        project_link_params.append(project_name)
    project_links = connection.execute(
        f"""
        SELECT *
        FROM project_intelligence_links
        WHERE {' AND '.join(project_link_clauses)}
        ORDER BY relevance_score DESC, linked_object_type ASC, id DESC
        LIMIT ?
        """,
        (*project_link_params, clean_limit),
    ).fetchall()
    lines.extend(["", "## Project Links"])
    if not project_links:
        lines.append("- none")
    for row in project_links:
        evidence_ids = _parse_json_list(row["evidence_item_ids_json"])
        lines.append(
            f"- project_link_id={row['id']}: project={row['project_name']} object={row['linked_object_type']}:{row['linked_object_id']}"
        )
        lines.append(
            f"  input_row_ids: project_link_id={row['id']} evidence_item_ids={_preview(evidence_ids)}"
        )
        lines.append(f"  reason: {row['match_reason']} score={float(row['relevance_score'] or 0.0):.2f}")

    return "\n".join(lines).rstrip() + "\n"
