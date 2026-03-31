# Telegram Research Agent

Персональная intelligence-система для фильтрации Telegram-сигналов, приоритизации по проектам и управляемого learning loop.

Система уходит от модели "еженедельный AI-дайджест" к модели "личный слой принятия решений":
- что действительно важно сейчас
- что влияет на активные проекты
- что стоит изучить глубже
- что можно проигнорировать без потерь

---

## Что изменилось

Новая целевая архитектура строится вокруг трёх обязательных способностей:
- `Model routing`: дешёвые модели фильтруют поток, сильные модели получают только high-value сигналы
- `Signal-first output`: выход больше не выглядит как информационный дайджест; он разделён на Strong signals, Project relevance, Weak signals, Think layer, Light/cultural, Ignored
- `Personalization`: система учитывает интересы, приоритеты, anti-preferences и накопленную историю выбора

Это меняет и продукт, и порядок разработки. План реализации теперь описан как поэтапный execution roadmap в [docs/tasks.md](/home/ashishki/Documents/dev/ai-stack/projects/telegram-research-agent/docs/tasks.md).

---

## Целевой продукт

На входе:
- Telegram-каналы и их история
- профиль пользователя
- активные проекты
- накопленная история сигналов, решений и learning goals

На выходе:
- краткий weekly intelligence report
- приоритизированные сигналы по силе и проектной релевантности
- learning guidance по реально значимым темам
- прозрачная стоимость каждого запуска и понятная трассировка решений

---

## High-Level Architecture

```text
Telegram ingestion
  -> preprocessing
  -> deterministic scoring
  -> model routing
  -> interpretation
  -> project lens
  -> learning layer
  -> signal-first output
  -> Telegram / files / future surfaces

Cross-cutting:
  personalization
  observability
```

Текущее целевое описание слоёв и их контрактов находится в [docs/architecture.md](/home/ashishki/Documents/dev/ai-stack/projects/telegram-research-agent/docs/architecture.md).

---

## Phased Development

Актуальная последовательность разработки:
1. Baseline stabilization
2. Scoring foundation
3. Model routing
4. Signal-first output
5. Project relevance upgrade
6. Personalization / taste model
7. Learning layer refinement
8. Productization / surface layer

Для каждой фазы зафиксированы:
- цель
- что входит и что не входит
- зависимости
- риски
- критерии готовности
- quality gates

Источник истины: [docs/tasks.md](/home/ashishki/Documents/dev/ai-stack/projects/telegram-research-agent/docs/tasks.md).

---

## Development Workflow

Разработка идёт по циклу:

```text
Strategist -> Orchestrator -> Codex -> Review -> Fixes
```

Роли и правила handoff описаны в:
- [docs/dev-cycle.md](/home/ashishki/Documents/dev/ai-stack/projects/telegram-research-agent/docs/dev-cycle.md)
- [docs/prompts/workflow_orchestrator.md](/home/ashishki/Documents/dev/ai-stack/projects/telegram-research-agent/docs/prompts/workflow_orchestrator.md)
- [docs/IMPLEMENTATION_CONTRACT.md](/home/ashishki/Documents/dev/ai-stack/projects/telegram-research-agent/docs/IMPLEMENTATION_CONTRACT.md)

---

## Operator Commands

| Command | Description | Example |
|---|---|---|
| `score-stats` | Bucket counts and average signal scores for recently scored posts | `python3 src/main.py score-stats` |
| `cost-stats` | LLM cost breakdown grouped by model | `python3 src/main.py cost-stats` |
| `health-check` | DB connectivity/status plus config file presence checks | `python3 src/main.py health-check` |
| `report-preview` | Preview the current signal-first report from the DB | `python3 src/main.py report-preview` |

---

## Documentation That Matters

Ключевые документы:
- [docs/spec.md](/home/ashishki/Documents/dev/ai-stack/projects/telegram-research-agent/docs/spec.md) — product/spec contract
- [docs/architecture.md](/home/ashishki/Documents/dev/ai-stack/projects/telegram-research-agent/docs/architecture.md) — component boundaries and data flow
- [docs/tasks.md](/home/ashishki/Documents/dev/ai-stack/projects/telegram-research-agent/docs/tasks.md) — phased implementation roadmap
- [docs/dev-cycle.md](/home/ashishki/Documents/dev/ai-stack/projects/telegram-research-agent/docs/dev-cycle.md) — execution workflow
- [docs/prompts/](/home/ashishki/Documents/dev/ai-stack/projects/telegram-research-agent/docs/prompts) — prompt contracts

---

## Current Priority

Следующий implementation focus:
- сначала стабилизировать baseline и сделать scoring reproducible
- потом ввести routing layer
- только после этого перестроить output и добавлять personalization

Персонализацию нельзя делать раньше устойчивого scoring и routing. Иначе система начнёт оптимизировать шум.
