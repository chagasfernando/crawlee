FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y wget gnupg
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium && playwright install-deps
COPY main.py .
EXPOSE 8000
CMD ["python", "main.py"]
