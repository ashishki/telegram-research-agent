# Deep review: границы фаз и запуск Terra/high

Дополнение к аудиту от 17.09.2026. [Карточки задач и карта PRM-SN-DR-1…PRM-SN-DR-5](PRM_SEARCH_NEWS_PLAN.md).

**Да: для exec-based reviewer здесь принят `gpt-5.6-terra` с `model_reasoning_effort="high"`.** Это точное требование текущей [REVIEW_POLICY](https://github.com/ashishki/telegram-research-agent/blob/cee8baae3b8a41f571bd689f2dadf7e6e981863f/docs/REVIEW_POLICY.md), а не вывод из того, что аудит выполняла Astra. Модель runtime-бота выбирается отдельно.

Документ конкретизирует применение существующих Playbook review rules к пяти новым фазам. Он **не заменяет** установленный audit checklist, reporting format, human completion authority и immediate triggers. Task/gate IDs зарегистрированы в docs/tasks.md по поручению владельца; это не выполненные reviews и не одобрение runtime.

## Когда

- Один накопительный deep review на границе каждой большой фазы: PRM-SN-DR-1 после ответа; PRM-SN-DR-2 после диалога/памяти/свежести; PRM-SN-DR-3 после внешней проверки; PRM-SN-DR-4 после одноразового выпуска; PRM-SN-DR-5 после подписки/outbox.
- Внутри фазы — focused tests/test critic; не полный аудит после каждой мелкой правки.
- Изменение privacy/egress, confirmation/write, schema/retention, allowlist/SSRF, schedule/caps/notifications, trust/restore или release boundary вызывает immediate review **до дальнейшей зависимой работы**. Его результат включается в фазовый пакет.
- PRM-SN-DR-5 предшествует отдельно разрешённому ручному пилоту. PRM-SN-DR-PILOT по реальным наблюдениям предшествует расширению rollout. Fixture pass не заменяет эти наблюдения и согласие.

## Кто и с какими полномочиями

Агент-исполнитель готовит код и evidence; отдельный exec reviewer читает их в новой сессии и ищет ошибки. Reviewer не исправляет код, не commit/push, не меняет статусы, не включает jobs и не одобряет человеческие gates. Исправления делает implementer в назначенном scope. Это review после bootstrap, а не запрещённый nested Codex bootstrap/implementation.

Штатный end-to-end goal включает необходимые bounded exec reviews публичного кода и synthetic evidence для всех пяти фаз, immediate safety triggers и исправлений. На каждый review и переход после engineering PASS внутри goal не нужен новый запрос разрешения. Карточки и review packets остаются узкими; цель выполняется целиком. **Регистрация задач сама по себе не запускает implementation или provider review.** Если пакет содержит частные данные, прежнего согласия на review кода недостаточно: сначала убрать данные или отдельно определить разрешённый egress.

## Пакет входных данных

Перед запуском orchestrator готовит вне production:

1. Base SHA, reviewed SHA, hash diff и manifest файлов. Если изменения незакоммичены — явно записанный working diff hash; не приписывать их одному HEAD.
2. Карточки текущей фазы, ожидаемое поведение и применимые разделы policy/contracts. Полный накопительный diff фазы и достаточно окружающего кода для трассировки активного пути.
3. Команды и точные результаты focused tests, известные failures; synthetic before/after UX и воспроизведения критических дефектов. Логи сами по себе не доказательство: reviewer проверяет, действительно ли assertions ловят проблему.
4. Claim/evidence либо event/delivery traces по области review; budgets/permissions/state transitions; rollback и все unresolved risks.
5. Предыдущие findings и исправления. Для review после правок — отдельный diff от проверенной версии.
6. Manifest доказательств: code/fixture/advisory/human/runtime. Human holdout не генерируется самим reviewer; закрытые задания не передаются implementer для подстройки. Reviewer может читать агрегаты/нужные разрешённые результаты, сохраняя независимость набора.

Использовать отдельный snapshot с public tracked code и synthetic fixtures. Не давать `.env`, credentials, Telegram archive, backup, private reports, host sockets или production mounts. `--sandbox read-only` ограничивает запись, **не является сам по себе полной изоляцией чтения, сети и приватности**. Изоляцию и разрешённый provider egress обеспечивает среда запуска; tools/MCP/hooks не должны незаметно расширять доступ. Перед запуском проверить их effective configuration, не печатая секреты.

## Команда

Следующий шаблон **не запускался**. На текущем окружении проверен только `codex exec --help`: доступны `--model`, `--config`, `--sandbox read-only`, `--ignore-user-config`, `--ephemeral`, `--skip-git-repo-check`, `--output-last-message` и ввод prompt через stdin. Наличие модели Terra/high и её фактическое исполнение этим не проверены.

После подготовки изолированного input и ограниченного review scope:

```bash
REVIEW_INPUT=/tmp/telegram-prm-review/PRM-SN-DR-1/input
REVIEW_OUTPUT=/tmp/telegram-prm-review/PRM-SN-DR-1/output

codex exec \
  --cd "$REVIEW_INPUT" \
  --skip-git-repo-check \
  --ignore-user-config \
  --ephemeral \
  --sandbox read-only \
  --model gpt-5.6-terra \
  -c 'model_reasoning_effort="high"' \
  --output-last-message "$REVIEW_OUTPUT/review.md" \
  - < "$REVIEW_INPUT/review-prompt.md" \
  > "$REVIEW_OUTPUT/runner.stdout.log" \
  2> "$REVIEW_OUTPUT/runner.stderr.log"
```

Директории и заполненный prompt должны существовать **до** команды. В input — read-only sanitised snapshot, `scope.md`, `manifest.json`, `phase.diff`, `evidence/` и применимые policy/contracts. `--skip-git-repo-check` нужен для такой копии без `.git`, не для сокрытия версии: версии зафиксированы в manifest. `--ignore-user-config` отключает загрузку пользовательского config, но не отменяет provider authentication и не гарантирует всю изоляцию. Не добавлять bypass sandbox/approvals flags.

Шаблон prompt: [reviewer-prompt.template.md](prompts/prm_search_news_reviewer.md). Подставить gate, SHA, область и actual checklist; не отправлять незаполненные placeholders. Из действующего Playbook брать обязательный формат/проверки, из нового пакета — границы конкретной фазы. Не вкладывать всю историческую документацию автоматически.

## Что reviewer обязан проверить

- Пройти активный путь от ввода до окончательного текста/записи/доставки; проверить final output, не только промежуточные метрики.
- Искать ложный pass: unsupported claim с хорошим overlap, неверная ссылка, неразобранный хвост, неправильная дата, передача старого scope, подтверждение другого объекта, lost event, ambiguous send как success.
- Проверить полезные положительные случаи: исправление не должно превращать всё в отказ. Для retrieval/generation — paired positives, coverage/ranking и ложные отказы; для новостей — событие/новизна/значимость/полезность, не только schema.
- Оценить tests как критик: какая ошибка ими обнаруживается, где assertions тавтологичны, какие fault/holdout cases отсутствуют. Не подменять human usefulness модельной оценкой.
- Проверить privacy, расходы, concurrency/rollback в реально изменённой области. Данные источника не меняют полномочия.
- У каждого существенного finding указать severity, файл/символ, trigger, expected/actual, evidence, минимальное исправление и проверку закрытия. Гипотезу назвать гипотезой; отсутствие измерения — отсутствием измерения.

Reviewer может запросить дополнительное безопасное воспроизведение. Orchestrator запускает его только после проверки I/O в одноразовой среде. Read-only review не даёт reviewer права менять код или настоящие данные ради reproduction.

## Формат и фиксация результата

Сохранить существующий формат `PACKET_REVIEW_RESULT: PASS` либо `ISSUES_FOUND`, work item и конкретные issues из repository reviewer contract. Дополнительно в receipt записать:

```text
Gate / scope:
Base SHA / reviewed SHA / diff hash:
Requested model: gpt-5.6-terra
Requested reasoning effort: high
Observed model / observed effort:
Runtime evidence for observed values:
Exact command / runner version / exit code / timestamps:
Evidence checked / tests rerun / tests only inspected:
Findings P0/P1/P2 and unresolved evidence gaps:
Corrections and new diff hash:
Re-verification result:
Engineering scope passed:
Human/runtime gates still pending:
```

Запрошенная модель в команде — не доказательство effective model. Сохранить действительные runtime metadata/banner/runner receipts, если они доступны. Если runtime сообщил другой model/effort или не даёт их установить, записать `mismatch`/`unverified`. Полезные findings сохранить, но **не утверждать «Terra/high review выполнен»** без подтверждения. Текст самого reviewer «я Terra» таким подтверждением не является.

Не писать PASS при отсутствии обязательного evidence для заявленного scope. Можно отдельно указать «engineering subset checked; human/runtime quality not evaluated», но это не общий quality/release PASS.

## Исправления, повторная проверка, переход

1. P0/P1 и нарушения privacy/confirmation/caps/critical facts исправить до зависимой фазы. При нехватке evidence — добрать соответствующую проверку, не переименовывать finding в warning.
2. Implementer делает минимальный fix и focused regression; reviewer проверяет закрытие каждого finding и новый риск diff. Прошлый review не распространяется автоматически на изменившийся код.
3. Обычно достаточно одного review и одной адресной перепроверки. У текущего delivery model correction budget по умолчанию 2; после исчерпания — явный нерешённый scope/план исправления, а не бесконечный self-approve loop. Это не автоматическое право игнорировать blocker.
4. Gate считается инженерно закрытым только для зафиксированного SHA/diff при корректном review provenance и выполненных обязательных проверках. Список всех residual risks и недостающей human/runtime evidence остаётся видимым. В назначенном полном goal после этого самостоятельно перейти к следующей фазе; complete goal допустим только после всех пяти engineering gates и итоговой интеграционной проверки/pilot packet.
5. Владелец сохраняет completion authority. Review не разрешает release, PRM-19/20, deployment, production migrations, provider/archive egress или live subscription. Конкретный пилот и rollout принимаются отдельно по готовому пакету.

Raw runner logs и packet остаются вне рабочего дерева. Sanitised итоговый receipt сохраняется в docs/audit/ и связывается с назначенной задачей, если это входит в поручение; штатный implementer prompt включает такие записи. Не коммитить transcripts, секреты и частные source snippets. Фазовый receipt обязан указывать phase base и последний reviewed diff; focused critic по одной карточке не закрывает всю фазу.
