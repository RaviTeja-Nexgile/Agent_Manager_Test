-- =============================================================================
-- Seed 0021 - Complete crash coordinates and dates for the map/trend
-- ALL data is synthetic / dev-test-demo only.
-- =============================================================================
-- GAP-BRD-11 plots `crashes.latitude`/`longitude`, which the gap analysis noted
-- were "captured and editable but rendered only as text fields and never
-- plotted". Plotting them exposed that 17 of 45 seeded crashes carry no
-- coordinates at all, so the map reported "28 of 45 ... 16 cannot be plotted"
-- — accurate, but it left a third of the demo data invisible.
--
-- Every one of those 17 is in a city that ALREADY has coordinates on another
-- crash (Salina, Topeka, Wichita, Houston). So the position is derived from the
-- city's own existing coordinates rather than invented: the map keeps asserting
-- only geography the database already contained.
--
-- A small deterministic offset (±0.08°, roughly ±9 km) is applied per crash so
-- multiple crashes in one city do not stack into a single indistinguishable
-- dot. It is derived from the CCFP identifier via md5, so it is stable across
-- re-seeds and identical on every machine — not random.
--
-- Two crashes also carry no crash_date. The trend chart already handles that
-- correctly ("Excludes N with no recorded crash date"), but an undated crash
-- cannot appear on a timeline at all, so they are dated here to make the demo
-- data complete. The handling remains for real-world records that genuinely
-- lack a date.
--
-- Idempotent: only fills rows that are still NULL.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Coordinates, derived from the same city's existing values.
-- ---------------------------------------------------------------------------
WITH city_anchor AS (
    -- One representative coordinate per (city, State) from crashes that have one.
    SELECT DISTINCT ON (city, state_code)
           city, state_code, latitude AS lat, longitude AS lon
      FROM crashes
     WHERE latitude IS NOT NULL AND longitude IS NOT NULL
     ORDER BY city, state_code, ccfp_identifier
)
UPDATE crashes c
   SET latitude  = a.lat + ((('x' || substr(md5(c.ccfp_identifier || 'lat'), 1, 6))::bit(24)::int % 161) - 80) / 1000.0,
       longitude = a.lon + ((('x' || substr(md5(c.ccfp_identifier || 'lon'), 1, 6))::bit(24)::int % 161) - 80) / 1000.0,
       updated_at = now()
  FROM city_anchor a
 WHERE (c.latitude IS NULL OR c.longitude IS NULL)
   AND c.city = a.city AND c.state_code = a.state_code;

-- Fallback for any crash whose city has no anchor at all: place it at the
-- State's own centroid, derived from that State's other crashes. Without this a
-- city that appears only on coordinate-less crashes would stay unplottable.
WITH state_anchor AS (
    SELECT state_code, avg(latitude) AS lat, avg(longitude) AS lon
      FROM crashes WHERE latitude IS NOT NULL GROUP BY state_code
)
UPDATE crashes c
   SET latitude  = s.lat + ((('x' || substr(md5(c.ccfp_identifier || 'slat'), 1, 6))::bit(24)::int % 201) - 100) / 1000.0,
       longitude = s.lon + ((('x' || substr(md5(c.ccfp_identifier || 'slon'), 1, 6))::bit(24)::int % 201) - 100) / 1000.0,
       updated_at = now()
  FROM state_anchor s
 WHERE (c.latitude IS NULL OR c.longitude IS NULL) AND c.state_code = s.state_code;

-- ---------------------------------------------------------------------------
-- Dates for the undated crashes, so every crash can appear on the timeline.
-- Spread deterministically across the study window rather than clustered on one
-- day, which would read as a spike that never happened.
-- ---------------------------------------------------------------------------
UPDATE crashes
   SET crash_date = DATE '2026-02-01'
                    + ((('x' || substr(md5(ccfp_identifier), 1, 6))::bit(24)::int % 150) || ' days')::interval,
       updated_at = now()
 WHERE crash_date IS NULL;

-- ---------------------------------------------------------------------------
-- Guards.
-- ---------------------------------------------------------------------------
DO $$
DECLARE n INT;
BEGIN
    SELECT count(*) INTO n FROM crashes WHERE latitude IS NULL OR longitude IS NULL;
    IF n > 0 THEN
        RAISE EXCEPTION 'BRD-11 seed: % crash(es) still have no coordinates', n;
    END IF;

    SELECT count(*) INTO n FROM crashes WHERE crash_date IS NULL;
    IF n > 0 THEN
        RAISE EXCEPTION 'BRD-11 seed: % crash(es) still have no crash_date', n;
    END IF;

    -- Coordinates must stay inside the continental frame the map renders, or a
    -- crash would be silently dropped from the plot.
    SELECT count(*) INTO n FROM crashes
     WHERE latitude NOT BETWEEN 24 AND 49.5 OR longitude NOT BETWEEN -125 AND -66.5;
    IF n > 0 THEN
        RAISE EXCEPTION 'BRD-11 seed: % crash(es) fall outside the map frame', n;
    END IF;
END $$;
