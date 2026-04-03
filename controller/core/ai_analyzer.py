import yaml
import os
import json
import requests
import google.generativeai as genai

# Setup API Key securely
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")

class AIAnalyzer:
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-2.5-pro') if GEMINI_API_KEY else None

    def read_architecture(self, compose_path: str = "/app/target-app/docker-compose.yml"):
        """Extracts dependency graph AST from Docker Compose configs."""
        try:
            # Depending on deployment, actual path may vary
            if not os.path.exists(compose_path):
                return {"gateway": ["auth-service", "data-service"]} # Mock fallback for demo
                
            with open(compose_path, 'r') as f:
                compose_file = yaml.safe_load(f)
                
            services = compose_file.get("services", {})
            topology = {}
            for name, config in services.items():
                topology[name] = config.get("depends_on", [])
                
            return topology
        except Exception as e:
            return {"error": str(e)}

    def generate_chaos_scenarios(self):
        """Uses Gemini GenAI to suggest targeted GameDays based on AST topology."""
        if not self.model:
            return [{"name": "auth-mock-latency", "target_selector": {"container": "auth-service"}, "parameters": {"delay": "300ms"}, "reasoning": "Mock: Provide GEMINI API KEY for real suggestions"}]
            
        topology = self.read_architecture()
        prompt = f"""
        You are an SRE Principal Engineer. 
        Here is the topology of our microservices system: {json.dumps(topology)}
        
        Generate 3 strict JSON objects representing Chaos Engineering GameDays to test this.
        Example format: 
        [{{ "name": "gateway-auth-latency", "target_selector": {{"container": "auth-service"}}, "parameters": {{"delay": "200ms"}}, "reasoning": "Gateway might lack fallback if auth is slow" }}]
        
        Return ONLY valid JSON.
        """
        try:
            response = self.model.generate_content(prompt)
            # Safe parsing
            text = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception as e:
            return {"error": str(e)}

    def extract_metrics(self):
        """Pulls raw telemetry from Prometheus after an experiment."""
        try:
            query = "rate(gateway_requests_total{status='503'}[1m])"
            res = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query})
            
            query_latency = "rate(gateway_latency_seconds_sum[1m]) / rate(gateway_latency_seconds_count[1m])"
            res_lat = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query_latency})
            
            return {
                "error_rates_503": res.json() if res.status_code == 200 else [],
                "latency_spikes": res_lat.json() if res_lat.status_code == 200 else []
            }
        except Exception as e:
            return {"error": f"Failed reaching Prometheus: {str(e)}"}

    def generate_sre_report(self, experiment_name: str):
        """Generates the post-mortem SRE Report."""
        if not self.model:
            return {"report_markdown": "## Mock SRE Report\n\nGemini API key not configured. Mock analysis: Latency increased by 200ms. Consider circuit breakers."}
            
        metrics = self.extract_metrics()
        prompt = f"""
        You are an SRE Principal Engineer analyzing telemetry post-experiment '{experiment_name}'.
        
        Prometheus Telemetry: {json.dumps(metrics)}
        
        Write a concise, professional SRE Remediation Report analyzing the degradation and suggesting concrete code-level fixes (e.g., Circuit Breakers, Retries). Use markdown formatting.
        """
        try:
            response = self.model.generate_content(prompt)
            return {"report_markdown": response.text}
        except Exception as e:
            return {"error": str(e)}
