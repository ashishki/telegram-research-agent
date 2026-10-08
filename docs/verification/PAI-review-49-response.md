# Review 49 — media boundaries and migration counterexample

Every local, cached and OCR page payload is validated: required dict/status/pages, bounded positive ascending unique integer page numbers, bounded string bodies and aggregate length. OCR page numbers cannot exceed the local document page count. Missing fields/types fail with StorageError before caching/citation use.

An injected OCR callable requires explicit provider identity, cost upper bound and dedicated media.ocr grant. Missing scope returns ocr_unavailable without calling the adapter. Remote OCR also uses the durable logical task attempt fence and execute_reserved accounting; a repeated task cannot make another call. Cache remains subject to current source authorization.

Telegram download now requires a durable conversation input authenticated to the owner and exact matching file/kind, before reservation or HTTP. Composition passes the fenced input reference for voice and images/documents. Foreign/unbound/mismatched inputs are tested.

The migration allegation assumes legitimate recreation of the same deleted identity. StateTransaction.put rejects tombstoned identities; deletion is monotone. Migration intentionally reapplies retained tombstones. Weakening deletion to skip restored objects could resurrect content. Full storage/deletion/migration sources and scoped tests are supplied for independent resolution.

Observed report-media-fixes-final.log: 30 passed in 75.64 s, source-cleanup-delete-proof.log: 15 passed in 53.11 s; final added lineage case recorded separately. No live source or provider result is inferred.
