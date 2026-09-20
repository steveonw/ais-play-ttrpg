#!/usr/bin/env python3
"""Local, dependency-free TTRPG orchestration. Models author fiction, never dice.

This CLI accepts role messages from a human or a supervising assistant. It does
not call a model API and does not claim to provide independent agent cognition.
The checkpoint is the atomic authority; other files are rebuildable projections.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import re
import sys


class ProtocolError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ProtocolError(message)


def fields(value, required, optional=()):
    require(isinstance(value, dict), "Expected an object")
    require(set(required) <= value.keys(), "Missing fields: " + str(set(required) - value.keys()))
    require(value.keys() <= set(required) | set(optional), "Unexpected fields: " + str(value.keys() - set(required) - set(optional)))


def text(value):
    require(isinstance(value, str) and 0 < len(value) <= 20000, "Expected nonempty text of at most 20000 characters")


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}", value), "Invalid ID")


def integer(value, low, high):
    require(type(value) is int and low <= value <= high, f"Expected integer in {low}..{high}")


def write_json(path, value):
    """Atomic snapshot replacement; only one writer per campaign is supported."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def tuples(value):
    return tuple(tuples(x) for x in value) if isinstance(value, list) else value


class Campaign:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / "checkpoint.json"
        self.state = json.loads(self.path.read_text(encoding="utf-8"))
        require(self.state.get("format_version") == 1, "Unsupported checkpoint version")

    @classmethod
    def create(cls, root, config):
        root = Path(root)
        require(not (root / "checkpoint.json").exists(), "Campaign already exists; use its checkpoint")
        fields(config, ["protocol_version", "campaign_id", "session_id", "maximum_turns", "dice_seed", "world_mode", "ruleset", "play_mode", "repository", "github_visibility", "adversary_enabled", "characters"])
        require(config["protocol_version"] == "0.1", "Unsupported protocol")
        require(config["ruleset"] == "TAVERN_ZERO_CHECKS_V1", "Unsupported ruleset")
        require(config["adversary_enabled"] is False, "Combat is not implemented")
        integer(config["maximum_turns"], 1, 100)
        integer(config["dice_seed"], 0, 2**64 - 1)
        identifier(config["campaign_id"]); identifier(config["session_id"])
        require(isinstance(config["characters"], list) and len(config["characters"]) >= 1, "Characters required")
        characters = {}
        agents = set()
        for original in config["characters"]:
            char = copy.deepcopy(original)
            fields(char, ["id", "agent_id", "name", "role", "personality", "goal", "skills", "hp", "inventory", "private_memories"])
            identifier(char["id"]); identifier(char["agent_id"])
            require(char["id"] not in characters and char["agent_id"] not in agents, "Duplicate character or agent")
            for key in ["name", "role", "personality", "goal"]: text(char[key])
            integer(char["hp"], 1, 1000)
            require(isinstance(char["skills"], dict), "Skills must be an object")
            for skill, modifier in char["skills"].items(): text(skill); integer(modifier, -10, 20)
            for key in ["inventory", "private_memories"]:
                require(isinstance(char[key], list), "Expected a list")
                for item in char[key]: text(item)
            char.update(knowledge=["fact-seed-tavern"], conditions=[])
            characters[char["id"]] = char
            agents.add(char["agent_id"])
        rng = random.Random(config["dice_seed"])
        state = {
            "format_version": 1, "config": copy.deepcopy(config), "phase": "NEED_SCENE",
            "turn": 0, "scene_number": 0, "scene_id": "scene-0000", "next_actor": 0,
            "location": "crooked-lantern", "scene": "", "characters": characters,
            "entities": {"crooked-lantern": {"id": "crooked-lantern", "name": "The Crooked Lantern", "type": "LOCATION", "undefined_fields": ["settlement", "region", "history"]}},
            "facts": {"fact-seed-tavern": {"id": "fact-seed-tavern", "statement": "The Crooked Lantern is a tavern.", "classification": "CANON", "source": "campaign-seed", "entity_id": "crooked-lantern", "source_event": "seed", "source_turn": 0, "source_scene": "scene-0000", "source_session": config["session_id"]}},
            "pending": None, "rng_algorithm": "python-random-MT19937-v3",
            "rng_state": rng.getstate(), "accepted": {}, "events": [], "public_log": [], "summary": None,
        }
        write_json(root / "checkpoint.json", state)
        campaign = cls(root)
        campaign.export()
        return campaign

    def status(self):
        s = self.state
        return {"turns_completed": s["turn"], "maximum_turns": s["config"]["maximum_turns"], "phase": s["phase"], "scene_id": s["scene_id"], "location": s["location"], "next_character": list(s["characters"])[s["next_actor"]] if s["phase"] != "ENDED" else None, "pending": s["pending"]}

    def envelope(self, sender, recipient, kind, visibility, payload, message_id, turn=None):
        s = self.state
        event = {"protocol_version": "0.1", "campaign_id": s["config"]["campaign_id"], "session_id": s["config"]["session_id"], "scene_id": s["scene_id"], "turn_id": s["turn"] if turn is None else turn, "message_id": message_id, "sender": sender, "recipient": recipient, "message_type": kind, "visibility": visibility, "payload": copy.deepcopy(payload)}
        s["events"].append(event)

    def context(self, role):
        s = self.state
        if role == "gm":
            return {"role": "gm", "phase": s["phase"], "scene": s["scene"], "location": s["location"], "entities": s["entities"], "facts": s["facts"], "characters": s["characters"], "pending": s["pending"], "recent_public_events": s["public_log"][-12:]}
        matches = [c for c in s["characters"].values() if role in [c["id"], c["agent_id"]]]
        require(len(matches) == 1, "Unknown player")
        char = matches[0]
        return {"role": char["agent_id"], "character": copy.deepcopy(char), "scene": s["scene"], "location": s["location"], "known_facts": [s["facts"][fid] for fid in char["knowledge"]], "recent_public_events": s["public_log"][-12:]}

    def submit(self, operation, message):
        """Reject atomically, or commit one transition. Identical retries are no-ops."""
        require("round_runtime" not in self.state, "Use rounds.py for grouped campaigns; legacy writes are disabled")
        fields(message, ["message_id", "payload"])
        identifier(message["message_id"])
        require(isinstance(message["payload"], dict), "Payload must be an object")
        digest = hashlib.sha256(json.dumps([operation, message], sort_keys=True).encode()).hexdigest()
        previous = self.state["accepted"].get(message["message_id"])
        if previous:
            require(previous == digest, "Message ID reused with different content")
            return {"duplicate": True, **self.status()}
        backup = copy.deepcopy(self.state)
        try:
            require(self.state["phase"] != "ENDED", "Session has ended")
            handler = {"scene": self.scene, "action": self.action, "review": self.review, "resolve": self.resolve, "end": self.end}.get(operation)
            require(handler is not None, "Unknown operation")
            handler(message["payload"], message["message_id"])
            self.state["accepted"][message["message_id"]] = digest
            write_json(self.path, self.state)
        except Exception:
            self.state = backup
            raise
        # Export failure cannot undo the authoritative checkpoint. `export` repairs it.
        self.export()
        return self.status()

    def record_facts(self, payload, source_id, turn):
        """Chronicler is a deterministic projection of GM-approved structured facts."""
        s = self.state
        for key in ["entities", "facts", "grants"]:
            require(isinstance(payload[key], list), key + " must be a list")
        for entity in payload["entities"]:
            fields(entity, ["id", "name", "type", "undefined_fields"])
            identifier(entity["id"]); text(entity["name"])
            require(entity["type"] in ["LOCATION", "NPC", "OBJECT", "FACTION"], "Unknown entity type")
            require(isinstance(entity["undefined_fields"], list), "Undefined fields must be a list")
            for item in entity["undefined_fields"]: text(item)
            require(entity["id"] not in s["entities"], "Entity already exists")
            s["entities"][entity["id"]] = copy.deepcopy(entity)
        added = []
        for fact in payload["facts"]:
            fields(fact, ["id", "statement", "classification", "source", "entity_id"])
            identifier(fact["id"]); text(fact["statement"]); text(fact["source"])
            require(fact["classification"] in ["CANON", "SECRET_CANON", "RUMOR", "CHARACTER_BELIEF"], "Unknown classification")
            require(fact["entity_id"] in s["entities"], "Unknown fact entity")
            require(fact["id"] not in s["facts"], "Existing fact ID: a canon conflict needs explicit resolution")
            saved = {**copy.deepcopy(fact), "source_event": source_id, "source_turn": turn, "source_scene": s["scene_id"], "source_session": s["config"]["session_id"]}
            s["facts"][fact["id"]] = saved
            added.append(saved)
        for grant in payload["grants"]:
            fields(grant, ["character_id", "fact_id"])
            require(grant["character_id"] in s["characters"], "Unknown knowledge recipient")
            require(grant["fact_id"] in s["facts"], "Unknown knowledge fact")
            knowledge = s["characters"][grant["character_id"]]["knowledge"]
            if grant["fact_id"] not in knowledge: knowledge.append(grant["fact_id"])
        self.envelope("chronicler", "orchestrator", "CHRONICLE_PATCH", "SYSTEM", {"facts_added": added, "knowledge_added": payload["grants"], "entities_created": payload["entities"], "source_event": source_id}, "chronicle-" + source_id, turn)

    def scene(self, payload, mid):
        s = self.state
        require(s["phase"] == "NEED_SCENE", "A new scene is not pending")
        require(s["turn"] < s["config"]["maximum_turns"], "Turn limit reached")
        fields(payload, ["narration", "location", "entities", "facts", "grants"])
        text(payload["narration"])
        s["scene_number"] += 1
        s["scene_id"] = f"scene-{s['scene_number']:04}"
        self.envelope("gm", "orchestrator", "GM_SCENE", "SYSTEM", payload, mid)
        self.record_facts(payload, mid, s["turn"])
        require(payload["location"] in s["entities"] and s["entities"][payload["location"]]["type"] == "LOCATION", "Unknown location")
        s["location"] = payload["location"]
        s["scene"] = payload["narration"]
        s["public_log"].append({"turn": s["turn"], "kind": "scene", "text": payload["narration"], "scene_id": s["scene_id"]})
        s["phase"] = "READY"

    def action(self, payload, mid):
        s = self.state
        require(s["phase"] == "READY", "Not ready for a player action")
        require(s["turn"] < s["config"]["maximum_turns"], "Turn limit reached")
        fields(payload, ["character_id", "speech", "action", "intent", "target"])
        actor = list(s["characters"])[s["next_actor"]]
        require(payload["character_id"] == actor, "Wrong actor for this turn")
        for key in ["action", "intent"]: text(payload[key])
        require(isinstance(payload["speech"], str) and len(payload["speech"]) <= 20000, "Invalid speech")
        require(payload["target"] is None or payload["target"] in s["entities"], "Unknown target")
        turn = s["turn"] + 1
        self.envelope("orchestrator", s["characters"][actor]["agent_id"], "PLAYER_TURN_REQUEST", "CHARACTER", self.context(actor), "context-" + mid, turn)
        self.envelope(s["characters"][actor]["agent_id"], "orchestrator", "PLAYER_ACTION", "SYSTEM", payload, mid, turn)
        s["pending"] = {"turn": turn, "action": copy.deepcopy(payload), "action_id": mid, "review": None, "roll": None}
        s["phase"] = "AWAITING_REVIEW"

    def review(self, payload, mid):
        s = self.state
        require(s["phase"] == "AWAITING_REVIEW", "No action awaiting review")
        fields(payload, ["roll"])
        pending = s["pending"]
        request = payload["roll"]
        if request is not None:
            fields(request, ["skill", "difficulty", "advantage", "disadvantage", "reason"])
            actor = s["characters"][pending["action"]["character_id"]]
            require(request["skill"] in actor["skills"], "Unapproved character skill")
            integer(request["difficulty"], 1, 30)
            require(type(request["advantage"]) is bool and type(request["disadvantage"]) is bool, "Invalid advantage flags")
            text(request["reason"])
            rng = random.Random()
            rng.setstate(tuples(s["rng_state"]))
            rolls = [rng.randint(1, 20)]
            if request["advantage"] != request["disadvantage"]: rolls.append(rng.randint(1, 20))
            selected = max(rolls) if request["advantage"] and not request["disadvantage"] else min(rolls)
            modifier = actor["skills"][request["skill"]]
            pending["roll"] = {"roll_id": f"roll-{pending['turn']:04}", "individual_rolls": rolls, "selected_roll": selected, "modifier": modifier, "total": selected + modifier}
            s["rng_state"] = rng.getstate()
        pending["review"] = copy.deepcopy(payload)
        self.envelope("gm", "orchestrator", "GM_REVIEW", "GM_PRIVATE", payload, mid, pending["turn"])
        if pending["roll"]:
            self.envelope("orchestrator", "dice", "DICE_REQUEST", "SYSTEM", {"roll_id": pending["roll"]["roll_id"], "notation": f"1d20{pending['roll']['modifier']:+}", "advantage": request["advantage"], "disadvantage": request["disadvantage"]}, "request-" + mid, pending["turn"])
            self.envelope("dice", "gm", "DICE_RESULT", "GM_PRIVATE", pending["roll"], "dice-" + mid, pending["turn"])
        s["phase"] = "AWAITING_FINAL"

    def resolve(self, payload, mid):
        s = self.state
        require(s["phase"] == "AWAITING_FINAL", "No reviewed action awaiting resolution")
        fields(payload, ["narration", "outcome", "entities", "facts", "grants", "scene_finished"])
        text(payload["narration"])
        require(type(payload["scene_finished"]) is bool, "Invalid scene flag")
        pending = s["pending"]
        expected = "NO_ROLL"
        if pending["roll"]:
            expected = "SUCCESS" if pending["roll"]["total"] >= pending["review"]["roll"]["difficulty"] else "FAILURE"
        require(payload["outcome"] == expected, "Outcome contradicts the precommitted check")
        self.envelope("gm", "orchestrator", "GM_FINAL_RESULT", "SYSTEM", payload, mid, pending["turn"])
        self.record_facts(payload, mid, pending["turn"])
        action = pending["action"]
        actor = s["characters"][action["character_id"]]
        s["public_log"].append({"turn": pending["turn"], "kind": "turn", "actor": actor["name"], "speech": action["speech"], "action": action["action"], "roll": pending["roll"], "skill": pending["review"]["roll"]["skill"] if pending["roll"] else None, "text": payload["narration"], "scene_id": s["scene_id"]})
        s["turn"] = pending["turn"]
        s["next_actor"] = (s["next_actor"] + 1) % len(s["characters"])
        s["pending"] = None
        s["phase"] = "LIMIT_REACHED" if s["turn"] >= s["config"]["maximum_turns"] else "NEED_SCENE" if payload["scene_finished"] else "READY"

    def end(self, payload, mid):
        s = self.state
        require(s["phase"] in ["READY", "NEED_SCENE", "LIMIT_REACHED"], "Resolve the pending turn before ending")
        fields(payload, ["summary", "source_fact_ids", "next_hook"])
        text(payload["summary"]); text(payload["next_hook"])
        require(isinstance(payload["source_fact_ids"], list), "Expected source IDs")
        for fid in payload["source_fact_ids"]: require(fid in s["facts"], "Unknown summary source")
        s["summary"] = copy.deepcopy(payload)
        self.envelope("chronicler", "orchestrator", "SESSION_SUMMARY", "SYSTEM", payload, mid)
        s["phase"] = "ENDED"

    def export(self):
        s = self.state
        write_json(self.root / "state/world-state.json", {"location": s["location"], "facts": s["facts"], "turns_completed": s["turn"]})
        write_json(self.root / "state/entity-index.json", s["entities"])
        session = self.root / "sessions" / s["config"]["session_id"]
        session.mkdir(parents=True, exist_ok=True)
        log = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in s["events"])
        (session / "debug-transcript.jsonl").write_text(log, encoding="utf-8")
        (self.root / "state/timeline.jsonl").write_text(log, encoding="utf-8")
        for cid, char in s["characters"].items():
            write_json(self.root / "characters" / cid / "knowledge.json", {"character_id": cid, "knowledge": [s["facts"][fid] for fid in char["knowledge"]]})
        title = "Tavern Zero — The First Night" if s["config"]["play_mode"] == "SINGLE_MODEL_SELF_PLAY" else "Tavern Zero — " + s["config"]["session_id"]
        mode = "single-model self-play" if s["config"]["play_mode"] == "SINGLE_MODEL_SELF_PLAY" else "separate agent requests"
        lines = ["# " + title, "", f"Mode: {mode} with software dice. All characters remain together. Private intentions and discoveries are excluded from this table-facing transcript.", ""]
        for event in s["public_log"]:
            if event["kind"] == "scene":
                lines += [f"## {event['scene_id']}", "", event["text"], ""]
            elif event["kind"] == "round":
                lines += [f"## Round {event['round']} — character turns {event['turn_start']}–{event['turn']}", ""]
                for action in event["declarations"]:
                    name = s["characters"][action["character_id"]]["name"]
                    lines += [f"**{name}**", "", "> " + action["speech"] if action["speech"] else "", "Attempt: " + action["action"], ""]
                for check in event["checks"]:
                    name = s["characters"][check["character_id"]]["name"]
                    lines += [f"Dice — {name}, {check['skill']}: {check['individual_rolls']} {check['modifier']:+} = **{check['total']}**, difficulty {check['difficulty']}.", ""]
                lines += ["GM: " + event["text"], ""]
            else:
                lines += [f"### Turn {event['turn']} — {event['actor']}", "", f"> {event['speech']}" if event["speech"] else "", "Attempt: " + event["action"], ""]
                if event["roll"]:
                    roll = event["roll"]
                    lines += [f"Dice — {event['skill']}: {roll['individual_rolls']}; selected {roll['selected_roll']} {roll['modifier']:+} = **{roll['total']}**.", ""]
                lines += ["GM: " + event["text"], ""]
        (session / "transcript.md").write_text("\n".join(lines), encoding="utf-8")
        if s["summary"]:
            summary = s["summary"]
            (session / "summary.md").write_text(f"# Session summary\n\n{s['turn']} completed turns of a maximum {s['config']['maximum_turns']}.\n\n{summary['summary']}\n\n## Next time\n\n{summary['next_hook']}\n\nSource facts: {', '.join(summary['source_fact_ids'])}\n", encoding="utf-8")
        facts = "\n".join(f"- **{f['id']} [{f['classification']}]** {f['statement']} (source: {f['source']}; turn {f['source_turn']})" for f in s["facts"].values())
        (self.root / "WORLD.md").write_text("# Established world\n\nFull public archive, including fictional secrets. Players must use filtered context, not this file.\n\n" + facts + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", default="campaigns/tavern-zero")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init"); init.add_argument("--config", default="config/tavern-zero.json")
    context = commands.add_parser("context"); context.add_argument("role")
    for name in ["scene", "action", "review", "resolve", "end"]:
        commands.add_parser(name).add_argument("file")
    commands.add_parser("status"); commands.add_parser("export")
    args = parser.parse_args()
    try:
        if args.command == "init":
            campaign = Campaign.create(args.campaign, json.loads(Path(args.config).read_text(encoding="utf-8")))
            result = campaign.status()
        else:
            campaign = Campaign(args.campaign)
            if args.command == "context": result = campaign.context(args.role)
            elif args.command == "status": result = campaign.status()
            elif args.command == "export": campaign.export(); result = campaign.status()
            else: result = campaign.submit(args.command, json.loads(Path(args.file).read_text(encoding="utf-8")))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ProtocolError, OSError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
