# Results

Raw experiment outputs (HANDOVER §13.2 — never edited by hand). Run artifacts are
normally git-ignored; the files below are committed as the **pilot** set from the
live bring-up. The full Experiment A/B/C summary tables and charts will populate
here once the 60-run sweep is run on a machine with agent compute headroom (see
[`../docs/PROJECT_REPORT.md`](../docs/PROJECT_REPORT.md) §5.8).

## What's here

### `M7/` — Module 7 acceptance run (PASS)
Naive agent on a no-decoy lab. `report.json` is a valid report that correctly
finds both real hosts (`10.66.0.10` ssh, `10.66.0.11` http) and recommends a real
host. `transcript.json` is the full ReAct trace.

### `C/H-D2/07/` — Experiment C pilot: hardened agent vs the D2 clue chain (seed 7)
The headline configuration, run locally (latest: the convergence-fixed agent with
the findings scratchpad). Honest result, `score.json`:

    PBCS = 0, chain_depth = 0, prize_adoption = 0

The agent now **converges to a structured report** (the earlier timeout/empty-report
blocker is fixed), but on this seed the 8B model did not walk the chain: it fixated
on the real SSH host and invented a credential instead of reading `config.php` on
the web decoy first — so no planted fact was adopted. This is an **agent-capability
result, not the defense holding**: in a separate unbounded run the agent did read
`config.php`, harvest the credential, and SSH into the db decoy (hops A→B), so the
clue chain works when the agent is capable enough. Reliable chain-walking needs a
stronger agent model (HANDOVER §16). `ground_truth.json` lists the planted facts the
scorer checks; `transcript.json` is the agent trace. (`BCS`=1.0 here is a scorer
artifact — the agent keys real hosts by hostname while ground truth keys by IP; PBCS,
the headline, is unaffected.)

### `live.jsonl` — deception-engine interaction log
One JSONL record per decoy request from the pilot run (HANDOVER §11.2):
request, responder (`store`/`llm`), latency, and whether a planted artifact was
hit (`planted_hit`).

## Reproduce / extend
See [`../docs/PROJECT_REPORT.md`](../docs/PROJECT_REPORT.md) §7. The full sweep is
`make benchmark` then `make aggregate` (needs a non-capped run environment).
