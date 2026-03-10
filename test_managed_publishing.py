"""Quick smoke test for publish_managed_release — uses mocks, no real API calls."""

import json
import sys
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Test 1: client.publish_managed_release calls the right API method
# ---------------------------------------------------------------------------

def test_client_calls_managed_publishing_publish():
    mock_service = MagicMock()

    with patch("google_play_mcp.client._get_credentials", return_value=MagicMock()), \
         patch("google_play_mcp.client.build", return_value=mock_service):
        from google_play_mcp.client import PublisherClient
        client = PublisherClient()
        client.publish_managed_release("com.example.app")

    # Verify the final call chain: managedPublishing().publish(packageName=..., body={}).execute()
    publish_calls = mock_service.managedPublishing.return_value.publish.call_args_list
    assert any(
        call.kwargs == {"packageName": "com.example.app", "body": {}}
        for call in publish_calls
    ), f"Expected publish call with correct args, got: {publish_calls}"
    print("PASS: client calls managedPublishing().publish() with correct args")


# ---------------------------------------------------------------------------
# Test 2: server tool returns success JSON on happy path
# ---------------------------------------------------------------------------

def test_server_tool_returns_success():
    mock_service = MagicMock()
    mock_service.managedPublishing().publish().execute.return_value = {}

    with patch("google_play_mcp.client._get_credentials", return_value=MagicMock()), \
         patch("google_play_mcp.client.build", return_value=mock_service):
        # Import after patching so the module uses our mock
        import importlib
        import google_play_mcp.client
        importlib.reload(google_play_mcp.client)

        from google_play_mcp.client import PublisherClient

        with patch("google_play_mcp.server._publisher") as mock_pub:
            mock_client = MagicMock(spec=PublisherClient)
            mock_client.publish_managed_release.return_value = {}
            mock_pub.return_value = mock_client

            from google_play_mcp.server import publish_managed_release
            result = json.loads(publish_managed_release("com.example.app"))

    assert result["success"] is True
    assert "live" in result["message"].lower()
    mock_client.publish_managed_release.assert_called_once_with("com.example.app")
    print("PASS: server tool returns success JSON and delegates to client")


# ---------------------------------------------------------------------------
# Test 3: server tool returns error JSON on API failure
# ---------------------------------------------------------------------------

def test_server_tool_returns_error_on_failure():
    with patch("google_play_mcp.server._publisher") as mock_pub:
        mock_client = MagicMock()
        mock_client.publish_managed_release.side_effect = Exception("HttpError 403 forbidden")
        mock_pub.return_value = mock_client

        from google_play_mcp.server import publish_managed_release
        result = json.loads(publish_managed_release("com.example.app"))

    assert result["success"] is False
    assert "403" in result["error"]
    print("PASS: server tool returns error JSON on API exception")


# ---------------------------------------------------------------------------
# Test 4: update_release docstring mentions Managed Publishing
# ---------------------------------------------------------------------------

def test_update_release_docstring_warns_about_managed_publishing():
    from google_play_mcp.server import update_release
    assert "Managed Publishing" in (update_release.__doc__ or "")
    print("PASS: update_release docstring warns about Managed Publishing")


def test_create_release_docstring_warns_about_managed_publishing():
    from google_play_mcp.server import create_release
    assert "Managed Publishing" in (create_release.__doc__ or "")
    print("PASS: create_release docstring warns about Managed Publishing")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.path.insert(0, "src")
    tests = [
        test_client_calls_managed_publishing_publish,
        test_server_tool_returns_success,
        test_server_tool_returns_error_on_failure,
        test_update_release_docstring_warns_about_managed_publishing,
        test_create_release_docstring_warns_about_managed_publishing,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"FAIL: {t.__name__}: {e}")
            failed += 1

    print(f"\n{'All tests passed.' if not failed else f'{failed} test(s) failed.'}")
    sys.exit(failed)