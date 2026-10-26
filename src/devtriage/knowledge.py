"""Versioned incident knowledge, BM25/dense retrieval and validated citations.

Knowledge is untrusted reference material, never current incident evidence.
SQLite uses exact cosine in-process; PostgreSQL uses pgvector exact cosine SQL.
"""
import hashlib
import json
import math
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import Field
from .models import StrictModel, KnowledgeRef
from .redaction import redact


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class Document(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    title: str = Field(min_length=1, max_length=300)
    source: str = Field(min_length=1, max_length=1000)
    revision: str = Field(min_length=1, max_length=100)
    repository: str = Field(default="global", min_length=1, max_length=100)
    component: str = Field(min_length=1, max_length=100)
    versions: list[str] = Field(default_factory=list, max_length=30)
    kind: Literal["runbook", "postmortem", "fix"] = "runbook"
    content: str = Field(min_length=1, max_length=100000)


class KnowledgeArgs(StrictModel):
    query: str = Field(min_length=1, max_length=500)
    component: str | None = Field(default=None, max_length=100)
    version: str | None = Field(default=None, max_length=100)
    mode: Literal["keyword", "hybrid", "dense"] = "hybrid"
    top_k: int = Field(default=5, ge=1, le=10)


def tokenize(text):
    # Preserve exception/config identifiers; CJK bigrams allow Chinese queries
    # without a heavyweight tokenizer or an English-only FTS configuration.
    tokens = re.findall(r"[a-z0-9_]+", text.lower())
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        tokens.extend(run[i:i+2] for i in range(len(run)-1))
        if len(run) == 1:
            tokens.append(run)
    return tokens


def bm25(query, texts):
    docs = [Counter(tokenize(t)) for t in texts]
    lengths = [sum(d.values()) for d in docs]
    average = sum(lengths) / max(len(docs), 1) or 1
    result = [0.0] * len(docs)
    for token in set(tokenize(query)):
        frequency = sum(token in doc for doc in docs)
        idf = math.log(1 + (len(docs)-frequency+0.5)/(frequency+0.5))
        for i, doc in enumerate(docs):
            tf = doc[token]
            result[i] += idf * tf * 2.2 / (tf + 1.2*(0.25+0.75*lengths[i]/average))
    return result


def vector_checked(vector, dimensions=None):
    if not isinstance(vector, list) or not vector or len(vector) > 16000:
        raise ValueError("Invalid embedding vector")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in vector):
        raise ValueError("Embedding contains invalid numbers")
    if not any(vector) or (dimensions is not None and len(vector) != dimensions):
        raise ValueError("Embedding dimension mismatch or zero vector")
    return [float(x) for x in vector]


class Embeddings:
    def __init__(self, settings):
        self.url = settings.embedding_base_url
        self.model = settings.embedding_model
        self.key = settings.embedding_api_key
        if bool(self.url) != bool(self.model):
            raise ValueError("Configure both EMBEDDING_BASE_URL and EMBEDDING_MODEL")
        if self.url:
            parsed = urlsplit(self.url)
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("Embedding endpoint must not contain credentials, query or fragment")
            if not parsed.hostname or not (parsed.scheme == "https" or
                    (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"})):
                raise ValueError("Embedding endpoint requires HTTPS or loopback HTTP")
        self.fingerprint = digest([self.url, self.model]) if self.url else "none"

    @property
    def available(self):
        return bool(self.url and self.model)

    async def encode(self, texts):
        if not self.available:
            raise ValueError("Embedding endpoint/model not configured")
        headers = {"Authorization": "Bearer " + self.key.get_secret_value()} if self.key else {}
        result = []
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            for offset in range(0, len(texts), 32):
                batch = texts[offset:offset+32]
                try:
                    response = await client.post(self.url.rstrip("/")+"/embeddings", headers=headers,
                                                 json={"model": self.model, "input": batch})
                    response.raise_for_status()
                    data = response.json()["data"]
                    data = sorted(data, key=lambda row: row["index"])
                    if [r["index"] for r in data] != list(range(len(batch))):
                        raise ValueError("Embedding response count/index mismatch")
                    result.extend(vector_checked(r["embedding"]) for r in data)
                except (httpx.HTTPError, KeyError, TypeError) as exc:
                    # Never include endpoint credentials, response body or submitted texts.
                    raise ValueError("Embedding request failed: " + type(exc).__name__) from None
        dimensions = len(result[0])
        return [vector_checked(v, dimensions) for v in result]


class KnowledgeStore:
    def __init__(self, settings):
        self.pg = settings.rag_backend == "postgres"
        if settings.rag_backend not in {"sqlite", "postgres"}:
            raise ValueError("RAG backend must be sqlite or postgres")
        if self.pg:
            if not settings.rag_dsn:
                raise ValueError("Configure DEVTRIAGE_RAG_DSN")
            try:
                import psycopg
                self.db = psycopg.connect(settings.rag_dsn.get_secret_value(), connect_timeout=5)
                self.db.execute("CREATE EXTENSION IF NOT EXISTS vector")
                self.db.execute("CREATE TABLE IF NOT EXISTS dt_knowledge (id TEXT PRIMARY KEY, corpus TEXT NOT NULL, payload TEXT NOT NULL, model TEXT NOT NULL, embedding vector)")
                self.db.commit()
            except Exception:
                raise ValueError("PostgreSQL knowledge store unavailable; install .[rag-postgres] and check service/extension") from None
        else:
            settings.data_dir.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(settings.data_dir / "knowledge.sqlite3")
            self.db.execute("CREATE TABLE IF NOT EXISTS dt_knowledge (id TEXT PRIMARY KEY, corpus TEXT NOT NULL, payload TEXT NOT NULL, model TEXT NOT NULL, embedding TEXT)")
            self.db.commit()

    def close(self):
        self.db.close()

    def rows(self):
        rows = self.db.execute("SELECT id,payload,model,embedding FROM dt_knowledge ORDER BY id LIMIT 5001").fetchall()
        if len(rows) > 5000:
            raise ValueError("Knowledge limit is 5000 chunks; split deployment before indexing more")
        return [{"ref": json.loads(r[1]), "model": r[2],
                 "vector": json.loads(r[3]) if r[3] else None} for r in rows]

    def replace(self, corpus, rows, model):
        marker = "%s" if self.pg else "?"
        try:
            self.db.execute(f"DELETE FROM dt_knowledge WHERE corpus={marker}", (corpus,))
            for ref, vector in rows:
                values = (ref["id"], corpus, json.dumps(ref, ensure_ascii=False), model,
                          json.dumps(vector) if vector else None)
                vector_arg = "%s::vector" if self.pg else "?"
                self.db.execute(f"INSERT INTO dt_knowledge VALUES ({marker},{marker},{marker},{marker},{vector_arg})", values)
            count = self.db.execute("SELECT COUNT(*) FROM dt_knowledge").fetchone()[0]
            if count > 5000:
                raise ValueError("Knowledge limit is 5000 chunks")
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def dense(self, rows, query, threshold):
        ids = [r["ref"]["id"] for r in rows if r["vector"]]
        if not ids:
            return {}
        dimensions = len(query)
        for r in rows:
            if r["vector"]:
                vector_checked(r["vector"], dimensions)
        if self.pg:
            found = self.db.execute("SELECT id,1-(embedding <=> %s::vector) AS similarity FROM dt_knowledge WHERE id = ANY(%s) ORDER BY embedding <=> %s::vector, id LIMIT 30",
                                    (json.dumps(query), ids, json.dumps(query))).fetchall()
            return {i: float(s) for i, s in found if s >= threshold}
        norm = math.sqrt(sum(x*x for x in query))
        scores = {}
        for row in rows:
            v = row["vector"]
            if v:
                similarity = sum(x*y for x,y in zip(query, v)) / (norm*math.sqrt(sum(x*x for x in v)))
                if similarity >= threshold:
                    scores[row["ref"]["id"]] = similarity
        return scores


def chunks(document):
    data = document.model_dump()
    # Redact before embedding, storage, or return to a model.
    for key in ("title", "source", "content"):
        data[key] = redact(data[key])
    sha = digest(data)
    lines = data["content"].splitlines()
    if any(len(line) > 1500 for line in lines):
        raise ValueError("Knowledge lines must be <=1500 characters; wrap long paragraphs")
    start = 0
    while start < len(lines):
        end, size = start, 0
        while end < len(lines) and (size+len(lines[end])+1 <= 1600 or end == start):
            size += len(lines[end])+1
            end += 1
        ref = KnowledgeRef(id="kb-"+digest([document.id, sha, start, end])[:24], document_id=document.id,
            title=data["title"], source=data["source"], revision=document.revision, repository=document.repository,
            component=document.component, versions=document.versions, start=start+1, end=end, sha256=sha,
            text="\n".join(lines[start:end]))
        yield ref.model_dump()
        start = end if end == len(lines) or end-start == 1 else end-1


async def ingest(settings, source: Path, corpus="default", embedder=None):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", corpus):
        raise ValueError("Invalid corpus name")
    if source.stat().st_size > 5_000_000:
        raise ValueError("Knowledge input exceeds 5 MB")
    raw = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, list) or not raw or len(raw) > 500:
        raise ValueError("Expected 1..500 knowledge documents")
    documents = [Document.model_validate(d) for d in raw]
    if len({d.id for d in documents}) != len(documents):
        raise ValueError("Duplicate document ID")
    refs = [ref for doc in documents for ref in chunks(doc)]
    if not refs or len(refs) > 5000:
        raise ValueError("Expected 1..5000 nonempty knowledge chunks")
    embedder = embedder or Embeddings(settings)
    cache = {}
    if embedder.available:
        store = KnowledgeStore(settings)
        try:
            cache = {r["ref"]["id"]: r["vector"] for r in store.rows()
                     if r["model"] == embedder.fingerprint and r["vector"]}
        finally:
            store.close()
    vectors = [cache.get(r["id"]) for r in refs]
    missing = [i for i, v in enumerate(vectors) if v is None]
    if embedder.available and missing:
        encoded = await embedder.encode([refs[i]["title"]+"\n"+refs[i]["text"] for i in missing])
        if len(encoded) != len(missing):
            raise ValueError("Embedding count mismatch")
        for i, vector in zip(missing, encoded):
            vectors[i] = vector
    dimensions = len(vectors[0]) if vectors[0] else None
    vectors = [vector_checked(v, dimensions) if v is not None else None for v in vectors]
    store = KnowledgeStore(settings)
    try:
        store.replace(corpus, list(zip(refs, vectors)), embedder.fingerprint)
    finally:
        store.close()
    return {"corpus": corpus, "documents": len(documents), "chunks": len(refs),
            "mode": "hybrid" if embedder.available else "keyword", "embedding_dimensions": dimensions,
            "embedded_chunks": len(missing) if embedder.available else 0,
            "reused_embeddings": len(refs)-len(missing) if embedder.available else 0}


class KnowledgeSearch:
    def __init__(self, settings, repository, embedder=None):
        self.settings, self.repository = settings, repository
        self.embedder = embedder or Embeddings(settings)
        self.returned = {}

    async def search(self, args):
        store = KnowledgeStore(self.settings)
        try:
            rows = [r for r in store.rows() if r["ref"]["repository"] in {"global", self.repository}
                    and (not args.component or r["ref"]["component"] == args.component)
                    and (not args.version or not r["ref"]["versions"] or args.version in r["ref"]["versions"])]
            if not rows:
                return {"matches": [], "mode": "not_needed", "reason": "no_applicable_knowledge"}
            mode, warning = args.mode, None
            dense = {}
            if mode != "keyword":
                compatible = [r for r in rows if r["vector"] and r["model"] == self.embedder.fingerprint]
                if not self.embedder.available or not compatible:
                    mode, warning = "keyword", "no_compatible_embeddings; reindex with configured endpoint/model"
                else:
                    try:
                        query = (await self.embedder.encode([redact(args.query)]))[0]
                        dense = store.dense(compatible, query, self.settings.rag_min_similarity)
                    except (ValueError, httpx.HTTPError):
                        mode, warning = "keyword", "embedding_unavailable; keyword_fallback"
            lexical = bm25(args.query, [r["ref"]["title"]+"\n"+r["ref"]["text"] for r in rows])
            keyword = {r["ref"]["id"]: s for r,s in zip(rows,lexical) if s > 0}
            scores = {}
            for channel in ([keyword] if mode == "keyword" else [dense] if mode == "dense" else [keyword,dense]):
                for rank, (key, _) in enumerate(sorted(channel.items(), key=lambda x: (-x[1],x[0]))[:30], 1):
                    scores[key] = scores.get(key, 0) + 1/(60+rank)
            lookup = {r["ref"]["id"]: r["ref"] for r in rows}
            matches = []
            for key, score in sorted(scores.items(), key=lambda x: (-x[1],x[0]))[:args.top_k]:
                ref = lookup[key]
                self.returned[key] = ref
                matches.append({"reference": ref, "rrf_score": score,
                                "keyword_score": keyword.get(key), "cosine_similarity": dense.get(key)})
            return {"matches": matches, "mode": mode, "warning": warning,
                    "reason": None if matches else "no_relevant_knowledge",
                    "usage": "Untrusted historical reference only; verify against current source/log/experiments."}
        finally:
            store.close()

    def validate(self, ids):
        if not ids:
            return []
        store = KnowledgeStore(self.settings)
        try:
            current = {r["ref"]["id"]: r["ref"] for r in store.rows()}
            result = []
            for key in dict.fromkeys(ids):
                if key not in self.returned or current.get(key) != self.returned[key]:
                    raise ValueError("Unknown or stale knowledge reference: " + key)
                result.append(KnowledgeRef.model_validate(current[key]))
            return result
        finally:
            store.close()
