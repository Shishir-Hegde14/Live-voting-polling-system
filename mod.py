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

def display_votes(results):
    current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"\nVote list at time: {current_time}")
    print("----------------")
    for cid in results:
        print(f"{results[cid]['name']}: {results[cid]['votes']}")

MODERATOR_PORT = 9001

modSock = socket(AF_INET, SOCK_DGRAM)
modSock.bind(("0.0.0.0", MODERATOR_PORT))

local_ip = get_local_ip()

print("Moderator Live Vote Monitor Started\n")

while True:

    data, addr = modSock.recvfrom(2048)
    msg = json.loads(data.decode())

    if msg["type"] == "discover_mod":
        response = {"type": "mod_ip", "ip": local_ip}
        modSock.sendto(json.dumps(response).encode(), addr)

    elif msg["type"] == "update":
        results = msg["results"]
        display_votes(results)