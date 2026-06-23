# Agentic SRS Generator — Linux Setup & Execution Guide

Follow these instructions to install dependencies, configure local models, and run the application on a Linux-based system.

---

## 📋 System Requirements
- **OS:** Any modern Linux distribution (Ubuntu, Debian, Fedora, Arch, etc.)
- **Python:** Version 3.10 or higher
- **RAM:** Minimum 8GB (16GB+ recommended for running local LLMs)
- **Nvidia GPU** (Optional, but highly recommended for fast model inference)

---

## 🛠️ Step 1: Install and Configure Ollama

Ollama runs as a system service in Linux and handles all local model hosting.

1. **Install Ollama** via the official script:
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ```

2. **Verify the Ollama service** is running:
   ```bash
   systemctl status ollama
   ```

3. **Pull the target models** (do this while you have internet access):
   ```bash
   # Pull the heavy model (default for architecture snapshot, rollups, section writing, audits)
   ollama pull llama3.2:latest   # or your custom heavy model, e.g. gpt-oss-20b

   # Pull the fast model (default for leaf node summarizations)
   ollama pull gemma3:latest     # or your custom fast model, e.g. gemma3n:e4b
   ```

---

## 🐍 Step 2: Set Up Python Environment

1. **Navigate to the project root**:
   ```bash
   cd srs_doc
   ```

2. **Create a virtual environment**:
   ```bash
   python3 -m venv .venv
   ```

3. **Activate the virtual environment**:
   ```bash
   source .venv/bin/activate
   ```

4. **Install core dependencies**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

5. **Install Graphify**:
   ```bash
   pip install graphifyy
   ```

---

## 🚀 Step 3: Run the Application

With the virtual environment active and Ollama running:

```bash
streamlit run app.py
```

The terminal will output a local network address (typically `http://localhost:8501`). Open this URL in your web browser to access the graphical control center.
