# Telegram Personal AI Assistant

Персональный ассистент одного владельца: **Chat, Search, Brief, Watch и подтверждённый Act** в общей беседе. Канонический Telegram-архив остаётся в SQLite; разрешения, состояние, задачи, результаты и квитанции имеют локально реализованный PostgreSQL runtime.

**Состояние на 10 октября 2026:** основная локальная реализация собрана, проверена полным активным набором и испытана с настоящей модельной генерацией. Следующий этап — выбранные реальные подключения и операторский пилот. Ежедневная эксплуатация, production cutover и человеческая приёмка ещё не подтверждены.

Проверенный код: `0fbcfd1dde780724ad934aa66825afe17a6efc98`. Последующие изменения оформляют документацию, публичные синтетические доказательства и узкую CI guard compatibility correction, независимо проверенную118. Runtime остаётся тем же. Целевая ветка интеграции — `master`; фактические refs и проверки находятся в [пакете слияния](docs/verification/PAI-master-integration-20261010.md).

## Навигация

| Вопрос | Документ |
| --- | --- |
| Что готово, чего нет и почему | [Подробный статус](docs/PRODUCT_STATUS.md) |
| Доказательство каждого обязательства | [69 требований и 10 сценариев](docs/verification/PAI-requirement-evidence-20261010.md) |
| Реальные команды, модели и результаты | [Проверка Go/пилота](docs/verification/PAI-go-pilot-20261010.md), [receipts JSON](docs/verification/PAI-go-pilot-20261010.json) |
| Посмотреть результат | [Синтетический AI Brief и изображения](docs/artifacts/pa-20261010/README.md) |
| Устройство системы | [Архитектура](docs/ARCHITECTURE.md) |
| Продолжить в новой сессии | [Handoff](docs/CODEX_PROMPT.md) |
| Подключить пилот | [20 задач и access packet](docs/verification/PAI-pilot-access-20261010.md) |
| Полный целевой продукт | [Спецификация](docs/PERSONAL_ASSISTANT_SPEC.md) |
| Метод и правила | [Контракт](docs/IMPLEMENTATION_CONTRACT.md), [тестирование](docs/TEST_STRATEGY.md), [review policy](docs/REVIEW_POLICY.md) |

## Возможности и границы доказательства

| Возможность | Реализовано и наблюдалось | Ещё не доказано |
| --- | --- | --- |
| **Chat** | Общий ingress/worker, разрешённая генерация, исходный контекст и недавние ходы, смена темы, сокращение, правка адресата. Два настоящих модельных диалога /12 ходов. | Долгое ежедневное использование, сложные реальные 10–20-ходовые задачи и все домены. |
| **Search** | Канонический FTS, bounded research worker, строгая проверка фактов/цитат/чисел/URL, честный fallback, покрытие по запросу. Настоящая V4.1-сводка двух источников прошла verifier и тестовую доставку. | Live scope личного архива, настоящий Brave discovery, полнота интернета и представительский набор личных вопросов. |
| **Brief** | Immutable документ, версии, источники, редакторская модель, HTML/PDF/Markdown, private reader, mobile light/dark. | Недельные личные материалы, человеческая полезность отбора, защищённый развёрнутый reader. |
| **Watch** | Preview/confirm, durable расписание, локальные tick/сбор/квитанция тестового адаптера, quiet hours/caps/pause/revoke. | Недельная работа сервиса, настоящая Telegram-доставка и notification noise. |
| **Act** | Точный preview, expiring one-use confirmation, executor, отдельный reconcile, `202 → unknown`, provider object и no-replay. | Настоящие test mail/calendar accounts, получение письма адресатом, запись выбранного календаря. |
| **Connections / Academic** | OAuth/PKCE/vault, отдельные Graph/Canvas/calendar адаптеры, lifecycle и негативные HTTP fixtures; различение сроков/локального выполнения/подтверждения источника. | Реальный OAuth/аккаунты. UTD/Canvas API отложен владельцем. |
| **Memory / Media** | Версии, explicit confirmation, provenance, forget/derived deletion; download/inspect/text layer/OCR/speech/vision seams и holdouts. | Личные retention настройки и реальные разрешённые speech/OCR/provider данные. |
| **Operations / Cost** | Grants/revoke, reserve/settle, unknown fences, leases/checkpoints/recovery, status, backup/restore и selected-domain migration rehearsal. | Production target/cutover, аварии настоящего хоста, SLO и фактическая стоимость полезной задачи. |

Наличие функции или теста не означает, что источник подключён. Тестовые данные и внешние эффекты в последнем benchmark синтетические; обращения к моделям и публичным GitHub/Python источникам были настоящими.

## Последняя проверка

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

Наборы пересекаются: не складывать их в уникальные тесты. Старые736 PRM/150 retrofit относятся к датированным SHAs; текущие проверки перед master записаны отдельно. Полный исторический pytest запрещён и не запускался. GitHub CI — отдельное доказательство; его статус нельзя выводить из локального результата.

## Независимая безопасность

Первоначальный P1 удаления диагностических частей исправлен: source/input/main-result зависимости и tombstone checks под общей блокировкой. **Review116 явно закрыл его**, но нашёл новый P1: multipart HTML сверялся по старым границам и кнопкам. Шесть регрессий воспроизвели сбой; общий payload builder исправил sending/reconcile. **Review117 на `0fbcfd1`: ADVISORY, открытых P0/P1 в проверенном объёме нет.**

Сохранён один P2 о предельной вложенности HTML и верхней границе Telegram-части. Исходные STOP/429/403, ошибки измерителей и исправления — в [отчёте](docs/verification/PAI-go-pilot-20261010.md). CI correction также получила118 ADVISORY/no P0/P1; fail-closed empty-draft robustness P2 сохранён. Engineering verdict не заменяет design/role/human приёмку.

## Что отделяет локальную версию от полного принятия

1. Не выбраны конкретные Telegram/test mail/calendar/resource/destination и scopes.
2. UTD/API отложен владельцем; fixture contract не является institutional access.
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

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python tools/test_tiers.py pai-complete
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python tools/test_tiers.py focused-prm
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python tools/test_tiers.py retrofit-boundaries
```

Выбирать минимальный подходящий tier. Не повторять успешно завершённый полный блок без изменения/сбоя/нового риска. Runtime CLI требует явных target/config; [runbook](docs/runbooks/assistant_runtime.md) не содержит автоматического live startup или connect-all.

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
