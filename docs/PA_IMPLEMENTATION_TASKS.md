# Personal Assistant: задания для полной реализации

## Наблюдённое состояние — 10 октября2026

Этот документ сохраняет формальные карточки/зависимости2026-10-06. Не начинать PAI-00 заново из старого launch note. Local runtime0fbcfd1 прошёл398/69/10; original deletion и multipart P1 независимо закрыты116/117; code/wiring по каждому пакету — [PRODUCT_STATUS](PRODUCT_STATUS.md), formal acceptance остаётся draft/planned. Live27/28/29 и conditional30/31 имеют явные незакрытые границы. Последнее поручение — документировать и интегрировать master, не включать production.

Дата: 2026-10-06. Основа: [стратегия](PA_SCALING_STRATEGY_2026-10-06.md),
[полная спецификация](PERSONAL_ASSISTANT_SPEC.md), [PA-задачи](tasks.md).
Исходный код при подготовке: `8faee4232cb30e6b6f39cfbd974c151846f79da6`.

**Как пользоваться:** выбрать Sol в рабочей сессии, дать
[стартовый промпт](prompts/pa_sol_implementation.md) и начать с **PAI-00**.
Далее идти по таблице, пропуская только задачи с реальным внешним блокером
или невыполненными зависимостями. Каждая карточка заканчивается проверяемым
результатом и записью следующей задачи. Перечитывать весь план каждый раз
не требуется.

Здесь **30 обязательных задач PAI-00…29 и две условные PAI-30…31**.
Это детализация оставшейся работы, а не повтор PA-00…18 с нуля.
Существующие контракты и пройденные сценарии переиспользовать. Продукт готов
после PAI-29 и действительной PA-18 приёмки; отсутствие выбранного обязательного
подключения остаётся блокером полной готовности.

## Что именно строим

- Один модульный монолит с отдельными процессами для долгой работы.
- PostgreSQL — общее состояние PA и очередь. Канонический Telegram-архив
  и FTS первоначально остаются в SQLite.
- Общие разрешения, бюджеты, подтверждения и квитанции для всех процессов.
- В одной беседе: нормальный Chat, архивный и внешний Search, полезные красивые
  Brief, управляемый Watch, подтверждаемый Act, почта/календарь/Academic,
  память, голос и документы.
- Redis и перенос всего архива — только по результатам измерений. Они не
  являются скрытыми обязательными зависимостями выпуска.

Это рекомендуемое направление для оформления дизайна в PAI-01. Публикация
этих карточек сама по себе не является принятием архитектуры или разрешением
на реализацию/production. Изначальное поручение было подготовкой заданий; 2026-10-06 владелец назначил
выполнение по Sol prompt. Состояние исполнения — в PAI-progress, новый draft
scope — docs/design/PAI.md. Design/live approval этим не создаётся.

## Правила выполнения карточек

1. **Два разных реестра.** PAI — номера понятных инженерных пакетов в этом
   документе. PA — формальные срезы Playbook. Поле `PA-Refs` задаёт покрытие
   требований, а не заменяет formal dependencies. В PAI-00/01 оформлено
   сопоставление с отдельным draft feature PAI: формальные PAI-00..31 добавлены
   в docs/tasks.md и docs/design/PAI.design.json через pinned scaffold.
   Регистрация не означает approval, приёмку или выбранный planning decision.
2. **Модель.** Исполнитель — выбранная владельцем Sol в текущей сессии.
   Этот документ не фиксирует API model ID, не переключает модель и не
   назначает исполнителя собственным независимым reviewer.
3. **Полномочия.** После назначения локальной реализации выполнять её без
   нового согласования каждого файла/теста. До live-gates использовать
   synthetic данные и fake transports. Изолированная тестовая PostgreSQL
   разрешается в составе назначенной PAI-02: отдельная БД/роль/порты, явный
   test DSN, без чтения production DSN, `.env` и приватных данных.
4. **Вертикальный результат.** Interface, DTO или Protocol сами по себе не
   завершают карточку. Там, где указан пользовательский путь, тест проходит
   через настоящий application/ingress, подменяя только внешний I/O.
5. **Проверки.** У каждой карточки ниже дан точный acceptance command.
   Пути `tests/test_pai_*.py` — **планируемые новые тесты, сейчас их нет**.
   Добавлять их при реализации, с содержательными positive/negative/crash
   cases; зарегистрировать в подходящем tier/проектной проверке до завершения.
   Отсутствующий файл или skipped PostgreSQL suite не считается PASS.
6. **Глубина проверок.** На карточке — её acceptance и затронутые существующие
   тесты. На границе фазы — общий regression floor и независимый review
   изменённого риска. Не запускать весь исторический pytest или всех reviewers
   после каждого маленького патча. Не ослаблять проверки ради зелёного статуса.
7. **Границы ревью.** Фазы: A=00…01, B=02…06, C=07…09, D=10…15,
   E=16…20, F=21…26, G=27…29. Политика/runner уточняются в PAI-00.
   Сначала полностью подготовить reviewable результат. Новые egress, OAuth,
   confirmation, retention и execution boundaries проверяются до их реального
   использования; подтверждённые P0/P1 исправляются и независимо перепроверяются
   до зависимой работы. Reviewer не получает live/private payload по умолчанию.
8. **Статус не равен приёмке.** В карточках стартовый `Status: planned`.
   После работы возможны `in_progress`, `local_verified`, `blocked_external`,
   `live_verified`, `accepted`; для условных — `not_needed` с измеренным
   основанием. Это engineering evidence, не автоматическое изменение PA
   approval. `accepted` требует необходимой человеческой приёмки.
9. **Остановка.** Account/egress/institution/budget/deploy gate блокирует только
   зависящий от него путь. Сохранить blocker и продолжить независимые готовые
   задачи. Не обходить отсутствующий consent и не спрашивать заново уже
   предоставленное согласие в том же scope.
10. **Git.** Работать в назначенной ветке, сохранять чужие изменения. Scoped
    commit/push — по действующим полномочиям сессии; не использовать `git add .`,
    не включать приватные данные и посторонние untracked файлы. Если публикация
    не разрешена, оставить точный локальный diff и evidence без остановки
    независимой локальной работы.

## Порядок

| Фаза | ID | Результат | Зависит от |
| --- | --- | --- | --- |
| A. Подготовка | [PAI-00](#pai-00) | Один актуальный handoff и честная карта готовности | — |
| A | [PAI-01](#pai-01) | Конкретный дизайн и оформленные scope/gates | 00 |
| B. Устойчивое ядро | [PAI-02](#pai-02) | Изолированная PostgreSQL и слой хранения | 01 |
| B | [PAI-03](#pai-03) | Общие grants, отзыв и атомарный бюджет | 02 |
| B | [PAI-04](#pai-04) | Подтверждения и квитанции переживают рестарт | 03 |
| B | [PAI-05](#pai-05) | Беседа и версии результатов переживают рестарт | 03, 04 |
| B | [PAI-06](#pai-06) | Настоящая очередь, worker, checkpoints | 03, 04, 05 |
| C. Исполнение | [PAI-07](#pai-07) | Быстрый Telegram ingress, status/cancel | 05, 06 |
| C | [PAI-08](#pai-08) | Scheduler и восстановимые Watch | 06, 07 |
| C | [PAI-09](#pai-09) | Общая доставка и безопасное восстановление исходов | 04, 07, 08 |
| D. Основной продукт | [PAI-10](#pai-10) | Реальный модельный Chat через общий runtime | 03, 05, 07, 09 |
| D | [PAI-11](#pai-11) | Полезный архивный AI Search | 10 |
| D | [PAI-12](#pai-12) | Внешний поиск и чтение выбранного GitHub ref | 10, 11 |
| D | [PAI-13](#pai-13) | Возобновляемое глубокое исследование | 06, 11, 12 |
| D | [PAI-14](#pai-14) | Редакционный Brief и его обсуждение | 05, 08, 09, 11, 13 |
| D | [PAI-15](#pai-15) | Приватный reader, красивые HTML/PDF/Markdown | 07, 14 |
| E. Личные источники | [PAI-16](#pai-16) | OAuth, secret store и управление подключениями | 03, 07 |
| E | [PAI-17](#pai-17) | Выбранная почта Microsoft Graph в беседе | 10, 14, 16 |
| E | [PAI-18](#pai-18) | Календарь, контакты и разрешение адресатов | 10, 16 |
| E | [PAI-19](#pai-19) | Academic Inbox и разрешённый Canvas adapter | 08, 14, 17, 18 |
| E | [PAI-20](#pai-20) | Настоящие mail/calendar writes за подтверждением | 04, 09, 17, 18 |
| F. Полнота и надёжность | [PAI-21](#pai-21) | Управляемая память и сквозное удаление | 05, 14, 17 |
| F | [PAI-22](#pai-22) | Голос, изображения, документы в той же беседе | 10, 15, 21 |
| F | [PAI-23](#pai-23) | Измеренный model routing, кэш и cost per success | 03, 13, 15, 20, 22 |
| F | [PAI-24](#pai-24) | Status/метрики, backup/restore и пакет развёртывания | 09, 16, 21, 22, 23 |
| F | [PAI-25](#pai-25) | Репетиция миграции и честный rollback | 02, 04, 05, 08, 21, 24 |
| F | [PAI-26](#pai-26) | Полный synthetic E2E, нагрузка и review | 15, 19, 20, 22, 23, 24, 25 |
| G. Живое завершение | [PAI-27](#pai-27) | Согласованные реальные интеграции и canary | 26 |
| G | [PAI-28](#pai-28) | Разрешённый production cutover/deploy | 25, 27 |
| G | [PAI-29](#pai-29) | Пилот владельца и полная PA-18 приёмка | 28 |
| Условно | [PAI-30](#pai-30) | Redis, только если он улучшает измерения | 23, 24, 26 |
| Условно | [PAI-31](#pai-31) | Перенос архива в PostgreSQL при необходимости | 11, 25, 26 |

Номера в последнем столбце — PAI. Последовательный проход сверху вниз
достаточен; параллельные агенты не требуются. Если условная задача меняет
release candidate, затронутые проверки 26…29 повторяются для нового SHA.

## Карточки

<a id="pai-00"></a>
### PAI-00 — Убрать противоречия из инструкций и зафиксировать старт

Depends-On: none

PA-Refs: PA-00, PA-01, PA-18

Mode: local-docs

Status: planned

**Результат:** следующий исполнитель однозначно понимает, что уже написано,
что подключено и что ему разрешено.

**Сделать:** сверить HEAD/branch/status и актуальные пути; оформить
`docs/verification/PAI-progress.md` с колонками code/wiring/tests/review/live/
human acceptance. Привести AGENTS, handoff, README, architecture, старые prompts
и skill policy к конкретным исправлениям из стратегии, сохранив safety
contract. Свести reviewer-policy с provenance owner amendments и возможностями
pinned runner; не выдавать Mimo-отчёт за Codex Role Runner receipt. Неизвестное
решение владельца вынести одним конкретным вопросом после подготовки вариантов.

**Контекст:** аудит инструкций в стратегии; `docs/CODEX_PROMPT.md`,
`docs/REVIEW_POLICY.md`, `.playbook/instruction_manifest.json`.

**Готово, когда:** одна текущая задача/граница, нет ложного «PA-00 снова сломан»;
формальные approval ошибки объяснены, но не подавлены. Исторические статусы
сохранены. Есть соответствие всех PAI-карточек PA-требованиям.

**Проверить:** `python3 tools/playbook.py --check-pin`;
`python3 tools/check_personal_assistant_plan.py`;
`python3 tools/playbook.py playbook_validate --root . --check tasks --check references`.
Последний baseline — 19 approval errors; это не зелёный результат.

**Откат:** revert только новых инструкций/ссылок, не истории approvals.

<a id="pai-01"></a>
### PAI-01 — Принять исполнимый дизайн хранения и фоновой работы

Depends-On: PAI-00

PA-Refs: PA-01, PA-02, PA-09, PA-13, PA-16, PA-17

Mode: local-design; human-design-gate

Status: planned

**Результат:** конкретный согласованный проект, по которому можно писать код.

**Сделать:** ADR для PostgreSQL state/jobs + SQLite archive; выбрать очередь
с обоснованием и границами своей реализации/библиотеки; описать ownership
таблиц, versioned job payload, transitions, budgets, lease/fencing,
dispatch/pause/revoke и неизвестные исходы. Зафиксировать запрет слепого
takeover внешней попытки. Выбрать narrow locking или доказанный sequencer,
показать trade-off. Определить retention, план cutover, test DB, SLO/load
profile и registry mapping; параметры с финансовыми/live последствиями
оставить решениями владельца.

**Контекст:** стратегия §§2–4, `docs/design/PA.md`, `PA.design.json`,
`docs/PLAYBOOK_ADOPTION.md`, `capabilities.py`, `watch_jobs.py`, `confirmed_actions.py`.

**Готово, когда:** scope и новые acceptance suites оформлены через pinned
workflow; обязательный независимый design review выполнен разрешённым способом;
нужное hash-bound human approval получено реально. Если approval отсутствует,
design пакет завершён, gate отмечен; изменять его вручную нельзя.

**Проверить:** `python3 tools/check_personal_assistant_plan.py` и pinned
validator из PAI-00; `python3 tools/playbook.py feature_workflow --help`
для выбора реальных plan/draft/review/approve команд зарегистрированного task.
Не придумывать approval flags или task IDs.

**Откат:** отозвать предложенный design через workflow; production не меняется.

<a id="pai-02"></a>
### PAI-02 — Подготовить PostgreSQL для локальной разработки и тестов

Depends-On: PAI-01

PA-Refs: PA-01, PA-17

Mode: local-synthetic

Status: planned

**Результат:** тестовый runtime с явным выбором backend и воспроизводимой схемой.

**Сделать:** добавить pinned DB driver и настройку изолированной test DB;
узкие repositories/unit-of-work для нового PA-state; versioned migrations,
schema compatibility и роли. Соединения создаются в своём процессе. Сохранить
архивный SQLite adapter и fixtures; не переписывать весь SQL/ORM. У migration
команды явный target и отказ от production/default пути без нужного scope.

**Контекст/файлы:** `src/db/`, `src/prm/`, `requirements.txt`, test fixtures,
новые `tests/test_pai_storage.py`, документация setup. `.env`, `data/` и
production migrations не исполнять.

**Готово, когда:** чистая test DB создаётся и восстанавливается; migration
повторяемо отказывает на неправильном target/version; real PostgreSQL tests
идут на synthetic data, а не заменены SQLite mocks. Прежний архив читается.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_storage.py tests/test_assistant_contracts.py tests/test_archive_search.py`.

**Откат:** выключить новый backend; удалять можно только явно созданную test DB.

<a id="pai-03"></a>
### PAI-03 — Сделать разрешения и бюджеты общими для всех процессов

Depends-On: PAI-02

PA-Refs: PA-02, PA-16

Mode: local-synthetic

Status: planned

**Результат:** два workers видят один отзыв разрешения и не тратят один бюджет
дважды.

**Сделать:** durable grants/revisions/revocations, reservations/operation groups
и spend ledger. Сохранить purpose separation и существующий transport
contract; перед вызовом проверять текущий grant. Atomically reserve верхнюю
оценку и общий request/job/day/month limit, затем settle usage; unknown не
возвращает резерв без оснований. Очередь содержит refs, не готовое право
или credential. Не добавлять permissive fallback при недоступности БД.

**Контекст/файлы:** `src/prm/capabilities.py`, `model_cost.py`, storage PAI-02,
`tests/test_pai_durable_policy.py`; PA-02 permission/egress suites.

**Готово, когда:** multiprocess race допускает ровно доступный лимит;
revoke/revision между enqueue и transport запрещает вызов; restart не
сбрасывает расход; request/context pair потребляется корректно.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_durable_policy.py tests/test_assistant_permissions.py tests/test_assistant_egress.py tests/test_assistant_grant_codec.py`.

**Откат:** остановить новые egress; не возвращаться к in-memory budget при
включённом multi-worker runtime.

<a id="pai-04"></a>
### PAI-04 — Сохранять подтверждения, попытки и квитанции действий

Depends-On: PAI-03

PA-Refs: PA-00, PA-13

Mode: local-synthetic

Status: planned

**Результат:** повторное нажатие или рестарт не повторяет внешнее действие.

**Сделать:** durable proposal/confirmation/attempt/receipt repositories вместо
`ActionReceiptStore` в памяти; atomic one-use claim и idempotency по scope,
версии и digest. Попытка фиксируется до fake provider effect. Исключение,
crash или потеря ACK оставляет unknown до reconciliation. Сохранить
PA-00 callback bindings, owner tuple и правила drain старых handlers.

**Контекст/файлы:** `confirmed_actions.py`, `assistant/prm_post_answer_actions.py`,
storage, `tests/test_pai_durable_actions.py`.

**Готово, когда:** гонка двух процессов, double click, restart после effect
до receipt, stale proposal, foreign owner и revoke покрыты; ни один
неизвестный исход не становится автоматическим retry.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_durable_actions.py tests/test_assistant_actions.py tests/test_prm_post_answer_actions.py`.

**Откат:** выключить execution, сохранить ledger; старый writer только после drain.

<a id="pai-05"></a>
### PAI-05 — Сохранять беседу и точные версии результатов

Depends-On: PAI-03, PAI-04

PA-Refs: PA-03, PA-07, PA-14

Mode: local-synthetic

Status: planned

**Результат:** после перезапуска «объясни второй пункт» относится к правильному
отчёту, а «да» — только к одному текущему предложению.

**Сделать:** durable conversation state, result/object/version refs,
request status, history policy, pending confirmation binding и expiry.
Сохранить BriefDocument identity; immutable result отдельно от navigation.
История, явно сохранённая память и source data — отдельные слои.
Не отправлять сохранённую историю модели без соответствующего scope.

**Контекст/файлы:** `conversation.py`, `briefs.py`, `application.py`,
`tests/test_pai_durable_conversation.py`.

**Готово, когда:** restart, новая тема, отмена, старый callback, две pending
proposals и expiry дают правильный результат; retained history удаляется
по выбранной политике; беседа другого owner недоступна.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_durable_conversation.py tests/test_assistant_conversation.py tests/test_assistant_report_dialogue.py`.

**Откат:** читать сохранённые объекты; отключить неподдерживаемые переходы,
не превращать старые ссылки в новое подтверждение.

<a id="pai-06"></a>
### PAI-06 — Реализовать очередь и worker, переживающие падение

Depends-On: PAI-03, PAI-04, PAI-05

PA-Refs: PA-06, PA-09, PA-17

Mode: local-synthetic

Status: planned

**Результат:** задача выполняется отдельным процессом и возобновляется с
безопасного checkpoint.

**Сделать:** PostgreSQL jobs, atomic enqueue с доменным изменением, bounded
claim, lease/heartbeat/fencing, checkpoints, deadline/cancel, retry/backoff,
quarantine и priorities. Versioned payload содержит refs/digests, не pickle,
callbacks или secrets. Pure/read/compute retry отделить от unknown external
effect. Начать с небольшой реализации выбранного в PAI-01 решения.

**Контекст/файлы:** `research_worker.py`, `deep_research.py`, `watch_jobs.py`,
новый worker runtime и `tests/test_pai_workers.py`.

**Готово, когда:** реальные два test processes не берут один claim; старое
поколение не записывает результат; killed worker восстанавливает compute,
но не пересылает unknown action; limits/backpressure работают.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_workers.py tests/test_assistant_jobs.py tests/test_assistant_research.py`.

**Откат:** прекратить claims, drain/record in-flight; jobs не удалять.

<a id="pai-07"></a>
### PAI-07 — Освободить Telegram polling от долгих задач

Depends-On: PAI-05, PAI-06

PA-Refs: PA-03, PA-06, PA-09

Mode: local-synthetic

Status: planned

**Результат:** бот принимает новый запрос и отмену, пока готовится предыдущий.

**Сделать:** durable inbox/update dedup и transaction enqueue; быстрый
acknowledgement только после сохранения. Подключить job status/progress/cancel
к обычной беседе и CLI. Результат возвращается по своему request/result ID,
не текущему `last_topic`. Проверить private tuple для текста, voice и callbacks.

**Контекст/файлы:** `bot/bot.py`, `bot/prm_handlers.py`, `prm/application.py`,
`prm/cli.py`, `tests/test_pai_ingress_jobs.py`.

**Готово, когда:** через настоящий ingress fake long job не блокирует другой
запрос; duplicate update не создаёт вторую job; restart сохраняет status;
cancel прекращает будущие steps. Не писать «в фоне», если enqueue не состоялся.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_ingress_jobs.py tests/test_prm_bot_dispatch.py tests/test_callbacks.py tests/test_prm_cli.py`.

**Откат:** прекратить новый job intake, сохранить доступ к status/cancel/results.

<a id="pai-08"></a>
### PAI-08 — Подключить планировщик и жизненный цикл Watch

Depends-On: PAI-06, PAI-07

PA-Refs: PA-09, PA-12

Mode: local-synthetic

Status: planned

**Результат:** подтверждённая подписка действительно создаёт задания по времени
и восстанавливается без лавины старых уведомлений.

**Сделать:** durable schedules, occurrences, next_due_at и scheduler lease;
одна транзакция enqueue + продвижение расписания. Встроить PA-09
material-change detection, quiet hours/DST, deadline recalculation,
pause/unsubscribe/snooze/done и caps. Background collection/delivery grants
проверяются отдельно. Старый UTD watch не становится согласием на новые источники.

**Контекст/файлы:** `watch_jobs.py`, `external_watch/` только нужные adapters,
`tests/test_pai_scheduler.py`; fixture clock и provider.

**Готово, когда:** два scheduler, повтор tick, downtime, DST, изменение срока,
revoke и paused scope проходят; UI различает сохранённое намерение и реально
работающий scheduler. Никакой systemd timer не включён этим тестом.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_scheduler.py tests/test_assistant_jobs.py tests/test_assistant_subscriptions.py`.

**Откат:** остановить scheduler, сохранить subscriptions/occurrences/receipts.

<a id="pai-09"></a>
### PAI-09 — Сделать общий executor доставки и сверки исходов

Depends-On: PAI-04, PAI-07, PAI-08

PA-Refs: PA-02, PA-09, PA-13

Mode: local-synthetic

Status: planned

**Результат:** ответ, Watch и действие проходят один контракт последнего
разрешения и правдиво показывают исход.

**Сделать:** подключить durable attempts/receipts к foreground/background
delivery; отдельные purposes сохранить. Выполнить согласованное в PAI-01
упорядочивание pause/revoke/send. Не выносить `sender` из SQLite transaction
без эквивалентного доказанного поведения. Ввести provider reconciliation
adapter и UI для unknown; receipts выдаются после реального transport результата.

**Контекст/файлы:** `watch_jobs.py`, `confirmed_actions.py`,
`bot/telegram_delivery.py`, `bot/prm_handlers.py`, `tests/test_pai_delivery.py`.

**Готово, когда:** fake server принял effect, но ACK потерян — повтор не
происходит; pause/revoke race и старый lease не обходят guard; unknown без
возможности проверки остаётся unknown. Реальных отправок ещё нет.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_delivery.py tests/test_assistant_jobs.py tests/test_assistant_actions.py tests/test_assistant_egress.py`.

**Откат:** stop новых effects, reconciliation/read-only оставить доступными.

<a id="pai-10"></a>
### PAI-10 — Подключить нормальный AI Chat к рабочему приложению

Depends-On: PAI-03, PAI-05, PAI-07, PAI-09

PA-Refs: PA-03, PA-16

Mode: local-synthetic

Status: planned

**Результат:** приветствие, объяснение и редактирование текста проходят
реальный model route и возвращаются в ту же беседу.

**Сделать:** единый runtime composition root внедряет model access/provider
в Telegram/CLI/application. Provider/model config явные, без hardcoded
«лучшая модель»; реальный HTTP adapter тестируется fake server. Бounded history
и object followups собираются только в разрешённом data scope. Privacy-safe
fallback, timeouts, отмена и usage settlement обязательны.

**Контекст/файлы:** `application.py`, `conversation.py`, `src/llm/`,
`bot/bot.py`, `tests/test_pai_chat_runtime.py`.

**Готово, когда:** 10–20 последовательных ходов, смена темы, «коротко» и
неоднозначное «да» ведут себя правильно; отсутствие grants не делает HTTP
вызов. Наличие fake client только в unit test недостаточно для wiring.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_chat_runtime.py tests/test_assistant_conversation.py tests/test_prm_application.py tests/test_openai_provider.py tests/test_llm_client.py`.

**Откат:** отключить модельный маршрут; доступный локальный поиск сохранить.

<a id="pai-11"></a>
### PAI-11 — Довести архивный AI Search до полезного ответа

Depends-On: PAI-10

PA-Refs: PA-04

Mode: local-synthetic

Status: planned

**Результат:** запрос на русском/английском находит нужные материалы и даёт
синтез с проверяемыми основаниями.

**Сделать:** соединить FTS retrieval, bounded evidence, paired request/context
authorization и archive synthesis с ingress. Зафиксировать RU/EN holdout
до настройки; отдельно измерять recall, unsupported claims, false refusals,
пропущенные важные материалы. Сохранить source IDs, negation/conflict и
insufficient evidence. Не добавлять vector DB без отдельного measured ADR.

**Контекст/файлы:** `src/db/archive_search.py`, `prm/archive_context.py`,
`archive_synthesis_transport.py`, `synthesis.py`, `tests/test_pai_archive_search.py`.

**Готово, когда:** end-to-end positive/empty/conflict/revoked cases проходят;
bounded excerpts действительно совпадают с разрешёнными источниками;
улучшения recall не скрывают ухудшение factual support.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_archive_search.py tests/test_archive_search.py tests/test_prm_synthesis.py tests/test_prm_intent_archive_contract.py`.

**Откат:** прежний FTS/evidence fallback; канонический архив не переписывается.

<a id="pai-12"></a>
### PAI-12 — Подключить внешний поиск и контекст GitHub

Depends-On: PAI-10, PAI-11

PA-Refs: PA-05, PA-06

Mode: local-synthetic

Status: planned

**Результат:** приложение умеет проверить свежий факт и сравнить его с
материалами владельца/выбранным ref репозитория.

**Сделать:** реализовать конкретный search adapter, безопасный fetch/extract
и GitHub read adapter; внедрить в composition root. Выбор провайдера и API
подтвердить официальной документацией при реализации. Public query отдельно
минимизируется и не наследует private text. Ограничить DNS/redirect/actual
connection, size/time/content type; untrusted text не выдаёт инструментам прав.

**Контекст/файлы:** `public_web.py`, `research_facade.py`, `deep_research.py`,
`tests/test_pai_web_github.py`, существующий web-search suite.

**Готово, когда:** через fake HTTP проверены snippets-vs-read-doc distinction,
timestamps, partial/conflicting sources, SSRF, redirect/DNS смена, malicious
content; GitHub answer называет действительно прочитанный ref.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_web_github.py tests/test_assistant_web_search.py tests/test_assistant_research.py`.

**Откат:** отключить конкретный adapter, честно сохранить локальный ответ/пробел.

<a id="pai-13"></a>
### PAI-13 — Сделать глубокое исследование отменяемой durable задачей

Depends-On: PAI-06, PAI-11, PAI-12

PA-Refs: PA-06

Mode: local-synthetic

Status: planned

**Результат:** большой вопрос переживает рестарт, показывает прогресс и
заканчивается синтезом, а не списком ссылок.

**Сделать:** перенести ограниченный research plan/gather/gap-check/synthesis/
verify в checkpoints worker. Параллелить только независимые reads в пределах
общего бюджета; отсутствие источника даёт объяснимый partial outcome.
Сохранять evidence versions и расход, не повторять оплаченный завершённый
step без основания. Внешние side effects в research не разрешать.

**Контекст/файлы:** `deep_research.py`, `research_worker.py`, planner/facade,
`tests/test_pai_deep_research.py`.

**Готово, когда:** kill/resume в каждом phase, отмена, потеря провайдера,
исчерпание steps/time/cost и новый вопрос в той же беседе корректны;
выводы о проекте опираются на актуальный ref, а не общий фон модели.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_deep_research.py tests/test_assistant_research.py tests/test_prm_research_planner.py`.

**Откат:** запрет новых deep jobs; уже готовые checkpoints/results доступны.

<a id="pai-14"></a>
### PAI-14 — Собрать полезный недельный Brief и его продолжения

Depends-On: PAI-05, PAI-08, PAI-09, PAI-11, PAI-13

PA-Refs: PA-07, PA-09

Mode: local-synthetic

Status: planned

**Результат:** «что важного за неделю» даёт редакционный обзор событий,
который можно обсудить и обновить.

**Сделать:** полный путь window/timezone → разрешённые источники → event dedup
→ selection/editorial → один immutable BriefDocument → delivery.
Отличать публикацию, событие и обнаружение; хранить coverage/omissions/conflicts.
Сильный отбор и объяснение важности проверять отдельно от цитат и схемы.
«Пункт 2», «для проекта», «сравни недели», «обнови» связывать с версией.
Добавить source hooks для личных источников следующих карточек.

**Контекст/файлы:** `briefs.py`, `brief_editorial.py`, `editorial_transport.py`,
`application.py`, `PA-PRODUCT-QUALITY.md`, `tests/test_pai_brief_runtime.py`.

**Готово, когда:** quiet/partial week, дубли, противоречия, delayed source,
DST и followups проходят; смена представления не перегенерирует факты.
Fixture quality не выдаётся за human/live quality.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_brief_runtime.py tests/test_assistant_briefs.py tests/test_assistant_brief_editorial.py tests/test_assistant_report_dialogue.py`.

**Откат:** отключить schedule/editorial route; сохранить принятые версии отчётов.

<a id="pai-15"></a>
### PAI-15 — Сделать приватное чтение и качественный экспорт отчётов

Depends-On: PAI-07, PAI-14

PA-Refs: PA-08

Mode: local-synthetic

Status: planned

**Результат:** один отчёт читается с телефона в Telegram и приватном reader,
экспортируется в HTML/PDF/Markdown с одинаковыми фактами.

**Сделать:** подключить существующий rendering и access contract к реальному
локально тестируемому reader endpoint/доставке. Owner authentication, expiry,
no indexing, share preview и отсутствие внешних ресурсов обязательны.
Renderer изолировать от сети, ограничить ресурсы, хранить artifacts/version.
Светлая/тёмная тема, keyboard, кириллица, длинные URLs и page overflow проверять
на настоящих synthetic renders, а не строковых шаблонах.

**Контекст/файлы:** `report_exports.py`, `pdf_inspection.py`, bot presentation,
`tests/test_pai_report_runtime.py`; визуальные fixtures вне приватных данных.

**Готово, когда:** чужой/отозванный/истёкший доступ не читает artifact;
Telegram/HTML/PDF показывают те же story/source IDs, ничего не обрезано.
Человеческая визуальная приёмка остаётся в PAI-27/29.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_report_runtime.py tests/test_assistant_report_exports.py tests/test_assistant_report_access.py tests/test_pdf_inspection.py`.

**Откат:** отключить reader/экспорт, сохранить исходный BriefDocument.

<a id="pai-16"></a>
### PAI-16 — Сделать безопасный жизненный цикл подключения аккаунта

Depends-On: PAI-03, PAI-07

PA-Refs: PA-02, PA-10, PA-11, PA-17

Mode: local-synthetic

Status: planned

**Результат:** пользователь видит scope подключения, может подтвердить его,
проверить состояние, отозвать и удалить производные данные.

**Сделать:** конкретный OAuth flow для первого выбранного Graph provider;
state/PKCE/redirect validation, owner/connection binding, минимальные scopes,
защищённое token storage, refresh/revoke/rotation. Concurrent refresh
сериализуется. Secrets никогда не являются payload/log/fixture value.
UI различает ширину provider token и фильтр приложения. Fake OAuth server
проверяет реальный callback/client; новые providers не нужны без выбора.

**Контекст/файлы:** `mail_connector.py`, `schedule_connectors.py`,
`docs/security/PA-10-mail-access-plan.md`, `OWNER-ACCESS-REQUEST.md`,
новые connector/auth adapters, `tests/test_pai_connections.py`.

**Готово, когда:** foreign owner/state, redirect substitution, expired refresh,
revoke во время job и restart корректны; UI не называет configured account
подключённым без успешного handshake. Здесь handshake только synthetic.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_connections.py tests/test_assistant_mail.py tests/test_assistant_calendar.py tests/test_assistant_egress.py`.

**Откат:** disconnect и запрет refresh/egress; сохранность/удаление токенов
согласно выбранной политике, не через вывод в отчёт.

<a id="pai-17"></a>
### PAI-17 — Подключить выбранную почту Microsoft Graph

Depends-On: PAI-10, PAI-14, PAI-16

PA-Refs: PA-10

Mode: local-synthetic

Status: planned

**Результат:** «что требует ответа в почте» и раздел Brief используют выбранную
почту с понятными ссылками, сроками и ограничениями покрытия.

**Сделать:** production-shaped Graph read/search adapter, pagination/delta
checkpoints, minimal fields, thread normalization и derived store. Внутри
adapter всегда вызывается guard до HTTP. Обработка смены/удаления писем,
delta reset, 429 и partial pages обязательна. По умолчанию не загружать
bodies/attachments; если metadata недостаточно для нужной сводки, подготовить
точный новый минимальный scope для владельца, не расширять его молча.

**Контекст/файлы:** `mail_connector.py`, connections PAI-16, jobs/brief/source
composition, `tests/test_pai_graph_mail.py`.

**Готово, когда:** настоящий adapter с fake HTTP проходит multi-page,
deadline conflict, missing data и revoke/delete; беседа даёт сводку, а не
дамп заголовков и не выдуманные действия. Sync cursor продвигается только
после durable обработки страницы.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_graph_mail.py tests/test_assistant_mail.py tests/test_pai_brief_runtime.py`.

**Откат:** отключить sync/source; сохранить независимый Telegram-архив.

<a id="pai-18"></a>
### PAI-18 — Подключить календарь и контакты

Depends-On: PAI-10, PAI-16

PA-Refs: PA-11

Mode: local-synthetic

Status: planned

**Результат:** ассистент показывает конфликты расписания и находит адресата,
не путая аккаунты, зоны времени и совпадающие имена.

**Сделать:** read adapters для выбранного календарного provider, paging/sync,
free/busy, recurrence/exceptions, source/local timezone и deleted/cancelled
events. Contacts — отдельный scope/adapter. Сначала выбранный Graph, если
владелец не выбрал другой; не реализовывать все экосистемы ради симметрии.
Подключить ответы, Brief и watch evidence.

**Контекст/файлы:** `schedule_connectors.py`, PAI-16, application/source adapters,
`tests/test_pai_schedule_runtime.py`.

**Готово, когда:** DST, all-day, recurring exception, несколько аккаунтов,
неоднозначный recipient и revoked calendar видны пользователю; read grant
не выполняет write, email по имени не угадывается.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_schedule_runtime.py tests/test_assistant_calendar.py tests/test_assistant_contacts.py`.

**Откат:** отключить connector; pending actions по нему становятся unavailable.

<a id="pai-19"></a>
### PAI-19 — Объединить Academic Inbox и минимальный Canvas adapter

Depends-On: PAI-08, PAI-14, PAI-17, PAI-18

PA-Refs: PA-12

Mode: local-synthetic; institution-gate-for-live

Status: planned

**Результат:** академическая сводка различает обязательства, возможности и
чтение; напоминания опираются на актуальный подтверждённый срок.

**Сделать:** использовать existing Academic handoff; Canvas adapter для
разрешаемого минимального assignments/calendar/announcements scope;
объединить mail/calendar candidates, provenance, categories, stage profile,
eligibility uncertainty, conflicting dates и completion states.
Не читать grades/roster/submission bodies по умолчанию. Определить
institutional permission до live подключения; offline adapter продолжить.

**Контекст/файлы:** `academic_inbox.py`, `watch_jobs.py`,
`UTD_ACADEMIC_INBOX_RESEARCH_HANDOFF.md`, `tests/test_pai_academic_runtime.py`.

**Готово, когда:** письмо и Canvas с разными сроками дают видимый конфликт;
изменённый срок пересчитывает jobs; локальное «готово» не становится source
submission; повтор кандидата не создаёт второе обязательство.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_academic_runtime.py tests/test_assistant_academic.py tests/test_assistant_subscriptions.py`.

**Откат:** выключить Canvas scope; не скрывать отсутствие источника за «задач нет».

<a id="pai-20"></a>
### PAI-20 — Довести подтверждённые mail/calendar действия до адаптеров

Depends-On: PAI-04, PAI-09, PAI-17, PAI-18

PA-Refs: PA-13

Mode: local-synthetic

Status: planned

**Результат:** находка превращается в редактируемое предложение, точное
подтверждение и проверяемую квитанцию выполнения.

**Сделать:** конкретные executor/reconcile adapters для выбранных mail и
calendar операций. Перед отправкой проверить account, recipient, thread,
content digest, version/ETag и free/busy где нужно. Provider draft тоже write.
Показать последствия, expiry и изменённый preview; старое подтверждение
не переиспользовать. Семантику idempotency/reconciliation проверить по
официальному API, не переносить её с другого провайдера.

**Контекст/файлы:** `confirmed_actions.py`, PAI-09/17/18, application/callbacks,
`tests/test_pai_action_runtime.py`.

**Готово, когда:** настоящий путь preview→edit→confirm→fake provider→receipt
проходит; content/recipient/time change, two clicks, kill/ACK loss, version
conflict и revoke не дают неожиданную запись. Payments/submission/registration
остаются вне tools.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_action_runtime.py tests/test_assistant_actions.py tests/test_pai_delivery.py tests/test_prm_post_answer_actions.py`.

**Откат:** отключить executor, оставить preview и reconciliation существующих
attempts; не удалять receipts.

<a id="pai-21"></a>
### PAI-21 — Подключить память, исправление и сквозное удаление

Depends-On: PAI-05, PAI-14, PAI-17, PAI-19

PA-Refs: PA-14

Mode: local-synthetic

Status: planned

**Результат:** владелец видит, что сохранено, может исправить/забыть/экспортировать;
удалённое не возвращается из кэша или отложенной job.

**Сделать:** wire memory library в разговор и Brief; provenance/confirmation/
versions, lifecycle distinctions, source retention. Durable delete/revoke
workflow инвалидирует derived rows, indexes, caches, jobs и artifacts;
определяет backup retention/tombstones и поведение restore. Пользовательский
экспорт доступен только owner. Не превращать реакцию в постоянный preference.

**Контекст/файлы:** `memory_library.py`, conversation/briefs/state/jobs,
`tests/test_pai_memory_runtime.py`.

**Готово, когда:** inspect→edit→forget→restart→search и concurrent running job
не воскрешают данные; независимый архив не удалён; opened/read/applied не
выводятся из факта индексации. Restore/delete ограничения объяснены честно.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_memory_runtime.py tests/test_assistant_memory.py tests/test_assistant_report_dialogue.py`.

**Откат:** остановить новые mutations; deletion tombstones не откатывать молча.

<a id="pai-22"></a>
### PAI-22 — Подключить голос, изображения и документы к той же беседе

Depends-On: PAI-10, PAI-15, PAI-21

PA-Refs: PA-15

Mode: local-synthetic

Status: planned

**Результат:** voice/image/PDF input продолжает правильный разговор, показывает
редактируемую расшифровку и source/page references.

**Сделать:** media adapters и реальная wiring цепочка download/inspect/text
layer/optional OCR/question/response/cleanup. Сначала локальный текст,
bounded OCR по необходимости, speech response опционален. Проверить
content type/size/active content/archive bombs и resource limits.
Каждая modality получает отдельный purpose; temporary files удаляются
реальным cleanup, включая exception/cancel/restart, не только CleanupPlan.

**Контекст/файлы:** `media_connectors.py`, `pdf_inspection.py`, `bot/voice.py`,
model adapters, `tests/test_pai_media_runtime.py`.

**Готово, когда:** исправленная транскрипция не наследует старую confirmation;
page citations сохраняются; malicious/oversized file не исполняется;
неразрешённый fallback provider не получает документ.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_media_runtime.py tests/test_assistant_media.py tests/test_voice_transcription.py tests/test_pdf_inspection.py`.

**Откат:** отключить новые media types, сохранить plain text и гарантировать cleanup.

<a id="pai-23"></a>
### PAI-23 — Измерять качество, стоимость и полезный эффект кэша

Depends-On: PAI-03, PAI-13, PAI-15, PAI-20, PAI-22

PA-Refs: PA-16

Mode: local-synthetic; budget-gate-for-paid-eval

Status: planned

**Результат:** видны стоимость целой задачи, задержка, маршрут модели и
ограничения; оптимизация не ухудшает согласованное качество.

**Сделать:** подключить versioned model/tariff catalog к реальному runtime;
usage adapter различает input/cache-read/cache-write/output/reasoning по
семантике провайдера. Агрегировать unique user task и все attempts/tools/judges,
а не число успешных реплик. Реализовать caches для extraction/retrieval/
render и допустимый model prefix caching; keys включают scope/version.
Revoke/delete/freshness проверяются на hit. Подготовить paired holdout
strong baseline vs candidate; платное сравнение только в разрешённом scope.

**Контекст/файлы:** `model_cost.py`, `src/llm/`, `COST_BUDGET.md`,
`COST_ARCHITECTURE.md`, `tests/test_pai_cost_cache.py`.

**Готово, когда:** synthetic usage доказывает отсутствие двойного счёта;
unknown price не ноль; limits общие; cache не раскрывает отозванный результат.
Экономия не заявляется до сопоставимого quality evidence.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_cost_cache.py tests/test_assistant_cost.py tests/test_pai_durable_policy.py`.

**Откат:** фиксированный разрешённый baseline, cache bypass с сохранением caps.

<a id="pai-24"></a>
### PAI-24 — Сделать наблюдаемость, восстановление и пакет запуска

Depends-On: PAI-09, PAI-16, PAI-21, PAI-22, PAI-23

PA-Refs: PA-17

Mode: local-synthetic

Status: planned

**Результат:** оператор понимает состояние системы и может восстановить её
по проверенному runbook.

**Сделать:** wired status/readiness/health, metrics/traces с безопасными IDs,
queue age, unknown age, sync freshness, spend, lock/pool wait, disk/backup.
Реализовать backup/restore, а не только план: synthetic PG/state/artifacts,
проверка WAL/backup выбранного способа, restoration isolation. После restore
новая execution epoch, egress off и сверка потерянного интервала.
Подготовить reproducible dependencies, service/container templates,
graceful drain, secret rotation и kill switch; templates не активировать.

**Контекст/файлы:** `operations.py`, `systemd/`, deploy tooling/runbooks,
`tests/test_pai_operations_runtime.py`; historical timers не возрождать.

**Готово, когда:** реальный synthetic backup восстанавливается, unknown
effects не повторяются; DB loss, disk full, 429, revoked token и logs с
secret-shaped fixture values проверены; измерены rehearsal RPO/RTO.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_operations_runtime.py tests/test_assistant_ops.py tests/test_delivery_health.py`;
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py retrofit-boundaries`.

**Откат:** выключить новые процессы/egress, удержать безопасный read-only status;
restore никогда не является автоматическим разрешением отправки.

<a id="pai-25"></a>
### PAI-25 — Прорепетировать перенос состояния и откат без потери квитанций

Depends-On: PAI-02, PAI-04, PAI-05, PAI-08, PAI-21, PAI-24

PA-Refs: PA-00, PA-17

Mode: local-synthetic

Status: planned

**Результат:** готов конкретный cutover plan для выбранных PA-таблиц,
который воспроизведён на копиях synthetic data.

**Сделать:** versioned export/import, counts/checksums/refs, ownership и
digest preservation; финальный freeze/drain, один writer, старый store
read-only. Не переносить весь Telegram-архив. Проверить N/N−1 compatibility,
old confirmation drain и unknown transfer. Rollback после новых записей
переносит ledger delta либо использует forward fix; не возвращает старый
snapshot с повторно действующими подтверждениями. Реальную приватную копию
использовать только по отдельному разрешению.

**Контекст/файлы:** storage/migration tooling, `watch_jobs.py`, action/brief/
memory stores, `tests/test_pai_migration.py`, новый cutover runbook.

**Готово, когда:** rehearsal before/after/rollback совпадает по IDs/digests,
grants/tombstones/receipts; повреждённая запись блокирует переключение;
искусственный crash в каждом шаге не создаёт второго writer или отправки.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_migration.py tests/test_pai_storage.py tests/test_pai_durable_actions.py tests/test_prm_post_answer_actions.py`.

**Откат:** описанный и испытанный reverse-delta/forward-fix путь. Production
cutover не выполнять в этой карточке.

<a id="pai-26"></a>
### PAI-26 — Проверить полный продукт без живых аккаунтов

Depends-On: PAI-15, PAI-19, PAI-20, PAI-22, PAI-23, PAI-24, PAI-25

PA-Refs: PA-18

Mode: local-synthetic; independent-review-gate

Status: planned

**Результат:** один release candidate с полной requirement-to-evidence
матрицей и конкретным списком оставшихся live-gates.

**Сделать:** fixture E2E из спецификации через настоящий composition root и
HTTP/Telegram test doubles; lifecycle connections/actions/memory/media;
load на зафиксированном expected и 2× peak; process kill/restart, stale
lease, budget contention, lost ACK, DB outage, restore и injection из каждого
источника. Зафиксировать p95/queue lag/ресурсы и regression floors.
Независимый review изменённого полного диапазона и P0/P1 recheck — по
согласованной политике и бюджету, без приватного содержимого.

**Контекст/файлы:** spec §13; все новые acceptance suites;
`tests/test_pai_end_to_end.py`, `tests/test_pai_load_recovery.py`,
`docs/verification/PAI-release-candidate.md`.

**Обязательный набор:** SC13.2-01..10 из docs/design/PAI.requirements.json: чат/multiturn; object followups/yes/cancel/restart; архив+web/конфликты/coverage; Brief/dedup/deadlines/outage; Telegram/HTML/PDF mobile/кириллица/dark theme; Watch pause/DST/revoke/unknown; Academic conflicts/done/eligibility; Act edit/confirm/double-click/owner/expiry/version; injection/secrets/query/fallback; restore/migration/delete/cache. Все 69 spec-ID имеют отдельные test/review/human obligations; planned mapping не считается PASS.

**Готово, когда:** каждая обязательная PA-возможность имеет wired positive
и failure evidence, нет открытых P0/P1; отсутствие provider/human proof
указано отдельно. Generic tier и judge не заменяют эту матрицу.

**Проверить:** `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_end_to_end.py tests/test_pai_load_recovery.py`;
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm`;
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py retrofit-boundaries`;
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/playbook.py verify_project --root .`.
Новые suites должны быть действительно включены в соответствующий verifier.
Любой formal approval failure сохранить отдельно, не назвать весь gate PASS.

**Откат:** не продвигать release candidate; исправлять конкретные findings.


Дополнительная обязательная проверка всех 69 requirement cases и десяти сценариев:
`python3 tools/run_pai_acceptance.py --require-spec-matrix -q tests/test_pai_academic_runtime.py tests/test_pai_acceptance_guard.py tests/test_pai_action_runtime.py tests/test_pai_archive_search.py tests/test_pai_brief_runtime.py tests/test_pai_chat_runtime.py tests/test_pai_connections.py tests/test_pai_cost_cache.py tests/test_pai_deep_research.py tests/test_pai_delivery.py tests/test_pai_durable_actions.py tests/test_pai_durable_conversation.py tests/test_pai_durable_policy.py tests/test_pai_end_to_end.py tests/test_pai_graph_mail.py tests/test_pai_ingress_jobs.py tests/test_pai_load_recovery.py tests/test_pai_media_runtime.py tests/test_pai_memory_runtime.py tests/test_pai_migration.py tests/test_pai_operations_runtime.py tests/test_pai_plan.py tests/test_pai_report_runtime.py tests/test_pai_schedule_runtime.py tests/test_pai_scheduler.py tests/test_pai_storage.py tests/test_pai_web_github.py tests/test_pai_workers.py tests/test_pai_requirements.py`.
Нулевой набор, пропущенный case, skipped/xfail или отсутствующий файл дают failure.

<a id="pai-27"></a>
### PAI-27 — Проверить реальные подключения в ограниченном canary

Depends-On: PAI-26

PA-Refs: PA-02, PA-05, PA-09, PA-10, PA-11, PA-12, PA-13, PA-15, PA-16, PA-18

Mode: live; explicit-scoped-grants-required

Status: planned

**Результат:** реальные integrations подтверждены наблюдениями, а не mocks.

**Сначала подготовить:** один reviewable access packet: account/resource/
operation/data/provider, retention, duration, budgets, места хранения secrets,
test recipient/destination, список exact canary действий, stop/cleanup.
Указать реальную ширину OAuth scopes и institutional Canvas gate. Использовать
уже действующие подходящие grants; недостающее согласие запрашивать конкретно,
не просить присылать токены в чат. Canary runtime запускается только в scope
этого разрешения, без production cutover и фоновых таймеров по умолчанию.

**Затем выполнить:** по одному источнику проверить OAuth/read/sync/freshness/
revoke/delete; разрешённые модели и usage; настоящий search/fetch; delivery
с проверяемым receipt. Mail/calendar write — отдельный exact preview/confirm
на контролируемом объекте. Проверить реальные Telegram/HTML/PDF views и
reconciliation только способами, которые поддерживает provider; не изображать
искусственно полученное доказательство как live observation.

**Контекст:** access packet, runbooks PAI-24/25, `OWNER-ACCESS-REQUEST.md`,
evidence matrix PAI-26.

**Готово, когда:** для каждого выбранного обязательного подключения записаны
точные scope/time/version, observed outcome и ограничения; приватные receipts
в защищённом хранилище, в Git только sanitized metadata. Отсутствующий Canvas
или model grant имеет свой blocker и не тормозит независимые проверки.

**Проверить:** сначала PAI-26 commands на текущем SHA. Затем использовать
только реальные canary commands, созданные и записанные в PAI-24/26 packet
с default-off live flags; их argv/results входят в evidence. Здесь намеренно
нет выдуманной команды `connect-all` и универсального флага согласия.

**Откат:** stop canary, revoke выданного test scope, согласованный cleanup;
уже отправленный эффект не объявлять отменённым без проверки.

<a id="pai-28"></a>
### PAI-28 — Выполнить согласованный production cutover и deployment

Depends-On: PAI-25, PAI-27

PA-Refs: PA-17, PA-18

Mode: production; migration-deployment-gate

Status: planned

**Результат:** нужный SHA работает в назначенной среде с проверенной БД,
worker, scheduler и управляемыми capabilities.

**Сначала подготовить:** exact SHA/artifact hashes, migration scope, backup,
окно работ, конфигурация, RPO/RTO, go/no-go/rollback и список реально
включаемых функций. Проверить inventory текущих процессов/таймеров в рамках
разрешённого доступа. Подтверждение deployment не разрешает произвольные
accounts/schedules/sends; сослаться на их отдельные grants.

**Затем выполнить:** frozen intake/drain, fresh backup, approved migration,
verification и один новый writer; запустить agreed runtime, проверить
health/readiness, ingress ownership, job progress и разрешённые smoke cases.
Включать только выбранные schedules. Legacy report timers не включать.

**Готово, когда:** deployment/migration receipts и наблюдаемый SHA совпадают;
нет второго polling/executor, выполнены restore/rollback prerequisites;
ошибки переключают систему в заранее согласованный безопасный режим.

**Проверить:** exact команды из проверенного runbook PAI-25 и release packet
PAI-26, с записанными результатами; новый synthetic regression обязателен,
если SHA изменился. В этой плановой карточке команды production не выполняются.

**Откат:** утверждённый runbook с сохранением новых receipts/unknown/tombstones;
старый snapshot автоматически не восстанавливать.

<a id="pai-29"></a>
### PAI-29 — Пройти пользовательский пилот и закрыть полную PA-18 приёмку

Depends-On: PAI-28

PA-Refs: PA-18

Mode: live-owner-acceptance

Status: planned

**Результат:** владелец принимает полный персональный ассистент по своим
задачам, качеству ответов и эксплуатации.

**Сделать:** до старта зафиксировать 20 начальных задач и длительность
дальнейшего пилота; пройти Chat/Search/Brief/Watch/Act, выбранные личные
источники, memory/media, restore/cancel/revoke. Проверить полезность,
coverage/citations, пропущенные обязательства, шум, latency/cost и visual
quality на телефоне/PDF. Исправления проходят scoped tests и независимые
P0/P1 rechecks, затем повторяются затронутые live cases на новом SHA.

**Контекст:** spec §13, product quality amendment, PAI-progress и release packet.

**Готово, когда:** финальная requirement matrix полна, exact-HEAD checks
и обязательные reviews пройдены, человек явно принял продукт через workflow.
Неподключённый обязательный источник/формат/действие оставляет незавершённость;
не переименовывать результат в MVP или full done с исключением по умолчанию.

**Проверить:** `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/playbook.py verify_project --root .`,
актуальные acceptance/visual/live receipts и реальная human acceptance.
Число тестов или model judge не принимают продукт за владельца.

**Откат:** stop нового rollout/автоматических writes, сохранить рабочие
разрешённые read paths и точную точку продолжения.

<a id="pai-30"></a>
### PAI-30 — Добавить Redis, только если он устраняет измеренный предел

Depends-On: PAI-23, PAI-24, PAI-26

PA-Refs: PA-16, PA-17

Mode: conditional; new-design-scope-required

Status: planned

**Условие запуска:** измерен выигрыш общего кэша или PostgreSQL queue pressure
мешает согласованному SLO. Без условия записать `not_needed` с результатами;
это нормальное завершение условной карточки.

**Сделать при условии:** сначала выбрать конкретную роль Redis. Для cache —
scope/version keys, TTL, revoke invalidation, limits и безопасный miss/failure.
Для Streams — отдельный ADR, transactional outbox в PostgreSQL, dedup,
pending recovery, ACK, persistence, trimming и DLQ. Не использовать Pub/Sub
как durable queue; grants/budget/receipts остаются в authority DB.

**Готово, когда:** cache/broker outage, redelivery и stale state не обходят
policy; paired load доказывает пользу с учётом новой операционной цены.
Production включение отдельно разрешается; обновить PAI-26…29 evidence.

**Проверить:** создать `tests/test_pai_redis.py` только при реализации;
`PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_redis.py tests/test_pai_cost_cache.py tests/test_pai_delivery.py`.

**Откат:** cache bypass или восстановленный PostgreSQL dispatch без потери
domain jobs; никаких повторных effects из потерянного Redis state.

<a id="pai-31"></a>
### PAI-31 — Перенести архив/FTS в PostgreSQL, если SQLite стал ограничением

Depends-On: PAI-11, PAI-25, PAI-26

PA-Refs: PA-04, PA-17

Mode: conditional; canonical-storage-ADR-required

Status: planned

**Условие запуска:** измеренный предел архивного доступа/записи или требование
доступа с нескольких хостов, которое нельзя разумно закрыть текущим adapter.
Без него `not_needed`; размер репозитория сам по себе не основание.

**Сделать при условии:** ADR и отдельный export/import `raw_posts`/`posts`,
сохранение canonical IDs/refs/reactions, rebuild производного поиска.
Сравнить SQLite FTS и PostgreSQL retrieval на одном RU/EN holdout: recall,
exact matches, ranking, source/citation integrity. Cutover одним writer,
тест backward compatibility и reverse-delta/forward-fix; сеть не монтирует
живой SQLite-файл. Vector/microservice не добавлять в этот scope.

**Готово, когда:** data parity и agreed retrieval/SLO выполнены;
проверены backup/restore/rollback. Реальный перенос только по отдельному
migration разрешению с повтором затронутой приёмки PAI-26…29.

**Проверить:** создать `tests/test_pai_archive_migration.py` при реализации;
`PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_archive_migration.py tests/test_archive_search.py tests/test_archive_documents.py tests/test_pai_migration.py`.

**Откат:** испытанный reader/writer switch, сохранение новых данных;
старый архив не удалять до завершения agreed rollback window.

## Что записывать после каждой задачи

В `docs/verification/PAI-progress.md` — одна компактная строка на ID:

| ID | Engineering status | Code SHA / diff | Acceptance commands | Review evidence | Live/human evidence | Blocker | Next |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PAI-00 | planned | — | — | — | — | — | PAI-00 |

Подробный receipt — `docs/verification/PAI-NN-<short-topic>.md`:
исходный/проверенный SHA, changed files, конкретное поведение, exact commands/
exit codes/counts, requested/observed reviewer identity, findings/rechecks,
synthetic/live distinction, rollback, remaining gates и следующая команда.
Не создавать заранее фиктивные PASS/review/live записи. Эта таблица — шаблон;
progress файл создан PAI-00 и отражает фактическую работу.

Следующая команда карточки должна быть исполнимой на получившемся состоянии.
Если её ещё не существует, сначала создать предусмотренный CLI/tool и
проверить `--help`/dry-run. Не оставлять в receipt выдуманный флаг или команду.

## Проверки на границах фаз

| Граница | Что предъявить |
| --- | --- |
| A | Актуальные authority/design records, зарегистрированный scope, acceptance cases, нужные человеческие решения |
| B | Multiprocess/restart tests общего состояния, version compatibility, независимый policy/storage review |
| C | Сквозной request→job→result→delivery на fake transport, cancel/revoke/unknown races |
| D | Согласованный search/content/multiturn holdout и настоящие synthetic renders; существующие regression floors |
| E | Реальные адаптеры на fake HTTP, lifecycle scopes/consent, write/reconciliation cases; privacy review |
| F | Полный offline release packet, load/recovery/restore, отсутствие открытых P0/P1, список точных live-gates |
| G | Реальные scopes/receipts/визуальные наблюдения, deployment evidence, owner acceptance текущего SHA |

Для code-phase boundaries минимум
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm`;
`retrofit-boundaries` добавлять для изменённых runtime/legacy/deploy границ.
Новые карточные acceptance suites запускать независимо, пока они не вошли
в соответствующий tier. Полный historical pytest не нужен.

## Покрытие исходной программы

| PA-требования | Где доводятся до результата |
| --- | --- |
| PA-00/01 baseline/design | PAI-00/01; совместимость и миграция PAI-04/25 |
| PA-02 policy | PAI-03/04/09/16; negative cases во всех adapters |
| PA-03 Chat | PAI-05/07/10 |
| PA-04/05/06 Search/research | PAI-11/12/13, durable runtime PAI-06 |
| PA-07/08 Brief/visual | PAI-14/15; человеческая оценка PAI-27/29 |
| PA-09 Watch | PAI-06/08/09, личные источники PAI-17/18/19 |
| PA-10/11/12 personal/academic | PAI-16/17/18/19 |
| PA-13 Act | PAI-04/09/20 |
| PA-14 memory | PAI-05/21 |
| PA-15 media | PAI-22 |
| PA-16 models/cost | PAI-03/10/23 |
| PA-17 ops | PAI-02/06/24/25/28 |
| PA-18 full acceptance | PAI-26/27/28/29 |

## Статус этого плана

Исторический статус подготовки пакета: все карточки были planned; никакая реализация, review, human approval,
production миграция, запуск таймера или платный вызов этим документом не
заявлены. Историческая стратегия и её 135 тестов — evidence исходного SHA,
а не доказательство выполнения новых карточек. Подготовка этого task pack
не меняет `review_required` у исходного PA design.

Проверка подготовки пакета 2026-10-06: 32 уникальные карточки, обязательные
поля, зависимости без циклов, PA-Refs, локальные ссылки/якоря и существующие
regression test paths проверены локальным Python-чекером. Продуктовые тесты
повторно не запускались: изменены только документы.

| Команда | Наблюдаемый результат |
| --- | --- |
| `python3 tools/playbook.py --check-pin` | Exit 0; pinned kit подтверждён |
| `python3 tools/check_personal_assistant_plan.py` | Exit 0; 19 согласованных PA-срезов; `review_required` |
| `python3 tools/playbook.py playbook_validate --root . --check tasks --check references` | Exit 1; прежние 19 `TASK_DESIGN_APPROVAL_REQUIRED`, новых ошибок нет |
| `git diff --check` | Exit 0 |

Подготовлены этот файл и `docs/prompts/pa_sol_implementation.md`; ссылки и
указание на новое поручение добавлены в `docs/tasks.md` и `docs/CODEX_PROMPT.md`.
Остальные файлы сохранены. Рассмотренный SHA — `8faee4232cb30e6b6f39cfbd974c151846f79da6`;
нового code commit, независимого review и формальной приёмки нет.
Оставшиеся gates перечислены в PAI-00/01/26…29. Следующая карточка — PAI-00;
первая команда новой сессии — `git status --short`, затем launch prompt.

## Исполнение 2026-10-06

Владелец назначил локальную очередь через Sol prompt. PAI-00/01 оформляют
сверку, deterministic baseline и конкретный draft design. Фактические статусы
и результаты — [PAI progress](verification/PAI-progress.md); формальные
planned/review_required записи не заменены инженерной таблицей.
