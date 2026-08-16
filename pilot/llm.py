"""LLM 客户端：Anthropic 兼容接口优先，DeepSeek official API fallback。"""
import json, os, time, threading
from concurrent.futures import ThreadPoolExecutor
import httpx
import config

_lock = threading.Lock()

def runtime_config():
    """Return inference provenance fields used by experiment cache keys."""
    if config.LLM_BASE_URL and config.LLM_API_KEY:
        return {
            "backend": "anthropic_compatible",
            "base_url": config.LLM_BASE_URL,
            "model": config.LLM_MODEL,
            "temperature": config.LLM_TEMPERATURE,
            "max_tokens": config.LLM_MAX_TOKENS,
            "thinking": "disabled",
        }
    if os.environ.get("DEEPSEEK_API_KEY"):
        return {
            "backend": "deepseek_openai_compatible",
            "base_url": os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            "temperature": config.LLM_TEMPERATURE,
            "max_tokens": config.LLM_MAX_TOKENS,
            "thinking": "not_supported",
        }
    return {
        "backend": "unconfigured",
        "base_url": config.LLM_BASE_URL,
        "model": config.LLM_MODEL,
        "temperature": config.LLM_TEMPERATURE,
        "max_tokens": config.LLM_MAX_TOKENS,
        "thinking": "disabled",
    }

def _extract_text(data):
    parts = []
    for c in data.get("content", []):
        if c.get("type") == "text":
            parts.append(c.get("text", ""))
    return "\n".join(parts).strip()

def _call_anthropic_compatible(messages, max_tokens, temperature, timeout):
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
        return _extract_text(r.json())
    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")

def _call_deepseek(messages, max_tokens, temperature, timeout):
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
        "model": cfg["model"],
        "messages": chat_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    r = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    if r.status_code == 200:
        data = r.json()
        return data["choices"][0]["message"].get("content", "").strip()
    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")

def call_once(messages, max_tokens=None, temperature=None, timeout=180):
    max_tokens = max_tokens or config.LLM_MAX_TOKENS
    temperature = config.LLM_TEMPERATURE if temperature is None else temperature
    last_err = None
    for attempt in range(config.LLM_MAX_RETRIES):
        try:
            if config.LLM_BASE_URL and config.LLM_API_KEY:
                return _call_anthropic_compatible(messages, max_tokens, temperature, timeout)
            if os.environ.get("DEEPSEEK_API_KEY"):
                return _call_deepseek(messages, max_tokens, temperature, timeout)
            raise RuntimeError("no LLM backend configured")
        except Exception as e:
            last_err = str(e)
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"LLM call failed after retries: {last_err}")

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
