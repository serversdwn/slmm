# NL-43 / NL-53 Communication Guide (Concise Summary)

This is a terse operator/dev summary of the official “NL-43/NL-53 Communication Guide” (No. 66132, 97 pages). Use the PDF for authoritative details.

## Transport Modes
- **USB CDC**: Serial over USB. Mutually exclusive with LAN TCP/FTP/web/I/O port comm. No driver needed on Win10/11.
- **LAN (NX-43EX required)**: TCP control, FTP for file transfer, and optional web app (ports 80 and 8000). LAN TCP/FTP/web/USB comm are mutually exclusive—turning one on can disable the others.
- **RS-232C**: Classic serial. Baud 9600–115200; DRD streaming requires ≥19200 (EX) or ≥57600 (RT).

## Command Protocol
- ASCII text; end every command with `CR LF`.
- Two types:
  - **Setting**: `$Command,Param[CR][LF]`
  - **Request**: `Command?[CR][LF]`
- Wait for the leading `$` prompt/idle before sending the next command; guide recommends ≥1 s between commands.
- Result codes: `R+0000` success; `0001` command error; `0002` parameter error; `0003` spec/type error; `0004` status error (wrong device state).
- Control codes: `CR`=0x0D, `LF`=0x0A, `SUB`=0x1A (stop DRD stream).

## Core Commands (common)
- **Clock**: `Clock, YYYY/MM/DD hh:mm:ss` | `Clock?`
- **Start/Stop**: `Measure, Start` | `Measure, Stop`
- **Store mode**: `Store Mode, Manual|Auto` (many related time/interval setters in Store section)
- **Manual store**: `Manual Store, Start`
- **Battery/SD**: `Battery Level?`, `SD Card Total Size?`, `SD Card Free Size?`, `SD Card Percentage?`
- **Display/Measure params**: numerous `Display ...` and `Measure ...` setters/getters (frequency/time weighting, ranges, etc.).

## LAN / Ethernet (NX-43EX)
- `Ethernet, On|Off` — enable LAN.
- `Ethernet DHCP, On|Off` — address assignment.
- `Ethernet IP|Subnet|Gateway, <value>` — static settings.
- `TCP, On|Off` — TCP control channel. TCP stops if USB comm, web app, or I/O port comm is turned on.
- `FTP, On|Off` — file transfer mode (mutually exclusive with TCP/web/USB comm when active).
- `Web, On|Off` — built-in web app (ports 80 and 8000). Disables Timer Auto, Trigger Mode, Delay Time, USB comm, LAN TCP, LAN FTP while in use.

## Data Outputs
- **DOD?** — Snapshot of displayed values (Lp/Leq/LE/Lmax/Lmin/LN1–LN5/Lpeak/LIeq/Leq,mov/Ltm5 + over/under flags) for up to 4 channels. Leave ≥1 s between requests.
- **DLC?** — Final calculation result set (similar fields as DOD) for last measurement/interval.
- **DRD?** — Continuous output every 100 ms; stop by sending `SUB` (0x1A). Main/Sub1–Sub3 Lp/Leq/Lmax/Lmin/Lpeak/LIeq + over/under flags.
- **DRD?status** — Same as DRD plus timestamp, power source (I/E/U), battery level (F/M/L/D/E), SD remaining MB, measurement state (M/S).
- Optional NX-43RT variants include octave/1⁄3 octave band data appended.

## Examples (from guide)
- Basic setup for Auto store:
  - `Frequency Weighting, A`
  - `Time Weighting, F`
  - `Store Mode, Auto`
  - `Store Name, 0100`
  - `Measurement Time Preset Auto, 10m`
  - `Lp Store Interval, 100ms`
  - `Leq Calculation Interval Preset, 1m`
  - Start/stop: `Measure, Start` / `Measure, Stop`
  - Read values: `DOD?`
- Manual store:
  - `Store Mode, Manual`
  - `Store Name, 0200`
  - `Measurement Time Preset Manual, 15m`
  - Start/stop: `Measure, Start` / `Measure, Stop`
  - Save: `Manual Store, Start`
  - Read values: `DOD?`

## Timing/Behavior Constraints
- Device responds within ~3 s; if busy, may return `R+0004`.
- Time between sent characters: ≤100 ms.
- After sending a command, wait for `$` prompt/idle before the next; recommended 1 s.
- DRD streaming continues until `SUB` (0x1A) is received.

## Web App (NX-43EX)
- Ports 80 and 8000; login required. Disables Timer Auto, Trigger Mode, Delay Time, I/O port comm, USB comm, LAN TCP, and LAN FTP while active.

## Optional Programs
- **NX-43EX**: LAN TCP/FTP/web, DRD/DRD?status (EX flavor).
- **NX-43RT**: Octave/1⁄3 octave features; DRD/DRD?status/DOD/DLC include band data; higher baud needed for RS-232C streaming.
- **NX-43WR**: Waveform recording (noted in guide; specific settings in Operation Guide).

## Quick Startup Checklist (for TCP control)
1) Install NX-43EX; on device: Ethernet On, set IP/subnet/gateway/DHCP; `TCP, On`; ensure USB comm + web app + I/O port comm are Off.  
2) On controlling host/RX55: ensure port-forward/VPN to NL43 IP:TCP port (default 80).  
3) Send `Clock,<timestamp>` to sync time.  
4) Configure mode/intervals, then `Measure, Start`.  
5) Poll `DOD?` for snapshots (≥1 s), or `DRD?status` for live stream; stop stream with `SUB`.  
6) Switch to `FTP, On` only when pulling SD files; then back to `TCP, On` for control.
