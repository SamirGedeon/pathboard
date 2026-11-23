from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from pathboard.main import create_app
from pathboard.planning import ProjectInput
from pathboard.store import Store


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(str(tmp_path / "test.sqlite"), origin="http://testserver")) as c:
        response = c.post(
            "/api/auth/signup",
            json={"email": "learner@example.com", "password": "a-strong-password"},
        )
        assert response.status_code == 200
        yield c


def project(client):
    response = client.post(
        "/api/projects",
        json={
            "name": "Launch",
            "tasks": [
                {"id": "a", "title": "Discover", "hours": 4},
                {"id": "b", "title": "Build", "hours": 6, "dependencies": ["a"]},
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def payload(p):
    return {k: p[k] for k in ("name", "description", "tasks", "version")}


def test_account_isolation_on_read_write_and_simulation(client):
    p = project(client)
    client.post("/api/logout")
    client.post(
        "/api/auth/signup", json={"email": "other@example.com", "password": "a-strong-password"}
    )
    assert client.get("/api/projects").json() == []
    assert client.get("/api/projects/" + p["id"]).status_code == 404
    assert client.put("/api/projects/" + p["id"], json=payload(p)).status_code == 404
    assert (
        client.post(
            "/api/projects/" + p["id"] + "/simulate",
            json={"task_id": "a", "hours": 8, "version": 1},
        ).status_code
        == 404
    )


def test_stale_versions_rejected_without_altering_saved_plan(client):
    p = project(client)
    body = payload(p)
    body["name"] = "Updated"
    assert client.put("/api/projects/" + p["id"], json=body).json()["version"] == 2
    assert client.put("/api/projects/" + p["id"], json=body).status_code == 409
    assert client.get("/api/projects/" + p["id"]).json()["name"] == "Updated"


def test_invalid_graph_rejected_atomically(client):
    p = project(client)
    body = payload(p)
    body["tasks"][0]["dependencies"] = ["b"]
    assert client.put("/api/projects/" + p["id"], json=body).status_code == 422
    assert client.get("/api/projects/" + p["id"]).json()["version"] == 1


def test_simulation_is_read_only_and_version_guarded(client):
    p = project(client)
    r = client.post(
        "/api/projects/" + p["id"] + "/simulate", json={"task_id": "a", "hours": 8, "version": 1}
    )
    assert r.json()["baseline"] == 10 and r.json()["impact"] == 4
    saved = client.get("/api/projects/" + p["id"]).json()
    assert saved["plan"]["duration"] == 10 and saved["version"] == 1
    assert (
        client.post(
            "/api/projects/" + p["id"] + "/simulate",
            json={"task_id": "a", "hours": 8, "version": 2},
        ).status_code
        == 409
    )


def test_credentials_sessions_and_logout(client):
    assert client.get("/api/me").status_code == 200
    client.post("/api/logout")
    assert client.get("/api/me").status_code == 401
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "learner@example.com", "password": "incorrect-password"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "learner@example.com", "password": "a-strong-password"},
        ).status_code
        == 200
    )
    store = client.app.state.store
    with store.connect() as db:
        db.execute("UPDATE sessions SET expires=0")
    assert client.get("/api/me").status_code == 401


def test_origin_body_limits_and_password_redaction(client):
    assert (
        client.post(
            "/api/projects", headers={"Origin": "https://evil.example"}, json={"name": "No"}
        ).status_code
        == 403
    )
    assert client.post("/api/projects", content="x" * 65537).status_code == 413
    response = client.post("/api/auth/signup", json={"email": "a@example.com", "password": "short"})
    assert response.status_code == 422 and "short" not in response.text
    # Unknown fields must be rejected without echoing any submitted secrets.
    response = client.post(
        "/api/auth/signup",
        json={"email": "a@example.com", "password": "do-not-echo-this", "unknown": "value"},
    )
    assert response.status_code == 422 and "do-not-echo-this" not in response.text


def test_session_cookie_flags(tmp_path):
    with TestClient(create_app(str(tmp_path / "cookies.sqlite"), secure=True)) as c:
        r = c.post(
            "/api/auth/signup",
            json={"email": "secure@example.com", "password": "a-strong-password"},
        )
        cookie = r.headers["set-cookie"].lower()
        assert "httponly" in cookie and "secure" in cookie and "samesite=strict" in cookie


def test_concurrent_mutations_allow_only_one_version_winner(client):
    p = project(client)
    store = client.app.state.store
    uid = client.get("/api/me").json()["id"]

    def write(name):
        document = ProjectInput(**{**payload(p), "name": name})
        try:
            return store.save(uid, document, p["id"])["version"]
        except HTTPException as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ["First", "Second"]))
    assert sorted(results) == [2, 409]


def test_database_and_session_survive_reopen(client):
    p = project(client)
    store = client.app.state.store
    reopened = Store(store.path)
    uid = reopened.user(client.cookies.get("session"))["id"]
    assert reopened.get(uid, p["id"])["plan"]["duration"] == 10
    with reopened.connect() as db:
        token = db.execute("SELECT token FROM sessions").fetchone()["token"]
        assert token != client.cookies.get("session")


def test_authentication_rate_limit(tmp_path):
    with TestClient(create_app(str(tmp_path / "limit.sqlite"))) as c:
        for _ in range(30):
            c.post("/api/auth/login", json={})
        r = c.post("/api/auth/login", json={})
        assert r.status_code == 429 and int(r.headers["retry-after"]) > 0
