# Live Voter-Poll Monitoring (LAN)

A lightweight UDP-based voting system for local networks (LAN), with live moderator updates and basic packet-loss analysis.

## What this project does

- Lets a voter submit one vote from a client app.
- Prevents duplicate votes by voter ID.
- Sends live vote updates to a moderator monitor.
- Tracks reliability metrics (timeouts, retries, packet loss, RTT, jitter) over UDP.

## Works on LAN

This project is designed for devices connected to the same LAN/subnet.

- Discovery uses UDP broadcast (`x.x.x.255`), which typically does not cross routers.
- Keep all machines on the same Wi-Fi/Ethernet network.
- Open firewall access for UDP ports `9000` and `9001`.

## Computer Network Concepts Used

- **UDP communication**: connectionless, low-overhead socket messaging.
- **Broadcast-based service discovery**: client discovers server and server discovers moderator using LAN broadcast.
- **Client-Server-Moderator architecture**:
  - `client1.py`: voter interaction and vote submission.
  - `server2.py`: vote handling, duplicate check, and stats aggregation.
  - `mod.py`: real-time vote monitor.
- **Application-layer reliability on top of UDP**:
  - sequence numbers (`seq`), timeouts, retries, and loss reporting.
- **RTT and jitter observation**:
  - client estimates RTT; server estimates inter-arrival jitter and sequence gaps.
- **JSON serialization**:
  - messages encoded/decoded as JSON payloads over UDP datagrams.
- **Port-based multiplexing**:
  - vote server on `9000`, moderator service on `9001`.

## Project Files

- `mod.py` - moderator live monitor.
- `server2.py` - voting server + packet tracking.
- `client1.py` - voter client + packet tracking.

## Requirements

- Python 3.8+
- No external Python packages required (uses standard library only).

## How to Run

Run each component in a separate terminal (or separate LAN machines).

1. Start moderator:

```bash
python mod.py
```

2. Start server:

```bash
python server2.py
```

3. Start client:

```bash
python client1.py
```

4. In client terminal:
- Enter a 4-digit voter ID.
- Choose candidate number.
- Vote is submitted and reflected on moderator output.

## Recommended startup order

1. `mod.py`
2. `server2.py`
3. `client1.py`

## Notes

- If discovery fails, confirm all devices are on the same subnet and firewall rules allow UDP traffic.
- On congested networks, packet retries/timeouts may increase.
