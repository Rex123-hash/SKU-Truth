# The public submission API (backend only). The frontend is deployed separately.
#
#   gcloud run deploy skutruth-api --source . --region us-central1
#
# Two things about this image are load-bearing:
#
# 1. LAYOUT. `ApiSettings` resolves its data root as parents[3] of
#    backend/skutruth/api/config.py — i.e. the directory holding `backend/`. So `backend/`
#    and `data/` must keep their relative positions and the package must NOT be installed
#    into site-packages, or the demo record becomes unreachable at runtime.
#
# 2. WHAT IS ABSENT. Only the two data files the API actually reads are copied in. The
#    organizer pack, the manufacturer artifacts, and the runtime cassettes are third-party
#    material with no redistribution grant, and this image is public.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY deploy/requirements-api.txt ./deploy/requirements-api.txt
RUN pip install --no-cache-dir -r ./deploy/requirements-api.txt

COPY backend/ ./backend/
COPY data/demo/cases.json ./data/demo/cases.json
COPY data/discovery/manufacturer_domains.demo.toml ./data/discovery/manufacturer_domains.demo.toml

ENV PYTHONPATH=/app/backend \
    SKUTRUTH_API_MODE=DEMO_REPLAY \
    PORT=8080

# Fail the BUILD, not a judge's first request. This proves the import graph resolves with
# the pinned subset, that both data files landed at the paths the settings resolve to, and
# that the committed demo record parses into exactly the three real cases.
RUN python -c "\
from skutruth.api.asgi import app;\
from skutruth.api.config import ApiSettings;\
s = ApiSettings.from_env();\
assert s.mode.value == 'DEMO_REPLAY', s.mode;\
assert s.demo_cases_path.exists(), s.demo_cases_path;\
assert s.registry_path.exists(), s.registry_path;\
n = len(app.state.library.cases);\
assert n == 3, n;\
print('image self-check ok:', s.mode.value, n, 'demo cases')"

# Cloud Run runs the container as this user; nothing in the image needs to be written to.
RUN useradd --create-home --uid 10001 skutruth && chown -R skutruth:skutruth /app
USER skutruth

EXPOSE 8080

# Cloud Run supplies PORT. Bind 0.0.0.0 — never localhost.
CMD exec uvicorn skutruth.api.asgi:app --host 0.0.0.0 --port ${PORT:-8080}
