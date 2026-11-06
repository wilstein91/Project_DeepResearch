"""정부의 공개 첨부 PDF를 분석용 캐시에 내려받습니다. AI 호출 없음."""
import hashlib
import json
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
URL = "https://www.mofe.go.kr/com/cmm/fms/FileDown.do?atchFileId=ATCH_000000000033083&fileSn=2"
folder = ROOT / "data" / ".cache" / "official-pdf"
folder.mkdir(parents=True, exist_ok=True)
response = requests.get(URL, timeout=45, headers={"User-Agent": "AiffelResearchCourse/1.0 (educational source verification)"})
response.raise_for_status()
if not response.content.startswith(b"%PDF") or len(response.content) > 10_000_000:
    raise ValueError("예상한 크기의 PDF 본문이 아닙니다.")
path = folder / "mofe-emergency-market-meeting-20261106.pdf"
path.write_bytes(response.content)
print(json.dumps({"path": str(path), "url": URL, "bytes": len(response.content),
                  "sha256": hashlib.sha256(response.content).hexdigest()}, ensure_ascii=False))
