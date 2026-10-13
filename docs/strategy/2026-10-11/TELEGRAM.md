# Telegram: решения для ежедневного ассистента

Дата проверки официальной документации и кода: **11 октября 2026**. Это архитектурное обоснование карточек **единого [backlog](BACKLOG.md)**, не отдельный план исполнения. Точка входа всей программы — [README](README.md). Статус — исследование и исполнимый план; прикладной код, сервисы, BotFather, токены и личные подключения не изменялись. Реализацию выполняет следующий агент пакетами с Deep Review между ними: исправить находки, узко перепроверить критические, идти дальше.

## Решение

Внедрять **привязанные к результату действия, понятный прогресс/остановку и Rich Messages** в существующий ассистент. Это сокращает повторный ввод, ожидание без обратной связи и переходы из Telegram. Темы включать после проверки удобства на двух параллельных задачах; обычный разговор остаётся полноценным. Secretary Mode сначала проверить на выделенной тестовой переписке, затем довести выбранный сценарий чтения/черновиков и отдельно подтверждаемой отправки. Mini App исключён владельцем. Для отчётов использовать native Telegram, экспорт и существующий приватный reader.

Не нужен новый бот, новый агентный фреймворк или обязательный выбор Chat/Search/Brief/Watch перед вопросом. Цель — полноценная работа выбранных сценариев; первые успешные API calls являются промежуточной проверкой. UTD/Nebula развивается в той же общей очереди и получает улучшенный Telegram-интерфейс через общие результаты/Brief, без второго набора Telegram-компонентов.

## Выбор направлений и пользовательский эффект

Оценка затрат относительная: S — небольшой срез; M — несколько срезов; L — пакет с изменением данных/полномочий. Это оценка разработки и сопровождения, не календарное обещание.

| Направление | Решение | Сценарий и польза | Более простой путь / цена |
| --- | --- | --- | --- |
| Reply, цитата, пересланный материал, действия у результата | **Внедрять первыми**, D56 + уточнения D04/D19/D34 | «Поясни этот пункт», «сохрани к проекту», «следи за этим» адресуют конкретный результат/версию. Переслал сообщение → получил разбор без выбора режима. | Reply + 2–3 inline buttons уже дают пользу без новых форматов. M, малые текущие расходы. |
| Прогресс и остановка | **Внедрять**, D57 поверх D02 | Долгая задача показывает фактический этап и число обработанных источников; «стоп»/кнопка останавливают нужную работу. | Сначала одна редактируемая карточка; native draft добавляет более плавный ответ. M. Нужны throttling и lifecycle, не поток из десятков сообщений. |
| Rich Messages | **Внедрять с обязательной проверкой на настоящих клиентах**, D58 | Читабельный Brief с заголовками, компактным сравнением, раскрываемыми источниками и продолжением работы внутри Telegram. | Существующие HTML/PDF остаются совместимым представлением того же документа. M, без нового web hosting. |
| Поток текста модели | **Проверить экспериментом в D57**, затем включить для полезных классов ответа | Быстрее получить осмысленное начало ответа. | Для исследования сначала progress и проверенные промежуточные блоки; весь неподтверждённый текст не публикуется ради эффекта печати. Расход зависит от провайдера, SSE/recovery усложняет transport. |
| Темы в личном чате | **Эксперимент → внедрение при пользе**, D59 | Два длительных исследования продолжаются независимо; возврат в тему восстанавливает её контекст. | До включения достаточно reply/result focus и кнопки «Продолжить». M/L из-за миграции ключей, а не создания темы. Не создавать тему на каждый вопрос. |
| Secretary: выбранные входящие и черновики | **Эксперимент доступа → полноценный выбранный коннектор**, D60/D61 | Заметить просьбу/обещание/изменившийся срок; предложить ответ владельцу и напоминание. | Forward в личный чат бота даёт полезный ручной путь без подключения переписок. L; главная цена — scope, lineage, редакции/удаления и шум. |
| Secretary: ответ от имени владельца | **Отдельный этап после чтения/черновиков**, D62 | Владелец проверяет точный ответ и адресата и подтверждает отправку. | До этого — локальный черновик и ручное копирование. L, отдельный effect adapter и реальные проверки. Автоответы по входящим не включать. |
| Mini App | **Исключён владельцем** | Не входит в продуктовый план, эксперименты или rollout. | Native Telegram-отчёты, PDF/MD и обычный приватный reader D25. |
| Guest Mode / inline sharing | **Отложить** | Контекстный вызов бота из другого чата возможен, но результат виден участникам того чата. | Пересылка в приватного ассистента полезнее для текущего персонального контекста. Нужна отдельная outbound policy; это не безопасная замена Secretary. |
| Native checklist | **Отложить** | Привычная форма списка задач. | По текущему контракту `sendChecklist` требует business connection. Наши задачи/кнопки/Rich task list не должны зависеть от подключения аккаунта. |
| Ephemeral group UI, communities, paid broadcasts, bot-to-bot, managed bots | **Не включать в эту программу** | Подтверждённого выигрыша для одного владельца нет. | Увеличивают surface и поддержку; основной личный интерфейс обходится без них. |

Пример целевого потока: «Сравни две библиотеки для моего проекта» → короткое подтверждение начала и «Остановить» → реальные стадии поиска → цельный rich report → «Почему такой вывод?» по выбранному пункту → «Сохрани решение». Для второго исследования не нужно заранее выбирать режим или создавать папку. Тему можно предложить, когда она поможет возвращаться к длительной работе; перенос темы не меняет проектные разрешения.

## Что подтверждено документацией Telegram

На дату исследования официальная страница Bot API показывает **10.3, 24 августа 2026**. Это версия публичного контракта, а не доказательство поддержки каждым приложением владельца. Источники ниже официальные; локальные snapshots с SHA-256 перечислены в [telegram_evidence.json](telegram_evidence.json).

| Возможность | Реальный API / настройка | Существенное ограничение |
| --- | --- | --- |
| Structured rich report | `sendRichMessage`; `InputRichMessage` — ровно одно из `blocks`, `html`, `markdown`; обновление через `editMessageText.rich_message` | 32768 UTF-8 characters, 500 блоков, глубина 16, 50 media, 20 столбцов. Это потолки API, не UX-цели. [Контракт](https://core.telegram.org/bots/api#rich-messages). |
| Кнопки внутри отчёта | `RichMessageButton`, `InputRichBlockButtons`; callbacks используют обычный `CallbackQuery` | `callback_data` 1–64 bytes; не вмещать туда весь объект/секрет/полномочие. [Тип](https://core.telegram.org/bots/api#richmessagebutton). |
| Потоковые previews | `sendMessageDraft`, `sendRichMessageDraft`, nonzero `draft_id`, optional `message_thread_id`, `can_stop`, `keep_on_stop` | Preview живёт 30 секунд; для сохранения нужен отдельный final send. Text draft до 4096 символов; rich draft не поддерживает прямую загрузку новых файлов/загрузку по URL. [Draft](https://core.telegram.org/bots/api#sendmessagedraft), [rich draft](https://core.telegram.org/bots/api#sendrichmessagedraft). |
| Native Stop | Update `stopped_message_generation` / `MessageGenerationStopped` | В событии есть `chat`, optional thread, `draft_id`; поля `from` нет. Нужна собственная привязка draft → job, проверка приватного owner route. [Тип](https://core.telegram.org/bots/api#messagegenerationstopped). |
| Темы private bot chat | Включить в BotFather; `getMe.has_topics_enabled`, `allows_users_to_create_topics`; `createForumTopic`, `editForumTopic`, delete/close/reopen; отправка с `message_thread_id` | Это не channel direct messages: `direct_messages_topic_id` — другой механизм. Доступность конкретному боту и клиентам проверяется. [Описание](https://core.telegram.org/bots/features#topics-in-private-chats), [создание](https://core.telegram.org/bots/api#createforumtopic), [getMe/User](https://core.telegram.org/bots/api#user). |
| Secretary Mode | Настройка BotFather; `getMe.can_connect_to_business`; `BusinessConnection`, `getBusinessConnection`, `business_message`, `edited_business_message`, `deleted_business_messages` | Название Secretary Mode использует официальный feature guide; протокол остаётся BusinessConnection. Доступ — выбранные приватные переписки, а не история всех чатов. [Guide](https://core.telegram.org/bots/features#business-bots). |
| Ответ от аккаунта | `sendMessage(business_connection_id=...)`, права `BusinessBotRights.can_reply` | Отправка/редактирование ограничены приватными чатами с входящими за последние 24 часа. `can_read_messages` означает **пометку прочитанным**, не разрешение получать историю. [Права](https://core.telegram.org/bots/api#businessbotrights), [readBusinessMessage](https://core.telegram.org/bots/api#readbusinessmessage). |
| Условия подключения | Один connected business bot на аккаунт; Premium для подключения сейчас не требуется | Проверить, не занят ли слот уже выбранным ботом; не отключать его автоматически. Формулировки старых статей про обязательный Premium не использовать. [Connected bots](https://core.telegram.org/api/bots/connected-business-bots). |

Дополнительные ограничения: long polling и webhook взаимоисключающие; pending updates хранятся не бесконечно (Bot API указывает до 24 часов). Бот не получает произвольную историю переписки по `chat_id`. Выбор чата через request-chat кнопку передаёт идентификатор, но не создаёт доступ. `getMe` не сообщает версию клиентского приложения владельца и не является общей проверкой поддержки Rich Messages. Проверка server API и visual/client evidence раздельна. [Updates](https://core.telegram.org/bots/api#getting-updates), [выбор чата](https://core.telegram.org/bots/features#chat-and-user-selection).

Для отправок FAQ рекомендует избегать частоты выше одного сообщения в секунду в один чат; предел для draft/edit отдельно не гарантирован. Проектный default — coalescing и не чаще одного preview update в 1–2 секунды, с реакцией на `retry_after`; это начальная настройка для измерения, не обещанный лимит Telegram. Progress heartbeat нужен реже, по изменению этапа. [Ограничения](https://core.telegram.org/bots/faq#my-bot-is-hitting-limits-how-do-i-avoid-this).

Guest Mode получает вызвавшее сообщение и иногда replied-to сообщение, допускает один ответ на вызов и не даёт историю/дальнейшие обновления. Его нельзя использовать для незаметного чтения переписки; ответ публикуется в исходном чате. [Официальное описание](https://core.telegram.org/bots/features#guest-interactions). FAQ содержит более старые общие утверждения о bot-to-bot; для новых возможностей приоритет у текущего Bot API/feature guide. Неподтверждённые client/version детали оставлены экспериментам, не скрытым зависимостям.

## Текущее состояние проекта и совместимость

Исследован HEAD `23312b8`; source/runtime baseline `0fbcfd1`. В текущем worktree только документационные изменения этого плана. Дополнительный worktree `/tmp/tra-db6df8d` существует, его `git status --short` пуст; назначение/активность другой сессии неизвестны. Это не утверждение об отсутствии других агентов. Перед началом пакета исполнитель сверяет HEAD/diff и assignment, согласует владение общими файлами и не перезапускает уже закрытые D/PAI задачи.

| Наблюдение | Следствие для плана |
| --- | --- |
| [bot.py](../../../src/bot/bot.py) использует `urllib` и JSON Bot API; `allowed_updates` только message/edited_message/callback_query. | Нет python-telegram-bot/aiogram, которые надо сначала обновить. Новые методы добавляются в существующий HTTP boundary с typed request/response. |
| [requirements.txt](../../../requirements.txt): `telethon>=1.36.0`; в `.venv-pai` установлен 1.42.0. [Telegram ingestion](../../../src/ingestion/telegram_client.py) использует пользовательскую сессию. | Telethon — архивный MTProto-путь. Его capabilities не определяют поддержку новых Bot API методов. Широкий dependency range исправляется D47; слепой upgrade не нужен. Текущая stable документация Telethon показывает 1.45.0, production environment не исследован. [Документация](https://docs.telethon.dev/en/stable/). |
| [Ingress](../../../src/prm/runtime/ingress.py) берёт только `message`/`callback_query`, проверяет owner/private tuple, теряет thread/reply/quote/forward metadata. | Native Stop, edited_message и business_message сейчас возвращают `None`; первые три случая воспроизведены локально. Нельзя просто добавить их в allowed_updates и считать поддержку готовой. |
| [Conversation key](../../../src/prm/conversation.py) строится только из chat_id; [durable store](../../../src/prm/storage/conversations.py) повторяет это. [Queue claim](../../../src/prm/storage/jobs.py) сериализует compute.assistant по owner. | Включение тем без нового ключа смешает контекст. Нужны scoped keys и conversation-level fencing; повышать parallelism только с общей budget/admission policy. |
| [BoundedTelegramSender](../../../src/prm/runtime/transports.py) умеет только sendMessage, owner destination, <=3800 characters, HTML/текст. Navigation разрешает только text reply keyboards. | Rich payload, inline callbacks, thread, edits/drafts и business target требуют явных контрактов. Нельзя превратить безопасный owner sender в произвольный sender для всех chat_id. |
| В durable ветке [bot.py](../../../src/bot/bot.py) IntakeReply отправляется через прежний send_private_message; navigation не передаётся, callback acknowledgement в этой ветке не вызван. | Реальные кнопки/status UX надо проверять через внешний polling loop, а не только ingress unit test. D56 закрывает этот разрыв. |
| Есть durable jobs/cancel/results, [delivery attempts/unknown](../../../src/prm/runtime/delivery.py), immutable BriefDocument и [HTML splitter](../../../src/prm/runtime/presentation.py). | Переиспользовать, не создавать второй job manager или отдельный rich-report source of truth. Current multipart no-replay поведение сохраняется. |
| [Model transport](../../../src/prm/runtime/model.py) отправляет `stream:false`, читает целый ответ. | Telegram draft сам по себе не ускорит получение токенов. Progress доступен раньше; модельный streaming — отдельная часть D05/D57 с provider-specific проверкой. |
| [Action allowlist](../../../src/prm/confirmed_actions.py) содержит mail/calendar; [executor](../../../src/prm/runtime/actions.py) привязан к Graph. | Telegram business reply — новый action code/adapter D62; подключение Secretary не превращает mail confirmation в право отвечать в Telegram. |
| [Reader](../../../src/prm/runtime/reader.py) — localhost/header auth/in-memory sessions; имеются HTML/PDF/MD. | Обычный приватный reader требует D25 auth/lifecycle; экспорт не требует Mini App. |

Выполнены только чистые локальные probes без БД/сети: три игнорируемых update, inline navigation ignored, сигнатуры sender/conversation key. Это **baseline наблюдения**, не новые failing regression tests и не live Telegram. Исторические 398 PAI checks не повторялись; реальная доставка, Rich UI, draft, topics и Secretary не проверялись.

## Архитектурные решения

### 1. Общий Telegram transport, разные адресаты и полномочия

Сохранить Bot API HTTP и long polling. Новый нейтральный `TelegramTransport` кодирует только поддержанные методы и различает `KnownRejected`, `Accepted(message receipt)` и `Unknown`. Owner delivery остаётся отдельной обёрткой; business effect получает собственный executor. Общий transport сам не выдаёт разрешений. Не использовать webhook-response shortcut для эффектов: нужен наблюдаемый API result и receipt. Webhook сейчас не даёт установленного выигрыша и не входит в первый пакет.

Предлагаемый `TelegramDestination`: `bot_ref`, `chat_id`, `message_thread_id?`, `business_connection_id?`, `audience_kind=owner_private|business_peer`. Поля входят в digest/receipt; неизвестный thread не заменяется main chat молча. Channel direct messages в этот контракт пока не входят. IDs хранить без сужения до 32 bit; draft/job/connection IDs никогда не угадывать из текста модели.

`TelegramCapabilities` различает configured / observed / unsupported / not_checked. `getMe` и тестовый canary дают отдельные observations с датой; client UX фиксируется по платформе/версии вручную на canary, поскольку Bot API не сообщает её. Новый feature flag — prefer/off/observed_supported с причинами fallback, а не ложный supported из одного config.

### 2. Durable вход и привязки

Добавить normalized envelope `telegram.update.v2`: bot_ref/update_id/kind, optional verified actor, owner, destination, source message_id/revision, reply_to_id, quote, forward origin, attachment refs, received_at. Native Stop имеет отдельное правило доверия route/binding; отсутствующий actor не синтезировать. Это не исключение для обычных callbacks или подтверждения действий. Входящие source text/цитаты не могут содержать доверенные actions/navigation. Статус обработки — persisted/explicitly rejected/quarantined; offset продвигается только после такого решения. Сбой сохранения не теряет update, невалидный poison update не блокирует очередь навсегда. Не хранить все чужие сообщения ради диагностики.

`TelegramMessageBinding` хранит owner, destination, message_id, job_ref, response_ref/version, optional story_ref, presentation revision и scope revision. Reply сначала разрешается через эту запись; quote проверяется против доступного snapshot, missing original даёт ограниченный контекст. Цитата пользователя не подтверждает источник сама по себе. `external_reply`/forward origin часто неполны: не обещать недоступную историю. Edited message создаёт revision; не переисполняет старое действие и не означает новое подтверждение.

Inline callback передаёт короткий opaque token до 64 bytes. Сервер хранит owner/route/object/version/action/expiry; каждый callback проверяется независимо от красивой кнопки. Навигация может быть повторяемой; effect confirmation одноразовая и bound к полностью показанному preview. `answerCallbackQuery` быстро снимает spinner и не обещает успех выполнения. Кнопки для стороннего собеседника не дают доступа к owner controls.

### 3. Отображение длительной работы

Ввести `ProgressEvent(job, generation, stage, completed_units?, total_units?, verified_block_refs?, at)` и `PresentationState(job, route, revision, draft_id?, status_message_id?, visible_result_digest?, terminal_state)`. Это проекция существующего JobQueue, а не новый workflow engine. Статусы выводятся из worker events: принят запрос, читаются источники, сравниваются данные, результат частичный/готов, остановка запрошена. Процент показывается только при известном total; содержимое скрытого reasoning не публикуется.

Первый working путь — одна status card с inline Stop и edit по смене стадии. Затем native draft: отдельный lease на видимый preview для owner chat/thread, стабильный nonzero draft_id и generation fence. Конкурирующие jobs не перезаписывают друг друга; до подтверждения client поведения в одной области показывается preview только foreground-задачи, остальные доступны через статус.

Каждый frame — replaceable preview, с coalescing и ограниченным TTL; финальное сообщение идёт через durable delivery ledger. Draft success=True не означает сохранённый ответ. Final send сохраняет provider message_id и immutable result/version. Если final rich send завершился timeout/unknown, **не** отправлять plain fallback автоматически: ответ мог уже сохраниться. После доказанного format rejection можно отправить другой renderer того же результата. Повтор edit известного message_id проверяется по revision и безопасной retry policy.

Нажатие native Stop не содержит `from`: валидировать доверенный Bot API ingress, exact owner private chat, thread и активную draft binding/generation. Событие старого draft не отменяет новую задачу. Inline Stop и обычное «стоп» идут в тот же D02 resolver. Сначала durable cancel fence, затем прекращение будущих tool calls/egress/preview updates и попытка прервать текущий HTTP/model stream. У провайдера выполнение/списание может продолжаться: не обещать мгновенный provider cancel. Уже отправленный effect и unknown receipt остаются в учёте; отмена вычисления их не отменяет.

По умолчанию `keep_on_stop=false`; при необходимости сохранить только проверенный partial result отдельным явным сообщением. Старые provider completions после cancel не оживляют draft и не меняют focus. При недоступности draft работают status card и текстовый cancel, без потери способности управлять задачей.

Модельный streaming входит в существующий D05 protocol transport: SSE parsing, tool/event schema, usage settlement, partial/timeout/cancel и guards на каждом публикуемом блоке. Для grounded Search/Brief выводить только проверенные завершённые блоки; до них — progress. Для обычного Chat провести matched latency/quality сравнение; UI не должен заставлять модель пропускать citations или verifier. Эффектный поток повторно порезанного готового ответа не объявлять уменьшением model latency.

### 4. Один документ, несколько Telegram-представлений

`BriefDocument`/answer result остаётся source of truth. Новый pure renderer строит `InputRichMessage.blocks`: heading, paragraph, небольшая table, details, source links/references и trusted buttons. Источники в раскрываемом блоке, вывод/что сделать — видимы сразу. Использовать 2–3 смысловых действия: «Источники», «Обсудить», «Сохранить»; дополнительные — по ситуации. В широкой таблице важнее чтение на телефоне, чем использование лимита 20 столбцов.

LLM не генерирует исполняемый Telegram JSON/кнопки/URL media. Renderer получает валидированное содержание и trusted navigation. Проверять nested limits до сети, блоки делить по границам разделов; весь документ доступен без silent truncation, PDF/MD остаются экспортом. Classic HTML splitter не применяется к rich syntax. Embedded remote media не загружаются автоматически; source URL и attachment policy проверяются отдельно. Не считать protect_content или скрытый details блок защитой от получателя сообщения.

Presentation edit меняет только отображение данной версии. «Обнови данные» создаёт новую версию документа; старые callbacks продолжают указывать на старую, с явным предложением открыть новую. Preview внешнего действия показывается полностью; сокращённый rich summary не заменяет exact content/recipient/time confirmation. Входящий rich_message обрабатывается как поддержанный документ/блоки в D34 либо даёт понятное unsupported, не молча пропадает.

### 5. Темы как удобная проекция, а не режим работы

Conversation key v2: owner + bot + chat + thread (null → существующий default context). Project/workspace identity хранится отдельно: переименование/закрытие Telegram topic не меняет проект или гранты. Миграция сохраняет существующую default conversation и result refs; новые thread conversations создаются с явным родителем/выбранным контекстом. Не копировать автоматически полную память другого проекта.

`TopicBinding` хранит thread_id, workspace/focus, display name, status и version. Разрешение обычного follow-up: reply binding → explicit object → текущий thread focus → однозначный recent; глобальное последнее сообщение не переопределяет активную тему. «Да» подтверждает только fully delivered preview в этой conversation и его version; неоднозначность требует выбора.

Рекомендуемый UX эксперимента: default разговор + до двух тем для длительных исследований. Ассистент предлагает отделить работающую задачу или делает это по однажды выбранной политике; не требует topic-picker перед вопросом. Закрытие темы не удаляет данные; deleteForumTopic не использовать как штатный архив. На rollback выключить создание тем, сохранить маршрутизацию старых ответов и «Продолжить» в основном чате с явной binding. Не объединять истории двух тем автоматически.

Изменить owner-wide serialization только в рамках D59: один активный compute на conversation при общем owner budget/concurrency cap; отдельная control lane остаётся отзывчивой. Две темы сами по себе не являются разрешением параллельно тратить неограниченные ресурсы.

### 6. Secretary: источник, черновик и действие — три слоя

Read connector D60 работает отдельно от owner command ingress. `BusinessConnection.user` должен совпадать с выбранным owner; `id`, `is_enabled`, rights и connection revision сохраняются. При неизвестном connection допустим только ограниченный getBusinessConnection и проверка, не обработка payload в LLM. Telegram-selected chats и локальный exact peer allowlist применяются совместно. Bot API BusinessConnection не выдаёт полный UI список выбранных чатов: не выдумывать discovery API. Владелец выбирает scope при подключении; неоднозначные peer identities уточняются до обработки.

Source identity: `(bot_ref, business_connection_id, peer_chat_id, message_id, revision)`; edits обновляют evidence/candidate version, deletes создают tombstone и останавливают связанные drafts/reminders. Переустановленная connection не переиспользует старые scopes. После outage показывать coverage since и возможный пробел; без подтверждённого backfill API не обещать восстановить пропущенную историю. Существующий Telethon archive не включается автоматически для заполнения пробелов.

`InboxCandidate` D61: источник/цитата, кто просит/обещает, действие, срок с precision/timezone, confidence/uncertainty, project, status, source revisions. Переиспользовать deadline/conflict правила Academic Inbox, но не называть всякую переписку академической. Сообщение «надо бы встретиться» не становится обязательством; черновик модели не превращается в обещание владельца. Owner-visible сводка показывает только важное и «что сделать», объединяет повторы, поддерживает snooze/dismiss/ответить. Дайджест и urgent thresholds используют D33; одна настройка, затем минимум обслуживания.

Результаты triage и drafts доставляются **только владельцу в чат ассистента**. Ни входящее сообщение постороннего, ни исходящее владельца в подключённой переписке не являются control-plane approval. Scope на получение текста, хранение, передачу выбранному LLM, background processing, owner notification и внешнюю отправку отдельны. Для внешней модели нужны разрешённый provider/data class и минимальный контекст. Telegram прямо требует разрешения пользователя на передачу Business data сторонним API и прозрачности обработки. [Bot Developer Terms §5.4](https://telegram.org/tos/bot-developers#5-4-telegram-business).

D62 добавляет `telegram.business_reply` к typed action contracts, отдельный adapter и точный preview: account/connection revision, peer identity, reply target, полный текст/entities/attachments, источник версии и expiry. Подтверждение только в owner control chat. Preview показывает, если ответ использует данные другого источника: межчатовое раскрытие не разрешается одним фактом чтения. Перед отправкой повторно проверить connection/right/recent inbound window/source revision/cancel fence и текущую привязку адресата. Ошибка expired 24h window оставляет локальный draft, не включает обход через личную MTProto-сессию.

У Bot API send нет обещанной server idempotency по нашему attempt_ref. Success с message_id — provider acceptance, не чтение собеседником. Timeout после начала запроса — unknown, без автоматического повтора. Возможность сверки по business updates/own-message echoes **не подтверждена здесь**: проверить в выделенном canary; если точной сверки нет, оставить manual reconciliation и запрет blind retry. Incoming/forwarded quote не может подтвердить неизвестный effect. Mark-as-read/delete/profile/gifts/stars/bot-to-bot права остаются выключены: они не нужны для выбранного секретарского сценария.

### 7. Данные и миграции

Новые bindings/presentation/connection records хранить в текущем Postgres, с owner/version/expiry и lineage; private snippets не дублировать без нужды. Предлагаемые logical records: transport capabilities, message binding, draft presentation state, topic binding, business scope revision и inbox candidate. Конкретная DDL выбирается кодирующим агентом в соответствующем пакете после проверки действующих repository schemas; versioned migration обязательна, изменение старого checksum без миграции запрещено.

Разделить ephemeral progress frames и durable final deliveries. В ephemeral storage достаточно latest frame digest/stage/revision, не полного токенового лога. Message/result/source refs включить в D42 deletion cascade; tombstone блокирует serving и generation на старой версии. Минимальный effect receipt сохраняется для no-replay, без удалённого текста. В URL/callback/обычных логах — opaque IDs, не содержимое переписки или токен.

## Место в общем backlog

Порядок исполнения задают только [BACKLOG](BACKLOG.md) / [backlog.json](backlog.json) и [этапы общей стратегии](README.md#последовательность-и-критерии-перехода). D56–D62 встроены в них вместе с уточнениями D02/D04/D05/D19/D25/D26/D27/D28/D34/D38–D44/D47. Отдельных Telegram-фаз или второго задания исполнителю нет.

D56 продолжает общий первый пакет D01–D03; D57/D58 входят в G1 и общую приёмку D40. Темы D59 — условное развитие G2. Выбранный Secretary D60→D61→D62 — G3 с раздельными read/draft/send gates, без зависимости от тем, почты и Canvas. Mini App исключён; D25 сохраняет обычный приватный reader. Отсутствие доступа к этим дополнительным возможностям не блокирует основной daily pilot.

Параллельно допустимы pure rich renderer D58 и progress schema D57 после общего D56 contract; fixture подбор для D59/D60 не требует аккаунтов. `bot.py`, `composition.py`, `transports.py`, conversation keys, action contracts и storage schema имеют одного назначенного владельца изменений на пакет. Перед интеграцией — синхронизация diff, без конкурентного переписывания общего файла. Зависимости задают завершение карточек; независимые DTO/fixtures можно готовить раньше live gates.

## Проверка эффекта, включение и откат

Baseline — текущий exact SHA и те же inputs/results. Сравнивать UI на фиксированных answer/Brief objects, чтобы смена модели не маскировала интерфейс; затем полноценные реальные задачи. Локальные fixtures, Telegram API receipts, клиентский visual review и польза владельцу — отдельные колонки. Из этого исследования есть только первая статическая/локальная часть.

| Набор | Как сравнить | Предлагаемый критерий перехода, ещё не измеренный |
| --- | --- | --- |
| 12 UI задач | 4 коротких ответа/follow-up, 4 исследования с ожиданием/stop/restart, 4 Brief со сравнением/источниками/сохранением. Чередовать baseline/new по одинаковым материалам. | 12/12 корректных route/result/version; 0 потерянных источников; минимум 10/12 выполнены без подсказки; median ручных действий ниже baseline хотя бы на 25%, либо установленный иной выигрыш по времени/читаемости без ухудшения остальных осей. |
| Progress/stop | Время durable ack, первого полезного status, meaningful content и final; synthetic slow call + real разрешённый запрос. | Project target: ack/status p95 ≤2s вне provider outage; visible stop acknowledgement ≤2s, новые tool/egress после durable cancel не начинаются. Текущий provider call может закончиться позднее; его стоимость/исход честно учтены. Не объявлять p95 по 2–3 запросам. |
| Rich report | Телефон владельца + desktop, версии/light/dark, длинный русский текст, sources, table, 32K/blocks overflow, файлы, fallback. | 0 clipping/lost facts/source links; тот же document digest/version; владельцу легче проверить вывод и выбрать следующий шаг. Старый клиент имеет читаемый путь. |
| Topics | 8 ходов попеременно в двух проектах, reply на старый результат, late completion, два «да», один stop и restart. | 0 cross-topic history/confirmation/cancel; возврат к нужному результату быстрее default focus baseline. Если нет пользы — выключить создание тем, сохранить безопасную модель идентичности. |
| Secretary triage | Synthetic set: 30 входящих, 10 обязательств/просьб, дубли/редакции/удаления/инъекции; затем 7–14 дней в 1–2 выбранных переписках. | Proposed recall ≥9/10 seeded важных items, false actionable ≤2/20 остальных; 0 invented deadlines/unauthorized disclosure. В реальном периоде считать абсолютные misses/noise и оценку владельца, не переносить synthetic проценты. |
| Secretary send | Выделенный consenting test peer, exact preview/edit/confirm, expired window, revoke race, injected timeout. | Одно подтверждение → не более одной попытки отправки; wrong recipient/source version отвергнуты; unknown не повторяется. Никаких live сообщений без отдельного выбранного canary. |

Пользовательская нагрузка ограничена коротким сравнением интерфейса и привычными задачами в существующем D38/D39 пилоте. Не заводить новый ежедневный журнал. Недельный эффект считать с учётом времени чтения, настройки и исправлений; красивые таблицы без сокращения усилий не оправдывают новый компонент.

Включение: offline capability config → synthetic transports/fixtures → независимый Deep Review → выбранный test bot/chat canary → один owner deployment с feature flags → измерение пользы. Существующий grant переиспользуется в его scope; настройка BotFather, подключение переписок и sending tests выполняются только на следующем разрешённом этапе. Уровни rollout independent: controls, rich, drafts, topics, secretary-read, secretary-send.

Rollback: отключить новые preview/render/create-topic пути; сохранить bindings, consume/unknown receipts, scope revocations и tombstones. Для Rich known incompatibility включить classic/PDF renderer того же объекта; при unknown send сначала сверка. Для topics сохранить чтение старых ветвей без слияния истории. Для Secretary сразу остановить intake processing/egress/effects и отозвать локальный scope, отдельно отключить connection штатным способом; ранее отправленное не объявлять отменённым. Forward-compatible migration сохраняет default conversation и старые receipts; schema rollback не стирает факт действия.

## Передача следующему агенту

Использовать единое [IMPLEMENTER_START](IMPLEMENTER_START.md). Сверить фактическую готовность D01–D03; если открыты — закончить их, затем D56. После его scoped checks и Deep Review взять dependency-ready D57/D58. Доступ к личным перепискам для этого не нужен. Остальные карточки, команды и критерии перехода находятся в общем backlog и общем задании; повторное общее исследование Telegram не требуется.
