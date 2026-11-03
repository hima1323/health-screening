# One image for Render: the Express API serves the built client, and starts the reasoning model
# (reasoning_model's triage expert system, python -m triage.demo_service) beside it.
# Debian trixie ships Python 3.13, which the pinned packages have wheels for.
FROM node:22-trixie-slim

# python for the reasoning model
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY reasoning_model/requirements-service.txt reasoning_model/
RUN python3 -m venv /opt/model && /opt/model/bin/pip install --no-cache-dir -r reasoning_model/requirements-service.txt

COPY client/package.json client/package-lock.json client/
RUN cd client && npm ci
COPY server/package.json server/package-lock.json server/
RUN cd server && npm ci --omit=dev

COPY client client
COPY server server
COPY reasoning_model reasoning_model
RUN cd client && npm run build && rm -rf node_modules

ENV NODE_ENV=production MODEL_PYTHON=/opt/model/bin/python
# the demo cases (only the draft vignettes: the ED datasets are not in the image); a broken model fails here
RUN cd reasoning_model/src && /opt/model/bin/python -m triage.demo_samples --build

CMD ["node", "server/index.js"]
