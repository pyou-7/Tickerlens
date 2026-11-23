# Tickerlens — public hosting image (Railway)
# Build context is the GitHub repo. The seeded SQLite DB (tickerlens.db)
# is committed (git add -f) so the image ships with all 303 companies;
# entrypoint.sh copies it onto the persistent volume on first boot.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY alembic ./alembic
COPY alembic.ini .
COPY tickerlens.db ./tickerlens.db
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

EXPOSE 8123
ENTRYPOINT ["./entrypoint.sh"]
