def test_detail_404(client):
    assert client.get("/api/entities/missing").status_code == 404

def test_detail_returns_entity(client):
    r = client.get("/api/entities/in-premji")
    assert r.status_code == 200
    body = r.json()
    assert body["entity"]["name"] == "Premji Invest"
    assert body["sources"] == []
    assert body["activities"] == []
    assert body["assumptions"] == []
