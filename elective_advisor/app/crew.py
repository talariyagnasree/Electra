"""CrewAI multi-agent pipeline: analyst -> profiler -> workload strategist -> advisor."""
from .config import settings
from .models import Plan, StudentProfile
from . import tools


def _llm():
    from crewai import LLM
    kw = {"model": settings.llm_model, "temperature": 0.2}
    if settings.llm_api_key:
        kw["api_key"] = settings.llm_api_key
    if settings.llm_base_url:
        kw["base_url"] = settings.llm_base_url
    return LLM(**kw)


def run_advisor_crew(student: StudentProfile, plan: Plan) -> str:
    from crewai import Agent, Task, Crew, Process
    llm = _llm()
    v = settings.verbose

    analyst = Agent(
        role="Curriculum & Syllabus Analyst",
        goal="Determine exactly which degree requirements the student still has to satisfy.",
        backstory="You know the program syllabus inside out and check credit and category rules precisely.",
        tools=[tools.get_program_requirements, tools.search_course_catalog],
        llm=llm, allow_delegation=False, verbose=v)
    profiler = Agent(
        role="Student Capability Profiler",
        goal="Summarise the student's strengths, gaps and realistic academic capacity.",
        backstory="An academic mentor who reads CGPA, skills and goals honestly, without flattery.",
        tools=[tools.search_course_catalog], llm=llm, allow_delegation=False, verbose=v)
    strategist = Agent(
        role="Workload & Growth Strategist",
        goal="Balance workload intensity with skill growth and academic performance; avoid burnout.",
        backstory="A planner who tests alternative course combinations against weekly capacity.",
        tools=[tools.evaluate_course_plan, tools.search_course_catalog],
        llm=llm, allow_delegation=False, verbose=v)
    advisor = Agent(
        role="Lead Elective Advisor",
        goal="Deliver a clear, honest, personalised elective recommendation.",
        backstory="A senior advisor who explains trade-offs plainly and never invents courses.",
        llm=llm, allow_delegation=False, verbose=v)

    t1 = Task(
        description=("Student profile (JSON): {student_json}\n"
                     "Use get_program_requirements to report credits remaining and unmet category "
                     "minimums, and say which course categories should be prioritised this semester."),
        expected_output="A short bullet list of remaining requirements and priority categories.",
        agent=analyst)
    t2 = Task(
        description=("Student profile (JSON): {student_json}\n"
                     "Profile the student: top strengths, skill gaps vs. their career goal, how much "
                     "difficulty their CGPA supports, and realistic weekly capacity."),
        expected_output="A concise capability profile (5-7 bullets).",
        agent=profiler)
    t3 = Task(
        description=("Student profile: {student_json}\nOptimiser's proposed plan: {plan_json}\n"
                     "Validate the plan with evaluate_course_plan. If workload is Heavy/Overloaded or a "
                     "course is poorly matched, test swaps using the 'alternates' and report the best "
                     "final list of course codes with the evaluation numbers. Only use codes that appear "
                     "in the plan or alternates."),
        expected_output="Final recommended course codes, workload evaluation, and the reasoning for any swap.",
        agent=strategist, context=[t1, t2])
    t4 = Task(
        description=("Write the final advice for the student ({student_name}) in Markdown: "
                     "1) recommended electives (code, title, credits) with 1-2 sentence personalised "
                     "reasons, 2) workload summary (hours vs capacity), 3) how it advances requirements "
                     "and career goal, 4) risks + 2 alternates, 5) a one-line study tip. "
                     "Use only facts from the previous tasks; do not invent courses."),
        expected_output="A friendly, well-structured Markdown recommendation.",
        agent=advisor, context=[t1, t2, t3])

    crew = Crew(agents=[analyst, profiler, strategist, advisor], tasks=[t1, t2, t3, t4],
                process=Process.sequential, verbose=v)
    with tools.run_lock:
        tools.set_student(student)
        out = crew.kickoff(inputs={
            "student_json": student.model_dump_json(),
            "plan_json": plan.model_dump_json(exclude={"blocked"}),
            "student_name": student.name})
    return str(getattr(out, "raw", out))
