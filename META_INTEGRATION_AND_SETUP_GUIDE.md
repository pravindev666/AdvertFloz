# 📘 Meta (Facebook & Instagram) Integration Guide for AdvertFloz

A complete, step-by-step reference for integrating your **Meta Developer App** with AdvertFloz, Streamlit Cloud, and Cloudflare Worker.

---

## 🏗️ 1. Mental Model & Architecture

```
                                  OAuth Handshake
   [ Streamlit Cloud ]  ─────────────────────────────────►  [ Meta Graph API ]
 (advertfloz.streamlit.app)                                  (Facebook / Instagram)
          │                                                          │
          │ Service Key                                              │ Authorized
          ▼                                                          ▼ Redirect
   [ Cloudflare Worker ]  ◄──────────────────────────────────────────┘
(advertfloz-worker.pravindev666.workers.dev)
       ├── Seals token with TOKEN_ENCRYPTION_KEY
       └── Stores long-lived token in D1 Database (advertfloz-db)
```

### ⚠️ Critical Rule: "Business" App Type vs "Consumer" App Type
* ❌ **Consumer Login App**: Only gives access to personal user data (`user_birthday`, `user_friends`, `user_gender`). It will reject publishing scopes with an `"Invalid Scopes"` error.
* ✅ **Business App Type**: Mandatory for AdvertFloz. Gives you developer access to your **Facebook Pages** (`pages_manage_posts`, `pages_show_list`) and **Instagram Professional Accounts** (`instagram_content_publish`, `instagram_basic`).

---

## 🚀 2. Step-by-Step Meta App Setup

### Step 2.1: Create the App via the "Other ➔ Business" Flow
1. Go to **[developers.facebook.com/apps](https://developers.facebook.com/apps)** and log in with your Facebook account.
2. Click the green/blue **Create App** button.
3. On the *Add use cases* screen, scroll to the very bottom text:
   > *"Looking for something else? ... **Other**"*  
   > Click the blue word **"Other"**.
4. On the *Select an app type* screen, choose **Business** ➔ Click **Next**.
5. Fill in your details:
   - **App name**: `AdvertFloz Business` (or any name you prefer)
   - **App contact email**: Your email address
   - **Business portfolio**: Choose *"I don't want to connect a business portfolio yet"* (or connect yours if you have one).
6. Click **Create app** (enter your Facebook password if prompted).

---

### Step 2.2: Configure App Settings & Domains
1. In the left sidebar of your new app, click **App settings ➔ Basic**.
2. Copy your credentials:
   - **App ID**: *(e.g. `959652643419554`)*
   - **App secret**: Click the **Show** button, enter your Facebook password, and copy the secret string.
3. Set **App domains**:
   - In the **App domains** box, add:
     - `workers.dev`
     - `streamlit.app`
4. Add Website Platform:
   - Scroll to the bottom of the page and click **+ Add platform**.
   - Select **Website** ➔ Click **Next**.
   - In **Site URL**, paste:
     ```text
     https://advertfloz.streamlit.app
     ```
5. Click **Save changes** at the bottom right.

---

### Step 2.3: Set the Allowed OAuth Redirect URIs
This tells Meta where to send the user back after they authorize access.

1. In the left sidebar, find **Facebook Login for Business** (or click **Use cases** ➔ **Customize** next to Facebook Login).
2. Click **Settings** under Facebook Login.
3. Scroll to **Valid OAuth Redirect URIs** and paste:
   ```text
   https://advertfloz-worker.pravindev666.workers.dev/oauth/meta/callback
   ```
   *(Optional for local laptop testing, also add on a new line: `http://localhost:8765/oauth/meta/callback`)*
4. Scroll down and click **Save changes**.

---

## 🔐 3. Adding Your Keys to AdvertFloz

### 3.1 In Streamlit Cloud (https://advertfloz.streamlit.app/)
1. Go to your live dashboard at **[https://advertfloz.streamlit.app/](https://advertfloz.streamlit.app/)**.
2. Click **Settings** (top right 3 dots or sidebar) ➔ **Edit Secrets**.
3. Ensure the secrets block includes your Meta App keys:

```toml
# Operating mode
ADVERTFLOZ_MODE = "remote"
ADVERTFLOZ_DEFAULT_TIMEZONE = "Asia/Kolkata"

# Master Operator Password
ADVERTFLOZ_ADMIN_PASSWORD = "Pravin@265070"

# Token Encryption Key
TOKEN_ENCRYPTION_KEY_ID = "k1"
TOKEN_ENCRYPTION_KEY = "E6gZFvWS90dd7uvz9P3McdYWnXUS2N72KfYRAx2znOA="

# Cloudflare 24/7 Worker Connection
WORKER_BASE_URL = "https://advertfloz-worker.pravindev666.workers.dev"
WORKER_SERVICE_KEY = "MO67_rDIDi3-4SzfVENyxFhpzQtxQbr4hGl-kozd5QY"

# Meta Developer App Credentials
META_APP_ID = "YOUR_META_APP_ID"
META_APP_SECRET = "YOUR_META_APP_SECRET"
META_GRAPH_VERSION = "v21.0"
```
4. Click **Save**.

### 3.2 In Cloudflare Worker
The worker performs the server-to-server token exchange with Meta. Upload your `META_APP_SECRET` to the worker by running this in PowerShell:

```powershell
cd c:\Users\hp\Desktop\AdvertFloz\advertfloz\worker
"YOUR_META_APP_SECRET" | npx wrangler secret put META_APP_SECRET
```

---

## 🔗 4. Authorizing Facebook & Instagram

1. Open **[https://advertfloz.streamlit.app/](https://advertfloz.streamlit.app/)** and sign in with your master password (`Pravin@265070`).
2. In the left sidebar, click **Connections & Credentials**.
3. Click the blue **"Connect Facebook Page"** button.
4. In the Meta authorization pop-up:
   - Select your Facebook Page(s).
   - Select your connected Instagram Professional account(s).
   - Grant all requested permissions (`pages_show_list`, `pages_manage_posts`, `instagram_content_publish`, etc.).
   - Click **Done / Allow**.
5. The pop-up closes and your dashboard updates:
   - ✅ **Facebook**: Connected
   - ✅ **Instagram**: Connected

---

## 🛠️ 5. Troubleshooting & Error Directory

| Error Message | Why It Happened | How to Fix It |
| :--- | :--- | :--- |
| **`Invalid Scopes`** (`pages_show_list`, `instagram_content_publish`...) | App was created as a **Consumer** app rather than a **Business** app. | Create a new app at [developers.facebook.com/apps](https://developers.facebook.com/apps) ➔ Click **Other** ➔ Select **Business**. |
| **`Can't load URL: The domain of this URL isn't included in the app's domains`** | Meta blocked the redirect domain. | In **App settings ➔ Basic**, add `workers.dev` and `streamlit.app` into **App domains**, and add **Website** platform with `https://advertfloz.streamlit.app`. |
| **Token expiration** | Meta short-lived user tokens expire in 1–2 hours. | AdvertFloz automatically exchanges the authorization code for a **60-day long-lived page token**, encrypted in D1 with AES-GCM-256 (`TOKEN_ENCRYPTION_KEY`). |
| **Publishing stops on laptop sleep** | Running on `localhost`. | Use the hosted **Streamlit Cloud + Cloudflare Worker** flow so posts publish autonomously 24/7/365. |
