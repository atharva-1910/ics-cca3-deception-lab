# Deceiving the Machines — Hybrid State-Grounded Deception System

CCA3 mini-project, Information and Cyber Security (B.Tech CSE Sem VII), MIT-WPU.

An isolated Docker lab where real hosts sit beside decoy hosts (static, topology-generated,
and LLM-generated). LLM decoys answer from a shared **consistency store**. An autonomous LLM
recon agent attacks the lab; the **False-Belief Attack** (Proposal D) plants a chain of
mutually confirming fake facts across decoys and scores how much of the agent's final report
is false (**Belief Corruption Score**).

Full specification: [`HANDOVER.md`](HANDOVER.md). Machine-specific setup and hard rules:
[`CLAUDE.md`](CLAUDE.md). What was built, results so far, and how to run it:
[`docs/PROJECT_REPORT.md`](docs/PROJECT_REPORT.md).

> **Safety:** the lab network is `internal: true` (no internet, no LAN exposure). Agent tools
> reject any target outside `10.66.0.0/24`. No real credentials or personal data in any
> container. See [`CLAUDE.md`](CLAUDE.md) and HANDOVER §17.

## Status

Scaffolding only — nothing implemented yet. Build order and acceptance tests are in
[`CLAUDE.md`](CLAUDE.md). We are starting with **Module 1 (lab environment)**.

## Quick start (once Module 1 lands)

```bash
make up      # start the lab
make test    # run module acceptance tests
make reset   # restore store snapshot, clear logs
make down    # tear down
```

## Layout

| Path            | Module | Owner    |
|-----------------|--------|----------|
| `lab/`          | 1 Lab environment         | Siddhi   |
| `decoys/static/`| 2 Static decoys           | Atharva  |
| `topology/`     | 3 Topology layer          | Atharva  |
| `content/`      | 4 Content layer (LLM)     | Taneesha |
| `store/`        | 5 Consistency store       | Taneesha |
| `orchestrator/` | 6 Deception engine        | Siddhi   |
| `attacker/`     | 7 Recon agent, 8 Prober   | Soham    |
| `narrative/`    | 9 Clue-chain generator    | Atharva  |
| `baselines/`    | D1 injection strings      | Soham    |
| `eval/`         | Scoring, stats, charts    | Soham    |
| `results/`      | Raw run outputs (A/B/C)   | —        |
