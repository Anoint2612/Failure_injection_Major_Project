# AI-Powered Resilience Framework

This document provides a step-by-step guide to setting up the **AI-Powered Resilience Framework** from scratch in a WSL/Linux environment, and running the included experiments.

***

## 1. System Requirements Check

Ensure you have the following installed. Run these commands to verify:
* **Docker**: `docker --version` (Ensure Docker is running. If on Windows, ensure Docker Desktop is running with WSL2 integration ON).
* **Python**: `python3 --version` (3.8 or higher required).
* **Gemini API Key**: Obtain from [Google AI Studio](https://aistudio.google.com/).

***

## 2. Infrastructure Setup (Target App)

The target application consists of 3 microservices and a monitoring stack.

1. **Build and Start Containers**:
   ```bash
   cd target-app
   docker compose up --build -d
   ```

2. **Verify Health**:
   * API Dashboard: [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
   * Prometheus Targets: [http://localhost:9090/targets](http://localhost:9090/targets) (All should be green/UP)
   * Grafana: [http://localhost:3000](http://localhost:3000) (Default login: `admin` / `admin`)

***

## 3. Controller Setup (The "Chaos Engine")

The controller manages the injection and recovery of faults.

1. **Initialize Virtual Environment**:
   ```bash
   cd framework-controller
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   *(Alternatively, install manually: `pip install fastapi uvicorn docker google-generativeai requests httpx prometheus-fastapi-instrumentator`)*

3. **Launch the Controller**:
   ```bash
   export GEMINI_API_KEY="YOUR_ACTUAL_KEY"
   uvicorn main:app --host 0.0.0.0 --port 5000
   ```
   *(Note: You can also use an `.env` file to store your API key instead of exporting it directly!)*

***

## 4. Running Experiments

Once everything is running, use the provided automation scripts to perform tests. **Ensure your virtual environment is active** before running these scripts.

### A. Run a Resilience Test

This script injects faults (like CPU stress or latency), measures the impact, recovers the service, and saves a JSON result file.

```bash
python3 run_experiment.py
```

### B. Generate AI Analysis

This script sends the test results to Gemini and generates a Markdown report (`ai_remediation_report.md`).

```bash
python3 ai_analyst.py
```

### C. Generate New Scenarios

Ask Gemini to analyze your architecture and suggest new fault injection tests.

```bash
python3 scenario_generator.py
```

***

## 5. Troubleshooting

* **`tc` command not found**: Ensure `iproute2` is installed in the service Dockerfiles.
* **`stress-ng` not found**: Ensure `stress-ng` is installed in the service Dockerfiles.
* **Docker permission denied**: Run `sudo chmod 666 /var/run/docker.sock` in WSL if you are encountering permission issues.