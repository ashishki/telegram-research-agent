# Приоритизированный пул исполнения

62 карточки поверх существующей реализации, включая Nebula и новые возможности Telegram. Это единый backlog: отдельных очередей Telegram/Nebula нет. Источник карточек — [backlog.json](backlog.json). Исследование 11 октября не реализовывало эти задачи; назначение 13 октября разрешает последовательную локальную реализацию. D01–D03 реализованы локально на `08fb32e`, независимый review pending. Остальные карточки proposed; формальная приёмка отдельно. P0 — ближайшие препятствия полезному ежедневному контуру; P1 — развитие и качество выбранных способностей; P2 — последующие/условные улучшения, включая отложенный Canvas. Приоритет не равен обязательности: темы/Secretary имеют явные условия выбора; Mini App исключён владельцем; P2 не вычёркивает обязательные требования полного замысла.

## Исполнение 13 октября 2026

| Пакет | Код и локальные проверки | Deep Review | Следующий блок |
| --- | --- | --- | --- |
| D01–D03 | `08fb32e`; 32 новых acceptance + 6 safety holdouts = 38 passed; отдельный regression floor 52 passed | pending; reviewed SHA отсутствует; нужен scoped Go-review либо явно выбранная локальная замена | D56 после review gate |

[Квитанция пакета](../../verification/DAILY-package-01-20261013.md) сохраняет точные argv, результаты и первоначальные ошибки. Реальные подключения и пользовательская польза этим не доказаны. Working branch: `codex/pa-daily-implementation-20261013`.

Типы: **K** код, **C** настройка, **L** реальное подключение, **H** решение/оценка владельца, **R** исследование/измерение. Размер S — один небольшой срез; M — 2–3 среза; L — разбить до начала. Это относительная сложность, не обещанные сроки.

Зависимости AND обязательны совместно. Варианты OR позволяют выбрать фактического провайдера: Microsoft или Google; не нужно подключать оба. При смешанном выборе mail/calendar закрыть соответствующие части обоих adapter contracts. Нельзя трактовать отсутствие доступа как завершение карточки.

Первый блок: **D01 → D02 → D03**, затем **D56**, точное задание — [IMPLEMENTER_START](IMPLEMENTER_START.md). Уже закрытое по evidence не повторять. D05/D06/D10/D22 и подготовка D48 могут идти независимо с согласованными границами файлов; D57/D58 выполняются после своих общих зависимостей. Этапы/пакеты — в [едином плане](README.md#последовательность-и-критерии-перехода); исследование Telegram — [обоснование карточек](TELEGRAM.md), не отдельный roadmap. После core/read canary начинаются реальная проверка и длительный пилот; дальнейшие способности продолжаются.

## Общая приёмка

Следующий кодирующий агент работает законченными пакетами: реализация → адресные проверки → один независимый Deep Review накопленного diff → исправления → следующий пакет. У каждого пакета один native ingress→use case→result результат. P0/P1 исправлены и независимо перепроверены узко до зависимой работы; повторное полное ревью/все тесты без нового существенного риска не запускаются. Некритические остатки фиксируются; 62 карточки не означают 62 полных ревью. Изменения egress/secrets/retention/confirmation/recovery получают требуемое риск-ревью до реального использования.

Record exact SHA/diff, commands, pass/fail/skip, requested/observed model, public fixture hashes and unresolved live/operator gates. A test filename is not a pass. No private payloads in Git.

Отключить новую способность или вернуть предыдущий совместимый код; не откатывать consumed/unknown receipts, revoke/tombstones и canonical source IDs. Для schema changes нужен отдельный forward-compatible recovery.

Существующие test paths перечислены как regression floor. Для D01–D03 tests/test_daily_entrypoint.py, test_daily_controls.py и test_daily_dispatch.py созданы и зарегистрированы; прочие предложенные daily-тесты создаются в своих пакетах. Только затронутый tier; полный исторический pytest запрещён.

PAI references mean reuse/coverage, never automatic completion or human approval. Do not modify formal statuses based solely on this plan.

## Очередь

| ID | Приоритет и этап | Тип | Размер | Работа | Зависимости |
| --- | --- | --- | --- | --- | --- |
| [D01](#d01) | P0 G0 | K/C | M | Однозначный runtime и безопасная проверка готовности | нет |
| [D02](#d02) | P0 G0 | K | M | Статус отмена и возврат к задаче без ID | D01 |
| [D03](#d03) | P0 G0 | K | M | Один типизированный диспетчер существующих способностей | D01, D02 |
| [D04](#d04) | P0 G1 | K | L | Понимание задачи и устойчивый фокус беседы | D03, D05, D06 |
| [D05](#d05) | P0 G1 | K/R | M | Совместимые и наблюдаемые модельные адаптеры | нет |
| [D06](#d06) | P0 G0 | K/R | M | Эталонные задачи и единый trace | нет |
| [D07](#d07) | P0 G1 | K/C/H | M | Профили качества бюджеты и политика провайдеров | D05, D06 |
| [D08](#d08) | P0 G1 | K/H | M | Актуальные проекты и проверяемая применимость | D03, D06 |
| [D09](#d09) | P0 G1 | K/C/L | M | Выбранный Telegram архив и его свежесть | D10 |
| [D10](#d10) | P0 G1 | K | M | Единый контракт источников и полноты | D06 |
| [D11](#d11) | P1 G1 | K/R | M | Измеримый поиск RU EN и объединение retrieval путей | D06, D10 |
| [D12](#d12) | P0 G1 | K/L | M | Естественный веб поиск и проверка свежести | D04, D10 |
| [D13](#d13) | P1 G1 | K/C/L | M | Контекст выбранного GitHub проекта | D08, D10 |
| [D14](#d14) | P0 G1 | K/R | M | Синтез с отдельными фактами выводами и советами | D05, D06, D10 |
| [D15](#d15) | P1 G1 | K | L | Составное исследование с разумным завершением | D04, D07, D12, D14 |
| [D16](#d16) | P0 G1 | K | M | Полная выборка недели до лимита модели | D10 |
| [D17](#d17) | P1 G1 | K/R | M | События новизна и противоречия | D10, D16 |
| [D18](#d18) | P0 G1 | K/H | M | Обзор который помогает выбрать следующий шаг | D08, D14, D16 |
| [D19](#d19) | P0 G1 | K | M | Обсуждение документов и версий в беседе | D04, D18 |
| [D20](#d20) | P1 G1 | K/H | M | Полезная обратная связь без работы по разметке | D08, D18 |
| [D21](#d21) | P0 G1 | K/H | M | Память которая помогает следующему вопросу | D04, D08, D10 |
| [D22](#d22) | P0 G2 | K/C | L | Настоящий private storage target | D01 |
| [D23](#d23) | P0 G2 | K/C/H | M | Retention backup и восстановление private среды | D22 |
| [D24](#d24) | P0 G2 | K/C | M | Один профиль запуска и наблюдаемое состояние | D01, D02, D22 |
| [D25](#d25) | P1 G2 | K/C/L/H | M | Приватный reader удобный на телефоне | D19, D22, D23 |
| [D26](#d26) | P0 G2 | K/C/H | M | Короткая настройка источников и полномочий | D07, D08, D23, D24 |
| [D27](#d27) | P0 G2 | L/C/H | M | Ограниченный canary реального чтения и запуска | D09, D12, D23, D24, D26 |
| [D28](#d28) | P1 G3 | K | M | Локальные черновики из обычного разговора | D04, D14, D21 |
| [D29](#d29) | P1 G3 | K/C/L/H | M | Выбранная почта Microsoft с полным lifecycle | D10, D22, D26 |
| [D30](#d30) | P1 G3 | K/C/L/H | M | Календарь и адресаты в повседневном контексте | D10, D22, D26 |
| [D31](#d31) | P1 G3 | K/C/L/H | L | Google адаптеры если выбраны владельцем | D10, D22, D26 |
| [D32](#d32) | P1 G3 | K/L/H | M | Настоящие подтверждённые письма и события | D23, D28; OR D29+D30 / D31 |
| [D33](#d33) | P1 G3 | K/L/H | M | Наблюдения которые редко отвлекают | D02, D10, D17, D24, D26 |
| [D34](#d34) | P1 G3 | K/L/H | M | Документы голос и изображения в общей беседе | D04, D05, D21, D23 |
| [D35](#d35) | P0 G1 | K/R | M | Судья с доказательствами и полными диалогами | D06 |
| [D36](#d36) | P1 G1 | K/R/H | M | Калибровка судьи и контроль смещения | D35, D05 |
| [D37](#d37) | P1 G1 | K/R/L/H | M | Сравнение моделей и фактической стоимости | D05, D06, D07, D36 |
| [D38](#d38) | P0 G2 | L/H/R | M | Четырнадцать дней ежедневного использования | D18, D19, D21, D27, D40 |
| [D39](#d39) | P1 G3 | L/H/R | M | Четыре полезных недельных обзора | D17, D18, D19, D20, D27, D40 |
| [D40](#d40) | P0 G2 | K/H/L | M | Приёмка интерфейса на реальном телефоне | D02, D19, D27, D56, D57, D58 |
| [D41](#d41) | P2 G3 | K/L/H | M | Canvas и персональный академический модуль после снятия отсрочки | D10, D26 |
| [D42](#d42) | P1 G3 | K/L/H | M | Сквозной отзыв экспорт и удаление | D21, D23, D34; OR D29+D30 / D31 |
| [D43](#d43) | P1 G3 | K/L/R | M | Устойчивость в условиях реального хоста | D24, D27 |
| [D44](#d44) | P1 G4 | R/H/L | M | Приёмка полного ассистента по требованиям | D25, D32, D33, D34, D39, D41, D42, D43, D37, D38, D47, D54 |
| [D45](#d45) | P2 G4 | K | L | Разделение больших модулей по действительным обязанностям | D03, D06 |
| [D46](#d46) | P2 G4 | K/R/H | M | Learned retrieval только при измеренном выигрыше | D11, D23 |
| [D47](#d47) | P1 G4 | K/C | M | Понятные конфигурация промпты и зависимости | D05, D07 |
| [D48](#d48) | P1 G4 | C/H/R | M | Короткая актуальная методика с проверками по риску | нет |
| [D49](#d49) | P2 G4 | R/K/H | L | Масштабирование только по эксплуатационному пределу | D11, D23, D43 |
| [D50](#d50) | P2 G4 | K/C/H | M | Поддержка качества без постоянного присмотра | D36, D38, D43, D47 |
| [D51](#d51) | P1 G1 | K/C | L | Nebula: полноценное подключение и надёжное обновление данных | D10 |
| [D52](#d52) | P1 G1 | K/C | L | Nebula в общем диалоге и Academic Inbox без Canvas | D03, D10, D26, D51, D04, D08, D21 |
| [D53](#d53) | P1 G3 | K/C/H | L | Nebula в Brief и Watch с отбором и первоисточниками | D52, D17, D18, D20, D33 |
| [D54](#d54) | P1 G2 | C/L/H/R | M | Nebula: реальный запуск и приёмка ежедневной работы | D52, D53, D27 |
| [D55](#d55) | P2 G3 | R/K/C/L | M | Условно: довести пробел данных через готовый компонент или официальный источник | D51 |
| [D56](#d56) | P0 G1 | K/C | M | Telegram: точная адресация результатов и работающие controls | D03 |
| [D57](#d57) | P1 G1 | K/C/R | L | Telegram: честный прогресс, потоковый preview и остановка | D56, D02, D24, D05 |
| [D58](#d58) | P1 G1 | K/C | M | Telegram: полноценные интерактивные отчёты из общего документа | D56, D19 |
| [D59](#d59) | P2 G2 | R/K/C/L/H | L | Условно: темы для параллельных личных исследований | D56, D04, D57, D27 |
| [D60](#d60) | P1 G3 | R/K/C/L/H | L | Secretary: управляемое чтение выбранных переписок | D56, D26, D23, D10 |
| [D61](#d61) | P1 G3 | K/H/L | L | Secretary: обязательства, важные входящие и локальные ответы | D60, D21, D28, D33 |
| [D62](#d62) | P1 G3 | K/L/H | L | Secretary: точный подтверждённый ответ от имени владельца | D61, D28, D23 |

## Карточки

<a id="d01"></a>
### D01 Однозначный runtime и безопасная проверка готовности

**Engineering:** implemented_locally_review_pending, source `08fb32e`, [evidence](../../verification/DAILY-package-01-20261013.md). Formal/live/operator acceptance не заявлена.

P0 · G0 · K/C · размер M. Зависимости: нет.

**Цель.** Исполнитель и владелец понимают, какой путь реально будет запущен и чего ему не хватает.

**Изменение.** Добавить явный профиль durable запуска и offline config-check/doctor с версиями schema, capabilities и missing prerequisites. Без complete runtime config не молча переходить на другой продуктовый путь. Прежний путь доступен явно как compatibility. В preflight разделить offline validation и отдельно разрешаемые сетевые probes; запуск и миграция не выполняются.

**Компоненты.** `src/prm/cli.py`; `src/prm/runtime/composition.py`; `src/prm/runtime/setup.py`; `systemd/telegram-prm-assistant.service`; `docs/runbooks/assistant_runtime.md`.

**Проверка.** tests/test_prm_cli.py и tests/test_pai_operations_runtime.py; новые tests/test_daily_entrypoint.py: пустая/частичная/неверная config, неизвестное поле, выбранный legacy, coherent durable profile. Spy доказывает zero network/DDL/service start на help/check. Секреты не выводятся, process state не объявляется observed из config.

**Доступы и переход.** Личный target не требуется; synthetic config достаточно. Публикация service template не включает сервис.

**Переиспользование.** PAI-07, PAI-24, PAI-28.

<a id="d02"></a>
### D02 Статус отмена и возврат к задаче без ID

**Engineering:** implemented_locally_review_pending, source `08fb32e`, [evidence](../../verification/DAILY-package-01-20261013.md). D56 завершит outbound receipts, callback ack и route envelopes.

P0 · G0 · K · размер M. Зависимости: D01.

**Цель.** Длительная работа не заставляет владельца администрировать очередь.

**Изменение.** Разрешать status/result/cancel по reply/callback и одному активному job; при нескольких показывать короткие названия. Natural стоп относится к выбранной задаче, stop all явно отделён. Сохранять актуальную привязку Telegram message→job/result. Показать checkpoints, partial и unknown без модельной выдумки, не сбрасывать unrelated conversation при отмене одного job. Общий TelegramMessageBinding и route contract из TELEGRAM.md использовать уже здесь; D56 доводит их транспортную реализацию, D57 — native drafts/Stop. Не создавать второй resolver отмены. Job control не требует Rich Messages или включённых тем.

**Компоненты.** `src/prm/runtime/ingress.py`; `src/prm/runtime/presentation.py`; `src/prm/storage/jobs.py`; `src/bot/bot.py`.

**Проверка.** tests/test_pai_ingress_jobs.py, tests/test_pai_control_polish.py; tests/test_daily_controls.py: zero/one/two jobs, restart, late callback, другой actor, завершение одновременно с cancel, model outage. Cancel не стирает prepared/unknown effect и не отменяет другую задачу.

**Доступы и переход.** Первый блок работает через synthetic Telegram updates; настоящий bot позднее D27.

**Переиспользование.** PAI-06, PAI-07, PAI-09.

<a id="d03"></a>
### D03 Один типизированный диспетчер существующих способностей

**Engineering:** implemented_locally_review_pending, source `08fb32e`, [evidence](../../verification/DAILY-package-01-20261013.md). Это ограниченный deterministic mapping; универсальный planner и устойчивый фокус остаются D04.

P0 · G0 · K · размер M. Зависимости: D01, D02.

**Цель.** Команды и понятные обычные фразы вызывают те же use cases.

**Изменение.** Ввести RequestIntent/dispatch contract для chat, search, weekly, memory, status/cancel и preview. Перенести текущие command/prefix mappings в один adapter; добавить небольшой явно проверенный набор естественных формулировок. Никаких новых модельных tool loops в первом блоке. Неизвестное намерение передаётся существующему Chat; это ещё не универсальное понимание речи.

**Компоненты.** `src/prm/runtime/composition.py`; `src/prm/runtime/ingress.py`; `src/prm/routing.py`; `src/prm/contracts.py`; `src/prm/runtime/presentation.py`.

**Проверка.** tests/test_pai_chat_runtime.py, tests/test_pai_brief_runtime.py, tests/test_pai_control_polish.py; tests/test_daily_dispatch.py: slash/natural equivalence, новая тема, без capabilities, ambiguous yes, injected source instructions. Один и тот же handler и result schema, никакой второй grant registry.

**Доступы и переход.** Граница первого исполнения. Полное LLM понимание D04 отдельно; не рекламировать fixed phrase coverage как всеобщую поддержку.

**Переиспользование.** PAI-07, PAI-10, PAI-14.

<a id="d04"></a>
### D04 Понимание задачи и устойчивый фокус беседы

P0 · G1 · K · размер L. Зависимости: D03, D05, D06.

**Цель.** Ассистент выбирает инструменты и продолжает правильный объект без знания пользователем режимов.

**Изменение.** Добавить bounded schema-bound intent planner над RequestIntent, ConversationFocus с thread/project/object/version и source filters. Модель предлагает только доступные read/compose/preview steps; code валидирует plan. Приоритет reply→явная ссылка→active focus→однозначный recent. Новая тема создаёт новый фокус; старые документы доступны через lookup. Ввести reason для необходимого уточнения и stop conditions. Reply/quote/forward нормализуются D56; ConversationFocus сохраняет optional thread без автоматического смешения историй. Полная миграция ключей и параллельность по conversation — D59. Полученное из переписки содержание не становится owner instruction.

**Компоненты.** `src/prm/runtime/composition.py`; `src/prm/conversation.py`; `src/prm/storage/conversations.py`; `src/prm/contracts.py`; `src/prm/routing.py`.

**Проверка.** tests/test_pai_durable_conversation.py, tests/test_pai_product_sessions.py; tests/test_daily_conversation.py: 10–20 turns, вмешавшийся background result, второй пункт, исправление проекта, возврат после restart, no model, ambiguity, malformed plan, injection. Planner не подтверждает actions и не выдаёт новые permissions.

**Доступы и переход.** Synthetic fake planner сначала; real model evidence через D37. История личной беседы только после retention решения.

**Переиспользование.** PAI-05, PAI-10, PAI-13.

<a id="d05"></a>
### D05 Совместимые и наблюдаемые модельные адаптеры

P0 · G1 · K/R · размер M. Зависимости: нет.

**Цель.** Выбранная модель работает через тот же product runtime, что и synthetic тесты.

**Изменение.** Выделить transport protocol и capability descriptor. Начать с нужного Chat Completions адаптера для Flash и GPT-4o, нормализовать token parameters/usage/stop reason и явное alias mapping. Responses/Messages добавлять при выборе кандидата. Сохранять exact endpoint/credential binding, deny redirect, schema bounds и unknown accounting. Для Go проверить допустимость нагрузки и корректный собственный client/session, не маскировку. Для эксперимента D57 добавить SSE/event stream как capability выбранного адаптера с cancel/usage/partial handling; не объявлять streaming доступным всем моделям по одному совместимому endpoint. Progress worker не зависит от model SSE.

**Компоненты.** `src/prm/runtime/model.py`; `src/prm/runtime/model_errors.py`; `src/prm/runtime/model_attempts.py`; `src/prm/runtime/speech.py`; `src/prm/runtime/vision.py`.

**Проверка.** tests/test_pai_chat_runtime.py, tests/test_pai_cost_cache.py; tests/test_daily_model_protocols.py с HTTP doubles: alias/snapshot, unsupported parameter, truncated response, 403, 429, timeout after request, output too large, usage mismatch, header redaction. Canary только после выбранного provider/data scope.

**Доступы и переход.** Никаких вызовов модели в этой планировочной сессии; unit tests без credentials. Provider compatibility не даёт privacy approval.

**Переиспользование.** PAI-10, PAI-23.

<a id="d06"></a>
### D06 Эталонные задачи и единый trace

P0 · G0 · K/R · размер M. Зависимости: нет.

**Цель.** Каждое изменение сравнивается по поведению и результату, а не числу модулей.

**Изменение.** Создать первые 20 synthetic end-to-end задач и расширяемый manifest до 120 единиц MODELS_EVAL. Case хранит source snapshots, expected constraints, intended object binding и must-not-effects. Trace содержит visible turns, typed tool results, versions, errors, costs и latency без secrets. Переиспользовать native capture/test fixtures, сохранить historical datasets отдельно.

**Компоненты.** `tests/pai_runtime_fixtures.py`; `tests/test_pai_product_sessions.py`; `src/prm/runtime/evaluation.py`; `evals/assistant_judge/`; `tools/run_pai_acceptance.py`.

**Проверка.** tests/test_pai_product_sessions.py, tests/test_pai_acceptance_guard.py; tests/test_daily_eval_manifest.py: missing evidence/turn/required case fail, pass cannot come from matching keywords, train/dev/holdout source split, secrets scan на synthetic canaries. Recording не считается provider execution.

**Доступы и переход.** Эталон личной полезности дополняет владелец в D38; независимая часть готовится сейчас без его данных.

**Переиспользование.** PAI-26.

<a id="d07"></a>
### D07 Профили качества бюджеты и политика провайдеров

P0 · G1 · K/C/H · размер M. Зависимости: D05, D06.

**Цель.** Стоимость и передача личных данных управляются независимо от названия модели.

**Изменение.** Versioned role profiles chat/planner/research/brief_editorial/extraction/judge/media; tariffs и allowed data classes с checked_at/expiry. Подключить реальные paired receipts к economical promotion. Budget показывает subscription, meter, overage и unknown отдельно. Кэш ключуется scope/version; fallback только в заранее разрешённый набор, с cooldown и bounded attempts.

**Компоненты.** `src/prm/runtime/profiles.py`; `src/prm/runtime/cost_cache.py`; `src/prm/runtime/composition.py`; `src/prm/model_cost.py`; `src/prm/storage/policy.py`.

**Проверка.** tests/test_pai_cost_cache.py, tests/test_pai_durable_policy.py; tests/test_daily_profiles.py: role selection, expired privacy policy, отсутствующий receipt, unknown tariff/usage, revoked grant invalidates cache, peak/offpeak и валютные единицы. Missing provider не вызывает молчаливый приватный fallback.

**Доступы и переход.** Бюджет/egress выбирает владелец перед live. Изменение governed reviewer model не входит в product profile.

**Переиспользование.** PAI-03, PAI-23.

<a id="d08"></a>
### D08 Актуальные проекты и проверяемая применимость

P0 · G1 · K/H · размер M. Зависимости: D03, D06.

**Цель.** Находки связываются с реальными целями, а не с совпадением названия проекта.

**Изменение.** Переиспользовать project_portfolio_context: confirmed goal/blocker/next_proof/status/aliases. Добавить durable versioned ProjectContext, source refs и reviewed_at; 1–3 проекта для первого пилота. Карточка применимости содержит evidence связи, минимальный эксперимент и критерий отказа. Паузу/смену цели учитывать при очередной рекомендации.

**Компоненты.** `src/assistant/project_portfolio_context.py`; `src/assistant/project_context.py`; `src/prm/runtime/memory.py`; `src/prm/storage/conversations.py`.

**Проверка.** tests/test_project_portfolio_context.py, tests/test_project_context.py; tests/test_daily_projects.py: wrong alias, paused project, stale ref, goal change, unknown owner confirmation. Keyword match без связи не даёт уверенного action recommendation.

**Доступы и переход.** Synthetic проекты сначала; реальные цели выбираются без публикации в Git. Существующие profiles не массово перезаписывать.

**Переиспользование.** PAI-05, PAI-13, PAI-21.

<a id="d09"></a>
### D09 Выбранный Telegram архив и его свежесть

P0 · G1 · K/C/L · размер M. Зависимости: D10.

**Цель.** Пользователь понимает, какие каналы и периоды действительно прочитаны.

**Изменение.** Связать существующий ingestion/reaction sync с selected source registry: source allowlist, cursor, watermark, edit/delete, lag и quota. Сохранить canonical raw_posts/posts IDs и возможность поиска без enrichment. Предложить импорт/forward как ограниченный путь при отсутствии Telegram session; Bot API не выдавать за доступ ко всей истории.

**Компоненты.** `src/ingestion/`; `src/ingestion/reaction_sync.py`; `src/db/archive_search.py`; `src/prm/runtime/archive.py`; `src/prm/runtime/research.py`.

**Проверка.** tests/test_reaction_sync.py, tests/test_archive_search.py, tests/test_pai_archive_search.py; tests/test_daily_source_freshness.py: edits/deletes, duplicate ingest, cursor interruption, outage, reacted post without enrichment, old source watermark. No private DB read в обычном CI.

**Доступы и переход.** Реальный collector/session и разрешённые каналы только D27; не запускать старые report timers.

**Переиспользование.** PAI-11, PAI-27.

<a id="d10"></a>
### D10 Единый контракт источников и полноты

P0 · G1 · K · размер M. Зависимости: D06.

**Цель.** Ограниченная выборка не выглядит проверкой всех материалов.

**Изменение.** Ввести SourceBatch и EvidenceBundle: selected resources, checked_at, publication/event/discovery time, versions, pagination/continuation, completeness, omitted count if known, reason. Привести archive, web, Brief hooks и позже connectors к contract; лимит model packet отделить от source enumeration. Source IDs/account scopes сохраняются при объединении.

**Компоненты.** `src/prm/contracts.py`; `src/prm/runtime/research.py`; `src/prm/runtime/brief.py`; `src/prm/runtime/graph.py`; `src/prm/public_web.py`.

**Проверка.** tests/test_pai_archive_search.py, tests/test_pai_web_github.py, tests/test_pai_brief_runtime.py; tests/test_daily_coverage.py: >48 items, unavailable/empty/partial pages, date unknown, later source, boundary timestamps и conflict. Счётчики полученного/кандидатов/процитированного различаются.

**Доступы и переход.** Расширение contract аддитивное; старый collector без completeness считается bounded/unknown, не complete.

**Переиспользование.** PAI-11, PAI-12, PAI-14, PAI-17.

<a id="d11"></a>
### D11 Измеримый поиск RU EN и объединение retrieval путей

P1 · G1 · K/R · размер M. Зависимости: D06, D10.

**Цель.** Находить нужные материалы при перефразировании и другом языке запроса.

**Изменение.** Общий retrieval service над canonical FTS с query normalization, bounded expansions и source/project/time filters. Сравнить FTS, текущий hashed-vector fusion и learned candidate отдельно. Не делать curated atoms обязательными. Gold exact lookup, bilingual paraphrase и no-answer размечены до настройки; source diversity и dedup после candidate retrieval.

**Компоненты.** `src/db/archive_search.py`; `src/db/archive_vector.py`; `src/assistant/semantic_retrieval.py`; `src/prm/runtime/research.py`; `evals/retrieval/`.

**Проверка.** tests/test_archive_search.py, tests/test_archive_documents.py; frozen recall@20/nDCG@10/MRR/no-answer false positive по RU/EN и filters. Learned experiment D46 запускается только если есть типы промахов и ресурсная смета. Baseline receipts сохраняются.

**Доступы и переход.** Улучшение не предполагается из имени semantic. FTS позволяет начать пилот, если проходит agreed задачи.

**Переиспользование.** PAI-11, PAI-23, PAI-31.

<a id="d12"></a>
### D12 Естественный веб поиск и проверка свежести

P0 · G1 · K/L · размер M. Зависимости: D04, D10.

**Цель.** Изменчивые вопросы действительно проверяются по источникам без обязательного /web.

**Изменение.** Planner формирует public query и bounded discovery/fetch steps; reuse Brave и safe fetch. Private context не попадает в public query. Distinguish search snippet vs fetched source; exact timestamps/coverage. Для public domains подготовить расширяемую policy с network guard; частные источники строго выбраны. RSS выбранных первоисточников добавить как pull connector, если это уменьшает повторный поиск.

**Компоненты.** `src/prm/runtime/web.py`; `src/prm/public_web.py`; `src/prm/runtime/network_guard.py`; `src/prm/runtime/composition.py`.

**Проверка.** tests/test_pai_web_github.py, tests/test_assistant_web_search.py; tests/test_daily_web_route.py: fresh fact without keyword, no permission, stale snippet, malformed date, redirects/private IP/DNS cases, private text in query. Live Brave canary отдельно с receipt.

**Доступы и переход.** Отсутствие Brave key не останавливает tests и archive path; live search не подменять одним HTTP fetch.

**Переиспользование.** PAI-12, PAI-13, PAI-27.

<a id="d13"></a>
### D13 Контекст выбранного GitHub проекта

P1 · G1 · K/C/L · размер M. Зависимости: D08, D10.

**Цель.** Рекомендации учитывают актуальный код и проектные решения.

**Изменение.** Расширить existing exact-ref public reader: selected files, relevant issues/PR/releases с versions и cache invalidation. Private repositories через выбранный read-only fine-grained token либо GitHub App; prefer App для длительной установки, token допустим для ограниченного canary. Разделить account scope и model egress; exclude secrets/generated files и arbitrary repo execution.

**Компоненты.** `src/prm/runtime/web.py`; `src/assistant/project_context.py`; `src/prm/runtime/connections.py`; `src/prm/runtime/cost_cache.py`.

**Проверка.** tests/test_pai_web_github.py, tests/test_project_context.py; tests/test_daily_github_context.py: branch moved, pinned commit stable, missing path, 404 private access, issue injection, revoke/cached ref. Ответ показывает прочитанный SHA и не утверждает изменение репозитория.

**Доступы и переход.** Public path независим от private credential; repo write остаётся вне product полномочий.

**Переиспользование.** PAI-12, PAI-13, PAI-16.

<a id="d14"></a>
### D14 Синтез с отдельными фактами выводами и советами

P0 · G1 · K/R · размер M. Зависимости: D05, D06, D10.

**Цель.** Ответ помогает разобраться и решить, сохраняя проверяемость.

**Изменение.** Расширить ResearchResult типами fact/inference/recommendation. Facts требуют supporting spans; выводы имеют premises и неопределённость, рекомендации — цель/условия и не маскируются под факт. Измерить false reject нынешнего all-or-none verifier, разрешить partial supported blocks с явным пробелом. Сохранить строгие проверки numbers/entity/negation/URL; не снижать их ради красивого текста.

**Компоненты.** `src/prm/runtime/research_answer.py`; `src/assistant/claim_ledger.py`; `src/prm/synthesis.py`; `src/prm/archive_synthesis_transport.py`; `src/prm/contracts.py`.

**Проверка.** tests/test_claim_ledger.py, tests/test_pai_archive_search.py; tests/test_daily_synthesis.py: faithful paraphrase/translation, swapped actors, false number, contradiction, advice with absent premise, one bad claim among good. Отдельно groundedness precision и required fact recall.

**Доступы и переход.** Изменение verifier требует независимого read-only recheck и нового matched dataset evidence; старые pass не переносятся.

**Переиспользование.** PAI-11, PAI-13, PAI-14.

<a id="d15"></a>
### D15 Составное исследование с разумным завершением

P1 · G1 · K · размер L. Зависимости: D04, D07, D12, D14.

**Цель.** Ассистент сам делает необходимые промежуточные шаги и останавливается при достаточном ответе.

**Изменение.** Связать typed plan с существующим durable research worker: archive/web/selected project, independent parallel reads, gap-based additional wave, stopping by coverage/budget/deadline. Reuse proven deep_research planning logic после согласования contracts. Сохранить промежуточные evidence refs, поддержать продолжение exact result и обновление stale источников. Не расширять source scopes в ходе поиска.

**Компоненты.** `src/prm/runtime/research.py`; `src/prm/deep_research.py`; `src/prm/research_planner.py`; `src/prm/storage/jobs.py`.

**Проверка.** tests/test_pai_deep_research.py и tests/test_pai_load_recovery.py; tests/test_daily_research.py: useful second wave, sufficient first wave, insufficient budget, cancellation/restart между шагами, source conflict, cached expired grants. No blind replay prepared paid call.

**Доступы и переход.** Широкий multiwave live research — отдельное provider evidence; локальная механика проверяется без account.

**Переиспользование.** PAI-06, PAI-13.

<a id="d16"></a>
### D16 Полная выборка недели до лимита модели

P0 · G1 · K · размер M. Зависимости: D10.

**Цель.** Важное раннее событие и небольшой источник не пропадают из-за первых 48 записей.

**Изменение.** Заменить early LIMIT/slice на paginated bounded candidate enumeration и per-source quotas до общей оценки. Global caps отражать в SourceBatch coverage. Разделить all candidates, selected evidence, model packet и omitted material refs. Реализовать calendar-week/rolling window option с timezone. Сохранить возможность открыть не вошедшие материалы без второго raw corpus dump.

**Компоненты.** `src/prm/runtime/research.py`; `src/prm/runtime/brief.py`; `src/prm/briefs.py`; `src/prm/storage/briefs.py`.

**Проверка.** tests/test_pai_brief_runtime.py, tests/test_reporting_period.py; tests/test_daily_brief_selection.py: 200 archive items плюс late mail source, важное событие в начале недели, no content week, DST, removed/late publication, cap exceeded. Числа coverage вытекают из collector, не из LLM.

**Доступы и переход.** First fix protects selection integrity; полная персонализация D18 позже. Новый объём чтения bounded, egress не увеличивается автоматически.

**Переиспользование.** PAI-11, PAI-14.

<a id="d17"></a>
### D17 События новизна и противоречия

P1 · G1 · K/R · размер M. Зависимости: D10, D16.

**Цель.** Обзор показывает изменения, а не многократные пересказы одной новости.

**Изменение.** EventCluster с canonical URLs/content fingerprints и revisions; source independence сохраняется. Учитывать last surfaced/previous Brief, не считать discovered_at временем события. Семантическое объединение только с поддержкой, uncertain candidates остаются раздельными. Изменившийся срок/версия и correction не подавляются dedup.

**Компоненты.** `src/prm/briefs.py`; `src/prm/runtime/brief.py`; `src/prm/storage/briefs.py`; `src/output/editorial_memory.py`.

**Проверка.** tests/test_pai_brief_runtime.py; tests/test_daily_event_clusters.py: ten reposts/one primary, similar but different events, conflicting deadlines, weekly recurrence, title change, new revision. Измерить duplicate rate и gold event recall вместе.

**Доступы и переход.** До завершения semantic clustering допускается deterministic URL/fingerprint baseline с видимыми ограничениями.

**Переиспользование.** PAI-14, PAI-21.

<a id="d18"></a>
### D18 Обзор который помогает выбрать следующий шаг

P0 · G1 · K/H · размер M. Зависимости: D08, D14, D16.

**Цель.** Недельный Brief экономит внимание и связан с текущими проектами.

**Изменение.** Применить отдельные признаки importance/novelty/reliability/project applicability/reading cost; 3–5 событий, максимум несколько выбранных продолжений. Для каждого: что изменилось, почему важно, изучить/эксперимент/пропустить и evidence. Не требовать заполнения рубрик и не генерировать обязанности. D17 подключается как улучшение новизны после baseline.

**Компоненты.** `src/prm/brief_editorial.py`; `src/prm/runtime/brief.py`; `src/prm/briefs.py`; `src/prm/runtime/profiles.py`.

**Проверка.** tests/test_pai_brief_runtime.py, tests/test_pai_brief_polish.py; frozen candidate sets с owner/gold priorities, no-news, weak project linkage, opportunity vs obligation. Required important events retained, no invented importance fact/deadline; real usefulness отдельно D39.

**Доступы и переход.** Synthetic editorial evidence не заменяет оценку владельцем. Сам текст не создаёт задачи и расписания.

**Переиспользование.** PAI-14, PAI-23.

<a id="d19"></a>
### D19 Обсуждение документов и версий в беседе

P0 · G1 · K · размер M. Зависимости: D04, D18.

**Цель.** Обзор становится рабочим объектом, к которому легко вернуться.

**Изменение.** Привязать natural followups к Brief ID/version/story и document focus. Поддержать поясни/почему/применить/сократи/только тема/сравни/обнови/экспорт. Refresh создаёт новую версию с diff; style change сохраняет facts. Возврат из reader/Telegram reply адресует тот же объект; late completion не меняет focus автоматически. Rich Messages D58 — ещё одно представление этого же immutable документа. Object/version/story bindings общие с D56; ссылки и точный confirmation preview не заменять краткой rich карточкой.

**Компоненты.** `src/prm/application.py`; `src/prm/briefs.py`; `src/prm/storage/briefs.py`; `src/prm/runtime/presentation.py`; `src/prm/report_exports.py`.

**Проверка.** tests/test_assistant_report_dialogue.py, tests/test_pai_brief_polish.py; tests/test_daily_document_dialogue.py: две версии, два документа, ambiguous пункт2, revoked source, refresh vs restyle, new fact provenance. Telegram/HTML/PDF/MD содержат одну версию фактов.

**Доступы и переход.** Локальные artifacts достаточны для code gate; hosted mobile reader D25/D40 отдельно.

**Переиспользование.** PAI-05, PAI-14, PAI-15.

<a id="d20"></a>
### D20 Полезная обратная связь без работы по разметке

P1 · G1 · K/H · размер M. Зависимости: D08, D18.

**Цель.** Отбор постепенно учитывает владельца и остаётся объяснимым.

**Изменение.** Соединить существующие reaction/editorial/artifact feedback с versioned FeedbackEvent и new runtime. Полезно/не тема/уже знал/длинно/неверно/применил влияют на конкретный признак. Явное изменение предпочтения показывает область и отмену; passive reaction не меняет durable profile сама. Добавить why shown и необязательный weekly feedback prompt.

**Компоненты.** `src/output/editorial_memory.py`; `src/output/reaction_personalization.py`; `src/db/artifact_feedback.py`; `src/db/ai_report_feedback.py`; `src/prm/runtime/memory.py`.

**Проверка.** tests/test_artifact_feedback.py, tests/test_editorial_memory.py; tests/test_daily_feedback.py: no reaction unknown, all emoji positive interest, отмена правила, wrong target/version, learning state provenance, repeated signals not automatic confirmed preference. A/B selection replay показывает конкретное изменение.

**Доступы и переход.** Настройка logging/retention до personal usage. Не просить владельца маркировать каждый пост.

**Переиспользование.** PAI-14, PAI-21.

<a id="d21"></a>
### D21 Память которая помогает следующему вопросу

P0 · G1 · K/H · размер M. Зависимости: D04, D08, D10.

**Цель.** Полезный сохранённый контекст действительно используется и управляется владельцем.

**Изменение.** Context builder объединяет current task, bounded turns, relevant confirmed memory, project и selected source refs с раздельными grants. Улучшить memory retrieval сверх substring JSON, добавить explicit save/correct/inspect/forget/export natural flows. Для явной однозначной команды предложить save+undo policy, сохраняя preview до её принятия. Не вводить второй memory service.

**Компоненты.** `src/prm/runtime/memory.py`; `src/prm/memory_library.py`; `src/prm/storage/conversations.py`; `src/prm/runtime/composition.py`; `src/prm/runtime/deletion.py`.

**Проверка.** tests/test_pai_memory_runtime.py, tests/test_pai_durable_conversation.py; tests/test_daily_memory_context.py: remembered preference improves answer, unrelated memory excluded, expired/revoked source not recalled, corrected fact wins, conversation reset vs permanent memory, forget cascades. No inferred read/understood/applied.

**Доступы и переход.** Политика explicit save/undo — изменение UX semantics, не отмена existing подтверждений без решения.

**Переиспользование.** PAI-05, PAI-21.

<a id="d22"></a>
### D22 Настоящий private storage target

P0 · G2 · K/C · размер L. Зависимости: D01.

**Цель.** Личные данные могут храниться в проверяемой постоянной среде.

**Изменение.** Добавить отдельный PrivateTarget/protocol рядом со строгим SyntheticTarget, explicit identity/auth, app/migrator roles и staged versioned migrations. Убрать test-role coupling из новых migration definitions, не менять исторические checksum без migration. Secrets outside repo; connection config redacted; test environment отдельный. Подготовить private install manifest, не применять к production.

**Компоненты.** `src/prm/storage/postgres.py`; `src/prm/storage/`; `src/prm/runtime/setup.py`; `src/prm/runtime/composition.py`; `src/prm/cli.py`.

**Проверка.** tests/test_pai_storage.py, tests/test_pai_migration.py; tests/test_daily_private_target.py на отдельной disposable БД: wrong identity, privileged role, schema mismatch, DDL denied app role, auth failure redaction, additive migration/reopen, no ambient DSN fallback. Synthetic guard остаётся строгим.

**Доступы и переход.** Код/изолированный PG разрешены в будущем local block; реальный host/DSN/migration отдельный D27 grant и независимое security review.

**Переиспользование.** PAI-02, PAI-25, PAI-28.

<a id="d23"></a>
### D23 Retention backup и восстановление private среды

P0 · G2 · K/C/H · размер M. Зависимости: D22.

**Цель.** Потеря процесса или восстановление не теряют контекст и не повторяют действия.

**Изменение.** Применить existing backup/domain migration к private target и согласованным retention windows. Защитить backup/artifacts ключами и правами по threat model, записать restore order: authority/tombstones/fences до serving. Отдельно measured RPO/RTO на копии и storage/disk limits; rollback app/schema compatibility matrix.

**Компоненты.** `src/prm/runtime/operations.py`; `src/prm/runtime/migration.py`; `src/prm/runtime/deletion.py`; `src/prm/storage/artifacts.py`; `docs/runbooks/assistant_runtime.md`.

**Проверка.** tests/test_pai_migration.py, tests/test_pai_operations_runtime.py, tests/test_pai_memory_runtime.py; restore rehearsal на synthetic private-target copy с revoked grants, unknown effect, consumed confirmation, deleted source, interrupted artifact cleanup и disk full. Hash/count/refs parity и no replay.

**Доступы и переход.** Владелец выбирает сроки и backup destination перед private persistence. Нет обещания мгновенного удаления у provider/из старого backup.

**Переиспользование.** PAI-21, PAI-24, PAI-25.

<a id="d24"></a>
### D24 Один профиль запуска и наблюдаемое состояние

P0 · G2 · K/C · размер M. Зависимости: D01, D02, D22.

**Цель.** Запуск и поддержка не превращаются в отдельный ежедневный проект.

**Изменение.** Подготовить coherent ingress/compute/effect/scheduler configs и service templates с single poller/leader control, safe health/status, last successful job/source, classified error/backoff. Silent loop failures становятся safe diagnostic events и degraded status. Default background/writes off, emergency pause/drain/kill проверяемы. Startup сам не мигрирует.

**Компоненты.** `src/prm/runtime/service.py`; `src/prm/runtime/operations.py`; `src/prm/cli.py`; `systemd/pai-worker.service.example`; `systemd/telegram-prm-assistant.service`.

**Проверка.** tests/test_pai_operations_runtime.py, tests/test_pai_load_recovery.py; tests/test_daily_launch.py: duplicate process/poller, missing worker, invalid config, SIGTERM, crash loop, queue age, source failure. Preflight сообщает configured/observed раздельно. Никаких systemctl start в CI.

**Доступы и переход.** Deploy manifest готовится локально; actual service startup после выбранного host/cutover решения D27.

**Переиспользование.** PAI-24, PAI-28.

<a id="d25"></a>
### D25 Приватный reader удобный на телефоне

P1 · G2 · K/C/L/H · размер M. Зависимости: D19, D22, D23.

**Цель.** Полный обзор открывается из Telegram без технических заголовков авторизации.

**Изменение.** Добавить reviewed browser session exchange для exact owner/report/version, короткий одноразовый token→cookie flow, TLS/reverse proxy deployment contract, no indexing/cache/analytics и revoke checks. Tokens не в access logs/referrers; persisted sessions scoped and expiring. Return-to-chat сохраняет focus. Альтернатива на первом этапе — безопасная доставка существующего PDF/MD без публичного hosting. Сначала использовать native rich D58 там, где он покрывает задачу. Reader остаётся обычной приватной веб-страницей; Mini App исключён владельцем. Не требовать hosting ради первого Telegram-улучшения.

**Компоненты.** `src/prm/runtime/reader.py`; `src/prm/runtime/render.py`; `src/prm/report_exports.py`; `src/prm/storage/artifacts.py`; `src/prm/runtime/delivery.py`.

**Проверка.** tests/test_pai_report_runtime.py и tests/test_pai_brief_polish.py; tests/test_daily_reader_session.py: stolen/expired/replayed token, wrong owner/version, source revoke after open, restart, referrer/log leakage, mobile back-to-chat. Browser и PDF visual checks на synthetic документах.

**Доступы и переход.** Выбор hosting и домена позднее; он не блокирует Telegram/plain document pilot. Full reader acceptance остаётся отдельной.

**Переиспользование.** PAI-15, PAI-27, PAI-28.

<a id="d26"></a>
### D26 Короткая настройка источников и полномочий

P0 · G2 · K/C/H · размер M. Зависимости: D07, D08, D23, D24.

**Цель.** Владелец выбирает полезные настройки без инфраструктурной анкеты.

**Изменение.** Экран readiness/connections: реально доступные возможности, 1–3 проекта, выбранные sources/window, timezone, retention, provider/data mapping и budget. Понятные read/AI processing/background/write scopes с provider token breadth. Defaults предложены, sensitive values выбираются явно. Missing connector предлагает независимый доступный путь; consent revision сохраняется один раз. Для выбранного Secretary-коннектора D60 показывать отдельно BotFather capability, connection identity/rights, локальный peer allowlist, model egress и запрет write. Telegram UI selection не равна provider-verifiable полной истории; не расширять Telethon session.

**Компоненты.** `src/prm/runtime/connections.py`; `src/prm/runtime/presentation.py`; `src/prm/storage/policy.py`; `src/bot/`; `docs/runbooks/assistant_runtime.md`.

**Проверка.** tests/test_pai_connections.py, tests/test_pai_durable_policy.py; tests/test_daily_onboarding.py: skip source, change timezone, partial grant, expired policy, revoke, no key in chat, token-wide vs selected folder wording. Обычное разрешённое чтение не спрашивает согласие повторно.

**Доступы и переход.** Synthetic preview готовится до владельца; личные значения хранятся вне Git. Пользователь подтверждает конкретные настройки, не абстрактную свободу.

**Переиспользование.** PAI-03, PAI-16, PAI-27.

<a id="d27"></a>
### D27 Ограниченный canary реального чтения и запуска

P0 · G2 · L/C/H · размер M. Зависимости: D09, D12, D23, D24, D26.

**Цель.** Подтвердить реальный Telegram→assistant→source→answer путь на выбранных данных.

**Изменение.** Подготовить exact private-config commands, reviewed SHA/host/target/source/destination/model grants. Сначала test content/read-only foreground; source sync, one web discovery, answer delivery с message_id, cancel/revoke. После отдельного разрешения выполнить выбранный deploy profile и короткое наблюдение без mail writes; source failures локализовать. Reuse разрешённые scopes, не повторять общий запрос на разрешение. Через тот же выбранный bot/chat выполнить canary D56–D58: getMe capability snapshot, plain/rich final, draft/Stop, callback, observed client versions и rollback. Не активировать BotFather topics/business настройку автоматически. Provider acceptance и visual support записывать отдельно.

**Компоненты.** `docs/runbooks/assistant_runtime.md`; `src/prm/cli.py`; `src/prm/runtime/service.py`; `src/prm/runtime/delivery.py`; `docs/verification/PAI-pilot-access-20261010.md`.

**Проверка.** Actual receipts: exact SHA/config digest, real source version/message_id, 20 operator tasks из обновлённого packet, restart/cancel/revoke и restore prerequisites. В Git только sanitized metadata. Fetch, search, actual model, actual Telegram delivery фиксируются раздельно.

**Доступы и переход.** Требует конкретных источников, private storage/egress и запуска. При отсутствии доступа статус awaiting_resource только этой карточки; D28–D37 независимая разработка продолжается.

**Переиспользование.** PAI-27, PAI-28.

<a id="d28"></a>
### D28 Локальные черновики из обычного разговора

P1 · G3 · K · размер M. Зависимости: D04, D14, D21.

**Цель.** Делегирование начинается с качественного конкретного результата, который можно исправить.

**Изменение.** Natural request→local DraftDocument→versioned ActionProposal. Поддержать rewrite, recipient correction, exact timezone и attachments manifest; address lookup только из разрешённых contacts/explicit input. Локальный черновик доступен без account writes. Cloud draft явно отдельное действие. Показать краткий diff перед новым подтверждением; сохранить fully delivered preview binding. Локальные Telegram reply drafts из D61 используют тот же DraftDocument/ActionProposal. D62 добавляет отдельный business effect adapter; входящие и исходящие в source chat не подтверждают proposal. Exact disclosure из других личных источников виден владельцу до отправки.

**Компоненты.** `src/prm/runtime/actions.py`; `src/prm/confirmed_actions.py`; `src/prm/storage/actions.py`; `src/prm/runtime/composition.py`; `src/prm/conversation.py`.

**Проверка.** tests/test_pai_action_runtime.py, tests/test_pai_durable_actions.py; tests/test_daily_drafts.py: ambiguous recipient, tomorrow in timezone, changed attachment, old yes, two proposals, edit after delivery, local draft with no write grant. No inferred email address.

**Доступы и переход.** External send не входит в D28; effect engine переиспользуется без нового confirm bypass.

**Переиспользование.** PAI-04, PAI-20.

<a id="d29"></a>
### D29 Выбранная почта Microsoft с полным lifecycle

P1 · G3 · K/C/L/H · размер M. Зависимости: D10, D22, D26.

**Цель.** Ассистент находит, что требует ответа, и объясняет основания по настоящим письмам.

**Изменение.** Довести existing Graph OAuth/PKCE/vault/refresh/revoke и selected-folder delta до operator flow. Metadata triage отдельно от selected body/thread read; uncertain reply-needed не выдавать за факт. Paging, cursor reset, tombstones и link to original; messages с несколькими обязанностями не теряются. Mail candidates подключить к Brief/research без академической зависимости.

**Компоненты.** `src/prm/runtime/connections.py`; `src/prm/runtime/graph.py`; `src/prm/mail_connector.py`; `src/prm/runtime/connector_summary.py`; `src/prm/runtime/brief.py`.

**Проверка.** tests/test_pai_connections.py, tests/test_pai_graph_mail.py; tests/test_daily_mail_triage.py: metadata insufficient, thread pagination, moved/deleted mail, token refresh/revoke, expired delta, source injection. Live selected test folder: read/update/delete/revoke с protected receipts.

**Доступы и переход.** Выполнять live только если выбран Microsoft. Если выбран Google — D31 реализует тот же contract, не заставлять владельца заводить другой аккаунт.

**Переиспользование.** PAI-16, PAI-17, PAI-27.

<a id="d30"></a>
### D30 Календарь и адресаты в повседневном контексте

P1 · G3 · K/C/L/H · размер M. Зависимости: D10, D22, D26.

**Цель.** Понимать расписание и готовить реалистичные встречи без ошибок времени.

**Изменение.** Довести selected calendar/contacts read path: rolling window вместо навсегда фиксированной даты config, recurrence/exceptions, timezone conversion, free/busy, cancelled events, exact contact resolution. Связать mail+calendar duplicates, сохраняя разные source authority. Подготовка встречи использует fresh snapshot; read не включает invitations.

**Компоненты.** `src/prm/runtime/schedule.py`; `src/prm/schedule_connectors.py`; `src/prm/runtime/composition.py`; `src/prm/runtime/graph.py`.

**Проверка.** tests/test_pai_schedule_runtime.py, tests/test_assistant_contacts.py; tests/test_daily_calendar.py: DST repeated/missing hour, recurring exception, cancellation, all-day event, stale conflict, two same-name contacts. Actual selected calendar canary отдельно от fixture pass.

**Доступы и переход.** Выбор provider/calendar/contact sources нужен только для live. Read-only calendar даёт пользу до разрешения writes.

**Переиспользование.** PAI-18, PAI-27.

<a id="d31"></a>
### D31 Google адаптеры если выбраны владельцем

P1 · G3 · K/C/L/H · размер L. Зависимости: D10, D22, D26.

**Цель.** Поддерживать фактическую личную почту и календарь, не навязывая Microsoft.

**Изменение.** Реализовать Gmail/Google Calendar adapters по общему connection/read/draft/action contract, incremental history/sync tokens, minimal scopes и lifecycle. Сначала read, затем provider drafts/writes через общий executor. Reuse reviewed OAuth library при меньшей поверхности поддержки; проверить testing/published OAuth refresh lifecycle конкретного аккаунта. Не делать единый универсальный connector с десятками permissions.

**Компоненты.** `src/prm/runtime/connections.py`; `src/prm/mail_connector.py`; `src/prm/schedule_connectors.py`; `src/prm/runtime/actions.py`; `src/prm/runtime/connectors/google.py (новый)`.

**Проверка.** Общие connector contract tests плюс tests/test_daily_google.py: sync token expired, paging, draft write vs local draft, gmail.compose breadth, readonly grants, webhook/poll dedup, revoke/cleanup. Live test selected mailbox/calendar после scope decision.

**Доступы и переход.** Conditional provider branch: если не выбран Google, оставить deferred/not selected, не считать реализованным. Это не блокирует Microsoft и core daily loop.

**Переиспользование.** PAI-16, PAI-17, PAI-18, PAI-20.

<a id="d32"></a>
### D32 Настоящие подтверждённые письма и события

P1 · G3 · K/L/H · размер M. Зависимости: D23, D28.

Дополнительно один вариант: D29 + D30 **или** D31.

**Цель.** Делегировать конкретную запись и понимать её фактический исход.

**Изменение.** Выбранный mail/calendar provider подключить к существующему bound executor и reconcile. Exact preview account/recipients/content/attachments/time/invite consequences, one-use expiry и current versions. Отдельно provider acceptance, created object и recipient delivery. Реализовать только поддержанную сверку; uncertain absence не разрешает повторную отправку.

**Компоненты.** `src/prm/runtime/actions.py`; `src/prm/storage/actions.py`; `src/prm/runtime/graph.py`; `src/prm/runtime/delivery.py`.

**Проверка.** tests/test_pai_action_runtime.py, tests/test_pai_durable_actions.py, tests/test_pai_delivery.py; actual controlled recipient/calendar: one effect, exact provider object, duplicate confirmation, timeout/202→unknown→reconcile, revoke race, edited proposal. Независимый safety review перед live.

**Доступы и переход.** Если выбран Google, D31 заменяет provider-specific D29/D30 prerequisites; semantic prerequisites те же. Доступ recipient/calendar и preview approval обязательны; эта сессия ничего не отправляет.

**Переиспользование.** PAI-04, PAI-20, PAI-27.

<a id="d33"></a>
### D33 Наблюдения которые редко отвлекают

P1 · G3 · K/L/H · размер M. Зависимости: D02, D10, D17, D24, D26.

**Цель.** Сообщать о значимом изменении и надёжно молчать при его отсутствии.

**Изменение.** Natural current-object→Watch preview с trigger/cadence/sources/expiry/quiet/caps/cost. Event-based novelty и per-topic importance, digest coalescing, no-news silent по политике, snooze/paused/done/revoke. Показать saved intent vs running scheduler. Для сроков fresh source check; urgent override только заранее выбранный.

**Компоненты.** `src/prm/runtime/watch.py`; `src/prm/runtime/scheduler.py`; `src/prm/watch_jobs.py`; `src/prm/runtime/delivery.py`; `src/prm/runtime/ingress.py`.

**Проверка.** tests/test_pai_watch_wiring.py, tests/test_pai_scheduler.py, tests/test_pai_delivery.py; tests/test_daily_watch_noise.py: duplicates/revisions, quiet DST, edited deadline, pause/revoke between enqueue/send, catch-up after outage, unknown send. Live 7-day receipt: due/checked/notified и user useful/noisy assessments.

**Доступы и переход.** Фоновые checks/delivery включаются отдельной selected subscription; состояние модели не является observed scheduler activity.

**Переиспользование.** PAI-08, PAI-09, PAI-27.

<a id="d34"></a>
### D34 Документы голос и изображения в общей беседе

P1 · G3 · K/L/H · размер M. Зависимости: D04, D05, D21, D23.

**Цель.** Можно передать привычный файл или голосовое и продолжить работу с ним.

**Изменение.** Довести existing media download/text extraction/OCR/speech/vision seams до естественного document focus и исправления транскрипции. Text-first PDF, page refs; docx/txt только по реальной потребности и isolated parsing. Allowlist types/size/decompression/time, no active content/network. Голосовой ответ опционален; важные факты доступны текстом. Входящий Telegram rich_message/quote/forward разбирается через normalized source envelope D56 и отдельный bounded rich block extractor; неподдержанный блок даёт явный partial/unsupported. Скрытое происхождение пересылки не восстанавливать выдуманным chat/message ID.

**Компоненты.** `src/prm/runtime/media.py`; `src/prm/runtime/media_download.py`; `src/prm/runtime/media_extract.py`; `src/prm/runtime/speech.py`; `src/prm/runtime/vision.py`.

**Проверка.** tests/test_pai_media_runtime.py; tests/test_daily_media_dialogue.py: scanned/text PDF, Cyrillic tables, malicious document, OCR date error, voice name correction, no vision grant, temp cleanup on cancel/failure. Real selected audio/image canary и page-grounded answer отдельно.

**Доступы и переход.** Private audio/image egress отдельно от text. Новый формат не разрешает arbitrary files или shell.

**Переиспользование.** PAI-22, PAI-27.

<a id="d35"></a>
### D35 Судья с доказательствами и полными диалогами

P0 · G1 · K/R · размер M. Зависимости: D06.

**Цель.** Оценка видит реальные основания ответа и пропущенные важные материалы.

**Изменение.** Общий judge case schema для answer/research/Brief/session: full visible turns, source spans/versions/dates, candidate set, tool outcomes, expected constraints и versions. Убрать обязательное молчаливое усечение до 4000 символов: bounded packet с completeness flag. Assessable/unknown для отсутствующих доказательств. Judges остаются advisory, output schema строго проверяется.

**Компоненты.** `tools/assistant_answer_judge.py`; `tools/assistant_visual_judge.py`; `tools/opencode_pool_review.py`; `src/prm/runtime/evaluation.py`; `evals/assistant_judge/`.

**Проверка.** Existing judge tests при наличии плюс tests/test_daily_judge_packets.py: URL without source yields unknown, missing middle turn rejected, omitted important candidate visible, injection in evidence, malformed verdict, blinded labels. Historical results не перезаписываются новой схемой.

**Доступы и переход.** Harness offline независимо от credentials; actual judge calls только выбранный provider/public data budget.

**Переиспользование.** PAI-23, PAI-26.

<a id="d36"></a>
### D36 Калибровка судьи и контроль смещения

P1 · G1 · K/R/H · размер M. Зависимости: D35, D05.

**Цель.** Высокая модельная оценка имеет проверенное значение.

**Изменение.** 40 human-labelled pairs и 20 seeded faults, separate calibration/holdout. Blind A/B and swap, repeat/length/style/injection controls; second family judge на 20% и adjudication disagreements. Выход включает agreement/order consistency/repeat consistency/critical false negatives/confusion matrix и uncertainty. Сохранять requested/observed identity/effort.

**Компоненты.** `evals/assistant_judge/`; `tools/assistant_answer_judge.py`; `tools/assistant_visual_judge.py`; `docs/strategy/2026-10-11/MODELS_EVAL.md`.

**Проверка.** Offline rubric/packet checks; после provider grant actual calibration: proposed ≥80% human agreement, ≥90% swap/repeat consistency, zero seeded critical misses. Ниже порога judge не используется для promotion. Human labels не корректируются ради согласия с моделью.

**Доступы и переход.** Владелец размечает личную полезность ограниченной части; технические fault labels проверяет исполнитель. Калибровка не даёт safety acceptance.

**Переиспользование.** PAI-23, PAI-26, PAI-29.

<a id="d37"></a>
### D37 Сравнение моделей и фактической стоимости

P1 · G1 · K/R/L/H · размер M. Зависимости: D05, D06, D07, D36.

**Цель.** Выбрать рабочие роли на одинаковых задачах, включая запрошенный GPT-4o baseline.

**Изменение.** Исполнить MODELS_EVAL: capability canary→12-case screening→120-unit paired holdout для finalists→shadow pilot. Фиксировать source/prompt/tool/context budgets, cold/warm cache, availability windows, cost_per_success. Разные source datasets не смешивать. Promotion только после quality floors; inconclusive outcome сохраняет baseline.

**Компоненты.** `src/prm/runtime/profiles.py`; `src/prm/runtime/evaluation.py`; `evals/assistant_judge/`; `tools/assistant_answer_judge.py`; `src/prm/runtime/cost_cache.py`.

**Проверка.** Deterministic experiment manifest and dry-run cost estimate; actual receipts с requested/observed model, 403/429/timeout/usage/latency. Report wins/ties/losses и paired bootstrap по cases/sessions, not correlated turns. GPT-4o unavailable → missing baseline, не победа Go.

**Доступы и переход.** Budget и допустимость assistant traffic/egress должны быть выбраны. Если сравнительный доступ отсутствует, первый пилот использует разрешённый baseline с явной неопределённостью.

**Переиспользование.** PAI-23, PAI-26, PAI-27.

<a id="d38"></a>
### D38 Четырнадцать дней ежедневного использования

P0 · G2 · L/H/R · размер M. Зависимости: D18, D19, D21, D27, D40.

**Цель.** Доказать, что core assistant экономит работу на реальных задачах.

**Изменение.** После 20-task foreground session провести 14 дней read-focused pilot: свои запросы, поиск, save/return, project application и on-demand Brief. Брать ограниченную добровольную оценку полезности/переделки/минут; учитывать время настройки и исправлений. Не навязывать ежедневный чеклист. При source outage переключать только в разрешённый доступный путь.

**Компоненты.** `docs/verification/ (новый sanitized pilot receipt)`; `src/prm/runtime/evaluation.py`; `src/prm/runtime/operations.py`; `src/db/artifact_feedback.py`.

**Проверка.** 20 задач: ≥16 полезных без существенной переделки как initial gate; добровольное использование ≥5/7 дней, weekly net time saved >0 и maintenance стремится ≤15min/week. Показать counts/unknowns; отсутствующее использование — факт для пересмотра, не автоматический провал человека. Telegram baseline и новая версия проходят одинаковые реальные задачи; считать ручные шаги, завершение без помощи, время до полезного результата, ошибочные привязки и затраты на настройку по TELEGRAM.md. D59/D60 условны и не задерживают основной пилот.

**Доступы и переход.** Личный operator pilot обязателен для утверждения ежедневной пользы. Его нельзя выполнить synthetic пользователем или judge.

**Переиспользование.** PAI-29.

<a id="d39"></a>
### D39 Четыре полезных недельных обзора

P1 · G3 · L/H/R · размер M. Зависимости: D17, D18, D19, D20, D27, D40.

**Цель.** Подтвердить качество отбора и долгосрочную пользу обзора.

**Изменение.** Начать параллельно D38 четыре последовательных weekly windows с заранее согласованным reading budget. Владелец отмечает главное пропущенное/лишнее и до трёх продолжений; сравнить с candidate coverage. Измерять cumulative duplicates, novelty, important misses и reading time. Не превращать непрочитанные пункты в долг и не считать recommended action выполненным.

**Компоненты.** `src/prm/runtime/brief.py`; `src/prm/storage/briefs.py`; `src/db/artifact_feedback.py`; `docs/verification/ (sanitized weekly receipt)`.

**Проверка.** Фактические четыре Brief IDs/versions, coverage, owner ratings, useful decisions/experiments, reading time 5–8min target, no critical deadline miss в выбранном coverage. Открытый документ не считается прочитанным. Пропуски расследуются по collector→ranker→editor цепочке. Один и тот же BriefDocument показывается текущим и rich renderer D58; оценивать время выбора продолжения, доступ к первоисточнику и шум, отдельно от редакционного качества.

**Доступы и переход.** Calendar duration нельзя заменить четырьмя synthetic генерациями в один день. Scheduled delivery только если включена владельцем.

**Переиспользование.** PAI-14, PAI-29.

<a id="d40"></a>
### D40 Приёмка интерфейса на реальном телефоне

P0 · G2 · K/H/L · размер M. Зависимости: D02, D19, D27, D56, D57, D58.

**Цель.** Ежедневный путь удобен в настоящем Telegram, а не только в browser fixture.

**Изменение.** Проверить short answer/card, status/cancel, reply binding, selection controls, exports на телефоне владельца. Reader добавляется после D25 отдельной записью, не блокируя text pilot. Исправить clipping, controls placement, Cyrillic/long links и лишний technical wording в затронутых templates. Единая сравнительная приёмка включает новые rich/draft/Stop/callback сценарии D56–D58. Ранний plain baseline можно снять в D27 до их завершения; enhanced acceptance требует всех трёх. Не создавать отдельный Telegram-пилот с дублирующими отчётами.

**Компоненты.** `src/prm/runtime/presentation.py`; `src/prm/runtime/delivery.py`; `src/prm/report_exports.py`; `docs/verification/ (visual acceptance receipt)`.

**Проверка.** tests/test_pai_brief_polish.py, tests/test_pai_control_polish.py; actual Telegram mobile session, synthetic public screenshots и owner rating. Long multipart controls относятся к correct object; mobile reader/HTML/PDF parity проверяется отдельно после D25. 12 сопоставимых задач (4 chat, 4 research, 4 Brief): 12/12 верных object/source bindings, минимум 10/12 без помощи, ориентир ≥25% меньше ручных действий против baseline; показывать actual counts, время и client/version. Native Stop не обещает откат отправленного эффекта. Один мобильный клиент владельца и desktop; неподтверждённые платформы unknown.

**Доступы и переход.** Human visual acceptance не заменяется Kimi verdict. Private screenshots остаются вне Git.

**Переиспользование.** PAI-09, PAI-15, PAI-29.

<a id="d41"></a>
### D41 Canvas и персональный академический модуль после снятия отсрочки

P2 · G3 · K/L/H · размер M. Зависимости: D10, D26.

**Цель.** Довести полный замысел без блокировки остальных источников университетским доступом.

**Изменение.** Сохранить disabled Canvas adapter; подготовить selected assignments/calendar/announcements lifecycle и owner stage. Связать разрешённую mail/calendar информацию с AcademicCandidate, сохранив conflicts, deadline precision, eligibility uncertainty и local/source done. После institutional access выполнить narrow canary; не собирать grades/roster/submissions по умолчанию. Общий coordinator согласовать с D52; не возвращать привязку всего Academic Inbox к наличию Canvas config.

**Компоненты.** `src/prm/runtime/academic.py`; `src/prm/academic_inbox.py`; `src/prm/storage/academic.py`; `src/prm/runtime/composition.py`.

**Проверка.** tests/test_pai_academic_runtime.py; pending actual selected course/source canary: missing permission, inconsistent deadline, edited/cancelled assignment, local done vs source completion, revoke. Mail-only academic useful path не объявляет Canvas connected.

**Доступы и переход.** Canvas institution access остаётся отложенным; его не запрашиваем сейчас. Nebula исследована отдельно по новому поручению владельца: D51–D54, ключ запросит владелец. Nebula-only/mail-only не зависят от Canvas. Полная программа не помечается done при обязательном незакрытом модуле.

**Переиспользование.** PAI-19, PAI-27, PAI-29.

<a id="d42"></a>
### D42 Сквозной отзыв экспорт и удаление

P1 · G3 · K/L/H · размер M. Зависимости: D21, D23, D34.

Дополнительно один вариант: D29 + D30 **или** D31.

**Цель.** Владелец управляет накопленным контекстом и понимает границу удаления.

**Изменение.** Проверить новые projects/feedback/event clusters/reader sessions/connector caches на общую lineage/tombstones схему. Natural privacy overview/export/forget source с областью и исключениями. Отзыв немедленно блокирует serving/egress, physical cleanup может быть pending; backup/provider сроки явно показаны. Receipts сохраняют минимальную no-replay информацию. По мере выбора D59/D60 включить message/topic/presentation bindings, business revisions, InboxCandidate в общую deletion/lineage схему. После revoke запрещено продолжать serving старых источников; минимальные no-replay receipts не стираются. Реальный lifecycle выбранной ветки проверяется её карточкой, без зависимости Secretary от почты.

**Компоненты.** `src/prm/runtime/deletion.py`; `src/prm/runtime/memory.py`; `src/prm/runtime/reader.py`; `src/prm/runtime/migration.py`; `src/prm/runtime/cost_cache.py`.

**Проверка.** tests/test_pai_memory_runtime.py, tests/test_pai_migration.py, tests/test_pai_connections.py; tests/test_daily_privacy_cascade.py: concurrent new derived object, offline store, export pagination beyond1000, restore tombstones before reads, revoked session, pending cleanup. Независимый privacy recheck.

**Доступы и переход.** Provider-specific D31 заменяет D29/D30 где выбран Google. Live deletion preview должен описывать exact source/scope; canonical independent archive не удаляется случайно.

**Переиспользование.** PAI-16, PAI-21, PAI-25.

<a id="d43"></a>
### D43 Устойчивость в условиях реального хоста

P1 · G3 · K/L/R · размер M. Зависимости: D24, D27.

**Цель.** Сбой не требует постоянного внимания и не создаёт скрытых эффектов.

**Изменение.** Закрыть current extreme HTML-depth P2 с явной payload bound/fallback; instrument classified errors, queue admission, provider cooldown, disk pressure и clock skew. Проверить long provider calls/locks/cancel, split compute/effect capacity. Defined read retry policy не стирает unknown spend. Подготовить one-page incident flow и recovery evidence.

**Компоненты.** `src/prm/runtime/delivery.py`; `src/prm/runtime/service.py`; `src/prm/runtime/operations.py`; `src/prm/storage/jobs.py`; `src/prm/storage/policy.py`.

**Проверка.** tests/test_pai_delivery.py, tests/test_pai_load_recovery.py, tests/test_pai_end_to_end.py; controlled host fault rehearsal после разрешения: process kill, DB unavailable, quota429, disk full, clock/timezone, stale lease. Observe intake/cancel/lock latency и no repeated effects. Telegram update gap >24h, restart draft lease, stale native Stop, rich final unknown, 429 coalescing и Secretary disconnect по выбранным capabilities. Не обещать восстановление business history без подтверждённого API.

**Доступы и переход.** Host incident tests требуют выбранного безопасного окружения; не ломать работающие сервисы ради проверки.

**Переиспользование.** PAI-06, PAI-09, PAI-24, PAI-28.

<a id="d44"></a>
### D44 Приёмка полного ассистента по требованиям

P1 · G4 · R/H/L · размер M. Зависимости: D25, D32, D33, D34, D39, D41, D42, D43, D37, D38, D47, D54.

**Цель.** Полная готовность означает работающие сценарии и подтверждённую пользу.

**Изменение.** Сверить все 69 требований spec и 10 групп с latest exact SHA receipts; обновить product status слоями code/fixture/provider/visual/operator/formal. Выполнить текущий полный активный product tier только после значимого интеграционного изменения и scoped checks; независимые риск-ревью и настоящее human acceptance. Неподключённые обязательные источники остаются blocker. Для Nebula отдельно проверить receipts D51–D54 и выбранный scope; D55 условна, а ключ Nebula не закрывает Canvas gate.

**Компоненты.** `docs/PRODUCT_STATUS.md`; `docs/verification/PAI-requirement-evidence-20261010.md`; `tools/run_pai_acceptance.py`; `docs/design/PAI.design.json`; `docs/tasks.md`.

**Проверка.** Current registered spec matrix, zero unexpected skips/xfails, approved private live receipts, visual owner acceptance, 20-task plus prolonged pilot. Ни judge, ни CI expected rejection не создают approval. Conditional integrations отображаются по явному selected scope.

**Доступы и переход.** Пока обязательный D41 отложен, можно принять daily/other capabilities, но whole programme остаётся незавершённым. Не переименовывать в урезанную final версию. Telegram D56–D58 входят через D40/D38. D59/D60–D62 требуют явного решения выбора и собственных live/operator gates, когда выбраны; их неопределённость не блокирует core assistant. Невыбранная optional capability записывается как deferred/not-selected, а не implemented/PASS.

**Переиспользование.** PAI-26, PAI-27, PAI-28, PAI-29.

<a id="d45"></a>
### D45 Разделение больших модулей по действительным обязанностям

P2 · G4 · K · размер L. Зависимости: D03, D06.

**Цель.** Новый сценарий меняется в нескольких понятных местах без разрушения безопасности.

**Изменение.** Постепенно выделять conversation/research/briefs/connectors/jobs/actions внутри prm, SQL в repositories, presentation отдельно. Начать с изменяемых composition dispatch и Brief selection, затем exports/watch. Typed dependencies вместо scattered hasattr/service dict, normal formatting вместо semicolon chains. Compatibility wrappers сохраняют public imports до usage audit.

**Компоненты.** `src/prm/application.py`; `src/prm/runtime/composition.py`; `src/prm/briefs.py`; `src/prm/report_exports.py`; `src/prm/watch_jobs.py`; `src/bot/prm_handlers.py`.

**Проверка.** tests/test_prm_package_imports.py, tests/test_retrofit_boundaries.py плюс tests соответствующего перенесённого use case. Behavior/receipt parity на frozen fixtures, no new grant store/executor. Считать changed surfaces и time-to-change до/после, не только LOC.

**Доступы и переход.** Рефакторинг вплетать в продуктовые slices; массовый rename не предшествует ежедневному пилоту.

**Переиспользование.** PAI-07, PAI-10, PAI-14, PAI-24.

<a id="d46"></a>
### D46 Learned retrieval только при измеренном выигрыше

P2 · G4 · K/R/H · размер M. Зависимости: D11, D23.

**Цель.** Устранить реальные смысловые и bilingual промахи без ненужного сервиса.

**Изменение.** Сравнить локальный BGE-M3 или другой выбранный multilingual encoder и reranker с FTS/hashed baseline на gold misses. Derived index с source/version/grant keys, rebuild/delete и resource budget. Хранить vectors в простом локальном index для малого corpus; pgvector при измеренном объёме и выбранном ADR. External embeddings только scoped egress.

**Компоненты.** `src/db/archive_vector.py`; `src/db/archive_api_vector.py`; `evals/retrieval/`; `src/prm/runtime/cost_cache.py`; `src/prm/runtime/deletion.py`.

**Проверка.** Matched recall@20/nDCG@10, critical exact lookup retention, no-answer error, RAM/index build/query p95 и deletion/rebuild. Предлагаемый gate: ощутимый выигрыш на заранее выделенном классе промахов без regression и acceptable ops cost; threshold зафиксировать до run.

**Доступы и переход.** Conditional measured enhancement. Новая library/model download/index architecture нуждаются в pinned trust review и ADR, но FTS path продолжает работать.

**Переиспользование.** PAI-11, PAI-23, PAI-31.

<a id="d47"></a>
### D47 Понятные конфигурация промпты и зависимости

P1 · G4 · K/C · размер M. Зависимости: D05, D07.

**Цель.** Обновления воспроизводимы, а действующая конфигурация проверяется без чтения секретов.

**Изменение.** Схема runtime config с version/migration, role profiles и secret refs; safe example configs. Вынести затронутые prompts в versioned resources с input/output contracts. Зафиксировать воспроизводимый dependency lock/constraints и разделить runtime/eval/dev extras, сохранив совместимость Python и rendering. Inventories active/deprecated tools, no automatic latest upgrade. Bot API использует существующий urllib transport; новые методы не требуют миграции на aiogram/PTB или blind Telethon upgrade. Версионировать Telegram payload contracts, independent feature flags/capability evidence и lock выбранных dependencies. Telethon archive и BusinessConnection — разные коннекторы.

**Компоненты.** `src/prm/runtime/composition.py`; `src/prm/runtime/profiles.py`; `src/prm/runtime/research_answer.py`; `src/prm/brief_editorial.py`; `requirements.txt`; `requirements-playbook.txt`.

**Проверка.** tests/test_pai_chat_runtime.py, tests/test_pai_cost_cache.py; config schema fixtures, prompt hash changes and complete output parser tests; fresh isolated dependency resolution/build по утверждённым constraints. Не запускать paid eval при косметике prompts без semantic changes.

**Доступы и переход.** Версионирование не означает массовый перенос всех исторических prompts. Secrets/config реальной среды не переписывать.

**Переиспользование.** PAI-10, PAI-23, PAI-24.

<a id="d48"></a>
### D48 Короткая актуальная методика с проверками по риску

P1 · G4 · C/H/R · размер M. Зависимости: нет.

**Цель.** Разработка не требует больше внимания, чем продукт приносит пользы.

**Изменение.** Предложить ADR с current authority, one task registry/current handoff/status receipt и review-by-risk. Вынести исторические model/budget amendments в receipts/config, сохранить immutable past records. Один принятый дизайн плюс delta reviews; документы/низкорисковая UX правка не запускают programme batches. Подготовить законный путь принятия будущих slices без подделки прежних missing approvals.

**Компоненты.** `AGENTS.md`; `docs/CODEX_PROMPT.md`; `docs/REVIEW_POLICY.md`; `docs/IMPLEMENTATION_CONTRACT.md`; `docs/PLAYBOOK_ADOPTION.md`; `docs/adr/`; `tools/playbook.py`.

**Проверка.** Pinned --check-pin и plan/reference/approval-guard checks; independent read-only policy review проверяет сохранение source/egress/effect/retention guards и human authority. Старые STOP/draft/planned не превращаются в approved. Сравнить overhead на следующих трёх slices, без заявленного заранее процента экономии.

**Доступы и переход.** Только предложение до принятия владельцем изменённой нормативной политики. Эта работа не блокирует независимый локальный first block по текущему assignment.

**Переиспользование.** PAI-00, PAI-01.

<a id="d49"></a>
### D49 Масштабирование только по эксплуатационному пределу

P2 · G4 · R/K/H · размер L. Зависимости: D11, D23, D43.

**Цель.** Добавлять инфраструктуру, только когда она уменьшает измеренную работу или задержку.

**Изменение.** Отдельные решения для Redis/broker, переноса archive FTS в PG и workflow framework. Trigger: устойчивый queue/lock/query SLO miss после локальных оптимизаций либо неприемлемая поддержка. Для каждой альтернативы benchmark, migration/rollback, authority/deletion parity и полный ops cost. Не объединять три замены в один обязательный релиз.

**Компоненты.** `src/prm/storage/jobs.py`; `src/prm/runtime/migration.py`; `src/db/archive_search.py`; `src/prm/runtime/cost_cache.py`; `docs/adr/`.

**Проверка.** Paired workload measurements до/после, outage/redelivery/cache stale/deletion tests и restore rehearsal. Отсутствие measured trigger означает keep current, а не недоделанную обязательную Redis feature.

**Доступы и переход.** Каждая условная замена получает отдельную карточку и ADR перед реализацией; production migration отдельно разрешается.

**Переиспользование.** PAI-30, PAI-31.

<a id="d50"></a>
### D50 Поддержка качества без постоянного присмотра

P2 · G4 · K/C/H · размер M. Зависимости: D36, D38, D43, D47.

**Цель.** Новые модели и источники не ломают полезность незаметно.

**Изменение.** Подготовить release checklist, compact regression pack, provider-policy expiry monitoring и controlled profile rollout/rollback. После изменения model alias/prompt/schema выполнить соответствующую калибровку. Периодический обзор source noise/maintenance и неиспользуемых capabilities; не собирать бесконечные traces. Пользователь управляет частотой обзора состояния.

**Компоненты.** `src/prm/runtime/profiles.py`; `src/prm/runtime/operations.py`; `src/prm/runtime/evaluation.py`; `evals/assistant_judge/`; `docs/runbooks/assistant_runtime.md`.

**Проверка.** Simulated provider policy expiry/model alias drift/quality regression; rollback profile без удаления receipts, no private fallback, alert dedup. На реальном пилоте наблюдать maintenance time и actionable alert ratio; schedules включаются только по выбранной настройке.

**Доступы и переход.** Политика upkeep предлагается, не создаёт сейчас внешних automation/timers. Новая модель не означает автоматическую private promotion.

**Переиспользование.** PAI-23, PAI-24, PAI-29.

<a id="d51"></a>
### D51 Nebula: полноценное подключение и надёжное обновление данных

P1 · G1 · K/C · размер L. Зависимости: D10.

**Цель.** Полностью поддержать полезные публичные данные Nebula и их жизненный цикл в ассистенте; успешный GET не является итогом работы.

**Изменение.** По UTD_NEBULA.md выбрать готовый официальный SDK при наличии, генерацию клиента из совместимого Swagger либо existing HTTP transport с typed adapter; записать решение по покрытию/актуальности/recovery/сопровождению. Ввести NebulaSelection, provider_nebula и SourceBatch. Покрыть academic calendars, course/section/professor lookup/relations, campus events/location, clubs/discounts; включать в личный scope по интересу. Первые calendar/course endpoints — промежуточный срез, не финальный стоп. Нормализовать envelope, offset pagination и nested events, primary URLs и stable IDs. Durable checkpoint/cache по dataset/selection/window, last_success и unknown upstream freshness; restart/resume, bounded retries/backoff, изоляция отказа, key rotation/revoke, cancellation и coverage. Использовать общие storage/jobs/HTTP, не расширять legacy collector allowlist. Выбор компонента api-tools возможен в D55 при обоснованном пробеле.

**Компоненты.** `src/prm/nebula_connector.py (новый)`; `src/prm/runtime/nebula.py (новый)`; `src/prm/capabilities.py`; `src/prm/runtime/setup.py`; `src/prm/public_web.py`; `docs/strategy/2026-10-11/UTD_NEBULA.md`; `src/prm/storage/jobs.py`; `src/prm/storage/postgres.py`; `docs/runbooks/assistant_runtime.md`.

**Проверка.** Новый tests/test_daily_nebula_connector.py: контракты всех целевых семейств; pagination+duplicate IDs, empty vs missing vs stale, даты/timezones, unsupported production field, 401/403/429/5xx и byte/time/call caps. Restart с checkpoint, повторная page без дублей, конкурентный sync, key rotation/revoke, cancel, schema drift одного dataset при работе остальных, исчезновение в partial не равно deletion. Credential redaction/cross-host redirect/forbidden method. Synthetic результаты явно отделены от реального D54; только затронутые HTTP/storage/policy tiers.

**Доступы и переход.** Разработку разделить на обозримые пакеты с готовым пользовательским результатом; ключ не нужен для synthetic контрактов. Полное выбранное покрытие и provider evidence обязательны перед объявлением готовности. Ключ и ранний contract canary — первые шаги D54, без автозапуска фоновых заданий.

**Переиспользование.** PA-12, PAI-03, PAI-11, PAI-19.

<a id="d52"></a>
### D52 Nebula в общем диалоге и Academic Inbox без Canvas

P1 · G1 · K/C · размер L. Зависимости: D03, D10, D26, D51, D04, D08, D21.

**Цель.** Все полезные сценарии UTD доступны в обычном разговоре с сохранением контекста и результатов, независимо от Canvas.

**Изменение.** Вынести регистрацию общего academic service из Canvas config branch. Независимые Nebula/Canvas/mail hooks, типизированный выбор источника в dispatcher, reply/result context. Normalized records связать с выбранным term/session/course и проектным контекстом; только actionable records становятся AcademicCandidate. Добавить обратно совместимую date precision/source text/session модель; date-only не превращается в точное время. Aggregator не переопределяет Canvas/primary evidence. Origin IDs и field-path дедлайна стабильны. Приватный профиль фильтрует публичный результат локально. Поддержать поиск/сравнение курсов, секций и преподавателей, объяснение prerequisites по источнику, выбор term/session, события/клубы/предложения/место. Разрешать неоднозначные названия уточнением; не требовать от владельца provider IDs. Follow-up, сохранение, проектные связи, correction/forget и возврат после рестарта используют D04/D08/D21. Сохранённые результаты держат версии/источники. Календарный draft/напоминание готовится общим Act-контуром D28/D32, с source/timezone и обычным подтверждением; открытая зависимость Act остаётся явной.

**Компоненты.** `src/prm/runtime/composition.py`; `src/prm/runtime/academic.py`; `src/prm/academic_inbox.py`; `src/prm/storage/academic.py`; `src/prm/runtime/ingress.py`; `src/prm/runtime/nebula.py (новый)`.

**Проверка.** Новый tests/test_daily_nebula_academic.py плюс tests/test_assistant_academic.py и tests/test_pai_academic_runtime.py по затронутому поведению. Nebula-only, mail-only и disabled Canvas; запрос→источники→follow-up; другой term/session, date-only, DST America/Chicago, conflict, stale, wrong owner, local_done не source_done. Ноль Canvas HTTP при Nebula-only. Не выводить enrollment/eligibility из каталога. Сценарии всех целевых datasets, natural ambiguity, сравнение с отсутствующим полем, сохранение→restart→продолжение, исправление personal context, revoke/forget; длинный список имеет полное coverage или честное продолжение, а не скрытую обрезку.

**Доступы и переход.** NB-1 — несколько законченных пакетов по результату, а не обязательство вместить D51/D52 в один большой diff. Deep Review между пакетами, исправления и узкий P0/P1 recheck. Готовность общего диалога/памяти задают D04/D08/D21. Canvas не нужен; real utility — D54.

**Переиспользование.** PAI-05, PAI-07, PAI-19.

<a id="d53"></a>
### D53 Nebula в Brief и Watch с отбором и первоисточниками

P1 · G3 · K/C/H · размер L. Зависимости: D52, D17, D18, D20, D33.

**Цель.** UTD-находки снимают работу: несколько важных изменений вместо дублирующей ленты кампуса.

**Изменение.** Подключить SourceBatch Nebula к общим BriefSourceHook/Watch. Объединять Localist/Nebula/официальные записи по исходному URL/ID и явным identity bindings; при неуверенном совпадении не сливать сроки автоматически. Отбор по term, интересу и применимости к проекту. Срочные даты проверять по первоисточнику с сохранением precision/conflicts; отсутствие primary делает срок uncertain. Watch создаётся через обычный preview, уведомляет о существенном изменении, соблюдает pause/quiet hours/caps. Calendar write идёт только через D28/D32. Feedback применяется общим способом. Сохранять sync/notification state и переживать restart/retry без повторов. Отмена/исчезновение события проверяется по полному окну/первоисточнику; частичный ответ не удаляет запись. Полезное разнообразие и полное выбранное окно важнее количества карточек. Сбой Nebula не останавливает Brief других источников; источник, freshness и partial видимы. После выбора тем регулярная работа обходится без ежедневной настройки.

**Компоненты.** `src/prm/runtime/brief.py`; `src/prm/runtime/academic.py`; `src/prm/runtime/watch.py`; `src/prm/storage/watch_jobs.py`; `src/external_watch/selection.py`; `src/external_watch/relevance.py`; `src/prm/runtime/nebula.py (новый)`.

**Проверка.** Новый tests/test_daily_nebula_brief_watch.py и tests/test_external_watch_selection.py при изменении общей selection. Дубль источников→одна карточка; исправление даты→один revision; отсутствие изменений→нет push; source outage→partial, не пустая успешная неделя; pause/revoke/cancel; конфликт primary/aggregator остаётся видимым. Synthetic weekly corpus не считается доказательством живой свежести. Restart между detect/enqueue/send, повторная доставка, shifted/removed event, mixed source outage и пропуск early-window items. Два живых Brief и actual Watch usefulness входят в D54, имитация результата недостаточна.

**Доступы и переход.** NB-2: один пакет/Deep Review/исправления. Real pilot после D54 и готового D27 runtime; background schedule требует выбора владельца. Не блокирует общий daily pilot или отключённый Canvas.

**Переиспользование.** PAI-09, PAI-14, PAI-19, PAI-27.

<a id="d54"></a>
### D54 Nebula: реальный запуск и приёмка ежедневной работы

P1 · G2 · C/L/H/R · размер M. Зависимости: D52, D53, D27.

**Цель.** Подтвердить полноценную работу выбранных возможностей в реальном ассистенте, включая надёжность и пользу в течение двух недель.

**Изменение.** Владелец запросит ключ по тексту UTD_NEBULA.md. Ранний шаг после D51/D52: настроить secret reference и проверить до 20 GET на одном term/двух датах/курсе, актуальные schema/quota/cache rules. Это canary, не финальная приёмка. Далее проверить каждое выбранное семейство endpoints и representative pagination/date/session случаи; сверить минимум 10 реальных записей с первоисточниками. На готовых D53/D27 выполнить 14 дней использования, два недельных Brief и 20 сценариев из UTD_NEBULA.md, совмещённых с D38/D39. Оценить добавочную пользу, coverage, latency cold/warm, обращения к API, стоимость и обслуживание. Act-сценарий проверить с D32; до его готовности не объявлять полную готовность подтверждаемых действий. Пробелы источника передать в D55, не закрывать обязательную способность формулировкой недоступно.

**Компоненты.** `src/prm/runtime/setup.py`; `docs/runbooks/assistant_runtime.md`; `docs/security/OWNER-ACCESS-REQUEST.md`; `docs/verification/nebula-canary-20261011.md (будущий receipt)`; `docs/strategy/2026-10-11/UTD_NEBULA.md`.

**Проверка.** Proposed targets: >=16/20 полезных результатов без существенной переделки; каждый выбранный dataset проверен реальным read; ноль выдуманных точных сроков, скрытых coverage gaps, duplicate alerts и неподтверждённых действий. Срочные даты подтверждены первоисточником или явно uncertain. Проверить recovery после restart/429/expired key/schema drift; fault injection помечать synthetic. Provider receipt содержит даты/schema hashes/coverage/latency/error counts без ключей и личных payloads. Владелец кратко оценивает 3–5 ответов и два Brief; не вести отдельный дневник. Ориентир обслуживания — общий бюджет ассистента 15 минут/неделю; скорость/SLO подтверждаются замерами, не предположением.

**Доступы и переход.** AND dependencies описывают завершение D54: D52/D53/D27. Подготовка ключа и ранний canary после D51/D52 разрешены как незавершённый подэтап параллельно NB-2. Код не становится ready по одному smoke. Отсутствие ключа/обязательного dataset остаётся конкретным открытым gate; остальные способности ассистента продолжаются. Canvas не требуется.

**Переиспользование.** PAI-27, PAI-29.

<a id="d55"></a>
### D55 Условно: довести пробел данных через готовый компонент или официальный источник

P2 · G3 · R/K/C/L · размер M. Зависимости: D51.

**Цель.** Закрыть обнаруженный пробел обязательного пользовательского сценария работающим источником, используя готовые компоненты там, где они подходят.

**Изменение.** При конкретном пробеле, обнаруженном в раннем canary или D54, сравнить официальный fetch, разрешённый импорт набора и подходящий компонент api-tools. Оценить pinned schema, provenance, freshness, права на данные, cache/model cost и сопровождение; язык Go сам по себе не причина отказа. Если выбран api-tools/другой способ, выполнить обозримый implementation пакет: изолированный runner либо повторное использование parser, bounded selected input/output, общий SourceBatch, состояние/recovery, diagnostics и отключение. Нельзя ограничиться запиской о возможном fallback и объявить задачу решённой. Hosted API остаётся основным там, где работает. Нет автоматического scraping fallback после denied/rate-limit; Mongo upload и платный parser требуют фактически выбранного назначения/доступа.

**Компоненты.** `docs/strategy/2026-10-11/UTD_NEBULA.md`; `docs/adr/ (только при новом архитектурном решении)`; `src/external_watch/adapters.py (оценить переиспользование, не менять автоматически)`; `src/prm/runtime/nebula.py (новый)`; `src/prm/nebula_connector.py (новый)`; `tests/test_daily_nebula_fallback.py (условный новый)`; `docs/runbooks/assistant_runtime.md`.

**Проверка.** Сравнить на обнаруженном сценарии coverage/точность/freshness/операционную цену. Выбранный fallback проходит fixtures, provenance, budgets, restart/retry/dedupe и разрешённую реальную проверку; source outage не становится пустым успехом. Deep Review на законченный пакет, адресный recheck находок. Если hosted API достаточен, явный not-needed с доказательством, без инфраструктуры ради полноты списка.

**Доступы и переход.** Запускается по подтверждённому пробелу после D51, не ждёт завершения D54 и не создаёт циклическую зависимость. Блокирует только приёмку затронутой обязательной способности; остальные работы продолжаются. Настоящие подключения/runner/private egress не разрешаются этим планом.

**Переиспользование.** PA-12, PAI-19.

<a id="d56"></a>
### D56 Telegram: точная адресация результатов и работающие controls

P0 · G1 · K/C · размер M. Зависимости: D03.

**Цель.** Любой reply, цитата и кнопка продолжают правильный результат; обычный диалог сохраняет контекст без режимов.

**Изменение.** Расширить bindings D02, не создавать параллельный ingress. Ввести TelegramDestination, UpdateEnvelope v2 и MessageBinding (bot/chat/thread/message/job/result/version/story/revision/scope). Сохранить reply/quote/forward provenance; edited_message — revision. Durable commit/reject/quarantine до offset advance; allowed_updates по реализованным handlers. Исправить передачу navigation и callback acknowledgement в настоящей durable polling ветке. Оpaque callbacks <=64 bytes разрешаются сервером. Общий bounded Bot API transport возвращает Accepted/KnownRejected/Unknown; owner-only wrapper сохранён. Method/route/payload/schema digest входит в delivery identity; старые receipts и multipart читаются. Неподдержанные topics не смешиваются с default history. Proposed DTO/storage paths создаются лишь если нет подходящих после D02/D04.

**Обоснование.** [TELEGRAM.md](TELEGRAM.md), [telegram_evidence.json](telegram_evidence.json).

**Компоненты.** `src/bot/bot.py`; `src/prm/runtime/ingress.py`; `src/prm/runtime/transports.py`; `src/prm/runtime/delivery.py`; `src/prm/runtime/presentation.py`; `src/prm/runtime/composition.py`; `src/prm/telegram_contracts.py (proposed)`; `src/prm/storage/telegram.py (proposed)`.

**Проверка.** Новые tests/test_daily_telegram_routes.py и tests/test_daily_telegram_transport.py: actual polling→ingress→result→delivery с fake HTTP; update replay/conflicting body/DB failure; reply A после B; UTF-16 quote/hidden forward; edited source; чужой/expired callback; acknowledgement; inline markup reaches transport; timeout-after-dispatch остаётся unknown. Existing floor: tests/test_pai_ingress_jobs.py, tests/test_pai_delivery.py, tests/test_prm_bot_dispatch.py; conversation tier только при изменении ключей.

**Доступы и переход.** Без аккаунтов/сети на локальном code gate. После scoped checks и одного Deep Review перейти к dependency-ready D57/D58; настоящий Telegram route/receipt проверяется в D27/D40. Нельзя выводить readiness из helper-only unit tests.

**Переиспользование.** D02, D04, PAI-06, PAI-07, PAI-09, PAI-14.

<a id="d57"></a>
### D57 Telegram: честный прогресс, потоковый preview и остановка

P1 · G1 · K/C/R · размер L. Зависимости: D56, D02, D24, D05.

**Цель.** Долгая работа понятна и управляется одним нажатием, без потока уведомлений и потерянных результатов.

**Изменение.** JobQueue/worker events проецируются в ProgressEvent и PresentationState; сначала одна редактируемая status card, затем sendMessageDraft/sendRichMessageDraft. Draft nonzero ID + job/generation/route binding записывается до отправки, один foreground lease на chat/thread до проверки client concurrency. Coalesce frames, react retry_after, не показывать ложный процент. Native stopped_message_generation не имеет from: проверить owner private route/thread/active binding, поставить durable cancel fence и прекратить будущие calls/frames; попытаться оборвать transport, не обещать provider cancellation или undo effects. Draft живёт 30 секунд и требует отдельного durable final send; keep_on_stop=false. Проверенный partial хранится явно. SSE в D05 включать по matched latency/quality эксперименту; Search/Brief публикуют verified blocks. Unknown final исключает fallback/replay, legacy callbacks/text stop остаются.

**Обоснование.** [TELEGRAM.md](TELEGRAM.md), [telegram_evidence.json](telegram_evidence.json).

**Компоненты.** `src/prm/runtime/worker.py`; `src/prm/storage/jobs.py`; `src/prm/runtime/model.py`; `src/prm/runtime/ingress.py`; `src/prm/runtime/transports.py`; `src/prm/runtime/delivery.py`; `src/prm/runtime/presentation.py`; `src/prm/storage/telegram.py (proposed)`.

**Проверка.** Новый tests/test_daily_telegram_progress.py: native Stop без actor field, другой route/old draft, cancel vs completion/effect, restart lease, two jobs, 429, no provider SSE, 30s expiry, dropped stream/unknown spend/final unknown, no unverified text. Existing test_pai_workers.py и test_pai_delivery.py; model tier если затронут. В D40 измерить ack/first useful/cancel latency (предлагаемый ориентир ack <=2s) и число сообщений; маленькие выборки показывать числами. Model SSE лучше только при измеренном выигрыше без падения grounding.

**Доступы и переход.** Разбить на два законченных среза: truthful status/cancel, затем native draft/stream. Локальная разработка без bot; реальные client/Stop/limits — D27/D40. Нет draft capability — status card работает. Не заявлять native или user benefit PASS по synthetic тесту.

**Переиспользование.** D02, D05, D24, PAI-07, PAI-08, PAI-09.

<a id="d58"></a>
### D58 Telegram: полноценные интерактивные отчёты из общего документа

P1 · G1 · K/C · размер M. Зависимости: D56, D19.

**Цель.** Читать вывод, проверять источник и продолжать исследование внутри Telegram без потери полной версии отчёта.

**Изменение.** Pure renderer BriefDocument/answer→InputRichMessage.blocks: heading/paragraph/compact table/details/references/buttons. Один source of truth, exact object/version/story callbacks. Локально ограничить 32768 UTF-8 characters, 500 nested blocks, depth16, 50 media, 20 columns; делить по разделам без silent loss. Trusted controls/URLs формирует сервер, модель не выдаёт исполняемый JSON. sendRichMessage и editMessageText.rich_message проходят общий delivery ledger. Full exact action preview остаётся обязательным. Plain/HTML/PDF/MD fallback того же digest после known format rejection; unknown send не повторять. Feature flag независим от topics/Secretary/hosting.

**Обоснование.** [TELEGRAM.md](TELEGRAM.md), [telegram_evidence.json](telegram_evidence.json).

**Компоненты.** `src/prm/briefs.py`; `src/prm/runtime/presentation.py`; `src/prm/runtime/transports.py`; `src/prm/runtime/delivery.py`; `src/prm/report_exports.py`; `src/prm/telegram_rich.py (proposed)`.

**Проверка.** Новый tests/test_daily_telegram_rich.py: Cyrillic/emoji/count limits, deep details, large table, citations parity, missing/changed source, spoofed button/link, long full preview, known reject vs unknown, same document across renderers. Existing tests/test_pai_brief_runtime.py, tests/test_pai_brief_polish.py, tests/test_pai_delivery.py по затронутым частям. Actual mobile/desktop rendering и useful follow-up — общий D40; getMe не доказывает клиентскую совместимость.

**Доступы и переход.** Локальный renderer можно готовить параллельно D57 после согласования D56. Реальный canary требует только выбранный bot/chat и synthetic/public report; business connection не нужна. Rich off восстанавливает совместимое представление, сохраняя старые receipts/bindings.

**Переиспользование.** D19, D40, PAI-05, PAI-14, PAI-15.

<a id="d59"></a>
### D59 Условно: темы для параллельных личных исследований

P2 · G2 · R/K/C/L/H · размер L. Зависимости: D56, D04, D57, D27.

**Цель.** Возвращаться к двум длительным работам без смешения контекста и обязательной ручной организации.

**Изменение.** Сначала canary private topics BotFather/getMe на выбранном test bot; feature off по умолчанию. Conversation key v2 owner+bot+chat+thread, null сохраняет default history; TopicBinding отдельно от project/grants. Route всех drafts/finals/controls и exact confirmation учитывает thread. Rename/close не удаляют память; темы создаются по запросу или выбранной политике, не на каждый вопрос. Queue serialize по conversation с owner budget/concurrency cap вместо безусловного owner-wide compute lock. Default conversation остаётся полноценной. Rollback отключает новые темы, сохраняет существующие bindings и explicit return-to-main без слияния историй.

**Обоснование.** [TELEGRAM.md](TELEGRAM.md), [telegram_evidence.json](telegram_evidence.json).

**Компоненты.** `src/prm/conversation.py`; `src/prm/storage/conversations.py`; `src/prm/storage/jobs.py`; `src/prm/runtime/ingress.py`; `src/prm/runtime/composition.py`; `src/prm/runtime/transports.py`; `src/prm/storage/telegram.py (proposed)`.

**Проверка.** Новый tests/test_daily_telegram_topics.py: default migration, 2 topics/8 interleaved turns, reply/yes/stop across threads, late completion, restart, close/rename, stale generation and budget. Existing conversation/worker/ingress tiers по изменениям. Real two-task comparison с reply-only baseline: ноль context leaks, правильный resume, меньше ручных переключений либо явно выбранное удобство владельца; current clients recorded.

**Доступы и переход.** Аккаунтные настройки сейчас не менять. До canary можно завершать fixtures/migration code. Если темы не помогают или недоступны, оставить off с объяснением; D56–D58 и общий daily pilot не ждут D59. Not-selected не считать implemented.

**Переиспользование.** D04, D27, D40, PAI-10, PAI-13.

<a id="d60"></a>
### D60 Secretary: управляемое чтение выбранных переписок

P1 · G3 · R/K/C/L/H · размер L. Зависимости: D56, D26, D23, D10.

**Цель.** Подключить конкретные входящие как источник, сохраняя owner control plane и запрет исходящих действий.

**Изменение.** Сначала выделенная test connection и peer: проверить доступные read/deny-write rights, one-bot slot, редакции/удаления/disconnect и фактическую полноту. BotFather Secretary Mode использует BusinessConnection; реализовать business_connection/business_message/edited/deleted handlers отдельно от owner commands. Verify connection.user, revision,is_enabled, Telegram selection плюс local peer allowlist; никакого guessed history API. Нормализовать source IDs (bot/connection/peer/message/revision) в существующий source/lineage contract. Outage gap явно виден; не включать Telethon backfill. Минимальный getBusinessConnection до доверия, no LLM before scope. Разделить read/storage/model/background/notification grants. Incoming и собственные сообщения в source chat не подтверждают actions; не mark-as-read. Revocation/reconnect инвалидируют старые derived objects/scopes.

**Обоснование.** [TELEGRAM.md](TELEGRAM.md), [telegram_evidence.json](telegram_evidence.json).

**Компоненты.** `src/bot/bot.py`; `src/prm/runtime/ingress.py`; `src/prm/runtime/connections.py`; `src/prm/runtime/telegram_business.py (proposed)`; `src/prm/storage/telegram.py (proposed)`; `src/prm/storage/policy.py`; `src/prm/contracts.py`.

**Проверка.** Новый tests/test_daily_telegram_business_read.py: forged owner connection, peer outside scope, same message ID in different connection, edit/delete/tombstone, reconnect, revocation race, update gap, incoming prompt injection, no outbound calls. Existing connections/policy/revoke tiers по изменениям. Canary 1–2 выбранных test chats доказывает реальные receive/rights/lifecycle; private payload вне Git. Full history/echo не объявлять подтверждёнными.

**Доступы и переход.** Только выбранная ветка: локальный код без аккаунтов; live requires конкретное чтение/retention, отдельно model egress. Если провайдер не позволяет ограничить token rights до read, показать фактическую широту и enforce deny-write локально; не выдавать это за provider restriction. При отказе оставить forwarding путь. D60 не зависит от topics, Canvas или mail.

**Переиспользование.** D10, D26, D42, PAI-03, PAI-16, PAI-21.

<a id="d61"></a>
### D61 Secretary: обязательства, важные входящие и локальные ответы

P1 · G3 · K/H/L · размер L. Зависимости: D60, D21, D28, D33.

**Цель.** Ассистент снимает работу по разбору переписки и подготовке ответа, не превращая каждое сообщение в уведомление.

**Изменение.** InboxCandidate с source quote/revision, requester/promisor, action, deadline precision/timezone, uncertainty, project/status; reuse Academic deadline/conflict rules и D33 quiet/dedup/caps. Отличать просьбу/обещание/идею и факт от model inference. Сводка важных входящих и DraftDocument доставляются только в owner assistant chat. Поддержать snooze/dismiss/почему/исправить/подготовь ответ, в общем фокусе без Secretary mode selector. Source edit/delete/revoke инвалидирует derived candidate/draft и требует re-evaluation. Не подтягивать нерелевантный личный контекст; межисточниковое раскрытие явно показывать. Никаких send/read-receipt/auto-reply эффектов.

**Обоснование.** [TELEGRAM.md](TELEGRAM.md), [telegram_evidence.json](telegram_evidence.json).

**Компоненты.** `src/prm/runtime/telegram_business.py (proposed)`; `src/prm/runtime/academic.py`; `src/prm/runtime/actions.py`; `src/prm/confirmed_actions.py`; `src/prm/runtime/composition.py`; `src/prm/runtime/presentation.py`; `src/prm/watch_jobs.py`; `src/prm/storage/telegram.py (proposed)`.

**Проверка.** Новый tests/test_daily_telegram_secretary.py: source instructions, vague dates, reversed speaker, already completed obligation, edit/delete, repeated message, quiet hours, wrong project, unrelated private content in draft. 30 размеченных synthetic conversations: предложенный gate >=9/10 существенных обязательств и <=2/20 false actionable. Затем 7–14 дней на 1–2 выбранных чатах: реальные пропуски/ложные уведомления, полезность drafts и суммарное сэкономленное внимание; числа/ошибки, не inflated accuracy.

**Доступы и переход.** Synthetic quality и owner-only delivery сначала; пилот после D60 scopes/выбора модели. Live usefulness отдельно от passing extraction. При шуме отключить push и сохранить on-demand inbox/drafts; не требовать ежедневной разметки владельцем.

**Переиспользование.** D21, D28, D33, D41, PAI-19, PAI-20, PAI-21.

<a id="d62"></a>
### D62 Secretary: точный подтверждённый ответ от имени владельца

P1 · G3 · K/L/H · размер L. Зависимости: D61, D28, D23.

**Цель.** Отправить проверенный владельцем ответ конкретному собеседнику через существующую защиту действий.

**Изменение.** Добавить typed telegram.business_reply в общий ActionProposal/effect engine, отдельный Telegram adapter вместо Graph assumptions. Exact preview: connection/account/peer/reply target, полный body/entities/attachments, source and draft versions, expiry и disclosure refs. Confirmation только owner control chat, single-use/version-bound. Перед effect проверить connection revision/right, входящее в 24h window, recipient/source grant, cancel fence; outgoing source message не approval. Telegram success Message сохраняется с exact identity; dispatch timeout unknown без blind retry или plain/MTProto fallback. Canary проверяет возможность exact reconciliation по собственному echo; до доказательства этого manual unknown reconciliation. Read receipts/delete/profile/gifts остаются вне action allowlist.

**Обоснование.** [TELEGRAM.md](TELEGRAM.md), [telegram_evidence.json](telegram_evidence.json).

**Компоненты.** `src/prm/confirmed_actions.py`; `src/prm/runtime/actions.py`; `src/prm/storage/actions.py`; `src/prm/runtime/telegram_business.py (proposed)`; `src/prm/runtime/transports.py`; `src/prm/runtime/delivery.py`; `src/prm/runtime/presentation.py`.

**Проверка.** Новый tests/test_daily_telegram_business_actions.py + affected tests/test_pai_durable_actions.py/test_pai_action_runtime.py: changed peer/body/source/scope/connection, stale yes, expired24h, duplicate confirmation, revoke/cancel race, unknown send/reconcile. Отдельный approved test-peer send: exact message_id/account/recipient/body receipt и отсутствие второго эффекта; acceptance != recipient read. Privacy tests на перенос секрета из другого чата.

**Доступы и переход.** Код/fixtures без write credentials. Личный read grant не даёт send; перед canary конкретный peer/message/action scope, не общее разрешение секретарю. Если подтверждённой reconciliation нет — честно unknown и без автоповтора. Полезные D60/D61 продолжают работать без D62.

**Переиспользование.** D28, D32 (reuse effect engine, not dependency on mail access), PAI-04, PAI-20.

## Покрытие полного замысла

Это карта работ, не новое доказательство PASS. Существующая dated evidence matrix остаётся фактической базой. Все 69 exact IDs спецификации сопоставлены новым карточкам; acceptance каждой требует соответствующих code/provider/operator слоёв.

| Требование | Карточки |
| --- | --- |
| CHAT-01 | [D03](#d03), [D04](#d04), [D38](#d38) |
| CHAT-02 | [D04](#d04), [D19](#d19), [D59](#d59) |
| SEARCH-01 | [D12](#d12), [D14](#d14), [D27](#d27) |
| BRIEF-01 | [D18](#d18), [D39](#d39) |
| CONNECT-01 | [D10](#d10), [D29](#d29), [D30](#d30), [D31](#d31), [D51](#d51), [D54](#d54), [D60](#d60) |
| ACT-01 | [D28](#d28), [D32](#d32), [D62](#d62) |
| QUALITY-01 | [D06](#d06), [D35](#d35), [D38](#d38), [D44](#d44) |
| MIGRATION-01 | [D09](#d09), [D22](#d22), [D23](#d23) |
| UX-01 | [D01](#d01), [D26](#d26), [D56](#d56) |
| UX-02 | [D18](#d18), [D19](#d19), [D40](#d40), [D58](#d58) |
| UX-03 | [D04](#d04), [D19](#d19), [D56](#d56), [D59](#d59) |
| UX-04 | [D02](#d02), [D15](#d15), [D57](#d57) |
| UX-05 | [D02](#d02), [D32](#d32), [D43](#d43), [D57](#d57), [D62](#d62) |
| MEM-01 | [D04](#d04) |
| MEM-02 | [D21](#d21), [D42](#d42) |
| MEM-03 | [D08](#d08), [D20](#d20), [D21](#d21) |
| SEARCH-02 | [D04](#d04), [D11](#d11), [D12](#d12) |
| SEARCH-03 | [D15](#d15) |
| SEARCH-04 | [D14](#d14) |
| EVIDENCE-01 | [D10](#d10) |
| EVIDENCE-02 | [D14](#d14), [D17](#d17) |
| EVIDENCE-03 | [D12](#d12) |
| RAG-01 | [D11](#d11), [D46](#d46) |
| BRIEF-02 | [D18](#d18), [D39](#d39) |
| BRIEF-03 | [D19](#d19), [D58](#d58) |
| BRIEF-04 | [D16](#d16), [D17](#d17), [D18](#d18) |
| VISUAL-01 | [D19](#d19), [D40](#d40), [D58](#d58) |
| VISUAL-02 | [D25](#d25), [D40](#d40) |
| VISUAL-03 | [D19](#d19), [D40](#d40), [D58](#d58) |
| VISUAL-04 | [D19](#d19), [D25](#d25) |
| BRIEF-05 | [D16](#d16) |
| BRIEF-06 | [D10](#d10), [D16](#d16) |
| BRIEF-07 | [D19](#d19), [D58](#d58) |
| WATCH-01 | [D33](#d33) |
| WATCH-02 | [D33](#d33) |
| WATCH-03 | [D02](#d02), [D33](#d33) |
| WATCH-04 | [D33](#d33), [D43](#d43) |
| CONNECT-02 | [D26](#d26), [D29](#d29), [D30](#d30), [D31](#d31), [D60](#d60) |
| CONNECT-03 | [D26](#d26), [D28](#d28), [D32](#d32), [D62](#d62) |
| ACADEMIC-01 | [D41](#d41), [D51](#d51), [D52](#d52) |
| ACADEMIC-02 | [D41](#d41), [D52](#d52), [D53](#d53) |
| ACADEMIC-03 | [D41](#d41), [D52](#d52) |
| ACADEMIC-04 | [D41](#d41), [D52](#d52), [D53](#d53) |
| ACADEMIC-05 | [D41](#d41), [D52](#d52), [D54](#d54) |
| PERM-01 | [D07](#d07), [D26](#d26), [D32](#d32) |
| ACT-02 | [D28](#d28), [D32](#d32), [D62](#d62) |
| ACT-03 | [D28](#d28), [D32](#d32), [D62](#d62) |
| SEC-01 | [D04](#d04), [D12](#d12), [D14](#d14), [D34](#d34), [D60](#d60), [D61](#d61) |
| SEC-02 | [D05](#d05), [D07](#d07), [D34](#d34) |
| SEC-03 | [D23](#d23), [D42](#d42), [D60](#d60), [D61](#d61), [D62](#d62) |
| SEC-04 | [D23](#d23), [D26](#d26), [D42](#d42), [D60](#d60), [D61](#d61), [D62](#d62) |
| ARCH-01 | [D03](#d03), [D04](#d04), [D45](#d45), [D56](#d56), [D59](#d59) |
| ARCH-02 | [D10](#d10), [D22](#d22), [D42](#d42) |
| OPS-01 | [D02](#d02), [D15](#d15), [D24](#d24), [D43](#d43), [D57](#d57) |
| OPS-02 | [D23](#d23), [D24](#d24), [D43](#d43), [D50](#d50) |
| MODEL-01 | [D05](#d05), [D07](#d07), [D37](#d37) |
| MODEL-02 | [D07](#d07), [D37](#d37) |
| COST-01 | [D07](#d07) |
| COST-02 | [D07](#d07), [D37](#d37) |
| MEDIA-01 | [D34](#d34) |
| MEDIA-02 | [D34](#d34) |
| MEDIA-03 | [D19](#d19), [D28](#d28), [D34](#d34) |
| EVAL-01 | [D06](#d06), [D35](#d35), [D36](#d36), [D38](#d38) |
| EVAL-02 | [D06](#d06), [D37](#d37) |
| EVAL-03 | [D38](#d38), [D39](#d39), [D40](#d40) |
| DONE-01 | [D44](#d44) |
| PLAN-01 | [D01](#d01), [D03](#d03), [D38](#d38) |
| PLAN-02 | [D48](#d48) |
| PLAN-03 | [D45](#d45), [D47](#d47), [D48](#d48) |
