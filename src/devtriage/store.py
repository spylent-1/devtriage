import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .redaction import redact, redact_data


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(root / "tasks.sqlite3")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, state TEXT, request TEXT, report TEXT);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, run_id TEXT, time TEXT, kind TEXT, payload TEXT);
        """)
        self.db.commit()

    def start(self, run_id, request):
        self.db.execute("INSERT INTO runs VALUES(?,?,?,NULL)", (run_id, "running", request.model_dump_json()))
        self.db.commit()

    def event(self, run_id, kind, payload):
        self.db.execute("INSERT INTO events(run_id,time,kind,payload) VALUES(?,?,?,?)", (
            run_id, datetime.now(timezone.utc).isoformat(), kind,
            json.dumps(redact_data(payload), ensure_ascii=False, default=str)))
        self.db.commit()

    def finish(self, report, state="completed"):
        value = report.model_dump_json(indent=2)
        self.db.execute("UPDATE runs SET state=?,report=? WHERE id=?", (state, value, report.run_id))
        self.db.commit()
        folder = self.root / report.run_id
        folder.mkdir(exist_ok=True)
        (folder / "report.json").write_text(value, encoding="utf-8")
        body = [f"# DevTriage {report.run_id}", f"状态：{report.status}", report.symptom,
                "## 根因", report.root_cause, f"位置：{report.location}", "## 修复建议",
                *[f"- {x}" for x in report.suggestions], "## 证据缺口", *[f"- {x}" for x in report.gaps], "## 验证"]
        body += [f"- {v.case_id}: reproduced={v.reproduced}, healthy={v.healthy_control}; {v.detail}" for v in report.verification]
        body += ["## 证据"]
        for e in report.evidence:
            body += [f"### {e.id} {e.path}:{e.start}-{e.end}", f"SHA256: {e.sha256}", "```text", e.text, "```"]
        body += ["## 历史知识参考（不代表当前故障已验证）"]
        for k in report.knowledge:
            body += [f"### {k.id} {k.title}", f"来源：{k.source}；版本：{k.revision}；行：{k.start}-{k.end}",
                     f"SHA256: {k.sha256}", "```text", k.text, "```"]
        (folder / "report.md").write_text("\n\n".join(body), encoding="utf-8")

    def state(self, run_id, state):
        self.db.execute("UPDATE runs SET state=? WHERE id=?", (state, run_id))
        self.db.commit()

    def report(self, run_id):
        row = self.db.execute("SELECT state,report FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise ValueError("Unknown run_id")
        return {"state": row[0], "report": json.loads(row[1]) if row[1] else None}
