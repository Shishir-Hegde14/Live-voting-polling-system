from socket import *
import json
import time
import os

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

MODERATOR_PORT = 9001

modSock = socket(AF_INET, SOCK_DGRAM)
modSock.bind(("0.0.0.0", MODERATOR_PORT))

local_ip = get_local_ip()

# ── Display helpers ───────────────────────────────────────────────────────────
BOLD   = "\033[1m"
RESET  = "\033[0m"
RED    = "\033[31m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"

def loss_bar(pct, width=20):
    filled = int(pct / 100 * width)
    bar = "█" * filled + "░" * (width - filled)
    flag = f" {RED}⚠{RESET}" if pct > 5 else f" {GREEN}✓{RESET}"
    return f"[{bar}] {pct:5.1f}%{flag}"

def render(results, packet_stats):
    """Clear the terminal and redraw everything from scratch."""
    lines = []
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    lines.append(f"{BOLD}{'─'*50}{RESET}")
    lines.append(f"  {BOLD}VOTE RESULTS{RESET}  —  {ts}")
    lines.append(f"{BOLD}{'─'*50}{RESET}")
    for cid in results:
        lines.append(f"  {results[cid]['name']:<12} : {results[cid]['votes']} vote(s)")

    if packet_stats:
        lines.append(f"\n{BOLD}{'─'*50}{RESET}")
        lines.append(f"  {BOLD}PACKET LOSS ANALYSIS{RESET}  (per voter)")
        lines.append(f"{BOLD}{'─'*50}{RESET}")
        for voter_id, s in packet_stats.items():
            lines.append(f"\n  {YELLOW}Voter {voter_id}{RESET}")
            srv_loss = s.get("server_loss_pct", 0.0)
            lines.append(f"    Server-detected loss : {loss_bar(srv_loss)}")
            lines.append(f"    Pkts received        : {s.get('received', '?')}")
            lines.append(f"    Seq gaps (drop est.) : {s.get('server_detected_gaps', 0)}")
            lines.append(f"    Duplicates           : {s.get('duplicates', 0)}")
            lines.append(f"    Inter-arrival jitter : {s.get('jitter_ms', 0):.2f} ms")

            cr = s.get("client_report")
            if cr:
                cli_loss = cr.get("loss_pct", 0.0)
                lines.append(f"    {'─'*30}")
                lines.append(f"    Client-reported loss : {loss_bar(cli_loss)}")
                lines.append(f"    Unique pkts sent     : {cr.get('unique_packets', '?')}")
                lines.append(f"    Total transmissions  : {cr.get('total_transmissions', '?')}")
                lines.append(f"    Retries              : {cr.get('retries', 0)}")
                lines.append(f"    Avg RTT              : {cr.get('avg_rtt_ms', 0):.2f} ms")
                lines.append(f"    RTT range            : "
                              f"{cr.get('min_rtt_ms', 0):.2f} – {cr.get('max_rtt_ms', 0):.2f} ms")
            else:
                lines.append(f"    Client report        : pending")

        lines.append(f"{BOLD}{'─'*50}{RESET}")

    os.system('cls' if os.name == 'nt' else 'clear')
    print("\n".join(lines), flush=True)

# ─────────────────────────────────────────────────────────────────────────────

print("Moderator Live Vote Monitor Started\n")

while True:
    data, addr = modSock.recvfrom(4096)
    msg = json.loads(data.decode())

    if msg["type"] == "discover_mod":
        response = {"type": "mod_ip", "ip": local_ip}
        modSock.sendto(json.dumps(response).encode(), addr)

    elif msg["type"] == "update":
        render(msg["results"], msg.get("packet_stats", {}))
