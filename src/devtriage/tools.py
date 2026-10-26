import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Protocol
from pydantic import Field
from tree_sitter import Language, Parser
import tree_sitter_java
from .models import StrictModel, EvidenceRef, ToolResult
from .logs import parse_log
from .redaction import redact
from .process import run
from .config import LAB

PROTECTED_PARTS = {".git", ".env", ".devtriage", "target", "node_modules", ".venv", "test", "tests", "evals"}


class Empty(StrictModel):
    pass


class SearchArgs(StrictModel):
    query: str = Field(min_length=1, max_length=200)


class FileArgs(StrictModel):
    path: str
    start: int = Field(default=1, ge=1)
    end: int = Field(default=80, ge=1)


class SymbolArgs(StrictModel):
    path: str
    symbol: str = Field(min_length=1)


class ConfigArgs(StrictModel):
    path: str


class TestArgs(StrictModel):
    case_id: str = Field(pattern=r"^case-[123]$")


class CodeSearch(Protocol):
    async def search(self, query: str) -> dict: ...


class Repository:
    def __init__(self, root: Path, log: Path):
        self.root, self.log = root.resolve(strict=True), log.resolve(strict=True)
        if not self.root.is_dir() or not self.log.is_file():
            raise ValueError("Expected repository directory and log file")
        self.evidence: dict[str, EvidenceRef] = {}

    def path(self, relative: str) -> Path:
        p = (self.root / relative).resolve(strict=True)
        if not p.is_relative_to(self.root) or not p.is_file():
            raise ValueError("Path outside repository or not a file")
        parts = p.relative_to(self.root).parts
        if any(x.lower() in PROTECTED_PARTS or x.lower().startswith(".env.") for x in parts):
            raise ValueError("Protected path")
        if p.suffix.lower() not in {".java", ".xml", ".yml", ".yaml", ".properties", ".gradle", ".txt", ".log", ".sql"}:
            raise ValueError("Unsupported source/config file")
        return p

    def read(self, path: Path, start=1, end=80, kind="source") -> dict:
        if path.stat().st_size > 2_000_000:
            raise ValueError("File too large; supply a smaller log/source file")
        raw = path.read_bytes()
        lines = raw.decode("utf-8", errors="replace").splitlines()
        if end < start or start > len(lines) or end-start >= 200:
            raise ValueError("Invalid line range (maximum 200 lines)")
        end = min(end, len(lines))
        label = "@log" if kind == "log" else path.relative_to(self.root).as_posix()
        digest = hashlib.sha256(raw).hexdigest()
        eid = hashlib.sha256(f"{label}:{start}:{end}:{digest}".encode()).hexdigest()[:16]
        evidence = EvidenceRef(id=eid, path=label, start=start, end=end, sha256=digest,
                               text=redact("\n".join(lines[start-1:end])), kind=kind)
        self.evidence[eid] = evidence
        return evidence.model_dump()

    def validate(self, ids: list[str]) -> list[EvidenceRef]:
        result = []
        for eid in ids:
            if eid not in self.evidence:
                raise ValueError(f"Unknown evidence: {eid}")
            e = self.evidence[eid]
            path = self.log if e.kind == "log" else self.path(e.path)
            if hashlib.sha256(path.read_bytes()).hexdigest() != e.sha256:
                raise ValueError(f"Stale evidence: {eid}")
            result.append(e)
        return result

    async def search(self, query: str) -> dict:
        rg = shutil.which("rg")
        if not rg:
            raise ValueError("ripgrep missing; install rg and add to PATH")
        exclusions = [arg for part in sorted(PROTECTED_PARTS)
                      for arg in ("--glob", f"!**/{part}/**")]
        result = await run([rg, "--json", "--fixed-strings", "--max-count", "30",
                            "--glob", "*.java", "--glob", "*.xml", "--glob", "*.properties",
                            "--glob", "*.yml", "--glob", "*.yaml", "--glob", "!target/**",
                            "--glob", "*.sql",
                            *exclusions, "--glob", "!**/.env.*", "--", query, "."], cwd=self.root)
        if result["returncode"] not in (0, 1):
            raise ValueError("ripgrep failed")
        hits = []
        for line in result["output"].splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item["type"] == "match":
                d = item["data"]
                try:
                    p = self.path(d["path"]["text"])
                    hit = self.read(p, d["line_number"], d["line_number"])
                except (ValueError, OSError):
                    # A protected, vanished, or unreadable match must not discard
                    # valid evidence from the rest of the repository.
                    continue
                hits.append(hit)
                if len(hits) == 30:
                    break
        return {"matches": hits, "narrow_query": len(hits) == 30}


class ToolRegistry:
    SPECS = {
        "parse_java_log": (Empty, "Parse supplied Java exception log; return exception chain, frames and log evidence."),
        "search_code": (SearchArgs, "Search repository source/config with literal ripgrep query. Narrow broad queries."),
        "read_file": (FileArgs, "Read complete numbered source lines; returns evidence ID and file fingerprint."),
        "inspect_java_symbol": (SymbolArgs, "Parse Java AST and locate a class, method or constructor by name."),
        "read_project_config": (ConfigArgs, "Read redacted Maven or Spring configuration."),
        "run_lab_test": (TestArgs, "Run registered isolated lab case (case-1/2/3); unavailable outside approved lab mode."),
    }

    def __init__(self, repo: Repository, verify="none"):
        self.repo, self.verify = repo, verify
        self.verification = []
        self.specs = dict(self.SPECS)
        self.handlers = {}

    def register(self, name, schema, description, handler):
        """Trusted application extension point; never exposed as an LLM tool."""
        if name in self.specs or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name):
            raise ValueError("Duplicate or invalid tool name")
        if not issubclass(schema, StrictModel):
            raise ValueError("Tool parameters must use StrictModel")
        self.specs[name] = (schema, description)
        self.handlers[name] = handler

    def schemas(self):
        return [{"type": "function", "function": {"name": name, "description": desc,
                "parameters": schema.model_json_schema()}} for name, (schema, desc) in self.specs.items()
                if name != "run_lab_test" or (self.verify == "lab" and self.repo.root == LAB.resolve())]

    async def execute(self, name, arguments):
        try:
            if name not in self.specs:
                raise ValueError("Unknown tool")
            args = self.specs[name][0].model_validate(arguments)
            if name in self.handlers:
                data = await self.handlers[name](args)
            elif name == "parse_java_log":
                if self.repo.log.stat().st_size > 2_000_000:
                    raise ValueError("Log exceeds 2 MB")
                text = self.repo.log.read_text(encoding="utf-8", errors="replace")
                data = parse_log(redact(text))
                data["evidence"] = self.repo.read(self.repo.log, 1, min(200, len(text.splitlines())), "log") if text else None
            elif name == "search_code":
                data = await self.repo.search(args.query)
            elif name == "read_file":
                data = self.repo.read(self.repo.path(args.path), args.start, args.end)
            elif name == "read_project_config":
                p = self.repo.path(args.path)
                if p.suffix not in {".xml", ".properties", ".yaml", ".yml", ".gradle", ".sql"}:
                    raise ValueError("Expected project config")
                data = self.repo.read(p, 1, 200, "config")
            elif name == "inspect_java_symbol":
                p = self.repo.path(args.path)
                if p.suffix != ".java" or p.stat().st_size > 2_000_000:
                    raise ValueError("Expected Java source under 2 MB")
                raw = p.read_bytes()
                tree = Parser(Language(tree_sitter_java.language())).parse(raw)
                symbols = []
                def visit(node):
                    if node.type in {"class_declaration", "method_declaration", "constructor_declaration", "interface_declaration"}:
                        n = node.child_by_field_name("name")
                        if n and raw[n.start_byte:n.end_byte].decode() == args.symbol:
                            start, end = node.start_point.row+1, node.end_point.row+1
                            symbols.append({"kind": node.type, "start": start, "end": end,
                                            "evidence": self.repo.read(p, start, min(end, start+199))})
                    for child in node.children:
                        visit(child)
                visit(tree.root_node)
                data = {"symbols": symbols, "parse_errors": tree.root_node.has_error}
            else:
                if self.verify != "lab" or self.repo.root != LAB.resolve():
                    raise ValueError("Test execution is restricted to the bundled lab")
                from .lab import verify_case
                verified = await verify_case(args.case_id)
                self.verification.append(verified)
                data = verified.model_dump()
            return ToolResult(ok=True, data=data)
        except Exception as exc:
            return ToolResult(ok=False, error=redact(f"{type(exc).__name__}: {exc}"))
