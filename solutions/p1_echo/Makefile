CC      = gcc
CFLAGS  = -std=c99 -Wall -Wextra -O2

all: server client

server: server.c
	$(CC) $(CFLAGS) -o $@ $<

client: client.c
	$(CC) $(CFLAGS) -o $@ $<

clean:
	rm -f server client

.PHONY: all clean
