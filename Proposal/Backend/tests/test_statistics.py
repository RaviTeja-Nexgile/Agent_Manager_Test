"""Unit tests for the statistical machinery behind the BRD's named methods.

These test the *mathematics*, not the API, and they deliberately need no
database: a wrong p-value is a wrong finding, and that failure should be
catchable in milliseconds rather than only through a full-stack run against the
remote PostgreSQL instance.

Every expected value below was cross-checked against SciPy
(``scipy.stats.chi2.sf``, ``scipy.stats.t.sf``, ``scipy.stats.norm.ppf``,
``scipy.stats.fisher_exact``) and is pinned here as a literal. SciPy is
deliberately *not* imported — it is not in requirements.txt, so a test that
imported it would pass locally and fail in a clean deployment, which is exactly
the trap ``app.core.statsmath`` exists to avoid.
"""
from __future__ import annotations

import math

import pytest

from app.core.statsmath import (
    chi2_sf,
    norm_cdf,
    norm_ppf,
    norm_sf,
    student_t_sf,
    two_tailed_normal_p,
    two_tailed_t_p,
)
from app.workers.statistics import _fisher_exact_two_sided

TOL = 1e-10


# ---------------------------------------------------------------------------
# Normal
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "z,expected",
    [
        (0.0, 0.5),
        (1.0, 0.8413447460685429),
        (1.959963984540054, 0.975),
        (-2.0, 0.022750131948179195),
        (3.0, 0.9986501019683699),
    ],
)
def test_norm_cdf(z, expected):
    assert norm_cdf(z) == pytest.approx(expected, abs=TOL)


def test_norm_sf_keeps_far_tail_precision():
    """1 - cdf(8) cancels to 0 in double precision; erfc does not."""
    assert norm_sf(8.0) == pytest.approx(6.220960574271786e-16, rel=1e-9)
    assert norm_sf(8.0) > 0


@pytest.mark.parametrize(
    "p,expected",
    [
        (0.5, 0.0),
        (0.9, 1.2815515655446004),
        (0.95, 1.6448536269514722),
        (0.975, 1.959963984540054),
        (0.995, 2.5758293035489004),
    ],
)
def test_norm_ppf(p, expected):
    assert norm_ppf(p) == pytest.approx(expected, abs=1e-9)


def test_norm_ppf_rejects_out_of_range():
    for bad in (0.0, 1.0, -0.5, 1.5):
        with pytest.raises(ValueError):
            norm_ppf(bad)


def test_two_tailed_normal_p():
    assert two_tailed_normal_p(1.959963984540054) == pytest.approx(0.05, abs=1e-12)
    assert two_tailed_normal_p(0.0) == pytest.approx(1.0, abs=TOL)
    # Symmetric in the sign of z.
    assert two_tailed_normal_p(-2.4) == pytest.approx(two_tailed_normal_p(2.4), abs=TOL)


# ---------------------------------------------------------------------------
# Chi-square — exercises both the series and continued-fraction branches
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "x,df,expected",
    [
        (3.841458820694124, 1, 0.05),          # the classic 5% critical value
        (0.5, 1, 0.4795001221869535),          # series branch (x < a+1)
        (10.0, 1, 0.0015654022580026237),      # continued-fraction branch
        (2.0, 2, 0.36787944117144233),         # exactly exp(-1)
        (15.0, 5, 0.010362337911415677),
        (0.1, 3, 0.9918374237319115),
        (50.0, 10, 2.669083424903988e-07),
        (100.0, 1, 1.5239706048319807e-23),    # far tail stays finite and positive
    ],
)
def test_chi2_sf(x, df, expected):
    assert chi2_sf(x, df) == pytest.approx(expected, rel=1e-9, abs=1e-300)


def test_chi2_sf_edges():
    assert chi2_sf(0.0, 1) == 1.0
    assert chi2_sf(-5.0, 3) == 1.0
    with pytest.raises(ValueError):
        chi2_sf(1.0, 0)


# ---------------------------------------------------------------------------
# Student t — including the fractional df Welch's test produces
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "t,df,expected",
    [
        (2.0, 10, 0.07338803477136584),
        (1.96, 1000, 0.05027318495570206),
        (0.5, 3, 0.6514479648476431),
        (4.2, 7.34, 0.0036305419259954176),    # fractional df
        (0.0, 5, 1.0),
        (3.1, 2.5, 0.06778837832480832),
    ],
)
def test_two_tailed_t_p(t, df, expected):
    assert two_tailed_t_p(t, df) == pytest.approx(expected, rel=1e-9)


def test_t_is_symmetric():
    assert two_tailed_t_p(-2.0, 10) == pytest.approx(two_tailed_t_p(2.0, 10), abs=TOL)


def test_student_t_sf_halves_at_zero():
    assert student_t_sf(0.0, 7) == pytest.approx(0.5, abs=TOL)


def test_t_approaches_normal_as_df_grows():
    """With large df the t distribution is the normal one; if the incomplete-beta
    branch were wrong these would diverge."""
    assert two_tailed_t_p(1.96, 5_000_000) == pytest.approx(
        two_tailed_normal_p(1.96), abs=1e-6
    )


# ---------------------------------------------------------------------------
# Fisher's exact test
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "table,expected",
    [
        ((2, 24, 4, 10), 0.15908013276379242),
        ((0, 4, 2, 24), 1.0),
        ((5, 20, 10, 15), 0.21653421943076983),
        ((1, 1, 1, 1), 1.0),
        ((12, 8, 3, 17), 0.007911693673868787),
        ((3, 1, 1, 3), 0.4857142857142857),     # Fisher's tea-tasting table
    ],
)
def test_fisher_exact(table, expected):
    assert _fisher_exact_two_sided(*table) == pytest.approx(expected, rel=1e-9)


def test_fisher_exact_degenerate_margins():
    """Exposure absent from both arms, or universal in both: only one table has
    these margins, so p = 1 rather than NaN."""
    assert _fisher_exact_two_sided(0, 10, 0, 10) == 1.0
    assert _fisher_exact_two_sided(10, 0, 10, 0) == 1.0


def test_fisher_exact_empty_arm_is_nan():
    """An empty cohort is not a degenerate table, it is an unanswerable question."""
    assert math.isnan(_fisher_exact_two_sided(0, 0, 5, 5))
    assert math.isnan(_fisher_exact_two_sided(5, 5, 0, 0))


def test_fisher_exact_is_symmetric_under_row_swap():
    assert _fisher_exact_two_sided(2, 24, 4, 10) == pytest.approx(
        _fisher_exact_two_sided(4, 10, 2, 24), rel=1e-12
    )


# ---------------------------------------------------------------------------
# Odds ratio / Woolf interval, as risk_model computes them
# ---------------------------------------------------------------------------
def test_odds_ratio_and_woolf_interval():
    """Hand-checked against the 2x2 the seeded cohorts actually produce."""
    a, b, c, d = 2, 24, 4, 10
    odds_ratio = (a * d) / (b * c)
    assert odds_ratio == pytest.approx(20 / 96)

    se = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    z = norm_ppf(0.975)
    assert math.exp(math.log(odds_ratio) - z * se) == pytest.approx(0.03273, abs=1e-5)
    assert math.exp(math.log(odds_ratio) + z * se) == pytest.approx(1.32597, abs=1e-5)


def test_haldane_correction_pulls_estimate_toward_one():
    """A zero cell makes the raw odds ratio undefined; +0.5 to every cell defines
    it and biases it toward 1, which is why risk_model discloses it."""
    a, b, c, d = 2, 24, 0, 4
    corrected = ((a + 0.5) * (d + 0.5)) / ((b + 0.5) * (c + 0.5))
    assert corrected == pytest.approx(0.9183673469387755, rel=1e-12)
    assert 0.5 < corrected < 2.0


# ---------------------------------------------------------------------------
# Yates-corrected chi-square
# ---------------------------------------------------------------------------
def test_chi_square_with_yates_matches_reference():
    a, b, c, d = 40, 60, 25, 75
    total = a + b + c + d
    chi = total * (abs(a * d - b * c) - total / 2) ** 2 / (
        (a + b) * (c + d) * (a + c) * (b + d)
    )
    assert chi == pytest.approx(4.467236467236467, rel=1e-12)
    assert chi2_sf(chi, 1) == pytest.approx(0.03455083095061162, rel=1e-9)
