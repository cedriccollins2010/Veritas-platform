import hashlib
import io

import pytest

from app.crypto.hash_service import (
    digests_match,
    normalize_digest,
    sha256_file,
    sha256_stream,
    verify_file,
)

# Vecteurs de test connus (FIPS 180-2 et valeurs de référence courantes).
EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
HELLO_WORLD = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"


@pytest.mark.parametrize(
    ("content", "expected"),
    [(b"", EMPTY), (b"abc", ABC), (b"hello world", HELLO_WORLD)],
)
def test_known_vectors(tmp_path, content: bytes, expected: str) -> None:
    path = tmp_path / "sample.bin"
    path.write_bytes(content)
    assert sha256_file(path) == expected


def test_streaming_matches_single_pass_on_multi_chunk_file(tmp_path) -> None:
    content = bytes(range(256)) * 20_000  # environ 5 Mo, donc plusieurs blocs de 1 Mo
    path = tmp_path / "large.bin"
    path.write_bytes(content)
    assert sha256_file(path) == hashlib.sha256(content).hexdigest()


def test_small_chunks_give_same_result() -> None:
    assert sha256_stream(io.BytesIO(b"hello world"), chunk_size=3) == HELLO_WORLD


def test_one_changed_byte_is_detected(tmp_path) -> None:
    path = tmp_path / "document.pdf"
    path.write_bytes(b"%PDF-1.7 contenu original")
    original = sha256_file(path)
    path.write_bytes(b"%PDF-1.7 contenu originaL")
    assert not verify_file(path, original)


def test_digest_comparison_ignores_case_and_whitespace() -> None:
    assert digests_match(HELLO_WORLD.upper(), f"  {HELLO_WORLD}\n")


@pytest.mark.parametrize("bad", ["", "abc", "z" * 64, HELLO_WORLD + "0"])
def test_malformed_digest_is_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        normalize_digest(bad)
