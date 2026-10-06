# Tech stack — what we used and why

Every tool, the job it does, and *why it* (and not the obvious alternative). Useful for
the viva/Q&A: examiners often ask "why this and not X?"

---

## At a glance

| Layer | Tool | Why we picked it |
|-------|------|------------------|
| Isolation / hosts | **Docker + Docker Compose** | Each decoy is its own container with its own IP, so a scan sees *separate machines*; an `internal` network gives a sealed, no-internet lab reproducibly |
| Language | **Python 3.11** | One language for every part (decoys, engine, agent, scoring); huge security/ML ecosystem |
| Local AI | **Ollama** + `llama3.1:8b`, `llama3.2:3b` | Runs models on the laptop — free, offline, private (no data leaves the machine); easy model swapping |
| Fake SSH server | **asyncssh** | Lets us write a *custom* SSH server that forwards every command to our engine, instead of running a real shell |
| Fake HTTP/API server | **FastAPI + uvicorn** | Tiny async web server with a catch-all route — answers any URL the attacker probes |
| Shared memory | **SQLite** (built into Python) | One file = the single source of truth for all fakes; trivially snapshot/restore between runs; no server to manage |
| Attacker tools | **python-nmap, paramiko, requests** | Standard libraries for scanning, SSH, and HTTP — the three things a recon agent does |
| Attacker brain | **plain-Python ReAct loop** | A hand-written think→act→observe loop we can fully log and control |
| Static baseline decoy | **Cowrie** | A well-known real honeypot — our "no-tricks" comparison point |
| Scoring / stats / charts | **pandas, scipy, matplotlib** | Standard data-science stack for metrics, significance tests, and figures |
| Tests | **pytest** | 46 fast unit tests guard the safety allow-list, the store, and the scorer |
| Automation | **Make** | `make up / test / demo / reset` — one word per task |

---

## The decisions that need defending

### Why Docker with an `internal` network (not VMs, not just processes)?
- **Separate IPs:** `nmap` must see each decoy as a distinct host (`10.66.0.20`, `.21`,
  …). Containers give that cheaply; plain processes on one machine would share an IP.
- **Isolation by design:** `internal: true` means the lab has **no route to the
  internet or the campus LAN** — the safety requirement (HANDOVER §17) is enforced by
  the network itself, not by discipline.
- **Reproducible:** one `docker compose up` rebuilds the exact same lab on any machine.
- VMs would do the same but are far heavier (GBs and minutes each).

### Why a *local* LLM (Ollama) instead of the OpenAI/Anthropic API?
- **Cost:** the experiment is 60+ runs × many LLM calls — a hosted API would cost real
  money; local inference is free.
- **Offline & private:** fits the sealed-lab rule; nothing leaves the laptop.
- **Control:** we pin exact model versions for reproducibility and licence compliance.
- Trade-off: laptops are slower than the cloud — hence the model split below.

### Why two models — `llama3.2:3b` for decoys, `llama3.1:8b` for the agent?
- Decoys answer **many** commands and must feel instant; the 3B model gives a **~1.4 s
  median** reply (under our 5 s target).
- The attacker's reasoning is harder, so it gets the stronger **8B** model.
- This "small for volume, large for brains" split is the standard latency-vs-quality
  trade-off (and HANDOVER §16's fallback made concrete).

### Why SQLite for the consistency store (not Postgres/MySQL/Redis)?
- The whole point is **one source of truth that never contradicts itself**. SQLite is a
  single file — easy to **snapshot before a run and restore after** (our reset).
- No separate database server to run inside the lab.
- The data is small; a heavyweight DB would be pure overhead.

### Why a custom `asyncssh` server (not a real shell, not Cowrie everywhere)?
- A **real** shell on a decoy would actually execute the attacker's commands — unsafe
  and uncontrolled. Our server **forwards** each command to the engine, which decides
  the answer from the store or the LLM. We control and log everything.
- Cowrie is great but fixed; we need decoys whose answers come from our shared store so
  the clue chain stays consistent. (We still use Cowrie as the **static baseline** to
  compare against.)

### Why a plain-Python ReAct agent (not LangChain / AutoGPT)?
- We need to **log every token and every tool call** and enforce a hard **target
  allow-list** before each action. A hand-written loop is easier to audit and control
  than a heavy framework, and removes a big dependency. (LangChain was considered and
  rejected for this reason — HANDOVER §8.)

### Why FastAPI for both the engine and the API decoy?
- Async (handles the LLM's slow replies without blocking), a trivial **catch-all
  route** for the API decoy, and automatic request validation for the engine's
  `/respond` and `/auth` endpoints.

### The one macOS-specific choice
Ollama runs **natively on the Mac**, not in a container, reachable from containers at
`host.docker.internal:11434`. Because our lab network is sealed (`internal: true`), only
the **engine** (and, for its own reasoning, the attacker) is also attached to a second
network that can reach the host — the decoys stay fully offline. (Details in
[`CLAUDE.md`](../CLAUDE.md).)

---

## How the pieces talk

```
attacker (nmap/paramiko/requests)  ──►  decoy (asyncssh / FastAPI)
                                             │  forwards the request
                                             ▼
                                   deception engine (FastAPI)
                                     ├─ consistency store (SQLite)  ← deterministic answers
                                     ├─ local LLM (Ollama)          ← improvised answers
                                     └─ JSONL log                   ← every interaction
```
