"""
JSON-RPC protocol for the Gateway WebSocket control plane.
Inspired by OpenClaw's protocol layer (src/gateway/protocol/).
"""
from pydantic import BaseModel
from typing import Any, Optional
import uuid


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[str] = None
    method: str
    params: dict = {}


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[dict] = None


class JsonRpcEvent(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: dict = {}


def success_response(request_id: Optional[str], result: Any) -> dict:
    return JsonRpcResponse(id=request_id, result=result).model_dump(exclude_none=True)


def error_response(request_id: Optional[str], code: int, message: str, data: Any = None) -> dict:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return JsonRpcResponse(id=request_id, error=err).model_dump(exclude_none=True)


def event_message(method: str, params: dict) -> dict:
    return JsonRpcEvent(method=method, params=params).model_dump()


# Standard error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
AUTH_REQUIRED = -32000
AUTH_FAILED = -32001
