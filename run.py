"""실행 입구. 기본은 비용 없는 가짜 응답 점검이며 --live만 유료입니다."""
import argparse
import json
from pathlib import Path
from graph import ROOT, ResearchTeam, save_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="실제 OpenAI API 사용; 설정된 비용 상한 적용")
    parser.add_argument("--question-id", default="Q1")
    parser.add_argument("--max-usd", type=float, help="이번 실행의 별도 상한. 기본 설정보다 낮게만 적용")
    parser.add_argument("--mode", choices=["team", "baseline", "no-assignment", "no-roles", "no-redelegation"], default="team")
    args = parser.parse_args()
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    if args.max_usd is not None:
        if args.max_usd <= 0 or args.max_usd > config["max_usd_per_run"]:
            parser.error("별도 상한은 0보다 크고 기본 상한 이하여야 합니다.")
        config["max_usd_per_run"] = args.max_usd
    questions_path = ROOT / "data" / "questions.json"
    question = config["main_question"]
    if questions_path.exists():
        item = next(q for q in json.loads(questions_path.read_text(encoding="utf-8")) if q["id"] == args.question_id)
        question = item["question"]
        if "roster" in item:
            config["roster"] = item["roster"]
            config["sections"] = len(item["roster"])
    if args.mode == "no-assignment":
        config["assignment"] = False
    elif args.mode == "no-roles":
        config["roles"] = False
    elif args.mode == "no-redelegation":
        config["redelegate"] = False
    if args.mode == "baseline":
        from baseline import run_baseline
        result = run_baseline(config, question, mock=not args.live)
    else:
        result = ResearchTeam(config, mock=not args.live).run(question)
    result["mode"] = args.mode
    result["question_id"] = args.question_id
    path = save_run(result, f"{args.question_id}-{args.mode}")
    print(json.dumps({"saved": str(path), "mock": result["mock"], "metrics": result["metrics"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
