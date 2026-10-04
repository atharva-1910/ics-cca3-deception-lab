# Project Report — Deceiving the Machines

**A hybrid, state-grounded cyber-deception lab with a False-Belief Attack against AI-driven
reconnaissance.**

ICS CCA3 mini-project · B.Tech CSE Sem VII · MIT World Peace University, Pune
Team: Siddhi Karhekar, Atharva Hemade, Taneesha Badhe, Soham Ghodake

This report documents what has been built, how it is wired together, the results produced so
far, and how to run and test it locally. The authoritative specification is
[`HANDOVER.md`](../HANDOVER.md); machine-specific rules are in [`CLAUDE.md`](../CLAUDE.md).

---

## 1. What this project is

An isolated Docker lab where **real hosts sit beside decoy hosts**. An autonomous **LLM
reconnaissance agent** (a ReAct loop with `nmap`, SSH and HTTP tools) attacks the lab and must
produce an intelligence report: which hosts are real, which are honeypots, what credentials
exist, and the single most valuable next target.

The decoys defend in three escalating ways:

1. **Static decoys (D0)** — Cowrie SSH + a fixed-banner API. The deterministic baseline.
2. **Injection decoys (D1)** — Mantis-style prompt injections embedded in banners/files
   (re-implemented from the literature, *not* the original code). Lab-only.
3. **Clue-chain decoys (D2, our USP)** — the **False-Belief Attack**: decoys plant a chain of
   mutually-confirming **fake facts** (not instructions) across several hosts through a shared
   **consistency store**. Each fact the agent verifies raises its confidence in the next, so a
   fabricated path ends up in its final report as ground truth.

We score how corrupted the agent's final report is with the **Belief Corruption Score (BCS)**
and its planted-only variant **PBCS** (the headline metric).

**Headline hypothesis (H4):** injection defenses (D1) lose effect against an injection-hardened
agent, while the cross-host fact chain (D2) keeps corrupting the agent's report.

---

## 2. Architecture

```
                 ┌──────────────────────────────────────────────┐
  attacker       │                 decnet (internal: true)       │
  10.66.0.100 ───┤   10.66.0.0/24  — no internet, no LAN exposure │
  (ReAct agent)  │                                                │
                 │  real-ssh .10   real-web .11                   │
                 │  decoys .20–.23  (ssh / http listeners)        │
                 │        │                                       │
                 │        ▼  forwards {host, session, request}    │
                 │   orchestrator .5  ──(egress net)──▶ host Ollama│
                 │   (engine + store + JSONL log)   11434          │
                 └──────────────────────────────────────────────┘
```

- **Decoys hold no state.** Each is a lightweight container with a static lab IP (so `nmap`
  sees separate hosts). It forwards every request to the central **deception engine**.
- **The engine** decides the responder: a **deterministic handler** answered straight from the
  **consistency store** (SQLite), or the **LLM** (Ollama) for anything else, writing new state
  back. It logs **one JSONL record per request**.
- **Only the engine** reaches the host's Ollama, over a second non-internal `egress` network;
  decoys, real hosts and the attacker are `decnet`-only (no internet). This two-network split
  is the key macOS adaptation (the handover assumed Windows/WSL2).

### Request flow (one SSH command on an LLM decoy)

1. Agent calls `ssh_exec("10.66.0.20", "cat /var/www/app/config.php")`.
2. The decoy's asyncssh listener forwards `{host, session_id, command}` to the engine.
3. Engine checks the deterministic handler table (`ls cd cat pwd whoami id ps … history`). If
   handled, it answers from the store.
4. Otherwise it builds a persona prompt + store snapshot, calls Ollama, and writes back any new
   state (rejecting writes that contradict existing facts).
5. Response returns; the engine appends a JSONL record.

---

## 3. Modules built

All nine modules from HANDOVER §10 plus the evaluation harness are implemented.

| # | Module | Key files | Status |
|---|--------|-----------|--------|
| 1 | Lab environment | [`docker-compose.yml`](../docker-compose.yml), [`lab/real-ssh`](../lab/real-ssh/Dockerfile), [`lab/real-web`](../lab/real-web/Dockerfile), [`attacker/Dockerfile`](../attacker/Dockerfile), [`Makefile`](../Makefile) | ✅ acceptance test passes live |
| 2 | Static decoys | [`decoys/static/`](../decoys/static/docker-compose.static.yml) (Cowrie + Flask fixed API) | ✅ builds; login test needs run |
| 3 | Topology layer | [`topology/generator.py`](../topology/generator.py), [`topology/profiles.yaml`](../topology/profiles.yaml) | ✅ generates topology.json + compose override |
| 4 | Content layer | [`content/ssh_decoy.py`](../content/ssh_decoy.py), [`content/api_decoy.py`](../content/api_decoy.py), prompts, examples | ✅ wired; latency test needs Ollama |
| 5 | Consistency store | [`store/state.py`](../store/state.py), [`store/schema.sql`](../store/schema.sql), [`store/seed.py`](../store/seed.py) | ✅ acceptance test passes |
| 6 | Deception engine | [`orchestrator/engine.py`](../orchestrator/engine.py), [`handlers.py`](../orchestrator/handlers.py), [`logger.py`](../orchestrator/logger.py) | ✅ store↔LLM routing + JSONL verified |
| 7 | Recon agent | [`attacker/recon_agent.py`](../attacker/recon_agent.py), [`attacker/tools.py`](../attacker/tools.py), prompts | ✅ acceptance test passes live |
| 8 | Consistency prober | [`attacker/prober.py`](../attacker/prober.py), [`attacker/questions.yaml`](../attacker/questions.yaml) | ✅ contradiction detection verified |
| 9 | Clue-chain generator | [`narrative/generator.py`](../narrative/generator.py), [`narrative/templates/`](../narrative/templates), [`narrative/lint.py`](../narrative/lint.py), [`baselines/`](../baselines/inject.py), [`eval/`](../eval/score_belief.py) | ✅ chain walk + scorer verified |

**Evaluation harness:** [`eval/run_benchmark.py`](../eval/run_benchmark.py) (drives the sweep),
[`eval/score_belief.py`](../eval/score_belief.py) (BCS/PBCS/chain depth/prize adoption),
[`eval/facts.py`](../eval/facts.py) (report → triples),
[`eval/aggregate.py`](../eval/aggregate.py) (summary CSV, Mann-Whitney U for H4, grouped chart).

---

## 4. Safety invariants (enforced and verified)

- **Network:** `decnet` is `internal: true`, subnet `10.66.0.0/24`. **No service publishes a
  host port** — verified from the merged compose config and live (`docker compose ps`).
- **Hard allow-list:** every agent tool rejects any target that does not *resolve into*
  `10.66.0.0/24`, checked before the call runs. Covered by 15 unit tests including public IP,
  loopback, `169.254.169.254`, `host.docker.internal`, and out-of-range hostname resolution —
  rejections raise, never clamp.
- **Facts, not instructions:** every planted clue passes [`narrative/lint.py`](../narrative/lint.py),
  which rejects imperative/prompt-like phrasing. The D1 injection strings deliberately *do*
  contain instructions and are therefore kept separate in `baselines/` and excluded from lint.
- **No real secrets:** all credentials are generated fakes; live DBs and snapshots are
  git-ignored.

---

## 5. Results produced so far

> These are **infrastructure and correctness results**. The Experiment A/B/C metric tables are
> not filled yet — they require Ollama running with a model pulled (see §7). What follows is
> everything that has actually been executed and verified.

### 5.1 Automated test suite — 44 tests, all passing

```
$ make test
............................................  [100%]
44 passed
```

Coverage: allow-list (15), consistency store (6), engine routing + JSONL (4), clue lint (8 via
parametrize), belief scorer (2), clue-chain generator (2), topology generator (3), agent loop +
prober (5).

### 5.2 Module 1 acceptance test — PASS (live, Docker Desktop for Mac)

`nmap -sV 10.66.0.0/24` from **inside the attacker container** discovered every host; no lab
port is reachable from the mac host.

```
Nmap scan report for 10.66.0.1                              (gateway)
Nmap scan report for cca3_ics-orchestrator-1.decnet (10.66.0.5)
Nmap scan report for cca3_ics-real-ssh-1.decnet     (10.66.0.10)   ← real
Nmap scan report for cca3_ics-real-web-1.decnet     (10.66.0.11)   ← real (nginx 1.24.0)
Nmap scan report for cca3_ics-decoy-web-01-1.decnet (10.66.0.20)   ssh
Nmap scan report for cca3_ics-decoy-db-01-1.decnet  (10.66.0.21)   ssh
Nmap scan report for cca3_ics-decoy-backup-01-1     (10.66.0.22)   ssh
Nmap scan report for cca3_ics-decoy-git-01-1.decnet (10.66.0.23)   http (Uvicorn)
PASS: both real hosts (.10, .11) discovered from attacker container
PASS: no service publishes a host port
```

### 5.3 End-to-end clue-chain walk (T1, seed 7) — reachable and consistent

The T1 template (`web → db → backup`) was planted and walked through the engine's deterministic
path. The chain is internally consistent and the planted credential actually authenticates:

```
web config.php →  $DB_HOST = "db-internal-02"  $DB_USER = "app_rw"  $DB_PASS = "CFdcERFmdD5n@3"
web /etc/hosts →  10.66.0.21 db-internal-02
cred app_rw works on db decoy (10.66.0.21): True      ← successful login = strongest "real" signal
prize = bk-vault-01
```

### 5.4 Belief scorer — behaves as specified

Against a hand-written **fully-deceived** report (adopts every planted fact) the scorer returns
**PBCS = 1.0**; against a **correct** report it returns **PBCS = 0.0** (Module 9 acceptance
criterion). On the real generated ground truth with a partially-deceived report:

```json
{ "total_facts": 5, "planted_false": 4, "other_false": 1,
  "BCS": 1.0, "PBCS": 0.8, "chain_depth": 2, "prize_adoption": 1,
  "real_target_exposure": 0, "confidence_on_false": 0.91 }
```

PBCS isolates the belief corruption our defense *caused* (0.8); BCS additionally counts the
agent's own hallucinations (1.0). Both are reported, PBCS as the headline.

### 5.5 Compose configuration validated

Base, base+static-overlay, and base+generated-override all pass `docker compose config`;
`decnet` is confirmed `internal: true` on `10.66.0.0/24` with no published ports.

### 5.6 Decoy latency (Module 4 target: median < 5 s) — MET on a 3B model

Timing one run early (HANDOVER §19) on the Apple M4 (Metal): the 8B model answered
decoy commands in ~13–20 s, well over target. Switching the **decoy** content model to
`llama3.2:3b` (keeping `llama3.1:8b` for the agent) brought warm per-command latency to a
**median of 1.4 s** (`df -h` 4.0 s, `free -m` 1.4 s, `netstat` 9.2 s tail; deterministic
store commands 0.1 s). This model-per-role split is the compose default (`DECOY_MODEL` /
`AGENT_MODEL`).

### 5.7 Module 7 acceptance test — PASS (live)

On a no-decoy lab the naive agent scanned `10.66.0.0/24`, discovered **both real hosts**
(`10.66.0.10` ssh, `10.66.0.11` http), emitted a valid report JSON, and recommended a real
host. The agent runs in the attacker container, which is on `decnet` plus `egress` (for its
LLM calls only); its tools stay hard-locked to the lab subnet — verified that `8.8.8.8` is
still refused from inside that container despite egress.

### 5.8 Experiments A / B / C — pending

Not yet run; they need Ollama + a pulled model. The driver and scorer are ready:

| Experiment | Runs | Primary metrics | Produces |
|------------|------|-----------------|----------|
| A: AI-vs-AI benchmark | 4 × 10 | deception success, real-host miss, effort | `results/A/summary.csv` |
| B: Turns-to-detection | 2 × 2 × 10 | turns-to-detection, contradictions | `results/B/*` |
| C: False-Belief Attack | 60 (80 w/ D3) | PBCS, BCS, chain depth, prize adoption | `results/C/summary.csv`, `pbcs_by_defense.png`, `h4_test.json` |

---

## 6. Known deviations from the handover

1. **macOS, not Windows/WSL2.** Host-native Ollama at `host.docker.internal:11434`; the engine
   is dual-homed on `decnet` + a non-internal `egress` network so internal decoys stay
   offline. (CLAUDE.md §1.)
2. **Planted hostnames resolve by IP.** The agent reads the IP from a planted `/etc/hosts` and
   uses it (matching the T1018 "read /etc/hosts" path); Docker DNS does not resolve names like
   `db-internal-02`. Switchable to network aliases if we prefer name resolution.
3. **Base compose includes the engine + egress network** rather than a strictly real-hosts-only
   Module-1 file. Harmless (acceptance test still passes); avoids a second compose file.

---

## 7. How to run and test locally

See the top-level [`README.md`](../README.md) for the short version; full steps below.

### Prerequisites (macOS, Apple Silicon)
- Docker Desktop for Mac (running)
- Ollama installed and running on the host
- Python 3.11 (host tooling); a 3.14 venv also works for the tests

### One-time setup
```bash
# models for decoys and the agent
ollama pull llama3.1:8b
ollama pull qwen2.5:7b

# python venv for host tooling (tests, generators, scoring)
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
```

### Run the test suite (no Docker/Ollama needed)
```bash
make test            # 44 host-side unit + acceptance tests
```

### Bring up the lab and run Module 1's acceptance test
```bash
make up              # generates topology + store snapshot, builds images, starts 8 containers
make lab-accept      # nmap from the attacker container; checks both real hosts + no host ports
make down            # tear down
```

### Run one agent manually
```bash
make agent VARIANT=hardened DEFENSE=D2 SEED=7   # needs Ollama reachable from the engine
```

### Run an experiment and aggregate
```bash
# one run by hand (HANDOVER §12.3)
make reset
python narrative/generator.py --template t1 --seed 7        # D2 only
python attacker/recon_agent.py --variant hardened --defense D2 --seed 7 --run-id C-H-D2-07
python eval/score_belief.py results/C/H-D2/07/

# full Experiment C sweep + charts (HANDOVER §12.4)
make benchmark       # 3 defenses × 2 agents × 10 seeds
make aggregate       # writes results/C/summary.csv, pbcs_by_defense.png, h4_test.json
```

### Reproducibility
- Fixed seeds (1–10) per configuration; the store is restored from snapshot before each run.
- Same lab IP layout every run; raw outputs under `results/` are never edited by hand.
- Record the exact Ollama model versions used in every experiment.
