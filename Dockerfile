# Standard syntax uses Docker's built-in frontend; no extra registry frontend required.
FROM node:22.23.3-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS frontend
WORKDIR /assets
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend ./frontend
COPY templates ./templates
COPY apps ./apps
COPY scripts/copy_frontend.mjs ./scripts/copy_frontend.mjs
RUN mkdir -p static/css static/js && npm run build

FROM python:3.12.15-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS python-base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
RUN groupadd --gid 10001 shipping && useradd --uid 10001 --gid shipping --no-create-home shipping && mkdir -p /data/private /app/staticfiles && chown -R shipping:shipping /data /app
RUN chmod 0700 /data /data/private
COPY --chown=shipping:shipping apps ./apps
COPY --chown=shipping:shipping config ./config
COPY --chown=shipping:shipping templates ./templates
COPY --chown=shipping:shipping locale ./locale
COPY --chown=shipping:shipping static ./static
COPY --chown=shipping:shipping scripts ./scripts
COPY --chown=shipping:shipping deploy ./deploy
COPY --chown=shipping:shipping tests ./tests
COPY --chown=shipping:shipping manage.py ./manage.py
COPY --from=frontend --chown=shipping:shipping /assets/static/css/site.css /app/static/css/site.css
COPY --from=frontend --chown=shipping:shipping /assets/static/js/alpine.min.js /app/static/js/alpine.min.js
RUN python scripts/compile_translations.py
USER shipping
EXPOSE 8000

FROM python-base AS development
ENV DJANGO_SETTINGS_MODULE=config.settings.development
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

FROM python-base AS production
# This build-only key is non-secret and is NOT written into image environment.
RUN DJANGO_SETTINGS_MODULE=config.settings.base DJANGO_SECRET_KEY=build-only-collectstatic-placeholder-not-runtime-secret-000000000000 SHIPPING_DATA_DIR=/tmp/collectstatic python manage.py collectstatic --noinput
ENV DJANGO_SETTINGS_MODULE=config.settings.production
CMD ["gunicorn", "config.wsgi:application", "--config", "deploy/gunicorn.conf.py"]
