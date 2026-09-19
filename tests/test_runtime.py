import copy
import json
from pathlib import Path
import tempfile
import unittest

from ttrpg import Campaign, ProtocolError

CONFIG = json.loads((Path(__file__).parents[1] / "config/tavern-zero.json").read_text())


def message(mid, payload):
    return {"message_id": mid, "payload": payload}


def scene():
    return {"narration": "Three travelers sit in a tavern.", "location": "crooked-lantern", "entities": [], "facts": [], "grants": []}


def action(cid="arlen-vale"):
    return {"character_id": cid, "speech": "Any work?", "action": "Ask for work.", "intent": "PRIVATE INTENTION", "target": "crooked-lantern"}


def result(outcome="NO_ROLL"):
    return {"narration": "The room is quiet.", "outcome": outcome, "entities": [], "facts": [], "grants": [], "scene_finished": False}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.c = Campaign.create(self.root, CONFIG)
        self.c.submit("scene", message("opening", scene()))

    def begin_check(self):
        self.c.submit("action", message("action-1", action()))
        return message("review-1", {"roll": {"skill": "INSIGHT", "difficulty": 13, "advantage": False, "disadvantage": False, "reason": "Read a reaction"}})

    def test_hidden_fact_and_private_intent_not_in_other_player_context(self):
        self.c.submit("action", message("action-1", action()))
        self.c.submit("review", message("review-1", {"roll": None}))
        final = result()
        final["facts"] = [{"id": "hidden", "statement": "HIDDEN CLUE", "classification": "SECRET_CANON", "source": "gm", "entity_id": "crooked-lantern"}]
        final["grants"] = [{"character_id": "arlen-vale", "fact_id": "hidden"}]
        self.c.submit("resolve", message("final-1", final))
        self.assertIn("HIDDEN CLUE", json.dumps(self.c.context("player-01")))
        self.assertNotIn("HIDDEN CLUE", json.dumps(self.c.context("player-02")))
        self.assertNotIn("PRIVATE INTENTION", json.dumps(self.c.context("player-02")))
        transcript = next(self.root.glob("sessions/*/transcript.md")).read_text()
        self.assertNotIn("HIDDEN CLUE", transcript)
        self.assertNotIn("PRIVATE INTENTION", transcript)

    def test_player_cannot_create_facts_or_change_hp(self):
        before = self.c.path.read_bytes()
        for field in ["new_world_facts", "hp"]:
            forged = {**action(), field: 100}
            with self.assertRaises(ProtocolError): self.c.submit("action", message("forged", forged))
            self.assertEqual(before, self.c.path.read_bytes())

    def test_wrong_actor_rejected(self):
        with self.assertRaises(ProtocolError): self.c.submit("action", message("wrong", action("elara-voss")))

    def test_durable_roll_and_idempotent_retry(self):
        review = self.begin_check()
        first = self.c.submit("review", review)["pending"]["roll"]
        restored = Campaign(self.root)
        snapshot = restored.path.read_bytes()
        retry = restored.submit("review", review)
        self.assertTrue(retry["duplicate"])
        self.assertEqual(first, retry["pending"]["roll"])
        self.assertEqual(snapshot, restored.path.read_bytes())
        changed = copy.deepcopy(review); changed["payload"]["roll"]["difficulty"] = 1
        with self.assertRaises(ProtocolError): restored.submit("review", changed)

    def test_gm_cannot_override_software_roll(self):
        review = self.begin_check()
        invalid = copy.deepcopy(review); invalid["payload"]["roll"]["total"] = 20
        with self.assertRaises(ProtocolError): self.c.submit("review", invalid)
        total = self.c.submit("review", review)["pending"]["roll"]["total"]
        wrong = "FAILURE" if total >= 13 else "SUCCESS"
        with self.assertRaises(ProtocolError): self.c.submit("resolve", message("final-1", result(wrong)))

    def test_advantage_disadvantage_cancel(self):
        review = self.begin_check()
        review["payload"]["roll"].update(advantage=True, disadvantage=True)
        rolled = self.c.submit("review", review)["pending"]["roll"]
        self.assertEqual(1, len(rolled["individual_rolls"]))

    def test_failed_resolution_is_atomic(self):
        review = self.begin_check(); self.c.submit("review", review)
        pending = self.c.state["pending"]
        final = result("SUCCESS" if pending["roll"]["total"] >= 13 else "FAILURE")
        final["facts"] = [{"id": "valid", "statement": "A new fact", "classification": "RUMOR", "source": "npc", "entity_id": "crooked-lantern"}]
        final["grants"] = [{"character_id": "nonexistent", "fact_id": "valid"}]
        before = self.c.path.read_bytes()
        with self.assertRaises(ProtocolError): self.c.submit("resolve", message("bad-final", final))
        self.assertEqual(before, self.c.path.read_bytes())
        self.assertNotIn("valid", self.c.state["facts"])

    def test_rumor_keeps_exact_wording_and_classification(self):
        self.c.submit("action", message("action-1", action()))
        self.c.submit("review", message("review-1", {"roll": None}))
        final = result()
        final["facts"] = [{"id": "rumor", "statement": "Three caravans failed to arrive.", "classification": "RUMOR", "source": "mara", "entity_id": "crooked-lantern"}]
        self.c.submit("resolve", message("final-1", final))
        self.assertEqual("RUMOR", self.c.state["facts"]["rumor"]["classification"])
        self.assertEqual(final["facts"][0]["statement"], self.c.state["facts"]["rumor"]["statement"])

    def test_restart_preserves_next_roll(self):
        review = self.begin_check(); self.c.submit("review", review)
        original = copy.deepcopy(self.c.state)
        restored = Campaign(self.root)
        self.assertEqual(json.dumps(original["rng_state"]), json.dumps(restored.state["rng_state"]))
        import random
        from ttrpg import tuples
        r1, r2 = random.Random(), random.Random()
        r1.setstate(tuples(original["rng_state"])); r2.setstate(tuples(restored.state["rng_state"]))
        self.assertEqual([r1.randint(1,20) for _ in range(20)], [r2.randint(1,20) for _ in range(20)])

    def test_hard_limit_of_100_completed_actor_turns(self):
        # Exercise real transitions; avoid regenerating presentation files 300 times.
        self.c.export = lambda: None
        for turn in range(1, 101):
            cid = list(self.c.state["characters"])[self.c.state["next_actor"]]
            self.c.submit("action", message(f"a-{turn}", action(cid)))
            self.c.submit("review", message(f"r-{turn}", {"roll": None}))
            self.c.submit("resolve", message(f"f-{turn}", result()))
        self.assertEqual(100, Campaign(self.root).state["turn"])
        self.assertEqual("LIMIT_REACHED", self.c.state["phase"])
        with self.assertRaises(ProtocolError): self.c.submit("action", message("turn-101", action()))
        self.c.submit("end", message("ending", {"summary": "A test ended.", "source_fact_ids": [], "next_hook": "None established."}))
        self.assertEqual("ENDED", self.c.state["phase"])

    def test_export_rebuild_and_init_protection(self):
        transcript = next(self.root.glob("sessions/*/transcript.md"))
        expected = transcript.read_bytes(); transcript.unlink()
        Campaign(self.root).export()
        self.assertEqual(expected, transcript.read_bytes())
        with self.assertRaises(ProtocolError): Campaign.create(self.root, CONFIG)


if __name__ == "__main__": unittest.main()
