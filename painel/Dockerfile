FROM python:3.12-slim
RUN useradd -m painel
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY painel.py seed.py .
USER painel
EXPOSE 8080
CMD ["python", "-u", "painel.py"]
