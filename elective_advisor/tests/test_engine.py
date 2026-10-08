from app import data_store, engine
from app.models import StudentProfile

C, R = data_store.load_courses(), data_store.load_requirements()
S = {s["name"]: StudentProfile(**s) for s in data_store.load_samples()}


def test_prereqs_and_cgpa_block():
    plan = engine.build_plan(S["Ravi"], C, R)
    blocked = {b.code: b.reasons for b in plan.blocked}
    assert "CS501" in blocked and any("prerequisite" in r for r in blocked["CS501"])
    assert all(x.code != "CS501" for x in plan.selected)


def test_plan_respects_capacity_and_credits():
    for s in S.values():
        p = engine.build_plan(s, C, R)
        assert p.selected
        assert p.total_credits <= s.max_elective_credits
        assert p.total_hours <= p.capacity_hours + 1e-6
        assert p.workload_level != "Overloaded"


def test_goal_alignment_for_llm_student():
    codes = {x.code for x in engine.build_plan(S["Asha"], C, R).selected}
    assert codes & {"CS561", "CS502", "CS501"}


def test_even_only_course_blocked_in_odd_semester():
    p = engine.build_plan(S["Meera"], C, R)  # semester 7 = odd
    assert any(b.code == "CS570" for b in p.blocked)


def test_whatif_flags_overload():
    s = S["Ravi"].model_copy(update={"core_weekly_hours": 40})
    p = engine.evaluate_codes(s, C, R, ["CS540", "CS520", "CS541"])
    assert p.workload_level == "Overloaded" and p.warnings
