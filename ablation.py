"""절제(소거) 실험 — 기준에서 출발해 스위치를 '하나씩만' 끄고, 단일 에이전트 대조군과 함께 같은 잣대로 잰다.
같은 설정도 시행마다 십몇 %p씩 흔들리므로 질문마다 REPEAT 번 돌려 평균과 범위를 함께 본다.

실행:  .venv\\Scripts\\python.exe -X utf8 ablation.py            (전체)
       .venv\\Scripts\\python.exe -X utf8 ablation.py --quick    (질문 1개 × 1번, 동작 확인용)
결과:  output/ablation.json, output/reports/<질문번호>_<설정>_<n>.md, output/runs.jsonl
"""
import json
import statistics
import sys

import baseline
import graph
from common import ROOT, 설정

SWITCHES = [("기준", {}),
            ("배정·구역 끔", {"배정": False, "구역": False}),
            ("역할 끔", {"역할": False}),
            ("재위임 끔", {"재위임": False}),
            ("원고 덮어쓰기", {"원고선택": "덮어쓰기"})]
KEYS = ["근거율", "인용편중", "중복률", "읽은문서", "인용수", "보고서자수", "격리율", "LLM호출"]
REPEAT = 2


def 요약(ms: list) -> dict:
    out = {}
    for k in KEYS:
        vals = [m[k] for m in ms]
        out[k] = {"평균": round(statistics.mean(vals), 1), "최소": min(vals), "최대": max(vals)}
    for k in ["허위인용", "무근거절", "읽고안쓴"]:
        out[k + "_평균개수"] = round(statistics.mean(len(m[k]) for m in ms), 1)
    out["최신뉴스인용_평균"] = round(statistics.mean(m["층별인용"]["최신뉴스"] for m in ms), 1)
    return out


def main():
    qs = json.loads((ROOT / "data/questions.json").read_text(encoding="utf-8"))
    targets = [q for q in qs if q.get("실험")]
    quick = "--quick" in sys.argv
    if quick:
        targets = targets[:1]
    only = [x.split("=", 1)[1] for x in sys.argv if x.startswith("--only=")]
    if only:
        targets = [q for q in targets if q["id"] == only[0]]
    repeat = 1 if quick else REPEAT
    (ROOT / "output/reports").mkdir(parents=True, exist_ok=True)
    원본 = dict(설정)
    result = {"반복": repeat, "질문": {}}
    for q in targets:
        print(f"\n■ {q['id']} [{q['성격']}] {q['질문']}")
        result["질문"][q["id"]] = {"질문": q["질문"], "성격": q["성격"], "설정별": {}}
        for 이름, 끄기 in SWITCHES + [("단일 대조군", {})]:
            ms = []
            for n in range(repeat):
                설정.clear(); 설정.update(원본); 설정.update(끄기)       # 늘 기준에서 출발해 하나만 끈다
                r = baseline.run(q["질문"]) if 이름 == "단일 대조군" else graph.run(q["질문"], label=이름)
                ms.append(r["metrics"])
                fn = f"{q['id']}_{이름.replace('·', '').replace(' ', '')}_{n+1}.md"
                (ROOT / "output/reports" / fn).write_text(r["report"], encoding="utf-8")
                print(f"   {이름:<8} #{n+1} {r['log'][-1].replace('⑥ 평가 ', '')[:150]}")
            result["질문"][q["id"]]["설정별"][이름] = 요약(ms)
    설정.clear(); 설정.update(원본)
    out = ROOT / ("output/ablation.json" if not only else f"output/ablation_{only[0]}.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장: {out}")


if __name__ == "__main__":
    main()
