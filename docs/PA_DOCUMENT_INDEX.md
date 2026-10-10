# PA — индекс актуальных документов

Обновлён10 октября2026. Начать с [README](../README.md) и [подробного статуса](PRODUCT_STATUS.md). Датированные результаты не превращаются в подтверждение live/production при обновлении индекса.

| Потребность | Канонический документ |
| --- | --- |
| Что готово /что нет /почему | [PRODUCT_STATUS](PRODUCT_STATUS.md) |
| Пять режимов и полный конечный продукт | [PERSONAL_ASSISTANT_SPEC](PERSONAL_ASSISTANT_SPEC.md) |
| Реализованный runtime /data/effects | [ARCHITECTURE](ARCHITECTURE.md) |
| Продолжение /current scope | [CODEX_PROMPT](CODEX_PROMPT.md) |
| Каждое69 требование /10 сценариев | [Evidence projection](verification/PAI-requirement-evidence-20261010.md), [JSON](verification/PAI-requirement-evidence-20261010.json) |
| Реальные model calls /P1 closure /quality | [Go/pilot report](verification/PAI-go-pilot-20261010.md), [receipts](verification/PAI-go-pilot-20261010.json) |
| Просмотреть HTML/PDF/mobile и inputs | [Portable synthetic artifacts](artifacts/pa-20261010/README.md) |
| Master refs /current CI checks | [Integration packet](verification/PAI-master-integration-20261010.md) |
| Live test account/destination/20 tasks | [Pilot access](verification/PAI-pilot-access-20261010.md), [owner setup](security/OWNER-ACCESS-REQUEST.md) |
| Private target /cutover | [Prepared PAI-28 packet](verification/PAI-28-cutover-packet.md) |
| Полный dependency/scope/test graph | [Tasks](tasks.md), [PAI execution cards](PA_IMPLEMENTATION_TASKS.md), [PAI design](design/PAI.md), [registry](design/PAI.design.json) |
| Оригинальная PA contract map | [PA design](design/PA.md), [registry](design/PA.design.json) |
| Scope/privacy/permission | [Boundaries](ASSISTANT_BOUNDARIES.md), [contract](IMPLEMENTATION_CONTRACT.md) |
| Проверки /commands /expected gates | [TEST_STRATEGY](TEST_STRATEGY.md), [review policy](REVIEW_POLICY.md), [Playbook adoption](PLAYBOOK_ADOPTION.md) |
| Operator/runtime next step | [Operating model](PRODUCT_OPERATING_MODEL.md), [runtime runbook](runbooks/assistant_runtime.md) |
| История решений/ошибок | [Evidence index](EVIDENCE_INDEX.md), [implementation journal](IMPLEMENTATION_JOURNAL.md), [PAI chronological progress](verification/PAI-progress.md) |
| Последняя Git authority | [ADR-019](adr/ADR-019-pa-documentation-and-master-merge.md) |

## Что не переписано как новое доказательство

- `*.before-*`, `docs/archive/**`, dated audits/review attempts сохраняют исходные утверждения на своих SHAs/dates.
- Full spec и formal registry не одобрены автоматически; statuses draft/planned остаются.
- Older runbooks про включённый сервис/UTD timer описывают историческое наблюдение, не нынешнее состояние хоста.
- PRM-SN/RFX/report-era документы — specific compatibility/domain references. Их old NEXT-TASK/Terra recipes не текущая PA assignment.
- Local ignored artifacts не единственный источник: curated public synthetic subset опубликован в Git; остальные private/experiment files не копируются целиком.

Current-doc scope и preservations перечислены в integration receipt. Не перечитывать весь исторический архив перед маленьким срезом.
