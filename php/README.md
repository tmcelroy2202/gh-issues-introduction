# PHP + SQLite implementation

This implementation is independent of GitHub and Cloudflare. The browser sends
only a Charlotte username; PHP constructs the JSON URL, fetches and validates
that student's public file, then atomically inserts or replaces that username's
SQLite row. A failed fetch or validation leaves the previous row unchanged.

## DreamHost setup

Upload `index.php` as the endpoint on your DreamHost site. Enable PHP with the
`curl` and `pdo_sqlite` extensions. Use PHP 8.1 or newer.

Set these environment variables for the PHP site (for example in the hosting
configuration or an Apache `.htaccess` file):

```apache
SetEnv INTRODUCTIONS_DB_PATH /home/ACCOUNT/data/introductions.sqlite3
SetEnv INTRODUCTIONS_ALLOWED_ORIGIN https://webpages.charlotte.edu
SetEnv INTRODUCTIONS_SOURCE_BASE_URL https://webpages.charlotte.edu
SetEnv INTRODUCTION_JSON_PATH itis3135/introduction_generated.json
```

Put the SQLite file in a directory outside the public web root and make sure the
PHP process can create and write it. The endpoint creates the table on first use.
`INTRODUCTIONS_SOURCE_BASE_URL` defaults to `https://webpages.charlotte.edu`.
It can be set to an origin on `127.0.0.1` for local testing; no other source
hosts are allowed. `INTRODUCTION_JSON_PATH` is relative to each username
directory. Set it to the location where students publish their generated
introduction JSON.

## API

Submit from a page on `webpages.charlotte.edu`:

```js
const response = await fetch("https://YOUR-DREAMHOST-HOST/php/index.php", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ username: "abc123" })
});
const result = await response.json();
```

PHP constructs:

```text
https://webpages.charlotte.edu/abc123/itis3135/introduction_generated.json
```

For local testing, put the generated JSON under a matching local directory and
serve it on loopback. For example:

```sh
mkdir -p /tmp/introduction-site/tmcelro3/itis3135
cp introduction_generated.json /tmp/introduction-site/tmcelro3/itis3135/
python3 -m http.server 8765 --directory /tmp/introduction-site
```

Run the PHP endpoint with `INTRODUCTIONS_SOURCE_BASE_URL=http://127.0.0.1:8765`;
the POST body remains `{"username":"tmcelro3"}` and PHP fetches
`http://127.0.0.1:8765/tmcelro3/itis3135/introduction_generated.json`.

The default path can be changed with `INTRODUCTION_JSON_PATH`. Successful
submissions return the updated record. Validation/fetch errors return a JSON
`detail` message and an HTTP error status.

Read the class data:

```text
GET https://YOUR-DREAMHOST-HOST/php/index.php
```

The response is keyed by username and uses the same record shape as the other
implementations: `lastUpdated`, `jsonUrl`, `baseSiteUrl`, and
`introductionData`.

## Validation and operations

The endpoint accepts only usernames matching a 1–39 character account-name
pattern, fetches only from HTTPS `webpages.charlotte.edu` or the configured
`127.0.0.1` loopback source, disables redirects, times out outbound requests,
and caps the linked JSON at 5 MiB. It
validates the current camelCase introduction schema, including
`prettyNameDivider`, `personalInfo`, course `reasonForTaking`, and Base64 image
data URLs. SQLite is updated only after the entire document passes validation.

CORS allows the configured `INTRODUCTIONS_ALLOWED_ORIGIN` and handles OPTIONS
preflight requests. Without an `Origin` header, command-line and server-side
clients can still call the endpoint. Use HTTPS for the endpoint and keep the
database outside the public directory.
