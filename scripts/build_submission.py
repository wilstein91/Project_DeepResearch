"""교재 예시의 output/runs.jsonl·ablation.json·reports/ 형태로 정리합니다.

실험을 실행하거나 실패를 성공으로 바꾸지 않습니다. 인터넷·AI 호출 없음.
"""
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
PILOT = "20261106T064103-Q1-team.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uploaded-ref", help="원격에서 실제 존재를 확인한 검토 커밋")
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    old_status = OUT / "submission_status.json"
    previous = json.loads(old_status.read_text(encoding="utf-8")) if old_status.exists() else {}
    uploaded = args.uploaded_ref or previous.get("uploaded_review_commit")
    review_path = OUT / "reviews.json"
    reviews = json.loads(review_path.read_text(encoding="utf-8")).get("runs", {}) if review_path.exists() else {}
    reports = OUT / "reports"
    reports.mkdir(exist_ok=True)
    runs = []
    for path in sorted((OUT / "runs").glob("*.json")):
        run = json.loads(path.read_text(encoding="utf-8"))
        if run.get("mock"):
            raise ValueError("가짜 응답을 유료 실행 폴더에 혼합할 수 없습니다.")
        reviewed = reviews.get(path.name, {})
        status = "제출 제외: " + reviewed.get("reason", "") if reviewed.get("status") == "rejected" else "직접 검토 필요"
        runs.append({"source_file": path.relative_to(ROOT).as_posix(), "review_status": status, **run})
        label = "FAILURE-" if reviewed.get("status") == "rejected" else "REPAIR-" if run.get("writing_repair_only") else "REVIEW-"
        text = f"> 상태: {status}\n\n" + run["report"]
        (reports / (label + path.stem + ".md")).write_text(text, encoding="utf-8")
    (OUT / "runs.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in runs), encoding="utf-8")
    matrices = []
    for path in sorted((OUT / "experiments").glob("*-matrix.json")):
        matrices.extend(json.loads(path.read_text(encoding="utf-8")))
    if any(row.get("mock") for row in matrices):
        raise ValueError("실제 비교 집계에 가짜 응답을 넣을 수 없습니다.")
    ablation = {"status": "실제 반복 비교 미실행" if not matrices else "직접 비교·원문 검토 필요",
                "cases_planned": ["Q1", "Q4", "Q5"], "repeats_planned": 2,
                "modes": ["team", "baseline", "no-assignment", "no-roles", "no-redelegation"],
                "actual_results": matrices, "offline_checks_location": "output/offline_checks/",
                "note": "오프라인 가짜 응답 숫자는 실제 성능 결과에 포함하지 않음"}
    (OUT / "ablation.json").write_text(json.dumps(ablation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failed_cost = 0.0
    failure_count = 0
    for path in (OUT / "failures").glob("*.json"):
        failed = json.loads(path.read_text(encoding="utf-8"))
        if not failed.get("mock"):
            failure_count += 1
            failed_cost += failed.get("known_estimated_usd", failed.get("estimated_usd_from_rounded_stdout", 0.0))
    completed_cost = sum(r.get("repair_estimated_usd", 0.0) if r.get("writing_repair_only") else r["metrics"]["estimated_usd"] for r in runs)
    manifest = {"updated_at": datetime.now(timezone.utc).isoformat(),
                "existing_github_repository": "https://github.com/wilstein91/Project_DeepResearch",
                "review_branch_url": "https://github.com/wilstein91/Project_DeepResearch/tree/codex/official-corpus-review-20261106",
                "uploaded_review_commit": uploaded,
                "review_draft_uploaded": bool(uploaded), "main_merged": False, "course_submitted": False,
                "required_files": {name: (ROOT / name).exists() for name in ["data/corpus.json", "data/questions.json",
                    "config.json", "graph.py", "metrics.py", "ablation.py", "baseline.py", "app.py", "README.md", "REPORT.md",
                    "output/runs.jsonl", "output/ablation.json", "output/reports"]},
                "actual_full_runs": sum(not r.get("writing_repair_only") for r in runs),
                "writing_repairs": sum(bool(r.get("writing_repair_only")) for r in runs),
                "failed_attempts": failure_count, "known_total_estimated_usd": round(completed_cost + failed_cost, 6),
                "cost_note": "작성 교정의 부모 실행 비용을 중복 합산하지 않음. 일부 중단 비용은 반올림된 표준출력 합계임.",
                "actual_ablation_runs": len(matrices),
                "remaining": ["수정 후 실제 보고서 검증", "동일 조건의 반복 비교", "작성자의 직접 판단·회고",
                              "검토 브랜치의 최종본을 확정하고 main에 반영", "수업 URL 제출"]}
    (OUT / "submission_status.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
