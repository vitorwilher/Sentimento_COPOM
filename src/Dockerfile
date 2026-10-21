FROM python:3.11-slim

WORKDIR /app

# Dependências primeiro (cache de camadas).
COPY src/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Código da API.
COPY src/ ./src/

# Caches do pipeline (fonte de verdade do MVP de leitura).
COPY atas_cache.json selic_cache.json ./
COPY scores_gemini_cache.csv scores_claude_cache.csv scores_openai_cache.csv ./

WORKDIR /app/src
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
