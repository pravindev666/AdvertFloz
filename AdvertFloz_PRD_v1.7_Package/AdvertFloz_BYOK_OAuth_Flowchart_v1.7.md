# AdvertFloz BYOK and OAuth connection flow — v1.7

```mermaid
flowchart TD
    A[Open Connections & Credentials] --> B{App/deployment configured?}
    B -->|No| C[Installation owner configures Meta App ID/Secret and callback in deployment secrets]
    C --> B
    B -->|Yes| D[Click Connect Facebook]
    D --> E[Redirect browser to official Meta authorization]
    E --> F[User signs in on Meta and approves permissions]
    F --> G[Secured backend OAuth callback]
    G --> H{OAuth state/callback/scopes valid?}
    H -->|No| I[Reject callback; show safe error]
    H -->|Yes| J[Exchange code server-side; fetch authorized Pages]
    J --> K[User selects returned Page name and ID]
    K --> L[Permission test and confirmed Facebook test post]
    L --> M{Facebook test passed?}
    M -->|No| N[Keep Facebook disabled; diagnose/reconnect]
    M -->|Yes| O[Save Page metadata, encrypted token and expiry/scope metadata]
    O --> P[Connect Instagram]
    P --> Q[Use configured official Meta login flow]
    Q --> R[Discover eligible professional Instagram account]
    R --> S{Eligible account found and permissions valid?}
    S -->|No| T[Keep Instagram disabled; explain eligibility/linking steps]
    S -->|Yes| U[Confirm username/ID and run separate test publish]
    U --> V{Instagram test passed?}
    V -->|No| W[Keep Instagram disabled; reconnect or remediate]
    V -->|Yes| X[Save encrypted credentials and account metadata]
    X --> Y[Readiness gate: alerts, storage, sync, backup and restore tests]
    Y --> Z[Only then enable controlled campaign activation]
```

## Ownership boundary

- The operator provides account consent on Meta and selects the returned Page/account.
- The installer supplies Meta App/Cloudflare/GitHub/Telegram secrets through deployment secret settings. They are not ordinary form fields.
- OAuth access tokens are received by the backend and never shown in the UI.
- Page names/IDs are provider metadata. They are not credentials.
- Each platform has an independent readiness and pause state.
