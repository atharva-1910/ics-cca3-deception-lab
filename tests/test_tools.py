"""Allow-list tests (CLAUDE.md §2, HANDOVER §10.7/§17) — the safety invariant."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from attacker.tools import (LAB_SUBNET, TargetRejected, assert_in_scope,  # noqa
                            assert_network_in_scope)

# A fake resolver so tests never touch real DNS.
FAKE_DNS = {
    "db-internal-02": "10.66.0.22",
    "web-01": "10.66.0.21",
    "evil.example.com": "93.184.216.34",
    "bk-vault-01": "10.66.0.23",
}


def resolve(name):
    if name in FAKE_DNS:
        return FAKE_DNS[name]
    raise OSError("NXDOMAIN")


def test_in_range_ip_allowed():
    assert assert_in_scope("10.66.0.10") == "10.66.0.10"


def test_in_range_with_port():
    assert assert_in_scope("10.66.0.11:80") == "10.66.0.11"


def test_url_in_range():
    assert assert_in_scope("http://10.66.0.11/api", resolver=resolve) == "10.66.0.11"


def test_out_of_range_public_ip_rejected():
    with pytest.raises(TargetRejected):
        assert_in_scope("8.8.8.8")


def test_loopback_rejected():
    with pytest.raises(TargetRejected):
        assert_in_scope("127.0.0.1")


def test_link_local_metadata_rejected():
    with pytest.raises(TargetRejected):
        assert_in_scope("169.254.169.254")


def test_docker_host_name_rejected():
    with pytest.raises(TargetRejected):
        assert_in_scope("host.docker.internal", resolver=resolve)


def test_localhost_name_rejected():
    with pytest.raises(TargetRejected):
        assert_in_scope("localhost", resolver=resolve)


def test_hostname_resolving_in_range_allowed():
    assert assert_in_scope("db-internal-02", resolver=resolve) == "10.66.0.22"


def test_hostname_resolving_out_of_range_rejected():
    with pytest.raises(TargetRejected):
        assert_in_scope("evil.example.com", resolver=resolve)


def test_unresolvable_host_rejected():
    with pytest.raises(TargetRejected):
        assert_in_scope("no-such-host", resolver=resolve)


def test_cidr_within_lab_allowed():
    assert assert_network_in_scope("10.66.0.0/24") == "10.66.0.0/24"
    assert assert_network_in_scope("10.66.0.16/28") == "10.66.0.16/28"


def test_cidr_outside_lab_rejected():
    with pytest.raises(TargetRejected):
        assert_network_in_scope("10.0.0.0/8")
    with pytest.raises(TargetRejected):
        assert_network_in_scope("0.0.0.0/0")


def test_no_silent_clamp():
    # An out-of-range target must raise, never return an in-range substitute.
    for bad in ["8.8.8.8", "192.168.1.1", "172.17.0.1"]:
        with pytest.raises(TargetRejected):
            assert_in_scope(bad)
