# Prompt: аудит пользовательской ценности Telegram Research Agent

Ты - сильная frontier-модель в роли независимого product/engineering reviewer.
Твоя задача: проанализировать проект `telegram-research-agent` как личную
систему AI Knowledge Intelligence для одного пользователя и дать конкретные
рекомендации, что изменить, улучшить или выкинуть, чтобы система стала реально
полезнее для пользователя.

Пиши на русском. Не делай маркетинговый обзор. Нужен честный, прикладной аудит.

## Контекст пользователя

Пользователь ведет много AI/LLM/engineering Telegram-каналов и хочет не просто
дайджест, а понятный еженедельный интеллект-отчет:

- что нового появилось за неделю;
- как новые идеи, тренды, инструменты и события изменились относительно прошлых
  недель;
- что теперь важно изучать;
- что стоит сделать или проверить на практике;
- как находки связаны с его проектами и личным профилем;
- где доказательства слабые и выводы нельзя считать уверенными;
- как все это складывается в долгую базу знаний, а не одноразовый пересказ.

Пользователю не нужно видеть "кто и как" как главную поверхность отчета. Источники
и каналы нужны для внутреннего скоринга, доверия и аудита, но пользовательская
поверхность должна объяснять "что это значит для меня и что делать дальше".

Текущая стратегическая цель проекта:

```text
Telegram posts
  -> durable archive
  -> cheap Knowledge Atoms
  -> temporal Idea Threads
  -> frontier-model weekly analysis
  -> human-readable HTML report
  -> generated Obsidian projection
  -> personal read/try/build loop
```

MVP Radar, Implementation Ideas и project insights остаются downstream-
потребителями knowledge layer, но не должны быть главным продуктом.

## Что прочитать

Сначала изучи репозиторий и особенно эти файлы:

- `README.md`
- `docs/CODEX_PROMPT.md`
- `docs/tasks.md`
- `docs/ai_knowledge_intelligence_roadmap.md`
- `docs/operator_workflow.md`
- `docs/architecture.md`
- `docs/memory_architecture.md`
- `src/output/ai_visual_report.py`
- `src/output/ai_intelligence_report.py`
- `src/output/knowledge_extraction.py`
- `src/output/idea_threads.py`
- `src/output/frontier_analysis.py`
- `src/output/obsidian_export.py`
- `src/config/channels.yaml`
- `src/config/profile.yaml`
- `src/config/projects.yaml`

Также открой versioned artifact:

- `docs/artifacts/ai-decision-intelligence-2026-W28/2026-W28.visual.html`
- `docs/artifacts/ai-decision-intelligence-2026-W28/2026-W28.visual.json`
- `docs/artifacts/ai-decision-intelligence-2026-W28/2026-W28.knowledge-flow.archify.html`
- `docs/artifacts/ai-decision-intelligence-2026-W28/2026-W28.knowledge-flow.archify.json`

Если можешь запускать код, используй CLI inspection commands из README и docs,
но не делай дорогие LLM-вызовы без явной необходимости.

## Важные факты о текущем состоянии

- 12-недельный тестовый прогон уже был начат по всем каналам.
- Канал `https://t.me/leadgenvalley` добавлен ранее как часть источников.
- Система уже умеет генерировать Knowledge Atoms, Idea Threads, Frontier
  Analysis, HTML reports и Obsidian export.
- Последний визуальный HTML отчет был улучшен до `AI Decision Intelligence`:
  первый экран теперь показывает Decision Brief, top actions, trust caveats и
  метрики.
- `Project Implications` намеренно консервативен: широкие совпадения вроде
  `AI`, `workflow`, `evidence`, `tool` не должны показываться пользователю как
  уверенные проектные выводы. В артефакте `2026-W28` получилось `0 project
  leads`; это честный результат текущих данных, а не обязательно сбой.
- Archify используется для визуализации knowledge-flow, но диаграмма должна
  быть вспомогательной audit surface, а не главным смыслом отчета.
- Runtime source of truth - SQLite/database + generated artifacts. Obsidian -
  projection для человеческой навигации, не основная база.

## Что нужно получить на выходе

Сформируй отчет для владельца системы. Структура:

1. **Короткий диагноз**
   - Что уже стало полезным.
   - Что все еще не решает пользовательскую задачу.
   - Главный bottleneck: данные, атомы, threading, frontier synthesis, report UX,
     personalization, delivery, feedback loop или проектная привязка.

2. **Оценка текущего HTML артефакта**
   - Понятен ли он пользователю без знания внутренней архитектуры.
   - Что в нем помогает принять решение.
   - Что выглядит красиво, но не добавляет практической ценности.
   - Какие 3-5 изменений в отчете дадут максимальный прирост понятности.

3. **Что изменить в продукте**
   - P0: изменения, без которых система останется "интересным отчетом", но не
     рабочим intelligence desk.
   - P1: улучшения на ближайшие 1-2 недели.
   - P2: более крупные улучшения после стабилизации.

4. **Что изменить в data/AI pipeline**
   - Knowledge Atom extraction: какие поля, проверки, evals или prompts улучшить.
   - Idea Threads: как лучше отслеживать развитие, устаревание, противоречия,
     production patterns и hype-only темы.
   - Frontier Analysis: какой контекст давать топ-модели, какие выходные
     контракты требовать, где нужна строгая JSON-схема.
   - Project Implications: как перейти от keyword leads к реально полезной
     персональной привязке к проектам.

5. **Что изменить в Obsidian projection**
   - Что должно быть в vault, чтобы пользователь реально возвращался к знаниям.
   - Какие заметки лишние или опасны как шум.
   - Как связать weekly report, idea threads, read queue, experiments и projects.

6. **Что измерять**
   - 5-10 конкретных метрик качества для пользователя.
   - Как понять через 4 недели, что система стала лучше.
   - Какие ручные feedback actions пользователь должен делать минимум.

7. **План работ**
   - Конкретный 7-дневный plan с задачами, acceptance criteria и тестами.
   - Конкретный 30-дневный plan.
   - Что не делать сейчас, даже если выглядит заманчиво.

8. **Риски и честные ограничения**
   - Где система может уверенно говорить глупости.
   - Где LLM может переобобщать.
   - Где красивые HTML/Obsidian артефакты могут маскировать слабую базу данных.
   - Какие guardrails добавить.

## Требования к качеству ответа

- Не пересказывай README. Делай выводы.
- Разделяй "уже реализовано", "частично реализовано", "нужно построить".
- Ссылайся на конкретные файлы/команды/артефакты, когда делаешь технические
  утверждения.
- Не советуй "добавить AI" абстрактно. Все рекомендации должны быть
  реализуемыми в этом репозитории.
- Не предлагай публичный SaaS, multi-user UI или монетизацию, если это не
  помогает личному intelligence workflow.
- Не делай вид, что `0 project leads` - ошибка. Оцени, как сделать этот блок
  полезнее без ложной уверенности.
- Приоритизируй пользовательскую ясность, повторяемость weekly loop,
  доказательность и actionability.

Формат ответа: русский Markdown, без длинной воды. Начни с 5-7 bullet points
самого важного, затем дай подробный prioritized plan.
