from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import random
import socket
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .config import Settings


class VisionModel:
    def __init__(self, settings: Settings) -> None:
        if not settings.api_key or not settings.model:
            raise ValueError("请配置 ER_LLM_API_KEY 和 ER_LLM_MODEL。")
        self.settings = settings
        self.model_requests = 0
        self.cache_hits = 0

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        images: list[Path],
    ) -> dict[str, Any]:
        content: list[dict[str, Any]] = [
            {"type": "text", "text": user_prompt}
        ]
        for image in images:
            mime = mimetypes.guess_type(image.name)[0] or "image/png"
            encoded = base64.b64encode(image.read_bytes()).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime};base64,{encoded}",
                        "detail": "high",
                    },
                }
            )
        payload = {
            "model": self.settings.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
        }
        key = hashlib.sha256(
            json.dumps(
                payload, ensure_ascii=False, sort_keys=True
            ).encode("utf-8")
        ).hexdigest()
        cache_path = (
            Path(self.settings.response_cache_dir).expanduser()
            / f"{key}.json"
        )
        if cache_path.is_file():
            self.cache_hits += 1
            return json.loads(cache_path.read_text(encoding="utf-8"))
        request = urllib.request.Request(
            self.settings.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
                "Connection": "close",
            },
            method="POST",
        )
        self.model_requests += 1
        response = self._send(request)
        parsed = _parse_response(response)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(parsed, ensure_ascii=False), encoding="utf-8"
        )
        return parsed

    def _send(
        self, request: urllib.request.Request
    ) -> dict[str, Any]:
        attempts = max(1, self.settings.http_retries + 1)
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(
                    request, timeout=self.settings.request_timeout
                ) as response:
                    return json.loads(response.read())
            except (
                urllib.error.URLError,
                ssl.SSLError,
                TimeoutError,
                ConnectionError,
                socket.timeout,
            ) as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(
                        min(8.0, 0.8 * (2**attempt))
                        + random.uniform(0, 0.3)
                    )
        raise RuntimeError(
            f"模型请求失败（{attempts} 次）: {last_error}"
        ) from last_error


def _parse_response(payload: dict[str, Any]) -> dict[str, Any]:
    if "choices" not in payload:
        return payload
    content = (
        payload.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    if isinstance(content, list):
        content = "\n".join(
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict)
        )
    text = str(content).strip().lstrip("\ufeff")
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines.pop()
        text = "\n".join(lines)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("模型未返回有效 JSON。")
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise RuntimeError("模型 JSON 顶层必须是对象。")
    return parsed
