from typing import Literal, Optional
from pydantic import BaseModel, Field


class Course(BaseModel):
    code: str
    title: str
    credits: int = Field(3, ge=1, le=6)
    category: str = "General"
    description: str = ""
    syllabus_topics: list[str] = []
    prerequisites: list[str] = []
    required_skills: dict[str, int] = {}      # skill -> level (1-5) expected on entry
    skills_gained: list[str] = []
    career_paths: list[str] = []
    difficulty: int = Field(3, ge=1, le=5)
    weekly_hours: float = Field(6, ge=1, le=30)  # typical effort incl. self study
    min_cgpa: float = Field(0, ge=0, le=10)
    offered: Literal["both", "odd", "even"] = "both"
    min_semester: int = 1


class Requirements(BaseModel):
    program: str = "B.Tech"
    elective_credits_required: int = 18
    category_minimums: dict[str, int] = {}     # category -> min elective credits
    notes: str = ""


class StudentProfile(BaseModel):
    name: str = "Student"
    cgpa: float = Field(7.5, ge=0, le=10)
    semester: int = Field(6, ge=1, le=12)
    completed_courses: list[str] = []
    elective_credits_earned: Optional[int] = None   # auto-computed from catalog if None
    skills: dict[str, int] = {}                     # skill -> self/assessed level 0-5
    target_skills: list[str] = []
    interests: list[str] = []
    career_goal: str = ""
    core_weekly_hours: float = 24                   # mandatory courses + labs
    max_weekly_hours: float = 48                    # realistic total weekly study capacity
    min_elective_credits: int = 6
    max_elective_credits: int = 9
    risk_preference: Literal["safe", "balanced", "growth"] = "balanced"


class ScoredCourse(BaseModel):
    code: str
    title: str
    credits: int
    category: str
    difficulty: int
    score: float
    relevance: float
    readiness: float
    growth: float
    performance_fit: float
    effective_hours: float
    reasons: list[str] = []


class Blocked(BaseModel):
    code: str
    title: str
    reasons: list[str]


class Plan(BaseModel):
    selected: list[ScoredCourse]
    alternates: list[ScoredCourse]
    blocked: list[Blocked]
    total_credits: int
    total_hours: float
    capacity_hours: float
    utilization: float
    workload_level: str
    remaining_required_credits: int
    unmet_categories: dict[str, int]
    warnings: list[str] = []


class RecommendRequest(BaseModel):
    student: StudentProfile
    mode: Literal["fast", "agentic"] = "agentic"


class RecommendResponse(BaseModel):
    plan: Plan
    narrative: str
    mode_used: str
    note: str = ""


class SimulateRequest(BaseModel):
    student: StudentProfile
    course_codes: list[str]
