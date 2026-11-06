"""교재 수집 코퍼스를 유지하고, 짧은 최신 관찰 카드를 구분해 보강합니다."""
from collections import Counter
import json
import os
from pathlib import Path
import statistics
import tiktoken

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(DATA / ".cache" / "tiktoken"))


def main():
    corpus = json.loads((DATA / "corpus.json").read_text(encoding="utf-8"))
    sources = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))
    cards = json.loads((DATA / "fact_cards.json").read_text(encoding="utf-8"))
    for title, card in cards.items():
        corpus["docs"][title] = card["text"]
        corpus["links"][title] = card["links"]  # 실제 원문에 없는 연결을 만들지 않습니다.
        sources[title] = {k: v for k, v in card.items() if k not in ("text", "links")}
        sources[title].update(chars=len(card["text"]), full_text=False,
                              modified="직접 작성한 관찰/요약 카드; 원문 전문 아님")
    for name, value in (("corpus.json", corpus), ("sources.json", sources)):
        (DATA / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stats = json.loads((DATA / "corpus_stats.json").read_text(encoding="utf-8"))
    sizes = [len(t) for t in corpus["docs"].values()]
    stats["combined"] = {
        "documents": len(sizes), "total_chars": sum(sizes), "minimum_doc_chars": min(sizes),
        "links": sum(len(v) for v in corpus["links"].values()),
        "median_links": statistics.median(len(v) for v in corpus["links"].values()),
        "zero_outgoing_links": [k for k, v in corpus["links"].items() if not v],
        "token_counts_by_encoding": {enc: sum(len(tiktoken.get_encoding(enc).encode(t, disallowed_special=()))
            for t in corpus["docs"].values()) for enc in ("o200k_base", "cl100k_base")},
    }
    stats["source_counts"] = dict(Counter(v["source_type"] for v in sources.values()))
    stats["fact_card_note"] = f"추가 카드 {len(cards)}건은 3000자 조건의 위키백과 40건에 포함하지 않음. 요약 카드는 원문 전문 열람으로 계산하지 않음."
    stats["model_context_check"] = {
        "candidate_model": "gpt-4o-mini", "actual_context_tokens": 128000,
        "corpus_o200k_tokens": stats["combined"]["token_counts_by_encoding"]["o200k_base"],
        "exceeds": stats["combined"]["token_counts_by_encoding"]["o200k_base"] > 128000,
        "source": "https://developers.openai.com/api/docs/models/gpt-4o-mini",
        "note": "모델 변경 시 실제 입력 한도로 재검증해야 함.",
    }
    (DATA / "corpus_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"documents": len(sizes), "total_chars": sum(sizes), "context_check": stats["model_context_check"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
