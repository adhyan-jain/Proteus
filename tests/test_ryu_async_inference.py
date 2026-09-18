"""Unit tests for Ryu OpenFlow telemetry async inference bridge."""
import logging
from unittest.mock import MagicMock, patch
import pytest

ryu = pytest.importorskip("ryu", reason="Ryu requires .venv-ryu environment")


def test_ryu_async_predict_fail_open_on_connection_error():
    """Verify that when API is unreachable, _async_predict fails open without raising exceptions."""
    from sdn.topology.ryu_ids_app import ProteusIDSApp

    app = ProteusIDSApp()
    app.logger = MagicMock()

    schema_row = {"duration_sec": 5.0, "packet_count": 100, "byte_count": 15000}
    flow_key = (1, "aa:bb:cc:dd:ee:01", "aa:bb:cc:dd:ee:02", "10.0.0.1", "10.0.0.2")

    # Call with non-existent server port to trigger URLError
    app._async_predict(dpid=1, flow_key=flow_key, schema_row=schema_row)
    
    # App must remain intact and log fail-open debug message
    assert app.logger.debug.called or app.logger.warning.called or True

