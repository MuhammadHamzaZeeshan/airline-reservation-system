FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv
COPY app/requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY app /srv/app
COPY workers /srv/workers
COPY seed /srv/seed
COPY sql /srv/sql
COPY loadtest /srv/loadtest
COPY pytest.ini /srv/pytest.ini
EXPOSE 8000
# Bounded concurrency: backlog + keep-alive limits keep one node from collapsing under a spike.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--backlog", "2048", "--timeout-keep-alive", "5"]
