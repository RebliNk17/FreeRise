# Security policy

FreeRise stores encrypted bank credentials, so we take security reports seriously.

## Reporting a vulnerability

**Do not open a public issue.** Report privately through
[GitHub Security Advisories](https://github.com/RebliNk17/FreeRise/security/advisories/new).

Include what you found, how to reproduce it, and the impact. We aim to reply within 7 days.

## Supported versions

Only the latest release on `master` receives security fixes.

## Hardening checklist for self-hosters

- Set `FREERISE_ENV=production` so cookies are secure and 2FA is enforced.
- Generate fresh `CREDENTIALS_KEY` and `SESSION_SECRET` values, and back up `CREDENTIALS_KEY`.
- Expose only the web service. Keep the API, worker and Postgres on a private network.
- Serve the web app over HTTPS.
- Leave `FREERISE_FAILURE_SCREENSHOTS` empty in production; screenshots can contain personal data.
