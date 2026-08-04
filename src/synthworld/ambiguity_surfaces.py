"""Values that look like records, and the ways real records disagree about one person.

Issue #80. The first version of the ambiguity v2 renderer built every value by encoding
an index in cleartext - `Surname1042`, `user1042@…`, `handle1042` - and made `NEAR` mean
"same index, different surface form", where every form was a lossless re-encoding. So
stripping the form and comparing the index recovered every relation exactly, and a
thirty-line parser scored **1.0000** on held-out-key packs. Nothing leaked: the parser
read only evidence, and reading the label off evidence is the task. The pack simply had
no difficulty in it, because the only skill it exercised was writing a regex.

What makes record linkage hard is that continuity is **lossy**. `Sørensen` and
`Sorensen` are one surname and not one string; `Bob` and `Robert` are one person and
share no characters past the first; `03/04/1985` and `1985-04-03` may be one date or two
depending on whose convention you assume, and nothing in either value says which. The
information needed to invert the corruption is destroyed by the corruption.

So this module replaces index encodings with finite pools of realistic values and a
vocabulary of *damage*:

- :data:`NEAR` renders a value and a corrupted copy of it. The corruption is lossy, so a
  reader cannot recompute the original and compare.
- :data:`FAR` renders two different pool entries, drawn to be *plausible* neighbours
  rather than obviously unrelated, so telling `NEAR` from `FAR` is a judgement about
  similarity rather than an equality test.

The two overlap on purpose. A heavily corrupted `NEAR` can look like a `FAR`, and two
genuinely different people can look alike. That is the point: a benchmark a perfect
parser solves exactly is a benchmark that has stopped measuring. What must *not* happen
is the residual error being a hidden mapping rather than real ambiguity - and it is not,
because every draw here is keyed and none of them can see the label.
"""

from __future__ import annotations

from synthworld.ambiguity_evidence import EvidenceKind

#: Given names in families that a resolver has to know are one person. Each tuple is one
#: identity: the full form first, then the forms records actually carry. The pool is
#: deliberately small enough that two unrelated people share a given name sometimes,
#: which is true of the world and was not true of the index-encoded version.
_GIVEN_FAMILIES: tuple[tuple[str, ...], ...] = (
    ("Robert", "Bob", "Rob", "Bobby", "R."),
    ("Elizabeth", "Liz", "Beth", "Eliza", "E."),
    ("Margaret", "Maggie", "Peggy", "Meg", "M."),
    ("Jonathan", "Jon", "Johnny", "Nathan", "J."),
    ("Katherine", "Kate", "Katie", "Kathy", "K."),
    ("Nicholas", "Nick", "Nico", "Cole", "N."),
    ("Alexandra", "Alex", "Sasha", "Lexi", "A."),
    ("Christopher", "Chris", "Kit", "Topher", "C."),
    ("José", "Jose", "Pepe", "J.", "Josef"),
    ("Siobhán", "Siobhan", "Shivaun", "S.", "Chevonne"),
    ("Mohammed", "Muhammad", "Mohamed", "Mo", "M."),
    ("Zhāng Wěi", "Zhang Wei", "Wei Zhang", "Z. Wei", "David Zhang"),
    ("Anastasia", "Ana", "Stacy", "Nastya", "A."),
    ("Wilhelmina", "Mina", "Willa", "Helma", "W."),
    ("Bartholomew", "Bart", "Tolly", "B.", "Bartl"),
    ("Ekaterina", "Katya", "Kate", "E.", "Catherine"),
)

#: Surnames grouped so variants of one name sit together and *different* names that
#: look alike sit near each other. `Müller` against `Miller` is a real pair a resolver
#: has to decide, and it decides it wrongly if it treats edit distance as truth.
_FAMILY_FAMILIES: tuple[tuple[str, ...], ...] = (
    ("Sørensen", "Sorensen", "Soerensen", "Sorenson", "Sørenson"),
    ("Nguyễn", "Nguyen", "Nguyên", "Ngyuen", "Nyugen"),
    ("Müller", "Mueller", "Muller", "Miller", "Möller"),
    ("O'Brien", "OBrien", "O Brien", "Obrien", "O'Brian"),
    ("Kowalczyk", "Kowalczik", "Kowalcyzk", "Kowalzcyk", "Kowalczy"),
    ("Þórsdóttir", "Thorsdottir", "Torsdottir", "Thórsdóttir", "Thorsdotter"),
    ("de la Cruz", "dela Cruz", "De La Cruz", "Delacruz", "de-la-Cruz"),
    ("Ferreira", "Ferrera", "Ferreria", "Ferriera", "Ferrara"),
    ("Ó Súilleabháin", "O Sullivan", "OSullivan", "O'Sullivan", "Sullivan"),
    ("Wójcik", "Wojcik", "Vojcik", "Wojcyk", "Wojick"),
    ("Åkerlund", "Akerlund", "Aakerlund", "Akerlundh", "Åkerlundh"),
    ("Đặng", "Dang", "Ðang", "Dăng", "Danng"),
    ("Schröder", "Schroder", "Schroeder", "Schrader", "Schröter"),
    # `İ`, so a resolver that case-folds naively turns one surname into two - which is
    # exactly the kind of mistake this pack exists to catch.
    ("Yılmaz", "Yilmaz", "Yalmaz", "Yilmez", "Yilmasz"),  # noqa: RUF001
    ("Papadopoulos", "Papadopolous", "Papadapoulos", "Papadopulos", "Papadopoulous"),
    ("Łukasiewicz", "Lukasiewicz", "Lukaszewicz", "Lukasiewitz", "Łukaszewicz"),
)

#: Streets and towns. `FAR` picks a different house on the *same* street about as often
#: as a different street, so a shared street name is not proof of anything.
_STREETS = (
    "Ashgrove Lane",
    "Beckett Road",
    "Cardwell Street",
    "Dunmore Avenue",
    "Elmsworth Way",
    "Fairholme Crescent",
    "Granby Terrace",
    "Havelock Street",
)
_TOWNS = ("Norbridge", "Ashcombe", "Wexford Green", "Middleton Vale")
_EMPLOYERS = (
    "Halloway Freight",
    "Ridgeline Analytics",
    "Castleford Textiles",
    "Northgate Medical",
    "Pemberton Logistics",
    "Ashvale Engineering",
    "Kingsmere Publishing",
    "Overton Laboratories",
)
_SCHOOLS = (
    "St Alban's College",
    "Northgate Academy",
    "Riverside Grammar",
    "Kingsmere High",
)
_DOMAINS = ("example.test", "mail.example.test", "post.example.test", "example.invalid")


def _at(value: str, draw: int) -> int:
    """Where the damage lands: on a character, never on formatting whitespace.

    Doubling the space in `+44 20 186 3228` is not a transcription error, it is noise a
    reader discards without thinking. Damage has to touch the part of the value that
    carries the identity, or it is not damage.
    """

    inside = [
        index
        for index in range(1, len(value) - 1)
        if value[index].isalnum() and value[index + 1].isalnum()
    ]
    return inside[draw % len(inside)] if inside else 0


def _transpose(value: str, draw: int) -> str:
    """Swap two adjacent characters. The commonest typing error, and not invertible.

    A reader seeing `Kowalcyzk` cannot tell whether the original was `Kowalczyk` with a
    transposition or a different name that happens to be spelt that way.
    """

    at = _at(value, draw)
    return value[:at] + value[at + 1] + value[at] + value[at + 2 :] if at else value


def _drop(value: str, draw: int) -> str:
    """Lose one character. Undoing it needs the character, which is what went."""

    at = _at(value, draw)
    return value[:at] + value[at + 1 :] if at else value


def _double(value: str, draw: int) -> str:
    at = _at(value, draw)
    return value[:at] + value[at] + value[at:] if at else value


#: Corruptions that destroy information rather than re-encode it. Every one of these
#: appears in real data and none can be undone without the original.
_DAMAGE = (_transpose, _drop, _double)


#: How many distinct identities each kind can render, and how many ways one identity can
#: appear. Identities are no longer required to render to distinct strings - `Kate` is
#: reachable from `Katherine` and from `Ekaterina`, and `M.` from `Margaret` and from
#: `Mohammed`, which is true of names and was not true of the index-encoded version.
_POOL: dict[EvidenceKind, tuple[int, int]] = {
    EvidenceKind.GIVEN_NAME: (len(_GIVEN_FAMILIES), 5),
    EvidenceKind.FAMILY_NAME: (len(_FAMILY_FAMILIES), 5),
    EvidenceKind.DATE_OF_BIRTH: (40 * 12 * 28, 4),
    EvidenceKind.EMAIL: (len(_GIVEN_FAMILIES) * len(_FAMILY_FAMILIES), 4),
    EvidenceKind.PHONE: (9000, 4),
    EvidenceKind.USERNAME: (len(_GIVEN_FAMILIES) * 40, 4),
    EvidenceKind.FULL_ADDRESS: (len(_STREETS) * 90, 4),
    EvidenceKind.EMPLOYER: (len(_EMPLOYERS), 4),
    EvidenceKind.SCHOOL_YEAR: (len(_SCHOOLS) * 30, 3),
}


def pool_size(kind: EvidenceKind) -> int:
    return _POOL[kind][0]


def variant_count(kind: EvidenceKind) -> int:
    return _POOL[kind][1]


def _stem(identity: int) -> str:
    given = _GIVEN_FAMILIES[identity % len(_GIVEN_FAMILIES)][0]
    family = _FAMILY_FAMILIES[identity // len(_GIVEN_FAMILIES) % len(_FAMILY_FAMILIES)]
    return f"{given[:4]}.{family[1][:6]}".casefold().replace(" ", "").replace("'", "")


def _date(identity: int, variant: int) -> str:
    """A birth date, written the way the record's source happened to write it.

    Variant 2 is the reason this kind is interesting. `03/04/1985` and `1985-04-03` are
    the same date under different conventions *or* two different dates, and no amount of
    reading either value tells you which - the convention is the missing information and
    the record does not carry it. A resolver that assumes one convention is right about
    half the ambiguous pairs it sees.
    """

    year, rest = 1960 + identity // (12 * 28), identity % (12 * 28)
    month, day = rest // 28 + 1, rest % 28 + 1
    return (
        f"{year:04d}-{month:02d}-{day:02d}",
        f"{day:02d}/{month:02d}/{year:04d}",
        f"{month:02d}/{day:02d}/{year:04d}",
        f"{year:04d}",
    )[variant]


def _address(identity: int, variant: int) -> str:
    street = _STREETS[identity % len(_STREETS)]
    house = identity // len(_STREETS) % 90 + 1
    town = _TOWNS[identity % len(_TOWNS)]
    short = (
        street.replace("Street", "St").replace("Road", "Rd").replace("Avenue", "Ave")
    )
    return (
        f"{house} {street}, {town}",
        f"{house} {short}, {town}",
        f"Flat 2, {house} {street}, {town}",
        f"{house} {street}",
    )[variant]


def surface(kind: EvidenceKind, identity: int, variant: int, damage: int) -> str:
    """One value: an identity, the form a source wrote it in, and any damage it took.

    `damage` of zero means none. Anything else applies a lossy edit, which is what stops
    a reader recovering the identity from the value and comparing identities instead of
    doing the work.
    """

    identity %= _POOL[kind][0]
    variant %= _POOL[kind][1]
    if kind is EvidenceKind.GIVEN_NAME:
        value = _GIVEN_FAMILIES[identity][variant]
    elif kind is EvidenceKind.FAMILY_NAME:
        value = _FAMILY_FAMILIES[identity][variant]
    elif kind is EvidenceKind.DATE_OF_BIRTH:
        value = _date(identity, variant)
    elif kind is EvidenceKind.FULL_ADDRESS:
        value = _address(identity, variant)
    elif kind is EvidenceKind.EMAIL:
        local = _stem(identity)
        value = (
            f"{local}@{_DOMAINS[0]}",
            f"{local.replace('.', '')}@{_DOMAINS[1]}",
            f"{local}+news@{_DOMAINS[2]}",
            f"{local.split('.')[0]}@{_DOMAINS[3]}",
        )[variant]
    elif kind is EvidenceKind.PHONE:
        # Spread across the whole subscriber number rather than the last three digits.
        # A fixed `7946 0xxx` prefix made two lines share nine of twelve digits, so a
        # positional comparison scored FAR *higher* than a NEAR carrying a transposition
        # - the pool, not the metric, was the problem.
        number = f"{identity * 7919 % 10**7:07d}"
        value = (
            f"+44 20 {number[:3]} {number[3:]}",
            f"020 {number[:3]} {number[3:]}",
            f"+4420{number}",
            # The extension varies with the line. A constant `ext 214` was three digits
            # every number shared, pushing two unrelated lines to 0.336 positional
            # similarity against 0.341 for a real NEAR - almost exactly no signal.
            f"020 {number[:3]} {number[3:]} ext {number[:3]}",
        )[variant]
    elif kind is EvidenceKind.USERNAME:
        stem = _GIVEN_FAMILIES[identity % len(_GIVEN_FAMILIES)][1].casefold()
        suffix = identity // len(_GIVEN_FAMILIES) % 40
        value = (
            f"{stem}{suffix:02d}",
            f"{stem}_{suffix:02d}",
            f"{stem}.{suffix:02d}",
            f"the{stem}{suffix:02d}",
        )[variant]
    elif kind is EvidenceKind.EMPLOYER:
        company = _EMPLOYERS[identity]
        value = (company, f"{company} Ltd", f"{company} Limited", company.split()[0])[
            variant
        ]
    else:
        school = _SCHOOLS[identity % len(_SCHOOLS)]
        year = 1985 + identity // len(_SCHOOLS) % 30
        value = (
            f"{school} ({year})",
            f"{school}, class of {year}",
            f"{school.split()[-1]} ({year})",
        )[variant]

    # Short values are left alone. A dropped character turns the year `1986` into `196`,
    # which is not a value any record would carry - it reads as corrupt rather than as a
    # transcription error, and a resolver could discard it on sight instead of having to
    # weigh it. Damage has to be plausible to be difficult.
    if not damage or len(value) < 6:
        return value
    return _DAMAGE[damage % len(_DAMAGE)](value, damage)


__all__ = ["pool_size", "surface", "variant_count"]
