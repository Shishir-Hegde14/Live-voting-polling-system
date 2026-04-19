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

local_ip = get_local_ip()
broadcast_ip = get_broadcast_ip(local_ip)

clientSock = socket(AF_INET, SOCK_DGRAM)
clientSock.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)

# ── Packet Loss Tracker ──────────────────────────────────────────────────────
class PacketLossTracker:
    """Tracks sent/received packets and computes loss statistics."""

    def __init__(self, timeout=5.0, max_retries=3):
        self.timeout = timeout
        self.max_retries = max_retries
        self.seq = 0                   # next sequence number
        self.sent = 0                  # total transmissions (including retries)
        self.retries = 0               # retry count
        self.lost = 0                  # packets with no response after all retries
        self.rtts = []                 # round-trip times for successful exchanges

    def next_seq(self):
        self.seq += 1
        return self.seq

    def send_with_tracking(self, sock, msg: dict, dest, description=""):
        """
        Attach a sequence number + timestamp, send with retries, return response.
        Returns (response_dict, rtt_ms) or raises RuntimeError on total loss.
        """
        seq = self.next_seq()
        msg["seq"] = seq
        msg["ts"] = time.time()
        payload = json.dumps(msg).encode()

        for attempt in range(1, self.max_retries + 1):
            send_time = time.time()
            sock.sendto(payload, dest)
            self.sent += 1

            sock.settimeout(self.timeout)
            try:
                data, _ = sock.recvfrom(4096)
                rtt = (time.time() - send_time) * 1000          # ms
                self.rtts.append(rtt)
                if attempt > 1:
                    self.retries += attempt - 1
                response = json.loads(data.decode())
                label = f" [{description}]" if description else ""
                print(f"  [PKT] seq={seq} attempt={attempt}{label} "
                      f"RTT={rtt:.1f}ms ✓")
                return response, rtt

            except timeout:
                print(f"  [PKT] seq={seq} attempt={attempt}/{self.max_retries}"
                      f" TIMEOUT — retrying…")

        # All retries exhausted
        self.lost += 1
        self.retries += self.max_retries - 1
        raise RuntimeError(
            f"Packet seq={seq} lost after {self.max_retries} attempts"
        )

    def summary(self):
        total_unique = self.seq          # one unique packet per logical message
        loss_pct = (self.lost / total_unique * 100) if total_unique else 0.0
        avg_rtt  = (sum(self.rtts) / len(self.rtts)) if self.rtts else 0.0
        min_rtt  = min(self.rtts) if self.rtts else 0.0
        max_rtt  = max(self.rtts) if self.rtts else 0.0
        return {
            "unique_packets": total_unique,
            "total_transmissions": self.sent,
            "retries": self.retries,
            "lost": self.lost,
            "loss_pct": round(loss_pct, 2),
            "avg_rtt_ms": round(avg_rtt, 2),
            "min_rtt_ms": round(min_rtt, 2),
            "max_rtt_ms": round(max_rtt, 2),
        }

    def print_summary(self):
        s = self.summary()
        print("\n╔══════════════════════════════════════╗")
        print("║     CLIENT PACKET LOSS ANALYSIS      ║")
        print("╠══════════════════════════════════════╣")
        print(f"║  Unique packets sent  : {s['unique_packets']:<13}║")
        print(f"║  Total transmissions  : {s['total_transmissions']:<13}║")
        print(f"║  Retries              : {s['retries']:<13}║")
        print(f"║  Packets lost         : {s['lost']:<13}║")
        print(f"║  Loss rate            : {s['loss_pct']:<12.2f}%║")
        print(f"║  Avg RTT              : {s['avg_rtt_ms']:<10.2f} ms║")
        print(f"║  Min RTT              : {s['min_rtt_ms']:<10.2f} ms║")
        print(f"║  Max RTT              : {s['max_rtt_ms']:<10.2f} ms║")
        print("╚══════════════════════════════════════╝")

# ────────────────────────────────────────────────────────────────────────────

tracker = PacketLossTracker(timeout=5.0, max_retries=3)

# ── Server Discovery ─────────────────────────────────────────────────────────
discover_msg = {"type": "discover_server"}
clientSock.sendto(json.dumps(discover_msg).encode(), (broadcast_ip, SERVER_PORT))

clientSock.settimeout(300)
try:
    data, addr = clientSock.recvfrom(2048)
    response = json.loads(data.decode())
    if response["type"] == "server_ip":
        SERVER_IP = response["ip"]
        print(f"Found server at {SERVER_IP}")
    else:
        print("Invalid response")
        exit()
except:
    print("Server discovery failed")
    exit()
clientSock.settimeout(None)

# ── Voter ID ─────────────────────────────────────────────────────────────────
while True:
    voter_id = input("Enter 4 digit Voter ID: ")
    if len(voter_id) == 4 and voter_id.isdigit():
        break
    else:
        print("Invalid Voter ID. Must be exactly 4 digits.")

# ── Check ID (with loss tracking) ────────────────────────────────────────────
try:
    check_msg = {"type": "check_id", "voter_id": voter_id}
    response, _ = tracker.send_with_tracking(
        clientSock, check_msg, (SERVER_IP, SERVER_PORT), "check_id"
    )
except RuntimeError as e:
    print(f"Network error: {e}")
    tracker.print_summary()
    exit()

if response["status"] == "used":
    print("Voter ID already used")
    tracker.print_summary()
    exit()

print("\nCandidates:")
candidates = response["candidates"]
for cid in candidates:
    print(cid, "-", candidates[cid]["name"])

# ── Candidate Selection ───────────────────────────────────────────────────────
while True:
    choice_str = input("\nChoose candidate number: ")
    if choice_str.isdigit() and choice_str in candidates:
        choice = int(choice_str)
        break
    print("Invalid choice. Please select a valid candidate number (1, 2, or 3).")

# ── Cast Vote (with loss tracking) ───────────────────────────────────────────
try:
    vote_msg = {"type": "vote", "voter_id": voter_id, "candidate": choice}
    res, _ = tracker.send_with_tracking(
        clientSock, vote_msg, (SERVER_IP, SERVER_PORT), "vote"
    )
except RuntimeError as e:
    print(f"Network error: {e}")
    tracker.print_summary()
    exit()

if res["status"] == "vote_counted":
    print("Vote successfully recorded")
else:
    print("Vote rejected")

# ── Final Stats ───────────────────────────────────────────────────────────────
tracker.print_summary()

# Send loss stats to server so moderator can see them
stats_msg = {
    "type": "loss_report",
    "voter_id": voter_id,
    "stats": tracker.summary()
}
clientSock.sendto(json.dumps(stats_msg).encode(), (SERVER_IP, SERVER_PORT))
