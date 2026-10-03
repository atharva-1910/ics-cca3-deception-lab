# Decoy listener image (HANDOVER §10.4). One container per decoy (static lab IP),
# running either ssh_decoy.py or api_decoy.py. Holds NO state — forwards to the
# engine. decnet-only (internal: true): a decoy never reaches the host/internet.
FROM python:3.11-slim

WORKDIR /opt/content
RUN pip install --no-cache-dir asyncssh fastapi "uvicorn[standard]" httpx

COPY content/ /opt/content/

ENV ENGINE_URL=http://orchestrator:9000
# command (ssh_decoy.py | api_decoy.py) and DECOY_IP are set per service in the
# generated docker-compose.override.yml.
CMD ["python", "ssh_decoy.py"]
