pipeline {
    agent any

    environment {
        // Jenkins credential ID for the Gemini API key.
        // Add yours at: Jenkins → Manage Jenkins → Credentials
        GEMINI_API_KEY = credentials('gemini-api-key')
        
        // Path to your docker-compose file (relative to repo root)
        COMPOSE_FILE = 'target-app/docker-compose.yml'
        
        // The network created by your compose file (usually <foldername>_default)
        APP_NETWORK = 'target-app_default'
    }

    stages {

        stage('Build & Deploy Application') {
            steps {
                echo '🔨 Building and starting the application...'
                // Spin up the target application. Make sure the Dockerfiles have iproute2 and stress-ng!
                sh "docker compose -f ${COMPOSE_FILE} up --build -d"
                sh "sleep 15" // Wait for services to be healthy
                echo '✅ Application is running.'
            }
        }

        stage('Start ChaosController') {
            steps {
                echo '🔥 Starting ChaosController...'
                // We run the framework image and attach it to the application's network
                // so it can communicate with your services.
                sh """
                    docker run -d \\
                        --name chaos-controller-ci \\
                        --network ${APP_NETWORK} \\
                        -p 5050:5050 \\
                        -v /var/run/docker.sock:/var/run/docker.sock \\
                        -e GEMINI_API_KEY=${GEMINI_API_KEY} \\
                        chaos-controller:latest
                """
                sh "sleep 10" // Wait for controller backend to boot
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
║   IMPORTANT for Experiments: When typing the "Probe URL",    ║
║   use your internal docker container name, not localhost!    ║
║   (e.g., http://target-app-api-gateway-1:8000 )              ║
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
            echo '🧹 Cleaning up ...'
            sh 'docker stop chaos-controller-ci || true'
            sh 'docker rm chaos-controller-ci || true'
            sh "docker compose -f ${COMPOSE_FILE} down || true"
        }
    }
}
