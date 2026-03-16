# Telegram Research Agent

Персональная AI-система для непрерывного мониторинга технологического ландшафта через Telegram-каналы. Агент автоматически собирает посты, кластеризует темы, генерирует еженедельные дайджесты и составляет индивидуальный план обучения — всё доступно через Telegram-бота.

---

## Что это и зачем

Проблема: в AI/tech пространстве ежедневно выходят сотни постов. Читать всё — невозможно. Пропустить важное — легко. Связать происходящее в индустрии со своими проектами — ещё сложнее.

Решение: агент делает это автоматически. Каждую неделю он:
- Забирает новые посты из 19 Telegram-каналов
- Кластеризует их в темы (TF-IDF + KMeans, без LLM)
- Генерирует структурированный дайджест (Claude Sonnet)
- Сопоставляет темы с твоими GitHub-проектами
- Составляет персональный 3-часовой план обучения с конкретными ссылками
- Присылает всё это в Telegram-бот

---

## Архитектура

```
Telegram MTProto (Telethon)
    ↓
SQLite (2 376+ постов, WAL mode, FTS5)
    ↓
TF-IDF + KMeans → тематические кластеры
    ↓
Anthropic Claude API (Haiku / Sonnet — роутинг по задаче)
    ↓
Дайджест · Рекомендации · Study Plan · Project Insights
    ↓
Telegram Bot (long-polling, только owner)
```

**Стек:** Python 3.10, Telethon, scikit-learn, Anthropic SDK, SQLite, systemd

---

## Возможности

| Команда бота | Что делает |
|---|---|
| `/digest` | Дайджест текущей недели |
| `/topics` | Список обнаруженных тем с весами |
| `/study` | 3-часовой план обучения с книгами и ссылками |
| `/insight` | Что из 90 дней истории релевантно твоим проектам |
| `/project <name>` | Конкретный проект × Telegram-темы |
| `/ask <вопрос>` | Свободный вопрос по корпусу постов |
| `/costs` | Статистика расходов на LLM по категориям |
| `/status` | Состояние системы |

**Автоматика:**
- Пн 07:00 — инкрементальный парсинг всех каналов
- Пн 09:00 — генерация дайджеста + отправка в бот
- Вт 10:00, Пт 10:00 — напоминание с планом обучения

---

## Роль OpenClaw

Проект развёрнут на инфраструктуре [OpenClaw](https://github.com/openclaw) — multi-protocol agent framework. OpenClaw предоставляет:
- VPS-окружение с изолированным пользователем `oc_you`
- Управление секретами (`/srv/openclaw-you/secrets/`, `/srv/openclaw-you/.env`)
- Сетевую инфраструктуру и systemd-окружение

Изначально планировалось использовать OpenClaw WebSocket gateway как прокси к LLM. После анализа исходников (`/opt/openclaw/src`) принято архитектурное решение: использовать Anthropic Python SDK напрямую — протокол OpenClaw gateway написан на TypeScript и не имеет Python-клиента. OpenClaw остаётся платформой деплоя; LLM-вызовы идут напрямую через `anthropic` SDK.

---

## Структура проекта

```
src/
  config/          — настройки, channels.yaml
  db/              — schema.sql, migrate.py
  ingestion/       — Telethon bootstrap + incremental
  processing/      — normalize, cluster, detect_topics
  output/          — digest, recommendations, insight, study_plan
  integrations/    — github_sync, github_crossref
  llm/             — client.py (роутинг моделей, трекинг стоимости)
  bot/             — Telegram bot (long-polling)
docs/prompts/      — LLM prompt templates
systemd/           — service + timer units
scripts/           — setup, bootstrap, healthcheck
data/output/       — дайджесты, планы, рекомендации (gitignored)
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

## Мониторинг расходов

Каждый LLM-вызов логируется в таблицу `llm_usage`. Модели подобраны по сложности задачи:

| Задача | Модель |
|---|---|
| Классификация тем (×8/нед) | claude-haiku-4-5 |
| Дайджест, рекомендации, план обучения | claude-sonnet-4-6 |

Типичная стоимость полного недельного цикла: **~$0.07–0.15**
