import asyncio
import json

from server import ConnectionManager


class FakeWebSocket:
    def __init__(self):
        self.messages: list[dict] = []

    async def send_text(self, value: str) -> None:
        self.messages.append(json.loads(value))


def test_manual_job_progress_goes_only_to_requesting_session():
    manager = ConnectionManager()
    first = FakeWebSocket()
    second = FakeWebSocket()
    manager.connections = {"session-a": [first], "session-b": [second]}
    manager.session_users = {"session-a": "user-a", "session-b": "user-b"}

    asyncio.run(manager.dispatch_job_event(
        "job_progress",
        {
            "requested_by": "user-a",
            "requested_session_id": "session-a",
            "run": {"id": "run-1", "status": "RUNNING"},
        },
    ))

    assert [item["type"] for item in first.messages] == ["job_progress"]
    assert second.messages == []


def test_job_completion_does_not_refetch_account_lists():
    manager = ConnectionManager()
    requester = FakeWebSocket()
    viewer = FakeWebSocket()
    manager.connections = {"request-session": [requester], "viewer-session": [viewer]}
    manager.session_users = {"request-session": "requester", "viewer-session": "viewer"}

    asyncio.run(manager.dispatch_job_event(
        "job_finished",
        {
            "requested_by": "requester",
            "requested_session_id": "request-session",
            "run": {"id": "run-2", "status": "COMPLETED"},
        },
    ))

    assert [item["type"] for item in requester.messages] == ["job_finished", "dashboard_changed"]
    assert [item["type"] for item in viewer.messages] == ["dashboard_changed"]


def test_row_updates_are_sent_only_to_authorized_viewers(monkeypatch):
    manager = ConnectionManager()
    requester, allowed, stranger = FakeWebSocket(), FakeWebSocket(), FakeWebSocket()
    manager.connections = {"s1": [requester], "s2": [allowed], "s3": [stranger]}
    manager.session_users = {"s1": "boss", "s2": "owner", "s3": "stranger"}
    monkeypatch.setattr(manager, "_account_recipients", lambda _: {"boss", "owner"})
    asyncio.run(manager.dispatch_job_event("job_progress", {
        "requested_session_id": "s1", "run": {"id": "run"},
        "account": {"account_id": "a", "owner_id": "owner", "followers": 123,
                    "alerts": [], "leader_id": "leader"},
    }))
    assert [x["type"] for x in requester.messages] == ["job_progress", "account_updated"]
    assert [x["type"] for x in allowed.messages] == ["account_updated"]
    assert stranger.messages == []
    assert "leader_id" not in allowed.messages[0]["data"]["account"]
