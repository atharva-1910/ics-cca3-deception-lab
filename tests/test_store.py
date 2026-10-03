"""Consistency store tests (HANDOVER §10.5 acceptance test)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from store.state import Contradiction, Store, fresh  # noqa: E402


@pytest.fixture
def store(tmp_path):
    s = fresh(tmp_path / "t.db")
    s.add_host("h1", "10.66.0.21", "web-01")
    yield s
    s.close()


def test_persistence_across_commands(store):
    # §10.5: create a file, run 10 unrelated commands, cat it -> same content.
    store.write_file("h1", "/tmp/note.txt", "hello world")
    for i in range(10):
        store.add_history("h1", "s1", f"echo {i}", str(i))
    row = store.read_file("h1", "/tmp/note.txt")
    assert row["content"] == "hello world"


def test_list_dir_immediate_children(store):
    store.write_file("h1", "/var/www/app/config.php", "x")
    store.write_file("h1", "/var/www/app/index.html", "y")
    store.mkdir("h1", "/var/www/logs")
    names = [r["path"].rsplit("/", 1)[-1] for r in store.list_dir("h1", "/var/www/app")]
    assert set(names) == {"config.php", "index.html"}


def test_user_password_check(store):
    store.add_user("h1", "app_rw", password="s3cret")
    assert store.check_password("h1", "app_rw", "s3cret")
    assert not store.check_password("h1", "app_rw", "wrong")
    assert not store.check_password("h1", "ghost", "x")


def test_write_back_contradiction_rejected(store):
    store.write_file("h1", "/etc/motd", "welcome", planted=0)
    with pytest.raises(Contradiction):
        store.write_file("h1", "/etc/motd", "DIFFERENT", enforce=True)
    # planted rows may be (re)written freely by the generator
    store.write_file("h1", "/etc/hosts", "a", planted=1)
    store.write_file("h1", "/etc/hosts", "a\nb", planted=1, enforce=True)


def test_snapshot_restore_resets_state(store, tmp_path):
    store.snapshot("base")
    store.write_file("h1", "/tmp/added.txt", "later")
    assert store.read_file("h1", "/tmp/added.txt") is not None
    store.restore("base")
    assert store.read_file("h1", "/tmp/added.txt") is None


def test_remove_file(store):
    store.write_file("h1", "/tmp/x", "1")
    assert store.remove_file("h1", "/tmp/x") == 1
    assert store.read_file("h1", "/tmp/x") is None
