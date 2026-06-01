# Automated Daily LinkedIn Content Generator

Built for Max Bennett, Technical Account Manager at RavenTrack — an iGaming affiliate tracking platform. This system monitors iGaming industry RSS feeds every morning, scores articles for relevance to your role, generates a 200-300 word LinkedIn post in your voice using a local AI model, runs quality checks, and emails you the post ready to copy-paste.

---

## What This Does

Here is the full workflow from start to finish:

1. **Fetch RSS feeds** — pulls the latest articles from igamingbusiness.com, casinobeats.com, sbcnews.co.uk, and affiliateinsider.com
2. **Score articles** — each article is scored based on how relevant it is to your area of expertise. Topics like affiliate tracking, attribution, data analytics, regulation, and CRM score highest
3. **Detect trends** — the system checks `topic_history.json` to avoid repeating topics you have posted about recently
4. **Generate a LinkedIn post** — sends the top article and your personal opinions to Ollama (a local AI running on your machine) to draft a post
5. **QA check** — scores the post for authenticity, readability, and LinkedIn suitability (all out of 10). Regenerates if any score falls below 8
6. **Email the post** — sends the finished post to your inbox via Gmail SMTP
7. **Archive** — saves the post to `generated_posts/YYYY-MM-DD.txt` and logs the run to `logs/YYYY-MM-DD.log`

The whole process runs automatically every day at 07:00 UK time. You open your email, read the post, and paste it into LinkedIn if you like it. Nothing else required.

---

## Prerequisites

Before you start, make sure you have or can install the following:

- **Python 3.10 or higher** — the programming language this project runs on
- **Ollama** — a free tool that runs AI models locally on your computer (no API fees, no internet required for generation)
- **Git** — optional, only needed if you want to use GitHub Actions for automation
- **Gmail account with App Password** — standard Gmail login will not work; you need a special app password (instructions below)

---

## Installation Guide

Work through these steps in order. Each one builds on the last.

---

### Step 1: Install Python

**On Windows:**
1. Go to [python.org/downloads](https://python.org/downloads)
2. Click the yellow "Download Python 3.x.x" button
3. Run the installer
4. On the first screen, check the box that says **"Add Python to PATH"** — this is important, do not skip it
5. Click "Install Now"

**On Mac:**
- Option A (recommended): If you have Homebrew installed, open Terminal and run:
  ```
  brew install python3
  ```
- Option B: Download the installer from [python.org/downloads](https://python.org/downloads) and run it

**Verify the installation:**
```
python --version
```
or on Mac:
```
python3 --version
```
You should see something like `Python 3.11.4`. If you get an error, Python was not installed correctly — try again and make sure "Add to PATH" was checked on Windows.

---

### Step 2: Install Ollama

Ollama is the software that runs the AI model on your computer. This keeps your content generation private, fast, and free.

**On Mac:**
- Option A: Open Terminal and run:
  ```
  brew install ollama
  ```
- Option B: Download from [ollama.com](https://ollama.com) and run the installer

**On Windows:**
- Download the installer from [ollama.com](https://ollama.com) and run it

**Verify Ollama installed:**
```
ollama --version
```

**Start Ollama** (you need to keep this running whenever you use the system):
```
ollama serve
```
Leave this terminal window open. Open a new terminal for the remaining steps.

**Pull the AI model** (this downloads about 4GB — takes 5 to 10 minutes):
```
ollama pull llama3
```
Wait for this to finish completely before moving on.

**Test that it works:**
```
ollama run llama3 "Hello, are you working?"
```
You should get a response. Type `/bye` to exit the chat.

---

### Step 3: Download This Project

**With Git:**
```
git clone [your-repo-url]
cd Linkedin
```

**Without Git:**
1. Download the ZIP file from the repository page
2. Extract it to a folder on your computer (e.g., `C:\Users\Max\Linkedin` on Windows or `/Users/maxbennett/Desktop/Linkedin` on Mac)
3. Open a terminal and navigate into that folder:
   ```
   cd /Users/maxbennett/Desktop/Linkedin
   ```
   Windows:
   ```
   cd C:\Users\Max\Linkedin
   ```

---

### Step 4: Create a Gmail App Password

Gmail blocks normal password logins from scripts for security reasons. Instead, you create a special one-time "App Password" that only this project uses.

**Step by step:**
1. Go to [myaccount.google.com](https://myaccount.google.com)
2. Click **Security** in the left sidebar
3. If you have not already, enable **2-Step Verification** — App Passwords are only available once this is on
4. Once 2-Step Verification is active, search for **"App Passwords"** in the search bar at the top of the page
5. You may be asked to sign in again
6. Under "Select app", choose **Mail**
7. Under "Select device", choose **Windows Computer** (or Mac — it does not actually matter)
8. Click **Generate**
9. Copy the **16-character password** shown in the yellow box — it looks like `abcd efgh ijkl mnop`

**Important:** This is not your regular Gmail password. Store it somewhere safe. You will not be able to see it again after closing that screen (but you can always generate a new one).

---

### Step 5: Set Up Environment Variables

Your Gmail credentials need to be stored in a `.env` file. This file is never shared or committed to Git — it lives only on your machine.

**Copy the example file:**

Mac/Linux:
```
cp .env.example .env
```

Windows:
```
copy .env.example .env
```

**Open `.env` in any text editor** (Notepad, TextEdit, VS Code) and fill in your values:

```
GMAIL_USER=youraddress@gmail.com
GMAIL_APP_PASSWORD=abcdefghijklmnop
RECIPIENT_EMAIL=youraddress@gmail.com
```

- `GMAIL_USER` — the Gmail address you generated the App Password for
- `GMAIL_APP_PASSWORD` — the 16-character password from Step 4 (no spaces)
- `RECIPIENT_EMAIL` — where you want the finished post emailed (can be the same address or a different one)

Save the file.

---

### Step 6: Install Python Dependencies

The project uses a few Python libraries that need to be installed. They are all listed in `requirements.txt`.

Make sure your terminal is inside the project folder, then run:

```
pip install -r requirements.txt
```

On Mac, you may need:
```
pip3 install -r requirements.txt
```

This should complete in under a minute. You will see a list of packages being installed.

---

### Step 7: Test the Setup

Run the script manually to make sure everything is working:

```
python main.py
```

Mac:
```
python3 main.py
```

**What to expect:**
```
Fetching RSS feeds...         (may take 30 seconds)
Scoring articles...
Generating post with Ollama... (may take 2-5 minutes with llama3)
QA check...
Sending email...
Done! Check your inbox.
```

If you see all of those lines and receive an email, the setup is complete.

If something goes wrong, check the Troubleshooting section at the bottom of this file, or look at the log file in `logs/` for details.

---

### Step 8: Automate — Option A: Windows Task Scheduler

This option runs the script automatically on your Windows PC every morning. Your computer must be turned on at 07:00 for this to work.

**Find your Python path first:**
```
where python
```
It will return something like `C:\Python311\python.exe` — copy this.

**Find your project folder path:**
Open File Explorer, navigate to the project folder, and copy the path from the address bar. It will look like `C:\Users\Max\Linkedin`.

**Set up the scheduled task:**
1. Press the Windows key and search for **Task Scheduler** — open it
2. In the right-hand panel, click **Create Basic Task**
3. **Name:** `LinkedIn Post Generator` — click Next
4. **Trigger:** Select Daily — click Next
5. **Start time:** Set to `07:00:00` — click Next
6. **Action:** Select "Start a program" — click Next
7. **Program/script:** Paste the Python path from above (e.g., `C:\Python311\python.exe`)
8. **Add arguments:** `main.py`
9. **Start in:** Paste your project folder path (e.g., `C:\Users\Max\Linkedin`)
10. Click Next, then **Finish**
11. In the Task Scheduler library, find your new task, right-click it, and choose **Properties**
12. Go to the **Conditions** tab and uncheck **"Start the task only if the computer is on AC power"** — otherwise it will not run on a laptop on battery
13. Click OK

To test it, right-click the task and choose **Run**. Check your inbox and the `logs/` folder.

---

### Step 9: Automate — Option B: GitHub Actions

This option runs the script in the cloud using GitHub's free automation service. Your computer does not need to be on. It runs at 07:00 UTC every day (adjust the cron schedule in the workflow file if you want UK time with BST offset).

**Note on speed:** GitHub Actions needs to install Ollama and download the model (~4GB) on every single run, which takes 15-20 minutes. The post still arrives, just later than 07:00. If speed matters, use Option A (Task Scheduler) instead. If reliability and not needing your PC on matters more, use this option.

**Steps:**
1. Go to [github.com](https://github.com) and create a new repository (click the + icon, then "New repository")
2. Push this project to that repository:
   ```
   git init
   git add .
   git commit -m "feat: initial commit"
   git remote add origin https://github.com/yourusername/your-repo-name.git
   git push -u origin main
   ```
3. In your GitHub repository, go to **Settings** → **Secrets and variables** → **Actions**
4. Click **New repository secret** and add these three secrets one at a time:
   - Name: `GMAIL_USER` — Value: your Gmail address
   - Name: `GMAIL_APP_PASSWORD` — Value: the 16-character app password
   - Name: `RECIPIENT_EMAIL` — Value: where to send the post
5. The workflow file at `.github/workflows/daily_post.yml` is already configured to run at 07:00 UTC daily
6. Go to the **Actions** tab in your repository to see run history, logs, and status

---

### Step 10: Customise Your Setup

#### Change the AI Model

Edit `config.json` and change the `model` field:

```json
{"model": "mistral", "qa_min_score": 8, "post_min_words": 200, "post_max_words": 300}
```

Available models and their trade-offs:
- `llama3` — default, good balance of quality and speed, ~4GB
- `mistral` — faster than llama3, slightly smaller, good quality
- `gemma` — Google's model, tends toward more creative writing

You must pull the model before switching to it:
```
ollama pull mistral
```

#### Add Your Own RSS Sources

Open `rss_sources.json` and add or remove feed URLs. Any RSS feed URL works. To disable a feed without deleting it, you can remove it from the list temporarily.

#### Update Your Opinions

Open `opinions.txt` and write your genuine views on iGaming industry topics. The more specific and personal these are, the more authentic your generated posts will sound. Write in the same way you would speak to a client. There are no rules on format — just add your thoughts one per line or in paragraphs.

Examples of useful opinions:
- Views on first-party data vs third-party tracking
- What good affiliate attribution actually looks like
- Where you think regulation is heading
- Common mistakes operators make with CRM

---

## Project Structure

```
Linkedin/
├── main.py                     # Main script — runs the full workflow
├── config.py                   # Loads .env and config.json, defines constants
├── config.json                 # Model selection and QA/post length settings
├── .env                        # Your private credentials (never share this)
├── .env.example                # Template for .env — safe to share
├── rss_sources.json            # List of RSS feed URLs to monitor
├── topic_history.json          # Tracks recently used topics to avoid repetition
├── opinions.txt                # Your personal views injected into posts
├── requirements.txt            # Python package dependencies
├── prompts/
│   └── linkedin_prompt.txt     # Jinja2-style prompt template for post generation
├── generated_posts/
│   └── YYYY-MM-DD.txt          # One file per day — archive of all generated posts
├── logs/
│   └── YYYY-MM-DD.log          # One log file per day — check here when things go wrong
└── .github/
    └── workflows/
        └── daily_post.yml      # GitHub Actions workflow for cloud automation
```

**What each file does:**

| File | Purpose |
|------|---------|
| `main.py` | Orchestrates the full pipeline: fetch → score → generate → QA → email → archive |
| `config.py` | Single source of truth for all settings; reads `.env` and `config.json` |
| `config.json` | User-editable settings — model name, minimum QA scores, post word count |
| `.env` | Private credentials — Gmail address, app password, recipient address |
| `rss_sources.json` | The RSS feeds to monitor each morning |
| `topic_history.json` | Prevents the same topic appearing in consecutive posts |
| `opinions.txt` | Your voice — injected into the prompt so posts sound like you |
| `prompts/linkedin_prompt.txt` | The instruction template sent to Ollama for post generation |
| `generated_posts/` | Archive of every post generated, one file per date |
| `logs/` | Detailed run logs — timestamps, scores, errors, decisions |

---

## Troubleshooting

### Ollama not responding

**Symptom:** Error mentioning "connection refused" or "failed to connect to localhost:11434"

**Fix:**
1. Make sure Ollama is running — open a terminal and run `ollama serve`
2. Test the connection directly:
   ```
   curl http://localhost:11434/api/tags
   ```
   You should get a JSON response listing your installed models. If you get an error, Ollama is not running.
3. On Mac, check if Ollama is in your menu bar (top right) — there may be an icon for it

---

### Email not sending

**Symptom:** Error mentioning SMTP, authentication, or "Username and Password not accepted"

**Fix:**
1. Double-check your App Password — it should be exactly 16 characters with no spaces when saved in `.env`
2. Make sure `GMAIL_USER` is your full Gmail address including `@gmail.com`
3. Verify that IMAP is enabled on your Gmail account:
   - Open Gmail
   - Click the gear icon → See all settings
   - Click the "Forwarding and POP/IMAP" tab
   - Make sure "Enable IMAP" is selected
   - Save changes
4. If you recently changed your Google password, regenerate the App Password — the old one will have been invalidated

---

### Posts sound generic or AI-generated

**Symptom:** The post does not sound like you, uses buzzwords, or feels impersonal

**Fix:**
1. Add more specific, opinionated content to `opinions.txt` — the more concrete and personal your views, the better
2. Try a different model in `config.json` — `mistral` sometimes produces more natural-sounding output than `llama3`
3. Review `prompts/linkedin_prompt.txt` — you can edit the tone instructions to be more specific to how you like to write

---

### RSS feeds failing or returning no articles

**Symptom:** "No articles found" or errors during the fetch stage

**Fix:**
1. Some RSS feeds block automated requests periodically — this is temporary and usually resolves itself the next day
2. If a specific feed keeps failing, open `rss_sources.json` and remove or comment out that URL
3. Test an individual feed by visiting its URL in your browser — if you see XML, the feed is live

---

### QA keeps rejecting posts

**Symptom:** "Regenerating post — QA score below threshold" appears repeatedly, or the script fails after too many attempts

**Fix:**
1. Lower the minimum QA score in `config.json`:
   ```json
   {"model": "llama3", "qa_min_score": 7, "post_min_words": 200, "post_max_words": 300}
   ```
2. Try a different model — some models score more consistently on the QA metrics
3. Check `opinions.txt` is not empty — very sparse opinions can lead to bland posts that score poorly

---

### Python not found

**Symptom:** `python: command not found` or `'python' is not recognized`

**Fix:**
- On Mac, try `python3` instead of `python`
- On Windows, Python was likely installed without adding it to PATH. Reinstall from python.org and check the "Add Python to PATH" box on the first screen of the installer

---

## Logs

Every run writes a log file to `logs/YYYY-MM-DD.log`. This is the first place to check when something goes wrong.

The log contains:
- Timestamps for each stage of the pipeline
- How many articles were fetched from each feed
- The scores of the top-ranked articles
- Which topic was selected and why
- QA scores for each generated post attempt
- Whether the email was sent successfully
- Any errors with full details

To view today's log on Mac/Linux:
```
cat logs/$(date +%Y-%m-%d).log
```

On Windows, open the file in Notepad from the `logs/` folder.

---

## Future Enhancements

Potential improvements planned for future versions:

- **LinkedIn API direct posting** — post directly to LinkedIn without copy-pasting (requires a LinkedIn Developer App and OAuth approval)
- **Slack notification** — send the post to a Slack channel alongside the email
- **Multiple post variations** — generate two or three versions per day for A/B testing which performs better
- **Web dashboard** — a simple local web interface to browse post history, scores, and topic frequency
- **Sentiment analysis** — score the tone of generated content before sending (positive, neutral, authoritative)
- **RavenTrack data integration** — pull real anonymised metrics from RavenTrack to ground posts in actual data points, making them more credible and specific
- **Engagement tracking** — manually log which posts you published and track patterns in what performs well
