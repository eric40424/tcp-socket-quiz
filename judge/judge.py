#!/usr/bin/env python3
"""TCP Socket 上機考 —— 自動評分程式 (Judge)

用法:
    python judge/judge.py                     # 評全部題目
    python judge/judge.py p2 p3               # 只評部分題目
    python judge/judge.py -v                  # 失敗時印出 server 的輸出
    python judge/judge.py --target solutions  # 評參考解答 (用來確認 judge 本身沒問題)

P1 (C) 需要 POSIX 環境與 gcc (Linux / macOS / WSL / Docker)，在 Windows 原生環境會被略過。
"""
import argparse
import collections
import contextlib
import importlib.util
import json
import os
import platform
import queue
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "problems"
VERBOSE = False

with contextlib.suppress(AttributeError):
    sys.stdout.reconfigure(errors="replace")


# =====================================================================
# 共用工具
# =====================================================================

class Skip(Exception):
    """這個測試在目前的環境無法執行。"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    """啟動一個待測 server 的 subprocess，並在背景收集它的輸出。"""

    def __init__(self, cmd, cwd=None):
        self.cmd = cmd
        self.log = collections.deque(maxlen=200)
        self._lines = queue.Queue()
        self.proc = subprocess.Popen(
            cmd, cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for raw in self.proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip("\n")
            self.log.append(line)
            self._lines.put(line)

    def output(self):
        return "\n".join(self.log)

    def wait_ready(self, timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                line = self._lines.get(timeout=0.1)
            except queue.Empty:
                if self.proc.poll() is not None:
                    time.sleep(0.1)  # 讓 _pump 把最後的輸出收完
                    raise AssertionError(
                        f"server 啟動失敗 (exit code {self.proc.returncode})\n"
                        f"--- server 輸出 ---\n{self.output()}"
                    )
                continue
            if "listening" in line.lower():
                return
        raise AssertionError(f"server 沒有在 {timeout}s 內印出 'listening'\n{self.output()}")

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()


_current_servers = []


@contextlib.contextmanager
def running(cmd, cwd=None):
    srv = Server(cmd, cwd=cwd)
    _current_servers.append(srv)
    try:
        srv.wait_ready()
        yield srv
    finally:
        srv.stop()


def connect(port, timeout=3.0):
    return socket.create_connection(("127.0.0.1", port), timeout=timeout)


def recv_n(sock, n, timeout=3.0, what=""):
    """剛好收 n bytes，逾時或連線中斷就判定失敗。"""
    buf = b""
    deadline = time.monotonic() + timeout
    while len(buf) < n:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"{what}預期收到 {n} bytes，逾時，只收到 {len(buf)} bytes: {buf[:120]!r}")
        sock.settimeout(remaining)
        try:
            chunk = sock.recv(min(n - len(buf), 1 << 20))
        except socket.timeout:
            continue
        except ConnectionError as e:
            raise AssertionError(f"{what}連線發生錯誤 ({e})，只收到 {len(buf)} bytes: {buf[:120]!r}")
        if not chunk:
            raise AssertionError(f"{what}連線被關閉，預期 {n} bytes，只收到 {len(buf)} bytes: {buf[:120]!r}")
        buf += chunk
    return buf


def expect(sock, expected, timeout=3.0, what=""):
    got = recv_n(sock, len(expected), timeout, what)
    if got != expected:
        raise AssertionError(f"{what}預期 {expected!r}，實際收到 {got!r}")


def expect_silence(sock, duration=0.3, what=""):
    sock.settimeout(duration)
    try:
        data = sock.recv(4096)
    except socket.timeout:
        return
    except ConnectionError:
        data = b""
    if data:
        raise AssertionError(f"{what}不應該收到任何資料，卻收到 {data!r}")
    raise AssertionError(f"{what}連線不應該被關閉")


def expect_eof(sock, timeout=3.0, what=""):
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"{what}預期連線被 server 關閉，但等了 {timeout}s 還沒關")
        sock.settimeout(remaining)
        try:
            if not sock.recv(4096):
                return
        except socket.timeout:
            continue
        except ConnectionError:
            return  # RST 也算被關閉


def background(fn, *args):
    """在 daemon thread 執行輔助工作 (例如對面那一端的送資料)。

    測試失敗、socket 被關掉後，這些 thread 常會跟著出錯；那些錯誤不是考生的問題，直接忽略。
    """
    def runner():
        with contextlib.suppress(Exception):
            fn(*args)

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    return t


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


# =====================================================================
# 測試註冊
# =====================================================================

PROBLEMS = collections.OrderedDict()


class Problem:
    def __init__(self, key, title):
        self.key = key
        self.title = title
        self.tests = []


def problem(key, title):
    PROBLEMS[key] = Problem(key, title)


def test(key, points, name, timeout=15):
    def deco(fn):
        PROBLEMS[key].tests.append((name, points, fn, timeout))
        return fn
    return deco


# =====================================================================
# P1: C echo server / client
# =====================================================================

problem("p1", "P1  C 語言 Echo Server / Client")
P1_BUILD = {"dir": None}


def p1_requirements():
    if os.name == "nt":
        raise Skip("P1 需要 POSIX socket，請在 Linux / WSL / Docker 執行")
    if shutil.which("gcc") is None:
        raise Skip("找不到 gcc")


def p1_bin(name):
    p1_requirements()
    if P1_BUILD["dir"] is None:
        raise AssertionError("server.c / client.c 沒有編譯成功，無法測試")
    return str(P1_BUILD["dir"] / name)


@test("p1", 3, "編譯 server.c 與 client.c (gcc -std=c99)")
def p1_compile():
    p1_requirements()
    out = Path(tempfile.mkdtemp(prefix="tcpquiz-p1-"))
    src = TARGET / "p1_echo"
    for name in ("server", "client"):
        r = subprocess.run(
            ["gcc", "-std=c99", "-Wall", "-Wextra", "-O2", "-o", str(out / name), str(src / f"{name}.c")],
            capture_output=True, text=True,
        )
        check(r.returncode == 0, f"{name}.c 編譯失敗:\n{r.stderr[-2000:]}")
    P1_BUILD["dir"] = out


@test("p1", 5, "基本 echo")
def p1_basic():
    port = free_port()
    with running([p1_bin("server"), str(port)]), connect(port) as c:
        c.sendall(b"hello, tcp\n")
        expect(c, b"hello, tcp\n")
        c.sendall("中文也可以\n".encode())
        expect(c, "中文也可以\n".encode())


@test("p1", 5, "1 MiB 大量資料 echo (partial send)", timeout=30)
def p1_large():
    port = free_port()
    payload = os.urandom(1 << 20)
    with running([p1_bin("server"), str(port)]), connect(port) as c:
        t = background(c.sendall, payload)
        got = recv_n(c, len(payload), timeout=20)
        t.join(5)
        check(got == payload, "收到的資料與送出的不一致")


@test("p1", 4, "第一個 client 離開後，能繼續服務下一個 client")
def p1_sequential():
    port = free_port()
    with running([p1_bin("server"), str(port)]):
        with connect(port) as a:
            a.sendall(b"first\n")
            expect(a, b"first\n", what="client A: ")
        time.sleep(0.2)
        with connect(port) as b:
            b.sendall(b"second\n")
            expect(b, b"second\n", what="client A 離開後 client B: ")


@test("p1", 3, "server 重啟後能立刻 bind 同一個 port (TIME_WAIT)")
def p1_restart():
    port = free_port()
    srv = Server([p1_bin("server"), str(port)])
    _current_servers.append(srv)
    try:
        srv.wait_ready()
        c = connect(port)
        c.sendall(b"x")
        expect(c, b"x")
    finally:
        srv.stop()  # server 端先關閉連線 → server 端的 port 會進入 TIME_WAIT
    time.sleep(0.2)
    c.close()
    time.sleep(0.3)
    with running([p1_bin("server"), str(port)]), connect(port) as d:
        d.sendall(b"again")
        expect(d, b"again")


def chunky_echo_server(lsock, chunk):
    """故意把資料切成很小的片段、慢慢回傳的 echo server。"""
    conn, _ = lsock.accept()
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    with conn:
        while True:
            data = conn.recv(65536)
            if not data:
                return
            for i in range(0, len(data), chunk):
                conn.sendall(data[i:i + chunk])
                time.sleep(0.003)


@test("p1", 5, "client 能正確處理分段抵達的資料", timeout=40)
def p1_client():
    client = p1_bin("client")
    lsock = socket.socket()
    lsock.bind(("127.0.0.1", 0))
    lsock.listen(1)
    port = lsock.getsockname()[1]
    background(chunky_echo_server, lsock, 7)
    data = (b"hello\n"
            b"TCP is a byte stream, not a message stream.\n"
            + b"x" * 3000 + b"\n"
            b"bye\n")
    try:
        r = subprocess.run([client, "127.0.0.1", str(port)], input=data, capture_output=True, timeout=30)
    finally:
        lsock.close()
    check(r.returncode == 0, f"client exit code = {r.returncode}\nstderr: {r.stderr.decode(errors='replace')[-500:]}")
    check(r.stdout == data,
          f"stdout 與預期不同 (預期 {len(data)} bytes，實際 {len(r.stdout)} bytes)\n"
          f"前 120 bytes: {r.stdout[:120]!r}")


# =====================================================================
# P2: Length-prefixed framing
# =====================================================================

problem("p2", "P2  Python 訊息邊界 (Length-prefixed Framing)")


def load_protocol():
    path = TARGET / "p2_framing" / "protocol.py"
    spec = importlib.util.spec_from_file_location(f"protocol_under_test_{time.monotonic_ns()}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def frame(payload):
    return struct.pack("!I", len(payload)) + payload


@contextlib.contextmanager
def pair():
    a, b = socket.socketpair()
    a.settimeout(5)
    b.settimeout(5)
    try:
        yield a, b
    finally:
        a.close()
        b.close()


def trickle(sock, data, delay=0.002):
    """一個 byte 一個 byte 慢慢送。"""
    for i in range(len(data)):
        sock.sendall(data[i:i + 1])
        time.sleep(delay)


@test("p2", 3, "send_msg 的線上格式 (big-endian header)")
def p2_wire_format():
    mod = load_protocol()
    with pair() as (a, b):
        mod.send_msg(a, b"hello")
        got = recv_n(b, 9)
        check(got == b"\x00\x00\x00\x05hello", f"預期 b'\\x00\\x00\\x00\\x05hello'，實際 {got!r}")
        mod.send_msg(a, b"")
        got = recv_n(b, 4)
        check(got == b"\x00\x00\x00\x00", f"空訊息預期 b'\\x00\\x00\\x00\\x00'，實際 {got!r}")


@test("p2", 3, "recv_exact 能拼湊分段資料，而且不會多讀")
def p2_recv_exact():
    mod = load_protocol()
    with pair() as (a, b):
        data = b"0123456789ABCDE"
        t = background(trickle, a, data)
        got = mod.recv_exact(b, 10)
        check(got == b"0123456789", f"recv_exact(10) 預期 b'0123456789'，實際 {got!r}")
        t.join(5)
        rest = recv_n(b, 5)
        check(rest == b"ABCDE", f"recv_exact 多讀了資料，剩下的應該是 b'ABCDE'，實際 {rest!r}")
        check(mod.recv_exact(b, 0) == b"", "recv_exact(sock, 0) 應回傳 b''")


@test("p2", 2, "recv_exact 在資料不足時連線關閉 → ConnectionError")
def p2_recv_exact_eof():
    mod = load_protocol()
    with pair() as (a, b):
        a.sendall(b"abc")
        a.close()
        try:
            mod.recv_exact(b, 10)
        except ConnectionError:
            return
        raise AssertionError("應該要 raise ConnectionError")


@test("p2", 3, "黏包：一次收到多則訊息 (含空訊息)")
def p2_sticky():
    mod = load_protocol()
    with pair() as (a, b):
        a.sendall(frame(b"one") + frame(b"two") + frame(b"") + frame("三".encode()))
        for want in (b"one", b"two", b"", "三".encode()):
            got = mod.recv_msg(b)
            check(got == want, f"預期 {want!r}，實際 {got!r}")


@test("p2", 3, "半包：訊息一個 byte 一個 byte 抵達")
def p2_trickle():
    mod = load_protocol()
    with pair() as (a, b):
        msg = "分段傳輸 split delivery".encode()
        t = background(trickle, a, frame(msg) + frame(b"next"))
        got = mod.recv_msg(b)
        check(got == msg, f"預期 {msg!r}，實際 {got!r}")
        got = mod.recv_msg(b)
        check(got == b"next", f"預期 b'next'，實際 {got!r}")
        t.join(5)


@test("p2", 2, "EOF 處理：訊息之間 → None；訊息中間 → ConnectionError")
def p2_eof():
    mod = load_protocol()
    with pair() as (a, b):
        a.sendall(frame(b"last"))
        a.close()
        check(mod.recv_msg(b) == b"last", "應先收到 b'last'")
        got = mod.recv_msg(b)
        check(got is None, f"連線在訊息之間正常關閉，應回傳 None，實際 {got!r}")
    with pair() as (a, b):
        a.sendall(frame(b"truncated message")[:10])
        a.close()
        try:
            mod.recv_msg(b)
        except ConnectionError:
            pass
        else:
            raise AssertionError("訊息傳到一半連線就關閉，應 raise ConnectionError")
    with pair() as (a, b):
        a.sendall(b"\x00\x00")  # header 只到一半
        a.close()
        try:
            mod.recv_msg(b)
        except ConnectionError:
            pass
        else:
            raise AssertionError("header 只收到 2 bytes 連線就關閉，應 raise ConnectionError")


@test("p2", 2, "length 過大 → ProtocolError")
def p2_too_large():
    mod = load_protocol()
    with pair() as (a, b):
        a.sendall(struct.pack("!I", mod.MAX_MSG_SIZE + 1))
        try:
            mod.recv_msg(b)
        except mod.ProtocolError:
            pass
        else:
            raise AssertionError("應 raise ProtocolError")
    with pair() as (a, b):
        try:
            mod.send_msg(a, b"\0" * (mod.MAX_MSG_SIZE + 1))
        except mod.ProtocolError:
            pass
        else:
            raise AssertionError("send_msg 送出過大的訊息應 raise ProtocolError")


@test("p2", 2, "5 MiB 訊息與 JSON 往返", timeout=30)
def p2_big_roundtrip():
    mod = load_protocol()
    with pair() as (a, b):
        a.settimeout(20)
        b.settimeout(20)
        big = os.urandom(5 << 20)
        t = background(mod.send_msg, a, big)
        got = mod.recv_msg(b)
        t.join(10)
        check(got == big, "5 MiB 訊息內容不一致")
        obj = {"op": "SET", "key": "名字", "value": [1, 2.5, None, {"ok": True}]}
        mod.send_json(a, obj)
        got = mod.recv_json(b)
        check(got == obj, f"JSON 往返不一致: {got!r}")


# =====================================================================
# P3: selectors chat server
# =====================================================================

problem("p3", "P3  Python 非阻塞多人聊天室 (selectors)")


def chat_cmd(port):
    return [sys.executable, "-u", str(TARGET / "p3_chat" / "chat_server.py"), str(port)]


def join(port, nick, settle=0.15):
    s = connect(port)
    s.sendall(nick.encode() + b"\n")
    time.sleep(settle)
    return s


def drain(sock, quiet=0.3):
    sock.settimeout(quiet)
    with contextlib.suppress(socket.timeout):
        while sock.recv(65536):
            pass


@test("p3", 4, "加入通知 (暱稱分段抵達)")
def p3_join():
    port = free_port()
    with running(chat_cmd(port)):
        alice = join(port, "alice")
        bob = connect(port)
        bob.sendall(b"bo")
        time.sleep(0.2)
        bob.sendall(b"b\n")
        expect(alice, b"* bob joined\n", what="alice: ")
        expect_silence(bob, what="bob (自己加入不該收到通知): ")
        alice.close()
        bob.close()


@test("p3", 4, "廣播給其他人、不含自己")
def p3_broadcast():
    port = free_port()
    with running(chat_cmd(port)):
        alice = join(port, "alice")
        bob = join(port, "bob")
        carol = join(port, "carol")
        drain(alice)
        drain(bob)
        alice.sendall(b"hello\n")
        expect(bob, b"[alice] hello\n", what="bob: ")
        expect(carol, b"[alice] hello\n", what="carol: ")
        expect_silence(alice, what="alice (自己): ")
        for s in (alice, bob, carol):
            s.close()


@test("p3", 4, "一次收到多行與不完整的行")
def p3_lines():
    port = free_port()
    with running(chat_cmd(port)):
        alice = join(port, "alice")
        bob = join(port, "bob")
        drain(alice)
        alice.sendall(b"line1\nline2\npar")
        expect(bob, b"[alice] line1\n[alice] line2\n", what="bob: ")
        expect_silence(bob, what="不完整的行 'par' 還不該被廣播: ")
        alice.sendall(b"tial\r\n")
        expect(bob, b"[alice] partial\n", what="bob: ")
        alice.close()
        bob.close()


@test("p3", 3, "/who 只回給自己")
def p3_who():
    port = free_port()
    with running(chat_cmd(port)):
        carol = join(port, "carol")
        alice = join(port, "alice")
        bob = join(port, "bob")
        drain(carol)
        drain(alice)
        bob.sendall(b"/who\n")
        expect(bob, b"* online: alice, bob, carol\n", what="bob: ")
        expect_silence(alice, what="alice: ")
        expect_silence(carol, what="carol: ")
        for s in (alice, bob, carol):
            s.close()


@test("p3", 3, "尚未設定暱稱的連線不會收到廣播")
def p3_no_nick():
    port = free_port()
    with running(chat_cmd(port)):
        alice = join(port, "alice")
        bob = join(port, "bob")
        drain(alice)
        dave = connect(port)
        time.sleep(0.2)
        alice.sendall(b"secret\n")
        expect(bob, b"[alice] secret\n", what="bob: ")
        expect_silence(dave, what="dave (還沒有暱稱): ")
        dave.sendall(b"dave\n")
        expect(alice, b"* dave joined\n", what="alice: ")
        for s in (alice, bob, dave):
            s.close()


@test("p3", 4, "/quit：server 關閉連線並通知其他人")
def p3_quit():
    port = free_port()
    with running(chat_cmd(port)):
        alice = join(port, "alice")
        bob = join(port, "bob")
        drain(alice)
        bob.sendall(b"/quit\nthis line must be ignored\n")
        expect_eof(bob, what="bob: ")
        expect(alice, b"* bob left\n", what="alice: ")
        expect_silence(alice, what="/quit 之後的內容不該被廣播: ")
        alice.sendall(b"still alive?\n")
        carol = join(port, "carol")
        expect(alice, b"* carol joined\n", what="alice: ")
        alice.close()
        carol.close()


@test("p3", 3, "client 直接斷線也要通知其他人")
def p3_abrupt():
    port = free_port()
    with running(chat_cmd(port)) as srv:
        alice = join(port, "alice")
        carol = join(port, "carol")
        drain(alice)
        carol.close()
        expect(alice, b"* carol left\n", what="alice: ")
        alice.sendall(b"/who\n")
        expect(alice, b"* online: alice\n", what="alice: ")
        check(srv.proc.poll() is None, "server 不應該結束")
        alice.close()


@test("p3", 3, "30 個 client 同時聊天", timeout=30)
def p3_many():
    port = free_port()
    n = 30
    with running(chat_cmd(port)):
        socks = [join(port, f"u{i:02d}", settle=0.02) for i in range(n)]
        time.sleep(0.3)
        for s in socks:
            drain(s)
        for i, s in enumerate(socks):
            s.sendall(f"msg from u{i:02d}\n".encode())
        for i, s in enumerate(socks):
            want = sorted(f"[u{j:02d}] msg from u{j:02d}\n" for j in range(n) if j != i)
            got = recv_n(s, sum(len(w) for w in want), timeout=10, what=f"u{i:02d}: ").decode()
            lines = sorted(got.splitlines(keepends=True))
            check(lines == want, f"u{i:02d} 收到的訊息不正確: {lines[:5]} ...")
        for s in socks:
            s.close()


def proc_cpu_seconds(pid):
    with open(f"/proc/{pid}/stat") as f:
        fields = f.read().rsplit(")", 1)[1].split()
    utime, stime = int(fields[11]), int(fields[12])
    return (utime + stime) / os.sysconf("SC_CLK_TCK")


@test("p3", 2, "閒置時不會空轉 (CPU 使用率)")
def p3_idle_cpu():
    if not os.path.exists("/proc/self/stat"):
        raise Skip("需要 Linux /proc")
    port = free_port()
    with running(chat_cmd(port)) as srv:
        alice = join(port, "alice")
        bob = join(port, "bob")
        expect(alice, b"* bob joined\n")
        time.sleep(0.2)
        before = proc_cpu_seconds(srv.proc.pid)
        time.sleep(1.5)
        used = proc_cpu_seconds(srv.proc.pid) - before
        check(used < 0.5, f"閒置 1.5 秒內用了 {used:.2f} 秒 CPU，select() 一直被喚醒 (EVENT_WRITE 沒取消？)")
        alice.close()
        bob.close()


# =====================================================================
# P4: threaded KV server
# =====================================================================

problem("p4", "P4  Python 多執行緒 Key-Value Server")


def kv_cmd(port, idle_timeout=30):
    return [sys.executable, "-u", str(TARGET / "p4_kvstore" / "kv_server.py"),
            "--port", str(port), "--idle-timeout", str(idle_timeout)]


def kv_raw(sock, payload, timeout=5.0):
    """judge 自己的 framing 實作 (不依賴考生的 protocol.py 來送 request)。"""
    sock.sendall(frame(payload))
    (length,) = struct.unpack("!I", recv_n(sock, 4, timeout, "response header: "))
    return json.loads(recv_n(sock, length, timeout, "response payload: ").decode())


def kv(sock, **req):
    return kv_raw(sock, json.dumps(req).encode())


@test("p4", 4, "SET / GET 基本操作")
def p4_basic():
    port = free_port()
    with running(kv_cmd(port)), connect(port) as c:
        r = kv(c, op="SET", key="a", value=1)
        check(r == {"ok": True}, f"SET 回應錯誤: {r}")
        r = kv(c, op="GET", key="a")
        check(r.get("ok") is True and r.get("value") == 1, f"GET 回應錯誤: {r}")
        value = {"名字": "成大", "list": [1, 2, 3], "nested": {"x": None}}
        kv(c, op="SET", key="obj", value=value)
        r = kv(c, op="GET", key="obj")
        check(r.get("value") == value, f"GET 複雜物件錯誤: {r}")


@test("p4", 3, "GET 不存在的 key 與 DEL")
def p4_missing_del():
    port = free_port()
    with running(kv_cmd(port)), connect(port) as c:
        r = kv(c, op="GET", key="nope")
        check(r.get("ok") is False and "error" in r, f"GET 不存在的 key 應回傳 ok=false: {r}")
        kv(c, op="SET", key="k", value="v")
        r = kv(c, op="DEL", key="k")
        check(r == {"ok": True, "deleted": True}, f"DEL 存在的 key: {r}")
        r = kv(c, op="DEL", key="k")
        check(r == {"ok": True, "deleted": False}, f"DEL 不存在的 key: {r}")
        r = kv(c, op="GET", key="k")
        check(r.get("ok") is False, f"DEL 之後 GET 應失敗: {r}")


@test("p4", 3, "錯誤的 request 不會中斷連線")
def p4_bad_request():
    port = free_port()
    with running(kv_cmd(port)), connect(port) as c:
        r = kv_raw(c, b"{this is not json")
        check(r.get("ok") is False, f"不合法的 JSON 應回傳 ok=false: {r}")
        r = kv_raw(c, b"\xff\xfe\xfd")
        check(r.get("ok") is False, f"不合法的 UTF-8 應回傳 ok=false: {r}")
        r = kv(c, op="FLY", key="a")
        check(r.get("ok") is False, f"未知的 op 應回傳 ok=false: {r}")
        kv(c, op="SET", key="a", value=42)
        r = kv(c, op="GET", key="a")
        check(r.get("value") == 42, f"錯誤之後連線應該還能正常使用: {r}")


@test("p4", 3, "INCR")
def p4_incr():
    port = free_port()
    with running(kv_cmd(port)), connect(port) as c:
        r = kv(c, op="INCR", key="n")
        check(r == {"ok": True, "value": 1}, f"INCR 不存在的 key 應得到 1: {r}")
        r = kv(c, op="INCR", key="n", by=5)
        check(r == {"ok": True, "value": 6}, f"INCR by=5 應得到 6: {r}")
        kv(c, op="SET", key="s", value="abc")
        r = kv(c, op="INCR", key="s")
        check(r.get("ok") is False, f"INCR 字串應回傳 ok=false: {r}")


@test("p4", 4, "同時服務多個 client")
def p4_concurrent_clients():
    port = free_port()
    with running(kv_cmd(port)):
        idle = connect(port)  # 連上但什麼都不送
        time.sleep(0.2)
        with connect(port) as c:
            try:
                r = kv_raw(c, b'{"op": "SET", "key": "x", "value": 1}', timeout=3.0)
            except AssertionError:
                raise AssertionError("另一個 client 還連著時，新的 client 得不到回應 (一次只能服務一個 client？)")
            check(r == {"ok": True}, f"SET 回應錯誤: {r}")
        r = kv(idle, op="GET", key="x")
        check(r.get("value") == 1, f"第一個 client 應該也能正常使用: {r}")
        idle.close()


@test("p4", 5, "10 個 client 同時 INCR 同一個 key (race condition)", timeout=90)
def p4_race():
    port = free_port()
    n_clients, n_ops = 10, 50
    errors = []
    with running(kv_cmd(port)):
        def worker():
            try:
                with connect(port, timeout=30) as c:
                    for _ in range(n_ops):
                        r = kv_raw(c, b'{"op": "INCR", "key": "counter"}', timeout=30)
                        if not r.get("ok"):
                            errors.append(r)
            except Exception as e:  # noqa: BLE001
                errors.append(repr(e))

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(n_clients)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(80)
        check(not errors, f"INCR 過程發生錯誤: {errors[:3]}")
        with connect(port) as c:
            r = kv(c, op="GET", key="counter")
        want = n_clients * n_ops
        check(r.get("value") == want, f"counter 應為 {want}，實際為 {r.get('value')} (lost update!)")


@test("p4", 3, "閒置逾時會被斷線，活躍的連線不受影響")
def p4_idle_timeout():
    port = free_port()
    with running(kv_cmd(port, idle_timeout=1)):
        idle = connect(port)
        active = connect(port)
        start = time.monotonic()
        while time.monotonic() - start < 1.8:
            r = kv(active, op="INCR", key="ping")
            check(r.get("ok") is True, f"活躍連線的 request 失敗: {r}")
            time.sleep(0.3)
        expect_eof(idle, timeout=2.0, what="閒置 1 秒以上的連線: ")
        r = kv(active, op="GET", key="ping")
        check(r.get("ok") is True, f"活躍的連線不應該被斷線: {r}")
        idle.close()
        active.close()


# =====================================================================
# 執行
# =====================================================================

def run_one(fn, timeout):
    result = {}

    def target():
        try:
            fn()
            result["status"] = "PASS"
        except Skip as e:
            result["status"] = "SKIP"
            result["msg"] = str(e)
        except AssertionError as e:
            result["status"] = "FAIL"
            result["msg"] = str(e)
        except Exception as e:  # noqa: BLE001
            result["status"] = "FAIL"
            result["msg"] = f"{type(e).__name__}: {e}"

    _current_servers.clear()
    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        result = {"status": "FAIL", "msg": f"逾時 (超過 {timeout}s，可能卡在 blocking 的 recv/accept)"}
    servers = list(_current_servers)
    for srv in servers:
        srv.stop()
    if VERBOSE and result["status"] == "FAIL" and servers:
        result["msg"] += "\n--- server 輸出 ---\n" + "\n".join(s.output() for s in servers)
    return result


def main():
    global TARGET, VERBOSE
    parser = argparse.ArgumentParser(description="TCP Socket 上機考 Judge")
    parser.add_argument("problems", nargs="*", help="要評分的題目 (p1 p2 p3 p4)，預設全部")
    parser.add_argument("--target", default="problems", help="要評分的資料夾 (預設 problems)")
    parser.add_argument("-v", "--verbose", action="store_true", help="失敗時印出 server 輸出")
    args = parser.parse_args()

    TARGET = (ROOT / args.target).resolve()
    VERBOSE = args.verbose
    selected = args.problems or list(PROBLEMS)
    for key in selected:
        if key not in PROBLEMS:
            parser.error(f"未知的題目: {key}")

    print(f"Target : {TARGET}")
    print(f"Python : {platform.python_version()} on {platform.system()}")
    print()

    t0 = time.monotonic()
    total = earned = skipped = 0
    summary = []
    for key in selected:
        prob = PROBLEMS[key]
        p_total = sum(t[1] for t in prob.tests)
        p_earned = 0
        print(f"== {prob.title} ({p_total} 分) ==")
        for name, points, fn, timeout in prob.tests:
            r = run_one(fn, timeout)
            status = r["status"]
            if status == "PASS":
                p_earned += points
            elif status == "SKIP":
                skipped += points
            print(f"  [{status}] {name:<46} {points if status == 'PASS' else 0:>2}/{points}")
            if r.get("msg"):
                for line in r["msg"].splitlines()[:40]:
                    print(f"         {line}")
        print(f"  小計: {p_earned}/{p_total}\n")
        summary.append((prob.title, p_earned, p_total))
        total += p_total
        earned += p_earned

    print("=" * 60)
    for title, e, t in summary:
        print(f"  {title:<44} {e:>3}/{t}")
    print(f"  {'總分':<44} {earned:>3}/{total}")
    if skipped:
        print(f"  (有 {skipped} 分的測試因環境限制被略過)")
    print(f"  耗時 {time.monotonic() - t0:.1f}s")
    sys.stdout.flush()
    # 逾時的測試可能留下卡住的 daemon thread；直接結束 process，
    # 避免 Python 在 interpreter finalization 時處理它們而崩潰
    os._exit(0)


if __name__ == "__main__":
    main()
