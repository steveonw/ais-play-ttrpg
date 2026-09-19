# Separate-agent layer validation

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
