import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from agent_provider import ProviderError, ResponsesProvider
from live import LiveSession, continue_campaign
from ttrpg import Campaign, ProtocolError

ROOT = Path(__file__).parents[1]
CONFIG = json.loads((ROOT / "config/tavern-zero.json").read_text())
SECRET = "HIDDEN_ZEBRA_739"


def reply(packet, payload):
    return {"request_id": packet["request_id"], "agent_id": packet["agent_id"], "payload": payload}


class FixtureProvider:
    def __init__(self): self.packets = []

    def complete(self, packet):
        self.packets.append(copy.deepcopy(packet))
        op, ctx = packet["operation"], packet["context"]
        if op == "scene":
            payload = {"narration": "The party waits in the tavern.", "location": "crooked-lantern", "entities": [{"id": "hidden-hatch", "name": SECRET, "type": "OBJECT", "undefined_fields": []}], "facts": [{"id": "hidden-fact", "entity_id": "hidden-hatch", "statement": SECRET, "classification": "SECRET_CANON", "source": "gm"}], "grants": []}
        elif op == "action":
            payload = {"character_id": ctx["character"]["id"], "speech": "Who is here?", "action": "Look around the room.", "intent": "PRIVATE_" + ctx["character"]["id"], "target": "crooked-lantern"}
        elif op == "review":
            actor = ctx["characters"][ctx["pending"]["action"]["character_id"]]
            payload = {"roll": {"skill": next(iter(actor["skills"])), "difficulty": 13, "advantage": False, "disadvantage": False, "reason": "Inspect the room"}}
        elif op == "resolve":
            p = ctx["pending"]
            outcome = "SUCCESS" if p["roll"]["total"] >= p["review"]["roll"]["difficulty"] else "FAILURE"
            payload = {"narration": "Rain taps the shutters.", "outcome": outcome, "entities": [], "facts": [], "grants": [], "scene_finished": False}
        elif op == "chronicle": payload = {"approved": True, "conflicts": []}
        elif op == "end": payload = {"summary": "The party inspected the tavern.", "source_fact_ids": ["fact-seed-tavern"], "next_hook": "Ask another question."}
        else: raise AssertionError(op)
        return reply(packet, payload), {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8}


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "campaign"
        config = copy.deepcopy(CONFIG); config["maximum_turns"] = 3
        Campaign.create(self.root, config)
        self.live = LiveSession.attach(self.root)
        self.provider = FixtureProvider()

    def advance_to(self, operation):
        for _ in range(30):
            packet = self.live.request()
            if packet["operation"] == operation: return packet
            self.live.step(self.provider)
        self.fail("Phase never reached")

    def test_three_agents_have_separate_packets_and_limit_ends_session(self):
        for _ in range(30):
            if not self.live.step(self.provider): break
        self.assertEqual("ENDED", self.live.campaign.state["phase"])
        self.assertEqual(3, self.live.campaign.state["turn"])
        packets = {p["agent_id"]: p for p in self.provider.packets if p["operation"] == "action"}
        self.assertEqual({"player-01", "player-02", "player-03"}, set(packets))
        for role, packet in packets.items():
            self.assertNotIn(SECRET, json.dumps(packet))
            self.assertNotIn("hidden-hatch", json.dumps(packet))
            self.assertNotIn("private_memories", json.dumps(packet["context"].get("other_characters", {})))
            cid = packet["context"]["character"]["id"]
            for other in CONFIG["characters"]:
                if other["id"] != cid:
                    for memory in other["private_memories"]: self.assertNotIn(memory, json.dumps(packet))
                    self.assertNotIn("PRIVATE_" + other["id"], json.dumps(packet))
        self.assertGreater(self.live.data["usage"]["total_tokens"], 0)

    def test_chronicler_runs_before_publication(self):
        packet = self.advance_to("resolve")
        answer, _ = self.provider.complete(packet)
        self.live.submit(answer)
        self.assertEqual(0, self.live.campaign.state["turn"])
        self.assertEqual("AWAITING_FINAL", self.live.campaign.state["phase"])
        self.assertEqual("chronicle", self.live.request()["operation"])
        self.live.step(self.provider)
        self.assertEqual(1, self.live.campaign.state["turn"])

    def test_veto_pauses_and_gm_revision_reuses_roll(self):
        packet = self.advance_to("resolve")
        original_roll = copy.deepcopy(self.live.campaign.state["pending"]["roll"])
        answer, _ = self.provider.complete(packet); self.live.submit(answer)
        packet = self.live.request()
        self.live.submit(reply(packet, {"approved": False, "conflicts": [{"fact_id": "hidden-fact", "reason": "Clarify the narration"}]}))
        self.assertEqual("canon_conflict", self.live.data["paused"]["kind"])
        self.live = LiveSession(self.root); self.live.retry()
        corrected = self.live.request()
        self.assertEqual("gm", corrected["agent_id"])
        self.assertEqual("resolve", corrected["operation"])
        self.assertEqual(original_roll, corrected["context"]["pending"]["roll"])
        self.assertIsNotNone(corrected["context"]["correction"])

    def test_wrong_role_and_unknown_fields_rejected_without_world_change(self):
        packet = self.advance_to("action")
        answer, _ = self.provider.complete(packet)
        before = self.live.campaign.path.read_bytes()
        bad = copy.deepcopy(answer); bad["agent_id"] = "gm"
        with self.assertRaises(ProtocolError): self.live.submit(bad)
        bad = copy.deepcopy(answer); bad["payload"]["facts"] = []
        with self.assertRaises(ProtocolError): self.live.submit(bad)
        self.assertEqual(before, self.live.campaign.path.read_bytes())

    def test_guessing_hidden_target_is_rejected(self):
        packet = self.advance_to("action")
        answer, _ = self.provider.complete(packet)
        answer["payload"]["target"] = "hidden-hatch"
        with self.assertRaises(ProtocolError): self.live.submit(answer)

    def test_repeated_bad_output_pauses_after_three_attempts(self):
        self.live.request()
        for _ in range(3):
            with self.assertRaises(ProtocolError): self.live.submit({})
        self.assertEqual(3, self.live.data["calls"])
        self.assertEqual("attempt_limit", self.live.data["paused"]["kind"])
        with self.assertRaises(ProtocolError): self.live.request()

    def test_duplicate_reply_is_idempotent(self):
        packet = self.live.request(); answer, _ = self.provider.complete(packet)
        self.live.submit(answer)
        count = self.live.data["calls"]
        self.assertTrue(self.live.submit(answer)["duplicate"])
        self.assertEqual(count, self.live.data["calls"])

    def test_request_survives_restart(self):
        packet = self.live.request()
        self.assertEqual(packet, LiveSession(self.root).request())

    def test_crash_after_campaign_commit_recovers_without_reroll(self):
        self.advance_to("review")
        original = self.live.campaign.submit
        def crash(*args):
            original(*args)
            raise OSError("Simulated crash after checkpoint replacement")
        with patch.object(self.live.campaign, "submit", side_effect=crash):
            with self.assertRaises(OSError): self.live.step(self.provider)
        saved = Campaign(self.root).state["pending"]["roll"]
        restarted = LiveSession(self.root)
        packet = restarted.request()
        self.assertEqual("resolve", packet["operation"])
        self.assertEqual(saved, packet["context"]["pending"]["roll"])
        dice = [e for e in restarted.campaign.state["events"] if e["message_type"] == "DICE_RESULT"]
        self.assertEqual(1, len(dice))

    def test_interrupted_external_call_consumes_attempt(self):
        self.live.request(); self.live.reserve()
        restarted = LiveSession(self.root); restarted.request()
        self.assertEqual(1, restarted.data["calls"])
        self.assertEqual(1, restarted.data["request"]["attempts"])
        self.assertFalse(restarted.data["request"]["in_flight"])

    def test_call_budget_blocks_provider_before_call(self):
        self.live.data["limits"]["maximum_calls"] = 1; self.live.save()
        self.live.step(self.provider)
        with self.assertRaises(ProtocolError): self.live.step(self.provider)
        self.assertEqual(1, len(self.provider.packets))

    def test_stale_reply_cannot_apply_to_modified_campaign(self):
        packet = self.live.request(); answer, _ = self.provider.complete(packet)
        self.live.campaign.state["scene"] = "Changed elsewhere"
        with self.assertRaises(ProtocolError): self.live.submit(answer)

    def test_continue_preserves_knowledge_rng_and_source(self):
        for _ in range(30):
            if not self.live.step(self.provider): break
        source = self.live.campaign.path
        old_bytes = source.read_bytes()
        nxt = continue_campaign(source, Path(self.temp.name) / "next", "session-0002", 100)
        self.assertEqual(old_bytes, source.read_bytes())
        self.assertEqual(0, nxt.state["turn"])
        self.assertEqual(3, nxt.state["campaign_turns_before"])
        self.assertEqual(json.dumps(self.live.campaign.state["rng_state"]), json.dumps(nxt.state["rng_state"]))
        self.assertEqual(self.live.campaign.state["characters"], nxt.state["characters"])
        self.assertEqual("NEED_SCENE", nxt.state["phase"])
        with self.assertRaises(ProtocolError): continue_campaign(source, Path(self.temp.name) / "bad", "session-0003", 101)

    def test_finish_waits_for_pending_turn_and_chronicler(self):
        self.advance_to("resolve")
        self.live.data["finish_requested"] = True; self.live.save()
        self.live.step(self.provider)
        self.assertEqual("chronicle", self.live.request()["operation"])
        self.live.step(self.provider)
        self.assertEqual("end", self.live.request()["operation"])
        self.live.step(self.provider)
        self.assertEqual(1, self.live.campaign.state["turn"])
        self.assertEqual("ENDED", self.live.campaign.state["phase"])


class ProviderTests(unittest.TestCase):
    def packet(self):
        return {"agent_id": "player-01", "instructions": "Only your role", "operation": "action", "context": {"known": "hello"}, "response_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}}

    def test_tool_free_stateless_request_and_json_parse(self):
        requests = []
        def opener(request, timeout):
            requests.append(json.loads(request.data))
            return io.BytesIO(json.dumps({"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "{}"}]}], "usage": {"total_tokens": 8, "unknown": "do not retain"}}).encode())
        provider = ResponsesProvider({"player-01": "test-model"}, api_key="TEST_ONLY", opener=opener)
        answer, usage = provider.complete(self.packet())
        provider.complete(self.packet())
        self.assertEqual({}, answer); self.assertEqual({"total_tokens": 8}, usage)
        for body in requests:
            self.assertFalse(body["store"])
            self.assertNotIn("tools", body)
            self.assertNotIn("previous_response_id", body)
            self.assertNotIn("conversation", body)
            self.assertNotIn("TEST_ONLY", json.dumps(body))
            self.assertEqual("json_schema", body["text"]["format"]["type"])

    def test_refusal_and_incomplete_do_not_become_game_actions(self):
        for value in [{"status": "incomplete"}, {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "No"}]}]}]:
            provider = ResponsesProvider({"player-01": "test-model"}, api_key="TEST_ONLY", opener=lambda *a, **k: io.BytesIO(json.dumps(value).encode()))
            with self.assertRaises(ProviderError): provider.complete(self.packet())

    def test_http_error_does_not_echo_credentials(self):
        def fail(*args, **kwargs):
            raise urllib.error.HTTPError("url", 401, "TEST_SECRET", {}, io.BytesIO(b"TEST_SECRET"))
        provider = ResponsesProvider({"player-01": "test-model"}, api_key="TEST_SECRET", opener=fail)
        with self.assertRaises(ProviderError) as caught: provider.complete(self.packet())
        self.assertNotIn("TEST_SECRET", str(caught.exception))


if __name__ == "__main__": unittest.main()
