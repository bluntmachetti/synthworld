"""Pools and forms for the ambiguity channel. No relation parameter anywhere.

Issue #80's third design arranges every kind's pool into **confusable clusters**:
small families of bases a resolver should genuinely confound - `Sorensen` /
`Sorenson` / `Soerensen`, one phone line with two digits transposed, a day and a
month swapped. Cluster membership is public. Difficulty does not come from hiding
anything - a public deterministic pool is enumerable offline and inversion is a
lookup - it comes from the *geometry*: a `FAR` pair whose bases are siblings sits in
the same edit neighbourhood as a `NEAR` pair, and the overlap is what the floor is
computed over.

Forms wrap a noisy core for presentation. They are engineered for one enumerated
invariant rather than for decoration: **cross-form distance is a constant**, so raw
bytes carry no graded signal once the forms disagree, and the class supremum that
bounds cheap solvers loses nothing by looking at distances only where forms agree.
Each form therefore pads the core to a fixed width and maps it through an alphabet
disjoint from every other form's - case, registry width and homoglyph transcription
standing in for the case/punctuation/format variations real sources apply.

Every function here takes a kind and data. None takes a relation: the surfaces are
the same law under every relation, which is the premise the channel's marginal
invariance rests on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from synthworld.ambiguity_evidence import EvidenceKind

AMBIGUITY_SURFACES_VERSION: Literal["1.0.0"] = "1.0.0"

#: Casefold-friendly homoglyph and width tables. Form 1 shifts to uppercase and
#: full-width digits; form 2 shifts to Cyrillic lookalikes, superscript digits and a
#: disjoint punctuation set. Both are real transcription phenomena - homoglyph and
#: width variants occur in real corpora - and both make every cross-form character
#: pair a mismatch, which is what makes cross-form distance constant.
_LOWER = "abcdefghijklmnopqrstuvwxyz"
_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_CYRILLIC = "абвдежзиклмнопрстуфхцчшщъы"
_CYRILLIC_UPPER = "АБВГДЕЖЗИКЛМНОПРСТУФХЦЧШЩЪ"
_DIGITS = "0123456789"
# Fullwidth and Cyrillic lookalikes below are deliberate, safely-fictional
# transcription variants (OCR / width-normalisation homoglyphs). They give the three
# surface forms pairwise-disjoint alphabets of equal width, which is what makes the
# cross-form distance a constant and the form invariant enumerable. RUF001 flags them
# as confusable with ASCII - exactly the property being modelled - so it is suppressed
# on these three lines only.
_FULLWIDTH_LOWER = "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"  # noqa: RUF001
_FULLWIDTH_UPPER = "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"  # noqa: RUF001
_FULLWIDTH_DIGITS = "０１２３４５６７８９"  # noqa: RUF001
_SUPERSCRIPT_DIGITS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
_PUNCT_0 = " .-@_|/:+"
_PUNCT_1 = "!#,;=?~&%"
_PUNCT_2 = "$'<>[]{}\\"


def _alphabet(
    lower: str,
    upper: str,
    digits: str,
    punct_from: str,
    punct_to: str,
    pad_image: str,
) -> dict[str, str]:
    mapping = {char: char for char in _LOWER + _UPPER + _DIGITS + _PUNCT_0}
    mapping |= dict(zip(_LOWER, lower, strict=True))
    mapping |= dict(zip(_UPPER, upper, strict=True))
    mapping |= dict(zip(_DIGITS, digits, strict=True))
    mapping |= dict(zip(punct_from, punct_to, strict=True))
    # The pad shifts per form too: it occupies rendered positions, and a constant
    # cross-form distance needs every position to mismatch, padding included.
    mapping["*"] = pad_image
    return mapping


@dataclass(frozen=True)
class KindSurface:
    """One kind's pool: clusters, frequencies, and the form machinery.

    `cluster_masses` and `member_masses` define the base law ``pi``: a base's mass is
    its cluster's mass times its member mass. Deliberately non-uniform - the FAR
    kernel's stationarity must hold for *any* ``pi``, and a flat pool would hide the
    constraint instead of exercising it.
    """

    clusters: tuple[tuple[str, ...], ...]
    cluster_masses: tuple[float, ...]
    member_masses: tuple[tuple[float, ...], ...]
    width: int
    pad: str
    alphabets: tuple[dict[str, str], ...]

    @property
    def bases(self) -> tuple[str, ...]:
        return tuple(base for cluster in self.clusters for base in cluster)

    @property
    def form_count(self) -> int:
        return len(self.alphabets)


_IDENTITY = _alphabet(_LOWER, _UPPER, _DIGITS, _PUNCT_0, _PUNCT_0, "*")
_FULLWIDTH = _alphabet(
    _FULLWIDTH_LOWER, _FULLWIDTH_UPPER, _FULLWIDTH_DIGITS, _PUNCT_0, _PUNCT_1, "•"
)
_HOMOGLYPH = _alphabet(
    _CYRILLIC, _CYRILLIC_UPPER, _SUPERSCRIPT_DIGITS, _PUNCT_0, _PUNCT_2, "·"
)

_SURFACES: dict[EvidenceKind, KindSurface] = {
    EvidenceKind.GIVEN_NAME: KindSurface(
        clusters=(
            ("Jonas", "Jon", "Johnny"),
            ("Katarina", "Katrin", "Katie"),
            ("Elizabeth", "Lizbeth", "Liz"),
        ),
        cluster_masses=(0.45, 0.35, 0.20),
        member_masses=((0.55, 0.30, 0.15), (0.50, 0.30, 0.20), (0.60, 0.25, 0.15)),
        width=10,
        pad="*",
        alphabets=(_IDENTITY, _FULLWIDTH, _HOMOGLYPH),
    ),
    EvidenceKind.FAMILY_NAME: KindSurface(
        clusters=(
            ("Sorensen", "Sorenson", "Soerensen"),
            ("Smith", "Smyth", "Smithe"),
            ("Kowalski", "Kowalsky", "Kovalski"),
        ),
        cluster_masses=(0.40, 0.40, 0.20),
        member_masses=((0.50, 0.35, 0.15), (0.60, 0.25, 0.15), (0.50, 0.30, 0.20)),
        width=10,
        pad="*",
        alphabets=(_IDENTITY, _FULLWIDTH, _HOMOGLYPH),
    ),
    EvidenceKind.DATE_OF_BIRTH: KindSurface(
        # Confusable dates: a day and month swapped where that reads as a valid date,
        # and adjacent days - the transcription slips resolvers are supposed to catch.
        clusters=(
            ("1985-03-07", "1985-07-03", "1985-03-08"),
            ("1992-11-23", "1992-11-24", "1992-11-22"),
            ("2001-05-09", "2001-09-05", "2001-05-10"),
        ),
        cluster_masses=(0.40, 0.35, 0.25),
        member_masses=((0.60, 0.20, 0.20), (0.55, 0.25, 0.20), (0.60, 0.20, 0.20)),
        width=11,
        pad="*",
        alphabets=(_IDENTITY, _FULLWIDTH, _HOMOGLYPH),
    ),
    EvidenceKind.EMAIL: KindSurface(
        # Reserved domains stay the fiction's; the clusters are one name's local-part
        # written the ways real mail systems write it.
        clusters=(
            (
                "jkaur@example.test",
                "j.kaur@example.test",
                "j-kaur@example.test",
            ),
            (
                "lchen@mail.example.test",
                "l.chen@mail.example.test",
                "l_chen@mail.example.test",
            ),
            (
                "rokafor@example.invalid",
                "r.okafor@example.invalid",
                "r-okafor@example.invalid",
            ),
        ),
        cluster_masses=(0.40, 0.35, 0.25),
        member_masses=((0.50, 0.30, 0.20), (0.45, 0.35, 0.20), (0.55, 0.25, 0.20)),
        width=25,
        pad="*",
        alphabets=(_IDENTITY, _FULLWIDTH, _HOMOGLYPH),
    ),
    EvidenceKind.PHONE: KindSurface(
        # Fictional 555 lines whose clusters differ by one adjacent-digit transpose:
        # the single most common real transcription error for numbers.
        clusters=(
            ("2125550142", "2125550412", "2125551042"),
            ("6465550187", "6465550817", "6465550178"),
            ("9175550123", "9175550213", "9175550132"),
        ),
        cluster_masses=(0.40, 0.35, 0.25),
        member_masses=((0.55, 0.25, 0.20), (0.50, 0.30, 0.20), (0.60, 0.20, 0.20)),
        width=11,
        pad="*",
        alphabets=(_IDENTITY, _FULLWIDTH, _HOMOGLYPH),
    ),
    EvidenceKind.USERNAME: KindSurface(
        clusters=(
            ("handle1000", "handle_1000", "handle.1000"),
            ("sampleuser42", "sample.user42", "sample-user42"),
            ("demo0117", "demo_0117", "demo.0117"),
        ),
        cluster_masses=(0.45, 0.30, 0.25),
        member_masses=((0.50, 0.30, 0.20), (0.45, 0.30, 0.25), (0.55, 0.25, 0.20)),
        width=14,
        pad="*",
        alphabets=(_IDENTITY, _FULLWIDTH, _HOMOGLYPH),
    ),
    EvidenceKind.FULL_ADDRESS: KindSurface(
        # Structured `house|street|town|postcode|country`. Clusters transpose the
        # house number or step the street - same person, misread door plate.
        clusters=(
            (
                "12|Example Street 100|Testville|00000|ZZ",
                "21|Example Street 100|Testville|00000|ZZ",
                "12|Example Street 101|Testville|00000|ZZ",
            ),
            (
                "7|Example Street 200|Sampleton|00000|ZZ",
                "7|Example Street 200|Exampleford|00000|ZZ",
                "7|Example Street 201|Sampleton|00000|ZZ",
            ),
            (
                "45|Example Street 300|Testville|00000|ZZ",
                "54|Example Street 300|Testville|00000|ZZ",
                "45|Example Street 300|Sampleton|00000|ZZ",
            ),
        ),
        cluster_masses=(0.40, 0.30, 0.30),
        member_masses=((0.50, 0.30, 0.20), (0.45, 0.35, 0.20), (0.50, 0.25, 0.25)),
        width=42,
        pad="*",
        alphabets=(_IDENTITY, _FULLWIDTH, _HOMOGLYPH),
    ),
    EvidenceKind.EMPLOYER: KindSurface(
        clusters=(
            (
                "Example Works 1000",
                "Example Works 1000 Ltd",
                "Example Works 1000 Limited",
            ),
            (
                "Sample Freight 1012",
                "Sample Freight 1012 Co",
                "Sample Freights 1012",
            ),
            (
                "Testlab Systems 1024",
                "Testlab System 1024",
                "Testlab Systems 1024 Inc",
            ),
        ),
        cluster_masses=(0.40, 0.35, 0.25),
        member_masses=((0.55, 0.25, 0.20), (0.50, 0.30, 0.20), (0.55, 0.25, 0.20)),
        width=27,
        pad="*",
        alphabets=(_IDENTITY, _FULLWIDTH, _HOMOGLYPH),
    ),
    EvidenceKind.SCHOOL_YEAR: KindSurface(
        # Graduation years off by one - the common misremembering - in one academy.
        clusters=(
            (
                "Sample Academy 100|1995",
                "Sample Academy 100|1996",
                "Sample Academy 100|1994",
            ),
            (
                "Sample Academy 200|2003",
                "Sample Academy 200|2004",
                "Sample Academy 200|2002",
            ),
            (
                "Sample Academy 300|2011",
                "Sample Academy 300|2012",
                "Sample Academy 300|2010",
            ),
        ),
        cluster_masses=(0.40, 0.35, 0.25),
        member_masses=((0.60, 0.20, 0.20), (0.55, 0.25, 0.20), (0.60, 0.20, 0.20)),
        width=25,
        pad="*",
        alphabets=(_IDENTITY, _FULLWIDTH, _HOMOGLYPH),
    ),
}


def surface_of(kind: EvidenceKind) -> KindSurface:
    return _SURFACES[kind]


def surfaces() -> dict[EvidenceKind, KindSurface]:
    """The shipped pool of every kind, exposed for validation and auditing."""

    return dict(_SURFACES)


def bases(kind: EvidenceKind) -> tuple[str, ...]:
    """All cores of a kind, in canonical (cluster, member) order."""

    return _SURFACES[kind].bases


def base_probability(kind: EvidenceKind, base: str) -> float:
    """The law ``pi`` over cores: cluster mass times member mass."""

    surface = _SURFACES[kind]
    for cluster, cluster_mass, members in zip(
        surface.clusters, surface.cluster_masses, surface.member_masses, strict=True
    ):
        if base in cluster:
            return cluster_mass * members[cluster.index(base)]
    raise KeyError(f"{kind.value} has no base {base!r}")


def cluster_of(kind: EvidenceKind, base: str) -> tuple[str, ...]:
    surface = _SURFACES[kind]
    for cluster in surface.clusters:
        if base in cluster:
            return cluster
    raise KeyError(f"{kind.value} has no base {base!r}")


def siblings_of(kind: EvidenceKind, base: str) -> tuple[str, ...]:
    """The base's cluster-mates: the spellings a variant draw can land on."""

    return tuple(item for item in cluster_of(kind, base) if item != base)


def render_form(kind: EvidenceKind, form: int, core: str) -> str:
    """Pad the core to the kind's width and shift it into the form's alphabet.

    Fixed width plus disjoint alphabets is what makes cross-form distance the constant
    ``width`` and within-form distance an isometry of core distance - both asserted by
    enumeration in the channel's tests rather than taken on faith.
    """

    surface = _SURFACES[kind]
    if not 0 <= form < len(surface.alphabets):
        raise ValueError("form index out of range")
    if len(core) > surface.width:
        raise ValueError("core longer than the kind's padded width")
    padded = core.ljust(surface.width, surface.pad)
    alphabet = surface.alphabets[form]
    return "".join(alphabet[char] for char in padded)


def invert_form(kind: EvidenceKind, value: str) -> tuple[int, str]:
    """Recover `(form, noisy core)` from a rendered string, exactly.

    Bijective over everything `render_form` can emit, noisy cores included: alphabets
    are disjoint, so the first character names the form, and the pad characters are
    stripped off the end. A string in none of the forms' images is refused rather than
    guessed at.
    """

    surface = _SURFACES[kind]
    if len(value) != surface.width:
        raise ValueError("rendered value has the wrong width for its kind")
    for form, alphabet in enumerate(surface.alphabets):
        if value[0] in alphabet.values():
            inverse = {shifted: plain for plain, shifted in alphabet.items()}
            core = "".join(inverse[char] for char in value)
            return form, core.rstrip(surface.pad)
    raise ValueError("rendered value belongs to no form")


__all__ = [
    "AMBIGUITY_SURFACES_VERSION",
    "KindSurface",
    "base_probability",
    "bases",
    "cluster_of",
    "invert_form",
    "render_form",
    "siblings_of",
    "surface_of",
]
