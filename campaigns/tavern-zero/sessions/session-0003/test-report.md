# Session 0003: 100-turn test blocked at 29

The live Session 2.5 test stopped at **29 of 100 requested character turns**.
It reached a real implementation limit: after completing paid work, all three
players asked Sella to settle Arlen's two silver, but the runtime prohibits
inventory changes and has no payment transaction. The operator paused before
GM adjudication. No payment, refusal or delaying story was invented.

This is a blocked test, not a completed 100-turn session. Round 12's three
independent declarations are saved. The checkpoint remains `ADJUDICATE` with
`paused.kind = capability_gap`; it is not `ENDED`.

[Read the transcript](https://github.com/steveonw/ais-play-ttrpg/blob/world-state/campaigns/tavern-zero/sessions/session-0003/transcript.md)
or [inspect the public records and recovery status](https://github.com/steveonw/ais-play-ttrpg/tree/world-state/campaigns/tavern-zero/sessions/session-0003).

## Actual results

| Measure | Result |
| --- | --- |
| Completed character turns | 29 / 100 |
| Completed rounds | 11 |
| Pending declarations | 3, for round 12; no GM request dispatched |
| Native role calls | 52: 36 player, 13 GM, 3 Chronicler |
| Accepted replies | 50 |
| Extra calls for transport corrections | 2 |
| Calls through the last completed round | 49 |
| Approved Chronicler reviews | 2, covering rounds 1–10 |
| Completed but unreviewed rounds | Round 11 |
| Dice checks / recalls | 0 / 0 |
| Deferred declarations | 4, across two prefix-only rounds |
| Median completed round | 448.8 seconds, about 7.5 minutes |
| Longest completed round | 1,512.9 seconds, about 25.2 minutes |
| Total completed-round durations | About 100.5 minutes |
| Approximate first-packet-to-pause interval | 121.0 minutes |

The approximate overall interval uses the preserved first packet's file
timestamp, 2026-09-20 00:45:12 UTC, and the recorded pause at 02:46:14 UTC.
The runtime did not retain an explicit session-start timestamp. Round timings
exclude opening and between-round review gaps. Dispatch-to-reply timings include
packet copying, scheduling and submission; they are not pure model inference.

The observed count is 1.79 role calls per completed turn, including the three
pending declarations. The preparation fixture's 22 calls for 15 turns was a
synthetic, ordinary-action case, not a live-speed prediction. Supervisor
inference calls are excluded from these role counts; native tokens and monetary
cost were unavailable. This run does not establish a total-cost reduction.

## What happened in the adventure

The players independently agreed to travel from the tavern lane to the bridge,
and the GM moved them together in one passage. Sella showed a ledger entry for
someone named Dain doing sluice clearing. The characters investigated the entry
and her recollection; neither established that this worker was the Dain sought,
nor where he went.

The travelers accepted stone-sorting work. Much of the session repeated work
terms, Dain questions and sorting status. Eventually the GM advanced routine work
through sunset, after Arlen independently accepted the full-day terms. His two
silver were acknowledged as earned, not transferred. All three next actions
asked for that payment. Those actions remain unresolved at the bridge.

## What worked

- Independent player contexts and differing initial choices were preserved.
- Agreed travel moved the party outside and onward without separate footstep turns.
- Grouped resolution generally handled three declarations with one GM call.
- The saved source session remained unchanged. Earlier facts and knowledge were
  preserved, and uncertain claims about Dain stayed uncertain in the reviews.
- Atomic saves retained the pending choices and allowed an honest pause with no
  outstanding agent calls. No dice were required by these chosen actions.

## What failed or needs improvement

**The action contract was too narrow for ordinary play.** The GM could offer
paid work, but the engine could not complete its payment. Add validated currency
transactions before resuming this checkpoint. Payment, journal, public facts and
the accepted result must commit atomically, with duplicate submissions unable to
pay twice. Merely narrating coins while leaving the character sheet unchanged
would not fix this.

**Manual packet relay dominated the experience.** Players received roughly
7–8 thousand characters, the GM up to 16 thousand, and the two review packets
were roughly 33–36 thousand. A supervisor had to copy these into native agent
calls. Fewer role calls did not make this workflow suitable for quick live play.
Use a supported direct packet transport before another long test; the optional
API runner has not been exercised against a live account.

**Memory selection lost useful context.** Current-location ranking crowded
packets with successive work-status facts. Compact facts omitted their turn and
session provenance, leaving historical states without an explicit time label.
Arlen repeated a pay question when its terms were absent from his packet.
Torren also repeated a question despite its answer being in the latest scene:
both retrieval and player behavior contributed. Journals retained stale
questions. Chronicler summaries were archived but were not supplied to later
player or GM contexts, so the proposed shared memory refresh was incomplete.

**World and story progress were limited.** The party reached a new location and
made choices, but repeatedly sorting stones did not sustain exploration. This
test cannot isolate whether the smaller player model was sufficient: transport,
memory and pacing were substantial confounding factors. Combat, inventory
updates and live dice behavior were not successfully exercised.

## Interventions and test limits

This was an adaptive live test, not a frozen benchmark. Runtime source and model
tiers stayed unchanged: players `gpt-5.6-luna`/low, GM `gpt-6-astra`/medium,
Chronicler `gpt-5.6-terra`/medium. The operator made these recorded interventions:

1. After round 4, clarified that independent declarations should resolve in one
   batch; two prior rounds had unnecessarily deferred the other players.
2. Briefly split packet routing between two supervisors. Root then blocked its
   assigned player dispatch while publishing a snapshot, causing a recorded
   1,289.9-second coordination stall in round 7. All routing returned to one
   operator. That delay was not a player-model stall.
3. After round 8, clarified that routine work should advance meaningful time
   while respecting the players' chosen commitments.
4. Counted two extra native calls to correct operator copying errors: added
   words in one Chronicler fact and a duplicate entity in one GM packet. The
   initial replies were discarded; scoped corrective follow-ups reused those
   same role agents. Canonical accepted packets/replies and error notes are saved.
5. Paused before round 12 adjudication when the requested payment exposed the
   unsupported operation. There was no Chronicler veto and no hidden retcon.

Fresh role contexts and no-tools instructions provided cooperative separation,
not a security sandbox. Two approved reviews do not prove the entire session
conflict-free: round 11 has not received its periodic review.

## Verification and next step

Read-only checks verified contiguous turn ranges, accepted-reply hashes, call
accounting, unchanged source facts, preserved knowledge, unchanged HP/inventory
and RNG state, review coverage, three pending declarations, and empty inboxes.
The public records include machine-readable verification and SHA-256 checksums.
The full checkpoint archive was saved separately for the owner. Automatic
approval review rejected its public upload because it contains private agent
and character records and requested explicit approval for that disclosure.
The public transcript, metrics and this report exclude those private records.

Preserve this failed test as evidence. Obtain the owner's saved archive before
attempting recovery. Implement and test currency accounting,
then explicitly resume the paused session with its saved choices and document
the new runtime version. Before another speed comparison, connect summaries to
role memory, retain fact chronology and remove manual packet copying from the
critical path. Do not call `retry` to clear this capability pause or restart the
story from the older completed checkpoint.
