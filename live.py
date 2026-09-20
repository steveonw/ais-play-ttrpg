#!/usr/bin/env python3
"""Separate-role dispatch, durable relay and optional API runner."""
import argparse
import copy
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sys

from agent_prompts import VERSION, prompt
from agent_provider import ProviderError, ResponsesProvider
from agent_schemas import response_schema, validate
from ttrpg import Campaign, ProtocolError, identifier, integer, require, write_json

ROOT = Path(__file__).resolve().parent
DEFAULTS = {"maximum_attempts": 3, "maximum_calls": 600, "maximum_input_characters": 120000, "maximum_output_tokens": 5000, "timeout_seconds": 60}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@contextmanager
def campaign_lock(root):
    """CLI serialization on POSIX. Agents must never write campaign files."""
    import fcntl
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    with (root / "live.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ProtocolError("Another live command is operating on this campaign") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def continue_campaign(source, destination, session_id, maximum_turns=100):
    """Create a new session without modifying its completed predecessor."""
    identifier(session_id); integer(maximum_turns, 1, 100)
    path = Path(destination) / "checkpoint.json"
    require(not path.exists(), "Destination already contains a campaign")
    state = json.loads(Path(source).read_text(encoding="utf-8"))
    require(state.get("format_version") == 1 and state["phase"] == "ENDED", "Continue from a completed supported checkpoint")
    require(state["config"]["session_id"] != session_id, "Choose a new session ID")
    previous = {"session_id": state["config"]["session_id"], "turns": state["turn"], "summary": state["summary"], "checkpoint_sha256": digest(state)}
    prior_log = (state.get("prior_public_log", []) + state["public_log"])[-12:]
    state["campaign_turns_before"] = state.get("campaign_turns_before", 0) + state["turn"]
    state.update(previous_session=previous, prior_public_log=prior_log, turn=0, scene_number=0, scene_id="scene-0000", phase="NEED_SCENE", pending=None, events=[], public_log=[], accepted={}, summary=None)
    state["config"].update(session_id=session_id, maximum_turns=maximum_turns, play_mode="SEPARATE_AGENTS")
    # Character knowledge, next actor, facts and RNG state survive; no reseeding.
    write_json(path, state)
    campaign = Campaign(destination); campaign.export()
    return campaign


class LiveSession:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / "live.json"
        self.campaign = Campaign(root)
        self.data = json.loads(self.path.read_text(encoding="utf-8"))
        require(self.data.get("version") == 1, "Unsupported live checkpoint")
        require(self.data["prompt_version"] == VERSION, "Prompt version changed; explicitly migrate before resuming")

    @classmethod
    def attach(cls, root, limits=None):
        path = Path(root) / "live.json"
        require(not path.exists(), "Live session already exists")
        campaign = Campaign(root)
        require("round_runtime" not in campaign.state, "Use rounds.py for grouped campaigns")
        require(campaign.state["phase"] != "ENDED", "Start a new session from this completed checkpoint")
        settings = {**DEFAULTS, **(limits or {})}
        require(set(settings) == set(DEFAULTS), "Unknown execution limit")
        integer(settings["maximum_attempts"], 1, 3)
        integer(settings["maximum_calls"], 1, 10000)
        integer(settings["maximum_input_characters"], 1000, 1000000)
        integer(settings["maximum_output_tokens"], 100, 32000)
        integer(settings["timeout_seconds"], 1, 120)
        campaign.state["config"]["play_mode"] = "SEPARATE_AGENTS"
        write_json(campaign.path, campaign.state)
        write_json(path, {"version": 1, "prompt_version": VERSION, "limits": settings, "sequence": 0, "calls": 0, "usage": {}, "request": None, "proposal": None, "paused": None, "finish_requested": False, "correction": None, "replies": {}, "audit": []})
        return cls(root)

    def save(self):
        write_json(self.path, self.data)

    def status(self):
        r = self.data["request"]
        return {"campaign": self.campaign.status(), "paused": self.data["paused"], "calls": self.data["calls"], "maximum_calls": self.data["limits"]["maximum_calls"], "usage": self.data["usage"], "pending_agent": r["packet"]["agent_id"] if r else None, "pending_operation": r["packet"]["operation"] if r else None, "proposal_awaiting_review": self.data["proposal"] is not None}

    def context(self, role, operation):
        s = self.campaign.state
        recent = (s.get("prior_public_log", []) + s["public_log"])[-12:]
        if role == "gm":
            value = copy.deepcopy(self.campaign.context("gm"))
            value.update(recent_public_events=recent, previous_session=s.get("previous_session"), correction=self.data["correction"], turns_remaining=s["config"]["maximum_turns"] - s["turn"])
            return value
        if role == "chronicler":
            if operation == "end":
                return {"facts": s["facts"], "public_events": s["public_log"], "turns_completed": s["turn"], "previous_session": s.get("previous_session")}
            pending = copy.deepcopy(s["pending"])
            if pending: pending["action"].pop("intent", None)
            return {"existing_facts": s["facts"], "entities": s["entities"], "proposed_event": self.data["proposal"]["message"]["payload"], "resolved_action": pending, "characters": list(s["characters"])}
        value = copy.deepcopy(self.campaign.context(role))
        known = {f["entity_id"] for f in value["known_facts"]} | {s["location"]}
        value["visible_entities"] = [{k: entity[k] for k in ["id", "name", "type"]} for eid, entity in s["entities"].items() if eid in known]
        value["recent_public_events"] = recent
        # Do not include the full config, previous summary, all entities, or debug logs.
        return value

    def request(self):
        self.recover()
        require(not self.data["paused"], "Live session is paused; inspect status before retrying")
        if self.data["request"]:
            request = self.data["request"]
            require(request["base_hash"] == digest(self.campaign.state), "Campaign changed outside the live runner")
            return copy.deepcopy(request["packet"])
        s = self.campaign.state
        if s["phase"] == "ENDED": return None
        if self.data["proposal"]:
            role, operation = "chronicler", "chronicle"
        elif s["phase"] == "LIMIT_REACHED" or (self.data["finish_requested"] and s["phase"] in ["READY", "NEED_SCENE"]):
            role, operation = "chronicler", "end"
        elif s["phase"] == "NEED_SCENE": role, operation = "gm", "scene"
        elif s["phase"] == "AWAITING_REVIEW": role, operation = "gm", "review"
        elif s["phase"] == "AWAITING_FINAL": role, operation = "gm", "resolve"
        elif s["phase"] == "READY":
            char = list(s["characters"].values())[s["next_actor"]]
            role, operation = char["agent_id"], "action"
        else: raise ProtocolError("Unsupported campaign phase")
        context = self.context(role, operation)
        number = self.data["sequence"] + 1
        identity = digest([s["config"]["campaign_id"], s["config"]["session_id"]])[:12]
        rid = f"rq-{identity}-{number:06}"
        packet = {"request_id": rid, "agent_id": role, "operation": operation, "prompt_version": VERSION, "instructions": prompt(role), "context": context, "response_schema": response_schema(operation, rid, role, context)}
        require(len(json.dumps(packet)) <= self.data["limits"]["maximum_input_characters"], "Agent context exceeds the configured size limit; no request was dispatched")
        self.data["sequence"] = number
        self.data["request"] = {"packet": packet, "base_hash": digest(s), "attempts": 0, "in_flight": False, "reply": None}
        self.save()
        return copy.deepcopy(packet)

    def reserve(self):
        r = self.data["request"]
        require(r is not None and not self.data["paused"], "No active request")
        require(not r["in_flight"], "An attempt is already reserved")
        if self.data["calls"] >= self.data["limits"]["maximum_calls"]:
            self.data["paused"] = {"kind": "call_budget", "message": "Configured call limit reached"}
            self.save()
            raise ProtocolError("Call budget reached; no further calls were made")
        require(r["attempts"] < self.data["limits"]["maximum_attempts"], "Attempt limit reached")
        r["attempts"] += 1; r["in_flight"] = True
        self.data["calls"] += 1
        self.save()  # Persist before an external call; a crash still consumes the attempt.

    def fail(self, reason):
        r = self.data["request"]
        require(r is not None, "No request to fail")
        r["in_flight"] = False
        r["packet"]["validation_feedback"] = reason[:1000]
        self.data["audit"].append({"request_id": r["packet"]["request_id"], "agent_id": r["packet"]["agent_id"], "attempt": r["attempts"], "error": reason[:1000]})
        if r["attempts"] >= self.data["limits"]["maximum_attempts"]:
            self.data["paused"] = {"kind": "attempt_limit", "message": "Three or fewer configured attempts exhausted"}
        self.save()

    def preview(self, operation, payload, mid):
        candidate = copy.copy(self.campaign)
        candidate.state = copy.deepcopy(self.campaign.state)
        getattr(candidate, operation)(payload, mid)

    def submit(self, answer, usage=None, reserved=False):
        self.recover(keep_in_flight=reserved)
        if isinstance(answer, dict) and answer.get("request_id") in self.data["replies"]:
            require(self.data["replies"][answer["request_id"]] == digest(answer), "Accepted reply was changed")
            return {"duplicate": True}
        r = self.data["request"]
        require(r is not None and not self.data["paused"], "No active request")
        require(r["base_hash"] == digest(self.campaign.state), "Stale agent reply: campaign changed")
        require(r["base_hash"] == digest(json.loads(self.campaign.path.read_text())), "Stale agent reply: campaign changed on disk")
        if not reserved: self.reserve()
        require(r["in_flight"], "Attempt must be reserved")
        try:
            require(len(json.dumps(answer)) <= 250000, "Reply exceeds size limit")
            validate(answer, r["packet"]["response_schema"])
            operation = r["packet"]["operation"]
            if operation == "chronicle":
                payload = answer["payload"]
                require(payload["approved"] == (len(payload["conflicts"]) == 0), "Approval and conflict list disagree")
            else:
                self.preview(operation, answer["payload"], r["packet"]["request_id"])
        except ProtocolError as exc:
            self.fail(str(exc))
            raise
        clean_usage = {k: v for k, v in (usage or {}).items() if k in ["input_tokens", "output_tokens", "total_tokens"] and type(v) is int and v >= 0}
        r["reply"] = copy.deepcopy(answer)
        r["usage"] = clean_usage
        r["in_flight"] = False
        self.save()  # Write-ahead reply: recovery can apply it without another model call.
        self.apply_reply()
        return self.status()

    def apply_reply(self):
        r = self.data["request"]
        answer = r["reply"]
        operation = r["packet"]["operation"]
        message = {"message_id": r["packet"]["request_id"], "payload": answer["payload"]}
        if operation in ["scene", "resolve"]:
            self.data["proposal"] = {"operation": operation, "message": message}
            self.data["correction"] = None
        elif operation == "chronicle":
            if answer["payload"]["approved"]:
                proposal = self.data["proposal"]
                self.campaign.submit(proposal["operation"], proposal["message"])
                self.data["proposal"] = None
            else:
                self.data["paused"] = {"kind": "canon_conflict", "message": "Chronicler requested GM correction", "conflicts": answer["payload"]["conflicts"]}
        else:
            self.campaign.submit(operation, message)
        self.data["audit"].append({"request_id": answer["request_id"], "agent_id": answer["agent_id"], "operation": operation, "packet": copy.deepcopy(r["packet"]), "reply": answer, "usage": r.get("usage", {})})
        for key, value in r.get("usage", {}).items(): self.data["usage"][key] = self.data["usage"].get(key, 0) + value
        self.data["replies"][answer["request_id"]] = digest(answer)
        self.data["request"] = None
        self.save()

    def recover(self, keep_in_flight=False):
        r = self.data["request"]
        if r and r["reply"] is not None:
            self.apply_reply()
        elif r and r["in_flight"] and not keep_in_flight:
            self.fail("Previous model call was interrupted; any provider cost may already have occurred")

    def retry(self):
        require(self.data["paused"] is not None, "Session is not paused")
        kind = self.data["paused"]["kind"]
        require(kind != "call_budget", "Call budget is exhausted; inspect and explicitly configure a new budget")
        if kind == "canon_conflict":
            self.data["correction"] = {"rejected_proposal": self.data["proposal"], "conflicts": self.data["paused"]["conflicts"]}
            self.data["proposal"] = None
        else:
            self.data["request"]["attempts"] = 0
        self.data["paused"] = None
        self.save()

    def step(self, provider):
        packet = self.request()
        if packet is None: return False
        self.reserve()
        try:
            answer, usage = provider.complete(packet)
        except ProviderError as exc:
            self.fail(str(exc))
            return True
        try:
            self.submit(answer, usage=usage, reserved=True)
        except ProtocolError:
            # Validation failure is already durable; next request contains feedback.
            if self.data["request"] and self.data["request"]["in_flight"]:
                self.fail("Invalid response; inspect the current phase")
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", default="runs/live-session")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--config", default=str(ROOT / "config/tavern-zero.json"))
    init.add_argument("--from-checkpoint")
    init.add_argument("--session-id", default="session-0002")
    init.add_argument("--max-turns", type=int, default=100)
    init.add_argument("--max-calls", type=int, default=600)
    for name in ["status", "finish", "retry"]: sub.add_parser(name)
    request = sub.add_parser("request"); request.add_argument("--output")
    reply = sub.add_parser("reply"); reply.add_argument("file")
    run = sub.add_parser("run")
    run.add_argument("--steps", type=int, default=1)
    run.add_argument("--models", default=str(ROOT / "config/live-models.json"))
    args = parser.parse_args()
    try:
        with campaign_lock(args.campaign):
            if args.command == "init":
                if args.from_checkpoint:
                    continue_campaign(args.from_checkpoint, args.campaign, args.session_id, args.max_turns)
                else:
                    config = json.loads(Path(args.config).read_text())
                    config.update(session_id=args.session_id, maximum_turns=args.max_turns, play_mode="SEPARATE_AGENTS")
                    Campaign.create(args.campaign, config)
                live = LiveSession.attach(args.campaign, {"maximum_calls": args.max_calls})
                result = live.status()
            else:
                live = LiveSession(args.campaign)
                live.recover()
                if args.command == "request":
                    result = live.request()
                    if args.output: write_json(args.output, result)
                elif args.command == "reply":
                    raw = Path(args.file).read_text()
                    try: answer = json.loads(raw)
                    except ValueError:
                        live.reserve(); live.fail("Response is not valid JSON")
                        raise ProtocolError("Response is not valid JSON") from None
                    result = live.submit(answer)
                elif args.command == "finish":
                    live.data["finish_requested"] = True; live.save(); result = live.status()
                elif args.command == "retry":
                    live.retry(); result = live.status()
                elif args.command == "run":
                    integer(args.steps, 1, 10000)
                    env_names = json.loads(Path(args.models).read_text())
                    roles = {"gm", "chronicler"} | {c["agent_id"] for c in live.campaign.state["characters"].values()}
                    require(set(env_names) == roles, "Model config must map exactly the campaign roles to environment variable names")
                    models = {role: os.environ.get(env_name, "") for role, env_name in env_names.items()}
                    limits = live.data["limits"]
                    provider = ResponsesProvider(models, timeout=limits["timeout_seconds"], max_output_tokens=limits["maximum_output_tokens"])
                    for _ in range(args.steps):
                        if live.data["paused"] or not live.step(provider): break
                    result = live.status()
                else: result = live.status()
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ProtocolError, ProviderError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
