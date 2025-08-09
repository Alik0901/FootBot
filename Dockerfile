FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

# ВСЁ В ОДНУ СТРОКУ:
EXPOSE 5000
CMD ["gunicorn", "-c", "gunicorn_conf.py", "entry:app"]


