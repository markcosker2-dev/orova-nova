"""
OROVA Core Data Models using SQLModel (SQLAlchemy + Pydantic)
Enables type-safe, structured management of leads, tasks, meetings, and metrics.
"""

from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import datetime
import uuid


class Lead(SQLModel, table=True):
    """B2B Lead record with validation and scoring."""
    id: Optional[int] = Field(default=None, primary_key=True)
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()), unique=True)
    
    # Contact Info
    company_name: str = Field(index=True)
    contact_email: Optional[str] = Field(default=None, index=True)
    contact_phone: Optional[str] = Field(default=None)
    contact_name: Optional[str] = Field(default=None)
    
    # Lead Classification
    niche: str = Field(index=True)  # e.g., "solar", "hvac", "construction"
    company_size: Optional[str] = None  # "1-10", "11-50", "51-200", "200+"
    industry: Optional[str] = None
    job_signal: Optional[str] = None  # From JobSpy: "VP of Sales", "Marketing Manager"
    
    # Scoring & Status
    lead_score: float = Field(default=0.0, index=True)  # 0-100
    status: str = Field(default="prospecting")  # prospecting, contacted, replied, qualified, closed
    
    # Engagement
    email_sent: bool = Field(default=False)
    call_triggered: bool = Field(default=False)
    call_outcome: Optional[str] = None  # "voicemail", "answered", "interested", "no_answer"
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    tasks: List["Task"] = Relationship(back_populates="lead")
    meetings: List["Meeting"] = Relationship(back_populates="lead")


class Task(SQLModel, table=True):
    """Autonomous task execution record."""
    id: Optional[int] = Field(default=None, primary_key=True)
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()), unique=True)
    
    # Task Definition
    task_type: str = Field(index=True)  # "send_email", "trigger_call", "seo_audit", "book_meeting"
    description: str
    
    # Foreign Key
    lead_id: int = Field(foreign_key="lead.id", index=True)
    lead: Optional[Lead] = Relationship(back_populates="tasks")
    
    # Status
    status: str = Field(default="pending")  # pending, executing, completed, failed
    result: Optional[str] = None  # JSON result from execution
    error: Optional[str] = None
    
    # Execution Tracking
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Agent Tracking
    assigned_agent: str = Field(default="nova")  # e.g., "hawk", "atlas", "oracle"


class Meeting(SQLModel, table=True):
    """Booked meetings via Cal.com webhook integration."""
    id: Optional[int] = Field(default=None, primary_key=True)
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()), unique=True)
    
    # Booking Info
    lead_id: int = Field(foreign_key="lead.id", index=True)
    lead: Optional[Lead] = Relationship(back_populates="meetings")
    
    cal_event_id: str = Field(unique=True)  # From Cal.com webhook
    scheduled_time: datetime = Field(index=True)
    timezone: Optional[str] = None
    
    # Status
    status: str = Field(default="scheduled")  # scheduled, completed, cancelled, no_show
    notes: Optional[str] = None
    
    # Follow-up Automation
    follow_up_sent: bool = Field(default=False)
    follow_up_time: Optional[datetime] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Metric(SQLModel, table=True):
    """Agency KPI tracking."""
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Date Scope
    date: str = Field(index=True)  # YYYY-MM-DD
    
    # Lead Funnel
    leads_found: int = Field(default=0)
    leads_contacted: int = Field(default=0)
    leads_replied: int = Field(default=0)
    meetings_booked: int = Field(default=0)
    
    # Revenue Proxy
    estimated_pipeline_value: float = Field(default=0.0)
    
    # Efficiency
    emails_sent: int = Field(default=0)
    calls_triggered: int = Field(default=0)
    seo_audits_run: int = Field(default=0)
    
    # AI Cost
    ai_tokens_used: int = Field(default=0)
    ai_cost_usd: float = Field(default=0.0)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
