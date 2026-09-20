"""Authorized, bounded memory projections. Complete records remain in checkpoint."""
import re

from ttrpg import require


def character_for(state, role):
    return next((c for c in state["characters"].values() if c["agent_id"] == role), None)


def allowed_facts(state, role):
    char = character_for(state, role)
    require(char is not None or role in ["gm", "chronicler"], "Unknown memory audience")
    ids = set(char["knowledge"]) if char else set(state["facts"])
    return [f for fid, f in state["facts"].items() if fid in ids]


def compact_fact(fact, state=None, role=None):
    value = {k: fact[k] for k in ["id", "statement", "classification", "source", "entity_id"]}
    if state is not None and role in ["gm", "chronicler"]:
        value["known_by"] = [cid for cid, c in state["characters"].items() if fact["id"] in c["knowledge"]]
    return value


def recall(state, role, query, limit=8):
    # Filter before search: even a guessed hidden ID returns nothing to a player.
    words = set(re.findall(r"[\w-]+", query.casefold()))
    scored = []
    for i, f in enumerate(allowed_facts(state, role)):
        haystack = " ".join(str(f[k]) for k in ["id", "statement", "source", "entity_id"]).casefold()
        score = sum(word in haystack for word in words)
        if score: scored.append((score, i, f))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return {"query": query, "facts": [compact_fact(x[2], state, role) for x in scored[:limit]], "more_matches": max(0, len(scored) - limit)}


def context(state, role):
    char = character_for(state, role)
    facts = allowed_facts(state, role)
    recent = (state.get("prior_public_log", []) + state["public_log"])[-3:]
    relevant = {state["location"]}
    for event in recent:
        for key in ["location", "target"]:
            if event.get(key): relevant.add(event[key])
    ranked = sorted(enumerate(facts), key=lambda x: (x[1]["entity_id"] in relevant, x[0]), reverse=True)
    cap = 6 if char else 12
    chosen = [compact_fact(f, state, role) for _, f in ranked[:cap]]
    entities = {f["entity_id"] for f in facts} | {state["location"]}
    if not char: entities = set(state["entities"])
    index = [{k: e[k] for k in ["id", "name", "type"]} for eid, e in state["entities"].items() if eid in entities]
    public = []
    for e in recent:
        item = {"text": e.get("text", "")[-1000:]}
        if e.get("kind") == "round":
            item["declarations"] = [{k: a[k] for k in ["character_id", "speech", "action"]} for a in e["declarations"]]
        else:
            item.update({k: e[k] for k in ["actor", "speech", "action"] if k in e})
        public.append(item)
    result = {"location": state["location"], "scene": state["scene"][-1400:], "facts": chosen,
              "older_facts_available": max(0, len(facts) - len(chosen)), "entities": index,
              "recent_public_events": public}
    if char:
        result["character"] = {k: v for k, v in char.items() if k not in ["knowledge", "agent_id"]}
        result["journal"] = state.get("role_journals", {}).get(role, {"goal": char["goal"], "notes": [], "questions": []})
    elif role == "gm":
        result["party"] = [{k: c[k] for k in ["id", "name", "skills", "conditions"]} for c in state["characters"].values()]
        result["notebook"] = state.get("role_journals", {}).get("gm", {"goal": "", "notes": [], "questions": []})
    return result
