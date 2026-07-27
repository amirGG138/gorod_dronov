# Survey + Commerce Live Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an optional combined survey dashboard where spectators can follow agent negotiation and independently verified AP2/x402/Anvil settlement in real time.

**Architecture:** The payment explorer remains the read-only source of truth. A credential-free observer converts its sanitized SSE stream and evidence snapshots into `kind=commerce` blackboard events; the existing survey SSE carries those events to an opt-in spectator dock. The normal mission, `/survey`, ROS bridges, and payment authorization paths remain independent.

**Tech Stack:** Python 3.12 stdlib observer, FastAPI explorer, append-only blackboard JSONL/SSE, vanilla HTML/CSS/JavaScript, Docker Compose, Anvil `eip155:31337`, unittest, real Chrome/Playwright verification.

## Global Constraints

- The mission must continue if payment, observer, or explorer fails.
- The observer may read only sanitized explorer endpoints and may write only blackboard events.
- Raw AP2 SD-JWTs, EIP-3009 signatures, x402 payloads, bearer credentials, and private keys must never enter the blackboard or dashboard.
- A green confirmation requires matching AP2 verification, receipts, indexed transfer, participants, amount, and transaction hash.
- `/survey` is unchanged; commerce is opt-in through `/survey-commerce` and can be disabled with `?commerce=0`.
- No agent role, mission phase, ROS command, rover code, or LLM decision is modified.

---

### Task 1: Explorer Evidence Contract

**Files:**
- Modify: `payments/explorer.py`
- Modify: `payments/tests/test_explorer_api.py`

**Interfaces:**
- Consumes: existing `ExplorerService.payment(payment_id)`.
- Produces: `detail["evidence"]` with `ap2_verified`, `receipts_verified`, `receipt_tx_match`, `transfer_indexed`, `participants_match`, `amount_match`, and `onchain_confirmed`.

- [ ] **Step 1: Write the failing evidence test**

Add assertions to `test_detail_is_sanitized_and_has_verification_summaries` proving all seven evidence flags are true for the matched fixture, then mutate the receipt confirmation hash in a second test and assert `receipt_tx_match` and `onchain_confirmed` are false.

- [ ] **Step 2: Verify RED**

Run:
`docker compose -f docker-compose.payments.yml run --rm commerce-runtime python -m unittest payments.tests.test_explorer_api.ExplorerApiTests.test_detail_is_sanitized_and_has_verification_summaries -v`

Expected: failure because `evidence` is absent.

- [ ] **Step 3: Implement evidence derivation**

Add a private `ExplorerService._evidence(payment, indexed, mandates, receipts)` method. It compares normalized addresses, atomic amount, tx hash, receipt confirmation, verification booleans, and indexed integrity status. Return public booleans only and include it in `payment()`.

- [ ] **Step 4: Verify GREEN and commit**

Run the explorer API test module, inspect staged diff for secrets, then commit:
`feat: expose spectator-safe payment evidence`.

### Task 2: Exactly-Once Commerce Observer

**Files:**
- Create: `payments/blackboard_bridge.py`
- Create: `payments/tests/test_blackboard_bridge.py`

**Interfaces:**
- Consumes: explorer `/v1/explorer/events`, `/payments/{id}`, and `/participants`.
- Produces: `CommerceNarrator.consume(source_event, detail=None, participants=None) -> dict | None` and append-only `kind=commerce` events with `source_event_id`.

- [ ] **Step 1: Write failing narration and safety tests**

Cover open negotiation, offer, counteroffer, accept/quote, AP2 lifecycle, x402 settlement, final chain confirmation, failed payment, and unsupported events. Assert serialized output excludes `raw_sd_jwt`, `signature`, `x402_payload`, `authorization`, and `bearer`.

- [ ] **Step 2: Verify RED**

Run the new test module in the payment container. Expected: import failure because `payments.blackboard_bridge` does not exist.

- [ ] **Step 3: Implement the pure narrator**

Track negotiation buyer/seller/service and the last offer. Emit concise Russian bodies, normalized stages, public evidence, balances in cents, tx hash, block, gas, and timestamp. Use explicit allowlists; never recursively copy source payloads.

- [ ] **Step 4: Write and verify failing replay test**

Use a temporary `events.jsonl` and cursor file. Simulate a crash after append but before cursor update, reconstruct the observer, and assert scanning existing `source_event_id` prevents a duplicate.

- [ ] **Step 5: Implement the observer loop**

Parse SSE with stdlib `urllib.request`, resume through `Last-Event-ID`, enrich final events through sanitized JSON GETs, append one atomic JSONL line, and atomically replace `state/commerce_cursor.json`. Retry unavailable explorer with bounded 1–5 second backoff without emitting success.

- [ ] **Step 6: Verify GREEN and commit**

Run the observer tests and legacy tests. Commit:
`feat: mirror verified commerce events to blackboard`.

### Task 3: Opt-In Spectator Dock

**Files:**
- Create: `viz/commerce-widget.css`
- Create: `viz/commerce-widget.js`
- Modify: `viz/survey.html`
- Modify: `viz/server.py`
- Create: `tests/test_survey_commerce.py`

**Interfaces:**
- Consumes: same-origin `kind=commerce` events already arriving through the survey SSE.
- Produces: `window.CommerceWidget.mount(mainElement)` and `window.CommerceWidget.handle(event)`.

- [ ] **Step 1: Write failing route and static-contract tests**

Assert `/survey-commerce` serves survey HTML, `/survey` remains commerce-disabled, widget assets are local, the script uses `textContent` rather than payment-derived HTML, `?commerce=0` prevents mount, and no iframe or privileged API URL exists.

- [ ] **Step 2: Verify RED**

Run `python -m unittest tests.test_survey_commerce -v`. Expected: route/asset failures.

- [ ] **Step 3: Implement the route and safe mount**

Serve the two local assets from `viz/server.py`. In `survey.html`, mount only when pathname is `/survey-commerce` and query `commerce` is not `0`; dispatch only `kind=commerce` events to the widget.

- [ ] **Step 4: Implement the visual dock**

Build DOM nodes with `createElement`/`textContent`: payer-to-payee deal card, negotiation bubbles, five-step evidence rail, balance deltas, tx/block/gas proof, integrity badge, failure state, and full explorer link derived from `location.hostname`. Add 380px desktop rail, responsive bottom sheet, reduced-motion support, and accessible live regions.

- [ ] **Step 5: Implement easy disable**

Add `Скрыть` and restore chip controls. Store only `commerce-widget-collapsed` in `localStorage`; show aggregate payment count and USDC total on the chip. Ensure reset/hello clears event state but preserves the presentation preference.

- [ ] **Step 6: Verify GREEN and commit**

Run the new contract tests and all 42 legacy tests. Commit:
`feat: add optional live commerce spectator dock`.

### Task 4: Combined Compose Demo

**Files:**
- Create: `docker-compose.survey-commerce.yml`
- Modify: `Makefile`
- Modify: `payments/README.md`
- Create: `payments/tests/test_survey_commerce_compose.py`

**Interfaces:**
- Consumes: main compose, payment compose, bridge module.
- Produces: `make demo-survey-commerce` and `make down-survey-commerce`.

- [ ] **Step 1: Write failing compose contract test**

Parse `docker compose ... config --format json` and assert the observer has blackboard rw, no secrets volume, read-only root, dropped capabilities, no published port, and access to payment explorer. Assert normal `viz` keeps blackboard read-only.

- [ ] **Step 2: Verify RED**

Run the compose test. Expected: missing overlay and Make target.

- [ ] **Step 3: Add the hardened observer service**

Use the existing payment image, command `python -m payments.blackboard_bridge`, payment explorer URL, blackboard mount, read-only root, `/tmp` tmpfs, `no-new-privileges`, and `cap_drop: ALL`. Do not mount `payment-secrets` or expose a port.

- [ ] **Step 4: Add orchestration targets and docs**

`demo-survey-commerce` cleans both stacks, starts survey and payment services, waits for health, runs the deterministic driver once, prints all three URLs, and leaves services running. `down-survey-commerce` removes only the combined stack and volumes. Document that the deals are deterministic shadow commerce today and how to disable the widget.

- [ ] **Step 5: Verify GREEN and commit**

Run compose config and the contract test. Commit:
`feat: orchestrate combined survey commerce demo`.

### Task 5: End-to-End and Browser Proof

**Files:**
- Modify only if a failing test exposes a defect in Task 1–4 files.

**Interfaces:**
- Consumes: `make demo-survey-commerce`.
- Produces: verified live demonstration and screenshots.

- [ ] **Step 1: Run full automated suites**

Run `make payments-test`, the 42 legacy tests, and Foundry tests. Expected: all pass.

- [ ] **Step 2: Start the clean combined demo**

Run `make demo-survey-commerce`, then query explorer payments and blackboard events. Assert exactly two `RECEIPTED` payments, 14 USDC total, matching tx hashes, and no secret field names.

- [ ] **Step 3: Verify desktop in real Chrome**

Open `http://localhost:8080/survey-commerce` at 1440×1000. Confirm live negotiation, completed evidence rail, 90→100 USDC charging-station balance delta, tx/block/gas fields, collapse/restore, explorer link, and clean console.

- [ ] **Step 4: Verify disable and responsive modes**

Open `/survey`, `/survey-commerce?commerce=0`, and `/survey-commerce` at a 390×844 viewport. Confirm no widget in the first two and a usable bottom sheet in the third.

- [ ] **Step 5: Final verification and commit**

Run `git diff --check`, ensure the worktree contains no secrets or generated payment state, commit any test-driven corrections, and push `codex/commerce-live-demo` to GitHub.
