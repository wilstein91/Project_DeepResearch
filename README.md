# 금융위기·폭락사 딥리서처 (Deep Researcher)

AIFFEL AI Agent 2기 · 에이전트 팀 꾸리기 8 「딥리서치 에이전트 만들기 [프로젝트]」 제출물
작성: Sung, Hyun-Joon

> 코디네이터가 질문을 받아 **내용 단위 목차**를 짜고, 서브에이전트 넷을 **동시에** 보내 각자 배정받은 자료만 읽고 한 절씩 쓰게 한 뒤, 원고를 이어 붙여 장문 보고서를 만든다.
> 자료는 **영문 위키 34건 + 한국어 위키 15건 + 2026-11-06 국내 증시 뉴스 묶음 6건 = 55건, 약 58.6만 토큰** — `gpt-4o-mini` 컨텍스트 윈도우(128,000토큰)의 **4.6배**라 한 번에 넣을 수 없다.

자세한 설계·실험·회고는 **[REPORT.md](REPORT.md)**.

## 구조

| 파일 | 하는 일 |
|---|---|
| `collect.py` | 코퍼스 수집 — MediaWiki API(영·한), 최신 뉴스 스냅샷을 매체별 '뉴스 묶음' 문서로 → `data/corpus.json` |
| `news_snapshot.py` | 국내 증시·경제 RSS 6개를 지금 시점 그대로 저장 → `data/news/raw/` (저작권 때문에 깃 제외) |
| `config.json` | 도메인에 묶인 값 — 절 수 · 절 예산 · 바퀴 상한 · 역할 명단 · 스위치 |
| `common.py` | 코퍼스·설정 로드, LLM 호출 입구 `ask()`, 코디네이터/서브에이전트 글자 계량기 |
| `graph.py` | LangGraph: ① 기획 → ② 배치 → ③ 서브에이전트(Send 팬아웃) → ④ 점검(재위임 루프) → ⑤ 종합 → ⑥ 평가 |
| `metrics.py` | 정답표·판정 모델 없는 지표 (신호 6 + 경보 2) |
| `baseline.py` | 단일 에이전트 대조군 — 같은 자료·모델·도구·읽기 예산 |
| `ablation.py` | 스위치를 하나씩 끄고 같은 잣대로 재는 실험 |
| `app.py` | streamlit 데모 — 보고서 + 절마다 누가 무엇을 읽고 썼는지 + 인용 대조 |
| `data/questions.json` | 질문 12개와 질문마다 "왜 나눌 만한가" |
| `output/` | `runs_*.jsonl`(실행 기록 전체) · `ablation_*.json` · `reports/`(보고서 원문) |

## 실행 (Windows PowerShell)

```powershell
# 1) 가상환경과 패키지 (uv 사용)
uv venv .venv
uv pip install -p .venv\Scripts\python.exe -r requirements.txt

# 2) API 키 — .env.example 을 복사해 키를 넣는다 (.env 는 깃에 올라가지 않는다)
Copy-Item .env.example .env
notepad .env

# 3) 데모
.venv\Scripts\streamlit.exe run app.py
```

자료를 다시 모으려면(선택):

```powershell
.venv\Scripts\python.exe -X utf8 news_snapshot.py   # 그 시점의 뉴스 — 날짜가 바뀌면 내용도 바뀐다
.venv\Scripts\python.exe -X utf8 collect.py
```

실험 재현:

```powershell
.venv\Scripts\python.exe -X utf8 graph.py "질문"            # 한 번 실행, 로그와 보고서 출력
.venv\Scripts\python.exe -X utf8 ablation.py --only=Q5      # 질문 하나 × 설정 6가지 × 2번
```

⚠️ 저장소의 `data/corpus.json` 에는 뉴스 묶음(기사 제목·RSS 요약)이 들어 있지 않다. 뉴스는 저작권 때문에 `data/news/` 와 함께 깃에서 뺐고, 커밋된 코퍼스는 위키 49건만이다. 실험 기록(`output/`)은 뉴스 6건을 포함한 55건으로 돌린 결과다.

## 데모 화면

![데모](docs/demo_report.png)
![절마다 누가 무엇을 읽고 썼나](docs/demo_sections.png)
