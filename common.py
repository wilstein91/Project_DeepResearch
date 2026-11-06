"""모든 파일이 함께 쓰는 것: 코퍼스, 설정, LLM 호출 입구(ask), 글자 수 계량기(COST)."""
import json
import os
import re
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
assert os.getenv("OPENAI_API_KEY", "").startswith("sk-"), ".env 에 OPENAI_API_KEY 를 넣으세요 (.env.example 참고)"

from langchain_openai import ChatOpenAI  # noqa: E402  (키를 읽은 뒤에 불러온다)

_cp = ROOT / "data/corpus.json"                     # 뉴스 포함판 (collect.py 를 돌리면 생김, 깃 제외)
if not _cp.exists():
    _cp = ROOT / "data/corpus_wiki.json"            # 저장소에 들어 있는 위키만 판
CORPUS = json.loads(_cp.read_text(encoding="utf-8"))
DOCS, LINKS = CORPUS["docs"], CORPUS["links"]
LANG = CORPUS.get("meta", {}).get("lang", {})          # 제목 → en / ko / news

CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
설정 = dict(CONFIG["설정"])          # 절제 실험이 하나씩 끄는 스위치들
ROSTER = CONFIG["역할명단"]
LLM_MODEL = CONFIG.get("모델", "gpt-4o-mini")
# 실행 기록 파일. 실험을 질문별 프로세스로 동시에 돌릴 때 서로 섞이지 않게 환경변수로 나눈다
RUNS_FILE = ROOT / "output" / os.getenv("RUNS_FILE", "runs.jsonl")

llm = ChatOpenAI(model=LLM_MODEL, temperature=0, timeout=90, max_retries=0)

# 계량기 — 코디네이터(coord)와 서브에이전트가 읽은 글자를 따로 센다 (격리를 숫자로 증명)
COST = {"calls": 0, "sub_chars": 0, "coord_chars": 0}
_lock = threading.Lock()          # 서브에이전트 넷이 동시에 세므로 잠금
일시적오류 = ("RateLimit", "APIConnection", "Timeout", "InternalServer")


def reset_cost():
    with _lock:
        COST.update(calls=0, sub_chars=0, coord_chars=0)


def ask(system: str, user: str, coord: bool = False, cap: int = 80000) -> str:
    """모든 LLM 호출의 입구. 호출 수·읽은 글자 수를 센다."""
    body = user[:cap]
    with _lock:
        COST["calls"] += 1
        COST["coord_chars" if coord else "sub_chars"] += len(body)
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": body}]
    for 시도 in range(4):
        try:
            return llm.invoke(msgs).content
        except Exception as e:
            잠깐뿐 = any(k in type(e).__name__ for k in 일시적오류)
            if 시도 == 3 or not 잠깐뿐:
                raise
            time.sleep(2 ** 시도 + 1)


def jload(raw: str, default):
    """모델 답에서 JSON 부분만 꺼낸다. 실패하면 기본값."""
    try:
        m = re.search(r"\[.*\]" if isinstance(default, list) else r"\{.*\}", raw, re.S)
        return json.loads(m.group(0))
    except Exception:
        return default


def kind(title: str) -> str:
    return {"en": "영문 위키", "ko": "한국어 위키", "news": "최신 뉴스"}.get(LANG.get(title, ""), "문서")


def _norm(x: str) -> str:
    return re.sub(r"[\[\]\s()·,:'\"]", "", x).casefold()


def resolve(c: str):
    """인용 «…» 를 실제 문서 제목으로. 모델은 '[뉴스 2026-11-06] 동아일보 경제' 를 '동아일보 경제',
    '뉴스 2026-11-06 동아일보 경제' 처럼 줄이거나 괄호를 빼고 쓰곤 한다 → 괄호·공백을 무시하고 비교해,
    그 글자를 포함하는 문서가 '딱 하나'일 때만 그 문서로 본다(둘 이상이면 인정하지 않는다)."""
    c = c.strip()
    if c in DOCS:
        return c
    n = _norm(c)
    if len(n) < 3:
        return None
    hit = [t for t in DOCS if n == _norm(t)] or [t for t in DOCS if n in _norm(t)]
    return hit[0] if len(hit) == 1 else None
