# AI Multi-Docs Extraction Pipeline: Installation & Setup Guide

This document provides step-by-step instructions for installing and setting up the **AI Multi-Docs Extraction Pipeline** development environment on Windows.

---

## 📋 System Prerequisites

Before installing the project environment, ensure your system meets the following requirements:

- **Operating System**: Windows 10 / 11 (64-bit)
- **Python**: Version **3.10** or higher (Tested on Python 3.10 – 3.14)
- **Git**: Installed and available in your system PATH
- **Google Gemini API Key**: An active Gemini API key from Google AI Studio

---

## ⚡ Option 1: Automated 1-Click Setup (Recommended)

An automated cross-platform setup script is provided in the project root folder.

### Cross-Platform Command (Windows / macOS / Linux)
```bash
python setup_env.py
```

### OS Launcher Wrappers
- **Windows (CMD / Double-Click)**:
  ```cmd
  setup_env.bat
  ```
- **macOS / Linux / Git Bash**:
  ```bash
  chmod +x setup_env.sh
  ./setup_env.sh
  ```

**What `setup_env.py` automatically handles:**
1. Checks for `.venv`. If missing, creates a new Python virtual environment (`python -m venv .venv`).
2. Upgrades `pip` and installs all dependencies listed in `requirements.txt`.
3. Checks for `.env`. If missing, creates `.env` from `.env.example`.
4. Configures Git to use version-controlled hooks (`git config core.hooksPath .githooks`).
5. Runs system initialization (`python main.py --step init`) to construct required pipeline storage directories and initialize the SQLite database schema.

---

## 🛠️ Option 2: Manual Installation & Setup

If you prefer setting up the environment manually via Terminal, follow these steps:

### Step 1: Clone & Verify Branch
```bash
git clone https://github.com/prokungdev/AI-Multi-Docs-Extraction-Pipeline.git
cd AI-Multi-Docs-Extraction-Pipeline
git pull origin main
```

### Step 2: Create Python Virtual Environment (`.venv`)
```bash
python -m venv .venv
```

### Step 3: Activate Virtual Environment
- **PowerShell**:
  ```powershell
  .\.venv\Scripts\Activate.ps1
  ```
  *(Note: If PowerShell displays a script execution policy error, run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process` first)*
- **Command Prompt (CMD)**:
  ```cmd
  .\.venv\Scripts\activate.bat
  ```

### Step 4: Upgrade Pip & Install Dependencies
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Step 5: Configure Environment Variables (`.env`)
Copy the template file to `.env`:
```bash
copy .env.example .env
```
Open `.env` in a text editor and set your API key:
```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
```

### Step 6: Initialize System Schema & Storage Directories
```bash
python main.py --step init
```

---

## 🚀 Running the Pipeline & User Interface

Once setup is complete, you can launch the application through any of the following entry points:

### 1. Web UI (Streamlit Interface)
Launch the interactive Web UI by running:
```cmd
run_ui_streamlit.bat
```
or via terminal:
```bash
streamlit run apps/streamlit/app.py
```

### 2. REST API Backend (FastAPI)
Launch the REST API server by running:
```cmd
run_api.bat
```
or via terminal:
```bash
uvicorn apps.api.main:app --reload --port 8000
```
API Documentation will be accessible at `http://127.0.0.1:8000/docs`.

### 3. Command Line Interface (CLI)
Run individual pipeline stages:
```bash
python main.py --step split_match
python main.py --step extract
python main.py --step validate
python main.py --step transform_db
python main.py --step export
python main.py --step run_all
```

### 4. Jupyter Notebook Walkthrough
Open and run cells step-by-step in [`notebooks/01_pipeline_walkthrough.ipynb`](../notebooks/01_pipeline_walkthrough.ipynb). Make sure to select the `.venv` Python kernel in your IDE / Jupyter interface.

---

## ❓ Troubleshooting

### Issue 1: `ModuleNotFoundError: No module named 'loguru'`
- **Cause**: Virtual environment is not activated or dependencies were not installed into `.venv`.
- **Solution**: Ensure `.venv` is activated (you should see `(.venv)` in terminal) and rerun `pip install -r requirements.txt`.

### Issue 2: Script Execution Disabled in PowerShell
- **Cause**: Windows PowerShell default Execution Policy blocks `.ps1` scripts.
- **Solution**: Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process` in your PowerShell session.

### Issue 3: Missing API Key Warning
- **Cause**: `GEMINI_API_KEY` is empty or missing in `.env`.
- **Solution**: Open `.env` and paste a valid key obtained from Google AI Studio.
