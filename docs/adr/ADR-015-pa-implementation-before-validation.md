# ADR-015: accumulate implementation before validation

Date: 2026-10-07. Status: owner-directed development sequencing.

Owner: «реализуй дальше до конца тасков и только потом будем тестить и
липиревью делать». Continue the authorized local PAI-10..26 implementation
queue, adding acceptance tests without executing them. Prepare PAI-27..29
packages; live accounts, production and release still need their exact gates.
Defer test execution and independent reviews until the implementation queue is
ready. No further Mimo call during this implementation pass. Existing failed
reviews and 23/30 consumed calls remain evidence, not approvals.

New engineering progress is implementation_unverified, never local_verified
or accepted. This supersedes intermediate test/review cadence in repository
instructions for this pass; it does not change runtime default-deny policy,
human completion authority or data/account/production permissions.
