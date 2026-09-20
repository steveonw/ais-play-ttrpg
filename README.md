# AIS Play TTRPG

A tabletop adventure that grows through play. The GM establishes the world,
three player characters choose their intentions, software rolls the dice, and
the runtime records what happened.

**Two completed sessions and a blocked third test are recorded: 24 turns of
first-night self-play, three turns outside with separate agents, and 29 turns
of grouped play. The requested 100-turn test stopped on a payment capability gap.**
Session two uses separate GM, player and Chronicler invocations through the
live relay. The relay runs without API keys or third-party dependencies;
an optional API runner is also included. Neither runs in the background by itself.

**[100-turn live test — blocked at 29, findings and recovery](docs/session-0003-live-test.md)**

The grouped workflow uses three independent players, one GM/NPC response for
ordinary actions, private journals and a Chronicler review every five rounds.
The live test used 52 role calls for 29 completed turns, including two transport
corrections and three pending declarations. Median completed-round time was
about 7.5 minutes: manual context transfer remained slow. The party reached the
bridge and completed paid work, but inventory/payment updates are not implemented.
The paused checkpoint preserves their requests for payment. The earlier 22-call,
15-turn result was a preparation fixture. [Workflow](docs/session-2-5.md)
and [validation](docs/validation.md).

## Read the adventure

**[Session three — At the bridge, paused](https://github.com/steveonw/ais-play-ttrpg/blob/world-state/campaigns/tavern-zero/sessions/session-0003/transcript.md)**
· [Findings and checkpoint status](https://github.com/steveonw/ais-play-ttrpg/tree/world-state/campaigns/tavern-zero/sessions/session-0003)

Session three remains unfinished at sunset, before payment. Fix the recorded
capability gap before resuming its saved declarations; do not restart from the
older completed session or count the pending actions as completed turns.

**[Session two — Outside the Crooked Lantern](https://github.com/steveonw/ais-play-ttrpg/blob/world-state/campaigns/tavern-zero/sessions/session-0002/transcript.md)**
· [Summary](https://github.com/steveonw/ais-play-ttrpg/blob/world-state/campaigns/tavern-zero/sessions/session-0002/summary.md)

The three characters question a notice poster on the lane outside the tavern.
They learn of Sella, a possible contact at the bridge, while keeping claims
about Dain unverified. Each player acts through a separate fresh context; the
GM and Chronicler also run separately. The session pauses before the party
travels to the bridge. No dice checks were needed for the chosen actions.

**[The First Night — full transcript](https://github.com/steveonw/ais-play-ttrpg/blob/world-state/campaigns/tavern-zero/sessions/session-0001/transcript.md)**

[Session summary](https://github.com/steveonw/ais-play-ttrpg/blob/world-state/campaigns/tavern-zero/sessions/session-0001/summary.md)
· [Established world](https://github.com/steveonw/ais-play-ttrpg/blob/world-state/campaigns/tavern-zero/WORLD.md)
· [Results and dice](https://github.com/steveonw/ais-play-ttrpg/blob/world-state/campaigns/tavern-zero/sessions/session-0001/metrics.json)

Arlen Vale, a suspicious rogue; Elara Voss, an idealistic fighter; and Torren
Bright, a cautious wizard arrive at the Crooked Lantern. A bell rings below the
floor. Mara says nobody is down there. The rest emerges from their choices and
seven software-generated checks.

The first session finishes at a natural overnight pause. Four checks succeed
and three fail. The story keeps those failures and their consequences. Session
two continues the lead in daylight outside the tavern.

## Run locally

Use Python 3.10 or later. No installation step or API credential is required.

```bash
git clone https://github.com/steveonw/ais-play-ttrpg.git
cd ais-play-ttrpg
python3 -m unittest discover -s tests -v
python3 scripts/replay_session.py --output /tmp/tavern-zero-replay
python3 ttrpg.py --campaign /tmp/tavern-zero-replay status
```

Choose a new output directory each time. Replay reproduces the recorded session
from its accepted role messages and seeded software dice; it does not invent
a new adventure. The result should be `ENDED`, with 24 completed turns.

## Start a different adventure

```bash
python3 ttrpg.py --campaign /tmp/my-tavern init
python3 ttrpg.py --campaign /tmp/my-tavern context gm
python3 ttrpg.py --campaign /tmp/my-tavern scene opening.json
python3 ttrpg.py --campaign /tmp/my-tavern context player-01
python3 ttrpg.py --campaign /tmp/my-tavern action action.json
python3 ttrpg.py --campaign /tmp/my-tavern review review.json
# Read the software dice result before authoring the final resolution.
python3 ttrpg.py --campaign /tmp/my-tavern resolve resolution.json
```

The JSON files above are role inputs you supply, not pre-existing files.
See [the runtime contract](docs/runtime.md) and the complete recorded examples
in [first-night.jsonl](examples/first-night.jsonl). Actor order is Arlen, Elara,
Torren, then repeats. `maximum_turns` in [configuration](config/tavern-zero.json)
is the total number of character turns, not rounds or turns per character.
It may be lowered, but this version rejects values above 100.

## What is implemented

- A state machine with validated action, review, resolution and scene phases.
- Approved skill modifiers, seeded d20 checks and advantage/disadvantage.
- A deterministic recorder that copies GM-approved facts and grants.
- Periodic Chronicler reviews in grouped play, with immediate gates for secrets
  and selective grants; the legacy relay reviews every GM scene/result.
- Per-character knowledge, private intentions and filtered player requests.
- Full protocol envelopes in the debug history and a table-facing transcript.
- Atomic checkpoints with pending rolls, RNG state and idempotent message IDs.
- Rebuildable JSON/Markdown records and a reproducible first-session fixture.
- Grouped concurrent declarations, combined GM narration and per-role model profiles.
- Compact role journals, scoped recall, durable inboxes and handoff timing.
- Strict response schemas, bounded retries and a single atomic grouped checkpoint.
- A relay for chat agents and an optional stateless Responses API transport.
- Continuation from a completed checkpoint, preserving knowledge and dice state.
- Tests for routing, hidden information, recovery, provider errors and turn limits.

Combat, inventory/HP changes, split parties and automatic new sessions are not
implemented. Context-filter tests verify the runtime data boundary. Native chat
agents must receive fresh contexts and restricted access; prompts alone are not
a filesystem sandbox. The optional API transport has mocked tests but has not
been exercised against a live API account. See [validation](docs/validation.md).

## Repository layout

| Location | Contents |
| --- | --- |
| `main` branch | Runtime, tests, configuration, prompts, docs and replay inputs |
| `world-state` branch | Runtime snapshot, campaign archive and latest checkpoint |
| `campaigns/tavern-zero/checkpoint.json` | Latest completed checkpoint, session 0002; not the paused session 0003 |
| `campaigns/tavern-zero/state/` | World facts, entities and full event timeline |
| `campaigns/tavern-zero/characters/` | Individual knowledge records |
| `campaigns/tavern-zero/sessions/session-0001/` | Transcript, summary, metrics and full debug log |
| `campaigns/tavern-zero/sessions/session-0002/` | Separate-agent transcript, summary, metrics and recovery snapshots |
| `campaigns/tavern-zero/sessions/session-0003/` | Blocked live test: public transcript, report, metrics and recovery status; full archive awaits publication approval |

Campaign records, including fictional secrets, are public by the owner's choice.
Player agents must use filtered contexts instead of reading the whole repository.
Never put actual credentials in configuration, prompts, logs or checkpoints.

## Design references

- [Original protocol PDF](docs/protocol-v0.1.pdf)
- [Setup guide](docs/setup-guide.docx)
- [Implemented runtime contract](docs/runtime.md)
- [Session 2.5 grouped workflow](docs/session-2-5.md)
- [Legacy separate-agent workflow](docs/live-play.md)
- [Role prompts](prompts/roles.md)

The protocol and setup guide describe the wider design. The runtime contract
and live-play guide state the implementation's limits. Source and session commits are made
explicitly through authenticated Git; the CLI itself never claims to push data.
