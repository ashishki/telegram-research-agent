# PA: проверка продукта 2026-10-09

Проверяемый код: `6467c503c7d196926632da03cf5dce49ed181d2e`. Задание владельца — полное тестирование доступной активной реализации, реальные синтетические прогоны и оценка моделью; границы зафиксированы в ADR-016. Это проверка текущей реализации, а не завершение всей программы или разрешение на релиз.

Исправлены обнаруженные сбои: личное воспоминание уходило в поиск; результат94,796байт превышал64KiB; Chat терял исходные слова пользователя; сокращение списка возвращало «1.»; Brief сохранял несуществующую вторую версию; редактор отвечал по-английски; фиксированный PDF обрезал страницу/длинную карточку. История теперь ограничена сроком хранения, исходным запросом и тремя недавними запросами; для передачи прошлых слов пользователя требуется отдельное разрешение. Поля подтверждений, источников и квитанций сохранены в компактном результате; большие диагностические данные связаны с удалением исходного запроса.

| Проверка | Результат | Команда |
| --- | --- | --- |
| pai-complete | 359 passed, 1115.03s | `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/test_tiers.py pai-complete` |
| focused-prm | 736 passed, 151.08s | `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/test_tiers.py focused-prm` |
| retrofit-boundaries | 150 passed, 14.37s | `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/test_tiers.py retrofit-boundaries` |

PAI включает все69 точных обязательств спецификации и10 сценариев; skip/failure не допускаются. Полный исторический pytest не запускался. Наборы пересекаются: складывать их как уникальные тесты нельзя. Дополнительно: исправления64/154.56s; длинный PDF15/23.92s; удаление диагностических частей1/7.25s; регистрация/bridge39/1.56s. Исходные неудачные прогоны сохранены. Первое полное357-case прохождение относилось к cbab0fb и не покрывало затем найденный P1; финальная таблица относится к6467c50. Pinned playbook_validate(tasks,references) всё ещё сообщает51 TASK_DESIGN_APPROVAL_REQUIRED: формальные approvals не созданы; этот известный governance gate не подменяет разрешённое владельцем локальное тестирование. План32 packets/69 IDs/10 scenarios и pin проверены.

## Что проверено в приложении

| Возможность | Наблюдение | Граница доказательства |
| --- | --- | --- |
| Chat | Два диалога,12 ходов: Аврора/Python, сокращение, сброс темы, fixture/mock, редактирование и смена адресата с сохранением «завтра утром». | Настоящая MiMo Flash; синтетические пользовательские сведения. |
| Search | Очередь/рабочий процесс извлекают два источника, сохраняют ссылки и отсутствие измерения результата. | AI-сводка не прошла строгую проверку; показаны исходные подтверждения (`evidence_only`). Полноценный внешний поиск отдельно не подтверждён. |
| Brief | Реальная редакционная модель, русский текст, цитаты, собственный immutable документ и native HTML/PDF/Markdown. | Исправленный экспорт повторно отрисован в native private runtime из точного ранее полученного JSON редактора и тех же синтетических источников; новых модельных вызовов нет. |
| Watch | Подтверждение, реальный локальный scheduler tick, сбор1 изменения,1 доставка тестовому адаптеру; после паузы нет новой задачи. | Время контролируется фикстурой; службы/таймеры не запускались, Telegram доставку имитирует адаптер. |
| Act | Точный предпросмотр, одна тестовая запись;202=unknown, авторизованная сверка находит объект, повторное подтверждение не повторяет запись. | Graph HTTP имитируется; это не отправка настоящему адресату и не доказательство получения письма. |

Дополнительно реальные публичные HTTP: GitHub `pytest-dev/pytest`, README.rst на точномSHA `e4f7f174bc4a1686b31639d29a3e211941390979` (0.933s); Python unittest, HTTP200/336954байта (0.761s). Первые ошибки измерительного скрипта сохранены: отсутствие обязательного аргумента и попытка JSON-сериализации bytes; это не объявлено отказом провайдера. Доступ к частному архиву/аккаунтам не выполнялся.

В исходном полностью полученном наборе11 реальных вызовов MiMo Flash,9 относятся к Chat. Все9 ответов Chat получены:3.184–12.418s на транспорте; приложение в этом benchmark использует явный30s лимит. Предыдущие задержки MiMo Pro до99–102s и неизвестные исходы не стерты. Это один development benchmark на Go через объявленный адаптер, без выбора production модели; стандартный8s лимит не изменён. Стоимость и фактический effort при отсутствии телеметрии остаются unknown.

## Оценка диалогов моделью

Важно: все сырые метки модели — pass, но3 из6 сессий не достигают заявленного4-по-каждой-оси порога. Метки не считаются успешным принятием; баллы и исходный JSON сохранены. Эту оценку нельзя выдать за повторную оценку после последних исправлений.

Исходная оценка до последних исправлений: GLM5.3, requested max / observed effort unknown; 478.329s; actual usage `{'prompt_tokens': 7313, 'completion_tokens': 31202, 'total_tokens': 38515, 'prompt_tokens_details': {'audio_tokens': None, 'cached_tokens': 11}}`. Оценены6 полных диалогов/24 хода с источниками и содержимым артефакта. Шкала1–5; диагностический порог4 по каждой оси. Нет человеческой калибровки или разрешения на релиз.

| Сессия | Вердикт модели | Среднее8 осей | Оси ниже4 |
| --- | --- | --- | --- |
| context_and_topic | pass | 3.62 | source_support=3, goal_progress=3, clarity=3, honest_execution_status=2 |
| editing_and_context_repair | pass | 4.88 | — |
| archive_research | pass | 4.50 | — |
| weekly_brief | pass | 4.62 | — |
| watch | pass | 4.00 | usable_next_step=3, clarity=3 |
| confirmed_action | pass | 4.00 | usable_next_step=3, clarity=3 |

The assistant behaves as a disciplined, honest state machine with strong fact fidelity, but not yet as a consistently natural conversational product. Its strongest demonstrated quality is execution truthfulness: saved watch intent is never conflated with a running monitor, the scheduler is reported unconfirmed until evidence shows activity, a mail send stays «unknown» until provider reconciliation, a repeated /actconfirm produces no second write (synthetic_graph_write_count 1), and nothing is claimed as live integration, recipient delivery or human acceptance — all Telegram receipts, archive contents, watch effects and graph writes in these records are explicitly synthetic, and only provider inference is framed as real. Fact fidelity is equally strong where sources exist: archive findings and the weekly brief reproduce supplied texts, URLs, windows and publication times exactly, keep unmeasured effects unmeasured, report the unittest/pytest source as containing no quality-advantage data, and add only conditional next steps. The single substantive functional defect is conversational robustness: a trivial in-chat edit request («Сделай короче») is answered by an irrelevant canned system line that also misrepresents the assistant's own demonstrably intact context — the one session scored below the diagnostic floor. The remaining weaknesses are ergonomic and presentational: operator-grade surfaces (raw JSON, UUID/hash tokens, mixed-language machine statuses, dangling empty fields, internal IDs the user was never shown in-band), an under-specified pause acknowledgment, a citation-count inconsistency and under-linked chat summary in the brief, and artifact rendering blemishes. Priority work, in order: (1) restore genuine handling of in-chat edit requests and remove the «диалог экспирирует» template; (2) humanize control surfaces — plain-language confirmations, proactively surfaced IDs, explained idempotency, no dangling machine fields; (3) align brief coverage counts with cited sources and clean artifact rendering; (4) make research-result delivery channel-consistent and coverage statements explicit. This conclusion is advisory and derives solely from the supplied synthetic records; it contains no release approval.

- context_and_topic: Turn 3 (major): «Сделай короче» is answered only with «Сейчас твой диалог экспирирует, так что я не могу увидеть детали твоего проекта напрямую.» — nothing is shortened, the line is irrelevant to the request, and it reads as a canned template response; the user must repeat or rephrase to get anything usable.; Turns 2–3 (major): the «диалог экспирирует» excuse is internally inconsistent and leaks internal mechanics: the assistant demonstrably retains the Aurora/Python context (uses it in the same turn 2 and recalls it exactly in turn 4), so the statement misrepresents actual behavior to the user.; Turn 2 (moderate): the example code block is syntactically broken for a beginner audience — the assert inside def test_... is not indented — and «from calculator import сложение # замени на реальное имя» is only weakly flagged as a placeholder.; Turn 2 (minor): «экспирирует» is an unnatural anglicism; «истекает/заканчивается» would be correct Russian (or the phrase should not appear at all).
- editing_and_context_repair: Turn 5 (minor): the answer opens with a meta-phrase («это срок, который фигурировал во всех вариантах, которые я предлагал») instead of anchoring first to the user's own original wording («Не смогу закончить сегодня, пришлю завтра утром»); the fact is correct, the framing is slightly self-referential.; Turn 5 (minor): register toward the user switches to formal «Хотите», while turn 3 in another session addresses the same user informally — inconsistent assistant persona across the product.
- archive_research: Turn 1 (moderate): the acknowledgment exposes a raw job UUID plus /status and /cancel commands — a working operator control, but machine-style for an ordinary user, with no plain-language statement of what happens next or when.; Turn 2 (moderate): coverage framing is incomplete — the result does not state that these are the items the archive query returned, and the measurement status of normalize_email is left unstated rather than explicitly marked unknown; the user cannot distinguish «measured» from «no data».; Turn 2 (minor): the completed result is delivered as stored_result (real research worker, synthetic sources) while every other turn in the record goes through a synthetic Telegram send; this record shows no sent receipt for the result, so the user-facing channel for research completion is unverified.
- weekly_brief: Chat message (moderate): the headline item asserts findings from two sources but links only https://t.me/source/1001; the slugify finding from /1002 is uncited at chat level (it is cited only in the full artifact).; Chat message (moderate): «✓ Проверено 1 из 1 источников» conflicts with the three sources actually used and cited in the artifact (1001–1003); the count apparently refers to the single archive resource, but as worded it misstates source coverage to the user.; Artifact (minor): rendering blemishes — stray escape sequences ('\(' and '\_'), each timeline entry duplicating its source text, and internal version/identity hashes (brief_0843d7f061ce6993202c015f, sha256) exposed in the readable brief.; Artifact (minor): «Статус покрытия: complete» is stated without spelling out that completeness holds only within the bounded local archive selection (limitation listed elsewhere as bounded_local_archive_selection).
- watch: Turn 5 (moderate): the pause acknowledgment «Состояние подписки сохранено» does not state the resulting state or effect — the user cannot tell paused from active, nor what stops (collection and sends) or how to resume; the evidence (new_job_after_pause false) shows the pause worked, but the reply never says so.; Turns 3–5 (moderate, usability/continuity): the user addresses /watchstatus and /watchpause by watch_89bebc89033244c897a640d6fa073f04, an identifier the assistant never surfaced in any prior turn; in a real conversation the user would have nothing to reference.; Whole flow (moderate, usability): hash-token commands with terse machine replies — a functional operator control, not natural conversation; no plain-language summary of what the subscription will do is ever given.; Turn 3 (minor): «Последний результат: .» renders an empty value with a stray dot — a machine artifact in user-visible text.; Turn 4 (minor): «Последний результат: active» is vague — it restates the subscription state instead of describing the last collection outcome; the user learns nothing about what changed or whether a notification was produced.
- confirmed_action: Turn 4 (moderate): the reply to the repeated /actconfirm does not explain idempotency — the user cannot tell whether a second email was sent; the provider ref label «synthetic_sent_2» may even suggest a second provider object, while the case evidence shows exactly one write (synthetic_graph_write_count 1).; Turn 3 (moderate): the reconcile outcome provides no provider message ID or verifiable detail — just «succeeded»; the user receives nothing concrete to check against the provider.; Turns 3 (moderate, usability/continuity): the user invokes /actreconcile with action_04b919a0541885064d40f73effdcac8ecc060c55, an internal action ID the assistant never displayed in any prior turn.; Turns 2 and 4 (minor): machine-style mixed-language statuses with an empty trailing value («Исход действия: unknown. Provider ref: ») — terse and unnatural for an ordinary user; the empty ref is honest but rendered as a dangling label.; Turn 1 (minor): the /actconfirm affordance is a long hash token with no plain-language statement of what confirming will do; also the preview is a raw JSON echo including the internal account_ref.

## Визуальная оценка

Офлайн Chromium: desktop1280/light и mobile390/light/dark; ошибок страницы и горизонтального переполнения нет. PDF проверен растром и расположением текста,4 страницы,0 текстовых фрагментов за листом; длинная карточка продолжается на следующем листе. Фиксированный вариант с потерей нижней цитаты сохранён как неудачное доказательство.

DeepSeek V4 Flash Vision Exp реально оценил6 изображений (4 страницы PDF + 2 мобильных вида), 21.834s, usage `{'prompt_tokens': 5068, 'completion_tokens': 4462, 'total_tokens': 9530, 'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 5068, 'prompt_tokens_details': {'cached_tokens': 0}, 'completion_tokens_details': {'reasoning_tokens': 2944}}`. `warn`: pdf_legibility=4/5, pdf_pagination=3/5, source_visibility=4/5, mobile_layout=3/5, dark_theme=4/5, visual_hierarchy=4/5.

Открытые замечания: мелкие графики на телефоне, агрессивные переносы таблицы покрытия, длинная строка периода в колонтитуле, повторы заголовка и текста источника, лишняя пустота между секциями. Это сохранённые результаты оценщика, не автоматическое подтверждение точности каждого визуального замечания.

## Независимая проверка исправлений

Первичная независимая проверка112: GLM5.3/max,481.525s,usage48116/26566/74682, **STOP/P1** на cbab0fb. Найдено отсутствие связей от исходного ответа/основного результата к диагностическим частям. Новый тест воспроизвёл сбой (1 failed/7.63s). Исправление6467c50 добавляет связи и проверки существования источников/tombstone под общим lock; удаление ответа и основного результата проверено (2 passed/10.85s). Текущие Chat/memory/ingress проверки:67 passed/210.53s.

Независимая повторная проверка113 была действительно запущена на6467c50, но завершилась HTTPError за0.577s, без отчёта/usage; точный HTTP status не сохранён и не выдуман. **P1 исправлен и проверен локально; независимое закрытие пока не получено.** В повторном живом Chat все5 модельных запросов получили настоящий HTTP429. После этого новые обращения остановлены: причина/срок восстановления лимита не установлены, другой провайдер или модель не подставлялись.

Функциональное сокращение отдельно проверено без новой платной генерации: native worker получил точный ранее наблюдённый ответ MiMo и вернул «**Посмотри структуру проекта и найди первую «чистую» функцию для теста.**» вместо фразы про экспирацию. Это replay существующего синтетического ответа, не новая независимая LLM-оценка. Отступы Python сохраняются в тексте ответа и сохранённом видимом объекте; регрессии проверяют оба пути.

## Артефакты и продолжение

- [Проверяемый Brief HTML](../../.playbook-artifacts/pai-product-verification-20261009/corrected-brief/product-brief.html)
- [PDF](../../.playbook-artifacts/pai-product-verification-20261009/corrected-brief/product-brief.pdf)
- [Markdown](../../.playbook-artifacts/pai-product-verification-20261009/corrected-brief/product-brief.md)
- [Машиночитаемое доказательство](PAI-product-verification-20261009.json)

GCN использован read-only: SHA83f0701 + фактически прочитанные dirty hashes в PAI-GCN-reuse-20261009.json. Перенесены идеи компактных исходных пользовательских ходов, приоритета новой темы, раздельных history scopes и оценки целого диалога. Продвижение состояния только после Telegram receipt остаётся референсной идеей; в этой правке оно не внедрено. Содержимое грузинских документов, аккаунтов и секретов не переносилось.

UTD API отсутствует и по указанию владельца отложен. Для настоящих почты/календаря пока не выбран тестовый аккаунт; текущий результат — фикстуры. Brave discovery требует отдельно выбранного ключа. Формальное принятие дизайна/ролей, будущие slices, человеческая полезность и production остаются отдельными незакрытыми слоями. Ни master, ни production DB, ни .env, ни службы/таймеры не менялись; push не выполнен.110/111 относятся к прежнему cb7020f;110 не подменяет аудит изменённого tools/test_tiers.py.

Следующий шаг после восстановления Go — один свежий независимый P1 recheck114, без перезаписи неудачного113. Подготовленная команда: `PYTHONPATH=src .venv-pai/bin/python .playbook-artifacts/pai-product-verification-20261009/recheck_after_provider_recovery.py`. Не запускать её вслепую при текущем429 и не возобновлять старый full-design batch. Затем — UX Watch/Act, мобильные графики/таблица и явное покрытие Brief из фактических замечаний.

Изменённые файлы кандидата:

- `docs/CODEX_PROMPT.md`
- `docs/adr/ADR-016-pa-product-verification.md`
- `docs/design/PAI.design.json`
- `docs/design/PAI.md`
- `docs/design/PAI.requirements.json`
- `docs/tasks.md`
- `docs/verification/PAI-GCN-reuse-20261009.json`
- `docs/verification/PAI-next-review-packets.json`
- `docs/verification/PAI-progress.md`
- `docs/verification/PAI-review-continuation-110.json`
- `docs/verification/PAI-review-continuation-111.json`
- `docs/verification/PAI-tooling-110-accepted.md`
- `src/prm/application.py`
- `src/prm/conversation.py`
- `src/prm/report_exports.py`
- `src/prm/routing.py`
- `src/prm/runtime/brief.py`
- `src/prm/runtime/composition.py`
- `src/prm/runtime/ingress.py`
- `src/prm/runtime/model.py`
- `src/prm/runtime/result_payloads.py`
- `src/prm/storage/conversations.py`
- `src/prm/storage/policy.py`
- `src/prm/storage/postgres.py`
- `tests/test_pai_product_sessions.py`
- `tools/test_tiers.py`
