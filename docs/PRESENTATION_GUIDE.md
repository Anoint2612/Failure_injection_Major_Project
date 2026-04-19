# End-to-End Presentation Guide: ChaosController 

When presenting this project, you want to show it as a **fully packaged, enterprise-grade tool** that any team could drop into their CI/CD pipeline today. 

Here is the exact script/flow to follow to demonstrate its power smoothly.

---

## 1. Setup (Before the Presentation)

You should have two terminals ready. Make sure port `5050` and `5173` are free (`killall uvicorn` and `killall node` if they were running from your local dev setup). 

1. **Terminal 1**: Make sure the target application is running:
   ```bash
   cd target-app
   docker compose down -v  # Start fresh
   docker compose up --build -d
   ```
2. **Terminal 2**: Have this ready in the project root to spin up the containerized framework:
   ```bash
   docker stop chaos-test && docker rm chaos-test
   ```

---

## 2. The Live Demo Script

### Step A: Pitching the "Plug-and-Play" Architecture
Start by explaining that this is a **zero-configuration** chaos engineering platform.
* *"We packaged the entire backend and React dashboard into a single Docker image."*
* *"To use it, a development team just runs one single Docker command to spin it up alongside their app."*

**Run this command live:**
```bash
docker run -d \
  --name chaos-test \
  --network target-app_test-net \
  -p 5055:5050 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e GEMINI_API_KEY=$GEMINI_API_KEY \
  chaos-controller:latest
```
*(Note: Replace `target-app_test-net` with whatever `docker network ls` shows as your app's network, and make sure your GEMINI_API_KEY is exported in your terminal!)*

### Step B: The Dashboard & Discovery
1. Open your browser to **http://localhost:5055**
2. Point out that the React dashboard is being served directly from the Python backend container — no separate Node.js server needed.
3. Show the **Topology/Services** sidebar.
   * *"Notice how it instantly discovered the API Gateway, Auth Service, Date Service, Prometheus, and Grafana. We did not hardcode these. It uses the Docker Socket to dynamically discover the stack."*

### Step C: Injecting a Live Fault
1. Select the **Network Partition** or **Bandwidth Throttle** fault.
2. Target the `target-app-auth-service-1`.
3. Click "Inject". 
4. Explain that the framework is currently executing `tc` (Traffic Control) or `iptables` commands *directly inside* that specific Docker container without affecting the host machine.
5. Click "Recover" to restore it.

### Step D: The "Experiment" & AI Analysis (The Crown Jewel)
This is where you prove the project's true value for CI/CD pipelines.

1. Go to the **Experiments** tab.
2. **Target Service**: `target-app-auth-service-1`
3. **Probe URL**: `http://target-app-api-gateway-1:8000/auth/token`
   *(Explain carefully: Because we are running inside the CI/CD Docker network, we tell the experiment runner to hit the API gateway using its internal Docker name, not localhost).*
4. **Select Fault**: `latency` (Set to something noticeable, like 500ms).
5. Click **Run Experiment**.

**While it runs, explain the 3-Phase Methodology:**
* *"It's doing 5 requests to establish a baseline, then it injects the fault, does 5 more requests under duress, and finally auto-recovers the container and verifies it's healthy."*

**When the AI Report generates:**
* Show the structured JSON data on the left.
* Emphasize the **Gemini AI Root Cause Analysis** on the right. 
* *"Instead of just failing a pipeline silently, the framework feeds the telemetry to Google's Gemini GenAI, which acts as an automated Site Reliability Engineer (SRE), telling the developer exactly why the failure happened and how to fix their code (e.g., adding circuit breakers or timeouts) before they are allowed to merge."*

### Step E: The Jenkins Integration
Finally, show them the documentation (`docs/JENKINS_INTEGRATION.md`) and the `Jenkinsfile` you wrote.
* *"This isn't just a manual tool. We designed this to pause a CI/CD pipeline. When a developer pushes code, Jenkins spins up their app, spins up this exact dashboard, and pauses. The developer gets a link to this UI, tests their scenario, gets AI feedback, and only clicks 'Approve' in Jenkins when the architecture is resilient enough for production."*

---

## 3. Potential "Gotchas" During Presentation
- **The Probe URL hanging:** Always remember that if you test the containerized version (port 5055), you **must** use the internal docker name (`target-app-api-gateway-1`) for the Probe URL, not `localhost`.
- **Make sure you have an API Gateway route:** If you haven't written a dummy endpoint inside your real target app yet (like `/auth/token` or `/health` on port 8000), the experiments tab will just return 404s. Make sure whatever Probe URL you use actually returns a 200 OK under normal circumstances!
