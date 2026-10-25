# PA — индекс актуальных документов

Обновлён **25 октября 2026**. Начать с [English README](../README.md), [русского обзора и плана](../README_RU.md) и [подробного статуса](PRODUCT_STATUS.md). Текущий source/rechecked `b00a5cb`, восемь daily-пакетов; следующий D22+D23+D24+D57. Датированные результаты не превращаются в подтверждение live/production при обновлении индекса.

| Потребность | Канонический документ |
| --- | --- |
| Что готово /что нет /почему | [PRODUCT_STATUS](PRODUCT_STATUS.md) |
| Daily62: engineering23, оставшиеся39, зависимости и пакеты | [Strategy](strategy/2026-10-11/README.md), [backlog](strategy/2026-10-11/BACKLOG.md), [JSON](strategy/2026-10-11/backlog.json) |
| Последний код /review /ограничения | [Package08 ledger](verification/DAILY-package-08-D19-D20-D21-D58-20261014.md), [review/rechecks](verification/DAILY-package-08-local-review-20261014.md) |
| Пять режимов и полный конечный продукт | [PERSONAL_ASSISTANT_SPEC](PERSONAL_ASSISTANT_SPEC.md) |
| Реализованный runtime /data/effects | [ARCHITECTURE](ARCHITECTURE.md) |
| Продолжение /current scope | [CODEX_PROMPT](CODEX_PROMPT.md) |
| Датированный foundation baseline:69 требований /10 сценариев | [Evidence projection](verification/PAI-requirement-evidence-20261010.md), [JSON](verification/PAI-requirement-evidence-20261010.json) |
| Реальные model calls /P1 closure /quality на 10 октября | [Go/pilot report](verification/PAI-go-pilot-20261010.md), [receipts](verification/PAI-go-pilot-20261010.json) |
| Просмотреть HTML/PDF/mobile и inputs | [Portable synthetic artifacts](artifacts/pa-20261010/README.md) |
| Foundation master refs /CI на 10 октября | [Integration packet](verification/PAI-master-integration-20261010.md) |
| Сверка README и Git-публикация 25 октября | [Publication receipt](verification/DAILY-docs-publication-20261025.md) |
| Live test account/destination/20 tasks | [Pilot access](verification/PAI-pilot-access-20261010.md), [owner setup](security/OWNER-ACCESS-REQUEST.md) |
| Private target /cutover | [Prepared PAI-28 packet](verification/PAI-28-cutover-packet.md) |
| Полный dependency/scope/test graph | [Tasks](tasks.md), [PAI execution cards](PA_IMPLEMENTATION_TASKS.md), [PAI design](design/PAI.md), [registry](design/PAI.design.json) |
| Оригинальная PA contract map | [PA design](design/PA.md), [registry](design/PA.design.json) |
| Scope/privacy/permission | [Boundaries](ASSISTANT_BOUNDARIES.md), [contract](IMPLEMENTATION_CONTRACT.md) |
| Проверки /commands /expected gates | [TEST_STRATEGY](TEST_STRATEGY.md), [review policy](REVIEW_POLICY.md), [Playbook adoption](PLAYBOOK_ADOPTION.md) |
| Operator/runtime next step | [Operating model](PRODUCT_OPERATING_MODEL.md), [runtime runbook](runbooks/assistant_runtime.md) |
| История решений/ошибок | [Evidence index](EVIDENCE_INDEX.md), [implementation journal](IMPLEMENTATION_JOURNAL.md), [PAI chronological progress](verification/PAI-progress.md) |
| Историческая master-integration authority | [ADR-019](adr/ADR-019-pa-documentation-and-master-merge.md); актуальное назначение — в handoff/publication receipt |

## Что не переписано как новое доказательство

- `*.before-*`, `docs/archive/**`, dated audits/review attempts сохраняют исходные утверждения на своих SHAs/dates.
- Full spec и formal registry не одобрены автоматически; statuses draft/planned остаются.
- Older runbooks про включённый сервис/UTD timer описывают историческое наблюдение, не нынешнее состояние хоста.
- PRM-SN/RFX/report-era документы — specific compatibility/domain references. Их old NEXT-TASK/Terra recipes не текущая PA assignment.
- Local ignored artifacts не единственный источник: curated public synthetic subset опубликован в Git; остальные private/experiment files не копируются целиком.

Current-doc scope и preservations перечислены в integration receipt. Не перечитывать весь исторический архив перед маленьким срезом.
