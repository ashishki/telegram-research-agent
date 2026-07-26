# Agent Evaluation Plan

Status: draft because Agentic profile is ON

## Why Agentic Is ON

Current PI chat uses an LLM planner that can select up to 4 read-only tools
before answer synthesis. The target assistant may retain a bounded iterative
multi-tool loop. This is agentic enough to require harness, trace, termination,
and recovery evaluation. It does not justify T3 runtime.

## Harness Properties

- max tool calls per turn is bounded;
- tool catalog is allowlisted;
- write tools are proposal-and-confirmation gated;
- no hidden mutation tools;
- no child agent completion authority;
- deterministic fallback when tool planning fails;
- `insufficient_evidence` is a valid terminal state.

## Evaluation Scenarios

- exact archive search uses `search_telegram_archive`;
- reaction recall uses reacted-post path;
- project question combines archive and project context;
- current/high-stakes question requests external verification;
- no-answer query stops without fabrication;
- save request proposes but does not write;
- tool failure returns bounded error and no hidden retry loop.

## Required Evidence

- tool trace fixture;
- termination reason;
- result evidence status;
- latency/cost per retrieval and generation stage;
- privacy review for prompt/context/log handling.
