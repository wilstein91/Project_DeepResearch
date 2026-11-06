"""같은 모델·코퍼스·문서 선택/읽기 도구를 사용하는 순차 단일 조사자."""
from datetime import datetime, timezone
import hashlib
import time
from graph import ROOT, Draft, ResearchTeam
from metrics import measure


def run_baseline(config, question, mock=False):
    started = time.monotonic()
    engine = ResearchTeam(config, mock=mock)
    # 팀의 모든 담당·모든 라운드에 허용되는 총 읽기 횟수와 같습니다.
    budget = config["sections"] * config["documents_per_section"] * config["max_rounds"]
    task = {"id": 1, "title": "전체 질문의 단일 조사", "role": "단일 종합 조사자",
            "instruction": "질문 전체와 아래의 모든 범위를 혼자 조사한다.", "exclude": "자료 밖 추측", "start_document": "",
            "all_scopes": config["roster"]}
    seen, notes, log = [], [], []
    for _ in range(budget):
        chosen = engine.choose_document(question, task, seen, [], actor="researcher")
        if chosen is None:
            break
        notes.append(engine.read_one(chosen, question, task, actor="researcher"))
        seen.append(chosen)
        log.append({"stage": "baseline_read", "document": chosen})
    if len(seen) != budget:
        raise RuntimeError("단일 조사자가 동일 읽기 예산을 다 소비하지 못했습니다. 비교에서 제외해야 합니다.")
    drafts = []
    for i, scope in enumerate(config["roster"]):
        # 각 절의 출력 상한을 팀과 같게 유지합니다. 한 조사자가 모든 노트와
        # 앞서 쓴 원고를 계속 보며 순차 작성하므로 격리된 조사자는 아닙니다.
        section_task = {**task, "id": i + 1, "current_scope": scope}
        drafted = engine.model.ask(Draft, {"question": question, "task": section_task, "notes": notes,
            "previous_sections": [{"title": d["title"], "text": d["text"]} for d in drafts],
            "rule": "전체를 혼자 조사한 노트로 current_scope 절만 한국어 600~900자로 쓴다. 사실마다 마침표 앞에 «정확한 문서명» 인용. 읽지 않은 자료 인용 금지. 원문 구절과 노트가 뒷받침하는 사실·해석·확인 불가를 구분한다."},
            "researcher", "baseline_draft", i + 1)
        drafts.append({"id": i + 1, "title": scope["name"], "text": drafted.text, "role": task["role"], "read": list(seen),
               "notes": notes, "new_read": list(seen) if i == 0 else [], "sufficient": drafted.sufficient,
               "missing": drafted.missing, "round": 1})
    state = {"question": question, "selected": {str(d["id"]): d for d in drafts}}
    # 같은 종합 단계, 같은 총괄 입력 형식. 총괄은 원문 대신 절 원고만 봅니다.
    combined = engine.synthesize(state)
    metrics = measure("\n\n".join(d["text"] for d in drafts) + "\n\n" + combined["synthesis"], drafts, engine.model.calls,
                      read_events=seen)
    metrics["all_read_events_including_replaced_drafts"] = len(seen)
    return {**state, **combined, "drafts": drafts, "tasks": [task], "log": log, "metrics": metrics,
            "calls": engine.model.calls, "config": config, "mock": mock, "read_budget": budget,
            "created_at": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": round(time.monotonic() - started, 3),
            "corpus_sha256": hashlib.sha256((ROOT / "data" / "corpus.json").read_bytes()).hexdigest(),
            "stop_reason": "동일한 최대 읽기 예산을 전부 사용"}
