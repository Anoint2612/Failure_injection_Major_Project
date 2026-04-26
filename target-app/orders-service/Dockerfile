FROM python:3.9-slim
WORKDIR /app
# Required for chaos tooling (tc/iptables + stress)
RUN apt-get update && apt-get install -y iproute2 stress-ng && rm -rf /var/lib/apt/lists/*
RUN pip install fastapi uvicorn httpx prometheus-fastapi-instrumentator
COPY . .
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8003"]

