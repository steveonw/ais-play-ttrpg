# Separate-agent layer validation

## Live test update

The grouped native-agent test was attempted and blocked at **29/100 turns** by
unsupported payment/inventory changes. It used 52 role calls and completed
11 rounds, with a median round duration of about 7.5 minutes. Manual packet relay,
memory selection and repetitive play remain significant limitations. Two
Chronicler reviews cover rounds 1–10; round 11 remains unreviewed. These results
do not establish native token cost, a completed 100-turn run or live dice coverage.
See [the full report](session-0003-live-test.md) and its saved evidence. The
preparation results below describe synthetic tests, not those live timings.

## Session 2.5 preparation

**52 automated tests pass: 28 existing tests and 24 grouped-runtime tests.**
No real campaign turn, native model call or paid API call was made during this
preparation. Session 0002 remains the latest completed adventure.

The new tests cover independent same-scene player requests, parallel transport,
serial acceptance, per-role journals, scoped recall, frozen dice, crash recovery,
duplicate replies, immediate review gates, periodic review/end scheduling,
ordinary group travel, deferred actions, bounded attempts, call reservation,
stale writers, the 100-character-turn limit, and source-preserving continuation.
A mocked API request verifies per-role effort and output limits. The native
operator must still select the specified model tiers when launching agents.

`python3 scripts/benchmark_rounds.py` completes five synthetic rounds and 15
character turns in **22 fixture role replies**, including opening and final
review. A one-round no-roll trial needs six replies rather than the legacy
session's 15. Each ordinary additional round needs four; checks, recalls,
corrections and secret gates add calls. These figures compare routing overhead,
not equivalent narrative output or measured model latency.

A disposable probe inherited the completed Session 0002 checkpoint and checked
all new packet types for one synthetic no-roll round. The source remained
byte-for-byte unchanged. Compact serialized request sizes were:

| Request | Characters |
| --- | ---: |
| Opening GM | 12,738 |
| Arlen | 7,397 |
| Elara | 7,993 |
| Torren | 7,983 |
| Combined GM result request | 13,916 |
| Final Chronicler | 12,701 |

These sizes include instructions, schema and profile. The probe uses fixture
declarations; real wording changes sizes. Optional history is omitted as needed
to meet player/GM budgets. The complete source and audience-filtered recall
remain available. On this workspace the five-round local fixture took about
0.6 seconds; that measures disk work and synthetic responses, **not live AI
latency**. No story-quality improvement or speedup has yet been demonstrated
with the new live agents. The next short trial must measure those separately.

Run the read-only campaign probe with
`python3 scripts/benchmark_rounds.py --checkpoint PATH_TO_COMPLETED_CHECKPOINT`.
Its temporary records are never published as campaign events. See the
[operating guide](session-2-5.md) for recovery and privacy limitations.

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
for every model/account. No live API call was made. None of these preparation tests advanced the real campaign.
