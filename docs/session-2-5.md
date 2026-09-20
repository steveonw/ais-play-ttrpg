# Session 2.5: before-play setup

Preparation is implemented. The next real adventure has **not** been played.
Session 0002 remains the latest completed campaign. The party is on the lane
outside the Crooked Lantern, with the bridge visible and Sella mentioned as a
possible contact. They have not reached the bridge or met Sella. Claims about
Dain remain unverified.

The next trial is five rounds, up to 15 completed character turns, with the
existing hard ceiling of 100 character turns per session. A round may resolve
fewer than three actions when a conversation needs an answer before the next
character chooses. Five rounds is therefore a ceiling, not a promise of 15 turns.

## Roles and model tiers

| Role | Native model | Effort | Job |
| --- | --- | --- | --- |
| Three independent players | `gpt-5.6-luna` | low | Each chooses one action and updates their own small journal |
| GM, including all NPCs | `gpt-6-astra` | medium | Narrates one combined result, establishes needed world details, requests checks |
| Chronicler | `gpt-5.6-terra` | medium | Reviews every five rounds and at the end; summarizes public events |

Profiles live in `config/round-models.json` and are copied into the checkpoint
and each request. These are proposed resource allocations, not a measured ranking
of story quality. The native operator must actually select the packet's model
and effort; writing a model name in a prompt does not select a model. If the
host cannot provide a configured tier, report that before substituting it.

## The ordinary round

1. Generate all three player packets together. They see the same world version,
   their own knowledge and journal, and recent public events.
2. Dispatch those independent player calls together. Apply replies serially;
   players do not see each other's fresh declarations before choosing.
3. Send all declarations to the GM. Ordinary questions and agreed travel resolve
   in one GM reply, including any new location. Do not spend turns on footsteps.
4. If uncertainty warrants dice, the GM submits only the checks. Software saves
   the difficulty, modifiers, rolls and outcomes before a GM follow-up narrates
   the result. No rerolls during recovery.
5. Save the accepted round and show one connected story passage. After round five
   (or an early finish), run one Chronicler review and summary.

The GM may resolve only the first declaration, or the first two, in actor order.
Deferred players receive fresh packets next round with the NPC's answer. Their
unresolved attempts do not count as completed turns. A rolled action cannot be
deferred. The GM must not invent agreement to group travel.

A no-roll round uses four role calls. Starting and ending a one-round trial uses
six; a five-round trial uses 22. Checks, recalls, corrections and immediate
reviews add calls. This is a call-count improvement; real elapsed-time
improvement still needs measurement in live play.

## Memory and world authority

| Record | Purpose |
| --- | --- |
| `checkpoint.json` | Single atomic authority: world, inboxes, dice, journals, accepted replies and audit |
| `views/player-01.json` etc. | Per-player memory projections; exclude other players' journals and unknown facts |
| `memory/player-01.json` etc. | Own short goal, notes and questions; updated with each declaration |
| `memory/gm.json` | GM's short notebook, updated with each result |
| `memory/shared-scene.json` | Current scene and recent public events |
| `sessions/<id>/transcript.md` | Complete table-facing transcript, updated after every accepted round |
| `sessions/<id>/reviews.json` | Periodic public summaries |
| `sessions/<id>/round-audit.json` | Full role packets, replies and errors for operator review |
| `sessions/<id>/round-metrics.json` | Call counts, request sizes, round and handoff timings |

These are generated files, not documents every agent edits concurrently. The
operator is the only writer. Notes and hypotheses do not create canon. Facts
retain their classifications, sources and knowledge grants. Established facts
cannot be overwritten by reusing their IDs.

Normal packets select recent/relevant facts and public history. When necessary,
older optional public history and facts are omitted to meet the packet budget;
complete records remain saved. A role can reply with
`{"kind":"recall","query":"topic or fact ID"}` as its payload. The dispatcher
filters by that role's knowledge **before** searching, then regenerates its
packet. Two recalls per role/task are allowed and consume calls. A guessed
secret ID cannot retrieve that secret for an unauthorized player. Journals
should preserve useful unresolved questions across these compact contexts.

Player packets are limited to 8,000 characters; GM packets to 16,000. Chronicler
packets have a 90,000-character ceiling to accommodate up to five rounds of
unabridged review evidence. Ordinary fixture review packets are much smaller.
Oversized mandatory evidence stops dispatch instead of silently dropping it.
Character counts are not token counts.

New secret facts and selective grants trigger an immediate Chronicler gate
before publication. Routine public events are reviewed after up to five rounds.
This trades earlier semantic checking for fewer calls: a contradiction might
already have appeared in the transcript when the periodic reviewer catches it.
A rejection pauses the run; it does not silently rewrite history. There is no
automatic conflict-repair command in this pilot. An operator must inspect the
record and agree an explicit correction before resuming with repaired state.
Do not use `retry` to bypass a review conflict.

Structured filtering and exact-text leak checks are enforced. They cannot prove
that free-form narration or a paraphrase never reveals a secret. Fresh native
agents also inherit host capabilities unless the host restricts them; the
no-tools instruction is cooperative isolation, not a security sandbox. The
owner permits public fictional archives; player agents must still receive only
their permitted packets. Do not give them the repository or unrestricted memory
CLI. The `--role` memory flag is a trusted operator interface, not authentication.

## Start the real trial only when asked

From a source checkout, retrieve the completed checkpoint into a separate file:

```bash
git fetch origin world-state
mkdir -p runs
git show origin/world-state:campaigns/tavern-zero/checkpoint.json > runs/session-0002-source.json
python3 rounds.py --campaign runs/session-0003 init \
  --from-checkpoint runs/session-0002-source.json \
  --session-id session-0003 --max-rounds 5 \
  --directive 'Explore beyond the tavern. Follow player choices; resolve ordinary agreed travel in one passage.'
```

Initialization preserves the completed source, character knowledge, next actor
and RNG state. It creates no story event. The opening GM packet re-establishes
the saved scene without forcing the party to return inside. The working trial
is named session 0003 on disk; “2.5” is the experiment's informal name.

### Native chat relay

```bash
python3 rounds.py --campaign runs/session-0003 requests --output-dir runs/packets
python3 rounds.py --campaign runs/session-0003 dispatch REQUEST_ID --output runs/dispatched.json
# Invoke the indicated agent with that exact dispatched packet.
python3 rounds.py --campaign runs/session-0003 reply runs/reply.json
python3 rounds.py --campaign runs/session-0003 status
```

`REQUEST_ID` and `runs/reply.json` are placeholders for the generated request and
agent output. `requests` returns one GM/Chronicler packet or up to three player
packets. Reserve each with `dispatch` **before** starting its agent so call usage
and elapsed handoff time are durable. Each dispatch needs a distinct output
filename when preparing a player batch.

The supervising assistant launches separate fresh agents with
`fork_turns="none"`, using the exact model/effort in each profile. Supply only the
packet, verbatim, and request only the contracted JSON response. Launch the
three player requests before waiting for results, then submit their replies
serially. Never let players choose the other's actions or share private notes.
Fresh contexts avoid inherited supervisor information; files provide durable
role memory. Do not reuse an agent across roles.

A recall is a complete reply, not permission to browse files. Submit it, obtain
the next packet, and dispatch that role again. Invalid output receives bounded
feedback; do not write the correction on the agent's behalf. After three
attempts a request pauses. `retry --feedback 'specific correction'` reopens only
an attempt-limit pause, while preserving the total call budget.

The Python program does not itself invoke native chat collaboration tools or
run unattended in the background. The supervising assistant must perform those
handoffs. Present the story after each accepted round and keep operational
updates short; do not narrate every routing step to the user.

### Optional API transport

`rounds.py run --batches N` can automate packet transmission, run simultaneous
player requests in a thread pool, and apply replies serially. It requires an
API key and `TTRPG_PLAYER_MODEL`, `TTRPG_GM_MODEL`, `TTRPG_CHRONICLER_MODEL` in the
environment. Each must be an API model available to the account that supports
the configured reasoning setting and structured outputs. Native collaboration
model names are not assumed to be API model IDs. The provider applies each
role's output limit and effort. Tests mock this transport; no live API account
or paid call has been exercised for this preparation.

## Stop, recover and measure

Use `finish` between rounds for an immediate final review. If a declaration has
already been accepted or dispatched, finish the current round first. The next
Chronicler review also serves as the final summary; there is no extra end call.
The hard 100-character-turn ceiling applies even to a partially filled round.

On restart, accepted replies and rolls are already in the checkpoint. Identical
replies are no-ops. A changed duplicate, wrong role or stale world version is
rejected. In-flight requests remain reserved until their reply arrives or the
operator explicitly uses `interrupt REQUEST_ID`; an interruption consumes an
attempt because a call may already have incurred cost. Reload after a write
error. `export` rebuilds derived documents after an export failure. Do not use
legacy `live.py` or `ttrpg.py` writes on a grouped checkpoint.

A review-conflict or call-budget pause requires operator investigation and is
not bypassed by `retry`. The default total budget is 240 calls; the five-round
ordinary fixture uses 22. The cap counts recalls and failed attempts too.

Measure request character counts, dispatch-to-reply milliseconds and total round
elapsed time. Handoff timing includes scheduling and relay work, not pure model
inference. If a reply was submitted without prior dispatch, its handoff time is
null rather than a made-up near-zero measurement. API token usage is retained
when supplied; unavailable native usage remains unknown.

The first live trial should assess: whether waiting feels shorter, whether
characters still make distinct choices, whether uncertain claims stay uncertain,
and whether agreed travel progresses beyond the tavern in one passage. A fixture
cannot answer those story-quality and live-speed questions.

## Reproduce preparation checks

```bash
python3 -m unittest discover -s tests -v
python3 scripts/benchmark_rounds.py
# Optional read-only source probe after retrieving the checkpoint above:
python3 scripts/benchmark_rounds.py --checkpoint runs/session-0002-source.json
```

Fixtures run in temporary directories and never become campaign history. See
[validation](validation.md) for what was tested and what remains unmeasured.
