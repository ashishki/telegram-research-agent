# Archive Refresh

Status: bounded approved routine
Last updated: 2026-08-12

The active weekly timer performs only the approved bounded local archive refresh.
It is not legacy ingestion, reaction sync, report generation, provider egress,
or operator-test evidence by itself.

Manual refresh writes the canonical local archive and requires separate explicit
approval plus `--confirm-canonical-write`. Do not run it as a documentation or
test step. See `docs/audit/PRM_MANUAL_ARCHIVE_REFRESH_2026-08-12.md` and
`docs/PRODUCT_OPERATING_MODEL.md` for the recorded boundary.
