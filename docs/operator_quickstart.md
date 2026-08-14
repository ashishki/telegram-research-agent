# Operator Quickstart

Status: draft for PRM-UX planning
Date: 2026-08-12

## 1. What do I send to the bot?

Send a normal text or voice message. Use Russian when you want the answer in
Russian.

Examples:

```text
Какие практики agent evals обсуждались за последние 90 дней?
Что из этого применимо к telegram-research-agent?
Собери бриф для поста про AI adoption и workflow.
Что важно по моделям за последние две недели?
```

Manual commands such as `/research`, `/brief`, and `/chat` are fallback
controls, not the normal workflow.

For a non-obvious request, the assistant may first say in one line how it will
handle it. If the goal is unclear, it asks one short choice: archive research
or an editor brief.

The current conversation context is temporary: a follow-up can use the recent
topic for up to 30 minutes. A new topic, an explicit command, or a restart
starts a new conversation rather than creating permanent memory.

## 2. What kind of answer should I receive?

The normal answer is:

- `Короткий вывод`;
- `Что найдено`;
- `Почему это важно тебе`;
- `Что сделать`;
- `Чего пока не делать`;
- `Где доказательства слабые`;
- `Источники`.

Ordinary Telegram answers should not show debug metrics, token counts, model
call counts, local paths, raw DB IDs, or unexplained internal labels.

## 3. How do I save something?

Use the post-answer save action when it exists, or ask:

```text
Сохрани это как заметку
Следи за этой темой
Привяжи к проекту telegram-research-agent
```

The assistant should show a compact proposal first. Nothing durable should be
written until you explicitly confirm.

## 4. How do I refresh the archive?

Current approved routine: weekly bounded archive refresh timer.

Manual refresh requires explicit approval because it writes the canonical local
archive:

```bash
PYTHONPATH=src python3 src/main.py memory refresh-archive \
  --days 21 \
  --confirm-canonical-write \
  --json
```

Target Telegram action `/refresh` remains planned; PRM-MAT-8 defines the
owner-only, independently reported refresh lifecycle. It is not implemented by this
document.

## 5. How do I leave feedback?

Use short feedback after an answer:

```text
полезно
мимо
слишком shallow
не тот приоритет
применил
```

Voice feedback should enter the same proposal/confirmation path as text.

## 6. What does the system not do?

It does not:

- start autonomous production testing without explicit approval;
- prove product value before real labels;
- run unrestricted web research;
- use external embeddings or hosted vector services;
- save memory without confirmation;
- mutate code/config/projects automatically;
- generate weekly reports as the product center;
- treat legacy bot/report timers as the PRM product.

## 7. Where do I see current health?

Local status:

```bash
PYTHONPATH=src python3 src/main.py memory status --json
```

Gate status:

- `evals/prm18_release_gate_receipt_2026-08-11_post_prm28.json`
- `docs/audit/PRM_MANUAL_TELEGRAM_ASSISTANT_ACTIVATION_2026-08-11.md`
- `docs/audit/PRM_MANUAL_ARCHIVE_REFRESH_2026-08-12.md`
- `docs/audit/PRM_WEEKLY_ARCHIVE_REFRESH_TIMER_2026-08-12.md`
