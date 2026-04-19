# ───────────────────────────────────────────────
# Stage 1: Build the React frontend
# ───────────────────────────────────────────────
FROM node:18-alpine AS frontend-build

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
RUN npm run build
# Output: /frontend/dist/ contains index.html + assets/


# ───────────────────────────────────────────────
# Stage 2: Python controller runtime
# ───────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies
COPY framework-controller/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the controller source code
COPY framework-controller/ .

# Remove any stale bytecode from the host machine
RUN find /app -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; true

# Copy the compiled React frontend from Stage 1
# It lands at /app/static — this is what main.py serves
COPY --from=frontend-build /frontend/dist /app/static

# Verify the frontend was actually built and copied
RUN ls /app/static/index.html && echo "✅ Frontend build verified"

# Expose the controller's port
EXPOSE 5050

# Start the controller
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5050"]
