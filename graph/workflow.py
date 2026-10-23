"""
LangGraph Orchestrator & Workflow Definition
Connects question routing, authorization guard (R7), retrieval & precedence (Annex A),
deterministic academic tools (R5), citation validation, and audit logger (R10).
"""

import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from langgraph.graph import StateGraph, END

from graph.state import AgentState
from graph.nodes import (
    classify_and_authorize_node,
    retrieval_and_precedence_node,
    execute_tools_node,
    synthesize_and_validate_node,
    audit_logger_node
)
from core.config import settings
from core.database import get_connection

def route_after_classification(state: AgentState) -> str:
    """Conditional edge router based on intent and authorization."""
    category = state.get("category")
    if category in ("refused", "not_found"):
        return "synthesize_and_validate"
    elif category in ("personal_data", "personal_eligibility", "what_if"):
        return "execute_tools"
    else:
        return "retrieval_and_precedence"

def build_workflow():
    workflow = StateGraph(AgentState)

    # 1. Add nodes
    workflow.add_node("classify_and_authorize", classify_and_authorize_node)
    workflow.add_node("retrieval_and_precedence", retrieval_and_precedence_node)
    workflow.add_node("execute_tools", execute_tools_node)
    workflow.add_node("synthesize_and_validate", synthesize_and_validate_node)
    workflow.add_node("audit_logger", audit_logger_node)

    # 2. Add edges
    workflow.set_entry_point("classify_and_authorize")

    workflow.add_conditional_edges(
        "classify_and_authorize",
        route_after_classification,
        {
            "synthesize_and_validate": "synthesize_and_validate",
            "execute_tools": "execute_tools",
            "retrieval_and_precedence": "retrieval_and_precedence"
        }
    )

    workflow.add_edge("retrieval_and_precedence", "synthesize_and_validate")
    workflow.add_edge("execute_tools", "synthesize_and_validate")
    workflow.add_edge("synthesize_and_validate", "audit_logger")
    workflow.add_edge("audit_logger", END)

    return workflow.compile()

# Singleton compiled graph
graph_app = build_workflow()

def process_question(
    question: str,
    as_of_date: Optional[str] = None,
    student_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main entrypoint for processing user queries through the LangGraph pipeline.
    Returns response strictly conforming to Section 6.1 contract.
    """
    start_time = time.time()
    trace_id = uuid.uuid4().hex[:8]
    date_val = as_of_date or datetime.now().strftime("%Y-%m-%d")

    initial_state: AgentState = {
        "trace_id": trace_id,
        "question": question,
        "as_of_date": date_val,
        "student_id": student_id,
        "category": "policy_fact",
        "auth_status": "authorized" if student_id else "anonymous",
        "auth_error_message": None,
        "target_course_code": None,
        "target_semester": None,
        "has_medical_cert": False,
        "retrieved_chunks": [],
        "precedence_decision": None,
        "winning_chunk": None,
        "conflicts_detected": [],
        "tools_invoked": [],
        "applied_rules": [],
        "tool_raw_result": None,
        "answer": "",
        "answer_type": "retrieved_fact",
        "citations": [],
        "explanation": "",
        "llm_calls": 0,
        "tokens": 0,
        "latency_ms": 0,
        "model_used": "mock_llm" if settings.MOCK_LLM else settings.OLLAMA_MODEL
    }

    final_state = graph_app.invoke(initial_state)

    total_latency_ms = int((time.time() - start_time) * 1000)
    final_state["latency_ms"] = total_latency_ms

    # Finding #28: Update audit_log with actual measured elapsed latency
    used_trace_id = final_state.get("trace_id", trace_id)
    try:
        conn = get_connection()
        with conn:
            conn.execute("UPDATE audit_log SET latency_ms = ? WHERE trace_id = ?", (total_latency_ms, used_trace_id))
        conn.close()
    except Exception as e:
        print(f"[WARN] Failed to update audit log latency: {e}")

    # Transform applied_rules to Section 6.1 schema
    formatted_rules = []
    for r in final_state.get("applied_rules", []):
        formatted_rules.append({
            "rule_id": r.get("rule_id", ""),
            "value": f"{r.get('operator', '')} {r.get('value', '')}".strip(),
            "source_doc_id": r.get("source_doc_id", "")
        })

    # Clean tools_invoked for API response
    formatted_tools = []
    for t in final_state.get("tools_invoked", []):
        formatted_tools.append({
            "tool": t.get("tool", ""),
            "input": t.get("input", {}),
            "output": t.get("output", {})
        })

    return {
        "trace_id": final_state.get("trace_id", trace_id),
        "answer": final_state.get("answer", ""),
        "answer_type": final_state.get("answer_type", "not_found"),
        "citations": final_state.get("citations", []),
        "retrieved_chunks": final_state.get("retrieved_chunks", []),
        "tools_invoked": formatted_tools,
        "applied_rules": formatted_rules,
        "conflicts_detected": final_state.get("conflicts_detected", []),
        "explanation": final_state.get("explanation", ""),
        "as_of_date": date_val
    }
