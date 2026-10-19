# 🚀 Deploying AdvertFloz to Streamlit Cloud & Cloudflare (ELI5 Step-by-Step)

Congratulations! Your code is already committed and pushed to GitHub at:  
👉 **[https://github.com/pravindev666/AdvertFloz](https://github.com/pravindev666/AdvertFloz)**

This guide walks you through the exact steps to deploy your private dashboard to **Streamlit Community Cloud** and set up **Cloudflare (D1, R2, and Worker)** so your campaigns post automatically 24/7/365 at **₹0 cost**.

---

## 📋 The Overview: What We Are Doing

```
   1. STREAMLIT CLOUD (5 min)         2. CLOUDFLARE R2 & D1 (5 min)        3. WORKER DEPLOY (3 min)
  ┌─────────────────────────┐        ┌────────────────────────────┐       ┌───────────────────────┐
  │ Host your Dashboard UI  │  --->  │ Create Cloud DB + Storage  │ --->  │ Deploy 24/7 Publisher │
  │ Protected by Master Key │        │ Holds posts & images at $0 │       │ Runs Cron in Cloud    │
  └─────────────────────────┘        └────────────────────────────┘       └───────────────────────┘
```

---

## Part 1: Deploy Dashboard to Streamlit Cloud (Takes 5 Minutes)

Streamlit Community Cloud gives you free hosting for your dashboard.

### Step 1.1: Log in to Streamlit Cloud
1. Go to **[share.streamlit.io](https://share.streamlit.io)**.
2. Click **Continue with GitHub** and authorize Streamlit to access your GitHub repositories.

### Step 1.2: Create New App
1. Click the blue **"Create app"** button (or **"New app"**).
2. Choose **"I already have an app"**.
3. Fill in the repository details:
   - **Repository:** `pravindev666/AdvertFloz`
   - **Branch:** `main`
   - **Main file path:** `streamlit_app.py`
   - **App URL:** (You can customize it, e.g. `advertfloz-musikflo.streamlit.app`)

### Step 1.3: Add Your Secrets (Lock Down With Your Master Password)
Before clicking Deploy, click **"Advanced settings..."** (at the bottom of the form):
1. In the **Secrets** box, paste the following configuration:
   ```toml
   # Operating mode
   ADVERTFLOZ_MODE = "remote"
   ADVERTFLOZ_DEFAULT_TIMEZONE = "Asia/Kolkata"

   # 🔒 Your Master Access Password (Choose any strong password):
   ADVERTFLOZ_ADMIN_PASSWORD = "ChooseYourStrongPassword123!"

   # Meta Developer App (Leave blank for now, or fill if you have them):
   META_APP_ID = ""
   META_APP_SECRET = ""
   META_GRAPH_VERSION = "v21.0"

   # Token Encryption (Required for saving Meta tokens safely):
   TOKEN_ENCRYPTION_KEY_ID = "k1"
   # To generate a 32-byte key, run in your terminal: 
   # python -m advertfloz.infrastructure.security.crypto genkey
   TOKEN_ENCRYPTION_KEY = ""

   # Cloudflare Worker Connection (We will fill this in Part 3):
   WORKER_BASE_URL = ""
   WORKER_SERVICE_KEY = ""
   ```
2. Click **Save**.
3. Click **Deploy!**

### Step 1.4: Verify Your Dashboard Is Live & Protected
- Streamlit will take ~1–2 minutes to build dependencies.
- Once loaded, you will see your **Operator Authentication Screen**:
  > 🔒 **"AdvertFloz Operator Authentication — Enter Master Access Key"**
- Type your `ADVERTFLOZ_ADMIN_PASSWORD` and click **Unlock**.
- **Boom!** Your private marketing dashboard is live on the internet, accessible from your phone or laptop, and completely locked to strangers!

---

## Part 2: Set Up Free Cloudflare Storage (D1 & R2)

Now we set up Cloudflare so your images and post schedules have a permanent home in the cloud that **never sleeps and never pauses**.

### Step 2.1: Log in to Cloudflare
1. Go to **[dash.cloudflare.com](https://dash.cloudflare.com)** and create a free account (or log in).
2. In the left sidebar, click **Storage & Databases** -> **R2 (Object Storage)**.
   - If prompted, click **Purchase R2 Plan** (it is **$0/month free tier**; Cloudflare gives you 10 GB free forever).
   - Click **Create bucket**.
   - Name it: `advertfloz-media`
   - Click **Create Bucket**. Done!

### Step 2.2: Create Your Cloudflare D1 Database
1. Open PowerShell on your computer and navigate to your project directory:
   ```powershell
   cd c:\Users\hp\Desktop\AdvertFloz\advertfloz\worker
   ```
2. Make sure you are logged into Wrangler (Cloudflare's official tool):
   ```powershell
   npx wrangler login
   ```
   *(A browser window will open. Click **Allow**).*

3. Create the D1 database:
   ```powershell
   npx wrangler d1 create advertfloz-db
   ```
   Wrangler will print output like this:
   ```text
   [[d1_databases]]
   binding = "DB"
   database_name = "advertfloz-db"
   database_id = "xxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
   ```
   👉 **Copy the `database_id` string.**

4. Initialize the SQL database tables:
   ```powershell
   npx wrangler d1 execute advertfloz-db --file=migrations/0001_init.sql --remote
   ```
   *(This creates all tables for campaigns, posts, schedules, and audit events).*

---

## Part 3: Deploy the 24/7 Background Publisher Worker

The Worker is the automated robot that wakes up on a timer, grabs the image from R2, and posts it to Facebook and Instagram.

### Step 3.1: Configure `worker/wrangler.toml`
1. In the `worker/` folder, copy the example config:
   ```powershell
   cp wrangler.toml.example wrangler.toml
   ```
2. Open `worker/wrangler.toml` in your text editor:
   - Paste your `database_id` under `[[d1_databases]]`:
     ```toml
     [[d1_databases]]
     binding = "DB"
     database_name = "advertfloz-db"
     database_id = "PASTE_YOUR_DATABASE_ID_HERE"
     ```
   - Ensure the R2 bucket name matches:
     ```toml
     [[r2_buckets]]
     binding = "MEDIA"
     bucket_name = "advertfloz-media"
     ```
   - Generate a random 32-character string for `WORKER_SERVICE_KEY`:
     *(This is the private password that lets your Streamlit dashboard talk to your Worker).*

### Step 3.2: Deploy the Worker to Cloudflare
In your `worker/` folder, run:
```powershell
npx wrangler deploy
```

Cloudflare will deploy your worker in ~5 seconds and output:
```text
Published advertfloz-worker (https://advertfloz-worker.yourname.workers.dev)
Current Cron Triggers: */15 * * * * (Every 15 minutes)
```

---

## Part 4: Connect Streamlit Cloud to Your Worker

Now connect the two halves so Streamlit can send campaigns to the Worker:

1. Go to your live dashboard on **[share.streamlit.io](https://share.streamlit.io)**.
2. Click **Settings** (the 3 dots at top right) -> **Edit Secrets**.
3. Fill in the Worker details:
   ```toml
   WORKER_BASE_URL = "https://advertfloz-worker.yourname.workers.dev"
   WORKER_SERVICE_KEY = "YOUR_WORKER_SECRET_KEY"
   ```
4. Click **Save**.

Streamlit will automatically refresh.

---

## 🎉 The Result: You Now Have a 100% Autonomous System!

| Where Everything Happens | Component | Cost | Sleep Status |
| :--- | :--- | :--- | :--- |
| **Control Dashboard** | Streamlit Cloud (`advertfloz.streamlit.app`) | **$0** | Hibernates when idle; wakes up when you visit. Protected by Master Key. |
| **Media Storage** | Cloudflare R2 (`advertfloz-media`) | **$0** | 10 GB free forever. Never pauses. Zero egress fees. |
| **Post Database** | Cloudflare D1 (`advertfloz-db`) | **$0** | Serverless SQL database. Never pauses. |
| **Daily Publisher** | Cloudflare Worker Cron | **$0** | Wakes up 24/7/365 to post on schedule while your laptop is off. |

---

## 🚦 Daily Usage Workflow (How You Run Campaigns Now)

1. **On your phone or laptop:** Open your Streamlit URL -> Enter your Master Password.
2. **Build Prompt:** Go to **Marketing Prompt Builder** -> Generate Master Prompt.
3. **Generate with ChatGPT:** Paste into ChatGPT -> Get CSV and images (`1.jpg`, `2.jpg`...).
4. **Import:** Zip them up and upload in **Campaign Import**.
5. **Inspect:** Check the **Calendar** and **Instagram 3x3 Grid**.
6. **Activate:** Click **Activate Campaign**.
7. **Close your browser and turn off your laptop!** Cloudflare Worker will publish each post on its scheduled day and time automatically.
