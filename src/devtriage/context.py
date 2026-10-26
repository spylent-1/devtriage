import copy
import json


def compact(messages, budget):
    """Preserve protocol and goals; replace old tool payloads with evidence handles."""
    result = copy.deepcopy(messages)
    for message in result[2:-4]:
        if len(json.dumps(result, ensure_ascii=False)) <= budget:
            break
        if message.get("role") == "tool" and len(message.get("content", "")) > 500:
            import re
            ids = re.findall(r'"id":\s*"((?:kb-)?[a-f0-9]{16,24})"', message["content"])
            message["content"] = json.dumps({"omitted": True, "evidence_ids": ids,
                "note": "Full observation saved in SQLite; reread source if needed."})
    if len(json.dumps(result, ensure_ascii=False)) > budget:
        raise ValueError("Context budget exceeded; stop with partial report")
    return result
