"""딥리서처 — ① 기획 → ② 배치 → ③ 서브에이전트(동시) → ④ 점검(재위임 루프) → ⑤ 종합 → ⑥ 평가.

강의(에이전트 팀 꾸리기 6·7) 구조를 그대로 따르고, 바꾼 곳은 주석에 [변경]으로 표시했다.
실행:  .venv\\Scripts\\python.exe -X utf8 graph.py "질문"
"""
import json
import operator
import re
import sys
import time
from datetime import datetime
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from common import COST, DOCS, LINKS, ROSTER, ROOT, RUNS_FILE, ask, jload, kind, reset_cost, 설정
from metrics import evaluate_parts, 인용들, 한줄


class Research(TypedDict):
    question: str
    plan: dict                                   # ① 목차 · 역할 · 배정
    sections: Annotated[list, operator.add]      # ③ 서브에이전트가 올린 절 원고 (병렬 → 이어 붙임)
    visited: Annotated[list, operator.add]       # ③ (절, 문서) — 누가 무엇을 읽었나
    report: str
    metrics: dict
    log: Annotated[list, operator.add]
    task: dict                                   # Send 로 서브에이전트 하나에게만 가는 지시
    prior: dict                                  # 재위임일 때 지난 바퀴 원고


# ── ① 기획 ──────────────────────────────────────────────────────────────────
CARD = 250


def cards() -> str:
    """문서 카드 = [종류] 제목 + 앞 250자. 코디네이터는 원문 대신 이것만 본다."""
    return "\n".join(f"- [{kind(t)}] {t}: {re.sub(r'\s+', ' ', v[:CARD])}" for t, v in DOCS.items())


def plan(s: dict) -> dict:
    roster = "\n".join(f"- {k}: {v}" for k, v in ROSTER.items())
    raw = ask(
        "너는 리서치 팀의 코디네이터다. 질문에 답하는 한국어 보고서의 목차를 짜고, 각 절을 리서처 에이전트 "
        f"하나에게 맡긴다. 절은 최대 {설정['절수']}개.\n"
        "목차는 반드시 **내용 단위**로 나눠라 — 위기·시기·국가·쟁점처럼 질문이 실제로 묻는 덩어리로 쪼갠다. "
        "'개요·연표·분석·결론' 같은 형식 단위로 나누지 마라. 그렇게 나누면 리서처 전부가 같은 문서를 읽는다.\n"
        "절마다 가장 먼저 읽어야 할 문서를 문서 카드에서 하나 배정하라. 절끼리 다른 문서를 주어라. "
        "문서는 영문 위키·한국어 위키·최신 뉴스 세 종류다. 질문이 최근 상황을 묻는다면 최신 뉴스 문서를 배정하라.\n"
        f"절의 성격에 맞는 리서처 에이전트를 명단에서 골라 붙여라.\n[리서처 에이전트 명단]\n{roster}\n"
        'JSON으로만: {"제목":"보고서 제목(한국어)","목차":[{"절":"절 제목","지시":"이 절에서 밝혀야 할 것 한두 문장",'
        '"역할":"명단에 있는 이름 그대로","시작문서":"카드에 있는 제목 그대로"}]}',
        f"[질문] {s['question']}\n[읽을 수 있는 문서 카드]\n{cards()}", coord=True)
    obj = jload(raw, {})
    toc, taken, 고침 = [], set(), 0
    for item in obj.get("목차", [])[:설정["절수"]]:
        role, seed = item.get("역할", ""), str(item.get("시작문서") or "")
        # 배정이 실제 문서를 가리키는지 코드가 검사한다 — 모델은 그럴듯한 제목을 지어낸다
        if 설정["배정"] and (seed not in DOCS or seed in taken):
            고침 += 1
            seed = next((t for t in DOCS if t not in taken), "")
        if not 설정["배정"]:
            seed = ""
        if seed:
            taken.add(seed)
        toc.append({"절": item.get("절", "무제"), "지시": item.get("지시", s["question"]),
                    "역할": role if (설정["역할"] and role in ROSTER) else "큰그림 담당",
                    "시작문서": seed, "예산": 설정["절예산"]})
    if not toc:
        toc = [{"절": "개요", "지시": s["question"], "역할": "큰그림 담당", "시작문서": "", "예산": 설정["절예산"]}]
    seeds = " · ".join(f"{t['역할']}→«{t['시작문서'] or '자율'}»" for t in toc)
    return {"plan": {"제목": obj.get("제목", s["question"]), "목차": toc, "배치": list(range(len(toc))),
                     "바퀴": 1, "배정교정": 고침},
            "log": [f"① 기획 목차 {len(toc)}절 · {seeds} · 배정 교정 {고침}건"]}


# ── ② 배치 ──────────────────────────────────────────────────────────────────
def dispatch(s: dict) -> dict:
    return {"log": [f"② 배치 {s['plan'].get('바퀴', 1)}바퀴 · 서브에이전트 {len(s['plan'].get('배치', []))}개 동시 파견"]}


def 절모음(sections: list) -> dict:
    """같은 절 원고가 여러 번 오면 하나만 남긴다.
    [변경] 강의는 '마지막 것'만 남겼다 → 인용이 빠진 두 번째 원고가 멀쩡한 첫 원고를 지우는 문제.
    '인용우선'이면 실제로 읽은 문서를 인용한 수가 더 많은 원고를 남긴다(같으면 나중 것)."""
    out = {}
    for sec in sections:
        old = out.get(sec["절"])
        if old is None or 설정.get("원고선택") == "덮어쓰기" or 유효인용(sec) >= 유효인용(old):
            out[sec["절"]] = sec
    return out


def 유효인용(sec: dict) -> int:
    return len([c for c in sec["인용"] if c in sec["읽은문서"]])


def fanout(s: dict):
    idxs = s["plan"].get("배치", [])
    if not idxs:
        return "review"
    done = 절모음(s["sections"])
    목차 = s["plan"]["목차"]
    sends = []
    for i in idxs:
        mine = 목차[i]["절"]
        남의구역 = {t["시작문서"] for j, t in enumerate(목차) if j != i and t["시작문서"]}
        남의구역 |= {d for name, sec in done.items() if name != mine for d in sec["읽은문서"]}
        sends.append(Send("researcher", {
            "question": s["question"],
            "task": {**목차[i], "번호": i, "피하기": sorted(남의구역) if 설정["구역"] else []},
            "prior": done.get(mine, {})}))
    return sends


# ── ③ 서브에이전트 ──────────────────────────────────────────────────────────
def read_one(title: str, brief: str) -> str:
    """격리의 경계 — 원문은 이 함수 안에서만 읽고, 밖으로는 짧은 한국어 요약만 나간다."""
    return ask("너는 자료 조사 담당이다. 아래 문서(영어일 수도 있다)를 읽고 지시에 관련된 내용만 "
               "한국어로 여섯 문장 이내로 간추려라. 연도·수치·고유명사는 정확히 옮겨라. "
               "관련 없으면 '관련 없음'이라고만 답하라.\n"
               f"[지시] {brief}", f"[문서: {title}]\n{DOCS[title]}")


def 후보목록(read: list, 피하기: list) -> list:
    """읽은 문서의 링크가 다음 후보다. 링크가 막히면 전체에서, 그것도 막히면 구역을 푼다."""
    쓴것 = set(read) | set(피하기)
    frontier = sorted({x for v in read for x in LINKS.get(v, []) if x in DOCS} - 쓴것)
    return frontier or [x for x in DOCS if x not in 쓴것] or [x for x in DOCS if x not in read]


def 역할문장(t: dict) -> str:
    return f"너는 {t['역할']}이다. {ROSTER.get(t['역할'], ROSTER['큰그림 담당'])}."


def 다음문서(t: dict, read: list, 피하기: list):
    cand = 후보목록(read, 피하기)
    raw = ask(f"{역할문장(t)} 맡은 절을 쓰기 위해 다음에 읽을 문서를 후보 중에서 정확히 하나 고른다. "
              "더 읽을 것이 없으면 그만둔다.\n"
              'JSON으로만: {"문서":"후보에 있는 제목 그대로"} 또는 {"문서":null}',
              f"[맡은 절] {t['절']}\n[지시] {t['지시']}\n[이미 읽음] {', '.join(read) or '없음'}\n"
              f"[후보] {', '.join(cand[:60])}")
    pick = str(jload(raw, {}).get("문서") or "")
    return pick if pick in DOCS and pick not in read else None


def 탐색(t: dict, prior: dict):
    read, notes = list(prior.get("읽은문서", [])), list(prior.get("메모", []))
    피하기 = t.get("피하기") or []
    다음 = t.get("시작문서") if t.get("시작문서") in DOCS else None
    for _ in range(t["예산"]):
        if 다음 is None or 다음 in read:
            다음 = 다음문서(t, read, 피하기)
        if 다음 is None:
            break
        notes.append([다음, read_one(다음, t["지시"])])
        read.append(다음)
        다음 = None
    return read, notes


def 집필(t: dict, notes: list) -> dict:
    자료 = "\n\n".join(f"[{d}]\n{n}" for d, n in notes) or "(읽은 자료 없음)"
    raw = ask(f"{역할문장(t)} 아래 자료만 근거로 한국어 보고서의 한 절을 써라. "
              "여섯 문장 이상 열두 문장 이하, 600자 이상. 모든 문장에 빠짐없이 근거가 된 문서 제목을 «문서명» 으로 "
              "붙여라 — 인용 없는 문장은 자료 없이 쓴 문장으로 본다. 문서명은 자료의 [대괄호] 안 제목을 한 글자도 "
              "바꾸지 말고 그대로 쓴다(영어 제목은 영어 그대로, '[뉴스 …]' 머리도 그대로). "
              "자료에 없는 내용은 쓰지 마라. 지시를 자료로 다 채우지 못했으면 충분을 false 로 하고 "
              "무엇이 비었는지 적어라.\n"
              'JSON으로만: {"본문":"...","충분":true,"부족":""}',
              f"[맡은 절] {t['절']}\n[지시] {t['지시']}\n[모은 자료]\n{자료}")
    obj = jload(raw, {})
    text = str(obj.get("본문") or "")
    if len(text) < 100:
        text = re.sub(r'^\s*\{.*?"본문"\s*:\s*"?', "", raw, flags=re.S)[:2500].strip()
    return {"본문": text, "충분": bool(obj.get("충분")), "부족": str(obj.get("부족") or "")}


def researcher(s: dict) -> dict:
    t = s["task"]
    read, notes = 탐색(t, s.get("prior") or {})
    원고 = 집필(t, notes)
    인용 = 인용들(원고["본문"])
    sec = {"번호": t["번호"], "절": t["절"], "역할": t["역할"], "지시": t["지시"], "본문": 원고["본문"],
           "시작문서": t.get("시작문서", ""), "피하기": t.get("피하기", []),
           "읽은문서": read, "메모": notes, "인용": 인용,
           "허위인용": sorted({c for c in 인용 if c not in read}),
           "충분": 원고["충분"], "부족": 원고["부족"], "바퀴": 2 if s.get("prior") else 1,
           "읽은글자": sum(len(DOCS[d][:80000]) for d in read)}
    mark = "충분" if sec["충분"] else f"부족({sec['부족'][:18]})"
    return {"sections": [sec], "visited": [[t["절"], d] for d in read],
            "log": [f"  ③ {t['역할']} «{t['절'][:16]}» {len(read)}건 읽고 {len(원고['본문'])}자 · "
                    f"인용 {len(인용)}곳 · {mark}"]}


# ── ④ 점검 ──────────────────────────────────────────────────────────────────
def review(s: dict) -> dict:
    latest = 절모음(s["sections"])
    toc, wheel = s["plan"]["목차"], s["plan"].get("바퀴", 1)
    if not 설정["재위임"] or wheel >= 설정["최대바퀴"]:
        gaps = []
    else:
        # [변경] 자기신고만 믿지 않는다 — 인용이 하나도 없는 원고는 '충분'이라 신고해도 부족으로 본다
        #        (실험 중 인용 0곳 원고가 '충분'으로 통과해 재위임이 한 번도 안 돈 일이 있었다)
        gaps = [i for i, t in enumerate(toc)
                if not latest.get(t["절"], {}).get("충분", False) or 유효인용(latest.get(t["절"], {"인용": [], "읽은문서": []})) == 0]
    if not gaps:
        why = "루프 없음" if not 설정["재위임"] else ("라운드 소진" if wheel >= 설정["최대바퀴"] else "빈 칸 없음")
        return {"plan": {**s["plan"], "배치": [], "종료": why},
                "log": [f"④ 점검 {len(toc)}절 중 빈 칸 0개 — 종합으로 ({why})"]}
    newtoc = [dict(t) for t in toc]
    for i in gaps:
        prev = latest.get(toc[i]["절"], {})
        newtoc[i]["지시"] = (f"{toc[i]['지시']} (재위임: 지난번에 «{'», «'.join(prev.get('읽은문서', [])) or '없음'}»를 "
                             f"읽었지만 {prev.get('부족') or '원고에 «문서명» 인용이 하나도 없었다'}. 그 빈 칸을 채우도록 아직 안 본 문서를 찾아라)")
    return {"plan": {**s["plan"], "목차": newtoc, "배치": gaps, "바퀴": wheel + 1},
            "log": [f"④ 점검 {len(toc)}절 중 빈 칸 {len(gaps)}개 — «{'», «'.join(toc[i]['절'][:12] for i in gaps)}» 재위임"]}


def route(s: dict) -> str:
    return "more" if s["plan"].get("배치") else "done"


# ── ⑤ 종합 ──────────────────────────────────────────────────────────────────
def synthesize(s: dict) -> dict:
    """본문은 고치지 않고 이어 붙인다. 편집자는 절 제목과 첫 90자만 본다(격리 유지, 인용 보존)."""
    order = sorted(절모음(s["sections"]).values(), key=lambda x: x["번호"])
    outline = "\n".join(f"{i+1}. {x['절']}: {x['본문'][:90]}…" for i, x in enumerate(order))
    raw = ask("너는 보고서를 마무리하는 편집자다. 아래는 리서처들이 각자 쓴 절의 제목과 첫머리다. "
              "본문은 고치지 말고, 전체를 여는 머리말과 닫는 맺음말만 한국어로 써라. 각각 세 문장 이내. "
              "새로운 사실이나 «인용»을 만들지 마라.\n"
              'JSON으로만: {"머리말":"...","맺음말":"..."}',
              f"[질문] {s['question']}\n[보고서 제목] {s['plan']['제목']}\n[절 목록]\n{outline}", coord=True)
    obj = jload(raw, {})
    parts = [f"# {s['plan']['제목']}", str(obj.get("머리말") or "")]
    for i, x in enumerate(order):
        parts.append(f"## {i+1}. {x['절']} _({x['역할']})_\n\n{x['본문']}")
    parts.append(f"## 맺음말\n\n{obj.get('맺음말') or ''}")
    report = "\n\n".join(p for p in parts if p.strip())
    return {"report": report, "log": [f"⑤ 종합 {len(order)}절 이어붙임 → 보고서 {len(report):,}자"]}


# ── ⑥ 평가 ──────────────────────────────────────────────────────────────────
def evaluate(s: dict) -> dict:
    m = evaluate_parts(s["visited"], s["report"], list(절모음(s["sections"]).values()))
    return {"metrics": m, "log": [f"⑥ 평가 {한줄(m)}"]}


def build():
    g = StateGraph(Research)
    for name, fn in [("plan", plan), ("dispatch", dispatch), ("researcher", researcher),
                     ("review", review), ("synthesize", synthesize), ("evaluate", evaluate)]:
        g.add_node(name, fn)
    g.add_edge(START, "plan")
    g.add_edge("plan", "dispatch")
    g.add_conditional_edges("dispatch", fanout, ["researcher", "review"])
    g.add_edge("researcher", "review")
    g.add_conditional_edges("review", route, {"more": "dispatch", "done": "synthesize"})
    g.add_edge("synthesize", "evaluate")
    g.add_edge("evaluate", END)
    return g.compile()


GRAPH = build()


def run(question: str, label: str = "기준", save: bool = True) -> dict:
    reset_cost()
    t0 = time.time()
    out = GRAPH.invoke({"question": question, "plan": {}, "sections": [], "visited": [], "report": "",
                        "metrics": {}, "log": [], "task": {}, "prior": {}})
    rec = {"시각": datetime.now().isoformat(timespec="seconds"), "방식": "팀", "라벨": label,
           "설정": dict(설정), "질문": question, "초": round(time.time() - t0),
           "plan": out["plan"], "sections": list(절모음(out["sections"]).values()),
           "원고전부": out["sections"], "visited": out["visited"], "report": out["report"],
           "metrics": out["metrics"], "log": out["log"]}
    if save:
        with open(RUNS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "역대 주요 금융위기들의 공통 원인은 무엇이고, 이번 폭락과는 무엇이 같고 다른가?"
    r = run(q, label="수동실행")
    print("\n".join(r["log"]))
    print(f"\n({r['초']}초)\n")
    print(r["report"])
