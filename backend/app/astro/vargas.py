"""Five more divisional-chart SIGN calculators (D2 Hora, D3 Drekkana, D7
Saptamsa, D12 Dwadashamsa, D30 Trimshamsa), beyond the three
(D1/D9/D10 — app.astro.charts) this app already exposes as full charts
through the API.

These five exist ONLY to feed Shadbala's Saptavargaja Bala
(app.astro.shadbala), which needs a planet's DIGNITY in all seven classical
vargas (D1, D2, D3, D7, D9, D12, D30) — not full chart objects with their
own houses/Lagna. So unlike app.astro.charts.compute_chart, these are bare
`longitude -> sign index` functions, not full ChartResult builders: nothing
here computes a divisional Lagna, houses, or exposes a new API chart type.
"""
from app.astro.charts import degree_in_sign, sign_index


def hora_sign_index(longitude: float) -> int:
    """D2. Each 30° sign splits into two 15° horas, each entirely ruled by
    either the Sun (assigned to Leo, sign index 4) or the Moon (assigned to
    Cancer, sign index 3) — never any other sign. Classical rule: in an odd
    sign, the first half is the Sun's hora and the second half the Moon's;
    in an even sign this reverses."""
    rasi = sign_index(longitude)
    half = int(degree_in_sign(longitude) // 15)  # 0 or 1
    is_odd_sign = rasi % 2 == 0  # 0-indexed even == classical odd-numbered sign
    sun_hora = half == 0 if is_odd_sign else half == 1
    return 4 if sun_hora else 3  # Leo (Sun) or Cancer (Moon)


def drekkana_sign_index(longitude: float) -> int:
    """D3. Each 30° sign splits into three 10° decans: the 1st decan stays
    the sign itself, the 2nd maps to the 5th sign from it, the 3rd to the
    9th sign from it — the classical trikona (own/5th/9th) pattern, which
    reduces to the closed form (rasi + decan*4) % 12 (decan*4 = 0/4/8, i.e.
    the 5th and 9th signs are 4 and 8 positions ahead)."""
    rasi = sign_index(longitude)
    decan = int(degree_in_sign(longitude) // 10)
    return (rasi + decan * 4) % 12


def saptamsa_sign_index(longitude: float) -> int:
    """D7. Each 30° sign splits into seven parts of 30/7 degrees. Classical
    rule: an odd sign counts its 7 parts starting from itself; an even sign
    starts from the 7th sign from itself (its own opposite sign) — same
    "odd starts from itself, even starts elsewhere" convention as D10
    (app.astro.charts.dashamsa_sign_index), just a different offset (+6
    here vs +8 there)."""
    rasi = sign_index(longitude)
    part = int(degree_in_sign(longitude) // (30 / 7))
    starting_sign = rasi if rasi % 2 == 0 else (rasi + 6) % 12
    return (starting_sign + part) % 12


def dwadashamsa_sign_index(longitude: float) -> int:
    """D12. Each 30° sign splits into twelve 2.5° parts, always counted
    starting from the sign itself regardless of odd/even — the simplest of
    the seven Saptavargaja vargas, no branching rule at all."""
    rasi = sign_index(longitude)
    part = int(degree_in_sign(longitude) // 2.5)
    return (rasi + part) % 12


# D30. Unlike every varga above, Trimshamsa does NOT divide a sign into
# equal parts, and the resulting sign is not offset-from-the-original the
# way D3/D7/D12 are — each unequal degree range within the sign is ruled by
# one of the five classical planets (Mars/Saturn/Jupiter/Mercury/Venus; the
# Sun and Moon never rule a Trimshamsa portion), and the resulting D30 sign
# is simply THAT PLANET'S OWN SIGN OF THE SAME PARITY as the sign being
# divided (e.g. Mars maps to Aries — his odd-numbered own sign — inside any
# odd sign's Trimshamsa, but to Scorpio — his even-numbered own sign —
# inside any even sign's). Odd-sign ranges/rulers and their mirrored
# even-sign counterparts (same ranges, reversed ruler order) per Brihat
# Parashara Hora Shastra:
#   Odd:  Mars 0-5, Saturn 5-10, Jupiter 10-18, Mercury 18-25, Venus 25-30
#   Even: Venus 0-5, Mercury 5-12, Jupiter 12-20, Saturn 20-25, Mars 25-30
# verified against a secondary published source, not reconstructed from
# memory alone (see PR discussion / research notes for this feature).
_ODD_SIGN_TRIMSHAMSA = [
    (5, "Ma", 0), (10, "Sa", 10), (18, "Ju", 8), (25, "Me", 2), (30, "Ve", 6),
]
_EVEN_SIGN_TRIMSHAMSA = [
    (5, "Ve", 1), (12, "Me", 5), (20, "Ju", 11), (25, "Sa", 9), (30, "Ma", 7),
]


def trimshamsa_sign_index(longitude: float) -> int:
    rasi = sign_index(longitude)
    degree = degree_in_sign(longitude)
    table = _ODD_SIGN_TRIMSHAMSA if rasi % 2 == 0 else _EVEN_SIGN_TRIMSHAMSA
    for upper_bound, _ruler, resulting_sign in table:
        if degree < upper_bound:
            return resulting_sign
    return table[-1][2]  # degree == 30.0 edge case (shouldn't occur in practice)
