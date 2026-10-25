> Обновлено 25 октября 2026. [English README](README.md) — главная страница; [PRODUCT_STATUS](docs/PRODUCT_STATUS.md) — подробный статус с датированными доказательствами. Разделение EN/RU из обновления 24 октября сохранено.

# Telegram Personal AI Assistant

Персональный ассистент одного владельца: **Chat, Search, Brief, Watch и подтверждённый Act** в общей беседе. Канонический Telegram-архив остаётся в SQLite; разрешения, состояние, задачи, результаты и квитанции имеют локально реализованный PostgreSQL runtime.

**Где мы сейчас:** после восьми локальных пакетов есть engineering implementation/review evidence для **D01–D21, D56 и D58 — 23 из 62 карточек**. Остальные 39 включают обязательные и условные работы. Это счётчик карточек, а не процент готовности или формальная приёмка. В актуальном источнике реализованы диалоговый фокус, проекты, общий retrieval, составное исследование, отбор и обсуждение Brief, обратная связь, подтверждённая память и opt-in rich Telegram delivery.

Последний source/narrow review: **`b00a5cb` от 14 октября**, предыдущий package handoff **`865a7d8`**. Рабочая ветка — **`codex/pa-daily-implementation-20261013`**. Более свежий upstream README от 24 октября, `f878cc9`, подтянут обычным merge с сохранением истории. В `master` ежедневные пакеты пока не интегрированы; публикация рабочей ветки и слияние в master — отдельные шаги.

**Следующий пакет — D22+D23+D24+D57:** private storage, retention/backup/restore, один наблюдаемый профиль запуска и честный Telegram progress/Stop. D22 и D57 сначала разбить на ограниченные срезы. Реальные подключения, постоянная эксплуатация, production cutover и пользовательская приёмка ещё не подтверждены. Сверка документации 25 октября не является новой проверкой runtime.

## Навигация

| Вопрос | Документ |
| --- | --- |
| Текущие 62 карточки, зависимости и engineering receipts | [Единый backlog](docs/strategy/2026-10-11/BACKLOG.md), [JSON](docs/strategy/2026-10-11/backlog.json) |
| Что готово, чего нет и почему | [Подробный статус](docs/PRODUCT_STATUS.md) |
| Историческая проверка обязательств на 10 октября | [69 требований и 10 сценариев](docs/verification/PAI-requirement-evidence-20261010.md) |
| Последний пакет D19+D20+D21+D58 | [Команды и результаты](docs/verification/DAILY-package-08-D19-D20-D21-D58-20261014.md), [независимый review/rechecks](docs/verification/DAILY-package-08-local-review-20261014.md) |
| Реальные команды, модели и результаты | [Проверка Go/пилота](docs/verification/PAI-go-pilot-20261010.md), [receipts JSON](docs/verification/PAI-go-pilot-20261010.json) |
| Посмотреть результат | [Синтетический AI Brief и изображения](docs/artifacts/pa-20261010/README.md) |
| Устройство системы | [Архитектура](docs/ARCHITECTURE.md) |
| Продолжить в новой сессии | [Handoff](docs/CODEX_PROMPT.md) |
| Подключить пилот | [20 задач и access packet](docs/verification/PAI-pilot-access-20261010.md) |
| Полный целевой продукт | [Спецификация](docs/PERSONAL_ASSISTANT_SPEC.md) |
| Метод и правила | [Контракт](docs/IMPLEMENTATION_CONTRACT.md), [тестирование](docs/TEST_STRATEGY.md), [review policy](docs/REVIEW_POLICY.md) |

## Какой функционал заявлен

Полная [спецификация](docs/PERSONAL_ASSISTANT_SPEC.md) описывает одного помощника и одну беседу:

| Способность | Что получает пользователь |
| --- | --- |
| **Chat** | Обычный разговор: объяснить, переписать, обдумать решение, продолжить нужный вопрос или документ без обязательных команд. |
| **Search** | Исследование разрешённых Telegram/web/GitHub и выбранных личных источников, проверка актуальности, ссылки, даты, противоречия и честные пробелы покрытия. |
| **Brief** | Полезные обзоры недели/темы/проекта, важность и применимость, обсуждение пункта, обновление отдельной версии с diff; согласованные Telegram/HTML/PDF/Markdown представления. |
| **Watch** | Подтверждённые наблюдения за темами и сроками: расписание, тихие часы, лимиты, пауза, отзыв и проверяемая доставка. |
| **Act** | Черновики и выбранные письма/события календаря после точного предпросмотра и одноразового подтверждения; неизвестный результат сначала сверяется. |

Сквозные способности: управляемая память и актуальные проекты; выбранная почта/календарь Microsoft либо Google; Academic Inbox и полноценная Nebula; документы, голос и изображения; приватный reader; бюджеты, статус/отмена, восстановление, экспорт и удаление данных. Telegram Secretary добавляет отдельно выбранные чтение переписок, подготовку и подтверждённую отправку ответов. Темы Telegram условны. Canvas остаётся отложенным требованием; отсутствие доступа не делает его выполненным. **Mini App исключён владельцем. Полный замысел не сокращён до MVP.**

## Возможности и границы доказательства

| Возможность | Реализовано и наблюдалось | Ещё не доказано |
| --- | --- | --- |
| **Chat** | Native dispatch/focus, reply/callback, разделение старого документа и текущей темы, подтверждённый проект, relevant confirmed memory, status/cancel. На foundation от 10 октября есть настоящая генерация; ежедневные пакеты проверены synthetic/loopback. | Долгое ежедневное использование, native progress/streaming D57, сложные реальные задачи и откалиброванное качество. |
| **Search** | Канонический RU/EN retrieval, selected archive/GitHub contracts, public discovery/fetch contracts, две bounded research waves, checkpoints/continuation, факты отдельно от выводов/советов, current source guards. | Реальные scopes архива/GitHub, Brave discovery, provider quality и представительский набор личных вопросов. |
| **Brief** | Полная bounded выборка периода до model packet, event/project selection, exact story/version followups, refresh/diff, реальные локальные HTML/PDF/Markdown bytes, feedback и confirmed topic rules с undo; opt-in rich delivery. | Недельные личные материалы, полезность отбора, развёрнутый приватный reader D25 и реальная Telegram/mobile/desktop visual acceptance D40. |
| **Watch** | Preview/confirm, durable расписание, локальные tick/сбор/квитанция тестового адаптера, quiet hours/caps/pause/revoke. | Недельная работа сервиса, настоящая Telegram-доставка и notification noise. |
| **Act** | Точный preview, expiring one-use confirmation, executor, отдельный reconcile, `202 → unknown`, provider object и no-replay. | Настоящие test mail/calendar accounts, получение письма адресатом, запись выбранного календаря. |
| **Connections / Academic** | OAuth/PKCE/vault и Graph/Canvas/calendar adapter foundation, lifecycle/negative fixtures; отдельные read/model-egress scopes. | Выбранные реальные аккаунты; onboarding D26, mail/calendar D29–D32, Nebula D51–D54; Canvas D41 отложен отдельно. |
| **Memory / Media** | Explicit save/correct/inspect/search/export/forget, версии и provenance; relevant confirmed lexical memory в следующем вопросе с current egress grants; media foundation/seams. | Retention D23, полноценный media dialogue D34, семантическое качество. Save+undo предложен, но не активирован. |
| **Operations / Cost** | Grants/revoke, model profiles/budgets, durable jobs/leases/checkpoints, routing/delivery receipts, unknown fences и isolated recovery rehearsal. | D22/D23/D24/D57, private target/cutover, реальные аварии/стоимость/SLO и постоянная эксплуатация. |

Наличие функции или теста не означает, что источник подключён. Daily-пакеты используют isolated PostgreSQL/SQLite и fake/actual loopback HTTP. Настоящие модельные и публичные GitHub/Python вызовы в отчёте 10 октября относятся к его точному SHA. Rich выключен по умолчанию; nonfull/refresh виды сохраняют точный совместимый HTML/text. Выбор на основе topic rules остаётся local-only до отдельного разрешения model-egress.

## Что дальше по плану

1. **D22+D23+D24+D57 — ближайший пакет.** Разбить D22 на storage/target/offline recovery, D57 на truthful status/cancel и draft/stream. Затем реализовать synthetic storage, retention/restore, runtime profile и progress; D23 следует D22, D57 — D24. Реальные host/DSN/migrations/backup destination/service/cutover/canary требуют отдельного назначения.
2. **D25+D26 → D27+D40 → D38/D39.** Довести приватный reader и понятное подключение источников; отдельно разрешённый read canary и интерфейс на реальном телефоне; 20 задач владельца, затем 14 дней ежедневного использования и четыре полезных недельных обзора.
3. **D35–D37, D47/D48.** Независимо продвигать evidence-based judge, калибровку, сравнение качества/фактической стоимости, понятную config и методику. Эти карточки не закрываются старыми model scores.
4. **D28–D34, D42/D43.** Довести локальные черновики, выбранные mail/calendar lifecycle и подтверждённые эффекты, Watch без шума, мультимодальность, сквозной отзыв/удаление и устойчивость реального хоста. Microsoft/Google выбираются владельцем; оба провайдера не обязательны.
5. **D51–D54 и выбранные D59–D62.** Полная Nebula независимо от Canvas; D55 только при измеренном пробеле. Темы/Secretary идут через собственные selection/read/draft/send gates. Canvas D41 сохраняет отдельную отсрочку.
6. **D44 — приёмка полного продукта.** Закрыть все применимые требования и human/design/role gates. D45–D50 развивают архитектуру и сопровождение по зависимостям; learned retrieval D46 и масштабирование D49 требуют измеренного основания.

Точные AND/OR-зависимости и условия — в [backlog](docs/strategy/2026-10-11/BACKLOG.md). Отсутствие аккаунта не останавливает независимую локальную работу и не превращает live-задачу в выполненную.

## Последние локальные daily-проверки

Пакет D19+D20+D21+D58: source/full review `dbf4958`, first repairs/narrow STOP `b2092d6`, final code/narrow R02/R03 PASS `b00a5cb`. Один независимый full review и две узкие перепроверки закрыли семь P1 и два P2; открытых P0/P1 этого пакета нет. Финальные scoped runs: **30 passed /146.47s** и **6 passed /54.96s**, zero skips, выборки пересекаются. [Квитанция](docs/verification/DAILY-package-08-D19-D20-D21-D58-20261014.md) сохраняет команды, промежуточные failures и три action-preview provenance failures, воспроизведённые на исходном коде пакета. Legacy publication seam и прежние P2 остаются ограничениями.

Все восемь пакетов имеют отдельные receipts в backlog. Локальный independent review не заменяет non-Codex Go/governed/human gates. В проходе документации 25 октября заново проверяются ссылки, структура и сохранность плана; runtime/полный pytest/провайдеры не запускаются.

## Датированный foundation baseline — 10 октября

| Набор | Результат | Граница |
| --- | --- | --- |
| Полный **активный** PAI | **398 passed /1164.34s**, 69 exact IDs /10 сценариев, zero skips/failures | Код `0fbcfd1`, local synthetic acceptance. |
| Доставка /controls | **43 passed /127.72s** | Шесть до исправления падавших multipart recovery случаев. |
| Brief /exports /sessions | **77 passed /100.04s** | Source completeness, единые KPI, identity, реальный PDF overflow. |
| Recovery /end-to-end | **33 passed /260.43s** | Изолированная PostgreSQL /контролируемые внешние эффекты. |
| Новый Go transport и existing guard/plan/bridge | **195 passed /6.50s** | Advisory маршрут не создаёт governed role approval. |
| Реальная генерация | **11 ответов DeepSeek V4.1 Flash** | 1.21–5.237s, median1.753s; 30s development deadline. |
| Оценка диалогов | **6/6 сессий /25 ходов**, каждая из8 осей ≥4/5 | DeepSeek Pro/max requested; observed effort unknown. |
| Визуальная оценка | Kimi: PDF/источники/dark **5/5**, mobile/иерархия **4/5**, `pass` | Исправленный renderer на фиксированном прежнем редакционном содержимом. |
| Новый AI Brief | **5 PDF страниц**, zero out-of-page text/browser errors | Новый V4.1 текст проверен browser/PDF; отдельной новой vision-оценки этого содержания нет. |

Таблица сохраняет [отчёт 10 октября](docs/verification/PAI-go-pilot-20261010.md): базовый runtime `0fbcfd1`, отдельные инструменты/исправления имеют свои SHA в квитанциях. Это не новая проверка текущего source `b00a5cb`. Наборы пересекаются и не складываются. Старые736 PRM/150 retrofit тоже привязаны к своим SHAs. Полный исторический pytest запрещён. GitHub CI — отдельное доказательство; его статус нельзя выводить из локального результата или самого push.

## Независимая безопасность foundation baseline

Первоначальный P1 удаления диагностических частей исправлен: source/input/main-result зависимости и tombstone checks под общей блокировкой. **Review116 явно закрыл его**, но нашёл новый P1: multipart HTML сверялся по старым границам и кнопкам. Шесть регрессий воспроизвели сбой; общий payload builder исправил sending/reconcile. **Review117 на `0fbcfd1`: ADVISORY, открытых P0/P1 в проверенном объёме нет.**

Сохранён один P2 о предельной вложенности HTML и верхней границе Telegram-части. Исходные STOP/429/403, ошибки измерителей и исправления — в [отчёте](docs/verification/PAI-go-pilot-20261010.md). CI correction также получила118 ADVISORY/no P0/P1; fail-closed empty-draft robustness P2 сохранён. Engineering verdict не заменяет design/role/human приёмку.

## Что отделяет локальную версию от полного принятия

1. Не выбраны конкретные Telegram/test mail/calendar/resource/destination и scopes.
2. Nebula ещё не интегрирована: D51–D54; ключ и первый GET не заменяют полноценный lifecycle/пилот. Canvas отложен отдельно, fixture contract не является institutional access.
3. Brave discovery не испытан: ключ/область поиска не выбраны.
4. Private/production storage и cutover не выполнены: `SyntheticTarget` намеренно ограничен test DB.
5. Нет нескольких недель операторского пилота: полезность, пропущенные обязанности, noise, реальный p95 и стоимость успеха неизвестны.
6. Формальные design/role/human gates открыты: raw playbook сообщает51 missing approvals. Expected-rejection guard CI не создаёт согласие владельца и не превращает whole project verifier в PASS.

Полная спецификация сохраняется. Redis/перенос канонического архива PAI-30/31 требуют измеренного основания; отсутствие условных карточек отмечено в карте статуса.

## Development setup

Python3.10+, Git/submodules/symlinks, application dependencies из `requirements.txt`, development checks из `requirements-playbook.txt`. PostgreSQL14 tools требуются PAI тестам: disposable localhost instances, отдельные port/database/roles/marker, существующий порт5432/сервис не используются.

```bash
git submodule update --init --checkout -- .playbook/upstream
python -m pip install -r requirements.txt -r requirements-playbook.txt
python tools/playbook.py --check-pin
python tools/check_personal_assistant_plan.py
python tools/check_pai_plan.py
PYTHONPATH=src python -m prm.cli --help
```

Playbook pin: `d570163ab17ec3b4245187c778f1e8d89af9690f`, не latest. Это инструкции новой среды, не утверждение о переустановке/старте сервиса в текущем проходе.

Выбирать минимальный подходящий scoped tier по [TEST_STRATEGY](docs/TEST_STRATEGY.md). Регистрация26 daily test files в `tools/run_daily_acceptance.py` не является проходом всех тестов и не требует запускать их ради документации. Не повторять успешно завершённый полный блок без изменения/сбоя/нового риска. Runtime CLI требует явных target/config; [runbook](docs/runbooks/assistant_runtime.md) не содержит автоматического live startup или connect-all.

## Структура

- `src/prm/` — shared use cases /domain contracts.
- `src/prm/runtime/` — composition, ingress, workers, sources, delivery, private reader, media, operations.
- `src/prm/storage/` — versioned repositories /изолированный target.
- SQLite `raw_posts`/`posts`/FTS — канонический Telegram-архив.
- `src/bot/`, `src/assistant/` — интерфейсы и compatibility seams.
- `tools/` — проверка, advisory judges, pinned Playbook proxies.
- `docs/verification/` — датированные доказательства.
- `docs/artifacts/pa-20261010/` — переносимые синтетические примеры.

Исторические audit/receipts и `*.before-*` сохранены. Актуальный маршрут — [индекс PA](docs/PA_DOCUMENT_INDEX.md). Merge/CI не запускают production и не предоставляют права на личные источники.
