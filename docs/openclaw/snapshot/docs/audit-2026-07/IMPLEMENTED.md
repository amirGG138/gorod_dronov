# Implementation pass — 2026-07-02 (same day as the audit)

Everything below was applied to the working tree and verified with THREE full
`make local-studio` runs on the real sverk brain (plus one mock plumbing run).
Final state: **25 LLM calls, 1 transient URLError (recovered), 0 parse failures,
0 fallback lines**; canvas `verify-canvas.png` — coherent single-subject scene,
every line ≤ 36 canvas units.

## Gateway probes (do these findings first — they shaped the design)

| Probe | Result |
|---|---|
| `response_format: json_schema` const-lock (schema forces "BLUE", prompt begs "RED") | **ENFORCED** — model returned "BLUE" (vllm-0.21.0 behind litellm) |
| invalid schema | **400** (param not stripped — real grammar) |
| vLLM-native `guided_choice` | **STRIPPED by litellm** — model happily said "Pizza!". Use `json_schema` + `enum` instead |
| json_schema on LARGE outputs (collab_compose, 6000 max_tokens) | **the vllm#34650 trap is REAL here**: 3/4 schema-guided compose calls hit the 120 s timeout; their plain retries answered in 27–39 s. Schemas stay on small calls only |

## P0 — studio decision quality

1. **Semantic ballot dedup** — new `agent/roles/ballot.py`: fold (case/ё/punct)
   + crude stemming + token-containment/Jaccard clustering, then one optional
   facilitator LLM merge (fail-safe validated). Coordinator publishes clustered
   candidates + `candidate_variants` to `collaborative.json`. Reproduces both
   audit examples: «Лунный рассвет» variants merge; «Зелёный клин в тишине» ≡
   «Зелёный клин тишины»; «Ледяная сфера» stays separate.
2. **Votes resolve onto the ballot** — CONVERGE tally maps every vote (and every
   scores key) through `ballot.resolve`; an unmatched write-in is an explicit
   abstain (`invalid: true` in the vote record), never a pool write-in. Ranking
   now runs over ballot candidates only.
3. **Ballot ranked by final-stance support** — verification run 2 exposed that
   first-seen `[:5]` truncation cut the chat's actual consensus («Солнечная
   волна», 4/4 final stances) off the ballot entirely. Clusters are now ranked
   by (# of drones whose FINAL chat stance resolves to the cluster, recency)
   before truncation.
4. **Chat/vote coherence** — `compose_vote` now (a) includes the CHAT phase in
   the negotiation transcript (it previously carried ZERO chat context — the
   root cause of the audit's coherence gap), (b) injects the drone's own final
   chat stance with an instruction to vote consistently or explain the change,
   (c) biases the fallback vote to the stance.
5. **Enum-locked ballots** — the vote call uses `json_schema` with
   `endorse: {enum: candidates}`; the model physically cannot vote off-ballot.
   Verified: 3 runs, 12 votes, 12 on-ballot.
6. **Done-consensus stall** — a drone that burns `STUDIO_CHAT_TURNS` with
   `done:false` now counts as done in `should_end_chat` (it can never post
   `done` again; it used to freeze the exit and burn the full DEADLINE_CHAT).
7. **Global z race** — the facilitator's z-slot now namespaces every drone's
   layer: emitted `z = slot*1000 + clamp(local_z, 0..999)`. Verified in events:
   painter layers at 1xxx/2xxx/3xxx bands.
8. **Shape-clamp holes** — in `collab_paint._clamp_to_region`:
   radius-like keys (r/rx/ry/outer) capped at maxd/2 (diameter ≤ maxd, was 2×
   loose); `line` length capped at maxd around the midpoint; **SVG-style
   x1/y1/x2/y2 lines normalized to from/to first** (they bypassed every clamp —
   caught live in verification run 2 as a full-canvas slash); malformed
   endpoints dropped; all numeric reads fault-tolerant (`_fnum`).
   In `paint_shapes._render_one`: a `line` with missing endpoints defaults to a
   ±12.5%-width stroke around its centre, not the old (0,0)→(w,h) diagonal.
9. **No duplicate re-emission** — `paint_collab` renders the whole layer first,
   then emits events + writes progress together; unguarded `int()/float()` on
   LLM z/alpha removed.
10. **Silent failures now visible** — `collab_compose` added to
    `PAINT_JSON_CONTEXTS` (llm_error events + «детерминированный слой» suffix);
    a studio-chat turn that falls back to the canned line emits an `llm_error`
    event (an sverk outage can no longer produce a fake scripted chat).

## P1 — engine robustness

11. **Board-global message ordering** — `bb.Blackboard._next_seq()`: one
    flock-guarded counter file (`blackboard/.seq`) shared by every process;
    `write_message` stamps `seq`, ids are `msg-<agent>-<seq:06d>` (no more
    restart collisions → no more silently skipped debate turns), filenames are
    seq-first so directory order = append order; `list_messages` sorts by seq.
    Wiped by `reset_runtime`, re-seeds from surviving files when
    RESET_ON_START=0. Hub stamps server-side → distributed ordering is free.
    Debate-engine consumers (`moderator._last_argument`, recent-floor listing,
    `debate_common` floor sort) now sort by seq. Concurrency-tested: 6
    processes × 25 messages → no gaps, no dups, correct order.
12. **run_log integrity** — `_append_jsonl` now does a single `os.write` on an
    O_APPEND fd (was buffered `open("a")` — interleaved 30–80 KB records from
    concurrent agents); new `log_parse` records make `parsed_ok` observable
    per attempt (the audit noted the repair path was invisible).
13. **Retry loop split** — `chat_json_with_retry` distinguishes transport-empty
    (backoff + same prompt, no fake format-error turn) from parse failure
    (echo + fix); total wall-clock capped (`LLM_RETRY_WALL_SEC`, default 300);
    echoed bad output trimmed 20k→6k chars (`LLM_RETRY_RAW_CHARS`); optional
    `schema=` param compiles to enforced `json_schema`.
14. **SSE lifecycle** — server: stat-and-rewind when `events.jsonl` shrinks
    (post-/rerun truncation used to leave every other dashboard seeked past
    EOF, silent forever) + re-sends `hello`; client (`useStudio.ts`): `hello`
    resets the reducer to initial state, so reconnect replays no longer
    double-count chat lines and shape counters. Frontend rebuilt.

## Cosmetics fixed on the way
- `decision.json` `canvas: "quadrants"` → `"shared"`.
- The wrong PIPE_BUF claim in `bb.py`'s header corrected (O_APPEND writes to
  regular files are kernel-serialized; PIPE_BUF applies to pipes).

## Second pass (same day): debate engine + P2 — all applied & sverk-verified

**Debate baseline first** (audit precondition): unmodified `make local-debate`
on sverk ran FRAME→OPENING→DEBATE(3 rounds)→VOTE→CONCLUDE→DONE — and live-
reproduced the write-in loss: debater-2 voted **«Intentional Hybrid»** for the
option «Hybrid (2-3 days in office)», the substring matcher discarded it as an
abstain, and Office-first won a 1-1 stable-key tie-break against the room's
actual preference.

Then applied:

15. **Moderator is a first-class role** — `moderator` in `_ROLES` with its own
    `step()`; `make local-debate` now runs `ROLE=moderator AGENT_ID=moderator`
    (coordinator's task==debate dispatch kept for compat); loop.py board-reset
    honours whichever role owns the phase machine. Caught + fixed a promotion
    regression: role≠coordinator meant every moderator thought streamed a fresh
    LLM narration, queueing the CONCLUDE tally minutes behind narration calls —
    phase-machine owners now always emit precooked thoughts (debate runtime
    returned from 25+ min to ~4.7 min).
16. **`phase_util.py` extraction** — now/iso/parse_iso/deadline_passed/
    deadline_in/transition/stable_key shared by coordinator + moderator (the
    8-item duplicated-helper inventory is gone; the two divergent stable_key
    hashes unified).
17. **Ballot resolver in the debate engine** — `ballot.resolve` gained a third
    pass (vote references exactly ONE candidate's tokens → match) that recovers
    «Intentional Hybrid»-class ballots; wired into `debate._resolve_choice`,
    `moderator._conclude` (tally-side, write-ins → explicit abstain with `raw`
    recorded), `candidate_positions` (no-options ballots are clustered, not
    string-deduped), `_top_share` (folded consensus keys). `start_run` no longer
    demands a paint_seed (debate domain-leak gone).
18. **Distributed mode un-bricked** — `run_log.refresh_from_bb` no-ops on an
    HttpBoard (was an AttributeError crash-loop outside the resilience try, on
    every remote drone's first cycle); `drone/entrypoint.sh` no longer dies on
    unbound `$NAME` for generated scout/rover souls.
19. **Docker parity** — STUDIO_CHAT/COLLAB_*/DEADLINE_*/LLM_JSON_* passed
    through compose env; new `make demo-studio` target; `wait_done.sh` accepts
    the Russian «Картина готова» verdict (every docker painters demo used to
    exit FAIL on an English-only grep).
20. **Security** — `/rerun` is POST-only behind an `x-rerun` header (custom
    header forces a CORS preflight → drive-by run-wipes impossible; the old GET
    answers 405); hub POST ids validated against `[A-Za-z0-9][A-Za-z0-9_.-]*`
    (path-traversal via `/register`//`progress/<id>`/message `from` closed);
    `bb.write_message` sanitizes filename components as defense in depth.
21. **Launch hygiene** — `run_local.sh` refuses to start while a previous
    stack's pids are alive (a second launch used to rm -rf the board under live
    KEEP_ALIVE agents); `stop_local.sh` kills only this checkout's processes by
    absolute path and now also stops `viz/server.py`.
22. **openai fallback provider unbroken** — vLLM-only `enable_thinking` params
    are no longer sent to api.openai.com (was a silent 400→""); dead
    `session_transcript`/`clip_transcript` helpers deleted.

**Second-pass verification (all real sverk):** debate baseline ~8 min → after
refactor 282 s DONE, tally clean (2/3 majority, raw ballots recorded, zero lost
votes); mock debate with promoted moderator passes; final studio regression
191 s DONE, 24 LLM calls, 0 transport errors, 0 parse failures, 0 lines over
cap, coherent canvas (`verify-canvas-2.png`), ballot of 5 with a clean 2-1-1
vote.

## Third pass (same day): city of drones + docs

23. **safe_passage refactored onto the chat architecture** — new
    `agent/roles/scout_chat.py`: scouts negotiate the sector split in an open
    CHAT (claim / argue / trade by name, done-consensus; enum-locked claims via
    json_schema), the coordinator derives the assignment from the final claims
    (a contested sector goes to whoever settled first, leftovers round-robin);
    `SCOUT_CHAT=0` restores the legacy silent PROPOSE→CONVERGE. Verified live
    on sverk: 110 s to DONE, a real contested-sector negotiation (two drones
    argued over C; one yielded and took D), rover PASS, 0 LLM errors.
    **TODO(crypto)** — agent-to-agent payments for sector swaps — is designed
    but not implemented (sketch in the scout_chat.py docstring).
24. **`docs/HANDOFF-vllm-upgrade.md`** — handoff for the gateway upgrade + LLM
    overhaul (probe protocol, measured limits, ordered client flips).
25. **Docs overhauled** — README + docs/README rewritten around the three
    flows; `painters.md` rewritten (the dead layer/roster model removed);
    `HANDOFF.md` superseded-rewritten as the start-here doc;
    `audit-report.md` marked historical; agents/protocol/visualizer/
    architecture/configuration/overview/running/security/debate-system/
    debugging-painters updated for the CHAT phases, seq ordering, the React
    frontend, PAINT_MODE, structured output and the new make targets.

## Still open (small, deliberate)
- **json_schema on collab_compose** — measured harmful on this deploy (see
  probes); revisit if the gateway upgrades past the MTP+grammar bug.
- **HttpBoard full E2E** — crash-loops fixed and hub ids hardened, but a real
  multi-host run (`make demo-distributed`) hasn't been exercised here.
- Docker image builds (`make demo-studio`) not run in this environment.

## Verification evidence
- Run 1 (sverk): DONE ~4.5 min; exposed compose-schema stall (fixed) and
  ballot truncation (fixed). Vote already unanimous & on-ballot.
- Run 2 (sverk): DONE ~2.3 min; 22 calls, 0 errors, 0 parse fails; caught the
  x1/y1 line bypass (fixed).
- Run 3 (sverk): DONE ~3 min; 25 calls, 1 transient URLError (recovered),
  0 parse fails; ballot «Тёплая сфера в синем кубе» won 2-1-1 with all stances
  in the sphere family; canvas = `verify-canvas.png`; all line lengths ≤ 36.
- Mock run: full plumbing pass (seq order, ballot state, coherent votes,
  namespaced z).
