# Runbook — token reauthorization

## Symptoms

- Overview shows a token warning (T−14 or expired).
- Publishing Queue rows move to `PAUSED` with error class `auth`.
- Reliability shows an `authorization` incident.

## Steps

1. Open **Connections & Credentials** and confirm which platform is affected.
2. Click **Connect <platform>**. Complete Meta's official authorization (no password or token is
   ever typed into AdvertFloz).
3. Re-select the target Page/account and run the connection test, then a confirmed test post.
4. Resume the platform: **Resume <platform>** on the platform page or in the queue.
5. Confirm the previously paused rows return to `QUEUED` and the incident is resolved.

## Notes

- Only the affected platform is paused; the other platform keeps its own state.
- A pause prevents new dispatch. An already in-flight provider call cannot be recalled.
- Never paste a token to "fix" auth; re-authorize instead.
