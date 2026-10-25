# Подробный статус Personal AI Assistant

**Сверка документации, 25 октября:** текущий source/rechecked **`b00a5cb` от
14 октября**, предыдущий package handoff `865a7d8`, ветка
`codex/pa-daily-implementation-20261013`. Восемь daily-пакетов покрывают
**D01–D21, D56 и D58: local engineering evidence для23 из62 карточек**.
Оставшиеся39 включают обязательные/условные работы; это не процент готовности
и не формальная приёмка. Machine backlog/69 requirement mappings сохранены.
Чужой English/Russian README refresh от24 октября `f878cc9` подтянут обычным
merge; ежедневный код пока в рабочей ветке, без интеграции в master.

Ближайший пакет **D22+D23+D24+D57**: сначала ограниченные storage/recovery
и status/cancel→draft/stream slices, затем synthetic storage/retention/restore/
runtime-profile/progress. Дальше D25/D26, separately authorized D27/D40 и
пилоты D38/D39, независимая оценка D35–D37, затем полный mail/calendar/Watch/
media/Nebula/Act programme по зависимостям. Подробный заявленный функционал и
порядок — в [русском README](../README_RU.md) и [backlog](strategy/2026-10-11/BACKLOG.md).
Mini App исключён. Эта сверка/публикация документов не запускает runtime/tests/
провайдеры и не обновляет исторические acceptance/quality/CI/visual результаты.
[Git/doc receipt](verification/DAILY-docs-publication-20261025.md) отделяет
публикацию ветки от production, реальных подключений и human acceptance.

**Локальная реализация, 13 октября:** в ветке `codex/pa-daily-implementation-20261013`
выполнены D01–D03 и следующий пакет **D56**: durable Telegram routing/reply/callback,
acknowledgement, cursor/quarantine, bounded transport и source-edit fences.
D01–D03: original/reviewed `08fb32e`, final P1 recheck `988da0e`;
[квитанция](verification/DAILY-package-01-20261013.md) сохраняет 38 адресных
проверок и отдельный floor 52. D56: original/reviewed `8b56d8e`, final fix/recheck
`d231d9a`; [квитанция](verification/DAILY-package-02-D56-20261013.md) содержит
точные перекрывающиеся проверки, реальный loopback polling→worker→HTTP и финальные
6 passed /38.03s после исправлений. Один независимый локальный full review D56
нашёл два P1/два P2; все исправлены, P1 независимо перепроверены узко.
Это local engineering evidence; non-Codex Go/governed review и human acceptance
остаются открыты. Реальные аккаунты/клиенты, remote CI и пользовательская польза
не доказаны. D05 + D06 выполнен следующим локальным пакетом; текущий срез ниже. Датированный baseline
ниже сохранён и не объявляется новой проверкой всего продукта.

**Следующий большой пакет, 13 октября — D05 + D06:** source/full local review
`2318bbe`, focused repairs `e10365e`. Добавлены явные Chat capabilities/aliases,
bounded HTTP/SSE, durable observed model/usage/stop и frozen manifest/trace для
20 native synthetic tasks. [Квитанция](verification/DAILY-package-03-D05-D06-20261013.md)
сохраняет падавшие проверки, source SHA и границы. Два P1 исправлены и закрыты
узкой независимой перепроверкой на `e10365e`; post-fix capture завершён:
20 cases/35 loopback model calls, offline mechanics_met:true. [Packet](evidence/daily-package-03-fixed-20261013-traces.json). Исходные20 — dev cases;
120-unit target сохраняется, независимый holdout/quality/provider/operator
acceptance отсутствуют. R05 P2: blocking read может задержать отмену; после
чтения принятие просроченного результата запрещено. D04 + D10 реализован
следующим локальным пакетом; non-Codex Go/governed gates остаются открыты.

**Пакет D04 + D10, 13 октября:** versioned focus admission и bounded
intent plans, exact old-result binding, ephemeral project context, SourceBatch/
EvidenceBundle с отдельными received/eligible/selected/cited/omitted counters.
300 synthetic archive items перечисляются до выбора canonical20 Brief items;
packet omission делает обзор partial. Native archive hooks привязаны к owner,
privacy задаёт authorized route, response origins сохраняются, source revocation
проверяется при serving, synthesis HTTP и delivery. Source/full local review
`71704c4`, initial repairs `2a20da4`, final fix/recheck `0287f87`; [квитанция](verification/DAILY-package-04-D04-D10-20261013.md)
и [находки](verification/DAILY-package-04-local-review-20261013.md). Один full
review нашёл шесть P1/два P2. Narrow recheck2a20da4 закрыл их, но нашёл P1 R09
в scheduled replay. Узкая независимая PASS на0287f87 закрывает все package
findings; открытых P0/P1 нет. Исходный STOP и промежуточная ошибка сохранены.
Affected tier78 passed/2 fixture failures, затем исправленные fixtures+pure checks
7 passed/6.28s; final R09/delivery tier5 passed/20.18s; shared model floor10
passed/41.30s, counts не суммируются. Второй full review не запускался.
Actual20-turn synthetic transcript на71704c4 содержит fake planner/loopback;
это dialogue mechanics до source repairs, не реальная модель/качество/польза.
Следующим локально выполнен D07 + D08 + D09; текущая квитанция ниже. Ни аккаунты/платные
вызовы/сервисы/production, ни provider/operator/human acceptance не выполнены.
Полный Chat/Search/Brief/Watch/Act programme и исключение Mini App сохранены.

**Пакет D07 + D08 + D09, 13 октября:** versioned profiles по ролям/
privacy/expiry/fallback, promotion по фактическим paired attempts и observed
policy binding, честный бюджет; подтверждённые версии проектов с транзитивным
provenance/deletion; выбранный canonical архив с global tombstones, exact ID/name
filters, atomic cursor/quota и source snapshots. Обычный research, Brief/Watch,
модель, focus/delivery и reader повторно проверяют текущий источник. Source/full
review `caefb45`, initial repairs `9f5feec`, final fix/narrow PASS `8f193bb`.
[Проверки](verification/DAILY-package-05-D07-D08-D09-20261013.md),
[review/rechecks](verification/DAILY-package-05-local-review-20261013.md).
Один full STOP семь P1/четыре P2; narrow9f5feec закрыл R01–R11, нашёл R12 в
reader. Узкая PASS8f193bb закрывает R12; открытых package P0/P1 нет. Final native
24 passed/52.27s; R12+Brief5 passed/18.21s, reader/deletion5 passed/29.76s,
zero skips, counts перекрываются. Все исходные failures сохранены. Pair40
loopback responses — одинаковый synthetic model, разные connections/объявленные
цены, не quality/savings claim. Telegram session проверен fake client, не реальный
аккаунт; bounded scan не доказывает full history. Текущий snapshot консервативно
инвалидирует старые копии; historical UX остаётся D19, legacy/admin writers вне
lock contract. Structured project onboarding — engineering interface, не human
acceptance. Go/governed, provider/CI/operator/live/production gates остаются
открыты. Следующим локально выполнен D11+D12+D14+D16; текущий срез ниже. Полный
Chat/Search/beautiful Brief/Watch/confirmed Act сохраняется; Mini App исключён.

**Пакет D11+D12+D14+D16, 13 октября:** общий canonical retrieval с
bounded RU/EN expansions/filters/cache/exact lookup и revalidated opt-in hybrid;
нативный public plan для обычных вопросов, discovery отдельно от fetch и дат;
частично подтверждённые факты/выводы/предложения с source/premise proof; полная
bounded paginated выборка недели, ранжирование source/channel до model packet,
rolling168h/calendar-week и immutable /briefmaterials inventory без копии corpus.
Source/full review b442682, repairsde1e511, final source/narrow PASS650b8dd.
[Проверки](verification/DAILY-package-06-D11-D12-D14-D16-20261013.md),
[review](verification/DAILY-package-06-local-review-20261013.md). One full
STOP3P1/1P2 и промежуточные narrow STOP сохранены; R01 закрыт650b8dd,R02 на9ae,
R03/R04 наde1. Открытых package P0/P1 нет. Final verifier49 passed96.06s,
web/verifier59 passed125.07s, targeted native4 passed23.65s, zero skips; counts
перекрываются.21/10 synthetic dev labels, не human gold/holdout: expanded FTS
recall .8958/nDCG .9267 против .6146/.6775; hashed FP .8, auto native off.
Блоки используют консервативный lexical proof, не общий NLI. Личные source/topic
вопросы требуют отдельной public formulation; source date publication unknown
сохраняется, HTTP modification не выдаётся за publication. Синтетический actual
loopback/PG не доказывает live Brave/client/account/CI/operator usefulness или
Go/governed/human acceptance. Следующим локально выполнен D13+D15+D17+D18;
текущая квитанция ниже. Полный замысел сохранён, Mini App исключён.

**Пакет D13+D15+D17+D18, 14 октября:** выбранные GitHub files и
точные issue/PR/release IDs с SHA/versions/cache; отдельный synthetic private
read-only credential contract и model-egress scope; двухволновое исследование
с persisted coverage/checkpoints, bounded parallel reads и exact continuation;
детерминированные event revisions/новизна и проектный отбор Brief. D15a plan/
coverage, D15b reads/gap и D15c recovery/continuation разбиты до source changes.
Source/full review134172e, first repairs/narrow STOPa638afc, final source/narrow
PASS1717567. [Ledger](verification/DAILY-package-07-D13-D15-D17-D18-20261014.md),
[review](verification/DAILY-package-07-local-review-20261014.md),
[runbook](runbooks/project_research_event_brief.md). Один full STOP8P1/2P2;
first narrow оставил два P1 варианта/R10 P2; final R04/R07-only recheck закрывает
их, новых P0/P1 в исправлениях нет. Исходные STOP/failures сохранены. Final
affected43 passed191.86s и targeted6 passed32.51s, zero skips, counts перекрываются.
Prepared/unknown synthesis переживает recovery и блокирует fresh continuation;
исходная Telegram lineage остаётся связана. Native canonical ID/hash/URL/cited
result связывают архив с подтверждённым проектом; bindings реально включённых
историй проверяются после restart/expiry/replacement при serving/delivery/reader.
Facts/titles local/model проходят D14, иначе neutral wording/visible gap. История
редакционного включения отдельно от packet selection и неизвестного surfaced/read.
Exact groups7/7 на tiny authored dev fixture — не semantic quality/gold/holdout;
lexical coverage8/1200 не доказывает полноту ответа или полезность. Реальные GitHub
permissions/token rotation/App minting/provider/client/CI/visual/operator acceptance
не выполнялись. Non-Codex Go/governed и formal/human gates открыты. Следующим
локально выполнен **D19+D20+D21+D58**; текущая квитанция ниже. Full Chat/Search/
beautiful weekly Brief/Watch/confirmed Act сохраняется, Mini App исключён.

**Текущий пакет D19+D20+D21+D58, 14 октября:** обсуждение точной версии/
пункта документа, refresh с immutable новой версией/diff и HTML/PDF/MD export;
явная обратная связь, owner reactions и подтверждённые topic rules с undo;
bounded relevant confirmed memory в следующем вопросе с отдельными source/model
grants; opt-in Telegram rich renderer/delivery/edit того же документа. Source/
full review `dbf4958`, first repairs/narrow STOP `b2092d6`, final code/narrow
R02/R03 PASS `b00a5cb`. [Ledger](verification/DAILY-package-08-D19-D20-D21-D58-20261014.md),
[review/rechecks](verification/DAILY-package-08-local-review-20261014.md),
[runbook](runbooks/documents_feedback_memory_rich.md). Один full STOP7P1/2P2 и
две узкие независимые перепроверки; все девять находок закрыты локально, открытых
package P0/P1 нет. Final publication30 passed146.47s, targeted6 passed54.96s,
first-repair memory/conversation25 passed161.51s, zero skips; counts перекрываются,
точные границы изменений и первоначальные failures сохранены в ledger.
Source-bound immutable manifest сохраняется до атомарных native view/origin/
history/dependencies с текущими original-input/source/memory guards; потеря
parent освобождает compute lease
без stale ответа/автоматического replay. Exact historical ancestry и memory
проверяются до delivery HTTP. Исключающие правила сохраняют зависимости;
rule-derived editorial local-only. Nonfull/refresh rich views передают точный
совместимый HTML/text, full rich off по умолчанию. Save+undo — неактивное
предложение; lexical4 memories/128 heads/1200 chars не доказывают semantic
качество. Три action-preview provenance failures воспроизведены на base1db5034
и сохранены; legacy application publication seam вне native closure. Isolated
PG/SQLite и actual loopback подтверждают локальную механику, не реальные
providers/accounts/client/CI/visual/operator usefulness. Non-Codex Go/governed/
design/human gates остаются открыты. Следующий блок **D22+D23+D24+D57**;
D22 и D57 сначала разбить на ограниченные срезы. Real storage/retention/backup/
service/cutover/canary требуют отдельной авторизации. Полный замысел сохранён,
Mini App исключён.

Дата среза: **10 октября 2026**. Runtime/test/independent source SHA: `0fbcfd1dde780724ad934aa66825afe17a6efc98`. Документация и Git integration изменены позднее; фактические refs — в [merge receipt](verification/PAI-master-integration-20261010.md).

**Уточнение по Nebula, 11 октября:** [аудит двух upstream-репозиториев и пакет подключения](strategy/2026-10-11/UTD_NEBULA.md). Клиент Nebula в текущем коде отсутствует; существующие UTD watch и Canvas — другие интеграции. Владелец запросит ключ. Подготовлены D51–D54 для полноценной рабочей интеграции (включая recovery и 14-дневную приёмку) и условная D55 для закрытия пробелов через api-tools/официальный источник; Canvas остаётся отдельно отложенным. Исторические строки об отсрочке UTD/API ниже описывают состояние до этого уточнения; ни одной live-проверки Nebula пока нет.

**Дополнение 11 октября:** подготовлены [стратегия ежедневной полезности и пакет реализации](strategy/2026-10-11/README.md): статический аудит текущего кода `23312b8`, продуктовый дизайн, актуальный модельный обзор, эксперимент качества и 62 предлагаемых задачи (первоначальные 50, Nebula D51–D55 и Telegram D56–D62). Runtime, реальные подключения и приведённые ниже результаты этим исследованием не изменены. Первый будущий блок — D01–D03; новые наблюдения об entrypoint, отборе Brief и диалоговом управлении находятся в [аудите](strategy/2026-10-11/CODE_AUDIT.md).

**Telegram, 11 октября:** новые возможности встроены в тот же [backlog](strategy/2026-10-11/BACKLOG.md), пересекающиеся карточки уточнены. [Обоснование](strategy/2026-10-11/TELEGRAM.md) проверено по официальным источникам: rich reports/progress/Stop выбраны для основного интерфейса; темы — эксперимент, Secretary — отдельные read/draft/send gates, Mini App исключён владельцем из плана. Pure local probe подтвердил, что текущий ingress игнорирует native Stop/edited/business updates, sender не поддерживает inline navigation, conversation key не содержит thread. Это наблюдение baseline, не новый failing product test. Реальные Telegram/account/client проверки не выполнялись; code и сервисы не изменены.

## 1. На каком этапе продукт

Собрана работающая локальная система основных PA-сценариев с durable состоянием. Её функциональная механика проверена full active PAI, а выбранные ответы, research и Brief — настоящими запросами к Go. Мы на переходе от synthetic/provider development verification к выбранным реальным подключениям и операторскому пилоту.

Полный целевой продукт остаётся [PERSONAL_ASSISTANT_SPEC](PERSONAL_ASSISTANT_SPEC.md): все пять режимов, источники, память/media, устойчивость и подтверждённые действия. Текущий результат не является утверждением завершения программы. Нет честного единого процента готовности: код, live integration, качество и человеческая полезность имеют разное доказательство.

## 2. Что означает каждый статус

| Слой | Критерий | Наблюдение сейчас |
| --- | --- | --- |
| Code | Конкретные реализованные use cases/адаптеры | Runtime/storage реализованы локально; maps ниже. |
| Wiring | Настоящий composition/ingress/worker/store, а не отдельно вызываемый контракт | Native synthetic потоки, real isolated PG, HTTP/Telegram test doubles. |
| Synthetic tests | Фактическое выполнение positive/failure/owner/version/recovery случаев |398 current active PAI, zero skips/failures,69 IDs/10 scenarios. |
| Provider | Настоящий HTTP конкретного выбранного сервиса | Go inference и GitHub/Python fetch; Graph/Telegram реальные аккаунты отсутствуют. |
| Visual | Реальная отрисовка/инспекция и отдельный image judge | Local HTML/PDF/MD, browser/PyMuPDF, Kimi на фиксированном dataset. |
| Review | Независимая проверка точного source/diff с valid verdict | Engineering117 ADVISORY; two repaired P1 closed; extreme HTML P2 retained. |
| CI | Фактический remote workflow на конкретном SHA | Отдельный integration receipt; local pass не равен CI pass. |
| Operator | Владелец решает свои реальные задачи и оценивает результат | Настоящий двадцатизадачный/длительный пилот не выполнен. |
| Formal acceptance | Genuine hash-bound design/roles/human workflow | Draft/planned,51 raw missing approvals; не подменены merge или оценщиком. |

Эти слои независимы. Одна model label pass, наличие тест-файла, память fixture или доступный ключ не доказывают последующие слои.

## 3. Что действительно получилось

### Chat и контекст

Единый root обрабатывает вход, очередь, ответ и объект результата. Исходный пользовательский запрос и недавние ходы имеют bounded/expiring policy. Контекст исходных пользовательских слов отделён от generated history и private connector context; для egress отдельные grants. Новая тема и reset очищают текущий смысл, не превращая прошлый проект в authority.

Исправлены неправильный уход воспоминаний в поиск, потеря исходных фактов/срока, бессмысленный ответ на сокращение и сломанные Python-отступы. Current real capture:12 ходов в двух диалогах, включая Аврору/Python, сокращение, новую тему, fixture/mock, правку адресата и сохранение «завтра утром».

GCN использован как read-only reference: bounded original/recent turn anchor, separation of history scopes, topic precedence, оценка целого диалога. Код/данные/настройки грузинского домена не перенесены; provenance — [датированный reuse record](verification/PAI-GCN-reuse-20261009.json). Post-Telegram promotion idea не объявлена внедрённой.

### Grounded Search

Канонический архив читается через FTS независимо от curated atoms. Deep research выполняет bounded plan/read/synthesis/verify. Новые structured findings имеют text, exact URL и supporting quote; весь ответ допускается только после прежнего строгого verifier. Числа, actor/entity, negation и source integrity не ослаблены ради красивого ответа.

Current real V4.1 inference дал synthesized_verified с четырьмя фактическими предложениями по двум найденным источникам. Явно показаны checked steps, found/cited materials, ограничение по запросу и отсутствие измеренного результата. Некорректная генерация остаётся source-only fallback с честным статусом. Полного поиска интернета/частных аккаунтов этим не доказано.

### Brief и private reading

Один immutable BriefDocument содержит ID/version/digest/window/timezone/evidence/editorial/coverage. Chat, HTML, PDF, Markdown и followups используют этот объект. Refresh/comparison не подменяют незаметно исходную версию. Редакционный эффект без измерений не становится достигнутым результатом.

Исправлены несуществующая v2, английский редакционный вывод, отсутствующие ссылки, Source resource vs evidence count, мелкие mobile charts, разваливавшаяся coverage table, повтор source title/summary, обрезанные PDF titles, несогласованные cover KPI и fixed-page loss. Overflow guard/fallback, identity и private scope остались.

Новый реальный V4.1 Brief:3 материала, native exports,5 PDF страниц,0 clipping/browser errors. Controlled renderer benchmark с тем же старым MiMo JSON:3 страницы, полные источники и единые KPI. Kimi оценил именно controlled dataset, а не новый редакционный текст; отдельные screenshots/PDF сохранены [в Git](artifacts/pa-20261010/README.md).

### Watch и подтверждённый Act

Watch показывает реальный preview cadence/quiet/cap/source/expiry, separate saved intent vs observed scheduler activity, active/paused/latest check. Current wall/DB capture:tick создал задачу, collection нашла1 изменение, synthetic delivery получила receipt; после паузы новых задач нет. Resume сохраняет намерение; новый post-resume live запуск не утверждается.

Act показывает точный recipient/body или event arguments; natural text confirmation привязана к current fully delivered owner-visible proposal/version/digest/expiry и scopes. Accepted202 остаётся unknown, отдельная сверка подтверждает provider object, повтор не создаёт вторую запись. Current fake Graph exactly1 write; получение адресатом неизвестно.

### Durable foundation и операции

PostgreSQL реализует version/CAS, grants/revoke, reserve/settle, queue/lease/heartbeat/fencing/checkpoints, durable actions/results, subscriptions и артефакты. Unknown spend/effect не превращается в zero/known failure. Background collection и delivery scopes разделены. Pause/revoke и финальный source/owner guard действуют у эффекта.

Есть локальные status/drain/kill, private artifact cleanup, backup/restore и selected-domain export/import с locked manifests/monotone fences. Всё доказательство использует SyntheticTarget; production/private-data target, настоящий cutover и host incident validation остаются незавершёнными.

## 4. Точная карта PAI-00…31

Formal statuses ниже не меняются на done. Таблица показывает engineering observations, а не approve_feature_design/accept_slice.

| Пакет | Поверхность | Код /wiring | Доказательство | Незавершённое /почему |
| --- | --- | --- | --- | --- |
| PAI-00 | Instructions /review tooling | Pinned bridge, scopes, authority reconciliation, separate advisory Go transport | 195 scoped transport/plan/bridge; dated receipts | Formal role audit/gates remain separate |
| PAI-01 | Durable design | ADR-013 /32 registered packets /69 IDs /10 scenarios | Structural plan/schema checks | Exact human design approval not recorded |
| PAI-02 | PostgreSQL storage | Versioned repositories/unit-of-work, synthetic target marker/roles/schema checks | test_pai_storage; complete398 | Production/private target not implemented or selected |
| PAI-03 | Policy /budgets | Durable grants/revisions/revoke, atomic reserve/settle, unknown spend | test_pai_durable_policy; complete398 | Actual account billing/real private scopes not measured |
| PAI-04 | Action state | Proposal/one-use confirmation/attempt/receipt survive restart | test_pai_durable_actions; complete398 | Real Graph effect not exercised |
| PAI-05 | Conversation /results | CAS state, original/recent user context, expiring history, source/version object refs | test_pai_durable_conversation + product sessions | Long personal daily conversation absent |
| PAI-06 | Jobs /recovery | Inbox→queue, leases/heartbeat/checkpoints/fencing/deadline/cancel | test_pai_workers /load_recovery /end_to_end | Production scale/long crashes/SLO absent |
| PAI-07 | Ingress | Durable update dedup, quick persisted acknowledgement, one root | test_pai_ingress_jobs; native captures | Actual deployed Telegram polling not observed |
| PAI-08 | Watch scheduler | Schedule/occurrence atomic enqueue, collection, pause/quiet/caps/revoke | Current wall/DB tick→1 notification→synthetic sent; paused→no job | Real long-running service/delivery absent |
| PAI-09 | Delivery | Precommitted attempts, no-replay, exact receipts, shared multipart HTML reconstruction | 43 cases; reproduced6 failures; actual117 closure | Live Telegram receipt/reconcile absent; HTML nesting P2 |
| PAI-10 | Chat composition | Scoped model access; user/generated/connector contexts remain separate | V4.1 real responses in2 dialogues12 turns | Production profile/long representative conversations unproved |
| PAI-11 | Archive answer | Canonical FTS, bounded evidence and strict claims/quotes/numbers/ref verification | Current source-bound search + test_pai_archive_search | Private archive canary absent |
| PAI-12 | Web /GitHub | Brave/search and safe fetch adapters; exact commit/blob reads | Actual GitHub SHA and Python HTTP200 | Brave discovery credential not selected |
| PAI-13 | Deep research | Bounded durable plan/reads/synthesis/verify, source lineage, cancellation | Actual V4.1 synthesized_verified;2 matches/2 cited; synthetic delivery | Real heterogeneous/multiwave private/internet research absent |
| PAI-14 | Brief | Selection/editorial/versions/coverage/comparison over immutable document | New real editorial model /HTML/PDF/MD; content judge | Owner weekly personal selection/usefulness unproved |
| PAI-15 | Private report | Scoped sessions/artifacts, local isolated renderer, source identity, themes/print | 77 cases;5-page new PDF no clipping; fixed3-page Kimi pass | Hosted authenticated reader /live mobile experience absent |
| PAI-16 | Connection lifecycle | Selected Graph OAuth/PKCE/state/vault/refresh/revoke plumbing | test_pai_connections synthetic HTTP | Real Entra registration/consent/account not selected |
| PAI-17 | Mail reads | Graph paging/delta/minimal fields/thread/derived scope | test_pai_graph_mail | Real selected folder/lifecycle not exercised |
| PAI-18 | Calendar reads | Selected calendar/contacts/free-busy/recurrence/timezone scope | test_pai_schedule_runtime | Real selected calendar/contacts not exercised |
| PAI-19 | Academic | Separate Canvas/minimal fields, deadlines/conflicts/local/source done | test_pai_academic_runtime | UTD API/institution permission owner-deferred |
| PAI-20 | Confirmed writes | One bound executor;202 unknown; exact reconcile; duplicate confirmation | Current native fake Graph exactly1 write | Actual test mail/calendar/delivery recipient absent |
| PAI-21 | Memory | Explicit confirmed values/preferences, provenance, inspect/forget/source cascade | test_pai_memory_runtime; deletion116 explicitly closed | Personal retention/backup exceptions not selected/accepted |
| PAI-22 | Media | Download/type/size/network guard, text-first PDF/OCR/speech/vision adapters | test_pai_media_runtime /speech/vision seams | No real product speech/OCR/upload provider canary |
| PAI-23 | Profiles /cost | Versioned tariffs, per-role profiles, conservative unknown accounting/cache scopes | test_pai_cost_cache; actual provider usage receipts | Dollar cost/per-success/paired cheaper-profile gain unmeasured |
| PAI-24 | Operations | Status/drain/kill/health/metrics and safe secret-free metadata | test_pai_operations_runtime | No current host/service/operator incident validation |
| PAI-25 | Migration /restore | Selected-domain export/import, locked manifests, monotone unknown/consumed fences | test_pai_migration; local isolated rehearsal | Production RPO/RTO/backup/cutover absent |
| PAI-26 | Product verification | Positive/failure matrix, strict full-spec runner, public synthetic sessions/judges | 398/69/10;6 model-qualified sessions25 turns | Full connected human acceptance absent |
| PAI-27 | Live connections | Reviewable access packet; public fetch/model partial observations | Go +GitHub/Python observed; exact selected accounts still missing | Owner-selected bot/account/folder/calendar/source scopes needed |
| PAI-28 | Production cutover | Prepared sequence/guards/templates and domain delta tooling | Synthetic rehearsals only | Production adapter/host/snapshot/operator window/authority needed |
| PAI-29 | Owner pilot | Concrete20-task checklist, evidence/quality/noise/cost dimensions | Prepared packet; development benchmark is separate | Real owner tasks/duration/human PA-18 acceptance absent |
| PAI-30 | Redis conditional | Measured-trigger design only | Planned suite absent, disclosed | No measured reason or implementation |
| PAI-31 | Archive migration conditional | Measured-trigger design only; SQLite remains canonical | Planned suite absent, disclosed | No measured reason or implementation |

## 5. Два найденных P1 и их закрытие

1. Engineering112 обнаружил отсутствие cascade lineage диагностических chunks. Репродукция падала,6467c50 добавил source/input/main-result edges и tombstone/parent checks под lineage lock. Engineering113/114 не дали verdict из-за provider errors; эти attempts сохранены. Actual116 на fa7857b явно признал исходный P1 закрытым.
2. Actual116 одновременно нашёл новый P1: dispatch split HTML и last-part controls не совпадали с reconstruction в reconcile. Current six regressions до исправления:6 failed/44.95s. Shared _multipart_payloads используется обоими путями; accepted части не отправляются снова, missing/not-sent поздняя часть не становится отсутствием всего эффекта.43 after tests passed; actual117 на0fbcfd1:ADVISORY/no P0/P1.

Открытый P2: экстремальная вложенность HTML может превысить bound части. Это availability advisory, не основание объявлять arbitrary nested HTML поддержанным. Не удалять замечание и не запускать новый полный review ради каждого косметического изменения. Скрипты/inputs/STOPs/receipts сохранены [в portable evidence](artifacts/pa-20261010/README.md).

## 6. Модели, квоты, качество и задержка

| Работа | Requested /observed | Наблюдение |
| --- | --- | --- |
| Engineering116 | deepseek-v4-pro /max requested, actual effort unknown |890.457s;232712 input /40027 completion /272739 total; STOP с новым P1. |
| Closure117 | тот же Pro/max /actual unknown |470.397s;49125/19472/68597; ADVISORY. |
| Current generation | deepseek-v4.1-flash /thinking disabled benchmark |11 successful responses; min1.21/median1.753/max5.237s. |
| Text judge | deepseek-v4-pro /max /actual unknown |201.587s;8592/10683/19275;6/6 at diagnostic floor4 in every8 axes. |
| Controlled visual after repair | kimi-k2.7-code /provider default unknown |84.257s;8927/2172/11099; pass;5/5 PDF/sources/dark,4/5 mobile/hierarchy. |

Original115 получил GoUsageLimitError429. Владелец включил extra usage, затем116 реально завершился. Тариф/долларовый остаток/фактический счёт не прочитаны: стоимость unknown, не zero. Legacy V4 Flash и experimental Vision дали403 access disabled; наличие ID в каталоге не считается доступностью. Они заменены отдельно выбранными текущими моделями; отказы не стёрты.

Качественный benchmark:6 sessions/25 turns, синтетические факты и эффекты, настоящий native runtime. Старые GLM/MiMo3/6 и новые Pro/V4.1 6/6 имеют разных генератора/оценщика и обновлённые controls: это не matched causal improvement, не human usefulness и не обещание качества всех задач.

Учитываются замечания: сокращение может терять полезные подшаги; coverage wording в artifact можно сделать точнее; post-resume activity не наблюдалась. Предложение judge считать третью запись найденной не соответствует query-bounded FTS match2, поэтому счётчик не изменён ради score. Native states действительно рассчитаны кодом/PG; fake только источники и внешние providers.

## 7. Что ещё не доказано и почему

| Недостающий слой | Причина | Доказательство, которое нужно получить |
| --- | --- | --- |
| Real Telegram ingress/send/HTML/files | Не выбран test bot/chat/owner/destination/scope | Exact test message, matching provider recipient/message_id, unknown-send procedure, operator view. |
| Microsoft mail/calendar | Нет выбранного test account/folder/calendar и OAuth scopes | Real OAuth/read/sync/revoke/delete; exact confirmed controlled write и provider receipt. |
| Brave discovery | Не выбран credential/query/hosts budget | Actual search→primary fetch→verified answer; unavailable/partial coverage observation. |
| UTD/Canvas/academic | API отсутствует/owner-deferred; institutional permission отдельное | Выбранные allowed scopes/endpoint и реальные source-authoritative records, без grades/roster/submission bodies. |
| Product speech/OCR/image inputs | Fixtures/adapters есть, real product provider не выбран | Настоящий consented input→text/OCR→answer→cleanup и source page refs. |
| Private retention/memory | Реальные настройки/backup exceptions не выбраны | Owner-selected retention, inspect/forget on private scope, delayed/provider exceptions exposed. |
| Production target/cutover | Storage deliberately synthetic; нет selected host/DSN/operator window/authority | Reviewable private target design, actual restore/RPO/RTO, one writer/epoch, recovery/rollback and exact deployment decision. |
| Everyday usefulness/noise | Нет real owner20 tasks/нескольких недель | Whole-task success, missed obligations, false refusals, feedback/noise, perceived quality. |
| Production latency/cost |11 small dev responses, synthetic budget records, no billing | Representative p95, actual tariffs/provider telemetry, cost per useful completion incl fixes/retries. |
| All formal gates | Exact design/role/human decisions отсутствуют | Genuine pinned hash-bound approvals; current51 raw missing gates remain visible. |
| Conditional Redis/archive move | Нет измеренного triggering bottleneck | Measurement +ADR +holdout improvement before introducing another state backend. |

Доступный ключ не заменяет consent; mail folder filter не сужает OAuth token на стороне provider. Private source read, model egress, write и background work имеют отдельные права. Живой pilot не начинается на неизвестном аккаунте, а тестовый PostgreSQL не переименовывается в production.

## 8. Следующая последовательность

1. Завершить нормальную интеграцию документации/кода в master и проверить фактические refs/CI отдельно от source proof.
2. Получить выбранные test resources/credential references; вопрос отправлен, настройки не получены. [Access packet20 задач](verification/PAI-pilot-access-20261010.md) уже reviewable.
3. Составить команды на действительных конфигурациях, отдельные read/egress/write/background scopes, retention/duration/caps/stop/cleanup. Не запрашивать повторное общее разрешение вместо недостающей конкретики.
4. Выполнить по одному контролируемому подключению. Перед письмом/event/Telegram test effect предъявить точный preview и использовать owner-bound one-use confirmation.
5. Провести owner20 tasks и согласованный длительный pilot; сохранить private receipts/screenshots вне Git, публиковать только sanitized counts.
6. Выполнить необходимые genuine formal acceptance/production decisions. Полная спецификация не сокращается до прошедшего development benchmark.

## 9. Как сохранить честное доказательство

Raw failures и dated snapshots неизменны; новый evidence имеет свой SHA/input/log hash. Последующие docs-only commits не являются повторной execution proof. Model output — advisory/untrusted, не инструкция выдавать grants или preferences. Пересекающиеся tiers не суммируются. Remote CI фиксируется observed, не expected success.

Актуальные документы и исторические роли — [PA_DOCUMENT_INDEX](PA_DOCUMENT_INDEX.md). Полная карта binding nodes — [69/10 evidence projection](verification/PAI-requirement-evidence-20261010.md). Конкретные implementation contracts/ADRs сохраняют силу; Git merge не является runtime rollout.

## 10. Документация и CI compatibility correction

Текущие README/status/architecture/operator/runbook/index/authority документы пересмотрены; полная карта69/10 имеет фактические binding nodes и отдельные live/human границы. Подробности вынесены из compact design maps: pinned20k context bound не расширен. Исторические snapshots не переписаны.

Перед master обновлён только CI planning guard: старый PA-only checker отвергал зарегистрированные PAI задачи. Новый known-PA/PAI union сохраняет exact51 expected negative errors, foreign/duplicate/nonplanned/unexpected warning/error denial и raw validation после approved state. Source4c2656c,63 scoped tests3.21s; независимый118 ADVISORY/no P0/P1,222.626s,usage7993/13229/21222. P2 о пустом draft остаётся,для current51 nonempty tasks не применяется. Приложение/runtime/requirements/CI workflow bytes равны0fbcfd1; это не новое выполнение398.
