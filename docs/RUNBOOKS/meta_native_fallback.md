# Runbook — Meta native scheduler fallback (FR-031)

If remote mode is NO-GO (for example the R2 payment prerequisite cannot be met), do not pretend
laptop-off publishing works. Operate with:

1. **Local mode + Meta Business Suite / native scheduling**: import the campaign, approve assets,
   and schedule the posts in Meta Business Suite (or Instagram's native scheduler) yourself.
   AdvertFloz remains the source of truth for the plan, contact sheet, calendar and reporting.
2. **GitHub Actions is not a scheduler.** It may only run CI, tests and deployment after a separate
   proof of concept with external durable state, safe concurrency, pause controls, alerts, retry and
   restore. Never store live campaign state or tokens in Git.

## No assumed import

AdvertFloz does not assume it can import a plan into Meta Business Suite. There is no assumed
horizon for how far ahead native scheduling works either — check the current Meta limits. If native
scheduling cannot cover the window, keep the window short and publish deliberately.

## Reporting

Whatever the scheduling route, record the real outcome and use
**Reports & Export → what_actually_posted.csv** so history stays accurate. Never mark a row
published because it was scheduled elsewhere.
