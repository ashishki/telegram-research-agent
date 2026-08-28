# PRM Repository Retrofit

Status: active structural retrofit

This directory contains the current repository-retrofit plan and dependency inventory for the Personal Telegram Research Memory product.

The retrofit follows these rules:

- preserve runtime behavior while introducing one PRM application boundary;
- keep historical documents under `docs/archive/`;
- use Git history and the pre-retrofit branch point as the archive for removed executable code;
- keep only thin compatibility adapters in the active tree;
- do not delete database migrations or safety/privacy tests;
- do not perform destructive user-surface cleanup before operator smoke evidence exists;
- never mix file moves, behavior changes, and deletion in one commit.

Canonical retrofit artifacts:

- `docs/tasks.md`
- `docs/retrofit/RFX_REPOSITORY_RETROFIT.md`
- `docs/retrofit/RFX_DEEP_REVIEW.md`
