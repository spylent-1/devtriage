import json
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from .config import PROJECT, LAB
from .models import VerificationResult
from .process import run

COMPOSE = PROJECT / "lab" / "compose.yaml"
CASES = {"case-1": ("NullPointerException", "checkout"), "case-2": ("DuplicateKeyException", "create"),
         "case-3": ("SerializationException", "cache")}


async def compose(*args, timeout=180):
    return await run(["docker", "compose", "-f", str(COMPOSE), *args], timeout=timeout)


def validate_xml(xml: str, case_id: str):
    root = ET.fromstring(xml)
    n = case_id[-1]
    tests = {t.attrib.get("name"): t for t in root.iter("testcase")}
    def passed(name):
        t = tests.get(name)
        return t is not None and all(t.find(tag) is None for tag in ("failure", "error", "skipped"))
    text = "\n".join(root.itertext())
    exception, method = CASES[case_id]
    reproduced = passed("scenario"+n) and exception in text and f"OrderService.{method}(OrderService.java:" in text
    return reproduced, passed("control"+n)


async def verify_case(case_id):
    if case_id not in CASES:
        raise ValueError("Unknown lab case")
    # A fresh named test container and fresh output directory avoid stale XML acceptance.
    token = uuid.uuid4().hex[:12]
    container = "devtriage-test-"+token
    directory = "/results/"+token
    try:
        result = await compose("run", "--name", container, "tests", f"-Dlab.build.dir={directory}",
                               f"-Dtest=LabTest#scenario{case_id[-1]}+control{case_id[-1]}", "test", timeout=180)
        # Copy only this execution's XML into a unique local directory.
        output = PROJECT / ".devtriage" / "lab" / token
        output.mkdir(parents=True, exist_ok=True)
        copied = await run(["docker", "cp", f"{container}:{directory}/surefire-reports/TEST-dev.triage.lab.LabTest.xml", str(output / "result.xml")])
        (output / "execution.log").write_text(result["output"], encoding="utf-8")
        reproduced = healthy = False
        if result["returncode"] == 0 and copied["returncode"] == 0:
            reproduced, healthy = validate_xml((output / "result.xml").read_text(encoding="utf-8"), case_id)
        detail = f"JUnit XML + expected stack + assertions; artifacts={output}; exit={result['returncode']}"
        return VerificationResult(case_id=case_id, reproduced=reproduced, healthy_control=healthy, detail=detail)
    finally:
        # Remove only the uniquely named container; never remove business volumes here.
        try:
            await run(["docker", "rm", "-f", container], timeout=15)
        except Exception:
            pass


async def reproduce(case_id):
    if case_id not in CASES:
        raise ValueError("Unknown lab case")
    import urllib.request
    import urllib.error
    import asyncio
    from datetime import datetime, timezone
    since = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    business_no = "incident-"+uuid.uuid4().hex[:12]
    def request(method, suffix):
        try:
            with urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18080/orders/"+business_no+suffix, method=method), timeout=15) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
    if case_id == "case-2":
        await asyncio.to_thread(request, "POST", "")
    status = await asyncio.to_thread(request, "POST" if case_id == "case-2" else "GET", "/cache" if case_id == "case-3" else "")
    logs = await compose("logs", "--no-color", "--since", since, "app")
    output = PROJECT / ".devtriage" / "incidents" / (business_no+".log")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(logs["output"], encoding="utf-8")
    return {"http_status": status, "log": str(output), "case_id": case_id}
