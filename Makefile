# Standard entry points (HANDOVER §12). macOS + Docker Desktop + host-native
# Ollama (CLAUDE.md §1). PY is the project venv interpreter for host tooling.
PY ?= .venv/bin/python
COMPOSE = docker compose -f docker-compose.yml
STATIC  = -f decoys/static/docker-compose.static.yml
OVERRIDE = $(wildcard docker-compose.override.yml)

.PHONY: help venv test topology seed up up-static down reset lab-accept agent benchmark aggregate clean

help:
	@echo "targets: venv test topology seed up up-static down reset lab-accept agent benchmark aggregate"

venv:
	python3 -m venv .venv && . .venv/bin/activate && pip install -U pip && pip install -r requirements.txt

test:            ## run the host-side unit/acceptance tests (no Docker/Ollama needed)
	$(PY) -m pytest tests/ -q

topology:        ## generate topology.json + docker-compose.override.yml
	$(PY) topology/generator.py --decoys 4 --seed 1

seed:            ## build the base store snapshot from topology.json + real hosts
	$(PY) store/seed.py --snapshot base

decoy-image:     ## build the shared decoy image once (all decoys reference it)
	docker build -t deception-decoy:latest ./content

up: topology seed decoy-image ## start the full lab (real hosts + engine + attacker + generated decoys)
	$(COMPOSE) $(if $(OVERRIDE),-f docker-compose.override.yml,) up -d --build

up-static:       ## start the lab with the static (D0) decoys overlaid
	$(COMPOSE) $(STATIC) up -d --build

down:
	$(COMPOSE) $(if $(OVERRIDE),-f docker-compose.override.yml,) $(STATIC) down -v

reset:           ## restore the store snapshot and clear live logs (HANDOVER §12.3)
	$(PY) store/seed.py --snapshot base
	: > results/live.jsonl || true

lab-accept:      ## Module 1 acceptance test (§10.1): attacker sees every real host
	@echo ">> nmap from the attacker container (expect 10.66.0.10 and 10.66.0.11 up):"
	$(COMPOSE) exec attacker nmap -sV --open 10.66.0.0/24 | tee /tmp/nmap.out
	@grep -q "10.66.0.10" /tmp/nmap.out && grep -q "10.66.0.11" /tmp/nmap.out \
		&& echo "PASS: both real hosts discovered" \
		|| (echo "FAIL: a real host was not found" && exit 1)
	@echo ">> host-side check: no published lab ports (expect empty):"
	@docker compose ps --format '{{.Publishers}}' | grep -v '^\[\]$$' || echo "PASS: no host-published ports"

demo:            ## live False-Belief Attack walkthrough (lab must be up; fresh chain first)
	$(PY) store/seed.py --snapshot base
	$(PY) narrative/generator.py --template t1 --seed 7 --run-id DEMO
	: > results/live.jsonl
	$(COMPOSE) restart orchestrator && sleep 3
	./demo.sh

prove-isolation: ## prove harvested fake creds open decoys but are REJECTED on real hosts
	$(PY) store/seed.py --snapshot base
	$(PY) narrative/generator.py --template t1 --seed 7 --run-id ISO
	$(COMPOSE) restart orchestrator && sleep 3
	./prove_isolation.sh

agent:           ## run one agent manually (VARIANT=naive DEFENSE=D2 SEED=7)
	$(PY) attacker/recon_agent.py --variant $(or $(VARIANT),naive) \
		--defense $(or $(DEFENSE),D2) --seed $(or $(SEED),7) --run-id manual

benchmark:       ## full Experiment C sweep (needs live lab + Ollama)
	$(PY) eval/run_benchmark.py --experiment C --seeds 1-10 \
		--agents naive,hardened --defenses D0,D1,D2

aggregate:
	$(PY) eval/aggregate.py --experiment C

clean:
	rm -f store/state.db ground_truth.json docker-compose.override.yml topology.json
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
