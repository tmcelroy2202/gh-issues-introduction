# Introduction JSON API

This FastAPI service downloads an introduction JSON export, validates its structure, and stores it in SQLite. Public JSON links must be hosted directly on `webpages.charlotte.edu`; local test links may use exactly `127.0.0.1`. For Charlotte URLs, the first URL path segment is the username and SQLite primary key. For a local URL ending in `/username.json`, the filename stem is used as the username.

## Start the API

From this directory, create and activate the local virtual environment, install dependencies, and start Uvicorn:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

The SQLite database is created as `introductions.sqlite3` in this directory. Set `INTRO_API_DATABASE` to use another database path.

## Endpoints

`POST /sites` and `PUT /sites` accept:

```json
{
  "json_url": "https://webpages.charlotte.edu/tmcelro3/itis3135/introduction_generated.json"
}
```

`POST` creates the username record or refreshes it if it already exists. `PUT` always upserts the same record. Both return the username and a record containing metadata plus the fetched JSON under `introductionData`.

`GET /sites` (also `GET /`) returns a JSON object keyed by username:

```json
{
  "tmcelro3": {
    "lastUpdated": "2026-09-26T12:34:56.000000+00:00",
    "jsonUrl": "https://webpages.charlotte.edu/tmcelro3/itis3135/introduction_generated.json",
    "baseSiteUrl": "https://webpages.charlotte.edu/tmcelro3/",
    "introductionData": {
      "firstName": "Thomas",
      "lastName": "McElroy",
      "courses": []
    }
  }
}
```

Introduction exports use camelCase consistently: `prettyNameDivider` names the
display-name separator, each course uses `reasonForTaking`, and the statement,
background, and work-computer fields are grouped under `personalInfo`. Its
`statement` field contains the personal statement. Legacy flat personal fields
and `reasonfortaking` are rejected with a validation error.

The API's interactive documentation is at `/docs`.

For local testing, serve a JSON export at a path such as `http://127.0.0.1:9000/localuser/introduction.json` and submit that URL. Other loopback aliases and local-network hosts are rejected.

## Example exports

The API directory includes `tmcelro3.json`, `spate338.json`, `ndudley2.json`, and `hgibso21.json`. The latter three are examples based on these introduction pages:

- <https://webpages.charlotte.edu/spate338/itis3135/introduction.html>
- <https://webpages.charlotte.edu/ndudley2/itis3135/introduction.html>
- <https://webpages.charlotte.edu/hgibso21/itis3135/introduction.html>

Fields not present on those pages are left blank. To submit one of these local files, run a static server in this directory in a separate terminal:

```bash
python3 -m http.server 9000
```

Then POST or PUT a URL such as `http://127.0.0.1:9000/spate338.json` to the API.

Invalid URLs, links outside the allowed host, and JSON that does not match the introduction export return a `422` response. Fetch failures return `502` or `504` with a detail message; oversized exports return `413`.

## Tests

With the virtual environment active:

```bash
python -m unittest discover -s tests -v
```
