# Модели и доказательство качества

Срез публичных первичных источников: 11 октября 2026. Платных inference и проверок личной квоты в этом исследовании нет. «Опубликована в каталоге», «доступна конкретному аккаунту», «совместима с нашим transport» и «полезна в продукте» — четыре разные проверки.

## Текущая отправная точка

Новый production профиль неизвестен; код принимает явную конфигурацию. Прежний `src/llm/client.py` содержит Sonnet/Haiku/Opus defaults. Последний реальный synthetic capture — **DeepSeek V4.1 Flash**: 11 ответов, median 1.753 s, диапазон 1.21–5.237 s, deadline 30 s. Это model-call latency маленькой выборки, не end-to-end p95. Текстовый судья DeepSeek V4 Pro оценивал 6 сессий/25 ходов; vision Kimi K2.7 Code — фиксированный renderer dataset. Полного сравнения с GPT-4o нет. [Датированное доказательство](../../verification/PAI-go-pilot-20261010.md).

Прежние DeepSeek V4 Flash и experimental vision дали account-level 403; Pro первоначально дал quota 429, затем работал после включения extra usage. Эти результаты относятся к 10 октября и не исчезают из-за появления названия в каталоге. GLM/MiMo результаты имеют другие наборы/настройки и не дают честной сравнительной таблицы качества.

## Что сейчас опубликовано в OpenCode Go

В открытом [models endpoint](https://opencode.ai/zen/go/v1/models) наблюдалось 45 ID. Следующий список — каталог, не разрешение аккаунта:

```text
minimax-m3, minimax-m2.7, minimax-m2.5
kimi-k3, kimi-k2.7-code, kimi-k2.6, kimi-k2.5
longcat-2.0, longcat-2.5-preview-free
glm-5.3-flash, glm-5.3, glm-5.2, glm-5.1, glm-5
deepseek-v4.1-flash, deepseek-v4-pro, deepseek-v4-flash,
deepseek-flash, deepseek-v4-flash-vision-exp
qwen3.8-max, qwen3.8-flash, qwen3.7-max, qwen3.7-plus,
qwen3.6-plus, qwen3.5-plus
mimo-v2.6-flash, mimo-v2.6-pro, mimo-v2.5, mimo-v2.5-pro,
mimo-v2-pro, mimo-v2-omni
step-5-preview-free, hy4-preview, hy3, hy3-preview
claude-haiku-5-5, gpt-6-luna, gpt-5.6-luna
grok-4.7, grok-4.6, grok-4.5
muse-spark-1.3-contributor, muse-spark-1.2-contributor
omen-alpha, space-bunny
```

Публичная документация перечисляет 32 текущие позиции, API дополнительно возвращает старые/иные ID. Не выбирать дополнительные aliases автоматически. Прямой анонимный HTTP GET из shell здесь получил 403; web-инструмент прочитал JSON. Это различие сетевых путей, **не проверка пользовательской подписки**. Endpoint не дал в этом просмотре полноценной матрицы context/tool/modality/effort — эти поля нельзя придумать по имени модели.

Ниже компактные опубликованные тарифы для shortlist, USD за миллион токенов; фактический счёт не измерен. Порядок чисел: input / cached input / output. Go-квота — долларовый лимит учёта модели, не количество денег на весь аккаунт. [OpenCode Go, раздел Usage limits](https://docs.opencode.ai/docs/go/#usage-limits).

| ID | Тариф | Go в месяц | API |
| --- | --- | --- | --- |
| deepseek-v4.1-flash | 0.15 / 0.003 / 0.60; peak ×2 | 60 | Chat |
| deepseek-v4-pro | 0.66 / 0.022 / 1.98; peak ×2 | 15 | Chat |
| glm-5.3-flash | 0.15 / 0.03 / 0.50 | 60 | Chat |
| glm-5.3 | 1.40 / 0.26 / 4.40 | 15 | Chat |
| mimo-v2.6-flash | 0.14 / 0.0028 / 0.28 | 60 | Chat |
| mimo-v2.6-pro | 0.435 / 0.003625 / 0.87 | 15 | Chat |
| kimi-k2.7-code | 0.95 / 0.19 / 4.00 | 60 | Chat |
| kimi-k3 | 3.00 / 0.30 / 15.00 | 15 | Chat |
| gpt-6-luna | 0.10 / 0.01 / 0.50, ≤272K | 15 | Responses |
| gpt-4o, direct OpenAI | 2.50 / 1.25 / 10.00 | не Go | Chat/Responses |

Go/Plus стоят $10/$40. Окна модели: 5h=20%, неделя=50%, месяц=100%; Use balance расходует дополнительный баланс. DeepSeek peak: рабочие дни 01–04 и 06–10 UTC. Go ориентирован на coding-agent traffic и просит собственный User-Agent и стабильный `x-opencode-session`. DeepSeek ZDR действует до 31.10.2026 с ежемесячным продлением; Muse Contributor использует данные для обучения. [Go](https://docs.opencode.ai/docs/go/).

GPT-4o: text/image→text, context 128K, max output 16,384; snapshot фиксировать явно. Указанный тариф и возможности — из [карточки GPT-4o](https://developers.openai.com/api/docs/models/gpt-4o). Audio требует другого endpoint/model. Direct OpenAI API не использует API-данные для обучения по умолчанию; стандартные abuse logs могут храниться до 30 дней, ZDR требует соответствующей доступности и имеет исключения. `store:false` не равно отсутствию любых логов. [Data controls](https://developers.openai.com/api/docs/guides/your-data).

### Вывод для этого продукта

Go остаётся кандидатом для согласованных нагрузок и сравнений. **Не делать подписку единственной зависимостью личного ассистента.** Текущая формулировка coding traffic не устанавливает явно пригодность постоянного mail/news assistant. До такого использования выяснить допустимость конкретной нагрузки по условиям сервиса; если подтверждения нет, выбрать обычный inference API с подходящими условиями. Не имитировать чужой coding client заголовками. Это provider decision, не причина остановить независимые код, fixtures и оценочный harness.

Для private egress нужен versioned provider policy: допустимые data classes/purposes, retention/training, region/subprocessor facts при наличии, source URL, checked_at, policy expiry, model aliases и fallback set. Отсутствующее поле остаётся unknown. Модель через Go и та же модель напрямую — разные маршруты данных и договорённости. Нельзя перенести Go ZDR на direct DeepSeek или direct OpenAI policy на посредника.

Истекающее соглашение должно отзывать соответствующий private route либо переключать на заранее разрешённый equivalent route; не открывать новую передачу данных автоматически. Шаблон политики не создаёт согласие владельца. Для публичных и synthetic тестов можно оставить более широкий отдельный allowlist. Не использовать training/contributor или анонимную экспериментальную модель для личных писем по умолчанию.

## Предлагаемое распределение ролей

Все назначения ниже — проверяемые гипотезы. Наблюдавшийся Flash — инженерный baseline, а не объявленный победитель. Скорость, русский язык и работа с источниками оцениваются на наших задачах; coding benchmark провайдера не решает этот выбор.

| Роль | Baseline и кандидаты | Правило выбора |
| --- | --- | --- |
| Разговор, переписывание, объяснение | V4.1 Flash против GPT-4o; challengers GLM-5.3-Flash и MiMo-V2.6-Flash | Выбрать минимальную end-to-end стоимость среди прошедших качество/continuity/latency, а не самую низкую цену токена. |
| Planner и извлечение структур | Сначала тот же основной baseline; сравнить GLM Flash/MiMo Flash | Короткий schema-bound output. Authority, budgets, дата API и execution остаются детерминированными. Малый planner не должен ухудшать всю цепочку. |
| Исследование и редактура Brief | Flash baseline против DeepSeek Pro, MiMo Pro, Kimi K2.7 Code; Kimi K3 — challenge на трудных случаях | Сильная модель используется, когда измерен выигрыш в применимости/полноте. Separate workload `brief_editorial`, сейчас он скрыт под research. |
| Проверка claims | Exact IDs/quotes/numbers/versions кодом; semantic entailment — отдельный ограниченный verifier | Судья не отменяет policy и не подтверждает источник, которого нет в packet. При uncertainty частичный ответ/проверка, а не уверенная рекомендация. |
| Текстовый судья | Для DeepSeek generator — GPT-4o либо Kimi/GLM после калибровки; Pro сохранить для повторяемости прежнего benchmark | Разные семейства уменьшают один источник корреляции, но не доказывают независимость ошибки. Blind/paired/human calibration обязательны. |
| Vision/PDF | Kimi K2.7 Code как наблюдавшийся baseline против GPT-4o image | Реальные mobile/dark/PDF screenshots, не HTML source. Experimental DeepSeek Vision исключён из рабочего baseline до нового успешного canary. |
| Голос/OCR | Существующие scoped seams; локальный text extraction первым | Выбирать отдельным экспериментом на RU/EN audio, именах и датах; текстовая модель не доказывает наличие ASR. |
| Embeddings/rerank | FTS baseline; локальный BGE-M3 кандидат | [Первичная карточка BGE-M3](https://huggingface.co/BAAI/bge-m3) описывает multilingual dense/sparse retrieval. Проверить RAM/latency/recall на хосте; не объявлять текущие hashed vectors learned semantics. |

Qwen/MiniMax/Haiku/Grok/Luna добавлять в следующий раунд, если протокол поддержан и первый shortlist не закрывает задачу. Новые Responses/Messages adapters строить по выбранной роли, а не ради проверки всех 45 ID. Space Bunny/Omen/временные preview — исследовательские кандидаты после проверки provenance, не default.

### Стоимость и доступность

Считать отдельно: subscription fee; billed overage; стоимость токенов по опубликованному meter; auxiliary/judge calls; search/OCR/storage; собственное время. `cost_per_success = total attributable cost / успешно решённые задачи`, включая неудачные attempts и retries. Unknown charge не превращать в ноль. Скидку подписки не распределять пропорционально выдуманному использованию.

Пример расчёта, **не замер**: 8000 uncached input +1000 output дают $0.0018 у Flash вне peak и $0.03 у direct GPT-4o. Это отношение тарифов для одного одинакового вызова. Длинное reasoning, лишний поиск, повтор генерации и худшее качество могут изменить стоимость успешной задачи. Для monthly forecast использовать реальное распределение количества calls и output, а не рекламные requests/5h, рассчитанные на другой cache hit rate.

Transport обязан сохранять requested/observed model, endpoint protocol, stop reason, usage semantics, cached/reasoning tokens, time to first output при наличии, total time, error category и tariff version. Exact alias mapping допускается только по записанному model registry; нельзя просто убрать проверку модели. Неподдержанный параметр или 403 — явное unsupported/unavailable, 429 — cooldown/quota, timeout — отдельная неопределённость оплаты. Никакого бесконечного failover или автоматической смены privacy class.

## Исполнимый эксперимент

1. **Offline до доступа.** D06/D35: frozen cases, expected constraints, sanitized source snapshots, trace schema; replay через реальный ingress/worker/application с fake I/O. Подготовить точную смету и provider/data allowlist. Не выполнять платные вызовы из unit tests.
2. **Capability canary после выбора доступа.** Один короткий synthetic text/JSON/tool/schema/image test на нужную способность модели; записать 403/429/timeout как результат. Для обычного text-only provider не требовать vision. Отдельно проверить protocol/token parameters, alias echo, auth error redaction и запрет redirects. Доступность аккаунта не выводить из `/models`.
3. **Screening.** 12 фиксированных representative cases, до 6 кандидатов плюс GPT-4o и Flash при их доступности, одинаковые source/context budgets. Это фильтр явных провалов, не ranking с точной статистикой. Перемешать порядок и окна времени, отделить cold/warm cache.
4. **Matched comparison.** Лучшие 2 challengers, Flash baseline и GPT-4o; 120 независимых единиц holdout, описанных ниже. Context, source versions, инструменты и stop conditions одинаковы; model-specific prompts только после общей baseline версии и с отдельным ablation. Для nondeterminism повторить заранее выбранные 20% случаев, а не только неудачи конкурента.
5. **Online после read canary.** Один baseline и один challenger на разрешённых данных, сначала shadow без лишних сообщений/действий. Владелец видит один результат; диагностическое хранение согласовано. Если трафик дублировать нельзя — чередовать полные задачи по заранее заданному порядку.
6. **Promotion.** Нет новых критических ошибок; пройдены per-axis floors, нет значимого ухудшения task success, privacy и latency; полезность подтверждена. Если интервалы перекрывают практически значимый порог, оставить baseline или расширить выборку. Не выбирать по среднему 4.9 против 4.8.

Смета строится до inference из числа cases/turns/candidates/repeats и максимального input/output, отдельно judge. Sessions — много вызовов, не один. Действующий grant определяет бюджет; это исследование не задаёт новый расход. Если access/budget недоступен, оставить эксперимент prepared и явно назвать неподтверждённый выбор.

## Набор задач и метрики

120 единиц: 40 простых Chat/edit/context; 30 поисковых и исследовательских задач; 16 наборов недельных материалов; 20 целых диалогов по 10–20 ходов; 14 Watch/Act lifecycle сценариев. Внутри группы нужны RU/EN, ambiguity, source conflict/absence, source outage, незаметная смена темы и adversarial content. Делить train/dev/holdout по исходным документам и сценариям, а не по перефразированным репликам; шаблоны тестов, использованные для фикса, не становятся независимым holdout.

| Слой | Метрика и предлагаемый gate |
| --- | --- |
| Task success | Простой ≥95%, сложный ≥90% на согласованном holdout; числа успехов/denominator и Wilson interval обязательно. На малом наборе это диагностический порог, не доказанная вероятность в эксплуатации. |
| Источники | Supported factual claims / все проверяемые factual claims ≥98%; одновременно coverage обязательных gold facts ≥90%, чтобы молчание не давало идеальный score. Отдельно citation validity и semantic support. |
| Retrieval | Recall@20, nDCG@10, MRR для exact lookup, no-answer false positive; RU→EN отдельно. Релевантность размечена до оценки моделей. |
| Research | Решён ли вопрос, рассмотрены ли необходимые аспекты, различены ли факт/вывод/совет, актуальность, diversity независимых источников, стоимость и доля полезных partial. |
| Brief | Recall важных gold events, precision выбранных событий, duplicate rate, novel-to-owner, проектная применимость, reading time; важность выбирает человек, не generator. |
| Диалог | Полное завершение session; правильная object/version binding; сохранение исходных ограничений; topic switch; исправление ошибки; unnecessary questions; правильный cancel. Средний score ходов не заменяет успех всей цепочки. |
| Watch/Act | Ноль unauthorized effects/replays/ложных critical deadlines в обязательном наборе; timely useful notifications, unknown reconciliation. Модель не присуждает safety PASS. |
| UX/скорость | Intake p95 ≤2s, Chat ≤10s, обычный Search ≤45s как исходные цели; compute queue и provider time отдельно. Long tasks показывают checkpoints и доступны отмене. |
| Ресурсы | Стоимость успешной задачи, quota failures, cache hit rate, пиковая память, доля ручных исправлений и operator maintenance time. |

Все thresholds — предлагаемые критерии, унаследованные либо уточняющие спецификацию, не нынешние показатели. Если задача в этой сессии не тестировалась, её метрика unknown.

## Как должен работать LLM-судья

Judge packet: полная задача/диалог с видимыми ответами, точные input sources/excerpts/page refs и даты, tool results/status/errors, разрешённый контекст проекта, ожидаемые ограничения и фактически выполненные эффекты, coverage/omissions. Секреты и реальные приватные payloads в публичный packet не попадают. Для Brief нужен также candidate set, иначе судья не обнаружит пропущенное главное. Для диалога — все ходы и ссылки на объекты, не только последний красивый ответ.

Выход: оценки 1–5 по заданным осям, список ошибок с turn/claim/evidence ref, тяжесть, `assessable` и причина unknown, pairwise winner/tie при сравнении. Нужна короткая проверяемая аргументация, не скрытый chain-of-thought. Если источник не предоставлен, groundedness unknown, даже если URL правдоподобен. Формат/schema validation отдельно от качества вердикта.

Рубрики: 1 — ответ неверен/не выполняет задачу; 3 — помогает частично, нужна заметная переделка; 5 — решает задачу точно и удобно. Оси для Chat: task completion, fidelity, continuity, clarity. Для Search: support, coverage, freshness, synthesis. Для Brief: selection, personal applicability, novelty, actionability, reading burden. Для session: устойчивость контекста, корректность переходов, контроль действий, завершённость. Любой критический неверный срок/адресат/unauthorized effect блокирует promotion независимо от среднего.

### Проверка самого судьи

Отдельный calibration set: минимум 40 пар с человеческими предпочтениями и 20 намеренно испорченных примеров — смена отрицания/числа/адресата, цитата не к тому утверждению, пропущенный важный event, ложный «отправлено», prompt injection в источнике. Это не те же случаи, на которых настроили prompt. Владелец размечает компактную репрезентативную часть; технические ошибки готовит и проверяет исполнитель. Полезность для владельца нельзя заменить мнением разработчика.

Скрыть названия моделей, случайно менять A/B и повторять в обратном порядке, проверять короткие/длинные эквивалентные ответы, одинаковые ответы, стиль и инъекции с требованием поставить 5. Минимальные диагностические gates: ≥80% agreement с human preferences, ≥90% order consistency, ≥90% repeat consistency, ноль пропущенных заранее размеченных критических ловушек. Показывать confidence intervals и confusion matrix; эти числа при малом n не гарантируют безопасность. Низкое согласие означает пересмотр rubric/packet/judge, а не исправление human labels под модель.

На 20% новых paired cases нужен второй судья другой семьи; разногласия и critical flags идут на human adjudication. Повторная калибровка после смены judge alias, prompt, parser или источников. Не оценивать самим генератором собственные ответы как единственным мерилом. Position/verbosity/self-enhancement biases документированы в [исследовании MT-Bench](https://arxiv.org/abs/2306.05685); наш контроль должен доказать устойчивость именно на этом продукте.

Visual judge — отдельный набор actual screenshots/PDF pages на 390px/desktop, light/dark, длинные заголовки/ссылки/кириллица. Он оценивает читаемость/иерархию/источники. Детерминированные проверки полноты страниц и фактов остаются. Финальное восприятие на телефоне подтверждает владелец.

## Граница готовности

Одна таблица результатов должна показывать code, fixture, provider canary, matched eval, visual и owner pilot отдельно. Не складывать пересекающиеся тесты; не объявлять пропуски PASS; сохранять failures. Удачный модельный judge не даёт разрешения на deployment, личные данные или внешний effect. Следующий исполнитель получает эксперимент и критерии, а не неподтверждённого «лучшего поставщика».
