"""
Graph State Definitions for LangGraph Student Services Assistant
"""

from typing import TypedDict, List, Dict, Any, Optional

class AgentState(TypedDict):
    # Request context
    trace_id: str
    question: str
    as_of_date: str
    student_id: Optional[str]
    
    # Classification & Authorization
    category: str  # 'policy_fact', 'personal_data', 'personal_eligibility', 'what_if', 'not_found', 'refused', 'clarification_needed'
    auth_status: str  # 'authorized', 'unauthorized', 'anonymous'
    auth_error_message: Optional[str]
    target_course_code: Optional[str]
    target_semester: Optional[int]
    has_medical_cert: bool
    
    # Retrieval & Precedence
    retrieved_chunks: List[Dict[str, Any]]
    precedence_decision: Optional[str]
    winning_chunk: Optional[Dict[str, Any]]
    conflicts_detected: List[Dict[str, Any]]
    
    # Deterministic Tools
    tools_invoked: List[Dict[str, Any]]
    applied_rules: List[Dict[str, Any]]
    tool_raw_result: Optional[Dict[str, Any]]
    
    # Synthesis & Audit
    answer: str
    answer_type: str  # 'retrieved_fact', 'calculated', 'not_found', 'clarification_needed', 'refused', 'conflict_flagged'
    citations: List[Dict[str, Any]]
    explanation: str
    
    # Telemetry
    llm_calls: int
    tokens: int
    latency_ms: int
    model_used: str
