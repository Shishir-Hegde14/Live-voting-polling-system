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

# ── Server-Side Packet Loss Tracker ──────────────────────────────────────────
class ServerPacketTracker:
    """
    Per-client sequence number gap analysis.

    When a client attaches seq numbers, the server detects gaps (missing
    packets that were never retried successfully) and measures inter-arrival
    jitter. It also aggregates client-reported loss stats forwarded from the
    client's own tracker.
    """

    def __init__(self):
        # per-client state: { voter_id or addr_str: {...} }
        self.clients = {}

    def _key(self, voter_id):
        return str(voter_id)

    def _ensure(self, key):
        if key not in self.clients:
            self.clients[key] = {
                "expected_seq": 1,
                "received": 0,
                "gaps": 0,            # sequence gaps (server-detected loss)
                "duplicates": 0,
                "last_arrival": None,
                "inter_arrivals": [],
                "client_report": None  # filled when client sends loss_report
            }
        return self.clients[key]

    def record(self, voter_id, seq):
        """Call this for every packet that arrives with a seq field."""
        key = self._key(voter_id)
        c = self._ensure(key)
        now = time.time()

        if c["last_arrival"] is not None:
            ia = (now - c["last_arrival"]) * 1000   # ms
            c["inter_arrivals"].append(ia)
        c["last_arrival"] = now

        if seq < c["expected_seq"]:
            c["duplicates"] += 1
        elif seq > c["expected_seq"]:
            gap = seq - c["expected_seq"]
            c["gaps"] += gap
            print(f"  [SERVER-PKT] voter={voter_id} gap detected: "
                  f"expected seq={c['expected_seq']} got seq={seq} "
                  f"(gap={gap})")
            c["expected_seq"] = seq + 1
        else:
            c["expected_seq"] += 1

        c["received"] += 1

    def record_client_report(self, voter_id, stats: dict):
        """Store the loss report the client sends at the end of its session."""
        key = self._key(voter_id)
        c = self._ensure(key)
        c["client_report"] = stats
        print(f"  [SERVER-PKT] loss report received from voter={voter_id}: "
              f"loss={stats.get('loss_pct', '?')}% "
              f"avg_rtt={stats.get('avg_rtt_ms', '?')}ms")

    def jitter(self, voter_id):
        key = self._key(voter_id)
        if key not in self.clients:
            return 0.0
        ias = self.clients[key]["inter_arrivals"]
        if len(ias) < 2:
            return 0.0
        diffs = [abs(ias[i] - ias[i-1]) for i in range(1, len(ias))]
        return round(sum(diffs) / len(diffs), 2)

    def summary_all(self):
        """Return aggregated stats for all clients (sent to moderator)."""
        out = {}
        for key, c in self.clients.items():
            total = c["received"] + c["gaps"]
            loss_pct = (c["gaps"] / total * 100) if total > 0 else 0.0
            out[key] = {
                "received": c["received"],
                "server_detected_gaps": c["gaps"],
                "duplicates": c["duplicates"],
                "server_loss_pct": round(loss_pct, 2),
                "jitter_ms": self.jitter(key),
                "client_report": c["client_report"]
            }
        return out

pkt_tracker = ServerPacketTracker()
# ─────────────────────────────────────────────────────────────────────────────

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

def send_mod_update():
    """Push vote results + packet loss stats to moderator."""
    payload = {
        "type": "update",
        "results": candidates,
        "packet_stats": pkt_tracker.summary_all()
    }
    modSock.sendto(json.dumps(payload).encode(), (MODERATOR_IP, MODERATOR_PORT))

while True:
    timeout = 60 - (time.time() - last_send)
    serverSock.settimeout(max(timeout, 0.1))

    try:
        data, addr = serverSock.recvfrom(4096)
        msg = json.loads(data.decode())

        # Record sequence number for every packet that carries one
        voter_id = msg.get("voter_id", addr[0])
        seq = msg.get("seq")
        if seq is not None:
            pkt_tracker.record(voter_id, seq)

        if msg["type"] == "discover_server":
            response = {"type": "server_ip", "ip": local_ip}
            serverSock.sendto(json.dumps(response).encode(), addr)

        elif msg["type"] == "check_id":
            if voter_id in used_voters:
                serverSock.sendto(json.dumps({"status": "used"}).encode(), addr)
            else:
                serverSock.sendto(json.dumps({
                    "status": "ok",
                    "candidates": candidates
                }).encode(), addr)

        elif msg["type"] == "vote":
            choice = msg["candidate"]
            if voter_id not in used_voters:
                used_voters.add(voter_id)
                candidates[choice]["votes"] += 1
                serverSock.sendto(json.dumps({"status": "vote_counted"}).encode(), addr)
                send_mod_update()
                last_send = time.time()
            else:
                serverSock.sendto(json.dumps({"status": "duplicate"}).encode(), addr)

        elif msg["type"] == "loss_report":
            # Client finished — store its self-reported stats
            pkt_tracker.record_client_report(voter_id, msg["stats"])
            send_mod_update()      # push updated stats immediately
            last_send = time.time()

        elif msg["type"] == "get_votes":
            serverSock.sendto(json.dumps({
                "type": "vote_update",
                "results": candidates
            }).encode(), addr)

    except:
        # Periodic heartbeat
        send_mod_update()
        last_send = time.time()
