"""LLM 呼び出しユーティリティ.

キャッシュはインメモリ dict + キューで管理。
extract() はスレッドセーフ。flush_cache() で一括書き込み。
"""

import hashlib
import json
import subprocess
import time
from collections import deque
from pathlib import Path

MODEL = "gemini-3-flash-preview"
GEMINI_CMD = ["gemini", "-y", "--output-format", "json", "--model", MODEL]
TIMEOUT = 600  # 10 minutes
MAX_RETRIES = 3

# インメモリキャッシュ + 書き込みキュー（モジュールレベル）
_memory_cache: dict[str, str] = {}
_write_queue: deque[tuple[str, str]] = deque()
_cache_loaded = False
_cache_file_ref: Path | None = None


def _cache_key(prompt: str) -> str:
    raw = f"{MODEL}\n{prompt}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _ensure_loaded(cache_file: Path) -> None:
    """ディスクキャッシュをインメモリに読み込む（初回のみ）."""
    global _cache_loaded, _cache_file_ref
    if _cache_loaded:
        return
    if cache_file.exists():
        _memory_cache.update(json.loads(cache_file.read_text()))
    _cache_file_ref = cache_file
    _cache_loaded = True


def _parse_response(stdout: str) -> str:
    """Gemini CLI の JSON 出力から response テキストを抽出."""
    data = json.loads(stdout)
    response = data.get("response", "")
    if not response:
        raise RuntimeError("Gemini CLI returned empty response")
    return response.strip()


def flush_cache() -> None:
    """キューに溜まったエントリをディスクに一括書き込み."""
    if not _write_queue or _cache_file_ref is None:
        return

    # ディスクから最新を読み直してマージ
    on_disk: dict[str, str] = {}
    if _cache_file_ref.exists():
        on_disk = json.loads(_cache_file_ref.read_text())

    while _write_queue:
        key, value = _write_queue.popleft()
        on_disk[key] = value

    _cache_file_ref.write_text(json.dumps(on_disk, ensure_ascii=False, indent=2) + "\n")


def extract(extraction_prompt: str, content: str, *, cache_file: Path) -> str:
    """Gemini CLI を呼び出してドキュメントを凝縮する."""
    _ensure_loaded(cache_file)

    full_prompt = f"{extraction_prompt}\n\n{content}"

    key = _cache_key(full_prompt)
    if key in _memory_cache:
        return _memory_cache[key]

    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            result = subprocess.run(
                [*GEMINI_CMD, full_prompt],
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
            )
            if result.returncode == 0:
                output = _parse_response(result.stdout)
                _memory_cache[key] = output
                _write_queue.append((key, output))
                return output
            last_err = RuntimeError(
                f"Gemini CLI failed (exit {result.returncode}): "
                f"{result.stderr[:500]}"
            )
        except subprocess.TimeoutExpired as e:
            last_err = e
        except json.JSONDecodeError as e:
            last_err = RuntimeError(f"Gemini CLI returned invalid JSON: {e}")

        if attempt < MAX_RETRIES - 1:
            time.sleep(2 ** attempt)

    raise last_err  # type: ignore[misc]
