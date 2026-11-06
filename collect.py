"""딥리서처용 코퍼스(data/corpus.json)를 만든다 — 세 층.

① 글로벌 금융위기·폭락사   : 영어 위키백과
② 국내 폭락사              : 한국어 위키백과
③ 이번 폭락(최신)          : 가장 최근 RSS 스냅샷(news_snapshot.py)을 매체별 '뉴스 묶음' 문서로

강의의 '위키백과 코퍼스 수집 프롬프트' 규칙을 따른다:
- MediaWiki API만 쓴다 (HTML 크롤링 X), 호출 사이에 쉰다, continue 가 있으면 이어 받는다
- 시드 + 여러 시드가 함께 가리키는 문서(2홉 후보)
- 본문 3000자 미만 토막글, 연도·목록·틀·분류 문서는 버린다
- links 에는 코퍼스 안에 있는 제목만 남긴다
- 마지막에 문서 수 · 총 글자 수 · 토큰 수 · 링크 수 중앙값 · 링크 0개 문서를 출력한다
뉴스 묶음은 위키와 링크로 이어져 있지 않다 → 코디네이터의 '배정'만이 유일한 경로다.

실행:  .venv\\Scripts\\python.exe -X utf8 collect.py
"""
import json
import re
import statistics
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import requests

# ── 도메인에 묶인 값: 주제를 바꾸려면 여기만 고친다 ──────────────────────────
SEEDS = {
    "en": [
        "Panic of 1907", "Wall Street crash of 1929", "Great Depression",
        "Black Monday (1987)", "Savings and loan crisis", "Japanese asset price bubble",
        "1997 Asian financial crisis", "1998 Russian financial crisis",
        "Long-Term Capital Management", "Dot-com bubble", "Subprime mortgage crisis",
        "2007–2008 financial crisis", "Bankruptcy of Lehman Brothers", "European debt crisis",
        "2010 flash crash", "2015–2016 Chinese stock market turbulence",
        "2020 stock market crash", "2022 stock market decline", "2023 United States banking crisis",
        "2025 stock market crash",
        # 국내와 연결되는 영어 문서
        "South Korea and the International Monetary Fund", "Chaebol", "KOSPI",
        "2024 South Korean martial law crisis",
        # 오늘 뉴스에 나오는 장치들(강제청산·서킷브레이커·양적완화)
        "Margin (finance)", "Trading curb", "Quantitative easing",
    ],
    "ko": [
        "대한민국의 IMF 구제금융 요청", "1997년 아시아 금융 위기", "한보그룹", "대우그룹",
        "대한민국의 경제", "외환보유고", "2008년 세계 금융 위기", "2020년 주가 대폭락",
        "검은 월요일 (1987년)", "12.3 내란", "한국거래소", "코스닥", "라임 사태",
        "대공황", "닷컴 버블", "경제적 전염", "뱅크런", "1998년 러시아 금융 위기",
    ],
}
TARGET = {"en": 34, "ko": 0}    # 언어별로 이만큼 모으면 2홉 확장을 멈춘다
# ko 는 2홉 확장을 하지 않는다: 한국어 위키의 2홉 후보가 금융위기 틀(목록 상자) 탓에
# 19세기 미국 공황들로 채워져 '국내 폭락사' 층이 사라졌기 때문(1차 수집 결과)
MIN_CHARS = 3000
MIN_COSEED = 2
EXCLUDE = {  # 여러 시드가 가리키지만 주제와 무관하게 너무 일반적인 문서
    "United States", "United Kingdom", "Japan", "China", "Germany", "France", "Russia",
    "Europe", "Asia", "New York City", "London", "Economics", "Money", "Bank",
    "Industrial Revolution", "2000s energy crisis", "ISBN", "ISSN", "Digital object identifier", "OCLC", "Wayback Machine", "JSTOR", "PubMed", "Bibcode", "S2CID",
    "World War I", "World War II", "Cold War", "Internet", "Gross domestic product", "Inflation",
    "The New York Times", "The Wall Street Journal", "Financial Times", "Reuters",
    "The Economist", "Bloomberg News", "CNBC", "BBC News", "Forbes", "Time (magazine)",
    "대한민국", "미국", "일본", "중국", "서울특별시", "경제학", "화폐", "인플레이션", "국내총생산",
    "제2차 세계 대전", "제1차 세계 대전", "냉전", "인터넷", "영국", "독일", "프랑스", "러시아",
}
NEWS_MIN_CHARS = 3000   # 이보다 짧은 매체 묶음은 '기타 매체' 묶음으로 합친다
# ─────────────────────────────────────────────────────────────────────────────

HEADERS = {"User-Agent": "AiffelDeepResearch/0.1 (https://github.com/wilstein91/Project_DeepResearch) python-requests"}
SKIP = re.compile(r"^(\d{3,4}s?$|\d{3,4}년$|\d{3,4} in |List of |Lists of |Template:|Category:|"
                  r"Timeline of |틀:|분류:|.*목록$)")
OUT = Path("data/corpus.json")            # 뉴스 포함 — 깃 제외
OUT_WIKI = Path("data/corpus_wiki.json")  # 위키만 — 깃에 올림
session = requests.Session()
session.headers.update(HEADERS)


def api(lang, params):
    """continue 를 끝까지 이어 받는다. 429(요청 과다)면 기다렸다 다시 시도."""
    params = {**params, "action": "query", "format": "json", "formatversion": 2, "redirects": 1}
    pages, cont = [], {}
    while True:
        for attempt in range(5):
            r = session.get(f"https://{lang}.wikipedia.org/w/api.php", params={**params, **cont}, timeout=30)
            if r.status_code == 200:
                break
            time.sleep(10 * (attempt + 1))
        else:
            raise RuntimeError(f"{lang} API가 계속 거절함: {r.status_code}")
        data = r.json()
        pages.extend(data.get("query", {}).get("pages", []))
        time.sleep(0.5)
        if "continue" not in data:
            return pages
        cont = data["continue"]


def fetch(lang, title):
    """(정식 제목, 본문, 링크 목록). extracts 는 한 번에 한 문서만."""
    p = api(lang, {"prop": "extracts", "explaintext": 1, "titles": title})
    p = p[0] if p else {}
    real, text = p.get("title", title), p.get("extract", "") or ""
    if len(text) < MIN_CHARS:
        return real, text, []
    links = [l["title"] for q in api(lang, {"prop": "links", "plnamespace": 0, "pllimit": "max", "titles": real})
             for l in q.get("links", [])]
    return real, text, links


def usable(t):
    return not SKIP.match(t) and t not in EXCLUDE


def collect_wiki(lang, docs, raw_links, lang_of):
    print(f"\n① [{lang}] 시드")
    for seed in SEEDS[lang]:
        title, text, links = fetch(lang, seed)
        if len(text) < MIN_CHARS or title in docs:
            print(f"   - 버림: {seed} ({len(text)}자)")
            continue
        docs[title], raw_links[title], lang_of[title] = text, links, lang
        print(f"   + {title}: {len(text):,}자")
    print(f"② [{lang}] 2홉 후보 (여러 시드가 함께 가리키는 것부터)")
    co = Counter(t for d, ls in raw_links.items() if lang_of[d] == lang
                 for t in set(ls) if t not in docs and usable(t))
    count = sum(1 for d in docs if lang_of[d] == lang)
    for cand, n in co.most_common():
        if count >= TARGET[lang] or n < MIN_COSEED:
            break
        title, text, links = fetch(lang, cand)
        if title in docs or len(text) < MIN_CHARS or not usable(title):
            continue
        docs[title], raw_links[title], lang_of[title] = text, links, lang
        count += 1
        print(f"   + {title}: 시드 {n}개가 가리킴, {len(text):,}자")


def collect_news(docs, raw_links, lang_of):
    snaps = sorted(Path("data/news/raw").glob("*.json"))
    if not snaps:
        print("\n③ 뉴스 스냅샷 없음 → news_snapshot.py 를 먼저 실행")
        return None
    snap = snaps[-1]
    items = json.loads(snap.read_text(encoding="utf-8"))
    print(f"\n③ 뉴스 묶음: {snap.name} ({len(items)}건)")
    by_source = {}
    for it in sorted(items, key=lambda x: x["published"], reverse=True):
        line = f"- [{it['published'][:16].replace('T', ' ')}] {it['title']}"   # 연도까지 — 빼면 모델이 연도를 지어낸다
        if it["summary"]:
            line += f" — {it['summary']}"
        by_source.setdefault(it["source"], []).append(line)
    stamp = snap.stem[:10]
    small = []
    for source, lines in by_source.items():
        text = "\n".join(lines)
        if len(text) < NEWS_MIN_CHARS:
            small.append((source, lines))
            continue
        title = f"[뉴스 {stamp}] {source}"
        docs[title], raw_links[title], lang_of[title] = text, [], "news"
        print(f"   + {title}: {len(lines)}건, {len(text):,}자")
    if small:
        title = f"[뉴스 {stamp}] 기타 매체({', '.join(s for s, _ in small)})"
        text = "\n".join(f"({s}) {l[2:]}" for s, ls in small for l in ls)
        docs[title], raw_links[title], lang_of[title] = text, [], "news"
        print(f"   + {title}: {len(text):,}자")
    return snap.name


def main():
    docs, raw_links, lang_of = {}, {}, {}
    if "--news-only" in sys.argv:          # 위키는 저장된 것을 그대로 쓰고 뉴스 묶음만 다시 만든다
        old = json.loads(OUT_WIKI.read_text(encoding="utf-8"))
        docs, raw_links, lang_of = dict(old["docs"]), dict(old["links"]), dict(old["meta"]["lang"])
    else:
        collect_wiki("en", docs, raw_links, lang_of)
        collect_wiki("ko", docs, raw_links, lang_of)
    snap = collect_news(docs, raw_links, lang_of)

    links = {t: sorted({l for l in raw_links[t] if l in docs and l != t}) for t in docs}
    meta = {"built": datetime.now().isoformat(timespec="minutes"), "news_snapshot": snap,
            "lang": lang_of}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"docs": docs, "links": links, "meta": meta}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    # 깃에 올리는 판: 뉴스 묶음(기사 제목·요약)을 뺀 위키만 — 저작권 (위키백과 본문은 CC BY-SA)
    wiki = [t for t in docs if lang_of[t] != "news"]
    OUT_WIKI.write_text(json.dumps({"docs": {t: docs[t] for t in wiki},
                                    "links": {t: [l for l in links[t] if l in wiki] for t in wiki},
                                    "meta": {**meta, "lang": {t: lang_of[t] for t in wiki}}},
                                   ensure_ascii=False, indent=1), encoding="utf-8")

    import tiktoken
    enc = tiktoken.get_encoding("o200k_base")   # gpt-4o 계열 토크나이저
    tokens = sum(len(enc.encode(t)) for t in docs.values())
    n_links = [len(v) for v in links.values()]
    print("\n===== 코퍼스 요약 =====")
    print(f"문서 수            : {len(docs)}  " + str(Counter(lang_of.values())))
    print(f"총 글자 수         : {sum(len(t) for t in docs.values()):,}")
    print(f"총 토큰 수         : {tokens:,}  (gpt-4o-mini 컨텍스트 윈도우 128,000의 {tokens/128000:.1f}배)")
    print(f"문서당 링크 중앙값 : {statistics.median(n_links)}")
    print(f"링크 0개 문서      : {[t for t, v in links.items() if not v] or '없음'}")


if __name__ == "__main__":
    main()
