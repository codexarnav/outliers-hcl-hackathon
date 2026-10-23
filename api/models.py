"""
Pydantic V2 Models for FastAPI Endpoints (Section 6 Contract Compliance)
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class AskRequest(BaseModel):
    question: str = Field(..., description="Student service question")
    as_of_date: Optional[str] = Field(None, description="Date context in YYYY-MM-DD format (defaults to today)")

class Citation(BaseModel):
    doc_id: str
    title: str
    section: str
    page: int
    version: str = "1.0"
    effective_from: str

class ToolInvocation(BaseModel):
    tool: str
    input: Dict[str, Any] = Field(default_factory=dict)
    output: Dict[str, Any] = Field(default_factory=dict)

class AppliedRule(BaseModel):
    rule_id: str
    value: str
    source_doc_id: str

class AskResponse(BaseModel):
    trace_id: str
    answer: str
    answer_type: str = Field(
        ...,
        description="One of: 'retrieved_fact', 'calculated', 'not_found', 'clarification_needed', 'refused', 'conflict_flagged'"
    )
    citations: List[Citation] = Field(default_factory=list)
    tools_invoked: List[ToolInvocation] = Field(default_factory=list)
    applied_rules: List[AppliedRule] = Field(default_factory=list)
    conflicts_detected: List[Dict[str, Any]] = Field(default_factory=list)
    explanation: str
    as_of_date: str

class IngestResponse(BaseModel):
    doc_id: str
    chunks_indexed: int
    status: str = "ok"

class HealthResponse(BaseModel):
    status: str = "ok"
    api: str = "ready"
    vector_store: str = "connected"
    sqlite: str = "connected"
    llm: str = "ready"
    mock_mode: bool = True

class AuditRecordResponse(BaseModel):
    trace_id: str
    timestamp: str
    student_id: Optional[str] = None
    question_category: str
    question_text: str
    sources_retrieved: List[Dict[str, Any]]
    precedence_decision: Optional[str] = None
    tools_invoked: List[Dict[str, Any]]
    applied_rules: List[Dict[str, Any]]
    conflicts_detected: List[Dict[str, Any]]
    answer_type: str
    model: str
    llm_calls: int
    tokens: int
    latency_ms: int

class SourceRegisterRow(BaseModel):
    doc_id: str
    title: str
    issuer: str
    authority_level: int
    doc_type: str
    version: str
    effective_from: str
    effective_to: Optional[str] = ""
    supersedes: Optional[str] = ""
    scope_programmes: Optional[str] = "ALL"
    scope_batches: Optional[str] = "ALL"
    provenance: Optional[str] = ""
    retrieved_on: Optional[str] = ""
    synthetic: Optional[str] = "N"
