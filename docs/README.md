# Документация репозитория

Актуальное состояние10 октября2026: [README продукта](../README.md), [PRODUCT_STATUS](PRODUCT_STATUS.md), [PA_DOCUMENT_INDEX](PA_DOCUMENT_INDEX.md). Основной workstream — полный Personal AI Assistant, Chat/Search/Brief/Watch/confirmed Act.

## Текущая реализация и доказательство

- [Архитектура](ARCHITECTURE.md): durable local composition/storage/effects и private/live границы.
- [Статус](PRODUCT_STATUS.md): весь PAI-00…31, результаты, недоказанное и причины.
- [69/10 evidence matrix](verification/PAI-requirement-evidence-20261010.md).
- [Go assessment/P1 fixes](verification/PAI-go-pilot-20261010.md).
- [Portable Brief/receipts](artifacts/pa-20261010/README.md).
- [Master integration](verification/PAI-master-integration-20261010.md).

## План и продолжение

- [Handoff](CODEX_PROMPT.md), [full spec](PERSONAL_ASSISTANT_SPEC.md).
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
