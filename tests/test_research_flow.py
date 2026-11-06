import copy
import json
from graph import ROOT, ResearchTeam
from metrics import draft_signals, measure


def configuration():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    config["documents_per_section"] = 1
    return config


def test_parallel_workers_return_all_sections_without_foreign_notes():
    team = ResearchTeam(configuration(), mock=True)
    captured = []
    original = team.model.ask
    def ask(schema, payload, *args, **kwargs):
        captured.append(copy.deepcopy(payload))
        return original(schema, payload, *args, **kwargs)
    team.model.ask = ask
    result = team.run("구조 확인")
    assert set(result["selected"]) == {"1", "2", "3", "4"}
    assert len(result["drafts"]) == 4
    assert result["metrics"]["estimated_usd"] == 0
    starts = {t["id"]: t["start_document"] for t in result["tasks"]}
    for payload in captured:
        if "notes" in payload:
            own = payload["task"]["id"]
            assert {n["document"] for n in payload["notes"]} == {starts[own]}
    synthesis_input = next(p for p in captured if "sections" in p and "cards" not in p)
    assert "full_text" not in synthesis_input
    assert all("notes" not in s for s in synthesis_input["sections"])


def test_only_insufficient_sections_redelegate_and_bad_replacement_is_retained():
    team = ResearchTeam(configuration(), mock=True)
    prior = {"id": 1, "text": "확인한 사실 «A».", "read": ["A"], "sufficient": False}
    other = {"id": 2, "text": "확인한 사실 «B».", "read": ["B"], "sufficient": True}
    bad = {**prior, "round": 2, "text": "미열람 자료 주장 «없는문서».", "sufficient": True}
    review = team.review({"selected": {"1": prior, "2": other}, "drafts": [bad], "round": 2})
    assert review["selected"]["1"]["text"] == prior["text"]
    assert review["pending"] == []  # 라운드 상한
    assert review["stop_reason"] == "최대 라운드"
    team.config["max_rounds"] = 3
    review = team.review({"selected": {"1": prior, "2": other}, "drafts": [], "round": 1})
    assert review["pending"] == [1]
    team.config["redelegate"] = False
    assert not team.review({"selected": review["selected"], "drafts": [], "round": 1})["pending"]


def test_assignment_and_role_switches_change_worker_inputs():
    config = configuration()
    config.update(assignment=False, roles=False)
    team = ResearchTeam(config, mock=True)
    planned = team.plan({"question": "구조 확인"})
    planned.update(question="구조 확인", round=1)
    sends = team.fanout(planned)
    assert all(s.arg["task"]["start_document"] == "" and s.arg["avoid"] == [] for s in sends)
    assert all(s.arg["task"]["role"] == "일반 조사 담당" for s in sends)


def test_citation_signals_detect_unread_and_count_post_punctuation_citation():
    draft = {"id": 1, "text": "첫 사실입니다. «A»\n둘째 사실입니다 «가짜».", "read": ["A"]}
    signals = draft_signals(draft)
    assert signals["coverage"] == 1
    assert signals["unsupported"] == ["가짜"]
    metrics = measure(draft["text"], [draft], [])
    assert metrics["unread_citations"] == ["가짜"]
    assert metrics["section_unread_citations"][0]["section"] == 1


def test_bad_start_document_stops_instead_of_silently_reading_first_history_doc():
    import pytest
    config = configuration()
    config["roster"][0]["suggested_start"] = "코퍼스에 없는 문서"
    team = ResearchTeam(config, mock=True)
    with pytest.raises(ValueError):
        team.plan({"question": "구조 확인"})
    assert not any(c["stage"] == "read_one" for c in team.model.calls)


def test_baseline_really_consumes_same_maximum_document_budget():
    from baseline import run_baseline
    config = configuration()
    config["max_rounds"] = 1
    result = run_baseline(config, "구조 확인", mock=True)
    reads = [c for c in result["calls"] if c["stage"] == "read_one"]
    assert len(reads) == config["sections"] * config["documents_per_section"] * config["max_rounds"]
    assert result["metrics"]["total_read_events"] == len(reads)
    assert result["metrics"]["duplicate_read_ratio"] == 0
