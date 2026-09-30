FROM python:3.14-slim-bookworm

# System dependencies
RUN apt-get update && apt-get install -y \
    git curl wget gnupg2 \
    mariadb-client \
    redis-tools \
    wkhtmltopdf \
    libssl-dev libffi-dev \
    libmariadb-dev gcc g++ pkg-config \
    xvfb xfonts-75dpi xfonts-base \
    && rm -rf /var/lib/apt/lists/*

# Install Node 24
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g yarn

# Install bench CLI
RUN pip install frappe-bench

# Create bench user
RUN useradd -m -s /bin/bash frappe
WORKDIR /home/frappe
USER frappe

# Build from this repo's current working tree instead of cloning a separate
# fork (Lijishwilson-HTIPL/Frappe-Code) — that fork could silently drift out
# of sync with hephzibahtechnologies/Frappe-Code (the one this session
# actually pushes to), so any app added/changed here (e.g. the "mercury" app,
# or any of quality_dms/sbiqc_provisioning's local work) previously never
# reached the running container without a manual docker cp per file. This
# repo's root already IS a bench checkout (apps/, sites/apps.txt, etc.), so a
# straight copy is enough — see .dockerignore for what's excluded.
USER root
COPY --chown=frappe:frappe . /home/frappe/frappe-bench
USER frappe

WORKDIR /home/frappe/frappe-bench

# Set up Python virtualenv and install all apps
RUN bench setup env && \
    env/bin/pip install -e apps/frappe && \
    env/bin/pip install -e apps/erpnext && \
    env/bin/pip install -e apps/crm && \
    env/bin/pip install -e apps/hrms && \
    env/bin/pip install -e apps/helpdesk && \
    env/bin/pip install -e apps/telephony && \
    env/bin/pip install -e apps/sbiqc_provisioning && \
    env/bin/pip install -e apps/quality_dms && \
    env/bin/pip install -e apps/crm_unify && \
    env/bin/pip install -e apps/mercury

# Install frontend dependencies for all apps
RUN cd apps/frappe   && yarn install --frozen-lockfile && cd ../.. && \
    cd apps/erpnext  && yarn install --frozen-lockfile 2>/dev/null || true && cd ../.. && \
    cd apps/crm      && yarn install --frozen-lockfile 2>/dev/null || true && cd ../.. && \
    cd apps/hrms     && yarn install --frozen-lockfile 2>/dev/null || true && cd ../.. && \
    cd apps/helpdesk && yarn install --frozen-lockfile 2>/dev/null || true && cd ../..

# Build frontend assets — compiles Vue/JS bundles for CRM, Helpdesk, etc.
RUN bench build --app frappe --app erpnext --app crm --app hrms --app helpdesk --app telephony --app quality_dms --app mercury || true

# Regenerate Procfile with correct container paths; strip local redis entries
# (Redis runs in separate containers — no redis-server binary needed here)
RUN echo y | bench setup procfile && sed -i '/^redis_/d' Procfile

# bench was created via git clone (not `bench init`), so the logs dir honcho/bench
# start writes to does not exist — create it or `bench start` crash-loops.
RUN mkdir -p logs sites/assets

EXPOSE 8000 9000

# At startup: write Redis + DB config directly into common_site_config.json, then start bench.
# Using python instead of 'bench set-config' because bench requires a TTY / interactive context
# and is not reliably in PATH during Docker CMD execution.
CMD python3 -c " \
import json, os; \
cfg_path = 'sites/common_site_config.json'; \
cfg = json.load(open(cfg_path)) if os.path.exists(cfg_path) else {}; \
cfg.update({ \
  'redis_cache':    'redis://' + os.environ.get('REDIS_CACHE',    'redis-cache:6379'), \
  'redis_queue':    'redis://' + os.environ.get('REDIS_QUEUE',    'redis-queue:6379'), \
  'redis_socketio': 'redis://' + os.environ.get('REDIS_SOCKETIO', 'redis-socketio:6379'), \
  'db_host': os.environ.get('DB_HOST', 'db'), \
  'db_port': int(os.environ.get('DB_PORT', 3306)), \
}); \
json.dump(cfg, open(cfg_path, 'w'), indent=1) \
" && bench start
