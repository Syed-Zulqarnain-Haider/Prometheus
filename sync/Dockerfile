FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY metric_registry.py sync_job.py ./
# Runs as a Cloud Run JOB (not a service) — executes once and exits.
ENTRYPOINT ["python", "sync_job.py"]
