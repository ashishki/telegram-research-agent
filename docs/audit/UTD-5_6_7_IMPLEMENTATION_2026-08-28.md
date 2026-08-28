# UTD-5/6/7 implementation — 2026-08-28

Status: technically implemented; live operator quality validation intentionally deferred to dogfood.

## What is complete

The shadow candidate stream now has a separate delivery gate. Delivery requires all of: an explicit CLI `--enable-delivery`, `UTD_WATCH_DELIVERY_ENABLED=1`, and absence of `UTD_WATCH_KILL_SWITCH=1`. Missing Telegram owner credentials fail closed. Collection remains independently usable with delivery disabled.

Every attempted candidate is capped by the existing five-item selector and receives a deterministic delivery key. Successful sends write a sidecar-only receipt; the same material candidate cannot be sent twice. Telegram cards carry source/reason text and feedback controls for useful, noise, more, less, mute and pause. Mute/pause feedback is recorded but does not silently mutate the confirmed profile.

Feedback callbacks are wired into the existing PRM Telegram callback namespace (`utdw:`) and write only to the configured UTD sidecar. Feedback is aggregated into observed precision and a calibration report. Calibration may propose source/category up/down-weighting but never edits the confirmed profile automatically. This is designed so real dogfood can produce actionable evidence immediately.

## Safety boundary

No timer is enabled, no delivery environment flag is set in the repository, no Telegram token/chat ID is stored, and no production sidecar is created by this implementation. Live notification quality claims remain unmade until operator dogfood exists.

## Intended live sequence

1. Run shadow-only and inspect candidates.
2. When ready, set the delivery environment flag and invoke the one-shot live harness with `--enable-delivery`.
3. Use Telegram feedback buttons naturally.
4. Read `--feedback-summary` and the calibration report before changing relevance weights.
5. Keep the kill switch available as an immediate stop.

The temporary repository-edit workflow used to wire the runtime removed itself after the integration commit. The final ordinary commit exists to force the normal CI workflow to validate the cleaned tree rather than relying on GitHub Actions' self-push behavior.
