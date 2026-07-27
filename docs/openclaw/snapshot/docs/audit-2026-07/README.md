# Audit + architecture research — 2026-07-02

> **STATUS UPDATE (same day):** all P0 and P1 findings below are FIXED and
> verified with three live sverk studio runs — see `IMPLEMENTED.md` in this
> directory for what was applied, the gateway probe results (json_schema is
> enforced; guided_choice is stripped; grammar stalls large outputs), and the
> verification evidence (`verify-canvas.png`). P2 and the moderator-promotion
> refactor remain open.

Multi-agent audit of the working tree (post-handoff state): 7 code auditors by subsystem,
each top finding re-verified by an adversarial agent; one live `make local-studio` run on
the real sverk brain with a rendered canvas; 5 web-research tracks on adoptable
architectures. 54 agents total. Raw outputs in this directory:

- `findings-full.md` — all 77 findings with evidence, verdicts, corrections, fixes
- `live-run.md` — the instrumented studio run on sverk (timings, chat, ballot, llm.jsonl)
- `live-run-canvas.png` — the canvas that run produced (rendered by `scripts/render_canvas.py`)
- `research-full.md` — 50+ sourced architecture items with per-item adoption notes

---

## 1. Verdict up front

**The flagship works.** `make local-studio` on sverk ran end-to-end
(CHAT→CONVERGE→EXECUTE→REPORT→DONE, ~206s), the chat was coherent with real persona
names and private threads, done-consensus ended the chat naturally, per-voter tally
dedup works, and the canvas is a coherent layered scene (all 4 colours, clear
figure-ground) — not monochrome collapse, not noise.

**But the run also reproduced the two headline quality bugs live:**

1. **Vote split by near-duplicate candidates (handoff #1) — material, not theoretical.**
   Ballot had «Лунный рассвет» and «Лунный рассвет: гора из изумрудного овала и
   фиолетовая дуга» as separate lines. Their combined score (51.4) would have beaten the
   winner «Ледяная сфера» (30.1). The group's actual preference lost to vote
   fragmentation.
2. **Line-clamp bypass (handoff #9)** — thin diagonal lines crossing the full canvas are
   visible in `live-run-canvas.png`.

**Plus one new decision-quality finding:** a **chat/vote coherence gap**. The chat
converged (done:true) on «Лунный рассвет», yet two drones then voted «Ледяная сфера» in
CONVERGE — the executed subject diverged from the chat's stated consensus. The vote
prompt doesn't carry each drone's own final chat position.

## 2. Handoff §4 known-issue scorecard

| # | Handoff claim | Status (verified) |
|---|---|---|
| 1 | Ballot near-dup vote split, no semantic dedup | **Still present**, demonstrated materially in the live run (`studio_chat.py:57` exact-string dedup only) |
| 2 | Per-voter last-wins tally dedup | **Fixed & verified** on both `moderator._conclude` and studio CONVERGE (live run: 4 voters → 4 votes) |
| 3 | Explicit abstain | Debate path OK; studio path untested live (no abstains occurred); CONVERGE counts **off-ballot write-ins** (see findings) |
| 4 | Moderator not a first-class role | True but **less severe than stated**: `role: moderator` in the soul is inert metadata; dispatch works via coordinator. Promotion is a reusability win, not a bug fix |
| 5 | Duplicated helpers coordinator/moderator | Confirmed, 8-item inventory in findings; the two divergent `stable_key` hashes live in isolated subsystems (no present defect) |
| 6 | `paint_seed` domain leakage into debate | Confirmed (`moderator.debate_step` → `run_log.start_run(paint_seed=0)`) |
| 7 | Second-granularity timestamps → non-causal ordering | Confirmed and slightly worse: same-second order is decided by each process's **private** `_seq` counter; `moderator.py:99,124` sort debate transcripts by `ts` |
| 8 | `_seq` resets on restart | Confirmed + concrete impact traced: debate FLOOR/ARGUMENT matching keys on message id — a reissued floor id can look already-answered, silently skipping a debater's turn |
| 9 | `COLLAB_FREE=1` monochrome risk / line spans | Line spans **confirmed** (2 paths: length cap never applied to from/to; missing from/to defaults to `(0,0)->(w,h)`). Monochrome: radius caps are 2× too loose (r≤60 = Ø120), worst case ≈78.5% coverage, not 100% |
| 10 | Nickname hallucination | **Effectively fixed in practice** (live run: zero hallucinated names across 20+ messages — names arrive via recent-chat lines + validated `address`), but the roster is still never passed for the *first* turn |

## 3. Top defects to fix (confirmed, ranked)

### P0 — flagship studio quality (each corroborated by the live run)

1. **Semantic dedup of ballot candidates** — `studio_chat.py:57 derive_candidates`.
   Canonicalize before dedup (fold case/punct), then cluster near-dups (one LLM
   clustering call by the facilitator, or embeddings), tally at cluster level.
   Best combined with sampler-enforced ballots (see §5, `guided_choice`).
2. **Chat/vote coherence** — carry each drone's final chat stance (its last `subject` +
   `done` endorsement) into the CONVERGE vote prompt so the vote reflects the debate.
3. **Done-consensus stall** — `studio_chat.py:114`: a drone that hits `MAX_CHAT_TURNS`
   with `done:false` freezes the `all_done` exit; chat then always burns the full
   `DEADLINE_CHAT`. Treat capped drones as done (real-brain-only bug; mock forces done).
4. **Global z is a race** — `collab_paint.py:296`: every drone emits LLM-local z (1,2,3…),
   the facilitator's assigned z-slot is ignored. Namespace: `z_global = slot*1000 + local_z`.
5. **Shape-clamp holes** — `paint_shapes.py:405` line length/endpoint defaults;
   `collab_paint.py:95` radius keys capped at full-extent value (2× loose);
   unguarded `int()/float()` on LLM z/alpha can raise mid-emit → duplicate re-emission
   (emit after accumulating + write_progress together).
6. **Silent paint failures** — `llm_retry.py:10`: add `"collab_compose"` to
   `PAINT_JSON_CONTEXTS`; also emit an event when a studio-chat turn falls back to the
   canned line (today an sverk outage produces a fake scripted chat indistinguishable
   from a real one on the dashboard).

### P1 — engine structure & robustness

7. **Blackboard ordering** (root cause of #7/#8): assign a **global monotonic seq at
   append time** (hub/FileBoard owns it; seed from the last line/filenames at startup),
   stamp `(writer_id, writer_seq)` on every event/message, make consumers sort by seq —
   timestamps become metadata. Sub-second `now_iso` is a good hygiene addition but not
   the fix by itself.
8. **run_log multi-process corruption** — `run_log.py:32`: buffered `open("a")+write` of
   30–80KB lines from all agents into one `llm.jsonl`; mirror `bb.append_event`'s single
   `os.write(O_APPEND)` or use per-agent files. Also populate `parsed_ok` (currently
   always None → the repair path is unobservable).
9. **Moderator promotion + `phase_util.py`** — add `moderator` to `_ROLES`, extract the
   8 duplicated time/deadline/transition/tally helpers, remove `paint_seed` from
   `start_run` signature.
10. **Retry loop** — `brain.py:114`: distinguish transport-empty from parse failure
    (backoff, no fake «ОШИБКА ФОРМАТА» turn for network errors), cap total wall-clock,
    trim the echoed failed output (up to 20k chars/attempt today). Dead constants
    `CONTEXT_TOKENS`/`CHARS_PER_TOKEN` are never enforced; Cyrillic runs ~1.5–2.5
    chars/token so the char budgets underestimate real tokens by ~40–60%.
11. **SSE lifecycle** — `viz/server.py:329,335`: (a) on reconnect the server replays the
    whole feed into a reducer that never resets → duplicated chat, doubled shape
    counters; (b) after `/rerun`/coordinator-restart truncation the tailer seeks past
    EOF → every *other* open dashboard goes dead. Fix: stat-and-rewind on
    `st_size < pos`, reset client state on `hello`.

### P2 — broken modes, security, ops (decide: fix or explicitly deprecate)

12. **Distributed (HttpBoard) mode is dead on arrival, twice**: `run_log.refresh_from_bb`
    calls `bb.root`/`bb.read_json` which HttpBoard lacks (crash-loop on first cycle,
    `loop.py:235` is outside the resilience try) — and `drone/entrypoint.sh:64` dies on
    unbound `$NAME` under `set -eu` for generated souls. HttpBoard writes also swallow
    all errors silently (a dropped VOTE near deadline is simply never counted).
13. **Docker parity**: no `STUDIO_CHAT`/`COLLAB_*`/`DEADLINE_*` in any compose env block
    (studio is local-only); `wait_done.sh:34` greps "complete" but the coordinator writes
    «Картина готова: …» → `make demo-painters` always exits FAIL; `/rerun` in docker hits
    a read-only mount and dead agents.
14. **Security (matters once hub-exposed)**: `/rerun` is an unauthenticated destructive
    GET on 0.0.0.0 with CORS `*` (drive-by `fetch` can wipe a run); hub POST
    `/register|/progress|/messages` allow path traversal via unsanitized ids (absolute
    path in `id` escapes the blackboard entirely); no server-side single-writer
    enforcement (latent — no shipped client writes state today).
15. **Launch hygiene**: `run_local.sh` has no double-start guard (second launch rm-rfs
    the board under live KEEP_ALIVE agents, spawns a second coordinator);
    `stop_local.sh` pkill patterns are not repo-scoped and never kill `viz/server.py`.

### Notable corrections from adversarial verification (don't waste time on these)

- `clip_transcript` truncating the wrong end is real **but unreachable**: its only
  caller `session_transcript` has zero callers. Fix casually or delete the helper.
- The `PIPE_BUF` comment in `bb.py` is wrong (Cyrillic events reach ~19KB) but causes
  **no corruption**: O_APPEND writes to regular files are serialized on Linux. Fix the
  comment, not the code.
- `souls/moderator.md: role: moderator` is inert metadata; there is no active
  "unknown role" trap.
- `openai` provider is broken (vLLM-only params → 400 on api.openai.com, swallowed to
  "") — only matters if you ever use that fallback.

## 4. What the live run measured (sverk, 2026-07-02)

- Phases: CHAT 73s (20 msgs, 17 LLM calls) → CONVERGE 90s → EXECUTE 42s → DONE. 25 LLM
  calls, zero transport errors, no `<think>` leakage, no truncation; the 4 compose
  responses embed JSON in Russian prose and are the only calls exercising the regex
  extraction path.
- **Latency bottleneck is the vote**: one drone's CONVERGE call took 88.6s and landed 1s
  before the phase deadline. Deadline tuning or parallel-vote reminders matter more for
  runtime than anything in the paint path.
- 23 shapes, z 1..6, all four colours; `decision.json` still reports `canvas='quadrants'`
  (cosmetic leftover).

## 5. Architecture adoption plan (from the research tracks)

Unanimous meta-verdict: **do not adopt a framework** — every pattern worth having is a
30–100-line addition to `bb.py`/`loop.py`/`moderator.py`. Full sourced list in
`research-full.md`. In adoption order:

1. **Sampler-enforced structured output on the existing sverk endpoint** (deletes the
   failure class the regex repair exists for): migrate `response_format` to
   **`json_schema`** (enforced on vLLM ≥ 0.17; `json_object` is schema-less and often
   soft-emulated by gateways — which matches "accepted but not enforced"), use
   **`guided_choice` for VOTE ballots** (the model physically cannot vote off-ballot —
   also fixes the off-ballot write-in finding), keep `enable_thinking:false` on
   structured calls unless the server runs `--reasoning-parser qwen3`. **Verify the
   gateway first** with a const-lock probe (schema forces "BLUE", prompt begs "RED") and
   an invalid-schema probe (must 400; a 200 means the param was stripped). Known trap on
   this exact model family: MTP speculative decoding + reasoning + grammar (vllm#34650).
   Client side: keep retry-with-error-feedback for semantic errors, replace the ~250
   regex lines with the `json_repair` library for residual syntax.
2. **Speaker selection, the production pattern** (AG2 GroupChat / AutoGen
   SelectorGroupChat / CrewAI manager all converge on it): deterministic Python filter
   narrows candidates → LLM only ranks within the pool → validate returned name against
   roster → bounded repair re-prompts → deterministic fallback (next-in-list). The raw
   LLM pick must never drive the phase machine. (~40 lines in `moderator.py`.)
3. **Composable termination predicates** (AutoGen-style): small predicates over the
   message log (`max_messages | all_voted | text_mention | deadline | stop-file`)
   combined with any()/all(), plus an agent-initiated `escalate`/exit message under a
   hard round cap — replaces the scattered deadline logic and fixes the DEBATE-livelock
   class. Adaptive-stability stopping (stop when stances stabilize, arXiv:2510.12697)
   is the researched upgrade to done-consensus.
4. **Position canonicalization before tally** — the debate-track answer to handoff #1:
   embedding/string clustering or one LLM-canonicalizer call mapping free-text stances
   to stance ids; ballot and converge run on ids, prose is only display. (Same fix
   serves debate `candidate_positions` and studio subjects.)
5. **Blackboard ordering + event sourcing**: global seq at append + `(writer_id,
   writer_seq)` + per-consumer cursor (dedup, gap detection, idempotent restart);
   declare `events.jsonl` the source of truth, state JSONs become snapshots stamped
   `last_applied_seq`, rehydrate by replay-after-snapshot → free time-travel debugging.
   Checkpoint at **phase boundaries** into `runs/<id>/` (LangGraph/MS-Agent-Framework
   supersteps; their FileCheckpointStorage validates the file-blackboard design).
   Lamport/HLC/ULID only if the board ever spans hosts.
6. **Schema-validated state writes** (PatchBoard, arXiv:2605.29313 — 84.6% vs 30.8%
   task success vs free-form shared memory): per-file JSON schema + writer allowlist at
   the board layer; also the natural place to enforce single-writer server-side.
7. **Step-level failure policy** (LangGraph shape): typed retry with backoff at
   `roles.step`, ERROR durably committed as an event before recovery, then deterministic
   per-role fallback (debater → explicit ABSTAIN, moderator → deadline-advance).
8. **Painting coherence, in effort order** (coDrawAgents CVPR'26, GeoSVG-RL, Chat2SVG,
   RPG, MCCD, ART, LayoutGPT — all in `research-full.md`):
   a. **Deterministic geometric linter** before compositing (region containment, z-band,
      canvas fit, polygon validity — no LLM, catches the clamp-bypass class wholesale);
   b. **Canvas-grounded planning** — composite + render after each drone commit and feed
      the raster back (needs a vision model; sverk/qwen35 is text-only, so this is
      gated on adding a VLM — coDrawAgents' ablation says it's worth more than layout
      decomposition itself: +1.9 GenEval);
   c. **Skeleton upgrades** (text-only, available now): per-drone sub-briefs with
      neighbor-edge context (RPG), feathered seam bands with a designated seam-owner
      (MCCD), CSS-like layout serialization with few-shot exemplars (LayoutGPT);
      coarse-to-fine commit order along z;
   d. Benchmarks (SGP-GenBench, SVGenius): LLMs are strong on colour/attribute binding,
      weak on global spatial relations → keep inter-region geometry coordinator-owned,
      budget shapes per commit, favour many simple primitives.
9. **Human-in-the-loop for free**: moderator writes `pending_interrupt.json` and idles
   until the viz UI (or a human) writes the answering message — LangGraph `interrupt()`
   semantics with zero new infrastructure; doubles as a pre-CONCLUDE breakpoint.
10. **Debate-quality evidence to keep in mind** (arXiv:2502.19130 "Voting or
    Consensus?", 2509.11035 Free-MAD, 2606.03032): consensus-stopping commits to errors
    it never escalates; more rounds/agents ≠ better (stance homogenization). Voting-only
    conclusion (your decision) is well-supported; add stability detection rather than
    more rounds.

## 6. Method note

7 audit dimensions (blackboard/transport, phase engine + debate, studio chat, collab
painting, LLM layer, viz + frontend, ops/build), top findings re-verified by adversarial
agents instructed to refute (4 findings were refuted or materially corrected — §3
corrections); blackboard/ops verifications completed by direct code inspection.
`blackboard/` runtime state was backed up before the live run. Remaining known gap: the
debate engine was audited but not exercised live (`make local-debate` on sverk) — worth
one run before touching `moderator.py`.
