#!/usr/bin/env python3
"""Fetch one submitted introduction and upsert it in introductions.json."""

import base64
import binascii
import json
import os
import re
import sys
import uuid
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
    "prettyNameDivider", "adjectives", "animal", "img", "caption", "personalInfo",
    "courses", "quote", "quoteAuthor", "footerLinks",
}
PERSONAL_INFO_FIELDS = {
    "statement", "personalBackground", "professionalBackground", "academicBackground",
    "primaryWorkComputer", "primaryWorkLocation", "alternateComputerLocation",
}
COURSE_FIELDS = {"department", "courseNumber", "courseTitle", "reasonForTaking"}
LEGACY_TOP_LEVEL_FIELDS = {
    "divider", "personalStatement", "personalBackground", "professionalBackground",
    "academicBackground", "primaryWorkComputer", "primaryWorkLocation",
    "alternateComputerLocation",
}
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class SubmissionFailure(Exception):
    """Submission failed after enough information was gathered for a report."""

    def __init__(self, message: str, report: str):
        super().__init__(message)
        self.report = report


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


def validate(payload: object) -> list[str]:
    errors = []
    if not isinstance(payload, dict):
        return ["The linked JSON root must be an object; found " + json_type(payload) + "."]

    legacy_fields = LEGACY_TOP_LEVEL_FIELDS.intersection(payload)
    if legacy_fields:
        errors.append(
            "Outdated top-level keys found: " + ", ".join(sorted(legacy_fields))
            + ". Use 'prettyNameDivider' and group statement/background/computer fields under 'personalInfo'."
        )
    missing = REQUIRED_FIELDS - payload.keys()
    if missing:
        errors.append("Missing required top-level keys: " + ", ".join(sorted(missing)))
    for key in REQUIRED_FIELDS - {"courses", "footerLinks", "personalInfo"}:
        if key in payload and not isinstance(payload[key], str):
            errors.append(f"'{key}' must be a string (found {json_type(payload[key])}).")
    for key in ("middleName", "nickname", "pictureAlt", "funnyItem", "somethingToShare"):
        if key in payload and not isinstance(payload[key], str):
            errors.append(f"Optional field '{key}' must be a string (found {json_type(payload[key])}).")

    personal_info = payload.get("personalInfo")
    if "personalInfo" in payload and not isinstance(personal_info, dict):
        errors.append(f"'personalInfo' must be an object (found {json_type(personal_info)}).")
    elif isinstance(personal_info, dict):
        missing_personal = PERSONAL_INFO_FIELDS - personal_info.keys()
        if missing_personal:
            errors.append("Missing required personalInfo keys: " + ", ".join(sorted(missing_personal)))
        for key, value in personal_info.items():
            if not isinstance(value, str):
                errors.append(f"'personalInfo.{key}' must be a string (found {json_type(value)}).")

    image = payload.get("img")
    if isinstance(image, str):
        image_match = re.fullmatch(r"data:image/[A-Za-z0-9.+-]+;base64,([A-Za-z0-9+/]*={0,2})", image)
        if not image_match:
            errors.append("'img' must be a Base64 image data URL.")
        else:
            try:
                base64.b64decode(image_match.group(1), validate=True)
            except (binascii.Error, ValueError):
                errors.append("'img' contains invalid Base64 data.")

    courses = payload.get("courses")
    if "courses" in payload and not isinstance(courses, list):
        errors.append(f"'courses' must be an array (found {json_type(courses)}).")
    elif isinstance(courses, list):
        if len(courses) > 100:
            errors.append("'courses' cannot contain more than 100 entries.")
        for index, course in enumerate(courses, start=1):
            if not isinstance(course, dict):
                errors.append(f"Course {index} must be an object (found {json_type(course)}).")
                continue
            if "reasonfortaking" in course:
                errors.append(f"Course {index} uses 'reasonfortaking'; rename it to 'reasonForTaking'.")
            missing_course = COURSE_FIELDS - course.keys()
            if missing_course:
                errors.append(f"Course {index} is missing keys: " + ", ".join(sorted(missing_course)))
            for key, value in course.items():
                if not isinstance(value, str):
                    errors.append(f"Course {index} field '{key}' must be a string (found {json_type(value)}).")
                elif key in COURSE_FIELDS and not value.strip():
                    errors.append(f"Course {index} has an empty '{key}' value.")

    links = payload.get("footerLinks")
    if "footerLinks" in payload and not isinstance(links, list):
        errors.append(f"'footerLinks' must be an array (found {json_type(links)}).")
    elif isinstance(links, list):
        if len(links) > 50:
            errors.append("'footerLinks' cannot contain more than 50 entries.")
        for index, link in enumerate(links, start=1):
            if not isinstance(link, dict):
                errors.append(f"Footer link {index} must be an object (found {json_type(link)}).")
                continue
            for key in ("label", "url"):
                if key not in link:
                    errors.append(f"Footer link {index} is missing '{key}'.")
                elif not isinstance(link[key], str):
                    errors.append(f"Footer link {index} field '{key}' must be a string.")

    return errors


def json_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


def field_list(fields: object, limit: int = 80) -> str:
    names = sorted(fields) if isinstance(fields, (dict, list)) else []
    safe_names = []
    for name in names[:limit]:
        rendered_name = json.dumps(name, ensure_ascii=True)
        if len(rendered_name) > 120:
            rendered_name = rendered_name[:117] + "..."
        safe_names.append(rendered_name)
    rendered = ", ".join(safe_names)
    if len(names) > limit:
        rendered += f", … and {len(names) - limit} more"
    return rendered or "(none)"


def audit_report(payload: object, errors: list[str]) -> str:
    lines = [
        "### JSON inspection",
        "- JSON syntax: **valid**",
        f"- Root value: **{json_type(payload)}**",
    ]
    if isinstance(payload, dict):
        lines.append(f"- Top-level fields present ({len(payload)}): {field_list(payload)}")
        personal_info = payload.get("personalInfo")
        if isinstance(personal_info, dict):
            lines.append(f"- `personalInfo` fields present ({len(personal_info)}): {field_list(personal_info)}")
        elif "personalInfo" in payload:
            lines.append(f"- `personalInfo` is present as {json_type(personal_info)}, not an object")
        else:
            lines.append("- `personalInfo` fields: (personalInfo is missing)")

        courses = payload.get("courses")
        if isinstance(courses, list):
            lines.append(f"- Courses present: {len(courses)}")
            for index, course in enumerate(courses[:20], start=1):
                fields = field_list(course) if isinstance(course, dict) else f"(not an object: {json_type(course)})"
                lines.append(f"  - Course {index} fields: {fields}")
            if len(courses) > 20:
                lines.append(f"  - … and {len(courses) - 20} more courses")
        elif "courses" in payload:
            lines.append(f"- `courses` is present as {json_type(courses)}, not an array")
        else:
            lines.append("- Courses: field missing")

        links = payload.get("footerLinks")
        if isinstance(links, list):
            lines.append(f"- Footer links present: {len(links)}")
            for index, link in enumerate(links[:20], start=1):
                fields = field_list(link) if isinstance(link, dict) else f"(not an object: {json_type(link)})"
                lines.append(f"  - Footer link {index} fields: {fields}")
            if len(links) > 20:
                lines.append(f"  - … and {len(links) - 20} more footer links")
        elif "footerLinks" in payload:
            lines.append(f"- `footerLinks` is present as {json_type(links)}, not an array")
        else:
            lines.append("- Footer links: field missing")

    if errors:
        lines.append("- Introduction schema validation: **failed**")
        lines.append("\n### Validation findings")
        for error in errors[:40]:
            lines.append(f"- {error}")
        if len(errors) > 40:
            lines.append(f"- … and {len(errors) - 40} more findings")
    else:
        lines.append("- Introduction schema validation: **passed**")
        lines.append("- All required, optional, nested, course, and footer-link fields found have valid types and formats.")
    report = "\n".join(lines)
    if len(report) > 30000:
        report = report[:29900] + "\n\n… field report truncated to fit a GitHub issue comment."
    return report


def write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    delimiter = f"{name.upper()}_{uuid.uuid4().hex}"
    with open(output_path, "a", encoding="utf-8") as output:
        output.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")


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
    return parse_json_bytes(data)


def parse_json_bytes(data: bytes) -> object:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        report = (
            "### JSON inspection\n"
            "- JSON syntax: **invalid UTF-8**\n"
            "- Fields: could not inspect because the file is not valid UTF-8.\n"
            "- Introduction schema validation: **not run**"
        )
        raise SubmissionFailure("The linked file is not valid UTF-8 JSON.", report) from error
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        report = (
            "### JSON inspection\n"
            "- JSON syntax: **invalid**\n"
            f"- Parser location: line {error.lineno}, column {error.colno}.\n"
            "- Fields: could not inspect because the JSON document did not parse.\n"
            "- Introduction schema validation: **not run**"
        )
        raise SubmissionFailure(
            f"The linked file is not valid JSON (line {error.lineno}, column {error.colno}).",
            report,
        ) from error


def main() -> None:
    report = ""
    try:
        url = submitted_url(os.environ.get("ISSUE_BODY", ""))
        username = username_for(url)
        payload = fetch_json(url)
        errors = validate(payload)
        report = audit_report(payload, errors)
        write_output("report", report)
        if errors:
            raise SubmissionFailure("The introduction failed schema validation.", report)

        records = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if not isinstance(records, dict):
            raise ValueError("introductions.json must contain an object keyed by username.")
        operation = "updated" if username in records else "added"
        records[username] = {
            "lastUpdated": datetime.now(timezone.utc).isoformat(),
            "jsonUrl": url,
            "baseSiteUrl": f"https://{ALLOWED_HOST}/{username}/",
            "introductionData": payload,
        }
        DATA_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_output("username", username)
        write_output("operation", operation)
    except SubmissionFailure as error:
        details = error.report or report or (
            "### JSON inspection\n"
            "- JSON syntax: **not inspected**\n"
            "- Fields: not inspected because the submission URL could not be processed.\n"
            "- Introduction schema validation: **not run**"
        )
        write_output("feedback", details)
        print(f"::error::{error}", file=sys.stderr)
        raise SystemExit(1) from error
    except (OSError, json.JSONDecodeError, ValueError) as error:
        details = report or (
            "### JSON inspection\n"
            "- JSON syntax: **not inspected**\n"
            "- Fields: not inspected because the JSON could not be fetched.\n"
            "- Introduction schema validation: **not run**"
        )
        details += f"\n\n### Processing error\n- {error}"
        write_output("feedback", details)
        print(f"::error::{error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
