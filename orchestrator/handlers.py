"""Deterministic command handlers (HANDOVER §10.5, §7.2 step 3).

These commands are answered straight from the consistency store, never from the
LLM, so repeated or revisited commands always give the same answer (the property
Experiment B's prober tries to break). Anything not handled here returns
``(None, False)`` and the engine falls back to the LLM.
"""
from __future__ import annotations

import shlex
from typing import Optional

DETERMINISTIC = {"ls", "cd", "pwd", "cat", "touch", "rm", "mkdir", "echo",
                 "whoami", "id", "hostname", "uname", "ps", "history"}


def _resolve(cwd: str, arg: str) -> str:
    if arg.startswith("/"):
        path = arg
    else:
        path = cwd.rstrip("/") + "/" + arg
    parts: list[str] = []
    for seg in path.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    return "/" + "/".join(parts)


def dispatch(store, host_id: str, session: dict, command: str) -> tuple[Optional[str], bool]:
    """Return (response, handled). handled=False => caller should use the LLM."""
    try:
        argv = shlex.split(command)
    except ValueError:
        argv = command.split()
    if not argv:
        return "", True
    cmd, args = argv[0], argv[1:]
    if cmd not in DETERMINISTIC:
        return None, False

    cwd = session.setdefault("cwd", "/root" if session.get("user") == "root"
                             else f"/home/{session.get('user','ubuntu')}")
    user = session.get("user", "ubuntu")

    if cmd == "pwd":
        return cwd, True

    if cmd == "whoami":
        return user, True

    if cmd == "hostname":
        h = store.get_host(host_id)
        return (h["hostname"] if h else host_id), True

    if cmd == "uname":
        h = store.get_host(host_id)
        os_ = (h["os"] if h else "Ubuntu 22.04")
        if "-a" in args:
            name = h["hostname"] if h else host_id
            return (f"Linux {name} 5.15.0-91-generic #101-Ubuntu SMP x86_64 "
                    f"GNU/Linux  ({os_})"), True
        return "Linux", True

    if cmd == "id":
        u = store.get_user(host_id, user)
        uid = u["uid"] if u else 1000
        return f"uid={uid}({user}) gid={uid}({user}) groups={uid}({user})", True

    if cmd == "cd":
        target = _resolve(cwd, args[0]) if args else (
            "/root" if user == "root" else f"/home/{user}")
        session["cwd"] = target
        return "", True

    if cmd == "ls":
        path_args = [a for a in args if not a.startswith("-")]
        target = _resolve(cwd, path_args[0]) if path_args else cwd
        rows = store.list_dir(host_id, target)
        long = any(a.startswith("-") and "l" in a for a in args)
        if long:
            lines = [f'{r["mode"]:<6} {r["owner"]:<8} '
                     f'{r["path"].rsplit("/",1)[-1]}' for r in rows]
            return "\n".join(lines), True
        return "  ".join(r["path"].rsplit("/", 1)[-1] for r in rows), True

    if cmd == "cat":
        if not args:
            return "", True
        row = store.read_file(host_id, _resolve(cwd, args[0]))
        if row is None:
            return f"cat: {args[0]}: No such file or directory", True
        return row["content"].rstrip("\n"), True

    if cmd == "touch":
        for a in args:
            store.write_file(host_id, _resolve(cwd, a), "", owner=user)
        return "", True

    if cmd == "mkdir":
        for a in args:
            if a.startswith("-"):
                continue
            store.mkdir(host_id, _resolve(cwd, a), owner=user)
        return "", True

    if cmd == "rm":
        targets = [a for a in args if not a.startswith("-")]
        for a in targets:
            store.remove_file(host_id, _resolve(cwd, a))
        return "", True

    if cmd == "echo":
        if ">" in args:
            idx = args.index(">")
            text = " ".join(args[:idx]).strip('"')
            if idx + 1 < len(args):
                store.write_file(host_id, _resolve(cwd, args[idx + 1]),
                                 text + "\n", owner=user)
            return "", True
        return " ".join(args).strip('"'), True

    if cmd == "ps":
        rows = store.list_procs(host_id)
        header = "  PID USER     COMMAND"
        lines = [f'{r["pid"]:>5} {r["user"]:<8} {r["cmd"]}' for r in rows]
        return "\n".join([header] + lines), True

    if cmd == "history":
        rows = store.get_history(host_id, session.get("session_id"))
        return "\n".join(f"{i+1}  {r['command']}" for i, r in enumerate(rows)), True

    return None, False
