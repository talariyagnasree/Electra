"""Start FastAPI (8000), Flask admin (5000) and Streamlit (8501) together. Ctrl+C stops all."""
import subprocess, sys, time

procs = [
    [sys.executable, "-m", "uvicorn", "app.api:app", "--port", "8000"],
    [sys.executable, "-m", "admin.app"],
    [sys.executable, "-m", "streamlit", "run", "streamlit_app.py", "--server.port", "8501"],
]
running = []
try:
    for cmd in procs:
        running.append(subprocess.Popen(cmd))
        time.sleep(3)
    print("\nStudent UI  : http://localhost:8501\nAPI docs    : http://localhost:8000/docs\nAdmin (Flask): http://localhost:5000\n")
    for p in running:
        p.wait()
except KeyboardInterrupt:
    pass
finally:
    for p in running:
        p.terminate()
