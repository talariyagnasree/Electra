"""Deterministic reasoning core: eligibility -> multi-factor scoring -> workload-aware plan optimisation.

The CrewAI agents call into these functions (via tools) and explain / challenge the result.
"""
import itertools
from collections import Counter
from . import vectorstore
from .models import (Blocked, Course, Plan, Requirements, ScoredCourse, StudentProfile)

WEIGHTS = {  # relevance, readiness, growth, performance-fit
    "safe":     (0.25, 0.30, 0.10, 0.35),
    "balanced": (0.35, 0.25, 0.20, 0.20),
    "growth":   (0.35, 0.15, 0.35, 0.15),
}
POOL_SIZE = 12
MAX_COURSES = 5
CATEGORY_BONUS = 0.12


def _norm(d: dict) -> dict:
    return {k.lower().strip(): v for k, v in d.items()}


def _levels(student: StudentProfile) -> dict:
    return _norm(student.skills)


def capability(student: StudentProfile) -> float:
    """Map CGPA (0-10) to the course difficulty (0-5) the student typically handles well."""
    return student.cgpa / 2.0


def eligibility_issues(c: Course, s: StudentProfile, done: set) -> list[str]:
    issues = []
    if c.code.upper() in done:
        issues.append("already completed")
    missing = [p for p in c.prerequisites if p.upper() not in done]
    if missing:
        issues.append(f"missing prerequisites: {', '.join(missing)}")
    if s.cgpa < c.min_cgpa:
        issues.append(f"CGPA {s.cgpa:.1f} below minimum {c.min_cgpa:.1f}")
    if s.semester < c.min_semester:
        issues.append(f"not open before semester {c.min_semester}")
    term = "odd" if s.semester % 2 else "even"
    if c.offered not in ("both", term):
        issues.append(f"only offered in {c.offered} semesters")
    return issues


def readiness(c: Course, lv: dict) -> float:
    if not c.required_skills:
        return 1.0
    vals = [min(lv.get(k.lower(), 0) / max(v, 1), 1.0) for k, v in c.required_skills.items()]
    return sum(vals) / len(vals)


def growth(c: Course, lv: dict, targets: set) -> float:
    if not c.skills_gained:
        return 0.5
    vals = []
    for g in c.skills_gained:
        g = g.lower()
        vals.append(1.0 if g in targets else (0.8 if lv.get(g, 0) <= 2 else 0.3))
    return sum(vals) / len(vals)


def performance_fit(c: Course, s: StudentProfile) -> float:
    gap = max(0.0, c.difficulty - capability(s))
    return max(0.0, 1 - gap / 3.0)


def effective_hours(c: Course, ready: float) -> float:
    """Weekly effort adjusted for under-preparation and difficulty."""
    return round(c.weekly_hours * (1 + 0.4 * (1 - ready)) * (1 + 0.08 * (c.difficulty - 3)), 1)


def credits_earned(student: StudentProfile, courses: list[Course]) -> tuple[int, Counter]:
    done = {x.upper() for x in student.completed_courses}
    per_cat = Counter()
    for c in courses:
        if c.code.upper() in done:
            per_cat[c.category] += c.credits
    total = student.elective_credits_earned if student.elective_credits_earned is not None \
        else sum(per_cat.values())
    return total, per_cat


def unmet_categories(student, courses, reqs) -> dict[str, int]:
    _, per_cat = credits_earned(student, courses)
    return {k: v - per_cat.get(k, 0) for k, v in reqs.category_minimums.items()
            if v - per_cat.get(k, 0) > 0}


def student_query(s: StudentProfile) -> str:
    parts = []
    if s.career_goal:
        parts.append(s.career_goal)
    if s.interests:
        parts.append("Interests: " + ", ".join(s.interests))
    if s.target_skills:
        parts.append("Wants to learn: " + ", ".join(s.target_skills))
    return ". ".join(parts)


def _reasons(c, rel, ready, gr, perf, hrs, s, cat_needed) -> list[str]:
    r = []
    if rel >= 0.65:
        r.append("strong match with your interests and career goal")
    elif rel >= 0.4:
        r.append("moderate match with your interests/goal")
    if ready >= 0.9:
        r.append("you already meet the expected entry skills")
    elif ready < 0.6:
        r.append("you are under-prepared on some entry skills; expect extra effort")
    if gr >= 0.7:
        r.append("builds skills you want or have not yet developed")
    if perf < 0.7:
        r.append(f"difficulty {c.difficulty}/5 is demanding for CGPA {s.cgpa:.1f}")
    elif c.difficulty >= 4:
        r.append("challenging but well within your academic record")
    if cat_needed:
        r.append(f"counts towards the unmet {c.category} credit requirement")
    r.append(f"~{hrs} study hrs/week")
    return r


def score_courses(student: StudentProfile, courses: list[Course], reqs: Requirements):
    lv = _levels(student)
    targets = {t.lower().strip() for t in student.target_skills}
    done = {x.upper() for x in student.completed_courses}
    unmet = unmet_categories(student, courses, reqs)
    w_rel, w_rdy, w_gr, w_perf = WEIGHTS[student.risk_preference]

    eligible, blocked = [], []
    for c in courses:
        issues = eligibility_issues(c, student, done)
        (blocked if issues else eligible).append((c, issues))

    sims = vectorstore.similarities(student_query(student), courses)
    sub = [sims[c.code] for c, _ in eligible if c.code in sims]
    lo, hi = (min(sub), max(sub)) if sub else (0, 0)

    scored = []
    for c, _ in eligible:
        raw = sims.get(c.code)
        rel = 0.5 if raw is None else ((raw - lo) / (hi - lo) if hi > lo else 0.5)
        rdy, gr, perf = readiness(c, lv), growth(c, lv, targets), performance_fit(c, student)
        hrs = effective_hours(c, rdy)
        needed = c.category in unmet
        score = w_rel * rel + w_rdy * rdy + w_gr * gr + w_perf * perf + (CATEGORY_BONUS if needed else 0)
        scored.append(ScoredCourse(
            code=c.code, title=c.title, credits=c.credits, category=c.category,
            difficulty=c.difficulty, score=round(score, 3), relevance=round(rel, 2),
            readiness=round(rdy, 2), growth=round(gr, 2), performance_fit=round(perf, 2),
            effective_hours=hrs, reasons=_reasons(c, rel, rdy, gr, perf, hrs, student, needed)))
    scored.sort(key=lambda x: -x.score)
    blk = [Blocked(code=c.code, title=c.title, reasons=i) for c, i in blocked
           if i != ["already completed"]]
    return scored, blk, unmet


def workload_level(util: float) -> str:
    return ("Light" if util < 0.6 else "Moderate" if util < 0.85
            else "Heavy" if util <= 1.0 else "Overloaded")


def _capacity(student: StudentProfile) -> float:
    return max(0.0, student.max_weekly_hours - student.core_weekly_hours)


def _choose(pool: list[ScoredCourse], capacity: float, max_cr: int, min_cr: int):
    best, best_obj = None, -1e9
    for k in range(1, min(MAX_COURSES, len(pool)) + 1):
        for combo in itertools.combinations(pool, k):
            cr = sum(x.credits for x in combo)
            hrs = sum(x.effective_hours for x in combo)
            if cr > max_cr or hrs > capacity:
                continue
            obj = sum(x.score for x in combo)
            if cr < min_cr:
                obj -= 0.25 * (min_cr - cr)
            util = hrs / capacity if capacity else 1
            if util > 0.9:                       # burnout penalty
                obj -= 2.0 * (util - 0.9)
            obj -= 0.15 * sum(max(0, n - 2) for n in Counter(x.category for x in combo).values())
            if obj > best_obj:
                best, best_obj = combo, obj
    return list(best) if best else []


def _finish(sel, scored, blocked, unmet, student, courses, reqs, warnings) -> Plan:
    cap = _capacity(student)
    cr = sum(x.credits for x in sel)
    hrs = round(sum(x.effective_hours for x in sel), 1)
    util = round(hrs / cap, 2) if cap else (0.0 if not sel else 9.99)
    earned, _ = credits_earned(student, courses)
    remaining = max(0, reqs.elective_credits_required - earned)
    sel_codes = {x.code for x in sel}
    if cr < min(student.min_elective_credits, remaining or student.min_elective_credits):
        warnings.append(f"Plan has {cr} credits, below your preferred minimum of "
                        f"{student.min_elective_credits}.")
    if util > 1:
        warnings.append("Selected courses exceed your weekly study capacity.")
    cats_after = Counter()
    for x in sel:
        cats_after[x.category] += x.credits
    still = {k: v - cats_after.get(k, 0) for k, v in unmet.items() if v - cats_after.get(k, 0) > 0}
    for k, v in still.items():
        warnings.append(f"{v} more {k} credit(s) will still be required in later semesters.")
    return Plan(selected=sel, alternates=[x for x in scored if x.code not in sel_codes][:4],
                blocked=blocked, total_credits=cr, total_hours=hrs, capacity_hours=round(cap, 1),
                utilization=util, workload_level=workload_level(util),
                remaining_required_credits=remaining, unmet_categories=unmet, warnings=warnings)


def build_plan(student: StudentProfile, courses: list[Course], reqs: Requirements) -> Plan:
    scored, blocked, unmet = score_courses(student, courses, reqs)
    warnings: list[str] = []
    if not scored:
        warnings.append("No eligible electives found for this profile.")
        return _finish([], scored, blocked, unmet, student, courses, reqs, warnings)

    cap = _capacity(student)
    earned, _ = credits_earned(student, courses)
    remaining = max(0, reqs.elective_credits_required - earned)
    max_cr = student.max_elective_credits
    if remaining > 0:
        max_cr = min(max_cr, remaining)
    min_cr = min(student.min_elective_credits, max_cr)

    sel = _choose(scored[:POOL_SIZE], cap, max_cr, min_cr)
    if not sel:
        warnings.append("Your free weekly capacity is too small for the usual elective load; "
                        "showing the lightest good option. Consider reducing core load.")
        light = sorted((x for x in scored if x.credits <= max_cr), key=lambda x: x.effective_hours)
        sel = light[:1]
    return _finish(sel, scored, blocked, unmet, student, courses, reqs, warnings)


def evaluate_codes(student: StudentProfile, courses: list[Course], reqs: Requirements,
                   codes: list[str]) -> Plan:
    """What-if: evaluate a hand-picked set of electives with the same model."""
    scored, blocked, unmet = score_courses(student, courses, reqs)
    by = {x.code.upper(): x for x in scored}
    blk = {b.code.upper(): b for b in blocked}
    sel, warnings = [], []
    for code in codes:
        code = code.strip().upper()
        if code in by:
            sel.append(by[code])
        elif code in blk:
            warnings.append(f"{code} is not allowed: {'; '.join(blk[code].reasons)}.")
        else:
            warnings.append(f"{code} not found or already completed.")
    cr = sum(x.credits for x in sel)
    if cr > student.max_elective_credits:
        warnings.append(f"{cr} credits exceeds your maximum of {student.max_elective_credits}.")
    return _finish(sel, scored, list(blk.values()), unmet, student, courses, reqs, warnings)


def explain_markdown(student: StudentProfile, plan: Plan) -> str:
    """Template narrative (used in fast mode or when the LLM is unavailable)."""
    L = [f"### Recommended electives for {student.name}",
         f"Workload: **{plan.workload_level}** — {plan.total_hours} of {plan.capacity_hours} free "
         f"hrs/week ({plan.utilization:.0%}), {plan.total_credits} credits.\n"]
    for x in plan.selected:
        L.append(f"**{x.code} – {x.title}** ({x.credits} cr, difficulty {x.difficulty}/5, score {x.score})")
        L += [f"- {r}" for r in x.reasons]
        L.append("")
    if plan.alternates:
        L.append("**Alternates:** " + ", ".join(f"{a.code} ({a.title})" for a in plan.alternates[:3]))
    if plan.warnings:
        L.append("\n**Heads-up:**")
        L += [f"- {w}" for w in plan.warnings]
    return "\n".join(L)
