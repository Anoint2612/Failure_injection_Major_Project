# ChaosController — Failure Injection Framework 🌩️💥

Welcome to **ChaosController**, a complete, enterprise-grade Chaos Engineering resilience testing platform designed exclusively for modern microservices architectures. 

With ChaosController, you can deliberately inject highly-controlled faults—such as network latency, package drops, CPU starvation, and container crashes—into your running Docker applications to observe how they behave under extreme stress. 

## 🧠 What is Chaos Engineering?

Chaos Engineering is the discipline of experimenting on a software system in order to build confidence in the system's capability to withstand turbulent conditions in production. Instead of waiting for a random outage to happen, ChaosController allows you to purposefully "break" components in a controlled area to see if your fallback mechanisms (like circuit breakers, retries, and load balancers) activate correctly.

### ✨ The AI-Powered "Secret Sauce"
Unlike traditional tools that simply break your system and force you to dig through logs, ChaosController securely transmits fault telemetry and latency metrics to **Google's Gemini GenAI**. Gemini acts exactly like a Senior Site Reliability Engineer (SRE). It analyzes the exact network decay caused by the fault and mathematically assigns a Resilience Score along with a structured Markdown report suggesting exact Root Cause fixes (e.g., "Implement a 300ms timeout on the internal API Gateway fetch").

---

## 📖 Table of Contents
1. [Prerequisites & Initial Setup](#1-prerequisites--initial-setup)
2. [Setting up the Target Application](#2-setting-up-the-target-application)
3. [Execution Set A: Pure CLI & Local Developer Setup (Granular Testing)](#3-execution-set-a-pure-cli--local-developer-setup-granular-testing)
4. [Execution Set B: The Pluggable Docker Image (Recommended for CI/CD)](#4-execution-set-b-the-pluggable-docker-image-recommended-for-cicd)
5. [Jenkins Pipeline Integration Guide (External Plug-and-Play)](#5-jenkins-pipeline-integration-guide-external-plug-and-play)
6. [Supported Fault Types](#6-supported-fault-types)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Prerequisites & Initial Setup

Assume you are starting with nothing but a text editor (like VSCode). To run this project from scratch, you must install the following software on your machine:

1. **Docker & Docker Compose**: The entire system runs isolated processes inside containers.
2. **Python 3.10+**: Required for the FastAPI backend engine.
3. **Node.js (v18+) & npm**: Required to run and build the React frontend dashboard.

#### Securing your Gemini AI Key
The AI features require an API key to communicate with Google's GenAI models.
1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Click **Create API Key** and copy the string.
3. Open this project in your IDE. In the root folder of this project (next to this README), create a new file named exactly `.env`.
4. Add the following line to the file, replacing the placeholder with your copied key:
   ```env
   GEMINI_API_KEY=AIzaSyYourGeneratedKeyGoesHere12345
   ```
*(Note: Because of our built-in fallback engine, if your primary Gemini model gets rate-limited by high global traffic, we will automatically fall back to alternative Gemini models!)*

---

## 2. Setting up the Target Application

Chaos engineers need an application to attack. Included inside the `target-app` folder is a dummy e-commerce microservice architecture composed of:
- `api-gateway`: Receives the initial web traffic.
- `auth-service` & `data-service`: Internal logic services.
- `prometheus` & `grafana`: Industry-standard metric collectors tracking container memory/CPU.

Start this stack natively using Docker Compose:
```bash
cd target-app
docker compose down -v   # Ensure a clean slate
docker compose up -d
```
*Wait 15 seconds for Prometheus and Grafana to boot fully.*

---

## 3. Execution Set A: Pure CLI & Local Developer Setup (Granular Testing)

This highly-granular method avoids the unified Docker container. It requires you to start the Backend and Frontend manually. **This is highly recommended for users who want to test specific APIs, manually run CLI `curl` commands, or contribute code changes.**

### Step 3.1: Start the Backend (FastAPI Framework)
Open a new terminal at the root of the project:
```bash
cd framework-controller
python3 -m venv venv           # Create a virtual environment
source venv/bin/activate       # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 5050
```

### Step 3.2: Start the Frontend (Vite React)
Open a totally different terminal window:
```bash
cd frontend
npm install    # Installs heavy libraries like React elements
npm run dev
```

### Step 3.3: Manual CLI Testing (Understanding the Under-the-hood Mechanics)

Want to know how to interact with the project outside of the Graphical User Interface? Let's use `curl`!

**1. Test the Dummy App's API Gateway manually:**
```bash
curl http://localhost:8000/dashboard
```
*Result:* You should see a combined JSON payload from both the Auth and Data internal services!

**2. Test the Chaos Controller's Service Discovery via CLI:**
```bash
curl http://localhost:5050/status
```
*Result:* The Python backend dynamically lists all running Docker targets on your system.

**3. Test Prometheus Metrics via CLI (No UI):**
```bash
curl -g 'http://localhost:9090/api/v1/query?query=up'
```
*Result:* A raw JSON array outputting the exact uptime telemetry Prometheus scrapes every few seconds! Alternatively, open `http://localhost:3000` to visually see Grafana.

**4. Trigger a Latency Test via CLI (Bypassing the UI Backend completely):**
```bash
curl -X POST http://localhost:5050/experiment/run \
  -H "Content-Type: application/json" \
  -d '{"target_service":"auth-service", "probe_url":"http://localhost:8000/dashboard", "fault_type":"latency", "delay_ms": 3000, "num_requests": 3}'
```
*Result:* Your CLI will hang for a few seconds as it dynamically injects 3 seconds of TCP delay using Linux Network Traffic Control (`tc`), tests it 3 times, auto-removes the delay, and spits out a granular mathematical payload comparing the states.

**5. Trigger the AI Report Feature via CLI:**
Take the JSON output from the command above, and pipe it right back into the `/analyze` endpoint:
```bash
curl -X POST http://localhost:5050/experiment/analyze \
  -H "Content-Type: application/json" \
  -d '{ "baseline": [{"latency": 0.05}], "during_fault": [{"latency": 3.01}], "config": {"fault_type":"latency"} }'
```
*Result:* You will see a raw Markdown string generated dynamically by Google Gemini containing remediation strategies based mathematically on your fake payload!

### Step 3.4: Bring it Together in the UI
Now that you know how the API works natively, open your browser to **http://localhost:5173**.
1. Select a target object (e.g., `api-gateway`).
2. Run an experiment and wait for the table graph to appear.
3. Scroll down and click the **Generate AI Report** button to watch the backend securely interact with Gemini. 

*(When you are done testing, you must KILL the terminal servers by pressing **Ctrl+C** to free up the ports!)*

---

## 4. Execution Set B: The Pluggable Docker Image (Recommended for CI/CD)

This is the fully streamlined "production" method. We wrap the Vite UI and the Python server securely inside a single, heavily optimized Docker Image. It serves the React application seamlessly over static files.

### Step 4.1: Guarantee Clean Ports
If you previously used Execution Set A, you **must close the terminals** so they release port 5050, or this will fail.

### Step 4.2: Build the Super-Image
Go to the root folder (where this README is):
```bash
docker build -t chaos-controller:latest .
```

### Step 4.3: Run the Engine
Run the container, making sure to mount your environment variables (`--env-file`) and the Docker socket (`/var/run/docker.sock`) so the framework has permission to inject Linux traffic faults into other running containers on the system!

```bash
docker run -d \
  --name chaos-controller-ci \
  --network target-app_test-net \
  -p 5050:5050 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --env-file .env \
  chaos-controller:latest
```
*(Notice we pass `--network target-app_test-net`. This instructs the framework to bridge physically into the private subnet of the target e-commerce app so it can connect to them easily).*

### Step 4.4: Testing the Engine
1. Clear your browser cache (`Ctrl+Shift+R`).
2. Navigate to **http://localhost:5050**.
3. Select `auth-service`. The system's environment detector will realize it's running inside Docker and will automatically format the Probe URL to use Docker internal DNS names (`http://target-app-api-gateway-1:8000/health`)!
4. Launch an experiment, examine the results, and generate the AI report instantly!

---

## 5. Jenkins Pipeline Integration Guide (External Plug-and-Play)

The true value of ChaosController is preventing brittle code from entering production environments.

If you have a customized microservice application pushed to GitHub and want to test its resilience in a CI/CD pipeline, follow these exact steps.

### Requirement 1: Allow Target Tampering
For ChaosController to inject faults from the outside, your target containers must grant localized network permissions. Add these exact parameters to **every service** in your application's `docker-compose.yml`:
```yaml
services:
  your-service:
    build: .
    cap_add:
      - NET_ADMIN     # Gives us permission to edit local TCP tables
    privileged: true  # Provides hooks for CPU stress tests
```

Additionally, ensure your target Dockerfile contains standard injection utilities:
```dockerfile
# Add this above your ENTRYPOINT
RUN apt-get update && apt-get install -y iproute2 stress-ng && rm -rf /var/lib/apt/lists/*
```

### Requirement 2: The Jenkinsfile Stage
Inject the following stage directly into your existing `Jenkinsfile` right before your "Deploy to Production" step:

```groovy
stage('Resilience Experiment Gate') {
    steps {
        script {
            // 1. Build the unified Chaos Controller dynamically
            sh 'docker build -t chaos-controller:latest .'
            
            // 2. Start the controller (Make sure to replace MY_NETWORK with your app network!)
            sh '''
            docker rm -f chaos-controller-ci || true
            docker run -d --name chaos-controller-ci \
                --network MY_NETWORK_default \
                -p 5050:5050 \
                -v /var/run/docker.sock:/var/run/docker.sock \
                -e GEMINI_API_KEY=${GEMINI_API_KEY} \
                chaos-controller:latest
            '''
            
            // 3. Pause the CI pipeline until an SRE reviews the telemetry
            def dashboardUrl = "http://localhost:5050"
            echo "🚨 CHAOS CONTROLLER IS LIVE! 🚨"
            echo "Access the dashboard at: ${dashboardUrl}"
            
            def userInput = input(
                id: 'chaosApproval', 
                message: "Did your microservices survive the Chaos Injection?", 
                parameters: [
                    choice(choices: ['Yes - Resilient', 'No - Weak Code'], description: 'Review the AI Architect Remediation Report before deciding.', name: 'STATUS')
                ]
            )
            
            if (userInput == 'No - Weak Code') {
                error "Pipeline Failed: Application failed resilience testing!"
            }
        }
    }
}
```
**How this works in reality:** The developer pushes code. Jenkins spins up their app, compiles the container, and **freezes**. The developer logs into port 5050, tests clicking around, reads the AI guidance, and clicks "Approve" back in Jenkins if the app proved to be robust enough for actual production deployment!

---

## 6. Supported Fault Types

We currently support the following destructive capabilities via standard Linux internal tooling:

| Category | Fault | Linux Subsystem Tool | Effect on Application |
|----------|-------|----------------------|-----------------------|
| 🔴 **Infrastructure** | Container Crash | Docker SDK | Hard-stops the container abruptly, then forcibly restarts it in 5s. Tests failovers. |
| 🟡 **Network** | Latency | `tc netem delay` | Add exactly `X` milliseconds of delayed outbound HTTP traffic. |
| 🟡 **Network** | Packet Loss | `tc netem loss` | Randomly drop a set percentage of network packets. |
| 🟡 **Network** | Bandwidth Limit | `tc tbf limit` | Throttle the container's bandwidth to test low-data-connection behaviors. |
| 🟡 **Network** | Partition | `iptables DROP` | Block all networking entirely, simulating a severed switch. |
| 🟡 **Network** | DNS Failure | `/etc/resolv.conf` | Destroy the container's ability to locate other microservices by name. |
| 🔵 **Resource** | CPU Stress | `stress-ng --cpu` | Fully saturate the container's allocated processors. |
| 🔵 **Resource** | Memory Stress | `stress-ng --vm` | Greedily allocate memory blocks and lock them to trigger OOM faults. |

---

## 7. Troubleshooting

| Symptom | Probable Cause | Quick Fix |
|---------|----------------|-----------|
| **AI Feature not working** | Wrong API Key / Overload | Ensure `.env` is loaded. Our AI model automatically falls back to secondary networks if overloaded. |
| **All Experiments end in "Timeout"** | Wrong Probe URL Context | If hitting `api-gateway` from CLI directly, probe `localhost:8000`. If using the fully Dockerized mode, probe `target-app-api-gateway-1:8000`. |
| **"Operation not permitted" on Latency block** | `docker-compose.yml` mismatch | You absolutely MUST have `cap_add: [NET_ADMIN]` on the target container. |
| **The Framework can't find my containers** | Wrong Network Binding | When running Set B, if you don't attach ChaosController to `--network target-app_test-net`, it physically can't route packets to the containers. |
| **Frontend displays an older version** | Vite Cache issue | Perform a strict Hard Reload (`Ctrl+Shift+R`) inside Chrome/Firefox. |