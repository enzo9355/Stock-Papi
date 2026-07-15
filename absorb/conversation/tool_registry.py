from __future__ import annotations

import concurrent.futures
import dataclasses
import json
import re
from collections.abc import Callable
from typing import Any

from absorb.conversation.errors import ToolRejected, ToolUnavailable
from absorb.conversation.policies import MAX_TOOL_RESULT_BYTES, TOOL_TIMEOUT_SECONDS
from absorb.conversation.schemas import AccessLevel, ToolResult


_SYMBOL = re.compile(r"^(?:TAIEX|[0-9]{4,5}|[A-Z][A-Z0-9.-]{0,9})$")
_ACCESS = {"public": 0, "authenticated": 1, "admin": 2}
_ARGUMENT_TYPES = {
    "market": "TW or US",
    "symbol": "canonical stock symbol",
    "symbols": "list of two canonical stock symbols",
    "sessions": "integer from 1 to 20",
    "limit": "integer from 1 to 10",
    "industry_id": "resolved industry name",
    "entity_type": "market, industry, or stock",
    "entity_id": "canonical entity identifier",
    "forecast_id": "64-character forecast identifier",
}


@dataclasses.dataclass(frozen=True)
class ToolSpec:
    name: str
    handler: Callable[..., dict[str, Any]]
    description: str = ""
    allowed_arguments: tuple[str, ...] = ()
    required_arguments: tuple[str, ...] = ()
    access: AccessLevel = "public"
    timeout_seconds: float = TOOL_TIMEOUT_SECONDS
    max_result_bytes: int = MAX_TOOL_RESULT_BYTES


class ToolRegistry:
    def __init__(self, specs=()):
        specs = tuple(specs)
        self._specs = {spec.name: spec for spec in specs}
        if len(self._specs) != len(specs):
            raise ValueError("duplicate tool name")

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))

    @property
    def catalog(self) -> tuple[dict[str, Any], ...]:
        return self.catalog_for("admin")

    def catalog_for(self, access: AccessLevel) -> tuple[dict[str, Any], ...]:
        if access not in _ACCESS:
            raise ValueError("invalid tool catalog access")
        return tuple(
            {
                "name": spec.name,
                "description": spec.description,
                "access": spec.access,
                "arguments": {
                    name: {"type": _ARGUMENT_TYPES.get(name, "validated value"), "required": name in spec.required_arguments}
                    for name in spec.allowed_arguments
                },
            }
            for spec in sorted(self._specs.values(), key=lambda item: item.name)
            if _ACCESS[spec.access] <= _ACCESS[access]
        )

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        principal_access: AccessLevel,
        allowed_entities: set[tuple[str, str]],
    ) -> ToolResult:
        spec = self._specs.get(name)
        if spec is None:
            raise ToolRejected("工具不在允許清單。")
        if principal_access not in _ACCESS or _ACCESS[principal_access] < _ACCESS[spec.access]:
            raise ToolRejected("此工具需要登入或更高權限。")
        validated = self._validate_arguments(spec, arguments, allowed_entities)
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="absorb-tool")
        future = executor.submit(spec.handler, **validated)
        try:
            data = future.result(timeout=spec.timeout_seconds)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise ToolUnavailable("資料工具逾時。") from exc
        except Exception as exc:
            raise ToolUnavailable("資料工具暫時無法使用。") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        if not isinstance(data, dict):
            raise ToolUnavailable("資料工具回傳格式不正確。")
        encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
        if len(encoded) > spec.max_result_bytes:
            raise ToolUnavailable("資料工具結果超過安全上限。")
        return ToolResult(name=name, ok=True, data=data)

    @staticmethod
    def _validate_arguments(spec, arguments, allowed_entities):
        if not isinstance(arguments, dict) or len(arguments) > 6:
            raise ToolRejected("工具參數格式不正確。")
        clean: dict[str, Any] = {}
        for key, value in arguments.items():
            if not isinstance(key, str) or re.fullmatch(r"[a-z_]{1,40}", key) is None:
                raise ToolRejected("工具參數名稱不正確。")
            if isinstance(value, str):
                value = value.strip()
                if len(value) > 120:
                    raise ToolRejected("工具參數過長。")
            elif isinstance(value, list):
                if len(value) > 5 or not all(isinstance(item, str) and len(item) <= 20 for item in value):
                    raise ToolRejected("工具清單參數不正確。")
            elif value is not None and not isinstance(value, (int, float, bool)):
                raise ToolRejected("工具參數型別不正確。")
            clean[key] = value
        if any(key not in spec.allowed_arguments for key in clean):
            raise ToolRejected("工具包含未允許參數。")
        if any(key not in clean for key in spec.required_arguments):
            raise ToolRejected("工具缺少必要參數。")
        market = clean.get("market")
        if market is not None and market not in {"TW", "US"}:
            raise ToolRejected("市場不在允許清單。")
        symbols = [clean["symbol"]] if "symbol" in clean else clean.get("symbols", [])
        for symbol in symbols:
            canonical = str(symbol).upper()
            if _SYMBOL.fullmatch(canonical) is None:
                raise ToolRejected("股票代碼格式不正確。")
            entity_market = market or ("TW" if canonical == "TAIEX" or canonical.isdigit() else "US")
            if (entity_market, canonical) not in allowed_entities:
                raise ToolRejected("股票代碼未由本次問題或對話上下文解析。")
        for key in ("sessions", "limit"):
            if key in clean and (isinstance(clean[key], bool) or not isinstance(clean[key], int)):
                raise ToolRejected("工具參數型別不正確。")
        if "sessions" in clean and not 1 <= clean["sessions"] <= 20:
            raise ToolRejected("查詢期數超出允許範圍。")
        if "limit" in clean and not 1 <= clean["limit"] <= 10:
            raise ToolRejected("結果筆數超出允許範圍。")
        industry_id = clean.get("industry_id")
        if industry_id is not None and (
            not isinstance(industry_id, str)
            or not industry_id
            or len(industry_id) > 80
            or ".." in industry_id
            or "/" in industry_id
            or "\\" in industry_id
        ):
            raise ToolRejected("產業識別格式不正確。")
        entity_type = clean.get("entity_type")
        if entity_type is not None and entity_type not in {"market", "industry", "stock"}:
            raise ToolRejected("實體類型不在允許清單。")
        entity_id = clean.get("entity_id")
        if entity_id is not None:
            if not isinstance(entity_id, str) or not entity_id:
                raise ToolRejected("實體識別格式不正確。")
            if entity_type in {"market", "stock"}:
                canonical = entity_id.upper()
                if _SYMBOL.fullmatch(canonical) is None:
                    raise ToolRejected("實體識別格式不正確。")
                entity_market = market or ("TW" if canonical == "TAIEX" or canonical.isdigit() else "US")
                if (entity_market, canonical) not in allowed_entities:
                    raise ToolRejected("實體未由本次問題或對話上下文解析。")
                clean["entity_id"] = canonical
            elif ".." in entity_id or "/" in entity_id or "\\" in entity_id or len(entity_id) > 80:
                raise ToolRejected("實體識別格式不正確。")
        forecast_id = clean.get("forecast_id")
        if forecast_id is not None and (
            not isinstance(forecast_id, str)
            or re.fullmatch(r"[0-9a-f]{64}", forecast_id) is None
        ):
            raise ToolRejected("forecast_id 格式不正確。")
        return clean
