"""Distribution functions for inferential statistics.

The BRD asks for statistical analyses "both descriptive and inferential"
(p. 16). Descriptive statistics are computed in PostgreSQL, where the data is.
Inferential statistics additionally need p-values and confidence intervals,
which means evaluating the normal, chi-square and Student-t distributions.

WHY THIS FILE EXISTS RATHER THAN ``import scipy``

numpy/scipy happen to be importable in this environment but appear in no
requirements file, so relying on them would add an undeclared dependency to a
federal deployment — the kind of thing that passes locally and fails an ATO
review. Everything here is stdlib ``math``.

The three algorithms below (incomplete gamma by series/continued fraction,
incomplete beta by Lentz's continued fraction) are the standard ones; they are
accurate to roughly 1e-14 relative, far beyond what a p-value reported to four
decimal places needs. They are written out rather than approximated because a
p-value that is merely close is a p-value that can cross 0.05 in the wrong
direction, and this module's numbers end up in analysis that informs
rulemaking.
"""
from __future__ import annotations

import math

__all__ = [
    "norm_cdf",
    "norm_sf",
    "norm_ppf",
    "chi2_sf",
    "student_t_sf",
    "two_tailed_normal_p",
    "two_tailed_t_p",
]

# Iteration caps for the two continued fractions. Both converge in well under
# 100 iterations across the domain we use; the cap only prevents a pathological
# input from spinning.
_MAX_ITER = 300
_EPS = 3.0e-16
_TINY = 1.0e-300


# ---------------------------------------------------------------------------
# Normal
# ---------------------------------------------------------------------------
def norm_cdf(z: float) -> float:
    """P(Z <= z) for the standard normal, via the error function."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def norm_sf(z: float) -> float:
    """P(Z > z). Uses erfc rather than 1 - cdf so the far right tail keeps its
    significant digits instead of cancelling against 1.0."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def norm_ppf(p: float) -> float:
    """Inverse standard normal CDF.

    Bisection on ``norm_cdf`` rather than a rational approximation: this is
    called once per confidence interval (to turn 0.95 into 1.959964), never in a
    loop, so ~60 cheap iterations for full double precision is the right trade
    against carrying a table of magic coefficients nobody can check by eye.
    """
    if not 0.0 < p < 1.0:
        raise ValueError("norm_ppf requires 0 < p < 1")
    lo, hi = -40.0, 40.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if norm_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-15:
            break
    return (lo + hi) / 2.0


def two_tailed_normal_p(z: float) -> float:
    """Two-sided p-value for a z statistic."""
    return 2.0 * norm_sf(abs(z))


# ---------------------------------------------------------------------------
# Incomplete gamma -> chi-square
# ---------------------------------------------------------------------------
def _gamma_p_series(a: float, x: float) -> float:
    """Regularized lower incomplete gamma P(a,x) by series. Converges fast for
    x < a+1."""
    ap = a
    total = 1.0 / a
    delta = total
    for _ in range(_MAX_ITER):
        ap += 1.0
        delta *= x / ap
        total += delta
        if abs(delta) < abs(total) * _EPS:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gamma_q_continued_fraction(a: float, x: float) -> float:
    """Regularized upper incomplete gamma Q(a,x) by continued fraction
    (modified Lentz). Converges fast for x >= a+1."""
    b = x + 1.0 - a
    c = 1.0 / _TINY
    d = 1.0 / b
    h = d
    for i in range(1, _MAX_ITER + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < _TINY:
            d = _TINY
        c = b + an / c
        if abs(c) < _TINY:
            c = _TINY
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def chi2_sf(x: float, df: int) -> float:
    """Upper-tail probability P(X > x) for chi-square with ``df`` degrees of
    freedom — i.e. the p-value of a chi-square statistic."""
    if df <= 0:
        raise ValueError("chi2_sf requires df >= 1")
    if x <= 0:
        return 1.0
    a = df / 2.0
    y = x / 2.0
    if y < a + 1.0:
        return 1.0 - _gamma_p_series(a, y)
    return _gamma_q_continued_fraction(a, y)


# ---------------------------------------------------------------------------
# Incomplete beta -> Student t
# ---------------------------------------------------------------------------
def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (modified Lentz)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _TINY:
        d = _TINY
    d = 1.0 / d
    h = d
    for m in range(1, _MAX_ITER + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < _TINY:
            d = _TINY
        c = 1.0 + aa / c
        if abs(c) < _TINY:
            c = _TINY
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < _TINY:
            d = _TINY
        c = 1.0 + aa / c
        if abs(c) < _TINY:
            c = _TINY
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            break
    return h


def _betainc_reg(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a,b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log(1.0 - x)
    )
    # The continued fraction converges only on the left of the symmetry point;
    # reflect when x is past it.
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def student_t_sf(t: float, df: float) -> float:
    """Upper-tail probability P(T > t) for Student's t with ``df`` degrees of
    freedom. ``df`` is float because Welch's test produces fractional df."""
    if df <= 0:
        raise ValueError("student_t_sf requires df > 0")
    x = df / (df + t * t)
    tail = 0.5 * _betainc_reg(df / 2.0, 0.5, x)
    return tail if t > 0 else 1.0 - tail


def two_tailed_t_p(t: float, df: float) -> float:
    """Two-sided p-value for a t statistic with ``df`` degrees of freedom."""
    if df <= 0:
        return float("nan")
    return _betainc_reg(df / 2.0, 0.5, df / (df + t * t))
