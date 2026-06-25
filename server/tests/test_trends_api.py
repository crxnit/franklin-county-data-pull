"""Tests for /api/trends. The endpoint reads the materialized trend_cache when
present and otherwise recomputes from records (exercised here, since the test DB
may not have been materialized)."""


def test_dimensions_discovery(client):
    d = client.get("/api/trends/dimensions").json()
    assert "sale_biweek" in d["granularities"]
    keys = {dim["key"] for dim in d["dimensions"]}
    assert keys == {"overall", "school", "neighborhood", "price_tier", "sqft_band"}
    # Neighborhood dimension exposes real Dublin neighborhood codes as groups.
    nbhd = next(dim for dim in d["dimensions"] if dim["key"] == "neighborhood")
    assert "00111000" in nbhd["groups"]


def test_overall_monthly_trend(client):
    r = client.get("/api/trends", params={"dimension": "overall",
                                          "granularity": "sale_month"}).json()
    assert r["dimension"] == "overall"
    assert r["group"] == "all"
    assert r["trend"], "expected overall monthly trend rows"
    assert {"period", "n", "median_ppsf", "median_price"} == set(r["trend"][0])


def test_biweekly_granularity(client):
    r = client.get("/api/trends", params={"dimension": "overall",
                                          "granularity": "sale_biweek"}).json()
    periods = [row["period"] for row in r["trend"]]
    assert periods == sorted(periods)  # block-start ISO dates sort chronologically


def test_neighborhood_slice_matches_neighborhood_endpoint(client):
    """The trend for a neighborhood/month must agree with the existing
    /api/neighborhoods/{nbhdcd} trend on shared periods (same analyze.trend)."""
    nb = "00111000"
    t = client.get("/api/trends", params={"dimension": "neighborhood",
                                          "group": nb, "granularity": "sale_month"}).json()
    detail = client.get(f"/api/neighborhoods/{nb}").json()
    by_period = {row["period"]: row["median_ppsf"] for row in detail["trend"]}
    shared = [row for row in t["trend"] if row["period"] in by_period]
    assert shared, "expected overlapping periods"
    for row in shared:
        assert row["median_ppsf"] == by_period[row["period"]]


def test_group_required_and_validation(client):
    # A non-overall dimension without a group is a 400.
    assert client.get("/api/trends", params={"dimension": "neighborhood"}).status_code == 400
    # Unknown dimension / granularity are rejected.
    assert client.get("/api/trends", params={"dimension": "nope"}).status_code == 400
    assert client.get("/api/trends", params={"granularity": "weekly"}).status_code == 400
    # Unknown group is a 404.
    assert client.get("/api/trends", params={"dimension": "neighborhood",
                                             "group": "ZZZ"}).status_code == 404


def test_trends_auth_gated(auth_client):
    assert auth_client.get("/api/trends").status_code == 401
    ok = auth_client.get("/api/trends", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200
