# Dockerfile
FROM python:3.11-slim

# Рабочая директория
WORKDIR /app

# Копируем весь код
COPY . .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Экспонируем порт (если нужно)
EXPOSE 5000

# Команда запуска
CMD ["python", "entry.py"]
