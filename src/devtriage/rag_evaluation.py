"""Retrieval-only ablation: expected IDs never reach retrieval or model tools."""
import json
import time
from pathlib import Path
from .knowledge import KnowledgeSearch, KnowledgeArgs


async def evaluate_retrieval(settings, dataset: Path):
    rows = json.loads(dataset.read_text(encoding="utf-8"))
    if not rows:
        raise ValueError("Empty retrieval dataset")
    modes = {}
    for mode in ("keyword", "dense", "hybrid"):
        items = []
        for row in rows:
            start = time.monotonic()
            result = await KnowledgeSearch(settings, row.get("repository", "global")).search(
                KnowledgeArgs(query=row["query"], component=row.get("component"),
                              version=row.get("version"), mode=mode))
            found = list(dict.fromkeys(m["reference"]["document_id"] for m in result["matches"]))
            expected = set(row["expected"])
            rank = next((i for i, doc in enumerate(found,1) if doc in expected), None)
            items.append({"id": row["id"], "requested_mode": mode, "actual_mode": result["mode"],
                          "found": found, "recall_at_5": len(expected.intersection(found))/len(expected) if expected else None,
                          "mrr": 1/rank if rank else 0 if expected else None,
                          "abstention": not found if not expected else None,
                          "warning": result.get("warning"), "seconds": round(time.monotonic()-start,4)})
        averages = {}
        for metric in ("recall_at_5", "mrr", "abstention"):
            values = [i[metric] for i in items if i[metric] is not None]
            averages[metric] = sum(values)/len(values) if values else None
        available = all(i["actual_mode"] in {mode, "not_needed"} for i in items)
        modes[mode] = {"averages": averages if available else None, "items": items,
                       "fallback_averages": averages if not available else None,
                       "fully_available": available}
    result = {"dataset": dataset.name, "scope": "retrieval smoke/development set; not diagnosis accuracy", "modes": modes}
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "retrieval-latest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
