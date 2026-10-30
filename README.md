# TCP Socket 上機考 (仿成大資工特選乙組形式)

參考 [2024 成大資工特選乙組上機考心得](https://emtech.cc/p/srecruit-ncku-quiz/) 的形式設計：
考生拿到一個**寫到一半、藏有 bug 的專案**，要補完 TODO、修好 bug，並用自動評分程式驗證。
原考題的主題是 ROS2，這份改成 **TCP Socket 程式設計**。

## 目錄結構

```
tcp-socket-quiz/
├── docs.html            ← 所有文件的網頁版 (雙擊用瀏覽器開啟)
├── EXAM.md              ← 試題本 (從這裡開始讀)
├── TROUBLESHOOTING.md   ← 環境問題排解 (WSL / Docker)
├── Dockerfile           ← Ubuntu 22.04 考試環境
├── scripts/
│   ├── setup-wsl-docker.sh  ← 在 WSL 裡安裝 Docker Engine 並 build image
│   └── build_docs.py        ← 把所有 .md 打包成 docs.html
├── docs/                ← docs.html 的範本與內嵌的 JS 函式庫 (marked、highlight.js)
├── problems/            ← 作答區 (只改這裡)
│   ├── p1_echo/         C:      echo server / client
│   ├── p2_framing/      Python: length-prefixed 訊息邊界
│   ├── p3_chat/         Python: selectors 非阻塞聊天室
│   └── p4_kvstore/      Python: 多執行緒 key-value server
├── judge/
│   └── judge.py         ← 自動評分程式
├── materials/           ← 教材 (考前讀)
└── solutions/           ← 參考解答與解析 (考完再看！)
```

## 瀏覽文件

直接用瀏覽器開啟 **`docs.html`**（不需要網路、不需要架 server）。
裡面整合了試題本、7 章教材與解答，有左側導覽、本頁目錄、全文搜尋（按 `/`）、程式碼上色與深色模式。
解答頁預設會鎖住，按下「我考完了」才會顯示。

修改任何 `.md` 之後，重新產生網頁：

```powershell
wsl -d Ubuntu-22.04 -- python3 /mnt/c/Users/feng_hsiang/tcp-socket-quiz/scripts/build_docs.py
```

## 快速開始

### 方法一：WSL2 + Docker (推薦，和考試環境一致，P1 需要)

本機已安裝好：WSL2 的 `Ubuntu-22.04`、Docker Engine、考試環境 image `tcp-quiz`。

**開始作答**

```powershell
# 1. PowerShell：進入 Ubuntu
wsl -d Ubuntu-22.04
```

```bash
# 2. Ubuntu：進入考試環境的 container (專案資料夾會掛載到 /exam)
cd /mnt/c/Users/feng_hsiang/tcp-socket-quiz
docker run --rm -it -v "$PWD:/exam" tcp-quiz

# 3. container 裡：評分
python3 judge/judge.py
```

- 程式碼可以直接在 Windows 上編輯 `problems\`（例如用 VS Code），存檔後 container 裡立刻看得到
- 不想進 container，也可以在 PowerShell 一行跑完評分：
  ```powershell
  wsl -d Ubuntu-22.04 -- docker run --rm -v /mnt/c/Users/feng_hsiang/tcp-socket-quiz:/exam tcp-quiz python3 judge/judge.py
  ```
- 修改了 `Dockerfile` 之後要重新 build：`docker build -t tcp-quiz .`
- WSL 的資源上限設定在 `C:\Users\feng_hsiang\.wslconfig`（目前 3GB RAM / 2 CPU）

**在新電腦上從頭安裝**

1. 用系統管理員身分開 PowerShell：`wsl --install -d Ubuntu-22.04`，然後重新開機
   （如果內建的 `wsl.exe` 不接受 `--install`，改用 `winget install Microsoft.WSL`）
2. 執行 `wsl -d Ubuntu-22.04 -- bash /mnt/c/Users/<你>/tcp-socket-quiz/scripts/setup-wsl-docker.sh`，
   它會安裝 Docker Engine、build image，並用參考解答驗證 judge（應為 100/100）
3. 執行 `wsl --shutdown` 讓設定生效

> 用安裝腳本裝完時預設是 root。要建立自己的帳號：
> `adduser <名字> && usermod -aG sudo,docker <名字> && printf '[user]\ndefault=<名字>\n' >> /etc/wsl.conf`，
> 再執行 `wsl --shutdown`。

遇到 `permission denied ... docker.sock`、`$PWD` 不知道填什麼、`wsl --install` 失敗等問題，請看
**[環境問題排解 (TROUBLESHOOTING.md)](TROUBLESHOOTING.md)**。

### 方法二：Linux / macOS / WSL

```bash
python3 judge/judge.py           # 評全部
python3 judge/judge.py p2        # 只評 P2
python3 judge/judge.py -v p3     # 失敗時顯示 server 輸出
```

### 方法三：Windows 原生 Python

P2 ~ P4 可以直接跑；P1 (C 的 POSIX socket) 會被略過。

```powershell
python judge\judge.py p2 p3 p4
```

## 建議流程

1. 考前：讀 `materials/`，順序是 `01` → `07`
2. 計時 4 小時，打開 `EXAM.md` 開始作答
3. 寫一段就跑一次 judge
4. 考完：對照 `solutions/README.md` 的解析，並試著回答 `materials/07-interview-questions.md` 的口試題

驗證 judge 本身：`python3 judge/judge.py --target solutions` 應該拿到 100 分
（Windows 原生環境只會有 73 分，因為 P1 與 Linux-only 測試被略過）。
