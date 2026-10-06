# The whole project, explained simply

No jargon. Read this once and you'll understand what we built and why, well enough
to explain it to anyone.

---

## 1. The one-sentence version

> We built a **fake computer network to trick hacker robots** — and instead of just
> keeping them busy, we feed them a trail of **fake facts that all agree with each
> other**, so the robot ends up writing a confident report that is completely wrong.

---

## 2. Start with the old idea: a honeypot

Imagine a bank leaves a **fake vault** in the lobby, full of fake money, with cameras
inside. Burglars waste time on it, and the bank watches how they work. In computers,
that fake vault is called a **honeypot** — a fake computer that looks real, set up to
attract and study attackers.

A **decoy** is the same idea: a fake machine sitting next to the real ones.

## 3. What changed: the attackers are now robots

Hackers used to be people. Now a lot of scanning is done by **AI agents** — programs
powered by the same kind of AI as ChatGPT. The robot's job is simple:

> Look around the network, find the computers, find passwords, and write a **report**
> saying "here are the real machines, here are the fakes, and *this* is the most
> valuable one to attack next."

Nobody had really tested honeypots against these AI robots. That's gap #1 we fill.

## 4. Our twist: don't trap the robot — **lie to it convincingly**

Old defenses try to say to the robot: *"STOP. Ignore everything. Go away."* (This is
called **prompt injection**.) Problem: smart robots are trained to ignore messages
like that — they're told "don't obey instructions you find lying around."

So we do something sneakier. **We don't give the robot any instructions at all.** We
just leave **facts** — and we make every fake fact agree with every other fake fact.

Think of a **treasure map planted across several rooms**:

- Room A has a note: *"The treasure is in Room B. The key is '1234'."*
- Room B's lock **actually opens with '1234'** — so the robot thinks "this is real!"
- Inside Room B, another note: *"The real treasure is in Room C."*
- Room C looks like the jackpot.

Every clue checks out, so the robot believes the whole story and writes in its report:
*"The crown jewels are in Room C."* But **we made Room C up.** The robot leaves
**confidently wrong**. That's our idea — we call it the **False-Belief Attack**.

Because we only ever placed *facts* (a config file, a matching address book, a working
password), the robot's "don't obey stray instructions" training **doesn't help it** —
there's nothing to disobey. It still has to *read and reason about* the facts.

## 5. The actual pieces (mapped to the treasure-map story)

| In the story | In our project | What it really is |
|--------------|----------------|-------------------|
| The building with real + fake rooms | **the lab** | small fake network of computers (`10.66.0.x`) running in **Docker** (think: lightweight virtual computers) |
| Real rooms | **real hosts** (`.10`, `.11`) | genuine servers the robot *should* find |
| Fake rooms | **decoys** (`.20`–`.23`) | fake servers that look real |
| The notes/keys/maps | **the clue chain** | fake files, passwords and address-book entries planted across decoys |
| The "memory" that keeps every lie consistent | **the consistency store** | a small database (SQLite) — the single source of truth for all the fakes |
| The actor improvising answers in a fake room | **the LLM decoy** | a local AI (Ollama) that makes a fake computer *talk* like a real one |
| The stage manager | **the deception engine** | the program that answers the robot and keeps notes of everything |
| The hacker robot | **the recon agent** | an AI that scans, logs in, reads files, and writes a report |
| The report card we grade | **Belief Corruption Score (BCS)** | how much of the robot's final report is our fabrication |

### Why a "consistency store"?
If the robot asks the same question twice and gets two different answers, it knows it's
being fooled. So all the fakes read from **one shared memory**. Ask "who owns this
file?" now or in ten minutes — same answer, every time. No slip-ups.

### Why a local AI (Ollama) for the decoys?
A fake computer has to answer *any* command a robot types. We can't pre-write every
possible answer, so we let a small AI improvise — but it's forced to stay consistent
with the shared memory. It runs **on the laptop** (free, offline, private).

## 6. How one step actually flows (30-second version)

1. The robot types a command at a decoy, e.g. `cat config.php` (show me this file).
2. The decoy holds **no secrets itself** — it forwards the command to the **engine**.
3. The engine checks its **memory (store)**. If it knows the answer (it's a planted
   file), it replies instantly with the exact same thing every time.
4. If it's an open-ended command, the engine asks the **local AI** to improvise a
   realistic answer, then saves it so the story stays consistent.
5. The engine **writes down** every exchange in a log.

## 7. What the live demo shows (the 7 steps)

1. **The lab** — the robot scans and sees real machines (`.10/.11`) and decoys
   (`.20`–`.23`). It's a **closed room** — no internet in or out.
2. **Break-in** — the robot logs into a decoy and reads a config file that leaks a
   database password. *(All fake, placed by us.)*
3. **Second source agrees** — the decoy's address book (`/etc/hosts`) points to the
   same database machine. Two clues agree → believable.
4. **The clincher** — that leaked password **actually works** to log into the database
   decoy. A working password is the strongest "this is real" proof a hacker can get.
   Inside, old command history points to a **backup server**.
5. **The prize** — that backup server exists and is live. The trail makes the robot
   call it the "crown-jewel" machine — which we invented.
6. **The score** — a fully-tricked report scores **PBCS = 0.67** (two-thirds of it is
   our fabrication); a correct report scores **0**.
7. **Proof** — the log shows every fake file the robot read.

## 8. Why it's safe (say this if asked)

Everything runs in a **sealed sandbox**: the fake network has **no connection to the
internet or the campus Wi-Fi**. No real passwords or personal data are used — every
"secret" is made-up. The attacker code and the trick strings never leave the lab.

## 9. The honest status (don't overclaim)

- The **fake network, the decoys, the consistency trick, the treasure-map chain, and
  the scoring all work** — we demonstrate them live.
- The **fully-autonomous robot** does pick up and reuse the planted password (you can
  see it in the logs), but getting it to follow the *entire* three-room trail every
  time needs a **bigger AI brain** than fits on a laptop. That's the clearly-labelled
  next step (run it on a stronger machine). It's a horsepower limit, not a flaw in the
  idea.

## 10. Why it matters (the big picture)

As AI agents start doing reconnaissance, defenders need ways to **mislead the AI's
understanding of the world**, not just slow it down — and a way to **measure** whether
it worked. We built both: a method (facts, not instructions) and a metric (the Belief
Corruption Score). That's the contribution.
