# Separate-agent layer validation

## Recorded live session

Session 0002 exercised the full native relay in actual play outside the tavern:
15 fresh role invocations (7 GM, 3 player, 5 Chronicler), matching 15 accepted
runtime calls and audit entries. Each character completed one turn. All four
scene/result reviews and the final independent summary were accepted without
retries. The GM requested no dice checks for the ordinary questions and travel
proposal. The session ended at three turns with its 100-turn ceiling intact.
No live model API was used; native token usage was unavailable.

The full transcript and recovery snapshots are on `world-state` under
`campaigns/tavern-zero/sessions/session-0002/`. This was a short outside
encounter, not a 100-turn endurance run. The party has not yet reached the bridge.
Manual transfer of full packets made this relay slow; host tool restrictions
remain a cooperative boundary, as described in the live-play guide.

## Automated tests and initial smoke test

Run `python3 -m unittest discover -s tests -v` from the repository root.
The suite covers the original engine and the new dispatcher: character order,
turn caps, hidden-information filtering, forbidden targets, wrong-role replies,
Chronicler approval/veto, retry limits, duplicate replies, saved-request resume,
interrupted commits, call budgets and continuation without changing the source.
The provider tests inspect stateless/tool-free requests and simulate refusal,
incomplete output and transport errors without making paid calls.

A separate relay smoke test used three fresh native player agents, one each for
Arlen, Elara and Torren. Each supplied an accepted action; the fixture session
ended after exactly three turns and 15 role submissions. GM and Chronicler
responses came from deterministic test fixtures. This validates real player
handoffs, not a fully independent five-agent adventure. Fixture skill choices
and narration are test data, not campaign events. Player replies are saved in
`examples/relay-smoke-player-replies.json`; their request IDs belong only to
that smoke session and cannot be submitted to a new adventure.

The first two players received the generated packets; the third received an
equivalent manually assembled character packet. Production instructions now
require verbatim generated packets for every role. The automated full-flow
fixture tests exercise the exact generated packet for all roles and verify
that hidden entities, secret facts and other players' memories are absent.

The tests do not prove semantic correctness of every narration, resistance to
an agent deliberately using inherited host tools, or real API compatibility
for every model/account. No live API call was made. None of these tests advanced
the existing 24-turn campaign.
