import app.network.server as server_module
from fastapi.testclient import TestClient


def make_client() -> TestClient:
    return TestClient(server_module.app)


def test_index_serves_ui():
    with make_client() as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Carrera" in resp.content


def test_state_endpoint_reflects_initial_idle_state():
    with make_client() as client:
        resp = client.get("/api/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "idle"
        assert len(data["cars"]) == 6


def test_state_endpoint_exposes_cu_backend_so_mock_vs_real_is_unmistakable():
    with make_client() as client:
        data = client.get("/api/state").json()
        # No CARRERA_RMS_CU_DEVICE set in the test environment -> mock.
        assert data["cu_backend"].startswith("MOCK")


def test_assign_car_and_change_mode_and_weather():
    with make_client() as client:
        resp = client.post("/api/cars/0/assign", json={"controller_id": "p1", "name": "Red 7"})
        assert resp.status_code == 200

        resp = client.get("/api/state")
        assert resp.json()["cars"]["0"]["name"] == "Red 7"
        assert resp.json()["cars"]["0"]["controller_id"] == "p1"

        resp = client.post("/api/race/mode", json={"mode": "time_attack"})
        assert resp.status_code == 200
        assert client.get("/api/state").json()["mode"] == "time_attack"

        resp = client.post("/api/race/weather", json={"level": "wet"})
        assert resp.status_code == 200
        assert client.get("/api/state").json()["weather"] == "wet"


def test_invalid_mode_rejected():
    with make_client() as client:
        resp = client.post("/api/race/mode", json={"mode": "banana"})
        assert resp.status_code == 422


def test_go_start_and_stop_transition_states():
    with make_client() as client:
        client.post("/api/race/countdown")
        assert client.get("/api/state").json()["state"] == "countdown"
        client.post("/api/race/go")
        assert client.get("/api/state").json()["state"] == "running"
        client.post("/api/race/stop", json={})
        assert client.get("/api/state").json()["state"] == "paused"
        client.post("/api/race/resume")
        assert client.get("/api/state").json()["state"] == "running"


def test_penalty_endpoint():
    with make_client() as client:
        resp = client.post("/api/cars/0/penalty", json={"address": 0, "seconds": 5.0, "reason": "test"})
        assert resp.status_code == 200
        state = client.get("/api/state").json()
        assert state["cars"]["0"]["penalty_seconds"] == 5.0


def test_recording_lifecycle(tmp_path, monkeypatch):
    with make_client() as client:
        session = server_module.app.state.session
        monkeypatch.setattr(session.recorder, "storage_dir", tmp_path)

        resp = client.post("/api/recording/start", json={"address": 6, "name": "ghost1"})
        assert resp.status_code == 200
        resp = client.post("/api/recording/stop/6")
        assert resp.status_code == 200
        assert client.get("/api/recording/list").json()["recordings"] == ["ghost1"]


def test_websocket_input_updates_state():
    with make_client() as client:
        client.post("/api/cars/0/assign", json={"controller_id": "ws-player"})
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "input", "controller_id": "ws-player", "throttle": 0.7, "brake": 0.0})
            # Give the server a brief window; the WS message is applied
            # synchronously on receipt inside the endpoint handler.
            import time
            time.sleep(0.1)
        session = server_module.app.state.session
        controller = session.controllers[0]
        assert controller.poll().throttle == 0.7


def test_debug_log_endpoint_available():
    with make_client() as client:
        resp = client.get("/api/debug/log")
        assert resp.status_code == 200
        assert "log" in resp.json()
