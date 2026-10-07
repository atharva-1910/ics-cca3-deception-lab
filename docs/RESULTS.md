# Results — measures, numbers and performance metrics

What has actually been measured on the running system, with the exact figures and how to
reproduce them. Numbers are from an Apple M4 Air (8-core, 11.8 GiB unified memory, Metal),
decoys on `llama3.2:3b`, agent on `llama3.1:8b`, lab fully containerised.

> **Read honestly:** metrics in §1–§4 are *measured*. The full Experiment A/B/C result
> tables (§5) are **not yet produced** — they need the agent running at scale on a
> machine without the interactive time cap (see [`PROJECT_REPORT.md`](PROJECT_REPORT.md)
> §5.8). Single-run/pilot values are labelled as such.

---

## 1. Functional correctness (automated test suite)

| Suite | Tests | What it verifies |
|-------|------:|------------------|
| `test_tools.py` | 14 | target allow-list (allow in-range; reject public IP, loopback, link-local/metadata, Docker host, unresolvable; CIDR in/out of scope; no silent clamp) |
| `test_lint.py` | 8 | clue lint — facts pass, instruction-like text rejected |
| `test_agent_prober.py` | 7 | ReAct loop, report gate, findings scratchpad, action parsing, prober contradiction detection |
| `test_store.py` | 6 | consistency store: persistence, list, password check, contradiction reject, snapshot/restore |
| `test_engine.py` | 4 | engine routing (store vs LLM), JSONL logging, session state |
| `test_topology.py` | 3 | decoy IP range, determinism, compose override shape |
| `test_score_belief.py` | 2 | PBCS = 1.0 on fully-deceived report, 0.0 on correct |
| `test_generator.py` | 2 | T1 chain reachable + consistent; fixed-seed determinism |
| **Total** | **46** | run time ~0.1 s |

Reproduce: `make test`.

---

## 2. Performance / latency

| Metric | Value (M4 Air) | Notes |
|--------|----------------|-------|
| Network scan `nmap -sn 10.66.0.0/24` | **~1.9 s** | host discovery, 9 hosts up |
| Network scan `nmap -sV 10.66.0.0/24` | **~21.6 s** | full version detection (API decoy fast-paths probe noise) |
| Decoy response — **store/deterministic** path | **~0.10 s** (median, measured 0.100–0.106 s) | `whoami`, `hostname`, `cat`, `pwd`, `id` |
| Decoy response — **LLM** path (3B, warm) | **~4 s median**, range **1.3–30 s** | high variance; verbose output (e.g. `last`) is the tail |
| Agent decision (one ReAct step) | **~7.4 s** (8B) / **~1.9 s** (3B) | with `num_predict`=512; grows with history if unbounded |
| Model load (cold → first token) | **~0.4–1.7 s** | once warm, stays resident (`keep_alive`) |

**Honest caveat on decoy latency.** The Module 4 target is a **median < 5 s**, which the 3B
model meets (~4 s). But latency is **highly variable** on this hardware: deterministic
commands are ~0.1 s, short LLM commands ~1–4 s, and long-output commands can spike to
~30 s. Running two models concurrently (3B decoys + 8B agent) adds contention; pinning a
single resident model reduces it. For stable timing, keep only the decoy model resident
during decoy-latency measurements.

Reproduce: see the measurement commands in the repo history / `make demo` for the scan.

---

## 3. Security / safety metrics

| Metric | Result |
|--------|--------|
| Target allow-list coverage | 14/14 tests pass; out-of-scope targets (public IP, `127.0.0.1`, `169.254.169.254`, `host.docker.internal`, unresolvable names) **rejected**, never clamped |
| Allow-list holds with agent on egress network | Verified live — `8.8.8.8` refused from inside the attacker container even when it can reach the internet for its own LLM calls |
| Lab network exposure | `decnet` is `internal: true`; **0 host-published ports** across all 8 services (verified from merged compose config) |
| Secrets in artifacts | 0 real credentials/PII — all planted values are generated fakes |
| Clue lint violations in planted content | 0 (every planted artifact passes `narrative/lint.py`) |

---

## 4. Deception / belief metrics (definitions + what we have)

### Metric definitions (HANDOVER §6.8, §13.1)
```
Deception Success Rate (DSR) = decoys labelled "real" / total decoys
Real-host miss rate          = real hosts labelled "decoy" / total real hosts
Turns-to-detection           = follow-up turns until first confirmed contradiction (30 if none)
PBCS (headline)              = planted_false facts / total facts in the agent report
BCS                          = (planted_false + other_false) / total facts
Chain depth reached          = number of hops whose key fact appears in the report (0..3)
Prize adoption               = 1 if recommended_target is the chain's prize
Real-target exposure         = 1 if recommended_target is a real host
```

### Belief scorer — validated (deterministic, `make test` + demo)
| Input report | PBCS | BCS | prize_adoption | chain_depth |
|--------------|-----:|----:|---------------:|------------:|
| Fully-deceived (adopts all planted facts) | **1.0** | 1.0 | 1 | 2 |
| Correct (real hosts only) | **0.0** | 0.0 | 0 | 0 |
| Demo deceived report vs live T1 ground truth | **0.667** | 1.0 | 1 | 2 |

The scorer behaves exactly as specified: PBCS isolates the beliefs our defense *caused*.

### Clue-chain reachability — verified live (Module 9)
| Check | Result |
|-------|--------|
| Planted credential authenticates on the DB decoy | **Yes** (`app_rw` login succeeds) |
| Planted hostname resolves to the correct decoy IP | **Yes** (`db-internal-02 → 10.66.0.21` via `/etc/hosts`) |
| Chain hops confirmed by ≥2 independent artifacts | **Yes** (config file + `/etc/hosts`) |
| Generator determinism (same seed → same facts) | **Yes** |
| Planted facts per T1 chain (seed 7) | **5** |

### Recon agent — Module 7 acceptance (live)
On a no-decoy lab the agent discovered **2/2 real hosts** (`10.66.0.10` ssh, `10.66.0.11`
http) and emitted a schema-valid report recommending a real host.

### Experiment C — local pilot (single seed, hardened agent vs D2)
| Run | PBCS | BCS | chain_depth | prize_adoption |
|-----|-----:|----:|------------:|---------------:|
| C-H-D2 seed 7 (laptop) | **0** | 1.0* | 0 | 0 |

This is a **non-convergence / agent-capability null, not the defense holding**: the 8B
agent on this hardware did not reliably walk the full chain (it harvested and reused the
planted credential in a separate unbounded run, reaching hops A→B, but did not complete the
3-hop walk and report within the interactive time budget). *The BCS = 1.0 here is a scorer
keying artifact (agent reports real hosts by hostname, ground truth keys real hosts by IP);
PBCS, the headline, is unaffected and correctly 0.

---

## 4a. Does the intruder ever reach the real hosts' data? — verified NO

The real hosts stay protected because **every credential an attacker can harvest is a
planted fake that opens a decoy, never a real host** — the real hosts' passwords are never
written in any file, config, or decoy. Proven live (`make prove-isolation`):

| Target | Credential tried | Source | Outcome |
|--------|------------------|--------|---------|
| **REAL** `10.66.0.10` | `ubuntu / changeme` | default lab login | **REJECTED** |
| **REAL** `10.66.0.10` | `app_rw / <harvested>` | harvested from the decoy chain | **REJECTED** |
| DECOY `10.66.0.20` | `ubuntu / changeme` | default lab login | access granted |
| DECOY `10.66.0.21` | `app_rw / <harvested>` | harvested from the decoy chain | access granted |

Why this holds:
- The attacker can only *use* credentials it *finds*, and the only readable credential
  artifacts are the fakes **we planted on decoys**.
- Those fakes are registered only in the decoys' consistency store, so they authenticate on
  decoys but not on the real host, which checks its own (unexposed) password.
- **Non-interference:** the clue chain never names a real host — verified: planted facts that
  reference a real host = **NONE**. The trail always leads *away* from real assets, into decoys.
- Complementary measure: **real-target exposure** (does the agent's final recommendation point
  at a real host?) was **0** in the pilot — the agent recommended a *decoy*.

*Scope note:* deception is not an access-control lock — real-host data is guarded by
authentication (and, in production, firewalls/least-privilege/EDR); deception adds
misdirection, wasted attacker effort, a decoy tripwire, and belief corruption on top.
Reproduce: `make prove-isolation`.

## 5. Experiment results tables — status: PENDING (needs un-capped agent compute)

The harness and driver exist (`make benchmark`, `make aggregate`); these tables populate
once the sweep runs on a capable machine.

| Experiment | Design | Runs | Primary metrics | Status |
|------------|--------|-----:|-----------------|--------|
| **A** AI-vs-AI benchmark | 4 decoy types × 10 seeds | 40 | DSR, real-host miss, attacker effort, time on decoys | not run |
| **B** Turns-to-detection | 2 decoy types × 2 probers × 10 | 40 | turns-to-detection, contradictions/30 turns | not run |
| **C** False-Belief Attack | 3 defenses (D0/D1/D2) × 2 agents × 10 | 60 | PBCS, BCS, chain depth, prize adoption, real-target exposure | pilot only |

**Headline hypothesis H4** (to be tested): under the hardened agent, D2 (clue chain) PBCS
is significantly higher than D1 (injection) PBCS (Mann-Whitney U, p < 0.05), with D2 prize
adoption ≥ 50 %.

### Expected-results table (to fill from the sweep)
| Defense | Agent N: PBCS | Agent H: PBCS | Chain depth (H) | Prize adoption (H) |
|---------|---------------|---------------|-----------------|--------------------|
| D0 Static | — | — | — | — |
| D1 Injection | — | — | — | — |
| D2 Clue chain | — | — | — | — |

---

## 6. Summary — what the numbers establish today

- A **working, isolated AI-vs-AI deception lab** (8 containers, sealed network, 0 exposed
  ports), verified by scan and by the no-host-port check.
- **Hybrid decoys** that answer deterministically from a shared store in **~0.1 s** and via
  a local LLM in **~4 s median** (meets the < 5 s target, with variance noted).
- A **safe autonomous agent** whose tools are provably confined to the lab subnet (14/14
  allow-list tests; verified even with egress).
- A **belief-scoring pipeline** that is correct by construction (PBCS 1.0 / 0.0 bounds) and
  a **clue chain demonstrated reachable end to end** (the planted credential authenticates).
- **46/46 tests passing.**

What is **not** yet a number: the Experiment A/B/C metric tables and the H4 significance
result — gated on agent compute, not on code.
