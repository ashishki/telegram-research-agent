# Go: текущая проверка и подготовка пилота — 2026-10-10

Проверенный код `0fbcfd1dde780724ad934aa66825afe17a6efc98`. Задание — выбрать другую модель Go, продолжить оценку и пилот; затем владелец включил extra usage. ADR-018 фиксирует границы. Все модельные данные — публичный код или синтетические сведения, реальные аккаунты/архив не использованы.

## Независимая безопасность

- Actual115: DeepSeek Pro вернул HTTP429/GoUsageLimitError, ожидание148122s; исходный отказ сохранён.
- После включения extra usage actual116 завершился за890.457s, usage232712/40027/272739, requested max / observed effort unknown. Он явно закрыл исходный P1 удаления, но нашёл новый P1 multipart delivery: старый reconcile восстанавливал другие HTML границы и кнопки.
- Шесть регрессий воспроизвели ошибку (6 failed/44.95s). Общий _multipart_payloads теперь формирует и отправляемые, и сверяемые части; нет повторных отправок, отсутствие поздней части не становится отсутствием всего эффекта.
- Actual117 на текущем SHA: ADVISORY,470.397s,usage49125/19472/68597; multipart P1 закрыт, новых P0/P1 в проверенном объёме нет. Исходный116 STOP остаётся историческим STOP; его не переписали как PASS.
- Один P2: экстремальная вложенность HTML может создать часть сверх transport bound. Он сохранён; текущие проверенные шаблоны не являются проверкой произвольной глубины. Нет human/release acceptance.

## Тесты

| Набор | Результат |
| --- | --- |
| Исправленная доставка/controls | 43 passed /127.72s |
| Brief/export/product sessions | 77 passed /100.04s |
| Recovery/end-to-end | 33 passed /260.43s |
| Полный активный PAI | 398 passed /1164.34s; zero skips/failures;69 IDs/10 сценариев |
| Новый Go transport + существующий governed transport/plan/bridge | 195 passed /6.50s перед модельным запросом |

Это пересекающиеся наборы, их нельзя складывать в уникальное количество. Полный исторический pytest не запускался. Точные argv/environment/source SHA/log hashes — в JSON. Старые736 PRM/150 retrofit относятся к своим предыдущим SHAs и не объявлены свежим полным прогоном.

## Реальная генерация и оценка диалогов

Legacy DeepSeek V4 Flash дал3 отказа403 Model access is disabled в двух независимых capture workloads; запросы не выдаются за рабочую генерацию. Выбран актуальный DeepSeek V4.1 Flash на том же Go endpoint. Получены11 настоящих ответов: min1.21s,median1.753s,max5.237s; это development benchmark с явным30s model deadline, не production SLO или deployed model selection.

Шесть native сессий/25 ходов: Chat, редактирование/смена адресата, Search, Brief, Watch, Act. Search действительно synthesized_verified с exact URL/quotes,2 найденными и2 процитированными материалами и ограничением по запросу. Brief создан новой моделью и экспортирован native HTML/PDF/Markdown. Watch: один локальный tick/сбор1 изменения/одна synthetic доставка; после паузы новой задачи нет. Act: одна synthetic Graph write,202 unknown, отдельная сверка, повтор подтверждения без новой записи.

DeepSeek Pro оценил полные записи и фактический Markdown Brief:201.587s,usage8592/10683/19275,requested max/observed unknown. Диагностический порог4 на каждой из8 осей выполнен6/6 сессиями.

| Диалог | Минимальная ось | Среднее8 осей | Сырой вердикт |
| --- | --- | --- | --- |
| context_and_topic | 4 | 4.875 | pass |
| editing_and_context_repair | 5 | 5.000 | pass |
| archive_research | 5 | 5.000 | pass |
| weekly_brief | 5 | 5.000 | pass |
| confirmed_action | 5 | 5.000 | pass |
| watch | 5 | 5.000 | pass |

Это новый benchmark: сменились генератор и оценщик, а контролы стали естественными. Сравнение с прежними3/6 не является matched causal measurement. Оригинальные замечания оценщика сохранены. Его предположение о «третьем найденном источнике» не совпадает с ограниченным FTS-запросом, который вернул2; счётчик не изменён ради оценки. Source corpus size, query matches и cited count различаются. Состояния Watch/Act рассчитаны реальным native кодом/PG; источники и внешние эффекты синтетические. Получение письма адресатом и запуск после resume не заявлены.

Полный публичный input оценщика сохранён в PAI-go-pilot-session-judge-20261010.input.txt с manifest/hash рядом; не содержит реальной переписки/ключей.

## Рендеры и визуальная оценка

Экспериментальный DeepSeek Vision вернул403 Model access is disabled; этот отказ сохранён. Kimi K2.7 Code сначала оценил старые текущие рендеры на4/5 и указал реальные обрезанные заголовки источников/разные cover metrics. Источники теперь полные, обе формы используют одни factual KPI; identity/source/overflow guard сохранены.

Повтор Kimi на исправленном renderer и точном прежнем MiMo editorial JSON:84.257s,usage8927/2172/11099,pass; PDF legibility/pagination/source visibility/dark theme5, mobile layout/visual hierarchy4. Не переименовывать это в визуальную оценку нового DeepSeek editorial content.

Новый Brief из актуальной реальной V4.1 генерации отдельно проверен offline browser/PyMuPDF:5 PDF страниц,0 out-of-page text,0 JS/horizontal errors; светлый/тёмный mobile390 и desktop1280. Старый fixed-content re-render:3 страницы, также без выхода текста. Разное число страниц соответствует разному редакционному содержимому, не потере источников.

- [Новый AI Brief HTML](../artifacts/pa-20261010/fresh-ai/product-brief.html)
- [Новый AI Brief PDF](../artifacts/pa-20261010/fresh-ai/product-brief.pdf)
- [Мобильный вид](../artifacts/pa-20261010/fresh-ai/mobile-light.png)
- [Контролируемый renderer comparison PDF](../artifacts/pa-20261010/renderer-benchmark/product-brief.pdf)

## Публичные подключения и настоящий пилот

Native scoped GitHub read подтвердил README.rst наe4f7f174bc4a1686b31639d29a3e211941390979 за0.752s; Python unittest HTTP200/336954bytes за0.378s. Первый измеритель ошибочно извлёк observed_ref как null; исходный замер сохранён и только GitHub измеритель повторён после исправления поля. Это fetch/exact-ref, не Brave discovery.

Future-clock fixture у первого Watch capture правильно получила отказ delivery not due. Модельная генерация Search/Brief этого capture сохранена. Только controls повторены с wall/DB clock: никакого ослабления runtime guard и дополнительных inference ради исправления измерителя.

[Конкретный пакет20 задач и подключения](PAI-pilot-access-20261010.md): тестовые Telegram/mail/calendar/resource/destination ещё не выбраны; вопрос отправлен, настройки не получены. SyntheticTarget не объявлен production/private-data target. Реальные письма/записи, production migrations/config/services/timers, private model egress, master/push не выполнялись. UTD/API отложен. Формальные role/design/human gates остаются, новая инженерная advisory проверка их не подменяет.

Следующая безопасная команда: `PYTHONPATH=src .venv-pai/bin/python -m prm.cli --help`. После выбора реальных test resources составить exact private-config canary command и предъявить точный preview перед внешним эффектом. Не запускать старые115/116/117 скрипты повторно и не возобновлять programme/design batches.

Изменённые исходники после предыдущей проверки:

- `docs/CODEX_PROMPT.md`
- `docs/REVIEW_POLICY.md`
- `docs/adr/ADR-018-pa-go-pool-pilot.md`
- `docs/design/PAI.design.json`
- `docs/tasks.md`
- `src/prm/report_exports.py`
- `src/prm/runtime/delivery.py`
- `tests/test_opencode_pool_review.py`
- `tests/test_pai_brief_polish.py`
- `tests/test_pai_control_polish.py`
- `tools/opencode_pool_review.py`
- `tools/test_tiers.py`
