# Implementation pass — 2026-10-07

Owner sequencing: ADR-015. No tests, test tiers, validators, provider diagnostics
or independent review have been run in this pass. No dependency was installed.
No server, worker, scheduler, account, migration or deployment was activated.
Engineering status is implementation_unverified, not accepted/local_verified.

Code now covers the local PAI-10..25 components:

| Cards | Added implementation |
|---|---|
| 10–11 | Explicit composition, credential/endpoint binding, HTTP model transport, independently authorized bounded history, canonical source-bound archive synthesis |
| 12–13 | Brave discovery, DNS-pinned source reads, exact commit GitHub reads, persistent research gather/synthesis/verification checkpoints |
| 14–15 | Selected source hooks, structured editorial, immutable PostgreSQL Brief manifests/documents, visible version bindings, restricted subprocess exports and authenticated loopback reader |
| 16–19 | Graph OAuth/PKCE, one-use state, encrypted vault, account identity, refresh/disconnect, mail delta/page state, calendar/contacts, minimal paged Canvas and academic conflict/local completion |
| 20–22 | Exact action preview/edit/confirmation/receipt, Graph executor, memory previews/tombstones/dependencies, media download/extract/STT/vision and actual temporary-file cleanup |
| 23–25 | Versioned usage/tariffs, scoped caches, health/epoch/drain/kill, private PostgreSQL dump/restore and monotone receipt/tombstone transfer |
| 26 | Candidate inventory code, prepared per-card suites and ten scenario/load-recovery entrypoints; execution and independent acceptance deferred |

CLI and one-role service entrypoints select target/config explicitly. Service
examples are inactive. Restores disable egress and drain intake; old unknown
attempts never authorize resend. Historical SQLite archive/watch sender paths
were retained. No Redis/vector/archive migration was introduced.

The follow-through pass closes the previously recorded local gaps:

- Brief source hooks include selected calendar snapshots and academic state,
  with explicit source classes, current scopes and durable dependency edges.
- Academic local completion stops linked Watch subjects in the same transaction.
  The displayed completion command identifies the persisted item; source
  submission and academic eligibility remain distinct. Explicit stage selection
  uses memory preview/confirmation. Selected mail/calendar metadata can enter
  the academic merge only through configured academic selections and grants.
- Forget invalidates derived response/job copies, history, caches, Brief rows,
  files and linked reminders. Delivery fences retain digests/outcomes while
  deleted text is redacted. A failed filesystem cleanup remains cleanup_pending.
- Restore applies current and backed-up tombstones through that same graph,
  relocates the private artifact index and removes deleted/unindexed bytes.
- Domain transfer covers selected runtime tables, including conversation,
  memory, source/cache, schedule and artifact state. It preserves consumed
  confirmations, terminal/unknown receipts and spent budgets, verifies the
  target again under table locks, and leaves egress disabled.
- Source origin survives shortening, item follow-ups and mixed-source delivery.
  Each delivered data class needs a current scope. Long answers have separate
  bounded part attempts and an aggregate unknown fence; interrupted partial
  sends are never blindly repeated.
- Action execution checks account/recipients/thread, current event ETag and
  selected calendar availability before confirmation is consumed. User command
  confirmation includes exact proposal version/digest; plain yes additionally
  requires provider-confirmed delivery of the current preview. Positive
  reconciliation matches the original sent-item headers or event transactionId.
- `/deep` enqueues a bounded research plan; independent reads use at most two
  threads and precommitted step records. Interrupted ambiguous reads are not
  reissued. `/watch` prepares an exact subscription for confirmation; selected
  archive/mail sources share the durable scheduler.
- `/mailread` obtains only an explicitly scoped selected message body, converts
  HTML to inert text and requires separate body egress for model synthesis.
  Selected calendars share a bounded page plan; original provider time-zone
  metadata is retained alongside normalized instants and the local display zone.
- Task-cost recording now includes Chat/archive/research/editorial/connector/
  media calls and unknown usage. Extraction/retrieval/render caches are wired;
  model-role profiles retain the baseline until comparable quality is measured.
  The paired holdout comparator never grants release authority.
- Operations expose queue/unknown ages, sync freshness, connection/lock counts,
  disk and costs. CLI commands cover private state manifest/domain export/import
  and isolated restore. Backup requires drained, egress-disabled state.
- All 69 named requirement cases are prepared in test_pai_requirements.py.
  Required pai-complete registration binds them to the existing ten scenarios.
  New regression cases cover the additions above. None has been executed.

Remaining work is evidence and acceptance: run the deferred synthetic tiers,
fix observed failures, independently review the exact code, assess each of the
69 cases for sufficient behavioral evidence, and obtain scoped actual-provider,
visual/operator and measured recovery observations. Code presence is not proof
of complete behavior. No current SHA is reviewed or tested. Production target
selection belongs to the separately scoped cutover work; live account,
institution, deployment and release gates persist. Missing authoritative
provider lookup remains unknown; bounded absence never proves non-delivery.

Publication commits: d4d45a2 (initial composition) and 19477b2 (source/media/
recovery components), plus subsequent integration/doc commits in this branch.
Neither commit has independent review. Mimo stays 23/30 consumed; no new call.

Prepared validation is under tests/test_pai_*.py and tools/run_pai_acceptance.py.
PAI-27..29 packages below record exact prerequisites; they do not claim canary,
deployment or owner acceptance. PAI-30/31 conditions are unmeasured, so no
conditional infrastructure change or not_needed verdict is manufactured.

Primary API sources used during implementation: [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
[OpenAI transcription](https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions/methods/create),
[Brave Web Search](https://api-dashboard.search.brave.com/app/documentation/web-search/codes),
[GitHub commits](https://docs.github.com/en/rest/commits/commits),
[GitHub contents](https://docs.github.com/en/rest/repos/contents),
[Graph delegated OAuth](https://learn.microsoft.com/en-us/graph/auth-v2-user),
[Graph delta](https://learn.microsoft.com/en-us/graph/api/message-delta?view=graph-rest-1.0),
[Graph sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0),
[Graph event creation](https://learn.microsoft.com/en-us/graph/api/user-post-events?view=graph-rest-1.0),
[Graph event update](https://learn.microsoft.com/en-us/graph/api/event-update?view=graph-rest-1.0),
[Canvas assignments](https://developerdocs.instructure.com/services/canvas/resources/assignments).


Next command, for the deferred verification phase (not run in this pass):

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/test_tiers.py pai-complete
```

Then run the required focused project/Playbook checks and accumulated fresh
independent Mimo review on the exact implementation SHA. Do not reuse b267854's
652 passes or infer live/visual evidence from synthetic cases. Review budget is
still 23/30 consumed; no call was made in this follow-through pass.

Implementation SHA: e81b066646254e69af0e1c6ad749524387c199fa. Exact changed-file inventory and command outcomes: PAI-local-code-receipt-20261007.json. Reviewed SHA: none.
