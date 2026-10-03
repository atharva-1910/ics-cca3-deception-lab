# Deception engine (HANDOVER §10.6). Holds the consistency store and talks to
# host-native Ollama. This is the ONLY container attached to both decnet and the
# host-egress network (CLAUDE.md §1 gotcha #2), so decoys stay internal-only.
FROM python:3.11-slim

WORKDIR /opt/app
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" httpx pydantic

COPY store/ /opt/app/store/
COPY orchestrator/ /opt/app/orchestrator/
COPY content/prompts/ /opt/app/content/prompts/

ENV OLLAMA_URL=http://host.docker.internal:11434
ENV OLLAMA_MODEL=llama3.1:8b
EXPOSE 9000
CMD ["python", "-m", "uvicorn", "orchestrator.engine:create_app", \
     "--factory", "--host", "0.0.0.0", "--port", "9000"]
