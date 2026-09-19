# Runtime contract

## Scope

This implementation is a local CLI for supervised self-play, not an unattended
AI service. A supervising assistant authors the three players and GM. The
runtime handles randomness, typed validation, deterministic recording and
checkpointing. It needs Python 3.10 or later and only the standard library.
There are no API keys, paid calls or background jobs in the included demo.

The first-night fixture was recorded as play progressed. Review messages and
software dice results preceded the GM's final narration. Replaying it reproduces
the recorded adventure; it does not generate a new one.

## State machine

`NEED_SCENE -> READY -> AWAITING_REVIEW -> AWAITING_FINAL -> READY`

The GM may close a scene after resolution, returning to `NEED_SCENE`. At 100
completed actor turns the runtime enters `LIMIT_REACHED`. Only a summary/end
transition is then allowed. An early `end` is allowed between turns. Pending
actions must be resolved first. An ended session is immutable except exports.

## Input messages

Each input is `{"message_id": "unique-id", "payload": {...}}`. Commands define
the role; the runtime supplies the full protocol envelope and stores the request
context. This CLI is a trusted local authoring interface, not an authenticated
multi-user service. Do not expose it directly to untrusted remote agents.

| Command | Required payload |
| --- | --- |
| scene | narration, location, entities, facts, grants |
| action | character_id, speech, action, intent, target |
| review | roll, either null or the check object below |
| resolve | narration, outcome, entities, facts, grants, scene_finished |
| end | summary, source_fact_ids, next_hook |

A check contains `skill`, `difficulty`, `advantage`, `disadvantage`, `reason`.
The engine derives the modifier from the character sheet; no total or custom
modifier may be submitted. Roll 1d20 + modifier. Advantage chooses the higher
of two dice, disadvantage the lower; both cancel. A total >= difficulty is
SUCCESS. Otherwise FAILURE. No automatic natural 1/20 results. With no check,
the final outcome must be NO_ROLL. Difficulty is frozen before the roll.

Entities require `id`, `name`, `type`, `undefined_fields`. Types are LOCATION,
NPC, OBJECT or FACTION. Facts require `id`, `statement`, `classification`,
`source`, `entity_id`. Classifications are CANON, SECRET_CANON, RUMOR or
CHARACTER_BELIEF. Undefined topics remain in entities' `undefined_fields`;
they are not silently turned into facts. Grants require `character_id` and
`fact_id`. A grant is explicit even for observable canon.

Inspect `examples/first-night.jsonl` for complete input examples. Use a fresh ID
for every new message. Retrying the same ID and payload is a no-op; changing a
previously accepted payload under the same ID is rejected.

## Information and publication

All campaign files may be public on GitHub at the owner's request. Repository
privacy and fictional knowledge are separate. Player contexts include their
own character sheet, known facts and the common table transcript, never the
full world, another character's private memories, or pending private intents.
The GM author remains responsible for not revealing secrets in public prose.

This demo uses one model with shared context. Passing filter tests does not
prove that this model forgot secrets while playing a character. Real agent
isolation requires separate calls with filtered prompts and restricted tools.
All characters are together; split-party play is out of scope. The public
transcript excludes private grants; the public GitHub archive includes them.

## Persistence and recovery

`checkpoint.json` is the single atomic authority. It includes phase, pending
action and roll, actor order, world, characters, accepted message hashes,
software RNG state, full messages and transcript events. Each successful
transition replaces it atomically. One writer per campaign is required.
Reload with the same `--campaign` path; `status` tells you which phase is next.
Use the recorded Python RNG format on resume. A roll already saved is reused.

`export` rebuilds world JSON, entity index, timeline, character knowledge,
WORLD.md, debug transcript, table transcript and summary from the checkpoint.
These projections can lag if an export fails; regenerate them from the intact
checkpoint. Git commits are explicit scene/session batches, not per sentence.
The CLI never claims it pushed a commit and does not automatically authenticate
to GitHub. Standard authenticated Git or the connected GitHub tools publish it.

## Limits and next work

- No model API adapter or continuous background execution.
- No combat, HP modification, inventory mutation, spells, split parties or
  automatic next-session creation. These require additional contracts.
- A deterministic Chronicler copies approved records; it cannot detect every
  semantic contradiction. GM narration and summaries still need semantic review.
- Automatic model retries and budget enforcement belong in a future adapter.
  Current invalid inputs return an error without advancing the checkpoint.
- The 100-turn unit test exercises state transitions with fixtures. It is not
  evidence of a 100-turn independently generated multi-agent campaign.

The protocol PDF and setup guide are included as design references. Where they
describe future capabilities, this contract and the README identify the actual
implemented scope.
