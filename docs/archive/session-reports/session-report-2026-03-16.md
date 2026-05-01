# Session Report — 2026-03-16

## Что было сделано за сессию

Полный цикл от архитектурного замысла до работающей продакшн-системы на VPS.

---

## Фазы реализации

### Phase 0 — Архитектура
Написаны контрактные документы до первой строки кода:
- `docs/spec.md` — 21 секция, полная спецификация системы
- `docs/architecture.md` — компонентная карта, layer contracts
- `docs/tasks.md` — task graph с зависимостями (P0–P9)
- `docs/dev-cycle.md` — роли: Strategist (Claude), Implementer (Codex), Reviewer (Claude)
- `docs/ops-security.md` — threat model, secrets management, systemd hardening

### Phases 1–9 — Основной MVP
Все фазы реализованы через цикл: Codex пишет → Claude ревьюит → Codex фиксит.

| Фаза | Ключевые файлы |
|---|---|
| 1 — Scaffold | schema.sql, migrate.py, client.py, main.py, settings.py |
| 2 — Bootstrap | telegram_client.py, bootstrap_ingest.py (90 дней, FloodWaitError) |
| 3 — Normalization | normalize_posts.py (FTS5, language detection) |
| 4 — Topic Detection | cluster.py (TF-IDF+KMeans), detect_topics.py (LLM labeling) |
| 5 — Weekly Pipeline | incremental_ingest.py, systemd timers (пн 07:00) |
| 6 — Digest | generate_digest.py, systemd timer (пн 09:00) |
| 7 — Recommendations | generate_recommendations.py |
| 8 — Project Mapping | map_project_insights.py (FTS5 + relevance scoring) |
| 9 — Hardening | healthcheck.sh, retry logic, WAL mode, structured logging |

### Phase 10 — GitHub Integration
- `github_sync.py` — читает все репо (публичные + приватные через token), синхронизирует в `projects`
- `github_crossref.py` — матчит стек репо с Telegram-темами
- `generate_insight.py` — ретроспектива: что из 90 дней релевантно проектам
- Дайджест дополняется секцией "Your Projects × Telegram"
- Команда `insight --since-bootstrap`

### Phase 11 — Telegram Bot
Long-polling бот на `urllib` без сторонних библиотек:
- `/digest`, `/topics`, `/insight`, `/project`, `/ask`, `/run_digest`, `/status`
- Только owner (фильтр по chat_id)
- Авто-отправка дайджеста после генерации
- `systemd/telegram-bot.service` с `Restart=on-failure`

### Phase 12 — Cost Tracking
- Таблица `llm_usage`: каждый LLM-вызов → category, model, tokens, cost_usd, duration_ms
- Ценовой справочник для haiku/sonnet/opus
- `/costs` в боте: all-time, по категориям, по месяцам

### Phase 13 — Study Plan + Reminders
- `generate_study_plan.py` — 3-часовой план обучения с оценкой сложности для junior+
- Fetch книг из `github.com/marangelologic/books` (API)
- Конкретные ссылки: arxiv, GitHub, YouTube, official docs
- Вт 10:00 + Пт 10:00 — напоминания через systemd timers
- Команда `/study` в боте

---

## Ключевые архитектурные решения

**AD-01: Telethon вместо Bot API**
Bot API не даёт доступа к истории каналов. Telethon (MTProto) читает каналы от имени пользователя.

**AD-02: SQLite + FTS5 вместо внешней БД**
Один файл, WAL mode для concurrent reads, FTS5 для полнотекстового поиска. Достаточно для объёмов 10k–100k постов.

**AD-03: Anthropic SDK напрямую, не через OpenClaw gateway**
OpenClaw gateway написан на TypeScript с кастомным WebSocket-протоколом. Python-клиента нет. Решение: `anthropic` SDK + `LLM_API_KEY` из env. Архитектура готова к переключению за один параметр.

**AD-04: Роутинг моделей по категории задачи**
- Haiku: topic_detection (×8/нед, простой JSON)
- Sonnet: digest, recommendations, study_plan, bot_ask (глубокий синтез)
- Переключение без изменения кода: env var `LLM_MODEL_{CATEGORY}`

**AD-05: Codex для кода, Claude для ревью**
Строгое разделение ролей. Codex (gpt-5.4) пишет и фиксит. Claude (Agent/Explore) ревьюит по чеклисту. Ни разу не смешивали роли.

---

## Баги найденные и исправленные

| Баг | Причина | Фикс |
|---|---|---|
| Codex stdin 401 | `codex exec -` форсит модель gpt-5.3-codex | Передавать промт через shell variable |
| settings.py default session path | `data/telegram.session` внутри workspace | Исправлено на `/srv/openclaw-you/secrets/telegram.session` |
| normalize_posts.py `break` | Останавливал все батчи при ошибке одного | Заменено на `continue` |
| systemd `Group=users` | Неправильная группа в Phase 5 | Исправлено на `Group=oc_you` |
| Phase 6: `from datetime import UTC` | Python 3.10 не поддерживает | `from datetime import timezone` + `timezone.utc` |
| Отсутствует `PYTHONPATH` в systemd units | ImportError при запуске от oc_you | Добавлено `Environment=PYTHONPATH=...` |
| LLM возвращает JSON в markdown fence | Модель игнорирует "return JSON only" | `_strip_code_fence()` перед `json.loads()` |
| Session file owned by root | Сессия создана от root, сервисы запускаются от oc_you | `chown oc_you:oc_you telegram.session` |
| GitHub API возвращает только публичные репо | `/users/{u}/repos` — только public | С токеном: `/user/repos` — все репо |
| `auth_telegram.sh` EOFError | heredoc перехватывал stdin у Python | Скрипт пишет py-файл во temp и запускает через `exec` |

---

## Состояние системы на момент завершения сессии

```
Постов в БД:    2 376 (19 каналов, 90 дней)
Тем:            7
Проектов:       24 (синхронизированы с GitHub ashishki)
LLM-вызовов:   9
Потрачено:      $0.0702
```

**Запущенные сервисы:**
- `telegram-bot.service` — active (running)
- `telegram-ingest.timer` — пн 07:00
- `telegram-digest.timer` — пн 09:00
- `telegram-study-reminder-tue.timer` — вт 10:00
- `telegram-study-reminder-fri.timer` — пт 10:00

---

## Что не сделано (намеренно отложено)

- Векторные эмбеддинги (FTS5 достаточен для текущего объёма)
- Ретроспективный дайджест за 90 дней (заменён на `insight --since-bootstrap`)
- Multi-user режим (не нужен для личного использования)
- OpenClaw gateway интеграция (нет Python SDK)

---

## Как описать в резюме

**AI Engineer / Backend:**
> Built an autonomous AI research assistant monitoring 19 Telegram channels (2,000+ posts/week). Stack: Python, Anthropic Claude API with multi-model routing (Haiku/Sonnet by task complexity), Telethon MTProto, SQLite/FTS5, scikit-learn. Features: topic clustering, weekly digest generation, GitHub project cross-referencing, personalized study plan with real links, Telegram bot interface, per-category LLM cost tracking. Deployed on Linux VPS with systemd timers and service hardening.

**Software Engineer:**
> Designed and shipped a production Python system: async ingestion pipeline, idempotent schema migrations, WAL-mode SQLite, long-polling Telegram bot, systemd services/timers. Contract-first architecture with automated Claude+Codex review cycle. 3,000+ lines across 30+ modules.

---

## Будущие фичи (приоритизировано)

### Высокий приоритет
1. **Векторный поиск** — заменить FTS5 на эмбеддинги (`nomic-embed-text` локально или `text-embedding-3-small`). Даст семантический `/ask` вместо keyword-match.
2. **Feedback loop** — `/done`, `/useful`, `/skip` в боте. LLM учится на твоих оценках при следующей генерации плана.
3. **arXiv + HN как источники** — добавить RSS-парсер рядом с Telegram ingestion. Одна таблица `raw_posts`, разные `channel_username`.

### Средний приоритет
4. **Граф тем во времени** — как темы появляются, растут, умирают неделя к неделе. Визуализация через ASCII или экспорт в Obsidian Canvas.
5. **Breaking news** — polling high-priority каналов каждые 4 часа. Уведомление если тема набирает >N постов за <24 часа.
6. **Прогресс-трекер** — отметить блоки плана как выполненные. Persistence в `study_plans` таблице.

### Стратегический
7. **Агент-исследователь** — `/research <тема>` → ReAct loop: ищет статьи, читает GitHub, синтезирует ответ. Требует browser tool или серверный fetch.
8. **OpenClaw gateway** — когда появится Python SDK, переключить LLM-вызовы. Архитектура уже готова (один параметр в `client.py`).
