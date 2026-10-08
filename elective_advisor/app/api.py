"""FastAPI service: the agent brain. Run: uvicorn app.api:app --port 8000"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from . import data_store, engine, vectorstore
from .config import settings
from .models import (Course, RecommendRequest, RecommendResponse, Requirements, SimulateRequest)


@asynccontextmanager
async def lifespan(app: FastAPI):
    vectorstore.ensure_index(data_store.load_courses())
    yield


app = FastAPI(title="Agentic Course & Elective Advisor", version="1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"status": "ok", "llm_configured": settings.llm_configured,
            "llm_model": settings.llm_model, "embedding_backend": settings.embedding_backend}


@app.get("/courses", response_model=list[Course])
def courses():
    return data_store.load_courses()


@app.get("/requirements", response_model=Requirements)
def requirements():
    return data_store.load_requirements()


@app.get("/skills")
def skills():
    return data_store.all_skills(data_store.load_courses())


@app.get("/students/samples")
def samples():
    return data_store.load_samples()


@app.post("/catalog/reindex")
def reindex():
    cs = data_store.load_courses()
    vectorstore.ensure_index(cs, force=True)
    return {"indexed": len(cs)}


@app.get("/search")
def search(q: str, k: int = 5):
    cs = data_store.load_courses()
    by = {c.code: c for c in cs}
    return [{"code": code, "title": by[code].title, "similarity": round(s, 3)}
            for code, s in vectorstore.search(q, cs, k) if code in by]


@app.post("/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest):
    cs, reqs = data_store.load_courses(), data_store.load_requirements()
    plan = engine.build_plan(req.student, cs, reqs)
    fallback = engine.explain_markdown(req.student, plan)
    if req.mode == "fast":
        return RecommendResponse(plan=plan, narrative=fallback, mode_used="fast")
    if not settings.llm_configured:
        return RecommendResponse(
            plan=plan, narrative=fallback, mode_used="fast",
            note="No LLM configured (set LLM_API_KEY or use an ollama model) - used the built-in "
                 "reasoning engine instead of the CrewAI agents.")
    try:
        from .crew import run_advisor_crew
        return RecommendResponse(plan=plan, narrative=run_advisor_crew(req.student, plan),
                                 mode_used="agentic")
    except Exception as e:  # LLM/network failure should never break the app
        return RecommendResponse(plan=plan, narrative=fallback, mode_used="fast",
                                 note=f"Agent run failed ({type(e).__name__}: {e}); showing engine result.")


@app.post("/simulate")
def simulate(req: SimulateRequest):
    if not req.course_codes:
        raise HTTPException(400, "course_codes is empty")
    return engine.evaluate_codes(req.student, data_store.load_courses(),
                                 data_store.load_requirements(), req.course_codes)
