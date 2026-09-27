# Cloudflare Worker + D1 implementation

This implementation is independent of the GitHub issue/Actions flow. Clients
submit a direct introduction JSON URL to the Worker; it fetches and validates
the JSON, then inserts or replaces the username's record in D1. The Worker
serves the API from D1.

## Deploy

From this directory:

```sh
npm install
npx wrangler login
npx wrangler d1 create introduction-data
```

Copy the `database_id` printed by Wrangler into `d1_databases[0].database_id`
in `wrangler.jsonc`, replacing `REPLACE_WITH_DATABASE_ID`. Apply the schema and
deploy:

```sh
npx wrangler d1 migrations apply introduction-data --remote
npm run deploy
```

For local development, initialize the local D1 database and start the Worker:

```sh
npx wrangler d1 migrations apply introduction-data --local
npm run dev
```

Wrangler prints the local or deployed Worker URL.

## API

Submit or replace the introduction associated with the username in its URL:

```sh
curl -X POST 'https://YOUR-WORKER.workers.dev/sites' \
  -H 'Content-Type: application/json' \
  -d '{"json_url":"https://webpages.charlotte.edu/USERNAME/itis3135/introduction.json"}'
```

The response includes `username`, `lastUpdated`, `jsonUrl`, `baseSiteUrl`, and
`introductionData`. Invalid or unreachable files return a useful `detail`
message and are not written to D1.

Read all records or one username:

```text
GET https://YOUR-WORKER.workers.dev/sites
GET https://YOUR-WORKER.workers.dev/sites/USERNAME
```

The response shape matches the existing API's `/sites` response, while the
single-user route returns that user's record. Reads are edge-cacheable for 30
seconds with up to 60 seconds of stale-while-revalidate.

The JSON schema uses camelCase consistently: `prettyNameDivider`,
`personalInfo.statement` and related personal fields, and course
`reasonForTaking`. Legacy flat personal fields and `reasonfortaking` are rejected.

## Public submission endpoint

`POST /sites` is intentionally public and does not require a GitHub account.
It only fetches HTTPS JSON on `webpages.charlotte.edu`, checks redirects remain
on that same host, limits the JSON to 5 MiB, and validates required introduction
fields before writing. Since anyone can submit, configure Cloudflare rate
limiting for `POST /sites` in the zone/dashboard before sharing the endpoint
broadly. A submission for an existing username replaces that user's record.
