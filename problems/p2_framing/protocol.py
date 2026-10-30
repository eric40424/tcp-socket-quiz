"""P2: Length-prefixed message framing

每一則訊息在線上的格式:

    +-------------------+---------------------------+
    | length (4 bytes)  | payload (length bytes)    |
    | uint32 big-endian |                           |
    +-------------------+---------------------------+

length 是 payload 的長度 (不含 header 本身)，使用 network byte order (big-endian)。
payload 可以是空的 (length = 0)。

請完成 TODO 2-A ~ 2-C。注意：這個檔案除了 TODO 之外還藏有 1 個 bug。
P4 會 import 這個模組，所以 P2 沒寫好，P4 也會跟著出問題。
"""
import json
import struct

HEADER = struct.Struct("I")  # 4-byte unsigned int
MAX_MSG_SIZE = 16 * 1024 * 1024  # 16 MiB


class ProtocolError(Exception):
    """對方送來不符合規格的資料。"""


def recv_exact(sock, n):
    """從 sock 剛好讀出 n 個 bytes 並回傳。

    - 不可以多讀 (多讀的資料屬於下一則訊息！)
    - 在讀滿之前連線就被關閉 → raise ConnectionError
    - n == 0 時回傳 b""
    """
    # TODO 2-A
    raise NotImplementedError("TODO 2-A")


def send_msg(sock, payload):
    """送出一則訊息 (header + payload)。payload 超過 MAX_MSG_SIZE → raise ProtocolError。"""
    # TODO 2-B
    raise NotImplementedError("TODO 2-B")


def recv_msg(sock):
    """收一則完整的訊息並回傳 payload (bytes)。

    - 對方在「訊息與訊息之間」正常關閉連線 → 回傳 None
    - 對方在訊息傳到一半時關閉連線      → raise ConnectionError
    - length 超過 MAX_MSG_SIZE           → raise ProtocolError (不要真的去讀那麼多資料)
    - 注意：空訊息 (length = 0) 要回傳 b""，不是 None
    """
    # TODO 2-C
    raise NotImplementedError("TODO 2-C")


def send_json(sock, obj):
    send_msg(sock, json.dumps(obj, ensure_ascii=False).encode("utf-8"))


def recv_json(sock):
    """收一則 JSON 訊息。連線正常結束回傳 None；內容不是合法 JSON 會 raise ValueError。"""
    payload = recv_msg(sock)
    if payload is None:
        return None
    return json.loads(payload.decode("utf-8"))
