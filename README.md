# Telegram Research Agent

Персональная AI-система для непрерывного мониторинга технологического ландшафта через Telegram-каналы. Агент автоматически собирает посты, кластеризует темы, генерирует структурированный дайджест по 5 категориям и project-specific инсайты — всё доступно через Telegram-бота.

---

## Что это и зачем

Проблема: в AI/tech пространстве ежедневно выходят сотни постов. Читать всё — невозможно. Пропустить важное — легко. Связать происходящее в индустрии со своими проектами — ещё сложнее.

Решение: агент делает это автоматически. Каждую неделю он:
- Забирает новые посты из 19 Telegram-каналов
- Кластеризует их в темы (TF-IDF + KMeans, без LLM, с поддержкой русского и английского)
- Генерирует дайджест по 5 категориям (Claude Sonnet) — ≤3500 символов, Telegram HTML
- Находит инсайты для 4 активных проектов (Implement/Build типы)
- Присылает дайджест + инсайты двумя сообщениями в Telegram каждый понедельник

---

## Архитектура

```
Telegram MTProto (Telethon)
    ↓
SQLite (WAL mode, FTS5, message permalinks)
    ↓
TF-IDF + KMeans → тематические кластеры (RU+EN stopwords)
    ↓
Anthropic Claude API (Haiku / Sonnet — роутинг по задаче)
    ↓
ResearchReport JSON → Markdown → Telegram HTML (5 категорий, ≤3500 символов)
    ↓
Telegram Bot (long-polling, только owner)
```

**Стек:** Python 3.10, Telethon, scikit-learn, Anthropic SDK, SQLite, Jinja2, WeasyPrint, systemd

---

## Возможности

| Команда бота | Что делает |
|---|---|
| `/digest` | Дайджест текущей недели — текст (5 категорий, Telegram HTML) |
| `/topics` | Список обнаруженных тем с весами |
| `/study` | 3-часовой план обучения с книгами и ссылками |
| `/insight` | Что из 90 дней истории релевантно твоим проектам |
| `/project <name>` | Конкретный проект × Telegram-темы |
| `/ask <вопрос>` | Свободный вопрос по корпусу постов |
| `/costs` | Статистика расходов на LLM по категориям |
| `/status` | Состояние системы |

**Автоматика:**
- Пн 07:00 — инкрементальный парсинг всех каналов
- Пн 09:00 — генерация дайджеста + инсайтов + отправка двумя сообщениями в бот
- Вт 10:00, Пт 10:00 — напоминание с планом обучения

---

## Формат еженедельной доставки

Каждый понедельник в 09:00 приходят два сообщения:

**Сообщение 1 — Дайджест** (≤3500 символов, Telegram HTML):
- 🤖 Агенты и подходы — 1-2 поста
- 🛠️ Инструменты — 1-2 поста
- 💡 Идеи и концепции — 1-2 поста
- 🧠 Психология / культура разработки — 1-2 поста
- 📰 Индустрия и менеджмент — 1-2 поста

**Сообщение 2 — Инсайты** (до 3 идей):
- **Implement** — конкретная идея для одного из 4 активных проектов + обоснование
- **Build** — идея нового проекта/инструмента для портфолио + почему актуально

---

## Структура проекта

```
src/
  config/          — настройки, channels.yaml
  db/              — schema.sql, migrate.py
  ingestion/       — Telethon bootstrap + incremental (сохраняет message_url)
  processing/      — normalize, cluster (RU+EN), detect_topics
  output/          — digest, recommendations, insight, study_plan
  reporting/       — HTML/PDF рендерер (Jinja2 + WeasyPrint)
  integrations/    — github_sync, github_crossref
  llm/             — client.py (роутинг моделей, трекинг стоимости)
  bot/             — Telegram bot (long-polling, telegram_delivery.py)
docs/prompts/      — LLM prompt templates
systemd/           — service + timer units
scripts/           — setup, bootstrap, healthcheck
tests/             — unit tests (unittest)
data/output/       — дайджесты .md/.json/.pdf, планы, рекомендации (gitignored)
```

---

## Быстрый старт

```bash
# 1. Клонировать
git clone git@github.com:ashishki/telegram-research-agent.git
cd telegram-research-agent

# 2. Создать venv и установить зависимости
python3 -m venv /srv/openclaw-you/venv
/srv/openclaw-you/venv/bin/pip install -r requirements.txt

# 3. Заполнить /srv/openclaw-you/.env
# LLM_API_KEY=...
# TELEGRAM_API_ID=...
# TELEGRAM_API_HASH=...
# TELEGRAM_BOT_TOKEN=...
# TELEGRAM_OWNER_CHAT_ID=...
# GITHUB_USERNAME=...
# GITHUB_TOKEN=...

# 4. Миграция БД
bash scripts/setup.sh

# 5. Авторизация Telegram (один раз, интерактивно)
bash scripts/auth_telegram.sh

# 6. Первичный парсинг 90 дней
bash scripts/run_bootstrap.sh

# 7. Запустить бота
python3 src/main.py bot

# 8. Установить systemd-таймеры
sudo cp systemd/*.service systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-ingest.timer telegram-digest.timer \
  telegram-bot.service telegram-study-reminder-tue.timer telegram-study-reminder-fri.timer
```

---

## Тесты

```bash
python3 -m unittest discover tests/
```

---

## Мониторинг расходов

Каждый LLM-вызов логируется в таблицу `llm_usage`. Модели подобраны по сложности задачи:

| Задача | Модель |
|---|---|
| Классификация тем (×8/нед) | claude-haiku-4-5 |
| Дайджест, рекомендации, план обучения | claude-sonnet-4-6 |

Типичная стоимость полного недельного цикла: **~$0.07–0.15**

---

## Технические решения

**Почему SQLite, не PostgreSQL** — один файл, WAL mode для параллельных чтений, FTS5 для полнотекстового поиска. Достаточно для 10k–100k постов на VPS.

**Почему Telethon, не Bot API** — Bot API не даёт доступа к истории каналов. Telethon работает по MTProto от имени пользователя.

**Почему JSON → PDF, не просто Markdown** — структурированный промежуточный формат даёт валидируемый контракт между LLM и рендерером, позволяет собирать источники с permalinks и строить приложение с цитатами.

**Роутинг моделей** — Haiku для простых JSON-задач (классификация тем), Sonnet для глубокого синтеза. Переключение без изменения кода через env vars `LLM_MODEL_{CATEGORY}`.
