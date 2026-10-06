# Аудит

Стратегия следующего этапа Personal AI Assistant, 6 октября 2026 года.
Основание: [задание](prompts/astra6_strategy.md), выборочное чтение реализации,
полная [целевая спецификация](PERSONAL_ASSISTANT_SPEC.md), локальные проверки
и официальная документация технологий. Рассмотренный код:
`8faee4232cb30e6b6f39cfbd974c151846f79da6`, ветка
`docs/personal-assistant-blueprint-playbook-20260918`, Python 3.10.12.

**Рекомендация: сохранить модульный монолит, завершить устойчивое состояние и
подключение пользовательских сценариев, выделить durable worker. Для нескольких
исполнителей выбрать PostgreSQL как общее хранилище состояния и заданий. Redis
добавлять при доказанной потребности в общем кэше или отдельном брокере.**

Это законченная стратегическая записка, предложенная владельцу для выбора фазы.
Она не изменяет утверждённые решения, PA-реестр, полномочия или статус приёмки.
Полная цель сохраняется: Chat, Search, Brief, Watch, Act, личные источники,
память, мультимодальность и эксплуатация. Объём production-нагрузки, фактический
развёрнутый SHA и состояние сервисов в этой работе не проверялись.

## Что существует на рассматриваемом SHA

Под «активным» ниже понимается путь вызовов в коде, а не наблюдавшийся production.

| Область | Реализованная механика | Фактическая граница |
| --- | --- | --- |
| Вход Telegram | `src/prm/cli.py` → `bot.run_bot` → `prm_handlers` → `PersonalResearchAssistant`; приватная идентичность, callbacks, архивные ответы | Polling обрабатывает запросы последовательно. CLI вызывает `run_bot` без поставщиков разрешений для моделей. Работа запущенного бота не проверялась. |
| Chat / архивный синтез | В приложении есть ветка модельного ответа и отдельный транспорт синтеза ограниченного контекста | Без typed access Chat возвращает `provider_egress_required`. Наличие ключа не включает AI. Реальный synthesis требует разрешений, флагов и подключения к входному пути. |
| Web / GitHub | Контракты ограниченного public search/fetch и чтения контекста проекта; независимые разрешения | В конструкторе приложения провайдеры по умолчанию `None`; обычный Telegram factory их не внедряет. Это не готовый AI Search в интернете. |
| Deep research | План, ограниченные шаги, отмена/дедлайн, временные дочерние процессы Linux/fork | `research_worker.py` прямо исключает очередь, daemon и persistence. Завершение процесса приложения не оставляет возобновляемую задачу. |
| Brief / представления | `BriefDocument`, версии, редакционные истории, Telegram/Markdown/HTML/PDF, проверка содержимого | `BriefDocumentStore` сохраняет версии при наличии соответствующей таблицы выбранной БД; видимые привязки разговора остаются в процессе. Нет доказательства опубликованного приватного веб-сервиса или принятого владельцем качества всех представлений. |
| Watch PA-09 | Explicit-path SQLite: подписки, подтверждения, задания, lease, dedup, квоты, попытки, квитанции, reconciliation, тихие часы/DST | `WatchJobStore.run_once` принимает callbacks. Нет подключённого scheduler, сборщика источников или Telegram sender. Это durable локальный контракт. |
| Старый UTD watch | Отдельный ограниченный collector/store/selection/delivery в `src/external_watch/` | Не универсальный PA Watch; его прежнее согласие не распространяется на почту/Canvas. Текущее включение таймеров неизвестно. |
| Mail / calendar / contacts / Academic | Профили, scope/consent, нормализованные объекты и guards; SQLite-хранилище производных почтовых сводок | Нет завершённых OAuth/token/sync адаптеров и подключения этих контрактов к основной беседе. Microsoft Graph выбран как первый почтовый путь, но аккаунт не подключён этим кодом. |
| Confirmed Act PA-13 | Точное подтверждение версии/содержимого, одно использование, атомарный claim, состояния результата и reconciliation | `ActionReceiptStore` — словарь с `threading.Lock`. Защита в одном процессе не сохраняется после рестарта и не координирует разные процессы. Реального executor нет. |
| Memory / media | Локальная inspectable memory; контракты типов, размеров, OCR и cleanup; отдельный существующий голосовой путь | Модули PA-14/15 не доказывают сквозную интеграцию с ботом и реальное выполнение cleanup/OCR/vision. |
| Cost / operations | Каталог/тарифы/выбор маршрута, расчёт стоимости, DTO кэша; health/failure/recovery/rehearsal contracts | `CacheEntry` не является работающим кэшем; `build_migration_rehearsal` возвращает план, а не выполняет backup/restore. Нет измеренного рабочего model router или операционного контура. |

Ключевые места для проверки: [приложение](../src/prm/application.py),
[вход Telegram](../src/bot/prm_handlers.py), [polling](../src/bot/bot.py),
[временный research worker](../src/prm/research_worker.py),
[Watch](../src/prm/watch_jobs.py), [Act](../src/prm/confirmed_actions.py),
[operations](../src/prm/operations.py), [cost](../src/prm/model_cost.py).

## Что правильно заложено и должно сохраниться

- PA-02 разделяет `answer.request`, `answer.context`, `answer.delivery`,
  `watch.collection`, `watch.delivery`, `mail.read`, `calendar.read`,
  `contacts.read`, `academic.read`, `action.execute` и media purposes.
  Фоновое чтение, чтение по запросу, передача модели и отправка не подменяют друг
  друга. Это особенно важно после появления очереди.
- `CapabilityRegistry` проверяет owner/resource/operation/data/provider,
  ревизию, срок, отзыв и одноразовое резервирование перед транспортом.
  Парный доступ к пользовательскому тексту и архивному контексту не становится
  одним широким «LLM разрешён».
- PA-ответы Telegram сходятся в общий проверяемый final-send boundary.
  Совместимые dispatch-фасады уже имеют безопасный default; явно выбранный
  legacy остаётся отдельной поверхностью. Общий контракт политики нужно
  распространять на будущие адаптеры, сохраняя специализированные transports.
- Watch различает попытку, квитанцию и неизвестный исход; повтор информации
  не равен новому событию. Идентичность источников и версии BriefDocument
  позволяют перестраивать производные представления.
- Канонический Telegram-архив отделён от производных данных личных источников.
  У модульного монолита уже есть полезные предметные границы.

Основание: [capabilities](../src/prm/capabilities.py),
[archive transport](../src/prm/archive_synthesis_transport.py),
[briefs](../src/prm/briefs.py), [boundaries](ASSISTANT_BOUNDARIES.md).

## Что препятствует росту

1. **Авторитетное состояние пока неоднородно.** Grants, счётчики резервирования
   и operation groups в `CapabilityRegistry`, `ConversationStore` и PA-13
   receipts находятся в памяти. Несколько процессов получат разные бюджеты,
   сведения об отзыве и результаты действий. Это ограничение корректности,
   ещё до вопроса производительности.
2. **PA-09 держит `BEGIN IMMEDIATE` во время `sender(...)`.** Это осознанная
   защита порядка pause/revision/send, подтверждаемая специальными тестами.
   Медленная отправка удерживает блокировку записи всей SQLite-БД sidecar.
   Простое перенесение callback за commit разрушит существующую гарантию.
3. **У durable Watch нет общего исполнения.** Нет heartbeat-протокола общего
   worker, диспетчера расписаний, устойчивого intake, сквозного cancellation и
   очереди исследований/рендера. Истёкшие Watch leases сейчас консервативно
   становятся `unknown`; такую политику нельзя механически копировать на
   безопасно повторяемый рендер.
4. **Контракты опережают пользовательские пути.** Добавление ещё одной БД не
   подключит Chat/Search/почту и не обеспечит хороший недельный обзор.
   Следующие изменения должны замыкать сценарии от входа до результата.
5. **Документы смешивают целевое, локально проверенное и принятое.** README и
   handoff содержат новые результаты рядом со старыми ограничениями.
   Структурная согласованность плана не означает разрешение на исполнение.

## Выполненные проверки

| Команда | Результат |
| --- | --- |
| `python3 tools/playbook.py --check-pin` | Exit 0; pin `d570163ab17ec3b4245187c778f1e8d89af9690f` подтверждён. |
| `python3 tools/check_personal_assistant_plan.py` | Exit 0; 19 согласованных срезов; `review_required`. |
| `python3 tools/playbook.py playbook_validate --root . --check tasks --check references` | Exit 1; **19 `TASK_DESIGN_APPROVAL_REQUIRED`**, по PA-00…PA-18. Ошибки сохранены, approval не подменялся. |
| Команда pytest ниже | Exit 0; **135 passed in 45.18s**. Включён прежний `test_product_ux_keeps_project_context_for_confirmation_followups`. |

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_assistant_permissions.py tests/test_assistant_egress.py tests/test_assistant_jobs.py tests/test_assistant_subscriptions.py tests/test_assistant_actions.py tests/test_assistant_cost.py tests/test_assistant_ops.py tests/test_prm_product_ux_eval.py tests/test_playbook_bridge.py
```

Это адресные существующие проверки аудируемой механики, а не полный
`focused-prm`, CI, нагрузочный тест или live-интеграция. Код не менялся, новые
тесты не добавлялись. Исторические 576/150 из handoff здесь заново не проверены.
Независимый review этой стратегии и текущего SHA не запускался; существующий
[Mimo review](verification/PA-deep-review-1e83cdc-mimo.md) относится к `1e83cdc`
и описывает последующие исправления, что не равно свежему recheck `8faee42`.

# Стратегия масштабирования

## Когда нужны worker, PostgreSQL и отдельные сервисы

Отдельный процесс worker совместим с модульным монолитом: тот же пакет,
use cases, схемы и релиз, другой жизненный цикл исполнения. Потребность в
durable worker уже следует из требований к перезапуску, отмене, Watch и Brief.
Она не зависит от числа пользователей. Потребность в микросервисах пока не
подтверждена.

| Наблюдаемый сигнал / требование | Следующий шаг | Что измерять |
| --- | --- | --- |
| Долгая задача должна продолжиться после рестарта; polling ждёт research/PDF | Durable job + отдельный worker; быстрый приём и видимый статус | Время приёма, queue wait, completion time, восстановление/отмена |
| Нужны несколько исполнителей с общими grants/budgets/receipts | Durable authority store; PostgreSQL — рекомендуемый целевой backend | Гонки claims и бюджетов, свежесть revocation, число потерянных переходов |
| После коротких транзакций и индексов остаётся SQLite write contention | Перенос изменяемого PA-состояния в PostgreSQL | Lock wait p95/p99, busy/errors, oldest runnable job, длительность транзакций |
| Нужны workers на разных хостах или восстановление БД на точный момент | PostgreSQL и отдельный операционный проект backup/failover | Restore drills, RPO/RTO, отказы связи и сверка действий |
| Повторные вычисления/чтения стали существенной долей задержки | Сначала измеренный локальный кэш; затем общий Redis при необходимости | Hit rate по workload, стоимость miss, экономия end-to-end, invalidation lag |
| После настройки PostgreSQL именно queue load мешает основным транзакциям | Рассмотреть отдельный broker и transactional outbox | DB CPU/I/O, lock/connection pressure, lag при согласованной пиковой нагрузке |
| Компонент требует независимого релиза, жёсткой изоляции или другого ресурса | Выделение только этого компонента | Частота независимых релизов, blast radius, цена эксплуатации |

Для начального согласования сохранить цели спецификации: подтверждение приёма
до 2 секунд, Chat p95 до 10 секунд, Search p95 до 45 секунд. Для фоновых задач
установить отдельный deadline, учитывающий quiet hours. Проверять при ожидаемом
пике и удвоенном пике на синтетическом профиле; сами пики ещё предстоит измерить.
Ориентиры вроде устойчивого lock wait p95 >100 мс или >1% busy/timeout можно
использовать как повод расследовать БД, но не как уже наблюдавшиеся факты или
универсальный порог миграции. Размер файла и количество Python-модулей сами
по себе не определяют выбор.

SQLite WAL допускает одновременных читателей и писателя, но писатель остаётся
один; shared-memory WAL не предназначен для совместной работы разных хостов
через сетевой файловый ресурс. WAL не снимает найденную блокировку вокруг
отправки. [SQLite WAL](https://www.sqlite.org/wal.html).

## Очередь и планировщик: сравнение

Сравнение ниже — инженерная оценка применимости к этому репозиторию.
Очередь переносит работу между процессами, scheduler определяет наступление
срока, а доменные записи определяют, разрешена ли работа. Это разные функции.

| Вариант | Что даёт | Цена и ограничения | Решение для PA |
| --- | --- | --- | --- |
| SQLite job store + один локальный worker | Минимум новых зависимостей; использование PA-09; удобные offline fixtures | Один write lock, один хост, собственное восстановление; текущий Watch не универсальная очередь | Подходит для переходного вертикального сценария и режима без сервера БД. Не размножать независимые SQLite-ledgers по воркерам. |
| **PostgreSQL-backed очередь** | Задание и изменение доменного состояния в одной транзакции; unique keys, row locks, общая durability | Нужны индексы, pooling, очистка завершённых jobs, autovacuum, мониторинг и backup | **Предпочтительный основной вариант.** Broker пока не нужен. |
| Redis Streams + PostgreSQL | Consumer groups, pending entries, ACK и reclaim; отдельное масштабирование обработки | Два состояния, outbox, повторная доставка, настройка persistence и trimming; доменные receipts всё равно нужны | Следующий вариант при измеренном bottleneck очереди, не обязательный старт. |
| Celery с Redis/RabbitMQ | Готовая экосистема workers, routing, retries и scheduling | Семантика ACK/crash зависит от настроек; framework не знает PA grants, подтверждений и неизвестных внешних исходов | Разумно при потребности в этой экосистеме. Не внедрять только ради слова «worker». |
| RabbitMQ как broker | Подтверждения издателю/потребителю, маршрутизация и управление доставкой | Дополнительный сервис, outbox и idempotent consumers; возможны повторы | При доказанной потребности в broker-функциях, которых не хватает PostgreSQL. |
| Temporal | Durable workflow history, восстановление многошагового процесса, ожидания | Новая платформа, дисциплина replay/versioning и отдельная эксплуатация | Пересмотреть при множестве долгих ветвящихся workflows и компенсаций; сейчас чрезмерный переход. |
| Cron/systemd timer + прямой вызов / Redis Pub/Sub | Простой сигнал наступления времени или уведомление | Сам сигнал не хранит бизнес-состояние, подтверждения и результаты | Допустим только как wake-up для durable scheduler. Pub/Sub не использовать как надёжную очередь. |

PostgreSQL прямо описывает `FOR UPDATE SKIP LOCKED` как подход для нескольких
потребителей queue-like таблицы; это не универсальный согласованный snapshot.
После короткого claim транзакцию закрывают, длительную обработку выполняют
вне неё. [PostgreSQL SELECT](https://www.postgresql.org/docs/current/sql-select.html).

Для Python можно оценить Procrastinate против небольшого собственного
адаптера PA job store. У него есть PostgreSQL-backed tasks, retries и periodic
tasks; перед выбором проверить transactional enqueue в нужной транзакции,
crash recovery, миграции, cancellation и состояние сопровождения. Страница
проекта сообщает о поиске дополнительных maintainers. Библиотека не должна
стать вторым источником состояния действий.
[Procrastinate](https://procrastinate.readthedocs.io/en/stable/).

Streams требуют `XACK` и обработки pending после падения; reclaim не является
доказательством отсутствия внешнего эффекта.
[XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/),
[XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/).
Redis Pub/Sub имеет at-most-once доставку.
[Redis Pub/Sub](https://redis.io/docs/latest/develop/pubsub/).
Durability Redis зависит от persistence: RDB допускает потерю изменений после
снимка, AOF с fsync раз в секунду допускает потерю последних записей.
[Redis persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/).

Celery требует идемпотентности и осознанной настройки ACK; `acks_late` само по
себе не гарантирует нужного поведения при завершении дочернего процесса.
[Celery tasks](https://docs.celeryq.dev/en/stable/userguide/tasks.html).
RabbitMQ также предупреждает о повторах после потери подтверждения.
[RabbitMQ reliability](https://www.rabbitmq.com/docs/reliability).
Temporal восстанавливает workflow через историю/replay; сохранность workflow
не доказывает однократность письма у внешнего провайдера.
[Temporal workflow execution](https://docs.temporal.io/workflow-execution).

**Scheduler:** расписание хранится в БД с timezone, revision, `next_due_at` и
политикой пропущенных запусков. Один активный scheduler с lease достаточен
сначала. В одной транзакции он создаёт occurrence с уникальным ключом и
продвигает расписание. Повторный tick или второй scheduler не создают повтор.
После простоя устаревшие обзоры объединяются/пропускаются по явной политике;
сроки пересчитываются по свежему источнику. DST и тихие часы остаются доменной
логикой PA-09. Таймер не должен непосредственно отправлять сообщения.

## SQLite → PostgreSQL: что переносить

| Хранилище | Преимущество | Ограничение | Предложение |
| --- | --- | --- | --- |
| Всё в SQLite | Простое обслуживание одного узла, сохранение FTS baseline | Конкурирующая запись и распределённая authority усложняются | Сохранить для offline режима и переходного этапа. |
| **PostgreSQL для PA-state + SQLite archive/FTS** | Общие транзакции для grants/jobs/actions, минимальное вмешательство в архив | Нет общей транзакции между двумя БД; архивная часть остаётся привязана к узлу | **Рекомендуемый первый переход.** Между БД только versioned refs и проверяемые операции. |
| Полный PostgreSQL | Один основной backend, общий доступ нескольким хостам | Перенос SQL, FTS, IDs, collation и восстановления; риск ухудшения RU/EN поиска | Только после отдельного ADR и retrieval benchmark. |

В первую очередь переносить grants/revocations, reservations/budget ledger,
jobs/checkpoints, confirmations, attempts/receipts, conversation object refs,
subscriptions и версии результатов. Канонические `raw_posts`/`posts` и FTS
оставить в SQLite до отдельной доказанной потребности. Почтовые производные
данные выделять собственной схемой/правами, не смешивать с Telegram-корпусом.
Пока архив в SQLite, архивные workers находятся на том же хосте либо используют
узкий read adapter; сетевой mount файла БД не является решением.

План миграции после выбора фазы:

1. ADR фиксирует конкретные таблицы, authority для каждой записи, требования
   к потере данных, переходный период и владельца rollback. Новый backend
   внедряется через узкие repositories, сохраняя DTO и source IDs; не нужен
   предварительный перевод всего проекта на ORM.
2. На синтетических данных реализовать одинаковые contract tests для SQLite
   и PostgreSQL. Проверять CAS, one-use, race/restart, JSON versions, NULL,
   UTC/timezone, uniqueness, constraints и семантику транзакций; замены `?`
   на другой placeholder недостаточно.
3. Сделать versioned export/import, counts, checksum нормализованных записей,
   проверку ссылок и integrity. Не пересчитывать существующие identity hashes
   или confirmation digests при сериализации. Секреты отдельно от экспорта.
4. Прогнать forward/restore на копии. Для SQLite использовать согласованный
   snapshot/backup API; копирование только основного файла активной WAL-БД
   недостаточно. [SQLite backup](https://www.sqlite.org/backup.html).
5. При разрешённом cutover остановить новые claims/изменения переносимых
   таблиц, дождаться или зафиксировать in-flight/unknown, снять финальную
   копию, импортировать, сверить и переключить одного writer. Старую базу
   оставить read-only на срок rollback. Избегать неатомарного dual-write.
6. До новых записей rollback может вернуть старый backend. После новых
   записей нужен проверенный перенос дельты или forward fix. Возврат старого
   snapshot без новых receipts способен повторно отправить письмо; такой
   rollback запрещён. `unknown` переносится как `unknown`.
7. У схем/jobs должна быть совместимость согласованной пары релизов N/N−1,
   versioned payload и отказ от неизвестной версии. Старый обработчик
   подтверждений допускается только после предусмотренного drain; нельзя
   ослабить PA-00, чтобы запустить старый бинарник.

Если позже переносится архив: сравнить полноту top-k, точные совпадения,
морфологию, RU/EN aliases, дедупликацию и ссылки на одном holdout. PostgreSQL
FTS — отдельная поисковая реализация; равенство SQLite FTS5 нельзя считать
автоматическим. [PostgreSQL text search](https://www.postgresql.org/docs/current/textsearch.html).
Семантический индекс остаётся производным; новая vector DB не требуется этим
переходом.

# Рекомендуемая архитектура

## Состав и ответственность

Один кодовый продукт с общим релизом и следующими ролями исполнения:

| Роль | Ответственность | Доступ |
| --- | --- | --- |
| Ingress / application | Приватная идентичность, dedup Telegram update, беседа, быстрые ответы, создание jobs, cancel/status | Нужные use cases; durable intake/state; без тяжёлого рендера в polling |
| Scheduler | Выбор due schedules и создание jobs с revision/occurrence | Состояние расписаний/очереди; без токенов провайдеров |
| Research / connector worker | Ограниченный поиск, получение разрешённых данных, нормализация, checkpoints | Только разрешённые provider/resource/data scopes |
| Render worker | HTML/PDF/извлечение текста из сохранённой версии | Ограниченные CPU/RAM/time/temp-dir; без произвольной сети и model keys |
| Delivery / action executor | Последняя проверка политики, claim попытки, внешний эффект, receipt/reconciliation | Минимальные секреты конкретного транспорта; write scopes отдельно от read |

Это логические роли, а не требование сразу развернуть пять микросервисов.
Начало: один ingress, один scheduler/worker runtime и последовательный
исполнитель внешних эффектов; рендер запускается в изолированном процессе.
Разделять pools по ресурсу и latency, когда появится измерение.

В рекомендуемой конфигурации PostgreSQL хранит авторитетное PA-состояние и
очередь. Файлы отчётов остаются в приватном локальном хранилище с hash,
версией и retention в БД; object storage нужен лишь при нескольких хостах.
SQLite пока владеет архивом/FTS. Опциональный Redis хранит восстанавливаемый
кэш и сигналы обновления, без единственной копии consent, budget или receipt.

## Контракт исполнения worker

**Задание — сериализуемое намерение, не сериализованное разрешение.** Payload
содержит version, `job_id`, owner/connection/resource refs, purpose, input
object/version/digest, consent revision, deadline, limits и idempotency key.
В очереди нет ключей, полного письма, произвольного Python callable или pickle.
`AuthorizationDecision` с ссылкой на in-memory registry нельзя переносить
между процессами как действующее право: worker заново получает решение из
общей authority и проверяет его перед каждым egress/эффектом.

1. **Приём и enqueue.** Повторный update имеет unique inbox key. В одной
   транзакции записываются намерение и job; после commit можно показывать
   «задача сохранена». Если позже используется broker, outbox записывается
   в той же транзакции, dispatcher публикует повторяемо, consumer dedup по
   domain job ID. Broker ACK не заменяет бизнес-квитанцию.
2. **Lease и fencing.** Claim выдаёт token/монотонную generation и срок.
   Heartbeat продлевает lease только для текущего token. Запись результата,
   checkpoint и попытки требует того же поколения. Для общего времени lease
   использовать время БД, для локального timeout — monotonic clock.
   Fencing защищает запись в БД; внешний API не обязан понимать этот token.
3. **Результат и доставка отдельно.** Research/render можно повторить с
   сохранённых checkpoints, если это безопасно. `result_ready` не означает
   `delivered`. Если durable attempt мог пересечь внешнюю границу, истечение
   lease или timeout переводит его в `unknown`; другой worker не начинает
   повторную отправку.
4. **Идемпотентность.** Ключ связывает owner, connection, object, content или
   change version, operation и reminder stage. Уникальность проверяется БД.
   Для provider idempotency использовать документированную возможность
   конкретного API, если она есть. Один ключ очереди не обеспечивает
   exactly-once у Telegram, почты или календаря.
5. **Reconciliation.** Проверять provider receipt/object/version по
   минимальному отдельному scope; хранить основание вывода. Если провайдер
   не даёт достоверного способа узнать исход, оставлять `unknown` и показывать
   владельцу дальнейший безопасный выбор. Отсутствие результата в локальном
   кэше не доказывает отсутствие отправки.
6. **Retries.** Для transient read/known-no-effect — ограниченный exponential
   backoff с jitter, `Retry-After`, deadline и общим attempt budget. 401/403
   с отозванным доступом не зацикливать. Неизвестная запись не попадает в
   автоматический retry. DLQ/quarantine хранит reason/refs; ручной replay
   повторно проверяет grants, версии, бюджет и подтверждение.
7. **Backpressure.** Отдельные лимиты на interactive, background и rendering,
   общий provider concurrency/rate budget, ограничение глубины и возраста
   очереди. Chat/cancel не ждут длинный PDF. Объединять повторные sync/brief
   одного scope, не выбрасывать подтверждённые действия без видимого статуса.
   При перегрузке давать ETA/частичный результат или явный отказ приёма.
8. **Cancellation и отзыв.** Durable cancel/revoke прекращает новые шаги,
   инвалидирует queued work/cache и проверяется перед транспортом. Уже
   начатый внешний эффект остаётся в receipt/reconciliation; UI не обещает
   его отмену задним числом.

**Отдельное решение о гонке pause/send.** В первом PostgreSQL executor
сохранить строгий порядок существующего PA-09: фиксировать attempt до
транспорта и сериализовать финальную проверку с pause/revoke по конкретным
grant/subscription/action rows. При необходимости удерживать эти узкие row
locks через один ограниченный transport timeout. Это осознанное исключение
из правила коротких транзакций; оно не блокирует всю job-БД, но занимает
соединение и задерживает изменения соответствующего scope.

Следующий шаг — per-scope dispatch sequencer с короткими транзакциями и
явным порядком `dispatch_started`/cancel. Он требует нового согласованного
контракта: что считается начатой отправкой, когда подтверждается пауза,
что происходит при смерти старого исполнителя. Нельзя одновременно убрать
блокировку, разрешить takeover неизвестной попытки и сохранить прежние
гарантии только «последней проверкой». До доказательства гонок остаётся
один executor внешних эффектов; stale worker не получает право переслать.

PA-06 fork callbacks не становятся distributed jobs автоматически. Новые
workers стартуют с явной конфигурацией, своими DB connections и ограниченными
секретами; соединения PostgreSQL создаются после fork либо fork исключается
для этого runtime. [Psycopg concurrency](https://www.psycopg.org/psycopg3/docs/advanced/async.html).

## Наблюдаемость, восстановление и выпуск

- Одна operator status view: capability действительно подключена или только
  настроена; последний успешный sync и coverage; очередь/oldest due; попытки
  `unknown`; расход/остаток; версия приложения и схема; состояние backup.
- Метрики: intake и end-to-end p50/p95/p99, queue wait/run time, failures по
  классу, retries/429, stale leases, reconciliation age, delivery lag,
  DB lock/pool wait, disk/WAL и cache hits. Correlation IDs — непрозрачные;
  prompts, тела писем, токены и URL с ключами в обычные logs/traces не попадают.
- Readiness отличает работающий процесс от готовой authority/БД/секретов.
  При потере authority запрещается egress/запись; чтение уже доступного
  разрешённого результата зависит от отдельной freshness/access policy.
- Backup включает state, receipts, результаты и отдельно защищённые секреты;
  derived indexes можно перестроить. В PostgreSQL PITR требует base backup и
  пригодного архива WAL; одной реплики недостаточно.
  [PostgreSQL PITR](https://www.postgresql.org/docs/current/continuous-archiving.html).
- Restore выполняется в режиме без отправок: новая execution epoch, остановка
  старых workers, сверка in-flight/unknown и возможных эффектов после времени
  backup. Старые grants и подтверждения не возобновляются автоматически.
  Затем отдельно разрешаются reads, schedules и writes. RPO/RTO выбирает
  владелец до пилота, а подтверждает реальная репетиция восстановления.
- Развёртывание первоначально на одном управляемом узле с systemd либо
  выбранным контейнерным runtime. Нужны воспроизводимые зависимости, отдельный
  migration step, schema compatibility, graceful drain и аварийный stop
  новых внешних эффектов. Не включать исторические report timers.
- Ключи вне Git и job payload; отдельная OS identity/секреты по роли,
  ограниченные права файлов, rotation/revoke, запрет попадания в exception
  dumps. DB/broker доступны только нужным процессам; off-host соединения
  аутентифицированы и защищены. В production не мигрировать схему автоматически
  при старте каждого worker.

## Стоимость моделей, задержка и кэш

Сначала сильный измеренный baseline на задачах владельца; затем дешёвый
маршрут при сопоставимом качестве. Выбор учитывает grants/data class,
provider retention, quality, latency, context и бюджет. Model router не
выдаёт разрешение. Текущие тарифы и доступность конкретных моделей этой
запиской не устанавливаются, платные сравнения не выполнялись.

| Работа | Предлагаемая оптимизация | Критерий полезности |
| --- | --- | --- |
| Chat / обычный поиск | Ограниченный контекст, стабильный prefix, streaming при поддержке; fast/strong route после сравнения | Полезность и multi-turn качество при согласованном p95 |
| Deep research | Ограничить параллельные подзадачи, steps/time/cost, остановка по достаточности | Покрытие и доказательства, стоимость завершённой задачи |
| Brief | Incremental collection, event dedup, один сохранённый editorial object | Отсутствие повторной генерации при смене HTML/PDF/Markdown |
| Извлечение | Детерминированный parser/дешёвая модель при доказанном качестве | Не пропускать критические сведения; даты проверять первоисточником |
| Media | Сначала text layer, OCR по необходимости, limits до provider call | Страницы/источники сохранены, задержка/расход ограничены |
| Judge | Отдельный бюджет и выборка на границах фаз, калибровка человеком | Обнаруженные ошибки качества; judge не выдаёт approval |

Durable budget ledger резервирует верхнюю оценку до вызова атомарно для всех
workers, затем учитывает фактический usage. Неизвестный исход не освобождает
резерв автоматически. Лимиты — на job/request, день/месяц, background и eval;
retry/fallback расходуют тот же общий бюджет. Разработческие расходы учитывать
отдельно от работающего ассистента.

`cost_per_success = все расходы данной когорты задач / число успешно
завершённых уникальных задач`. В числитель входят неудачи, retries, tools,
OCR и проверки. При нескольких attempts нельзя считать каждую удачную
модельную реплику отдельной успешной пользовательской задачей. Usage адаптер
нормализует непересекающиеся классы input/cache-read/cache-write/output и
reasoning согласно конкретному провайдеру, чтобы не посчитать включённые
tokens дважды. Неизвестный тариф остаётся unknown.

Разделить кэш извлечения по content hash, retrieval по archive/index revision,
рендер по `BriefDocument ID/version + renderer version` и model prefix cache.
Ключ приватного результата включает owner/connection/data scope, grant
revision, input version, prompt/model/tool versions. На cache hit проверяется
текущее право чтения; отзыв сначала закрывает доступ, затем удаляет зависимые
записи/артефакты. TTL не является механизмом авторизации.

Кэш фактов с истекшим freshness нельзя использовать как подтверждение нового
дедлайна; side effects и подтверждения не «кэшируются». Redis cache loss
должен означать повторное допустимое вычисление, а не потерю бюджета/consent.
Если Redis недоступен, concurrency ограничивается консервативно, durable
spend enforcement продолжает работать в БД.

Provider prompt caching и локальный result cache имеют разные условия.
Для OpenAI reuse зависит от совпадения prefix, модели/настроек и retention;
cache read/write тарифицируются по актуальной модели. Стабильные инструкции
помещать впереди, изменяемые данные — после них; не обещать процент экономии
без usage receipts и не расширять хранение приватного контекста ради hit rate.
[OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching).

# Roadmap по фазам

Фазы ниже закрывают разрыв между PA-контрактами и полным продуктом. Это
предлагаемый план после выбора владельца, не новая отметка «done» у PA-00…18.
Не повторять уже сделанные срезы: добавить конкретные integration/reliability
задачи к существующим требованиям через Playbook и сохранить evidence history.

| Фаза | Зависимости и работа | Проверяемая готовность | Граница полномочий |
| --- | --- | --- | --- |
| **0. Единый baseline и инженерное решение** | Свести актуальный handoff; матрица implemented/wired/tested/reviewed/live/accepted; ADR по jobs/storage/dispatch; согласовать reviewer policy и формальное решение Playbook | Один текущий scope; 19 approval errors либо разрешены подлинным workflow, либо остаются явно открытыми; fixtures/load profile и критерии следующих фаз записаны | Документы и локальные проверки без ключей. Человек отдельно принимает exact design; модель не устанавливает approval. |
| **1. Устойчивый сквозной локальный сценарий** | PA-02/03/06/07/09/13: durable grants/budget/receipts/object refs; typed jobs; inbox/enqueue; cancel/status; первый worker. Сценарий: запрос brief → job → версия отчёта → fake delivery → restart → та же квитанция | Падения до/после claim, до/после фиксации attempt, после внешнего fake effect и до receipt; duplicate update; два процесса; revoke/pause; изменение версии; unknown без слепого retry. Разговор продолжает правильный объект после рестарта | После назначения фазы — синтетические DB и injected adapters; сетевые эффекты выключены. SQLite допустим как fixture/переходный backend. |
| **2. PostgreSQL для общего состояния** | После 0/1, до масштабирования workers: repository adapters, grants/jobs/actions/budget в одном authority store; queue/scheduler; migration/restore rehearsal; bounded final executor | Parity SQLite/PostgreSQL; несколько процессов конкурируют без двойного claim/spend; fencing; killed worker; отказ БД/заполненный диск; восстановление без отправок; согласованный нагрузочный профиль проходит | Изолированная тестовая PostgreSQL и synthetic data после выбора фазы. Production provisioning/cutover требует отдельного решения. Redis не является зависимостью. |
| **3. Завершение пользовательских путей** | Опирается на 1, а multi-worker — на 2. Последовательно: Chat/Search и текущий объект; Brief/экспорт/Watch; Graph mail, calendar/contacts и Academic; Act; memory/media. Конкретные адаптеры вызывают guards внутри транспортной границы | Через один ingress проходят полезные положительные сценарии и отказы; fake HTTP проверяет scopes, paging/delta, 429, revoke/delete и отсутствие обхода guards; один отчёт даёт одинаковые факты в представлениях | Код, fixtures и synthetic renders без живых ключей. OAuth handshake, реальное содержимое, provider egress и отправки требуют конкретных grants. |
| **4. Разрешённая эксплуатация и полная приёмка** | PA-16/17/18 + готовые пути 3: минимальные реальные подключения, наблюдаемость, backup/restore, бюджет, актуальные модели, independent review, deployment и ограниченный пилот | Текущий SHA проходит нужные tiers; реальная проверка чтения/отзыва/доставки/reconciliation; Telegram/HTML/PDF осмотрены; 20 согласованных пользовательских задач и последующий период использования; quality/cost/latency и RPO/RTO измерены; владелец принимает полный outcome | Отдельные разрешения на аккаунты/данные, оплачиваемые модели, расписания, production migration/deploy и writes. Подтверждение каждой внешней операции живёт в продукте. |
| **5. Рост по измерениям** | После baseline 4: tuning pools/indexes/cache; Redis при необходимости; перенос архива/FTS или выделение отдельного сервиса только при срабатывании критериев | Сопоставимое качество при лучшей задержке/стоимости; chaos/recovery не хуже; дополнительная эксплуатационная цена оправдана | Новое infrastructure/egress/production решение в соответствующей части. Фаза не нужна, чтобы формально «иметь Redis». |

Фазы 1 и 2 можно объединить в одном согласованном проекте с PostgreSQL-first
для новых authority tables, если владелец сразу выбирает обслуживаемую БД.
Не стоит писать полноценную новую SQLite-платформу только затем, чтобы её
переписать. Существующий PA-09 сохраняется как источник поведения и fixtures.
Независимые read-only адаптеры и render tests фазы 3 могут готовиться раньше;
writes и фоновые эффекты ждут устойчивой authority/recovery.

Все обязательные продуктовые области остаются в плане. Отсутствие Canvas
доступа оставляет конкретный внешний blocker; не блокирует независимые Chat
или Brief и не превращается в заявление о полном завершении.

**Без живых ключей:** ADR/дизайн, storage adapters, migration на synthetic DB,
workers с fake transports, конкурентные/crash tests, scheduler с fake clock,
моки provider pagination/delta/revoke, privacy и cache invalidation tests,
рендеры synthetic отчёта, операторский runbook и offline load measurements.
«Без ключей» не равно «назначено в этой сессии»: текущая работа заканчивается
стратегией, код начинается после выбора фазы.

**С согласием владельца:** настоящий OAuth/account access, чтение приватной
копии архива для eval, работа с реальной почтой/календарём/Canvas, передача
данных моделям/judges, платные вызовы, storage/retention вне текущей границы,
фоновый сбор/уведомления, production migration, запуск сервиса и deployment.
Один согласованный scope действует в своих пределах; повторное согласие на
каждое уже разрешённое чтение не требуется. Для Canvas дополнительно нужна
проверенная допустимость интеграции со стороны учреждения.

# Решения владельца

| Решение | Рекомендуемый выбор | Что фиксируется до исполнения |
| --- | --- | --- |
| Следующая фаза | Фаза 0 с подготовкой bounded задания 1/2 | Scope, критерии, exact design и способ подлинного принятия Playbook |
| Базовая инфраструктура | Модульный монолит; PostgreSQL state/jobs; SQLite archive; Redis отложить | Допустимая стоимость/операционная нагрузка, размещение, необходимость нескольких хостов |
| Источники и порядок подключения | Сначала существующий архив и bounded web; далее подтверждённый Graph provider, calendar/contacts, разрешённый Academic | Конкретные аккаунты/ресурсы/операции, реальная ширина OAuth scopes, дата/порядок отзыва |
| Модели и приватность | Сильный baseline и явно разрешённый fallback | Провайдеры, классы данных, retention, quality profile, request/day/month/background/eval budgets |
| Расписания и уведомления | Минимально достаточная частота, quiet hours, дедупликация | Timezone, срок согласия, cap, исключения срочности, missed-run policy |
| Поведение при `unknown` | Не повторять до доказательной сверки | Допустимый ручной recovery, ограничения конкретных провайдеров, возможность нового подтверждённого действия |
| Хранение и восстановление | Минимальное хранение; защищённые backups; restore сначала без отправок | Retention каждого слоя, RPO/RTO, окно миграции, что делать с действиями в потерянном интервале |
| Reviewer policy | Согласовать документы с записанным owner amendment о non-Codex judge/review | Какие роли обязательны, какой разрешённый runner/provider, provenance, бюджет, cadence; human acceptance отдельно |
| Приёмка и выпуск | Полные критерии PA-18, раздельные fixture/live/visual/usefulness evidence | Список пилотных задач, продолжительность, quality пороги, ответственный за stop/rollback |

Разработчик может выбирать структуру adapters, индексы, тестовые fixtures и
обычные reversible детали внутри назначенной фазы. Только владелец расширяет
live-полномочия, бюджет, retention, продуктовый объём, принимает дизайн и
решает о выпуске. Эти решения не надо превращать в подтверждение каждого
локального шага.

# Риски и митигации

| Риск | Почему существенен здесь | Митигация / проверка |
| --- | --- | --- |
| Распределённые workers со старым in-memory grant | Revoke/budget в одном процессе не обновляет другой | Единый durable authority; проверка текущей revision перед транспортом; no authority → no effect; multiprocess tests |
| Двойная запись после timeout/restart | PA-13 receipts пока непостоянны, provider ACK может потеряться | Durable attempt до вызова, unique key, unknown quarantine, provider reconciliation; не обещать exactly-once |
| Ослабление pause/send при оптимизации SQL | Текущая гарантия обеспечивается транзакцией вокруг sender | Сначала narrow locks/один executor, затем отдельный доказанный sequencer; тесты конкурирующих pause/revoke/send |
| Старая задача или worker выполняет уже изменённое действие | Lease не отзывает отправленный API-запрос | Fencing в state, version/hash binding, запрет takeover unknown effects, точная отмена до dispatch |
| Очередь и доменное состояние расходятся | При Redis/RabbitMQ возникает dual-write | Transactional outbox, idempotent inbox; ledger БД — authority; ACK только после durable перехода |
| Backup восстанавливает уже использованное подтверждение | Внешние системы не откатываются вместе с локальной БД | Restore без egress, execution epoch, сверка потерянного интервала; неподтверждённые исходы остаются unknown |
| Перенос БД ухудшает поиск | FTS tokenization/ranking отличаются | Старый FTS baseline, source-ID parity и RU/EN holdout до переключения; независимый rollback поиска |
| Provider outage вызывает лавину retries/старых уведомлений | Watch, Brief, sync конкурируют за квоты | Jitter, Retry-After, shared caps, coalescing, приоритеты, catch-up policy и ограниченная DLQ |
| Утечка через jobs, cache, logs, backups или judge | Новые процессы увеличивают число копий приватных данных | Минимальные refs/payload, scopes, log allowlist, encrypted private storage, revoke/delete propagation; synthetic reviewer packet |
| Более дешёвая модель ухудшает содержание | Корректная схема не означает полезный brief | Согласованные holdouts, человеческая калибровка, отдельные coverage/editorial/multiturn показатели |
| Параллельные вызовы превышают бюджет | Локальные max-request counters не равны общему spend cap | Атомарные reservations и учёт unknown usage; лимиты на всю задачу и период |
| Двойной polling или фоновые legacy timers | Возможны конкурирующие consumers и неожиданные отправки | Один ingress на bot identity, durable dedup, явный inventory перед разрешённым rollout; legacy не включать по умолчанию |
| Новая инфраструктура занимает время, продукт остаётся неподключённым | Много PA-срезов существуют как отдельные local contracts | Каждая фаза заканчивается сквозным пользовательским сценарием, не количеством новых модулей |
| Инструкции создают ложное approval либо бесконечную остановку | Новый handoff и старые нормативные тексты расходятся | Один current scope/evidence index; workflow для approval; явная матрица безопасной автономии; история остаётся историей |

# Аудит инструкций

## Обнаруженный дрейф

Правки ниже **предложены**, существующие инструкции этой сессией не изменены.
Сохранить fail-closed, минимальные scopes, source identity, независимость review,
запрет приватных данных в Git и запрет подмены human approval. Ослабить следует
дублирующие/устаревшие рецепты, а не эти границы.

| Файл / область | Конкретная проблема | Предлагаемая правка |
| --- | --- | --- |
| [AGENTS.md](../AGENTS.md), Authority/Verification | «This change is NOT product implementation» описывает публикацию сентября; «PA-00 must diagnose» выставляет старую ошибку текущей | Оставить стабильные правила; current task/scope брать из актуального handoff. Историческую UX ошибку заменить ссылкой на PA-00 evidence и датированный текущий результат. |
| [CODEX_PROMPT.md](CODEX_PROMPT.md) | `Updated: 2026-09-20` при amendment 23 сентября; next PA-10, current PA-09 и PA-10…17 local contracts одновременно; старое утверждение о legacy-default debt противоречит новой записи и коду | Переписать как один snapshot HEAD, активный scope, действующие полномочия, blockers, результаты и next command. Старые checkpoints — ссылки, не конкурирующие текущие инструкции. |
| [README.md](../README.md) | Сохранился «known UX failure», хотя выбранный тест на текущем SHA проходит; общее «blocks free AI» скрывает наличие conditional model path | Таблица «подключено по умолчанию / local contract / live evidence». Указать дату теста, не объявлять весь CI зелёным. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | `Status: current`, но reports secondary и «new weekly-report product» в non-goals расходятся с полной PA-целью | Разделить observed implementation и target architecture; Brief — основной PA outcome. Системные templates не называть наблюдением runtime. |
| [IMPLEMENTATION_CONTRACT.md](IMPLEMENTATION_CONTRACT.md) | Product Authority и budget wording ориентированы на PRM-SN; весь external skill слой объявлен disabled «during this planning retrofit» | Через ADR обновить applicability для PA, отдельно development/runtime и разрешения по риску. Не отменять запреты egress/secret/live-write. |
| [REVIEW_POLICY.md](REVIEW_POLICY.md), [PLAYBOOK_ADOPTION.md](PLAYBOOK_ADOPTION.md), [implementer prompt](prompts/personal_assistant_implementer.md), AGENTS | Жёсткий Terra/high reviewer противоречит позднему owner amendment о non-Codex OpenCode Go; prompt ещё требует design approval до любой capability work, handoff допускает local amendments | Одна актуальная review policy с ссылкой на owner amendment, ролями и cadence; prompts ссылаются на неё. Сохранить formal approval отдельно от local implementation authority. |
| Role Runner / Mimo | Codex role runner и отдельный OpenCode review tool не создают автоматически одинаковые Playbook receipts | Записать approved mapping role→runner→receipt и точный provenance. Если gateway не поддержан pinned workflow, обозначить integration gap; не выдавать текстовый verdict за успешный Role Runner. |
| [tasks.md](tasks.md), [PA.design.json](design/PA.design.json) | `planned`/`review_required` соседствуют с реализацией и evidence; одних этих статусов мало для выбора работы | Сохранить официальные состояния до workflow; рядом вести факт-матрицу implementation/wiring/test/review/live/acceptance по SHA. Не выставлять `done` по числу тестов. |
| Тот же registry, verification refs | PA-17 называет `test_assistant_operations.py`/`test_assistant_recovery.py` в allowed files, реализован `test_assistant_ops.py`; PA-16 дополнительно называет `test_assistant_models.py` | Сверить точные file refs и реальные acceptance cases при обновлении дизайна. Автоматическая проверка структуры сегодня не доказывает полноту этих связей. |
| [COST_BUDGET.md](COST_BUDGET.md) | Старые workload IDs и обязательный технический privacy footer каждого ответа расходятся с PA UX и cost architecture | Сохранить действующие ceilings до решения владельца; добавить PA workload budgets. Полную диагностику показывать в status/details, а не обязательным машинным текстом в каждом ответе. |
| [ORCHESTRATOR.md](prompts/ORCHESTRATOR.md), `workflow_*`, `prm_search_news_*` | Alias содержит абсолютный путь другой машины; активными названы maintenance backlog/старые роли и `codex exec` implementer | Relative link; metadata `workstream`, `status`, `superseded_by`. Старые промпты сохраняются как historical/explicit-use; default ведёт на PA assignment. |
| [test_tiers.py](../tools/test_tiers.py) | `FAST_CONTRACT_TESTS` включает весь `PRM_ACTIVE_TESTS`: «fast-contract» фактически шире focused-prm | Показать состав/стоимость tiers; предложить отдельный действительно узкий tier и независимые feature acceptance tests. Изменять registry/CI согласованно, не удалять coverage ради зелёного статуса. |

`tools/check_personal_assistant_plan.py` прошёл, а pinned validator выдал 19
approval errors. Это наглядно показывает необходимость различать structural
validity и authority. Нужное исправление — подлинное решение в workflow и
точная фиксация local amendments; не подавление ошибок валидатора.

## Навыки: что мешает выбирать и как исправить

В просмотренной основной части репозитория не обнаружены собственные
`SKILL.md`; доступный каталог среды содержит системные и пользовательские
навыки. Полный аудит их исполняемых scripts/dependencies здесь не проводился.
Доступность навыка в каталоге не доказывает project trust и не даёт ему доступ
к приватным данным.

Главная проблема — blanket-формулировка «all listed external skills are
project-disabled ... none is approved» без границы между чтением методики,
публичной документацией, запуском программы и подключением аккаунта.
Она мешает даже безопасному выбору помощника по документации и быстро
устаревает при изменении каталога. Необходимо управлять разрешёнными
действиями навыка, а не только его названием.

Предлагаемая матрица, требующая принятия как новая project policy:

| Класс использования | Правило |
| --- | --- |
| Чтение инструкции/официальной публичной документации без секретов и приватного контекста | Разрешено в назначенной исследовательской задаче; public requests минимизированы |
| Проверенный локальный инструмент над synthetic fixtures | Разрешён внутри task scope; фиксируется источник/version и набор файлов/действий |
| Новый сторонний executable, installer, hook или широкое сканирование | Trust review кода/dependencies и закреплённой версии до запуска; инструкция навыка не расширяет scope |
| Connector, секреты, приватный corpus, платный API, write/send/deploy | Отдельные конкретные полномочия; наследуется общая политика egress/actions, не выдаётся универсальное разрешение навыку |

Хранить trust record с source/version/hash, разрешёнными I/O, data classes,
нужными credentials, записью решения и условиями пересмотра. Выбирать только
навык, который помогает текущему результату; не загружать каталог целиком.
Официальная документация описывает загрузку сначала name/description, затем
выбранного `SKILL.md`, явный и неявный выбор по описанию. Это поддерживает
короткие triggers и точные границы применимости.
[OpenAI: Build skills](https://learn.chatgpt.com/docs/build-skills).

Для этой стратегии использован системный навык OpenAI Docs только для
официальной документации skills/prompt caching. SEO, Wordstat,
Telegram/Reddit/X сборщики не требовались задаче. Image generation и создание
сайта также не улучшают необходимое письменное решение. Новые навыки, плагины,
hooks и аккаунты не устанавливались и не активировались.

## Конкретные предлагаемые замены текста

Для `AGENTS.md` вместо исторического ограничения всего репозитория:

> Scope и stop point определяет текущее задание владельца и один актуальный
> handoff. В назначенной фазе разрешены чтение кода, безопасные локальные
> изменения и проверки на synthetic fixtures. Доступ к реальным аккаунтам,
> приватным данным вне согласованной границы, платный egress, фоновые сервисы,
> production migration и deployment требуют отдельных scoped полномочий.
> Formal design/release acceptance не выводится из разрешения писать код.

Для review-параграфов AGENTS/implementer prompt:

> Primary implementer использует текущую модель/режим сессии без project-wide
> override. Роли, разрешённые runners/providers и cadence определяются только
> актуальным `docs/REVIEW_POLICY.md` с provenance owner amendments. Review
> независим и read-only; фиксируются requested/observed model/effort, SHA/diff
> и receipt. Недоступный runner или неподтверждённая модель остаются пробелом
> evidence. Human acceptance и live permissions не делегируются reviewer.

Для `IMPLEMENTATION_CONTRACT.md`, External Skills:

> Выбирать навыки по назначению текущей задачи и читать их инструкции адресно.
> Чтение public documentation и reviewed local tools над synthetic fixtures
> допускаются внутри task scope. Новый executable/hook требует trust review.
> Ни один skill не расширяет доступ к файлам, секретам, аккаунтам, платным
> моделям или внешним записям. Для таких действий действуют отдельные grants;
> повторное согласие внутри уже выданного точного scope не требуется.

Для будущих стратегических промптов, включая `astra6_strategy.md`:

> Роль — стратегический архитектор; название роли не утверждает фактическую
> модель runtime. Различай observed code, synthetic evidence, live evidence
> и рекомендацию. Выполняй назначенные безопасные локальные проверки без
> промежуточного согласования. Заверши письменный результат с вариантами,
> критериями выбора и next step; не начинай реализацию до выбора фазы.
> Документацию изменчивых технологий проверяй по официальным публичным
> источникам, не передавая приватный контекст. Не включай сервисы и аккаунты.

Эти формулировки должны пройти обычный процесс изменения нормативных
документов; эта записка не делает их действующими правилами.

## Передача результата

Добавлен только `docs/PA_SCALING_STRATEGY_2026-10-06.md`; код, нормативные
инструкции, task/design statuses и runtime configuration не изменены.
Проверка документа: семь требуемых разделов, существующие локальные ссылки,
парные code fences; `git diff --no-index --check -- /dev/null
docs/PA_SCALING_STRATEGY_2026-10-06.md` не вывел ошибок whitespace (exit 1
обозначает новый файл в no-index сравнении).

Исходные untracked `UTD_intelligence_layer_research_report.md` и
`docs/prompts/astra6_strategy.md` сохранены. Commit/push и внешние записи не
выполнялись. Приватные БД, секреты и аккаунты не открывались; внешнее чтение
ограничено официальной публичной документацией.

Открыты: выбор фазы, exact design approval, согласование reviewer policy,
независимый review соответствующего изменения, подключение и проверка
реальных провайдеров, операторская/визуальная приёмка PA-18. Это разные gates.
Новая модель/effort исполнителя не запрашивались; независимый reviewer этой
работы отсутствует. Записка не является его receipt.

Следующая безопасная команда для просмотра полного результата:

```bash
git diff --no-index -- /dev/null docs/PA_SCALING_STRATEGY_2026-10-06.md
```

Exit 1 у этой команды означает наличие показываемого diff. Следующее
содержательное действие после решения владельца — фаза 0: согласовать ADR и
задание на один устойчивый сквозной сценарий, затем продолжить через pinned
Playbook. Не начинать с подключения Redis или переноса всего архива.
