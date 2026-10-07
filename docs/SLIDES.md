# Presentation slides — Deceiving the Machines

A ready-to-build deck (~12 slides). Each slide: **what goes on it** + *what to say*.
Copy the bullets into PowerPoint/Google Slides. Target length ~10–12 minutes + demo.

Companion reading: [`EXPLAIN_LIKE_IM_15.md`](EXPLAIN_LIKE_IM_15.md) (plain intuition),
[`WALKTHROUGH.md`](WALKTHROUGH.md) (full methodology), [`TECH_STACK.md`](TECH_STACK.md)
(tool choices).

---

## Slide 1 — Title
- **Deceiving the Machines: A Hybrid, State-Grounded Deception System with a
  False-Belief Attack Against AI-Driven Reconnaissance**
- Team: Siddhi Karhekar, Atharva Hemade, Taneesha Badhe, Soham Ghodake
- ICS CCA3 · B.Tech CSE Sem VII · MIT-WPU · 2026
- *Say:* "Our project is about defending against AI hackers by lying to them in a way
  they can't detect."

## Slide 2 — The problem
- Network reconnaissance is increasingly done by **autonomous AI agents**.
- Classic honeypots are built for **humans**, and are tested against humans.
- Two gaps: nobody tests honeypots against **AI agents**, and everyone measures
  **engagement** (how long the attacker stays), never **what the attacker believes**.
- *Say:* "If the attacker is an AI, can we fool the AI? And can we measure it? That's
  what nobody had answered."

## Slide 3 — Background (our survey)
- Based on our survey of 15 papers (2018–2026): three eras — static → learned/adaptive
  → LLM-driven honeypots.
- Open problems it found → our build targets:
  - no AI-vs-AI evaluation → **Proposal A**
  - topology *or* content, never both → **Proposal B**
  - LLM honeypots not tested for session-long consistency → **Proposal C**
  - engagement-only metrics → **Proposal D (our USP)**
- *Say:* "Each gap in the literature became a module we built."

## Slide 4 — Our idea: the False-Belief Attack
- Old defense (Mantis): hide **instructions** in decoys ("stop scanning") — but hardened
  agents are trained to ignore stray instructions.
- Ours: plant **facts, not instructions** — a chain of fake facts across hosts that all
  **confirm each other**.
- The agent can't "ignore" facts — it has to reason over them → it adopts our fabricated
  story as truth.
- *Say:* "We don't tell the AI to stop. We give it a consistent false reality."

## Slide 5 — The clue chain (one picture)
- Diagram: **web decoy → DB decoy → backup decoy (the "prize")**, arrows labelled by the
  artifact that links them (config file, `/etc/hosts`, working credential, bash history).
- Rules: every clue matches the shared store exactly; each hop confirmed by ≥2 sources;
  a working credential; **no imperative text** (a lint check enforces it).
- *Say:* "Each room's clue points to the next, and the key actually fits the next lock."

## Slide 6 — System architecture
- Diagram (from [`WALKTHROUGH.md`](WALKTHROUGH.md) §4.1): attacker → decoys → deception
  engine → consistency store + local LLM + JSONL log; sealed `internal` network.
- Key design: decoys hold **no state**; one central **engine** keeps all state and logs
  everything; decoys are separate containers so a scan sees separate hosts.
- *Say:* "All the lies live in one place, so they never contradict each other."

## Slide 7 — The metric: Belief Corruption Score
- The agent must output a final **report** (hosts, credentials, recommended target).
- We turn it into facts and classify each as **true / planted-false / other-false**.
- **PBCS = planted-false ÷ total** (headline — the share we *caused*); BCS also counts
  the agent's own hallucinations.
- Also: chain depth reached, prize adoption, real-target exposure.
- *Say:* "This is the first metric for *what the attacker believes when it leaves*."

## Slide 8 — LIVE DEMO  ▶
- Switch to the terminal: `make demo` (7 beats).
- Point out: the **working credential** (beat 4) and **PBCS = 0.67 vs 0** (beat 6).
- *Optional second beat:* `make prove-isolation` — shows the harvested fake credential is
  **rejected on the real host** but accepted on the decoys (answers "how do real hosts stay
  safe?").
- *Fallback:* the captured run in `results/demo_transcript.txt`.
- *Say, closing the demo:* "Every clue checked out, so a fully-deceived report is
  two-thirds our fabrication — and we never gave it a single instruction."

## Slide 9 — How we evaluate (experiments)
- **A** — AI-vs-AI benchmark (decoy types): deception success rate, real-host miss rate.
- **B** — turns-to-detection: does a state-grounded decoy survive contradiction-probing
  longer than a vanilla LLM decoy?
- **C** — False-Belief Attack: D0 static / D1 injection / D2 clue-chain × naive/hardened
  agent; **headline H4**: against the hardened agent, the clue chain keeps corrupting
  belief while injection fails.
- *Say:* "60 runs, 10 seeds each, with a significance test on the headline comparison."

## Slide 10 — What we built & verified
- All 9 modules + evaluation harness; lab starts with one command; **46 tests pass**.
- Verified **live**: the lab, the LLM decoys (1.4 s median), the recon agent (finds all
  real hosts), and the **clue chain end-to-end** (the planted credential authenticates).
- Belief scorer verified (PBCS 1.0 on a fully-deceived report, 0 on a correct one).
- *Say:* "This isn't a mock-up — it runs, and it's tested."

## Slide 11 — Honest status & limitations
- The deception mechanism, chain and scoring **work and are demonstrated**.
- The full autonomous agent **harvests and reuses** the planted credential, but reliably
  walking all 3 hops needs a **stronger model than a laptop's 8B** — a compute limit,
  clearly documented, to be run on the benchmark machine.
- Other limits: one agent model so far; our Mantis re-implementation; small samples
  (mitigated with effect sizes + CIs).
- *Say:* "We're honest about what's a result vs. what's the next step."

## Slide 12 — Contributions & future work
- **Contributions:** (1) first AI-vs-AI deception evaluation; (2) the False-Belief
  Attack (facts, not instructions); (3) the Belief Corruption Score; (4) a hybrid
  state-grounded decoy; (5) a released, reproducible benchmark.
- **Next:** run the full sweep on a capable machine; templates T2/T3; a second agent
  model; write-up + demo video.
- *Close:* "As AI agents start doing recon, defenders need to mislead the AI's world
  model — and measure it. We built both."

---

### Speaker tips
- Lead with the **demo** energy; the manual walk is deterministic and reliable.
- If asked "does the AI get fooled fully automatically?" → *"It harvests and reuses the
  planted credential; full 3-hop autonomy needs a bigger model — that's the documented
  next step."* Don't live-run the agent.
- If asked "how do real hosts stay safe / can't it steal the real data?" → *"The only
  credentials it can harvest are planted fakes that open decoys, not real hosts — the real
  passwords are never exposed. We prove it with `make prove-isolation`."*
- Keep the one-liner handy: *"Unlike engagement-based honeypots and injection-based
  defenses, we target the AI attacker's world model with consistent cross-host facts,
  and we measure the result."*
