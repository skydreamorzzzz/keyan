"""LLM 客户端：DeepSeek official API 优先，Anthropic 兼容接口 fallback。"""
import json, os, time, threading
from concurrent.futures import ThreadPoolExecutor
import httpx
from pilot import config

_lock = threading.Lock()

def runtime_config():
    """Return inference provenance fields used by experiment cache keys."""
    if os.environ.get("DEEPSEEK_API_KEY"):
        return {
            "provider": "DeepSeek",
            "backend": "deepseek_openai_compatible",
            "base_url": os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            "requested_model": os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            "effective_model": None,
            "model_version": None,
            "temperature": config.LLM_TEMPERATURE,
            "max_tokens": config.LLM_MAX_TOKENS,
            "thinking_mode": False,
        }
    if config.LLM_BASE_URL and config.LLM_API_KEY:
        return {
            "provider": "DeepSeek",
            "backend": "anthropic_compatible",
            "base_url": config.LLM_BASE_URL,
            "requested_model": config.LLM_MODEL,
            "effective_model": None,
            "model_version": None,
            "temperature": config.LLM_TEMPERATURE,
            "max_tokens": config.LLM_MAX_TOKENS,
            "thinking_mode": False,
        }
    return {
        "provider": "DeepSeek",
        "backend": "unconfigured",
        "base_url": config.LLM_BASE_URL,
        "requested_model": config.LLM_MODEL,
        "effective_model": None,
        "model_version": None,
        "temperature": config.LLM_TEMPERATURE,
        "max_tokens": config.LLM_MAX_TOKENS,
        "thinking_mode": False,
    }

def _extract_text(data):
    parts = []
    for c in data.get("content", []):
        if c.get("type") == "text":
            parts.append(c.get("text", ""))
    return "\n".join(parts).strip()

def _with_response_runtime(base_runtime, data):
    runtime = dict(base_runtime)
    response_model = data.get("model")
    runtime["response_model"] = response_model
    runtime["effective_model"] = response_model or runtime.get("requested_model")
    runtime["model_version"] = data.get("system_fingerprint") or data.get("model_version")
    runtime["system_fingerprint"] = data.get("system_fingerprint")
    return runtime

def _call_anthropic_compatible(messages, max_tokens, temperature, timeout, return_metadata=False):
    cfg = runtime_config()
    url = config.LLM_BASE_URL + "/v1/messages"
    headers = {
        "x-api-key": config.LLM_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": config.LLM_MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
        "thinking": {"type": "disabled"},
    }
    r = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    if r.status_code == 200:
        data = r.json()
        text = _extract_text(data)
        if return_metadata:
            runtime = _with_response_runtime(cfg, data)
            runtime["endpoint"] = url
            runtime["max_tokens"] = max_tokens
            runtime["temperature"] = temperature
            return {"text": text, "runtime": runtime}
        return text
    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")

def _call_deepseek(messages, max_tokens, temperature, timeout, return_metadata=False, response_format=None):
    cfg = runtime_config()
    url = cfg["base_url"] + "/chat/completions"
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    chat_messages = []
    for msg in messages:
        if msg.get("role") == "system":
            chat_messages.append({"role": "system", "content": msg.get("content", "")})
        else:
            chat_messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    headers = {
        "authorization": f"Bearer {api_key}",
        "content-type": "application/json",
    }
    payload = {
        "model": cfg["requested_model"],
        "messages": chat_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "thinking": {"type": "disabled"},
    }
    if response_format is not None:
        payload["response_format"] = response_format
    r = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    if r.status_code == 200:
        try:
            data = r.json()
        except Exception as e:
            raise RuntimeError(f"Failed to parse JSON response: {e}. Response text: {r.text[:500]}")
        choice = data["choices"][0]
        message = choice.get("message", {})
        text = message.get("content", "").strip()
        if not text:
            finish_reason = choice.get("finish_reason")
            message_keys = sorted(message.keys())
            raise RuntimeError(
                f"DeepSeek returned empty content; finish_reason={finish_reason}; "
                f"message_keys={message_keys}"
            )
        if return_metadata:
            runtime = _with_response_runtime(cfg, data)
            runtime["endpoint"] = url
            runtime["max_tokens"] = max_tokens
            runtime["temperature"] = temperature
            return {"text": text, "runtime": runtime}
        return text
    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")

def call_once_with_metadata(messages, max_tokens=None, temperature=None, timeout=180, response_format=None):
    max_tokens = max_tokens or config.LLM_MAX_TOKENS
    temperature = config.LLM_TEMPERATURE if temperature is None else temperature
    last_err = None
    for attempt in range(config.LLM_MAX_RETRIES):
        try:
            if os.environ.get("DEEPSEEK_API_KEY"):
                return _call_deepseek(
                    messages,
                    max_tokens,
                    temperature,
                    timeout,
                    return_metadata=True,
                    response_format=response_format,
                )
            if config.LLM_BASE_URL and config.LLM_API_KEY:
                return _call_anthropic_compatible(messages, max_tokens, temperature, timeout, return_metadata=True)
            raise RuntimeError("no LLM backend configured")
        except Exception as e:
            last_err = str(e)
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"LLM call failed after retries: {last_err}")

def call_once(messages, max_tokens=None, temperature=None, timeout=180, response_format=None):
    return call_once_with_metadata(
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
        response_format=response_format,
    )["text"]

class CachedLLM:
    """带磁盘缓存的 LLM 包装：key -> output，失败重试。缓存文件按 key 前缀分片。"""

    def __init__(self, cache_path):
        self.cache_path = cache_path
        self.cache = {}
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        if os.path.exists(cache_path):
            for line in open(cache_path):
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        self.cache[rec["key"]] = rec["out"]
                    except Exception:
                        pass

    def _save(self, key, out):
        with _lock:
            with open(self.cache_path, "a") as f:
                f.write(json.dumps({"key": key, "out": out}, ensure_ascii=False) + "\n")

    def call(self, key, messages, **kw):
        if key in self.cache:
            return self.cache[key]
        out = call_once(messages, **kw)
        self.cache[key] = out
        self._save(key, out)
        return out

    def run_batch(self, items):
        """items: list[(key, messages, kwargs)]，并发执行，返回 {key: output}。"""
        results = {}
        def work(item):
            key, messages, kw = item
            return key, self.call(key, messages, **(kw or {}))
        with ThreadPoolExecutor(max_workers=config.LLM_CONCURRENCY) as ex:
            for key, out in ex.map(work, items):
                results[key] = out
        return results
