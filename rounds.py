#!/usr/bin/env python3
"""Grouped play: durable independent inboxes, one GM, periodic Chronicler."""
import argparse
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import random
import time

from agent_provider import ResponsesProvider, ProviderError
from agent_schemas import validate
from live import campaign_lock, continue_campaign, digest
from round_contract import VERSION, instructions, response_schema
from round_memory import context, recall
from ttrpg import Campaign, ProtocolError, identifier, integer, require, tuples, write_json

ROOT = Path(__file__).resolve().parent


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class RoundSession:
    """All mutable engine and dispatcher state commits in ONE checkpoint replacement.

    Public methods require one writer; CLI holds campaign_lock. External agents
    can run concurrently, but responses are applied serially under that lock.
    """
    def __init__(self, root):
        self.campaign = Campaign(root)
        self.root = Path(root)
        require(self.e.get("version") == VERSION, "Unsupported round runtime")
        self.disk_hash = digest(self.s)

    @property
    def s(self): return self.campaign.state

    @property
    def e(self): return self.s["round_runtime"]

    @classmethod
    def attach(cls, root, max_rounds=5, review_every=5, max_calls=240, profiles=None, directive=""):
        c = Campaign(root)
        require("round_runtime" not in c.state, "Round runtime already attached")
        require(c.state["phase"] in ["NEED_SCENE", "READY"], "Attach only between actions in an active session")
        integer(max_rounds, 1, 100); integer(review_every, 1, 5); integer(max_calls, 1, 1000)
        require(len(c.state["characters"]) == 3, "This pilot requires exactly three characters")
        profiles = profiles or json.loads((ROOT / "config/round-models.json").read_text())
        require(set(profiles) == {"player", "gm", "chronicler"}, "Three role profiles required")
        for profile in profiles.values():
            require(set(profile) == {"native_model", "reasoning_effort", "api_model_env", "max_output_tokens"}, "Invalid profile")
            for key in ["native_model", "api_model_env"]:
                require(isinstance(profile[key], str) and profile[key], "Invalid model setting")
            require(profile["reasoning_effort"] in ["low", "medium", "high"], "Unsupported effort")
            integer(profile["max_output_tokens"], 500, 16000)
        require(isinstance(directive, str) and len(directive) <= 800, "Directive too long")
        c.state["config"]["play_mode"] = "GROUPED_AGENTS"
        c.state.setdefault("role_journals", {})
        c.state["round_runtime"] = {
            "version": VERSION, "phase": "OPENING" if c.state["phase"] == "NEED_SCENE" else "COLLECT",
            "state_version": 0, "round": 0, "max_rounds": max_rounds, "review_every": review_every,
            "maximum_calls": max_calls, "calls": 0, "sequence": 0, "requests": {}, "accepted": {},
            "actors": [], "declarations": {}, "checks": {}, "proposal": None, "paused": None,
            "finish_requested": False, "profiles": profiles, "directive": directive,
            "recall_counts": {}, "recalled": {}, "audit": [], "round_metrics": [],
            "review_start": 0, "review_event_start": 0, "reviews": [], "round_started_at": None,
        }
        write_json(c.path, c.state)
        live = cls(root); live.export()
        return live

    @classmethod
    def continue_from(cls, source, root, session_id="session-0003", **kwargs):
        c = continue_campaign(source, root, session_id, 100)
        # Runtime inboxes are session-specific; role journals are campaign memory.
        c.state.pop("round_runtime", None)
        write_json(c.path, c.state)
        return cls.attach(root, **kwargs)

    def ensure_current(self):
        require(digest(json.loads(self.campaign.path.read_text())) == self.disk_hash,
                "Checkpoint changed on disk; reload before applying a reply")

    def save(self):
        self.ensure_current()
        write_json(self.campaign.path, self.s)
        self.disk_hash = digest(self.s)

    def profile(self, role):
        return copy.deepcopy(self.e["profiles"]["player" if role.startswith("player-") else role])

    def status(self):
        return {"phase": self.e["phase"], "rounds_completed": self.e["round"], "maximum_rounds": self.e["max_rounds"],
                "character_turns": self.s["turn"], "maximum_turns": self.s["config"]["maximum_turns"],
                "calls": self.e["calls"], "maximum_calls": self.e["maximum_calls"], "paused": self.e["paused"],
                "inboxes": [{"request_id": rid, "agent": r["packet"]["agent_id"], "operation": r["packet"]["operation"],
                             "in_flight": r["in_flight"]} for rid, r in self.e["requests"].items()]}

    def packet_context(self, role, operation):
        value = context(self.s, role)
        if self.e["recalled"].get(role): value["recalled"] = self.e["recalled"][role][-2:]
        if role == "gm":
            value["table_direction"] = self.e["directive"]
            if operation != "opening":
                value["declarations"] = [self.e["declarations"][cid] for cid in self.e["actors"]]
                value["saved_checks"] = self.e["checks"]
        elif role == "chronicler":
            if operation == "gate":
                proposal = copy.deepcopy(self.e["proposal"])
                proposal["payload"].pop("notebook", None)
                value["proposed_event"] = proposal
                value["declarations"] = [{k: a[k] for k in ["character_id", "speech", "action"]}
                                         for a in self.e["declarations"].values()]
                value["saved_checks"] = self.e["checks"]
            else:
                value["review_window"] = self.s["public_log"][self.e["review_start"]:]
                value["record_changes"] = [e["payload"] for e in self.s["events"][self.e["review_event_start"]:]
                                           if e["message_type"] == "CHRONICLE_PATCH"]
                value["previous_reviews"] = [{"summary": r["summary"], "source_fact_ids": r["source_fact_ids"]}
                                             for r in self.e["reviews"][-3:]]
                value["ending"] = self.should_end()
                value["turns_completed"] = self.s["turn"]
        return value

    def should_end(self):
        return (self.e["finish_requested"] or self.e["round"] >= self.e["max_rounds"]
                or self.s["turn"] >= self.s["config"]["maximum_turns"])

    def requests(self):
        self.ensure_current()
        backup = copy.deepcopy(self.s)
        try:
            return self._requests()
        except Exception:
            self.campaign.state = backup
            raise

    def _requests(self):
        self.ensure_current()
        require(not self.e["paused"], "Session paused; inspect status")
        if self.e["phase"] == "ENDED": return []
        if self.e["phase"] == "COLLECT" and not self.e["actors"]:
            if self.should_end(): self.e["phase"] = "REVIEW"
            else:
                ids = list(self.s["characters"])
                count = min(3, self.s["config"]["maximum_turns"] - self.s["turn"])
                self.e["actors"] = [ids[(self.s["next_actor"] + i) % 3] for i in range(count)]
                self.e["round_started_at"] = time.time()
        phase = self.e["phase"]
        if phase == "COLLECT":
            wanted = [(self.s["characters"][cid]["agent_id"], "declare") for cid in self.e["actors"]
                      if cid not in self.e["declarations"]]
        else:
            operation = {"OPENING": "opening", "ADJUDICATE": "adjudicate", "RESOLVE": "resolve", "GATE": "gate", "REVIEW": "checkpoint"}[phase]
            wanted = [("chronicler" if phase in ["GATE", "REVIEW"] else "gm", operation)]
        existing = {r["packet"]["agent_id"] for r in self.e["requests"].values()}
        for role, op in wanted:
            if role in existing: continue
            started = time.perf_counter()
            self.e["sequence"] += 1
            prefix = digest([self.s["config"]["campaign_id"], self.s["config"]["session_id"]])[:10]
            rid = f"round-{prefix}-{self.e['sequence']:05}"
            ctx = self.packet_context(role, op)
            packet = {"request_id": rid, "agent_id": role, "state_version": self.e["state_version"],
                      "operation": op, "instructions": instructions(role), "context": ctx,
                      "profile": self.profile(role), "response_schema": response_schema(op, rid, role, self.e["state_version"], ctx)}
            limit = 8000 if role.startswith("player-") else 90000 if role == "chronicler" else 16000
            # Drop optional history before dispatch, never declarations, dice or review evidence.
            # Full records stay authoritative and can be recalled with audience filtering.
            while len(compact(packet)) > limit and ctx["recent_public_events"]:
                ctx["recent_public_events"].pop(0)
            while len(compact(packet)) > limit and len(ctx["facts"]) > 1:
                ctx["facts"].pop(); ctx["older_facts_available"] += 1
            size = len(compact(packet))
            require(size <= limit, f"{role} context exceeds {limit} characters; stop for operator investigation")
            self.e["requests"][rid] = {"packet": packet, "attempts": 0, "in_flight": False, "created_at": time.time(),
                                       "build_ms": (time.perf_counter() - started) * 1000, "input_characters": size}
        self.save()
        return [copy.deepcopy(r["packet"]) for r in self.e["requests"].values()]

    def reserve(self, rid):
        self.ensure_current()
        require(not self.e["paused"], "Session paused")
        r = self.e["requests"][rid]
        require(not r["in_flight"], "Request already dispatched; wait for it or mark it interrupted")
        if self.e["calls"] >= self.e["maximum_calls"]:
            self.e["paused"] = {"kind": "call_budget"}; self.save()
            raise ProtocolError("Call budget exhausted")
        require(r["attempts"] < 3, "Attempt limit reached")
        r["attempts"] += 1; r["in_flight"] = True; r["dispatched_at"] = time.time()
        self.e["calls"] += 1; self.save()

    def fail(self, rid, message):
        r = self.e["requests"][rid]
        r["in_flight"] = False
        r["packet"]["validation_feedback"] = str(message)[:500]
        self.e["audit"].append({"request_id": rid, "agent_id": r["packet"]["agent_id"], "error": str(message)[:500], "attempt": r["attempts"]})
        if r["attempts"] >= 3: self.e["paused"] = {"kind": "attempt_limit", "request_id": rid}
        self.save()

    def submit(self, answer, expected_request_id=None, usage=None):
        self.ensure_current()
        require(isinstance(answer, dict), "Expected JSON object")
        rid = expected_request_id or answer.get("request_id")
        if rid in self.e["accepted"]:
            require(self.e["accepted"][rid] == digest(answer), "Accepted response changed")
            return {"duplicate": True}
        require(not self.e["paused"] and rid in self.e["requests"], "No such pending request")
        req = self.e["requests"][rid]
        measured_dispatch = req["in_flight"]
        if not measured_dispatch: self.reserve(rid)
        received = time.time(); started = time.perf_counter()
        backup = copy.deepcopy(self.s)
        try:
            validate(answer, req["packet"]["response_schema"])
            require(answer["state_version"] == self.e["state_version"], "Stale world version")
            self.apply(req["packet"], answer["payload"])
            self.e["accepted"][rid] = digest(answer)
            self.e["requests"].pop(rid)
            self.e["audit"].append({"request_id": rid, "agent_id": answer["agent_id"], "operation": req["packet"]["operation"],
                "packet": req["packet"], "reply": copy.deepcopy(answer), "attempt": req["attempts"],
                "input_characters": req["input_characters"], "build_ms": req["build_ms"],
                "queue_wait_ms": (req["dispatched_at"] - req["created_at"]) * 1000 if measured_dispatch else None,
                "dispatch_to_reply_ms": (received - req["dispatched_at"]) * 1000 if measured_dispatch else None,
                "apply_ms": (time.perf_counter() - started) * 1000,
                "usage": {k: v for k, v in (usage or {}).items() if k in ["input_tokens", "output_tokens", "total_tokens"] and type(v) is int and v >= 0}})
        except ProtocolError as exc:
            self.campaign.state = backup
            self.fail(rid, str(exc))
            raise
        except Exception:
            self.campaign.state = backup
            raise
        # One atomic authority: a crash before save leaves the request pending;
        # a crash after save makes the exact same reply a no-op, including dice.
        self.save()
        self.export()  # May be rebuilt after an interrupted export.
        return self.status()

    def apply(self, packet, payload):
        role, op, rid = packet["agent_id"], packet["operation"], packet["request_id"]
        if payload["kind"] == "recall":
            key = f"{self.e['round']}:{op}:{role}"
            n = self.e["recall_counts"].get(key, 0)
            require(n < 2, "Recall allowance exhausted for this task")
            self.e["recall_counts"][key] = n + 1
            self.e["recalled"].setdefault(role, []).append(recall(self.s, role, payload["query"], 5))
            return
        if op == "declare":
            cid = payload["character_id"]
            require(cid in self.e["actors"] and cid not in self.e["declarations"], "Character already declared")
            require(payload["action"].strip() and payload["intent"].strip(), "Action and intent must be nonempty")
            self.e["declarations"][cid] = {k: payload[k] for k in ["character_id", "speech", "action", "intent", "target"]}
            self.s["role_journals"][role] = copy.deepcopy(payload["journal"])
            if len(self.e["declarations"]) == len(self.e["actors"]): self.e["phase"] = "ADJUDICATE"
        elif payload["kind"] == "checks":
            self.roll_checks(payload, rid)
        elif op in ["opening", "adjudicate", "resolve"]:
            self.validate_proposal(payload, op)
            self.e["proposal"] = {"operation": op, "payload": copy.deepcopy(payload), "request_id": rid}
            if self.needs_gate(payload): self.e["phase"] = "GATE"
            else: self.commit_proposal()
        elif op == "gate":
            self.validate_review(payload)
            if not payload["approved"]:
                self.e["paused"] = {"kind": "review_conflict", "conflicts": payload["conflicts"], "publication": "not_committed"}
            else: self.commit_proposal()
        elif op == "checkpoint":
            self.validate_review(payload)
            if not payload["approved"]:
                self.e["paused"] = {"kind": "review_conflict", "conflicts": payload["conflicts"], "publication": "already_recorded"}
            else:
                self.e["reviews"].append(copy.deepcopy(payload))
                self.e["review_start"] = len(self.s["public_log"])
                self.e["review_event_start"] = len(self.s["events"])
                if self.should_end():
                    summary = {k: payload[k] for k in ["summary", "source_fact_ids", "next_hook"]}
                    self.campaign.end(summary, rid)
                    self.e["phase"] = "ENDED"
                else: self.e["phase"] = "COLLECT"

    def roll_checks(self, payload, rid):
        require(self.e["phase"] == "ADJUDICATE" and not self.e["checks"], "Checks already committed")
        require(payload["checks"], "At least one check required")
        seen = set()
        for check in payload["checks"]:
            cid = check["character_id"]
            require(cid in self.e["actors"] and cid not in seen, "Unknown or duplicate check actor")
            require(check["skill"] in self.s["characters"][cid]["skills"], "Skill not on character sheet")
            seen.add(cid)
        rng = random.Random(); rng.setstate(tuples(self.s["rng_state"]))
        # Rolls have stable order even if GM check objects arrive in another order.
        checks = {x["character_id"]: x for x in payload["checks"]}
        for cid in self.e["actors"]:
            if cid not in checks: continue
            check = checks[cid]
            values = [rng.randint(1, 20)]
            if check["advantage"] != check["disadvantage"]: values.append(rng.randint(1, 20))
            selected = max(values) if check["advantage"] and not check["disadvantage"] else min(values)
            modifier = self.s["characters"][cid]["skills"][check["skill"]]
            result = {"roll_id": f"round-{self.e['round'] + 1}-{cid}", "individual_rolls": values,
                      "selected_roll": selected, "modifier": modifier, "total": selected + modifier}
            self.e["checks"][cid] = {"check": copy.deepcopy(check), "roll": result,
                "outcome": "SUCCESS" if result["total"] >= check["difficulty"] else "FAILURE"}
            self.campaign.envelope("dice", "gm", "DICE_RESULT", "GM_PRIVATE", self.e["checks"][cid], "dice-" + rid + "-" + cid)
        self.s["rng_state"] = rng.getstate()
        self.e["state_version"] += 1; self.e["phase"] = "RESOLVE"

    def public_guard(self, payload, candidate):
        public = set(payload["public_fact_ids"])
        for fid in public:
            require(fid in candidate["facts"], "Unknown public fact")
            require(all(fid in c["knowledge"] for c in candidate["characters"].values()), "Public fact was not granted to every present character")
        # Exact-text leak sentinel, not a claim of semantic secrecy detection.
        for fid, fact in candidate["facts"].items():
            if all(fid in c["knowledge"] for c in candidate["characters"].values()): continue
            require(fact["statement"].casefold() not in payload["narration"].casefold(), "Narration contains an unshared fact verbatim")

    def validate_proposal(self, payload, operation):
        if operation != "opening":
            ids = [x["character_id"] for x in payload["results"]]
            require(ids and ids == self.e["actors"][:len(ids)], "Resolve a nonempty prefix in actor order")
            require(set(self.e["checks"]) <= set(ids), "Cannot defer a character after rolling their check")
            for result in payload["results"]:
                expected = self.e["checks"].get(result["character_id"], {}).get("outcome", "NO_ROLL")
                require(result["outcome"] == expected, "Outcome contradicts saved dice")
        require(payload["narration"].strip(), "Narration required")
        candidate = copy.copy(self.campaign); candidate.state = copy.deepcopy(self.s)
        candidate.record_facts(payload, "preview", self.s["turn"])
        loc = payload["location"]
        require(loc in candidate.state["entities"] and candidate.state["entities"][loc]["type"] == "LOCATION", "Location must be a known or newly created LOCATION")
        self.public_guard(payload, candidate.state)

    def needs_gate(self, payload):
        if any(f["classification"] == "SECRET_CANON" for f in payload["facts"]): return True
        groups = {}
        for grant in payload["grants"]: groups.setdefault(grant["fact_id"], set()).add(grant["character_id"])
        return any(ids != set(self.s["characters"]) for ids in groups.values())

    def commit_proposal(self):
        proposal = self.e["proposal"]
        payload, rid = proposal["payload"], proposal["request_id"]
        self.s["role_journals"]["gm"] = copy.deepcopy(payload["notebook"])
        if proposal["operation"] == "opening":
            self.campaign.scene({k: payload[k] for k in ["narration", "location", "entities", "facts", "grants"]}, rid)
            self.e["phase"] = "COLLECT"
        else:
            if payload["location"] != self.s["location"]:
                self.s["scene_number"] += 1; self.s["scene_id"] = f"scene-{self.s['scene_number']:04}"
            count = len(payload["results"])
            ids = self.e["actors"][:count]
            declarations = [copy.deepcopy(self.e["declarations"][cid]) for cid in ids]
            self.campaign.envelope("gm", "orchestrator", "GM_ROUND_RESULT", "SYSTEM", payload, rid, self.s["turn"] + count)
            self.campaign.record_facts(payload, rid, self.s["turn"] + count)
            event = {"kind": "round", "round": self.e["round"] + 1, "turn_start": self.s["turn"] + 1,
                     "turn": self.s["turn"] + count, "scene_id": self.s["scene_id"], "location": payload["location"],
                     "text": payload["narration"], "results": payload["results"],
                     "declarations": [{k: a[k] for k in ["character_id", "speech", "action"]} for a in declarations],
                     "checks": [{"character_id": cid, "skill": x["check"]["skill"], "difficulty": x["check"]["difficulty"], **x["roll"]}
                                for cid, x in self.e["checks"].items()]}
            self.s["public_log"].append(event)
            self.e["round_metrics"].append({"round": event["round"], "character_turns": count,
                "wall_ms": (time.time() - self.e["round_started_at"]) * 1000,
                "deferred_characters": self.e["actors"][count:]})
            self.s["turn"] += count; self.s["next_actor"] = (self.s["next_actor"] + count) % 3
            self.s["location"] = payload["location"]; self.s["scene"] = payload["narration"]
            self.s["phase"] = "LIMIT_REACHED" if self.s["turn"] >= self.s["config"]["maximum_turns"] else "READY"
            self.e["round"] += 1
            self.e["phase"] = "REVIEW" if self.should_end() or self.e["round"] % self.e["review_every"] == 0 else "COLLECT"
        self.e["state_version"] += 1
        self.e["proposal"] = None; self.e["actors"] = []; self.e["declarations"] = {}; self.e["checks"] = {}
        self.e["recalled"] = {}

    def validate_review(self, payload):
        require(payload["approved"] == (len(payload["conflicts"]) == 0), "Review approval disagrees with conflicts")
        require(payload["summary"].strip() and payload["next_hook"].strip(), "Review summary and next hook required")
        state = self.s
        if self.e["phase"] == "GATE":
            candidate = copy.copy(self.campaign); candidate.state = copy.deepcopy(self.s)
            candidate.record_facts(self.e["proposal"]["payload"], "review-preview", self.s["turn"])
            state = candidate.state
        for fid in payload["source_fact_ids"]:
            require(fid in state["facts"], "Unknown summary fact")
            require(all(fid in c["knowledge"] for c in state["characters"].values()), "Summary source is not public")
        for fid, f in state["facts"].items():
            if all(fid in c["knowledge"] for c in state["characters"].values()): continue
            require(f["statement"].casefold() not in (payload["summary"] + payload["next_hook"]).casefold(), "Summary reveals unshared fact verbatim")

    def finish(self):
        self.e["finish_requested"] = True
        # If no declaration has been accepted/dispatched, cancel the unused inboxes.
        if self.e["phase"] == "COLLECT" and not self.e["declarations"] and not any(r["in_flight"] for r in self.e["requests"].values()):
            self.e["requests"] = {}; self.e["actors"] = []; self.e["phase"] = "REVIEW"
        self.save()

    def interrupt(self, rid):
        require(rid in self.e["requests"] and self.e["requests"][rid]["in_flight"], "No dispatched request")
        self.fail(rid, "Operator marked interrupted; cost may have occurred. Saved dice are unchanged.")

    def retry(self, feedback):
        require(self.e["paused"] is not None, "Not paused")
        require(self.e["paused"]["kind"] == "attempt_limit", "Review conflict or call-budget pause requires operator investigation; cannot bypass")
        r = self.e["requests"][self.e["paused"]["request_id"]]
        r["attempts"] = 0; r["packet"]["validation_feedback"] = feedback[:500]
        self.e["paused"] = None; self.save()

    def run_batch(self, provider):
        packets = self.requests()
        if not packets: return False
        require(not any(self.e["requests"][p["request_id"]]["in_flight"] for p in packets), "Outstanding dispatch exists; resume its reply or mark interrupted")
        # Reserve the whole batch before any transmission. Budget cannot strand a half-dispatched group.
        if self.e["calls"] + len(packets) > self.e["maximum_calls"]:
            self.e["paused"] = {"kind": "call_budget"}; self.save()
            raise ProtocolError("Insufficient call budget for this batch")
        for p in packets: self.reserve(p["request_id"])
        with ThreadPoolExecutor(max_workers=3) as pool:
            jobs = {pool.submit(provider.complete, p): p for p in packets}
            for future in as_completed(jobs):
                p = jobs[future]; rid = p["request_id"]
                try: answer, usage = future.result()
                except ProviderError as exc:
                    self.fail(rid, str(exc)); continue
                try: self.submit(answer, expected_request_id=rid, usage=usage)
                except ProtocolError:
                    if self.e["requests"].get(rid, {}).get("in_flight"):
                        self.fail(rid, "Response could not be accepted; inspect status")
        return True

    def export(self):
        self.campaign.export()
        session = self.root / "sessions" / self.s["config"]["session_id"]
        write_json(session / "round-audit.json", self.e["audit"])
        good = [a for a in self.e["audit"] if "reply" in a]
        write_json(session / "round-metrics.json", {**self.status(), "round_timings": self.e["round_metrics"],
            "accepted_role_replies": len(good), "request_characters": sum(a["input_characters"] for a in good),
            "timing_note": "Dispatch-to-reply includes scheduling/relay time, not pure inference. Null means no reservation timestamp.",
            "call_timings": [{k: a[k] for k in ["request_id", "agent_id", "input_characters", "build_ms", "queue_wait_ms", "dispatch_to_reply_ms", "apply_ms"]} for a in good]})
        write_json(session / "reviews.json", self.e["reviews"])
        for role, journal in self.s["role_journals"].items():
            write_json(self.root / "memory" / (role + ".json"), journal)
        for char in self.s["characters"].values():
            write_json(self.root / "views" / (char["agent_id"] + ".json"), context(self.s, char["agent_id"]))
        write_json(self.root / "views/gm.json", context(self.s, "gm"))
        write_json(self.root / "memory/shared-scene.json", {"location": self.s["location"], "scene": self.s["scene"],
                   "state_version": self.e["state_version"], "recent_public_events": self.s["public_log"][-3:]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", default="runs/session-0003")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--from-checkpoint"); init.add_argument("--session-id", default="session-0003")
    init.add_argument("--config", default=str(ROOT / "config/tavern-zero.json"))
    init.add_argument("--profiles", default=str(ROOT / "config/round-models.json"))
    init.add_argument("--max-rounds", type=int, default=5); init.add_argument("--max-calls", type=int, default=240)
    init.add_argument("--directive", default="Explore beyond the tavern. Follow player choices; ordinary agreed travel can resolve in one passage.")
    sub.add_parser("status"); sub.add_parser("finish"); sub.add_parser("export")
    request = sub.add_parser("requests"); request.add_argument("--output-dir")
    dispatch = sub.add_parser("dispatch"); dispatch.add_argument("request_id"); dispatch.add_argument("--output")
    reply = sub.add_parser("reply"); reply.add_argument("file")
    interrupt = sub.add_parser("interrupt"); interrupt.add_argument("request_id")
    retry = sub.add_parser("retry"); retry.add_argument("--feedback", required=True)
    memory = sub.add_parser("memory"); memory.add_argument("--role", required=True); memory.add_argument("--query", required=True)
    run = sub.add_parser("run"); run.add_argument("--batches", type=int, default=1)
    args = parser.parse_args()
    try:
        with campaign_lock(args.campaign):
            if args.command == "init":
                identifier(args.session_id)
                profiles = json.loads(Path(args.profiles).read_text())
                settings = dict(max_rounds=args.max_rounds, max_calls=args.max_calls, profiles=profiles, directive=args.directive)
                if args.from_checkpoint: live = RoundSession.continue_from(args.from_checkpoint, args.campaign, args.session_id, **settings)
                else:
                    config = json.loads(Path(args.config).read_text()); config.update(session_id=args.session_id, maximum_turns=100)
                    Campaign.create(args.campaign, config); live = RoundSession.attach(args.campaign, **settings)
                result = live.status()
            else:
                live = RoundSession(args.campaign)
                if args.command == "requests":
                    result = live.requests()
                    if args.output_dir:
                        for p in result: write_json(Path(args.output_dir) / (p["request_id"] + ".json"), p)
                elif args.command == "dispatch":
                    live.reserve(args.request_id); result = live.e["requests"][args.request_id]["packet"]
                    if args.output: write_json(args.output, result)
                elif args.command == "reply": result = live.submit(json.loads(Path(args.file).read_text()))
                elif args.command == "memory": result = recall(live.s, args.role, args.query)
                elif args.command == "finish": live.finish(); result = live.status()
                elif args.command == "interrupt": live.interrupt(args.request_id); result = live.status()
                elif args.command == "retry": live.retry(args.feedback); result = live.status()
                elif args.command == "export": live.export(); result = live.status()
                elif args.command == "run":
                    integer(args.batches, 1, 1000)
                    roles = ["gm", "chronicler"] + [c["agent_id"] for c in live.s["characters"].values()]
                    profiles = {r: live.profile(r) for r in roles}
                    models = {r: os.environ.get(p["api_model_env"], "") for r, p in profiles.items()}
                    provider = ResponsesProvider(models, role_settings={r: {"reasoning_effort": p["reasoning_effort"], "max_output_tokens": p["max_output_tokens"]} for r, p in profiles.items()})
                    for _ in range(args.batches):
                        if live.e["paused"] or not live.run_batch(provider): break
                    result = live.status()
                else: result = live.status()
            print(compact(result))
        return 0
    except (ProtocolError, ProviderError, OSError, ValueError, KeyError) as exc:
        print("Error: " + str(exc), file=__import__("sys").stderr)
        return 1


if __name__ == "__main__": raise SystemExit(main())
