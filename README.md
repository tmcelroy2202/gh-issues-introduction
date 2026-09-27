# gh-issues-introduction

## Static introductions data

The repository contains a no-hosting alternative to the API in [`api/`](api/).
To add or update an introduction, open an [introduction submission issue](../../issues/new?template=introduction-submission.yml)
and provide a direct JSON URL under `https://webpages.charlotte.edu/<username>/`.
The GitHub Action fetches and validates the public JSON, then adds or replaces
that username's record in the root-level [`introductions.json`](introductions.json).
The processed issue is closed automatically. Failed submissions get a comment
with the specific validation or fetch error; fix the issue body and edit the
issue or leave a new comment to retry processing.

Poll the raw file (for example, with a cache-busting query parameter if your
client needs fresh data):

```text
https://raw.githubusercontent.com/OWNER/REPOSITORY/main/introductions.json
```

The JSON is an object keyed by username. Each value contains `lastUpdated`,
`jsonUrl`, `baseSiteUrl`, and `introductionData`. GitHub's raw file delivery is
eventually consistent with the repository and may be slower than the hosted API.
After an update is committed, the raw URL may continue serving a cached older
version for several minutes or longer; GitHub does not guarantee an exact refresh
time. Adding a changing query parameter can help bypass some caches, but it is
not a guaranteed instant-update mechanism.

For a PHP/SQLite implementation that accepts a username directly and fetches
the Charlotte JSON immediately, see [`php/README.md`](php/README.md).

Introduction JSON uses camelCase keys. The display-name separator is
`prettyNameDivider`; course objects use `reasonForTaking`; and the statement,
background, and work-computer fields are grouped in `personalInfo` (including
`personalInfo.statement`). Courses and footer links remain arrays of objects.
