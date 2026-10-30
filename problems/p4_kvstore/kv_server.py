"""P4: Thread-per-connection 的 Key-Value server

用法: python kv_server.py [--port 9100] [--idle-timeout 30]

通訊格式: 使用 P2 的 length-prefixed JSON (../p2_framing/protocol.py)，
一個 request 對應一個 response，同一條連線可以連續送很多個 request。

Request / Response:
  {"op": "SET",  "key": k, "value": v}  → {"ok": true}
  {"op": "GET",  "key": k}              → {"ok": true, "value": v}
                                          key 不存在 → {"ok": false, "error": "..."}
  {"op": "DEL",  "key": k}              → {"ok": true, "deleted": true/false}
  {"op": "INCR", "key": k, "by": n}     → {"ok": true, "value": 新的值}
                                          by 省略時為 1；key 不存在時視為 0；
                                          原本的值不是整數 → {"ok": false, "error": "..."}
  其他 op / 內容不是合法 JSON           → {"ok": false, "error": "..."}，而且連線「不可以」被關掉

其他需求:
  - 要能同時服務多個 client
  - client 超過 idle_timeout 秒沒有送任何資料 → server 主動關閉連線
  - 多個 client 同時 INCR 同一個 key，結果必須正確

請完成 TODO 4-A ~ 4-C。注意：這個檔案除了 TODO 之外還藏有 1 個 bug。
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
        with threading.Lock():
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

    # TODO 4-C: 實作 DEL

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
        # TODO 4-B:
        #   1. 設定閒置逾時：idle_timeout 秒內沒收到任何資料就結束 (提示: settimeout)
        #   2. 迴圈: recv_json → handle_request → send_json
        #   3. 對方正常斷線 (recv_json 回傳 None) → 結束
        #   4. 收到的內容不是合法 JSON (ValueError) → 回傳錯誤 response，連線「不要」斷
        #   5. 逾時 / ConnectionError / ProtocolError / 其他 OSError → 結束
        #   提示: socket.timeout 是 OSError 的子類別，except 的順序很重要
        pass


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
            # TODO 4-A: 現在一次只能服務一個 client。改成每個連線開一條 daemon thread
            handle_conn(store, conn, addr, idle_timeout)


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
