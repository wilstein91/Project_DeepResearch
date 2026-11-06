"""딥리서처 데모 — 보고서와 함께 '절마다 누가 무엇을 읽고 무엇을 썼는지'를 보여 준다.
실행:  .venv\\Scripts\\streamlit.exe run app.py
"""
import json
import re
from urllib.parse import quote

import pandas as pd
import streamlit as st

from common import CORPUS, DOCS, LANG, ROOT, kind, resolve

st.set_page_config(page_title="금융위기 딥리서처", layout="wide")
RUNS = ROOT / "output/runs.jsonl"
CITE = re.compile(r"«([^»]+)»")


def load_runs():
    rows = []
    for f in sorted((ROOT / "output").glob("runs*.jsonl")):
        rows += [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    return sorted(rows, key=lambda r: r["시각"])


def 원문링크(t):
    lang = LANG.get(t)
    if lang in ("en", "ko"):
        return f"https://{lang}.wikipedia.org/wiki/{quote(t.replace(' ', '_'))}"
    return None


def 지표표(m):
    층 = m.get("층별인용", {})
    rows = [("근거율", f"{m['근거율']}%", "신호", "조사 깊이·재위임"),
            ("인용 편중", f"{m['인용편중']}%", "신호", "배정·구역"),
            ("중복률", f"{m['중복률']}%", "신호", "배정·구역"),
            ("읽고 안 쓴 문서", f"{len(m['읽고안쓴'])}건", "신호", "배정 품질"),
            ("층별 인용 (영/한/뉴스)", f"{층.get('영문위키',0)} / {층.get('한국어위키',0)} / {층.get('최신뉴스',0)}", "신호", "배정 (뉴스는 링크가 없어 배정만이 길)"),
            ("격리율", f"{m['격리율']}%  (코디 {m['코디네이터글자']:,}자 / 서브 {m['서브에이전트글자']:,}자)", "신호", "컨텍스트 격리 (30% 넘으면 실패)"),
            ("허위 인용", f"{len(m['허위인용'])}건 {m['허위인용'] or ''}", "경보", "0이어야 함"),
            ("인용 없는 절", f"{len(m['무근거절'])}개 {m['무근거절'] or ''}", "경보", "0이어야 함"),
            ("LLM 호출", f"{m['LLM호출']}회", "비용", "")]
    return pd.DataFrame(rows, columns=["지표", "값", "종류", "보는 장치"])


def 기록보기(r, key):
    st.markdown(f"**질문** {r['질문']}  \n방식 `{r['방식']}` · 설정 `{r['라벨']}` · {r['초']}초 · {r['시각']}")
    t1, t2, t3, t4 = st.tabs(["📄 보고서", "🧑‍🤝‍🧑 절마다 누가 무엇을 읽고 썼나", "🔎 인용 대조", "📊 지표"])
    with t1:
        st.markdown(r["report"])
    with t2:
        if r["plan"]:
            st.caption(f"① 기획: 목차 {len(r['plan']['목차'])}절 · 배정 교정 {r['plan'].get('배정교정', 0)}건 · "
                       f"멈춘 이유: {r['plan'].get('종료', '-')}")
        for sec in r["sections"]:
            ok = "✅ 충분" if sec["충분"] else f"⚠️ 부족 — {sec['부족']}"
            with st.expander(f"{sec['번호']+1}. {sec['절']} · {sec['역할']} · {len(sec['읽은문서'])}건 읽음 · {ok}"):
                if sec.get("지시"):
                    st.markdown(f"**받은 지시** {sec['지시']}")
                if sec.get("시작문서"):
                    st.markdown(f"**코디네이터가 배정한 시작 문서** «{sec['시작문서']}»")
                if sec.get("피하기"):
                    st.markdown(f"**피하라고 받은 남의 구역** {', '.join(sec['피하기'][:12])}")
                st.markdown("**읽은 순서와 읽고 남긴 메모** (원문은 이 서브에이전트 안에만 있고, 위로는 메모·원고만 올라감)")
                for i, (d, note) in enumerate(sec["메모"], 1):
                    st.markdown(f"{i}. `[{kind(d)}]` **{d}** ({len(DOCS.get(d, '')):,}자) — {note}")
                if r["방식"] == "팀":
                    st.markdown("**올린 원고**")
                    st.markdown(sec["본문"])
    with t3:
        st.caption("읽지 않은 문서를 인용한 것(허위 인용)은 코드가 잡는다. 읽은 문서를 엉뚱한 문장에 붙인 것(오귀속)은 "
                   "사람이 잡는다 — 문장 옆에 그 문서를 읽고 남긴 메모를 놓았다. 원문은 링크로 확인.")
        memo = {d: n for sec in r["sections"] for d, n in sec["메모"]}
        sents = [s for s in re.split(r"(?<=[.!?])\s+|\n", r["report"]) if CITE.search(s)]
        if not sents:
            st.warning("인용이 붙은 문장이 없다.")
        pick = st.selectbox("인용이 붙은 문장", range(len(sents)), format_func=lambda i: sents[i][:110], key=f"s{key}")
        if sents:
            st.info(sents[pick])
            for c in dict.fromkeys(r for r in (resolve(x) for x in CITE.findall(sents[pick])) if r):
                link = 원문링크(c)
                st.markdown(f"**«{c}»** `[{kind(c)}]`" + (f" — [원문 열기]({link})" if link else ""))
                st.write(memo.get(c, "⚠️ 이 문서는 읽은 기록이 없다 (허위 인용)"))
    with t4:
        st.dataframe(지표표(r["metrics"]), hide_index=True, use_container_width=True)
        st.code("\n".join(r["log"]), language=None)


st.title("📉 금융위기·폭락사 딥리서처")
meta = CORPUS.get("meta", {})
st.caption(f"코퍼스 {len(DOCS)}건 (영문 위키 {sum(v=='en' for v in LANG.values())} · 한국어 위키 "
           f"{sum(v=='ko' for v in LANG.values())} · 최신 뉴스 묶음 {sum(v=='news' for v in LANG.values())}) · "
           f"뉴스 스냅샷 {meta.get('news_snapshot', '-')} · 코디네이터 1 + 서브에이전트 최대 4")

mode = st.sidebar.radio("화면", ["새 질문 돌리기", "기록 보기", "두 보고서 나란히"])
runs = load_runs()

if mode == "새 질문 돌리기":
    qs = json.loads((ROOT / "data/questions.json").read_text(encoding="utf-8"))
    pre = st.selectbox("예시 질문", ["(직접 입력)"] + [f"{q['id']} [{q['성격']}] {q['질문']}" for q in qs])
    q = st.text_input("질문", "" if pre == "(직접 입력)" else pre.split("] ", 1)[1])
    방식 = st.radio("방식", ["팀 (코디네이터 + 서브에이전트)", "단일 에이전트 대조군"], horizontal=True)
    if st.button("조사 시작", type="primary", disabled=not q):
        with st.spinner("조사 중… (팀은 1~3분, OpenAI API 비용 발생)"):
            if 방식.startswith("팀"):
                import graph
                r = graph.run(q, label="데모")
            else:
                import baseline
                r = baseline.run(q, label="데모")
        기록보기(r, "new")

elif mode == "기록 보기":
    if not runs:
        st.warning("아직 기록이 없습니다.")
    else:
        i = st.selectbox("실행 기록", range(len(runs) - 1, -1, -1),
                         format_func=lambda i: f"{runs[i]['시각'][5:16]} · {runs[i]['방식']}/{runs[i]['라벨']} · {runs[i]['질문'][:50]}")
        기록보기(runs[i], "one")

else:
    if len(runs) < 2:
        st.warning("기록이 두 개 이상 필요합니다.")
    else:
        fmt = lambda i: f"{runs[i]['시각'][5:16]} · {runs[i]['방식']}/{runs[i]['라벨']} · {runs[i]['질문'][:40]}"
        a, b = st.columns(2)
        with a:
            i = st.selectbox("왼쪽", range(len(runs) - 1, -1, -1), format_func=fmt, key="L")
            기록보기(runs[i], "L")
        with b:
            j = st.selectbox("오른쪽", range(len(runs) - 1, -1, -1), index=1, format_func=fmt, key="R")
            기록보기(runs[j], "R")
