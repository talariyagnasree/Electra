"""Flask admin console for the catalog + syllabus requirements. Run: python -m admin.app (port 5000)"""
import json
import requests
from flask import Flask, flash, redirect, render_template_string, request, url_for
from app import data_store
from app.config import settings
from app.models import Course, Requirements

flask_app = Flask(__name__)
flask_app.secret_key = "dev-only-change-me"

PAGE = """
<!doctype html><title>Elective Advisor - Admin</title>
<style>body{font-family:system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#222}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:6px;text-align:left;font-size:14px}
input,select,textarea{padding:6px;margin:3px 0;width:100%;box-sizing:border-box}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.card{background:#f6f7f9;padding:1rem;border-radius:8px;margin:1rem 0}
button{padding:7px 14px;cursor:pointer}.msg{background:#e8f5e9;padding:8px;border-radius:6px;margin:6px 0}</style>
<h1>Elective Advisor - Admin</h1>
{% for m in get_flashed_messages() %}<div class="msg">{{m}}</div>{% endfor %}
<div class="card"><h3>Program requirements (syllabus rules)</h3>
<form method="post" action="/requirements"><div class="grid">
<label>Program<input name="program" value="{{reqs.program}}"></label>
<label>Elective credits required<input type="number" name="credits" value="{{reqs.elective_credits_required}}"></label>
<label>Category minimums (e.g. AI:6, Software:3)<input name="cats" value="{{cats}}"></label></div>
<label>Notes<textarea name="notes">{{reqs.notes}}</textarea></label><button>Save requirements</button></form></div>
<div class="card"><h3>Catalog ({{courses|length}} courses)</h3>
<table><tr><th>Code</th><th>Title</th><th>Cr</th><th>Category</th><th>Diff</th><th>Hrs/wk</th><th>Prereqs</th><th>Min CGPA</th><th></th></tr>
{% for c in courses %}<tr><td>{{c.code}}</td><td>{{c.title}}</td><td>{{c.credits}}</td><td>{{c.category}}</td>
<td>{{c.difficulty}}</td><td>{{c.weekly_hours}}</td><td>{{c.prerequisites|join(', ')}}</td><td>{{c.min_cgpa}}</td>
<td><form method="post" action="/delete/{{c.code}}"><button>Delete</button></form></td></tr>{% endfor %}</table>
<form method="post" action="/reindex" style="margin-top:10px"><button>Re-index vector DB</button></form></div>
<div class="card"><h3>Add / update a course</h3><form method="post" action="/course"><div class="grid">
<label>Code<input name="code" required></label><label>Title<input name="title" required></label>
<label>Category<input name="category" value="General"></label>
<label>Credits<input type="number" name="credits" value="3"></label>
<label>Difficulty (1-5)<input type="number" name="difficulty" min="1" max="5" value="3"></label>
<label>Weekly hours<input type="number" step="0.5" name="weekly_hours" value="6"></label>
<label>Min CGPA<input type="number" step="0.1" name="min_cgpa" value="0"></label>
<label>Prerequisites (comma sep)<input name="prerequisites"></label>
<label>Offered<select name="offered"><option>both</option><option>odd</option><option>even</option></select></label>
<label>Required skills (skill:level, ...)<input name="required_skills" placeholder="python:3, math:2"></label>
<label>Skills gained (comma sep)<input name="skills_gained"></label>
<label>Career paths (comma sep)<input name="career_paths"></label></div>
<label>Description<textarea name="description"></textarea></label>
<label>Syllabus topics (comma sep)<input name="syllabus_topics"></label><button>Save course</button></form></div>
<div class="card"><h3>Bulk upload catalog (JSON list of courses)</h3>
<form method="post" action="/upload" enctype="multipart/form-data"><input type="file" name="file" accept=".json" required>
<button>Replace catalog</button></form></div>
"""


def _csv(s: str) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _reindex() -> str:
    try:
        r = requests.post(f"{settings.api_url}/catalog/reindex", timeout=60)
        return f"Vector index rebuilt ({r.json().get('indexed')} courses)."
    except Exception:
        return "Saved. API not reachable - the index will refresh automatically on next request."


@flask_app.get("/")
def index():
    reqs = data_store.load_requirements()
    cats = ", ".join(f"{k}:{v}" for k, v in reqs.category_minimums.items())
    return render_template_string(PAGE, courses=data_store.load_courses(), reqs=reqs, cats=cats)


@flask_app.post("/course")
def save_course():
    f = request.form
    rs = {}
    for part in _csv(f.get("required_skills", "")):
        k, _, v = part.partition(":")
        rs[k.strip().lower()] = int(v or 3)
    try:
        c = Course(code=f["code"].strip().upper(), title=f["title"], category=f["category"],
                   credits=int(f["credits"]), difficulty=int(f["difficulty"]),
                   weekly_hours=float(f["weekly_hours"]), min_cgpa=float(f["min_cgpa"]),
                   prerequisites=[p.upper() for p in _csv(f["prerequisites"])], offered=f["offered"],
                   required_skills=rs, skills_gained=_csv(f["skills_gained"]),
                   career_paths=_csv(f["career_paths"]), description=f["description"],
                   syllabus_topics=_csv(f["syllabus_topics"]))
    except Exception as e:
        flash(f"Invalid course: {e}")
        return redirect(url_for("index"))
    courses = [x for x in data_store.load_courses() if x.code != c.code] + [c]
    data_store.save_courses(sorted(courses, key=lambda x: x.code))
    flash(f"Saved {c.code}. " + _reindex())
    return redirect(url_for("index"))


@flask_app.post("/delete/<code>")
def delete(code):
    data_store.save_courses([c for c in data_store.load_courses() if c.code != code])
    flash(f"Deleted {code}. " + _reindex())
    return redirect(url_for("index"))


@flask_app.post("/requirements")
def save_reqs():
    f = request.form
    cats = {}
    for part in _csv(f.get("cats", "")):
        k, _, v = part.partition(":")
        cats[k.strip()] = int(v)
    data_store.save_requirements(Requirements(
        program=f["program"], elective_credits_required=int(f["credits"]),
        category_minimums=cats, notes=f["notes"]))
    flash("Requirements saved.")
    return redirect(url_for("index"))


@flask_app.post("/upload")
def upload():
    try:
        courses = [Course(**c) for c in json.load(request.files["file"])]
        data_store.save_courses(courses)
        flash(f"Catalog replaced with {len(courses)} courses. " + _reindex())
    except Exception as e:
        flash(f"Upload failed: {e}")
    return redirect(url_for("index"))


@flask_app.post("/reindex")
def reindex():
    flash(_reindex())
    return redirect(url_for("index"))


if __name__ == "__main__":
    flask_app.run(port=5000, debug=True)
