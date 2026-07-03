#!/usr/bin/env python3
"""
fetch_news.py — Informed Republic news aggregator
--------------------------------------------------
Pulls RSS feeds by policy area, generates one-sentence summaries via
Anthropic API (Claude Haiku), and pushes results to news.json in GitHub.

Story retention strategy:
  - Pulls fresh stories from today (up to NEW_STORIES_PER_TOPIC)
  - Keeps older stories from the previous run (up to KEEP_OLD_STORIES)
  - Total per topic capped at MAX_STORIES_PER_TOPIC
  - This ensures each topic always has content even on slow news days

Schedule via cron (runs at 7am daily):
  0 7 * * * ANTHROPIC_API_KEY=sk-ant-... GITHUB_TOKEN=ghp_... python3 /var/www/informedrepublic.ecarndt.tech/fetch_news.py >> /home/ecarndt/news_fetch.log 2>&1

Requirements:
  pip3 install feedparser requests python-dateutil
"""

import json, os, time, hashlib, base64
from datetime import datetime, timezone, timedelta

try:
    import feedparser
except ImportError:
    print("ERROR: Run: pip3 install feedparser"); exit(1)
try:
    import requests
except ImportError:
    print("ERROR: Run: pip3 install requests"); exit(1)

# ── Config ────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY     = os.environ.get('ANTHROPIC_API_KEY', '')
GITHUB_TOKEN          = os.environ.get('GITHUB_TOKEN', '')
GITHUB_OWNER          = 'mraw435'
GITHUB_REPO           = 'informed-republic'
GITHUB_FILE           = 'news.json'
GITHUB_API            = f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_FILE}'

NEW_STORIES_PER_TOPIC  = 3   # fresh stories pulled today
KEEP_OLD_STORIES       = 3   # older stories kept from previous run
MAX_STORIES_PER_TOPIC  = 6   # total cap per topic
MAX_AGE_HOURS          = 48  # don't show stories older than 48 hours

# ── RSS feeds by topic ────────────────────────────────────────────────
# Multiple feeds per topic with source diversity as priority
# All are public RSS feeds — no scraping, no ToS issues
TOPICS = {
    "Defense": [
        "https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=945&max=10",
        "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml",
        "https://defenseone.com/rss/all/",
        "https://thehill.com/policy/defense/feed/",
        "https://rss.politico.com/defense.xml",
        "https://federalnewsnetwork.com/category/defense/feed/",
        "https://www.militarytimes.com/arc/outboundfeeds/rss/?outputType=xml",
    ],
    "Healthcare": [
        "https://thehill.com/policy/healthcare/feed/",
        "https://rss.politico.com/healthcare.xml",
        "https://kffhealthnews.org/feed/",
        "https://www.modernhealthcare.com/section/news/rss",
        "https://federalnewsnetwork.com/category/federal-benefits-pay/feed/",
    ],
    "Appropriations": [
        "https://thehill.com/policy/finance/feed/",
        "https://rss.politico.com/economy.xml",
        "https://www.rollcall.com/tag/appropriations/feed/",
        "https://federalnewsnetwork.com/category/budget-oversight/feed/",
        "https://www.govexec.com/rss/all/",
    ],
    "Foreign Policy": [
        "https://thehill.com/policy/international/feed/",
        "https://rss.politico.com/foreign-policy.xml",
        "https://foreignpolicy.com/feed/",
        "https://www.reuters.com/rssFeed/worldNews",
        "https://feeds.npr.org/1004/rss.xml",
    ],
    "Energy": [
        "https://thehill.com/policy/energy-environment/feed/",
        "https://rss.politico.com/energy.xml",
        "https://energynews.us/feed/",
        "https://www.eenews.net/rss/",
        "https://www.utilitydive.com/feeds/news/",
    ],
    "Education": [
        "https://thehill.com/policy/education/feed/",
        "https://rss.politico.com/education.xml",
        "https://www.edweek.org/feed/",
        "https://nces.ed.gov/whatsnew/nces_rss.asp",
        "https://hechingerreport.org/feed/",
        "https://federalnewsnetwork.com/category/education/feed/",
    ],
    "Criminal Justice": [
        "https://thehill.com/policy/criminal-justice/feed/",
        "https://www.themarshallproject.org/feeds/everything",
        "https://nij.ojp.gov/rss.xml",
        "https://thecrimereport.org/feed/",
        "https://www.reuters.com/rssFeed/domesticNews",
        "https://feeds.npr.org/1019/rss.xml",
    ],
    "Immigration": [
        "https://thehill.com/policy/immigration/feed/",
        "https://rss.politico.com/immigration.xml",
        "https://immigrationimpact.com/feed/",
        "https://www.reuters.com/rssFeed/domesticNews",
        "https://feeds.npr.org/1014/rss.xml",
    ],
    "Tax & Finance": [
        "https://thehill.com/policy/finance/feed/",
        "https://rss.politico.com/economy.xml",
        "https://taxfoundation.org/feed/",
        "https://www.taxpolicycenter.org/feed",
        "https://www.govexec.com/rss/all/",
    ],
    "Elections": [
        "https://thehill.com/homenews/campaign/feed/",
        "https://rss.politico.com/congress.xml",
        "https://fivethirtyeight.com/features/feed/",
        "https://feeds.npr.org/1012/rss.xml",
        "https://www.rollcall.com/feed/",
    ],
    "Transportation": [
        "https://thehill.com/policy/transportation/feed/",
        "https://rss.politico.com/transportation.xml",
        "https://www.ttnews.com/rss/news",
        "https://federalnewsnetwork.com/category/transportation/feed/",
        "https://www.aviationpros.com/rss/all-articles",
    ],
    "Agriculture": [
        "https://thehill.com/policy/agriculture/feed/",
        "https://www.agri-pulse.com/rss",
        "https://www.farmpolicynews.illinois.edu/feed/",
        "https://www.agriculture.com/rss",
        "https://www.dtnpf.com/agriculture/web/ag/news/rss",
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
        "https://arstechnica.com/gadgets/feed/",
        "https://feeds.npr.org/1019/rss.xml",
        "https://www.govtech.com/rss",
    ],
}

PAYWALLED_DOMAINS = {
    'wsj.com','nytimes.com','washingtonpost.com','ft.com',
    'bloomberg.com','economist.com','theathletic.com',
    'businessinsider.com','newyorker.com','wired.com',
}

def is_paywalled(url):
    return any(d in url for d in PAYWALLED_DOMAINS)

def get_domain(url):
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.replace('www.','')
    except:
        return url

def get_pub_date(entry):
    try:
        from dateutil import parser as dp
        raw = getattr(entry, 'published', None) or getattr(entry, 'updated', None)
        if raw:
            dt = dp.parse(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
    except:
        pass
    return None

def is_recent(entry, hours=MAX_AGE_HOURS):
    dt = get_pub_date(entry)
    if dt is None:
        return True
    return datetime.now(timezone.utc) - dt < timedelta(hours=hours)

def is_today(entry):
    dt = get_pub_date(entry)
    if dt is None:
        return False
    return datetime.now(timezone.utc) - dt < timedelta(hours=24)

def fetch_fresh_stories(topic, feeds):
    """Pull today's stories from feeds, deduplicated, one per source."""
    stories = []
    seen_titles = set()
    seen_sources = {}  # source -> count

    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            source = get_domain(feed_url)
            source_count = seen_sources.get(source, 0)

            for entry in feed.entries[:10]:
                title = getattr(entry, 'title', '').strip()
                url = getattr(entry, 'link', '').strip()
                if not title or not url:
                    continue
                title_hash = hashlib.md5(title.lower().encode()).hexdigest()
                if title_hash in seen_titles:
                    continue
                if not is_recent(entry):
                    continue
                # Limit stories per source to 2 to ensure diversity
                if source_count >= 2:
                    continue
                seen_titles.add(title_hash)
                seen_sources[source] = source_count + 1
                pub_dt = get_pub_date(entry)
                stories.append({
                    'title': title,
                    'url': url,
                    'source': source,
                    'paywalled': is_paywalled(url),
                    'topic': topic,
                    'published': pub_dt.isoformat() if pub_dt else '',
                    'is_today': is_today(entry),
                })
        except Exception as e:
            print(f"  Feed error ({feed_url[:50]}): {e}")
            continue

    # Sort: today's stories first, then by recency
    stories.sort(key=lambda s: (0 if s['is_today'] else 1, s['published']), reverse=False)
    stories.sort(key=lambda s: s['is_today'], reverse=True)
    return stories

def generate_summary(stories_batch):
    """Generate one-sentence summaries via Anthropic API (Claude Haiku)."""
    if not stories_batch:
        return {}
    if not ANTHROPIC_API_KEY:
        return {s['url']: '' for s in stories_batch}

    story_list = '\n'.join([
        f"{i+1}. TITLE: {s['title']}\n   URL: {s['url']}"
        for i, s in enumerate(stories_batch)
    ])

    prompt = f"""For each news story below, write a single sentence summary.
The summary should state the key fact — what happened, who was involved, and why it matters for federal policy.
Be specific. Be nonpartisan. Do not editorialize. Keep each summary under 30 words.

Return ONLY a valid JSON object mapping each URL to its summary string. No other text, no markdown.

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
                'model': 'claude-haiku-4-5-20251001',
                'max_tokens': 1024,
                'messages': [{'role': 'user', 'content': prompt}]
            },
            timeout=30
        )
        data = response.json()
        text = data['content'][0]['text'].strip()
        text = text.replace('```json','').replace('```','').strip()
        return json.loads(text)
    except Exception as e:
        print(f"  Summary generation error: {e}")
        return {s['url']: '' for s in stories_batch}

def fetch_existing_news():
    """Fetch current news.json from GitHub to retain older stories."""
    headers = {
        'Authorization': f'Bearer {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    try:
        res = requests.get(GITHUB_API, headers=headers, timeout=15)
        if res.ok:
            raw = base64.b64decode(res.json()['content'].replace('\n','')).decode('utf-8')
            data = json.loads(raw)
            return data.get('stories', []), res.json().get('sha')
    except Exception as e:
        print(f"  Could not fetch existing news: {e}")
    return [], None

def push_to_github(news_data, sha):
    if not GITHUB_TOKEN:
        with open('news.json', 'w') as f:
            json.dump(news_data, f, indent=2)
        print("No GitHub token — saved locally to news.json")
        return

    content = base64.b64encode(
        json.dumps(news_data, indent=2).encode('utf-8')
    ).decode('utf-8')

    headers = {
        'Authorization': f'Bearer {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }
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

    # Fetch existing stories to retain older ones
    print("Fetching existing stories from GitHub...")
    existing_stories, github_sha = fetch_existing_news()
    existing_by_topic = {}
    for s in existing_stories:
        t = s.get('topic','')
        if t not in existing_by_topic:
            existing_by_topic[t] = []
        existing_by_topic[t].append(s)

    all_stories = []

    for topic, feeds in TOPICS.items():
        print(f"Fetching: {topic}...")
        fresh = fetch_fresh_stories(topic, feeds)
        print(f"  Found {len(fresh)} fresh stories, generating summaries...")

        # Generate summaries for fresh stories
        summary_map = generate_summary(fresh[:NEW_STORIES_PER_TOPIC * 2])
        time.sleep(0.3)

        for s in fresh:
            s['summary'] = summary_map.get(s['url'], '')

        # Take top fresh stories
        new_stories = fresh[:NEW_STORIES_PER_TOPIC]

        # Get older stories from previous run, excluding duplicates
        new_urls = {s['url'] for s in new_stories}
        old_stories = [
            s for s in existing_by_topic.get(topic, [])
            if s.get('url') not in new_urls
            and s.get('published', '') >= (
                datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
            ).isoformat()
        ][:KEEP_OLD_STORIES]

        combined = (new_stories + old_stories)[:MAX_STORIES_PER_TOPIC]
        all_stories.extend(combined)
        print(f"  {len(new_stories)} new + {len(old_stories)} retained = {len(combined)} total for {topic}")

    news_data = {
        'last_updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'story_count': len(all_stories),
        'stories': all_stories
    }

    print(f"\nTotal stories: {len(all_stories)}")
    print("Pushing to GitHub...")
    push_to_github(news_data, github_sha)
    print("\nDone!")

if __name__ == '__main__':
    main()
