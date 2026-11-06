"""실제 비교 기록을 제출 보고서로 정리합니다. AI 호출·자동 순위 판정 없음."""
from collections import defaultdict
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
matrices = list((OUT / "experiments").glob("*-matrix.json"))
path = max(matrices, key=lambda p: p.stat().st_mtime)
rows = json.loads(path.read_text(encoding="utf-8"))
assert rows and all(not r["mock"] for r in rows)
assert len({r["model"] for r in rows}) == 1
assert len({r["corpus_sha256"] for r in rows}) == 1
grouped = defaultdict(list)
for row in rows:
    grouped[row["case"], row["mode"]].append(row)
labels = {"team": "전체 분업", "baseline": "단일 조사자", "no-assignment": "자료 배정 끄기",
          "no-roles": "전문 역할 끄기", "no-redelegation": "추가 조사 끄기"}
table = ["| 질문 | 설정 | 반복 수 | 평균 비용($) | 평균 실제 읽기 | 인용 문장 비율 | 미열람 인용 |",
         "|---|---|---:|---:|---:|---:|---:|"]
for (case, mode), items in sorted(grouped.items()):
    avg = lambda name: statistics.mean(x["metrics"][name] for x in items)
    table.append(f"| {case} | {labels[mode]} | {len(items)} | {avg('estimated_usd'):.5f} | {avg('total_read_events'):.1f} | {avg('citation_coverage'):.1%} | {sum(len(x['metrics']['unread_citations']) for x in items)} |")
comparison = "\n".join(table)
(OUT / "COMPARISON.md").write_text("# 실제 비교 기록\n\n" + comparison + "\n\n인용 비율은 정답률이 아니며 이 표로 자동 순위를 매기지 않습니다.\n", encoding="utf-8")
first_pair = [next((r for r in rows if r["case"] == "Q1" and r["mode"] == mode and r["repeat"] == 1), None)
              for mode in ("team", "baseline")]
if all(first_pair):
    texts = ["# 직접 읽고 판단할 첫 비교\n\nA는 전체 분업, B는 단일 조사자입니다. 같은 모델·코퍼스·최대 24건 읽기를 허용했습니다. 아래 원고는 실험 원본입니다.\n"]
    for name, row in zip(("A. 전체 분업", "B. 단일 조사자"), first_pair):
        run = json.loads((OUT / "runs" / Path(row["path"]).name).read_text(encoding="utf-8"))
        texts.append(f"## {name}\n\n실제 읽기 {row['metrics']['total_read_events']}건 · 추정 ${row['metrics']['estimated_usd']:.5f}\n\n" +
                     "\n\n".join(f"### {d['title']}\n\n{d['text']}" for d in run["selected"].values()))
    texts.append("## 직접 판단할 내용\n\n어느 쪽이 시점과 출처를 이해하기 쉬웠는지, 더 필요한 내용이 무엇인지 한두 문장으로 적습니다. 숫자만으로 정답을 정하지 않습니다.\n\n공통 점검: 위키백과 원문의 '2월 20일~4월 7일, 약 한 달'은 날짜 간격 47일과 어긋납니다. 출처 자체도 검토 대상입니다.")
    (OUT / "reports" / "COMPARE_Q1_FIRST_PAIR.md").write_text("\n\n".join(texts), encoding="utf-8")
stats = json.loads((ROOT / "data" / "corpus_stats.json").read_text(encoding="utf-8"))
reflection_file = OUT / "user_reflection.md"
reflection = reflection_file.read_text(encoding="utf-8") if reflection_file.exists() else "사용자 직접 평가를 기다리는 중입니다. AI가 작성자의 경험이나 판단을 대신 꾸며 쓰지 않았습니다."
complete = len(rows) == 20 and all(len(v) == 2 for v in grouped.values())
report = f"""# 금융위기·증시 충격 딥리서처

상태: 실제 비교 {len(rows)}/20회 {'완료' if complete else '진행 중'}. 작성자의 직접 평가·최종 제출 여부는 별도로 표시합니다.

## 1. 주제와 코퍼스

1900년 이후 금융위기와 증시 충격을 모아 2020년 코로나 급락기와 2026년 11월 5~6일의 한국·미국을 비교합니다. 교재의 한국어 위키백과 수집 방식(2홉 이내, 30건 이상, 각 3,000자 이상, 실제 링크, API 이어받기)을 기본으로 했습니다.

기본 위키백과 40건, 최소 3,006자, 687개 실제 내부 링크입니다. 공식 연준 본문 6건과 직접 작성한 짧은 사실 카드 8건을 보강해 전체 {stats['combined']['documents']}건·{stats['combined']['total_chars']:,}자입니다. 짧은 카드는 기본 3,000자 문서 수에 포함하지 않습니다. 실제 o200k_base 측정 {stats['combined']['token_counts_by_encoding']['o200k_base']:,}토큰으로 gpt-4o-mini의 128,000토큰 한도를 넘습니다. [모델 한도·가격 근거](https://developers.openai.com/api/docs/models/gpt-4o-mini).

코로나 시기의 한국은행 정책·국회예산정책처 사후 분석, 현재의 정부 발표·거래소 관찰·미국 장중 해설을 구분합니다. 관찰일·거래일·발표일·사후 분석을 혼동하지 않습니다. 출처 URL·버전·라이선스·변경 형태는 data/sources.json에 있습니다. 위키백과는 CC BY-SA 4.0, 연준 Board 본문은 공식 재사용 안내를 따릅니다. 다른 자료는 짧은 직접 작성 요약이며 원문 전문·이미지를 넣지 않았습니다.

## 2. 분업 설계

사용자가 고른 기간×시장 네 구역: 2020 한국 / 2020 미국 / 현재 한국 / 현재 미국입니다. config.json에 범위·역할·시작 자료·작성 근거 영역을 두었습니다. 총괄은 문서 카드만 보고, 조사자는 자기 자료·노트만 봅니다. 근거가 부족한 절만 최대 2라운드 안에서 추가 조사합니다. 인용 보존 신호가 악화하면 기존 원고를 유지합니다.

8개 질문과 분업의 필요·불필요 이유는 data/questions.json에 있고 정답표는 없습니다. 실제 반복 대표 사례는 Q1(네 구역 분산 비교)과 Q2(1907년 공황 단일 문서)입니다. Q2는 담당 1명으로 두어 나눌 필요가 작은 질문도 검토했습니다.

대표 Q1의 자료 구역에는 사람이 정리한 출발 자료와 허용 근거 목록을 적용했습니다. 따라서 이 실험은 순수하게 AI 수만 바꾼 비교가 아닙니다. 자료 배정 스위치는 시작 자료·타 담당 회피·작성 근거 범위를 함께 끕니다. 그 하위 요소의 효과까지 따로 분리하지 못한 한계가 있습니다.

## 3. 상태와 흐름

```mermaid
flowchart TD
 P[기획: 문서 카드] --> D[배치: 범위·역할·시작 자료]
 D --> W[Send: 독립 입력으로 병렬 조사]
 W --> R[충분성 자기 신고·원고 선택]
 R -->|부족한 절만·상한 이내| D
 R -->|종료| S[인용 보존·사실 비교표]
 S --> E[자동 지표·원문 대조]
```

State에는 question, tasks, pending, round, drafts, selected, log, synthesis, report, metrics가 있습니다. Send에 담당별 입력을 따로 담고 drafts/log는 리스트를 합쳐 수집합니다. 실제 메시지 글자 수를 총괄과 조사자별로 따로 기록합니다. 원문을 몰래 자르지 않습니다.

문서 선택은 실제 후보의 제한된 형식으로 받고, 원문에 실제 존재하는 구절만 근거로 남깁니다. 작성 AI는 근거 번호를 선택하며 문서명 인용은 프로그램이 붙입니다. 종합은 각 절의 문장을 보존한 비교표로 만듭니다. 인용 형식과 실제 의미 일치는 별개여서 원문 대조가 필요합니다.

## 4. 지표와 실제 비교

정답표·AI 심판을 사용하지 않습니다. 미열람/존재하지 않는 인용과 인용 없는 절은 경보로 확인합니다. 인용 문장 비율·편중·중복 읽기·읽고 미사용·입력 글자 수·실제 토큰·호출·비용은 비교 신호입니다. 인용 비율은 정답률이 아닙니다.

같은 모델·코퍼스 해시·도구·최대 읽기 예산으로 전체 분업, 단일 조사자, 자료 배정 끄기, 역할 끄기, 추가 조사 끄기를 두 질문에서 각각 2회 반복합니다. 단일 조사자는 총 최대 읽기 예산을 실제로 모두 소비합니다. 팀이 먼저 끝내면 실제 읽기량은 다르므로 함께 기록합니다. 동일 최대 예산이지 동일 실제 토큰 수를 맞춘 비교는 아닙니다.

{comparison}

이 표는 자동 순위표가 아닙니다. 반복 2회·대표 사례 2개라는 작은 범위이므로 모든 질문에 일반화할 수 없습니다. 실행 원문과 상세 기록은 output/runs, 집계는 output/ablation.json, 직접 나란히 읽는 자료는 output/reports/COMPARE_Q1_FIRST_PAIR.md에 있습니다. 가짜 응답 점검은 실제 성능 집계에서 제외했습니다.

## 5. 실패를 절·자료까지 추적

- 첫 시험: 현재 한국 절이 대공황을 인용하며 현재 회복을 주장했습니다. 미열람 인용 0이어도 의미가 틀릴 수 있었습니다. 실패 원본과 분석을 output/PILOT_REVIEW.md에 보존했습니다.
- 문서 선택: 목록에 없는 이름을 반환하면 조용히 첫 문서로 바꾸던 경로를 없애고 실제 후보 형식으로 제한했습니다. 중단과 비용 기록도 남깁니다.
- 현재 미국 절: 2023년 SVB를 현재 원인으로 가져온 원고를 발견해 시기·자료 영역을 분리했습니다.
- 종합: 연준 통화정책을 재정정책으로 쓰거나 정부의 설명을 확정 원인으로 바꾸는 추론이 나왔습니다. 절의 인용 문장을 보존한 비교표로 바꿨습니다.
- 원문 자체: 위키백과의 2020-02-20~04-07을 ‘약 한 달’이라 한 표현은 날짜 간격 47일과 맞지 않습니다. 인용이 원문과 같다는 사실만으로 정확성이 보장되지 않습니다. 원본을 보존하고 검토용 편집본에서는 이 상대기간 표현을 제외합니다.

## 6. 데모와 재현

app.py의 로컬 Streamlit 화면에서 질문·설정, 보고서 나란히 보기, 담당별 읽기·원고·부족 신고·호출 기록·원문을 확인합니다. 추가 의견과 직접 평가를 적는 칸도 있습니다. 실행 방법은 README.md에 있으며 기본은 비용 없는 구조 점검, 실제 API는 명시적으로 선택합니다. 코드 점검 9개를 통과했고, 크롬에서 무료 실행 결과의 저장과 화면 표시를 확인했습니다.

![데모 실행](output/screenshots/demo-free-run.jpg)

![사용자 의견·학습 안내](output/screenshots/demo-opinions.jpg)

## 7. 프로젝트 회고와 배운 점

이번 구현에서 가장 공들인 부분은 자료 수집 규칙, 실제 입력 격리, 잘못된 문서 선택 차단, 근거 구절과 인용의 연결입니다. 초기에는 데모·부가 문서와 실패한 작성 수정에 시간을 많이 써 진행 관리가 미흡했습니다. 개선 과제는 원문 자체의 날짜·수치 검증, 자유 추론의 과장 방지, 자료 배정의 세부 효과 분리입니다.

수업에서 확인할 핵심은 자료의 실제 분량 확인 → 내용별 분업 → 독립 입력 → 부족한 절만 재조사 → 같은 조건 비교 → 사람이 원문과 대조하는 순서입니다. 앞선 7개 노드와의 연결 및 전체 결과물에서 배운 점은 LEARNING_GUIDE.md에 모았습니다.

### 작성자의 직접 비교 평가

{reflection}
"""
(ROOT / "REPORT.md").write_text(report, encoding="utf-8")
print(json.dumps({"completed": len(rows), "matrix": path.name, "report": "REPORT.md"}, ensure_ascii=False))
