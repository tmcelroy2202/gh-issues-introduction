# gh-issues-introduction

## Static introductions data

The repository contains a no-hosting alternative to the API in [`api/`](api/).
To add or update an introduction, open an [introduction submission issue](../../issues/new?template=introduction-submission.yml)
and provide a direct JSON URL under `https://webpages.charlotte.edu/<username>/`.
The GitHub Action fetches and validates the public JSON, then adds or replaces
that username's record in the root-level [`introductions.json`](introductions.json).
The processed issue is closed automatically; failed submissions get an error
comment and can be edited and resubmitted.

Poll the raw file (for example, with a cache-busting query parameter if your
client needs fresh data):

```text
https://raw.githubusercontent.com/OWNER/REPOSITORY/main/introductions.json
```

The JSON is an object keyed by username. Each value contains `lastUpdated`,
`jsonUrl`, `baseSiteUrl`, and `introductionData`. GitHub's raw file delivery is
eventually consistent with the repository and may be slower than the hosted API.
