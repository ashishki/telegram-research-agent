# Telegram Channel Intelligence

Status: design direction

## Purpose

Evolve the private Telegram Research Agent toward evidence-backed channel
intelligence without turning it into a generic summarizer.

The product value is not "summarize Telegram." It is:

- what narratives are emerging
- which claims repeat across sources
- which channels are noisy or useful
- which source behavior changes over time
- which signals matter for current projects

## MVP Scope

- Weekly operator usefulness log.
- Source citations for recommendations.
- Repeated claim tracking.
- Topic/entity graph.
- Source trust signals based on observed behavior, not model opinion.
- Optional research brief receipt:
  - source window
  - channels used
  - model/config
  - generated report path
  - evidence files
  - verification status

## Non-Goals

- No generic public bot.
- No automated outreach.
- No uncited recommendations.
- No source reputation claims without observed evidence.
