import http.server
import threading

import pytest


class _Handler(http.server.BaseHTTPRequestHandler):
    """Answers each GET with the responder registered for its path."""

    def do_GET(self):
        respond = self.server.routes.get(self.path)
        if respond is None:
            self.send_error(404)
        else:
            respond(self)

    def log_message(self, format, *args):
        """Drop request logging so test output stays clean."""


def _full_response(status, body, headers):
    """Build a responder that sends a status, headers, and a body."""

    def respond(handler):
        handler.send_response(status)
        for name, value in headers.items():
            handler.send_header(name, value)
        if "content-length" not in {name.lower() for name in headers}:
            handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    return respond


def _raw_response(data):
    """Build a responder that writes data verbatim, then closes the connection."""

    def respond(handler):
        handler.wfile.write(data)
        handler.close_connection = True

    return respond


class LocalServer:
    """Serves the responses a test registers on 127.0.0.1."""

    def __init__(self, server):
        self._server = server

    def route(self, path, status=200, body=b"", headers=None):
        self._server.routes[path] = _full_response(status, body, dict(headers or {}))

    def raw_route(self, path, data):
        """Send data as the entire response, for malformed HTTP."""
        self._server.routes[path] = _raw_response(data)

    def url(self, path):
        port = self._server.server_address[1]
        return f"http://127.0.0.1:{port}{path}"


@pytest.fixture
def http_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.routes = {}
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        yield LocalServer(server)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
