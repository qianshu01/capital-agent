def test_list_all(client):
    r = client.get("/api/entities")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert len(body["results"]) == 3

def test_filter_country(client):
    r = client.get("/api/entities?country=HK")
    body = r.json()
    assert body["total"] == 1
    assert body["results"][0]["id"] == "hk-a"

def test_filter_min_aum(client):
    r = client.get("/api/entities?min_aum_usd=5000000000")
    ids = {e["id"] for e in r.json()["results"]}
    assert ids == {"hk-a", "in-premji"}

def test_sort_aum_desc(client):
    r = client.get("/api/entities?sort=aum_desc")
    results = r.json()["results"]
    assert [e["id"] for e in results] == ["hk-a", "in-premji", "sg-tsao"]

def test_q_substring(client):
    r = client.get("/api/entities?q=premji")
    assert r.json()["total"] == 1

def test_pagination(client):
    r = client.get("/api/entities?limit=1&offset=1&sort=aum_desc")
    body = r.json()
    assert body["total"] == 3
    assert len(body["results"]) == 1
    assert body["results"][0]["id"] == "in-premji"
