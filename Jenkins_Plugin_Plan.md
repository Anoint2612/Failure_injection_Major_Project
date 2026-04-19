# ChaosController — Jenkins Pipeline Integration: Execution Instructions

This document is the step-by-step execution guide for turning ChaosController into a plug-and-play Jenkins CI/CD stage. Every change is explained, every file is listed, and every command is included.

---

## How This Works (Big Picture)

```
Developer pushes code
        │
        ▼
Jenkins Stage 1: Build & start the developer's app (docker compose up)
        │
        ▼
Jenkins Stage 2: Pull & start chaos-controller (docker run)
        │
        ▼
Jenkins Stage 3: ← PIPELINE PAUSES HERE
        │           Dashboard URL printed to console
        │           Developer opens browser → tests faults → gets AI reports
        │           Developer clicks APPROVE or REJECT in Jenkins
        ▼
Jenkins Stage 4: Cleanup (always runs)
        │
        ▼
Jenkins Stage 5: Deploy to Production (only if APPROVED)
```

The key trick: **the entire ChaosController (backend + frontend UI) is packaged into a single Docker image** so any team can use it with one `docker run` command — no Python, no Node.js, no cloning the repo.

---

## Step 1 — Modify `frontend/src/App.jsx`

**File:** `frontend/src/App.jsx`  
**Line to change:** Line 4 — `const API = 'http://localhost:5050';`

**Why:** Right now the frontend hardcodes the API URL as `http://localhost:5050`. When the frontend is served *from inside* the Docker container (same port as the API), it needs to call the API relatively (just `/status` etc., not `http://localhost:5050/status`). In dev mode it stays as-is.

**Change:**
```javascript
// BEFORE (line 4):
const API = 'http://localhost:5050';

// AFTER:
const API = window.location.port === '5173'
  ? 'http://localhost:5050'   // Dev mode: Vite runs on 5173, API on 5050
  : '';                        // Production: frontend IS the API (same port)
```

This means every `fetch(${API}/status)` in dev mode calls `http://localhost:5050/status`, and in production (inside Docker) calls `/status` — same origin, no CORS issues.

---

## Step 2 — Modify `framework-controller/main.py`

**File:** `framework-controller/main.py`  
**Where:** At the **bottom** of the file, after all `app.include_router(...)` calls.

**Why:** When the Docker image is built, the React frontend is compiled into static HTML/CSS/JS files and placed at `/app/static`. FastAPI can serve these as static files. This makes the entire dashboard available at `:5050/` in production, so no separate Vite dev server is needed.

**Add at the bottom:**
```python
# Serve the built React frontend in production (inside Docker container)
import os
from starlette.staticfiles import StaticFiles

if os.path.isdir("/app/static"):
    app.mount("/", StaticFiles(directory="/app/static", html=True), name="static")
```

The `if os.path.isdir` guard means this only activates inside the Docker container. In local dev mode (`uvicorn main:app ...` on your machine), the `/app/static` directory doesn't exist so it's skipped — nothing breaks.

---

## Step 3 — Create Root `Dockerfile`

**File:** `Dockerfile` (at the project root, NOT inside `framework-controller/`)

**Why:** This is the core of the plug-and-play approach. A multi-stage build that:
1. **Stage 1** — Uses Node.js to compile the React frontend into static files
2. **Stage 2** — Uses Python to run the FastAPI controller, and copies the compiled frontend into it

```dockerfile
# ───────────────────────────────────────────────
# Stage 1: Build the React frontend
# ───────────────────────────────────────────────
FROM node:18-alpine AS frontend-build

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
RUN npm run build
# Output: /frontend/dist/ contains index.html + assets/


# ───────────────────────────────────────────────
# Stage 2: Python controller runtime
# ───────────────────────────────────────────────
FROM python:3.9-slim

WORKDIR /app

# Install Python dependencies
COPY framework-controller/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the controller source code
COPY framework-controller/ .

# Copy the compiled React frontend from Stage 1
# It lands at /app/static — this is what main.py serves
COPY --from=frontend-build /frontend/dist /app/static

# Expose the controller's port
EXPOSE 5050

# Start the controller
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5050"]
```

**Build command:**
```bash
# Run from the project root
docker build -t chaos-controller:latest .
```

---

## Step 4 — Create `.dockerignore`

**File:** `.dockerignore` (at the project root)

**Why:** Prevents Docker from copying huge unnecessary folders (`node_modules`, `venv`, `.git`, the target-app itself) into the build context. This keeps the image lean and the build fast.

```
# Python
__pycache__/
*.pyc
*.pyo
framework-controller/venv/
framework-controller/__pycache__/
framework-controller/*.json
framework-controller/*.md

# Node
frontend/node_modules/
frontend/dist/

# Git
.git/
.gitignore

# Target App (not part of the framework image)
target-app/

# Misc
*.env
.env
```

---

## Step 5 — Create `Jenkinsfile`

**File:** `Jenkinsfile` (at the project root)

**Why:** This is the file that users copy into their own repo. Jenkins automatically detects it and runs it. It defines the 5-stage pipeline with the interactive approval gate.

```groovy
pipeline {
    agent any

    environment {
        // Jenkins credential ID for the Gemini API key.
        // Add yours at: Jenkins → Manage Jenkins → Credentials
        GEMINI_API_KEY = credentials('gemini-api-key')
        
        // The port your app's entry point is exposed on (for the dashboard link)
        APP_PORT = '8000'
        
        // Path to your docker-compose file (relative to repo root)
        COMPOSE_FILE = 'docker-compose.yml'
    }

    stages {

        stage('Build & Deploy Application') {
            steps {
                echo '🔨 Building and starting the application...'
                sh "docker compose -f ${COMPOSE_FILE} up --build -d"
                sh "sleep 10" // Wait for services to be healthy
                echo '✅ Application is running.'
            }
        }

        stage('Start ChaosController') {
            steps {
                echo '🔥 Starting ChaosController...'
                sh """
                    docker run -d \\
                        --name chaos-controller-ci \\
                        --network host \\
                        -v /var/run/docker.sock:/var/run/docker.sock \\
                        -e GEMINI_API_KEY=${GEMINI_API_KEY} \\
                        chaos-controller:latest
                """
                sh "sleep 5" // Wait for controller to boot
                echo '✅ ChaosController is running.'
            }
        }

        stage('Resilience Testing Gate') {
            steps {
                script {
                    // Get the Jenkins agent's IP/hostname for the dashboard link
                    def agentHost = sh(script: "hostname -I | awk '{print \$1}'", returnStdout: true).trim()

                    echo """
╔══════════════════════════════════════════════════════════════╗
║           🔥  RESILIENCE TESTING GATE  🔥                    ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║   Dashboard: http://${agentHost}:5050                        ║
║                                                              ║
║   Your services have been auto-discovered.                   ║
║   Open the dashboard to:                                     ║
║     • Inject faults (latency, crash, CPU, packet loss...)   ║
║     • Run 3-phase chaos experiments                          ║
║     • Get AI-powered remediation reports (Gemini)            ║
║                                                              ║
║   When you are satisfied, come back here and click APPROVE.  ║
║   Click REJECT to fail the build and iterate on fixes.       ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
                    """

                    // ← PIPELINE PAUSES HERE
                    // Jenkins shows an Approve/Reject button in the UI
                    def decision = input(
                        id: 'ResilienceApproval',
                        message: 'Resilience Testing Complete?',
                        submitter: '', // any user can approve; lock down with a Jenkins user/group
                        parameters: [],
                        ok: 'Approve — System is resilient, continue to deploy'
                    )
                    
                    echo '✅ Resilience gate APPROVED. Proceeding to deployment.'
                }
            }
        }

        stage('Deploy to Production') {
            steps {
                echo '🚀 Deploying to production...'
                // Replace this with your actual deploy step:
                // e.g., kubectl apply, helm upgrade, SSH deploy, etc.
                echo 'Deploy step goes here.'
            }
        }
    }

    post {
        always {
            echo '🧹 Cleaning up ChaosController...'
            sh 'docker stop chaos-controller-ci || true'
            sh 'docker rm chaos-controller-ci || true'
        }
        failure {
            echo '❌ Pipeline REJECTED or failed. Clean up application containers.'
            sh "docker compose -f ${COMPOSE_FILE} down || true"
        }
    }
}
```

---

## Step 6 — Create `chaos-controller.example.yml`

**File:** `chaos-controller.example.yml` (at the project root)

**Why:** For teams who prefer to run the controller as part of their existing `docker-compose.yml` rather than a separate `docker run`. They can paste this service block into their own compose file.

```yaml
# ─────────────────────────────────────────────────────────
# Add this service to your existing docker-compose.yml
# to run ChaosController alongside your application.
# ─────────────────────────────────────────────────────────

services:
  chaos-controller:
    image: chaos-controller:latest  # or ghcr.io/your-org/chaos-controller
    ports:
      - "5050:5050"
    volumes:
      # Docker socket access — required for container discovery & fault injection
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      # Optional overrides:
      # - PROMETHEUS_URL=http://prometheus:9090
      # - HEALTH_PATH=/health
      # - HEALTH_TIMEOUT=15
    depends_on: []  # Add your service names here if needed
    restart: unless-stopped

# ─────────────────────────────────────────────────────────
# IMPORTANT: Your target services need these additions:
#
#   services:
#     your-service:
#       build: .
#       cap_add:
#         - NET_ADMIN
#       privileged: true
#
# And your Dockerfile must install:
#   RUN apt-get update && apt-get install -y iproute2 stress-ng
# ─────────────────────────────────────────────────────────
```

---

## Step 7 — Create `docs/JENKINS_INTEGRATION.md`

**File:** `docs/JENKINS_INTEGRATION.md` (create the `docs/` directory)

**Why:** The user-facing guide for teams integrating this into their own pipeline. Clear, short, actionable.

```markdown
# Jenkins Integration Guide

This guide explains how to add ChaosController as an interactive resilience testing stage in any Jenkins pipeline.

---

## Prerequisites

- Jenkins with Docker installed on the agent
- A Jenkins credential named `gemini-api-key` (Secret text) — your Gemini API key
- Your application deployed via Docker Compose

---

## Step 1: Prepare Your Containers (One-Time)

Add these to **each service** you want to test in your `docker-compose.yml`:

```yaml
services:
  your-service:
    build: .
    cap_add:
      - NET_ADMIN     # Required for tc/iptables network fault injection
    privileged: true  # Required for stress-ng resource injection
```

Add these to each service's **Dockerfile**:

```dockerfile
RUN apt-get update && apt-get install -y iproute2 stress-ng && rm -rf /var/lib/apt/lists/*
```

---

## Step 2: Build the ChaosController Image

Build once on your Jenkins agent (or add to your agent setup):

```bash
git clone https://github.com/your-org/chaos-controller.git
cd chaos-controller
docker build -t chaos-controller:latest .
```

---

## Step 3: Add the Jenkinsfile

Copy the provided `Jenkinsfile` from this repo into your project root. Adjust:
- `COMPOSE_FILE` — path to your `docker-compose.yml`
- `APP_PORT` — your app's main port
- The `Deploy to Production` stage — replace the placeholder with your real deploy step

---

## Step 4: Add Jenkins Credential

1. Jenkins → Manage Jenkins → Credentials → Global → Add Credential
2. Kind: **Secret text**
3. ID: `gemini-api-key`
4. Secret: Your Gemini API key (from https://aistudio.google.com/)

---

## How the Pipeline Works

When the pipeline reaches the **Resilience Testing Gate** stage:

1. The pipeline **pauses** automatically
2. Console output prints the dashboard URL (e.g., `http://192.168.1.10:5050`)
3. Open the URL in your browser — the ChaosController dashboard loads
4. Your running Docker Compose services are **auto-discovered** (no config needed)
5. Test freely:
   - Inject faults on individual services
   - Run structured 3-phase experiments
   - Get AI remediation reports
6. Return to Jenkins and click **Approve** or **Reject**

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Services not discovered | Ensure they were started with `docker compose up` (not bare `docker run`) |
| `tc: Operation not permitted` | Add `cap_add: NET_ADMIN` and `privileged: true` to the service |
| `stress-ng not found` | Add `RUN apt-get install -y stress-ng` to the service Dockerfile |
| Dashboard shows blank | Wait 5 seconds and refresh — controller may still be booting |
| Pipeline won't pause | Ensure the `input` step in the Jenkinsfile is not wrapped in a `timeout` |
```

---

## Step 8 — Update `README.md`

**File:** `README.md` (project root)

**What to add:** A new `## CI/CD Integration` section after `## Quick Start`, with a short overview and link to `docs/JENKINS_INTEGRATION.md`.

```markdown
## CI/CD Integration (Jenkins)

ChaosController can be added as an **interactive resilience gate** to any Jenkins pipeline.
When triggered, the pipeline pauses and presents developers with the dashboard URL.
Developers test their scenarios, review AI reports, then click **Approve** to continue
the pipeline — or **Reject** to fail the build.

→ **[Full Jenkins Integration Guide](docs/JENKINS_INTEGRATION.md)**

### Quick Snippet

Add this `docker run` to your Jenkinsfile after deploying your app:

```bash
docker run -d \
  --name chaos-controller-ci \
  --network host \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e GEMINI_API_KEY=${GEMINI_API_KEY} \
  chaos-controller:latest
```

Then pause the pipeline with:

```groovy
input message: 'Resilience testing ready. Open http://<agent>:5050',
      ok: 'Approve — System is resilient'
```
```

---

## Step 9 — Verify Everything

### 9.1 Build the image
```bash
cd /home/aagnik/Failure_injection_Major_Project
docker build -t chaos-controller:latest .
```
Expected: Build completes without errors. Image size should be ~400–600MB.

### 9.2 Test standalone (no Jenkins)
```bash
# Start the target-app (or any docker compose app)
cd target-app && docker compose up -d && cd ..

# Run the chaos-controller image
docker run -d \
  --name chaos-test \
  --network host \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e GEMINI_API_KEY=your-key-here \
  chaos-controller:latest

# Check it started correctly
docker logs chaos-test
```
Expected log output: `INFO: Application startup complete.` and `Uvicorn running on http://0.0.0.0:5050`

### 9.3 Verify dashboard
Open `http://localhost:5050` in your browser.
Expected: The ChaosController React dashboard loads (NOT a 404). Services discovered from target-app should appear in the sidebar.

### 9.4 Verify API works
```bash
curl http://localhost:5050/status
curl http://localhost:5050/faults
```
Expected: JSON responses with `services` and `faults` arrays.

### 9.5 Cleanup
```bash
docker stop chaos-test && docker rm chaos-test
cd target-app && docker compose down
```

---

## Summary of All Files Created/Modified

| Action | File | Purpose |
|--------|------|---------|
| **CREATE** | `Dockerfile` | Multi-stage build: React → Python image |
| **CREATE** | `.dockerignore` | Exclude node_modules, venv, .git, target-app |
| **CREATE** | `Jenkinsfile` | 5-stage pipeline with interactive approval gate |
| **CREATE** | `chaos-controller.example.yml` | Docker Compose snippet for non-Jenkins usage |
| **CREATE** | `docs/JENKINS_INTEGRATION.md` | Full user guide for Jenkins integration |
| **MODIFY** | `framework-controller/main.py` | Add StaticFiles mount for built frontend |
| **MODIFY** | `frontend/src/App.jsx` | Make API URL relative in production |
| **MODIFY** | `README.md` | Add CI/CD Integration section |
