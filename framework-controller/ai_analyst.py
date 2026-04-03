from dotenv import load_dotenv
import os
from google import genai
import json

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def analyze_results(json_file):
    # Read the data from the experiment we just ran
    with open(json_file, 'r') as f:
        data = json.load(f)

    # The Prompt: This is the "Secret Sauce" for your research paper
    prompt = f"""
    You are a Senior Site Reliability Engineer (SRE). 
    I ran a chaos engineering experiment on a microservices system.
    Here is the latency data collected during the failure:
    {json.dumps(data)}

    Please provide:
    1. Root Cause Analysis: What happened to the user experience?
    2. Resilience Score: (0-10) based on the recovery and latency.
    3. Remediation: Suggest 2 specific technical improvements (e.g., timeouts, circuit breakers).
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    
    print("\n--- GEMINI AI RESILIENCE REPORT ---")
    print(response.text)
    
    # Save the report for the research paper
    with open("ai_remediation_report.md", "w") as f:
        f.write(response.text)

if __name__ == "__main__":
    analyze_results("experiment_results.json")