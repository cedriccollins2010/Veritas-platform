"""Empreinte du manifeste (ADR-0007) : calcul et détection d'altération, sans serveur."""

import hashlib

import pytest

from veritas_verifier import canonical
from veritas_verifier import manifest as manifest_crypto


def _sample() -> dict:
    return manifest_crypto.seal({"format": "veritas-manifest", "evidence": {"title": "Disque"}})


def test_seal_and_check() -> None:
    sealed = _sample()
    body = {k: v for k, v in sealed.items() if k != "manifest_digest"}
    expected = hashlib.sha256(canonical.canonicalize(body)).hexdigest()
    assert sealed["manifest_digest"]["value"] == expected
    assert manifest_crypto.digest_is_valid(sealed)


@pytest.mark.parametrize(
    "tamper",
    [
        lambda m: m["evidence"].update(title="Disquf"),
        lambda m: m.update(format="veritas-manifesu"),
        lambda m: m["manifest_digest"].update(value="0" * 64),
        lambda m: m["manifest_digest"].update(algorithm="MD5"),
        lambda m: m.pop("manifest_digest"),
        lambda m: m.update(extra=None),
    ],
)
def test_tampering_invalidates_digest(tamper) -> None:
    sealed = _sample()
    tamper(sealed)
    assert not manifest_crypto.digest_is_valid(sealed)
