"""LLM 客户端：Anthropic 兼容接口（DeepSeek 端点），并发 + 缓存可恢复。"""
import json, os, time, threading
from concurrent.futures import ThreadPoolExecutor
import httpx
import config

_lock = threading.Lock()

def _extract_text(data):
    parts = []
    for c in data.get("content", []):
        if c.get("type") == "text":
            parts.append(c.get("text", ""))
    return "\n".join(parts).strip()

def call_once(messages, max_tokens=None, temperature=None, timeout=180):
    url = config.LLM_BASE_URL + "/v1/messages"
    headers = {
        "x-api-key": config.LLM_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": config.LLM_MODEL,
        "max_tokens": max_tokens or config.LLM_MAX_TOKENS,
        "temperature": config.LLM_TEMPERATURE if temperature is None else temperature,
        "messages": messages,
        "thinking": {"type": "disabled"},   # 节省 token，输出确定性程序
    }
    last_err = None
    for attempt in range(config.LLM_MAX_RETRIES):
        try:
            r = httpx.post(url, headers=headers, json=payload, timeout=timeout)
            if r.status_code == 200:
                return _extract_text(r.json())
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
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
