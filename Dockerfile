FROM python:3.12-slim
WORKDIR /app
RUN useradd -m appuser && mkdir /dados && chown -R appuser:appuser /app /dados && chmod 755 /dados
COPY servidor.py .
ENV PYTHONUNBUFFERED=1 DB_PATH=/dados/dados.db
EXPOSE 5000
USER appuser
CMD ["python", "servidor.py"]
