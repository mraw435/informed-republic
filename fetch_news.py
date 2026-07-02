#!/usr/bin/env python3
"""
fetch_news.py — Informed Republic news aggregator
--------------------------------------------------
Pulls RSS feeds by policy area, generates summaries via Anthropic API,
and pushes results to news.json in GitHub.

Schedule via cron (runs at 7am and 1pm daily):
  0 7 * * * ANTHROPIC_API_KEY=sk-ant-... GITHUB_TOKEN=ghp_... python3 /home/ecarndt/fetch_news.py

Requirements:
  pip3 install feedparser requests python-dateutil --break-system-packages
"""

import json
import os
import time
import hashlib
import base64
import urllib.request
from datetime import datetime, timezone, timedelta
from urllib.error import URLError

try:
    import feedparser
except ImportError:
    print("ERROR: feedparser not installed. Run: pip3 install feedparser --break-system-packages")
    exit(1)

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip3 install requests --break-system-packages")
    exit(1)

# ── Config ────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
GITHUB_TOKEN      = os.environ.get('GITHUB_TOKEN', '')
GITHUB_OWNER      = 'mraw435'
GITHUB_REPO       = 'informed-republic'
GITHUB_FILE       = 'news.json'
GITHUB_API        = f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_FILE}'

MAX_STORIES_PER_TOPIC = 6   # stories per policy area
MAX_AGE_HOURS         = 48  # only include stories from last 48 hours

# ── RSS feeds by topic ────────────────────────────────────────────────
# All feeds are public RSS — no scraping, no ToS issues
TOPICS = {
    "Defense": [
        "https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=945&max=10",
        "https://feeds.feedburner.com/defense-news-rss2-0",
        "https://thehill.com/policy/defense/feed/",
        "https://rss.politico.com/defense.xml",
    ],
    "Healthcare": [
        "https://thehill.com/policy/healthcare/feed/",
        "https://rss.politico.com/healthcare.xml",
        "https://www.commonwealthfund.org/rss.xml",
        "https://kffhealthnews.org/feed/",
    ],
    "Appropriations": [
        "https://thehill.com/policy/finance/feed/",
        "https://rss.politico.com/economy.xml",
        "https://www.rollcall.com/tag/appropriations/feed/",
        "https://federalnewsnetwork.com/category/budget-oversight/feed/",
    ],
    "Foreign Policy": [
        "https://thehill.com/policy/international/feed/",
        "https://rss.politico.com/foreign-policy.xml",
        "https://foreignpolicy.com/feed/",
        "https://www.reuters.com/rssFeed/worldNews",
    ],
    "Energy": [
        "https://thehill.com/policy/energy-environment/feed/",
        "https://rss.politico.com/energy.xml",
        "https://www.eenews.net/rss/",
        "https://energynews.us/feed/",
    ],
    "Education": [
        "https://thehill.com/policy/education/feed/",
        "https://rss.politico.com/education.xml",
        "https://www.edweek.org/feed/",
        "https://hechingerreport.org/feed/",
    ],
    "Criminal Justice": [
        "https://thehill.com/policy/criminal-justice/feed/",
        "https://thecrimereport.org/feed/",
        "https://www.marshallproject.org/feeds/everything",
        "https://rss.politico.com/politico-now.xml",
    ],
    "Immigration": [
        "https://thehill.com/policy/immigration/feed/",
        "https://rss.politico.com/immigration.xml",
        "https://immigrationimpact.com/feed/",
        "https://www.reuters.com/rssFeed/domesticNews",
    ],
    "Tax & Finance": [
        "https://thehill.com/policy/finance/feed/",
        "https://rss.politico.com/economy.xml",
        "https://taxfoundation.org/feed/",
        "https://www.taxpolicycenter.org/feed",
    ],
    "Elections": [
        "https://thehill.com/homenews/campaign/feed/",
        "https://rss.politico.com/congress.xml",
        "https://fivethirtyeight.com/features/feed/",
        "https://ballotpedia.org/wiki/index.php?title=Special:RecentChanges&feed=rss",
    ],
    "Transportation": [
        "https://thehill.com/policy/transportation/feed/",
        "https://rss.politico.com/transportation.xml",
        "https://www.ttnews.com/rss/news",
        "https://federalnewsnetwork.com/category/transportation/feed/",
    ],
    "Agriculture": [
        "https://thehill.com/policy/agriculture/feed/",
        "https://www.agriculture.com/rss",
        "https://www.agri-pulse.com/rss",
        "https://www.farmpolicy.com/feed/",
    ],
    "Cybersecurity": [
        "https://www.cisa.gov/feeds/alerts.xml",
        "https://thehill.com/policy/cybersecurity/feed/",
        "https://rss.politico.com/cybersecurity.xml",
        "https://www.cyberscoop.com/feed/",
        "https://krebsonsecurity.com/feed/",
    ],
    "Technology": [
        "https://thehill.com/policy/technology/feed/",
        "https://rss.politico.com/technology.xml",
        "https://www.theverge.com/rss/index.xml",
        "https://arstechnica.com/gadgets/feed/",
    ],
}

# Known paywalled domains
PAYWALLED_DOMAINS = {
    'wsj.com', 'nytimes.com', 'washingtonpost.com', 'ft.com',
    'bloomberg.com', 'economist.com', 'theathletic.com', 'axios.com',
    'businessinsider.com', 'newyorker.com', 'wired.com', 'thetimes.co.uk',
}

def is_paywalled(url):
    for domain in PAYWALLED_DOMAINS:
        if domain in url:
            return True
    return False

def get_domain(url):
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.replace('www.', '')
        return domain
    except:
        return url

def is_recent(entry):
    try:
        from dateutil import parser as dateparser
        if hasattr(entry, 'published'):
            pub = dateparser.parse(entry.published)
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - pub
            return age < timedelta(hours=MAX_AGE_HOURS)
    except:
        pass
    return True  # include if we can't parse date

def fetch_stories_for_topic(topic, feeds):
    stories = []
    seen_titles = set()

    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:8]:
                title = getattr(entry, 'title', '').strip()
                url = getattr(entry, 'link', '').strip()
                if not title or not url:
                    continue
                # Deduplicate by title hash
                title_hash = hashlib.md5(title.lower().encode()).hexdigest()
                if title_hash in seen_titles:
                    continue
                if not is_recent(entry):
                    continue
                seen_titles.add(title_hash)
                stories.append({
                    'title': title,
                    'url': url,
                    'source': get_domain(url),
                    'paywalled': is_paywalled(url),
                    'topic': topic,
                })
        except Exception as e:
            print(f"  Feed error ({feed_url[:50]}...): {e}")
            continue

    return stories[:MAX_STORIES_PER_TOPIC * 2]  # fetch extra, trim after BLUF

def generate_summary(stories_batch):
    """Generate summaries for a batch of stories via Anthropic API."""
    if not ANTHROPIC_API_KEY:
        # Return placeholder if no API key
        return {s['url']: 'Summary unavailable.' for s in stories_batch}

    story_list = '\n'.join([
        f"{i+1}. TITLE: {s['title']}\n   URL: {s['url']}"
        for i, s in enumerate(stories_batch)
    ])

    prompt = f"""For each news story below, write a single sentence "Summary" summary.
The BLUF should tell the reader the most important fact — what happened, who was involved, and why it matters for federal policy or government.
Be specific. Be nonpartisan. Do not editorialize. Keep each summary under 30 words.

Return ONLY a JSON object mapping each URL to its BLUF string. No other text.

Stories:
{story_list}"""

    try:
        response = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'x-api-key': ANTHROPIC_API_KEY,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            },
            json={
                'model': 'claude-haiku-4-5-20251001',  # use Haiku — cheap, fast, good for summaries
                'max_tokens': 1000,
                'messages': [{'role': 'user', 'content': prompt}]
            },
            timeout=30
        )
        data = response.json()
        text = data['content'][0]['text'].strip()
        # Strip markdown fences if present
        text = text.replace('```json', '').replace('```', '').strip()
        return json.loads(text)
    except Exception as e:
        print(f"  BLUF generation error: {e}")
        return {s['url']: '' for s in stories_batch}

def push_to_github(news_data):
    """Push news.json to GitHub."""
    if not GITHUB_TOKEN:
        print("No GitHub token — saving locally to news.json only")
        with open('news.json', 'w') as f:
            json.dump(news_data, f, indent=2)
        return

    content = base64.b64encode(
        json.dumps(news_data, indent=2).encode('utf-8')
    ).decode('utf-8')

    # Get current SHA
    headers = {
        'Authorization': f'Bearer {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }

    sha = None
    try:
        res = requests.get(GITHUB_API, headers=headers, timeout=15)
        if res.ok:
            sha = res.json().get('sha')
    except Exception as e:
        print(f"Could not fetch current SHA: {e}")

    payload = {
        'message': f'News update: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}',
        'content': content,
    }
    if sha:
        payload['sha'] = sha

    try:
        res = requests.put(GITHUB_API, headers=headers, json=payload, timeout=30)
        if res.ok:
            print(f"✓ Pushed news.json to GitHub")
        else:
            print(f"✗ GitHub push failed: {res.status_code} {res.text[:200]}")
    except Exception as e:
        print(f"✗ GitHub push error: {e}")

def main():
    print(f"Informed Republic — News Fetch")
    print(f"Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Topics: {len(TOPICS)}")
    print()

    all_stories = []

    for topic, feeds in TOPICS.items():
        print(f"Fetching: {topic}...")
        stories = fetch_stories_for_topic(topic, feeds)
        print(f"  Found {len(stories)} stories, generating summaries...")

        # Generate summaries in batches
        summary_map = generate_summary(stories)
        time.sleep(0.5)  # brief pause between API calls

        # Attach BLUFs and trim to MAX_STORIES_PER_TOPIC
        for s in stories:
            s['summary'] = summary_map.get(s['url'], '')

        # Prefer stories with summaries and trim
        stories_with_summary = [s for s in stories if s['summary']]
        stories_without = [s for s in stories if not s['summary']]
        final = (stories_with_summary + stories_without)[:MAX_STORIES_PER_TOPIC]
        all_stories.extend(final)
        print(f"  Kept {len(final)} stories for {topic}")

    news_data = {
        'last_updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'story_count': len(all_stories),
        'stories': all_stories
    }

    print(f"\nTotal stories: {len(all_stories)}")
    print("Pushing to GitHub...")
    push_to_github(news_data)
    print("\nDone!")

if __name__ == '__main__':
    main()
