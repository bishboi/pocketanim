"""A stand-in for Datalab's conversion API, following datalab-python-sdk's protocol.

POST /api/v1/convert (multipart, X-Api-Key) -> {success, request_check_url};
GET that URL -> {status: "processing"} once, then the result with markdown and
base64 images.
"""
import base64
import io
import json
from http.server import BaseHTTPRequestHandler

SEEN = {"posts": [], "polls": 0}


def _png() -> str:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (400, 250), "#2e7d32").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body: dict, code: int = 200):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        SEEN["posts"].append({"key": self.headers.get("X-Api-Key"), "path": self.path,
                              "has_file": b'name="file"; filename=' in body,
                              "format": b'name="output_format"\r\n\r\nmarkdown' in body})
        if self.headers.get("X-Api-Key") != "test-key":
            return self._send({"success": False, "error": "bad key"}, 401)
        self._send({"success": True, "request_id": "r1", "request_check_url": "/api/v1/convert/r1"})

    def do_GET(self):
        SEEN["polls"] += 1
        if SEEN["polls"] == 1:
            return self._send({"status": "processing", "success": True})
        markdown = ("# Agriculture in Uttar Pradesh\n\nUttar Pradesh is the largest producer of sugarcane in India.\n\n"
                    "![](_page_0_Picture_3.png)\n\n*Figure 1: The sugarcane belt of western Uttar Pradesh*\n\n"
                    "Wheat is the main rabi crop.\n")
        self._send({"status": "complete", "success": True, "output_format": "markdown", "markdown": markdown,
                    "images": {"_page_0_Picture_3.png": _png()}, "page_count": 2})
