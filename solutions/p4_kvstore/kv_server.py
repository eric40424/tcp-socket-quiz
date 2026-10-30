"""P4: Thread-per-connection 的 Key-Value server —— 參考解答

用法: python kv_server.py [--port 9100] [--idle-timeout 30]
通訊格式使用 P2 的 length-prefixed JSON (../p2_framing/protocol.py)。
"""
import argparse
import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "p2_framing"))
from protocol import ProtocolError, recv_json, send_json  # noqa: E402


class KVStore:
    def __init__(self):
        self.data = {}
        self.lock = threading.Lock()

    @staticmethod
    def _simulate_disk_latency():
        """模擬寫入磁碟的延遲 (請勿刪除)。"""
        time.sleep(0.0005)

    def get(self, key):
        with self.lock:
            return self.data[key]  # 不存在時 raise KeyError

    def set(self, key, value):
        with self.lock:
            self.data[key] = value

    def delete(self, key):
        with self.lock:
            if key in self.data:
                del self.data[key]
                return True
            return False

    def incr(self, key, by=1):
        # [BUG 修正] 必須用「同一把」鎖；threading.Lock() 每次都建立一把新的鎖，等於沒鎖
        with self.lock:
            cur = self.data.get(key, 0)
            if not isinstance(cur, int) or isinstance(cur, bool):
                raise TypeError("not an integer")
            self._simulate_disk_latency()
            self.data[key] = cur + by
            return cur + by


def error(msg):
    return {"ok": False, "error": msg}


def handle_request(store, req):
    if not isinstance(req, dict):
        return error("request must be a JSON object")
    op = req.get("op")
    key = req.get("key")
    if not isinstance(key, str):
        return error("missing key")

    if op == "GET":
        try:
            return {"ok": True, "value": store.get(key)}
        except KeyError:
            return error("not found")

    if op == "SET":
        if "value" not in req:
            return error("missing value")
        store.set(key, req["value"])
        return {"ok": True}

    # TODO 4-C
    if op == "DEL":
        return {"ok": True, "deleted": store.delete(key)}

    if op == "INCR":
        by = req.get("by", 1)
        if not isinstance(by, int) or isinstance(by, bool):
            return error("by must be an integer")
        try:
            return {"ok": True, "value": store.incr(key, by)}
        except TypeError:
            return error("not an integer")

    return error(f"unknown op: {op}")


def handle_conn(store, conn, addr, idle_timeout):
    """服務單一 client，直到對方斷線、閒置逾時或發生錯誤。"""
    with conn:
        # TODO 4-B
        conn.settimeout(idle_timeout)
        while True:
            try:
                req = recv_json(conn)
            except socket.timeout:  # 必須放在 OSError 前面 (它是 OSError 的子類別)
                break
            except ValueError:
                # 整則訊息已經完整讀完，只是內容不是 JSON → framing 沒壞，可以繼續服務
                resp = error("bad request: invalid JSON")
            except (ConnectionError, ProtocolError, OSError):
                break
            else:
                if req is None:
                    break
                resp = handle_request(store, req)
            try:
                send_json(conn, resp)
            except OSError:
                break


def serve(host, port, idle_timeout):
    store = KVStore()
    lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind((host, port))
    lsock.listen(128)
    print(f"kv server listening on {host}:{port}", flush=True)

    with lsock:
        while True:
            conn, addr = lsock.accept()
            # TODO 4-A
            t = threading.Thread(
                target=handle_conn, args=(store, conn, addr, idle_timeout), daemon=True
            )
            t.start()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9100)
    parser.add_argument("--idle-timeout", type=float, default=30.0)
    args = parser.parse_args()
    try:
        serve(args.host, args.port, args.idle_timeout)
    except KeyboardInterrupt:
        print("bye")


if __name__ == "__main__":
    main()
