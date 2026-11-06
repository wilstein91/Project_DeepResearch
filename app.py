"""수업 제출용 로컬 데모: 보고서·담당·읽기 기록·출처를 한 화면에서 확인합니다."""
from datetime import datetime
import json
from pathlib import Path
import streamlit as st
from graph import ROOT, ResearchTeam, save_run
from baseline import run_baseline
from ablation import experiment_config, MODES
from metrics import CITATION

st.set_page_config(page_title="위기 아틀라스 · 리서치 실험실", page_icon="📚", layout="wide")
st.markdown("""<style>
.block-container{max-width:1450px;padding-top:2rem}h1{letter-spacing:-.04em}
[data-testid=stMetric]{background:rgba(128,142,165,.12);border:1px solid #7c899455;border-radius:12px;padding:14px}
</style>""", unsafe_allow_html=True)
config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
questions = json.loads((ROOT / "data" / "questions.json").read_text(encoding="utf-8"))
corpus = json.loads((ROOT / "data" / "corpus.json").read_text(encoding="utf-8"))
sources = json.loads((ROOT / "data" / "sources.json").read_text(encoding="utf-8"))
stats = json.loads((ROOT / "data" / "corpus_stats.json").read_text(encoding="utf-8"))
card_count = len(json.loads((ROOT / "data" / "fact_cards.json").read_text(encoding="utf-8")))

st.caption("모두의연구소 · 딥 리서처 프로젝트 · 기준일 2026.11.06")
st.title("위기 아틀라스")
st.write("코로나와 현재의 한미 증시를 비교하며, AI가 읽은 자료와 쓴 주장을 함께 점검합니다.")
st.info("현재 상태: 첫 유료 시험에서 근거 불일치를 발견했습니다. 아래 보고서는 검토용이며 제출 완료 결과가 아닙니다.")
summary = st.columns(4)
summary[0].metric("교재 방식 위키백과", f"{stats['wikipedia']['documents']}건")
summary[1].metric("보강 포함 자료", f"{len(corpus['docs'])}건")
summary[2].metric("전체 자료 토큰", f"{stats['combined']['token_counts_by_encoding']['o200k_base']:,}")
summary[3].metric("선택 모델 입력 한도", f"{config['model_context_tokens']:,}")
st.caption(f"토큰은 AI가 글을 읽는 분량 단위입니다. 전체 자료가 한 번에 들어가지 않아 분업과 탐색이 필요합니다. 짧은 관찰·요약 카드 {card_count}건은 3,000자 이상 문서 수에 포함하지 않습니다.")

tabs = st.tabs(["조사·보고서", "나란히 비교", "자료·출처", "내 의견·배운 점"])


def run_paths():
    return sorted([p for folder in ("runs", "offline_checks")
                   for p in (ROOT / "output" / folder).glob("*.json")
                   if not p.name.endswith("-matrix.json")], key=lambda p: p.name, reverse=True)


def render_result(result, key):
    if result.get("mock"):
        st.warning("비용 없는 가짜 응답으로 구조만 점검한 결과입니다. 시장 분석이나 성능 평가에 사용하지 않습니다.")
    else:
        st.caption(f"실제 실행 · {result.get('created_at', '')} · {result['config']['model']}")
    m = result["metrics"]
    cols = st.columns(3)
    cols[0].metric("추정 API 비용", f"${m['estimated_usd']:.5f}")
    cols[1].metric("인용 표시가 있는 문장", f"{m['citation_coverage']:.0%}")
    cols[2].metric("미열람 문서 인용", len(m["unread_citations"]))
    st.caption("인용 비율은 정답률이 아닙니다. 읽은 문서를 잘못 인용해도 이 숫자만으로는 알 수 없습니다.")
    st.markdown(result["report"])
    st.download_button("보고서 Markdown 내려받기", result["report"], file_name=f"research-{key}.md", key=f"download-{key}")
    with st.expander("담당별로 무엇을 읽고 썼는지 보기"):
        for d in result["selected"].values():
            st.markdown(f"**{d['title']} · {d['role']}**")
            st.write("읽은 자료: " + " / ".join(d["read"]))
            st.write("추가로 필요한 근거: " + (d.get("missing") or "충분하다고 자기 신고함; 검증된 정답이라는 뜻은 아닙니다."))
        st.json(result.get("log", []))
    with st.expander("자동 지표와 실제 호출 기록"):
        st.json(m)
        st.dataframe([{k: c.get(k) for k in ("actor", "stage", "section", "document", "input_chars", "input_tokens", "output_tokens", "usd", "seconds")} for c in result.get("calls", [])], hide_index=True)
    cited = sorted(set(CITATION.findall(result["report"])))
    if cited:
        with st.expander("인용한 자료와 주장 대조하기"):
            doc = st.selectbox("확인할 문서", cited, key=f"source-{key}")
            if doc in corpus["docs"]:
                st.caption(sources.get(doc, {}).get("source_type", ""))
                st.link_button("공식 페이지 또는 원문 열기", sources[doc]["url"])
                st.text_area("이 실행의 코퍼스에 저장한 본문", corpus["docs"][doc], height=300, key=f"text-{key}")


with tabs[0]:
    with st.expander("새 조사 실행 · 기본은 비용 없음"):
        item = st.selectbox("질문", questions, format_func=lambda q: f"{q['id']} · {q['type']}")
        st.write(item["question"])
        st.caption("왜 나누는가: " + item["division_reason"])
        mode = st.selectbox("실험 설정", MODES, format_func=lambda m: {
            "team":"분업 전체", "baseline":"단일 조사자", "no-assignment":"시작 자료·담당 영역 안내 끄기",
            "no-roles":"전문 역할 끄기", "no-redelegation":"부족한 절 추가 조사 끄기"}[m])
        selected_config = experiment_config(config, item, mode)
        st.write("시작 자료 수정안")
        st.dataframe([{"담당": r["name"], "범위": r["scope"], "시작 자료": r.get("suggested_start", "기획 AI가 선택")} for r in selected_config["roster"]], hide_index=True)
        live = st.checkbox(f"실제 API로 이번 1회 실행 (최대 ${config['max_usd_per_run']:.2f})", value=False)
        if st.button("선택한 방식으로 실행", type="primary"):
            try:
                with st.spinner("자료를 읽고 작성 중입니다. 실제 실행은 몇 분 걸릴 수 있습니다."):
                    result = run_baseline(selected_config, item["question"], mock=not live) if mode == "baseline" else ResearchTeam(selected_config, mock=not live).run(item["question"])
                    result.update(question_id=item["id"], mode=mode)
                    saved = save_run(result, f"{item['id']}-{mode}")
                    st.session_state["saved_result"] = str(saved)
                    st.rerun()
            except Exception as exc:
                st.error(f"실행 중단: {type(exc).__name__}. 비밀키 보호를 위해 원본 오류를 표시하지 않습니다. 비용 상한·네트워크·검증 기록을 확인해 주세요.")
    paths = run_paths()
    if paths:
        path = Path(st.selectbox("저장된 결과", [str(p) for p in paths], format_func=lambda p: Path(p).name, key="saved_result"))
        result = json.loads(path.read_text(encoding="utf-8"))
        render_result(result, "main")

with tabs[1]:
    st.subheader("보고서를 직접 나란히 읽습니다")
    st.write("숫자가 좋아도 주장의 근거가 맞는지 확인해야 합니다. 가짜 응답 결과와 실제 실험 결과를 섞어 순위를 매기지 않습니다.")
    paths = run_paths()
    if len(paths) >= 2:
        cols = st.columns(2)
        for i, col in enumerate(cols):
            with col:
                path = st.selectbox("왼쪽 결과" if i == 0 else "오른쪽 결과", paths, index=min(i, len(paths)-1), format_func=lambda p: p.name, key=f"compare-{i}")
                render_result(json.loads(path.read_text(encoding="utf-8")), f"compare-{i}")
    st.caption("수정 전 첫 시험은 실패 분석용입니다. 최종 비교는 같은 모델·자료·최대 읽기 예산으로 다시 실행한 결과끼리 합니다.")

with tabs[2]:
    doc = st.selectbox("자료 고르기", list(corpus["docs"]))
    st.json(sources[doc])
    st.link_button("출처 페이지 열기", sources[doc]["url"])
    st.text_area("저장 본문", corpus["docs"][doc], height=450)
    st.write("실제로 연결된 코퍼스 문서", corpus["links"][doc])
    st.caption("문서 사이의 연결은 실제 링크만 사용합니다. 주제가 비슷하다는 이유로 링크를 만들지 않습니다.")

with tabs[3]:
    st.subheader("제안 외의 의견을 직접 적는 곳")
    st.write("원하시는 변경을 자유롭게 적고 저장할 수 있습니다. 저장은 이 컴퓨터 안에서만 이뤄집니다. 채팅에도 붙여 주시면 다음 작업 지시로 반영하겠습니다.")
    directions = st.text_area("추가 지시 / 다른 안", placeholder="예: 현재 한국 자료를 더 보강하고 싶어요. 코로나는 3월만 비교해 주세요.")
    reflection = st.text_area("내가 원문과 대조해 판단한 내용", placeholder="어느 절의 어느 주장이 자료와 맞았는지, 어떤 설정이 왜 나았는지 내 말로 적어 주세요.")
    if st.button("내 의견을 프로젝트에 저장"):
        folder = ROOT / "output" / "user_notes"
        folder.mkdir(parents=True, exist_ok=True)
        note = f"# 사용자 의견\n\n{directions}\n\n# 직접 판단한 내용\n\n{reflection}\n"
        path = folder / (datetime.now().strftime("%Y%m%d-%H%M%S") + ".md")
        path.write_text(note, encoding="utf-8")
        st.success("저장했습니다. 채팅에 알려 주시면 읽고 반영하겠습니다.")
        st.code(note)
    st.subheader("이번 수업에서 익힐 순서")
    for title, explanation in [
        ("1. 자료 묶음 만들기", "코퍼스는 AI가 읽도록 모아 놓은 자료입니다. 문서 수뿐 아니라 분량·출처·실제 연결을 검사합니다."),
        ("2. 내용을 기준으로 일 나누기", "총괄은 기획하고, 조사 담당은 자기 범위의 문서를 읽습니다. 각자 받은 입력을 컨텍스트라고 합니다."),
        ("3. 부족한 부분만 다시 조사하기", "읽을 횟수와 재시도 횟수를 제한합니다. 새 원고가 인용을 망가뜨리면 이전 원고를 보존합니다."),
        ("4. 같은 조건으로 비교하기", "단일 조사자와 분업을 같은 모델·자료·최대 읽기 예산으로 비교합니다. 설정을 하나씩 끄는 실험을 어블레이션이라고 합니다."),
        ("5. 사람이 근거 확인하기", "인용 표시가 많아도 정답은 아닙니다. 문장·원문·시점을 대조하고 본인이 내린 판단을 보고서에 적습니다."),
    ]:
        st.markdown(f"**{title}**")
        st.write(explanation)
