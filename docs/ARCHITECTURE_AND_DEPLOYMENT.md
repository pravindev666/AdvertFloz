# AdvertFloz — Architecture & Deployment Blueprint (ELI5 to Production)

This document provides the definitive architectural breakdown of **AdvertFloz**, comparing local vs. cloud execution, explaining the storage and scheduling pipeline, detailing security/authentication, and outlining the step-by-step deployment runbook for **100% autonomous 24/7 publishing at ₹0 cost**.

---

## 🌟 1. The Core Mental Model (ELI5)

AdvertFloz was built around three fundamental realities of modern social media automation:

1. **Meta (Instagram & Facebook) requires public HTTPS URLs:**  
   You cannot upload a raw image directly from a private `192.168.x.x` home Wi-Fi into Instagram’s API. Meta’s servers in California must be able to fetch your image over public HTTPS.
2. **Laptops sleep; free cloud dashboards hibernate:**  
   - If you close your laptop lid, Windows cuts Wi-Fi and pauses Python.
   - If you host a Streamlit dashboard on Streamlit Community Cloud, it hibernates after 15 minutes of inactivity.
3. **The Zero-Spend ($0/month) Mandate:**  
   Commercial platforms (Buffer, Hootsuite) cost $30–$100/mo because they run paid virtual machines 24/7. To achieve ₹0, **the UI must be allowed to sleep, while the Background Publisher runs serverless.**

---

## 🏛️ 2. The Three Operating Architectures

```
───────────────────────────────────────────────────────────────────────────────
[ ARCHITECTURE A: 100% Serverless Cloud Autopilot (Recommended for Production) ]
───────────────────────────────────────────────────────────────────────────────
      YOUR PHONE / BROWSER
               │
               ▼
   ┌────────────────────────────────────────┐
   │ 🔒 AUTHENTICATION GATE                 │
   │ • Cloudflare Zero Trust (Email PIN) OR │
   │ • Master Password Gate (Admin Key)     │
   └────────────────────────────────────────┘
               │
               ▼
   ┌────────────────────────────────────────┐
   │ 📊 ADVERTFLOZ DASHBOARD (STREAMLIT)    │
   │ Hosted on Streamlit Community Cloud    │
   │ (Free — hibernates when you leave!)    │
   └────────────────────────────────────────┘
               │ (Upload campaign once)
               ▼
   ┌────────────────────────────────────────────────────────┐
   │  CLOUDFLARE CLOUD TRINITY (FREE TIER, NEVER SLEEPS)   │
   │                                                        │
   │  1. Cloudflare D1: SQLite database in the cloud        │
   │     • Stores P001..P365 schedules, captions, statuses  │
   │     • NEVER pauses (no 7-day inactivity hibernation)   │
   │                                                        │
   │  2. Cloudflare R2: Private object storage              │
   │     • Stores 1.jpg .. 365.jpg (10 GB free forever)     │
   │     • ZERO egress / bandwidth transfer fees            │
   │                                                        │
   │  3. Cloudflare Worker: Serverless background robot     │
   │     • Cron Trigger wakes every 15 min at 9:00 AM       │
   │     • Creates 15-min signed temporary R2 link          │
   │     • Calls Meta Graph API to post image + caption     │
   │     • Records PUBLISHED in D1, pings Telegram, sleeps  │
   └────────────────────────────────────────────────────────┘
               │
               ▼
   ┌────────────────────────────────────────┐
   │ 📸 META GRAPH API (FACEBOOK & IG)       │
   │ Post appears live on your social feed! │
   └────────────────────────────────────────┘

───────────────────────────────────────────────────────────────────────────────
[ ARCHITECTURE B: Local Laptop Control Plane + Cloudflare Tunnel ]
───────────────────────────────────────────────────────────────────────────────
   • Streamlit runs locally on your laptop (http://localhost:8501).
   • Database: data/advertfloz.sqlite on your C: drive.
   • Images: Stored on your hard drive.
   • Publishing: When a post is due, Cloudflare Quick Tunnel (cloudflared) exposes 
     http://localhost:8501/media/1.jpg to Meta over a temporary HTTPS URL.
   • Limitation: Laptop must remain powered on and connected to Wi-Fi at post time.

───────────────────────────────────────────────────────────────────────────────
[ ARCHITECTURE C: Local Laptop + Meta Business Suite Bulk Upload (No APIs) ]
───────────────────────────────────────────────────────────────────────────────
   • Use AdvertFloz on your laptop to generate prompts and inspect campaigns.
   • In Reports & Export, click "Export for Meta Business Suite".
   • Upload the generated CSV to Meta Business Suite Planner (business.facebook.com).
   • Meta's servers schedule and post automatically for the next 30 days.
   • Laptop can be turned completely off. Zero API keys or cloud setup required.
───────────────────────────────────────────────────────────────────────────────
```

---

## ⚖️ 3. Why Cloudflare Beats Supabase for Marketing Autopilot

A common question is: *“Why not just use Supabase for Auth and Database?”*

| Architectural Factor | Cloudflare (D1 + R2 + Worker) | Supabase (Free Tier) |
| :--- | :--- | :--- |
| **7-Day Inactivity Rule** | **NEVER PAUSES.** Stays active 365 days a year. | ❌ **PAUSES after 7 days** of no queries. A 30-day autopilot campaign dies on Day 8 unless manually revived! |
| **Media Bandwidth** |  **$0 egress fees** on R2 forever. | ⚠️ Bandwidth quotas and egress charges on storage buckets. |
| **Cron Scheduling** |  **Native Worker Cron Triggers** (built into the platform). | ⚠️ Requires external cron services or pg_cron extensions. |
| **Network Proximity** |  Worker, D1, and R2 sit in the exact same Cloudflare edge node (sub-millisecond latency). | Cross-network HTTP calls between Supabase and worker. |
| **Long-term Autopilot** | 🏆 **10/10 Set-and-forget** | ⚠️ 4/10 Requires weekly dashboard logins to unpause. |

---

## 🔒 4. Access Control & Security: How Strangers Are Blocked

When hosting your AdvertFloz dashboard publicly on the internet (e.g. `advertfloz.streamlit.app`), anyone with the link could potentially access your social tokens and campaigns. AdvertFloz provides **two enterprise-grade protection layers**:

### Method 1: Master Password Gate (Built-in)
- Set `ADVERTFLOZ_ADMIN_PASSWORD=your_secret_password` in your `.env` or Streamlit Secrets.
- Any visitor is greeted by an **Operator Authentication Screen** before any navigation, pages, campaigns, or API keys are rendered.
- Submissions are evaluated using `hmac.compare_digest` to prevent side-channel timing attacks.
- Once unlocked, session state retains authentication with a 1-click **Sign Out / Lock** button in the sidebar.

### Method 2: Cloudflare Zero Trust (Cloudflare Access)
- Cloudflare Access sits in front of your domain for **$0 (up to 50 users)**.
- Rule: Only allow `your-email@gmail.com`.
- Strangers are blocked at the Cloudflare network perimeter and never reach your Streamlit server.
- Authorized operators log in via a 6-digit one-time PIN (OTP) emailed directly by Cloudflare.
- AdvertFloz automatically reads the `Cf-Access-Authenticated-User-Email` header to authenticate you seamlessly.

---

## 🚀 5. Step-by-Step Deployment Runbook (Path B)

Follow this runbook to deploy AdvertFloz to the cloud for autonomous 24/7 publishing:

### Step 1: Set Up Cloudflare Services
1. Install Wrangler CLI (if not already installed):
   ```bash
   npm install -g wrangler
   wrangler login
   ```
2. Create your private R2 media bucket:
   ```bash
   wrangler r2 bucket create advertfloz-media
   ```
3. Create your D1 SQL database:
   ```bash
   wrangler d1 create advertfloz-db
   ```
   *(Copy the `database_id` output into `worker/wrangler.toml`)*
4. Initialize database schema:
   ```bash
   wrangler d1 execute advertfloz-db --file=worker/schema.sql
   ```

### Step 2: Deploy the Cloudflare Background Worker
1. In the `worker/` directory:
   ```bash
   cd worker
   cp wrangler.toml.example wrangler.toml
   # Edit wrangler.toml with your database_id and bucket name
   wrangler deploy
   ```
2. Cloudflare outputs your worker URL (e.g., `https://advertfloz-worker.yourname.workers.dev`).
3. The Worker Cron is now active and will wake up on schedule (e.g., every 15 minutes) to publish pending posts.

### Step 3: Deploy Streamlit to Streamlit Community Cloud
1. Push your repository to a private GitHub repository.
2. Go to [share.streamlit.io](https://share.streamlit.io) and click **New App**.
3. Select your repository, branch `main`, and main file `streamlit_app.py`.
4. Under **Advanced Settings → Secrets**, paste your environment secrets:
   ```toml
   ADVERTFLOZ_MODE = "remote"
   ADVERTFLOZ_ADMIN_PASSWORD = "your_strong_master_password_here"
   WORKER_BASE_URL = "https://advertfloz-worker.yourname.workers.dev"
   WORKER_SERVICE_KEY = "your_worker_secret_key"
   TOKEN_ENCRYPTION_KEY = "your_base64_encryption_key"
   META_APP_ID = "your_meta_app_id"
   META_APP_SECRET = "your_meta_app_secret"
   ```
5. Click **Deploy!**

### Step 4: Verification
1. Visit your new live Streamlit URL.
2. You will be greeted by the **Operator Authentication Screen**. Enter your Master Password.
3. Open the **Campaign Import** tab and upload your campaign ZIP.
4. Check the **Calendar** (Month, Agenda, and Instagram Grid views).
5. Your posts are now queued in Cloudflare D1 with images in R2, scheduled to publish every day automatically!
