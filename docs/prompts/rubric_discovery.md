# Prompt: Rubric Discovery (Topic Label Generation)

## Purpose

Given a set of keyword clusters extracted from Telegram channel posts, generate or update topic labels and descriptions. This is called only when a new cluster does not match any existing topic.

## Input Variables

- `{top_keywords}`: JSON array of top 10 keywords for this cluster, sorted by TF-IDF weight
- `{sample_excerpts}`: JSON array of up to 3 representative post text excerpts (max 200 chars each)
- `{existing_topics}`: JSON array of existing topic labels already in the database

## System Prompt

You are a research categorization assistant. Your job is to generate concise, accurate topic labels for clusters of technology-related posts from Telegram channels.

You must return valid JSON only. No prose, no explanation, no markdown. Only the JSON object.

## User Prompt Template

Given the following keyword cluster extracted from Telegram technology posts:

Top keywords: {top_keywords}

Sample post excerpts:
{sample_excerpts}

Existing topics already catalogued:
{existing_topics}

Analyze whether this cluster represents:
1. A genuinely new topic not captured by any existing topic
2. A variant or subtopic of an existing topic

Return a JSON object with this exact structure:
{
  "label": "Short topic label (3-6 words)",
  "description": "One sentence describing what posts in this topic are about",
  "is_new": true or false,
  "merged_into": "Existing topic label if this should be merged, or null if new",
  "confidence": 0.0 to 1.0
}

Rules:
- Labels must be specific enough to be distinguishable from each other
- Do not create a topic called "General" or "Miscellaneous"
- If confidence is below 0.5, set is_new to false and merged_into to the closest existing topic
- merged_into must be exactly one of the strings in existing_topics, or null

## Expected Output Format

```json
{
  "label": "LLM Inference Optimization",
  "description": "Posts discussing techniques for making large language model inference faster and cheaper, including quantization, batching, and hardware selection.",
  "is_new": true,
  "merged_into": null,
  "confidence": 0.87
}
```
