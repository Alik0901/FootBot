FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

# ВСЁ В ОДНУ СТРОКУ:
CMD ["gunicorn","entry:app","--workers","2","--bind","0.0.0.0:5000","--capture-output","--log-level","debug"]
