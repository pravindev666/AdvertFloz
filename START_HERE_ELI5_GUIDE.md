# AdvertFloz — Quick Start & Setup Guide (ELI5)

A simple, step-by-step guide explaining **what keys you need, where to get them, where to put them, and how to create your image ZIP**.

---

## 🌟 The Big Picture (Mental Model)

1. **You do NOT need an OpenAI or Anthropic AI API key!** AdvertFloz never makes paid AI API calls. Instead, you download the master prompt from AdvertFloz, paste it directly into ChatGPT or Claude in your browser, and download your campaign plan CSV.
2. **You do NOT paste Facebook/Instagram passwords into AdvertFloz.** You connect your social accounts safely via official Meta OAuth (a pop-up window where you click "Allow").
3. AdvertFloz matches each post to an image purely by number:
   - Post `P001` looks for `1.jpg`
   - Post `P002` looks for `2.jpg`
   - Post `P042` looks for `42.jpg`
   - Post `P365` looks for `365.jpg`

---

## Step 1: How to Name and Create the Image ZIP

### 1. How to name your image files
- Every image **MUST** be named with its plain positive number:
  - Day 1 / Post 1: `1.jpg`
  - Day 42 / Post 42: `42.jpg`
  - Day 365 / Post 365: `365.jpg`
- ❌ **Do NOT use leading zeros:** Do *not* write `001.jpg` or `042.jpg`.
- ❌ **Do NOT add prefixes or words:** Do *not* write `image-1.jpg`, `P001.jpg`, or `pic_1.jpg`.
- ❌ **Do NOT rename `.png` to `.jpg`:** The file must be an actual JPEG image (export or save it as JPEG from your design software).

### 2. How to pack the ZIP file (Flat Structure Rule)
You can create a 30-day pilot ZIP or a full-year ZIP. The ZIP file must be named:
- **30-day pilot:** `advertfloz_images_001_030.zip` (holds `1.jpg` through `30.jpg`)
- **365-day full year:** `advertfloz_images_001_365.zip` (holds `1.jpg` through `365.jpg`)

> [!IMPORTANT]
> **No folders inside the ZIP!**
> 1. Select all your images (`1.jpg`, `2.jpg`, etc.) directly inside your folder.
> 2. Right-click the selected files -> **Compress to ZIP file** (or **Send to -> Compressed (zipped) folder**).
> 3. Name the resulting file `advertfloz_images_001_030.zip`.
>
> When you double-click open the ZIP file, you should see `1.jpg`, `2.jpg` immediately — **NOT** a subfolder like `images/` or `my_photos/`.

---

## Step 2: What Keys Do You Need & Where to Get Them?

You only need **two things** to post to social media:
1. **Meta Developer App** (Free from Meta/Facebook).
2. **Token Encryption Key** (Generated locally on your laptop in 2 seconds).
3. *(Optional)* **Telegram Bot** (If you want phone alerts and a pause button).

---

### 🔑 Getting Meta Developer Keys (Facebook & Instagram)

1. Go to [developers.facebook.com](https://developers.facebook.com) and log in with your Facebook account.
2. Click **My Apps** (top right) -> **Create App**.
3. Choose:
   - **What do you want your app to do?** -> Select **Other** -> Next.
   - **App Type** -> Select **Business** -> Next.
   - Enter an **App name** (e.g. `MyAdvertFlozPublisher`) and click **Create App**.
4. In your Meta App Dashboard:
   - In the left sidebar, click **App Settings** -> **Basic**.
   - You will see:
     - **App ID** (e.g. `123456789012345`)
     - **App Secret** (click "Show" and enter your Facebook password to reveal it).
5. In the left sidebar, click **Facebook Login for Business** -> **Settings**:
   - Under **Valid OAuth Redirect URIs**, enter:
     ```text
     http://localhost:8765/oauth/meta/callback
     ```
   - Click **Save changes**.

---

### 🔐 Generating Your Local Encryption Key

AdvertFloz encrypts stored login tokens so nobody can read them from your database.
1. Open PowerShell in the `advertfloz` folder.
2. Run this command:
   ```powershell
   & ".venv\Scripts\python.exe" -m advertfloz.infrastructure.security.crypto genkey
   ```
3. It will print a 32-byte secret key (e.g. `AbCdEf123456789...=`). Copy this string.

---

### 📱 Optional: Telegram Bot Keys (Phone Alerts & Kill Switch)

If you want phone alerts and a pause button:
1. Open Telegram and search for `@BotFather`.
2. Send `/newbot`, follow the instructions, and give it a name.
3. `@BotFather` will reply with your **Bot Token** (`123456789:ABCdefGHI...`).
4. Search for `@userinfobot` on Telegram and click Start — it will display your **Chat ID** (e.g. `987654321`).

---

## Step 3: Where to Put the Keys

In your project folder `C:\Users\hp\Desktop\AdvertFloz\advertfloz`:

1. Create a file named `.env` (it is gitignored, keeping your keys private on your machine).
2. Paste the following configuration, replacing the placeholders with your actual values:

```env
# 1. Operating mode
ADVERTFLOZ_MODE=local
ADVERTFLOZ_DB_PATH=data/advertfloz.sqlite
ADVERTFLOZ_DEFAULT_TIMEZONE=Asia/Kolkata

# 2. Local OAuth listener
OAUTH_CALLBACK_HOST=127.0.0.1
OAUTH_CALLBACK_PORT=8765
ADVERTFLOZ_CONTROL_PLANE_URL=http://localhost:8501

# 3. Meta Developer App Keys (from Step 2)
META_APP_ID=your_meta_app_id_here
META_APP_SECRET=your_meta_app_secret_here
META_OAUTH_REDIRECT_URI=http://localhost:8765/oauth/meta/callback
META_GRAPH_VERSION=v21.0

# 4. Token Encryption Key (generated in Step 2)
TOKEN_ENCRYPTION_KEY=paste_your_generated_genkey_here
TOKEN_ENCRYPTION_KEY_ID=k1

# 5. Optional Telegram Notifications (leave blank if unused)
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHAT_ID=
```

---

## Step 4: Step-by-Step Workflow in the App

1. **Launch AdvertFloz**:
   ```powershell
   & ".venv\Scripts\streamlit.exe" run streamlit_app.py
   ```
   Open [http://localhost:8501](http://localhost:8501) in your browser.

2. **Step A — Build Your Master Prompt**:
   - Go to **Marketing Prompt Builder** in the sidebar.
   - Enter your brand name, target markets, campaign tag, etc.
   - Click **Validate & build prompt**.
   - Download the **Master Prompt** (`advertfloz_master_prompt.txt`).

3. **Step B — Generate Your Plan with ChatGPT or Claude**:
   - Open ChatGPT or Claude.
   - Paste the downloaded Master Prompt and supply your product info.
   - The AI generates your `campaign_plan.csv` and image prompt library.

4. **Step C — Create Your Images & ZIP**:
   - Generate your images and name them `1.jpg`, `2.jpg` ... `30.jpg`.
   - Zip them into `advertfloz_images_001_030.zip` (flat structure).

5. **Step D — Import Campaign**:
   - In AdvertFloz, go to **Campaign Import**.
   - Upload `campaign_plan.csv` and `advertfloz_images_001_030.zip`.
   - AdvertFloz validates the hashes, images, and displays the contact sheet.

6. **Step E — Connect Facebook & Instagram**:
   - Go to **Facebook Page** -> Click **Connect Facebook**.
   - A Meta pop-up asks you to authorize.
   - Select your Facebook Page and click **Confirm**.
   - Run an explicit test post to verify the connection.

7. **Step F — Review Calendar & Activate**:
   - Check the **Calendar** to review post dates, captions, and image thumbnails in Month, Agenda, or Instagram 3x3 Grid view.
   - When ready, activate the posts for your 30-day pilot!

---

## Step 5: What Happens If Your Laptop Sleeps? (Local vs Cloud Modes)

| Mode | Where Images & Schedule Live | Does Laptop Need to Stay On? | How to Publish |
| :--- | :--- | :--- | :--- |
| **Option A: Meta Business Suite Export** *(Simplest)* | Uploaded directly to Facebook | **NO.** Turn off laptop immediately. | Go to **Reports** -> Click **Export for Meta Business Suite**. Upload CSV to Meta. |
| **Option B: Local Laptop + Cloudflare Tunnel** | Your C: drive + SQLite | **YES.** Laptop must be awake at post time. | Use **Tunnel Helper** tab to expose local images to Meta API while laptop is running. |
| **Option C: Cloudflare Autopilot (Path B)** | Cloudflare D1 + R2 + Worker | **NO.** Runs 24/7 in the cloud at $0 cost. | Deploy `/worker` to Cloudflare. Images in R2, schedule in D1. Never sleeps. |

> [!NOTE]
> **Why Cloudflare over Supabase?**  
> Supabase's free tier automatically pauses after 7 days of inactivity, which breaks 30-day autopilot campaigns. Cloudflare D1 + R2 + Workers never pause and run 365 days a year at $0.

---

## Step 6: How to Protect Your Cloud Dashboard From Strangers

When hosting AdvertFloz on the web (e.g. Streamlit Community Cloud), protect your dashboard from unauthorized visitors:

1. **Option 1 — Master Password Gate (Built-in):**
   - Add `ADVERTFLOZ_ADMIN_PASSWORD=your_secret_password` to your `.env` or Streamlit Secrets.
   - Any visitor must enter this master key on the lock screen before viewing campaigns or API keys.
   - Click **Sign Out / Lock** in the sidebar anytime.

2. **Option 2 — Cloudflare Zero Trust:**
   - Put Cloudflare Access in front of your domain for free (up to 50 users).
   - Only your email receives a 6-digit login PIN. Strangers are completely blocked.

For full architectural diagrams and production deployment guides, see [docs/ARCHITECTURE_AND_DEPLOYMENT.md](file:///c:/Users/hp/Desktop/AdvertFloz/advertfloz/docs/ARCHITECTURE_AND_DEPLOYMENT.md).
