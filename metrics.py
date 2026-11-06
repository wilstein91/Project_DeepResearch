"""정답표·판정용 AI 없이 읽기 기록과 보고서에서 실패 신호를 계산합니다."""
from collections import Counter
import re

CITATION = re.compile(r"«([^»]+)»")


def sentences(text):
    # 제목은 문장에서 제외하고, 마침표 뒤 인용도 앞 문장에 붙여 셉니다.
    lines = [line.strip() for line in text.splitlines()
             if line.strip() and not line.lstrip().startswith(("#", "작성 담당:", "실행 모드:", "기준일:"))]
    text = "\n".join(lines)
    text = re.sub(r"([.!?。])\s*((?:«[^»]+»\s*)+)", r" \2\1 ", text)
    return [part.strip() for part in re.split(r"(?<=[.!?。])\s+|\n+", text)
            if re.search(r"[가-힣A-Za-z0-9]", CITATION.sub("", part))]


def draft_signals(draft):
    cited = CITATION.findall(draft["text"])
    read = set(draft["read"])
    parts = sentences(draft["text"])
    return {"citations": len(cited), "unsupported": sorted(set(cited) - read),
            "coverage": sum(bool(CITATION.search(part)) for part in parts) / max(1, len(parts))}


def measure(report, drafts, calls, read_events=None):
    cited = CITATION.findall(report)
    if read_events is None:
        read_events = [title for draft in drafts for title in draft["read"]]
    read_set = set(read_events)
    parts = sentences(report)
    counts = Counter(cited)
    section_invalid = [{"section": d["id"], "documents": draft_signals(d)["unsupported"]}
                       for d in drafts if draft_signals(d)["unsupported"]]
    coordinator_chars = sum(c["input_chars"] for c in calls if c["actor"] == "coordinator")
    researcher_chars = sum(c["input_chars"] for c in calls if c["actor"] == "researcher")
    return {
        "report_chars": len(report), "sentences": len(parts), "citation_count": len(cited),
        "citation_coverage": sum(bool(CITATION.search(part)) for part in parts) / max(1, len(parts)),
        "unread_citations": sorted(set(cited) - read_set), "section_unread_citations": section_invalid,
        "read_but_unused": sorted(read_set - set(cited)),
        "citation_concentration": max(counts.values(), default=0) / max(1, len(cited)),
        "duplicate_read_ratio": (len(read_events) - len(read_set)) / max(1, len(read_events)),
        "total_read_events": len(read_events), "unique_documents_read": len(read_set),
        "zero_citation_sections": [d["id"] for d in drafts if not CITATION.search(d["text"])],
        "coordinator_input_chars": coordinator_chars, "researcher_input_chars": researcher_chars,
        "coordinator_context_share": coordinator_chars / max(1, coordinator_chars + researcher_chars),
        "llm_calls": len(calls), "input_tokens": sum(c["input_tokens"] for c in calls),
        "output_tokens": sum(c["output_tokens"] for c in calls),
        "estimated_usd": round(sum(c["usd"] for c in calls), 6),
        "warning": "인용 표시의 존재를 셉니다. 원문과 주장 사이의 의미 일치·인과관계는 사람이 원문과 대조해야 합니다."
    }
