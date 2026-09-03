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


def test_job_completion_broadcasts_only_data_invalidation_to_other_sessions():
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

    assert [item["type"] for item in requester.messages] == ["job_finished", "data_updated"]
    assert [item["type"] for item in viewer.messages] == ["data_updated"]
