# Handoff: vLLM gateway upgrade + LLM-layer overhaul

For the agent doing the gateway upgrade. Everything below was measured live on
2026-07-02 against the production endpoint; nothing is speculation. Read
`docs/audit-2026-07/IMPLEMENTED.md` for the wider context of what already
changed in the client code.

## 1. What you are upgrading

- **Endpoint:** `https://ai.sverk.tech/v1` (OpenAI-compatible), key in `.env`
  (`SVERK_API_KEY`). Requests go through a **litellm proxy** in front of
  **vLLM 0.21.0** (`system_fingerprint: "vllm-0.21.0-tp2-…"`, tensor-parallel 2).
- **Model:** `qwen35` = `cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit` — a Qwen3-family
  **reasoning** model, AWQ 4-bit. It "thinks out loud" unless
  `enable_thinking:false` + `chat_template_kwargs:{enable_thinking:false}` are
  sent (the client sends both on every structured call — `brain._no_think_params`).
  Without them the model burns the whole budget on English chain-of-thought and
  never reaches the JSON (`finish=length`, 90 s timeouts). Do not lose this
  behavior in the upgrade.

## 2. Measured state of structured output (2026-07-02)

| Capability | Status | Evidence |
|---|---|---|
| `response_format: {type: json_schema}` | **ENFORCED** (real grammar) | const-lock probe: schema forced `enum:["BLUE"]`, prompt begged RED → got BLUE |
| invalid schema | **400** (param not stripped) | `"type":"objecttt"` → litellm/vLLM "Grammar error" |
| `response_format: {type: json_object}` | schema-less, soft | why the old `LLM_GUIDED_JSON` looked "marginal" |
| vLLM-native `guided_choice` | **STRIPPED by litellm** | probe begged "pizza", choices were борщ/окрошка → model said "Pizza!" |
| json_schema on SMALL outputs (≤ ~1500 tok) | fine | studio chat turns 9–23 s, enum-locked votes 18–31 s, scout chat clean |
| json_schema on LARGE outputs (compose, 6000 max_tokens) | **STALLS** | 3/4 concurrent schema-guided `collab_compose` calls hit the 120 s timeout; their PLAIN retries answered in 27–39 s. Matches the vLLM MTP/spec-decode + reasoning + grammar bug class (vllm#34650) |

Because of the last row, the client currently ships with **schemas on small
calls only**; `collab_compose` (and curated compose) run plain + regex-repair.
The disabled spot is marked with a comment in
`agent/roles/collab_paint.py::_compose_drone_shapes`.

## 3. Goals of the upgrade (in value order)

1. **Fix the grammar stall on long outputs.** Upgrade vLLM past the
   MTP+grammar interaction (check the fix status of vllm#34650 and the
   xgrammar version), or disable speculative decoding for grammar-guided
   requests. Success = a schema-guided 6000-token compose call is within ~1.5×
   of its plain-decoding latency under 4 concurrent requests (that is the real
   shape of the EXECUTE phase).
2. **Reasoning parser.** If the server gains `--reasoning-parser qwen3`,
   thinking can stay ON for structured calls (reasoning goes to
   `reasoning_content`, grammar applies to `content`). Today the client forces
   thinking off for every JSON call; with a parser you can re-enable richer
   reasoning without losing enforcement. Optional but valuable.
3. **litellm passthrough.** Either allow vLLM-native params (`guided_choice`,
   `guided_regex`) through the proxy, or accept that ballots stay
   `json_schema`+`enum` (they work; this is cosmetic).
4. **Bigger context / newer weights** if planned — nothing in the client
   assumes 32k beyond `LLM_CONTEXT_TOKENS` in `.env`.

## 4. Verification protocol (run BEFORE flipping any client flag)

All four probes, against the upgraded endpoint (curl bodies are in
`docs/audit-2026-07/IMPLEMENTED.md` §Gateway probes; source `.env` for the key):

1. **Const-lock:** json_schema forcing `enum:["BLUE"]`, prompt begs RED.
   Expect BLUE. A RED answer = schema silently stripped → stop.
2. **Invalid schema:** must 400. A 200 = the proxy eats the param → stop.
3. **guided_choice:** optional; if it now passes, note it, but the client
   doesn't depend on it.
4. **Large-output timing (the important one):** the exact `collab_compose`
   shape — ~6000 max_tokens, the schema from
   `collab_paint._compose_drone_shapes` (the one in the removed-schema comment),
   4 concurrent requests. Compare schema vs plain wall-clock. Under ~1.5× →
   proceed.

Then live flows on the real brain (each ~2–5 min):

```bash
make local-studio    # flagship; chat → vote → collab paint
make local-debate    # moderator + 3 debaters, options ballot
make local           # city of drones: scouts negotiate sectors by chat
python3 scripts/render_canvas.py   # eyeball the studio canvas PNG
```

Check `blackboard/runs/<id>/llm.jsonl` for `"kind":"parse"` records —
`parsed_ok:false` count should be 0, transport errors 0.

## 5. Client flips after a good upgrade (the overhaul)

Small, ordered, each independently revertable:

1. **Re-enable schema on the big compose calls** — in
   `collab_paint._compose_drone_shapes` pass `schema=` to `llm_json` again
   (the old schema literal is preserved in the comment); do the same for
   `coordinator_paint`'s curated compose if the timing probe holds there too
   (its output is even larger: `LLM_OUTPUT_CURATED`, up to 12k tokens in .env).
2. **Retire the regex JSON-repair layer.** Once every JSON call carries a
   schema, `brain.parse_llm_json` / `_parse_json` / the retry "ОШИБКА ФОРМАТА"
   turn become dead weight (~250 lines). Delete gradually: first log how often
   the repair path actually fires (`llm.jsonl` parse records already tell you),
   then remove when it is provably zero for a week of runs. Keep
   `chat_json_with_retry`'s transport-retry half — network errors still happen.
3. **Re-enable thinking on structured calls** (only with goal 2 achieved):
   drop `_no_think_params` from schema-guided requests, read
   `reasoning_content` into the `thinking` fields the dashboards already show.
4. **Ballots** stay `json_schema`+`enum` regardless — enforced and portable.
5. Env kill switches stay: `LLM_JSON_SCHEMA=0` (all schemas off),
   `LLM_THINKING=1` (thinking back on), `LLM_GUIDED_JSON` (legacy json_object —
   delete this flag during the overhaul, it is superseded).

## 6. Traps seen on this exact deploy

- The stall (row 6 of the table) reproduces only under **concurrent** large
  grammar requests — a single warm probe can look fine. Test with 4 parallel.
- litellm silently strips unknown params (that's how guided_choice "worked"
  while doing nothing). After any proxy change, re-run probe 2 — a 200 on an
  invalid schema means enforcement is gone even if probe 1 happens to pass.
- The model replies in Russian prose with JSON embedded for the compose calls
  (painting prompts are Russian) — schema enforcement makes the envelope pure
  JSON, which is exactly why flip 1 unlocks flip 2.
- `api.openai.com` fallback: never send vLLM-only params there
  (`brain._chat_completions_msgs` already guards by base URL — keep that).

## 7. Related future work (not this upgrade, just don't design against it)

- **VLM for canvas-grounded painting** (audit research §8b): compositing the
  canvas after each drone commit and feeding the raster back needs a vision
  model on the gateway; text-only qwen35 can't do it. If the upgraded gateway
  ever hosts a VLM, `docs/audit-2026-07/research-full.md` has the adoption notes.
- **TODO(crypto): agent-to-agent payments** — design sketch lives in
  `agent/roles/scout_chat.py` (module docstring): wallet ids in souls/personas,
  OFFER/ACCEPT messages inside the existing CHAT protocol, settlement hook in
  the coordinator's REPORT phase. Blocked on choosing the payment rail; nothing
  in the LLM layer should assume its absence (it's just more message types).
