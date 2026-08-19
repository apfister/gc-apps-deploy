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
    def run_action(self, files):
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
            for relative_path, content in files.items():
                path = artifact / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
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

        return result, Receiver.uploaded

    def test_uploads_static_artifact_with_oidc(self):
        result, uploaded = self.run_action({
            "index.html": "hello",
            "assets/app.js": "javascript",
        })

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Deployment succeeded", result.stdout)
        self.assertEqual(uploaded["authorization"], "Bearer signed-token")
        self.assertEqual(uploaded["size"], str(len("hello") + len("javascript")))
        self.assertEqual(uploaded["files"]["index.html"], b"hello")
        self.assertEqual(uploaded["files"]["assets/app.js"], b"javascript")

    def test_uploads_service_artifact_with_oidc(self):
        manifest = '{"version":1,"type":"service"}'
        result, uploaded = self.run_action({
            "gcapps.json": manifest,
            "api/server.js": "server",
        })

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Deployment succeeded", result.stdout)
        self.assertEqual(uploaded["authorization"], "Bearer signed-token")
        self.assertEqual(uploaded["files"]["gcapps.json"], manifest.encode())
        self.assertEqual(uploaded["files"]["api/server.js"], b"server")

    def test_rejects_artifact_without_contract_marker(self):
        result, uploaded = self.run_action({"assets/app.js": "javascript"})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("regular index.html or gcapps.json", result.stderr)
        self.assertIsNone(uploaded)


if __name__ == "__main__":
    unittest.main()