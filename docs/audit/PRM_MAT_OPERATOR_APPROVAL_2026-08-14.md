# PRM-MAT operator approval — 2026-08-14

The operator approved both previously listed boundaries:

1. PRM-MAT-6/7/11 durable lifecycle work: approved schema work, retention
   policy work, confirmation-gated durable object/receipt implementation, and
   tests against temporary fixture databases. This does not authorize a
   migration or write against the production archive database, dogfood start,
   or automatic conversation-to-memory promotion.
2. PRM-MAT-10 bounded primary-source verification: approved implementation of
   the restricted verification mechanism and its external-cache design. It
   does not imply unrestricted browsing, provider use, third-party execution,
   or a live fetch before a concrete trusted-host allowlist and fetch budget
   are recorded.

The standing global test policy remains: only focused, relevant tests; never a
full pytest-suite run.
