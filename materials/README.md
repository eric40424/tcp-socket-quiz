# 教材

建議依序閱讀，每章最後都有練習題。標示的題號代表這一章是那一題的必備知識。

| 章節 | 內容 | 對應題目 |
|------|------|---------|
| [01. TCP 基礎觀念](01-tcp-fundamentals.md) | 分層、TCP vs UDP、byte stream、三次握手、四次揮手、TIME_WAIT、流量控制、Nagle | 全部 |
| [02. Berkeley Socket API (C)](02-socket-api-c.md) | socket/bind/listen/accept/connect、byte order、send_all、SIGPIPE、fork | P1 |
| [03. Python socket](03-python-socket.md) | C ↔ Python 對照、sendall、timeout、例外階層、bytes/str、struct | P2 ~ P4 |
| [04. 訊息邊界 Framing](04-message-framing.md) | 黏包/半包、分隔符號、長度前綴、串流錯位 | P2、P3、P4 |
| [05. 併發模型](05-concurrency-models.md) | iterative/fork/thread/event-driven、select/epoll、selectors、race condition、lock、asyncio | P3、P4 |
| [06. 除錯工具](06-debugging-tools.md) | nc、ss、tcpdump、Wireshark、strace、錯誤訊息速查 | 全部 |
| [07. 口試題](07-interview-questions.md) | 由淺入深的口試題與參考答案 | 考後 |

## 時間分配建議（準備期 1 週）

| 天 | 內容 |
|----|------|
| 1 | 01 + 06，裝好 Docker 環境，用 `nc` 玩一玩 |
| 2 | 02，自己從零寫一個 C echo server（不看 P1） |
| 3 | 03 + 04，用 Python 寫 length-prefix 的 client/server |
| 4 | 05，用 selectors 寫一個 echo server，再用 thread 寫一次 |
| 5 | 模擬考：計時 4 小時寫 `EXAM.md` |
| 6 | 對照 `solutions/README.md` 檢討，做每章的練習題 |
| 7 | 07 口試題，練習用自己的話說出來 |
