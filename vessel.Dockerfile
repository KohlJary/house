# The vessel: the daemon's backend (FastAPI), with the Babelr client it talks through.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl git build-essential ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY src/vessel/backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY src/babelr/packages/agent-client-py /opt/babelr-agent
RUN pip install --no-cache-dir /opt/babelr-agent

COPY src/vessel/backend backend
COPY seed/vessel_seed.py seed/member_genesis.py seed/member_name.py /house/

WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "main_sdk.py"]
