from dotenv import load_dotenv
import os
from google import genai
import json

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def generate_chaos_scenario():
    # Read your architecture file
    with open("../target-app/docker-compose.yml", "r") as f:
        arch = f.read()

    prompt = f"""
    Analyze this Docker Compose architecture:
    {arch}

    Suggest one 'Chaos Scenario' that would test the system's robustness.
    Format your answer as:
    - Target Service: 
    - Fault Type: (Latency, Crash, or CPU Stress)
    - Hypothesis: What do you think will happen to the API Gateway?
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    print("\n--- AI-GENERATED CHAOS SCENARIO ---")
    print(response.text)

    with open("scenario_generation_report.md", "w") as f:
        f.write(response.text)

if __name__ == "__main__":
    generate_chaos_scenario()