FROM mcr.microsoft.com/playwright/python:v1.63.0-noble
WORKDIR /app
COPY runner/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY runner ./runner
COPY fixture_contract ./fixture_contract
USER pwuser
CMD ["python", "-m", "runner.runner"]
