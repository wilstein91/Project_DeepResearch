"""기존 실제 읽기 노트를 재사용해 작성 단계만 교정합니다. 전체 반복 실험이 아닙니다."""
import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from graph import ROOT, ResearchTeam, save_run
from metrics import measure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--max-usd", type=float, required=True)
    args = parser.parse_args()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    if source.get("mock"):
        raise ValueError("실제 읽기 기록만 재사용합니다.")
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    config["max_usd_per_run"] = args.max_usd
    engine = ResearchTeam(config, mock=False)
    started = time.monotonic()
    selected = copy.deepcopy(source["selected"])
    def rewrite(item):
        key, draft = item
        task = {k: draft[k] for k in ("id", "title", "role", "instruction", "exclude", "start_document")}
        task["supported_years"] = [2020] if draft["id"] in (1, 2) else [2026]
        task["evidence_documents"] = config["roster"][draft["id"] - 1].get("evidence_documents", [])
        result = engine.write_section(task, draft["notes"])
        return key, {**draft, **result.model_dump(), "editorial_revision": 1}
    with ThreadPoolExecutor(max_workers=4) as pool:
        selected = dict(pool.map(rewrite, selected.items()))
    combined = engine.synthesize({"question": source["question"], "selected": selected})
    result = {**source, **combined, "selected": selected, "calls": source["calls"] + engine.model.calls,
              "writing_repair_only": True, "parent_run": args.source.name,
              "repair_note": "원래 전체 흐름 완료 후 같은 읽기 근거로 작성만 교정. 독립된 전체 실행·어블레이션 결과가 아님.",
              "repair_calls": engine.model.calls, "repair_estimated_usd": sum(c["usd"] for c in engine.model.calls)}
    result["parent_created_at"] = source["created_at"]
    result["created_at"] = datetime.now(timezone.utc).isoformat()
    result["repair_elapsed_seconds"] = round(time.monotonic() - started, 3)
    result["elapsed_seconds"] = source["elapsed_seconds"] + result["repair_elapsed_seconds"]
    drafts = list(selected.values())
    result["metrics"] = measure("\n\n".join(d["text"] for d in drafts) + "\n\n" + result["synthesis"], drafts, result["calls"],
                                read_events=[t for d in source["drafts"] for t in d["new_read"]])
    path = save_run(result, "Q1-writing-repair")
    print(json.dumps({"saved": str(path), "repair_usd": result["repair_estimated_usd"], "metrics": result["metrics"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
