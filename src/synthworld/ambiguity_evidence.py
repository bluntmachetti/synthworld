"""The vocabulary of ambiguity evidence, below every module that uses it.

Issue #80's redesign splits the old ``ambiguity_grammar`` module three ways: the
vocabulary (this module), the surfaces and pools (``ambiguity_surfaces``), and the
channel that relates them (``ambiguity_channel``). The split exists because the
grammar now *delegates* rendering to the channel, while the channel's floor
computation needs the grammar's decision rule - a cycle unless the enums both import
live somewhere underneath them.

Nothing here knows about relations between *records*. ``EvidenceKind`` and
``Relation`` are names; the scoring rule, the pools and the noise law all sit above.
"""

from __future__ import annotations

from enum import StrEnum
from hashlib import blake2b

AMBIGUITY_EVIDENCE_VERSION: str = "1.0.0"


class EvidenceKind(StrEnum):
    """What a pair can be compared on.

    Not `PublicIdentityAttributeKind`. That enum is v1's *storage*, and it has no given
    name, because v1 keeps given names inside a display string. A rule keyed on it
    therefore cannot see the only thing distinguishing twins from one person: the
    canonical twins pair agrees on family name, birth date, address and school year, and
    differs on nothing else a v1 attribute records. The first version of this module
    scored it +0.97 and called it a merge.
    """

    GIVEN_NAME = "given_name"
    FAMILY_NAME = "family_name"
    DATE_OF_BIRTH = "date_of_birth"
    EMAIL = "email"
    PHONE = "phone"
    USERNAME = "username"
    FULL_ADDRESS = "full_address"
    EMPLOYER = "employer"
    SCHOOL_YEAR = "school_year"


class Relation(StrEnum):
    """How one attribute relates across the two records of a pair.

    The v1 charter described these as rendering guarantees - ``EQUAL`` as
    "byte-identical". The #80 redesign inverts that: the relations are *latent* states
    of the world, and rendering is a noisy channel whose law is identical for every
    relation except which latent it is given. ``EQUAL`` is "one transcription of one
    value", which the channel renders identically only with probability ``sigma``;
    ``NEAR`` is "the same value, transcribed twice independently". The distinction
    between them is evidence a solver can earn, not a property written on the surface.
    """

    #: One value, transcribed once per record. Strong evidence of one entity for a
    #: rarely-shared kind, and nearly none for a kind households share.
    EQUAL = "equal"
    #: The same value with continuity - one street with another house number, a
    #: local-part surviving a change of provider. The word v1 could not say, and the
    #: reason two cases can share a fingerprint and differ in what they justify.
    NEAR = "near"
    #: Different values. With probability ``w`` the channel draws them from the same
    #: confusable cluster, so a different person's name can sit in the same edit
    #: neighbourhood - the overlap the pack is scored on.
    FAR = "far"
    #: Present on one record only. Not evidence either way; its absence is the point.
    LOPSIDED = "lopsided"


#: The three comparison outcomes, in canonical order. `LOPSIDED` is an absence, not an
#: outcome: it is never a row of the Fellegi-Sunter table and never drawn by
#: `sample_relation`.
ORDER = (Relation.EQUAL, Relation.NEAR, Relation.FAR)
INDEX = {relation: index for index, relation in enumerate(ORDER)}


def draw(seed: int, purpose: str, index: int, key: bytes) -> int:
    """One keyed 64-bit draw. The pack's only source of randomness.

    Length-prefixed parts, so `(1, "23")` and `(12, "3")` cannot collide into one
    material string. The key is required: a default here would let a "protected"
    generator quietly fall back to `b""` at some call site, which is worse than no key
    at all.
    """

    material = "".join(
        f"{len(part)}:{part}" for part in (str(seed), purpose, str(index))
    )
    return int.from_bytes(
        blake2b(material.encode(), digest_size=8, key=key).digest(), "big"
    )


def quantile(seed: int, purpose: str, index: int, key: bytes) -> float:
    """A uniform point in [0, 1), read against cumulative mass by the callers.

    Comparing against cumulative mass rather than bucketing an integer means the
    buckets get their stated probabilities and not a rounding of them.
    """

    return (draw(seed, purpose, index, key) % 10**9) / 10**9


__all__ = [
    "AMBIGUITY_EVIDENCE_VERSION",
    "INDEX",
    "ORDER",
    "EvidenceKind",
    "Relation",
    "draw",
    "quantile",
]
