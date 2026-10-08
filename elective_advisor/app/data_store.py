"""JSON-file persistence for the course catalog + program requirements."""
import json
from .config import settings
from .models import Course, Requirements


def _p(name):
    return settings.data_dir / name


def load_courses() -> list[Course]:
    return [Course(**c) for c in json.loads(_p("courses.json").read_text(encoding="utf-8"))]


def save_courses(courses: list[Course]) -> None:
    _p("courses.json").write_text(
        json.dumps([c.model_dump() for c in courses], indent=2), encoding="utf-8")


def load_requirements() -> Requirements:
    return Requirements(**json.loads(_p("requirements.json").read_text(encoding="utf-8")))


def save_requirements(r: Requirements) -> None:
    _p("requirements.json").write_text(json.dumps(r.model_dump(), indent=2), encoding="utf-8")


def load_samples() -> list[dict]:
    return json.loads(_p("sample_students.json").read_text(encoding="utf-8"))


def all_skills(courses: list[Course]) -> list[str]:
    s = set()
    for c in courses:
        s.update(k.lower() for k in c.required_skills)
        s.update(k.lower() for k in c.skills_gained)
    return sorted(s)
