# Review 56 — research/source follow-through

GitHub per-file fallback now propagates CapabilityDenied and all StorageError (including StateConflict) rather than disguising revocation, cancellation or exact-path/size violations as partial availability. A grant revoked between commit and file read denies the next read; the initial test tried revoking inside the held transport transaction and timed out, so the corrected counterexample revokes immediately after that transaction completes. Both observations are preserved.

Interrupted read_prepared rows now advance durably to source_outcome_unknown under lineage/lease locks and actual expected_version. Their tool-call upper bound MUST remain conservatively consumed: an interrupted read is not proof of zero external work. A recheck must not suggest resetting this fence or refunding possible spend. The existing test verifies no re-read and now also checks the persisted version/status.

Window evidence skips missing/non-string/blank canonical content instead of indexing an invalid body. Full-content SHA remains canonical; truncating before hashing would weaken provenance.

Missing dependency review is an evidence limitation, not by itself an executable defect. The follow-up supplies public_web, claim_ledger, jobs and registry sources. All claimed unreviewed dependencies remain explicit; these are advisory code reviews, no human/design/live acceptance.
