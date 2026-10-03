# Attacker container (HANDOVER §8, §10.7). Runs the recon agent and its tools
# from INSIDE the lab network (10.66.0.100) — the only place scanning happens,
# since Docker Desktop for Mac gives the host no route to container IPs
# (CLAUDE.md §1). Attached to decnet only (internal: true): no internet.
FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends nmap openssh-client curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/attacker
COPY requirements.txt /opt/attacker/requirements.txt
RUN pip install --no-cache-dir python-nmap paramiko requests pyyaml httpx

COPY attacker/ /opt/attacker/attacker/
# idle by default; experiments exec into this container (see Makefile / run_benchmark)
CMD ["sleep", "infinity"]
