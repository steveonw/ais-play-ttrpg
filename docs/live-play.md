# Live play with separate agents

The execution layer is ready for a supervised live session. One GM, three
players and one Chronicler receive different packets. They cooperate through
accepted game events, not direct access to one another's private context.
The first adventure remains at its 24-turn overnight pause; these changes do
not advance that story.

## Layers

| Layer | Responsibility |
| --- | --- |
| Player agents | Choose only their own speech, attempted action and private intent |
| GM agent | Establish scenes, request checks, narrate the saved result |
| Software engine | Enforce phases, actor order, modifiers, dice and the turn cap |
| Chronicler agent | Review GM scenes/results before publication; summarize the session |
| Dispatcher | Build role packets, validate replies, persist retries and route the next role |
| Operator | Run the relay, inspect pauses, decide when to finish and publish records |

Normal order: GM scene → Chronicler review → player intention → GM check
request → software dice → GM resolution → Chronicler review → next player.
The three players take turns; the shared state has only one writer. Separate
agents do not require simultaneous writes or simultaneous character turns.

## Prepare the next session

On `main`, fetch the saved checkpoint without switching away from current code:

```bash
git fetch origin main world-state
mkdir -p runs
git show origin/world-state:campaigns/tavern-zero/checkpoint.json > runs/session-0001-checkpoint.json
python3 live.py --campaign runs/session-0002 init \
  --from-checkpoint runs/session-0001-checkpoint.json \
  --session-id session-0002 --max-turns 100 --max-calls 600
```

Use a new destination. Continuation preserves world facts, character knowledge,
private memories, actor order and RNG state. It records the prior session's ID,
summary and checkpoint hash. The new session starts at zero completed turns,
awaiting a GM scene. The source checkpoint stays unchanged. The maximum is 100
character turns **total**, not 100 per character. A session can finish earlier.

For an unrelated test or new adventure, omit `--from-checkpoint` and use a
different directory and session ID. Do not reuse smoke-test records as canon.

## Chat relay: no API key needed

The supervising assistant uses the host's separate-agent facility. Python
creates and validates packets; it does not itself launch chat agents.

```bash
python3 live.py --campaign runs/session-0002 request --output runs/request.json
# Send only that JSON packet to a fresh agent for packet.agent_id.
# Save its exact JSON answer to runs/reply.json.
python3 live.py --campaign runs/session-0002 reply runs/reply.json
python3 live.py --campaign runs/session-0002 status
```

Repeat while the session is active. Spawn with no parent history; provide the
complete packet verbatim, including instructions, context and response schema.
The role returns JSON only. Use fresh role invocations rather than reusing a
GM conversation for a player. No extra planning summaries or full repository
contents should accompany a player's packet. `AGENTS.md` gives the operator's
instructions for the next chat.

Players see their own sheet, knowledge, visible entity IDs and recent public
events. They do not receive other character sheets, private intentions, hidden
entities or the prior GM summary. The GM receives authoritative world state.
The Chronicler receives the proposed result, existing records and saved check.
Role IDs, request IDs, actor IDs and permitted targets are validated locally.

Fresh contexts provide information separation, but native agents may still
inherit host tools. Instruct them not to use tools and disable file, browsing
and messaging access where supported. This relay is cooperative isolation,
not an operating-system sandbox. The GM and Chronicler must also prevent
secrets from leaking through public narration. All current characters remain
together; split-party audiences are not implemented.

## Pauses and recovery

```bash
python3 live.py --campaign runs/session-0002 status
python3 live.py --campaign runs/session-0002 request --output runs/request.json
```

The outstanding request survives restart. Resubmit the same accepted reply
without advancing twice. A changed reply under an accepted ID is rejected.
Pending dice are preserved; a narration correction cannot reroll them.
Accepted replies are saved before application so interrupted commits can be
recovered. Use the same Python RNG format when moving checkpoints across hosts.

A Chronicler rejection pauses play. Inspect its conflicts, then run `retry`
to send the proposal and objections back to the GM. Schema failures include
feedback in the next packet. After at most three attempts the dispatcher pauses;
`retry` explicitly starts another attempt allowance. The overall call budget
still applies. API attempts are reserved before transmission, including failed
or interrupted calls. Relay submissions consume attempts when submitted; an
abandoned external agent invocation is not counted by the Python relay.

```bash
python3 live.py --campaign runs/session-0002 retry
python3 live.py --campaign runs/session-0002 finish
```

`finish` requests an early end. Continue routing any outstanding request/current
turn and the Chronicler's summary until phase is `ENDED`. Reaching the character
turn cap also routes a summary instead of another player action. A call-budget
pause can occur before the turn cap or summary. `retry` does not increase that
budget; changing the saved limit requires an explicit operator decision.

CLI commands use a POSIX advisory lock. Do not call the core authoring commands
or edit campaign files while the live runner is active. The Python class is an
in-process interface; external callers must provide the same single-writer
discipline. An on-disk checkpoint mismatch rejects a stale reply.

## Optional API runner

The relay above is sufficient for the next chat. For separate API calls, locally
set `OPENAI_API_KEY` and a compatible model ID in each environment variable:

| Role | Model environment variable |
| --- | --- |
| GM | `TTRPG_GM_MODEL` |
| Chronicler | `TTRPG_CHRONICLER_MODEL` |
| Arlen | `TTRPG_ARLEN_MODEL` |
| Elara | `TTRPG_ELARA_MODEL` |
| Torren | `TTRPG_TORREN_MODEL` |

`config/live-models.json` maps roles to these variable names; it contains no
credentials. Roles may use the same model while still receiving separate
requests. Choose models available to your account that support Responses and
strict structured output. No model or price is assumed by this repository.

```bash
python3 live.py --campaign runs/session-0002 run --steps 1
# After inspecting the result, run up to 20 more role calls:
python3 live.py --campaign runs/session-0002 run --steps 20
```

Each call has only one role's packet, no tools, no shared conversation ID and
`store: false`. The adapter follows the official
[Responses structured-output format](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
Refusal, incomplete output, network failure and malformed JSON consume a bounded
attempt without advancing fiction. Defaults are 600 calls per session, three
attempts per request, 60-second HTTP timeout, 5,000 output tokens and 120,000
input characters. These are execution limits, not a dollar budget. Returned
token usage is recorded when available; failed calls may still incur charges.
This transport has mocked tests, but no real account/API run has been performed.

## Records and publication

`checkpoint.json` holds game authority; `live.json` holds the pending role
request, accepted replies, review proposals, attempts, usage and audit packets.
Keep both for recovery. Full live audit packets contain fictional secrets and
must never be loaded wholesale into a player agent. `status` is for the trusted
operator and may show a pending private intent.

Transcripts and world/character exports remain in the campaign directory.
`runs/` is ignored by Git to keep unfinished tests out of the story. At a real
session's end, preserve its complete directory in the campaign archive on
`world-state`, keeping earlier sessions intact. Publishing is a separate,
explicit Git operation. The runner is not a background service, and no new
session starts automatically.
