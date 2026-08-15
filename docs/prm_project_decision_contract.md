# PRM Project Decision Contract

Status: active
Date: 2026-08-15

Unnamed project-decision requests must ask which project to use before
retrieval-backed recommendations:

```text
К какому проекту применить находки?

[telegram-research-agent]
[AI_workflow_playbook]
[Agent-Runtime-Grid]
[Другой]
```

Named project-decision answers render a memo with:

```text
Решение
Что найдено в источниках
Контекст проекта
Варианты
Рекомендация
Следующий эксперимент / PR-sized action
Критерий успеха
Что изменило бы решение
Где доказательства слабые
Источники
```

Project actions require explicit project identity, cited evidence, and a bounded
next experiment. Zero recommendation is valid when evidence is weak.
