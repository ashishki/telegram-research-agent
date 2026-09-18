# PRM-SN-4A receipt

Pure `prm_news_edition.v1` projection added without collector, schema or
database changes. It retains distinct publication/update/fetch/check times,
uses instance-aware event identity, records repost family metadata, and makes
no write. Focused shadow/selection tests: `9 passed`.

Focused Terra/high review found and drove corrections for recurring instances,
repost family identity, deterministic edition ID, and material/cancellation
classification. Runtime collection, delivery and production migration remain
out of scope.
