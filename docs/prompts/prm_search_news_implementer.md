# Goal: реализовать Personal Search And News от начала до конца

Это готовое поручение агенту-имплементатору. Передача этого промпта владельцем
назначает **всю локальную реализацию PRM-SN**, а не одну карточку. Само хранение
промпта в репозитории не запускает работу.

## GOAL

Полностью реализуй согласованную эволюцию одного личного Telegram-бота:
полезный поиск по архиву, проверяемые ответы и естественные продолжения,
контролируемую внешнюю проверку, тематические дайджесты по запросу и
подтверждаемые подписки с устойчивой доставкой. Пройди все 12 implementation-задач
PRM-SN-1A…PRM-SN-5B, исправления и инженерные deep-review gates PRM-SN-DR-1…DR-5.
Закончи интегрированной, локально проверенной реализацией и конкретным пакетом
для отдельно разрешаемого ручного пилота. UTD сохрани как частный сценарий
того же бота.

Если среда поддерживает create_goal, создай один goal с этой целью, без
придуманного token budget. Если goal уже есть, продолжай его, не создавай
конкурирующий. Карточки и фазы — этапы внутри одного goal. Не отмечай goal
complete после первой задачи, красивого отчёта, окончания текущего контекста
или одного успешного review.

**Работай от начала до конца:** реализуй → проверь → проведи независимый review
на установленной границе → исправь → перепроверь → перейди к следующей фазе.
Не спрашивай разрешение продолжить уже назначенные локальные задачи и reviews.
Не возвращай владельцу управление после каждой карточки с предложением
«могу продолжить». После compaction/нового контекста восстанавливай текущую
позицию из goal, task graph и evidence и продолжай ту же работу.

## Что считается завершением goal

Все пункты обязательны:

1. Все 12 задач реализованы на настоящих application/handler/collector/delivery
   путях. Заглушки допустимы в tests; ими нельзя заменить требуемую рабочую
   интеграцию. Внешние capability/provider adapters реализованы, но их live
   включение и реальные вызовы в рамках этого goal не выполняются.
2. Архивный вопрос, текущий факт, смешанный запрос, сравнение, follow-up,
   сохранение конкретного пункта, выпуск и subscription lifecycle проходят
   сквозные безопасные локальные проверки. Нет известных незакрытых P0/P1
   или нарушений обязательных engineering acceptance criteria.
3. PRM-SN-DR-1…DR-5 имеют независимые engineering review receipts для конкретных
   SHA/diff, с подтверждённым runtime reviewer model/effort, исправлениями и
   повторной проверкой. Task critic не засчитывается как фазовый deep review.
4. Финальный integrated replay проверяет взаимодействие всех фаз: actual
   rendered text, evidence/citations, confirmation, scheduling, outbox,
   retries/unknown outcomes и rollback. Показаны полезные положительные ответы,
   а не только запреты и отказы. Затронутые required checks проходят.
5. Обновлены task graph, relevant contracts/runbooks, before/after UX и evidence;
   подготовлен reviewable итоговый diff. Есть один финальный handoff с точным
   кодовым snapshot, результатами, остаточными ограничениями и планом пилота:
   источники, действия, разрешения, бюджет, срок, наблюдения и откат.

Завершение означает **готовность локальной реализации к решению о пилоте**.
Независимая человеческая полезность, реальные provider latency/стоимость,
VPS/Telegram observations и PRM-SN-DR-PILOT остаются отдельными свидетельствами.
Не подделывай их и не объявляй public release, production readiness или dogfood.
Их отсутствие не должно останавливать доступную локальную реализацию.

## Начало и последовательность

Прочитай текущие AGENTS.md, docs/CODEX_PROMPT.md, PRM-SN task graph в docs/tasks.md,
docs/PRM_SEARCH_NEWS_PLAN.md и docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md. Для конкретного
этапа подключай нужные contracts и docs/PRM_SEARCH_NEWS_EVAL.md, не всю историю.
Исходные дефекты и synthetic receipt —
docs/audit/PRM_SEARCH_NEWS_BASELINE_2026-09-17.md.

Перепроверь HEAD и working tree. Audited code baseline:
cee8baae3b8a41f571bd689f2dadf7e6e981863f. Новые документы могут находиться в
незакоммиченном дереве: сохрани их, исходный diff и manifest при создании
изолированной локальной ветки/копии. Не сбрасывай чужие изменения, не открывай
private DB/backup, не теряй task queue при создании worktree от старого HEAD.

Иди по зависимостям:

```text
1A → 1B → 1C → DR-1
2A → 2B → 2C → DR-2
3A → 3B      → DR-3
4A → 4B      → DR-4
5A → 5B      → DR-5
итоговый integrated replay → готовый pilot packet → завершение локального goal
```

Все ID имеют префикс PRM-SN-. Начинай с первой реально незавершённой задачи.
Фазовый engineering PASS открывает следующую фазу **в этом же поручении**,
без нового запроса владельцу. Обязательный gate нельзя обойти сменой task ID.
Если код изменился после review, перепроверь затронутый scope и обнови receipt.

## Полномочия и границы

Разрешены необходимые локальные изменения source/tests, изолированные fixture
DB и schema checks, default-off adapters и конфигурационные шаблоны, fixes,
документация/evidence и честные статусы всей новой PRM-SN очереди. Сначала
переиспользуй существующие компоненты. Не заводи второй бот, SaaS, новую vector
DB, необоснованный rewrite или отдельную инфраструктуру на каждую тему.

Реализация кода subscriptions/scheduler/egress не означает разрешение их
включения. Не менять host `.env`, настоящие данные, профили, подписки, services,
timers и разрешения. Не запускать live ingestion, реальные внешние jobs бота,
платный benchmark, внешние embeddings, private archive egress, production
migrations, рассылки или legacy cleanup. Public technical documentation читать
можно. Все product checks — с проверенными fixtures, fake transports/providers
и временными DB, после проверки imports/I/O; без полной исторической pytest suite.

Commit/push/merge и deployment в goal не включены. Работай в отдельной локальной
ветке, не меняя master/main и старые RFX/UTD statuses/approvals. PRM-SN статусы
обновляй по фактам: in_progress → implemented_pending_phase_review → implemented
в пределах engineering scope после нужного gate. Обязательно сохраняй residual
human/runtime gates; не имитируй operator acceptance.

## Качество и проверки

Используй существующие evals; добавляй только недостающие meaningful tests.
Сначала зафиксируй before baseline, затем actual final outputs и after results.
Не исправляй accuracy одним threshold или метриками, не влияющими на публикацию.
Проверяй факты/числа/даты/отрицания/субъект/цитаты и completeness до финального
текста, включая fallback. Сохраняй полезные ответы при слабой выдаче/outage.

Проверь весь пользовательский путь: scope архив/внешнее, RU/EN/опечатки,
точность/coverage/ranking, смена темы/периода, TTL/restart/старые кнопки,
сохранение конкретного пункта, event dedup/reposts/corrections, подтверждение
и отмена подписки, cap/quiet hours/expiry, гонки/retries/unknown sends.
Не обещай exactly-once без доказательства.

28 сценариев, независимый holdout и знаменатели метрик описаны в
PRM_SEARCH_NEWS_EVAL. Model-authored labels не являются human gold. При отсутствии
человеческих labels подготовь intake/measurement и сохрани ограничение,
продолжая engineering checks. Не выдавай расчётные расходы за измеренные.
Проверки расширяй только по новым изменениям, сбоям или нерешённым рискам.

## Deep review: входит в goal

В поручение включены необходимые независимые read-only Codex exec reviews
публичного кода и synthetic evidence: **gpt-5.6-terra, reasoning high**.
Не требуется новое подтверждение на каждый review/fix внутри этого scope.
Reviewer не реализует код, не получает частный архив, не commit/push и не
одобряет человеческие gates. Не запускай nested Codex для bootstrap/implementation.

Следуй docs/REVIEW_POLICY.md и docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md:

- Полный накопительный deep review после каждой из пяти фаз, до зависимой фазы.
- Внутри фаз — focused tests/critic по риску, без полного review каждой мелочи.
- При изменении confirmation/write, schema/retention, egress, source safety,
  delivery/caps/schedule — адресный immediate review до продолжения через
  границу, затем включение его результата в фазовый пакет.
- Отдельный fresh reviewer получает sanitised snapshot, phase base/current
  SHA+diff hash, relevant contracts, tests, полные UX outputs, risks и прошлые
  findings. Используй docs/prompts/prm_search_news_reviewer.md.
- Подтверждай средой отсутствие доступа к production, секретам и лишним
  MCP/hooks. `--sandbox read-only` сам по себе не изолирует чтение/egress.

Параметры запуска, остальные аргументы и stdin/output пути — по протоколу:

```text
codex exec
  --sandbox read-only
  --model gpt-5.6-terra
  -c 'model_reasoning_effort="high"'
```

Raw runner logs — вне рабочего дерева; sanitised review receipt — в docs/audit/.
Запиши exact command, requested и **observed** model/effort, runtime evidence,
exit result, reviewed diff, findings, fixes и re-verification. Флаги команды
и самоописание модели не доказывают effective runtime. Не подменяй Terra/high
молча и не выдумывай PASS при отсутствии доказательств.

Исправляй P0/P1 и acceptance failures, затем повторно проверяй конкретный diff.
Используй correction budget разумно: после двух безуспешных циклов одного
пакета пересмотри причину и план исправления; не повторяй одинаковые вызовы и
не обходи согласованные лимиты. Это не основание объявить goal выполненным.
Если reviewer недоступен, заверши доступные независимые изменения/tests,
сохрани точный checkpoint и реальный review blocker. Не переходи зависимую
границу без обязательного review и не останавливай всё из-за отсутствия VPS
или human labels, не нужных для локальной задачи.

## Продолжение и финал

Веди короткие progress updates: что завершено, текущая задача/gate, что осталось.
Сохраняй checkpoint в task/evidence документах, чтобы следующий контекст
продолжил тот же goal без повторения сделанного. Статусный вопрос владельца
не отменяет goal. Если есть настоящий внешний блокер, назови точное условие
его закрытия, продолжи независимую разрешённую работу и следуй правилам
среды для blocked goal; не отмечай complete за частичный результат.

Финальный ответ — только после полного локального результата по Definition of
Done либо честного неустранимого блокера. Верни цельный итог: все фазы/gates,
реальные проверки, ссылки на diff/evidence/runbooks, полные UX-примеры,
оставшиеся human/runtime проверки и готовый pilot/rollback packet. Сам пилот
и последующий PRM-SN-DR-PILOT не запускай без отдельного разрешения.
