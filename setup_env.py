"""Cross-platform environment setup script for AI Multi-Docs Extraction Pipeline.

Automates virtual environment creation, dependency installation,
environment file template initialization, git hooks configuration,
and system directory/database initialization across Windows, macOS, and Linux.
"""

import sys
import os
import shutil
import subprocess
from pathlib import Path

# Base directory setup
BASE_DIR = Path(__file__).resolve().parent
VENV_DIR = BASE_DIR / ".venv"
ENV_FILE = BASE_DIR / ".env"
ENV_EXAMPLE = BASE_DIR / ".env.example"
GIT_HOOKS_DIR = BASE_DIR / ".githooks"

def get_venv_python() -> Path:
    """Get the path to the Python executable inside virtual environment."""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"

def run_command(cmd: list[str], check: bool = True) -> int:
    """Execute shell command with stream logging."""
    print(f"[EXEC] {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=BASE_DIR)
    if check and result.returncode != 0:
        print(f"[ERROR] Command failed with exit code {result.returncode}: {' '.join(cmd)}")
        sys.exit(result.returncode)
    return result.returncode

def main() -> None:
    """Run full environment setup pipeline."""
    print("==========================================================")
    print(" AI Multi-Docs Extraction Pipeline - Environment Setup")
    print("==========================================================")
    print()

    # 1. Create Python Virtual Environment (.venv)
    if not VENV_DIR.exists():
        print("[INFO] Creating Python virtual environment (.venv)...")
        run_command([sys.executable, "-m", "venv", str(VENV_DIR)])
        print("[SUCCESS] Virtual environment created successfully.")
    else:
        print("[INFO] Virtual environment (.venv) already exists.")

    venv_python = get_venv_python()

    # 2. Upgrade pip and install dependencies
    print()
    print("[INFO] Upgrading pip and installing requirements...")
    run_command([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"])
    run_command([str(venv_python), "-m", "pip", "install", "-r", "requirements.txt"])
    print("[SUCCESS] Dependencies installed successfully.")

    # 3. Setup .env file
    print()
    if not ENV_FILE.exists():
        if ENV_EXAMPLE.exists():
            print("[INFO] Creating .env file from .env.example...")
            shutil.copy(ENV_EXAMPLE, ENV_FILE)
            print("[WARNING] Please update .env with your actual GEMINI_API_KEY if needed.")
        else:
            print("[WARNING] .env.example not found. Skipping .env creation.")
    else:
        print("[INFO] .env file already exists.")

    # 4. Configure Git Hooks (.githooks)
    print()
    if GIT_HOOKS_DIR.exists():
        print("[INFO] Configuring Git hooks path to .githooks...")
        run_command(["git", "config", "core.hooksPath", ".githooks"], check=False)
        print("[SUCCESS] Git hooks configured successfully.")

    # 5. Initialize System Directories & Database Schema
    print()
    print("[INFO] Initializing system directories and SQLite database schema...")
    run_command([str(venv_python), "main.py", "--step", "init"])

    print()
    print("==========================================================")
    print(" [SUCCESS] Environment setup completed successfully!")
    print("==========================================================")
    print()
    print("You can launch the Streamlit Web UI by executing:")
    print("  run_ui_streamlit.bat  (or streamlit run apps/streamlit/app.py)")
    print("You can also run the REST API server by executing:")
    print("  run_api.bat           (or uvicorn apps.api.main:app --reload)")
    print()

if __name__ == "__main__":
    main()
