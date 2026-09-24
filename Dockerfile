FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY . /app
RUN useradd --create-home --uid 10001 kontturi && \
    mkdir -p /var/lib/kontturi/media /app/backend/.local && \
    chown -R kontturi:kontturi /var/lib/kontturi /app/backend
USER kontturi
RUN KONTTURI_ENV=local python backend/manage.py collectstatic --noinput --verbosity 0
ENV KONTTURI_ENV=production MEDIA_ROOT=/var/lib/kontturi/media
EXPOSE 8000
WORKDIR /app/backend
CMD ["waitress-serve", "--listen=0.0.0.0:8000", "--threads=4", "--max-request-body-size=12582912", "--ident=", "config.wsgi:application"]
