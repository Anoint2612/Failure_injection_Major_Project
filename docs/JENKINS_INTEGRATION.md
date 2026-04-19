# Jenkins Pipeline Integration Guide

This guide explains how to add ChaosController as an **interactive plug-and-play resilience testing stage** in any Jenkins CI/CD pipeline.

---

## Prerequisites

- Jenkins with Docker installed on the agent building the project.
- A Jenkins credential named `gemini-api-key` (Secret text) containing your Gemini API key.
- Your target application should be deployed via Docker Compose.

---

## Step 1: Prepare Your Target Containers (One-Time)

For ChaosController to inject faults, your target containers must grant network permissions and have the correct utilities installed.

Add these settings to **each service** you want to test in your `docker-compose.yml`:

```yaml
services:
  your-service:
    build: .
    # IMPORTANT: Required for controller to modify network and CPU
    cap_add:
      - NET_ADMIN
    privileged: true
```

Add these to each service's **Dockerfile**:

```dockerfile
# IMPORTANT: Required for network faults (tc) and resource faults (stress-ng)
RUN apt-get update && apt-get install -y iproute2 stress-ng && rm -rf /var/lib/apt/lists/*
```

---

## Step 2: Build the Framework Image

The ChaosController comes perfectly packaged as a single Docker image containing both the backend API and the frontend React Dashboard.

Build it once on your Jenkins agent (or push it to a container registry):

```bash
git clone https://github.com/anoint2612/Failure_injection_Major_Project.git
cd Failure_injection_Major_Project

# Build the unified image
docker build -t chaos-controller:latest .
```

---

## Step 3: Add the Jenkinsfile

A complete, working declarative pipeline is provided in [`Jenkinsfile`](../Jenkinsfile). Copy its contents into your project's `Jenkinsfile`.

### Important Jenkinsfile adjustments:
- Replace `COMPOSE_FILE = 'target-app/docker-compose.yml'` with the path to your app's compose file.
- Replace `APP_NETWORK = 'target-app_default'` with your app's actual Docker network name (usually `<your-folder-name>_default`).
- Replace the placeholder in the `Deploy to Production` stage with your actual deployment script (e.g., Helm, kubectl, or SSH).

---

## Step 4: How the Pipeline Works

When you push code and trigger the Jenkins pipeline, it natively acts as an interactive gatekeeper:

1. **Build & Deploy App**: Your target application spins up via `docker-compose up`.
2. **Start ChaosController**: Jenkins runs the `chaos-controller:latest` image, seamlessly connecting it to your app's network via the docker socket.
3. **Resilience Testing Gate (PIPELINE PAUSES)**: 
   - A message is printed to the Jenkins console with the URL of the Chaos Dashboard (e.g., `http://<jenkins-agent-ip>:5050`).
   - The developer clicks the URL to open the dashboard.
   - The developer tests scenarios (e.g., inducing latency, network partitions, or CPU spikes).
   - If regressions are found, they use the **Gemini AI Root Cause Analysis** to generate remediation suggestions.
4. **Approve or Reject**:
   - Return to Jenkins.
   - If the system proved resilient, click **Approve** and the pipeline automatically continues to deploy to production.
   - If the system failed, click **Reject** to purposefully fail the pipeline and force code fixes before merge.

---

## Important Usage Note: "Probe URLs"

When you use the frontend dashboard within the containerized CI/CD environment, remember that **`localhost` inside the container only points to the dashboard itself**.

If you are running an **Experiment** and need to provide a **Probe URL**, you **must use the internal Docker container name** of the target service you are hitting:

✅ **Correct:** `http://target-app-api-gateway-1:8000/api/dashboard`  
❌ **Incorrect:** `http://localhost:8000/api/dashboard`

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Services show as "Down" in Dashboard | Ensure the ChaosController Docker container was started with `--network <your_app_network_name>`. |
| `tc: Operation not permitted` | Ensure you added `cap_add: NET_ADMIN` and `privileged: true` to your `docker-compose.yml`. |
| `stress-ng not found` | Ensure you added `RUN apt-get install -y stress-ng` to your service Dockerfiles. |
| Dashboard shows blank | Wait 5 seconds and refresh (the backend may take a moment to bind the static files). |
| Jenkins pipeline won't pause | Ensure the `input` step in the Jenkinsfile is not wrapped in a `timeout` block without a long enough limit. |
