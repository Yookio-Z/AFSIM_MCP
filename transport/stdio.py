import json
import sys
from pathlib import Path

base_dir = Path(__file__).resolve().parent.parent
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

try:
    from ..core.server import MCPServer
except ImportError:
    from core.server import MCPServer


def main():
    server = MCPServer()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = server.handle_request(request)
            if "id" in request and request["id"] is not None:
                sys.stdout.write(
                    json.dumps(
                        {"jsonrpc": "2.0", "id": request["id"], "result": response},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                sys.stdout.flush()
        except Exception as exc:
            error = {"error": str(exc)}
            req_id = None
            try:
                req_id = request.get("id")
            except Exception:
                pass
            sys.stdout.write(
                json.dumps({"jsonrpc": "2.0", "id": req_id, "result": error}, ensure_ascii=False)
                + "\n"
            )
            sys.stdout.flush()


if __name__ == "__main__":
    main()
