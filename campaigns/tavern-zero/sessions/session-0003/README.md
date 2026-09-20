# Session 0003 — paused at 29 of 100 turns

This is the live Session 2.5 test, not a fixture. It is **blocked**, not ended.
The party is at the bridge at sunset. All three pending round-12 declarations
request Arlen's earned two silver. The current runtime cannot update inventories
or currency, so no GM resolution was invented.

- [Transcript through turn 29](transcript.md)
- [Test report and findings](test-report.md)
- [Measured role calls and timings](round-metrics.json)
- [Integrity checks and count reconciliation](verification.json)
- [Two approved reviews, covering rounds 1–10](reviews.json)
- [Operator interventions and transport errors](operator-notes.jsonl)
- [Full paused campaign archive](session-0003-paused.tar.gz)

The full archive is published with the owner's explicit approval, including
private agent and character records. The separate table-facing transcript,
metrics and report omit private intentions, journals and full agent packets.

The archive preserves the exact atomic checkpoint, full accepted role packets
and replies, error records, public/debug transcripts, world state, journals,
views and operator recovery notes. Its 24 files are compressed for transport;
the checkpoint is not abridged. Fictional private information is included by
the campaign owner's authorization. Round 11 remains unreviewed.

## Restore for inspection

From a checkout of `world-state`, verify the download and choose an empty
recovery directory:

```bash
mkdir -p /tmp/ais-ttrpg-recovery
(cd campaigns/tavern-zero/sessions/session-0003 && sha256sum -c SHA256SUMS)
tar -xzf campaigns/tavern-zero/sessions/session-0003/session-0003-paused.tar.gz \
  -C /tmp/ais-ttrpg-recovery
python3 rounds.py --campaign /tmp/ais-ttrpg-recovery/session-0003 status
```

Expected: 29 character turns, 11 rounds, 52 calls, phase `ADJUDICATE`, a
`capability_gap` pause, three saved declarations, and no outstanding inboxes.
The exact checkpoint SHA-256 is
`e86ff63c1c0649cc3e45d28dcb9af458b88432e709358d05f349a99587fe6ea3`.
`SHA256SUMS` covers the published files, including this README and the full archive.

Runtime source during this attempt was commit
`74e4a8cc4e60465ab07f38394fde170bf3d2755f`; only recorded table-direction
clarifications changed during play. The full session source checkpoint was
session 0002, whose SHA-256 remains
`6447cef9093bb8f0310f4b39ebafd16147e980c60467523457efb301450bc74b`.

## Resume only after implementing the missing operation

Keep the pending declarations and prior history. Implement and test a validated,
atomic currency transaction, document the new runtime version and explicit
checkpoint migration, and review any resulting state change. Do not clear the
pause with `retry`, pay through narration alone, invent a refusal, or start over
from the older checkpoint. No resume was performed as part of this test.

`campaigns/tavern-zero/checkpoint.json` remains the latest **completed** session
0002. Restore this archive for the latest unfinished story. The earlier
`snapshots/turn-0011-checkpoint.json` is an intermediate snapshot, not the current
paused state.
