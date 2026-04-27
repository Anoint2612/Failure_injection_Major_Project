pipeline {
    agent any

    environment {
        GEMINI_API_KEY   = credentials('gemini-api-key')
        COMPOSE_FILE     = 'target-app/docker-compose.yml'
        APP_NETWORK      = 'target-app_test-net'
        CHAOS_IMAGE      = 'chaos-controller:latest'
        CHAOS_CONTAINER  = 'chaos-controller-ci'
    }

    stages {

        // ── Stage 1: Build & Start Application ───────────────────────────
        stage('Build & Start Application') {
            steps {
                echo '🔨 Building and starting the application stack...'
                sh "docker compose -f ${COMPOSE_FILE} up --build -d"
                echo '✅ Application stack is building...'
            }
        }

        // ── Stage 2: Static Analysis (runs while app starts) ─────────────
        // The ChaosController starts HERE, warming up during static analysis.
        // By the time we reach the Resilience Gate, it has been up for ~2+ min.
        stage('Static Analysis + Start ChaosController') {
            parallel {
                stage('Start ChaosController') {
                    steps {
                        echo '🔥 Starting ChaosController (warming up alongside static analysis)...'
                        // Remove any leftover container from previous runs
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
                        // Wait for FastAPI to be ready
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
                stage('Static Code Analysis') {
                    steps {
                        echo '🔍 Running static analysis...'
                        // Replace with your actual static analysis tools:
                        // sh 'pylint target-app/api-gateway/'
                        // sh 'eslint frontend/src/'
                        // sh 'bandit -r target-app/'
                        echo '✅ Static analysis complete.'
                    }
                }
            }
        }

        // ── Stage 3: Application Health Check ────────────────────────────
        stage('Application Health Check') {
            steps {
                echo '🏥 Verifying all services are healthy...'
                sh '''
                    for i in $(seq 1 20); do
                        curl -sf http://localhost:8000/health > /dev/null && echo "API Gateway healthy" && exit 0
                        echo "Waiting for services... ($i/20)"
                        sleep 5
                    done
                    echo "Application failed to become healthy!" && exit 1
                '''
                echo '✅ Application is healthy and ready for resilience testing.'
            }
        }

        // ── Stage 4: Automated Resilience Gate ───────────────────────────
        stage('Resilience Gate (Automated)') {
            steps {
                echo '🔥 Running automated resilience gate via chaos-runner...'
                sh '''
                    # Install chaos-runner from the repo
                    pip install -e . --quiet

                    # Run the gate against the chaos-config.yml in repo root.
                    # --controller-url overrides config to use the CI container name.
                    chaos-runner run \\
                        --config chaos-config.yml \\
                        --controller-url http://localhost:5050

                    # chaos-runner exits 0 on PASS, 1 on FAIL.
                    # Jenkins automatically fails the stage on non-zero exit.
                '''
            }
            post {
                always {
                    // Archive the reports as build artifacts
                    archiveArtifacts artifacts: 'chaos-report.html, chaos-report.json', allowEmptyArchive: true
                    publishHTML(target: [
                        allowMissing: true,
                        alwaysLinkToLastBuild: true,
                        keepAll: true,
                        reportDir: '.',
                        reportFiles: 'chaos-report.html',
                        reportName: 'Resilience Gate Report'
                    ])
                }
            }
        }

        // ── Stage 5: Deploy to Production ────────────────────────────────
        stage('Deploy to Production') {
            // Only runs if all previous stages pass
            steps {
                echo '🚀 Resilience gate passed — deploying to production...'
                // Replace with your actual deployment steps:
                // sh 'kubectl apply -f k8s/'
                // sh 'helm upgrade --install my-app ./charts/my-app'
                echo '✅ Deployed to production.'
            }
        }
    }

    post {
        always {
            echo '🧹 Cleaning up CI environment...'
            sh "docker stop ${CHAOS_CONTAINER} 2>/dev/null || true"
            sh "docker rm ${CHAOS_CONTAINER} 2>/dev/null || true"
            sh "docker compose -f ${COMPOSE_FILE} down 2>/dev/null || true"
        }
        failure {
            echo '❌ Pipeline failed. Check the Resilience Gate Report artifact for details.'
            // Add Slack/email notification here if needed:
            // slackSend channel: '#deployments', message: "❌ Resilience gate FAILED for ${env.JOB_NAME} build ${env.BUILD_NUMBER}"
        }
        success {
            echo '✅ Pipeline succeeded. Application is deployed and resilient!'
        }
    }
}
