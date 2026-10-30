# 環境問題排解

> 安裝與使用 WSL2 + Docker 考試環境時實際遇到的問題與解法。
> 跟 socket 程式本身有關的錯誤（`Address already in use`、`Connection refused`…）請看
> [06. 除錯工具與常見錯誤](materials/06-debugging-tools.md)。

---

## 1. `docker run` 指令裡的 `$PWD` 要填什麼？

```bash
docker run --rm -it -v "$PWD:/exam" tcp-quiz
```

**什麼都不用填。** `$PWD` 是 shell 內建變數，會自動換成「目前所在的資料夾」。
所以執行前一定要先 `cd` 到專案資料夾：

```bash
cd /mnt/c/Users/<你的 Windows 帳號>/tcp-socket-quiz
docker run --rm -it -v "$PWD:/exam" tcp-quiz
```

| 部分 | 意思 |
|------|------|
| `--rm` | 離開後自動刪除 container |
| `-it` | 互動模式，可以在裡面打指令 |
| `-v "$PWD:/exam"` | 把本機目前的資料夾掛載到 container 裡的 `/exam` |
| `tcp-quiz` | 要使用的 image |
| （image 後面再接東西） | 會被當成「在 container 裡執行的指令」，執行完就離開 |

```bash
docker run --rm -it -v "$PWD:/exam" tcp-quiz pwd                     # 印出 /exam 就結束（可用來確認掛載）
docker run --rm -it -v "$PWD:/exam" tcp-quiz python3 judge/judge.py  # 直接評分
docker run --rm -it -v "$PWD:/exam" tcp-quiz                         # 進入 container 的 shell
```

### 進去之後 `ls` 是空的、找不到 `judge/`

執行 `docker run` 時不在專案資料夾，掛載到錯的地方了。離開後 `cd` 到專案資料夾重來，
或者直接寫完整路徑：

```bash
docker run --rm -it -v /mnt/c/Users/<你>/tcp-socket-quiz:/exam tcp-quiz
```

### 在 PowerShell 要怎麼寫？

PowerShell 的變數寫法是 `${PWD}`。但 Docker Engine 裝在 WSL 裡，**PowerShell 沒有 `docker` 指令**，
要嘛先 `wsl -d Ubuntu-22.04` 進 Ubuntu，要嘛透過 `wsl` 轉呼叫：

```powershell
wsl -d Ubuntu-22.04 -- docker run --rm -v /mnt/c/Users/<你>/tcp-socket-quiz:/exam tcp-quiz python3 judge/judge.py
```

---

## 2. `permission denied while trying to connect to the docker API at unix:///var/run/docker.sock`

### 原因

你的 Linux 帳號不在 `docker` 群組裡。docker 的控制介面 `/var/run/docker.sock` 的權限是：

```
srw-rw---- 1 root docker 0 ... /var/run/docker.sock
```

只有 `root` 和 **`docker` 群組**的成員可以讀寫。安裝腳本是用 root 跑的，
之後自己用 `adduser` 建立的帳號預設不在這個群組。

### 確認

```bash
id -nG                  # 列出自己所在的群組，沒有 docker 就是這個問題
getent group docker     # 列出 docker 群組的成員，例如 docker:x:999:root
```

### 解法

```bash
sudo usermod -aG docker $USER     # $USER 會自動換成你的帳號名稱
```

或者在 **PowerShell** 用 root 身分執行（不需要 sudo 密碼）：

```powershell
wsl -d Ubuntu-22.04 -u root -- usermod -aG docker <你的 Linux 帳號>
```

> ⚠ 一定要有 `-a`（append）。只寫 `-G docker` 會把你的群組清單**整個換成**只剩 docker，
> 你會被踢出 `sudo` 群組。

### 加了之後還是 permission denied？

群組要**重新登入**才會生效，已經開著的 Ubuntu 視窗不會自動更新。任選一種：

- `exit` 關掉，再 `wsl -d Ubuntu-22.04` 重新進去（推薦）
- 在目前視窗執行 `newgrp docker`（只有這個視窗生效）
- 在 PowerShell 執行 `wsl --terminate Ubuntu-22.04`（會關掉所有 Ubuntu 視窗）

> 加入 `docker` 群組等同給了 root 等級的權限（例如可以 `-v /:/host` 掛載整個系統）。
> 個人練習環境沒關係，多人共用的機器要小心。

---

## 3. `wsl --install` 只回應「尚未安裝 Windows 子系統 Linux 版」

Windows 內建的 `wsl.exe` 只是一個殼，在某些企業版 Windows 上連 `--install` 都不接受。
改用以下步驟（需要系統管理員權限）：

```powershell
# 1. 開啟 Windows 功能
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart

# 2. 從 winget 安裝 WSL 本體
winget install --id Microsoft.WSL --source winget

# 3. 重新開機，然後安裝 Ubuntu
wsl --install -d Ubuntu-22.04
```

- 跳出的 UAC 視窗被取消、或沒有管理員帳密 → 請公司 IT 協助
- 出現虛擬化相關錯誤 → 到 BIOS 開啟 Intel VT-x / AMD-V

---

## 4. `wsl --install -d Ubuntu-22.04 --no-launch` 之後沒有建立使用者

用 `--no-launch` 安裝時不會跑「設定使用者名稱與密碼」的流程，預設就是 root。要建立自己的帳號：

```bash
# 在 Ubuntu 裡以 root 執行
adduser <名字>
usermod -aG sudo,docker <名字>
printf '[user]\ndefault=<名字>\n' >> /etc/wsl.conf
```

再到 PowerShell 執行 `wsl --shutdown`，下次進入就會是新帳號。

### root 的密碼是什麼？

**沒有密碼。** Ubuntu 預設把 root 鎖住（`passwd -S root` 會顯示 `L`）。
在 WSL 裡不需要它：`wsl -d Ubuntu-22.04 -u root` 就能直接以 root 進入。
真的需要的話可以用 `sudo passwd root` 設定，但比較建議用自己的帳號 + `sudo`。

---

## 5. PowerShell 裡 `wsl` 的輸出變成亂碼

`wsl.exe` 預設輸出 UTF-16，在某些終端機會變成亂碼。先設定環境變數：

```powershell
$env:WSL_UTF8 = 1
wsl -l -v
```

---

## 6. 剛用 winget 裝好的指令（`gh`、`wsl`）找不到

新安裝的程式要**重新開啟終端機**，PATH 才會更新。在那之前可以用完整路徑：

```powershell
& "C:\Program Files\GitHub CLI\gh.exe" auth status
```

---

## 7. 電腦變很慢 / WSL 吃掉太多記憶體

WSL2 預設最多可以用掉一半的實體記憶體。在 `C:\Users\<你>\.wslconfig` 設定上限：

```ini
[wsl2]
memory=3GB
processors=2
swap=2GB
```

存檔後執行 `wsl --shutdown`，下次啟動生效。

---

## 8. judge 跑完最後出現 `Fatal Python error` / exit code 139

舊版 judge 在 Python 3.10 結束時，可能因為測試失敗後殘留的背景 thread 而崩潰（分數本身是正確的）。
目前版本已修正；如果還遇到，請先 `git pull` 更新到最新版。
