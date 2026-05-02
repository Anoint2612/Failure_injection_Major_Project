# Quick Start: Running the Jenkins Demo (Subsequent Runs)

If you have already completed the initial setup from the `COMPLETE_JENKINS_DEMO_GUIDE.md`, follow this guide to start the demo again after shutting down your PC or returning on a new day.

## 1. Start Jenkins

Depending on how Docker shut down on your machine, your Jenkins container might still exist, or it might have been removed. 

**Attempt 1: Start the existing container**
Open your terminal and run:
```bash
docker start jenkins
```

### ⚠️ If Attempt 1 fails with "Error: No such container: jenkins"
This means Docker automatically cleaned up the container when your PC shut down. Don't panic! Your data (jobs, pipelines, credentials) is safe in your `~/jenkins_home` folder. You just need to recreate the container and reinstall the Docker plugins inside it.

**Step 1: Recreate the container**
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

**Step 2: Reinstall Docker Compose & Buildx inside Jenkins**
Because this is a brand new container, it's missing the Docker plugins needed to build your app. Run this command:
```bash
docker exec -u root jenkins bash -c "
  mkdir -p /usr/libexec/docker/cli-plugins
  
  # Install docker-compose
  curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o /usr/local/bin/docker-compose
  chmod +x /usr/local/bin/docker-compose
  ln -sf /usr/local/bin/docker-compose /usr/bin/docker-compose

  # Install docker-buildx plugin
  curl -SL https://github.com/docker/buildx/releases/download/v0.33.0/buildx-v0.33.0.linux-amd64 -o /usr/libexec/docker/cli-plugins/docker-buildx
  chmod +x /usr/libexec/docker/cli-plugins/docker-buildx

  # Install pip and venv (required for python dependencies if needed)
  apt-get update && apt-get install -y python3 python3-pip python3-venv
"
```

## 2. Access the Jenkins Dashboard

1. Open your web browser and go to: **[http://localhost:8080](http://localhost:8080)**
2. Log in with the credentials you created during the initial setup.

## 3. Trigger the Pipeline

1. On the Jenkins dashboard, click on your pipeline project: **`voting-app-resilience-gate`**
2. On the left menu, click **Build Now**.
3. A new build run will appear under "Build History" (e.g., `#3`). Click on the build number.
4. Click on **Console Output** to watch the pipeline execute in real-time.

## 4. The Live Demo Flow

During the presentation, here is exactly what you should do while the pipeline runs:

1. **Wait for the App to Build**: Jenkins will clone your fork (`voting-app-chaos-demo`), build the Docker images, and start the app network.
2. **Wait for ChaosController**: Jenkins will start the `chaos-controller-ci` container and wait for it to report as "ready".
3. **The Resilience Gate Pauses**: The pipeline will pause and prompt for **"Resilience Testing Gate"**. It is waiting for human interaction.
4. **Open the Dashboards**:
   - Open the Voting App: **[http://localhost:8082](http://localhost:8082)**
   - Open ChaosController: **[http://localhost:5050](http://localhost:5050)**
5. **Demonstrate Chaos**: 
   - Show the audience the working Voting App.
   - Go to ChaosController, select the `vote` service, and inject a **Latency** or **Stress** fault.
   - Show the audience how the Voting App responds to the fault.
   - Click **Recover** in ChaosController to restore normal operations.
6. **Approve the Gate**: Go back to the Jenkins UI and click **Proceed** (or Approve) on the paused pipeline step.
7. **Pipeline Completes**: Jenkins will automatically tear down the test environment and clean up the containers.

## Troubleshooting

- **Port Conflicts**: Ensure nothing else is running on ports `8080` (Jenkins), `8082` (Voting App), `8081` (Result App), or `5050` (ChaosController). You can use `docker ps` to check. If previous demo containers are stuck, run `docker rm -f $(docker ps -aq --filter "name=voting-app") 2>/dev/null`.
