# Review 55 — logical request identity and cancellation

A new explicitly authenticated input is a new model task even if its text repeats. The durable fence denies EVERY re-invocation of the same logical task/purpose, including divergent bodies and newly reserved operation IDs, without comparing input_digest to permit anything. Different request_refs intentionally represent separate owner requests and independently accounted calls, not an automatic retry loophole. Existing unknown-fence test and new repeated-question integration test demonstrate the distinction.

Cancellation cannot undo a processed HTTP request or its cost. Composition rechecks the lease AFTER assistant.answer and before durable conversation/result completion; queue.complete also fences the lease. A real HTTP test cancels immediately after the accepted provider reply, verifies StateConflict, no result_ref and retained spend. No accepted call is converted to a retryable unknown or refunded.

The P2 pretransport bounds are strengthened: max_tokens is a bounded integer (1..16000), prompt/system/history strings are bounded before JSON allocation, then the existing 48000-byte total cap applies. Local bounds do not create an attempt fence.

Initial cancellation test mistakenly expected None from a worker that intentionally raises StateConflict; the failure is preserved. Corrected command/results are recorded separately. No reviewer acceptance is self-issued.
