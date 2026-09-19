# Running this adventure with separate agents

Read `docs/live-play.md` before starting a live session. Use `live.py` as the
dispatcher and `ttrpg.py` as the mechanical authority. The user has requested
separate agents and a maximum of **100 total character turns per session**.
Do not start another session merely because a previous one ended.

For chat relay play, the supervising assistant is the sole operator. Obtain the
next packet with `live.py request`. Spawn an agent with no inherited conversation
(`fork_turns="none"`) and provide only that packet, verbatim. Have it return the
required JSON without browsing, files, tools or direct agent messaging. Route
GM, Chronicler, Arlen, Elara and Torren independently. A fresh invocation for each
request is preferred: the packet is the role's durable memory. Never repurpose
one player as another player or as GM. Do not pass repository files, checkpoint,
full debug history, or the supervisor's conversation to a player. Fresh context
does not itself revoke tool access; use tool restrictions when the host supports
them. This cooperative relay is not a hostile-agent security sandbox.

Submit the reply unchanged with `live.py reply`; do not choose actions on a
player's behalf or invent dice. For invalid replies, obtain the packet again
and let the same role correct its response. Inspect a Chronicler conflict before
using `retry`, which sends the objection back to the GM. Never reroll to fix
narration. Stop at a pause requiring operator review, a natural stopping point,
or the session cap. Use `finish` then route the remaining summary request when
ending early. Report actual completed turns and outstanding pauses honestly.

The latest completed session is saved on `world-state`. Inspect the checkpoint's
session ID, then continue into a new directory/session ID; preserve earlier archives.
Sessions 0001 and 0002 are recorded. The next new session is 0003.
Do not publish fixture tests as campaign history. Campaign records, including
fictional secrets, may be public by the owner's instruction; credentials may
never be committed. Publish completed records explicitly through authenticated
Git or the connected GitHub tools. The CLI itself does not push.

For code changes, run `python3 -m unittest discover -s tests -v`. Current source
and instructions belong on `main`; retain campaign records when updating source
on `world-state`.
