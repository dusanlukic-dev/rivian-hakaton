"""One cabin camera (the one on the rear-view mirror): a second stream on /camera/ws is refused.

Two cameras used to interleave their frames into one model, which then saw "two drivers" (7. 11. 2026).
"""

import pytest
from starlette.websockets import WebSocketDisconnect

from tests.conftest import API


def camera_clients(client) -> int:
    return client.get(f"{API}/coordinator/status").json()["camera"]["stream_clients"]


def test_a_second_camera_is_refused_while_the_first_streams(client, jpeg_frames):
    with client.websocket_connect(f"{API}/camera/ws") as first:
        first.send_bytes(jpeg_frames[0])
        assert camera_clients(client) == 1
        with pytest.raises(WebSocketDisconnect) as refused:
            with client.websocket_connect(f"{API}/camera/ws"):
                pass
        assert refused.value.code == 1008
        assert camera_clients(client) == 1  # the refused one never counted
        first.send_bytes(jpeg_frames[1])  # the first camera keeps streaming


def test_the_next_camera_takes_over_once_the_first_disconnects(client):
    with client.websocket_connect(f"{API}/camera/ws"):
        assert camera_clients(client) == 1
    assert camera_clients(client) == 0
    with client.websocket_connect(f"{API}/camera/ws"):
        assert camera_clients(client) == 1
    assert camera_clients(client) == 0
