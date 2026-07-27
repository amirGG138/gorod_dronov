# Survey + Commerce live demo

## Goal

Provide one optional end-to-end demonstration in which the existing survey
agents continue their normal mission while observers can see a deterministic
agent-to-agent negotiation, AP2/x402 settlement, balances, and transaction
receipts in real time.

The demo must not make mission progress, flight safety, ROS commands, or the
competition result depend on a payment.

## Considered approaches

1. Embed only the existing payment explorer. This is smallest, but the main
   dashboard would not explain the negotiation in human-readable form.
2. Render commerce events only in browser JavaScript. This avoids a backend
   bridge, but commerce history would not be part of the normal blackboard SSE
   replay and would be harder to debug.
3. Add a read-only commerce observer that mirrors sanitized commerce events
   into the blackboard event feed, plus a purpose-built compact commerce dock.
   This is the selected approach because it gives one replayable timeline,
   keeps the mission field readable, and lets spectators understand a payment
   without reading a dense blockchain explorer.

## User-visible behavior

`make demo-survey-commerce` starts a clean survey and a clean Anvil payment
network. It serves:

- `http://localhost:8080/survey-commerce` — survey field, normal agent feed,
  human-readable commerce conversation, and a compact live commerce dock.
- `http://localhost:8090` — the full standalone Agent Commerce explorer.
- `http://localhost:8081/docs` — the commerce runtime API.

The deterministic commerce script remains:

1. `rover -> charging-station`: `9 USDC -> 10 USDC -> accept -> settle`.
2. `drone-2 -> drone-1`: `3 USDC -> 4 USDC -> accept -> settle`.

The combined dashboard shows messages such as:

- `rover: Предлагаю 9 USDC за 40 единиц заряда`
- `charging-station: Контрпредложение — 10 USDC`
- `rover: Принимаю предложение`
- `commerce: AP2 mandates verified`
- `commerce: 10 USDC settled, tx 0x…`

## Architecture

### Commerce blackboard bridge

`payments.blackboard_bridge` consumes the sanitized explorer SSE API. It never
mounts payment secrets and never calls a low-level transfer API.

Each supported commerce event is mapped to a blackboard event:

```json
{
  "kind": "commerce",
  "event_id": 42,
  "event_type": "negotiation.offer",
  "from": "rover",
  "to": "charging-station",
  "stage": "COUNTEROFFER",
  "body": "Предлагаю 9 USDC за 40 единиц заряда",
  "payment_id": null,
  "tx_hash": null
}
```

Only display-safe fields are copied. Raw AP2 tokens, receipts, private keys,
bearer credentials, EIP-3009 signatures, and x402 payloads are forbidden.
Lifecycle events include a sanitized evidence object with boolean AP2,
receipt, transfer-log, and tx-match checks plus public chain metadata and
before/after balances. It contains no signed authorization payload.

The bridge writes only `events.jsonl`; it does not write blackboard messages.
Mission agents therefore cannot consume commerce narration as mission context.
The payment system remains downstream of mission decisions.

The source payment SSE event ID is persisted in
`/blackboard/state/commerce_cursor.json`. Reconnect and container restart must
not duplicate narrated events. A blackboard reset clears this cursor so a new
clean demo can replay its new payment journal.

### Combined survey page

`/survey-commerce` serves the existing `survey.html` in an opt-in commerce
mode. The ordinary `/survey` route and layout remain unchanged.

Commerce mode adds a purpose-built spectator dock instead of embedding the
full explorer. The mission field remains the largest visual element.

The dock contains:

- an animated `payer -> payee` deal card with service name and USDC amount;
- short negotiation bubbles for offer, counteroffer, and acceptance;
- a five-step evidence rail: `NEGOTIATION -> QUOTE -> AP2 VERIFIED ->
  x402 SETTLED -> ONCHAIN CONFIRMED`;
- payer and payee balances with before/after deltas read from Anvil;
- transaction hash, block, gas, confirmation time, and an integrity badge;
- a link to open the full Agent Commerce explorer on port `8090`.

Success is green only after the explorer has matched the x402 settlement,
on-chain `Transfer` log, AP2 payment receipt, participants, amount, and tx
hash. Earlier stages have distinct pending states; no browser timer fabricates
progress. Failures remain red and show the exact failed stage.

The dock uses only same-origin `kind=commerce` blackboard events. The bridge
normalizes explorer data into display-safe snapshots, so the browser never
receives payment credentials or calls a privileged runtime endpoint.

On desktop the dock is a 380-pixel right rail. On narrow screens it becomes a
bottom sheet. A visible `Скрыть` control collapses it to a small status chip
such as `Commerce · 2 платежа · 14 USDC`; the preference is stored in
`localStorage`. The chip restores the dock. This is presentation state only
and contains no credential.

The feature is opt-in at three levels:

- ordinary `/survey` never creates commerce DOM or commerce connections;
- `/survey-commerce?commerce=0` renders the normal dashboard;
- the combined Compose/Make target is the only target that starts the bridge
  and payments stack.

Thus operators can disable the widget by using `/survey`, adding
`?commerce=0`, or running the existing non-commerce demo target. No source
edit or rebuild is required.

### Compose and orchestration

`docker-compose.survey-commerce.yml` is an overlay used together with the
existing main and payment compose files. It adds only the bridge and necessary
network/blackboard mounts.

The bridge:

- mounts `blackboard` read-write;
- has no payment-secrets mount;
- drops all Linux capabilities;
- runs with a read-only root filesystem and `no-new-privileges`;
- reaches only the payment explorer over the Compose network.

The Make target:

1. removes the prior combined stack and its volumes;
2. builds the existing images;
3. starts survey agents, bridges, dashboard, Anvil, bootstrap, runtime,
   explorer, and commerce observer;
4. waits until the survey blackboard has been initialized;
5. runs the existing deterministic demo driver once;
6. leaves the dashboards and long-running services available.

Financial failure is narrated but does not stop or alter the survey.

## Error handling

- Explorer unavailable: bridge retries with a bounded delay and emits no
  fabricated success.
- SSE reconnect: resume from the persisted source event ID.
- Malformed or unsupported event: ignore it without writing to the board.
- Payment failure: render a red `PAYMENT_FAILED` commerce event and continue
  the survey.
- Main dashboard unavailable: payments continue independently.

## Tests

1. Unit tests for event-to-narration mapping and secret-field rejection.
2. Bridge cursor/reconnect test proving exactly-once blackboard narration.
3. Dashboard contract test proving `/survey` stays unchanged and
   `/survey-commerce` enables the optional panel.
4. Compose validation and mount/environment inspection.
5. Full combined demo:
   - normal survey events remain visible;
   - exact offer/counteroffer/accept narration appears;
   - explorer contains two `RECEIPTED` payments;
   - blackboard and explorer tx hashes agree;
   - a same-namespace rerun does not add transactions.
6. Real Chrome test for live SSE, dock collapse/restore, `?commerce=0`,
   responsive desktop/mobile layout, clean console, and absence of secret
   material in the page.
7. Evidence integrity test proving the green confirmation state cannot render
   until receipt, transfer log, participants, amount, and tx hash all match.

## Non-goals

- LLM agents do not decide whether to buy in this demo.
- Commerce events do not modify mission phases or physical commands.
- The existing `/survey`, normal Make targets, ROS bridge, rover code, and
  payment explorer API remain backward compatible.
- No public-chain or real-money transaction is introduced.
