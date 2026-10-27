FROM python:3.11-slim

WORKDIR /app

# Copy dependency definitions
COPY requirements.txt pyproject.toml ./

# Install dependencies if present
RUN pip install --no-cache-dir -r requirements.txt || true

# Copy application source
COPY src/ ./src/
COPY tests/ ./tests/
COPY evals/ ./evals/

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Run unit tests on container build to verify integrity
RUN python3 -m unittest discover tests/

ENTRYPOINT ["python3", "-m", "strava_health_agent.cli"]
CMD ["demo", "--scenario", "danger_spike"]
