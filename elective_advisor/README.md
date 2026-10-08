# 🎓 Agentic Course & Elective Advisor

Autonomous AI agent system that recommends personalised electives by analysing **syllabus/degree requirements,
CGPA and an individual capability profile**, and balances **workload intensity vs. skill growth vs. academic performance**.

**Stack:** Python · CrewAI (LLM agents) · ChromaDB (vector DB) · FastAPI (agent API) · Flask (admin console) · Streamlit (student UI)

## Architecture
```
Streamlit UI (8501) ──► FastAPI (8000) ──► Reasoning engine (scoring + workload optimiser)
Flask Admin  (5000) ──►   │                       ▲
 edits catalog/rules      ├──► ChromaDB (semantic course search: goals/interests ↔ syllabus topics)
                          └──► CrewAI crew (4 agents, sequential, with tools)
                                Syllabus Analyst → Capability Profiler → Workload Strategist → Lead Advisor
```
**How a recommendation is made**
1. *Eligibility* – prerequisites, minimum CGPA, semester/term offering.
2. *Semantic relevance* – the student's goal/interests/target skills are embedded and matched against course
   descriptions, syllabus topics and career paths in ChromaDB.
3. *Scoring* – relevance + skill readiness + skill growth + CGPA-vs-difficulty fit (weights change with the
   `safe / balanced / growth` strategy) + bonus for unmet syllabus category requirements.
4. *Workload reasoning* – each course's hours are inflated for under-preparation and difficulty; an optimiser
   searches course combinations under credit limits and the student's **free weekly capacity**
   (`max hours − core hours`), penalising burnout (>90% utilisation) and category over-concentration.
5. *Agents* – the CrewAI crew reads the plan, verifies requirements, tests swaps with the `evaluate_course_plan`
   tool and writes the final personalised advice.
If no LLM is configured (or it fails) the API transparently falls back to the built-in engine, so the app always works.

## Setup
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                    # add your LLM key (or use ollama), see file
python run_all.py                                       # starts all 3 services
```
Or run individually:
```bash
uvicorn app.api:app --port 8000
python -m admin.app
streamlit run streamlit_app.py
```
Open **http://localhost:8501** (students), **http://localhost:5000** (admin), **http://localhost:8000/docs** (API).

### Offline / no API key
`EMBEDDING_BACKEND=hash` (no model download) and leave `LLM_API_KEY` empty → fast mode. For free local agents use
Ollama: `LLM_MODEL=ollama/llama3.1`, `LLM_BASE_URL=http://localhost:11434`.

## API
| Method | Path | Purpose |
|---|---|---|
| POST | `/recommend` | `{student, mode: fast\|agentic}` → plan + narrative |
| POST | `/simulate` | what-if evaluation of chosen course codes |
| GET | `/search?q=` | vector search over the catalog |
| GET | `/courses` `/requirements` `/skills` `/students/samples` | data |
| POST | `/catalog/reindex` | rebuild the vector index |

## Customising for your college
Use the Flask admin (or edit `data/courses.json`, `data/requirements.json`): add your real electives, prerequisites,
difficulty, weekly hours and category minimums. The vector index refreshes automatically.

## Tests
`python -m pytest -q tests` (uses the offline hash embedder).

## Layout
```
app/ engine.py (reasoning) · crew.py (agents) · tools.py · vectorstore.py · api.py · models.py · data_store.py · config.py
admin/app.py   Flask console      streamlit_app.py   student UI      data/   catalog, rules, sample students
```
