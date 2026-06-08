# NL-43 + RX55 TCP “Wedge” Investigation (2255 Refusal) — Full Log & Next Steps
**Last updated:** 2026-02-18  
**Owner:** Brian / serversdown  
**Context:** Terra-View / SLMM / field-deployed Rion NL-43 behind Sierra Wireless RX55

---

## 0) What this document is
This is a **comprehensive, chronological** record of the debugging we did to isolate a failure where the **NL-43’s TCP control port (2255) eventually stops accepting connections** (“wedges”), while other services (notably FTP/21) remain reachable.

This is written to be fed back into future troubleshooting, so it intentionally includes the **full reasoning chain, experiments, commands, packet evidence, and conclusions**.

---

## 1) Architecture (as tested)
### Network path
- **Server (SLMM host):** `10.0.0.40`
- **RX55 WAN IP:** `63.45.161.30`
- **RX55 LAN subnet:** `192.168.1.0/24`
- **RX55 LAN gateway:** `192.168.1.1`
- **NL-43 LAN IP:** `192.168.1.10` (confirmed via ARP OUI + ping; see LAN validation)

### RX55 details
- **Sierra Wireless RX55**
- **OS:** 5.2
- **Firmware:** `01.14.24.00`
- **Carrier:** Verizon LTE (Band 66)

### Port forwarding rules (RX55)
- **WAN:2255 → NL-43:2255**  (NL-43 TCP control)
- **WAN:21   → NL-43:21**    (NL-43 FTP control)

You also experimented with additional forwards:
- **WAN:2253 → NL-43:2255** (test)
- **WAN:2253 → NL-43:2253** (test)
- **WAN:4450 → NL-43:4450** (test)

**Important:** Rule “Input zone / interface” was set to **WAN-NAT**, and Source IP left as **Any IPv4**. This is correct for inbound port-forward behavior on Sierra OS 5.x.

---

## 2) Original problem statement (the “wedge”)
After running for hours, the NL-43 becomes unreachable over TCP control.

### Symptom signature (WAN-side)
- Client attempts to connect to `63.45.161.30:2255`
- Instead of timing out, the client gets **connection refused** quickly.
- Packet-level: SYN from client → **RST,ACK** back (meaning active refusal vs silent drop)

### Critical operational behavior
- **Power cycling the NL-43 fixes it.**
- **Power cycling the RX55 does NOT fix it.**
- FTP sometimes remains available even while TCP control (2255) is dead.

This combination is what forced us to determine whether:
- The RX55 is rejecting connections, OR
- The NL-43 is no longer listening on 2255, OR
- Something about the RX55 path triggers the NL-43’s control listener to die.

---

## 3) Event timeline evidence (SLMM logs)
A concrete wedge window was observed on **2026-02-18**:

- 10:55:46 AM — Poll success (Start)
- 11:00:28 AM — Measurement STOPPED (scheduled stop/download cycle succeeded)
- 11:55:50 AM — Poll success (Stop)
- 12:55:55 PM — Poll success (Stop)
- **1:55:58 PM — Poll failed (attempt 1/3): Errno 111 (connection refused)**
- 2:56:02 PM — Poll failed (attempt 2/3): Errno 111 (connection refused)

Key interpretation:
- The wedge occurred sometime between **12:55 and 1:55**.
- The failure type is **refused**, not timeout.

---

## 4) Early hypotheses (before proof)
We considered two main buckets:

### A) NL-43-side failure (most suspicious)
- NL-43 TCP control service crashes / exits / unbinds from 2255
- socket leak / accept backlog exhaustion
- “single control session allowed” and it gets stuck thinking a session is active
- mode/service manager bug (service restart fails after other activities)
- firmware bug in TCP daemon

### B) RX55-side failure (possible trigger / less likely once FTP works)
- NAT/forwarding table corruption
- firewall behavior
- helper/ALG interference
- MSS/MTU weirdness causing edge-case behavior
- session churn behavior causing downstream issues

---

## 5) Key experiments and what they proved

### 5.1) LAN-only stability test (No RX55 path)
**Test:** NL-43 tested directly on LAN (no modem path involved).
- Ran **24+ hours**
- Scheduler start/stop cycles worked
- Stress test: **500 commands @ 1/sec** → no failure
- Response time trend decreased (not degrading)

**Result:** The NL-43 appears stable in a “pure LAN” environment.

**Interpretation:** The trigger is likely related to the RX55/WAN environment, connection patterns, or service switching patterns—not just simple uptime.

---

### 5.2) Port-forward behavior: timeout vs refused (RX55 behavior characterization)
You observed:

- **If a WAN port is NOT forwarded (no rule):** connecting to that port **times out** (silent drop)
- **If a WAN port IS forwarded to NL-43 but nothing listens:** it **actively refuses** (RST)

Concrete example:
- Port **4450** with no rule → timeout
- Port **4450 → NL-43:4450** rule created → connection refused

**Interpretation:** This confirms the RX55 is actually forwarding packets to the NL-43 when a rule exists. “Refused” is consistent with the NL-43 (or RX55 relay behavior) responding quickly because the packet reached the target.

Important nuance:
- A “refused” on forwarded ports does **not** automatically prove the NL-43 is the one generating RST, because NAT hides the inside host and the RX55 could reject on behalf of an unreachable target. We needed a LAN-side proof test to close the loop.

---

### 5.3) UDP test confusion (and resolution)
You ran:

```bash
nc -vzu 63.45.161.30 2255
nc -vz  63.45.161.30 2255
```

Observed:
- UDP: “succeeded”
- TCP: “connection refused”

Resolution:
- UDP has **no handshake**. netcat prints “succeeded” if it doesn’t immediately receive an ICMP unreachable. It does **not** mean a UDP service exists.
- TCP refused is meaningful: a RST implies “no listener” or “actively rejected.”

**Net effect:** UDP test did not change the diagnosis.

---

### 5.4) Packet capture proof (WAN-side)
You captured a Wireshark/tcpdump summary with these key patterns:

#### Port 2255 (TCP control)
Example:
- `10.0.0.40 → 63.45.161.30:2255` SYN
- `63.45.161.30 → 10.0.0.40` **RST, ACK** within ~50ms

This happened repeatedly.

#### Port 2253 (test port)
Multiple SYN attempts to 2253 showed **retransmissions and no response**, i.e., **silent drop** (consistent with no rule or not forwarded at that moment).

#### Port 21 (FTP)
Clean 3-way handshake:
- SYN → SYN/ACK → ACK
Then:
- FTP server banner: `220 Connection Ready`
Then:
- `530 Not logged in` (because SLMM was sending non-FTP “requests” as an experiment)
Session closes cleanly.

**Key takeaway from capture:**
- TCP transport to NL-43 via RX55 is definitely working (port 21 proves it).
- Port 2255 is being actively refused.

This strongly suggested “2255 listener is gone,” but still didn’t fully prove whether the refusal was generated internally by NL-43 or by RX55 on behalf of NL-43.

---

## 6) The decisive experiment: LAN-side test while wedged (final proof)
Because the RX55 does not offer SSH, the plan was to test from **inside the LAN behind the RX55**.

### 6.1) Physical LAN tap setup
Constraint:
- NL-43 has only one Ethernet port.

Solution:
- Insert an unmanaged switch:
  - RX55 LAN → switch
  - NL-43 → switch
  - Windows 10 laptop → switch

This creates a shared L2 segment where the laptop can test NL-43 directly.

### 6.2) Windows LAN validation
On the Windows laptop:

- `ipconfig` showed:
  - IP: `192.168.1.100`
  - Gateway: `192.168.1.1` (RX55)
- Initial `arp -a` only showed RX55, not NL-43.

You then:
- pinged likely host addresses and discovered NL-43 responds on **192.168.1.10**
- `arp -a` then showed:
  - `192.168.1.10 → 00-10-50-14-0a-d8`
  - OUI `00-10-50` recognized as **Rion** (matches NL-43)

So LAN identities were confirmed:
- RX55: `192.168.1.1`
- NL-43: `192.168.1.10`

### 6.3) The LAN port tests (the smoking gun)
From Windows:

```powershell
Test-NetConnection -ComputerName 192.168.1.10 -Port 2255
Test-NetConnection -ComputerName 192.168.1.10 -Port 21
```

Results (while the unit was “wedged” from the WAN perspective):
- **2255:** `TcpTestSucceeded : False`
- **21:**   `TcpTestSucceeded : True`

**Conclusion (PROVEN):**
- The NL-43 is reachable on the LAN
- FTP port 21 is alive
- **The NL-43 is NOT listening on TCP port 2255**
- Therefore the RX55 is not the root cause of the refusal. The WAN refusal is consistent with the NL-43 having no listener on 2255.

This is now settled.

---

## 7) What we learned (final conclusions)
### 7.1) RX55 innocence (for this failure mode)
The RX55 is not “randomly rejecting” or “breaking TCP” in the way originally feared.

It successfully forwards and supports TCP to the NL-43 on port 21, and the LAN-side test proves the 2255 failure exists *even without NAT/WAN involvement*.

### 7.2) NL-43 control listener failure
The NL-43’s TCP control service (port 2255) stops listening while:
- the device remains alive
- the LAN stack remains alive (ping)
- FTP remains alive (port 21)

This looks like one of:
- control daemon crash/exit
- service unbind
- stuck service state (e.g., “busy” / “session active forever”)
- resource leak (sockets/file descriptors) specific to the control service
- firmware service manager bug (start/stop of services fails after certain sequences)

---

## 8) Additional constraint discovered: “Web App mode” conflicts
You noted an important operational constraint:

> Turning on the web app disables other interfaces like TCP and FTP.

Meaning the NL-43 appears to have mutually exclusive service/mode behavior (or at least serious conflicts). That matters because:
- If any workflow toggles modes (explicitly or implicitly), it could destabilize the service lifecycle.
- It reduces the possibility of using “web UI toggle” as an easy remote recovery mechanism **if** it disables the services needed.

We have not yet run a controlled long test to determine whether:
- mode switching contributes directly to the 2255 listener dying, OR
- it happens even in a pure TCP-only mode with no switching.

---

## 9) Immediate operational decision (field tomorrow)
Because the device is needed in the field immediately, you chose:
- **Old-school manual deployment**
- **Manual SD card downloads**
- Avoid reliance on 2255/TCP control and remote workflows for now.

**Important operational note:**
The 2255 listener dying does not necessarily stop the NL-43 from measuring; it primarily breaks remote control/polling. Manual SD workflow sidesteps the entire remote control dependency.

---

## 10) What’s next (future work — when the unit is back)
Because long tests can’t be run before tomorrow, the plan is to resume in a few weeks with controlled experiments designed to isolate the trigger and develop an operational mitigation.

### 10.1) Controlled experiment matrix (recommended)
Run each test for 24–72 hours, or until wedge occurs, and record:
- number of TCP connects
- whether connections are persistent
- whether FTP is used
- whether any mode toggling is performed
- time-to-wedge

#### Test A — TCP-only (ideal baseline)
- TCP control only (2255)
- **True persistent connection** (open once, keep forever)
- No FTP
- No web mode toggling

Outcome interpretation:
- If stable: connection churn and/or FTP/mode switching is the trigger.
- If wedges anyway: pure 2255 daemon leak/bug.

#### Test B — TCP with connection churn
- Same as A but intentionally reconnect on a schedule (current SLMM behavior)
- No FTP

Outcome:
- If this wedges but A doesn’t: churn is the trigger.

#### Test C — FTP activity + TCP
- Introduce scheduled FTP sessions (downloads) while using TCP control
- Observe whether wedge correlates with FTP use or with post-download periods.

Outcome:
- If wedge correlates with FTP, suspect internal service lifecycle conflict.

#### Test D — Web mode interaction (only if safe/possible)
- Evaluate what toggling web mode does to TCP/FTP services.
- Determine if any remote-safe “soft reset” exists.

---

## 11) Mitigation options (ranked)
### Option 1 — Make SLMM truly persistent (highest probability of success)
If the NL-43 wedges due to session churn or leaked socket states, the best mitigation is:
- Open one TCP socket per device
- Keep it open indefinitely
- Use OS keepalive
- Do **not** rotate connections on timers
- Reconnect only when the socket actually dies

This reduces:
- connect/close cycles
- NAT edge-case exposure
- resource churn inside NL-43

### Option 2 — Service “soft reset” (if possible without disabling required services)
If there exists any way to restart the 2255 service without power cycling:
- LAN TCP toggle (if it doesn’t require web mode)
- any “restart comms” command (unknown)
- any maintenance menu sequence
then SLMM could:
- detect wedge
- trigger soft reset
- recover automatically

Current constraint: web app mode appears to disable other services, so this may not be viable.

### Option 3 — Hardware watchdog power cycle (industrial but reliable)
If this is a firmware bug with no clean workaround:
- Add a remotely controlled relay/power switch
- On wedge detection, power-cycle NL-43 automatically
- Optionally schedule a nightly power cycle to prevent leak accumulation

This is “field reality” and often the only long-term move with embedded devices.

### Option 4 — Vendor escalation (Rion)
You now have excellent evidence:
- LAN-side proof: 2255 dead while 21 alive
- WAN packet evidence
- clear isolation of RX55 innocence

This is strong enough to send to Rion support as a firmware defect report.

---

## 12) Repro “wedge bundle” checklist (for future captures)
When the wedge happens again, capture these before power cycling:

1) From server:
- `nc -vz 63.45.161.30 2255` (expect refused)
- `nc -vz 63.45.161.30 21`   (expect success if FTP alive)

2) From LAN side (via switch/laptop):
- `Test-NetConnection 192.168.1.10 -Port 2255`
- `Test-NetConnection 192.168.1.10 -Port 21`

3) Optional: packet capture around the refused attempt.

4) Record:
- last successful poll timestamp
- last FTP session timestamp
- any scheduled start/stop/download cycles near wedge time
- SLMM connection reuse/rotation settings in effect

---

## 13) Final, current-state summary (as of 2026-02-18)
- The issue is **NOT** the RX55 rejecting inbound connections.
- The NL-43 is **alive**, reachable on LAN, and FTP works.
- The NL-43’s **TCP control listener on 2255 stops listening** while the device remains otherwise healthy.
- The wedge can occur hours after successful operations.
- The unit is needed in the field immediately, so investigation pauses.
- Next phase: controlled tests to isolate trigger + implement mitigation (persistent socket or watchdog reset).

---

## 14) Notes / misc observations
- The Wireshark trace showed repeated FTP sessions were opened and closed cleanly, but SLMM’s “FTP requests” were not valid FTP (causing `530 Not logged in`). That was part of experimentation, not a normal workflow.
- UDP “success” via netcat is not meaningful because UDP has no handshake; it simply indicates no ICMP unreachable was returned.

---

**End of document.**
