# Running this adventure with separate agents

Read `docs/session-0003-live-test.md` and `docs/session-2-5.md` before further play. Use `rounds.py`
for grouped play and its atomic checkpoint as authority. The user requested
three independent players, a stronger GM/NPC role, a middle-tier Chronicler,
and at most **100 total character turns per session**. The requested 100-turn
trial is paused at 29 turns: payment is unsupported. Preserve its pending
round-12 choices. Do not start play merely to test preparation.

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

The latest completed session is 0002 on `world-state`; its root checkpoint is
retained unchanged. Session 0003 (informally Session 2.5) is paused separately
with public records under `campaigns/tavern-zero/sessions/session-0003/`. Its
full compressed checkpoint was saved for the owner; automatic approval review
blocked public upload pending explicit approval of private agent records.
Obtain that saved archive before recovery; its README explains restoration.
The party has met Sella, worked until sunset
at the bridge, and requested Arlen's earned but unpaid two silver. Implement and
test a validated payment transaction before explicitly resuming those saved
choices under a documented new runtime version. Do not use `retry` to clear the
capability pause, restart from 0002, or mark 0003 completed. Preserve rumors as
rumors. Do not publish fixtures as history.
Campaign records, including fictional secrets, may be public by the owner's
instruction; credentials may never be committed. The CLI does not push.

For source changes, run `python3 -m unittest discover -s tests -v`.
`python3 scripts/benchmark_rounds.py` runs synthetic preparation only.
Current source and instructions belong on `main`; retain campaign records when
updating source on `world-state`. The legacy per-character runner is documented
in `docs/live-play.md`; do not mix its writes with grouped checkpoints.
