# Четыре пункта: реализация и единый блок проверок

Задание владельца 2026-10-10 — выполнить четыре пункта и затем один большой блок проверок по каждой теме. Код `2e541af8e9928e1b1002110e055bd615aa8b5434`; авторизация и конкретный дизайн — ADR-017. Независимая проверка удаления была отдельным необходимым первым запросом, остальные тесты/рендеры запущены после реализации.

| Тема | Наблюдение | Статус |
| --- | --- | --- |
| 1. Удаление | Фикс 6467c50 сохранён. Повторная независимая попытка 114 получила HTTP 429 / Retry-After 156472s за 0.536s; отчёта/usage нет. | Исправление локально проверено; независимое закрытие пока не получено. |
| 2. Search | Структурированные факты с точной цитатой/URL, публикация только после прежнего строгого verifier; явное ограниченное покрытие, найденное/процитированное, неизвестный эффект. | Реальный локальный worker/HTTP/PG проверен; свежей живой генерации нет. |
| 3. Watch/Act | Русский точный предпросмотр без JSON/хешей, текстовые кнопки, состояние паузы/запуска, 202 unknown, сверка/объект провайдера, объяснение повторного подтверждения. | Source/version/owner/full-delivery/grants/no-replay сохранены; внешние эффекты синтетические. |
| 4. Brief | Все ссылки у каждого редакционного пункта; подключения отдельно от материалов; читаемые значения графиков/таблица на телефоне, меньше повторов, безопасный печатный цвет и короткий период. | Immutable identity/даты/источники/private guards сохранены. |

## Результаты единого проверочного блока

| Проверка | Результат | SHA | Команда |
| --- | --- | --- | --- |
| p1 | 2 passed / 16.29s | `97b9388805d3ed5e709705d37e5eca139e18e48b` | `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q tests/test_pai_product_sessions.py::test_large_verified_result_is_losslessly_chunked_and_scope_projection_preserved` |
| search | 58 passed / 83.59s | `aa2002d68012503602d655805264c02f9b26ec59` | `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q tests/test_pai_search_polish.py tests/test_pai_deep_research.py tests/test_pai_archive_search.py tests/test_pai_web_github.py tests/test_assistant_research.py` |
| watch_act | 61 passed / 131.67s | `97b9388805d3ed5e709705d37e5eca139e18e48b` | `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q tests/test_pai_control_polish.py tests/test_pai_scheduler.py tests/test_pai_watch_wiring.py tests/test_pai_action_runtime.py tests/test_pai_delivery.py` |
| brief | 55 passed / 38.82s | `2e541af8e9928e1b1002110e055bd615aa8b5434` | `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q tests/test_pai_brief_polish.py tests/test_pai_brief_runtime.py tests/test_pai_report_runtime.py tests/test_assistant_report_exports.py tests/test_assistant_brief_editorial.py` |
| pai-complete | 390 passed / 871.25s | `2e541af8e9928e1b1002110e055bd615aa8b5434` | `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/test_tiers.py pai-complete` |
| focused-prm | 736 passed / 105.21s | `1f97b8cd2780c4dbeabb2a78c23d0f85a428fdc3` | `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/test_tiers.py focused-prm` |
| retrofit-boundaries | 150 passed / 10.12s | `aa2002d68012503602d655805264c02f9b26ec59` | `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/test_tiers.py retrofit-boundaries` |

Наборы пересекаются: их нельзя суммировать как уникальные случаи. Полный PAI использует strict zero-skip/failure guard, 69 точных IDs и 10 сценариев. Полный исторический pytest не запускался. Pin/план 32 packets/ссылки проверены; формальное принятие дизайна и человеческая полезность этим не объявлены. Выполнены все оставшиеся точные обязательные команды из project_verification.json (без повторного запуска уже проверенных продуктовых tiers): PA/PAI plan, bridge, MAT safety — прошли; playbook contract — прежние 51 TASK_DESIGN_APPROVAL_REQUIRED. Полный project verifier не объявлен прошедшим, manifest не ослаблен.

Исходные failures сохранены: цитата после точки не привязывалась к первому факту; ошибочные ожидания нового теста не совпадали с реальным echo-fixture; короткий Brief прятал длинные ссылки; длинные ссылки в сравнении вытеснили название изменённого пункта. Исправлен код привязки/ссылок; различие «подключение/материал» стало точной новой проверкой. Дополнительно старый overflow-specimen стал помещаться после уменьшения print typography; фикстура увеличена до 8 допустимых цитат, проверки переполнения/полных цитат сохранены, исправленный случай 1/3.81s прошёл. Global verifier, числовые/actor/negation/citation запреты и безопасность не ослаблены. При полной повторной проверке af087f2 exec-сессия завершилась с кодом 143/SIGTERM после 304 progress dots; отправитель/причина сигнала неизвестны, завершённого pytest/spec verdict нет. Это не успешный прогон и не воспроизведённый продуктовый failure. Единственный оставшийся временный PostgreSQL pa-synthetic в окне нашего запуска остановлен по точному PID/root/cluster-marker; папка сохранена, сервисы не затронуты. Повтор запущен на 2e541af отдельным one-shot тестовым recorder со своими PID/PGID, без сервиса/таймера. Мобильная подпись измерена 121.43px при колонке 120px; колонка расширена до 128px и Brief повторно проверен. Устаревший full-run aa2002d после 64 случаев аккуратно прерван SIGINT только у подтверждённого дочернего pytest нашего recorder; итоговый полный прогон запущен на актуальном коде.

## Как теперь выглядит продукт

Пример Search (синтетический HTTP-модельный ответ, без ключа/платной генерации):

```text
Аврора: тест slugify добавлен (https://t.me/source/1002).
Результат пока не измерен (https://t.me/source/1002).

Аврора: тест normalize_email проверяет пробелы и нижний регистр (https://t.me/source/1001).

Покрытие: проверено 1 из 1 запланированных поисковых шагов; найдено материалов: 2; процитировано: 2. Это ограниченная выборка по запросу, а не проверка всего архива или интернета.
Если источник не сообщает о результате измерения, результат остаётся неизвестным.
```

**act**

> Предпросмотр письма
> Из выбранного подключённого аккаунта Microsoft.
> Кому: recipient@example.test
> Тема: Учебная Аврора
>
> Текст письма:
> Работа будет готова завтра утром.
>
> Подтверждение действует до 10.10 07:25 (Europe/Berlin).
> Проверь полный текст и параметры. Нажми «Отправить письмо» или ответь «да».

> Провайдер принял запрос, но выполнение ещё не подтверждено. Автоматически повторять его не буду. Нажми «Проверить результат действия» для отдельной сверки.

> Письмо найдено в «Отправленных». Получение письма адресатом этим не подтверждается.
> Идентификатор объекта у провайдера: synthetic_sent_2

> Повторное подтверждение уже использовано; нового действия не было.
> Провайдер подтвердил операцию с письмом. Получение письма адресатом этим не подтверждается.
> Идентификатор объекта у провайдера: synthetic_sent_2

**watch**

> Предпросмотр наблюдения
> Источник: архив Telegram
> Проверка: каждые 5 мин.
> Сообщать: содержательные изменения
> Часовой пояс: Europe/Berlin
> Не больше 3 сообщений в день. Тихие часы: 22:00–08:00.
> До: 2026-11-09T05:15:12.125511+00:00
> Наблюдение ещё не включено. Нажми «Подтвердить наблюдение».

> Подписка сохранена. Работа планировщика пока не подтверждена; её состояние можно проверить кнопкой.

> Подписка сохранена: активна. Работа планировщика пока не подтверждена. Последняя проверка: проверки ещё не было.

> Подписка приостановлена: новые сборы и отправки остановлены. Уже начатый запрос мог продолжиться.

> Подписка сохранена: приостановлена. Работа планировщика пока не подтверждена. Последняя проверка: наблюдение приостановлено.

> Подписка возобновлена. Фактическую работу планировщика можно проверить кнопкой.

## Рендеры

- [Brief HTML](../../.playbook-artifacts/pai-four-point-20261010/brief-render-current/product-brief.html)
- [PDF](../../.playbook-artifacts/pai-four-point-20261010/brief-render-current/product-brief.pdf)
- [Мобильный светлый вид](../../.playbook-artifacts/pai-four-point-20261010/brief-render-current/mobile-light.png)
- [Мобильный тёмный вид](../../.playbook-artifacts/pai-four-point-20261010/brief-render-current/mobile-dark.png)

Offline Chromium: desktop 1280, mobile 390 light/dark; без внешних запросов, JS ошибок или горизонтального переполнения. На телефоне реальные значения графиков видимы с 16px; таблица перестроена в label/value. PDF: 3 страницы, 0 out-of-page text. Ранее полученная редакционная JSON переотрисована через native private renderer на точных синтетических источниках, новых платных вызовов нет. Это текущая визуальная инспекция, не новый балл внешнего LLM или человеческая приёмка.

## Что остаётся

GLM в Go недоступен: фактический HTTP 429 с Retry-After 156472 секунд указывает ожидание до 12 октября 00:00 UTC / 02:00 по Берлину. Вероятная причина — недельная квота GLM; это вывод по длительности ожидания, не подтверждённая выписка аккаунта. Тариф неизвестен, тело ошибки не сохранено. Go документирует отдельные лимиты каждой модели на 5 часов, неделю и месяц, считаемые по стоимости токенов: [официальные правила](https://opencode.ai/docs/go/#usage-limits). Новых запросов для диагностики не было.

Одна альтернативная независимая read-only проверка Codex запрошена явно, потому что REVIEW_POLICY закрепляет GLM; ответа пока нет и подмена не выполнена. P1-код исправлен, локальные тесты зелёные; независимое закрытие и свежая модельная оценка остаются открытыми. Последний успешный независимый code review — actual112 на cbab0fb, STOP/P1; actual114 относится только к 6467c50 и не оценивает новые изменения 2e541af. Запрошены glm-5.3/max; после 429 наблюдаемые модель/effort/usage неизвестны, отчёта нет. Никаких автоматических повторов, стороннего ключа/провайдера, реальных писем, private source egress, production DB/config/services/timers, master edits или push. UTD/API отложен, реальный mail/calendar test account и Brave key не выбраны.

Следующая безопасная команда для осмотра выбранного read-only entrypoint, без ключа и сетевого вызова: `.venv-pai/bin/python tools/mimo_code_review.py --help`. После восстановления выбранного оценщика или явного альтернативного выбора подготовить один отдельный immutable P1 closure/changed-range packet текущего SHA и выполнить один read-only вызов с действительным verdict/model/effort/usage. Старые скрипты 113/114 не запускать повторно; их результаты неизменны. Старые programme/design batches не возобновлять.

Изменённые файлы:

- `docs/CODEX_PROMPT.md`
- `docs/adr/ADR-017-pa-four-point-polish.md`
- `docs/design/PAI.design.json`
- `docs/design/PAI.md`
- `docs/design/PAI.requirements.json`
- `docs/tasks.md`
- `docs/verification/PAI-progress.md`
- `src/prm/briefs.py`
- `src/prm/report_exports.py`
- `src/prm/runtime/actions.py`
- `src/prm/runtime/composition.py`
- `src/prm/runtime/delivery.py`
- `src/prm/runtime/ingress.py`
- `src/prm/runtime/presentation.py`
- `src/prm/runtime/research.py`
- `src/prm/runtime/research_answer.py`
- `src/prm/runtime/scheduler.py`
- `src/prm/runtime/transports.py`
- `tests/test_assistant_brief_editorial.py`
- `tests/test_assistant_briefs.py`
- `tests/test_pai_brief_polish.py`
- `tests/test_pai_control_polish.py`
- `tests/test_pai_product_sessions.py`
- `tests/test_pai_search_polish.py`
- `tools/test_tiers.py`

Дополнительно обновлены текущий handoff и датированный журнал; новые документы доказательств: PAI-four-point-20261010.md/.json. Код и тесты после проверенного 2e541af не менялись.
