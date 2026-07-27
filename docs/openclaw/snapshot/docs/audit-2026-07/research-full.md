

# TRACK: orchestration-frameworks
SUMMARY: Surveyed AutoGen/AG2, AutoGen AgentChat (SelectorGroupChat), LangGraph, CrewAI, OpenAI Agents SDK, Claude Agent SDK, smolagents, Google ADK, LlamaIndex Workflows, and Microsoft Agent Framework (the 2025-26 AutoGen+Semantic Kernel successor). Every production framework converges on the same ~6 primitives, all expressible in ~100 lines of Python each over the existing bb.py/loop.py: (1) two-stage speaker selection (deterministic candidate filter, then validated LLM pick with bounded retries and a deterministic fallback), (2) checkpoints taken at phase/superstep boundaries containing {per-agent state, pending messages, shared state}, (3) composable termination predicates over the message log, (4) node-level retry policy with backoff plus a checkpointed error so recovery is idempotent, (5) manager/moderator as a first-class agent with its own LLM, and (6) structured output enforced at the sampler (vLLM guided decoding) rather than repaired by regex. The file blackboard is an advantage: since events.jsonl is already append-only, a checkpoint is just {phase, state/*.json snapshot, events byte-offset} — Microsoft Agent Framework's FileCheckpointStorage is literally this design shipped as a product.

## AG2 GroupChat auto speaker selection (validation loop + fallback)
url: https://docs.ag2.ai/0.8.2/docs/api-reference/autogen/GroupChat/
what: AG2 (AutoGen 0.2 lineage) GroupChat picks the next speaker via speaker_selection_method: 'auto'|'manual'|'random'|'round_robin' or a custom callable. 'auto' runs a nested two-agent chat: a selector LLM gets 'The following roles are available: {roles}... select the next role from {agentlist}. Only return the role.', and a checking_agent validates the returned name. On multiple/zero name matches it re-prompts with a repair message ('return just the name of the next speaker', with tie-break rules), up to max_retries_for_selecting_speaker (default 2). After exhausting retries it deterministically falls back to the next agent in the list. allowed_or_disallowed_speaker_transitions is a dict {agent: [agents that may follow]} constraining the graph of legal turns.
relevance: This is exactly the 'moderated' turn mode in agent/roles/moderator.py (FLOOR grants). The moderator currently trusts one LLM pick; AG2 shows the production-hardened shape: validate the picked name against the registry (debate_common.debaters), bounded re-prompt with a repair message, then deterministic round-robin fallback so the phase machine can never stall on a bad pick.
ADOPT: A ~40-line pick_speaker(ctx, last_speaker) in moderator.py: (1) build candidates from registry, (2) prompt with roles+candidates ('Only return the name'), (3) exact/substring-match the reply against candidate names, (4) on ambiguity re-prompt once or twice with the repair message, (5) fall back to next-in-list. Plus an optional allowed_transitions dict in config to forbid e.g. the same debater twice in a row.
effort: small

## AutoGen AgentChat SelectorGroupChat: candidate_func/selector_func split + composable termination
url: https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/selector-group-chat.html
what: The modern AutoGen (0.4+) team API. Speaker selection is two-stage: candidate_func (plain Python, filters the eligible pool from conversation history) then an LLM choice using a prompt templated with {roles} (name : description lines), {participants} (candidate list), {history}. selector_func can bypass the LLM entirely (return a name or None to defer to the model). allow_repeated_speaker=False forbids consecutive turns by the same agent. Termination is a separate composable object checked after every response: TextMentionTermination('TERMINATE') | MaxMessageTermination(25), combinable with | and &.
relevance: Maps to two review-debt items: moderator._pick logic and guaranteed termination in agent/loop.py. The candidate/selector split cleanly encodes 'drones may request more turns': candidate_func = agents who posted a floor-request or haven't spoken this round; the LLM only ranks within that pool. Composable termination replaces the scattered per-phase deadline checks in loop.py/moderator.py with one should_stop(messages) predicate list.
ADOPT: (1) Two-stage selection: deterministic filter first, LLM second — never let the LLM widen the pool. (2) A ~20-line termination module: predicates over ctx.messages (max_messages, text_mention, deadline_exceeded, all_voted, external stop-file) combined with any()/all(); moderator advances phase when the active predicate fires. Deadlines become just one predicate instead of the only mechanism.
effort: small

## LangGraph checkpointing, threads, and time travel
url: https://docs.langchain.com/oss/python/langgraph/persistence
what: A checkpointer snapshots full graph state at every step, keyed by thread_id (persistent cursor: reuse = resume, new = fresh thread) and checkpoint_id. Replay/fork: load any historical checkpoint, optionally inject corrected state, and continue from there down a new branch. Interrupts piggyback on this: state is saved, execution yields, later a resume signal re-hydrates and continues.
relevance: Direct blueprint for a blackboard runs/ directory. bb.py already has the hard part (append-only events.jsonl, single-writer state files), so a 'checkpoint' degenerates to {phase, copy of state/*.json, byte offset into events.jsonl, message-dir cursor}. thread_id == run_id directory. Time-travel debugging of a debate (re-run VOTE with a corrected ballot) becomes: copy checkpoint into runs/<new>/, restart containers pointed at it.
ADOPT: runs/<run_id>/checkpoints/ckpt-<phase>-<n>.json written by the coordinator/moderator at each phase transition, containing phase + snapshot of state files + events.jsonl offset. resume(run_id) loads the latest checkpoint and replays events after the offset. Fork = cp -r a checkpoint into a new run dir. ~60 lines in bb.py.
effort: medium

## LangGraph fault tolerance: RetryPolicy + checkpointed error + handler node
url: https://docs.langchain.com/oss/python/langgraph/fault-tolerance
what: Three composable mechanisms per node: retries (matched by exception type; defaults initial_interval=0.5s, backoff_factor=2.0, max_interval=128s, max_attempts=3), timeouts, and an error handler that runs after retries are exhausted, receives current state, and can patch state or route elsewhere. Key detail: the failed node's ERROR write is committed to the checkpoint, so if the process crashes mid-recovery, resume sees the same NodeError context — failure provenance is durable.
relevance: This is the fix for the known SPOF on the review-debt list: 'wrap roles.step in loop.py in try/except (coordinator SPOF, only non-termination hole)'. agent/llm_retry.py already exists for the LLM call layer; what's missing is the role-step layer: on exception, append an ERROR event to events.jsonl (durable failure provenance), then apply a deterministic fallback (skip turn / abstain / advance phase).
ADOPT: In loop.py: try/except around roles.step; on failure append {type:'error', agent, phase, exc, attempt} to events.jsonl, retry with the 0.5s/x2/max-3 policy, and after exhaustion invoke a per-role fallback (debater → explicit ABSTAIN vote, moderator → advance phase by deadline rule). Because the error is an event, a restarted agent sees it and does not repeat the turn. ~30 lines.
effort: small

## LangGraph interrupt()/resume for human-in-the-loop
url: https://docs.langchain.com/oss/python/langgraph/interrupts
what: interrupt(payload) inside a node persists state via the checkpointer and waits indefinitely; the host app reads the pending payload, shows it to a human, and resumes with Command(resume=value) + the thread_id; the graph re-hydrates and continues as if the value had been there all along.
relevance: On a file blackboard this is almost free and gives the debate engine a human seat: moderator writes state/pending_interrupt.json {question, options} and idles in a PAUSED sub-state; viz/debate.html (already polling the board) renders it; the human's answer is written as resume.json or as a normal VOTE/FLOOR message; moderator consumes it and continues. No new infra — the persistence layer already exists.
ADOPT: An interrupt/resume convention: (1) moderator.request_human(payload) writes pending_interrupt.json and stops advancing the phase clock, (2) any writer (viz UI, CLI) answers by writing a message of the requested type, (3) moderator clears the file and proceeds. Also usable as a debugging breakpoint before CONCLUDE.
effort: small

## Microsoft Agent Framework (2025 AutoGen+SK successor): superstep checkpoints + per-executor state hooks
url: https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints
what: Workflows run in discrete supersteps (Pregel-style); a checkpoint is created at the end of each superstep and captures: current state of all executors, all pending messages for the next superstep, pending requests/responses, and shared state. Executors opt in via on_checkpoint_save() -> dict and on_checkpoint_restore(state). Ships InMemory/File/CosmosDB storages behind one CheckpointStorage protocol; resume on the same instance via run(checkpoint_id=...) or rehydrate a brand-new workflow instance from a checkpoint.
relevance: Independent confirmation (from the team that owned AutoGen) of two choices: checkpoint at phase-boundary granularity, not per message — which maps 1:1 onto the FRAME→OPENING→DEBATE→VOTE→CONCLUDE transitions; and FileCheckpointStorage as a first-class production backend validates the file-blackboard approach outright. The per-executor save/restore hook is the piece openclaw lacks: a debater's in-memory scratch (current position, stance history) dies on container restart.
ADOPT: (1) Checkpoint only at phase transitions (superstep = phase). (2) Add optional on_checkpoint_save/on_checkpoint_restore to the role protocol in agent/roles/__init__.py; loop.py persists the returned dict to state/progress/<agent>.json (a file each agent already owns) so any agent can be killed and rejoin mid-debate. (3) Checkpoint contents checklist: agent states + unconsumed messages + shared state — verify the runs/ snapshot includes all three.
effort: small

## OpenAI Agents SDK handoffs-as-tools + input_filter
url: https://openai.github.io/openai-agents-python/handoffs/
what: Delegation is modeled as an LLM-callable tool named transfer_to_<agent>, with input_type (Pydantic schema the LLM must fill, e.g. {reason}) validated before the handoff fires, on_handoff callback for side effects, input_filter to transform what the receiving agent sees (e.g. handoff_filters.remove_all_tools strips tool noise from history), and a RECOMMENDED_PROMPT_PREFIX that teaches agents when to hand off. Full message history transfers by default.
relevance: Two mappings: (a) the FLOOR/floor-request protocol in debate_common.py — a drone requesting more turns or escalating to the moderator is a handoff with a typed payload {reason, target}; validating that payload schema kills a class of malformed-message bugs. (b) input_filter is the same idea as agent/context_budget.py: when the floor passes, deliberately shape the history the next speaker sees (drop stale rounds, keep openings + last round + tally) instead of truncating blindly.
ADOPT: (1) Typed control messages: FLOOR_REQUEST{reason} and ESCALATE{reason} with schemas validated on read; unparseable → ignored + error event, never a crash. (2) A per-role history filter hook applied when composing the LLM prompt (function history -> history), replacing ad-hoc trimming in context_budget.py. (3) A shared soul-prompt prefix explaining the floor protocol, mirroring RECOMMENDED_PROMPT_PREFIX.
effort: small

## Structured output at the sampler: Agents SDK output_type + vLLM guided decoding
url: https://docs.vllm.ai/en/latest/features/structured_outputs/
what: OpenAI Agents SDK attaches output_type (a schema) per agent so the final answer is constrained, not parsed. vLLM implements the same server-side for any model: response_format={'type':'json_schema',...} plus guided_choice (output is exactly one of N strings), guided_regex, guided_json, guided_grammar, backed by xgrammar (default backend, cached grammars, near-zero token overhead).
relevance: Directly executes the memory-noted decision: 'structured output via vLLM response_format on the sverk/Qwen endpoint to delete brain.py regex JSON-repair'. The killer specific for the debate engine: VOTE ballots become guided_choice over the frozen candidate options — the model physically cannot emit an off-ballot vote, which also simplifies moderator._conclude dedup/tally. ARGUMENT/OPENING metadata become guided_json per message type.
ADOPT: A schema-per-message-type table in debate_common.py (VOTE → guided_choice(options), FLOOR_REQUEST → json_schema, OPENING/ARGUMENT → json_schema with free-text field); brain.py passes the constraint through to the sverk endpoint via extra_body/response_format and drops the regex repair path (keep it only as fallback for non-vLLM providers).
effort: small

## CrewAI: manager agent as first-class role + Flows @router phase machine
url: https://docs.crewai.com/en/concepts/processes
what: Process.hierarchical requires a manager_agent (or auto-created manager_llm agent) that is itself a real agent: it plans, allocates tasks to workers by capability, reviews outputs, and validates completion — tasks are not pre-assigned. Separately, CrewAI Flows define deterministic orchestration with decorators: @start, @listen(event), @router (a handler returns a label that routes to the next step), plus or_/and_ combinators and persisted flow state for resumable long runs.
relevance: Validates two decisions already on the openclaw list: making moderator a real ROLE (currently runs as coordinator+soul — CrewAI's manager is precisely 'an agent with a soul whose tools are delegation and validation'), and shrinking the coordinator to a thin facilitator. The @router pattern is the cleanest ~50-line shape for the moderator phase machine: each phase handler returns the next phase name; the loop just dispatches.
ADOPT: (1) Register 'moderator' in agent/roles/__init__.py as a real role with its own soul, LLM, and progress file; coordinator keeps only phase-clock + final-tally duties. (2) Refactor moderator.py into PHASES = {'FRAME': frame_step, 'OPENING': opening_step, ...} where each step returns the next phase (or None to stay) — a declarative table instead of if/elif chains, reusable by the studio_chat and painting flows.
effort: medium

## Claude Agent SDK: lifecycle hooks + compaction with identity re-injection
url: https://code.claude.com/docs/en/agent-sdk/hooks
what: Named hook points fire around the agent lifecycle: SessionStart/SessionEnd, PreCompact (back up transcript before context compression), post-compaction (re-insert the agent's core identity document at the moment it is most at risk of being lost), SubagentStart. Subagents keep transcripts in separate files, unaffected by main-conversation compaction, and are resumable by session_id with full history.
relevance: Two mappings: (a) loop.py has implicit lifecycle moments (boot/register, phase change, turn start/end) that projects currently customize by editing engine code — named hook lists make the engine reusable across projects, the stated goal in memory. (b) context_budget.py trims history for the 32k-ish Qwen context; the Claude SDK pattern says: when compacting a long debate, summarize old rounds into one digest message BUT always re-pin the soul/frame after compaction, because that is exactly what gets lost.
ADOPT: (1) hooks = {'pre_turn': [], 'post_turn': [], 'on_phase_change': [], 'pre_compact': []} in loop.py, called with ctx — projects append callables without touching the engine. (2) In context_budget.py: compaction = replace rounds older than N with a moderator-authored ROUND_DIGEST message, and always re-inject soul + FRAME at the top of the composed prompt.
effort: small

## smolagents: agent-as-callable with mandated report template
url: https://smolagents.org/docs/orchestrate-a-multi-agent-system-%F0%9F%A4%96%F0%9F%A4%9D%F0%9F%A4%96/
what: Hugging Face's minimal framework: a manager CodeAgent receives worker agents via managed_agents (since 1.8.0, plain sub-agent passing — the ManagedAgent wrapper was deleted as overweight); each worker is exposed as a callable with name + description, and its final answer must follow a mandated template: 'Task outcome (short version) / Task outcome (extremely detailed) / Additional context'. The manager writes Python that calls workers.
relevance: Smallest-footprint datapoint: even the most minimal framework found two things non-negotiable — a name+description card per agent (openclaw already has this in the agents/ registry; ensure description is filled, since the SelectorGroupChat-style {roles} prompt needs it) and a fixed answer template so the manager can consume worker output without parsing prose. Their own deletion of ManagedAgent is a warning against wrapper layers — matches the no-framework stance.
ADOPT: Mandate a short/detailed/context template for terminal messages (debater CONCLUSION summaries, painter plan reports) enforced via the guided_json schemas from the vLLM item, so the moderator's tally and the viz never scrape free text.
effort: small

## Google ADK: LoopAgent escalate signal + state-rides-on-events rule
url: https://google.github.io/adk-docs/agents/workflow-agents/loop-agents/
what: LoopAgent reruns sub-agents until max_iterations OR any sub-agent signals escalate=True in its EventActions (or calls the built-in exit_loop tool) — dual exit: hard cap + agent-initiated early stop. Separately (https://google.github.io/adk-docs/sessions/state/): session.state must only be updated as part of appending an Event via append_event(), so every state mutation is tracked, persistence stays correct, and history is the source of truth.
relevance: (a) The DEBATE phase already has min/max rounds with drones requesting more turns — ADK shows the clean protocol: keep max_rounds as the hard cap and add an explicit ESCALATE/EXIT_LOOP message type (e.g., moderator or a consensus check emits it when DEBATE_CONSENSUS share is reached) instead of implicit heuristics. (b) The state-on-events rule is an audit for bb.py: any state/*.json write that lacks a corresponding events.jsonl line breaks replay — worth enforcing in Blackboard.write_state (auto-append a state_change event).
ADOPT: (1) Explicit exit_loop/escalate message honored by the moderator's round counter, alongside max_rounds. (2) bb.py invariant: every state-file write also appends an event, making state/*.json a pure projection of events.jsonl — which is what makes the LangGraph-style checkpoint/replay item trivially correct.
effort: small

## LlamaIndex Workflows 1.0: typed-event dispatch (consider, don't necessarily adopt)
url: https://www.llamaindex.ai/blog/announcing-workflows-1-0-a-lightweight-framework-for-agentic-systems
what: Workflows are @step-decorated functions that accept and emit typed (Pydantic) Events; control flow emerges from event subscriptions rather than a central graph or phase poller; Context checkpointing supports durable resume after restart.
relevance: The blackboard's messages ARE typed events (FRAME/FLOOR/ARGUMENT/VOTE...), so roles could dispatch on new-message-type → handler map instead of switching on phase. Attractive for the stigmergic studio_chat mode where drones self-drive; however for the debate engine the moderator-owned phase machine was a deliberate decision (guaranteed termination), so this is a secondary dispatch style, not a replacement.
ADOPT: Only the dispatch idiom, and only inside roles: a small ON = {FLOOR: on_floor, FRAME: on_frame, ...} handler table per role keyed by message type, replacing per-phase if-chains in debate.py — the moderator still owns phase transitions.
effort: medium

TAKEAWAYS:
- Universal convergent pattern for next-speaker choice (AG2, SelectorGroupChat, CrewAI manager): deterministic Python filter narrows candidates FIRST, the LLM only ranks within that pool, the returned name is validated against the roster with 2-3 bounded repair re-prompts, and exhaustion falls back deterministically (next-in-list). Never let the raw LLM pick drive the phase machine — this is the single highest-value ~40-line upgrade to moderator.py.
- Checkpoint at phase/superstep boundaries, not per message (Microsoft Agent Framework supersteps, LangGraph steps). Because bb.py is already append-only + single-writer, a checkpoint is just {phase, state/*.json snapshot, events.jsonl byte offset} in runs/<run_id>/ — resume, replay, and fork (time-travel debugging of a debate) come nearly free. MS Agent Framework shipping FileCheckpointStorage as a production backend is direct validation of the file-blackboard design.
- Failure handling has one production shape (LangGraph): typed retry policy with backoff (0.5s, x2, max 3) at the step level, the ERROR durably committed as an event before any recovery runs (so restarts see identical failure context), then a deterministic per-role fallback (debater → explicit ABSTAIN, moderator → deadline-advance). This closes the known roles.step SPOF and the hash-pick abstain debt in one pattern.
- Make the moderator a first-class agent, not coordinator glue — CrewAI's manager_agent, smolagents' manager CodeAgent, and SelectorGroupChat's inner selector all model the orchestrator as a real agent with its own LLM, prompt, and validation duties, while a thin deterministic runner keeps termination guarantees. This confirms the planned moderator-as-ROLE refactor and thin-facilitator coordinator.
- Enforce structured output at the sampler, not the parser: vLLM guided_choice for VOTE ballots (the model physically cannot vote off-ballot), guided_json per message type for FLOOR_REQUEST/ARGUMENT metadata, via response_format on the existing sverk/Qwen endpoint — then delete brain.py's regex JSON repair. This is the OpenAI Agents SDK output_type/input_type idea implemented server-side for free.
- Termination and loop-exit should be explicit and composable: small predicates over the message log (max_messages | text_mention | all_voted | deadline | external stop-file) combined with any()/all() (AutoGen termination conditions), plus an ADK-style escalate/exit_loop message for agent-initiated early stop under a hard max_rounds cap — replaces scattered deadline logic as the only safety net.
- Human-in-the-loop is trivial on a file blackboard: LangGraph's interrupt()/Command(resume) reduces to moderator writing pending_interrupt.json and idling until the viz UI or a human writes the answering message — no new infrastructure, and it doubles as a pre-CONCLUDE debugging breakpoint.
- Do NOT adopt a framework: every surveyed system's differentiator is packaging around the same six primitives, and the minimal players actively shed abstraction (smolagents deleted its ManagedAgent wrapper). Each primitive above is a 30-100 line pattern over the existing bb.py/loop.py/moderator.py.


# TRACK: blackboard-stigmergy
SUMMARY: Research across classic blackboard systems (Hearsay-II, BB1, GBB), 2024-26 LLM-era blackboard/stigmergy papers, distributed-ordering techniques, and event-sourcing practice yields a clear picture for openclaw-stack. (1) The classic lesson is that the blackboard alone is not the architecture — the control shell is: Hearsay-II's event-driven knowledge-source activation with a prioritized agenda, and BB1's move of putting the control plan itself ON the blackboard, map directly onto the coordinator role and suggest making agent activation event-driven off events.jsonl with the coordinator's strategy stored as inspectable blackboard state. (2) LLM-era work validates the pattern: LbMAS (arXiv 2507.01701) shows blackboard-selected agents match SOTA MAS at lower token cost; the data-science blackboard (arXiv 2510.01285) shows publish-request/agents-volunteer beats master-slave by 13-57% when the coordinator lacks capability observability; PatchBoard (arXiv 2605.29313) shows schema-validated JSON-patch mutations with role write-permissions massively beat free-form shared memory (84.6% vs 30.8% success on ALFWorld). (3) For the ordering bug: since events.jsonl is a single local file, the SIMPLEST correct fix is to treat physical line order as the total order (atomic via O_APPEND + single write() per line), make seq authoritative and recover it on restart by reading the log tail (fixing the reset bug), and demote timestamps to millisecond-precision metadata with (writer_id, per_writer_seq) for dedup — Lamport/HLC/ULID are only needed if the system ever spans hosts. (4) Event-sourcing practice says events.jsonl is the source of truth and state JSONs are snapshots/projections: stamp each state JSON with last_applied_seq, replay only events after it, keep consumers idempotent via last-processed-seq tracking, and suppress side effects (LLM calls, paint actions) during replay. (5) Stigmergic-vs-orchestrated benchmarking exists but is thin: CodeCRDT (600 trials) found stigmergic coordination gives up to +21% speedup on parallelizable tasks but up to -39% on dependency-heavy ones — task structure decides, so openclaw's hybrid (coordinator + blackboard) is defensible.

## Hearsay-II (event-driven KS activation + agenda scheduler)
url: https://en.wikipedia.org/wiki/Blackboard_system
what: The original 1970s blackboard speech-understanding system: independent knowledge sources (KSs) fire when blackboard changes match their trigger preconditions; a control shell with a prioritized agenda and focus-of-attention picks which activation runs next.
relevance: openclaw's painter/debater roles are exactly KSs and the coordinator is a (currently implicit) control shell; agents currently poll rather than being activated by blackboard events, and there is no priority/focus mechanism when multiple agents could act.
ADOPT: Event-driven activation: each role declares trigger conditions over event types in events.jsonl (a small precondition function), and the coordinator maintains an agenda of (agent, triggering_event, priority) instead of round-robin turns — activation records also give free provenance for debugging.
effort: medium

## BB1 — Hayes-Roth, 'A Blackboard Architecture for Control' (1985)
url: https://dl.acm.org/doi/10.1016/0004-3702(85)90063-3
what: The classic control-architecture paper: BB1's key innovation was a separate 'control blackboard' where the scheduling strategy itself is posted as data, so the system can inspect, explain, and modify its own control decisions in the same loop as domain problem-solving.
relevance: openclaw's coordinator makes scheduling decisions inside LLM prompts/Python that vanish after each turn; when debugging 'why did painter-3 go twice', there is no record.
ADOPT: A control-state JSON (single-writer: coordinator) holding the current strategy/phase/next-agent rationale, updated via the same event log — makes coordination decisions replayable and lets the moderator/coordinator reason over its own past control choices.
effort: small

## GBB + blackboard-systems retrospective (Nii lineage)
url: https://link.springer.com/article/10.1007/BF00140399
what: GBB (Generic BlackBoard) added typed, multi-dimensional blackboard 'spaces' with efficient pattern-matched retrieval; the Springer AI Review survey covers what generations of blackboard systems learned about structuring the shared store.
relevance: openclaw already fragments state into per-concern JSONs (map.json, palettes, debate state) — that is GBB's typed-spaces idea; the missing piece is declared schemas per space rather than ad-hoc dict shapes.
ADOPT: Formalize each state JSON as a named, schema'd blackboard space (even a lightweight dataclass/pydantic per file) so agents pattern-match on typed regions instead of parsing free-form blobs.
effort: small

## LbMAS — 'Exploring Advanced LLM Multi-Agent Systems Based on Blackboard Architecture' (2025)
url: https://arxiv.org/abs/2507.01701
what: LLM MAS where all agents share a blackboard, a control unit selects which agents act each round based on current blackboard content, looping until consensus; achieved best average performance vs static and dynamic MAS baselines while spending fewer tokens.
relevance: Direct modern validation of openclaw's design choice; their token result matters because openclaw feeds blackboard history into every prompt (the context_budget.py concern).
ADOPT: Content-based agent selection (coordinator selects next speaker from blackboard state, not fixed rotation) plus an explicit consensus/termination predicate on the blackboard instead of fixed round counts for debates.
effort: medium

## LLM-Based Multi-Agent Blackboard System for Information Discovery (2025)
url: https://arxiv.org/abs/2510.01285
what: Central agent posts requests to a shared blackboard; subordinate agents volunteer based on self-assessed capability. Beat master-slave orchestration by 13-57% relative end-to-end, precisely because the main agent lacked full observability of sub-agent competencies.
relevance: openclaw's coordinator currently must know what each painter/debater can do; a volunteer step ('who wants this region/argument?') removes that coupling and is natural for the persona system (personas.py).
ADOPT: A request-and-volunteer event pair on the blackboard: coordinator appends a task_request event, agents append bid events, coordinator picks — decouples adding new souls/personas from coordinator prompt changes.
effort: medium

## PatchBoard — Schema-Grounded State Mutation (2026)
url: https://arxiv.org/abs/2605.29313
what: Replaces free-form shared memory with JSON Patch mutations validated by a deterministic kernel (schema compliance + role-specific write permissions + runtime invariants) before commit, producing an auditable mutation log. 84.6% vs 30.8% (LangGraph) success on ALFWorld at ~8x fewer tokens per success.
relevance: openclaw's single-writer-per-JSON rule is a crude ACL; PatchBoard is the mature version — validate every state write, enforce writer identity, and log the patch, which also fixes silent state corruption when an LLM emits malformed updates.
ADOPT: A small validation kernel in bb.py: state mutations expressed as patches carried in events, checked against a per-file schema + writer_id allowlist + invariants before applying; rejected patches become error events the agent can react to.
effort: medium

## CodeCRDT — Observation-Driven (stigmergic) Multi-Agent Coordination (2025)
url: https://arxiv.org/abs/2510.18893
what: Agents coordinate by watching a shared CRDT document rather than messaging: 600 trials showed up to 21.1% speedup on some tasks, up to 39.4% slowdown on others, 100% convergence, 5-10% semantic conflict rates — the closest thing to a stigmergic-vs-orchestrated benchmark.
relevance: Answers the audit question 'does anyone benchmark stigmergy vs orchestration': yes, and the verdict is task-structure-dependent — parallelizable canvas painting suits stigmergy, dependency-heavy debate turns suit orchestration, which supports openclaw keeping both modes.
ADOPT: Their evaluation framing: measure openclaw's collab-paint mode with and without coordinator gating (agents self-select regions by observing map.json) and track semantic-conflict rate (overlapping paints) as the quality metric.
effort: large

## Ledger-State Stigmergy (2026) + Anthropic's observed emergent stigmergy
url: https://arxiv.org/abs/2604.03997
what: A formal framework for indirect coordination through shared persistent state, motivated by the lack of convergence guarantees under concurrent writes for stochastic LLM agents; complemented by the LessWrong writeup (https://www.lesswrong.com/posts/sX9LztxjtSEwd8qEo/emergent-stigmergic-coordination-in-ai-agents-1) of agents unintentionally coordinating through persistent web traces.
relevance: Both underline the audit's core risk: stigmergic systems inherit the consistency semantics of their medium — openclaw's medium (files + second-granularity timestamps) currently cannot guarantee the ordering the agents' reasoning assumes.
ADOPT: The framing only: document events.jsonl's ordering/atomicity guarantees explicitly as the system's 'coordination contract' so future role authors know what they can and cannot assume.
effort: small

## Atomic file appends (O_APPEND) — the physical-order fix
url: https://nullprogram.com/blog/2016/08/03/
what: On Linux local filesystems, writes to a file opened with O_APPEND are positioned atomically, and single write() calls of a full line (well under 4KB-4MB) do not interleave; stdio buffering ('a' mode with buffered partial writes) is the thing that breaks this. See also https://www.notthewizard.com/2014/06/17/are-files-appends-really-atomic/ and https://pvk.ca/Blog/2021/01/22/appending-to-a-log-an-introduction-to-the-linux-dark-arts/.
relevance: This is the SIMPLEST correct fix for openclaw's same-second ordering bug: for a single-host, single-file log, physical line order in events.jsonl IS a valid total order — timestamps are not needed for ordering at all.
ADOPT: In bb.py: open events.jsonl with O_APPEND, emit each event as exactly one write() of one full line, and define event order as line order; assign the authoritative global seq at append time; record timestamps in milliseconds purely as metadata. Caveat to document: not valid on NFS.
effort: small

## Per-writer (writer_id, seq) + Lamport/HLC/ULID — ordering ladder for if/when it distributes
url: https://github.com/ulid/spec
what: The escalation path beyond single-file order: (a) monotonic per-writer (writer_id, seq) pairs for dedup/causality; (b) Lamport clocks — counter = max(local, observed)+1, ties broken by writer_id (https://singhajit.com/distributed-systems/lamport-clock/); (c) HLCs combining wall time + logical counter (https://singhajit.com/distributed-systems/hybrid-clock/); (d) ULIDs — 48-bit ms timestamp + 80-bit randomness with a monotonic same-millisecond factory, giving sortable unique event IDs per process.
relevance: Fixes openclaw's two concrete bugs even without the file-order change: seq resetting on restart, and same-second timestamp ties; also future-proofs if painters ever run on separate hosts writing separate log segments.
ADOPT: Two-line fix for the seq-reset bug: on startup, read the last line of events.jsonl and resume seq from it (or max seq for this writer_id). Give every event (writer_id, writer_seq) so consumers can dedup and detect gaps. Only reach for HLC/ULID if the single-file invariant is ever broken — they are overkill today.
effort: small

## Event Sourcing pattern (snapshots, replay, source-of-truth)
url: https://microservices.io/patterns/data/event-sourcing.html
what: Canonical pattern: the append-only event stream is the source of truth; current state is a projection; snapshots let you rehydrate by loading the latest snapshot and replaying only events after it; replays must not re-trigger external side effects. See also https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing and https://dev.to/alex_aslam/snapshot-strategies-optimizing-event-replays-36oo.
relevance: openclaw already has both halves (events.jsonl + state JSONs) but with undefined relationship — is map.json truth or is the log? Ambiguity here is where restart bugs (like the seq reset) breed.
ADOPT: Declare events.jsonl the source of truth and each state JSON a snapshot stamped with last_applied_seq; on restart, rehydrate by replaying events after last_applied_seq instead of trusting the JSON blindly; add a replay mode flag that suppresses side effects (LLM calls, viz pushes) so any run can be reconstructed for debugging.
effort: medium

## Idempotent consumers (EventSourcingDB / Kafka practice)
url: https://docs.eventsourcingdb.io/best-practices/common-issues/
what: Consumers track the last event seq they processed and skip anything at-or-below it; handlers are written so processing a duplicate is a no-op — the standard defense against double-processing after crashes/restarts (see also https://www.conduktor.io/glossary/event-sourcing-patterns-with-kafka).
relevance: openclaw agents that tail events.jsonl will reprocess events after a restart (same root cause as the seq-reset bug on the write side); a painter re-acting on an old event double-paints or re-argues a settled debate point.
ADOPT: Each agent persists its own cursor (last processed global seq) next to its state; the loop in loop.py reads from cursor+1; combined with per-event (writer_id, writer_seq), duplicates become detectable and skippable.
effort: small

## Memory in LLM-based Multi-agent Systems survey (2025)
url: https://www.researchgate.net/publication/398392208_Memory_in_LLM-based_Multi-agent_Systems_Mechanisms_Challenges_and_Collective_Intelligence
what: Survey of shared-memory mechanisms in LLM MAS: blackboard-style designs (manager maintains global task state, workers do role-specific subtasks), externally hosted shared memory (databases/documents), and their tradeoffs for collective intelligence.
relevance: Positions openclaw's file-blackboard in the design space and confirms the manager-maintains-global-state pattern (coordinator + state JSONs) is the dominant working configuration, with context-budgeting of shared history as the recognized open problem.
ADOPT: Use its taxonomy to decide per-role what slice of the blackboard goes into each prompt (role-scoped views over the shared store) rather than sending full history — directly informs context_budget.py.
effort: medium

TAKEAWAYS:
- Simplest correct ordering fix (adopt now): for a single-host events.jsonl, physical line order is the total order — write each event as one O_APPEND write() of one full line, assign the global seq at append time, and fix the restart bug by resuming seq from the last line of the log at startup. Millisecond timestamps become metadata, never an ordering key. Lamport/HLC/ULID are only warranted if the log ever spans processes-on-different-hosts or multiple files.
- Add (writer_id, writer_seq) to every event and a persisted per-consumer cursor (last processed seq): together these give dedup, gap detection, and idempotent restart on both the write and read side — small changes to bb.py/loop.py that eliminate the whole class of same-second and restart bugs.
- Classic blackboard lesson that maps cleanest to LLM agents: the control shell is the architecture. Make activation event-driven (roles declare trigger preconditions over event types, Hearsay-II style) and post the coordinator's strategy/decisions to a control-state JSON (BB1 style) so scheduling is inspectable and replayable.
- Declare events.jsonl the source of truth and state JSONs snapshots stamped with last_applied_seq; rehydrate by replay-after-snapshot, and gate side effects behind a replay flag — standard event-sourcing practice that also gives free time-travel debugging for painter/debate runs.
- Free-form shared memory is the known failure mode in LLM MAS: PatchBoard's schema-validated patch mutations with role write-permissions (84.6% vs 30.8% success, ~8x fewer tokens) is the strongest recent evidence that openclaw should validate state writes against per-file schemas and writer allowlists rather than trusting agent output.
- Stigmergic vs orchestrated IS being benchmarked (CodeCRDT: +21% to -39% depending on task structure; blackboard-volunteer vs master-slave: +13-57% when the coordinator lacks capability observability), and the verdict is task-dependent — openclaw's hybrid of coordinator-gated debate plus blackboard-mediated painting matches the evidence; consider a request/volunteer event pair so new personas need no coordinator changes.
- Sources: Hearsay-II/control-shell background (https://en.wikipedia.org/wiki/Blackboard_system), BB1 (https://dl.acm.org/doi/10.1016/0004-3702(85)90063-3), blackboard-systems review (https://link.springer.com/article/10.1007/BF00140399), LbMAS (https://arxiv.org/abs/2507.01701), blackboard data-science MAS (https://arxiv.org/abs/2510.01285), PatchBoard (https://arxiv.org/abs/2605.29313), CodeCRDT (https://arxiv.org/abs/2510.18893), Ledger-State Stigmergy (https://arxiv.org/abs/2604.03997), emergent stigmergy writeup (https://www.lesswrong.com/posts/sX9LztxjtSEwd8qEo/emergent-stigmergic-coordination-in-ai-agents-1), MAS memory survey (https://www.researchgate.net/publication/398392208_Memory_in_LLM-based_Multi-agent_Systems_Mechanisms_Challenges_and_Collective_Intelligence), atomic appends (https://nullprogram.com/blog/2016/08/03/, https://www.notthewizard.com/2014/06/17/are-files-appends-really-atomic/, https://pvk.ca/Blog/2021/01/22/appending-to-a-log-an-introduction-to-the-linux-dark-arts/), Lamport/HLC (https://singhajit.com/distributed-systems/lamport-clock/, https://singhajit.com/distributed-systems/hybrid-clock/), ULID spec (https://github.com/ulid/spec), event sourcing (https://microservices.io/patterns/data/event-sourcing.html, https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing, https://docs.eventsourcingdb.io/best-practices/common-issues/, https://dev.to/alex_aslam/snapshot-strategies-optimizing-event-replays-36oo, https://www.conduktor.io/glossary/event-sourcing-patterns-with-kafka).


# TRACK: collab-image
SUMMARY: Research landscape 2024-2026 for making one coherent painting from 4 independent color-owning shape emitters. Three converging lines of work apply directly. (1) Multi-agent image-gen systems (coDrawAgents CVPR'26, Talk2Image, CREA, MCCD, RPG) all converge on the same integration recipe: a planner that decomposes the prompt into region/priority-ranked sub-briefs, incremental generation grounded in the *rendered partial canvas*, a dedicated Checker agent that validates cross-object conflicts (overlap, occlusion-order) before commit, and explicit seam treatment where independently-generated regions meet. coDrawAgents' ablation is the single most useful data point: letting the planner see the evolving rendered canvas was worth more (+1.9 GenEval) than layout decomposition itself. (2) LLM SVG/vector work (SVGenius, SGP-GenBench, Chat2SVG, IntroSVG, See-it-Say-it-Sorted, GeoSVG-RL) establishes that frontier LLMs are good at attribute binding and numeracy (80-90%) but weak at global spatial relations and degrade sharply with scene complexity; the scaffolds that work are layout-first "geometric contracts" checked by a deterministic renderer/verifier, and render-critique-refine loops with *qualitative relational* VLM feedback (not numeric coordinates), where ~2 iterations suffice and a critic-candidates-judge structure beats single-shot revision. (3) Layout research (LayoutGPT CSS-format prompting, ART's anonymous-region multi-layer generation) shows format and region-anchoring matter: CSS-like normalized layout blocks measurably improve LLM spatial planning, and a global caption + anonymous region boxes is sufficient to coordinate 50+ independent layers. True composition-negotiation-via-dialogue is thin: coDrawAgents is the closest published system, and the negotiation literature (PatchBoard, grounding-failure studies) argues for structured schema-validated blackboard patches over free-form chat — which maps directly onto openclaw-stack's existing bb.py blackboard and scene-skeleton map.json.

## coDrawAgents (CVPR 2026)
url: https://arxiv.org/abs/2603.12829
what: Multi-agent dialogue framework for compositional T2I: Interpreter (parses prompt into attribute-rich object descriptors ranked by semantic salience), Planner (proposes bounding-box layouts incrementally, grounded in the evolving rendered canvas via 'Visualization Chain-of-Thought': canvas-state analysis, context-aware planning, physics-constraint enforcement), Checker (object-level size/boundary checks plus global cross-object conflict checks including occlusion-ordering), Painter (incremental layout-to-image rendering). SOTA on GenEval (0.94 vs 0.84 for GPT Image 1).
relevance: The closest published analog to openclaw-stack: multiple agents incrementally committing to one shared canvas with a skeleton-like layout. Its ablation quantifies exactly which coherence mechanism matters: layout-aware mode +5.0, canvas-visual-context grounding +1.9 (largest single increment), Checker +0.66.
ADOPT: Two mechanisms: (a) sequence drone commits by semantic salience groups (background/structure first, detail last) and feed each drone a render of the partial composite before it emits shapes — canvas-grounded planning beat everything else in their ablation; (b) add a Checker pass between drone emission and compositing that validates per-shape constraints (in-region, in-canvas, sane size) and cross-drone conflicts (overlap, z/occlusion-order contradictions) and sends rejects back with reasons.
effort: medium

## See it. Say it. Sorted. (agentic compositional SVG diagram generation)
url: https://arxiv.org/abs/2508.15222
what: Training-free agentic loop for sketch-to-SVG: a Critic VLM proposes a small set of qualitative, relational edits; multiple candidate LLMs synthesize SVG updates with diverse strategies (conservative to aggressive); a Judge VLM selects the best candidate. Outperformed GPT-4o and Gemini 2.5 Pro at layout/structure reconstruction.
relevance: Directly answers 'iterative render-and-critique for vector composition'. The key insight — VLM critics are reliable at qualitative relational judgments ('the sun overlaps the roof, move it up-left') and unreliable at numeric coordinate estimates — dictates how a coordinator's vision feedback to drones should be phrased.
ADOPT: The critic-candidates-judge pattern on the composited canvas: after each round, a VLM critic emits a short list of relational defects; each affected drone produces 2-3 alternative patch sets (conservative vs aggressive); a judge VLM picks per-defect winners. Keep edits small and monotonic rather than regenerating layers wholesale.
effort: medium

## GeoSVG-RL (layout-constrained text-to-SVG)
url: https://arxiv.org/abs/2605.25447
what: RL framework (May 2026) where the model first emits a structured layout plan that serves as a 'geometric contract' for subsequent SVG code, and a browser-backed renderer/verifier computes executable rewards across six dimensions: rendering validity, canvas fitting, anchor placement, text containment, graph consistency, code cleanliness.
relevance: The 'geometric contract + deterministic verifier' idea is adoptable without any RL: openclaw's scene skeleton already is the contract; what is missing is the machine-checkable enforcement layer between drone output and composite.
ADOPT: A deterministic geometric linter run on each drone's emitted shape list before compositing: verify shapes fall inside the drone's assigned region (with tolerance band), z-values within the drone's assigned z-band, no canvas overflow, polygon validity. Auto-clip or bounce violations with a structured error message the drone can act on. Cheap, deterministic, catches the failure class that VLM critics miss.
effort: small

## RPG: Recaption, Plan, Generate (ICML 2024)
url: https://arxiv.org/abs/2401.11708
what: Training-free framework using an MLLM as global planner: recaptions the prompt into detail-enriched per-region sub-prompts, plans complementary (jointly exhaustive, non-overlapping) subregions, then runs complementary regional diffusion per region.
relevance: The canonical 'divide canvas into regions, enrich each sub-brief, generate independently' pipeline — exactly openclaw's skeleton-assigns-regions architecture, with one upgrade openclaw lacks: recaptioning.
ADOPT: Recaptioning: have the coordinator rewrite each drone's skeleton assignment into a self-contained, detail-enriched sub-prompt that includes neighbor context (what adjoins each region edge, what palette/shapes the neighbors will contribute), so drones make locally-informed decisions without seeing each other's chatter. Also the 'complementary' discipline: region partition should be jointly exhaustive so no dead zones appear.
effort: small

## MCCD: Multi-Agent Collaboration-based Compositional Diffusion
url: https://arxiv.org/abs/2505.02648
what: Training-free system: a multi-agent MLLM scene-parsing module (agents with distinct tasks extract objects, attributes, relations, layout boxes) feeding hierarchical compositional diffusion that merges regions via Gaussian-mask refinement of bounding boxes, region enhancement, and latent-space smoothing at region boundaries.
relevance: Its integration module solves openclaw's core seam problem: independently generated regions look pasted together. MCCD's answer is soft region edges plus explicit boundary smoothing.
ADOPT: The vector-space analog of latent smoothing: define overlap bands where drone regions meet, assign each band a single 'seam owner' drone (or the coordinator), and require transitional shapes there (intermediate colors/shapes bridging the two regions). Feathered region masks in the skeleton rather than hard rectangles.
effort: medium

## Talk2Image (known prior art, deepened)
url: https://arxiv.org/abs/2508.06916
what: Multi-turn multi-agent image generation/editing: intention parsing from dialogue history, task decomposition across specialized agents, and feedback-driven cyclic refinement based on a multi-view evaluation mechanism; a coordination module integrates agent outputs to avoid incoherent edits.
relevance: Confirms the pattern that coherence comes from the evaluation side as much as the planning side: multiple evaluation views (semantic alignment, consistency, controllability) scored each round drive refinement.
ADOPT: Multi-view evaluation: score the composite each round on separate axes (skeleton adherence, color-role fidelity, cross-region coherence, aesthetics) with separate rubric prompts, and route each failing axis to the responsible drone rather than issuing one blended critique.
effort: small

## CREA (NeurIPS 2025, known prior art, deepened)
url: https://arxiv.org/abs/2504.05306
what: Collaborative multi-agent framework mimicking human creative workflow: specialized agents (Creative Director, Art Critic, etc.) communicate to conceptualize, generate, critique, and enhance; first agentic framework for creative editing, disentangled phase structure.
relevance: Its contribution relative to openclaw is the disentangled phase protocol: conceptualization dialogue happens fully before generation, and critique is a distinct named role with authority, not a side-channel.
ADOPT: Phase-gate the run: a conceptualization round where drones and coordinator agree on the skeleton (this is the negotiation slot), a generation round, then a critique round by a dedicated Art Critic persona whose output is binding revision directives. Openclaw's souls/ personas map directly onto the named creative roles.
effort: small

## LayoutGPT
url: https://layoutgpt.github.io/
what: LLMs as visual planners generating 2D image layouts and 3D scene layouts from text, using CSS-like style-sheet formatting for in-context exemplars; 20-40% better than raw T2I on numerical and spatial-relation faithfulness. Follow-up work (FlairGPT, procedural scene programs) found imperative LLM placement violates physical constraints and moved to declarative constraint solving.
relevance: Two lessons for the skeleton format: serialization format measurably changes LLM spatial competence, and raw coordinate emission by LLMs drifts — constraints should be declared and solved/verified outside the LLM.
ADOPT: (a) Express the scene skeleton and drone briefs in CSS-like normalized blocks (object { position: x y; width; height; z }) with 2-3 few-shot exemplar layouts — cheap prompt-level change; (b) move toward declarative constraints in the skeleton (A above B, C inside region-2) checked by the geometric linter, instead of trusting drone-emitted absolute coordinates.
effort: small

## SGP-GenBench / Symbolic Graphics Programming with LLMs
url: https://arxiv.org/abs/2509.05208
what: Benchmark of LLM SVG scene generation across object fidelity, scene fidelity, and compositionality (attribute binding, spatial relations, numeracy). Frontier models (Claude, Gemini) hit 80-90% on color binding and numeracy; open 7B models near-fail (8.8) until RL lifts them to 60+. RL-trained models spontaneously learn to decompose complex objects into many simple primitives and add scene-appropriate unprompted detail.
relevance: Calibrates what to trust the drones with: attribute/count duties are safe to delegate; global spatial relations are the weak axis and must stay in the skeleton/coordinator. The emergent decomposition finding endorses openclaw's primitive vocabulary (rect/ellipse/line/poly) — many simple shapes beat few complex ones.
ADOPT: Prompt-level: instruct drones to build subjects from many simple primitives rather than single complex polygons, and to add scene-consistent supporting detail within their region; keep all inter-region spatial relationships in the coordinator-owned skeleton, never delegated.
effort: small

## SVGenius (ACM MM 2025)
url: https://arxiv.org/abs/2506.03139
what: First comprehensive LLM SVG benchmark: 2,377 queries across understanding/editing/generation with complexity stratification, 22 models evaluated. All models degrade with complexity; reasoning-enhanced training beats pure scaling.
relevance: Justifies a per-drone complexity budget and model selection policy: performance collapse is driven by scene complexity, not model size, so bounding each drone's shape count per commit protects quality.
ADOPT: Complexity budgeting: cap shapes-per-commit per drone and split complex subjects across multiple canvas-grounded rounds; use reasoning-mode models for the coordinator/planning steps where composition is decided.
effort: small

## Chat2SVG
url: https://arxiv.org/abs/2411.16602
what: LLM generates an SVG template from semantic primitives, then a visual rectification loop: render, LLM inspects the image, suggests corrections, regenerates. Empirically two iterations suffice for well-structured spatial layouts; detail added afterward via diffusion+optimization.
relevance: Template-first-then-detail and a hard iteration cap are directly transplantable to the drone loop, preventing endless refinement churn in the paint rounds.
ADOPT: Coarse-to-fine per drone: round 1 emits large layout-defining shapes only; render and rectify (max 2 vision-feedback passes); later rounds add detail shapes on higher z within the already-validated layout.
effort: small

## IntroSVG (generator-critic text-to-SVG)
url: https://arxiv.org/abs/2603.09312
what: A single VLM plays both Generator and Critic in a closed generate-critique-refine loop over rendered SVG; critic gives actionable revision suggestions plus scores; early-stage failures are systematically converted into error-correction training data. SOTA on semantic alignment and editability.
relevance: Shows the critique loop works with one model wearing two hats (cheap for openclaw's per-drone loop) and that failure logging compounds: yesterday's rejected shapes become tomorrow's few-shot corrections.
ADOPT: Persist a failure corpus: every Checker rejection and critic correction (bad shape list, reason, fixed version) gets logged and the best examples injected as few-shot error-correction demos into drone prompts on later runs — improvement without any training.
effort: medium

## ART: Anonymous Region Transformer (CVPR 2025, Microsoft)
url: https://arxiv.org/abs/2502.18364
what: Generates variable multi-layer transparent images (50+ layers) from one global caption plus an 'anonymous region layout' — region boxes with no per-layer captions needed; layer-wise region-crop attention makes it 12x faster than full attention; includes a multi-layer transparency autoencoder.
relevance: Strongest published validation of openclaw's exact architecture: a global brief plus anonymous region boxes is sufficient conditioning to keep 50+ independently generated layers coherent — 4 drones is well inside that envelope. Also suggests transparency semantics openclaw lacks.
ADOPT: (a) Confidence that skeleton = global caption + region boxes is the right minimal contract, and it scales past 4 drones; (b) consider per-shape alpha in the drone shape schema so z-compositing can produce blending/glazing between color layers instead of pure occlusion, which is a large coherence win for a one-color-per-drone system.
effort: medium

## Think in Strokes, Not Pixels (process-driven image generation)
url: https://huggingface.co/papers/2604.04746
what: Replaces single-pass synthesis with a Plan-Sketch-Inspect-Refine cycle of interleaved textual/visual reasoning; scene-graph subsampling produces logical incremental steps that expand the composition without contradictions; the Inspect stage explicitly distinguishes incomplete-but-correct states from actual errors. +5% GenEval on BAGEL-7B.
relevance: Solves a critique-loop failure mode openclaw will hit: a critic looking at a half-finished multi-round painting flags missing content as errors, causing drones to thrash.
ADOPT: (a) Derive commit order from a scene graph (coordinator subsamples it into contradiction-free increments assigned to drones per round); (b) give the critic the round plan so it labels findings as 'not-yet-painted (expected)' vs 'wrong (fix)', and only the latter triggers revisions.
effort: medium

## Structured negotiation over blackboards (PatchBoard + negotiation-grounding literature)
url: https://arxiv.org/pdf/2605.29313
what: PatchBoard: schema-grounded state mutation for reliable, auditable LLM multi-agent collaboration — agents interact by proposing typed, schema-validated patches to a shared blackboard rather than free-form chat. Companion evidence: 'Talk is Cheap, Communication is Hard' (https://arxiv.org/pdf/2605.01750) documents grounding failures in free-dialogue multi-agent negotiation; NegotiationArena shows LLMs can negotiate resource allocation over structured multi-turn protocols.
relevance: Answers the 'agents NEGOTIATE a shared composition' question with the field's current consensus: negotiation works when it is proposals-over-shared-typed-state, and fails as free chat due to grounding drift. Openclaw already has the substrate (bb.py blackboard, map.json skeleton, debate roles).
ADOPT: A skeleton-negotiation phase implemented as typed blackboard operations: drones emit claim(region), propose(shape-group, z-band), object(conflict-id, reason), accept(proposal-id) against the shared scene graph; the coordinator acts as control shell resolving conflicts by rule (z-band precedence, region ownership) with bounded rounds. Reuse the existing debate/moderator machinery but replace free-text arguments with schema-validated composition ops.
effort: medium

TAKEAWAYS:
- Canvas-grounded incremental planning is the highest-leverage single change: coDrawAgents' ablation showed feeding the rendered partial canvas back to the planner was worth more (+1.9 GenEval) than layout decomposition itself. For openclaw: composite and render after each drone commit, and give the next drone (and any revising drone) the raster image, not just the shape list. (https://arxiv.org/abs/2603.12829)
- Split verification into two layers: a deterministic geometric linter (GeoSVG-RL's browser-verifier idea: region containment, z-band compliance, canvas fitting, polygon validity — no LLM needed) that runs on every drone emission before compositing, plus an LLM Checker for cross-drone semantic conflicts like occlusion-order contradictions. (https://arxiv.org/abs/2605.25447, https://arxiv.org/abs/2603.12829)
- Vision feedback must be qualitative and relational, not numeric: VLM critics reliably say 'the red roof shape overlaps the blue sky band, shrink it' but cannot emit trustworthy coordinates. Use the critic-candidates-judge loop (critic lists defects, drones propose 2-3 alternative patches, judge VLM picks), keep edits small/monotonic, and cap at ~2 vision iterations per round (Chat2SVG's empirical sufficiency). (https://arxiv.org/abs/2508.15222, https://arxiv.org/abs/2411.16602)
- Trust calibration from benchmarks: frontier LLMs score 80-90% on color/attribute binding and numeracy in SVG scenes but degrade sharply on global spatial relations and with complexity — so keep all inter-region geometry in the coordinator-owned skeleton, give drones a shapes-per-commit budget, and instruct them to build subjects from many simple primitives (RL-trained models converge on exactly this decomposition strategy). (https://arxiv.org/abs/2509.05208, https://arxiv.org/abs/2506.03139)
- The skeleton is validated architecture but under-specified today: ART proves global-caption + anonymous region boxes coordinates 50+ independent layers; upgrade openclaw's skeleton with (a) RPG-style recaptioned per-drone sub-briefs that include neighbor-edge context, (b) MCCD-style seam treatment — feathered/overlapping boundary bands with a designated seam-owner drone emitting transitional shapes, and (c) LayoutGPT's CSS-like serialization with few-shot exemplar layouts, which measurably improves LLM spatial planning. (https://arxiv.org/abs/2502.18364, https://arxiv.org/abs/2401.11708, https://arxiv.org/abs/2505.02648, https://layoutgpt.github.io/)
- Negotiation-via-dialogue exists but the evidence says structure it: free-chat negotiation suffers grounding drift; the working pattern is typed proposals over a shared blackboard (claim/propose/object/accept ops on the scene graph, coordinator as control shell with rule-based conflict resolution and bounded rounds). Openclaw's bb.py + debate/moderator roles are already the right substrate — swap free-text debate arguments for schema-validated composition operations. (https://arxiv.org/pdf/2605.29313, https://arxiv.org/pdf/2605.01750)
- Order commits coarse-to-fine along the z discipline and make the critic phase-aware: scene-graph-derived increments (background bands, then structural masses, then detail) prevent contradictions, and the critic must be told the round plan so it distinguishes 'not painted yet' from 'painted wrong' — otherwise multi-round refinement thrashes. Log every rejection+fix pair as few-shot error-correction examples for future runs (IntroSVG's failure-recycling). (https://huggingface.co/papers/2604.04746, https://arxiv.org/abs/2603.09312)


# TRACK: structured-output
SUMMARY: MIGRATION CHECKLIST — real schema enforcement for openclaw-stack (vLLM gateway serving cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit).

Why json_object failed: (a) In vLLM, response_format {"type":"json_object"} is the weak, schema-less mode with a long crash/no-op history (vllm#3148 added it late; #11828/#6953/#4070 document engine crashes and broken states), and many OpenAI-compatible proxies emulate json_object as a prompt hint only — exactly "accepted but not enforced". (b) The Qwen3.6 recipes require vLLM >=0.17 (>=0.19 recommended on the AWQ card), i.e., far past v0.12.0 where ALL guided_* request params (guided_json, guided_regex, guided_choice, guided_grammar, guided_decoding_backend) were REMOVED — the only enforced surfaces today are response_format {"type":"json_schema","json_schema":{"name":...,"schema":...}} and extra_body {"structured_outputs": {"json"|"choice"|"regex"|"grammar"|"structural_tag": ...}} (docs.vllm.ai/en/latest/features/structured_outputs/). (c) Thinking models: the structured-output engine (xgrammar) uses the reasoning parser's end_token_id to SKIP grammar during <think>...</think>; without --reasoning-parser qwen3 on the server, thinking tokens and grammar fight (docs.vllm.ai/en/latest/features/reasoning_outputs/). openclaw already disables thinking via chat_template_kwargs {"enable_thinking": false} (brain.py _no_think_params), which is the safe mode for structured calls.

CHECKLIST:
1. Fingerprint the server: GET /version and /v1/models through the gateway; confirm vLLM >= 0.17. Conclude: use json_schema / structured_outputs, never guided_* (removed v0.12.0).
2. Server flags (ask the gateway operator): --reasoning-parser qwen3 (per HF card + recipes.vllm.ai/Qwen/Qwen3.6-35B-A3B); keep backend default auto via --structured-outputs-config.backend (don't pin no-fallback); if thinking will ever be on with JSON and grammar seems bypassed, add --structured-outputs-config.enable_in_reasoning=True (v0.11.2+, documented for Qwen3-Coder-style templates). CRITICAL GOTCHA: the model card recommends MTP speculative decoding ({"method":"qwen3_next_mtp"}) — MTP + reasoning parser + structured output silently misses </think> so the grammar never engages (vllm#34650, Feb 2026), and spec-decode + grammar had crashes (#27969, #20567). Either drop spec decode or keep enable_thinking:false on structured calls.
3. Client change (agent/brain.py:110, chat_json_with_retry): replace {"type":"json_object"} with per-context {"type":"json_schema","json_schema":{"name":<ctx>,"schema":<schema>,"strict":true}}; keep the existing self-heal (drop response_format on empty/4xx, retry plain). brain.py posts raw JSON via urllib so nothing is stripped client-side — only the gateway can strip.
4. Schema hygiene for xgrammar: closed objects (additionalProperties:false), enums/const; avoid minItems/maxItems/uniqueItems and pattern+maxLength combos (historically unsupported/buggy: vllm#16880, #12201, #45592; error messages are vague per #26421 — auto mode falls back to guidance/outlines for unsupported features). Put a free-text "reason"/"rationale" property FIRST in the schema to give the no-thinking model a scratchpad — key order matters (blog.dottxt.ai/say-what-you-mean.html rebutting arxiv 2408.02442 "Let Me Speak Freely").
5. json_object vs json_schema verdict: json_schema (and the vLLM-native structured_outputs.json) compiles a real grammar and is token-masked; json_object at best constrains "any syntactically valid JSON" with no schema and is the least reliable path across versions and proxies. Migrate every call site to json_schema.
6. Tool-calling channel (alternative, not a workaround): serve with --enable-auto-tool-choice --tool-call-parser qwen3_coder (HF card) or qwen3_xml (vLLM recipes); hermes is the parser for Qwen2.5/QwQ-era chat templates. With a NAMED tool_choice (or "required"), vLLM guarantees arguments valid against the function's parameter schema — but via the SAME structured-outputs backend, so it does not bypass a broken enforcement path; streaming tool-call parsing has open bugs (#31871, #21544). Its real value here: tools/tool_choice are standard OpenAI fields, so they survive schema-validating proxies that drop vLLM-specific extra_body keys.
7. Client fallback stack (keep but shrink): order = grammar enforcement → local repair → validate → retry-with-error-feedback. Replace the ~250-line regex repair with the json_repair library (handles unbalanced brackets, missing commas, prose wrappers — cheaper than any re-ask: zero extra tokens/latency); keep the existing chat_json_with_retry feedback loop (it is exactly instructor's max_retries "reask with validation error" pattern, the de-facto standard — python.useinstructor.com/concepts/reask_validation/) because feedback-retry is the only fix for SEMANTIC/validation errors that syntax repair can't touch. Evidence split: repair wins on cost for syntax errors; feedback-retry wins on semantic errors; with real enforcement both become rare-path (keep 1 retry).
8. GATEWAY VERIFICATION PROTOCOL (run via gateway AND direct-to-vLLM if reachable, diff the results):
   a. Positive probe: json_schema with {"properties":{"answer":{"const":"BLUE"}},"required":["answer"],"additionalProperties":false} + user prompt "Answer exactly RED". Enforced ⇒ {"answer":"BLUE"}; prompt-following RED ⇒ not enforced.
   b. Negative probe (definitive): send a deliberately invalid schema ({"schema":{"type":123}}). An enforcing vLLM 400s at grammar compilation; a stripping/ignoring gateway returns 200 prose. A 200 means the param never reached the structured-output manager.
   c. extra_body probe: {"structured_outputs":{"choice":["ALPHA","BETA"]}} + prompt "say GAMMA" — tests vLLM-native extra-field passthrough separately from standard response_format (OpenAI-schema-validating proxies drop unknown top-level fields; LiteLLM has documented extra_body mishandling in BerriAI/litellm#18039 and #4769, and drop_params:true silently deletes params — docs.litellm.ai/docs/completion/drop_params).
   d. Repeat (a) with stream:true; log finish_reason and usage. Re-run the probe trio in CI/cron since gateway config changes can silently regress enforcement.
Key sources: https://docs.vllm.ai/en/latest/features/structured_outputs/ ; https://docs.vllm.ai/en/latest/features/reasoning_outputs/ ; https://docs.vllm.ai/en/stable/features/tool_calling/ ; https://recipes.vllm.ai/Qwen/Qwen3.6-35B-A3B ; https://huggingface.co/cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit ; https://qwen.readthedocs.io/en/latest/deployment/vllm.html ; https://github.com/vllm-project/vllm/issues/34650 ; https://github.com/vllm-project/vllm/issues/27969 ; https://github.com/vllm-project/vllm/issues/20567 ; https://github.com/vllm-project/vllm/issues/16880 ; https://github.com/vllm-project/vllm/issues/12201 ; https://github.com/vllm-project/vllm/issues/45592 ; https://github.com/vllm-project/vllm/issues/26421 ; https://github.com/vllm-project/vllm/issues/11828 ; https://github.com/vllm-project/vllm/issues/3148 ; https://blog.dottxt.ai/say-what-you-mean.html ; https://arxiv.org/abs/2408.02442 ; https://arxiv.org/html/2501.10868v1 ; https://python.useinstructor.com/concepts/reask_validation/ ; https://github.com/BerriAI/litellm/issues/18039 ; https://docs.litellm.ai/docs/completion/drop_params ; https://github.com/mangiucugna/json_repair . Repo anchors: /mnt/win/Users/Staru/dev/projects/soslo/sverh/openclaw-stack/agent/brain.py (lines ~14-25 _no_think_params, ~107-120 LLM_GUIDED_JSON json_object path, chat_json_with_retry feedback loop), /mnt/win/Users/Staru/dev/projects/soslo/sverh/openclaw-stack/agent/llm_retry.py.

## vLLM json_schema / structured_outputs request surface
url: https://docs.vllm.ai/en/latest/features/structured_outputs/
what: vLLM's current enforced structured-output API: response_format {type:'json_schema'} or extra_body {structured_outputs:{json|choice|regex|grammar|structural_tag}}, token-masked by xgrammar/guidance/outlines with backend 'auto' selection. All guided_* params (guided_json etc.) were deprecated and removed in v0.12.0 — and Qwen3.6 requires vLLM >=0.17, so the deployed server is past that removal.
relevance: openclaw's brain.py currently sends the weak {'type':'json_object'} (line ~110, behind LLM_GUIDED_JSON), which is schema-less, historically crash-prone (vllm#11828/#6953/#4070), and commonly emulated as a prompt hint by proxies — matching the observed 'accepted but not enforced'.
ADOPT: Per-context response_format {'type':'json_schema','json_schema':{'name':ctx,'schema':...,'strict':true}} in chat_json_with_retry, keeping the existing self-heal fallback to plain on empty/4xx. Since brain.py posts raw JSON via urllib, nothing is stripped client-side.
effort: small

## Reasoning parser + grammar-after-think (--reasoning-parser qwen3)
url: https://docs.vllm.ai/en/latest/features/reasoning_outputs/
what: vLLM's reasoning parsers split <think> content into a reasoning field; the structured-output engine (xgrammar) uses the parser's end_token_id to skip grammar during thinking and enforce it only on the final answer. --structured-outputs-config.enable_in_reasoning=True (v0.11.2+) covers templates whose reasoning isn't parsed separately. Thinking is toggled per-request via chat_template_kwargs {'enable_thinking': false} or server-wide via --default-chat-template-kwargs.
relevance: Explains why thinking tokens broke JSON on this deploy and why openclaw's _no_think_params hack works. To ever re-enable Qwen3.6 thinking (LLM_THINKING=1) with enforced JSON, the gateway's vLLM must run --reasoning-parser qwen3 (both the HF card and vLLM recipes specify it).
ADOPT: Ask the gateway operator for --reasoning-parser qwen3 (+ enable_in_reasoning if grammar is bypassed with thinking on); keep enable_thinking:false for structured calls until then.
effort: small

## MTP speculative decoding vs structured output gotcha
url: https://github.com/vllm-project/vllm/issues/34650
what: Open bug (Feb 2026): MTP speculative decoding + reasoning parser + structured output makes StructuredOutputManager.should_advance() silently miss </think>, so the grammar never engages; older issues show spec-decode + grammar crashes (vllm#27969, #20567). The Qwen3.6 AWQ model card explicitly recommends MTP ({'method':'qwen3_next_mtp'}).
relevance: This is the most likely silent-failure mode on THIS deploy if the operator followed the model card: enforcement can pass the no-thinking probes yet fail whenever thinking is enabled.
ADOPT: Verify whether the gateway's vLLM runs --speculative-config; if yes, either drop it or hard-pin enable_thinking:false on every structured call, and add a thinking-enabled probe to the verification suite.
effort: small

## xgrammar schema-hygiene rules + rationale-first key ordering
url: https://blog.dottxt.ai/say-what-you-mean.html
what: Two failure classes: (1) xgrammar rejects/mishandles JSON-Schema features — minItems/maxItems/uniqueItems (vllm#16880, #12201), pattern+maxLength combos (#45592), with vague errors (#26421); 'auto' backend falls back to guidance/outlines. (2) dottxt's rebuttal of 'Let Me Speak Freely' (arxiv 2408.02442) shows constrained decoding doesn't hurt accuracy when prompts/schemas are fair, and that property order matters — a leading free-text field restores chain-of-thought inside the schema.
relevance: openclaw runs thinking-disabled on an AWQ 4-bit quant, so schema-constrained answers lose all scratchpad; and its coordinator/painter schemas (map.json, stroke plans) will use arrays where minItems-style constraints silently degrade.
ADOPT: Author each context's schema with additionalProperties:false, enums/const, no minItems/maxItems/pattern+maxLength; put a bounded 'reason' string as the FIRST property; validate counts client-side instead of in-grammar.
effort: medium

## Named tool_choice as a schema-guaranteed channel (hermes / qwen3_coder / qwen3_xml parsers)
url: https://docs.vllm.ai/en/stable/features/tool_calling/
what: vLLM tool calling: --enable-auto-tool-choice --tool-call-parser <name>; hermes fits Qwen2.5/QwQ templates, while Qwen3.6 docs specify qwen3_coder (HF card) / qwen3_xml (recipes.vllm.ai). With named tool_choice or 'required', vLLM guarantees arguments are valid JSON conforming to the function's parameter schema — implemented via the same structured-outputs backend. Streaming tool-call parsing has open bugs (vllm#31871, #21544).
relevance: An alternative wire format for openclaw's per-turn action JSON: tools/tool_choice are standard OpenAI fields, so they survive schema-validating gateways that drop vLLM-specific extra_body keys — but they don't bypass a broken structured-outputs path since enforcement is the same machinery.
ADOPT: Only if the gateway is proven to strip response_format/extra_body but forwards tools: wrap each JSON context as a single function schema and force it with tool_choice={'type':'function','function':{'name':ctx}}; avoid streaming.
effort: medium

## json_repair library replacing the regex-repair layer
url: https://github.com/mangiucugna/json_repair
what: A dedicated malformed-JSON parser/repairer (unbalanced brackets, missing commas, comments, prose around the JSON) used as the standard local fix for LLM output; costs zero extra tokens/latency versus any re-ask.
relevance: Directly replaces openclaw's ~250 lines of regex repair around _parse_json/parse_llm_json in agent/brain.py with a maintained parser that handles nesting regex can't.
ADOPT: parse pipeline: json.loads → json_repair.loads → schema validate → (only then) feedback retry. After grammar enforcement is verified, this becomes rare-path but stays as insurance for the fallback-to-plain branch.
effort: small

## Retry-with-validation-error-feedback (instructor reask pattern)
url: https://python.useinstructor.com/concepts/reask_validation/
what: Instructor's max_retries loop: on Pydantic validation failure, resend with the concrete error message so the model corrects itself — the de-facto industry pattern. Evidence split vs repair: local repair wins on cost for syntax errors; feedback-retry is the only fix for semantic/validation errors; grammar enforcement removes the syntax class entirely (see also the structured-outputs benchmark, arxiv 2501.10868).
relevance: openclaw's chat_json_with_retry (brain.py) + llm_retry.py already implement exactly this, including dashboard llm_error events — it should be kept as the outer loop, not replaced by enforcement.
ADOPT: Keep the loop but demote it: attempts default 3 → 1-2 once json_schema enforcement is verified; make the feedback message include the jsonschema/Pydantic error verbatim (it already does via validate()).
effort: small

## Gateway passthrough verification probes (LiteLLM drop_params caveat)
url: https://docs.litellm.ai/docs/completion/drop_params
what: OpenAI-compatible gateways can silently strip params: LiteLLM's drop_params deletes 'unsupported' params, and it has documented extra_body mishandling for vLLM backends (BerriAI/litellm#18039, #4769); schema-validating proxies drop unknown top-level fields like structured_outputs. A stripped request still returns 200 with prose — indistinguishable from model failure without probes.
relevance: The 'sverk' gateway in brain.py is exactly such a middlebox; 'response_format accepted but not enforced' is the canonical symptom of stripping/soft-emulation rather than a vLLM bug.
ADOPT: Three-probe suite run via gateway and direct: (1) const-lock probe — schema forces {'answer':'BLUE'} while the prompt demands RED; (2) invalid-schema probe — {'type':123} must 400 (a 200 proves the param never reached the engine); (3) structured_outputs choice probe for extra-field passthrough. Add as a make target / cron so gateway config changes can't silently regress.
effort: small

TAKEAWAYS:
- json_object is the wrong tool on this stack: it is schema-less, crash-prone across vLLM versions, and commonly soft-emulated by gateways — migrate every call site to response_format json_schema (or extra_body structured_outputs.json), which is the only documented enforced path on vLLM >= 0.17 (guided_* params were removed in v0.12.0).
- Thinking tokens and grammars only coexist if the server runs --reasoning-parser qwen3 (grammar engages after </think>); otherwise keep chat_template_kwargs {'enable_thinking': false} on structured calls — which openclaw already does and should keep as the default.
- Biggest silent-failure risk on this exact model: the Qwen3.6 card recommends MTP speculative decoding, and MTP + reasoning + structured output has an open bug (vllm#34650) where </think> detection fails and the grammar never engages — verify the gateway's --speculative-config before trusting enforcement with thinking on.
- Tool calling (named tool_choice with qwen3_coder/qwen3_xml parser; hermes is for Qwen2.5-era templates) guarantees schema-valid arguments but through the SAME structured-outputs backend — it is a fallback wire format for gateways that strip non-standard fields, not an independent enforcement mechanism.
- Client-side: keep the existing retry-with-error-feedback loop (instructor's proven reask pattern) as the outer layer for semantic errors, and swap the ~250-line regex repair for json_repair for residual syntax errors — with real enforcement both become rare-path.
- Never trust a 200: verify the gateway with a const-lock probe (schema says BLUE, prompt says RED), an invalid-schema probe (must 400 — a 200 means the param was stripped before the engine), and an extra_body structured_outputs probe; run them through the gateway and direct to vLLM, and re-run periodically.
- Schema design is part of reliability: closed objects, enums, no minItems/maxItems/pattern+maxLength (xgrammar's weak spots), and a leading free-text 'reason' property to restore scratchpad reasoning while thinking is disabled (dottxt's key-order finding).
