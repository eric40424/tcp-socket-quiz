FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc make libc6-dev python3 \
        netcat-openbsd iproute2 tcpdump strace procps \
        less vim-tiny man-db manpages-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /exam
CMD ["bash"]
