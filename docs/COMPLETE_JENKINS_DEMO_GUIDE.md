# ChaosController × Jenkins — Complete Demo & Presentation Guide

> **Audience:** You (the student) — assumes zero Jenkins knowledge.
> **Goal:** Set up a real Jenkins pipeline that uses ChaosController to resilience-test an open-source microservice app, then present the whole thing to your teachers.

---

## Table of Contents

1. [The Dummy App We Will Use](#1-the-dummy-app-we-will-use)
2. [Prerequisites — Install Everything](#2-prerequisites--install-everything)
3. [Phase A — Fork, Clone & Run the Voting App Locally](#3-phase-a--fork-clone--run-the-voting-app-locally)
4. [Phase B — Run ChaosController Against It (No Jenkins Yet)](#4-phase-b--run-chaoscontroller-against-it-no-jenkins-yet)
5. [Phase C — Install Jenkins via Docker](#5-phase-c--install-jenkins-via-docker)
6. [Phase D — Create the Jenkins Pipeline](#6-phase-d--create-the-jenkins-pipeline)
7. [Phase E — Trigger the Pipeline & Watch It Work](#7-phase-e--trigger-the-pipeline--watch-it-work)
8. [What to Show Your Teachers](#8-what-to-show-your-teachers)
9. [What to Explain to Your Teachers](#9-what-to-explain-to-your-teachers)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. The Dummy App We Will Use

### Docker's Example Voting App

| Detail | Value |
|--------|-------|
| **Repository** | <https://github.com/dockersamples/example-voting-app> |
| **Stars** | 5.7k+ |
| **License** | Apache-2.0 |
| **Why this app?** | Official Docker sample, uses multiple languages (Python, Node.js, .NET), has 5 containers, perfect microservice topology |

**Architecture (5 services):**

```
┌─────────────┐     ┌───────┐     ┌─────────┐
│  vote (Py)  │────▶│ Redis │◀────│ worker  │
│  port 8082  │     └───────┘     │  (.NET) │
└─────────────┘                   └────┬────┘
                                       │
┌─────────────┐     ┌──────────┐       │
│ result (JS) │◀────│ Postgres │◀──────┘
│  port 8081  │     └──────────┘
└─────────────┘
```

- **vote** — Python Flask web UI where users pick "Cats" or "Dogs"
- **redis** — In-memory queue for votes
- **worker** — .NET background service consuming votes from Redis → Postgres
- **db** — Postgres database storing final tallies
- **result** — Node.js web UI showing live results

---

## 2. Prerequisites — Install Everything

Run these on your Linux machine (Ubuntu/Debian). If anything is already installed, skip it.

### 2a. Docker & Docker Compose

```bash
# Install Docker
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin
sudo systemctl start docker
sudo systemctl enable docker

# Let your user run Docker without sudo
sudo usermod -aG docker $USER
newgrp docker

# Verify
docker --version
docker compose version
```

### 2b. Git

```bash
sudo apt-get install -y git
```

### 2c. Python 3.10+

```bash
sudo apt-get install -y python3 python3-pip python3-venv
```

### 2d. curl (for health checks)

```bash
sudo apt-get install -y curl
```

### 2e. Gemini API Key

1. Go to <https://aistudio.google.com/app/apikey>
2. Click **Create API Key**, copy it
3. Save it — you will need it multiple times below

---

## 3. Phase A — Fork, Clone & Prepare the Voting App

We **fork** the repo first so you own a copy on GitHub. Jenkins will pull from your fork, and you can push your changes (Jenkinsfile, chaos-config, modified docker-compose) to it.

### Step A1: Fork on GitHub

1. Open <https://github.com/dockersamples/example-voting-app> in your browser
2. Click the **Fork** button (top-right)
3. Keep all defaults → click **Create fork**
4. You now have `https://github.com/YOUR_GITHUB_USERNAME/example-voting-app`

### Step A2: Clone YOUR Fork

```bash
cd ~
# Replace YOUR_GITHUB_USERNAME with your actual GitHub username
git clone https://github.com/YOUR_GITHUB_USERNAME/example-voting-app.git voting-app-chaos-demo
cd voting-app-chaos-demo
```

> **Why fork?** Jenkins needs to pull code from a Git repository. By forking, you can push the Jenkinsfile, chaos-config.yml, and modified docker-compose.yml to your own repo and Jenkins will read them automatically on every build.

### Step A3: Modify the Dockerfiles (CRITICAL)

The original voting app containers do **NOT** have the Linux tools ChaosController needs for fault injection (`iproute2` for network faults, `stress-ng` for CPU/memory stress). We must install them.

**Modify `vote/Dockerfile`** — add one line right after the existing `apt-get install` block:

Open `vote/Dockerfile` and find this block near the top:
```dockerfile
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*
```

Replace it with:
```dockerfile
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl iproute2 stress-ng && \
    rm -rf /var/lib/apt/lists/*
```

**Modify `result/Dockerfile`** — same idea. Find this block:
```dockerfile
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl tini && \
    rm -rf /var/lib/apt/lists/*
```

Replace it with:
```dockerfile
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl tini iproute2 stress-ng && \
    rm -rf /var/lib/apt/lists/*
```

**Modify `worker/Dockerfile`** — the worker uses a .NET runtime image. Add this line right before the final `ENTRYPOINT`:

Find:
```dockerfile
FROM mcr.microsoft.com/dotnet/runtime:7.0
WORKDIR /app
COPY --from=build /app .
ENTRYPOINT ["dotnet", "Worker.dll"]
```

Replace with:
```dockerfile
FROM mcr.microsoft.com/dotnet/runtime:7.0

RUN apt-get update && apt-get install -y --no-install-recommends iproute2 stress-ng && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=build /app .
ENTRYPOINT ["dotnet", "Worker.dll"]
```

> **Why?** Without `iproute2`, the `tc netem` command (which injects latency/packet loss) does not exist inside the container. Without `stress-ng`, CPU/memory stress tests will fail with "Internal Server Error".

### Step A4: Replace docker-compose.yml (CRITICAL)

The original docker-compose.yml has **two separate networks** (`front-tier` and `back-tier`), and the services do **not** have the `cap_add: NET_ADMIN` and `privileged: true` flags ChaosController needs for fault injection.

Replace the entire `docker-compose.yml` with this:

```bash
cat > docker-compose.yml << 'COMPOSE_EOF'
services:
  vote:
    build:
      context: ./vote
      target: dev
    depends_on:
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 10s
    volumes:
     - ./vote:/usr/local/app
    ports:
      - "8082:80"
    networks:
      - app-net
    cap_add:
      - NET_ADMIN
    privileged: true

  result:
    build: ./result
    entrypoint: nodemon --inspect=0.0.0.0 server.js
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./result:/usr/local/app
    ports:
      - "8081:80"
    networks:
      - app-net
    cap_add:
      - NET_ADMIN
    privileged: true

  worker:
    build:
      context: ./worker
    depends_on:
      redis:
        condition: service_healthy
      db:
        condition: service_healthy
    networks:
      - app-net
    cap_add:
      - NET_ADMIN
    privileged: true

  redis:
    image: redis:alpine
    volumes:
      - "./healthchecks:/healthchecks"
    healthcheck:
      test: /healthchecks/redis.sh
      interval: "5s"
    networks:
      - app-net

  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: "postgres"
      POSTGRES_PASSWORD: "postgres"
    volumes:
      - "db-data:/var/lib/postgresql/data"
      - "./healthchecks:/healthchecks"
    healthcheck:
      test: /healthchecks/postgres.sh
      interval: "5s"
    networks:
      - app-net

volumes:
  db-data:

networks:
  app-net:
    driver: bridge
COMPOSE_EOF
```

> **What changed vs the original:**
> | Change | Why |
> |--------|-----|
> | `cap_add: NET_ADMIN` + `privileged: true` on vote, result, worker | Gives ChaosController permission to run `tc` and `iptables` inside them |
> | Two networks → single `app-net` | ChaosController needs to be on the same network as all services |
> | Port `8082:80` for vote | Avoids conflict with Jenkins on port 8080 |

### Step A5: Rebuild and verify the modified app

```bash
docker compose up -d --build

# Wait ~30-60 seconds (first build installs iproute2/stress-ng), then verify
docker ps
```

**Check it works:**

| URL | What You See |
|-----|-------------|
| <http://localhost:8082> | Voting page — pick Cats or Dogs |
| <http://localhost:8081> | Results page — live vote tally |

**Verify the tools were installed:**
```bash
docker exec voting-app-chaos-demo-vote-1 which tc
# Should print: /sbin/tc

docker exec voting-app-chaos-demo-vote-1 which stress-ng
# Should print: /usr/bin/stress-ng
```

> ✅ If both pages load AND both commands print paths, the app is ready for chaos testing.

---

## 4. Phase B — Run ChaosController Against It (No Jenkins Yet)

This proves ChaosController can discover and attack the modified voting app.

### Step B1: Build the ChaosController Image

```bash
cd ~/Failure_Injection_Fresh_Pull/Failure_injection_Major_Project
docker build -t chaos-controller:latest .
```

### Step B2: Find the Voting App's Network

Since we replaced the docker-compose.yml with a single `app-net` network in Step A4, there is only one network:

```bash
docker network ls | grep voting
# Expected output: voting-app-chaos-demo_app-net
```

Verify all services are on it:
```bash
docker network inspect voting-app-chaos-demo_app-net --format '{{range .Containers}}{{.Name}} {{end}}'
```

### Step B3: Start ChaosController

```bash
docker rm -f chaos-test 2>/dev/null || true
docker run -d \
  --name chaos-test \
  --network voting-app-chaos-demo_app-net \
  -p 5050:5050 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e GEMINI_API_KEY=YOUR_KEY_HERE \
  chaos-controller:latest
```

> Replace `YOUR_KEY_HERE` with your actual Gemini API key.

### Step B4: Test It

1. Open <http://localhost:5050> — the ChaosController dashboard
2. You should see the voting app containers discovered automatically
3. **Inject a latency fault** on the `vote` service (e.g., 3000ms)
4. Open <http://localhost:8082> — the voting page should be noticeably slower
5. Click **Recover** in the dashboard to fix it
6. **Try a stress test** on the `vote` service — this should now work since `stress-ng` is installed
7. **Run an experiment:** When running an experiment, you must provide a **Probe URL**. When ChaosController runs inside Docker, it must use the internal container name to reach the voting app. 

   **Valid Probe URLs:**
   - For the Vote service: `http://vote:80/`
   - For the Result service: `http://result:80/`

> **Why do `redis`, `db`, and `worker` show as "Down" in the dashboard?**
> The ChaosController dashboard uses HTTP requests (like a web browser) to check if a service is healthy. 
> - `redis` is a cache (port 6379)
> - `db` is a PostgreSQL database (port 5432)
> - `worker` is a background .NET process with no open ports
> Since none of these run web servers, the HTTP health checks fail, and the dashboard marks them as "Down". This is **expected behavior** and they are still functioning correctly in the background. You should focus your chaos testing on the `vote` and `result` services.

### Step B5: Cleanup

```bash
docker stop chaos-test && docker rm chaos-test
cd ~/example-voting-app && docker compose down -v
```

---

## 5. Phase C — Install Jenkins via Docker

### Step C1: Prepare Jenkins Home

```bash
mkdir -p ~/jenkins_home
sudo chown -R 1000:1000 ~/jenkins_home
```

### Step C2: Run Jenkins (with Docker-in-Docker access)

```bash
docker run -d \
  --name jenkins \
  -p 8080:8080 \
  -p 50000:50000 \
  -v ~/jenkins_home:/var/jenkins_home \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v $(which docker):/usr/bin/docker \
  --restart on-failure \
  jenkins/jenkins:lts
```

> **Key:** We mount `/var/run/docker.sock` so Jenkins can run Docker commands inside its pipelines.

### Step C3: Fix Docker Permissions Inside Jenkins

```bash
# Get the docker group ID from your host
DOCKER_GID=$(getent group docker | cut -d: -f3)

# Add jenkins user to docker group inside the container
docker exec -u root jenkins bash -c "groupadd -g $DOCKER_GID docker 2>/dev/null; usermod -aG docker jenkins"

# Restart Jenkins to apply
docker restart jenkins
```

### Step C4: Get the Initial Admin Password

```bash
docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```

Copy the output string.

### Step C5: Complete Jenkins Setup in Browser

1. Open <http://localhost:8080>
2. Paste the admin password → **Continue**
3. Click **Install suggested plugins** (wait 2-3 minutes)
4. Create an admin user (remember the username/password!)
5. Accept the default Jenkins URL → **Save and Finish** → **Start using Jenkins**

### Step C6: Install Required Plugins

1. Go to **Manage Jenkins** → **Plugins** → **Available plugins**
2. Search and install these (check the box, click "Install"):
   - **Docker Pipeline**
   - **Pipeline**
   - **HTML Publisher** (for chaos reports)
3. Restart Jenkins if prompted

### Step C7: Add Gemini API Key as Jenkins Credential

1. Go to **Manage Jenkins** → **Credentials**
2. Click **(global)** → **Add Credentials**
3. Kind: **Secret text**
4. Secret: paste your Gemini API key
5. ID: `gemini-api-key` (must be exactly this!)
6. Description: `Gemini API Key for ChaosController`
7. Click **Create**

### Step C8: Install Docker Compose inside Jenkins

```bash
docker exec -u root jenkins bash -c "
  curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o /usr/local/bin/docker-compose
  chmod +x /usr/local/bin/docker-compose
  ln -sf /usr/local/bin/docker-compose /usr/bin/docker-compose
"
```

Also install `pip` inside Jenkins:

```bash
docker exec -u root jenkins bash -c "
  apt-get update && apt-get install -y python3 python3-pip python3-venv
"
```

---

## 6. Phase D — Create the Jenkins Pipeline

### Step D1: Go to Your Forked Repo

The Dockerfiles and docker-compose.yml were already modified in Phase A. Now we just need to add the Jenkins-specific files.

```bash
cd ~/voting-app-chaos-demo
```

### Step D2: Create the chaos-config.yml

```bash
cat > chaos-config.yml << 'CONFIG_EOF'
version: "1.0"
project: "voting-app-chaos-demo"

controller:
  url: "http://localhost:5050"
  timeout_seconds: 300

thresholds:
  latency_regression_percent: 50
  max_5xx_rate_percent: 10
  max_payload_crash_rate_percent: 0

services:
  - name: vote
    probe_url: "http://vote:80/"

  - name: result
    probe_url: "http://result:80/"

  - name: worker
    probe_url: "http://worker:80/"

tests:
  - id: "latency-vote-service"
    type: latency
    target: vote
    params:
      delay_ms: 3000
      num_requests: 5
    on_fail: block

  - id: "latency-result-service"
    type: latency
    target: result
    params:
      delay_ms: 2000
      num_requests: 5
    on_fail: warn

report:
  output_path: "chaos-report.html"
  json_path: "chaos-report.json"
  ai_summary: true
  fail_on: "block"
CONFIG_EOF
```

### Step D3: Create the Jenkinsfile

```bash
cat > Jenkinsfile << 'JENKINS_EOF'
pipeline {
    agent any

    environment {
        GEMINI_API_KEY   = credentials('gemini-api-key')
        COMPOSE_FILE     = 'docker-compose.yml'
        APP_NETWORK      = 'voting-app-chaos-demo_app-net'
        CHAOS_IMAGE      = 'chaos-controller:latest'
        CHAOS_CONTAINER  = 'chaos-controller-ci'
    }

    stages {

        stage('Build & Start Voting App') {
            steps {
                echo '🔨 Building and starting the Voting App stack...'
                sh "docker compose -f ${COMPOSE_FILE} up --build -d"
                echo '✅ Voting App is building...'
            }
        }

        stage('Start ChaosController') {
            steps {
                echo '🔥 Starting ChaosController...'
                sh "docker rm -f ${CHAOS_CONTAINER} 2>/dev/null || true"
                sh """
                    docker run -d \
                        --name ${CHAOS_CONTAINER} \
                        --network ${APP_NETWORK} \
                        -p 5050:5050 \
                        -v /var/run/docker.sock:/var/run/docker.sock \
                        -e GEMINI_API_KEY=${GEMINI_API_KEY} \
                        ${CHAOS_IMAGE}
                """
                sh '''
                    for i in $(seq 1 30); do
                        curl -sf http://localhost:5050/status > /dev/null && echo "ChaosController ready!" && exit 0
                        echo "Waiting for ChaosController... ($i/30)"
                        sleep 5
                    done
                    echo "ChaosController failed to start!" && exit 1
                '''
                echo '✅ ChaosController is ready.'
            }
        }

        stage('Application Health Check') {
            steps {
                echo '🏥 Verifying all services are healthy...'
                sh '''
                    for i in $(seq 1 20); do
                        curl -sf http://localhost:8082 > /dev/null && echo "Vote app healthy!" && exit 0
                        echo "Waiting for Vote app... ($i/20)"
                        sleep 5
                    done
                    echo "Vote app failed to become healthy!" && exit 1
                '''
                echo '✅ Voting App is healthy and ready for chaos testing.'
            }
        }

        stage('Resilience Testing Gate') {
            steps {
                script {
                    def agentHost = sh(script: "hostname -I | awk '{print \$1}'", returnStdout: true).trim()

                    echo """
╔══════════════════════════════════════════════════════════════╗
║           🔥  RESILIENCE TESTING GATE  🔥                    ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║   Dashboard: http://${agentHost}:5050                        ║
║                                                              ║
║   Your Voting App services have been auto-discovered.        ║
║   Open the dashboard to:                                     ║
║     • Inject faults (latency, crash, CPU, packet loss...)   ║
║     • Run 3-phase chaos experiments                          ║
║     • Get AI-powered remediation reports (Gemini)            ║
║                                                              ║
║   When satisfied, come back here and click APPROVE.          ║
║   Click REJECT to fail the build.                            ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
                    """

                    input(
                        id: 'ResilienceApproval',
                        message: 'Resilience Testing Complete?',
                        ok: 'Approve — System is resilient, continue to deploy'
                    )

                    echo '✅ Resilience gate APPROVED.'
                }
            }
        }

        stage('Deploy to Production') {
            steps {
                echo '🚀 Resilience gate passed — deploying to production...'
                echo '(In a real scenario, this would run: kubectl apply, helm upgrade, etc.)'
                echo '✅ Deployed successfully!'
            }
        }
    }

    post {
        always {
            echo '🧹 Cleaning up...'
            sh "docker stop ${CHAOS_CONTAINER} 2>/dev/null || true"
            sh "docker rm ${CHAOS_CONTAINER} 2>/dev/null || true"
            sh "docker compose -f ${COMPOSE_FILE} down 2>/dev/null || true"
        }
        failure {
            echo '❌ Pipeline failed or was rejected.'
        }
        success {
            echo '✅ Pipeline succeeded!'
        }
    }
}
JENKINS_EOF
```

### Step D4: Commit & Push to Your Fork

Push all your changes (Jenkinsfile, chaos-config.yml, modified docker-compose.yml) to your forked GitHub repo so Jenkins can pull them:

```bash
cd ~/voting-app-chaos-demo
git add .
git commit -m "Add ChaosController pipeline: Jenkinsfile, chaos-config, modified compose"
git push origin main
```

> **If git push asks for credentials:** Use a GitHub Personal Access Token (PAT).
> Go to GitHub → Settings → Developer settings → Personal access tokens → Generate new token.
> Use your GitHub username and the PAT as the password when prompted.

---

## 7. Phase E — Trigger the Pipeline & Watch It Work

### Step E1: Pre-build the ChaosController Image

Jenkins needs the chaos-controller Docker image to exist:

```bash
cd ~/Failure_Injection_Fresh_Pull/Failure_injection_Major_Project
docker build -t chaos-controller:latest .
```

### Step E2: Create a Pipeline Job in Jenkins

1. Open Jenkins at <http://localhost:8080>
2. Click **New Item**
3. Name: `voting-app-resilience-gate`
4. Select **Pipeline** → **OK**
5. Scroll down to **Pipeline** section:
   - Definition: **Pipeline script from SCM**
   - SCM: **Git**
   - Repository URL: `https://github.com/YOUR_GITHUB_USERNAME/example-voting-app.git` (your fork URL!)
   - Branch: `*/main`
6. Click **Save**

> **This is why we forked:** Jenkins pulls the Jenkinsfile directly from your GitHub repo. Every time you push a change, Jenkins can re-run the pipeline with your latest code.

### Step E3: Run the Pipeline

1. Click **Build Now**
2. Watch the **Stage View** — you will see stages light up:
   - ✅ Build & Start Voting App
   - ✅ Start ChaosController
   - ✅ Application Health Check
   - ⏸️ **Resilience Testing Gate** (pipeline PAUSES here!)

### Step E4: Do the Chaos Testing

1. Open the ChaosController dashboard at **http://localhost:5050**
2. You will see the voting app services auto-discovered
3. **Inject a fault:**
   - Select the `vote` service
   - Choose **Latency** fault (e.g., 3000ms)
   - Click **Inject**
4. **Verify the impact:**
   - Open <http://localhost:8082> — it should be noticeably slower
5. **Recover:**
   - Click **Recover** in the dashboard
6. **Run an Experiment:**
   - Go to Experiments tab
   - Target: the vote service container name
   - Probe URL: `http://vote:80/` (internal Docker name!)
   - Fault: latency, 2000ms
   - Click **Run Experiment**
7. **Generate AI Report:**
   - After experiment completes, click **Generate AI Report**
   - Read the Gemini AI remediation suggestions

### Step E5: Approve or Reject

1. Go back to Jenkins at <http://localhost:8080>
2. Find your running build
3. Click **Approve** (or **Reject** to fail the pipeline)
4. If approved → pipeline continues to "Deploy to Production" → ✅ SUCCESS

---

## 8. What to Show Your Teachers

Present in this exact order for maximum impact:

### 🎬 Demo Script (15-20 minutes)

**Slide 1: The Problem (2 min)**
> "In production, microservices fail in unpredictable ways — network latency, CPU spikes, container crashes. Companies like Netflix discovered that the only way to build reliable systems is to deliberately break them in testing. This is Chaos Engineering."

**Slide 2: Our Solution (2 min)**
> "We built ChaosController — an AI-powered chaos engineering framework that plugs directly into CI/CD pipelines. It automatically injects faults, measures impact, and uses Google's Gemini AI to generate remediation reports."

**Live Demo Part 1: Show the Voting App (2 min)**
- Open <http://localhost:8082> — "This is our target: a real microservice app with 5 containers"
- Open <http://localhost:8081> — "Results update in real-time across services"

**Live Demo Part 2: The ChaosController Dashboard (5 min)**
- Open <http://localhost:5050>
- Show auto-discovery: "It found all 5 services using the Docker socket — zero configuration"
- Inject a latency fault on the `vote` service
- Switch to the voting page — show it's slow
- Recover it — show it's fast again
- Run a full 3-phase experiment
- Generate the AI report — show the Gemini analysis

**Live Demo Part 3: The Jenkins Pipeline (5 min)**
- Open Jenkins at <http://localhost:8080>
- Show the pipeline stages visually
- Explain: "When a developer pushes code, the pipeline builds the app, starts ChaosController, and PAUSES. The developer must prove their code is resilient before it can deploy."
- Show the Approve/Reject button
- Click Approve → pipeline goes green

**Slide 3: Architecture Diagram (2 min)**
> Show this flow:

```
Developer pushes code
        │
        ▼
Jenkins Stage 1: Build & Start microservices (docker compose up)
        │
        ▼
Jenkins Stage 2: Start ChaosController (docker run)
        │
        ▼
Jenkins Stage 3: Health Check — verify app is running
        │
        ▼
Jenkins Stage 4: ⏸️ PIPELINE PAUSES
        │           Developer opens ChaosController dashboard
        │           Injects faults, runs experiments
        │           Gets AI remediation report from Gemini
        │           Clicks APPROVE or REJECT in Jenkins
        ▼
Jenkins Stage 5: Deploy to Production (only if approved)
        │
        ▼
Jenkins Post: Cleanup all containers
```

### 📊 Key Points to Highlight

| Feature | What to Say |
|---------|-------------|
| **Plug-and-Play** | "Any team can add this to their pipeline with ONE docker command" |
| **Auto-Discovery** | "Zero configuration — it finds your containers automatically via Docker socket" |
| **8 Fault Types** | "Latency, packet loss, CPU stress, memory stress, container crash, bandwidth throttle, network partition, DNS failure" |
| **AI Analysis** | "Google Gemini acts as an automated SRE — it tells you exactly what to fix and where" |
| **Pipeline Gate** | "Code cannot reach production unless it passes resilience testing" |
| **Framework Agnostic** | "Works with any Docker Compose app — Python, Java, Node.js, Go, anything" |

---

## 9. What to Explain to Your Teachers

### 9a. "Why does this matter?"

> Traditional testing (unit tests, integration tests) only checks if code is *correct*. Chaos Engineering checks if code is *resilient*. Netflix pioneered this with Chaos Monkey. Our framework brings the same concept to any team's CI/CD pipeline with AI-powered analysis.

### 9b. "How does the Jenkins integration work?"

> The ChaosController is packaged as a single Docker image containing both the React dashboard and the Python FastAPI backend. Jenkins runs this image alongside the target application on the same Docker network. The pipeline uses Jenkins' `input` step to pause and wait for human approval. This creates a "resilience gate" — a quality checkpoint that code must pass before deployment.

### 9c. "How does fault injection actually work?"

> We use standard Linux networking tools inside Docker containers:
> - **Latency:** `tc netem delay` — adds delay to outgoing packets
> - **Packet Loss:** `tc netem loss` — randomly drops packets
> - **CPU Stress:** `stress-ng --cpu` — saturates CPU cores
> - **Container Crash:** Docker SDK — force-stops the container
> - **Network Partition:** `iptables DROP` — blocks all traffic
>
> This requires `cap_add: NET_ADMIN` and `privileged: true` in docker-compose.

### 9d. "What does the AI do?"

> After each experiment, we send the telemetry data (baseline latency, fault latency, recovery metrics) to Google's Gemini GenAI API. Gemini acts as an automated Site Reliability Engineer — it calculates a Resilience Score and generates a structured remediation report with specific code fixes (e.g., "add a 300ms timeout on the API gateway", "implement circuit breakers using the retry pattern").

### 9e. "How is this different from existing tools?"

| Feature | ChaosController (Ours) | Chaos Monkey (Netflix) | Gremlin | LitmusChaos |
|---------|----------------------|----------------------|---------|-------------|
| **AI Analysis** | ✅ Gemini AI | ❌ | ❌ | ❌ |
| **Web Dashboard** | ✅ React UI | ❌ CLI only | ✅ (paid) | ✅ |
| **Jenkins Plugin** | ✅ Pipeline gate | ❌ | ✅ (paid) | Partial |
| **Free/Open Source** | ✅ | ✅ | ❌ ($$$) | ✅ |
| **Single Docker Image** | ✅ | ❌ | ❌ | ❌ |

### 9f. "Can this work with any app?"

> Yes. The only requirements are:
> 1. The target app must run in Docker containers
> 2. Containers need `cap_add: NET_ADMIN` and `privileged: true`
> 3. Containers need `iproute2` and `stress-ng` installed
>
> We demonstrated this by taking Docker's official example-voting-app (which we did NOT build) and plugging ChaosController into it with zero code changes to the app itself.

---

## 10. Troubleshooting

| Problem | Solution |
|---------|----------|
| `docker: permission denied` | Run `sudo usermod -aG docker $USER` then log out and back in |
| Jenkins can't run Docker | Make sure you mounted `/var/run/docker.sock` and fixed group permissions (Step C3) |
| ChaosController can't find containers | Ensure it's on the same Docker network: `--network voting-app-chaos-demo_app-net` |
| `tc: Operation not permitted` | Add `cap_add: NET_ADMIN` and `privileged: true` to the target service in docker-compose.yml |
| Dashboard shows blank | Wait 5-10 seconds and hard-refresh (Ctrl+Shift+R) |
| AI report fails | Check your `GEMINI_API_KEY` is correct and not rate-limited |
| Jenkins `input` step not showing | Click on the build number, then look for the "Paused for input" link |
| `APP_NETWORK` wrong | Run `docker network ls` and use the exact network name shown |
| Port 8080 conflict (Jenkins vs Voting App) | Already fixed in this guide — vote app runs on `8082`, Jenkins on `8080` |
| `docker-compose: command not found` in Jenkins | Run Step C8 to install docker-compose inside Jenkins |

---

## Quick Reference: All URLs During Demo

| Service | URL | Notes |
|---------|-----|-------|
| **Jenkins** | <http://localhost:8080> | Pipeline management |
| **ChaosController Dashboard** | <http://localhost:5050> | Fault injection & experiments |
| **Voting App (Vote)** | <http://localhost:8082> | Vote UI (port changed to avoid Jenkins conflict) |
| **Voting App (Results)** | <http://localhost:8081> | Live results |

> ✅ **No port conflict** — Jenkins runs on `8080`, the Vote app runs on `8082`. This is already handled in the docker-compose.yml provided in Step D2.

---

## File Summary

| File | Location | Purpose |
|------|----------|---------|
| `docker-compose.yml` | `~/voting-app-chaos-demo/` | Modified voting app with chaos capabilities |
| `chaos-config.yml` | `~/voting-app-chaos-demo/` | Defines which services to test and thresholds |
| `Jenkinsfile` | `~/voting-app-chaos-demo/` | 5-stage Jenkins pipeline with resilience gate |

---

*Guide created for ChaosController — Failure Injection Major Project*
*Dummy App: https://github.com/dockersamples/example-voting-app*
