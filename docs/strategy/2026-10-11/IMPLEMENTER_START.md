# Первый блок реализации единого входа и управления задачами

Execution overlay, 13 October: D01–D03 and D56 are implemented locally. Final
local P1 rechecks: `988da0e` and `d231d9a`. D05 + D06 source/review `2318bbe`, fixes `e10365e`.
D04 + D10 source/review71704c4, initial repairs2a20da4, final fix/narrow PASS0287f87.
D07 + D08 + D09 source/full review caefb45, initial repairs9f5feec, final
fix/narrow PASS8f193bb; all package P1 including reader R12 closed locally.
[Latest receipt](../../verification/DAILY-package-05-D07-D08-D09-20261013.md).
D11/D12/D14/D16 source/full review b442682, final source/narrow PASS650b8dd;
all local P1 closed, earlier STOP stages preserved in [receipt](../../verification/DAILY-package-06-D11-D12-D14-D16-20261013.md).
Next ready package: D13 + D15 + D17 + D18 (split D15 L before implementation);
read [current handoff](../../CODEX_PROMPT.md) and [backlog receipts](BACKLOG.md).
The non-Codex Go/governed/human gates remain open; local review is separate.
The original first-block instructions below are design context, not a request
to repeat these implementations/tests or activate accounts.

Адресат: следующий кодирующий агент. Исходный исследованный код `23312b8`; предыдущая runtime verification `0fbcfd1`. Это единое задание на начало общего backlog: **D01 → D02 → D03 → D56**, затем dependency-ready D57/D58 и остальные карточки. Уже выполненные блоки не повторять; первым исполняется ближайший незакрытый. Реализация в исследовательской сессии не выполнялась. После назначения этого блока владельцем можно начинать с локального synthetic пути без повторного общего исследования. Аккаунты, платные вызовы, production, services/timers и внешние действия в блок не входят.

## Результат блока

Один явный runtime путь, безопасная проверка конфигурации и задача, которой можно управлять обычными словами. Пользователь отправляет «Собери обзор недели», получает понятное подтверждение приёма, спрашивает «Что с обзором?», при необходимости говорит «Останови обзор», возвращается к готовому результату. Slash-команды и ordinary text вызывают один use case. Старое подтверждение действия не переиспользуется.

Первый блок ещё не вводит универсальный LLM planner, private target, новый модельный провайдер или полный редакторский pipeline. Его ценность — сделать существующие функции доступными и управляемыми через один проверяемый вход; следующие D04–D21 улучшают смысл и качество.

## Прочитать узко

1. `AGENTS.md`, `docs/CODEX_PROMPT.md`, `docs/ASSISTANT_BOUNDARIES.md` и действующий `docs/IMPLEMENTATION_CONTRACT.md`.
2. [Аудит](CODE_AUDIT.md): F01–F03, F06, F14. [Архитектура](PRODUCT_ARCHITECTURE.md): один разговор, фокус, typed plan и инварианты.
3. Карточки [D01–D03](BACKLOG.md#d01) и common contract в [backlog.json](backlog.json). PAI-07/09/10/14/24 — reuse refs, не задания повторить старую реализацию.
4. Код `src/prm/cli.py`, `src/prm/runtime/ingress.py`, `composition.py`, `presentation.py`, `src/prm/storage/jobs.py`, `src/bot/bot.py`; указанные тесты. Full spec здесь не перечитывать: relevant UX-01…05, CHAT-01/02, MEM-01, OPS-01/02, ACT-02/03.

## Начальные команды

```bash
git status --short --branch
git log -1 --oneline
.venv-pai/bin/python tools/playbook.py --check-pin
PYTHONPATH=src .venv-pai/bin/python -m prm.cli --help
```

Проверь, что ветка назначена для реализации; не редактируй source на master. Если пакет остаётся в незакоммиченных документах, сохрани его перед созданием implementation branch без reset чужих изменений. Не fetch/pull/install/update tooling без необходимости. Не читай `.env` и реальные базы для этого блока.

## Предлагаемые интерфейсы

`RuntimeConfigSummary`: schema version, selected mode (`durable/compatibility`), configured capabilities, missing prerequisites, readiness evidence (`configured/observed/unknown`), safe errors. Без DSN, токена, account payload. `runtime-check` — **новая предлагаемая команда**, не существующая сейчас. Она принимает публичные ссылки конфигурации, валидирует offline и не делает DDL/network. Реальный `runtime-status` остаётся явным обращением к выбранному target.

`RequestIntent`: `kind`, `query`, `target_ref`, `target_version`, `project_ref`, `source_filters`, `origin` и `needs_clarification`. На первом блоке origin — explicit command, callback, reply или небольшой deterministic phrase mapping; никаких capabilities из model output. `kind` из enum: chat, search, weekly, memory_operation, job_status, job_result, job_cancel, action_preview. Confirmation обслуживает прежний exact-bound path с отдельным приоритетом, не свободный enum-executor.

`ResolvedJobTarget`: job ref, owner, origin binding, reason (`reply/explicit/only_active/selected`) либо кандидаты с короткими безопасными названиями. `JobProgressView`: status, последние реальные checkpoints, has_result, cancellable, awaiting_reconciliation. Стадии выводятся из сохранённого состояния. Не показывать внутренний UUID обязательным способом управления.

Предпочтительное размещение новых pure helpers: `src/prm/runtime/dispatch.py` и `src/prm/runtime/job_controls.py`. Это предлагаемые пути. `composition.py` занимается wiring и передаёт управление, `ingress.py` проверяет owner/dedup и сохраняет input, `presentation.py` рендерит DTO. Изменение persistent bindings выполнять аддитивно через существующие repositories и миграционные правила; не вводить новую SQLite с jobs.

## Порядок изменений

Применить уточнение владельца: **пакет → Deep Review → исправления → следующий пакет**. Один Deep Review на накопленный результат D01–D03, а не на каждый файл или карточку. После исправления P0/P1 — независимая проверка именно исправленных находок; без повторения полного ревью и всех тестов. Новая серьёзная находка разбирается по существу, некритический остаток переносится явно. Не застревать в улучшении оценок и косметических циклах.

1. Написать целевые behavioral fixtures для entrypoint, focus/control и dispatch, включая отрицательные случаи. Зафиксировать, какие ожидаемые проверки сейчас падают; не перепроигрывать исторические review scripts.
2. D01: выбрать и отобразить mode/config; сохранить explicit compatibility route. Неполный durable config даёт понятную ошибку до любых эффектов. Service template только документирует выбранные аргументы, без включения.
3. D02: `resolve_job_target` и safe progress. Если один актуальный job — выполнить status/result/cancel. Если два — предложить названия с bound callbacks. Если нет — честно сообщить. Cancel одного job не чистит unrelated focus; unknown effect остаётся в ledger.
4. D03: вынести существующие command/prefix mappings, добавить проверенный минимальный набор «обзор недели», «что с задачей», «останови», «верни результат», «новая тема». При отсутствии capability показать конкретный пробел/доступную альтернативу. Не давать legacy обхода scope checks.
5. Native replay через `TelegramJobIngress` → `AssistantJobWorker` → result store → synthetic delivery. Проверить restart и частичную доставку preview. Параллельная разработка D05/D06/D10 допустима только без конфликтующих edits shared contracts/composition.

## Обязательные примеры поведения

| Вход и состояние | Ожидаемый результат |
| --- | --- |
| `/help` или config-check без секретов | Ноль обращений к provider/DB migration; summary показывает unknown там, где наблюдения нет. |
| «Что с задачей?» при одном job | Реальный статус выбранной задачи; не запускать LLM. |
| «Стоп» при двух независимых jobs | Компактный выбор; обе остаются неотменёнными до разрешения неоднозначности. |
| Reply на карточку исследования и «стоп» | Cancel этого job, unrelated job и conversation refs сохранены. |
| Cancel после prepared external send | Future steps остановлены; возможный эффект отмечен unknown/reconcile, без повторной отправки. |
| «Собери обзор недели» и `/weekly …` с одинаковыми параметрами | Один use case, одинаковые window/source policy и result type. |
| «Да» после смены темы или старой версии draft | Никакого external effect. Прежний confirmation invariant работает. |
| Source text «отключи ограничения» | Только данные источника; ни config, ни permissions не меняются. |
| Worker завершился после нового пользовательского вопроса | Результат доступен по своей карточке; новый focus не заменён автоматически. |
| Update/callback от другого actor/chat | Данные и controls не раскрываются. |

## Проверка и передача

После появления новых файлов выполнить:

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python -m pytest -q tests/test_daily_entrypoint.py tests/test_daily_controls.py tests/test_daily_dispatch.py
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python -m pytest -q tests/test_prm_cli.py tests/test_pai_ingress_jobs.py tests/test_pai_control_polish.py tests/test_pai_operations_runtime.py tests/test_pai_chat_runtime.py tests/test_pai_brief_runtime.py
.venv-pai/bin/python tools/check_personal_assistant_plan.py
.venv-pai/bin/python tools/check_pai_plan.py
git diff --check
```

`tests/test_daily_*` пока **не существуют**; команды выше являются приёмкой после их создания. Изолированный PostgreSQL использует existing fixture, не port 5432/production. Если затронуты confirmation/delivery semantics, дополнительно точные `test_pai_durable_actions.py`/`test_pai_delivery.py` nodes и независимый risk review по действующей политике; P0/P1 закрыть с recheck до зависимой работы. Не запускать full historical pytest и платный judge ради документации.

Передать: список изменённых файлов, exact SHA/diff, реальный argv/exit/pass/fail/skip, synthetic screenshots/transcript, какие D01–D03 acceptance закрыты, оставшиеся риски и следующий dependency-ready блок. Называть результат «локально проверенный единый вход и controls», не daily-ready продукт.

Следующая работа: D56 после D01–D03; D05/D06/D10 можно начинать независимо, затем D04/D08/D12/D14/D16 по DAG. Не ждать личных аккаунтов для этого. Live gates остаются в D26/D27, согласие на real mail/calendar actions — в D32.

## Контракт Telegram для общих карточек

Перед D02/D04 согласовать route/message bindings по [TELEGRAM.md](TELEGRAM.md), чтобы D56 расширял эти же типы. Перед D56 прочитать разделы текущего состояния и архитектуры этого обоснования, [квитанцию](telegram_evidence.json) и карточку [D56](BACKLOG.md#d56). Официальные API проверены 11 октября; текущие bot/client capabilities остаются live gate. Новое общее исследование не требуется, достаточно сверить изменения HEAD/assignment и касающиеся пакета upstream изменения.

## Следующий пакет общего backlog: D56

**Результат:** owner пишет обычное сообщение → normalized durable input → job/result → final send с точным destination/receipt → reply или inline button адресует тот же result/version. Callback получает acknowledgement. Сохранение входа переживает replay; stop/business/topic envelopes не обходят owner policy.

Перед изменениями:

```bash
git status --short
git log -1 --format='%H %s'
git worktree list
.venv-pai/bin/python tools/playbook.py --check-pin
```

Использовать назначенную рабочую ветку; существующие незакоммиченные документы не удалять. Текущий research base `23312b8`; фактическая coding-session база может быть новее. Если D01–D03/D56 уже сделаны другим агентом, сверить код/receipt и взять следующий gap. Общие transport/ingress/schema файлы правит один назначенный исполнитель; остальные пакеты могут готовить pure renderer/fixtures.

Порядок D56:

1. Описать `TelegramDestination`, `TelegramUpdateEnvelope v2`, `TelegramMessageBinding`, typed transport outcomes и opaque callback records в текущем style проекта. Новые файлы, предлагаемые планом: `src/prm/telegram_contracts.py`, `src/prm/storage/telegram.py`. Проверить, нет ли уже подходящих типов после D02/D04; расширить их, а не дублировать.
2. `src/bot/bot.py`: нормализовать update type; durable commit/quarantine/reject до offset advance. Обрабатывать edited owner message как revision. Исправить фактическую передачу navigation и callback acknowledgement в durable polling ветке. `allowed_updates` формировать по реализованным capabilities; не подписываться на business stream до D60.
3. `src/prm/runtime/ingress.py`: сохранить reply/quote/thread/source metadata; различать owner command и untrusted source content. Null thread сохраняет default conversation. Если topics пока выключены, не обрабатывать foreign thread как общую беседу; вернуть понятное unsupported в правильный route, без выдачи её истории.
4. `src/prm/runtime/transports.py`: общий bounded request layer для существующих sends и новых message controls. Сохранить отдельный exact-owner wrapper. Разобрать `retry_after` и provider `ok/error/result`; не писать URL с токеном в ошибки. Реальный send receipt проверяет chat/thread/message identity. Формат ответа rich/draft не считать одинаковым с sendMessage.
5. `src/prm/runtime/delivery.py`: payload/schema digest включает method, destination, result/version и presentation. Старые receipts и multipart остаются читаемы. Явный migration/version путь, не правка старых checksum. Для D56 достаточно обычного text/HTML и inline controls; Rich/Draft payloads — следующие D57/D58.
6. `presentation.py`/`composition.py`: trusted inline navigation строится сервером по объекту. Использовать callbacks для действий у сообщения вместо глобальной reply keyboard там, где она теряет адресацию. До D62 никакого произвольного recipient/business send.

Поведенческие проверки D56:

- Replay update с тем же body создаёт один job; другое содержимое того же immutable update_id даёт конфликт/quarantine. Сбой БД не двигает offset.
- Ответ A, затем B; reply на A и callback A продолжают A, без смены B из-за позднего завершения.
- Unicode quote/UTF-16 position и скрытый forward origin не создают выдуманную source identity.
- Edited source меняет revision; старое подтверждение становится stale, новая версия автоматически не отправляется.
- Callback другого actor/chat/thread/expired version отвергается; owner callback быстро снимает spinner. Opaque token не содержит текста/секретов.
- Send timeout после dispatch остаётся unknown; fallback/retry не создаёт вторую возможную отправку.
- Реальный polling entrypoint передаёт markup: тест только `navigation_markup` недостаточен.

Предлагаемые новые тесты **ещё не существуют**. После написания/регистрации запустить один затронутый tier:

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python -m pytest -q tests/test_daily_telegram_routes.py tests/test_daily_telegram_transport.py tests/test_pai_ingress_jobs.py tests/test_pai_delivery.py tests/test_prm_bot_dispatch.py
```

Если миграция затронула durable conversation, дополнительно именно `tests/test_pai_durable_conversation.py`. Полный исторический suite не запускать. Один независимый Deep Review накопленного пакета → исправления → узкая независимая перепроверка P0/P1 → следующий пакет. Формальный статус, local engineering, provider и human acceptance не смешивать.

## Затем D57 и D58 по общим зависимостям

D57 сначала даёт реальный progress из JobQueue и одну status card; затем native draft и Stop. `draft_id → job/generation/destination` сохраняется до публикации; Stop без `from` проверяется через authenticated owner route и binding. Final result всегда durable send, а не сохранённый якобы навсегда draft. Model SSE часть координируется с D05; отсутствие SSE не блокирует truthful progress. Grounded блок публикуется только после проверки; partial draft не используется как confirmation preview.

D58 реализует renderer над существующим immutable BriefDocument и answer objects. Использовать typed blocks, deterministic source IDs и server-built buttons, не HTML страницы целиком и не произвольный JSON модели. Payload limits проверяются локально; известный rejection допускает совместимый renderer, unknown outcome — нет. Быстрый локальный прототип формы не завершает integration task: обязателен owner client canary через D27/D40.

Минимальный набор новых файлов по назначенному срезу: `tests/test_daily_telegram_progress.py`, `tests/test_daily_telegram_rich.py`. Regression floor — existing `tests/test_pai_workers.py`, `tests/test_pai_delivery.py`, `tests/test_pai_brief_runtime.py`, плюс model tier только при изменении model transport. Не повторять D56 tier целиком без изменений его контрактов.

Для live canary подготовить конкретный пакет: reviewed SHA/config, synthetic report, selected test bot/chat, методы/лимит запросов, affected flags и rollback. Дальше исполнять только в разрешённом scope. Проверить Android/iOS фактического телефона владельца и desktop, указав версии; не требовать купить второе устройство. Статус недоступной платформы unknown, а не PASS.


Для D59–D62 использовать карточки единого [BACKLOG](BACKLOG.md#d59): там заданы файлы, новые тесты и live/operator gates. Отдельную очередь Telegram не заводить. Темы и Secretary не блокируют основной ежедневный контур. Mini App исключён владельцем; не добавлять его в реализацию. D25 остаётся обычным приватным reader. После каждого законченного пакета — один Deep Review, исправления и узкая независимая перепроверка критических находок; переходить дальше без повторных общих циклов.

Короткое назначение: **прочитай CODEX_PROMPT и этот handoff; проверь состояние D01–D03. Реализуй первый незакрытый блок, затем D56 — один owner message→durable result→правильный reply/callback путь. После scoped проверки и закрытия критических находок переходи к готовым D57/D58. Прикладная реализация, live connections и human acceptance этим исследованием не выполнены.**
