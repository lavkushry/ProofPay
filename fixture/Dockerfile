FROM python:3.11-slim
WORKDIR /app
COPY fixture/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY fixture ./fixture
COPY fixture_contract ./fixture_contract
EXPOSE 8080
CMD ["uvicorn", "fixture.app:app", "--host", "0.0.0.0", "--port", "8080"]
