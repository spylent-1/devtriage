from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceRef(StrictModel):
    id: str
    path: str
    start: int
    end: int
    sha256: str
    text: str
    kind: Literal["source", "log", "config"] = "source"


class VerificationResult(StrictModel):
    case_id: str
    reproduced: bool = False
    healthy_control: bool = False
    detail: str


class DiagnosisRequest(StrictModel):
    repo: str
    log: str
    verify: Literal["none", "lab"] = "none"
    knowledge_repository: str | None = Field(default=None, max_length=100)


class KnowledgeRef(StrictModel):
    id: str
    document_id: str
    title: str
    source: str
    revision: str
    repository: str
    component: str
    versions: list[str]
    start: int
    end: int
    sha256: str
    text: str


class DiagnosisReport(StrictModel):
    run_id: str = ""
    symptom: str
    root_cause: str
    root_cause_label: str = "unknown"
    location: str = ""
    status: Literal["reproduced", "supported", "insufficient"] = "insufficient"
    evidence_ids: list[str] = Field(default_factory=list)
    knowledge_ids: list[str] = Field(default_factory=list)
    knowledge: list[KnowledgeRef] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    verification: list[VerificationResult] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class ToolCall(StrictModel):
    name: str
    arguments: dict


class ToolResult(StrictModel):
    ok: bool
    data: dict = Field(default_factory=dict)
    error: str | None = None
