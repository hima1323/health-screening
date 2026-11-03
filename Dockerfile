# One image for Render: the Express API serves the built client, and starts the Python model service
# (model_service/serve.py) and the triage reasoning service (reasoning_model, triage.demo_service) beside it.
# Debian trixie ships Python 3.13, which the pinned model packages have wheels for.
FROM node:22-trixie-slim

# python for the model service; libgomp1 is the OpenMP runtime LightGBM links against
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv libgomp1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY model_service/requirements.txt model_service/
RUN python3 -m venv /opt/model && /opt/model/bin/pip install --no-cache-dir -r model_service/requirements.txt
# the triage service also needs these (numpy, pandas and scipy come with the model service)
RUN /opt/model/bin/pip install --no-cache-dir pyyaml jsonschema

COPY client/package.json client/package-lock.json client/
RUN cd client && npm ci
COPY server/package.json server/package-lock.json server/
RUN cd server && npm ci --omit=dev

COPY client client
COPY server server
COPY model_service model_service
COPY reasoning_model reasoning_model
RUN cd client && npm run build && rm -rf node_modules

ENV NODE_ENV=production MODEL_PYTHON=/opt/model/bin/python
# the model service self-checks against fusion.py's own probabilities, so a bad build fails here, not on stage
RUN /opt/model/bin/python model_service/serve.py --check
# the triage demo's cases (only the draft vignettes: the ED datasets are not in the image)
RUN cd reasoning_model/src && /opt/model/bin/python -m triage.demo_samples --build

CMD ["node", "server/index.js"]
