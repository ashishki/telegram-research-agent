# Квитанция исследования и проверки пакета

11 октября 2026. Исполнитель: текущая сессия Codex Direct, без override модели/reasoning. Точная наблюдаемая модель и effort этой сессии не доступны в runtime telemetry и не выдумываются. Независимый reviewer этого пакета не запускался; ниже структурная проверка и собственная сверка, не independent PASS.

Актуальный объём после последнего решения владельца: **62 карточки, Mini App исключён**. Прежние результаты для 63 карточек ниже сохранены как история исследования, не текущее задание.

## Объём и происхождение

Исследованный HEAD: `23312b8` (начальный `master...origin/master`, clean worktree). Ветка пакета: `codex/pa-daily-strategy-20261011`. Исторический runtime/test SHA: `0fbcfd1dde780724ad934aa66825afe17a6efc98`. Датированные receipts прочитаны, старые тесты/модельные вызовы не повторялись. Репозиторий не начинался заново; formal PA/PAI registries и статусы не менялись.

Изучены README, PRODUCT_STATUS, полная PERSONAL_ASSISTANT_SPEC, актуальные boundaries/contract/review/playbook instructions, текущие PAI design/pilot/merge receipts, actual entrypoints/ingress/composition, storage/model/research/Brief/reader/memory/service adapters, retrieval/project/feedback foundations и judge tools. Частные базы, `.env`, токены, личные аккаунты и состояние сервисов не читались.

Публичные первичные источники прочитаны через web/OpenAI Docs: OpenCode Go catalog/endpoints/prices/privacy/usage intent, GPT-4o model/data controls, Graph/Gmail/Calendar/GitHub scopes/lifecycle, LangGraph/Temporal/MCP contracts, BGE-M3 и исследование LLM judges. Точные ссылки стоят рядом с утверждениями в [MODELS_EVAL](MODELS_EVAL.md) и [PRODUCT_ARCHITECTURE](PRODUCT_ARCHITECTURE.md). Публичный models API через web вернул список 45 ID; анонимный `urllib.request.urlopen` из shell получил HTTP403. Это не authenticated account probe.

Ключевые новые выводы: обязательный удобный product path пока не следует из наличия runtime; Brief candidate selection слишком рано ограничена 48 записями; typed routing/context/personalization требуют доведения; public Go catalog не подтверждает production suitability/account availability. Это кодовые наблюдения и проектные выводы с отмеченными границами, не результаты нового живого пилота.

## Изменённые файлы

- `README.md` — вход в стратегию.
- `docs/PRODUCT_STATUS.md` — датированная ссылка на исследование без изменения runtime evidence.
- `docs/CODEX_PROMPT.md` — актуальное задание и первый будущий блок; прежний handoff сохранён в Git.
- `docs/strategy/2026-10-11/README.md` — стратегия, этапы и критерии перехода.
- `docs/strategy/2026-10-11/CODE_AUDIT.md` — 16 проверенных участков и следствия.
- `docs/strategy/2026-10-11/PRODUCT_ARCHITECTURE.md` — UX, research value, память, архитектура и integrations.
- `docs/strategy/2026-10-11/MODELS_EVAL.md` — текущие публичные модели и исполнимый эксперимент.
- `docs/strategy/2026-10-11/backlog.json` — первоначальные 50, с Nebula и Telegram 62 предлагаемые карточки после исключения Mini App и mapping 69 требований.
- `docs/strategy/2026-10-11/BACKLOG.md` — представление этих карточек.
- `docs/strategy/2026-10-11/IMPLEMENTER_START.md` — D01–D03, интерфейсы, случаи и команды.
- `docs/strategy/2026-10-11/RESEARCH_RECEIPT.md` — эта квитанция.

Product source/config, tests, requirements, secrets, services, accounts и старые acceptance states не изменялись. Новая product implementation, deployments, внешние сообщения и inference не выполнялись. Git publication/merge этого пакета не запрашивались и не выполнялись.

## Фактические проверки

| Команда | Наблюдение |
| --- | --- |
| `.venv-pai/bin/python tools/playbook.py --check-pin` | exit0, закреплённый pin подтверждён; model/hook/runtime не включены. |
| `.venv-pai/bin/python tools/check_personal_assistant_plan.py` | exit0, 19 согласованных slices; review_required сохранён. |
| `.venv-pai/bin/python tools/check_pai_plan.py` | exit0, 32 packets, 69 IDs/10 сценариев; draft и 2 отсутствующих planned conditional test files сохранены. |
| `PYTHONPATH=src .venv-pai/bin/python -m prm.cli --help` | exit0; текущие команды подтверждены; предлагаемого runtime-check пока нет. |
| `.venv-pai/bin/python tools/playbook.py playbook_validate --root . --check references` | exit0, errors=0 warnings=0. |
| `.venv-pai/bin/python tools/check_pa_approval_guard.py` | exit0, expected rejection для 51 planned tasks; это не approval. |
| `python3` со структурной проверкой пакета | 50 карточек, ацикличные зависимости включая OR, все 69 spec IDs, 45 существующих regression test paths, 31 явно предложенный новый test path; 280 локальных ссылок/anchors; JSON/Markdown совпадают. |
| `git diff --check` | exit0. |

Product tests не запускались для изменения только документации. Прежние 398 проходят только как датированное доказательство на исходном runtime, не как новый результат. После уточнения владельца добавлен пакетный цикл следующего агента: один Deep Review между пакетами, исправления и узкая перепроверка критических находок, затем дальнейшая работа. Это документальное уточнение не требует повторения законченных проверок всей программы.

`python` отсутствует в shell; фактические проверки используют `python3` или `.venv-pai/bin/python`.

## Оставшиеся решения и следующий шаг

План — proposal. Не получены exact design/human acceptance, разрешение нового private target/cutover, selected personal resources/retention/model scopes и real daily usefulness. Существующие 51 missing formal approvals не закрывались. Public Go usage intent и истекающая privacy policy требуют отдельной проверки перед private assistant нагрузкой; никакой модели не присвоено неподтверждённое превосходство над GPT-4o. Canvas остаётся отложенным владельцем; Nebula выделена по дополнительному поручению в D51–D54, ключ владелец запросит. Реальная проверка ещё не выполнялась.

Готовое следующее задание: [D01–D03](IMPLEMENTER_START.md), локальный synthetic путь. Независимо готовы D05/D06/D10 и подготовка private target D22. Первая безопасная команда: `PYTHONPATH=src .venv-pai/bin/python -m prm.cli --help`. Выбор реальных доступов требуется позднее, после подготовленных конкретных экранов/команд D26/D27.

## Дополнение Nebula по новому поручению владельца

Владелец запросит API key. Дополнение остаётся исследованием/документацией; продуктовый код, конфигурация секретов, БД и сервисы не изменялись. Formal registry statuses не менялись. Исходный общий первый пакет D01–D03 сохранён.

Прочитаны публичные snapshots `UTDNebula/nebula-api@66695fd768b8d5a1e4dc6a3c4df90ddd955553c0` и `UTDNebula/api-tools@5375e688724dce67dc2768dbae82e9af1ebb29e6` через `git clone --quiet --depth 1` в `/tmp/pa-nebula-api-20261011` и `/tmp/pa-nebula-tools-20261011`; код upstream не исполнялся. SHA-256 исследованного `rest/docs/swagger.yaml`: `46eacbe8cdce5dba8e41f347118e8caaa2fb016aa0d435d3ac478f0c3aeb91ec`. Это Git-контракт develop, не production schema.

Публичные страницы репозиториев прочитаны web-инструментом. Два анонимных Python GET документации `/swagger/doc.json` и `/swagger/swagger.json` вернули 403; Swagger JSON через web тоже не получен. Keyed business API, scraper/parser/uploader, paid models и личные источники не вызывались. 403 не интерпретирован как отказ будущему ключу.

Добавлен [UTD_NEBULA.md](UTD_NEBULA.md), пять полных карточек D51–D55 и их mapping. D41 уточнён как Canvas/персональный академический модуль; D44 требует отдельного evidence выбранной Nebula-интеграции. Обновлены strategy README/audit/architecture, корневые README/CODEX_PROMPT/PRODUCT_STATUS, навигация tasks, dated overlay исторического UTD handoff и OWNER-ACCESS-REQUEST. Статус всех новых карточек proposed.

Проверки дополнения: inline `python3` — 55 карточек с обязательными полями, ацикличная DAG включая OR, 69 exact spec IDs, JSON/Markdown parity, 62 локальные файловые ссылки; четыре перечисленных regression test files существуют, три предлагаемых Nebula test files ещё не созданы. `.venv-pai/bin/python tools/playbook.py playbook_validate --root . --check references` — exit 0, errors=0 warnings=0. `git diff --check` — exit 0. Это структурная проверка документов; продуктовые тесты и Deep Review реализации сейчас не запускались.

Остались реальные production schema/quotas/coverage/freshness и полезность — D54; Brief/Watch operator evidence — D53/D39 после выбранного запуска. Они не блокируют независимую разработку. Следующий общий coding block D01–D03, Nebula block NB-1 D51–D52 после своих общих зависимостей. Никаких commit/push/merge в этом дополнении не выполнено.

## Уточнение полного объёма Nebula

Последующее указание владельца: требуется максимально рабочее решение, не минимальный адаптер. Без добавления карточек расширены D51–D55: полный целевой read coverage, выбор готовых компонентов, durable sync/recovery, общий диалог/память, Brief/Watch, 14 дней/20 сценариев/два Brief. Размеры задач и зависимости пересмотрены; D54 завершается после D52/D53/D27, начальный canary — только подэтап. D55 может начаться по пробелу после D51 и должна довести выбранный fallback до проверенного результата, либо явно обосновать not-needed. D44 теперь прямо зависит от D54. Предыдущие записи о малом canary описывают начало проверки, не готовность. Runtime/секреты/подключения не изменены; тесты продукта не запускались.

Проверка последнего уточнения: inline `python3` — PASS (55 карточек, ацикличные зависимости, 69 mapping entries, JSON/Markdown parity, локальные ссылки, явные зависимости D54/D55/D44); `git diff --check` — exit 0; `.venv-pai/bin/python tools/playbook.py playbook_validate --root . --check references` — exit 0, errors=0 warnings=0. Один структурный проход после изменений, без продуктовых тестов/провайдеров/циклов ревью.

## Telegram встроен в единый backlog — 11 октября

Последнее уточнение владельца: новые возможности должны находиться в общем backlog. Добавлены D56–D63; уточнены существующие D02/D04/D05/D19/D25/D26/D27/D28/D34/D38–D44/D47. Всего 63 карточки. Источником исполнения остаётся `backlog.json` и его представление `BACKLOG.md`; порядок включён в общие G0–G4, инструкция — в существующий `IMPLEMENTER_START.md`. Отдельной Telegram-очереди/фаз/задания нет. `TELEGRAM.md` — архитектурное обоснование карточек; `telegram_evidence.json` — публичные источники и наблюдения, не competing plan.

Прочитаны официальные Bot API, Bot Features, Connected Business Bots, Mini Apps, FAQ, Bot Developer Terms и документация Telethon. Ссылки, дата, версии, SHA-256 четырёх публичных HTML snapshots и размеры находятся в `telegram_evidence.json`. Публичный Bot API на дату чтения сообщает 10.3; это не наблюдение поддержки клиентом владельца. Credentials, getMe, BotFather, personal/business sessions и реальные sends не использовались. Public HTML скачан в `/tmp/pa-telegram-research-20261011`; upstream code не исполнялся. Попытка использовать отсутствующий bs4 заменена stdlib HTMLParser без установки зависимостей; отсутствующий shell `python` заменён `python3`.

Pure local probe `PYTHONPATH=src .venv-pai/bin/python /tmp/pa_telegram_probe_20261011.py` — exit 0. Сеть блокировалась до вызовов, DB не использовалась. Наблюдались ignored native Stop, edited owner message и business message, ignored inline navigation; introspection подтвердила sender без rich/draft/thread и chat-only conversation key. `true` в результатах означает **текущее игнорирование**, не PASS новой способности. Это уточнение baseline, не failing regression suite и не integration test.

Изменены только документы: общий README, CODEX_PROMPT, PRODUCT_STATUS, tasks; strategy README/audit/architecture/backlog/JSON/IMPLEMENTER_START/receipt; добавлены TELEGRAM.md и telegram_evidence.json. Nebula и прежний модельный план сохранены. Source/config/tests/requirements, formal registries, `.env`, DB и services не менялись. При проверке worktree обнаружен другой clean detached checkout `/tmp/tra-db6df8d`; активность чужой сессии не устанавливалась. Следующий исполнитель сверяет assignment/HEAD и не повторяет уже выполненное.

Фактические проверки этого дополнения:

| Команда | Результат |
| --- | --- |
| `python3 /tmp/validate_pa_strategy_telegram_20261011.py` | exit 0, 63 полные карточки; DAG acyclic, включая OR; 69 exact spec IDs; JSON/Markdown body parity; 415 local links/anchors в пакете на момент проверки; 48 существующих regression paths и 43 явно предлагаемых новых test paths. Новые component paths существуют либо помечены proposed. |
| Та же структурная проверка | Core D38 не зависит от optional D59–D63; Secretary D62 не зависит от mail/Canvas/topics. Telegram handoff объединён с существующим; changes documentation-only, live observations 0. |
| `.venv-pai/bin/python tools/playbook.py playbook_validate --root . --check references` | exit 0, errors=0 warnings=0. |
| `git diff --check` | exit 0. |

Независимый reviewer, продуктовые pytest, paid models и live canary для этого документационного дополнения не запускались. Проверка ссылок/путей нашла три неверных proposed component references; они исправлены на существующие worker/contracts/watch_jobs до итоговой структурной проверки. Старые исторические проверки не повторялись. SHA остаётся `23312b8ae60f8c8ba885322583db379960af3afc`; review/commit/push/merge нового пакета не утверждаются.

Открытые gates: реальные bot/client версии и поведение rich/draft/Stop; эксперимент тем; выбранная BusinessConnection/peer scope и lifecycle; точность reconciliation своих sends; личный model egress и польза. Отсутствие этих доступов не задерживает независимый UI код/fixtures. Первый общий блок D01–D03, если ещё не закрыт; затем D56; далее dependency-ready D57/D58, один Deep Review между пакетами с исправлениями и узким critical recheck. Следующая безопасная команда — `git status --short --branch`, затем чтение общего `IMPLEMENTER_START.md` и назначенной карточки.

## Исключение Mini App по решению владельца

Владелец явно указал, что Mini App не нужен. D63 удалён из исполнимого backlog, mapping требований и rollout; условное возвращение по результатам эксперимента также снято. Согласованы JSON/Markdown, общий индекс, CODEX_PROMPT, PRODUCT_STATUS, tasks, архитектура и задание исполнителю. D25 сохраняет обычный приватный reader, D58 — нативные Telegram-отчёты. Исследованные публичные Mini Apps sources остаются только историей; реализации по ним нет.

`python3 /tmp/validate_pa_without_miniapp_20261011.py` — exit 0: 62 карточки, ацикличная DAG, 69 spec IDs, JSON/Markdown parity, 411 локальных ссылок/anchors, 48 existing и 42 proposed test paths; D63 отсутствует среди задач и зависимостей требований, Mini App test task отсутствует. Изменения только документационные; продуктовые тесты, сервисы и подключения не запускались.
