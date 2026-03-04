FROM python:3.11-slim

WORKDIR /app

# Kopiuj pliki wymagań i zainstaluj zależności (warstwa cache)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Kopiuj kod źródłowy
COPY src/ ./src/

EXPOSE 8000 50051

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
