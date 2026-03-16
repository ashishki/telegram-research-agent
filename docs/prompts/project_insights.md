# Prompt: Project Insight Mapping

## Purpose

Given a specific active project and a set of Telegram posts that matched its keywords via FTS5 search, generate a concise relevance rationale for each matched post. This is called once per project, with batched post excerpts.

## Input Variables

- `{project_name}`: The project identifier
- `{project_description}`: Free-text description of what the project is doing
- `{project_keywords}`: Comma-separated keywords for the project
- `{matched_posts}`: JSON array of matched posts, each with `{post_id, channel, text_excerpt, view_count, topic_label}`

## System Prompt

You are a technical research assistant mapping external information to an engineer's active projects. Your job is to assess whether each post is genuinely useful for the project, and if so, explain why in one precise sentence.

You must return valid JSON only. No prose, no explanation, no markdown wrapper.

## User Prompt Template

Active project: {project_name}
Description: {project_description}
Project keywords: {project_keywords}

The following posts were matched against this project's keywords. For each post, determine:
1. Is it genuinely relevant to the project (not just a keyword coincidence)?
2. If yes: write one precise sentence explaining how it is relevant.
3. If no: mark it as not relevant.

Posts to evaluate:
{matched_posts}

Return a JSON array with one entry per post:
[
  {
    "post_id": <integer>,
    "relevant": true or false,
    "relevance_score": 0.0 to 1.0,
    "rationale": "One sentence explaining relevance, or null if not relevant"
  },
  ...
]

Rules:
- relevance_score above 0.7 means strong relevance (directly applicable)
- relevance_score 0.4–0.7 means moderate relevance (useful context)
- relevance_score below 0.4: set relevant to false, rationale to null
- Do not inflate scores. Be conservative.
- rationale must be specific to the project, not generic

## Expected Output Format

```json
[
  {
    "post_id": 42,
    "relevant": true,
    "relevance_score": 0.85,
    "rationale": "Describes a batched inference optimization technique directly applicable to the latency reduction work in the inference pipeline refactor."
  },
  {
    "post_id": 43,
    "relevant": false,
    "relevance_score": 0.2,
    "rationale": null
  }
]
```
