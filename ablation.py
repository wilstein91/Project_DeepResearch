"""실제 스위치를 하나씩 끈 반복 비교. 기본은 비용 없는 구조 점검입니다."""
import argparse
import copy
from datetime import datetime, timezone
import json
from graph import ROOT, ResearchTeam, save_run
from baseline import run_baseline

MODES = ("team", "baseline", "no-assignment", "no-roles", "no-redelegation")


def experiment_config(base, item, mode):
    config = copy.deepcopy(base)
    if "roster" in item:
        config["roster"] = item["roster"]
        config["sections"] = len(item["roster"])
    if mode == "no-assignment":
        config["assignment"] = False
    elif mode == "no-roles":
        config["roles"] = False
    elif mode == "no-redelegation":
        config["redelegate"] = False
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cases", nargs="+", default=["Q1", "Q4", "Q5"])
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--max-total-usd", type=float, default=0.0,
                        help="유료 비교 전체 상한. 명시하지 않으면 유료 실행을 거부합니다.")
    args = parser.parse_args()
    if args.live and args.max_total_usd <= 0:
        parser.error("--live에는 검토한 --max-total-usd를 명시해야 합니다.")
    if args.repeats < 1:
        parser.error("반복 수는 1 이상이어야 합니다.")
    base = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    questions = {q["id"]: q for q in json.loads((ROOT / "data" / "questions.json").read_text(encoding="utf-8"))}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    directory = ROOT / "output" / ("experiments" if args.live else "offline_checks")
    directory.mkdir(parents=True, exist_ok=True)
    rows = []
    index = directory / (stamp + "-matrix.json")
    for case in args.cases:
        item = questions[case]
        for repeat in range(1, args.repeats + 1):
            # 팀을 항상 먼저 돌리는 시간 순서 효과를 줄이기 위해 회전합니다.
            offset = (repeat - 1) % len(MODES)
            for mode in MODES[offset:] + MODES[:offset]:
                config = experiment_config(base, item, mode)
                spent = sum(r["metrics"]["estimated_usd"] for r in rows)
                if args.live and args.max_total_usd - spent < config["max_usd_per_run"]:
                    print("전체 비용 상한의 남은 금액이 1회 상한보다 작아 다음 실행을 시작하지 않습니다.")
                    return
                engine = None
                try:
                    if mode == "baseline":
                        result = run_baseline(config, item["question"], mock=not args.live)
                    else:
                        engine = ResearchTeam(config, mock=not args.live)
                        result = engine.run(item["question"])
                except Exception as exc:
                    failure = {"case": case, "repeat": repeat, "mode": mode, "error_type": type(exc).__name__,
                               "completed_calls": engine.model.calls if engine else [],
                               "note": "실패 뒤 자동 재실행하지 않음. 원본 오류문/키 미기록. 과금 불명확 호출은 공급자 사용량 확인 필요."}
                    (directory / (stamp + "-failure.json")).write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
                    raise RuntimeError("실험이 중단됐습니다. 저장한 실패 기록과 공급자 사용량을 검토해 주세요.") from None
                result.update(question_id=case, mode=mode, repeat=repeat)
                path = save_run(result, f"{case}-{mode}-r{repeat}")
                rows.append({"case": case, "repeat": repeat, "mode": mode, "path": str(path),
                             "metrics": result["metrics"], "elapsed_seconds": result["elapsed_seconds"],
                             "corpus_sha256": result["corpus_sha256"], "model": config["model"],
                             "max_read_budget": config["sections"] * config["documents_per_section"] * config["max_rounds"],
                             "mock": result["mock"]})
                index.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"index": str(index), "runs": len(rows), "estimated_usd": sum(r["metrics"]["estimated_usd"] for r in rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
