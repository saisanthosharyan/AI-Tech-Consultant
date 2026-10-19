from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Dict, Any
from datetime import datetime

# ==========================================
# Task 1: Knowledge Brain Schemas
# ==========================================

class Citation(BaseModel):
    title: str = Field(..., description="Article title")
    url: str = Field(..., description="URL of the source article")
    section: Optional[str] = Field(None, description="Section heading")
    chunk_id: Optional[str] = Field(None, description="Unique chunk identifier")
    snippet: Optional[str] = Field(None, description="Relevant evidence snippet")
    images: List[str] = Field(default_factory=list, description="Associated image URLs")

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, description="Customer or consultant question")
    top_k: int = Field(default=4, ge=1, le=10, description="Number of evidence chunks to retrieve")
    min_confidence: float = Field(default=0.35, ge=0.0, le=1.0, description="Minimum confidence threshold")

class QueryResponse(BaseModel):
    request_id: str = Field(..., description="Unique request identifier")
    question: str = Field(..., description="Original input question")
    answer: str = Field(..., description="Grounded answer or abstention message")
    status: str = Field(..., description="'success', 'insufficient_evidence', or 'error'")
    sources: List[Citation] = Field(default_factory=list, description="Grounded source citations")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Calibrated confidence score")
    needs_human: bool = Field(..., description="True if human escalation is required")
    reason: Optional[str] = Field(None, description="Reason if evidence was insufficient or escalated")
    model: Optional[str] = Field(None, description="Model identifier used for generation")
    latency_ms: Optional[float] = Field(None, description="End-to-end query latency in milliseconds")

class IngestionRunRequest(BaseModel):
    max_articles: Optional[int] = Field(default=15, description="Max articles to ingest in this batch (for polite crawl)")
    force_refresh: bool = Field(default=False, description="Re-ingest unchanged articles if true")
    sample_only: bool = Field(default=False, description="Quick run with sample articles")

class IngestionStatusResponse(BaseModel):
    is_running: bool
    total_discovered: int
    processed: int
    unchanged: int
    failed: int
    pending: int
    last_run_at: Optional[str] = None
    last_error: Optional[str] = None

class EscalationCreateRequest(BaseModel):
    request_id: Optional[str] = None
    question: str
    retrieved_evidence: List[Dict[str, Any]] = Field(default_factory=list)
    reason: str

class EscalationResolveRequest(BaseModel):
    expert_answer: str = Field(..., min_length=5, description="Expert verified answer")
    resolved_by: str = Field(..., description="Name or ID of expert reviewer")
    index_as_knowledge: bool = Field(default=True, description="Make searchable in Knowledge Brain")

class EscalationResponse(BaseModel):
    id: int
    request_id: Optional[str]
    question: str
    reason: str
    expert_answer: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[str] = None
    is_indexed: bool
    created_at: str

# ==========================================
# Task 2: Inbox Agent Schemas
# ==========================================

class EmailCategory(str):
    HOW_TO = "how_to"
    TECHNICAL_TROUBLESHOOTING = "technical_troubleshooting"
    NEW_PROJECT = "new_project"
    REFUND_CANCELLATION = "refund_cancellation"
    COMPLAINT = "complaint"
    QUOTE_REQUEST = "quote_request"
    FOLLOW_UP = "follow_up"
    URGENT_AMBIGUOUS = "urgent_ambiguous"
    MISSING_KB_INFO = "missing_kb_info"

class RiskLevel(str):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class EmailClassification(BaseModel):
    category: str
    urgency: str  # low, medium, high, urgent
    risk_level: str  # low, medium, high, critical
    risk_factors: List[str] = Field(default_factory=list)
    key_facts: List[str] = Field(default_factory=list)
    requires_kb: bool = True
    can_auto_send: bool = False

class CustomerEmail(BaseModel):
    id: str
    sender_name: str
    sender_email: str
    subject: str
    body: str
    timestamp: str
    expected_category: Optional[str] = None
    expected_risk: Optional[str] = None
    expected_behavior: Optional[str] = None
    is_synthetic: bool = True

class EmailDraftResponse(BaseModel):
    email_id: str
    classification: EmailClassification
    retrieved_sources: List[Citation]
    draft_subject: str
    draft_reply: str
    guardrails_passed: bool
    guardrail_warnings: List[str] = Field(default_factory=list)
    needs_human_review: bool
    autonomy_eligible: bool
    model_version: str

class ReviewActionRequest(BaseModel):
    action: str = Field(..., description="'approve', 'edit', 'reject', 'escalate'")
    edited_content: Optional[str] = None
    reviewer: str = Field(default="Consultant Reviewer")
    feedback_notes: Optional[str] = None

# ==========================================
# Task 3: Meeting to Scope Schemas
# ==========================================

class TranscriptRequirement(BaseModel):
    req_id: str = Field(..., description="Stable ID e.g. REQ-01")
    description: str
    quote: str = Field(..., description="Direct quote from meeting transcript")
    status: str = Field(default="confirmed", description="confirmed, unclear, disputed")
    priority: str = Field(default="medium", description="must_have, should_have, could_have")
    feasibility: str = Field(default="needs_clarification", description="existing_config, existing_with_limitations, custom_dev, needs_clarification")
    feasibility_notes: Optional[str] = None
    acceptance_criteria: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    needs_clarification: bool = False

class EngineeringTaskEstimate(BaseModel):
    task_id: str
    req_id: Optional[str] = None
    description: str
    low_hours: float
    likely_hours: float
    high_hours: float
    assumptions: str
    evidence_or_reasoning: str
    uncertainty_flag: bool = False

class ScopeOfWorkDocument(BaseModel):
    project_id: str
    version: int
    project_title: str
    client_name: str
    project_objective: str
    current_problem: str
    requirements: List[TranscriptRequirement]
    deliverables: List[str]
    exclusions: List[str]
    assumptions_and_dependencies: List[str]
    client_responsibilities: List[str]
    risks_and_open_questions: List[str]
    tasks: List[EngineeringTaskEstimate]
    total_low_hours: float
    total_likely_hours: float
    total_high_hours: float
    proposal_text: str
    is_approved: bool = False
    approved_by: Optional[str] = None
    created_at: str

class ScopeDiffReport(BaseModel):
    project_id: str
    baseline_version: int
    new_version: int
    added_requirements: List[TranscriptRequirement] = Field(default_factory=list)
    removed_requirements: List[Dict[str, Any]] = Field(default_factory=list)
    modified_requirements: List[Dict[str, Any]] = Field(default_factory=list)
    timeline_changes: Optional[str] = None
    budget_impact: Dict[str, float] = Field(default_factory=dict)
    summary_report: str
