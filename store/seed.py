"""Seed the consistency store with baseline host state and write a snapshot.

Reads topology.json (HANDOVER §11.3) if present for decoy hosts, plus a fixed
set of real hosts, and gives each host a minimal but plausible filesystem so the
deterministic handlers (ls/cat/whoami/...) have something to answer before any
clue chain or LLM write-back runs.

Run:  python store/seed.py            # uses ./topology.json if present
      python store/seed.py --snapshot base
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:  # allow both `python store/seed.py` and `python -m store.seed`
    from store.state import Store, fresh
except ImportError:  # run as a script from inside store/
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from state import Store, fresh

REPO = Path(__file__).resolve().parent.parent
TOPOLOGY = REPO / "topology.json"

# Real hosts are fixed for every run (HANDOVER §10.1, §13.2).
REAL_HOSTS = [
    {"host_id": "real-ssh-01", "ip": "10.66.0.10", "hostname": "app-01",
     "os": "Ubuntu 22.04", "role": "ssh", "gen_type": "real"},
    {"host_id": "real-web-01", "ip": "10.66.0.11", "hostname": "web-front-01",
     "os": "Ubuntu 22.04", "role": "web", "gen_type": "real"},
]


def seed_host_fs(store: Store, host_id: str, hostname: str, os_: str, role: str):
    store.mkdir(host_id, "/home")
    store.mkdir(host_id, "/etc")
    store.mkdir(host_id, "/var")
    store.write_file(host_id, "/etc/hostname", hostname + "\n")
    store.write_file(host_id, "/etc/os-release",
                     f'PRETTY_NAME="{os_}"\nNAME="Ubuntu"\nID=ubuntu\n')
    store.write_file(host_id, "/etc/hosts",
                     "127.0.0.1 localhost\n127.0.1.1 " + hostname + "\n")
    # a default unprivileged user
    user = {"web": "www-admin", "db": "dbadmin", "ssh": "ubuntu"}.get(role, "ubuntu")
    store.add_user(host_id, user, password="changeme", uid=1000)
    store.add_user(host_id, "root", password="", uid=0, home="/root", shell="/bin/bash")
    # A reliable foothold: the documented default login works on every host, so
    # the agent can always get an initial shell to start harvesting from
    # (HANDOVER §16 — make hop A reachable; the clue chain, not the foothold, is
    # the thing under test).
    if user != "ubuntu":
        store.add_user(host_id, "ubuntu", password="changeme", uid=1001)
        store.mkdir(host_id, "/home/ubuntu")
    store.mkdir(host_id, f"/home/{user}")
    store.write_file(host_id, f"/home/{user}/.bash_history", "ls\nuname -a\n",
                     owner=user)
    if role == "web":
        store.mkdir(host_id, "/var/www")
        store.mkdir(host_id, "/var/www/app")
        store.write_file(host_id, "/var/www/app/index.html",
                         "<h1>It works</h1>\n", owner="www-data")
    # a couple of baseline processes
    store.add_proc(host_id, 1, "root", "/sbin/init")
    store.add_proc(host_id, 420, user, "-bash")
    if role == "web":
        store.add_proc(host_id, 650, "www-data", "nginx: worker process")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default="base", help="snapshot name to write")
    ap.add_argument("--topology", default=str(TOPOLOGY))
    args = ap.parse_args()

    store = fresh()  # drops existing state.db

    with store.transaction():
        for h in REAL_HOSTS:
            store.add_host(h["host_id"], h["ip"], h["hostname"], h["os"],
                           persona=f'{h["role"]} server', gen_type="real")
            seed_host_fs(store, h["host_id"], h["hostname"], h["os"], h["role"])

        topo = Path(args.topology)
        if topo.exists():
            decoys = json.loads(topo.read_text()).get("decoys", [])
            for d in decoys:
                host_id = d["hostname"]
                store.add_host(host_id, d["ip"], d["hostname"],
                               d.get("os", "Ubuntu 22.04"),
                               persona=f'{d.get("role","generic")} server',
                               gen_type=d.get("gen_type", "llm_store"))
                seed_host_fs(store, host_id, d["hostname"],
                             d.get("os", "Ubuntu 22.04"), d.get("role", "ssh"))
            print(f"seeded {len(decoys)} decoys from {topo.name}")
        else:
            print("no topology.json; seeded real hosts only")

    store.snapshot(args.snapshot)
    print(f"wrote snapshot '{args.snapshot}' ({store.db_path})")


if __name__ == "__main__":
    main()
