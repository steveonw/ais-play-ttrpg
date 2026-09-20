"""Optional stateless Responses API transport; no tools or shared conversations."""
import json
import os
import urllib.error
import urllib.request


class ProviderError(RuntimeError):
    pass


class ResponsesProvider:
    ENDPOINT = "https://api.openai.com/v1/responses"

    def __init__(self, models, timeout=60, max_output_tokens=5000, api_key=None, opener=None, role_settings=None):
        self.models = models
        self.timeout = timeout
        self.max_output_tokens = max_output_tokens
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key: raise ProviderError("Set OPENAI_API_KEY locally to use API mode")
        if not models or any(not isinstance(v, str) or not v.strip() for v in models.values()):
            raise ProviderError("Configure a model for every role before API mode")
        self.opener = opener or urllib.request.urlopen
        self.role_settings = role_settings or {}

    def complete(self, packet):
        model = self.models.get(packet["agent_id"])
        if not model: raise ProviderError("No model configured for the requested role")
        # Never send the campaign, another agent's history or a previous_response_id.
        body = {
            "model": model, "store": False, "max_output_tokens": self.max_output_tokens,
            "input": [
                {"role": "system", "content": packet["instructions"]},
                {"role": "user", "content": json.dumps({k: v for k, v in packet.items() if k != "instructions"}, ensure_ascii=False)},
            ],
            "text": {"format": {"type": "json_schema", "name": "ttrpg_" + packet["operation"], "strict": True, "schema": packet["response_schema"]}},
        }
        settings = self.role_settings.get(packet["agent_id"], {})
        if settings.get("reasoning_effort"):
            body["reasoning"] = {"effort": settings["reasoning_effort"]}
        if settings.get("max_output_tokens"):
            body["max_output_tokens"] = settings["max_output_tokens"]
        request = urllib.request.Request(self.ENDPOINT, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.api_key}, method="POST")
        try:
            with self.opener(request, timeout=self.timeout) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000: raise ProviderError("Provider response exceeds size limit")
            result = json.loads(raw)
        except urllib.error.HTTPError as exc:
            # Do not persist provider error bodies or headers: they can contain secrets.
            raise ProviderError(f"Provider HTTP {exc.code}; check account, model and limits") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            raise ProviderError("Provider transport or JSON error; retry is bounded") from None
        if not isinstance(result, dict) or result.get("status") != "completed":
            raise ProviderError("Provider response was incomplete")
        fragments = []
        outputs = result.get("output", [])
        if not isinstance(outputs, list): raise ProviderError("Invalid provider output structure")
        for output in outputs:
            if not isinstance(output, dict): raise ProviderError("Invalid provider output structure")
            if output.get("type") != "message": continue
            contents = output.get("content", [])
            if not isinstance(contents, list): raise ProviderError("Invalid provider content structure")
            for content in contents:
                if not isinstance(content, dict): raise ProviderError("Invalid provider content structure")
                if content.get("type") == "refusal": raise ProviderError("Provider refused this request")
                if content.get("type") == "output_text":
                    value = content.get("text")
                    if not isinstance(value, str): raise ProviderError("Invalid provider text")
                    fragments.append(value)
        if not fragments: raise ProviderError("Provider returned no JSON text")
        try:
            answer = json.loads("".join(fragments))
        except ValueError:
            raise ProviderError("Provider returned invalid JSON") from None
        usage = result.get("usage", {})
        if not isinstance(usage, dict): usage = {}
        # Only known numeric fields cross into the audit log.
        usage = {k: v for k, v in usage.items() if k in ["input_tokens", "output_tokens", "total_tokens"] and type(v) is int and v >= 0}
        return answer, usage
