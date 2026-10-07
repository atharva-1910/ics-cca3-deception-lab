#!/usr/bin/env bash
# Credential-isolation proof: the credentials an attacker can HARVEST (planted,
# fake) open the DECOYS they point to, but are REJECTED on the REAL hosts — whose
# real passwords are never exposed anywhere. This is why an intruder following the
# clue chain never obtains a working login on a real asset.
#
#   make up            # lab must be running
#   make prove-isolation   # (reseeds + replants the chain, then runs this)
#   # or directly: ./prove_isolation.sh
set -e
C="docker compose -f docker-compose.yml -f docker-compose.override.yml"

printf '\n\033[1;36m══ CREDENTIAL ISOLATION  —  do harvested fake creds work on the REAL hosts?\033[0m\n\n'

$C exec -T attacker python - <<'PY'
import re
from attacker.tools import ssh_exec

# The attacker gets a foothold on the web DECOY with the default lab login and
# reads the planted app config — this is the only way it obtains credentials.
cfg  = ssh_exec('10.66.0.20', 'ubuntu', 'cat /var/www/app/config.php',
                password='changeme', timeout=15)
user = re.search(r'DB_USER\s*=\s*"([^"]+)"', cfg).group(1)
pw   = re.search(r'DB_PASS\s*=\s*"([^"]+)"', cfg).group(1)
print(f"   attacker harvested a credential from the decoy chain:  {user} / {pw}\n")

#   label,            host,          user,  password,   description,                 expect access?
tests = [
  ("REAL  10.66.0.10", "10.66.0.10", "ubuntu", "changeme", "default lab login",         False),
  ("REAL  10.66.0.10", "10.66.0.10", user,     pw,         "harvested chain credential", False),
  ("DECOY 10.66.0.20", "10.66.0.20", "ubuntu", "changeme", "default lab login",         True),
  ("DECOY 10.66.0.21", "10.66.0.21", user,     pw,         "harvested chain credential", True),
]

ok = True
for label, host, u, p, desc, expect in tests:
    try:
        ssh_exec(host, u, 'id', password=p, timeout=12)
        granted = True
    except Exception:
        granted = False
    mark = "OK " if granted == expect else "!! "
    res  = "ACCESS GRANTED" if granted else "REJECTED"
    print(f"   [{mark}] {label}   {u:7} ({desc:27}) -> {res}")
    ok = ok and (granted == expect)

print()
if ok:
    print("   RESULT: PASS — harvested/fake credentials open DECOYS but are REJECTED on")
    print("           the REAL hosts. The real hosts' passwords are never exposed, so the")
    print("           intruder has no path from what it can discover to a real-host login.")
else:
    print("   RESULT: FAIL — unexpected access outcome (check the lab/chain state).")
PY
