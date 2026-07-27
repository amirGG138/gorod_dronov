# Task 4 Commerce Hardening Design

## Goal

Close the six material Task 4 gaps without expanding beyond the payments
commerce runtime: truthful x402 lifecycle ordering, durable cross-process
purchase ownership and recovery, immediate in-flight idempotency conflicts,
seller-floor enforcement, immutable quote payment bindings, and typed/sanitized
API responses.

## Scope

Changes are limited to `payments` domain, persistence, commerce orchestration,
x402 gateway, API, and their tests. Explorer, demo driver, agent client,
mission, ROS, rover, and web code remain out of scope. The settlement network
remains `eip155:31337` with the pinned SVERK and official `x402==2.16.0`
components.

## Immutable Quotes and Negotiation Floor

An accepted quote stores its payment network, asset contract, payer address,
and payee address in addition to the existing commercial terms. A binding
callback supplied by `CommerceRuntime` lets the negotiation engine construct a
complete frozen `Quote` without coupling the domain engine to EVM bootstrap
state. AP2 and x402 derive and validate settlement requirements from these
stored fields; mutable runtime configuration is not used to reinterpret an
existing quote.

Accepting the latest offer checks the service floor before changing negotiation
state. This applies regardless of which participant proposed the offer.

## Truthful x402 Lifecycle

`OfficialX402Gateway` exposes three phases:

1. `prepare(quote)` deterministically creates the official signed payload.
2. `challenge(payment_id, prepared)` performs the unsigned protected-resource
   request and validates the actual HTTP 402 and exact `PAYMENT-REQUIRED`
   requirements.
3. `settle(payment_id, prepared)` sends `PAYMENT-SIGNATURE`, uses the official
   verify/settle middleware, and returns the resource only through
   `SkipHandlerResult` after settlement.

The runtime closes AP2 mandates around the prepared signature, calls
`challenge`, and only then records `PAYMENT_REQUIRED`. It subsequently records
`SIGNED`, verifies AP2 and records `VERIFIED`, records `SETTLING`, then invokes
`settle`. No persisted status describes an HTTP event before it occurred.

## Durable Purchase Ownership

SQLite contains one authoritative purchase claim per quote. The claim stores a
random owner token, SQLite-authoritative lease expiry, phase, deterministic
purchase/payment IDs, the prepared payload hash, sanitized settlement intent,
and public settlement/result data. It never stores the raw signed payload.

Claim mutations use `BEGIN IMMEDIATE` and compare the owner token:

- acquire creates the unique quote claim;
- renew extends an active owner's lease;
- takeover succeeds only after the SQLite lease expiry;
- intent, settlement, completion, and failure writes are atomic and
  owner-checked.

A live losing runtime polls the same claim and returns its terminal persisted
public result. It does not create receipts or settle independently. If its
bounded wait expires, it returns retryable `PURCHASE_IN_PROGRESS` in the common
error envelope. A stale claim may be taken over, after which recovery is always
attempted before any signed request.

The raw prepared x402 payload is stored as a buyer-owned secret artifact in
`IdentityVault`. SQLite stores only its hash and sanitized network, token,
payer, payee, amount, and authorization nonce. This enables restart while
keeping signed authorization material out of the journal and public API.

## Settlement Recovery

The official gateway provides a narrow recovery operation keyed by the
persisted sanitized intent. It checks the configured chain and exact token,
queries the EIP-3009 `AuthorizationUsed` event for the payer and nonce, locates
the canonical successful transaction receipt, and requires a matching ERC-20
`Transfer` in that receipt for the exact payer, payee, and amount. Only this
complete match is treated as settled and reconstructed into `SettledX402`.

If the authorization is proven unused, settlement may proceed. If it is used
but the canonical receipt or transfer does not match, recovery fails closed.
EIP-3009 replay protection remains defense-in-depth rather than the recovery
mechanism.

## Idempotency

Each in-memory single-flight entry stores both the request hash and future.
Under the same guard used to find an entry, a different hash raises
`IDEMPOTENCY_KEY_CONFLICT` immediately instead of waiting for or replaying the
first request.

## API Contract

Public routes declare Pydantic success response models. A shared typed error
envelope is documented for expected error status codes. A catch-all exception
handler returns status 500 with code `INTERNAL_ERROR`, a fixed sanitized
message, `retryable: false`, and empty details. Exception types, messages,
tracebacks, signed payloads, bearer values, and secrets are never returned.
`PURCHASE_IN_PROGRESS` maps to 409; `INTERNAL_ERROR` maps to 500.

## Verification

Tests are added red-first for:

- buyer-below-floor acceptance and immutable quote bindings;
- concurrent conflicting request bodies on one idempotency key;
- real challenge-before-lifecycle ordering;
- two runtimes sharing SQLite settling once;
- restart before settlement and after a mined settlement;
- exact live on-chain recovery validation;
- typed OpenAPI responses and sanitized unexpected 500 errors.

Focused tests run after each slice. Final verification runs the complete live
payments suite against pinned Anvil, all 42 pre-existing regression tests,
compile checks, and secret-leak checks. Task 4 is marked specification-complete
only if all six requirements and final verification pass.
