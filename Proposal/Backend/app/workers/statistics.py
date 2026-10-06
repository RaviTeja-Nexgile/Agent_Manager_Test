"""Statistical methods over Analysis Environment cohorts.

Implements the four method families the January 2026 BRD names (p. 16) plus the
inferential machinery it asks for in the same sentence:

    "descriptive, exploratory, and statistical analyses (both descriptive and
     inferential) ... central tendency and dispersion, data distributions,
     thematic analysis, and statistical risk modeling (given the availability of
     control such as non-fatal crashes)."

    central tendency and dispersion  ->  :func:`describe`
    data distributions               ->  :func:`distribution`
    thematic analysis                ->  :func:`thematic`
    statistical risk modeling        ->  :func:`risk_model`
    (comparative / trend, which the gap analysis calls out as expected of
     analysts)                       ->  :func:`compare`, :func:`trend`

Two conventions run through all of them.

**Aggregation happens in PostgreSQL.** The BRD wants large datasets handled
"with low performance impact", and pulling a cohort into Python to average it
would put the row count in the API process's memory. Python only ever sees
already-reduced quantities — counts, sums, moments — and turns them into test
statistics.

**Every result carries ``caveats``.** A statistic computed over five crashes is
arithmetically fine and analytically worthless, and the failure mode of a
statistics feature is not a crash — it is a confident number that nobody
questions. So each method states in its own output when n is too small, when a
zero cell forced a continuity correction, when a chi-square was abandoned for
Fisher's exact test, and when a distribution is too skewed for the mean to be
the right summary. These are part of the result, not logging.
"""
from __future__ import annotations

import math
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.statsmath import (
    chi2_sf,
    norm_ppf,
    two_tailed_normal_p,
    two_tailed_t_p,
)

# ---------------------------------------------------------------------------
# Analysis variable vocabulary. As everywhere else in this tier, a caller-
# supplied name is resolved through an allow-list before it reaches SQL; these
# are physical columns of analysis_cohort_members, never interpolated text.
# ---------------------------------------------------------------------------
NUMERIC_VARIABLES: dict[str, str] = {
    "num_fatalities": "Fatalities",
    "num_vehicles": "Vehicles involved",
    "num_persons": "Persons involved",
    "crash_year": "Crash year",
    "crash_month": "Crash month",
}

CATEGORICAL_VARIABLES: dict[str, str] = {
    "state_code": "State",
    "county": "County",
    "lifecycle_phase": "Lifecycle phase",
    "scope": "Study scope",
    "is_qualifying": "Qualifying crash",
    "is_fatal": "Fatal crash",
    "crash_year": "Crash year",
    "crash_month": "Crash month",
}

# Time buckets for trend analysis.
TREND_PERIODS: dict[str, str] = {
    "YEAR": "crash_year",
    "MONTH": "crash_month",
}

HISTOGRAM_BINS = 10

# Below this, a summary statistic is reported but flagged. Not a suppression
# threshold — every holder of analysis_stats:run is a CCFP analyst with PII
# access — but an analytic-validity one. Thirty is the conventional point at
# which a sample mean's sampling distribution is treated as approximately
# normal, which is the assumption the confidence intervals below rest on.
SMALL_SAMPLE = 30
# A 2x2 cell expected count below 5 invalidates the chi-square approximation;
# the standard response is Fisher's exact test, which this module computes.
MIN_EXPECTED_CELL = 5


class StatisticsError(ValueError):
    """A statistical request is not answerable as asked."""


# ---------------------------------------------------------------------------
# Shared plumbing
# ---------------------------------------------------------------------------
def _scope_clause(allowed_states: list[str] | None, params: dict) -> str:
    """State scope for the member table.

    ``analysis_stats:run`` is currently granted only to CCFP-internal roles, all
    of which are unscoped, so in practice this is a no-op today. It is applied
    anyway: the permission grant is a row in a table that a future migration can
    change, and a scoping rule that only holds because nobody currently has the
    permission is not a scoping rule.
    """
    if not allowed_states:
        return ""
    params["states"] = list(allowed_states)
    return " AND state_code = ANY(:states)"


def _f(value: Any) -> float | None:
    return None if value is None else float(value)


def _ci_z(confidence: float) -> float:
    if not 0.5 < confidence < 1.0:
        raise StatisticsError("confidence must be between 0.5 and 1.0")
    return norm_ppf(1.0 - (1.0 - confidence) / 2.0)


# ---------------------------------------------------------------------------
# Central tendency and dispersion
# ---------------------------------------------------------------------------
def describe(
    db: Session,
    version_id: uuid.UUID,
    variable: str,
    allowed_states: list[str] | None = None,
    confidence: float = 0.95,
) -> dict:
    """Central tendency and dispersion for one numeric variable.

    Everything is computed in a single round trip. The third and fourth central
    moments are taken against the mean computed in the same statement (rather
    than from raw power sums) because the raw-moment shortcut loses most of its
    significant digits to cancellation when the mean is large relative to the
    spread — ``crash_year`` is exactly that case, and it would have produced a
    plausible-looking but wrong skewness.
    """
    if variable not in NUMERIC_VARIABLES:
        raise StatisticsError(
            f"Unknown numeric variable '{variable}'. Allowed: {sorted(NUMERIC_VARIABLES)}"
        )
    params: dict[str, Any] = {"version_id": str(version_id)}
    scope = _scope_clause(allowed_states, params)
    z = _ci_z(confidence)

    row = db.execute(
        text(
            f"""
            WITH members AS (
                SELECT {variable} AS v
                  FROM analysis_cohort_members
                 WHERE version_id = :version_id{scope}
            ),
            vals AS (SELECT v FROM members WHERE v IS NOT NULL),
            agg AS (
                SELECT count(*)                                        AS n,
                       avg(v::numeric)                                 AS mean,
                       stddev_samp(v::numeric)                         AS sd,
                       stddev_pop(v::numeric)                          AS sd_pop,
                       var_samp(v::numeric)                            AS variance,
                       min(v)                                          AS minimum,
                       max(v)                                          AS maximum,
                       sum(v::numeric)                                 AS total,
                       percentile_cont(0.10) WITHIN GROUP (ORDER BY v) AS p10,
                       percentile_cont(0.25) WITHIN GROUP (ORDER BY v) AS p25,
                       percentile_cont(0.50) WITHIN GROUP (ORDER BY v) AS median,
                       percentile_cont(0.75) WITHIN GROUP (ORDER BY v) AS p75,
                       percentile_cont(0.90) WITHIN GROUP (ORDER BY v) AS p90,
                       mode() WITHIN GROUP (ORDER BY v)                AS modal_value
                  FROM vals
            )
            SELECT agg.*,
                   (SELECT count(*) FROM members WHERE v IS NULL) AS n_missing,
                   (SELECT sum(power((vals.v::numeric - agg.mean) / nullif(agg.sd, 0), 3))
                      FROM vals) AS m3,
                   (SELECT sum(power((vals.v::numeric - agg.mean) / nullif(agg.sd, 0), 4))
                      FROM vals) AS m4
              FROM agg
            """
        ),
        params,
    ).mappings().one()

    n = int(row["n"] or 0)
    out: dict[str, Any] = {
        "variable": variable,
        "label": NUMERIC_VARIABLES[variable],
        "n": n,
        "n_missing": int(row["n_missing"] or 0),
        "mean": _f(row["mean"]),
        "median": _f(row["median"]),
        "mode": _f(row["modal_value"]),
        "stddev": _f(row["sd"]),
        "stddev_population": _f(row["sd_pop"]),
        "variance": _f(row["variance"]),
        "minimum": _f(row["minimum"]),
        "maximum": _f(row["maximum"]),
        "total": _f(row["total"]),
        "p10": _f(row["p10"]),
        "p25": _f(row["p25"]),
        "p75": _f(row["p75"]),
        "p90": _f(row["p90"]),
        "confidence": confidence,
    }
    caveats: list[str] = []

    if n == 0:
        caveats.append("No non-null values for this variable in the cohort.")
        out["caveats"] = caveats
        return out

    if out["minimum"] is not None and out["maximum"] is not None:
        out["range"] = out["maximum"] - out["minimum"]
    if out["p25"] is not None and out["p75"] is not None:
        out["iqr"] = out["p75"] - out["p25"]

    mean, sd = out["mean"], out["stddev"]
    # Coefficient of variation is only meaningful on a ratio scale with a
    # non-zero mean; crash_year has an arbitrary origin, so it is skipped there
    # rather than reported as a meaningless 0.0002.
    if sd is not None and mean not in (None, 0) and variable != "crash_year":
        out["coefficient_of_variation"] = sd / mean
    if sd is not None and n > 1:
        sem = sd / math.sqrt(n)
        out["standard_error"] = sem
        # Normal-approximation interval. Flagged below when n is small enough
        # that the approximation is doing real work.
        out["ci_lower"] = mean - z * sem
        out["ci_upper"] = mean + z * sem

    # Shape. Fisher-Pearson adjusted sample skewness and excess kurtosis; both
    # need enough degrees of freedom for their bias corrections to be defined.
    m3, m4 = _f(row["m3"]), _f(row["m4"])
    if m3 is not None and n > 2 and sd:
        out["skewness"] = (n / ((n - 1) * (n - 2))) * m3
    if m4 is not None and n > 3 and sd:
        out["kurtosis_excess"] = (
            (n * (n + 1)) / ((n - 1) * (n - 2) * (n - 3)) * m4
            - 3.0 * (n - 1) ** 2 / ((n - 2) * (n - 3))
        )

    if n < SMALL_SAMPLE:
        caveats.append(
            f"n = {n} is below {SMALL_SAMPLE}; the confidence interval relies on a "
            "normal approximation that is not reliable at this sample size. Treat "
            "it as indicative only."
        )
    if sd == 0:
        caveats.append("Every value is identical; dispersion statistics are all zero.")
    skew = out.get("skewness")
    if skew is not None and abs(skew) > 1.0:
        caveats.append(
            f"Distribution is strongly skewed (skewness {skew:.2f}); the median "
            f"({out['median']}) describes the typical crash better than the mean."
        )
    if out["n_missing"]:
        caveats.append(
            f"{out['n_missing']} member(s) had no value recorded and were excluded."
        )
    out["caveats"] = caveats
    return out


# ---------------------------------------------------------------------------
# Data distributions
# ---------------------------------------------------------------------------
def distribution(
    db: Session,
    version_id: uuid.UUID,
    variable: str,
    allowed_states: list[str] | None = None,
    bins: int = HISTOGRAM_BINS,
) -> dict:
    """Frequency distribution for a categorical variable, or a histogram for a
    numeric one.

    The BRD asks for "data distributions" without qualifying the variable type,
    and the two cases genuinely need different answers: a frequency table with
    cumulative percentages for categories, a binned histogram for measurements.
    Dispatching on the variable rather than making the caller choose keeps a
    distribution of ``state_code`` from silently coming back as ten numeric bins.
    """
    kind = "CATEGORICAL" if variable in CATEGORICAL_VARIABLES else None
    if variable in NUMERIC_VARIABLES and variable not in ("crash_year", "crash_month"):
        kind = "NUMERIC"
    if kind is None:
        allowed = sorted({*CATEGORICAL_VARIABLES, *NUMERIC_VARIABLES})
        raise StatisticsError(f"Unknown variable '{variable}'. Allowed: {allowed}")

    params: dict[str, Any] = {"version_id": str(version_id)}
    scope = _scope_clause(allowed_states, params)

    if kind == "CATEGORICAL":
        rows = db.execute(
            text(
                f"""
                SELECT COALESCE({variable}::text, '(not recorded)') AS category,
                       count(*) AS frequency
                  FROM analysis_cohort_members
                 WHERE version_id = :version_id{scope}
                 GROUP BY 1
                 ORDER BY frequency DESC, category
                """
            ),
            params,
        ).mappings().all()
        total = sum(int(r["frequency"]) for r in rows)
        entries = []
        cumulative = 0
        for r in rows:
            freq = int(r["frequency"])
            cumulative += freq
            entries.append(
                {
                    "category": r["category"],
                    "frequency": freq,
                    "percent": (freq / total * 100.0) if total else 0.0,
                    "cumulative_percent": (cumulative / total * 100.0) if total else 0.0,
                }
            )
        caveats = []
        if total == 0:
            caveats.append("The cohort has no members.")
        elif len(entries) == 1:
            caveats.append(
                "Every member falls in a single category; this variable does not "
                "discriminate within this cohort."
            )
        rare = [e["category"] for e in entries if 0 < e["frequency"] < MIN_EXPECTED_CELL]
        if rare:
            caveats.append(
                f"{len(rare)} category/categories have fewer than {MIN_EXPECTED_CELL} "
                "members; percentages for them are unstable."
            )
        return {
            "variable": variable,
            "label": CATEGORICAL_VARIABLES.get(variable, variable),
            "kind": kind,
            "n": total,
            "distinct_categories": len(entries),
            "entries": entries,
            "histogram": [],
            "caveats": caveats,
        }

    # Numeric: bin with width_bucket, which pushes the maximum into bin n+1;
    # that overflow bin is folded back into the top bin so the counts sum to n.
    bins = max(2, min(int(bins), 50))
    bounds = db.execute(
        text(
            f"""
            SELECT count({variable}) AS n, min({variable}) AS lo, max({variable}) AS hi
              FROM analysis_cohort_members
             WHERE version_id = :version_id{scope}
            """
        ),
        params,
    ).mappings().one()
    n, lo, hi = int(bounds["n"] or 0), _f(bounds["lo"]), _f(bounds["hi"])
    if not n or lo is None or hi is None:
        return {
            "variable": variable,
            "label": NUMERIC_VARIABLES[variable],
            "kind": kind,
            "n": 0,
            "distinct_categories": 0,
            "entries": [],
            "histogram": [],
            "caveats": ["The cohort has no values for this variable."],
        }

    caveats = []
    if hi > lo:
        counts = {
            int(r["bucket"]): int(r["c"])
            for r in db.execute(
                text(
                    f"""
                    SELECT width_bucket({variable}::numeric, :lo, :hi, :bins) AS bucket,
                           count(*) AS c
                      FROM analysis_cohort_members
                     WHERE version_id = :version_id AND {variable} IS NOT NULL{scope}
                     GROUP BY bucket ORDER BY bucket
                    """
                ),
                {**params, "lo": lo, "hi": hi, "bins": bins},
            ).mappings().all()
        }
        width = (hi - lo) / bins
        histogram = [
            {
                "bin": i,
                "lower": round(lo + (i - 1) * width, 4),
                "upper": round(lo + i * width, 4),
                "count": counts.get(i, 0) + (counts.get(bins + 1, 0) if i == bins else 0),
            }
            for i in range(1, bins + 1)
        ]
    else:
        histogram = [{"bin": 1, "lower": lo, "upper": hi, "count": n}]
        caveats.append("Every value is identical; the histogram is a single bin.")

    # A discrete count variable with few distinct values reads far better as a
    # frequency table than as bins, so provide both rather than making the
    # analyst re-ask the question.
    entries = [
        {
            "category": str(r["category"]),
            "frequency": int(r["frequency"]),
            "percent": int(r["frequency"]) / n * 100.0,
            "cumulative_percent": 0.0,
        }
        for r in db.execute(
            text(
                f"""
                SELECT {variable}::text AS category, count(*) AS frequency
                  FROM analysis_cohort_members
                 WHERE version_id = :version_id AND {variable} IS NOT NULL{scope}
                 -- Group and order by the COLUMN, not by the projected text. A
                 -- `GROUP BY 1` here groups by the ::text expression, which
                 -- leaves the raw column outside the grouping and makes the
                 -- numeric ORDER BY invalid. Ordering by the column also keeps
                 -- 2 before 10, which ordering by text would not.
                 GROUP BY {variable} ORDER BY {variable}
                """
            ),
            params,
        ).mappings().all()
    ]
    running = 0.0
    for entry in entries:
        running += entry["percent"]
        entry["cumulative_percent"] = running

    if n < SMALL_SAMPLE:
        caveats.append(f"n = {n}; the shape of this distribution is not well determined.")
    return {
        "variable": variable,
        "label": NUMERIC_VARIABLES[variable],
        "kind": kind,
        "n": n,
        "distinct_categories": len(entries),
        "entries": entries,
        "histogram": histogram,
        "caveats": caveats,
    }


# ---------------------------------------------------------------------------
# Thematic analysis
# ---------------------------------------------------------------------------
def thematic(
    db: Session,
    version_id: uuid.UUID,
    allowed_states: list[str] | None = None,
    min_support: int = 1,
    top_n: int = 25,
) -> dict:
    """Recurring contributing-factor themes and the pairs that co-occur.

    "Thematic analysis" in the BRD's sense is finding what recurs across crashes
    and what travels together. Three layers are returned:

    * **themes** — how often each contributing factor appears, as a share of
      crashes rather than of selections, so a crash with four factors does not
      count four times toward the denominator;
    * **groups** — the same at contributing-factor-group level, which is the
      granularity a causal narrative is usually written at;
    * **co_occurrence** — factor pairs, with **lift**. Lift is the ratio of the
      observed joint rate to the rate expected if the two were independent, so
      lift > 1 means the pair appears together more often than chance. Raw pair
      counts alone are dominated by whichever factors are individually common,
      which is precisely the pattern an analyst already knows about.

    Lift is an association measure, not a causal one. The BRD asks analysts to
    "identify patterns and causal relationships"; this delivers the pattern half
    honestly and leaves causation to the investigator, which is the only
    defensible split — nothing in observational crash data licenses a causal
    claim from co-occurrence alone. That is stated in the caveats so it travels
    with the numbers.
    """
    params: dict[str, Any] = {"version_id": str(version_id)}
    scope = _scope_clause(allowed_states, params)
    top_n = max(1, min(int(top_n), 200))
    min_support = max(1, int(min_support))

    total = int(
        db.scalar(
            text(
                f"""SELECT count(*) FROM analysis_cohort_members
                     WHERE version_id = :version_id{scope}"""
            ),
            params,
        )
        or 0
    )
    with_factors = int(
        db.scalar(
            text(
                f"""SELECT count(*) FROM analysis_cohort_members
                     WHERE version_id = :version_id AND cardinality(factors) > 0{scope}"""
            ),
            params,
        )
        or 0
    )

    themes = [
        {
            "factor": r["factor"],
            "crashes": int(r["crashes"]),
            "percent_of_cohort": int(r["crashes"]) / total * 100.0 if total else 0.0,
            "percent_of_coded": int(r["crashes"]) / with_factors * 100.0 if with_factors else 0.0,
        }
        for r in db.execute(
            text(
                f"""
                SELECT f AS factor, count(*) AS crashes
                  FROM analysis_cohort_members m, unnest(m.factors) AS f
                 WHERE m.version_id = :version_id{scope}
                 GROUP BY f
                HAVING count(*) >= :min_support
                 ORDER BY crashes DESC, factor
                 LIMIT :top_n
                """
            ),
            {**params, "min_support": min_support, "top_n": top_n},
        ).mappings().all()
    ]

    groups = [
        {
            "group": r["grp"],
            "crashes": int(r["crashes"]),
            "percent_of_cohort": int(r["crashes"]) / total * 100.0 if total else 0.0,
        }
        for r in db.execute(
            text(
                f"""
                SELECT g AS grp, count(*) AS crashes
                  FROM analysis_cohort_members m, unnest(m.factor_groups) AS g
                 WHERE m.version_id = :version_id{scope}
                 GROUP BY g ORDER BY crashes DESC, grp
                """
            ),
            params,
        ).mappings().all()
    ]

    # Unordered pairs: `a < b` both de-duplicates (A,B)/(B,A) and drops the
    # self-pair, so each combination is counted once.
    pairs = db.execute(
        text(
            f"""
            SELECT a AS factor_a, b AS factor_b, count(*) AS crashes
              FROM analysis_cohort_members m,
                   unnest(m.factors) AS a,
                   unnest(m.factors) AS b
             WHERE m.version_id = :version_id AND a < b{scope}
             GROUP BY a, b
            HAVING count(*) >= :min_support
             ORDER BY crashes DESC, a, b
             LIMIT :top_n
            """
        ),
        {**params, "min_support": min_support, "top_n": top_n},
    ).mappings().all()

    theme_counts = {t["factor"]: t["crashes"] for t in themes}
    co_occurrence = []
    for r in pairs:
        a, b, joint = r["factor_a"], r["factor_b"], int(r["crashes"])
        na, nb = theme_counts.get(a), theme_counts.get(b)
        entry: dict[str, Any] = {
            "factor_a": a,
            "factor_b": b,
            "crashes": joint,
            "percent_of_cohort": joint / total * 100.0 if total else 0.0,
        }
        # Lift needs both marginals; they are absent only when a factor fell
        # below min_support or outside top_n, in which case the pair is reported
        # without a lift rather than with a wrong one.
        if total and na and nb:
            expected = (na / total) * (nb / total) * total
            entry["lift"] = joint / expected if expected else None
            entry["support_a"] = na
            entry["support_b"] = nb
        co_occurrence.append(entry)

    caveats: list[str] = []
    if total == 0:
        caveats.append("The cohort has no members.")
    elif with_factors == 0:
        caveats.append(
            "No member of this cohort has contributing factors recorded, so no "
            "themes can be identified. Contributing factors are captured during "
            "post-crash investigation; crashes still in earlier lifecycle phases "
            "will not have them yet."
        )
    else:
        coded_pct = with_factors / total * 100.0
        if coded_pct < 50.0:
            caveats.append(
                f"Only {with_factors} of {total} crashes ({coded_pct:.0f}%) have "
                "contributing factors recorded. Themes describe the coded subset, "
                "which may not be representative of the cohort."
            )
        if co_occurrence:
            caveats.append(
                "Lift measures association, not causation: a pair appearing "
                "together more often than chance does not establish that either "
                "factor caused the crash."
            )
        thin = [p for p in co_occurrence if p["crashes"] < MIN_EXPECTED_CELL]
        if thin:
            caveats.append(
                f"{len(thin)} co-occurrence pair(s) rest on fewer than "
                f"{MIN_EXPECTED_CELL} crashes; their lift values are volatile."
            )
    return {
        "n": total,
        "n_with_factors": with_factors,
        "coded_percent": with_factors / total * 100.0 if total else 0.0,
        "themes": themes,
        "groups": groups,
        "co_occurrence": co_occurrence,
        "caveats": caveats,
    }


# ---------------------------------------------------------------------------
# Statistical risk modeling
# ---------------------------------------------------------------------------
def _fisher_exact_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher's exact p for a 2x2 table.

    Sums the hypergeometric probabilities of every table with the same margins
    whose probability does not exceed the observed one — the conventional
    two-sided definition. Uses ``math.comb`` (exact integer arithmetic), so the
    result is right for the small cells this study actually produces, where the
    chi-square approximation is not.
    """
    row1, row2 = a + b, c + d
    col1, total = a + c, a + b + c + d
    if total == 0 or row1 == 0 or row2 == 0:
        return float("nan")
    if col1 == 0 or (b + d) == 0:
        # The exposure is absent from both cohorts, or universal in both. Only
        # one table has these margins, so it is by definition the most extreme
        # one and p = 1 — there is nothing to distinguish. Returning 1.0 rather
        # than NaN matches the standard convention and keeps the caller from
        # having to special-case a missing p-value; risk_model adds a caveat
        # saying the exposure did not vary.
        return 1.0

    denominator = math.comb(total, col1)

    def probability(a_i: int) -> float:
        return math.comb(row1, a_i) * math.comb(row2, col1 - a_i) / denominator

    observed = probability(a)
    lo = max(0, col1 - row2)
    hi = min(row1, col1)
    # 1e-7 relative tolerance absorbs float noise so a table that is exactly as
    # extreme as the observed one is not dropped by a last-bit comparison.
    return min(
        1.0,
        sum(
            probability(i)
            for i in range(lo, hi + 1)
            if probability(i) <= observed * (1.0 + 1e-7)
        ),
    )


def risk_model(
    db: Session,
    case_version_id: uuid.UUID,
    control_version_id: uuid.UUID,
    exposure_factor: str,
    allowed_states: list[str] | None = None,
    confidence: float = 0.95,
) -> dict:
    """Case-control risk model for one exposure, against a control population.

    This is the BRD line that could not be implemented before: "statistical risk
    modeling (given the availability of control such as non-fatal crashes)". The
    conditional is honoured literally — the caller must name a control cohort,
    and there is no code path that computes a risk estimate without one.

    Builds the 2x2 table

                        exposed   unexposed
        case cohort        a           b
        control cohort     c           d

    and reports the odds ratio (Woolf's log interval), relative risk, risk
    difference and attributable fraction. Which of those is meaningful depends
    on the design: in a true case-control sample the case:control ratio is fixed
    by the analyst, so the odds ratio is the only valid estimate and the relative
    risk is not interpretable. That is stated in the caveats rather than left for
    the reader to remember.
    """
    if case_version_id == control_version_id:
        raise StatisticsError(
            "The case and control cohorts are the same population; a risk model "
            "comparing a population with itself is not meaningful."
        )
    params: dict[str, Any] = {"factor": exposure_factor}
    scope = _scope_clause(allowed_states, params)

    def counts(version_id: uuid.UUID) -> tuple[int, int]:
        row = db.execute(
            text(
                f"""
                SELECT count(*) FILTER (WHERE :factor = ANY(factors)) AS exposed,
                       count(*) FILTER (WHERE NOT (:factor = ANY(factors))) AS unexposed
                  FROM analysis_cohort_members
                 WHERE version_id = :version_id{scope}
                """
            ),
            {**params, "version_id": str(version_id)},
        ).mappings().one()
        return int(row["exposed"] or 0), int(row["unexposed"] or 0)

    a, b = counts(case_version_id)
    c, d = counts(control_version_id)

    out: dict[str, Any] = {
        "exposure": exposure_factor,
        "confidence": confidence,
        "table": {
            "case_exposed": a,
            "case_unexposed": b,
            "control_exposed": c,
            "control_unexposed": d,
            "case_total": a + b,
            "control_total": c + d,
        },
    }
    caveats: list[str] = []

    if (a + b) == 0 or (c + d) == 0:
        caveats.append(
            "One of the two cohorts has no members, so no risk estimate can be "
            "computed. Refresh the environment, or widen the cohort definition."
        )
        out["caveats"] = caveats
        return out

    out["case_exposure_rate"] = a / (a + b)
    out["control_exposure_rate"] = c / (c + d)

    # An exposure that is absent from both cohorts (or present on every crash in
    # both) has no contrast to estimate. Every measure below would still compute
    # — to exactly 1.0, with a wide interval — and read as "no association
    # found", which is a different and misleading claim. Say what actually
    # happened instead.
    if (a + c) == 0 or (b + d) == 0:
        caveats.append(
            f"'{exposure_factor}' is "
            + ("recorded on no crash" if (a + c) == 0 else "recorded on every crash")
            + " in either cohort, so there is no contrast to estimate. No risk "
            "measure is reported. Check that the exposure is spelled as it "
            "appears in the contributing-factor catalog."
        )
        out["exposure_varies"] = False
        out["caveats"] = caveats
        return out
    out["exposure_varies"] = True

    # Haldane-Anscombe: a zero cell makes the odds ratio 0 or infinite and its
    # variance undefined. Adding 0.5 to every cell is the standard remedy and is
    # disclosed, because it materially shrinks the estimate toward 1 and a reader
    # comparing against a hand-computed OR needs to know it was applied.
    zero_cell = 0 in (a, b, c, d)
    aa, bb, cc, dd = (a + 0.5, b + 0.5, c + 0.5, d + 0.5) if zero_cell else (a, b, c, d)
    if zero_cell:
        caveats.append(
            "One or more cells of the 2x2 table is zero; a Haldane-Anscombe "
            "correction (+0.5 to every cell) was applied so the odds ratio and "
            "its interval are defined. The estimate is biased toward 1."
        )

    z = _ci_z(confidence)

    odds_ratio = (aa * dd) / (bb * cc)
    se_log_or = math.sqrt(1 / aa + 1 / bb + 1 / cc + 1 / dd)
    out["odds_ratio"] = odds_ratio
    out["odds_ratio_ci_lower"] = math.exp(math.log(odds_ratio) - z * se_log_or)
    out["odds_ratio_ci_upper"] = math.exp(math.log(odds_ratio) + z * se_log_or)

    risk_case = aa / (aa + bb)
    risk_control = cc / (cc + dd)
    relative_risk = risk_case / risk_control
    se_log_rr = math.sqrt(1 / aa - 1 / (aa + bb) + 1 / cc - 1 / (cc + dd))
    out["relative_risk"] = relative_risk
    out["relative_risk_ci_lower"] = math.exp(math.log(relative_risk) - z * se_log_rr)
    out["relative_risk_ci_upper"] = math.exp(math.log(relative_risk) + z * se_log_rr)

    risk_difference = risk_case - risk_control
    se_rd = math.sqrt(
        risk_case * (1 - risk_case) / (aa + bb) + risk_control * (1 - risk_control) / (cc + dd)
    )
    out["risk_difference"] = risk_difference
    out["risk_difference_ci_lower"] = risk_difference - z * se_rd
    out["risk_difference_ci_upper"] = risk_difference + z * se_rd

    # Attributable fraction among the exposed, from the relative risk.
    if relative_risk > 0:
        out["attributable_fraction_exposed"] = (relative_risk - 1.0) / relative_risk

    # Significance. Chi-square is only trustworthy when every expected cell is
    # at least 5; otherwise fall back to Fisher's exact test, which is valid at
    # any cell size. Both are reported when chi-square is admissible so a reader
    # can see they agree.
    total = a + b + c + d
    expected = [
        (a + b) * (a + c) / total,
        (a + b) * (b + d) / total,
        (c + d) * (a + c) / total,
        (c + d) * (b + d) / total,
    ]
    out["min_expected_cell"] = min(expected)
    fisher_p = _fisher_exact_two_sided(a, b, c, d)
    out["fisher_exact_p"] = None if math.isnan(fisher_p) else fisher_p

    if min(expected) >= MIN_EXPECTED_CELL:
        # Yates' continuity correction, conventional for a 2x2.
        numerator = total * (abs(a * d - b * c) - total / 2.0) ** 2
        denominator = (a + b) * (c + d) * (a + c) * (b + d)
        if denominator:
            chi_square = max(0.0, numerator / denominator)
            out["chi_square"] = chi_square
            out["chi_square_p"] = chi2_sf(chi_square, 1)
        out["p_value"] = out.get("chi_square_p")
        out["test_used"] = "CHI_SQUARE_YATES"
    else:
        out["p_value"] = out["fisher_exact_p"]
        out["test_used"] = "FISHER_EXACT"
        caveats.append(
            f"The smallest expected cell count is {min(expected):.2f}, below "
            f"{MIN_EXPECTED_CELL}, so the chi-square approximation does not hold. "
            "Fisher's exact test was used instead."
        )

    p = out.get("p_value")
    if p is not None and not math.isnan(p):
        out["significant"] = p < (1.0 - confidence)
    ci_lo, ci_hi = out["odds_ratio_ci_lower"], out["odds_ratio_ci_upper"]
    if ci_lo < 1.0 < ci_hi:
        caveats.append(
            "The odds-ratio confidence interval includes 1, so this exposure is "
            "not distinguishable from no association at this sample size."
        )
    if (a + b) < SMALL_SAMPLE or (c + d) < SMALL_SAMPLE:
        caveats.append(
            f"Case cohort n = {a + b}, control cohort n = {c + d}. Risk estimates "
            "from cohorts this small have very wide intervals and should not be "
            "cited as findings."
        )
    caveats.append(
        "In a case-control design the ratio of cases to controls is set by the "
        "analyst, not by nature, so the odds ratio is the interpretable estimate; "
        "the relative risk and risk difference shown alongside it are only valid "
        "if the two cohorts are a genuine random sample of one population."
    )
    caveats.append(
        "This is an unadjusted, single-exposure estimate. It controls for no "
        "confounders — State, road type, carrier and vehicle characteristics all "
        "differ between the cohorts unless the definitions matched on them."
    )
    out["caveats"] = caveats
    return out


# ---------------------------------------------------------------------------
# Comparative analysis
# ---------------------------------------------------------------------------
def compare(
    db: Session,
    version_a: uuid.UUID,
    version_b: uuid.UUID,
    variable: str,
    allowed_states: list[str] | None = None,
    confidence: float = 0.95,
) -> dict:
    """Compare one numeric variable between two cohorts.

    Welch's t-test rather than Student's: it does not assume the two populations
    share a variance, and the cohorts being compared here are routinely different
    sizes with different spreads (a fatal-crash cohort against a non-fatal
    control is exactly that). Welch is the safer default and costs nothing when
    the variances do happen to match.
    """
    if variable not in NUMERIC_VARIABLES:
        raise StatisticsError(
            f"Unknown numeric variable '{variable}'. Allowed: {sorted(NUMERIC_VARIABLES)}"
        )
    if version_a == version_b:
        raise StatisticsError("Cannot compare a cohort with itself.")

    def side(version_id: uuid.UUID) -> dict:
        params: dict[str, Any] = {"version_id": str(version_id)}
        scope = _scope_clause(allowed_states, params)
        row = db.execute(
            text(
                f"""
                SELECT count({variable}) AS n,
                       avg({variable}::numeric) AS mean,
                       stddev_samp({variable}::numeric) AS sd,
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY {variable}) AS median
                  FROM analysis_cohort_members
                 WHERE version_id = :version_id{scope}
                """
            ),
            params,
        ).mappings().one()
        return {
            "n": int(row["n"] or 0),
            "mean": _f(row["mean"]),
            "stddev": _f(row["sd"]),
            "median": _f(row["median"]),
        }

    a, b = side(version_a), side(version_b)
    out: dict[str, Any] = {
        "variable": variable,
        "label": NUMERIC_VARIABLES[variable],
        "confidence": confidence,
        "cohort_a": a,
        "cohort_b": b,
    }
    caveats: list[str] = []

    if a["n"] < 2 or b["n"] < 2:
        caveats.append(
            "At least one cohort has fewer than two values for this variable; a "
            "difference of means cannot be tested."
        )
        out["caveats"] = caveats
        return out

    out["mean_difference"] = a["mean"] - b["mean"]

    sa, sb = a["stddev"] or 0.0, b["stddev"] or 0.0
    var_a, var_b = sa**2 / a["n"], sb**2 / b["n"]
    se = math.sqrt(var_a + var_b)
    if se == 0:
        caveats.append(
            "Both cohorts have zero variance in this variable; no test statistic "
            "is defined."
        )
        out["caveats"] = caveats
        return out

    t_stat = (a["mean"] - b["mean"]) / se
    # Welch-Satterthwaite degrees of freedom.
    df = (var_a + var_b) ** 2 / (
        var_a**2 / (a["n"] - 1) + var_b**2 / (b["n"] - 1)
    )
    out["t_statistic"] = t_stat
    out["degrees_of_freedom"] = df
    out["p_value"] = two_tailed_t_p(t_stat, df)
    out["test_used"] = "WELCH_T"
    out["significant"] = out["p_value"] < (1.0 - confidence)

    z = _ci_z(confidence)
    out["difference_ci_lower"] = out["mean_difference"] - z * se
    out["difference_ci_upper"] = out["mean_difference"] + z * se

    # Cohen's d on the pooled SD. Reported because with cohorts this size a
    # difference can be significant and trivial, or large and non-significant,
    # and the p-value alone distinguishes neither.
    pooled = math.sqrt(
        ((a["n"] - 1) * sa**2 + (b["n"] - 1) * sb**2) / (a["n"] + b["n"] - 2)
    )
    if pooled:
        d = (a["mean"] - b["mean"]) / pooled
        out["cohens_d"] = d
        magnitude = (
            "negligible" if abs(d) < 0.2
            else "small" if abs(d) < 0.5
            else "medium" if abs(d) < 0.8
            else "large"
        )
        out["effect_size_magnitude"] = magnitude

    if a["n"] < SMALL_SAMPLE or b["n"] < SMALL_SAMPLE:
        caveats.append(
            f"Cohort sizes are {a['n']} and {b['n']}; below {SMALL_SAMPLE} the "
            "t-test relies on the variable being roughly normally distributed "
            "within each cohort, which crash counts often are not."
        )
    if not out.get("significant"):
        caveats.append(
            "The difference is not statistically significant at this confidence "
            "level. That is not evidence the cohorts are the same — with these "
            "sample sizes only a large difference could have been detected."
        )
    out["caveats"] = caveats
    return out


def compare_proportions(
    db: Session,
    version_a: uuid.UUID,
    version_b: uuid.UUID,
    factor: str,
    allowed_states: list[str] | None = None,
    confidence: float = 0.95,
) -> dict:
    """Compare the prevalence of one contributing factor between two cohorts."""
    if version_a == version_b:
        raise StatisticsError("Cannot compare a cohort with itself.")

    def side(version_id: uuid.UUID) -> tuple[int, int]:
        params: dict[str, Any] = {"version_id": str(version_id), "factor": factor}
        scope = _scope_clause(allowed_states, params)
        row = db.execute(
            text(
                f"""
                SELECT count(*) AS n,
                       count(*) FILTER (WHERE :factor = ANY(factors)) AS k
                  FROM analysis_cohort_members
                 WHERE version_id = :version_id{scope}
                """
            ),
            params,
        ).mappings().one()
        return int(row["n"] or 0), int(row["k"] or 0)

    n1, k1 = side(version_a)
    n2, k2 = side(version_b)
    out: dict[str, Any] = {
        "factor": factor,
        "confidence": confidence,
        "cohort_a": {"n": n1, "count": k1, "proportion": (k1 / n1) if n1 else None},
        "cohort_b": {"n": n2, "count": k2, "proportion": (k2 / n2) if n2 else None},
    }
    caveats: list[str] = []
    if not n1 or not n2:
        caveats.append("At least one cohort has no members.")
        out["caveats"] = caveats
        return out

    p1, p2 = k1 / n1, k2 / n2
    out["difference"] = p1 - p2
    pooled = (k1 + k2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        caveats.append("The factor is absent from (or universal in) both cohorts.")
        out["caveats"] = caveats
        return out

    z_stat = (p1 - p2) / se
    out["z_statistic"] = z_stat
    out["p_value"] = two_tailed_normal_p(z_stat)
    out["test_used"] = "TWO_PROPORTION_Z"
    out["significant"] = out["p_value"] < (1.0 - confidence)

    z = _ci_z(confidence)
    se_unpooled = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    out["difference_ci_lower"] = (p1 - p2) - z * se_unpooled
    out["difference_ci_upper"] = (p1 - p2) + z * se_unpooled

    # The normal approximation to the binomial needs a handful of events and
    # non-events in each arm; below that the z-test is unreliable in a way the
    # p-value itself will not reveal.
    if min(k1, n1 - k1, k2, n2 - k2) < MIN_EXPECTED_CELL:
        caveats.append(
            "Fewer than 5 crashes in at least one cell; the normal approximation "
            "behind this z-test is unreliable. Use the risk model, which falls "
            "back to Fisher's exact test at these counts."
        )
    out["caveats"] = caveats
    return out


# ---------------------------------------------------------------------------
# Trend analysis
# ---------------------------------------------------------------------------
def trend(
    db: Session,
    version_id: uuid.UUID,
    period: str = "YEAR",
    measure: str = "crash_count",
    allowed_states: list[str] | None = None,
) -> dict:
    """Trend over time: the series, plus an ordinary-least-squares fit.

    Reports slope, R^2, Pearson r and the p-value of the correlation, so an
    analyst can say not just "it rose" but how much of the variation the trend
    explains and whether it is distinguishable from noise. Both are needed: a
    steep slope through four scattered points is not a trend, and the slope
    alone would not say so.
    """
    if period not in TREND_PERIODS:
        raise StatisticsError(
            f"Unknown period '{period}'. Allowed: {sorted(TREND_PERIODS)}"
        )
    column = TREND_PERIODS[period]
    measures = {
        "crash_count": "count(*)",
        "sum_fatalities": "coalesce(sum(num_fatalities), 0)",
        "avg_fatalities": "avg(num_fatalities::numeric)",
        "sum_persons": "coalesce(sum(num_persons), 0)",
    }
    if measure not in measures:
        raise StatisticsError(
            f"Unknown measure '{measure}'. Allowed: {sorted(measures)}"
        )

    params: dict[str, Any] = {"version_id": str(version_id)}
    scope = _scope_clause(allowed_states, params)
    rows = db.execute(
        text(
            f"""
            SELECT {column} AS period, {measures[measure]} AS value
              FROM analysis_cohort_members
             WHERE version_id = :version_id AND {column} IS NOT NULL{scope}
             GROUP BY {column}
             ORDER BY {column}
            """
        ),
        params,
    ).mappings().all()

    series = [
        {"period": int(r["period"]), "value": _f(r["value"]) or 0.0} for r in rows
    ]
    out: dict[str, Any] = {
        "period": period,
        "measure": measure,
        "series": series,
        "n_periods": len(series),
    }
    caveats: list[str] = []

    if len(series) < 3:
        caveats.append(
            f"Only {len(series)} time period(s) with data. A trend line needs at "
            "least three points to be meaningful, and this cohort does not span "
            "enough time."
        )
        out["caveats"] = caveats
        return out

    xs = [float(p["period"]) for p in series]
    ys = [p["value"] for p in series]
    n = len(xs)
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    syy = sum((y - mean_y) ** 2 for y in ys)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))

    if sxx == 0:
        caveats.append("All periods are identical; no trend can be fitted.")
        out["caveats"] = caveats
        return out

    slope = sxy / sxx
    out["slope"] = slope
    out["intercept"] = mean_y - slope * mean_x
    out["direction"] = "increasing" if slope > 0 else "decreasing" if slope < 0 else "flat"
    out["change_per_period"] = slope

    if syy == 0:
        out["r_squared"] = 0.0
        caveats.append("The measure does not vary across periods; the trend is flat.")
        out["caveats"] = caveats
        return out

    r = sxy / math.sqrt(sxx * syy)
    out["pearson_r"] = r
    out["r_squared"] = r * r

    # t-test on the correlation, df = n - 2.
    if n > 2 and abs(r) < 1.0:
        t_stat = r * math.sqrt((n - 2) / (1 - r * r))
        out["t_statistic"] = t_stat
        out["degrees_of_freedom"] = float(n - 2)
        out["p_value"] = two_tailed_t_p(t_stat, n - 2)
        out["significant"] = out["p_value"] < 0.05
    elif abs(r) >= 1.0:
        out["p_value"] = 0.0
        out["significant"] = True
        caveats.append(
            "The points fall exactly on a line. With this few periods that is a "
            "property of the sample, not evidence of a deterministic trend."
        )

    if n < 5:
        caveats.append(
            f"The fit uses {n} periods. A slope estimated from this few points is "
            "dominated by any single unusual period."
        )
    if out.get("r_squared") is not None and out["r_squared"] < 0.3 and out.get("slope"):
        caveats.append(
            f"R^2 is {out['r_squared']:.2f}: the linear trend explains little of "
            "the variation between periods, so the slope is a poor summary."
        )
    if period == "MONTH":
        caveats.append(
            "Grouping by calendar month pools every year together, so this shows "
            "seasonality rather than a trend over time."
        )
    out["caveats"] = caveats
    return out
