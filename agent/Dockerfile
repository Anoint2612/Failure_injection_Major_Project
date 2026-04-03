FROM python:3.10-slim
WORKDIR /app

# Install stress-ng and iproute2 (for tc capability)
RUN apt-get update && apt-get install -y stress-ng iproute2 iptables && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Run in unbuffered mode so logs appear instantly
CMD ["python", "-u", "main.py"]
