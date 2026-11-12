FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY app/ ./app/
COPY static/ ./static/
COPY eval/ ./eval/
COPY .env.example .env.example

# docs/ and data/ are mounted as volumes at runtime
RUN mkdir -p docs data

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
