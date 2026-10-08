"""Student UI. Run: streamlit run streamlit_app.py"""
import pandas as pd
import requests
import streamlit as st
from app.config import settings

API = settings.api_url
st.set_page_config(page_title="Elective Advisor", page_icon="🎓", layout="wide")


@st.cache_data(ttl=30)
def get(path):
    return requests.get(f"{API}{path}", timeout=30).json()


def post(path, payload, timeout=300):
    r = requests.post(f"{API}{path}", json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


st.title("🎓 Agentic Course & Elective Advisor")
try:
    health, samples, skills_vocab, courses = get("/health"), get("/students/samples"), get("/skills"), get("/courses")
except Exception:
    st.error(f"Cannot reach the API at {API}. Start it with: uvicorn app.api:app --port 8000")
    st.stop()

with st.sidebar:
    st.header("Student profile")
    pick = st.selectbox("Load sample", ["(custom)"] + [s["name"] for s in samples])
    base = next((s for s in samples if s["name"] == pick), {})
    name = st.text_input("Name", base.get("name", "Student"))
    cgpa = st.slider("CGPA (10-pt)", 0.0, 10.0, float(base.get("cgpa", 7.5)), 0.1)
    sem = st.number_input("Current semester", 1, 12, int(base.get("semester", 6)))
    done = st.multiselect("Completed courses", sorted({c["code"] for c in courses} | set(base.get("completed_courses", [])) | {"CS201", "CS210", "CS220", "CS301", "MA201"}),
                          default=base.get("completed_courses", []))
    goal = st.text_input("Career goal", base.get("career_goal", ""))
    interests = st.text_input("Interests (comma separated)", ", ".join(base.get("interests", [])))
    targets = st.multiselect("Skills you want to build", skills_vocab, default=[t for t in base.get("target_skills", []) if t in skills_vocab])
    with st.expander("Current skill levels (0-5)"):
        skills = {s: st.slider(s, 0, 5, int(base.get("skills", {}).get(s, 0)), key=f"sk_{s}_{pick}") for s in skills_vocab}
    st.subheader("Capacity & preferences")
    core = st.slider("Core course/lab hrs per week", 0, 45, int(base.get("core_weekly_hours", 24)))
    cap = st.slider("Max total study hrs per week", 20, 70, int(base.get("max_weekly_hours", 48)))
    c1, c2 = st.columns(2)
    mn = c1.number_input("Min credits", 0, 12, int(base.get("min_elective_credits", 6)))
    mx = c2.number_input("Max credits", 3, 15, int(base.get("max_elective_credits", 9)))
    risk = st.select_slider("Strategy", ["safe", "balanced", "growth"], base.get("risk_preference", "balanced"))
    mode = st.radio("Engine", ["agentic", "fast"], help="agentic = CrewAI agents (needs an LLM); fast = built-in reasoning engine")
    go = st.button("Recommend electives", type="primary", use_container_width=True)

student = dict(name=name, cgpa=cgpa, semester=int(sem), completed_courses=done,
               skills={k: v for k, v in skills.items() if v > 0}, target_skills=targets,
               interests=[i.strip() for i in interests.split(",") if i.strip()], career_goal=goal,
               core_weekly_hours=core, max_weekly_hours=cap, min_elective_credits=int(mn),
               max_elective_credits=int(mx), risk_preference=risk)

if go:
    with st.spinner("Agents are analysing syllabus, profile and workload..." if mode == "agentic" else "Computing..."):
        try:
            st.session_state["result"] = post("/recommend", {"student": student, "mode": mode})
            st.session_state["student"] = student
        except Exception as e:
            st.error(f"Request failed: {e}")

res = st.session_state.get("result")
if not res:
    st.info("Fill in the profile on the left and click **Recommend electives**.")
    st.stop()

plan = res["plan"]
if res.get("note"):
    st.warning(res["note"])
st.caption(f"Mode used: **{res['mode_used']}** · LLM: {health['llm_model'] if health['llm_configured'] else 'not configured'}")

m = st.columns(5)
m[0].metric("Credits", plan["total_credits"])
m[1].metric("Weekly hours", plan["total_hours"], f"cap {plan['capacity_hours']}", delta_color="off")
m[2].metric("Workload", plan["workload_level"])
m[3].metric("Credits still required", plan["remaining_required_credits"])
m[4].metric("Unmet categories", ", ".join(f"{k}:{v}" for k, v in plan["unmet_categories"].items()) or "none")
st.progress(min(plan["utilization"], 1.0), text=f"Capacity used: {plan['utilization']:.0%}")
for w in plan["warnings"]:
    st.warning(w)

left, right = st.columns([3, 2])
with left:
    st.subheader("Advisor's recommendation")
    st.markdown(res["narrative"])
with right:
    st.subheader("Selected electives")
    df = pd.DataFrame(plan["selected"])
    if not df.empty:
        st.dataframe(df[["code", "title", "credits", "difficulty", "score", "readiness", "effective_hours"]], hide_index=True)
        st.bar_chart(df.set_index("code")["effective_hours"])
    st.subheader("Alternates")
    if plan["alternates"]:
        st.dataframe(pd.DataFrame(plan["alternates"])[["code", "title", "score", "effective_hours"]], hide_index=True)
    with st.expander("Not eligible (and why)"):
        for b in plan["blocked"]:
            st.write(f"**{b['code']}** {b['title']} - {'; '.join(b['reasons'])}")

st.divider()
st.subheader("🧪 What-if simulator")
opts = {f"{c['code']} - {c['title']}": c["code"] for c in courses}
chosen = st.multiselect("Pick your own combination", list(opts), default=[k for k, v in opts.items() if v in {x["code"] for x in plan["selected"]}])
if chosen:
    sim = post("/simulate", {"student": st.session_state["student"], "course_codes": [opts[c] for c in chosen]})
    a, b, c_ = st.columns(3)
    a.metric("Credits", sim["total_credits"])
    b.metric("Hours / capacity", f"{sim['total_hours']} / {sim['capacity_hours']}")
    c_.metric("Workload", sim["workload_level"])
    for w in sim["warnings"]:
        st.warning(w)
