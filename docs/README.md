# Документация репозитория

Сверка документации: **25 октября 2026**. [English README](../README.md), [русский обзор и план](../README_RU.md), [PRODUCT_STATUS](PRODUCT_STATUS.md), [PA_DOCUMENT_INDEX](PA_DOCUMENT_INDEX.md). Основной workstream — полный Personal AI Assistant, Chat/Search/Brief/Watch/confirmed Act; Mini App исключён.

Текущий source/rechecked `b00a5cb`, package handoff `865a7d8`: восемь локальных пакетов, D01–D21/D56/D58, engineering evidence для23 из62 карточек. Остальные39 включают обязательные и условные ветви, это не процент готовности. Следующий пакет **D22+D23+D24+D57**. Реальные подключения, постоянная эксплуатация и human/formal acceptance открыты; дата этой сверки не обновляет датированные test/provider результаты.

## Текущая реализация и доказательство

- [Архитектура](ARCHITECTURE.md): durable local composition/storage/effects и private/live границы.
- [Статус](PRODUCT_STATUS.md): текущие daily-пакеты, foundation PAI-00…31, результаты, недоказанное и причины.
- [Последний daily ledger](verification/DAILY-package-08-D19-D20-D21-D58-20261014.md), [review/rechecks](verification/DAILY-package-08-local-review-20261014.md).
- [69/10 evidence matrix — 10 октября](verification/PAI-requirement-evidence-20261010.md).
- [Go assessment/P1 fixes — 10 октября](verification/PAI-go-pilot-20261010.md).
- [Portable Brief/receipts](artifacts/pa-20261010/README.md).
- [Foundation master integration — 10 октября](verification/PAI-master-integration-20261010.md).
- [Сверка README и Git-публикация — 25 октября](verification/DAILY-docs-publication-20261025.md).

## План и продолжение

- [Handoff](CODEX_PROMPT.md), [full spec](PERSONAL_ASSISTANT_SPEC.md).
- [Стратегия ежедневного ассистента](strategy/2026-10-11/README.md), [единый backlog62](strategy/2026-10-11/BACKLOG.md), [машинный план](strategy/2026-10-11/backlog.json).
- [Task graph](tasks.md), [PAI cards](PA_IMPLEMENTATION_TASKS.md), [PAI registry](design/PAI.design.json).
- [Pilot access20 tasks](verification/PAI-pilot-access-20261010.md), [cutover preparation](verification/PAI-28-cutover-packet.md).
- [Operating model](PRODUCT_OPERATING_MODEL.md), [runtime runbook](runbooks/assistant_runtime.md).

## Контракты и verification

- [Implementation contract](IMPLEMENTATION_CONTRACT.md), [boundaries](ASSISTANT_BOUNDARIES.md).
- [Test strategy](TEST_STRATEGY.md), [review policy](REVIEW_POLICY.md), [Playbook pin/setup](PLAYBOOK_ADOPTION.md).
- [Evidence index](EVIDENCE_INDEX.md), [journal](IMPLEMENTATION_JOURNAL.md), [chronological PAI progress](verification/PAI-progress.md).
- [Owner access request](security/OWNER-ACCESS-REQUEST.md), [academic original handoff](UTD_ACADEMIC_INBOX_RESEARCH_HANDOFF.md).

## Исторические и предметные материалы

PRM-SN/RFX/UTD/report-era contracts, audits, roadmap и `docs/archive/**` сохраняются как references. Это не действующая команда запускать старый runtime/таймер/paid review. Последние local/provider proofs имеют конкретные SHA; model score не human acceptance. Private source/account data и tokens в документацию Git не публикуются.
