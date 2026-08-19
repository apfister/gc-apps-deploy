#!/usr/bin/env python3
import io
import json
import os
import pathlib
import subprocess
import tarfile
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


class Receiver(BaseHTTPRequestHandler):
    uploaded = None

    def do_GET(self):
        if urlsplit(self.path).path != "/oidc":
            self.send_error(404)
            return
        query = parse_qs(urlsplit(self.path).query)
        if self.headers.get("Authorization") != "Bearer request-token" or query.get("audience") != ["test-audience"]:
            self.send_error(401)
            return
        self.respond(200, {"value": "signed-token"})

    def do_POST(self):
        if self.path != "/_deploy":
            self.send_error(404)
            return
        length = int(self.headers["Content-Length"])
        archive = self.rfile.read(length)
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as content:
            files = {
                member.name.removeprefix("./"): content.extractfile(member).read()
                for member in content.getmembers()
                if member.isfile()
            }
        self.__class__.uploaded = {
            "authorization": self.headers.get("Authorization"),
            "size": self.headers.get("X-Artifact-Uncompressed-Size"),
            "files": files,
        }
        self.respond(200, {"outcome": "succeeded", "message": "Deployment succeeded", "deployment_id": 7})

    def respond(self, status, body):
        content = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, _format, *_args):
        pass


class DeployActionTest(unittest.TestCase):
    def test_uploads_artifact_with_oidc(self):
        Receiver.uploaded = None
        server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            artifact = root / "dist"
            (artifact / "assets").mkdir(parents=True)
            (artifact / "index.html").write_text("hello", encoding="utf-8")
            (artifact / "assets" / "app.js").write_text("javascript", encoding="utf-8")
            endpoint = f"http://127.0.0.1:{server.server_port}"
            environment = os.environ | {
                "ACTIONS_ID_TOKEN_REQUEST_URL": endpoint + "/oidc?job=deploy",
                "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "request-token",
                "GCAPPS_DEPLOY_ENDPOINT": endpoint + "/_deploy",
                "GCAPPS_OIDC_AUDIENCE": "test-audience",
                "RUNNER_TEMP": temporary,
            }
            result = subprocess.run(
                ["bash", str(pathlib.Path(__file__).parents[1] / "deploy.sh"), str(artifact)],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Deployment succeeded", result.stdout)
        self.assertEqual(Receiver.uploaded["authorization"], "Bearer signed-token")
        self.assertEqual(Receiver.uploaded["size"], str(len("hello") + len("javascript")))
        self.assertEqual(Receiver.uploaded["files"]["index.html"], b"hello")
        self.assertEqual(Receiver.uploaded["files"]["assets/app.js"], b"javascript")


if __name__ == "__main__":
    unittest.main()