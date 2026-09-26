import copy
import copy
import json
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import database
from main import app
from scraper import ScrapeError, username_from_json_url, validate_introduction_json


JSON_URL = "https://webpages.charlotte.edu/tmcelro3/itis3135/introduction_generated.json"
SAMPLE_INTRODUCTION = {
    "firstName": "Thomas",
    "middleName": "A.",
    "nickname": "Tommy",
    "lastName": "McElroy",
    "acknowledgment": "I understand this is public.",
    "acknowledgmentDate": "8/20/26",
    "divider": "~",
    "adjectives": "Terrific",
    "animal": "Muskrat",
    "img": "data:image/png;base64,aW1hZ2U=",
    "pictureAlt": "my face",
    "caption": "Me, at a friend's house",
    "personalStatement": "I study computer science.",
    "personalBackground": "I live in Charlotte.",
    "professionalBackground": "I work at Micro Center.",
    "academicBackground": "I transferred from CPCC.",
    "primaryWorkComputer": "ThinkPad running Linux.",
    "primaryWorkLocation": "UNCC campus.",
    "alternateComputerLocation": "My laptop at home.",
    "courses": [
        {
            "department": "ITIS",
            "courseNumber": "3135",
            "courseTitle": "Frontend Web App Development",
            "reasonfortaking": "It is useful for building web applications."
        }
    ],
    "quote": "A favorite quote.",
    "quoteAuthor": "A person",
    "funnyItem": "I type quickly.",
    "somethingToShare": "I like biking.",
    "footerLinks": [{"label": "Home", "url": "https://example.com/"}]
}


class IntroductionAPITests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_directory.name) / "test.sqlite3"
        self.database_patcher = patch.object(database, "DATABASE_PATH", self.database_path)
        self.database_patcher.start()
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.database_patcher.stop()
        self.temp_directory.cleanup()

    def test_post_and_put_upsert_by_username_and_get_all_values(self):
        revised_introduction = copy.deepcopy(SAMPLE_INTRODUCTION)
        revised_introduction["firstName"] = "Updated"

        with patch("main.fetch_introduction_json", new_callable=AsyncMock) as fetch_json:
            fetch_json.side_effect = [SAMPLE_INTRODUCTION, revised_introduction]
            created = self.client.post("/sites", json={"json_url": JSON_URL})
            updated = self.client.put("/sites", json={"json_url": JSON_URL})

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["username"], "tmcelro3")
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["introductionData"]["firstName"], "Updated")
        self.assertEqual(fetch_json.await_count, 2)

        saved = self.client.get("/sites")
        self.assertEqual(saved.status_code, 200)
        record = saved.json()["tmcelro3"]
        self.assertEqual(record["introductionData"], revised_introduction)
        self.assertEqual(record["jsonUrl"], JSON_URL)
        self.assertEqual(record["baseSiteUrl"], "https://webpages.charlotte.edu/tmcelro3/")
        self.assertTrue(record["lastUpdated"])

    def test_posting_same_username_updates_existing_record(self):
        revised_introduction = copy.deepcopy(SAMPLE_INTRODUCTION)
        revised_introduction["caption"] = "Updated caption"

        with patch("main.fetch_introduction_json", new_callable=AsyncMock) as fetch_json:
            fetch_json.side_effect = [SAMPLE_INTRODUCTION, revised_introduction]
            self.assertEqual(self.client.post("/sites", json={"json_url": JSON_URL}).status_code, 201)
            second_post = self.client.post("/sites", json={"json_url": JSON_URL})

        self.assertEqual(second_post.status_code, 200)
        record = self.client.get("/").json()["tmcelro3"]
        self.assertEqual(record["introductionData"], revised_introduction)
        self.assertEqual(record["baseSiteUrl"], "https://webpages.charlotte.edu/tmcelro3/")

    def test_rejects_urls_outside_allowed_hosts(self):
        with patch("main.fetch_introduction_json", new_callable=AsyncMock) as fetch_json:
            for json_url in (
                "https://webpages.charlotte.edu.evil.example/user/introduction.json",
                "http://localhost:9000/tmcelro3.json",
                "http://127.0.0.2:9000/tmcelro3.json",
            ):
                with self.subTest(json_url=json_url):
                    response = self.client.post("/sites", json={"json_url": json_url})
                    self.assertEqual(response.status_code, 422)
                    self.assertIn("webpages.charlotte.edu", response.text)

        fetch_json.assert_not_awaited()

    def test_returns_scraper_error_for_unavailable_json(self):
        with patch(
            "main.fetch_introduction_json",
            new_callable=AsyncMock,
            side_effect=ScrapeError(502, "The JSON URL returned HTTP 404."),
        ):
            response = self.client.post("/sites", json={"json_url": JSON_URL})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "The JSON URL returned HTTP 404.")

    def test_validates_json_export_shape_and_image_data(self):
        self.assertEqual(validate_introduction_json(SAMPLE_INTRODUCTION), SAMPLE_INTRODUCTION)
        legacy_introduction = copy.deepcopy(SAMPLE_INTRODUCTION)
        legacy_introduction["acknowledgment"] = ""
        legacy_introduction["adjectives"] = ""
        self.assertEqual(validate_introduction_json(legacy_introduction), legacy_introduction)
        invalid = copy.deepcopy(SAMPLE_INTRODUCTION)
        invalid["img"] = "images/photo.jpeg"
        with self.assertRaisesRegex(ScrapeError, "Base64 data URL"):
            validate_introduction_json(invalid)

    def test_example_exports_follow_the_intro_json_schema(self):
        examples = Path(__file__).resolve().parents[1]
        for username in ("tmcelro3", "spate338", "ndudley2", "hgibso21"):
            with self.subTest(username=username):
                data = json.loads((examples / f"{username}.json").read_text())
                validate_introduction_json(data)

    def test_extracts_username_from_direct_json_file_path(self):
        self.assertEqual(username_from_json_url(JSON_URL), "tmcelro3")
        self.assertEqual(
            username_from_json_url("http://127.0.0.1:8765/localuser/introduction.json"),
            "localuser",
        )
        self.assertEqual(
            username_from_json_url("http://127.0.0.1:8765/spate338.json"),
            "spate338",
        )
        with self.assertRaisesRegex(ValueError, "direct link to a .json file"):
            username_from_json_url("https://webpages.charlotte.edu/tmcelro3/itis3135/")

    def test_fetches_a_json_export_from_a_loopback_url(self):
        response_body = json.dumps(SAMPLE_INTRODUCTION).encode("utf-8")

        class JSONHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)

            def log_message(self, format_string, *args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), JSONHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            local_url = f"http://127.0.0.1:{port}/localuser.json"
            response = self.client.post("/sites", json={"json_url": local_url})
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["username"], "localuser")
        record = self.client.get("/sites").json()["localuser"]
        self.assertEqual(record["baseSiteUrl"], f"http://127.0.0.1:{port}/")
        data = record["introductionData"]
        self.assertEqual(data["firstName"], "Thomas")
        self.assertEqual(len(data["courses"]), 1)


if __name__ == "__main__":
    unittest.main()
