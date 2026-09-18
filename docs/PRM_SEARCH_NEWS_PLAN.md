# Задания реализации и границы deep review

Зарегистрировано по поручению владельца 17.09.2026. Карточки находятся в `docs/tasks.md`; все новые implementation-задачи и инженерные reviews имеют статус planned. Регистрация не означает начало реализации или выполненный review. Проверенный baseline кода: `cee8baae3b8a41f571bd689f2dadf7e6e981863f`.

[Диагноз и критерии качества](PRM_SEARCH_NEWS_EVAL.md) · [handoff](CODEX_PROMPT.md) · [подробная первая задача PRM-SN-1A](#prm-sn-1a-подробная-спецификация) · [протокол Terra/high](PRM_SEARCH_NEWS_DEEP_REVIEW.md).

## Как передавать следующему агенту

Штатный промпт docs/prompts/prm_search_news_implementer.md назначает **один goal на всю локальную реализацию**: 12 задач, пять фазовых engineering reviews, исправления, интеграционная проверка и готовый pilot packet. Карточки задают последовательные ограниченные шаги внутри goal. После пройденного инженерного gate агент самостоятельно продолжает следующую фазу, без нового разрешения на каждую карточку. Публикация, production и live-действия в goal не входят.

ID PRM-SN-1A и PRM-SN-DR-1 относятся к новой очереди в docs/tasks.md. Старые RFX/UTD/PRM статусы и approval receipts не изменены. Отдельная узкая задача по-прежнему ограничена своим scope, но штатный launch prompt явно назначает всю PRM-SN локальную очередь. Само наличие planned-карточек не запускает goal.

Общие границы всех карточек:

- Перепроверить HEAD и applicable AGENTS/REVIEW_POLICY; читать активный путь и нужные contracts, не всю историю. Работать в изолированной ветке/копии; не трогать чужие untracked-файлы.
- Исходные данные — synthetic/public sanitised fixtures; пустое окружение, fake search/model/Telegram. До исполнения проверить side effects. Production DB, `.env`, profiles, subscriptions, timers и services не менять.
- Не запускать provider jobs, ingestion, backfill, внешние embeddings или реальную рассылку. Exec reviewer — отдельный явно включённый в поручение вызов с public code/synthetic evidence; он не получает частный архив.
- Commit/push/merge — только при явном поручении. Запуск по штатному implementer prompt разрешает документацию/evidence и честный статус назначенной задачи; не даёт права объявлять human approval или менять чужие задачи. Fixtures и готовый diff не равны production-ready.
- Для каждой карточки: до/после UX, сфокусированные tests, точные результаты, границы доказательств и rollback. Новые tests проверяют пользовательское поведение/отказы, а не повторяют реализацию.

## Порядок и обязательные ворота

```text
PRM-SN-1A → PRM-SN-1B → PRM-SN-1C → PRM-SN-DR-1
                           ↓
PRM-SN-2A → PRM-SN-2B → PRM-SN-2C → PRM-SN-DR-2
                           ↓
PRM-SN-3A → PRM-SN-3B         → PRM-SN-DR-3
                           ↓
PRM-SN-4A → PRM-SN-4B         → PRM-SN-DR-4
                           ↓
PRM-SN-5A → PRM-SN-5B         → PRM-SN-DR-5
                           ↓
             отдельное разрешение ручного пилота
                           ↓
             реальные evidence → PRM-SN-DR-PILOT
                           ↓
             отдельное разрешение rollout
```

Это базовая последовательность по зависимостям; повторное полное review после каждой мелкой правки не требуется. Immediate review по новой опасной границе проводится **раньше очередных ворот** — см. ниже. В штатном end-to-end goal инженерный PASS открывает зависимую локальную фазу без повторного разрешения. Непройденный обязательный gate нельзя обойти. Для отдельно назначенной узкой задачи её scope остаётся ограниченным.

| Gate | После / до | Обязательный фокус | Что блокирует переход |
|---|---|---|---|
| PRM-SN-DR-1 | PRM-SN-1C / P2 | Реальный final text, claim→evidence→citation, числа/даты/отрицания/субъект, полезный fallback, mixed dispatch, отсутствие лишнего проекта | Критический неподдержанный факт; ложный citation pass; незаметная неполнота проверки; ухудшение answerable cases; crash |
| PRM-SN-DR-2 | PRM-SN-2C / P3 | Тема и фильтры, временные окна, TTL/restart, точный save preview, stale/repeated callbacks, свежесть и ошибки архива | Сохранение не того пункта/без confirm; загрязнение темы; ложная свежесть; скрытый refresh failure |
| PRM-SN-DR-3 | PRM-SN-3B / P4 | Public-search vs private-context consent, candidate→primary source, redirects/SSRF/injection, provenance, расходы и partial answer | Egress/scope bypass; snippet выдан за проверку; бесконтрольный budget; нет полезной части при outage |
| PRM-SN-DR-4 | PRM-SN-4B / P5 | Полезный выпуск до подписки, event identity, repost dates, corrections, significance как анализ, рубрики/Telegram renderer | Дубли/старая новость как новая; фиктивная свежесть; filler; бессодержательный выпуск; draft создаёт jobs |
| PRM-SN-DR-5 | PRM-SN-5B / ручной live-пилот | Точный subscription effect, outbox/quota/lease, retries/unknown, pause/mute/unsubscribe, quiet hours, kill switch, rollback | Гонки, потерянные pending, неоднозначный send как success, неожиданные уведомления, непроверенный rollback |
| PRM-SN-DR-PILOT | Реальный согласованный пилот / расширение | Owner usefulness, source coverage, шум, измеренные latency/стоимость, реальные receipts, все исправления с прошлых gates | Нет реальных данных; открытые критические findings; бюджет/уведомления не соблюдаются; недостаточно human evidence |

PRM-SN-DR-1…PRM-SN-DR-5 — инженерные ворота. Неизмеренная пользовательская полезность/закрытый human holdout должны оставаться явным ограничением и могут блокировать продуктовый допуск; reviewer не объявляет их пройденными на основании dev fixtures. Если независимых labels пока нет, допускается отдельно ограниченный engineering verdict, но не общий quality/release PASS.

## Фаза 1. Надёжный и понятный первый ответ

### PRM-SN-1A — Финальные цитаты и полнота проверки

**Задача:** исполнить [готовую подробную спецификацию](#prm-sn-1a-подробная-спецификация). Модули: `claim_ledger`, `synthesis`, `application` и необходимые tests. Зависимости: новый task scope, текущий SHA. Результат: чужая/отсутствующая ссылка не получает ложный precision=1; неполнота проверки видна и приводит к полезному fallback. Семантические искажения не считать исправленными этим slice. Откат: source-attributed fallback, без возвращения ложного verification pass.

### PRM-SN-1B — Поддержка ключевых фактов до публикации

**Задача:** после PRM-SN-1A отделить факты источника от inference/recommendation; закрыть доказанные мутации числа, даты, единицы, отрицания, субъекта и цитаты. Модули: те же ledger/synthesis/application, context/evidence DTO только по необходимости.

**Ожидается:** связь с конкретным evidence span/version; честный `supported/contradicted/insufficient`; overlap не используется как semantic truth. Выбор проверяющего механизма обосновать на парных dev случаях. Если свободную перефразу нельзя надёжно проверить локально, давать атрибутированный excerpt и ограниченный анализ; не притворяться, что regex решает произвольную семантику. Новую модель/verifier не подключать без отдельного provider scope.

**Приёмка:** все critical mutations аудита не публикуются как факты; парные правильные ответы/перефразы сохраняют полезный результат; отчёт о false accepts/false refusals с знаменателями; финальный текст/fallback проверены, 11-й claim не исчезает. Ограничения вынесены в результат. Откат: проверенный excerpt fallback. Один лишь новый threshold задачу не закрывает.

### PRM-SN-1C — Прямой ответ и mixed partial без падения

**Задача:** компактный первый ответ; исправить status/gate/actions mismatch в mixed query. Модули: `prm/application.py`, текущий renderer/answer contract, `bot/prm_handlers.py`.

**Приёмка:** архивный «agent evals… применимо сейчас» отвечает по архиву; без неявного проекта и web. Mixed archive+current при недоступном web сохраняет полезную архивную часть, не выдаёт старое за текущее и не падает на `action_codes=None`. Один ясный ответ, источники рядом, детали по запросу. Проверить настоящий application→dispatch с fake sender, существующие archive tests и 5–8 before/after outputs. Откат: предыдущий безопасный renderer с сохранённым crash fix.

**Завершение фазы:** PRM-SN-DR-1 на совокупном diff PRM-SN-1A…C и benchmark-сегменте; semantic gap нельзя закрыть косметической правкой.

## Фаза 2. Продолжение, сохранение, свежесть

### PRM-SN-2A — Тема, фильтры и период как состояние

**Задача:** типизированный volatile context с answer/item IDs; новая тема сбрасывает старые фильтры, follow-up меняет конкретный параметр. Модули: `prm_handlers`, `memory_research` time-window, minimal DTO.

**Приёмка:** A→B→«подробнее» остаётся B; «только прямые» и «за неделю» реально применяются; UTC/DST/пустое окно проверены. TTL/restart честно теряют контекст, без скрытой постоянной памяти. Откат: простой volatile режим с явным повторным уточнением.

### PRM-SN-2B — Подтвердить именно выбранный пункт

**Задача:** «сохрани второй» разрешается по answer/item IDs; preview показывает точное содержимое, источники и эффект. Модули: post-answer actions/callbacks, `pi_memory` только при необходимости.

**Приёмка:** cancel без canonical write; confirm один объект; repeated/cross-chat/expired/old-version callbacks безопасны. «Сохранить тему» не обещает работающий мониторинг. Технические drafts/receipts и их retention явно описаны. Откат не удаляет существующую память. **Immediate review confirmation/write semantics** до зависимой работы, если эта граница меняется.

### PRM-SN-2C — Понятное здоровье архива

**Задача:** показать last success/attempt/error и покрытие/index freshness без запуска refresh. Модули: refresh receipt, status renderer/handlers, существующий refresh CLI receipt contract; tests с fake результатами.

**Приёмка:** partial/error отличимы от «нового нет»; дата архива не заменяется временем запуска status; stale index виден. Никакого live refresh, реального timer или production write. Если нужен новый receipt store, только disposable schema и immediate review, rollout отдельно. Откат: прежний статус с честным «свежесть неизвестна».

**Завершение фазы:** PRM-SN-DR-2; receipt «service running» не заменяет проверку данных.

## Фаза 3. Контролируемая внешняя проверка

### PRM-SN-3A — План запроса и разрешения

**Задача:** небольшой RequestPlan с независимыми archive/public-search/private-context scopes, бюджетом и составными подзадачами; согласие на ограниченный режим без подтверждения каждого безопасного публичного запроса. Модули: routing/application, existing privacy/verification contracts.

**Приёмка:** архивное «сейчас» не открывает web; current price не закрывается архивом; приватные сущности не попадают в search query; отрицательные flags действительно блокируют вызов. Согласие на режим показано как preview и тестируется только на fixtures. **Immediate review egress/consent boundary** перед PRM-SN-3B. Откат: локальный режим.

### PRM-SN-3B — Candidate → первоисточник → ответ

**Задача:** discovery adapter и existing primary-source reader соединить с evidence provenance/claim gate. Модули: primary_source_verification, adapter, application/evidence. Providers mock; actual model/API/cost выбор проверить отдельно перед live.

**Приёмка:** достаточен один авторитетный источник; snippet не является proof; даты/URL/edition и source family сохранены; conflict/404/timeout/unsafe redirect/injection/budget cutoff дают правильный partial. Query builder не передаёт архив наружу. Есть fake usage receipts и расчёт, не фиктивные реальные расходы. Откат: capability off, кеш не выдаётся за текущую проверку.

**Завершение фазы:** PRM-SN-DR-3. Live external mode остаётся выключенным до отдельного разрешения.

## Фаза 4. Дайджест по запросу

### PRM-SN-4A — Темы и версии событий

**Задача:** общий TopicSpec/EditionRequest и event identity/version, адаптация разрешённых UTD source adapters как частного случая. Модули: external_watch adapters/store/selection, минимальные общие DTO.

**Приёмка:** различаются публикация/событие/обновление/fetch/check; перепечатки объединены по origin, косметический diff не новая новость, исчезновение из окна не отмена, существенное исправление сохраняет предыдущую версию. General topic не включает collector автоматически. Derived schema/retention — immediate review, без production migration. Откат: старые UTD adapters доступны, новые editions отключены.

### PRM-SN-4B — Полезный выпуск до подписки

**Задача:** редакционный selection/ranking, рубрики и компактный final renderer с «что/почему/источник/изменение». Модули: application, watch selection, renderer; только чистые legacy helpers.

**Приёмка:** несколько рубрик, один event не дублируется, old repost не новый, importance явно анализ, нет filler. «Нет новостей» отличается от source failure. Plain text/Telegram limit проверены fake transport; кнопки не обещают несуществующий UI. До подписки доступен useful draft в разрешённом source scope; никаких scheduled jobs. Откат: edition feature off.

**Завершение фазы:** PRM-SN-DR-4 с полными примерами выпуска и quality counters, не только JSON schema.

## Фаза 5. Подписка и доставка

### PRM-SN-5A — Outbox, повторы и неоднозначные sends

**Задача:** source change и pending delivery транзакционно связаны; reservation/lease/quota и состояния unknown/deferred; existing receipts сохранены совместимо. Модули: external_watch store/live/delivery; fake Telegram.

**Приёмка:** timeout до/после принятия, race двух workers, crash/restart, partial chunks, daily cap, retry/backoff не теряют pending и не дают локального double-send. Unknown не считается успехом и не повторяется вслепую. Не обещать exactly-once. **Immediate review schema/write/delivery semantics** перед PRM-SN-5B. Откат: sender off, outbox сохранён без автоматического replay.

### PRM-SN-5B — Честная подписка и готовность ограниченного пилота

**Задача:** general Subscription с точным preview, scope, sources, language/depth/period, timezone/schedule, caps, quiet hours, expiry, pause/mute/unsubscribe; UTD использует тот же контракт. Модули: profile/schema/callbacks/live/delivery, templates только в scope поручения.

**Приёмка:** confirm описывает реальный эффект; при выключенном runtime — «ожидает включения», не «завтра доставлю». До confirm нет poll/send; отмена/expiry блокируют pending; kill switch проверяется перед collection/send по выбранной политике. Проверены DST и переходы состояний. Собран конкретный pilot packet: SHA, источники, действия, бюджет, срок, metrics, rollback. Никакого live запуска. Откат: subscriptions paused/cancelled, совместимые receipts, явное разрешение на любые реальные миграции.

**Завершение фазы:** PRM-SN-DR-5, затем владелец решает о конкретном пилоте. После пилота — PRM-SN-DR-PILOT, прежде чем расширять источники/лимиты/автономию.

## Immediate reviews вне очереди

В соответствии с текущей [REVIEW_POLICY](https://github.com/ashishki/telegram-research-agent/blob/cee8baae3b8a41f571bd689f2dadf7e6e981863f/docs/REVIEW_POLICY.md): новая или изменённая граница permanent writes/confirmation, schema/retention, provider/private egress, source allowlist/SSRF, live verification, расписание/notifications/caps, trust, backup/restore, release/dogfood или compatibility removal требует адресного deep review до продолжения через эту границу. Fixture-only реализация не отменяет проверку семантики опасной границы; она лишь не требует запускать production.

Immediate review не означает полный повтор аудита всего проекта. Проверяется конкретный diff и затронутые контракты; результат включается в ближайший фазовый review. Новая правка после review проверяется по изменившемуся риску, без повторения всех не затронутых tests.

Если текущий UTD runtime отдельно подтвердится как активный, PRM-SN-5A и исправление misleading confirmation выделить раньше расширения доставки. Сами runtime-наблюдение и любые изменения сервиса должны быть в отдельном разрешённом scope.


## PRM-SN-1A: подробная спецификация

## Результат для пользователя

Ответ со ссылкой, не относящейся к использованному доказательству, не должен проходить проверку как корректно процитированный. Если финальный текст нельзя полностью проверить в установленном лимите, бот отдаёт полезный ответ из разрешённых фрагментов с их настоящими источниками. Он не объявляет такую проверку пройденной из-за нуля извлечённых claims.

## Отправная точка

Проверенный SHA `cee8baae3b8a41f571bd689f2dadf7e6e981863f`. Прочитать актуальные AGENTS и diff от этого SHA, затем только затронутые contracts. [Диагноз и зафиксированные результаты](audit/PRM_SEARCH_NEWS_BASELINE_2026-09-17.md), [synthetic probe receipt](../evals/prm_search_news/audit_baseline_2026-09-17.json).

Сейчас `claim_ledger` удаляет URL из финального текста и может автоматически присоединить похожий source_ref. `citation_precision=1.0` не подтверждает видимую ссылку. Claims короче четырёх токенов и сверх лимита могут исчезнуть; synthesis получает ложный успех. Application сохраняет final verification как метрику.

## Узкий scope

1. Сохранить явные citations финального ответа и их связь с текстом. Сопоставлять только с выбранными evidence IDs/версией; не заменять чужой/отсутствующий URL автоматически подобранным ref. Не нормализовать разные документы в один без обоснованного canonical mapping.
2. Развести диагностики: формат URL, принадлежность evidence, полнота проверки и семантическая поддержка. Lexical overlap можно оставить внутренней диагностикой, но не называть его доказанным entailment или precision видимых цитат. При изменении названия/семантики версионировать метрику, не переписывать старые eval reports.
3. Сделать пропущенные factual fragments/truncation/пустое извлечение явным `incomplete`, а не pass. Не требовать цитаты у приветствия, короткой границы возможностей или явно маркированной рекомендации; короткий факт с числом нельзя исключать по длине.
4. Перед возвратом synthesis применять решение по **структурной цитатной целостности и полноте**, а не только писать метрику. При fail/incomplete использовать существующий полезный source-attributed fallback: краткий разрешённый фрагмент/найденная часть с корректным URL, без неподдержанного продолжения. Не заменять каждый ответ общим отказом. Проверять и финальный fallback, чтобы renderer не вставлял другую ссылку.

Предпочтительные файлы: `src/assistant/claim_ledger.py`, `src/prm/synthesis.py`, `src/prm/application.py`; минимальное изменение renderer допустимо только для соблюдения этого контракта. Tests — существующие claim/synthesis/application tests плюс небольшая fixture. Без нового framework, embeddings, provider, scheduler, schema и изменения `.env`.

## Критерии приёмки

- Fake synthesis с верным содержанием и чужим URL не получает citation-integrity pass и не публикуется в таком виде; отсутствие ссылки не получает искусственный precision=1.
- URL на другой выбранный документ, который не является указанным evidence данного claim, не считается корректной связью. Несколько явно связанных evidence допускаются.
- Короткий factual текст и непроверенный остаток после лимита дают incomplete/fallback; длинный безопасный ответ можно проверить целиком в ограниченном бюджете или сократить явно, не молча пропустить хвост.
- Правильный source-attributed ответ проходит; boundary/приветствие/явная рекомендация не превращаются в ложный factual failure. Парные положительные сценарии обязательны.
- Fallback содержит полезную найденную часть и настоящие источники, не нарушает archive-only «сейчас», не придумывает текущие факты. Tests сравнивают фактически возвращаемый текст, а не только payload.metrics.
- На маленьком dev replay число answerable сценариев с полезным результатом не уменьшается относительно записанного до изменения baseline; приложить тексты before/after для 5–8 случаев. Это инженерная проверка, не independent human gold.
- Focused существующие claim/synthesis/application/intent tests проходят; новая проверка ловит прежний wrong-ref counterexample. Известные num/negation/actor контрпримеры с корректным URL фиксируются отдельно и **не объявляются решёнными** этим slice.

## Ограничение результата

Цитатная принадлежность не доказывает истинность утверждения. Этот slice не вводит универсальный semantic verifier и не даёт разрешения на production synthesis rollout. Завершение этапа 1 из roadmap дополнительно требует проверки дат/чисел/отрицаний/субъекта и независимого holdout с контролем ложных отказов. Не «исправлять» задачу только снижением `unsupported_claim_rate` threshold.


Стоимость/сложность фаз — ориентировочно 4–7, 3–5, 4–7, 4–7 и 4–7 инженерных дней соответственно, без ожидания human/live evidence. Это гипотезы, не SLA. Никакие provider jobs для этих оценок не запускались. Полезность, расходы и latency проверяются по docs/PRM_SEARCH_NEWS_EVAL.md. Не добавлять сейчас vector DB, второго бота, SaaS, массовый backfill или legacy cleanup.
