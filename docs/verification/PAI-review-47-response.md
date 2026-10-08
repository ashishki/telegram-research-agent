# Review 47 — concrete Brief and artifact fixes

The reader artifact key now includes owner, brief ID, immutable version, content digest and format. A PostgreSQL/subprocess counterexample creates two reports with identical content and separate identities, verifies separate artifact lineage, deletes one and verifies the sibling remains readable.

Brief collection now abandons a reservation only if it is still unprepared. The registry itself already settles a transport exception as unknown and conservatively charges its upper bound. It must not be refunded as known failure. Scoped tests verify the unknown charge can be reconciled to actual zero without clearing the attempt, and revocation immediately before preparation releases an unprepared reservation without calling the collector.

Observed: brief-reservation-fixes.log: 7 passed in 33.74 s. report-media-fixes-final.log: 30 passed in 75.64 s. Final reader-lineage test is recorded separately after actual completion. No live accounting or human visual acceptance is claimed.
