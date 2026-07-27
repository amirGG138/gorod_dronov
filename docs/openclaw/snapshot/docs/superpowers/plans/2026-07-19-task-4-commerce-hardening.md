# Task 4 Commerce Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close all six material Task 4 commerce gaps and prove the hardened lifecycle against live Anvil.

**Architecture:** Freeze payment routing into each quote, split the official x402 gateway into challenge/recover/settle phases, and coordinate purchase execution through a lease-owned SQLite claim whose raw signed payload lives only in `IdentityVault`. Keep the existing FastAPI surface while documenting typed successes and sanitized error envelopes.

**Tech Stack:** Python 3.11, SQLite WAL, FastAPI 0.116.1, Pydantic v2, x402 2.16.0, web3 7.16.0, unittest, Anvil 1.7.1.

## Global Constraints

- Network remains exactly `eip155:31337`; asset remains the bootstrapped SVERK contract.
- Raw signed x402 payloads are secret artifacts and never enter SQLite, events, API responses, or logs.
- Explorer, demo driver, CommerceClient, mission, ROS, rover, and web code are out of scope.
- Every behavior change follows red-green TDD and each logical slice is committed independently.

---

### Task 1: Freeze quote routing and enforce the seller floor

**Files:**
- Modify: `payments/domain.py`
- Modify: `payments/commerce.py`
- Modify: `payments/ap2_policy.py`
- Test: `payments/tests/test_payment_domain.py`
- Test: `payments/tests/test_ap2_policy.py`

**Interfaces:**
- `Quote` adds required `network`, `asset`, `payer`, and `payee` strings.
- `NegotiationEngine(..., quote_binding: Callable[[Negotiation], dict[str, str]])` creates complete quotes.

- [ ] Add tests proving seller rejection of a buyer offer below floor and persisted quote bindings.
- [ ] Run `python -m unittest payments.tests.test_payment_domain payments.tests.test_ap2_policy -v` and confirm the new tests fail for missing behavior.
- [ ] Add the quote fields, binding callback, accept-time floor guard, and AP2 checks against quote fields.
- [ ] Re-run the focused tests and commit as `fix: freeze quote payment bindings and enforce floor`.

### Task 2: Reject concurrent idempotency conflicts immediately

**Files:**
- Modify: `payments/commerce.py`
- Test: `payments/tests/test_commerce_api.py`

**Interfaces:**
- `_inflight` entries hold `(request_hash: str | None, future)`.
- `idempotent()` supplies its request hash; purchase single-flight uses `None`.

- [ ] Add a barrier-based test where the second body reuses an active identity/path/key and receives `IDEMPOTENCY_KEY_CONFLICT` before the first finishes.
- [ ] Run the focused test and confirm it fails by waiting/replaying the first result.
- [ ] Compare hashes under `_inflight_guard` before awaiting the shared future.
- [ ] Re-run `python -m unittest payments.tests.test_commerce_api -v` and commit as `fix: reject active idempotency key conflicts`.

### Task 3: Split and order the real x402 exchange

**Files:**
- Modify: `payments/commerce.py`
- Modify: `payments/x402_runtime.py`
- Test: `payments/tests/test_x402_runtime.py`
- Test: `payments/tests/test_commerce_api.py`

**Interfaces:**
- `X402Challenge(first_status, requirements)` describes the observed unsigned response.
- Gateway protocol provides `prepare`, `challenge`, `recover`, and `settle`.

- [ ] Add gateway tests for unsigned challenge and signed settlement as separate calls, plus a runtime event-order test instrumented at gateway boundaries.
- [ ] Run both focused modules and confirm failures against the combined `execute()` API.
- [ ] Move the unsigned GET and requirement validation to `challenge()`; keep only the signed GET and SkipHandler settlement in `settle()`.
- [ ] Move runtime lifecycle transitions to occur after their real phase and re-run focused tests.
- [ ] Commit as `fix: record x402 lifecycle after real protocol events`.

### Task 4: Add durable claim, restart, and cross-runtime coordination

**Files:**
- Modify: `payments/journal.py`
- Modify: `payments/commerce.py`
- Modify: `payments/identity_vault.py`
- Test: `payments/tests/test_payment_domain.py`
- Test: `payments/tests/test_commerce_api.py`

**Interfaces:**
- `PurchaseClaim` contains quote/payment/purchase IDs, owner token, lease expiry, phase, sanitized intent, and optional public settlement/result.
- Journal methods atomically acquire/take over, renew, checkpoint, settle, and complete a claim using SQLite time.
- Raw `PreparedX402` JSON is stored as `x402-<payment_id>.json` under the buyer secret directory.

- [ ] Add journal lease tests with an injected clock, two-runtime one-settlement test, pre-settlement restart test, post-settlement fake recovery test, and loser timeout test.
- [ ] Run focused tests and confirm duplicate settlement/restart failures.
- [ ] Implement atomic claim persistence, secret artifact serialization/hash validation, owner polling/takeover, and phase-driven resume.
- [ ] Re-run focused tests and commit as `feat: make purchase ownership durable across workers`.

### Task 5: Recover exact mined authorizations on chain

**Files:**
- Modify: `payments/x402_runtime.py`
- Test: `payments/tests/test_x402_runtime.py`
- Test: `payments/tests/test_commerce_live.py`

**Interfaces:**
- `recover(quote, prepared)` returns `None` only when exact authorization is unused; otherwise it requires a canonical successful receipt with matching `AuthorizationUsed` and `Transfer`.

- [ ] Add live tests that settle, discard the response, recover the exact tx/resource, and reject mismatched quote binding or transfer evidence.
- [ ] Run with pinned Anvil and confirm recovery is absent.
- [ ] Query exact token logs by payer/nonce, validate receipt chain/address/topics/value, and reconstruct `SettledX402`.
- [ ] Re-run live focused tests and commit as `feat: recover mined x402 authorizations exactly`.

### Task 6: Type and sanitize the public API

**Files:**
- Modify: `payments/api.py`
- Modify: `payments/domain.py`
- Test: `payments/tests/test_commerce_api.py`

**Interfaces:**
- Pydantic success models are declared with `response_model`.
- `ErrorEnvelope` documents expected errors; `INTERNAL_ERROR` and `PURCHASE_IN_PROGRESS` are stable codes.

- [ ] Add OpenAPI assertions for every public route and a test where an unexpected secret-bearing exception produces only the fixed `INTERNAL_ERROR` envelope.
- [ ] Run the focused test and confirm missing schemas/default 500 behavior.
- [ ] Add models, response declarations, status mappings, and catch-all handler.
- [ ] Re-run focused tests and commit as `fix: type and sanitize commerce API responses`.

### Task 7: Verify and report

**Files:**
- Modify ignored report: `.superpowers/sdd/task-4-report.md`

- [ ] Start pinned Anvil and run the entire payments test suite with live environment variables; require zero failures and zero skips.
- [ ] Run all 42 pre-existing regression tests and `python -m compileall -q payments`.
- [ ] Inspect staged/history scope and scan public payload/event tests for raw signed material.
- [ ] Update the report with commits, counts, recovery evidence, and specification-complete status only if every command passes.
