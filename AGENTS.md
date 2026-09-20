# Running this adventure with separate agents

Read `docs/session-2-5.md` before starting the next live session. Use `rounds.py`
for grouped play and its atomic checkpoint as authority. The user requested
three independent players, a stronger GM/NPC role, a middle-tier Chronicler,
and at most **100 total character turns per session**. The next trial defaults
to five rounds (up to 15 turns). Do not start play merely to test preparation.

The supervising assistant is the sole operator. Generate packets together with
`rounds.py requests`. Reserve each request using `dispatch` before invoking its
agent. Use `fork_turns="none"` and explicitly select the model and reasoning
effort from the packet's profile. These role-specific model tiers were requested
by the user. Supply only the exact generated packet and ask for contracted JSON,
with no browsing, file access, tools or direct messages between role agents.
Launch all ready player requests before waiting; apply replies serially.

A fresh invocation for each request is preferred: packets and private journals
are durable memory. Never repurpose one player as another or as GM. Do not pass
the repository, checkpoint, full audit or supervisor conversation to players.
Fresh context does not revoke host capabilities; restrict tools when supported.
This cooperative native relay is not a hostile-agent security sandbox.

Submit replies unchanged. Do not choose player actions, manufacture agreement,
or invent dice. The GM resolves ordinary actions in one combined passage. Dice
checks require committed difficulty, software rolls and a GM follow-up honoring
the saved outcome. The GM may resolve a prefix of declarations if later choices
need an NPC answer first. Deferred actions get fresh packets next round.
Ordinary agreed travel should move the party in one passage, not many footsteps.

The Chronicler reviews every five rounds and at the end, with immediate gates
for new secrets or selective grants. Stop on a review conflict; do not bypass
it or silently retcon public history. `retry` only reopens an attempt-limit
pause. Never reroll to fix narration. `finish` completes pending work and routes
one final review. Report actual completed turns and pauses honestly.

Present story after accepted rounds. Keep routing updates brief. Reserve calls
before dispatch to measure actual handoff time; unavailable native token usage
remains unknown. Do not claim fixture timings prove live speed or story quality.
The Python dispatcher does not launch native chat tools itself; the supervisor
must perform those handoffs. Optional API transport is separate and requires
configured API access. Do not substitute unavailable model tiers silently.

The latest completed session is on `world-state`. Inspect its session ID and
continue into a new directory/session ID, preserving earlier archives. Sessions
0001 and 0002 are recorded. The next real session is 0003 (informally Session
2.5). The party is outside the tavern; do not restart inside or claim they have
already met Sella. Preserve rumors as rumors. Do not publish fixtures as history.
Campaign records, including fictional secrets, may be public by the owner's
instruction; credentials may never be committed. The CLI does not push.

For source changes, run `python3 -m unittest discover -s tests -v`.
`python3 scripts/benchmark_rounds.py` runs synthetic preparation only.
Current source and instructions belong on `main`; retain campaign records when
updating source on `world-state`. The legacy per-character runner is documented
in `docs/live-play.md`; do not mix its writes with grouped checkpoints.
