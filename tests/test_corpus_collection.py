"""자료 수집 실패가 조용히 누락·잘림으로 이어지지 않는지 확인합니다."""

import importlib.util
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "scripts" / "collect_corpus.py"
spec = importlib.util.spec_from_file_location("collect_corpus", path)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def test_pagination_preserves_full_text_and_collects_later_links(tmp_path):
    client = collector.WikiClient(tmp_path)
    observed = []
    responses = [
        {"query": {"pages": [{"title": "대공황", "pageid": 1, "lastrevid": 123,
                               "extract": "본문" * 2000, "links": [{"ns": 0, "title": "금본위제"}]}]},
         "continue": {"plcontinue": "next", "continue": "||"}},
        {"query": {"pages": [{"title": "대공황", "pageid": 1,
                               "links": [{"ns": 0, "title": "은행"}],
                               "extlinks": [{"url": "https://www.federalreserve.gov/example"}]}]}},
    ]
    def query(parameters):
        observed.append(parameters)
        return responses.pop(0)
    client.query = query
    page = client.page("대공황")
    assert page["extract"] == "본문" * 2000
    assert set(page["links"]) == {"금본위제", "은행"}
    assert page["lastrevid"] == 123
    assert page["external_links"] == ["https://www.federalreserve.gov/example"]
    assert observed[1]["plcontinue"] == "next"


def test_excludes_years_and_lists_but_keeps_dated_crisis_articles():
    assert not collector.eligible_title("1997년")
    assert not collector.eligible_title("은행 목록")
    assert not collector.eligible_title("분류:금융 위기")
    assert not collector.eligible_title("1819년 공황")
    assert not collector.eligible_title("검은 금요일 (1869년)")
    assert not collector.eligible_title("시리아의 경제")
    assert collector.eligible_title("1997년 아시아 금융 위기")
    assert collector.eligible_title("1907년 공황")
