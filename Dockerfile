# Container image for hosting outside Databricks (for example Render). Builds the UI, then the API.
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY backend backend
COPY db db
COPY --from=web /web/dist frontend/dist
EXPOSE 10000
CMD ["sh", "-c", "uvicorn --factory travel_planner.main:create_app --app-dir backend --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips='*'"]
