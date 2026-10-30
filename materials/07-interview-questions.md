# 07. 口試常見問題與參考答案

> 上機考之外，教授常會針對你寫的程式追問。下面的問題由淺入深，
> 先自己回答，再展開參考答案。能用**自己的話**、並且**連結到你寫的程式**說明，比背答案重要。

---

## A. TCP 基礎

<details>
<summary><b>A1. TCP 和 UDP 的差別？各舉一個適合的應用。</b></summary>

TCP 是連線導向、可靠、依序的 byte stream，有流量控制與壅塞控制；UDP 是無連線的 datagram，
不保證送達與順序，但延遲低、標頭小、保留訊息邊界。
TCP 適合不能掉資料的情境（網頁、檔案傳輸、SSH）；UDP 適合即時性比完整性重要的情境
（視訊通話、線上遊戲、DNS 查詢）。另外 QUIC (HTTP/3) 是在 UDP 上自己實作可靠傳輸，
以避免 TCP 的 head-of-line blocking 與握手延遲。
</details>

<details>
<summary><b>A2. 為什麼 TCP 需要三次握手？兩次不行嗎？</b></summary>

1. 雙方都要讓對方知道自己的初始序號 (ISN)，並確認對方收到了。SYN 要被 ACK、對方的 SYN 也要被 ACK，
   中間的 ACK 和 SYN 可以合併，所以最少三次。
2. 防止歷史連線：如果一個很久以前的 SYN 延遲抵達，兩次握手的 server 會直接建立連線並配置資源；
   三次握手時 client 會發現這不是它要的連線而回 RST。
</details>

<details>
<summary><b>A3. TIME_WAIT 是什麼？為什麼要等 2MSL？會造成什麼問題？</b></summary>

主動關閉的一方在送出最後一個 ACK 後進入 TIME_WAIT，等待 2 倍的 Maximum Segment Lifetime。
原因：(1) 最後的 ACK 可能遺失，對方會重送 FIN，要能再回 ACK；
(2) 讓這條連線殘留在網路中的舊封包全部消失，避免干擾之後使用相同四元組的新連線。
問題：server 重啟時 bind 會失敗 (`EADDRINUSE`)，解法是 `SO_REUSEADDR`；
大量短連線的 client 可能耗盡 ephemeral port，解法是連線重用 (keep-alive / connection pool)。
在我寫的 P1 中，judge 先關掉 server，所以 TIME_WAIT 出現在 server 端，不設 SO_REUSEADDR 就無法立刻重啟。
</details>

<details>
<summary><b>A4. 什麼是「黏包」？怎麼解決？</b></summary>

TCP 是 byte stream，不保留 send 的邊界，接收端一次 recv 可能拿到多則訊息、或半則訊息。
這不是 TCP 的 bug，而是應用層要自己定義訊息邊界。常見方法：固定長度、分隔符號（如 `\n`，我的 P3）、
長度前綴（我的 P2：4-byte big-endian 長度 + payload）。接收端要維護 buffer，湊滿一則才處理。
</details>

<details>
<summary><b>A5. 流量控制和壅塞控制有什麼不同？</b></summary>

流量控制是避免**接收端**被淹沒：接收端在 ACK 中告知剩餘的 receive window，傳送端不能超過。
壅塞控制是避免**網路**被淹沒：傳送端根據遺失或延遲推測網路狀況，調整 congestion window
（slow start、AIMD、CUBIC、BBR）。實際能送的量是兩個 window 的較小值。
</details>

<details>
<summary><b>A6. 如果網路線突然被拔掉，連線兩端會發生什麼事？</b></summary>

不會有任何 FIN 或 RST，兩端都不知道。如果有一方在送資料，會不斷重傳直到逾時（Linux 預設約 15 分鐘）
然後回報 `ETIMEDOUT`；如果雙方都沒在送資料，連線可以「半開」永遠存在。
解法：TCP keepalive (`SO_KEEPALIVE`，預設 2 小時才開始探測)、或應用層 heartbeat + idle timeout（我的 P4）。
</details>

---

## B. Socket API

<details>
<summary><b>B1. 說明 server 端從 socket() 到 close() 的流程，accept 回傳的是什麼？</b></summary>

`socket` 建立 → `setsockopt(SO_REUSEADDR)` → `bind` 綁定位址 → `listen` 進入 LISTEN 狀態 →
`accept` 取出已完成握手的連線 → `recv`/`send` → `close`。
`accept` 回傳一個**新的** fd 代表這條連線，原本的 listening socket 不變，繼續接受其他連線。
</details>

<details>
<summary><b>B2. listen 的 backlog 參數是什麼意思？</b></summary>

已完成三次握手、但還沒被 `accept()` 取走的連線佇列上限（Linux 上，另外還有一個 SYN queue）。
佇列滿了之後，新的 SYN 會被丟掉，client 會重試。server `accept` 太慢時就會發生。
</details>

<details>
<summary><b>B3. 為什麼要 htons？忘記會怎樣？</b></summary>

網路協定規定使用 big-endian，而 x86/ARM 通常是 little-endian。`sin_port` 必須是 network byte order。
忘記的話 port 會被位元組對調，例如 9000 (0x2328) 會變成 10275 (0x2823)，server 監聽在錯的 port，
client 連線時得到 Connection refused。這正是 P1 server.c 裡的 bug，我是用 strace / ss 看到實際的 port 才發現的。
</details>

<details>
<summary><b>B4. recv 回傳 0 代表什麼？如果沒處理會怎樣？</b></summary>

代表對方已經關閉寫入方向（送了 FIN），之後不會再有資料。不處理的話，每次 recv 都會立刻回傳 0，
程式變成無窮迴圈、CPU 100%，而且 iterative server 永遠不會去 accept 下一個 client——P1 的另一個 bug。
</details>

<details>
<summary><b>B5. send 回傳成功代表對方收到了嗎？什麼時候 send 會只送出一部分？</b></summary>

不代表。send 成功只表示資料被複製進 kernel 的 send buffer。
send buffer 空間不足（對方讀太慢、網路慢）、被 signal 打斷、或 non-blocking 模式下，都可能只送出一部分，
所以要用迴圈（`send_all` / Python 的 `sendall`）。要確認對方「處理完」，必須在應用層協定設計回應（例如 P4 的 response）。
</details>

<details>
<summary><b>B6. SIGPIPE 是什麼？server 為什麼要處理它？</b></summary>

對已被對方關閉（收到 RST）的連線寫入時，kernel 會送 SIGPIPE，預設動作是終止 process。
server 如果不處理，任何一個 client 異常斷線都可能讓整個 server 死掉。
解法是 `signal(SIGPIPE, SIG_IGN)` 或 send 時加 `MSG_NOSIGNAL`，讓 send 改為回傳 `EPIPE`。
</details>

<details>
<summary><b>B7. SO_REUSEADDR 和 SO_REUSEPORT 的差別？</b></summary>

`SO_REUSEADDR`：允許 bind 一個還有 TIME_WAIT 連線的位址，主要用於 server 重啟。
`SO_REUSEPORT`（Linux 3.9+）：允許多個 socket 同時 bind 並 listen 同一個 port，kernel 會把連線分散給它們，
用於多 process 的負載平衡（例如 nginx 的 `reuseport`）。
</details>

---

## C. 併發與系統設計

<details>
<summary><b>C1. 要讓 server 同時服務多個 client，有哪些方法？</b></summary>

(1) fork 每條連線一個 process；(2) 每條連線一個 thread（我的 P4）；(3) thread pool；
(4) I/O multiplexing：select/poll/epoll + non-blocking socket，單執行緒處理所有連線（我的 P3）；
(5) 以上的組合，例如多個 worker process，每個跑一個 epoll event loop。
thread/process 模型好寫但連線數多時資源消耗大；event-driven 擴充性好但程式需要拆成狀態機。
</details>

<details>
<summary><b>C2. select、poll、epoll 的差別？</b></summary>

select 用 bitmap 傳 fd 集合，有 FD_SETSIZE (1024) 上限，每次呼叫都要複製整個集合並線性掃描；
poll 改用陣列，沒有數量上限，但仍是 O(n)；
epoll 先用 `epoll_ctl` 註冊，kernel 內部維護 ready list，`epoll_wait` 只回傳 ready 的 fd，
複雜度與 ready 的數量成正比，適合大量連線但只有少數活躍的情境。
epoll 還支援 edge-triggered 模式，只在狀態改變時通知一次，需要讀到 EAGAIN 為止。
</details>

<details>
<summary><b>C3. 你的聊天室為什麼需要 outbuf？為什麼不能直接 sendall？</b></summary>

socket 是 non-blocking 的，send buffer 滿了 sendall 會丟出 BlockingIOError，而且不知道送了多少。
如果改成 blocking，一個不讀資料的 client 會讓 sendall 卡住，整個單執行緒 server 的所有人都卡住。
所以要把資料放進每個 client 的 outbuf，註冊 EVENT_WRITE，等 socket 可寫時再送；送完要取消 EVENT_WRITE，
否則因為 socket 幾乎永遠可寫，select 會一直立刻返回造成 busy loop。
</details>

<details>
<summary><b>C4. 如果有一個 client 連上聊天室但從不讀資料，會發生什麼事？</b></summary>

它的 TCP receive window 會變成 0，server 送不出去，資料會一直累積在 server 端它的 outbuf，
記憶體無限增長，最後拖垮整個 server（slow consumer 問題）。
解法：設定 outbuf 上限，超過就斷線或丟棄訊息；或設定寫入逾時。
</details>

<details>
<summary><b>C5. 什麼是 race condition？你的 KV server 怎麼避免？為什麼 Python 有 GIL 還需要鎖？</b></summary>

多個 thread 同時存取共享資料、且至少一個在寫入時，結果取決於執行順序。
INCR 是讀-改-寫三步驟，兩條 thread 交錯執行會造成 lost update。
我用一把所有 thread 共用的 `threading.Lock` 保護整個讀-改-寫。
原本的 bug 是 `with threading.Lock():`，每次都建立新鎖，等於沒有鎖。
GIL 只保證同一時間只有一條 thread 執行 bytecode，但 thread 可能在兩個 bytecode 之間被切換，
而且遇到 I/O（sleep、磁碟）時 GIL 會被釋放，所以複合操作仍然需要鎖。
</details>

<details>
<summary><b>C6. thread-per-connection 在一萬個連線時會遇到什麼問題？</b></summary>

每條 thread 都有自己的 stack（Linux 預設保留 8 MB 虛擬位址空間），大量 thread 會耗盡記憶體與 thread 數量上限；
context switch 的成本隨 thread 數增加；而且大部分連線其實是閒置的，thread 只是在等待。
這就是 C10K 問題，解法是 event-driven（epoll）+ 少量 worker thread，或使用 coroutine（asyncio、Go goroutine）。
</details>

<details>
<summary><b>C7. 你的 KV server 收到不合法的 JSON 時繼續服務，但 length 太大時直接斷線，為什麼？</b></summary>

JSON 錯誤時，整則訊息已經按照 length 完整讀完，串流仍然對齊，下一個 header 位置是正確的，可以繼續。
length 太大時我們沒有讀 payload（也不應該讀），之後的 bytes 已經無法判斷邊界，串流錯位，只能斷線。
另外 length 上限本身是防禦：沒有上限的話，攻擊者送 `FF FF FF FF` 就能讓 server 嘗試配置 4 GiB。
</details>

---

## D. 延伸思考（沒有標準答案）

1. 如果要讓 P3 的聊天室支援 10 台 server 組成的叢集，使用者連到不同台也能互相聊天，你會怎麼設計？
2. P4 的資料都在記憶體裡，server 重啟就不見了。要怎麼做持久化？寫入順序和 crash 時的一致性要怎麼考慮？
3. 如果要在 P2 的協定上加入加密，你會自己設計還是用 TLS？為什麼？
4. HTTP/1.1 的 keep-alive、HTTP/2 的 multiplexing、HTTP/3 的 QUIC，各自想解決 TCP 的什麼問題？
5. judge 是怎麼測出你的程式有沒有正確處理「半包」的？如果要你出一題 judge，你會怎麼測 P3 的 slow consumer 問題？
