# Review 48 — source counterexamples and malformed metadata fix

Cursor reads are bounded authorized read operations, not single-use write confirmations. GraphMailAdapter and CanvasAdapter bind stored cursors to owner, connection and selection digest and validate same-origin URLs before credentials/transport. Every continuation uses a fresh reservation/current grant. Reuse does not override a changed selection or revoked grant. Executable Graph tests demonstrate both denials before HTTP. No cursor reset or permission expansion was introduced.

Credential retirement intentionally checks active secret references across all owners. A corrupted retirement record must not delete a token still active under another owner. An executable PostgreSQL/vault test creates that case and verifies the token remains intact. A pending cleanup record is a conservative availability result, not consent to delete the other owner's token.

Malformed mail dates/nested sender fields now raise typed StorageError before row insertion. Three synthetic malformed-provider cases verify this.

Observed source-cursor-metadata.log: 19 passed in 62.11 s; source-cleanup-delete-proof.log: 15 passed in 53.11 s. Scope is synthetic only. Findings require independent factual recheck; this response does not grant approval.
