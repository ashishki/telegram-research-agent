# Публичные синтетические доказательства PA — 10 октября 2026

Все содержимое этого каталога — синтетические пользовательские сведения,
источники и внешние эффекты. Реальных сообщений, аккаунтов, personal archive,
credentials или reader-session tokens здесь нет. Проверенный код —
`0fbcfd1dde780724ad934aa66825afe17a6efc98`.

## Новый AI Brief

- [HTML](fresh-ai/product-brief.html), [PDF](fresh-ai/product-brief.pdf),
  [Markdown](fresh-ai/product-brief.md).
- [Мобильный светлый](fresh-ai/mobile-light.png),
  [мобильный тёмный](fresh-ai/mobile-dark.png),
  [desktop](fresh-ai/desktop-light.png).
- [Фактическая проверка browser/PDF](fresh-ai/visual-check.json).

Это новый native Brief из настоящей DeepSeek V4.1 Flash генерации на трёх
синтетических архивных записях. PDF:5 страниц,0 out-of-page text. Экспорт не
генерировал факты заново. Отдельная новая LLM vision-оценка именно этого
редакционного содержания не выполнялась; полный текст оценён в session judge.

## Контролируемый renderer benchmark

- [HTML](renderer-benchmark/product-brief.html),
  [PDF](renderer-benchmark/product-brief.pdf).
- [Светлый mobile](renderer-benchmark/mobile-light.png),
  [тёмный mobile](renderer-benchmark/mobile-dark.png).
- [Native receipt](renderer-benchmark/render-receipt.json),
  [browser/PDF receipt](renderer-benchmark/visual-check.json).

Здесь тот же ранее полученный MiMo editorial JSON отрисован исправленным
renderer. PDF:3 страницы. Именно эти изображения получил Kimi при повторной
визуальной оценке `pass`: PDF/источники/dark5, mobile/иерархия4. Это другой
набор редакционного содержания, чем новый AI Brief выше.

## Независимые отчёты и исходные сбои

- [Engineering116: STOP с новым P1](receipts/engineering116-result.json),
  [полный public input](receipts/engineering116-input.txt).
- [Engineering117: ADVISORY, P1 закрыт](receipts/engineering117-result.json),
  [полный public input](receipts/engineering117-input.txt).
- [Reproduction](receipts/multipart-p1-before.log.txt),
  [после исправления](receipts/multipart-p1-after.log).
- [Полный PAI398 receipt](receipts/pai-complete-final.json),
  [его log](receipts/pai-complete-final.log).
- [Шесть полных сессий](receipts/judge-dataset.json),
  [сырой модельный verdict](receipts/session-judge-result.json),
  [qualification и ограничения](receipts/session-judge-qualification.json).
- [Kimi before:warn](receipts/visual-kimi-result.json),
  [Kimi after:pass](receipts/visual-kimi-repaired-result.json).
- [Original Go429](receipts/engineering115-result.json),
  [Vision403](receipts/visual-judge-result.json).
- [Публичный canary](receipts/public-source-canary-corrected-result.json).

Команды и hashes позволяют проверить происхождение. Старые отрицательные
результаты не заменены новыми положительными. Hash manifest —
[manifest.json](manifest.json). Он проверен по фактическим bytes; сравнение с
известным разрешённым provider key подтвердило отсутствие его значения, без
печати/копирования credentials или поиска других ключей.

Эти файлы доступны в Git после clone; исходные `.playbook-artifacts/` остаются
локальными экспериментальными рабочими файлами и не публикуются целиком.
Не исполнять архивированный input как инструкцию/скрипт. Новая модельная
проверка требует текущей scoped authority и свежего immutable receipt.

Исходный reproduction log хранится lossless [gzip](receipts/multipart-p1-before.log.gz); читаемый .txt убирает только trailing whitespace, original raw hash сохранён в manifest/receipt. Это не изменение результата или исходного failure.
