"""
Automated Daily LinkedIn Content Generator for Max Bennett
Technical Account Manager at RavenTrack (iGaming affiliate tracking platform)

Orchestrates: RSS fetch → scoring → trend detection → post generation → QA → email → archive
"""

import json
import logging
import os
import re
import smtplib
import time
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from logging.handlers import RotatingFileHandler
from pathlib import Path

import feedparser
import requests

import config


# ---------------------------------------------------------------------------
# 1. Logging
# ---------------------------------------------------------------------------

def setup_logging() -> logging.Logger:
    """Configure rotating file handler to logs/YYYY-MM-DD.log and console."""
    today = datetime.now().strftime("%Y-%m-%d")
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"{today}.log"

    logger = logging.getLogger("linkedin_generator")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        logger.handlers.clear()

    # File handler — rotates at 5 MB, keeps 7 backups
    file_handler = RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=7, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(funcName)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%H:%M:%S")
    console_handler.setFormatter(console_fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.info("Logging initialised. Log file: %s", log_path)
    return logger


# ---------------------------------------------------------------------------
# 2 & 3. Topic history
# ---------------------------------------------------------------------------

def load_topic_history() -> dict:
    """Read topic_history.json; return {'topics': []} if missing or corrupt."""
    logger = logging.getLogger("linkedin_generator")
    history_path = Path("topic_history.json")
    if not history_path.exists():
        logger.info("topic_history.json not found — starting with empty history.")
        return {"topics": []}
    try:
        with open(history_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if "topics" not in data:
            logger.warning("topic_history.json missing 'topics' key — resetting.")
            return {"topics": []}
        logger.info("Loaded topic history with %d entries.", len(data["topics"]))
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load topic_history.json: %s — resetting.", exc)
        return {"topics": []}


def save_topic_history(history: dict) -> None:
    """Write updated history dict to topic_history.json."""
    logger = logging.getLogger("linkedin_generator")
    try:
        with open("topic_history.json", "w", encoding="utf-8") as fh:
            json.dump(history, fh, indent=2, ensure_ascii=False)
        logger.info("Topic history saved (%d entries).", len(history.get("topics", [])))
    except OSError as exc:
        logger.error("Failed to save topic_history.json: %s", exc)


# ---------------------------------------------------------------------------
# 4. RSS fetching
# ---------------------------------------------------------------------------

def fetch_rss_feeds(sources: list[str]) -> list[dict]:
    """
    Fetch all RSS sources using feedparser.

    Returns list of article dicts:
      {title, summary, link, published, source}
    """
    logger = logging.getLogger("linkedin_generator")
    articles = []

    for url in sources:
        logger.info("Fetching RSS feed: %s", url)
        try:
            feed = feedparser.parse(url)
            if feed.bozo and feed.bozo_exception:
                logger.warning("Feed parse warning for %s: %s", url, feed.bozo_exception)

            feed_title = feed.feed.get("title", url)
            entries_found = len(feed.entries)
            logger.debug("Feed '%s' returned %d entries.", feed_title, entries_found)

            for entry in feed.entries:
                title = entry.get("title", "").strip()
                summary = entry.get("summary", entry.get("description", "")).strip()
                # Strip basic HTML tags from summary
                summary = re.sub(r"<[^>]+>", " ", summary).strip()
                link = entry.get("link", "")
                published = entry.get("published", entry.get("updated", ""))

                if not title:
                    logger.debug("Skipping entry with no title from %s.", url)
                    continue

                articles.append(
                    {
                        "title": title,
                        "summary": summary[:1000],  # cap length
                        "link": link,
                        "published": published,
                        "source": feed_title,
                    }
                )

            logger.info("Collected %d articles from '%s'.", entries_found, feed_title)

        except Exception as exc:
            logger.error("Connection error fetching %s: %s — skipping.", url, exc)

        time.sleep(1)  # polite crawl delay

    logger.info("Total articles fetched across all feeds: %d", len(articles))
    return articles


# ---------------------------------------------------------------------------
# 5. Article scoring
# ---------------------------------------------------------------------------

def score_article(article: dict, topic_history: dict) -> float:
    """
    Weighted scoring:
      +3 for each high-priority keyword match
      +1 for each medium-priority keyword match
      -5 if topic appeared in last 7 days
    Returns float score.
    """
    logger = logging.getLogger("linkedin_generator")
    text = (article.get("title", "") + " " + article.get("summary", "")).lower()
    score = 0.0

    for keyword in config.HIGH_PRIORITY_TOPICS:
        if keyword.lower() in text:
            score += 3.0
            logger.debug("High-priority match '%s' in article: '%s'", keyword, article["title"])

    for keyword in config.MEDIUM_PRIORITY_TOPICS:
        if keyword.lower() in text:
            score += 1.0
            logger.debug("Medium-priority match '%s' in article: '%s'", keyword, article["title"])

    # Penalise recently covered topics
    cutoff = datetime.now() - timedelta(days=7)
    recent_keywords = set()
    for entry in topic_history.get("topics", []):
        try:
            entry_date = datetime.strptime(entry["date"], "%Y-%m-%d")
        except (ValueError, KeyError):
            continue
        if entry_date >= cutoff:
            recent_keywords.add(entry.get("keyword", "").lower())

    for keyword in recent_keywords:
        if keyword in text:
            score -= 5.0
            logger.debug("Recent topic penalty applied for '%s' in article: '%s'", keyword, article["title"])

    logger.debug("Article score %.1f for: '%s'", score, article["title"])
    return score


# ---------------------------------------------------------------------------
# 6. Trend detection
# ---------------------------------------------------------------------------

def detect_trends(articles: list[dict]) -> list[str]:
    """
    Find keywords appearing in 3+ article titles/summaries.
    Returns list of trend strings.
    """
    logger = logging.getLogger("linkedin_generator")
    keyword_counts: dict[str, int] = {}

    all_keywords = config.HIGH_PRIORITY_TOPICS + config.MEDIUM_PRIORITY_TOPICS

    for article in articles:
        text = (article.get("title", "") + " " + article.get("summary", "")).lower()
        seen_in_article: set[str] = set()
        for keyword in all_keywords:
            if keyword.lower() in text and keyword.lower() not in seen_in_article:
                keyword_counts[keyword] = keyword_counts.get(keyword, 0) + 1
                seen_in_article.add(keyword.lower())

    trends = [kw for kw, count in keyword_counts.items() if count >= 3]
    trends.sort(key=lambda kw: keyword_counts[kw], reverse=True)

    logger.info("Detected %d trends: %s", len(trends), trends)
    return trends


# ---------------------------------------------------------------------------
# 7 & 8. Post generation
# ---------------------------------------------------------------------------

def _load_prompt_template() -> str:
    """Load the Jinja2-style prompt template from prompts/linkedin_prompt.txt."""
    logger = logging.getLogger("linkedin_generator")
    prompt_path = Path("prompts/linkedin_prompt.txt")
    if not prompt_path.exists():
        logger.warning("prompts/linkedin_prompt.txt not found — using built-in fallback template.")
        return (
            "You are Max Bennett, a Technical Account Manager at RavenTrack, an iGaming affiliate "
            "tracking platform. Write a LinkedIn post (200-300 words) based on the following:\n\n"
            "TOPIC: {{ topic }}\n\n"
            "ARTICLE TITLE: {{ title }}\n\n"
            "ARTICLE SUMMARY: {{ summary }}\n\n"
            "YOUR OPINIONS AND CONTEXT:\n{{ opinions }}\n\n"
            "Requirements:\n"
            "- Write as an experienced practitioner sharing practical observations\n"
            "- No buzzwords, no emojis, no AI-sounding phrases\n"
            "- 200-300 words\n"
            "- Sound like a real person, not a content marketer\n"
            "- End with a genuine question or reflection to spark discussion\n"
        )
    with open(prompt_path, "r", encoding="utf-8") as fh:
        template = fh.read()
    logger.debug("Loaded prompt template (%d chars).", len(template))
    return template


def _call_ollama(prompt: str, model: str) -> str:
    """
    Call local Ollama API at localhost:11434.
    Raises requests.RequestException on failure.
    """
    logger = logging.getLogger("linkedin_generator")
    url = "http://localhost:11434/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False}
    logger.debug("Calling Ollama model '%s' (prompt length: %d chars).", model, len(prompt))
    response = requests.post(url, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    generated = data.get("response", "").strip()
    logger.debug("Ollama returned %d chars.", len(generated))
    return generated


def generate_post_for_article(article: dict, opinions_text: str, cfg) -> str:
    """
    Build prompt from template, call Ollama, return generated post text.
    cfg is the config module.
    """
    logger = logging.getLogger("linkedin_generator")
    logger.info("Generating post for article: '%s'", article.get("title", ""))

    template = _load_prompt_template()

    # Placeholder names match those defined in prompts/linkedin_prompt.txt
    high_priority_str = ", ".join(cfg.HIGH_PRIORITY_KEYWORDS)
    prompt = (
        template
        .replace("{article_title}", article.get("title", ""))
        .replace("{article_source}", article.get("source", ""))
        .replace("{article_summary}", article.get("summary", ""))
        .replace("{high_priority_topics}", high_priority_str)
        .replace("{opinions}", opinions_text)
        .replace("{min_words}", str(cfg.POST_MIN_WORDS))
        .replace("{max_words}", str(cfg.POST_MAX_WORDS))
    )

    try:
        post = _call_ollama(prompt, cfg.MODEL)
        if not post:
            logger.warning("Ollama returned empty response for article post.")
        return post
    except requests.Timeout:
        logger.error("Ollama request timed out after 60s for article: '%s'", article.get("title", ""))
        return ""
    except requests.RequestException as exc:
        logger.error("Ollama request failed for article post: %s", exc)
        return ""


def generate_post_for_trend(trend: str, articles: list[dict], opinions_text: str, cfg) -> str:
    """
    Build trend-focused prompt, call Ollama, return generated post text.
    cfg is the config module.
    """
    logger = logging.getLogger("linkedin_generator")
    logger.info("Generating post for trend: '%s'", trend)

    template = _load_prompt_template()

    # Collect relevant article titles for context
    relevant_titles = []
    for art in articles:
        text = (art.get("title", "") + " " + art.get("summary", "")).lower()
        if trend.lower() in text:
            relevant_titles.append(art.get("title", ""))
        if len(relevant_titles) >= 5:
            break

    trend_articles_text = "\n".join(f"- {t}" for t in relevant_titles)

    # Map trend data into the standard article-based placeholders so the same
    # prompt template works for both article and trend posts.
    high_priority_str = ", ".join(cfg.HIGH_PRIORITY_KEYWORDS)
    trend_summary = (
        f"Multiple recent reports are covering the following trend: {trend}. "
        f"Related headlines:\n{trend_articles_text}"
    )
    prompt = (
        template
        .replace("{article_title}", f"Industry trend: {trend}")
        .replace("{article_source}", "Multiple industry sources")
        .replace("{article_summary}", trend_summary)
        .replace("{high_priority_topics}", high_priority_str)
        .replace("{opinions}", opinions_text)
        .replace("{min_words}", str(cfg.POST_MIN_WORDS))
        .replace("{max_words}", str(cfg.POST_MAX_WORDS))
    )

    try:
        post = _call_ollama(prompt, cfg.MODEL)
        if not post:
            logger.warning("Ollama returned empty response for trend post.")
        return post
    except requests.Timeout:
        logger.error("Ollama request timed out after 60s for trend: '%s'", trend)
        return ""
    except requests.RequestException as exc:
        logger.error("Ollama request failed for trend post: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# 9. QA check
# ---------------------------------------------------------------------------

def qa_check(post_text: str, cfg) -> dict:
    """
    Ask Ollama to score authenticity/readability/linkedin_suitability 1-10.
    Returns dict with keys: authenticity, readability, linkedin_suitability, feedback.
    Returns empty dict on failure.
    """
    logger = logging.getLogger("linkedin_generator")
    logger.info("Running QA check on post (%d words).", len(post_text.split()))

    qa_prompt = (
        "You are a professional LinkedIn content auditor. Evaluate the following post strictly.\n\n"
        "Score each dimension from 1 (very poor) to 10 (excellent):\n"
        "- authenticity: Does it sound like a real person, not AI or a content marketer?\n"
        "- readability: Is it clear, well-structured, and easy to read?\n"
        "- linkedin_suitability: Is it appropriate and effective for LinkedIn?\n\n"
        "Respond with ONLY valid JSON in exactly this format, no other text:\n"
        '{"authenticity": X, "readability": X, "linkedin_suitability": X, "feedback": "brief comment"}\n\n'
        "POST TO EVALUATE:\n"
        "---\n"
        f"{post_text}\n"
        "---"
    )

    try:
        raw_response = _call_ollama(qa_prompt, cfg.MODEL)
    except requests.Timeout:
        logger.error("Ollama QA request timed out.")
        return {}
    except requests.RequestException as exc:
        logger.error("Ollama QA request failed: %s", exc)
        return {}

    # Extract JSON from response — it may include surrounding text
    json_match = re.search(r'\{[^{}]*"authenticity"[^{}]*\}', raw_response, re.DOTALL)
    if not json_match:
        # Broader fallback: find any JSON object
        json_match = re.search(r'\{.*?\}', raw_response, re.DOTALL)

    if not json_match:
        logger.error("Could not extract JSON from QA response: %s", raw_response[:300])
        return {}

    try:
        scores = json.loads(json_match.group())
        required_keys = {"authenticity", "readability", "linkedin_suitability"}
        if not required_keys.issubset(scores.keys()):
            logger.error("QA JSON missing required keys. Got: %s", list(scores.keys()))
            return {}
        logger.info(
            "QA scores — authenticity: %s, readability: %s, linkedin_suitability: %s",
            scores.get("authenticity"),
            scores.get("readability"),
            scores.get("linkedin_suitability"),
        )
        return scores
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse QA JSON: %s | Raw: %s", exc, raw_response[:300])
        return {}


# ---------------------------------------------------------------------------
# 10. Email sending
# ---------------------------------------------------------------------------

def send_email(post_text: str, subject: str, cfg, image_url: str = "") -> bool:
    """
    Send post via Gmail SMTP port 587 with TLS.
    Embeds the image (if provided) in the HTML version of the email.
    Returns True on success, False on failure.
    """
    logger = logging.getLogger("linkedin_generator")
    logger.info("Sending email: '%s' to %s", subject, cfg.RECIPIENT_EMAIL)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.GMAIL_USER
    msg["To"] = cfg.RECIPIENT_EMAIL

    body_plain = (
        f"Your LinkedIn post for {datetime.now().strftime('%Y-%m-%d')} is ready:\n\n"
        f"{post_text}\n\n"
        "---\nGenerated by LinkedIn Content Generator"
    )

    image_html = (
        f"<img src='{image_url}' alt='Article image' "
        f"style='max-width:100%;border-radius:6px;margin-bottom:20px;display:block;'><br>"
        if image_url else ""
    )
    body_html = (
        f"<html><body style='font-family:Georgia,serif;max-width:640px;margin:auto;padding:24px;'>"
        f"{image_html}"
        f"<p style='color:#555;font-size:13px;'>Your LinkedIn post for "
        f"<strong>{datetime.now().strftime('%Y-%m-%d')}</strong> is ready:</p>"
        f"<hr style='border:none;border-top:1px solid #eee;margin:16px 0;'>"
        f"<p style='white-space:pre-wrap;font-size:15px;line-height:1.6;'>{post_text}</p>"
        f"<hr style='border:none;border-top:1px solid #eee;margin:16px 0;'>"
        f"<p style='color:#aaa;font-size:11px;'>Generated by LinkedIn Content Generator</p>"
        f"</body></html>"
    )

    msg.attach(MIMEText(body_plain, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(cfg.GMAIL_USER, cfg.GMAIL_APP_PASSWORD)
            server.sendmail(cfg.GMAIL_USER, cfg.RECIPIENT_EMAIL, msg.as_string())
        logger.info("Email sent successfully to %s.", cfg.RECIPIENT_EMAIL)
        return True
    except smtplib.SMTPAuthenticationError as exc:
        logger.error("SMTP authentication failed: %s", exc)
        return False
    except smtplib.SMTPException as exc:
        logger.error("SMTP error sending email: %s", exc)
        return False
    except OSError as exc:
        logger.error("Network error sending email: %s", exc)
        return False


# ---------------------------------------------------------------------------
# 11. Archiving
# ---------------------------------------------------------------------------

def archive_post(post_text: str, article_or_trend: str) -> None:
    """Save generated post to generated_posts/YYYY-MM-DD.txt."""
    logger = logging.getLogger("linkedin_generator")
    archive_dir = Path("generated_posts")
    archive_dir.mkdir(exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    archive_path = archive_dir / f"{today}.txt"

    separator = "\n" + "=" * 60 + "\n"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content = (
        f"{separator}"
        f"Generated: {timestamp}\n"
        f"Source/Topic: {article_or_trend}\n"
        f"{separator}\n"
        f"{post_text}\n"
    )

    try:
        with open(archive_path, "a", encoding="utf-8") as fh:
            fh.write(content)
        logger.info("Post archived to %s.", archive_path)
    except OSError as exc:
        logger.error("Failed to archive post: %s", exc)


# ---------------------------------------------------------------------------
# 12. Topic history update
# ---------------------------------------------------------------------------

def update_topic_history(history: dict, topics: list[str]) -> dict:
    """
    Add new topics to history with today's date.
    Prune entries older than 30 days.
    Returns updated history dict (immutable pattern — original not mutated).
    """
    logger = logging.getLogger("linkedin_generator")
    today_str = datetime.now().strftime("%Y-%m-%d")
    cutoff = datetime.now() - timedelta(days=30)

    existing_entries = [
        entry for entry in history.get("topics", [])
        if _parse_date(entry.get("date", "")) >= cutoff
    ]

    new_entries = [
        {"keyword": topic, "date": today_str, "title": topic}
        for topic in topics
    ]

    updated_history = {"topics": existing_entries + new_entries}
    logger.info(
        "Updated topic history: added %d entries, pruned to %d total.",
        len(new_entries),
        len(updated_history["topics"]),
    )
    return updated_history


def _parse_date(date_str: str) -> datetime:
    """Parse YYYY-MM-DD string to datetime; return epoch on failure."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return datetime.fromtimestamp(0)


# ---------------------------------------------------------------------------
# 13. Hashtag generation
# ---------------------------------------------------------------------------

# Maps scoring keywords to their LinkedIn hashtag equivalents.
_KEYWORD_HASHTAG_MAP: dict[str, str] = {
    "affiliate marketing":  "#AffiliateMarketing",
    "affiliate tracking":   "#AffiliateTracking",
    "attribution":          "#Attribution",
    "data analytics":       "#DataAnalytics",
    "revenue tracking":     "#RevenueTracking",
    "crm":                  "#CRM",
    "player acquisition":   "#PlayerAcquisition",
    "regulation":           "#GamblingRegulation",
    "compliance":           "#Compliance",
    "artificial intelligence": "#AI",
    "igaming":              "#iGaming",
    "casino":               "#OnlineCasino",
    "sports betting":       "#SportsBetting",
    "operator":             "#iGamingOperator",
    "marketing":            "#DigitalMarketing",
    "technology":           "#GamingTech",
    "growth":               "#BusinessGrowth",
}

_FALLBACK_HASHTAGS: list[str] = [
    "#iGaming", "#AffiliateMarketing", "#GamblingIndustry",
    "#PerformanceMarketing", "#B2BGaming",
]


def generate_hashtags(matched_keywords: list[str]) -> str:
    """
    Build 5 relevant hashtags from the keywords matched during article scoring.
    Always starts with #iGaming, fills remaining slots from matched keywords,
    then falls back to generic iGaming tags if needed.
    Returns a space-separated string ready to append to the post.
    """
    logger = logging.getLogger("linkedin_generator")
    tags: list[str] = ["#iGaming"]  # always first

    for kw in matched_keywords:
        if len(tags) >= 5:
            break
        tag = _KEYWORD_HASHTAG_MAP.get(kw.lower())
        if tag and tag not in tags:
            tags.append(tag)

    for fallback in _FALLBACK_HASHTAGS:
        if len(tags) >= 5:
            break
        if fallback not in tags:
            tags.append(fallback)

    hashtag_str = " ".join(tags[:5])
    logger.info("Generated hashtags: %s", hashtag_str)
    return hashtag_str


# ---------------------------------------------------------------------------
# 14. Image fetching (Pexels free API — optional)
# ---------------------------------------------------------------------------

def fetch_image(search_query: str, api_key: str) -> str:
    """
    Fetch a relevant landscape image URL from the Pexels free API.
    Returns the image URL string, or empty string if unavailable or no key set.
    Sign up free at pexels.com/api — 200 requests/hour on the free tier.
    """
    logger = logging.getLogger("linkedin_generator")
    if not api_key:
        logger.debug("PEXELS_API_KEY not set — skipping image fetch.")
        return ""

    try:
        response = requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": search_query, "per_page": 1, "orientation": "landscape"},
            headers={"Authorization": api_key},
            timeout=10,
        )
        response.raise_for_status()
        photos = response.json().get("photos", [])
        if photos:
            url = photos[0]["src"]["large2x"]
            logger.info("Image fetched from Pexels: %s", url)
            return url
        logger.warning("Pexels returned no photos for query: '%s'", search_query)
    except requests.RequestException as exc:
        logger.warning("Failed to fetch image from Pexels: %s", exc)

    return ""


# ---------------------------------------------------------------------------
# 13. Main orchestration
# ---------------------------------------------------------------------------

def main() -> None:
    """Orchestrate all steps with full error handling and logging."""
    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("LinkedIn Content Generator starting up.")
    logger.info("Date: %s | Model: %s", datetime.now().strftime("%Y-%m-%d"), config.MODEL)
    logger.info("=" * 60)

    # --- Load RSS sources ---
    # rss_sources.json stores {"sources": [{"url": "...", "enabled": true, ...}]}
    # We extract only the URLs for enabled sources so fetch_rss_feeds() receives
    # a plain list of URL strings.
    rss_sources_path = Path("rss_sources.json")
    if rss_sources_path.exists():
        try:
            with open(rss_sources_path, "r", encoding="utf-8") as fh:
                rss_data = json.load(fh)
            rss_sources = [
                s["url"]
                for s in rss_data.get("sources", [])
                if s.get("enabled", True) and s.get("url")
            ]
            logger.info("Loaded %d enabled RSS sources from rss_sources.json.", len(rss_sources))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load rss_sources.json: %s — using defaults.", exc)
            rss_sources = config.DEFAULT_RSS_SOURCES
    else:
        logger.info("rss_sources.json not found — using default RSS sources from config.")
        rss_sources = config.DEFAULT_RSS_SOURCES

    # --- Load opinions ---
    opinions_path = Path("opinions.txt")
    opinions_text = ""
    if opinions_path.exists():
        try:
            with open(opinions_path, "r", encoding="utf-8") as fh:
                opinions_text = fh.read().strip()
            logger.info("Loaded opinions.txt (%d chars).", len(opinions_text))
        except OSError as exc:
            logger.warning("Failed to load opinions.txt: %s — proceeding without opinions.", exc)
    else:
        logger.warning("opinions.txt not found — proceeding without personal opinions.")

    # --- Load topic history ---
    topic_history = load_topic_history()

    # --- Fetch RSS feeds ---
    logger.info("Fetching RSS feeds...")
    articles = fetch_rss_feeds(rss_sources)

    if not articles:
        logger.error("No articles fetched from any RSS feed. Aborting.")
        return

    # --- Score articles ---
    logger.info("Scoring %d articles...", len(articles))
    scored_articles = []
    for article in articles:
        score = score_article(article, topic_history)
        scored_articles.append((score, article))

    scored_articles.sort(key=lambda x: x[0], reverse=True)

    logger.info("Top 5 articles by score:")
    for score, art in scored_articles[:5]:
        logger.info("  [%.1f] %s", score, art["title"])

    # --- Detect trends ---
    logger.info("Detecting trends...")
    trends = detect_trends(articles)

    # --- Determine content source ---
    # Prefer a strong article; fall back to trend if best score is weak
    best_score, best_article = scored_articles[0] if scored_articles else (0, None)
    use_trend = trends and (best_score < 3 or not best_article)

    logger.info(
        "Content strategy: %s (best article score: %.1f, trends detected: %d)",
        "TREND" if use_trend else "ARTICLE",
        best_score,
        len(trends),
    )

    # --- Generate post with retry loop ---
    max_attempts = 3
    final_post = ""
    final_qa_scores = {}
    content_label = ""

    for attempt in range(1, max_attempts + 1):
        logger.info("Generation attempt %d of %d...", attempt, max_attempts)

        if use_trend:
            primary_trend = trends[0]
            post_text = generate_post_for_trend(primary_trend, articles, opinions_text, config)
            content_label = f"Trend: {primary_trend}"
        else:
            post_text = generate_post_for_article(best_article, opinions_text, config)
            content_label = best_article.get("title", "Unknown article")

        if not post_text:
            logger.warning("Attempt %d: Empty post generated — retrying.", attempt)
            continue

        # Word count check
        word_count = len(post_text.split())
        logger.info("Attempt %d: Generated post has %d words.", attempt, word_count)

        if word_count < config.POST_MIN_WORDS:
            logger.warning(
                "Attempt %d: Post too short (%d words, minimum %d) — retrying.",
                attempt, word_count, config.POST_MIN_WORDS,
            )
            continue

        if word_count > config.POST_MAX_WORDS:
            logger.warning(
                "Attempt %d: Post too long (%d words, maximum %d) — retrying.",
                attempt, word_count, config.POST_MAX_WORDS,
            )
            continue

        # QA check
        logger.info("Attempt %d: Running QA check...", attempt)
        qa_scores = qa_check(post_text, config)

        if not qa_scores:
            logger.warning("Attempt %d: QA check returned no scores — retrying.", attempt)
            continue

        auth = qa_scores.get("authenticity", 0)
        read = qa_scores.get("readability", 0)
        suitability = qa_scores.get("linkedin_suitability", 0)

        if auth >= config.QA_MIN_SCORE and read >= config.QA_MIN_SCORE and suitability >= config.QA_MIN_SCORE:
            logger.info(
                "Attempt %d: QA passed — authenticity=%s, readability=%s, linkedin_suitability=%s.",
                attempt, auth, read, suitability,
            )
            final_post = post_text
            final_qa_scores = qa_scores
            break
        else:
            logger.warning(
                "Attempt %d: QA failed — authenticity=%s, readability=%s, linkedin_suitability=%s. "
                "Minimum required: %d. Feedback: %s",
                attempt, auth, read, suitability, config.QA_MIN_SCORE,
                qa_scores.get("feedback", "no feedback"),
            )

    if not final_post:
        logger.error(
            "All %d generation attempts failed QA. "
            "Using best available post if any, or aborting.",
            max_attempts,
        )
        # Last resort: use post_text from last attempt even if QA failed
        if post_text:
            logger.warning("Using last generated post despite QA failure.")
            final_post = post_text
            final_qa_scores = qa_scores if qa_scores else {}
        else:
            logger.error("No post text available. Aborting.")
            return

    # --- Generate hashtags ---
    logger.info("Generating hashtags...")
    search_text = (
        trends[0] if use_trend
        else (best_article.get("title", "") + " " + best_article.get("summary", ""))
    ).lower()
    matched_kws = [
        kw for kw in config.HIGH_PRIORITY_KEYWORDS + config.MEDIUM_PRIORITY_KEYWORDS
        if kw.lower() in search_text
    ]
    hashtags = generate_hashtags(matched_kws)
    final_post_with_tags = final_post.rstrip() + "\n\n" + hashtags

    # --- Fetch image ---
    logger.info("Fetching image...")
    image_query = f"{trends[0]} igaming" if use_trend else best_article.get("title", "igaming")
    image_url = fetch_image(image_query, config.PEXELS_API_KEY)

    # --- Archive post ---
    logger.info("Archiving post...")
    archive_post(final_post_with_tags, content_label)

    # --- Update topic history ---
    logger.info("Updating topic history...")
    if use_trend:
        new_topics = [trends[0]]
    else:
        # Extract matched keywords from the best article for history tracking
        text = (best_article.get("title", "") + " " + best_article.get("summary", "")).lower()
        new_topics = [
            kw for kw in config.HIGH_PRIORITY_TOPICS + config.MEDIUM_PRIORITY_TOPICS
            if kw.lower() in text
        ][:5]  # cap at 5 topics per run

    updated_history = update_topic_history(topic_history, new_topics)
    save_topic_history(updated_history)

    # --- Send email ---
    today_str = datetime.now().strftime("%Y-%m-%d")
    qa_summary = ""
    if final_qa_scores:
        qa_summary = (
            f" [QA: auth={final_qa_scores.get('authenticity', '?')}, "
            f"read={final_qa_scores.get('readability', '?')}, "
            f"suit={final_qa_scores.get('linkedin_suitability', '?')}]"
        )

    subject = f"LinkedIn Post Ready — {today_str}{qa_summary}"
    logger.info("Sending email with subject: '%s'", subject)

    email_sent = send_email(final_post_with_tags, subject, config, image_url=image_url)
    if not email_sent:
        logger.error("Email delivery failed. Post is archived at generated_posts/%s.txt", today_str)
    else:
        logger.info("Pipeline complete. Post delivered successfully.")

    logger.info("=" * 60)
    logger.info("LinkedIn Content Generator finished.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
