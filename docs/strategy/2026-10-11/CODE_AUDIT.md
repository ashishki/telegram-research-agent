# Актуальный код и разрывы до ежедневной полезности

Статический срез `23312b8` от 11 октября 2026. Ссылки ниже ведут к просмотренным компонентам; для воспроизводимого чтения использовать этот SHA. Личные БД, `.env`, аккаунты и процессы хоста не исследовались. Наличие unit-функции рассматривается отдельно от её вызова из пользовательского входа.

## Что подтверждено и чем

| Слой | Факт | Практическая граница |
| --- | --- | --- |
| Код | Есть `AssistantRuntime`, PG repositories, jobs, grants, BriefDocument, Graph/Canvas/media adapters, renderer и effect ledger. | Код не равен установленному сервису. |
| Synthetic execution | Receipt 10 октября: 398 active PAI passed, 69 требований, 10 групп сценариев; отдельные 43 delivery, 77 Brief, 33 recovery пересекаются. | Здесь эти наборы повторно не запускались; это датированное доказательство на `0fbcfd1`. |
| Provider | 11 реальных генераций DeepSeek V4.1 Flash; публичные GitHub exact-ref и Python HTTP fetch. | Нет доказательства доступа к личному архиву через работающего Telegram-бота, Brave discovery, Graph/Canvas live. |
| Judge | 6 сессий/25 ходов оценены DeepSeek Pro; Kimi оценил фиксированную версию renderer. | Малая synthetic выборка, нет human calibration; генератор и текстовый судья одной семьи. |
| Рендер | Новый Brief: 5 PDF страниц, zero clipping/browser errors в датированном прогоне. | Новое содержание и fixed-content Kimi benchmark — разные наборы. |
| CI/review | Merge receipt сообщает успешный remote CI; scoped review117 закрыл multipart P1, оставил extreme HTML P2. | Независимое ревью именно этого стратегического пакета не проводилось. |
| Польза | Реальный двадцатизадачный и длительный пилот отсутствуют в текущих receipts. | Процент продуктовой готовности выводить нельзя. |

Основание: [статус](../../PRODUCT_STATUS.md), [Go receipt](../../verification/PAI-go-pilot-20261010.md), [merge receipt](../../verification/PAI-master-integration-20261010.json), [матрица требований](../../verification/PAI-requirement-evidence-20261010.md).

## Конкретные наблюдения из кода

| ID | Проверенный участок и наблюдение | Следствие и работа |
| --- | --- | --- |
| F01 | [`cli.py`](../../../src/prm/cli.py), ветка `assistant`: durable root только при явных target/owner/config. Без них вызывается прежний `run_bot`. [`telegram-prm-assistant.service`](../../../systemd/telegram-prm-assistant.service) запускает `prm.cli assistant` без этих аргументов. | Шаблон стандартного запуска не доказывает использование PAI. Реальный запущенный SHA неизвестен. D01/D24 делают путь однозначным; не включать service сейчас. |
| F02 | [`postgres.py`](../../../src/prm/storage/postgres.py): единственный target — `SyntheticTarget`, loopback, нестандартный порт, `pa_test_*`, password empty, SSL disabled, специальный cluster marker. [`setup.py`](../../../src/prm/runtime/setup.py) и DDL жёстко используют test migrator/app. | Нельзя получить личное хранилище переименованием JSON или ослаблением synthetic guard. Нужна отдельная реализация target, миграций, ролей и проверки восстановления: D22/D23. |
| F03 | [`ingress.py`](../../../src/prm/runtime/ingress.py): `/status`, `/result`, `/cancel` требуют job ID; natural Watch controls сопоставляют фиксированные фразы; callback принимает только status/cancel/result. [`composition.py`](../../../src/prm/runtime/composition.py) выбирает mail/calendar/actions/memory/weekly по префиксам. | Частично естественные контролы уже есть, но универсального разрешения намерений и ссылок нет. D02–D04, D19, D28. |
| F04 | [`research.py:window_evidence`](../../../src/prm/runtime/research.py) делает `ORDER BY posted_at DESC ... LIMIT 48`. [`brief.py:build`](../../../src/prm/runtime/brief.py) добавляет наборы источников, затем использует `evidence[:48]`; успешный collector отмечается `checked`. | Ограничение размера выбрано до оценки важности; поздние источники могут не попасть. Нет явного счётчика остатка в этом hook-контракте. D10/D16: отдельно перечисление кандидатов и bounded model packet; обрезание отражать в coverage. Это статическое наблюдение, не новый провал выполненного теста. |
| F05 | `/deep вопрос` строит один archive step. JSON-план допускает archive/public/github, до 8 шагов/10 calls/300 секунд; worker параллелит чтения, хранит checkpoints и один gap_check. | Рабочий bounded исполнитель уже есть; автономное формирование подходящего межисточникового плана и дополнительной волны не доказано этим входом. D03/D12/D15, с переиспользованием `deep_research.py` после проверки семантики. |
| F06 | [`model.py`](../../../src/prm/runtime/model.py) — только Chat Completions: фиксированные `max_completion_tokens`, `store:false`, `stream:false`; отвергает `tool_calls`, принимает только exact model echo, ограничивает тело 48 KB и timeout 120s. | JSON для нынешнего синтеза поддержан, произвольный agent tool loop — нет. Разные API Go нельзя включить сменой строки model. Нужны adapters/metadata, контролируемое разрешение alias→snapshot и task policy: D05/D07. |
| F07 | `ModelProfiles` имеет chat/research/extraction/vision/speech/judge. `runtime_from_config` выбирает chat endpoint и создаёт registry без `comparison_receipts`; economical возвращается к balanced. Редактор Brief использует роль research. | Не объявлять три профиля тремя измеренными режимами качества. D07/D36/D37 добавляют явный редакторский workload, валидные receipts и проверку фактически выбранной роли. |
| F08 | [`conversations.py`](../../../src/prm/storage/conversations.py) хранит bounded expiring state/history; root берёт последние четыре generated ответа и разрешённые original/recent user turns. [`memory.py`](../../../src/prm/runtime/memory.py) хранит confirmed note/preference/learning, ищет `position(lower(query) in lower(payload::text))`. | История и явная память реально существуют. Переиспользуемая автоматическая сборка релевантной проектной/долговременной памяти в обычном ответе требует отдельного пути. D04/D08/D21; не подменять разрешённую память всей историей. |
| F09 | [`project_portfolio_context.py`](../../../src/assistant/project_portfolio_context.py) уже содержит goal/blocker/next_proof/status/aliases и подтверждение владельца. [`editorial_memory.py`](../../../src/output/editorial_memory.py), [`reaction_personalization.py`](../../../src/output/reaction_personalization.py), feedback stores существуют в прежнем контуре. | Не создавать второй профиль/feedback engine. Извлечь полезную логику и связать с новым runtime, сохранив положительный смысл reaction и unknown при отсутствии реакции: D08/D20. |
| F10 | [`archive_vector.py`](../../../src/db/archive_vector.py) строит детерминированные hashed vectors и FTS fusion. [`semantic_retrieval.py`](../../../src/assistant/semantic_retrieval.py) — curated deterministic+FTS. Native `LocalArchiveReader` вызывает canonical FTS. | Слово semantic в имени не доказывает learned multilingual retrieval. Сохранить baseline и отдельно сравнить локальные learned embeddings/reranker: D11/D46. |
| F11 | [`research_answer.py`](../../../src/prm/runtime/research_answer.py): максимум шесть findings, exact quote/URL, все claims должны пройти общий verifier; при одном неподдержанном фрагменте возвращается fallback. | Ценный барьер против выдуманных фактов может ограничивать объяснение и рекомендации. Это гипотеза о false rejects, не доказательство дефекта verifier. D14 измеряет accepted true paraphrases и unsupported leakage, вводит типы fact/inference/recommendation. |
| F12 | [`web.py`](../../../src/prm/runtime/web.py): Brave реализован, fetch ограничен trusted hosts. GitHub читает один public repository, exact ref, до 6 выбранных paths, без private authentication. | «GitHub подключён» сейчас означает узкий публичный read. D12/D13/D31 расширяют пользовательский путь и выбранные ресурсы, не права на push. |
| F13 | [`reader.py`](../../../src/prm/runtime/reader.py) выдаёт короткие in-memory sessions, проверяет owner/expiry/source grants, рендерит локально; HTTP reader требует Authorization. | Есть защищённый локальный backend, но не готовая мобильная авторизация по ссылке Telegram. D25 задаёт реальные session/cookie/TLS/proxy и revocation UX. |
| F14 | [`service.py`](../../../src/prm/runtime/service.py): пять ролей, ручная конфигурация; `except Exception` в loop ждёт и продолжает без классифицированной диагностики. | Сбой может превращаться для владельца в молчание. D24/D43 добавляют safe structured status, backlog age, degraded state и проверку процессов. |
| F15 | [`assistant_answer_judge.py`](../../../tools/assistant_answer_judge.py), старый общий case builder: answer до 4000 символов, source URLs, notes до 400, без обязательных source excerpts. Последний отдельный session judge использовал более полный пакет. | Старый judge не способен честно проверить entailment только по URL; это нельзя переносить на последний полный packet без различения. D35: evidence spans, omissions, trace и assessable/unknown, D36: калибровка. |
| F16 | `application.py` 1895 строк, `briefs.py` 2788, `watch_jobs.py` 1945, `report_exports.py` 1588, `composition.py` 603; в runtime много строк с несколькими операциями. | Размер сам по себе не дефект. Но роутинг, SQL, prompts и wiring тесно соседствуют, что усложняет изменения. D45/D47 — разделение по тронутым сценариям, без массового переезда ради структуры. |

## Модели в текущем проекте

Есть три разных значения «текущей конфигурации»:

- **Public code defaults прежнего LLM client:** `claude-sonnet-4-6` для digest/bot_ask, `claude-haiku-4-5` для pi_chat/classification, отдельные Opus labels для некоторых стратегических задач. Это статическая карта [`src/llm/client.py`](../../../src/llm/client.py), а не наблюдение доступности этих моделей сегодня.
- **Новый runtime:** endpoint/model выбираются явно в runtime config; production config не исследовался и в receipts не утверждён.
- **Последний developer benchmark:** DeepSeek V4.1 Flash → текстовый judge DeepSeek V4 Pro; визуальный judge Kimi K2.7 Code. Governed reviewer GLM и advisory reviewers — отдельная конфигурация разработки.

GPT-4o — запрошенный внешний baseline для нового сравнения. Нельзя утверждать, что он уже является production моделью, что Go лучше него, или что benchmark endpoint без изменений работает в обычном runtime.

## Что сохранить без повторной реализации

Объектные ID и версии; canonical archive; FTS; immutable BriefDocument; scoped source lineage; grants/revoke; CAS, leases и fencing; подтверждение exact proposal; durable effect attempt; неизвестный исход без слепого повтора; изолированный renderer; deletion tombstones и monotone restore. Они решают реальные задачи личного инструмента, даже с одним владельцем.

Разработку направлять на соединение этих частей и устранение измеренных ограничений. Не делать заново уже прошедшие PAI пакеты и не приписывать этому исследованию их проверки.

## F17. Nebula упомянута, но не подключена; Academic ingress привязан к Canvas

Дополнительное поручение владельца: [полный аудит Nebula и api-tools](UTD_NEBULA.md). Поиск по src не нашёл клиента/конфигурации Nebula. UTD ShadowCollector использует три официальных источника, а source_nebula_1 — synthetic пример precedence. В composition.py общий academic handler и Brief hook регистрируются внутри Canvas config branch; Nebula-only требует независимого coordinator. Новые задачи D51–D54 и условная D55; ни runtime, ни фактические подключения этим аудитом не изменены.

## F18. Telegram-интерфейс ограничен существующим transport/ingress

Подробности и ссылки на exact code — [TELEGRAM](TELEGRAM.md#текущее-состояние-проекта-и-совместимость), фактический [local probe](telegram_evidence.json). Bot использует прямой HTTP Bot API, не aiogram/PTB; Telethon обслуживает ingestion. Durable ingress теряет reply/thread metadata и возвращает None для native Stop, edited_message и business_message; это воспроизведено pure local вызовами с заблокированной сетью. navigation_markup отвергает inline_keyboard; durable polling не передаёт navigation IntakeReply. Conversation key — chat-only, compute serialization — owner-wide. Текущий model transport stream:false. Rich/draft/business methods отсутствуют в BoundedTelegramSender. Дельта встроена в D56–D62 и общие D02/D04/D05/D19/D25/D28/D40; новые API по документации не считаются observed integration.
