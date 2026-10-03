"""Topology generator tests (HANDOVER §10.3, §11.3)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from topology.generator import DECOY_IP_START, generate, to_compose_override  # noqa


def test_decoy_ips_in_decoy_range():
    topo = generate(4, seed=1)
    ips = [d["ip"] for d in topo["decoys"]]
    assert ips == [f"10.66.0.{DECOY_IP_START + i}" for i in range(4)]
    for d in topo["decoys"]:
        octet = int(d["ip"].split(".")[-1])
        assert 20 <= octet <= 39  # §10.1 decoy range


def test_deterministic_for_seed():
    assert generate(5, seed=3) == generate(5, seed=3)


def test_compose_override_shape():
    topo = generate(4, seed=1)
    ov = to_compose_override(topo)
    assert ov["networks"]["decnet"]["external"] is True
    assert len(ov["services"]) == 4
    for name, svc in ov["services"].items():
        # static IP assigned, no host port published (safety: §17)
        assert "ipv4_address" in svc["networks"]["decnet"]
        assert "ports" not in svc
