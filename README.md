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
2. [Setting up the Target Application & Observability](#2-setting-up-the-target-application--observability)
3. [Execution Set A: Pure CLI & Local Scripting (No Overall Docker Image)](#3-execution-set-a-pure-cli--local-scripting-no-overall-docker-image)
4. [Execution Set B: The Pluggable Docker Image (Frontend Included)](#4-execution-set-b-the-pluggable-docker-image-frontend-included)
5. [Jenkins Pipeline Integration Guide (External Plug-and-Play)](#5-jenkins-pipeline-integration-guide-external-plug-and-play)
6. [Supported Fault Types](#6-supported-fault-types)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Prerequisites & Initial Setup

Assume you are starting with nothing but your computer and an IDE (like VSCode). To run this project from scratch, you must install the following software:

1. **Docker & Docker Compose**: The entire system runs isolated processes inside containers.
2. **Python 3.10+**: Required for the FastAPI backend engine and manual scripts.
3. **Node.js (v18+) & npm**: Required to run and build the React frontend dashboard.

#### Securing your Gemini AI Key
The AI features require an API key to communicate with Google's GenAI models. You should use a `.env` file to manage this key locally.
1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Click **Create API Key** and copy the string.
3. Open this project in your IDE. In the root folder of this project (next to this README file), create a new file named exactly `.env`.
4. Add the following line to the file, replacing the placeholder with your copied key:
   ```env
   GEMINI_API_KEY=YOUR_KEY
   ```
*(Note: Because of our built-in fallback engine, if your primary Gemini model gets rate-limited by high global traffic, we will automatically fall back to alternative Gemini models!)*

---

## 2. Setting up the Target Application & Observability

Chaos engineers need an application to attack. Included inside the `target-app` folder is a dummy e-commerce microservice architecture composed of:
- `api-gateway`: Receives the initial web traffic.
- `auth-service` & `data-service`: Internal logic services.
- `prometheus`: A time-series database tracking container memory/CPU.
- `grafana`: Industry-standard metrics dashboard.

Start this stack natively using Docker Compose:
```bash
cd target-app
docker compose down -v   # Ensure a clean slate
docker compose up -d     # Starts all 5 microservices
cd ..
```
*Wait 15 seconds for Prometheus and Grafana to boot fully.*

### 📊 How to see Metrics in Grafana & Prometheus
You can visually see the spikes when a fault is occurring!

1. Open **Prometheus** at `http://localhost:9090` in your browser.
   - Go to **Status > Targets** to verify all target microservices (`api-gateway`, etc) are registered and "UP".
   - Go to **Graph**, type `up` and hit execute to see the raw metrics.
2. Open **Grafana** at `http://localhost:3000` in your browser (Login is `admin` / `admin`).
   - Go to **Connections > Data Sources > Add data source**.
   - Select **Prometheus**.
   - Set the Prometheus server URL to `http://prometheus:9090` (since it runs in the same Docker network).
   - Click "Save & Test". You can now build powerful CPU/Memory dashboards to visualize Chaos spikes!

---

## 3. Execution Set A: Pure CLI & Local Scripting (No Overall Docker Image)

This highly-granular method lets you test every minute corner of the API independently natively on your OS without the Frontend UI wrapper.

### Step 3.1: Start the Backend (FastAPI Framework)
Open a new terminal at the root of the project:
```bash
cd framework-controller
python3 -m venv venv           # Create a virtual environment
source venv/bin/activate       # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 5050
```

*(Note: `python-dotenv` natively detects your `.env` file in the root folder, so the AI will work without manual exports!).*

### Step 3.2: Manually testing ALL APIs via cURL
Open a separate terminal window and test exactly how the architecture functions underneath:

**1. Service Discovery:** See all target containers dynamically.
```bash
curl http://localhost:5050/status
```

**2. List Fault Types:** Ask the system what chaos abilities it has.
```bash
curl http://localhost:5050/faults
```

**3. Inject Latency:** Hit the target app directly with a raw fault!
```bash
curl -X POST "http://localhost:5050/inject/latency/target-app-auth-service-1?delay_ms=3000"
```

**4. Check Prometheus CLI Reaction:** See if it registered the latency drop.
```bash
curl -g 'http://localhost:9090/api/v1/query?query=up'
```

**5. Heal the Network (Recover):** Fix the broken container!
```bash
curl -X POST "http://localhost:5050/recover/latency/target-app-auth-service-1"
```

**6. Run an End-to-End 3-Phase Experiment via API:**
```bash
curl -X POST http://localhost:5050/experiment/run \
  -H "Content-Type: application/json" \
  -d '{"target_service":"target-app-auth-service-1", "probe_url":"http://localhost:8000/dashboard", "fault_type":"latency", "delay_ms": 3000, "num_requests": 3}'
```

**7. Trigger the AI Report Feature via CLI:**
Take the JSON output from the experiment above, and pipe it right back into the `/analyze` endpoint:
```bash
curl -X POST http://localhost:5050/experiment/analyze \
  -H "Content-Type: application/json" \
  -d '{ "baseline": [{"latency": 0.05}], "during_fault": [{"latency": 3.01}], "config": {"fault_type":"latency"} }'
```

### Step 3.3: Manual Testing using Python Scripts
We have also included standalone Python scripts that automate API testing without the massive React UI.
In your Python terminal in the `framework-controller` folder:
- **Run `python run_experiment.py`**: This script automatically pings the gateway, injects a fault, records latency, recovers the system, and saves it to `experiment_results.json`.
- **Run `python scenario_generator.py`**: A powerful randomized scenario builder.
- **Run `python ai_analyst.py`**: A dedicated script that parses the results JSON and contacts Gemini natively.

*(Optional)* If you wish to use the Visual Dashboard over this native backend, open a separate terminal, `cd frontend`, run `npm install`, and `npm run dev`. Navigate to `http://localhost:5173`. Wait for the framework controller to load up completely in your backend prior to running `npm run dev`.

---

## 4. Execution Set B: The Pluggable Docker Image (Frontend Included)

This is the fully streamlined "production" method. We wrap the Vite UI and the Python FastAPI server securely inside a single Docker Image. It serves the React dashboard seamlessly.

### Step 4.1: Clean up Manual Ports
If you previously used Execution Set A, you **must close the terminals** so they release port 5050. Press Ctrl+C in your FastAPI terminal!

### Step 4.2: Build the Super-Image
Go to the root folder (where this README is):
```bash
docker build -t chaos-controller:latest .
```

### Step 4.3: Run the Engine
Run the container, making sure to mount your environment variables (`--env-file`) and the Docker socket (`/var/run/docker.sock`) so the framework has permission to tamper with local networking inside other containers!

```bash
docker run -d \
  --name chaos-controller-ci \
  --network target-app_test-net \
  -p 5050:5050 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --env-file .env \
  chaos-controller:latest
```
*(Notice we pass `--network target-app_test-net`. This bridges physically into the private subnet of the e-commerce app so the dashboard has internal access).*

### Step 4.4: Testing the Engine Visually
1. Open your browser to **http://localhost:5050**.
2. Select `auth-service` from the target list. 
3. *Important Note on URLs*: The system intelligently detects it is running inside Docker and will automatically format the Probe URL to use internal DNS names (`http://target-app-api-gateway-1:8000/health`) instead of `localhost`.
4. Launch the `LATENCY TEST`, examine the graphical tables, and click **Generate AI Report**!

---

## 5. Jenkins Pipeline Integration Guide (External Plug-and-Play)

The true value of ChaosController is preventing brittle code from entering production environments. If you are an external user who has a basic microservice application tested locally and want to integrate this Chaos Framework into Jenkins, read on!

### Requirement 1: Network Tampering Abilities
For ChaosController to inject faults seamlessly, your target containers must dynamically grant localized network modification privileges. 
Add these exact parameters to **every service** in your target application's `docker-compose.yml`:
```yaml
services:
  your-service:
    build: .
    cap_add:
      - NET_ADMIN     # Gives us permission to edit local TCP tables (tc iptables)
    privileged: true  # Provides hooks for CPU stress scripts
```

Ensure your target Dockerfile contains standard chaos utilities:
```dockerfile
# Add this right above your ENTRYPOINT/CMD
RUN apt-get update && apt-get install -y iproute2 stress-ng && rm -rf /var/lib/apt/lists/*
```

### Requirement 2: Jenkins Configuration
1. Open your Jenkins Server.
2. Ensure you have the `Docker Pipeline plugin` installed.
3. Manage Jenkins -> Credentials -> Create a "Secret text" credential named `gemini-api-key` using your exact Google AI Studio key!

### Requirement 3: The Jenkinsfile Stage
Inject this exact stage directly into your target app's `Jenkinsfile`, ideally running right after your app builds but right before your final "Deploy to AWS/Production" pipeline step:

```groovy
stage('Resilience Experiment Gate') {
    steps {
        script {
            // 1. Pull exactly our framework dynamically
            sh 'git clone https://github.com/anoint2612/Failure_injection_Major_Project.git temp-chaos-engine'
            sh 'cd temp-chaos-engine && docker build -t chaos-controller:latest .'
            
            // 2. Start the controller (Replace MY_NETWORK with your app network!)
            withCredentials([string(credentialsId: 'gemini-api-key', variable: 'GEMINI_KEY')]) {
                sh '''
                docker rm -f chaos-controller-ci || true
                docker run -d --name chaos-controller-ci \
                    --network MY_NETWORK_default \
                    -p 5050:5050 \
                    -v /var/run/docker.sock:/var/run/docker.sock \
                    -e GEMINI_API_KEY=${GEMINI_KEY} \
                    chaos-controller:latest
                '''
            }
            
            // 3. Pause the CI pipeline until an SRE tests the system 
            def dashboardUrl = "http://localhost:5050"
            echo "🚨 CHAOS CONTROLLER IS LIVE! 🚨"
            
            // This Jenkins Pipeline pauses entirely until a physical human decides!
            def userInput = input(
                id: 'chaosApproval', 
                message: "Please evaluate your App at ${dashboardUrl}. Did your microservices survive the Chaos Injection?", 
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
**How this works in reality:** You `git commit` to your repository. Jenkins automatically builds your internal app containers. It then pulls and spins up the Chaos Controller! The Jenkins Pipeline immediately **freezes**. 

You open `http://localhost:5050` (or your Jenkins server IP), break your own application deliberately, and then dynamically read the Gemini AI guidance. If you feel it recovered well, you open Jenkins and securely click "Approve" so the deployment goes to actual production!

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