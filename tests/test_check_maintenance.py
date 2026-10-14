from unittest.mock import Mock

import pytest
from fastapi import HTTPException
import server


@pytest.mark.parametrize("scope", ["SELECTED", "USER", "COMPANY"])
def test_maintenance_prevents_jobs_before_db_or_manager_access(scope, monkeypatch):
    manager = Mock()
    db = Mock()
    monkeypatch.setattr(server, "get_job_manager", manager)
    payload = server.CheckStartRequest(scope_type=scope)
    with pytest.raises(HTTPException) as error:
        server.start_check(payload, Mock(), db, Mock(), Mock())
    assert error.value.status_code == 503
    assert "đang bảo trì" in error.value.detail
    manager.assert_not_called()
    assert not db.mock_calls
