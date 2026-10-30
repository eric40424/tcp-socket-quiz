"""簡易聊天室 client (已完成，不需修改)，方便手動測試 chat_server.py。

用法: python chat_client.py [host] [port]
"""
import os
import socket
import sys
import threading


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 9000
    nick = input("nickname: ").strip()

    sock = socket.create_connection((host, port))
    sock.sendall((nick + "\n").encode("utf-8"))

    def reader():
        with sock.makefile("r", encoding="utf-8", errors="replace", newline="\n") as f:
            for line in f:
                print(line, end="", flush=True)
        print("[disconnected]")
        os._exit(0)

    threading.Thread(target=reader, daemon=True).start()

    try:
        for line in sys.stdin:
            sock.sendall(line.encode("utf-8"))
    except (KeyboardInterrupt, OSError):
        pass
    sock.close()


if __name__ == "__main__":
    main()
