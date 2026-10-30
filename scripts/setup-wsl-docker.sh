#!/usr/bin/env bash
# 在 WSL2 的 Ubuntu 22.04 裡安裝 Docker Engine (免費、開源，不需要 Docker Desktop)，
# 然後 build 考試環境的 image，並用參考解答驗證 judge。
#
# 用法 (在 Windows PowerShell):
#   wsl -d Ubuntu-22.04 -- bash /mnt/c/Users/<你>/tcp-socket-quiz/scripts/setup-wsl-docker.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> [1/5] 安裝必要套件"
sudo apt-get update
sudo apt-get install -y ca-certificates curl

echo "==> [2/5] 加入 Docker 官方 apt repository"
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

echo "==> [3/5] 安裝 Docker Engine"
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin
sudo usermod -aG docker "$USER"   # 之後不用 sudo 就能跑 docker (重新登入後生效)

# 讓 WSL 開機時用 systemd，docker 服務才會自動啟動
if ! grep -qs '^systemd=true' /etc/wsl.conf; then
    printf '[boot]\nsystemd=true\n' | sudo tee -a /etc/wsl.conf > /dev/null
    echo "    已啟用 systemd (需要在 Windows 執行 wsl --shutdown 後生效)"
fi

echo "==> [4/5] 啟動 docker 並 build 考試環境 image (tcp-quiz)"
if ! sudo docker info > /dev/null 2>&1; then
    sudo service docker start || true
    sleep 3
fi
sudo docker build -t tcp-quiz "$PROJECT_DIR"

echo "==> [5/5] 用參考解答驗證 judge (應該拿到 100/100)"
sudo docker run --rm -v "$PROJECT_DIR:/exam" tcp-quiz python3 judge/judge.py --target solutions

cat <<EOF

完成！接下來：
  1. 在 Windows PowerShell 執行:  wsl --shutdown   (讓 docker 群組與 systemd 生效)
  2. 之後進入考試環境:
       wsl -d Ubuntu-22.04
       cd $PROJECT_DIR
       docker run --rm -it -v "\$PWD:/exam" tcp-quiz
EOF
