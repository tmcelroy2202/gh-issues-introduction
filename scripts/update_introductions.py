#!/usr/bin/env python3
"""Fetch one submitted introduction and upsert it in introductions.json."""

import base64
import binascii
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "introductions.json"
ALLOWED_HOST = "webpages.charlotte.edu"
MAX_JSON_SIZE = 5 * 1024 * 1024
REQUIRED_FIELDS = {
    "firstName", "lastName", "acknowledgment", "acknowledgmentDate",
    "adjectives", "animal", "img", "caption", "personalStatement",
    "personalBackground", "professionalBackground", "academicBackground",
    "primaryWorkComputer", "primaryWorkLocation", "alternateComputerLocation",
    "courses", "quote", "quoteAuthor", "footerLinks",
}
COURSE_FIELDS = {"department", "courseNumber", "courseTitle", "reasonfortaking"}
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
def submitted_url(body: str) -> str:
    # Issue forms render input values after their matching field labels.
    match = re.search(r"### Introduction JSON URL\s*\n+([^\n]+)", body, re.IGNORECASE)
    value = match.group(1).strip() if match else ""
    value = value.strip("` ")
    if not value or value.lower() in {"_no response_", "no response"}:
        raise ValueError("The issue is missing its Introduction JSON URL field.")
    return value


def username_for(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https" or parsed.hostname is None or parsed.hostname.lower() != ALLOWED_HOST:
        raise ValueError(f"The URL must use HTTPS on {ALLOWED_HOST}.")
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("The URL must not contain credentials or a nonstandard port.")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or not parts[-1].lower().endswith(".json"):
        raise ValueError("Provide a direct .json file inside a username directory.")
    username = parts[0]
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("The username in the URL is invalid.")
    return username


def validate(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("The linked JSON must contain an object.")
    missing = REQUIRED_FIELDS - payload.keys()
    if missing:
        raise ValueError("Missing required introduction keys: " + ", ".join(sorted(missing)))
    for key in REQUIRED_FIELDS - {"courses", "footerLinks"}:
        if not isinstance(payload[key], str):
            raise ValueError(f"'{key}' must be a string.")
    image = payload["img"]
    image_match = re.fullmatch(r"data:image/[A-Za-z0-9.+-]+;base64,([A-Za-z0-9+/]*={0,2})", image)
    if not image_match:
        raise ValueError("'img' must be a Base64 image data URL.")
    try:
        base64.b64decode(image_match.group(1), validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("'img' contains invalid Base64 data.") from error
    courses = payload["courses"]
    if not isinstance(courses, list):
        raise ValueError("'courses' must be a list.")
    for index, course in enumerate(courses, start=1):
        if not isinstance(course, dict) or not COURSE_FIELDS <= course.keys():
            raise ValueError(f"Course {index} is missing required course fields.")
        if any(not isinstance(course[key], str) or not course[key].strip() for key in COURSE_FIELDS):
            raise ValueError(f"Course {index} contains an empty or invalid field.")
    links = payload["footerLinks"]
    if not isinstance(links, list) or any(
        not isinstance(link, dict) or not isinstance(link.get("label"), str)
        or not isinstance(link.get("url"), str) for link in links
    ):
        raise ValueError("'footerLinks' must be a list of objects with string label and url values.")
    return payload


def fetch_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "Introduction-Data-GitHub-Action/1.0"})

    class SameHostRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, new_url):
            parsed = urlsplit(new_url)
            if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
                raise ValueError("The URL redirected away from the approved HTTPS host.")
            return super().redirect_request(req, fp, code, msg, headers, new_url)

    try:
        with build_opener(SameHostRedirect()).open(request, timeout=20) as response:
            if urlsplit(response.geturl()).hostname != ALLOWED_HOST:
                raise ValueError("The URL redirected to a different host.")
            data = response.read(MAX_JSON_SIZE + 1)
    except (HTTPError, URLError, TimeoutError) as error:
        raise ValueError(f"Could not fetch the JSON URL: {error}.") from error
    if len(data) > MAX_JSON_SIZE:
        raise ValueError("The JSON file exceeds the 5 MiB limit.")
    try:
        return validate(json.loads(data))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("The linked file is not valid UTF-8 JSON.") from error


def main() -> None:
    try:
        url = submitted_url(os.environ.get("ISSUE_BODY", ""))
        username = username_for(url)
        payload = fetch_json(url)
        records = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if not isinstance(records, dict):
            raise ValueError("introductions.json must contain an object keyed by username.")
        records[username] = {
            "lastUpdated": datetime.now(timezone.utc).isoformat(),
            "jsonUrl": url,
            "baseSiteUrl": f"https://{ALLOWED_HOST}/{username}/",
            "introductionData": payload,
        }
        DATA_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(f"username={username}\n")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"::error::{error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
