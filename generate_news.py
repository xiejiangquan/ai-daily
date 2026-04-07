"""
AI Daily News Generator
每天定时抓取 AI 新闻 + X 上的 AI 趋势，调用 AI 生成中文摘要，输出 JSON 文件。
用于 GitHub Actions 定时运行 + GitHub Pages 托管。
"""

import os
import json
import re
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

# ============================================================
# 配置
# ============================================================
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
# 如果你更喜欢用 Anthropic Claude，把下面的 key 填上，脚本会自动切换
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

OUTPUT_DIR = Path("docs")
OUTPUT_FILE = OUTPUT_DIR / "news.json"
# 保留最近 N 天的历史数据
MAX_HISTORY_DAYS = 30

# ============================================================
# 1. 数据抓取 — NewsAPI
# ============================================================

def fetch_newsapi(query="artificial intelligence OR AI", page_size=20):
    """通过 NewsAPI 抓取最新 AI 新闻（免费版每天 100 次请求）"""
    if not NEWSAPI_KEY:
        print("[WARN] NEWSAPI_KEY not set, skipping NewsAPI")
        return []

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": page_size,
        "apiKey": NEWSAPI_KEY,
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
        return [
            {
                "title": a.get("title", ""),
                "description": a.get("description", ""),
                "url": a.get("url", ""),
                "source": a.get("source", {}).get("name", ""),
                "published": a.get("publishedAt", ""),
            }
            for a in articles
            if a.get("title") and "[Removed]" not in a.get("title", "")
        ]
    except Exception as e:
        print(f"[ERROR] NewsAPI fetch failed: {e}")
        return []


# ============================================================
# 2. 数据抓取 — RSS Feeds（免费，无需 API Key）
# ============================================================

def fetch_rss_feed(feed_url, source_name):
    """解析 RSS feed，提取标题和描述"""
    try:
        resp = requests.get(feed_url, timeout=30, headers={
            "User-Agent": "AI-Daily-News-Bot/1.0"
        })
        resp.raise_for_status()
        content = resp.text

        items = []
        # 简易 XML 解析（避免额外依赖 feedparser）
        item_blocks = re.findall(r"<item>(.*?)</item>", content, re.DOTALL)
        for block in item_blocks[:10]:
            title_match = re.search(r"<title><!\[CDATA\[(.*?)\]\]>|<title>(.*?)</title>", block)
            desc_match = re.search(r"<description><!\[CDATA\[(.*?)\]\]>|<description>(.*?)</description>", block, re.DOTALL)
            link_match = re.search(r"<link>(.*?)</link>", block)
            pub_match = re.search(r"<pubDate>(.*?)</pubDate>", block)

            title = ""
            if title_match:
                title = title_match.group(1) or title_match.group(2) or ""
            desc = ""
            if desc_match:
                desc = desc_match.group(1) or desc_match.group(2) or ""
            # 去掉 HTML 标签
            desc = re.sub(r"<[^>]+>", "", desc).strip()

            if title:
                items.append({
                    "title": title.strip(),
                    "description": desc[:500],
                    "url": (link_match.group(1).strip() if link_match else ""),
                    "source": source_name,
                    "published": (pub_match.group(1).strip() if pub_match else ""),
                })
        return items
    except Exception as e:
        print(f"[ERROR] RSS fetch failed ({source_name}): {e}")
        return []


def fetch_all_rss():
    """从多个 AI 相关 RSS 源抓取新闻"""
    feeds = [
        ("https://techcrunch.com/category/artificial-intelligence/feed/", "TechCrunch AI"),
        ("https://www.artificialintelligence-news.com/feed/", "AI News"),
        ("https://feeds.feedburner.com/TheHackersNews", "The Hacker News"),
        ("https://blog.google/technology/ai/rss/", "Google AI Blog"),
    ]
    all_items = []
    for url, name in feeds:
        items = fetch_rss_feed(url, name)
        all_items.extend(items)
        print(f"  [RSS] {name}: {len(items)} articles")
    return all_items


# ============================================================
# 3. 数据抓取 — X/Twitter AI 趋势（通过 Nitter 或公开搜索）
# ============================================================

def fetch_x_trends():
    """
    抓取 X 上的 AI 趋势话题。
    免费方案：通过搜索引擎间接获取 X 上的热门 AI 讨论。
    如果你有 X API Bearer Token，可以替换为直接调用 X API v2。
    """
    x_bearer = os.environ.get("X_BEARER_TOKEN", "")
    if x_bearer:
        return _fetch_x_api(x_bearer)

    # 无 X API 时，使用搜索引擎间接获取
    print("  [X] No X_BEARER_TOKEN set, using search fallback")
    return _fetch_x_via_search()


def _fetch_x_api(bearer_token):
    """通过 X API v2 搜索最近的 AI 热门推文"""
    url = "https://api.twitter.com/2/tweets/search/recent"
    headers = {"Authorization": f"Bearer {bearer_token}"}
    params = {
        "query": "(AI OR artificial intelligence OR LLM OR GPT) lang:en -is:retweet",
        "max_results": 20,
        "sort_order": "relevancy",
        "tweet.fields": "created_at,public_metrics,author_id,text",
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        tweets = resp.json().get("data", [])
        return [
            {
                "text": t.get("text", ""),
                "created_at": t.get("created_at", ""),
                "metrics": t.get("public_metrics", {}),
            }
            for t in tweets
        ]
    except Exception as e:
        print(f"[ERROR] X API fetch failed: {e}")
        return []


def _fetch_x_via_search():
    """通过 NewsAPI 搜索 X/Twitter 上的 AI 讨论作为替代"""
    if not NEWSAPI_KEY:
        return []
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": "AI trending twitter OR AI trending X platform",
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 10,
        "apiKey": NEWSAPI_KEY,
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return [
            {"text": a.get("title", "") + ": " + (a.get("description") or ""), "source_url": a.get("url", "")}
            for a in resp.json().get("articles", [])
            if a.get("title") and "[Removed]" not in a.get("title", "")
        ]
    except Exception as e:
        print(f"[ERROR] X search fallback failed: {e}")
        return []


# ============================================================
# 4. AI 摘要生成
# ============================================================

def generate_summary_openai(news_items, x_trends):
    """调用 OpenAI API 生成每日 AI 新闻中文摘要"""
    news_text = "\n".join(
        f"- [{item['source']}] {item['title']}: {item.get('description', '')}"
        for item in news_items[:25]
    )
    x_text = "\n".join(
        f"- {item.get('text', '')}"
        for item in x_trends[:15]
    )

    prompt = f"""你是一个专业的 AI 行业分析师。请根据以下今日 AI 相关新闻和 X(Twitter) 上的讨论，生成一份简洁的中文每日 AI 简报。

## 今日新闻
{news_text}

## X 上的 AI 讨论
{x_text}

请输出以下 JSON 格式（不要包含 markdown 代码块标记）：
{{
  "headline": "一句话总结今天最重要的 AI 事件",
  "sections": [
    {{
      "title": "分类标题（如：模型发布、产业动态、政策监管、X热议等）",
      "items": [
        {{
          "title": "新闻标题",
          "summary": "2-3句中文摘要",
          "source": "来源",
          "url": "原文链接（如有）",
          "tags": ["标签1", "标签2"]
        }}
      ]
    }}
  ],
  "x_highlights": [
    {{
      "topic": "X 上的热门话题",
      "summary": "简要描述讨论内容和观点"
    }}
  ]
}}

要求：
1. 全部用中文输出
2. 筛选最重要的 5-8 条新闻，不要堆砌
3. X 热议挑 2-3 个最有价值的话题
4. 摘要要有信息量，不要泛泛而谈
"""

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 3000,
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        # 去掉可能的 markdown 代码块标记
        content = re.sub(r"^```json\s*", "", content.strip())
        content = re.sub(r"\s*```$", "", content.strip())
        return json.loads(content)
    except Exception as e:
        print(f"[ERROR] OpenAI API failed: {e}")
        return None


def generate_summary_anthropic(news_items, x_trends):
    """调用 Anthropic Claude API 生成每日 AI 新闻中文摘要"""
    news_text = "\n".join(
        f"- [{item['source']}] {item['title']}: {item.get('description', '')}"
        for item in news_items[:25]
    )
    x_text = "\n".join(
        f"- {item.get('text', '')}"
        for item in x_trends[:15]
    )

    prompt = f"""你是一个专业的 AI 行业分析师。请根据以下今日 AI 相关新闻和 X(Twitter) 上的讨论，生成一份简洁的中文每日 AI 简报。

## 今日新闻
{news_text}

## X 上的 AI 讨论
{x_text}

请输出以下 JSON 格式（不要包含 markdown 代码块标记）：
{{
  "headline": "一句话总结今天最重要的 AI 事件",
  "sections": [
    {{
      "title": "分类标题（如：模型发布、产业动态、政策监管、X热议等）",
      "items": [
        {{
          "title": "新闻标题",
          "summary": "2-3句中文摘要",
          "source": "来源",
          "url": "原文链接（如有）",
          "tags": ["标签1", "标签2"]
        }}
      ]
    }}
  ],
  "x_highlights": [
    {{
      "topic": "X 上的热门话题",
      "summary": "简要描述讨论内容和观点"
    }}
  ]
}}

要求：
1. 全部用中文输出
2. 筛选最重要的 5-8 条新闻，不要堆砌
3. X 热议挑 2-3 个最有价值的话题
4. 摘要要有信息量，不要泛泛而谈
"""

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 3000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["content"][0]["text"]
        content = re.sub(r"^```json\s*", "", content.strip())
        content = re.sub(r"\s*```$", "", content.strip())
        return json.loads(content)
    except Exception as e:
        print(f"[ERROR] Anthropic API failed: {e}")
        return None


def generate_summary(news_items, x_trends):
    """自动选择可用的 AI API 生成摘要"""
    if ANTHROPIC_API_KEY:
        print("[AI] Using Anthropic Claude...")
        result = generate_summary_anthropic(news_items, x_trends)
        if result:
            return result

    if OPENAI_API_KEY:
        print("[AI] Using OpenAI...")
        result = generate_summary_openai(news_items, x_trends)
        if result:
            return result

    print("[WARN] No AI API available, generating basic summary")
    return _fallback_summary(news_items, x_trends)


def _fallback_summary(news_items, x_trends):
    """无 AI API 时的降级方案：直接整理原始数据"""
    items = []
    for n in news_items[:8]:
        items.append({
            "title": n["title"],
            "summary": n.get("description", "")[:200],
            "source": n.get("source", ""),
            "url": n.get("url", ""),
            "tags": ["AI"],
        })
    return {
        "headline": f"今日 AI 新闻速览（{len(news_items)} 条）",
        "sections": [{"title": "今日要闻", "items": items}],
        "x_highlights": [
            {"topic": t.get("text", "")[:100], "summary": ""}
            for t in x_trends[:3]
        ],
    }


# ============================================================
# 5. 输出与历史管理
# ============================================================

def generate_id(title):
    """根据标题生成唯一 ID"""
    return hashlib.md5(title.encode()).hexdigest()[:8]


def load_history():
    """加载历史数据"""
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"days": []}
    return {"days": []}


def save_output(summary):
    """保存今日摘要到 JSON 文件，保留历史"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone(timedelta(hours=8)))  # 北京时间
    today_str = now.strftime("%Y-%m-%d")

    today_entry = {
        "id": generate_id(today_str + summary.get("headline", "")),
        "date": today_str,
        "generated_at": now.isoformat(),
        "headline": summary.get("headline", ""),
        "sections": summary.get("sections", []),
        "x_highlights": summary.get("x_highlights", []),
    }

    # 加载历史并去重（同一天只保留最新的）
    history = load_history()
    history["days"] = [d for d in history["days"] if d.get("date") != today_str]
    history["days"].insert(0, today_entry)

    # 只保留最近 N 天
    cutoff = (now - timedelta(days=MAX_HISTORY_DAYS)).strftime("%Y-%m-%d")
    history["days"] = [d for d in history["days"] if d.get("date", "") >= cutoff]

    # 元信息
    history["last_updated"] = now.isoformat()
    history["total_days"] = len(history["days"])

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f"[OK] Saved to {OUTPUT_FILE} ({len(history['days'])} days of history)")

    # 同时生成一个 index.html 用于 GitHub Pages
    _generate_index_html(OUTPUT_DIR)


def _generate_index_html(output_dir):
    """生成一个简单的 index.html，方便浏览器直接查看"""
    html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>AI Daily</title></head>
<body>
<h1>AI Daily News API</h1>
<p>JSON endpoint: <a href="news.json">news.json</a></p>
</body></html>"""
    with open(output_dir / "index.html", "w", encoding="utf-8") as f:
        f.write(html)


# ============================================================
# Main
# ============================================================

def main():
    print("=" * 50)
    print(f"AI Daily News Generator")
    print(f"Time: {datetime.now(timezone(timedelta(hours=8))).isoformat()}")
    print("=" * 50)

    # 1. 抓取新闻
    print("\n[1/4] Fetching news from NewsAPI...")
    newsapi_items = fetch_newsapi()
    print(f"  Got {len(newsapi_items)} articles from NewsAPI")

    print("\n[2/4] Fetching news from RSS feeds...")
    rss_items = fetch_all_rss()
    print(f"  Got {len(rss_items)} articles from RSS")

    all_news = newsapi_items + rss_items

    # 去重（按标题）
    seen = set()
    unique_news = []
    for item in all_news:
        key = item["title"].lower().strip()
        if key not in seen:
            seen.add(key)
            unique_news.append(item)
    print(f"  Total unique articles: {len(unique_news)}")

    # 2. 抓取 X 趋势
    print("\n[3/4] Fetching X/Twitter AI trends...")
    x_trends = fetch_x_trends()
    print(f"  Got {len(x_trends)} X items")

    # 3. 生成 AI 摘要
    print("\n[4/4] Generating AI summary...")
    if not unique_news and not x_trends:
        print("[WARN] No data fetched, skipping generation")
        return

    summary = generate_summary(unique_news, x_trends)
    if not summary:
        print("[ERROR] Failed to generate summary")
        return

    # 4. 保存
    save_output(summary)
    print("\nDone!")


if __name__ == "__main__":
    main()
