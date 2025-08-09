FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

# ВСЁ В ОДНУ СТРОКУ:
EXPOSE 5000
CMD ["sh", "-c", "exec gunicorn -w 1 -k gthread --threads 8 --timeout 60 --bind 0.0.0.0:${PORT:-8080} entry:app"]


