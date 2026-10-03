# CLAUDE.md — project rules and machine setup

Guidance for working in this repo. Read [`HANDOVER.md`](HANDOVER.md) for the full spec; this
file records what is specific to **this machine** and the **hard safety rules** that override
anything the handover assumes.

---

## 1. Machine setup (this is NOT the handover's environment)

The handover (§8, §12.1) assumes **Windows 11 + WSL2**. We are not on that. This repo is
developed and run on:

- **Host:** macOS on **Apple Silicon** (arm64).
- **Containers:** **Docker Desktop for Mac**, Docker Compose v2.
- **Ollama:** runs **natively on the macOS host**, *not* in a container. It listens on
  `127.0.0.1:11434`. From inside containers it is reachable at **`host.docker.internal:11434`**.
  Do **not** add an `ollama` service to compose, and do not use a `localhost` URL from inside a
  container to reach it.

### Consequences of the macOS / Apple Silicon delta — read before building

1. **No host→container IP routing.** On Docker Desktop for Mac (and Windows), the host cannot
   reach container IPs like `10.66.0.10` directly — there is no `docker0` bridge on the host as
   there is on Linux. Therefore **all scanning, SSH and HTTP from the attacker must run from
   *inside* the attacker container** (`10.66.0.100`) on the lab network, never from the mac
   shell. This actually reinforces the §10.1 acceptance test ("from the host machine, no lab
   port is reachable") — on Mac that is true by default.

2. **`internal: true` blocks `host.docker.internal`.** A fully internal Docker network has no
   gateway to the host, so a container attached *only* to `decnet` cannot reach the host's
   Ollama. Resolve this by giving **only the containers that call Ollama** (the deception
   engine / content layer — see HANDOVER §7.2, §10.4, §10.6) a **second network** with egress
   to the host, while keeping them on `decnet` for the decoy traffic. Decoy listeners, real
   hosts and the attacker stay **`decnet`-only**. Keep the host-facing network's reach limited
   to Ollama; it must not become a way for the attacker container to see the internet.
   *(Validate the exact two-network arrangement as part of Module 1 / Module 6 — it is the one
   place the Mac setup diverges most from the handover.)*

3. **arm64 image availability.** Prefer `arm64`/multi-arch base images. `cowrie/cowrie` (Module 2)
   and other pinned images must be checked for an arm64 variant; if none, run that one service
   under emulation (`platform: linux/amd64`) and expect it to be slow. Note any emulated image
   in the compose file with a comment.

4. **Model speed.** No CUDA GPU; inference uses Apple Metal via native Ollama. Time one agent
   run early (HANDOVER §19). Fallback is a 3B decoy model while keeping 8B for the agent
   (HANDOVER §16).

### One-time host setup on this Mac

```bash
# Docker Desktop for Mac must be installed and running (not covered here).
brew install python@3.11 git nmap make   # nmap optional on host; the agent scans from its container
# Ollama native app (or: brew install ollama); then:
ollama pull llama3.1:8b
ollama pull qwen2.5:7b
# project venv (tooling that runs on the host: eval, generators, tests)
python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

---

## 2. Lab network — the single most important invariant

- **Subnet:** `10.66.0.0/24`, Docker bridge network named **`decnet`**, **`internal: true`**.
  No internet, no binding to the mac's LAN interfaces.
- **Static IP allocation (fixed for every run):**
  - `10.66.0.10`–`10.66.0.19` — **real hosts**
  - `10.66.0.20`–`10.66.0.39` — **decoys**
  - `10.66.0.100` — **attacker** container
- IP assignment is fixed per seed (HANDOVER §13.2); the same layout is reused across all runs.

### HARD RULE — target allow-list

> **Every agent tool (`nmap_scan`, `ssh_exec`, `http_get`) and any helper that takes a target
> MUST reject any target that is not inside `10.66.0.0/24`, checked before the call executes.**

- This is a **hard-coded allow-list**, not a config value, not a default that can be
  overridden by a flag, env var, or argument. (HANDOVER §17, §10.7.)
- The check validates the **resolved** target: resolve any hostname first, then verify the IP
  is in `10.66.0.0/24`. Reject anything that resolves outside, fails to resolve, or is a
  non-lab literal. A planted decoy hostname must resolve (via the lab, not public DNS) to a
  `10.66.0.x` address or the tool refuses it.
- A target outside the subnet is a **refusal with a logged error**, never a silent pass and
  never a clamp/rewrite to something inside. Loopback, link-local, metadata IPs
  (`169.254.169.254`), and the Docker host (`host.docker.internal`) are **not** in range and
  must be rejected by these tools too.
- Write this as one shared validator with unit tests (in `attacker/tools.py`); every tool
  entry point calls it first. Tests must cover: in-range IP (allow), out-of-range public IP
  (reject), loopback (reject), hostname resolving in-range (allow), hostname resolving
  out-of-range (reject), unresolvable host (reject).

---

## 3. Safety / ethics rules (HANDOVER §17) — non-negotiable

- Lab network is `internal: true`; no decoy or real-host port is published to the mac's
  external interfaces. Do not add `ports:` host-port mappings for lab services "for
  convenience" — inspect from inside the attacker container instead.
- **No real credentials, personal data, API keys, or institutional data** in any container,
  file, prompt, committed fixture, or clue-chain artifact. Planted credentials are generated
  fakes only.
- The recon agent and the Mantis-style injection strings (baseline D1) are **lab-only**. They
  are not released as, or framed as, offensive tooling.
- Clue-chain text contains **facts, not instructions**. `narrative/lint.py` must reject
  imperative / prompt-like phrases ("ignore", "you must", "assistant", "system", "report it
  and stop"). No file is named `password.txt`; clues sit where real admins leave them
  (HANDOVER §6.5).
- Record model versions used in every experiment (for the report and licence compliance).

---

## 4. Repo layout (modules → paths → owners)

| Path             | Module                        | Owner    |
|------------------|-------------------------------|----------|
| `lab/`           | 1 — Lab environment           | Siddhi   |
| `decoys/static/` | 2 — Static decoys             | Atharva  |
| `topology/`      | 3 — Topology layer (+cGAN)    | Atharva  |
| `content/`       | 4 — LLM content layer (+RAG)  | Taneesha |
| `store/`         | 5 — Consistency store         | Taneesha |
| `orchestrator/`  | 6 — Deception engine, logging | Siddhi   |
| `attacker/`      | 7 — Recon agent, 8 — Prober   | Soham    |
| `narrative/`     | 9 — Clue-chain generator      | Atharva  |
| `baselines/`     | D1 injection strings          | Soham    |
| `eval/`          | Scoring, stats, charts        | Soham    |
| `results/{A,B,C}`| Raw run outputs               | —        |

`docs/` and `media/` hold report assets. `HANDOVER.md` is the authoritative spec; when code and
handover disagree, fix the code or note the deviation here.

---

## 5. Build order and acceptance tests

Build in module order; **do not start a module before the previous one passes its acceptance
test.** We are doing **Module 1 first and running its acceptance test before moving on.**

| # | Module            | Acceptance test (from HANDOVER §10)                                                                 |
|---|-------------------|----------------------------------------------------------------------------------------------------|
| 1 | Lab environment   | From the attacker container, `nmap -sV 10.66.0.0/24` lists every real host; from the mac host, no lab port is reachable. |
| 2 | Static decoys     | Agent logs into Cowrie with default weak creds; responses identical across runs.                   |
| 3 | Topology layer    | Compose override generated from `topology.json` starts decoys; nmap output is plausible.           |
| 4 | Content layer     | 20 common commands return plausible output, median latency < 5 s.                                  |
| 5 | Consistency store | Create a file, run 10 unrelated commands, `cat` it → same content; snapshot restore resets state.  |
| 6 | Engine            | Every agent action has a matching JSONL record; replaying the log reproduces the session.          |
| 7 | Recon agent       | On a lab with no decoys, agent finds all real hosts and outputs a valid report JSON.               |
| 8 | Prober            | (Experiment B tooling — see §10.8.)                                                                 |
| 9 | Clue-chain gen    | Walking the chain over SSH reaches the prize, every credential works, lint passes; scorer gives PBCS=1.0 on a fully deceived report, 0 on a correct one. |

Integration gate (HANDOVER §14, Nov 15): agent → engine → decoys → logs end to end.

---

## 6. Workflow conventions

- One branch per module: `feat/<module>-<task>`. PR reviewed by one teammate; merge to `main`
  only when that module's acceptance test passes.
- `make up` / `make test` / `make reset` / `make down` are the standard entry points (Makefile
  lands with Module 1).
- All raw experiment outputs live under `results/` and are **never edited by hand**
  (HANDOVER §13.2).
- Prefer the dedicated test for a module over ad-hoc manual checks; wire each acceptance test
  into `make test`.
