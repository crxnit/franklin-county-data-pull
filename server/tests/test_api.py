"""API tests. The Whigham case is the correctness oracle: NBHD 00111000,
subject 1,868 sqft -> size-matched anchor ~$523K (matches the CLI/report)."""


def test_health(client):
    assert client.get("/api/health").json() == {"ok": True}


def test_meta(client):
    m = client.get("/api/meta").json()
    assert m["parcels"] > 10_000
    assert m["neighborhoods"] > 20


def test_address_search_finds_whigham(client):
    hits = client.get("/api/address/search", params={"q": "7518 whigham"}).json()
    assert hits and hits[0]["parcelid"] == "273-005856"
    assert hits[0]["sqft"] == 1868


def test_report_whigham_oracle(client):
    r = client.get("/api/report", params={"address": "7518 whigham ct"}).json()
    assert r["subject"]["resolved"] is True
    assert r["subject"]["nbhdcd"] == "00111000"
    anchor = r["estimate"]["anchor"]["value"]
    assert 510_000 <= anchor <= 535_000, anchor
    assert r["comps"], "expected comps"


def test_comps_matches_report(client):
    """POST /comps with the subject's attributes yields the same anchor as the
    report (both share analyze.price_estimate)."""
    body = {"address": "7518 whigham ct", "subject_sqft": 1868, "beds": 3,
            "baths": 2, "year_built": 1992, "nbhdcd": "00111000", "size_band": 0.15}
    c = client.post("/api/comps", json=body).json()
    r = client.get("/api/report", params={"address": "7518 whigham ct"}).json()
    assert c["estimate"]["anchor"]["value"] == r["estimate"]["anchor"]["value"]


def test_report_unknown_address_404(client):
    assert client.get("/api/report", params={"address": "999999 nowhere st"}).status_code == 404


def test_neighborhoods_list_and_detail(client):
    lst = client.get("/api/neighborhoods").json()
    assert any(n["nbhdcd"] == "00111000" for n in lst)
    d = client.get("/api/neighborhoods/00111000").json()
    assert d["summary"]["comps_usable"] >= 50
    assert d["trend"] and d["scatter"]


def test_auth_required(auth_client):
    assert auth_client.get("/api/meta").status_code == 401
    ok = auth_client.get("/api/meta", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200
    # health stays open
    assert auth_client.get("/api/health").status_code == 200
