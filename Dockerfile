FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY data ./data

# pass GEMINI_API_KEY at runtime via -e or an env file
ENTRYPOINT ["python", "-m", "src.main"]
