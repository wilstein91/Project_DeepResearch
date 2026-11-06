"""⑥ 평가 — 정답표도, 판정 모델(LLM 채점)도 쓰지 않는다.
만들어진 보고서와 '누가 무엇을 읽었나(visited)' 기록만 본다.
그래서 설정을 바꿔도, 단일 에이전트에도 같은 잣대가 그대로 돈다.

지표마다 보는 장치:
  [신호 — 설정끼리 높낮이를 견준다]
  근거율    «문서명»이 붙은 문장 ÷ 전체 문장                  → 조사 깊이·재위임
  인용편중  가장 많이 인용된 문서의 인용 ÷ 전체 인용            → 배정·구역
  중복률    같은 문서를 여러 절이 읽은 정도                     → 배정·구역
  읽고안쓴  읽었지만 보고서에 한 번도 인용 안 된 문서          → 배정 품질(문서 카드)
  층별인용  영문 위키 / 한국어 위키 / 최신 뉴스 인용 수        → 배정(뉴스는 링크가 없어 배정만이 길)
  격리율    코디네이터가 읽은 글자 ÷ 팀 전체가 읽은 글자      → 컨텍스트 격리 (30% 넘으면 실패)
  [경보 — 0이어야 한다. 0이 아니면 그 보고서는 비교에서 뺀다]
  허위인용  인용한 문서 − 실제로 읽은 문서
  무근거절  인용이 하나도 없는 절 (자료 없이 모델 상식으로 쓴 신호)
"""
import re
from collections import Counter

from common import COST, DOCS, LANG, resolve

CITE = re.compile(r"«([^»]+)»")


def 인용들(글: str) -> list:
    """글 속 «…» 를 실제 문서 제목으로 바꿔 돌려준다. 어느 문서인지 특정 못 하면 뺀다."""
    return [r for r in (resolve(c) for c in CITE.findall(글)) if r]


def 문장들(글: str) -> list:
    """보고서를 문장으로 자른다.
    강의 버전의 문제 두 가지를 고쳤다(REPORT.md 참고):
      ① 모델이 «인용»을 마침표 '뒤'에 붙이면 인용이 다음 문장으로 넘어가 근거율이 낮게 나온다
         → 마침표 바로 뒤의 인용 묶음을 앞 문장 안으로 당긴다
      ② '## 1. 절 제목' 같은 제목 줄도 문장으로 셌다 → 제목 줄은 뺀다
    """
    글 = re.sub(r"([.!?。])\s*((?:«[^»]+»[\s,·]*)+)", lambda m: " " + m.group(2).strip() + m.group(1) + " ", 글)
    줄들 = [l for l in 글.split("\n") if not l.lstrip().startswith("#")]
    return [x.strip() for x in re.split(r"(?<=[.!?。])\s+|\n", "\n".join(줄들)) if len(x.strip()) > 15]


def evaluate_parts(visited: list, report: str, sections: list) -> dict:
    쌍 = sorted({tuple(v) for v in visited})
    읽기시도 = [d for _, d in 쌍]
    읽은 = set(읽기시도)

    문장 = 문장들(report)
    근거붙은 = [s for s in 문장 if 인용들(s)]
    인용 = 인용들(report)
    쓰임 = Counter(인용)
    층 = Counter(LANG.get(c, "?") for c in 인용)
    무근거절 = [sec["절"] for sec in sections if not 인용들(sec["본문"])]

    return {
        "문장수": len(문장), "근거붙은문장": len(근거붙은),
        "근거율": round(100 * len(근거붙은) / max(len(문장), 1), 1),
        "허위인용": sorted(set(인용) - 읽은),
        "무근거절": 무근거절,
        "읽은문서": len(읽은), "읽고안쓴": sorted(읽은 - set(쓰임)),
        "인용편중": round(100 * max(쓰임.values()) / sum(쓰임.values()), 1) if 쓰임 else 0.0,
        "중복률": round(100 * (1 - len(읽은) / len(읽기시도)), 1) if 읽기시도 else 0.0,
        "층별인용": {"영문위키": 층.get("en", 0), "한국어위키": 층.get("ko", 0), "최신뉴스": 층.get("news", 0)},
        "절수": len(sections), "보고서자수": len(report), "인용수": len(인용),
        "LLM호출": COST["calls"],
        "격리율": round(100 * COST["coord_chars"] / max(COST["sub_chars"] + COST["coord_chars"], 1), 1),
        "코디네이터글자": COST["coord_chars"], "서브에이전트글자": COST["sub_chars"],
    }


def 한줄(m: dict) -> str:
    경보 = f"허위 {len(m['허위인용'])} · 무근거절 {len(m['무근거절'])}"
    층 = m["층별인용"]
    return (f"근거율 {m['근거율']}% · 편중 {m['인용편중']}% · 중복 {m['중복률']}% · "
            f"읽은 {m['읽은문서']}건(안 쓴 {len(m['읽고안쓴'])}) · 인용 {m['인용수']}곳"
            f"(영{층['영문위키']}/한{층['한국어위키']}/뉴스{층['최신뉴스']}) · "
            f"{m['보고서자수']:,}자 · 격리율 {m['격리율']}% · LLM {m['LLM호출']}회 · [경보] {경보}")
