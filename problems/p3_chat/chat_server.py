"""P3: 單執行緒、非阻塞 (non-blocking) 的多人聊天室 server

用法: python chat_server.py [port]

協定 (純文字、UTF-8、每一行以 "\\n" 結尾):
  - client 連上後送出的「第一行」是暱稱，server 廣播 "* <nick> joined\\n" 給其他人
  - 之後每一行都是聊天訊息，server 廣播 "[<nick>] <訊息>\\n" 給「其他人」(不含自己)
  - "/who"  → 只回給自己: "* online: <暱稱依字母排序，以 ", " 分隔>\\n"
  - "/quit" → server 關閉這條連線，廣播 "* <nick> left\\n"
  - client 直接斷線 (或連線錯誤) 也要廣播 "* <nick> left\\n"
  - 還沒送出暱稱的連線不算在線上，不會收到任何廣播

限制: 只能用一條 thread，所有 socket 都必須是 non-blocking，用 selectors 做 I/O multiplexing。

請完成 TODO 3-A ~ 3-F。注意：這個檔案除了 TODO 之外還藏有 1 個 bug。
"""
import selectors
import socket
import sys

MAX_LINE = 64 * 1024


class Client:
    def __init__(self, sock, addr):
        self.sock = sock
        self.addr = addr
        self.inbuf = b""   # 收到但還沒湊成完整一行的資料
        self.outbuf = b""  # 要送出但還沒送出去的資料
        self.nick = None
        self.closed = False


class ChatServer:
    def __init__(self, host="127.0.0.1", port=9000):
        self.sel = selectors.DefaultSelector()
        self.clients = {}  # socket -> Client

        self.lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.lsock.bind((host, port))
        self.lsock.listen(128)
        self.lsock.setblocking(False)

        # TODO 3-A: 把 listening socket 註冊到 selector，只關心「可讀」事件，data 設為 None
        #           (serve_forever 用 key.data is None 來判斷這是 listening socket)

    def serve_forever(self):
        host, port = self.lsock.getsockname()
        print(f"chat server listening on {host}:{port}", flush=True)
        while True:
            for key, mask in self.sel.select(timeout=1.0):
                if key.data is None:
                    self._accept()
                    continue
                client = key.data
                if client.closed:
                    continue
                if mask & selectors.EVENT_READ:
                    self._on_readable(client)
                if mask & selectors.EVENT_WRITE and not client.closed:
                    self._on_writable(client)

    # ---------- 連線管理 ----------

    def _accept(self):
        # TODO 3-B: accept 新連線 → 設成 non-blocking → 建立 Client 物件 →
        #           存進 self.clients → 註冊到 selector (EVENT_READ, data=client)
        pass

    def _disconnect(self, client):
        if client.closed:
            return
        client.closed = True
        # TODO 3-F: 從 selector 取消註冊、從 self.clients 移除、關閉 socket；
        #           如果這個 client 已經有暱稱，廣播 "* <nick> left\n"

    # ---------- 讀 ----------

    def _on_readable(self, client):
        try:
            data = client.sock.recv(4096)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            data = b""
        if not data:
            self._disconnect(client)
            return

        client.inbuf += data
        # TODO 3-C: 從 client.inbuf 切出所有「完整」的行 (以 b"\n" 結尾)，
        #           把每一行 decode 成 str (不含 "\n") 後交給 self._handle_line(client, line)。
        #           - 不完整的最後一段要留在 inbuf，等下次資料進來再拼起來
        #           - _handle_line 可能會把連線關掉 (/quit)，關掉之後就不要再處理剩下的行

        if not client.closed and len(client.inbuf) > MAX_LINE:
            self._disconnect(client)

    def _handle_line(self, client, line):
        line = line.rstrip("\r")
        if client.nick is None:
            client.nick = line.strip() or "anonymous"
            self.broadcast(f"* {client.nick} joined\n", exclude=client)
            return
        if line == "/quit":
            self._disconnect(client)
            return
        if line == "/who":
            names = sorted(c.nick for c in self.clients.values() if c.nick is not None)
            self.send(client, f"* online: {', '.join(names)}\n")
            return
        self.broadcast(f"[{client.nick}] {line}\n", exclude=client)

    # ---------- 寫 ----------

    def broadcast(self, text, exclude=None):
        for c in list(self.clients.values()):
            self.send(c, text)

    def send(self, client, text):
        """把資料放進 outbuf，等 socket 可寫時再由 _on_writable 送出 (不可以在這裡直接 sendall)。"""
        if client.closed:
            return
        was_empty = not client.outbuf
        client.outbuf += text.encode("utf-8")
        # TODO 3-D: 如果 outbuf 原本是空的，要讓 selector 開始監聽這個 socket 的 EVENT_WRITE
        #           (同時保留 EVENT_READ)。提示: self.sel.modify(...)

    def _on_writable(self, client):
        try:
            n = client.sock.send(client.outbuf)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            self._disconnect(client)
            return
        client.outbuf = client.outbuf[n:]
        # TODO 3-E: outbuf 全部送完之後，要取消 EVENT_WRITE 的監聽，
        #           否則 socket 幾乎永遠「可寫」，select() 會一直醒來 → CPU 100%


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9000
    server = ChatServer(port=port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("bye")


if __name__ == "__main__":
    main()
