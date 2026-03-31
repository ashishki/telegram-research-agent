# Telegram Research Agent

Персональная intelligence-система: читает Telegram-каналы, фильтрует шум, выдаёт структурированный отчёт о том, что важно — для тебя и твоих проектов.

---

## Зачем

Каждую неделю через Telegram-каналы проходит ~200–500 постов. Большинство — шум, переупаковки, объявления. Несколько штук реально влияют на то, что ты делаешь или должен изучить.

Этот агент делает одно: отделяет сигнал от шума и объясняет почему.

---

## Что ты получаешь

После запуска digest — отчёт в Telegram и/или файл. Структура фиксированная:

```
## Strong Signals
- [score=0.87] [model=claude-opus-4-6] Claude 4 анонсировал нативную поддержку...
- [score=0.81] [model=claude-opus-4-6] Новый подход к eval pipeline для агентов...

## Watch
- [score=0.61] Исследование по latency в RAG системах показало...
- [score=0.54] FastAPI 0.115 — изменения в dependency injection...

## Cultural
- Мем про vibe coding набирает обороты в сообществе...

## Ignored
3 posts filtered as noise. Top topics: ChatGPT tips, funding round, NFT

## Think Layer
Themes and patterns will be synthesized here.

## Stats
Total: 47 posts | strong: 2 | watch: 12 | cultural: 3 | noise: 30

## Project Relevance
- [gdev-agent] (score=0.71): Matches: fastapi, cost, async — Claude 4 анонсировал...
- [telegram-research-agent] (score=0.45): Matches: eval, pipeline — Исследование по...

## Learn
- langchain (seen 4 times) → Appeared 4 times in strong/watch posts, not in any project focus
- structured_output (seen 3 times) → Appeared 3 times in strong/watch posts, not in any project focus
```

**Strong Signals** — то, что нужно прочитать сегодня. Каждый пункт показывает score и модель, которая его обработала.

**Watch** — интересно, но не срочно. Можно вернуться позже.

**Cultural** — контекст сообщества, мемы, атмосфера. Полезно для понимания трендов, не требует действий.

**Ignored** — только счётчик. Контент не показывается, только сколько отфильтровано и по каким темам.

**Project Relevance** — какие посты из Strong/Watch касаются твоих активных проектов и почему (конкретные совпадающие ключевые слова).

**Learn** — темы, которые регулярно появляются в качественных постах, но ещё не покрыты ни одним из твоих проектов. Кандидаты для следующего learning gap.

---

## Как это работает

```
Telegram каналы
  → ingestion (Telethon)
  → scoring (signal_score 0–1, bucket, score_breakdown)
  → routing (CHEAP / MID / STRONG модель по score)
  → signal-first report (format_signal_report)
  → personalization (boost/downrank по profile.yaml)
  → project relevance (keyword matching по projects.yaml)
  → learning gaps (темы не покрытые проектами)
  → доставка в Telegram
```

Scoring **детерминированный** — никаких LLM на этом этапе. LLM получает только то, что прошло через routing layer.

---

## Выбор модели

### Три уровня

| Тир | Модель (по умолчанию) | Когда используется | Стоимость |
|---|---|---|---|
| CHEAP | `claude-haiku-4-5-20251001` | noise / cultural посты, score < 0.45 | $0.80 / $4.00 per M tokens |
| MID | `claude-sonnet-4-6` | watch посты, score 0.45–0.74 | $3.00 / $15.00 per M tokens |
| STRONG | `claude-opus-4-6` | strong посты, synthesis, score ≥ 0.75 | $15.00 / $75.00 per M tokens |

### Где твоё внимание

**Если прогоны стоят слишком дорого:**
- Проверь `python3 src/main.py cost-stats` — посмотри на долю STRONG вызовов
- Если STRONG > 20% постов — пороговое значение `STRONG_THRESHOLD` (0.75) можно поднять через env var
- Или понизь MID_MODEL на более дешёвую модель

**Если качество Strong сигналов низкое:**
- Скорее всего порог занижен — слишком много постов доходит до STRONG
- Подними `STRONG_MODEL` (Opus) или убедись что scoring.yaml настроен правильно

**Если хочешь сэкономить на тестах:**
```bash
export CHEAP_MODEL=claude-haiku-4-5-20251001
export MID_MODEL=claude-haiku-4-5-20251001   # понизить MID до CHEAP
export STRONG_MODEL=claude-sonnet-4-6         # понизить STRONG до MID
```

**Рекомендация по умолчанию:** оставь дефолты. Haiku для фильтрации, Sonnet для watch, Opus только для strong сигналов и synthesis — это оптимальный баланс quality/cost при недельном прогоне.

### Настройка через env vars

```bash
export CHEAP_MODEL=claude-haiku-4-5-20251001   # по умолчанию
export MID_MODEL=claude-sonnet-4-6             # по умолчанию
export STRONG_MODEL=claude-opus-4-6            # по умолчанию
export AGENT_DB_PATH=/path/to/your/agent.db
export ANTHROPIC_API_KEY=sk-ant-...
```

---

## Персонализация

Редактируй `src/config/profile.yaml`:

```yaml
boost_topics:        # эти темы повышают score × 1.3 (cap 1.0)
  - "AI agents"
  - "FastAPI"
  - "cost control"

downrank_topics:     # эти темы снижают score × 0.5
  - "crypto"
  - "NFT"
  - "ChatGPT tips"

downrank_sources:    # каналы с низким качеством сигнала
  - "@NeuralShit"
```

**Важно:** strong посты (score ≥ 0.75) не могут быть downranked ниже watch threshold (0.45). Система защищает объективно важные сигналы от подавления личными предпочтениями.

---

## Проекты

Редактируй `src/config/projects.yaml`:

```yaml
projects:
  - name: my-project
    description: "Краткое описание"
    focus: "ключевые слова через запятую, технологии, термины"
```

Чем конкретнее `focus` — тем точнее Project Relevance. Система ищет keyword overlap между постом и полем focus. Порог включения: score ≥ 0.3.

---

## CLI команды

```bash
# Проверить состояние системы
python3 src/main.py health-check

# Посмотреть распределение постов по bucket
python3 src/main.py score-stats

# Посмотреть расходы на LLM по моделям
python3 src/main.py cost-stats

# Предпросмотр signal-first отчёта из текущей БД
python3 src/main.py report-preview
```

### Пример: health-check

```
DB: /data/agent.db
  posts: 312
  scored_posts: 298
  llm_usage rows: 47

Config files:
  profile.yaml: present
  projects.yaml: present
  scoring.yaml: present
```

### Пример: score-stats

```
strong: count=8 avg_signal_score=0.8300
watch: count=41 avg_signal_score=0.5800
cultural: count=12 avg_signal_score=0.3100
noise: count=241 avg_signal_score=0.1500
top_topics: llm_agents (12), fastapi (8), eval (6)
```

### Пример: cost-stats

```
total_cost_usd: 0.0183
claude-opus-4-6: 3 calls | $0.0142
claude-sonnet-4-6: 18 calls | $0.0038
claude-haiku-4-5-20251001: 241 calls | $0.0003
distinct days: 1
```

---

## Документация

- `docs/architecture.md` — компонентная карта, data flow, контракты слоёв
- `docs/tasks.md` — Roadmap v2, все фазы и задачи
- `docs/IMPLEMENTATION_CONTRACT.md` — правила для codex/implementer
- `src/config/profile.yaml` — персонализация (boost/downrank)
- `src/config/projects.yaml` — активные проекты
- `src/config/scoring.yaml` — настройки scoring thresholds

---

## Статус

Roadmap v2 реализован полностью (фазы 1–8, задачи T29–T64).
Тестов: 83. CI: pytest на каждый push.
