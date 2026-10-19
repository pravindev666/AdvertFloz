# 🛠️ AdvertFloz — Issues Faced, Root Causes & Permanent Solutions

A complete post-mortem and reference guide detailing every technical roadblock encountered during development, deployment, and Meta integration, along with the exact root causes and fixes applied.

---

## 📑 Table of Contents
1. [Campaign Import Wizard & Image ZIP Rejections](#1-campaign-import-wizard--image-zip-rejections)
2. [Streamlit UI State Drops & `StreamlitWidgetAlreadyInstantiatedError`](#2-streamlit-ui-state-drops--streamlitwidgetalreadyinstantiatederror)
3. [Operator Password Gate Visibility](#3-operator-password-gate-visibility)
4. [Cloudflare Storage Confusion: Do We Need S3 Links?](#4-cloudflare-storage-confusion-do-we-need-s3-links)
5. [Meta App Creation: Consumer vs Business App & "Invalid Scopes"](#5-meta-app-creation-consumer-vs-business-app--invalid-scopes)
6. [Meta OAuth Callback: "Domain Not Allowed" & `ERR_CONNECTION_REFUSED`](#6-meta-oauth-callback-domain-not-allowed--err_connection_refused)

---

## 1. Campaign Import Wizard & Image ZIP Rejections

### The Problem
When uploading the campaign ZIP file `advertfloz_images_001_007.zip`, the import validator threw errors and refused to recognize the images.

### Root Causes
1. **Mismatched Image Format**: AI image generation tools produced PNG files, but the packaging script saved them with `.jpeg` extensions. Pillow detected PNG byte signatures (`\x89PNG`) instead of JPEG headers (`\xff\xd8\xff`).
2. **Strict Regex on Filename**: Validation rules only accepted `.jpg` with a 3-character extension; `.jpeg` was rejected.
3. **Nested Directory Structure**: The ZIP contained a top-level directory (`advertfloz_images_NNN_NNN.zip/1.jpeg`) instead of a flat list, violating `len(parts) == 1`.

### The Solution
* In `advertfloz/domain/validation_rules.py`: Updated `IMAGE_FILENAME_RE` to `r"[1-9]\d{0,2}\.jpe?g"`.
* In `advertfloz/infrastructure/storage/zip_validation.py`: Added automatic one-level directory stripping and PNG-to-JPEG conversion on the fly.
* Repacked the user's campaign ZIP flat with true JPEGs, reducing file size from ~11 MB to ~2 MB with 0 errors.

---

## 2. Streamlit UI State Drops & `StreamlitWidgetAlreadyInstantiatedError`

### The Problem
* Navigating between tabs in the import wizard erased previously uploaded CSV and ZIP files.
* Clicking "Next Step" buttons triggered:
  `streamlit.errors.StreamlitWidgetAlreadyInstantiatedError: ... st.session_state["import_step_radio"] = new_step`

### Root Causes
1. **Widget DOM Lifecycle**: `st.file_uploader` clears its in-memory buffer if the widget is removed from the DOM (e.g. when switching steps via radio buttons).
2. **Streamlit Widget Key Mutation**: Streamlit strictly forbids altering a `st.session_state` key tied to an active widget *after* that widget has already been instantiated in the current execution pass.

### The Solution
* **Persistent Upload Callbacks**: Attached `on_change` callbacks (`_persist_plan`, `_persist_zips`, `_persist_manifest`) directly to `st.file_uploader`. Uploaded bytes are saved into session state *before* the script reruns.
* **Pending Step Transition**: Decoupled tab navigation using `st.session_state["pending_step"]`. When "Next" is clicked, it records `pending_step` and calls `st.rerun()`. At the start of the next pass — *before* `st.radio` is rendered — the state is safely updated without lifecycle conflicts.

---

## 3. Operator Password Gate Visibility

### The Problem
The user didn't see the password login card (`ADVERTFLOZ_ADMIN_PASSWORD`) when opening AdvertFloz.

### Root Cause
AdvertFloz is designed to **fail open for local development** when no password is set, allowing developers to iterate quickly without typing a password on every browser refresh. The gate only engages once `ADVERTFLOZ_ADMIN_PASSWORD` is explicitly configured.

### The Solution
* Generated a secure encryption key and created `.env` and `.streamlit/secrets.toml` containing:
  ```toml
  ADVERTFLOZ_ADMIN_PASSWORD = "Pravin@265070"
  ```
* Both files are git-ignored, preventing credentials from ever leaking to GitHub.

---

## 4. Cloudflare Storage Confusion: Do We Need S3 Links?

### The Problem
Users looking at Cloudflare R2 dashboard saw S3 API URLs, CORS policies, and Public Development URL buttons, causing confusion over how Streamlit connects to R2 and D1.

### Root Cause & Clarification
* Streamlit Cloud does **not** connect directly to R2 or D1 via S3 keys.
* Cloudflare Workers use native internal bindings (`env.DB` and `env.MEDIA`). When `npx wrangler deploy` is executed, Cloudflare binds them internally with zero network latency and maximum security.
* Streamlit Cloud only needs two secrets: `WORKER_BASE_URL` and `WORKER_SERVICE_KEY`.

---

## 5. Meta App Creation: Consumer vs Business App & "Invalid Scopes"

### The Problem
Attempting to connect Facebook & Instagram showed:
> `This content isn't available right now. Invalid Scopes: pages_show_list, pages_manage_posts, instagram_content_publish...`

### Root Cause
In Meta's updated Developer UI, choosing the default "Authenticate users with Facebook Login" creates a **Consumer** app. Consumer apps only allow personal user data (`user_birthday`, `user_friends`) and strictly forbid business Page & Instagram publishing permissions.

### The Solution
* Click **Create App ➔ Other ➔ Business**.
* In a **Business App**, Meta natively supports `pages_manage_posts`, `instagram_content_publish`, and `pages_show_list` without restriction for the app developer.

---

## 6. Meta OAuth Callback: "Domain Not Allowed" & `ERR_CONNECTION_REFUSED`

### The Problem
* Meta popup gave: `Can't load URL: The domain of this URL isn't included in the app's domains.`
* Approving the login dialog resulted in: `http://localhost:8765/... ERR_CONNECTION_REFUSED`.

### Root Causes
1. **Missing App Domains**: Meta blocks redirect URIs whose domains are not listed in **App settings ➔ Basic ➔ App domains**.
2. **Missing Local Listener**: For local testing, Meta returns the authorization code to `http://localhost:8765/oauth/meta/callback`. If the local loopback listener (`advertfloz.oauth_callback.app`) isn't running, Windows refuses the connection.
3. **Cloud vs Local Redirect URI**: When running on Streamlit Cloud, the redirect URI must point to the Cloudflare Worker, not `localhost`.

### The Solution
* Added `workers.dev` and `streamlit.app` to **App domains** in Meta.
* Added Website platform with `https://advertfloz.streamlit.app`.
* For local testing: Launched `uvicorn advertfloz.oauth_callback.app:app --port 8765`.
* For cloud deployment: Set `META_OAUTH_REDIRECT_URI = "https://advertfloz-worker.pravindev666.workers.dev/oauth/meta/callback"`.
