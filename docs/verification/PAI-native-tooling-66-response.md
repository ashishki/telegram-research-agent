# Native tooling review 66 — concrete hardening and trust limits

Capture HEAD before building the packet. Before any key/provider call, every original manifest byte hash must equal the captured committed Git blob and current source; unrelated dirty files are allowed, dirty review inputs are denied. Provider output remains bound to post-call HEAD/document/gate checks.

Sources are a fixed public-code/synthetic-design allowlist, not runtime provider_ref-selected files. The manifest records the egress class/decision. Read/hash use one descriptor with O_NOFOLLOW, bounded bytes and hard-link denial; common credential/private-key material and explicitly private/credential/live-account metadata are denied before egress. Unstructured privacy cannot be cryptographically inferred; the no-private-content-in-Git contract and exact authorized source set remain the trust boundary. No private corpus/account payload was supplied.

Finalization now checks actual input packet/manifest bytes plus each report's role marker, full strict JSON schema and P0/P1/verdict consistency before aggregation. A rehashed report with a P1 under ADVISORY cannot be consumed even with matching sidecars.

SSE already required the exact provider-reported model on EVERY data event. Returning the matched observed event field now makes that provenance explicit. Identity is reported metadata over authenticated TLS, not signed physical-model attestation; no signed attestation is available or claimed. Request echo without model-bearing events never passes. Reviewer requests for unsupported cryptographic proof remain a trust limitation, not a forged measurement.

Strict acceptance now rejects duplicate full test nodes and requires every spec case in the canonical requirement module. Extra regression tests remain allowed/required; exact equality with the smaller 69/scenario set would incorrectly drop regression coverage. The checker separately prevents aliased spec case names.

Per-invocation cap is one, with existing caller allocation/ongoing owner authorization and failed-call counting. Numeric/monetary caller authority advisories remain explicit, no new product spending. Fresh independent native audit is required before design consumption; no implementer acceptance or tooling bypass.
