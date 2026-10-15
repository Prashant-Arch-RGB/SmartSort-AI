"""
main.py — SmartSort AI native desktop entry point.

Starts the Flask server on a background thread and opens the UI in a
native OS window via pywebview (no browser, no server-restart issue).

Run with:
    python main.py
"""

from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path before any local imports
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))


def _find_free_port() -> int:
    """Bind to port 0 to let the OS pick a free port, then release it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(host: str, port: int, timeout: float = 10.0) -> bool:
    """Poll until the Flask server accepts connections or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _start_flask(port: int) -> None:
    """Run the Flask app in the current thread (called from a daemon thread)."""
    from app import app  # import here so ROOT is already on sys.path

    # Disable the Werkzeug reloader — it forks a child process which fights
    # with pywebview on Windows.
    app.run(
        host="127.0.0.1",
        port=port,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


def main() -> None:
    try:
        import webview  # pywebview
    except ImportError:
        print(
            "pywebview is not installed.\n"
            "Install it with:  pip install pywebview\n"
            "Or run the web version with:  python app.py"
        )
        sys.exit(1)

    port = _find_free_port()
    url = f"http://127.0.0.1:{port}"

    # Start Flask on a daemon thread so it exits when the window closes
    flask_thread = threading.Thread(target=_start_flask, args=(port,), daemon=True)
    flask_thread.start()

    # Wait until Flask is ready before opening the window
    if not _wait_for_server("127.0.0.1", port):
        print("Flask server did not start in time.")
        sys.exit(1)

    # Override the tkinter folder dialog so pywebview's native dialog is used
    # instead — avoids two GUI toolkits conflicting on Windows.
    _patch_browse_endpoint()

    # Open the native window — this call blocks until the window is closed
    webview.create_window(
        title="SmartSort AI",
        url=url,
        width=1280,
        height=800,
        min_size=(900, 600),
        text_select=True,
    )
    webview.start()


def _patch_browse_endpoint() -> None:
    """
    Replace the /api/browse_folder Flask route with one that uses
    webview.windows[0].create_file_dialog instead of tkinter, which
    works correctly inside a pywebview app on Windows.
    """
    from flask import jsonify
    from app import app

    # Remove the old tkinter-based route and register a new one
    app.view_functions.pop("api_browse_folder", None)
    # Remove the URL rule so Flask lets us register a replacement
    rules_to_remove = [
        rule for rule in app.url_map.iter_rules()
        if rule.endpoint == "api_browse_folder"
    ]
    for rule in rules_to_remove:
        app.url_map._rules.remove(rule)
        app.url_map._rules_by_endpoint.pop("api_browse_folder", None)

    @app.route("/api/browse_folder", methods=["POST"])
    def api_browse_folder():  # type: ignore[no-redef]
        import webview
        windows = webview.windows
        if not windows:
            return jsonify({"error": "No active window"}), 500
        result = windows[0].create_file_dialog(
            webview.FOLDER_DIALOG,
            allow_multiple=False,
        )
        if result:
            # pywebview returns a tuple/list of paths
            path = result[0] if isinstance(result, (list, tuple)) else result
            return jsonify({"path": str(path)})
        return jsonify({"path": ""})


if __name__ == "__main__":
    main()
