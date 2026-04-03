FROM python:3.9-slim
WORKDIR /app
# Add iproute2 here!
RUN apt-get update && apt-get install -y iproute2 stress-ng && rm -rf /var/lib/apt/lists/*
RUN pip install fastapi uvicorn httpx prometheus-fastapi-instrumentator
COPY . .
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8002"] 
# (Note: Use the correct port for each service: 8000, 8001, 8002)