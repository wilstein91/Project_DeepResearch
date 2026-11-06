"""국내 증시·경제 RSS를 지금 시점 그대로 저장한다 (스냅샷).

RSS는 최근 하루이틀치만 보여 주고 지난 기사는 사라지므로, 모아 두려면 그날그날 실행해야 한다.
저장 위치: data/news/raw/<날짜_시각>.json  (기사 제목·요약·링크·발행 시각·매체)
⚠️ 기사 저작권 때문에 data/news/ 는 깃에 올리지 않는다(.gitignore). 저장소에는 이 스크립트만 올린다.

실행:  .venv\\Scripts\\python.exe news_snapshot.py
"""
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

FEEDS = {  # Project_Newsletter 에서 실측해 채택했던 국내 증시·경제 피드
    "연합뉴스 마켓": "https://www.yna.co.kr/rss/market.xml",
    "연합뉴스 경제": "https://www.yna.co.kr/rss/economy.xml",
    "한국경제 증권": "https://www.hankyung.com/feed/finance",
    "매일경제 증권": "https://www.mk.co.kr/rss/50200011/",
    "동아일보 경제": "https://rss.donga.com/economy.xml",
    "뉴시스 경제": "https://newsis.com/RSS/economy.xml",
}
HEADERS = {"User-Agent": "Mozilla/5.0 AiffelDeepResearch/0.1"}
OUT_DIR = Path("data/news/raw")


def clean(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def main():
    items = {}
    for source, url in FEEDS.items():
        try:
            root = ET.fromstring(requests.get(url, headers=HEADERS, timeout=20).content)
        except Exception as e:  # 피드 하나가 죽어도 나머지는 저장
            print(f"  ! {source} 실패: {e}")
            continue
        n = 0
        for it in root.findall(".//item"):
            link = (it.findtext("link") or "").strip()
            if not link or link in items:
                continue
            try:
                published = parsedate_to_datetime(it.findtext("pubDate")).isoformat()
            except Exception:
                published = ""
            items[link] = {
                "source": source,
                "title": clean(it.findtext("title")),
                "summary": clean(it.findtext("description")),
                "published": published,
                "link": link,
            }
            n += 1
        print(f"  {source}: {n}건")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{datetime.now():%Y-%m-%d_%H%M}.json"
    out.write_text(json.dumps(list(items.values()), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장: {out} (총 {len(items)}건)")


if __name__ == "__main__":
    main()
