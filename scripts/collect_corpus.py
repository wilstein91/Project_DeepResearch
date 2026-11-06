"""교재의 한국어 위키백과 수집 규칙 + 사용자가 허용한 공식 보강 자료."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import statistics
import time
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup


# 교재 지시: 출발 문서는 파일 맨 위의 SEEDS에 둡니다.
SEEDS = [
    "1907년 공황",
    "1929년 월스트리트 대폭락",
    "대공황",
    "1973년 석유 파동",
    "검은 월요일 (1987년)",
    "일본의 거품 경제",
    "1997년 아시아 금융 위기",
    "대한민국의 IMF 구제금융 요청",
    "1998년 러시아 금융 위기",
    "닷컴 버블",
    "세계 금융 위기 (2007~2008년)",
    "유럽 국가 부채 위기",
    "2020년 주가 대폭락",
    "SVB 파산 사건",
    "2025년 주가 대폭락",
]

API_URL = "https://ko.wikipedia.org/w/api.php"
USER_AGENT = "ModulabsDeepResearcher/0.1 (educational financial-history corpus)"
MIN_CHARS = 3000
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
FED_LICENSE_URL = "https://www.federalreserve.gov/disclaimer.htm"
AS_OF = "2026-11-06"

# 추가 자료: 교재 기본 수집과 구분합니다. 전문의 권리는 기관 안내를 확인합니다.
OFFICIAL_SOURCES = [
    ("연준: 2008년 위기와 정책 대응 회고 (2009)", "https://www.federalreserve.gov/newsevents/speech/bernanke20090821a.htm"),
    ("연준: 코로나 충격 대응 발표 (2020-03-23)", "https://www.federalreserve.gov/newsevents/pressreleases/monetary20200323b.htm"),
    ("연준: SVB 감독 검토 핵심 사항 (2023)", "https://www.federalreserve.gov/publications/2023-April-SVB-Key-Takeaways.htm"),
    ("연준: SVB 감독 검토 요약 (2023)", "https://www.federalreserve.gov/publications/2023-April-SVB-Executive-Summary.htm"),
    ("연준: 금융안정보고서 개요 (2026-05)", "https://www.federalreserve.gov/publications/2026-may-financial-stability-report-overview.htm"),
    ("연준: 금융안정보고서 단기 위험 (2026-05)", "https://www.federalreserve.gov/publications/2026-may-financial-stability-report-near-term-risks.htm"),
]

# 국가 일반사·유명인 등으로 탐색이 샛길로 빠지지 않도록 제목 단계에서 제한합니다.
# 분량을 늘리기 위해 무관한 문서를 포함하지 않습니다.
FINANCE_WORDS = (
    "경제", "금융", "위기", "공황", "은행", "주가", "주식", "증권", "증시", "거래소",
    "통화", "금리", "금본위", "부채", "채무", "채권", "국채", "재정", "외환", "환율",
    "신용", "자산", "버블", "거품", "모기지", "연방준비", "연준", "브레턴", "인플레이션",
    "디플레이션", "스태그플레이션", "대마불사", "구제", "양적", "유동성", "리먼", "베어스턴스",
    "골드만", "모건", "메릴", "서브프라임", "월스트리트", "검은", "블랙", "석유", "오일",
    "대침체", "뉴딜", "나스닥", "코스피", "코스닥", "다우", "S&P", "SVB", "IMF",
    "FDIC", "국제결제", "헤지", "파생", "선물", "옵션", "예금", "인출", "투자", "세계화",
    "불황", "침체", "뱅크", "머니", "국제통화", "국제 통화", "세계은행", "세계 은행",
)


def eligible_title(title: str) -> bool:
    if ":" in title or "목록" in title or title.startswith(("틀", "분류")):
        return False
    if re.fullmatch(r"\d{1,4}년(?:대)?(?:\s*\d{1,2}월(?:\s*\d{1,2}일)?)?", title):
        return False
    event_year = re.search(r"(?:^|\()(\d{4})년", title)
    if event_year and int(event_year.group(1)) < 1900:
        return False
    if title.endswith("의 경제") and title not in SEEDS:
        return False
    return title in SEEDS or any(word.casefold() in title.casefold() for word in FINANCE_WORDS)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), unquote(parts.path).rstrip("/"), "", ""))


class WikiClient:
    def __init__(self, cache_dir: Path, delay: float = 0.3):
        USER_AGENT.encode("ascii")
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.cache_dir = cache_dir
        self.delay = max(0.3, delay)
        self.last_request = 0.0
        self.calls = 0

    def query(self, parameters: dict) -> dict:
        time.sleep(max(0.0, self.delay - (time.monotonic() - self.last_request)))
        defaults = {"action": "query", "format": "json", "formatversion": 2, "maxlag": 5}
        for attempt in range(3):
            try:
                self.last_request = time.monotonic()
                response = self.session.get(API_URL, params={**defaults, **parameters}, timeout=30)
                self.calls += 1
                if response.status_code == 429 and attempt < 2:
                    self.delay = max(self.delay, 1.0)
                    retry_after = response.headers.get("Retry-After", "5")
                    time.sleep(min(60.0, float(retry_after)) if retry_after.isdigit() else 5.0)
                    continue
                response.raise_for_status()
                value = response.json()
                if "error" in value:
                    raise RuntimeError(str(value["error"]))
                return value
            except (requests.RequestException, ValueError, RuntimeError):
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
        raise RuntimeError("Unreachable retry branch")

    def page(self, title: str) -> dict:
        cache_key = hashlib.sha256(title.encode("utf-8")).hexdigest()
        cached_path = self.cache_dir / f"{cache_key}.json"
        if cached_path.exists():
            return json.loads(cached_path.read_text(encoding="utf-8"))
        parameters = {
            "titles": title, "redirects": 1,
            "prop": "extracts|links|info|pageprops|extlinks",
            "explaintext": 1, "exlimit": 1, "exsectionformat": "plain",
            "plnamespace": 0, "pllimit": "max", "ellimit": "max",
            "inprop": "url",
            "ppprop": "disambiguation",
        }
        merged: dict = {"requested_title": title, "links": [], "external_links": []}
        continuation = {}
        while True:
            value = self.query({**parameters, **continuation})
            pages = value.get("query", {}).get("pages", [])
            if not pages:
                raise RuntimeError(f"No page object for {title}")
            page = pages[0]
            for key in ("title", "pageid", "fullurl", "missing", "extract", "lastrevid", "touched", "pageprops"):
                if key in page:
                    merged[key] = page[key]
            merged["links"].extend(link["title"] for link in page.get("links", []) if link.get("ns") == 0)
            merged["external_links"].extend(link.get("url", link.get("*", "")) for link in page.get("extlinks", []))
            continuation = value.get("continue", {})
            if not continuation:
                break
        merged["links"] = sorted(set(merged["links"]))
        merged["external_links"] = sorted(set(filter(None, merged["external_links"])))
        merged["retrieved_at"] = datetime.now(timezone.utc).isoformat()
        write_json(cached_path, merged)
        return merged


def official_documents(session: requests.Session) -> tuple[dict, dict, dict, list]:
    docs, metadata, outward, skipped = {}, {}, {}, []
    # 공개 열람을 재배포 허가로 오인하지 않도록 기관의 재사용 안내도 남깁니다.
    disclaimer = session.get(FED_LICENSE_URL, timeout=30)
    disclaimer.raise_for_status()
    disclaimer_text = BeautifulSoup(disclaimer.content, "html.parser").get_text(" ", strip=True)
    if "public domain" not in disclaimer_text.casefold():
        raise RuntimeError("Federal Reserve Board reuse notice could not be verified")
    write_json(DATA / "source-policies" / "federal-reserve-board.json", {
        "url": FED_LICENSE_URL, "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "policy_text": disclaimer_text,
        "rule": "Board-authored text only; third-party copyrighted material and media excluded",
    })
    for label, url in OFFICIAL_SOURCES:
        try:
            time.sleep(0.3)
            response = session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
            main = soup.find(id="content") or soup.find("main")
            if main is None:
                raise ValueError("Main article container missing")
            outward[label] = sorted({urljoin(response.url, a["href"]) for a in main.find_all("a", href=True)})
            source_title = soup.title.get_text(" ", strip=True) if soup.title else label
            # Navigation and graphics are not included in the public-domain text corpus.
            for element in main.select("script, style, nav, footer, form, button, .shareDL, .breadcrumb, .sr-only, img, svg"):
                element.decompose()
            raw_text = main.get_text("\n", strip=True)
            raw_text = re.split(r"\nLast Update:", raw_text, maxsplit=1)[0]
            text = re.sub(r"\n{3,}", "\n\n", raw_text).strip()
            if len(text) < MIN_CHARS:
                skipped.append({"title": label, "reason": "official_shorter_than_3000", "chars": len(text), "url": url})
                continue
            docs[label] = text
            metadata[label] = {
                "source_type": "official_supplement", "publisher": "Board of Governors of the Federal Reserve System",
                "language": "en", "url": response.url, "original_title": source_title,
                "retrieved_at": datetime.now(timezone.utc).isoformat(), "as_of": AS_OF,
                "license": "Public domain Board text, unless otherwise indicated",
                "license_url": FED_LICENSE_URL, "chars": len(text), "modified": "HTML navigation and media removed; original language preserved",
                "caution": "Institution-authored source; separate observed facts from institutional assessment. No event inferred from publication year.",
            }
            print(json.dumps({"official": label, "chars": len(text)}, ensure_ascii=False), flush=True)
        except (requests.RequestException, ValueError) as error:
            skipped.append({"title": label, "reason": "official_fetch_failed", "error": str(error), "url": url})
    return docs, metadata, outward, skipped


def collect(target: int, max_attempts: int, with_official: bool) -> dict:
    client = WikiClient(DATA / ".cache" / "wikipedia")
    docs, metadata, raw_links, external_links = {}, {}, {}, {}
    aliases: dict[str, str] = {}
    skipped = []
    visited = set()
    origins: dict[str, set[str]] = {}
    direct_seed_refs: dict[str, set[str]] = {}
    hops: dict[str, int] = {}
    existence_checked = set()

    def fetch(title: str, hop: int, source_seeds: set[str]) -> None:
        visited.add(title)
        page = client.page(title)
        canonical = page.get("title", title)
        aliases[title] = canonical
        visited.add(canonical)
        if page.get("missing"):
            skipped.append({"title": title, "reason": "missing"})
            return
        if "disambiguation" in page.get("pageprops", {}):
            skipped.append({"title": canonical, "reason": "disambiguation"})
            return
        if canonical in raw_links:
            return
        text = page.get("extract", "").strip()
        raw_links[canonical] = page["links"]
        external_links[canonical] = page["external_links"]
        if hop < 2:
            for linked in page["links"]:
                if eligible_title(linked):
                    origins.setdefault(linked, set()).update(source_seeds)
                    hops[linked] = min(hops.get(linked, 99), hop + 1)
                    if hop == 0:
                        direct_seed_refs.setdefault(linked, set()).add(canonical)
        if len(text) < MIN_CHARS:
            skipped.append({"title": canonical, "reason": "shorter_than_3000", "chars": len(text), "hop": hop})
            return
        docs[canonical] = text
        metadata[canonical] = {
            "source_type": "wikipedia_course_prompt", "publisher": "Korean Wikipedia contributors",
            "language": "ko", "url": page.get("fullurl", "https://ko.wikipedia.org/wiki/" + quote(canonical.replace(" ", "_"))),
            "pageid": page.get("pageid"), "revision_id": page.get("lastrevid"), "page_touched_at": page.get("touched"),
            "retrieved_at": page["retrieved_at"], "as_of": AS_OF,
            "license": "CC BY-SA 4.0; per-page notices apply", "license_url": LICENSE_URL,
            "chars": len(text), "hop": hop, "origin_seeds": sorted(source_seeds),
            "modified": "MediaWiki plaintext extract; no translation or substantive text editing",
        }
        print(json.dumps({"wiki_docs": len(docs), "title": canonical, "chars": len(text), "hop": hop}, ensure_ascii=False), flush=True)

    for seed in SEEDS:
        fetch(seed, 0, {seed})
    attempts = 0
    while len(docs) < target and attempts < max_attempts:
        candidates = [title for title in origins if title not in visited and hops[title] <= 2]
        if not candidates:
            break
        # Multiple seeds sharing a candidate get priority, as in the course prompt.
        candidates.sort(key=lambda t: (-len(direct_seed_refs.get(t, set())), -len(origins[t]), hops[t], t))
        unchecked = [title for title in candidates if title not in existence_checked][:50]
        if candidates[0] not in existence_checked:
            # 없는 문서는 본문을 받기 전에 묶어서 확인합니다. 본문은 여전히 한 문서씩 받습니다.
            info = client.query({"titles": "|".join(unchecked), "prop": "info", "redirects": 1})
            query_info = info.get("query", {})
            remaps = {item["from"]: item["to"] for item in query_info.get("normalized", []) + query_info.get("redirects", [])}
            pages = {page["title"]: page for page in query_info.get("pages", [])}
            for title in unchecked:
                existence_checked.add(title)
                canonical = title
                for _ in range(10):
                    if canonical not in remaps:
                        break
                    canonical = remaps[canonical]
                page_info = pages.get(canonical, {})
                if page_info.get("missing"):
                    visited.add(title)
                    skipped.append({"title": title, "reason": "missing_prechecked"})
                elif 0 < page_info.get("length", 0) < MIN_CHARS:
                    visited.add(title)
                    skipped.append({"title": title, "reason": "source_smaller_than_3000_bytes"})
            continue
        title = candidates[0]
        fetch(title, hops[title], origins[title])
        attempts += 1
    if len(docs) < 30:
        raise RuntimeError(f"Only {len(docs)} eligible Wikipedia documents; minimum is 30")

    wiki_docs = dict(docs)
    wiki_metadata = dict(metadata)
    wiki_links = {title: sorted({aliases.get(link, link) for link in raw_links[title] if aliases.get(link, link) in wiki_docs and aliases.get(link, link) != title}) for title in wiki_docs}
    write_json(DATA / "corpus_wikipedia.json", {"docs": wiki_docs, "links": wiki_links})
    write_json(DATA / "sources_wikipedia.json", wiki_metadata)

    official_outward = {}
    if with_official:
        extra_docs, extra_metadata, official_outward, extra_skipped = official_documents(client.session)
        docs.update(extra_docs)
        metadata.update(extra_metadata)
        skipped.extend(extra_skipped)
    url_to_title = {canonical_url(meta["url"]): title for title, meta in metadata.items()}
    links = {}
    for title in docs:
        found = set(wiki_links.get(title, []))
        for url in external_links.get(title, []) + official_outward.get(title, []):
            mapped = url_to_title.get(canonical_url(url))
            if mapped and mapped != title:
                found.add(mapped)
        links[title] = sorted(found)
    # No inferred or fabricated bridges are added between source groups.
    corpus = {"docs": docs, "links": links}
    write_json(DATA / "corpus.json", corpus)
    write_json(DATA / "sources.json", metadata)
    write_json(DATA / "collection_skipped.json", skipped)

    def summary(subset: dict, edges: dict) -> dict:
        sizes = [len(text) for text in subset.values()]
        link_sizes = [len(edges[title]) for title in subset]
        tokens = {}
        import tiktoken
        for name in ("o200k_base", "cl100k_base"):
            encoder = tiktoken.get_encoding(name)
            tokens[name] = sum(len(encoder.encode(text, disallowed_special=())) for text in subset.values())
        return {"documents": len(subset), "total_chars": sum(sizes), "minimum_doc_chars": min(sizes),
                "links": sum(link_sizes), "median_links": statistics.median(link_sizes),
                "zero_outgoing_links": [title for title in subset if not edges[title]],
                "token_counts_by_encoding": tokens}

    result = {
        "collected_at": datetime.now(timezone.utc).isoformat(), "as_of": AS_OF,
        "course_prompt": {"language": "ko", "max_hops": 2, "minimum_doc_chars": MIN_CHARS,
                          "minimum_wiki_docs": 30, "api": API_URL, "delay_seconds": client.delay,
                          "target_wiki_docs": target, "seeds": SEEDS},
        "wikipedia": summary(wiki_docs, wiki_links), "combined": summary(docs, links),
        "source_counts": dict(Counter(item["source_type"] for item in metadata.values())),
        "wiki_api_calls_this_run": client.calls,
        "model_context_check": "Pending actual model choice; token counts are measured, model capacity not yet selected.",
    }
    write_json(DATA / "corpus_stats.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=60)
    parser.add_argument("--max-attempts", type=int, default=180)
    parser.add_argument("--with-official", action="store_true")
    arguments = parser.parse_args()
    collect(max(30, arguments.target), arguments.max_attempts, arguments.with_official)
