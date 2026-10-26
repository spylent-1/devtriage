import argparse
import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from .config import Settings, LAB
from .models import DiagnosisRequest
from .agent import diagnose
from .store import Store
from .process import run, executable


async def doctor(settings):
    from .telemetry import Telemetry
    checks = {name: bool(executable(name)) for name in ("python", "rg", "docker")}
    checks["model_key_configured"] = bool(settings.api_key())
    checks["rag_enabled"] = settings.rag_enabled
    checks["rag_backend"] = settings.rag_backend
    checks["embedding_configured"] = bool(settings.embedding_base_url and settings.embedding_model)
    telemetry = Telemetry()
    checks["langfuse_configured"] = bool(telemetry.client)
    if checks["docker"]:
        try:
            checks["docker_engine"] = (await run(["docker", "info"], timeout=15))["returncode"] == 0
            checks["compose"] = (await run(["docker", "compose", "version"], timeout=15))["returncode"] == 0
        except Exception:
            checks["docker_engine"] = False
    checks["lab_source"] = (LAB / "pom.xml").exists()
    return checks


async def dispatch(args):
    settings = Settings()
    if args.command == "doctor":
        value = await doctor(settings)
    elif args.command == "diagnose":
        value = (await diagnose(DiagnosisRequest(repo=args.repo, log=args.log, verify=args.verify, knowledge_repository=args.knowledge_repo), settings)).model_dump()
    elif args.command == "knowledge":
        from .knowledge import ingest, KnowledgeSearch, KnowledgeArgs
        if args.action == "index":
            value = await ingest(settings, Path(args.source), args.corpus)
        elif args.action == "search":
            value = await KnowledgeSearch(settings, args.repository).search(KnowledgeArgs(
                query=args.query, component=args.component, version=args.version, mode=args.mode, top_k=args.top_k))
        else:
            from .rag_evaluation import evaluate_retrieval
            value = await evaluate_retrieval(settings, Path(args.dataset))
    elif args.command == "report":
        value = Store(settings.data_dir).report(args.run_id)
    elif args.command == "eval":
        from .evaluation import evaluate
        value = await evaluate(settings, args.dataset, args.judge, args.langfuse, args.verify, args.resume)
    else:
        from .lab import compose, reproduce, verify_case
        if args.action == "reproduce":
            value = await reproduce(args.case_id)
        elif args.action == "verify":
            value = (await verify_case(args.case_id)).model_dump()
        elif args.action == "up":
            value = await compose("up", "-d", "--build", "--wait", timeout=600)
        elif args.action == "reset":
            # Reset application data only, keep containers/volumes and Maven cache.
            db = await compose("exec", "-T", "mysql", "mysql", "-ulab", "-plab-local-only", "orders", "-e", "DELETE FROM orders;")
            cache = await compose("exec", "-T", "redis", "redis-cli", "FLUSHDB")
            value = {"mysql": db, "redis": cache}
        else:
            value = await compose("down")
    print(json.dumps(value, ensure_ascii=False, indent=2))
    if isinstance(value, dict) and (value.get("returncode", 0) != 0 or value.get("reproduced") is False):
        return 1
    if args.command == "diagnose" and value["symptom"] in {"诊断未完成", "任务中断"}:
        return 1
    return 0


def main():
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="DevTriage Java 诊断 Agent")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    d = sub.add_parser("diagnose")
    d.add_argument("--repo", required=True)
    d.add_argument("--log", required=True)
    d.add_argument("--verify", choices=["none", "lab"], default="none")
    d.add_argument("--knowledge-repo", help="Knowledge repository namespace; defaults to repo directory name")
    k = sub.add_parser("knowledge").add_subparsers(dest="action", required=True)
    ki = k.add_parser("index")
    ki.add_argument("--source", required=True, help="Explicit curated JSON corpus (replaces this corpus atomically)")
    ki.add_argument("--corpus", default="default")
    ks = k.add_parser("search")
    ks.add_argument("query")
    ks.add_argument("--repository", default="global")
    ks.add_argument("--component")
    ks.add_argument("--version")
    ks.add_argument("--mode", choices=["keyword", "dense", "hybrid"], default="hybrid")
    ks.add_argument("--top-k", type=int, choices=range(1,11), default=5)
    ke = k.add_parser("eval")
    ke.add_argument("--dataset", default="evals/retrieval.json")
    r = sub.add_parser("report")
    r.add_argument("run_id")
    e = sub.add_parser("eval")
    e.add_argument("--dataset", choices=["baseline"], default="baseline")
    e.add_argument("--judge", action="store_true")
    e.add_argument("--resume", action="store_true", help="Continue completed checkpoint items without paying twice")
    e.add_argument("--langfuse", action="store_true", help="Upload dataset and run cloud experiment")
    e.add_argument("--verify", choices=["none", "lab"], default="none")
    lab = sub.add_parser("lab").add_subparsers(dest="action", required=True)
    for name in ("up", "down", "reset"):
        lab.add_parser(name)
    for name in ("reproduce", "verify"):
        lab.add_parser(name).add_argument("case_id", choices=["case-1", "case-2", "case-3"])
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # Third-party HTTP logs can contain endpoints. Keep them quiet.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        raise SystemExit(asyncio.run(dispatch(parser.parse_args())))
    except (ValueError, OSError, TimeoutError) as exc:
        from .redaction import redact
        parser.exit(1, redact(str(exc))+"\n")


if __name__ == "__main__":
    main()
