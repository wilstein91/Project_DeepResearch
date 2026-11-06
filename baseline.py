"""단일 에이전트 대조군 — 나누지 않는다. 에이전트 하나가 순서대로 고르고, 읽고, 전부 쓴다.

공정하게 맞춘 것: 같은 코퍼스 · 같은 모델 · 같은 도구(read_one, 후보목록) · 같은 읽기 예산(절수 × 절예산).
예산을 끝까지 쓰는지 확인한다 — 중간에 멈추면 이긴 게 아니라 상대를 묶어 둔 것이다.
"""
import json
import sys
import time
from datetime import datetime

from common import DOCS, RUNS_FILE, ask, jload, reset_cost, 설정
from graph import read_one, 후보목록
from metrics import evaluate_parts, 한줄


def 단일에이전트(질문: str, 예산: int):
    읽음, 메모, 교정 = [], [], 0
    while len(읽음) < 예산:
        cand = 후보목록(읽음, [])
        raw = ask("너는 자료 조사 오케스트레이터다. 질문에 답하려면 다음에 어느 문서를 읽어야 하는지 "
                  "후보 중에서 정확히 하나 고른다. 문서는 영문 위키·한국어 위키·최신 뉴스가 섞여 있다.\n"
                  'JSON으로만: {"문서":"후보에 있는 제목 그대로"}',
                  f"[질문] {질문}\n[지금까지 모은 요약]\n"
                  + "\n".join(f"- {t}: {n[:120]}" for t, n in 메모)
                  + f"\n[후보] {', '.join(cand[:60])}", coord=True)
        고름 = str(jload(raw, {}).get("문서") or "")
        if 고름 not in DOCS or 고름 in 읽음:
            고름, 교정 = cand[0], 교정 + 1          # 엉뚱한 답이면 후보 첫 번째로 — 예산은 끝까지 쓴다
        읽음.append(고름)
        메모.append((고름, read_one(고름, 질문)))   # 요약이 전부 한 창에 쌓인다
    지시 = ("너는 조사 결과를 정리하는 필자다. 아래 요약들만 근거로 질문에 답하는 한국어 보고서를 써라. "
            f"'## 제목' 형식의 절을 {설정['절수']}개 두고 각 절은 여섯 문장 이상 쓴다. 문장마다 근거가 된 문서 제목을 "
            "«문서명» 으로 문장 끝 마침표 앞에 붙여라(영어 제목은 영어 그대로). 요약에 없는 내용은 쓰지 마라.")
    보고서 = ask(지시, f"[질문] {질문}\n[모은 요약]\n" + "\n\n".join(f"[{t}]\n{n}" for t, n in 메모), coord=True)
    return 읽음, 메모, 보고서, 교정


def run(질문: str, label: str = "단일 대조군", save: bool = True) -> dict:
    reset_cost()
    예산 = 설정["절수"] * 설정["절예산"]
    t0 = time.time()
    읽음, 메모, 보고서, 교정 = 단일에이전트(질문, 예산)
    sec = {"번호": 0, "절": "(단일 에이전트 전체)", "역할": "단일", "본문": 보고서, "읽은문서": 읽음,
           "메모": [list(x) for x in 메모], "인용": [], "충분": True, "부족": ""}
    m = evaluate_parts([["(단일 에이전트)", d] for d in 읽음], 보고서, [sec])
    m["예산"], m["예산소진"], m["선택교정"] = 예산, len(읽음) == 예산, 교정
    rec = {"시각": datetime.now().isoformat(timespec="seconds"), "방식": "단일", "라벨": label,
           "설정": dict(설정), "질문": 질문, "초": round(time.time() - t0), "plan": {}, "sections": [sec],
           "visited": [["(단일 에이전트)", d] for d in 읽음], "report": 보고서, "metrics": m,
           "log": [f"단일 에이전트 {len(읽음)}/{예산}건 읽음(선택 교정 {교정}) · {한줄(m)}"]}
    if save:
        with open(RUNS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


if __name__ == "__main__":
    r = run(sys.argv[1] if len(sys.argv) > 1 else "역대 주요 금융위기들의 공통 원인은 무엇인가?")
    print(r["log"][0])
