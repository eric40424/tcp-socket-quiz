# 01. TCP 基礎觀念

> 寫 socket 程式之前，要先知道 TCP 幫你做了什麼、**沒有**幫你做什麼。

## 1. 網路分層：socket 在哪一層？

```
 應用層   HTTP, SSH, 你自己定義的協定 (P2 的 length-prefix、P3 的聊天協定)
 ───────────────────────── ← socket API 就是這條線
 傳輸層   TCP, UDP          (作業系統 kernel 實作)
 網路層   IP                (負責「送到哪台主機」)
 鏈結層   Ethernet, Wi-Fi
```

socket 是作業系統提供給應用程式的介面。你呼叫 `send()`，資料只是被**複製到 kernel 的 send buffer**；
真正什麼時候、切成幾個封包送出去，是 kernel 的 TCP 決定的。

一條 TCP 連線由 **四元組** 唯一識別：`(來源 IP, 來源 port, 目的 IP, 目的 port)`。
所以一個 server 的 port 80 可以同時有很多條連線——它們的 client 端 IP 或 port 不同。

## 2. TCP vs UDP

| | TCP | UDP |
|---|-----|-----|
| 連線 | 需要先建立連線 (handshake) | 不需要 |
| 可靠性 | 保證送達、不重複、**依序** | 可能遺失、重複、亂序 |
| 資料單位 | **byte stream (沒有訊息邊界)** | datagram (有訊息邊界) |
| 流量控制 / 壅塞控制 | 有 | 沒有 |
| 標頭大小 | 20 ~ 60 bytes | 8 bytes |
| 典型應用 | HTTP/1.1、HTTP/2、SSH、資料庫 | DNS、影音串流、遊戲、QUIC (HTTP/3) |

### 最重要的一點：TCP 是 byte stream

```
sender:   send("hello")  send("world")
                   │
           (TCP 只保證 bytes 依序抵達)
                   ▼
receiver: recv() → "hel"
          recv() → "loworld"
```

TCP **不保留** `send()` 的邊界。一次 `send` 可能要多次 `recv` 才收完（**半包**），
多次 `send` 也可能一次 `recv` 就全部收到（**黏包**）。
「黏包」這個詞其實是誤解——TCP 本來就沒有「包」，只有 stream。
要區分訊息，必須由應用層自己定義邊界 → 見 [04-message-framing.md](04-message-framing.md)。

> P1 的 client、P2 整題、P3 的切行，考的都是這個觀念。

## 3. 三次握手 (3-way handshake)

```
   Client                               Server
     │                                    │  (LISTEN)
     │ ──────── SYN, seq=x ─────────────► │
(SYN_SENT)                                │
     │ ◄─── SYN+ACK, seq=y, ack=x+1 ───── │ (SYN_RCVD)
     │                                    │
     │ ──────── ACK, ack=y+1 ───────────► │
(ESTABLISHED)                       (ESTABLISHED)
```

對應到 socket API：
- server 呼叫 `listen()` 之後，kernel 就會自動回應握手；完成握手的連線會進入 **accept queue**
- `accept()` 只是從 accept queue 裡**拿出一條已經建好的連線**
- client 的 `connect()` 會在握手完成後返回
- `listen(fd, backlog)` 的 backlog 就是 accept queue 的長度上限

**為什麼是三次，不是兩次？**
1. 雙方都要確認「對方的初始序號 (ISN)」並且讓對方知道自己收到了——SYN 和 ACK 各需要一次確認，中間兩個可以合併，所以最少三次
2. 防止**已失效的舊 SYN** 突然抵達時建立錯誤連線：兩次握手的話，server 收到舊 SYN 就會直接建立連線、浪費資源

## 4. 四次揮手 (4-way close)

```
   Client (主動關閉)                       Server (被動關閉)
     │ ───────────── FIN ───────────────► │
(FIN_WAIT_1)                              │ (CLOSE_WAIT)  ← recv() 回傳 0
     │ ◄──────────── ACK ──────────────── │
(FIN_WAIT_2)                              │  (server 可能還有資料要送)
     │ ◄──────────── FIN ──────────────── │ (LAST_ACK)    ← server 呼叫 close()
(TIME_WAIT)                               │
     │ ───────────── ACK ───────────────► │ (CLOSED)
  等待 2MSL
(CLOSED)
```

- TCP 是**全雙工**的，兩個方向要各自關閉，所以 FIN/ACK 要兩組
- 收到 FIN 後，`recv()` 會回傳 **0**——這是「對方不會再送資料了」的唯一訊號
  （P1 的 bug：沒處理 `recv() == 0`）
- `shutdown(fd, SHUT_WR)` 可以只關閉「我→對方」的方向（half-close），仍然能繼續收資料

### TIME_WAIT

**主動關閉**的一方會進入 TIME_WAIT，等待 **2 MSL**（Maximum Segment Lifetime，Linux 上固定 60 秒）。

為什麼要等？
1. 最後一個 ACK 可能遺失，對方會重送 FIN，我們要還在才能再回 ACK
2. 讓這條連線在網路上殘留的舊封包全部消失，避免被同一個四元組的新連線誤收

**實務影響**：server 主動關閉連線後重啟，`bind()` 同一個 port 會失敗：
`bind: Address already in use` (`EADDRINUSE`)。
解法：在 `bind()` 前設定 `SO_REUSEADDR` → 見 [02-socket-api-c.md](02-socket-api-c.md)。
（P1 的 TODO 1-B，judge 會測）

### CLOSE_WAIT

被動關閉的一方收到 FIN 後進入 CLOSE_WAIT，直到**應用程式自己呼叫 `close()`**。
如果你在 `ss` 上看到大量 CLOSE_WAIT，幾乎都是**程式忘了 close**（fd leak）。

## 5. TCP 狀態圖 (簡化)

```
                           ┌──────────┐
                           │  CLOSED  │
                           └──────────┘
             listen() │                     │ connect() / 送 SYN
                      ▼                     ▼
                ┌──────────┐          ┌──────────┐
                │  LISTEN  │          │ SYN_SENT │
                └──────────┘          └──────────┘
    收 SYN/送 SYN+ACK │                     │ 收 SYN+ACK/送 ACK
                      ▼                     │
                ┌──────────┐                │
                │ SYN_RCVD │                │
                └──────────┘                │
               收 ACK │                     │
                      ▼                     ▼
                ┌────────────────────────────────┐
                │          ESTABLISHED           │
                └────────────────────────────────┘
       close()/送 FIN │                     │ 收 FIN/送 ACK
                      ▼                     ▼
                ┌──────────┐          ┌──────────┐
                │FIN_WAIT_1│          │CLOSE_WAIT│
                └──────────┘          └──────────┘
               收 ACK │                     │ close()/送 FIN
                      ▼                     ▼
                ┌──────────┐          ┌──────────┐
                │FIN_WAIT_2│          │ LAST_ACK │ ── 收 ACK ──► CLOSED
                └──────────┘          └──────────┘
        收 FIN/送 ACK │
                      ▼
                ┌──────────┐
                │TIME_WAIT │ ── 等待 2MSL ──► CLOSED
                └──────────┘
```

用 `ss -tan` 可以看到每條連線目前的狀態。

## 6. 可靠傳輸、流量控制與壅塞控制

| 機制 | 解決的問題 | 怎麼做 |
|------|-----------|--------|
| 序號 (seq) + 確認 (ack) | 遺失、重複、亂序 | 每個 byte 都有序號；收方回 ack 告訴對方「我收到第 N byte 之前的所有資料了」 |
| 重傳 (retransmission) | 遺失 | 逾時 (RTO) 或收到 3 個重複 ack (fast retransmit) 就重送 |
| 滑動視窗 / 流量控制 | **收方**處理不來 | 收方在 ack 中告知 receive window (剩多少 buffer)，送方不能超過 |
| 壅塞控制 | **網路**塞車 | slow start、congestion avoidance (AIMD)、CUBIC、BBR |

### 和 socket 程式的關係：buffer 會滿

```
[你的程式] send() → [send buffer] ──網路──► [receive buffer] → recv() [對方的程式]
```

- 對方不 `recv()` → 對方的 receive buffer 滿 → window = 0 → 你的 send buffer 也滿 →
  你的 **blocking `send()` 會卡住**，non-blocking `send()` 會回傳 `EAGAIN` / `BlockingIOError`
- 這就是為什麼 `send()` 可能只送出一部分（partial send），也是 P3 需要 outbuf 的原因
- 兩邊同時大量 send、都不 recv → **互相卡死 (deadlock)**。judge 測 1 MiB echo 時，
  就是用另一條 thread 送、主 thread 收來避免這個問題

## 7. Nagle 演算法與 Delayed ACK

- **Nagle**：如果還有沒被 ack 的小封包，就先把新的小資料攢起來，等 ack 回來再一起送。減少小封包數量
- **Delayed ACK**：收方不立刻回 ack，等一下（最多約 40ms~200ms），看能不能搭著回應資料一起送
- 兩者同時作用在「寫-寫-讀」模式時會產生 **~40ms 延遲**
- 對延遲敏感的程式（遊戲、RPC）會設定 `TCP_NODELAY` 關掉 Nagle
- 更好的作法：把要送的資料組好，**一次** `send()` 出去（P2 參考解答把 header + payload 串起來一起送，就是這個原因）

## 8. 自我檢查

1. 用一句話說明為什麼 TCP 會有「黏包」問題。
2. server 呼叫 `accept()` 之前，三次握手完成了嗎？
3. `recv()` 回傳 0、回傳 -1、阻塞住不回傳，分別代表什麼？
4. 誰會進入 TIME_WAIT？為什麼要等 2MSL？
5. 一台機器上看到 5,000 條 CLOSE_WAIT，最可能是什麼問題？
6. 為什麼 `send()` 回傳成功，不代表對方已經收到資料？
