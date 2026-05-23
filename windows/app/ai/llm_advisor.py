import json
from typing import Dict, List, Optional


class LLMAdvisor:
    """Optional LLM-based tuning advisor.

    Takes recent parameter history and asks an LLM (Claude/DeepSeek/etc.)
    for tuning suggestions. Results are shown to the user for confirmation;
    the advisor never applies changes automatically.
    """

    def __init__(self, api_key: str = "", model: str = "claude-sonnet-4-6"):
        self.api_key = api_key
        self.model = model

    def build_prompt(self,
                     target_param: str,
                     target_value: float,
                     current_params: Dict[str, float],
                     error_history: List[float],
                     action_history: List[str]) -> str:
        return f"""You are a PID tuning expert. Analyze this control system data and suggest adjustments.

Target: {target_param} = {target_value}
Current parameters: {json.dumps(current_params)}
Recent errors: {json.dumps(error_history[-20:])}
Recent actions: {json.dumps(action_history[-10:])}

Based on the error trend:
- If oscillating: suggest reducing kp, increasing ki
- If slow to reach target: suggest increasing kp
- If steady offset: suggest increasing ki
- If overshooting: suggest reducing kp, increasing kd

Respond in JSON: {{"analysis": "...", "suggestion": {{"param_name": new_value, ...}}, "confidence": 0.0-1.0}}"""

    async def get_suggestion(self,
                             target_param: str,
                             target_value: float,
                             current_params: Dict[str, float],
                             error_history: List[float],
                             action_history: List[str]) -> Optional[dict]:
        try:
            import aiohttp
        except ImportError:
            return None

        prompt = self.build_prompt(target_param, target_value, current_params,
                                   error_history, action_history)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 500,
                        "messages": [{"role": "user", "content": prompt}]
                    },
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        text = data["content"][0]["text"]
                        try:
                            return json.loads(text)
                        except json.JSONDecodeError:
                            return {"analysis": text, "suggestion": {}, "confidence": 0}
        except Exception:
            pass
        return None
