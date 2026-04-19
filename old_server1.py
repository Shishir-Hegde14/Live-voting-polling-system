from socket import *
import json
import time

def get_local_ip():
    s = socket(AF_INET, SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def get_broadcast_ip(local_ip):
    parts = local_ip.split('.')
    return '.'.join(parts[:3]) + '.255'

SERVER_PORT = 9000
MODERATOR_PORT = 9001

serverSock = socket(AF_INET, SOCK_DGRAM)
serverSock.bind(("0.0.0.0", SERVER_PORT))

local_ip = get_local_ip()
broadcast_ip = get_broadcast_ip(local_ip)

modSock = socket(AF_INET, SOCK_DGRAM)
modSock.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)

# Discover moderator
discover_msg = {"type": "discover_mod"}
modSock.sendto(json.dumps(discover_msg).encode(), (broadcast_ip, MODERATOR_PORT))

modSock.settimeout(300)
try:
    data, addr = modSock.recvfrom(2048)
    response = json.loads(data.decode())
    if response["type"] == "mod_ip":
        MODERATOR_IP = response["ip"]
        print(f"Found moderator at {MODERATOR_IP}")
    else:
        print("Invalid response")
        exit()
except:
    print("Moderator discovery failed")
    exit()
modSock.settimeout(None)

print("Voting Server Started")

used_voters = set()

candidates = {
    1: {"name": "Alice", "votes": 0},
    2: {"name": "Bob", "votes": 0},
    3: {"name": "Charlie", "votes": 0}
}

last_send = time.time()

while True:
    timeout = 60 - (time.time() - last_send)
    if timeout > 0:
        serverSock.settimeout(timeout)
    else:
        serverSock.settimeout(0.1)

    try:
        data, addr = serverSock.recvfrom(2048)
        msg = json.loads(data.decode())

        if msg["type"] == "discover_server":
            response = {"type": "server_ip", "ip": local_ip}
            serverSock.sendto(json.dumps(response).encode(), addr)

        elif msg["type"] == "check_id":

            voter_id = msg["voter_id"]

            if voter_id in used_voters:
                serverSock.sendto(json.dumps({"status": "used"}).encode(), addr)
            else:
                serverSock.sendto(json.dumps({
                    "status": "ok",
                    "candidates": candidates
                }).encode(), addr)

        elif msg["type"] == "vote":

            voter_id = msg["voter_id"]
            choice = msg["candidate"]

            if voter_id not in used_voters:

                used_voters.add(voter_id)
                candidates[choice]["votes"] += 1

                serverSock.sendto(json.dumps({"status": "vote_counted"}).encode(), addr)

                # send update to moderator immediately
                modSock.sendto(
                    json.dumps({"type": "update", "results": candidates}).encode(),
                    (MODERATOR_IP, MODERATOR_PORT)
                )
                last_send = time.time()  # reset timer

            else:
                serverSock.sendto(json.dumps({"status": "duplicate"}).encode(), addr)

        elif msg["type"] == "get_votes":
            serverSock.sendto(json.dumps({"type": "vote_update", "results": candidates}).encode(), addr)

    except:
        # timeout, send periodic update
        modSock.sendto(json.dumps({"type": "update", "results": candidates}).encode(), (MODERATOR_IP, MODERATOR_PORT))
        last_send = time.time()