"""Small strict schema vocabulary shared by the relay, API and validator."""
import copy
from ttrpg import ProtocolError, require


def obj(**properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def arr(items):
    return {"type": "array", "items": items, "maxItems": 200}


TEXT = {"type": "string", "maxLength": 20000}
BOOL = {"type": "boolean"}
ENTITY = obj(id=TEXT, name=TEXT, type={"type": "string", "enum": ["LOCATION", "NPC", "OBJECT", "FACTION"]}, undefined_fields=arr(TEXT))
FACT = obj(id=TEXT, statement=TEXT, classification={"type": "string", "enum": ["CANON", "SECRET_CANON", "RUMOR", "CHARACTER_BELIEF"]}, source=TEXT, entity_id=TEXT)
GRANT = obj(character_id=TEXT, fact_id=TEXT)
RECORDS = dict(entities=arr(ENTITY), facts=arr(FACT), grants=arr(GRANT))
SCHEMAS = {
    "scene": obj(narration=TEXT, location=TEXT, **RECORDS),
    "action": obj(character_id=TEXT, speech=TEXT, action=TEXT, intent=TEXT, target={"type": ["string", "null"]}),
    "review": obj(roll={"anyOf": [{"type": "null"}, obj(skill=TEXT, difficulty={"type": "integer", "minimum": 1, "maximum": 30}, advantage=BOOL, disadvantage=BOOL, reason=TEXT)]}),
    "resolve": obj(narration=TEXT, outcome={"type": "string", "enum": ["NO_ROLL", "SUCCESS", "FAILURE"]}, **RECORDS, scene_finished=BOOL),
    "chronicle": obj(approved=BOOL, conflicts=arr(obj(fact_id=TEXT, reason=TEXT))),
    "end": obj(summary=TEXT, source_fact_ids=arr(TEXT), next_hook=TEXT),
}


def response_schema(operation, request_id, agent_id, context):
    payload = copy.deepcopy(SCHEMAS[operation])
    if operation == "action":
        payload["properties"]["character_id"] = {"type": "string", "enum": [context["character"]["id"]]}
        payload["properties"]["target"]["enum"] = [None] + [e["id"] for e in context["visible_entities"]]
    return obj(request_id={"type": "string", "enum": [request_id]}, agent_id={"type": "string", "enum": [agent_id]}, payload=payload)


def validate(value, schema, path="$", depth=0):
    """Validate exactly the subset emitted above. Reject before state mutation."""
    require(depth < 30, "Response nesting is too deep")
    if "anyOf" in schema:
        for option in schema["anyOf"]:
            try:
                validate(value, option, path, depth + 1)
                return
            except ProtocolError:
                pass
        raise ProtocolError(path + ": no matching permitted type")
    types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
    actual = "null" if value is None else "boolean" if type(value) is bool else "integer" if type(value) is int else "string" if isinstance(value, str) else "array" if isinstance(value, list) else "object" if isinstance(value, dict) else "unsupported"
    require(actual in types, path + ": invalid type")
    if "enum" in schema: require(value in schema["enum"], path + ": value is not allowed")
    if actual == "object":
        require(set(value) == set(schema["required"]), path + ": missing or extra fields")
        for key, item in value.items(): validate(item, schema["properties"][key], path + "." + key, depth + 1)
    elif actual == "array":
        require(len(value) <= schema.get("maxItems", 200), path + ": too many items")
        for i, item in enumerate(value): validate(item, schema["items"], f"{path}[{i}]", depth + 1)
    elif actual == "string":
        require(len(value) <= schema.get("maxLength", 20000), path + ": text too long")
    elif actual == "integer":
        require(schema.get("minimum", value) <= value <= schema.get("maximum", value), path + ": out of range")
