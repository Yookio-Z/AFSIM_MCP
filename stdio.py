import json
import sys
from pathlib import Path

base_dir = Path(__file__).resolve().parent.parent
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

try:
    from ..core.server import JsonRpcError, MCPServer
except ImportError:
    from core.server import JsonRpcError, MCPServer


def write_response(req_id, *, result=None, error=None):
    payload = {"jsonrpc": "2.0", "id": req_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    server = MCPServer()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request = None
        req_id = None

        try:
            request = json.loads(line)
        except Exception as exc:
            write_response(None, error={"code": -32700, "message": "Parse error", "data": {"error": str(exc)}})
            continue

        try:
            if isinstance(request, dict):
                req_id = request.get("id")
            response = server.handle_request(request)
            if req_id is not None:
                write_response(req_id, result=response)
        except JsonRpcError as exc:
            if req_id is not None:
                write_response(req_id, error=exc.to_error_obj())
        except Exception as exc:
            if req_id is not None:
                write_response(
                    req_id,
                    error={"code": -32000, "message": "Internal error", "data": {"error": str(exc)}},
                )


if __name__ == "__main__":
    main()
