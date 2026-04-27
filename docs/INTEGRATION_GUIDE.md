# ChaosController — Integration Guide

## How to Test Your Application with the Resilience Gate

This guide walks you through integrating the ChaosController resilience testing framework into your own application's CI/CD pipeline. By the end, your pipeline will automatically test your application for latency resilience, CPU stress handling, and security payload vulnerabilities — and block deployments that fail.

---

## Prerequisites

Your application must:
1. **Run in Docker** (via Docker Compose or individual containers)
2. Have at least one **health check endpoint** (e.g. `GET /health` returning 200)
3. Your pipeline server must have **Docker installed**

The framework needs:
- A **Gemini API key** for AI analysis (free tier works) — [get one here](https://aistudio.google.com/app/apikey)

---

## Step 1: Prepare Your Application

### 1a. Enable Fault Injection Capabilities

For latency and CPU stress injection to work, your application's Docker containers need elevated capabilities. Add these to each service in your `docker-compose.yml`:

```yaml
services:
  your-service:
    build: .
    cap_add:
      - NET_ADMIN   # Required for network latency injection (tc/netem)
    privileged: true  # Required for stress-ng CPU injection
```

### 1b. Install Fault Tools in Your Dockerfile

Your application's `Dockerfile` needs two tools installed: `iproute2` (for network shaping) and `stress-ng` (for CPU stress). Add this to your Dockerfile:

**For Debian/Ubuntu-based images:**
```dockerfile
RUN apt-get update && apt-get install -y iproute2 stress-ng && rm -rf /var/lib/apt/lists/*
```

**For Alpine-based images:**
```dockerfile
RUN apk add --no-cache iproute2 stress-ng
```

**Example complete Dockerfile:**
```dockerfile
FROM python:3.11-slim

# Install fault injection tools
RUN apt-get update && apt-get install -y iproute2 stress-ng && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

> **Note:** If you only want payload/security testing (no latency/CPU injection), you can skip this step. Payload tests work against any HTTP endpoint.

---

## Step 2: Create Your Chaos Configuration

Create a file called `chaos-config.yml` in the **root of your repository**.

```yaml
version: "1.0"
project: "my-app"   # Human-readable name, appears in reports

controller:
  url: "http://localhost:5050"   # ChaosController address
  timeout_seconds: 300

thresholds:
  # Fail gate if latency during fault is >50% worse than baseline
  latency_regression_percent: 50

  # Fail gate if more than 5% of security payloads return 5xx
  max_5xx_rate_percent: 5

  # Fail gate if any payload causes a crash or timeout
  max_payload_crash_rate_percent: 0

services:
  - name: my-api           # Must match your Docker Compose service name exactly
    probe_url: "http://my-api:8000/health"    # Use container name in CI, localhost locally
    openapi_url: "http://my-api:8000/openapi.json"  # For dynamic fuzzing (optional)
    # bearer_token_env: "TEST_JWT_TOKEN"      # Uncomment if your API requires auth

tests:
  # Test 1: Inject 3s of network latency and measure impact
  - id: "latency-my-api"
    type: latency
    target: my-api
    params:
      delay_ms: 3000
      num_requests: 5
    on_fail: block

  # Test 2: Stress the CPU and measure impact on response times
  - id: "cpu-stress-my-api"
    type: stress
    target: my-api
    params:
      cpu: 2
      stress_timeout: 20
      num_requests: 5
    on_fail: block

  # Test 3: Fuzz all API endpoints with malformed/malicious payloads
  # Also runs a 3-phase Huge JSON bombing degradation test
  - id: "payload-suite-my-api"
    type: payload
    target: my-api
    params:
      max_operations: 10
      max_cases_per_operation: 15
    on_fail: block

report:
  output_path: "chaos-report.html"
  json_path: "chaos-report.json"
  ai_summary: true
  fail_on: "block"
```

> **Tip:** Run `chaos-runner validate --config chaos-config.yml` to verify your config before committing.

---

## Step 3: Build the ChaosController Image

```bash
# Clone the framework repository
git clone https://github.com/Anoint2612/Failure_injection_Major_Project.git
cd Failure_injection_Major_Project

# Build the all-in-one image (bundles React UI + FastAPI backend)
docker build -t chaos-controller:latest .

# Optional: push to a registry so CI can pull it
docker tag chaos-controller:latest your-registry/chaos-controller:latest
docker push your-registry/chaos-controller:latest
```

---

## Step 4A: Jenkins Integration

### Jenkins Prerequisites
- Jenkins with Docker available on the build agent
- **Pipeline** plugin installed
- `GEMINI_API_KEY` stored as a Jenkins Secret Text credential (Manage Jenkins → Credentials → Global → Add Credential → Secret text, ID: `gemini-api-key`)

### Jenkinsfile

Add this `Jenkinsfile` to the root of **your** repository:

```groovy
pipeline {
    agent any

    environment {
        GEMINI_API_KEY   = credentials('gemini-api-key')  // Jenkins credential ID
        COMPOSE_FILE     = 'docker-compose.yml'           // Your app's compose file
        APP_NETWORK      = 'myapp_default'                // Your compose network name
        CHAOS_IMAGE      = 'chaos-controller:latest'      // Or your registry image
        CHAOS_CONTAINER  = 'chaos-controller-ci'
        CHAOS_FW_DIR     = '/tmp/chaos-framework'         // Where to clone the framework
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        // Build your app AND start the ChaosController in parallel.
        // The controller warms up while your app builds, saving time.
        stage('Build & Initialize') {
            parallel {

                stage('Build & Start Application') {
                    steps {
                        echo 'Building and starting the application...'
                        sh "docker compose -f ${COMPOSE_FILE} up --build -d"
                        echo 'Application stack started.'
                    }
                }

                stage('Start ChaosController') {
                    steps {
                        echo 'Cloning and starting ChaosController...'
                        sh "rm -rf ${CHAOS_FW_DIR}"
                        sh "git clone https://github.com/Anoint2612/Failure_injection_Major_Project.git ${CHAOS_FW_DIR}"
                        sh "docker build -t ${CHAOS_IMAGE} ${CHAOS_FW_DIR}/"
                        sh "docker rm -f ${CHAOS_CONTAINER} 2>/dev/null || true"
                        sh """
                            docker run -d \\
                                --name ${CHAOS_CONTAINER} \\
                                --network ${APP_NETWORK} \\
                                -p 5050:5050 \\
                                -v /var/run/docker.sock:/var/run/docker.sock \\
                                -e GEMINI_API_KEY=${GEMINI_API_KEY} \\
                                ${CHAOS_IMAGE}
                        """
                        // Poll until ChaosController is ready (up to 60s)
                        sh '''
                            for i in $(seq 1 12); do
                                curl -sf http://localhost:5050/status > /dev/null && echo "ChaosController ready!" && exit 0
                                echo "Waiting for ChaosController... ($i/12)"
                                sleep 5
                            done
                            echo "ERROR: ChaosController did not start!" && exit 1
                        '''
                        echo 'ChaosController is ready.'
                    }
                }
            }
        }

        stage('Application Health Check') {
            steps {
                sh '''
                    echo "Waiting for application to be healthy..."
                    for i in $(seq 1 24); do
                        curl -sf http://localhost:8000/health > /dev/null && echo "App is healthy!" && exit 0
                        echo "Waiting... ($i/24)"
                        sleep 5
                    done
                    echo "ERROR: Application did not become healthy!" && exit 1
                '''
            }
        }

        stage('Resilience Gate') {
            steps {
                sh """
                    pip3 install -e ${CHAOS_FW_DIR}/ --quiet

                    chaos-runner run \\
                        --config chaos-config.yml \\
                        --controller-url http://localhost:5050 \\
                        --code-path .
                """
                // chaos-runner exits 1 on failure → Jenkins marks stage FAILED
                // chaos-runner exits 0 on pass  → pipeline continues to deploy
            }
            post {
                always {
                    archiveArtifacts artifacts: 'chaos-report.html, chaos-report.json',
                                     allowEmptyArchive: true
                    publishHTML(target: [
                        allowMissing         : true,
                        alwaysLinkToLastBuild: true,
                        keepAll              : true,
                        reportDir            : '.',
                        reportFiles          : 'chaos-report.html',
                        reportName           : 'Resilience Gate Report'
                    ])
                }
            }
        }

        stage('Deploy to Production') {
            steps {
                echo 'Resilience gate passed — deploying...'
                // Your actual deploy step:
                // sh 'kubectl apply -f k8s/'
                // sh 'helm upgrade --install my-app ./charts/my-app'
            }
        }
    }

    post {
        always {
            sh "docker stop ${CHAOS_CONTAINER} 2>/dev/null || true"
            sh "docker rm ${CHAOS_CONTAINER} 2>/dev/null || true"
            sh "docker compose -f ${COMPOSE_FILE} down 2>/dev/null || true"
        }
    }
}
```

### Finding Your Compose Network Name

```bash
# Start your app once locally
docker compose up -d

# List networks — look for one matching your project directory name
docker network ls
# Example output:
# myapp_default   bridge
```

Set `APP_NETWORK = 'myapp_default'` in the Jenkinsfile.

---

## Step 4B: GitHub Actions Integration

### GitHub Actions Prerequisites
- Repository on GitHub
- Add secrets under **Settings → Secrets and variables → Actions**:
  - `GEMINI_API_KEY` — your Gemini API key
  - `TEST_JWT_TOKEN` — (optional) a test JWT if your API requires authentication

### Workflow File

Create `.github/workflows/resilience.yml` in **your** repository:

```yaml
name: Resilience Gate

on:
  push:
    branches: [main, master, develop]
  pull_request:
    branches: [main, master]
  workflow_dispatch:

concurrency:
  group: resilience-${{ github.ref }}
  cancel-in-progress: true

jobs:
  resilience-gate:
    name: Resilience Gate
    runs-on: ubuntu-latest
    timeout-minutes: 30

    env:
      GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
      TEST_JWT_TOKEN: ${{ secrets.TEST_JWT_TOKEN }}

    steps:

      - name: Checkout your application
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      # Clone and install the chaos-runner CLI
      - name: Install chaos-runner
        run: |
          git clone https://github.com/Anoint2612/Failure_injection_Major_Project.git /tmp/chaos-fw
          pip install -e /tmp/chaos-fw/ --quiet
          chaos-runner --version

      # Start your application
      - name: Build & Start Application
        run: docker compose up --build -d

      # Detect the network your compose stack created, then start the controller on it
      - name: Start ChaosController
        run: |
          APP_NETWORK=$(docker network ls --format "{{.Name}}" | grep "$(basename $PWD)" | head -1)
          echo "Detected app network: $APP_NETWORK"

          docker build -t chaos-controller:latest /tmp/chaos-fw/

          docker run -d \
            --name chaos-controller-ci \
            --network "$APP_NETWORK" \
            -p 5050:5050 \
            -v /var/run/docker.sock:/var/run/docker.sock \
            -e GEMINI_API_KEY="${{ secrets.GEMINI_API_KEY }}" \
            chaos-controller:latest

          echo "ChaosController started."

      # Wait for both your app and the controller to be healthy
      - name: Wait for services
        run: |
          for i in $(seq 1 24); do
            curl -sf http://localhost:8000/health > /dev/null && echo "App ready!" && break
            echo "  Waiting for app... ($i/24)"; sleep 5
          done
          for i in $(seq 1 12); do
            curl -sf http://localhost:5050/status > /dev/null && echo "Controller ready!" && break
            echo "  Waiting for controller... ($i/12)"; sleep 5
          done

      # Validate your chaos-config.yml before running
      - name: Validate config
        run: chaos-runner validate --config chaos-config.yml

      # THE GATE: exit 0 = pass, exit 1 = fail (blocks the workflow)
      - name: Run Resilience Gate
        run: |
          chaos-runner run \
            --config chaos-config.yml \
            --controller-url http://localhost:5050 \
            --code-path .

      # Upload the HTML and JSON reports as downloadable artifacts
      - name: Upload Resilience Report
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: chaos-resilience-report-${{ github.run_number }}
          path: |
            chaos-report.html
            chaos-report.json
          retention-days: 30

      # Post a summary table as a PR comment
      - name: Post PR Comment
        uses: actions/github-script@v7
        if: github.event_name == 'pull_request' && always()
        with:
          script: |
            const fs = require('fs');
            let body = '### Resilience Gate Results\n\n';
            try {
              const report = JSON.parse(fs.readFileSync('chaos-report.json', 'utf8'));
              const icon = report.overall === 'PASS' ? '✅' : '❌';
              body += `**${icon} Gate: ${report.overall}**\n\n`;
              body += `| Test | Type | Status | Issues |\n|---|---|---|---|\n`;
              for (const v of report.verdicts) {
                body += `| ${v.test_id} | ${v.type} | ${v.status} | ${v.reasons.join('; ') || '—'} |\n`;
              }
              const verdict = report.ai_verdict?.match(/Production Verdict[\s\S]*?\n([^\n]+)/);
              if (verdict) body += `\n> **AI**: ${verdict[1].trim()}\n`;
              body += `\n[View full report](${process.env.GITHUB_SERVER_URL}/${process.env.GITHUB_REPOSITORY}/actions/runs/${process.env.GITHUB_RUN_ID})`;
            } catch(e) {
              body += `Report not available: ${e}`;
            }
            await github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body
            });

      - name: Cleanup
        if: always()
        run: |
          docker stop chaos-controller-ci 2>/dev/null || true
          docker rm chaos-controller-ci 2>/dev/null || true
          docker compose down 2>/dev/null || true
```

---

## Step 5: Probe URL — Local vs CI

The most common mistake. In CI, services talk to each other by **container name**, not `localhost`:

| Environment | probe_url |
|---|---|
| Local dev | `http://localhost:8000/health` |
| CI (same Docker network) | `http://my-api:8000/health` |

Update your `chaos-config.yml` `probe_url` fields to use the container/service name when running in CI.

---

## Step 6: Local Manual Testing (Web UI)

```bash
# 1. Start your application
cd your-app && docker compose up -d

# 2. Find the network
docker network ls | grep your-app

# 3. Start ChaosController attached to that network
TARGET_NETWORK=your-app_default docker compose \
  -f /path/to/Failure_injection_Major_Project/docker-compose.yml up -d

# 4. Open the dashboard
open http://localhost:5050

# 5. Run the automated gate locally
cd your-app
chaos-runner run \
  --config chaos-config.yml \
  --controller-url http://localhost:5050 \
  --code-path .

# 6. Open the report
open chaos-report.html
```

---

## Reference: Test Types

| Type | What it does | Key params |
|---|---|---|
| `latency` | Injects network delay via `tc netem`, measures latency regression | `delay_ms`, `num_requests` |
| `stress` | Runs `stress-ng` CPU workers, measures performance degradation | `cpu`, `stress_timeout`, `num_requests` |
| `payload` | Fuzzes all OpenAPI endpoints with malformed/SQLi/XSS/type-confusion payloads + 3-phase JSON bombing | `max_operations`, `max_cases_per_operation` |

## Reference: on_fail Values

| Value | Behavior |
|---|---|
| `block` | Gate FAILS (exit code 1) — deployment is blocked |
| `warn` | Issue is logged in the report — gate still PASSES (exit code 0) |

## Reference: Thresholds

| Field | Default | Description |
|---|---|---|
| `latency_regression_percent` | 50 | Max allowed % latency increase during fault vs baseline |
| `max_5xx_rate_percent` | 5 | Max % of payload cases that may return 5xx errors |
| `max_payload_crash_rate_percent` | 0 | Max % of cases that may crash/timeout (0 = zero tolerance) |

---

## Troubleshooting

**`Cannot reach ChaosController at http://localhost:5050`**
- Check it is running: `docker ps | grep chaos-controller`
- In CI, ensure both containers are on the same Docker network

**`OpenAPI Fuzzing failed — fell back to 5 hardcoded tests`**
- Confirm your service exposes `/openapi.json`
- Verify the `openapi_url` uses the container name (not `localhost`) in CI

**`Latency regression = 0% even with 3000ms delay`**
- Ensure containers have `cap_add: [NET_ADMIN]` and `privileged: true`
- Ensure `iproute2` is installed inside the container image

**`GEMINI_API_KEY not set — AI verdict unavailable`**
- Gate still works without AI (threshold-based evaluation only)
- Add the key as a Jenkins credential or GitHub Actions secret to enable AI verdict + code review
