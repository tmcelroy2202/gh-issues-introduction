import base64
import binascii
import re
from urllib.parse import urlsplit

import httpx


ALLOWED_HOST = "webpages.charlotte.edu"
LOCAL_HOST = "127.0.0.1"
REQUIRED_FIELDS = {
    "firstName",
    "lastName",
    "acknowledgment",
    "acknowledgmentDate",
    "adjectives",
    "animal",
    "img",
    "caption",
    "personalStatement",
    "personalBackground",
    "professionalBackground",
    "academicBackground",
    "primaryWorkComputer",
    "primaryWorkLocation",
    "alternateComputerLocation",
    "courses",
    "quote",
    "quoteAuthor",
    "footerLinks",
}
COURSE_FIELDS = {"department", "courseNumber", "courseTitle", "reasonfortaking"}
IMAGE_DATA_PATTERN = re.compile(r"^data:image/[A-Za-z0-9.+-]+;base64,")
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
MAX_JSON_SIZE = 5 * 1024 * 1024


class ScrapeError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def username_from_json_url(json_url: str) -> str:
    try:
        parsed = urlsplit(json_url.strip())
        port = parsed.port
    except ValueError as error:
        raise ValueError("The JSON URL is malformed.") from error

    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("The JSON URL must use HTTP or HTTPS.")
    if parsed.hostname is None or parsed.hostname.lower() not in {ALLOWED_HOST, LOCAL_HOST}:
        raise ValueError(f"The JSON URL must be hosted on {ALLOWED_HOST} or {LOCAL_HOST}.")
    if parsed.username or parsed.password:
        raise ValueError("The JSON URL must not contain login credentials.")
    if parsed.hostname.lower() == ALLOWED_HOST and port not in {None, 80, 443}:
        raise ValueError("The JSON URL must use the standard web port.")

    path_parts = [part for part in parsed.path.split("/") if part]
    if not path_parts or not path_parts[-1].lower().endswith(".json"):
        raise ValueError("Provide a direct link to a .json file.")

    if parsed.hostname.lower() == LOCAL_HOST and len(path_parts) == 1:
        username = path_parts[0][:-5]
    else:
        if len(path_parts) < 2:
            raise ValueError("The JSON file must be inside a username directory.")
        username = path_parts[0]
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("The username in the URL path or filename is invalid.")
    return username


def validate_introduction_json(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ScrapeError(422, "The linked JSON must contain an introduction object.")

    missing_fields = sorted(REQUIRED_FIELDS.difference(payload))
    if missing_fields:
        raise ScrapeError(
            422,
            "The JSON does not look like an introduction export; missing keys: "
            + ", ".join(missing_fields),
        )

    for field in REQUIRED_FIELDS.difference({"courses", "footerLinks"}):
        if not isinstance(payload[field], str):
            raise ScrapeError(422, f"The introduction value '{field}' must be a string.")

    image_data = payload["img"].strip()
    if not IMAGE_DATA_PATTERN.match(image_data):
        raise ScrapeError(422, "The 'img' value must be a Base64 data URL for an image.")
    try:
        base64.b64decode(image_data.partition(",")[2], validate=True)
    except (binascii.Error, ValueError) as error:
        raise ScrapeError(422, "The 'img' value contains invalid Base64 data.") from error

    courses = payload["courses"]
    if not isinstance(courses, list):
        raise ScrapeError(422, "The 'courses' value must be a list.")
    for index, course in enumerate(courses, start=1):
        if not isinstance(course, dict):
            raise ScrapeError(422, f"Course {index} must be an object.")
        missing_course_fields = sorted(COURSE_FIELDS.difference(course))
        if missing_course_fields:
            raise ScrapeError(
                422,
                f"Course {index} is missing keys: " + ", ".join(missing_course_fields),
            )
        for field in COURSE_FIELDS:
            if not isinstance(course[field], str) or not course[field].strip():
                raise ScrapeError(422, f"Course {index} has an empty or invalid '{field}' value.")

    footer_links = payload["footerLinks"]
    if not isinstance(footer_links, list):
        raise ScrapeError(422, "The 'footerLinks' value must be a list.")
    for index, link in enumerate(footer_links, start=1):
        if not isinstance(link, dict) or not isinstance(link.get("label"), str) or not isinstance(link.get("url"), str):
            raise ScrapeError(422, f"Footer link {index} must have string 'label' and 'url' values.")

    return payload


async def fetch_introduction_json(json_url: str) -> dict:
    username_from_json_url(json_url)
    original_host = urlsplit(json_url).hostname.lower()
    timeout = httpx.Timeout(20.0, connect=8.0)
    headers = {"User-Agent": "ITIS3135-Introduction-API/1.0"}

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, headers=headers) as client:
            response = await client.get(json_url)
    except httpx.InvalidURL as error:
        raise ScrapeError(422, "The JSON URL is malformed.") from error
    except httpx.TimeoutException as error:
        raise ScrapeError(504, "Timed out while fetching the JSON file.") from error
    except httpx.RequestError as error:
        raise ScrapeError(502, f"Could not fetch the JSON file: {error.__class__.__name__}.") from error

    if response.url.host.lower() != original_host:
        raise ScrapeError(422, "The JSON URL redirected to a different host.")
    if response.status_code < 200 or response.status_code >= 300:
        raise ScrapeError(502, f"The JSON URL returned HTTP {response.status_code}.")
    if len(response.content) > MAX_JSON_SIZE:
        raise ScrapeError(413, "The JSON file is larger than the 5 MiB API limit.")

    try:
        payload = response.json()
    except ValueError as error:
        raise ScrapeError(422, "The linked file is not valid JSON.") from error

    return validate_introduction_json(payload)
