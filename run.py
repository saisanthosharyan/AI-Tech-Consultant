"""
Cross-platform One-Command Startup Launcher for AI Tech Consultant Platform.
Starts the Knowledge Brain REST API on port 8000 and the Streamlit dashboard on port 8501.
"""
import sys
import time
import subprocess
import webbrowser
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

def main():
    print("=" * 60)
    print("  AI TECH CONSULTANT — CAPSTONE PLATFORM LAUNCHER")
    print("=" * 60)
    print()

    # Ensure data directory exists
    data_dir = ROOT_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "vector_index").mkdir(parents=True, exist_ok=True)

    print("[1/3] Starting Knowledge Brain REST API on http://localhost:8000 ...")
    kb_cmd = [
        sys.executable,
        "-m", "uvicorn",
        "kb_app.main:app",
        "--app-dir", str(ROOT_DIR / "task1-knowledge-brain"),
        "--host", "127.0.0.1",
        "--port", "8000",
    ]
    kb_proc = subprocess.Popen(kb_cmd, cwd=str(ROOT_DIR))

    print("Waiting 3 seconds for Knowledge Brain API to initialize...")
    time.sleep(3)

    print("[2/3] Checking API health...")
    try:
        import httpx
        with httpx.Client(timeout=3.0) as client:
            resp = client.get("http://localhost:8000/health")
            if resp.status_code == 200:
                print(f"  Knowledge Brain API is Healthy: {resp.json().get('status')}")
    except Exception as e:
        print(f"  Note: API health check exception: {e}")

    print("[3/3] Launching Unified Streamlit Dashboard on http://localhost:8501 ...")
    st_cmd = [sys.executable, "-m", "streamlit", "run", str(ROOT_DIR / "frontend" / "app.py")]
    
    try:
        subprocess.run(st_cmd, cwd=str(ROOT_DIR))
    except KeyboardInterrupt:
        print("\nShutting down AI Tech Consultant services...")
    finally:
        kb_proc.terminate()
        print("Knowledge Brain API terminated. Goodbye!")

if __name__ == "__main__":
    main()
