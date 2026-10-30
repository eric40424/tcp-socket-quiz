"""P3: 單執行緒、非阻塞 (non-blocking) 的多人聊天室 server —— 參考解答

用法: python chat_server.py [port]
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

        # TODO 3-A
        self.sel.register(self.lsock, selectors.EVENT_READ, data=None)

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
        # TODO 3-B
        try:
            sock, addr = self.lsock.accept()
        except (BlockingIOError, InterruptedError):
            return
        sock.setblocking(False)
        client = Client(sock, addr)
        self.clients[sock] = client
        self.sel.register(sock, selectors.EVENT_READ, data=client)

    def _disconnect(self, client):
        if client.closed:
            return
        client.closed = True
        # TODO 3-F
        self.sel.unregister(client.sock)
        del self.clients[client.sock]
        client.sock.close()
        if client.nick is not None:
            self.broadcast(f"* {client.nick} left\n")

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
        # TODO 3-C
        while b"\n" in client.inbuf and not client.closed:
            raw, client.inbuf = client.inbuf.split(b"\n", 1)
            self._handle_line(client, raw.decode("utf-8", errors="replace"))

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
        # [BUG 修正] 不送給自己，也不送給還沒設定暱稱的連線
        for c in list(self.clients.values()):
            if c is exclude or c.nick is None:
                continue
            self.send(c, text)

    def send(self, client, text):
        if client.closed:
            return
        was_empty = not client.outbuf
        client.outbuf += text.encode("utf-8")
        # TODO 3-D
        if was_empty:
            self.sel.modify(
                client.sock, selectors.EVENT_READ | selectors.EVENT_WRITE, data=client
            )

    def _on_writable(self, client):
        try:
            n = client.sock.send(client.outbuf)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            self._disconnect(client)
            return
        client.outbuf = client.outbuf[n:]
        # TODO 3-E
        if not client.outbuf:
            self.sel.modify(client.sock, selectors.EVENT_READ, data=client)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9000
    server = ChatServer(port=port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("bye")


if __name__ == "__main__":
    main()
