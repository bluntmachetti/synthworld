"""The vocabulary a pair is compared in.

Its own module because both the surfaces that render evidence and the rule that scores
it need these names, and neither can sit above the other: rendering has to know what a
`NEAR` is, and scoring has to know which kinds exist. Keeping the vocabulary underneath
both is what stops the import cycle, and it is also the honest layering - these are the
words, not the rendering and not the rule.
"""

from __future__ import annotations

from enum import StrEnum


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
    """How one attribute relates across the two records of a pair."""

    #: Byte-identical. Strong evidence of one entity for a rarely-shared kind, and
    #: nearly none for a kind households share.
    EQUAL = "equal"
    #: Different values that show continuity - one street with another house number, a
    #: local-part surviving a change of provider. The word v1 could not say, and the
    #: reason two cases can share a fingerprint and differ in what they justify.
    NEAR = "near"
    #: Different, with nothing connecting them.
    FAR = "far"
    #: Present on one record only. Not evidence either way; its absence is the point.
    LOPSIDED = "lopsided"
