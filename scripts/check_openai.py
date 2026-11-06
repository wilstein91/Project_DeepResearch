"""비밀키를 출력하지 않고 모델 목록 조회로 연결만 확인합니다."""
import json
from pathlib import Path

from dotenv import dotenv_values
from openai import OpenAI

root = Path(__file__).resolve().parents[1]
key = dotenv_values(root / ".env").get("OPENAI_API_KEY")
if not key:
    print(json.dumps({"key_configured": False, "connection_ok": False}))
    raise SystemExit(1)

try:
    client = OpenAI(api_key=key, base_url="https://api.openai.com/v1", timeout=20)
    available = {model.id for model in client.models.list().data}
    candidates = ["gpt-4o-mini", "gpt-5-mini", "gpt-6-luna", "gpt-6.1-terra", "gpt-6.1-sol"]
    result = {"key_configured": True, "connection_ok": True,
              "available_candidates": [model for model in candidates if model in available],
              "paid_generation_calls": 0}
    print(json.dumps(result))
    output = root / "output" / "model_availability.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
except Exception as error:
    # SDK의 오류 문자열에는 키 일부가 들어갈 수 있으므로 출력하지 않습니다.
    print(json.dumps({"key_configured": True, "connection_ok": False,
                      "error_type": type(error).__name__, "status": getattr(error, "status_code", None)}))
    raise SystemExit(1)
