FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn[standard] pydantic

COPY mock_api/ ./mock_api/

EXPOSE 8000

CMD ["uvicorn", "mock_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
