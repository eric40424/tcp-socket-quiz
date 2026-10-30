# 05. 併發模型：如何同時服務多個 client

> P1 一次只能服務一個 client。P3 用單執行緒 + I/O multiplexing，P4 用多執行緒。
> 這一章比較各種作法，以及多執行緒帶來的 race condition。

## 1. 問題：blocking I/O

```python
conn, _ = lsock.accept()   # 卡在這裡等新連線
data = conn.recv(4096)     # 卡在這裡等這個 client 送資料
```

一條 thread 一次只能卡在一個地方。如果卡在 client A 的 `recv()`，client B 送來的資料就沒人處理。

## 2. 五種模型比較

| 模型 | 作法 | 優點 | 缺點 |
|------|------|------|------|
| Iterative | 一次一個 | 最簡單 | 完全不能併發 (P1) |
| Process per connection | `fork()` | 隔離性好，一個掛掉不影響其他 | process 很重；共享資料要 IPC |
| Thread per connection | `pthread_create` / `threading.Thread` | 程式好寫（每條連線就是一段 blocking 的流程）| 每條 thread 有自己的 stack (Linux 預設 8 MB 虛擬記憶體)；context switch；**共享資料要上鎖** (P4) |
| Thread pool | 固定 N 條 thread 從 queue 拿工作 | 限制資源用量 | 連線數 > N 時，閒置連線會佔住 thread |
| Event-driven / I/O multiplexing | `select` / `poll` / `epoll` + non-blocking | 單執行緒就能撐上萬條連線，沒有鎖的問題 | 程式要拆成 callback / 狀態機，比較難寫 (P3) |

現代高效能 server（nginx、Redis、Node.js、Go runtime、Python asyncio）幾乎都以 event-driven 為核心，
再搭配多個 worker 吃滿多核心。

## 3. I/O Multiplexing

核心想法：**問 kernel「這一堆 socket 裡，哪些現在可以讀/寫而不會阻塞？」**，只處理準備好的那些。

```
         ┌────────────── event loop ──────────────┐
         │                                        │
         ▼                                        │
   select([lsock, c1, c2, c3])  ← 阻塞在這裡，直到至少一個 ready
         │
         ├─ lsock 可讀  → accept()，把新連線加入監聽清單
         ├─ c2 可讀     → recv()，一定馬上有資料 (或 EOF)
         └─ c3 可寫     → send() 把 outbuf 的資料送出去
```

| 系統呼叫 | 特性 |
|---------|------|
| `select` | 最古老、可攜；fd 數量上限 (FD_SETSIZE，通常 1024)；每次 O(n) |
| `poll` | 沒有數量上限，但每次仍 O(n) |
| `epoll` (Linux) / `kqueue` (BSD/macOS) | 註冊一次、只回傳 ready 的 fd，O(ready)；C10K 的解法 |
| IOCP (Windows) | completion-based，模型不同 |

Python 的 `selectors.DefaultSelector` 會自動挑該平台最好的實作。

### 「可讀」代表什麼？

- listening socket 可讀 → 有新連線可以 `accept()`
- 一般 socket 可讀 → 有資料、**或對方關閉了**（此時 `recv()` 回傳 `b""`）、或發生錯誤

### 「可寫」代表什麼？

send buffer 有空間。**幾乎永遠成立**，所以只在有資料要送時才監聽 `EVENT_WRITE`，
送完就取消，否則 `select()` 每次都立刻返回 → busy loop、CPU 100%（P3 TODO 3-E）。

## 4. Python `selectors` 用法

```python
import selectors, socket

sel = selectors.DefaultSelector()

lsock = socket.socket()
lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
lsock.bind(("127.0.0.1", 9000))
lsock.listen()
lsock.setblocking(False)
sel.register(lsock, selectors.EVENT_READ, data=None)   # data 可以放任何東西

while True:
    for key, mask in sel.select(timeout=1.0):
        if key.data is None:                  # listening socket
            conn, addr = lsock.accept()
            conn.setblocking(False)
            sel.register(conn, selectors.EVENT_READ, data={"out": b""})
        else:
            conn, state = key.fileobj, key.data
            if mask & selectors.EVENT_READ:
                data = conn.recv(4096)
                if not data:
                    sel.unregister(conn)       # 先 unregister 再 close
                    conn.close()
                    continue
                state["out"] += data          # echo：放進 outbuf
                sel.modify(conn, selectors.EVENT_READ | selectors.EVENT_WRITE, data=state)
            if mask & selectors.EVENT_WRITE:
                n = conn.send(state["out"])   # non-blocking：可能只送出一部分
                state["out"] = state["out"][n:]
                if not state["out"]:
                    sel.modify(conn, selectors.EVENT_READ, data=state)
```

### Non-blocking 的三個鐵則

1. **每條連線要有自己的 input buffer**：資料可能只來一半（半包）
2. **每條連線要有自己的 output buffer**：`send()` 可能只送出一部分
3. **handler 裡絕對不能有 blocking 呼叫**：一個 `time.sleep(1)` 或 `sendall()` 就會讓所有 client 一起卡住

### 慢速 client 問題

如果某個 client 一直不 `recv()`，它的 outbuf 會無限增長。實務上要設上限，超過就斷線。
（EXAM.md 加分思考題 2）

## 5. Race Condition 與 Lock

多條 thread 共享資料時，「讀 → 改 → 寫回」不是一個不可分割的動作：

```python
# 兩條 thread 同時執行 counter += 1
cur = data["counter"]        # A 讀到 0        B 讀到 0
data["counter"] = cur + 1    # A 寫入 1        B 寫入 1   ← A 的更新消失了
```

這叫 **lost update**。解法是用 **mutex (互斥鎖)** 把臨界區段 (critical section) 保護起來：

```python
lock = threading.Lock()          # ← 所有 thread 共用「同一把」鎖

def incr(key):
    with lock:                   # 同一時間只有一條 thread 能進來
        cur = data.get(key, 0)
        data[key] = cur + 1
```

### P4 的 bug

```python
def incr(self, key, by=1):
    with threading.Lock():       # ✘ 每次都建立一把「新的」鎖
```

每條 thread 都拿到一把只有自己有的鎖，當然每次都能馬上拿到 → 等於沒鎖。
**鎖必須是共享的**才有意義。

### 「Python 有 GIL，所以不用鎖？」—— 錯

GIL 只保證**一次只有一條 thread 執行 Python bytecode**，但 thread 可以在任兩個 bytecode 之間被切換。
`counter += 1` 是好幾個 bytecode（LOAD、ADD、STORE），中間可能被切走。
加上 I/O（如 P4 的 `_simulate_disk_latency`）時 GIL 會被釋放，race 幾乎必定發生。
（而 Python 3.13 起還有可以關掉 GIL 的 free-threaded build。）

### 常見的鎖相關問題

| 問題 | 說明 | 預防 |
|------|------|------|
| Deadlock | A 拿著鎖 1 等鎖 2，B 拿著鎖 2 等鎖 1 | 固定上鎖順序；用 `with` 確保釋放 |
| 拿著鎖做 I/O | 在鎖裡 `sendall()`，一個慢 client 卡住所有人 | 鎖內只做記憶體操作 |
| 鎖的粒度太粗 | 一把全域鎖讓所有操作排隊 | lock striping、讀寫鎖 |
| 忘記鎖讀取 | 「只是讀而已」也可能讀到寫到一半的狀態 | 讀寫都要保護 |

### C 語言的對應 (pthread)

```c
#include <pthread.h>
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static long counter = 0;

void *worker(void *arg) {
    pthread_mutex_lock(&lock);
    counter++;
    pthread_mutex_unlock(&lock);
    return NULL;
}
/* 編譯時加 -pthread */
```

## 6. asyncio：另一種寫法

asyncio 是 event-driven 模型，但讓你用「看起來像 blocking」的方式寫程式：

```python
import asyncio

async def handle(reader, writer):
    while line := await reader.readline():   # await = 交出控制權給 event loop
        writer.write(line)
        await writer.drain()                 # 等 outbuf 降下來 (back-pressure)
    writer.close()
    await writer.wait_closed()

async def main():
    server = await asyncio.start_server(handle, "127.0.0.1", 9000)
    async with server:
        await server.serve_forever()

asyncio.run(main())
```

底層就是 selectors + 每條連線的 buffer，只是 asyncio 幫你管理好了。
親手寫過 P3，才會懂 `await writer.drain()` 在做什麼。

## 7. 練習

1. 用 `threading` 改寫 P3，比較程式碼長度與需要上鎖的地方
2. 用 asyncio 重寫 P3
3. 把 P4 的 `incr` 鎖拿掉，跑 judge 看看 counter 少了多少；再把 `_simulate_disk_latency` 也拿掉，再跑幾次
4. 寫一個 C 程式：兩條 pthread 各自把共享變數 +1 一百萬次，不加鎖印出結果，再加鎖比較
