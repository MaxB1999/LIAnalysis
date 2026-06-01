"""
config.py — Central configuration for the Automated LinkedIn Content Generator.

Loads environment variables from .env, reads config.json for runtime settings,
and exposes all constants used across the pipeline (RSS scoring, Ollama, Gmail,
file paths, QA thresholds, topic-tracking parameters).
"""

import os
import json
import logging
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Bootstrap: load .env before anything else so os.getenv() calls below pick
# up values from the file when the process is launched by the cron job and
# does not inherit a populated shell environment.
# ---------------------------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------------------------
# BASE_DIR
# Absolute path to the directory that contains this file.  All other paths
# are expressed relative to BASE_DIR so the project can be moved without
# breaking any hard-coded paths.
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# config.json — runtime tunables
# The file lets you change the Ollama model, QA thresholds, and post length
# without touching Python source.  Defaults are used when the file is absent.
# ---------------------------------------------------------------------------
_CONFIG_FILE = BASE_DIR / "config.json"

_CONFIG_DEFAULTS = {
    "model": "llama3",
    "qa_min_score": 8,
    "post_min_words": 200,
    "post_max_words": 300,
}

if _CONFIG_FILE.exists():
    with _CONFIG_FILE.open("r", encoding="utf-8") as _fh:
        config_data: dict = json.load(_fh)
else:
    config_data = _CONFIG_DEFAULTS.copy()


# ===========================================================================
# 1. GMAIL / EMAIL
# ===========================================================================

# Gmail address used as the From: sender.
# Must be a real Google account; app password is required (not account password).
GMAIL_USER: str = os.getenv("GMAIL_USER", "")

# Google App Password (16-character token from myaccount.google.com/apppasswords).
# Never commit the real value — keep it in .env only.
GMAIL_APP_PASSWORD: str = os.getenv("GMAIL_APP_PASSWORD", "")

# Destination address for the daily post email.
# Can be the same as GMAIL_USER (send-to-self) or a separate inbox.
RECIPIENT_EMAIL: str = os.getenv("RECIPIENT_EMAIL", "")


# ===========================================================================
# 2. OLLAMA / LLM
# ===========================================================================

# Which local Ollama model to use for post generation.
# Supported values: "llama3" | "mistral" | "gemma"
# Controlled via config.json so you can switch without editing source.
MODEL: str = config_data.get("model", _CONFIG_DEFAULTS["model"])

# Base URL for the Ollama HTTP API running on localhost.
# Change the port only if you started Ollama with a custom --port flag.
OLLAMA_URL: str = "http://localhost:11434/api/generate"

# Seconds to wait for Ollama to return a complete response.
# llama3 on a modern Mac M-series chip typically responds in < 30 s;
# 60 s gives comfortable headroom for longer prompts or slower hardware.
OLLAMA_TIMEOUT: int = 60

# Maximum number of times the pipeline will ask Ollama to regenerate a post
# when the QA step rejects the output.  After MAX_REGENERATIONS attempts the
# pipeline logs a warning and skips the email for today rather than sending
# a low-quality post.
MAX_REGENERATIONS: int = 3


# ===========================================================================
# 3. QA / POST LENGTH
# ===========================================================================

# Minimum acceptable score (1–10) for each QA dimension:
#   • authenticity      — does it sound like Max, not like a chatbot?
#   • readability       — clear sentences, no jargon avalanche?
#   • linkedin_suitability — appropriate length, professional tone?
# Any dimension below this threshold triggers a regeneration cycle.
QA_MIN_SCORE: int = config_data.get("qa_min_score", _CONFIG_DEFAULTS["qa_min_score"])

# Target word-count window for generated posts.
# LinkedIn's algorithm favours 150–300 words; 200–300 hits the sweet spot
# while leaving room for Max's signature sign-off line.
POST_MIN_WORDS: int = config_data.get(
    "post_min_words", _CONFIG_DEFAULTS["post_min_words"]
)
POST_MAX_WORDS: int = config_data.get(
    "post_max_words", _CONFIG_DEFAULTS["post_max_words"]
)


# ===========================================================================
# 4. FILE PATHS
# ===========================================================================

# JSON array of RSS feed URLs to poll each morning.
# Format: ["https://igamingbusiness.com/feed/", ...]
RSS_SOURCES_FILE: Path = BASE_DIR / "rss_sources.json"

# Tracks which article topics have been used in recent posts so the pipeline
# can avoid repeating the same theme too soon.
# Format: {"topics": [{"topic": "...", "date": "YYYY-MM-DD"}, ...]}
TOPIC_HISTORY_FILE: Path = BASE_DIR / "topic_history.json"

# Plain-text file containing Max's personal opinions and stances on key
# iGaming topics.  Injected into the Ollama prompt to ground the post in
# Max's authentic voice rather than generic industry commentary.
OPINIONS_FILE: Path = BASE_DIR / "opinions.txt"

# Jinja2-style prompt template for post generation.
# Variables available inside the template:
#   {{ article_title }}, {{ article_summary }}, {{ trend_context }},
#   {{ opinions }}, {{ min_words }}, {{ max_words }}
PROMPT_FILE: Path = BASE_DIR / "prompts" / "linkedin_prompt.txt"

# Directory where each day's approved post is archived as YYYY-MM-DD.txt.
# Created automatically if it does not exist.
POSTS_DIR: Path = BASE_DIR / "generated_posts"

# Directory for daily rotating log files (YYYY-MM-DD.log).
# Created automatically if it does not exist.
LOGS_DIR: Path = BASE_DIR / "logs"

# Ensure output directories exist at import time so the rest of the pipeline
# can write files without checking first.
POSTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)


# ===========================================================================
# 5. RSS ARTICLE SCORING — keyword weights
# ===========================================================================

# Articles are scored by counting keyword matches in the title + summary.
# A high-priority match contributes 3 points; medium contributes 1 point.
# The highest-scoring article that has not been used recently becomes today's
# post topic.

# Topics directly relevant to RavenTrack's product and Max's TAM expertise.
# Each match adds 3 points to an article's relevance score.
HIGH_PRIORITY_KEYWORDS: list[str] = [
    "affiliate marketing",
    "affiliate tracking",
    "attribution",
    "data analytics",
    "revenue tracking",
    "crm",
    "player acquisition",
    "regulation",
    "compliance",
    "artificial intelligence",
]
# Alias used throughout main.py
HIGH_PRIORITY_TOPICS = HIGH_PRIORITY_KEYWORDS

# Broader iGaming industry terms.  Useful signal but less specific to
# RavenTrack's value proposition.  Each match adds 1 point.
MEDIUM_PRIORITY_KEYWORDS: list[str] = [
    "igaming",
    "casino",
    "sports betting",
    "operator",
    "marketing",
    "technology",
    "growth",
]
# Alias used throughout main.py
MEDIUM_PRIORITY_TOPICS = MEDIUM_PRIORITY_KEYWORDS

# Fallback RSS sources used when rss_sources.json is missing.
DEFAULT_RSS_SOURCES: list[str] = [
    "https://igamingbusiness.com/feed/",
    "https://casinobeats.com/feed/",
    "https://sbcnews.co.uk/feed/",
    "https://affiliateinsider.com/feed/",
]


# ===========================================================================
# 6. TREND DETECTION
# ===========================================================================

# Minimum number of independent articles covering the same topic within the
# current RSS fetch before the pipeline considers it a trending topic.
# A higher value means only strong, multi-source signals are treated as trends.
TREND_THRESHOLD: int = 3

# How many days back the topic history is retained.
# Entries older than this are pruned on each run to keep the file compact.
TOPIC_HISTORY_DAYS: int = 30

# Topics used within this many days receive a score penalty so the pipeline
# naturally rotates through a diverse range of subjects and avoids the
# appearance of obsessing over a single theme.
RECENT_TOPIC_PENALTY_DAYS: int = 7


# ===========================================================================
# 7. CONFIGURATION VALIDATION
# ===========================================================================

def validate_config() -> None:
    """
    Warn loudly — but do not crash — when required environment variables are
    missing.  The pipeline can still run (e.g., to generate and archive a
    post) even without email credentials, so a hard exit here would be
    unnecessarily disruptive during local testing.
    """
    _logger = logging.getLogger(__name__)

    missing: list[str] = []

    if not GMAIL_USER:
        missing.append("GMAIL_USER")
    if not GMAIL_APP_PASSWORD:
        missing.append("GMAIL_APP_PASSWORD")
    if not RECIPIENT_EMAIL:
        missing.append("RECIPIENT_EMAIL")

    if missing:
        _logger.warning(
            "The following required environment variables are not set: %s.  "
            "Email delivery will fail.  Add them to .env or export them "
            "before running the pipeline.",
            ", ".join(missing),
        )

    # Validate Ollama model selection against the known-supported list.
    _supported_models = {"llama3", "mistral", "gemma"}
    if MODEL not in _supported_models:
        _logger.warning(
            "MODEL '%s' is not in the supported list %s.  "
            "Ollama may reject the request at runtime.",
            MODEL,
            sorted(_supported_models),
        )

    # Sanity-check post length bounds.
    if POST_MIN_WORDS >= POST_MAX_WORDS:
        _logger.warning(
            "POST_MIN_WORDS (%d) is not less than POST_MAX_WORDS (%d).  "
            "Check config.json.",
            POST_MIN_WORDS,
            POST_MAX_WORDS,
        )


# Run validation whenever this module is imported so misconfiguration is
# surfaced immediately — in cron output, test runs, or interactive sessions.
validate_config()
