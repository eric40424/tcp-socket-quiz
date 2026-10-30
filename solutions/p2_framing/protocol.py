"""P2: Length-prefixed message framing —— 參考解答

每一則訊息在線上的格式:

    +-------------------+---------------------------+
    | length (4 bytes)  | payload (length bytes)    |
    | uint32 big-endian |                           |
    +-------------------+---------------------------+
"""
import json
import struct

# [BUG 修正] "!" = network byte order (big-endian)、標準大小、無 padding
HEADER = struct.Struct("!I")
MAX_MSG_SIZE = 16 * 1024 * 1024  # 16 MiB


class ProtocolError(Exception):
    """對方送來不符合規格的資料。"""


def recv_exact(sock, n):
    """從 sock 剛好讀出 n 個 bytes。

    在讀滿之前連線就被關閉 → raise ConnectionError。
    """
    # TODO 2-A
    chunks = []
    remaining = n
    while remaining > 0:
        chunk = sock.recv(min(remaining, 65536))
        if not chunk:
            raise ConnectionError(
                f"connection closed with {remaining} of {n} bytes unread"
            )
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def send_msg(sock, payload):
    """送出一則訊息 (header + payload)。"""
    # TODO 2-B
    if len(payload) > MAX_MSG_SIZE:
        raise ProtocolError(f"message too large: {len(payload)} bytes")
    sock.sendall(HEADER.pack(len(payload)) + payload)


def recv_msg(sock):
    """收一則完整的訊息並回傳 payload (bytes)。

    - 對方在「訊息與訊息之間」正常關閉連線 → 回傳 None
    - 對方在訊息傳到一半時關閉連線      → raise ConnectionError
    - length 超過 MAX_MSG_SIZE           → raise ProtocolError
    """
    # TODO 2-C
    first = sock.recv(HEADER.size)
    if not first:
        return None
    header = first + recv_exact(sock, HEADER.size - len(first))
    (length,) = HEADER.unpack(header)
    if length > MAX_MSG_SIZE:
        raise ProtocolError(f"message too large: {length} bytes")
    return recv_exact(sock, length)


def send_json(sock, obj):
    send_msg(sock, json.dumps(obj, ensure_ascii=False).encode("utf-8"))


def recv_json(sock):
    """收一則 JSON 訊息。連線正常結束回傳 None；內容不是合法 JSON 會 raise ValueError。"""
    payload = recv_msg(sock)
    if payload is None:
        return None
    return json.loads(payload.decode("utf-8"))
