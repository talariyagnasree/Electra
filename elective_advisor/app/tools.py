"""CrewAI tools exposing the engine + vector DB to the agents."""
import json
import threading
from crewai.tools import tool
from . import data_store, engine, vectorstore
from .models import StudentProfile

_ctx = {"student": None}
run_lock = threading.Lock()   # tools read a shared context, so crew runs are serialised


def set_student(s: StudentProfile):
    _ctx["student"] = s


@tool("search_course_catalog")
def search_course_catalog(query: str) -> str:
    """Semantic (vector DB) search of the elective catalog. Input: free-text topic, skill or career goal.
    Returns the top matching courses with credits, difficulty and prerequisites."""
    courses = data_store.load_courses()
    by = {c.code: c for c in courses}
    rows = [{"code": code, "title": by[code].title, "similarity": round(sim, 2),
             "credits": by[code].credits, "difficulty": by[code].difficulty,
             "prerequisites": by[code].prerequisites}
            for code, sim in vectorstore.search(query, courses, 6) if code in by]
    return json.dumps(rows)


@tool("get_program_requirements")
def get_program_requirements(scope: str = "all") -> str:
    """Returns the degree/syllabus elective requirements (credits needed, category minimums)
    and the student's progress against them. Input can be any string, e.g. 'all'."""
    s, courses, reqs = _ctx["student"], data_store.load_courses(), data_store.load_requirements()
    earned, per_cat = engine.credits_earned(s, courses)
    return json.dumps({"program": reqs.program, "required_credits": reqs.elective_credits_required,
                       "earned_credits": earned, "category_minimums": reqs.category_minimums,
                       "earned_by_category": dict(per_cat),
                       "unmet_categories": engine.unmet_categories(s, courses, reqs),
                       "notes": reqs.notes})


@tool("evaluate_course_plan")
def evaluate_course_plan(course_codes: str) -> str:
    """Evaluates workload, credits and eligibility for a comma-separated list of course codes
    (e.g. 'CS561,CS501') for the current student. Use it to test swaps before recommending."""
    codes = [c for c in course_codes.replace(";", ",").split(",") if c.strip()]
    p = engine.evaluate_codes(_ctx["student"], data_store.load_courses(),
                              data_store.load_requirements(), codes)
    return json.dumps({"credits": p.total_credits, "weekly_hours": p.total_hours,
                       "capacity_hours": p.capacity_hours, "utilization": p.utilization,
                       "workload_level": p.workload_level, "warnings": p.warnings,
                       "courses": [{"code": x.code, "score": x.score, "hours": x.effective_hours}
                                   for x in p.selected]})
