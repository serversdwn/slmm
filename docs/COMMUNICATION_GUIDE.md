# NL-43 / NL-53 Communication Guide (Concise + Full Reference)

Single-file quick reference for the NL-43/NL-53 Communication Guide (No. 66132, pages ~1–97). Use the official PDF for authoritative details, exact formatting, and option requirements.

## Protocol Basics
- ASCII commands terminated with `CR LF`.
- Setting: `$Command,Param[CR][LF]`; Request: `Command?[CR][LF]`.
- Wait for `$` prompt/idle before the next command; recommended ≥1 s between commands.
- Result codes: `R+0000` success; `0001` command error; `0002` parameter error; `0003` spec/type error; `0004` status error (wrong state).
- Control codes: `CR`=0x0D, `LF`=0x0A, `SUB`=0x1A (stop DRD stream).
- Timing: responds within ~3 s; characters ≤100 ms apart; DRD streams until `SUB`.

## Transport Modes
- USB CDC: Serial over USB (mutually exclusive with LAN TCP/FTP/web/I/O port comm).
- RS-232C: 9600–115200 bps; DRD streaming needs ≥19200 (EX) or ≥57600 (RT).
- LAN (NX-43EX): TCP control, FTP, web app (ports 80 & 8000). TCP/FTP/Web are mutually exclusive with each other and with USB comm while active.

## Quick Startup Checklist (TCP control)
1) Install NX-43EX; on device: Ethernet On; DHCP On or set IP/Subnet/Gateway; `TCP, On`; ensure USB comm + web app + I/O port comm are Off.  
2) Ensure reachability to device IP:TCP port (default 80).  
3) `Clock,<timestamp>` to sync time.  
4) Configure mode/intervals, then `Measure, Start`.  
5) Poll `DOD?` (≥1 s) or stream `DRD?status`; stop with `SUB`.  
6) Toggle `FTP, On` only when pulling SD files; then back to `TCP, On`.

## LAN / USB / Web / FTP (NX-43EX)
| Command | Purpose | Type | Notes / Params |
| --- | --- | --- | --- |
| Ethernet | LAN on/off | S/R | `Ethernet, On|Off` (p84) |
| Ethernet DHCP | DHCP on/off | S/R | `Ethernet DHCP, On|Off` (p84) |
| Ethernet IP | Set IP | S/R | `Ethernet IP, a.b.c.d` (p84) |
| Ethernet Subnet | Set subnet | S/R | `Ethernet Subnet, a.b.c.d` (p84) |
| Ethernet Gateway | Set gateway | S/R | `Ethernet Gateway, a.b.c.d` (p85) |
| TCP | TCP control | S/R | `TCP, On|Off` (p86); stops if USB comm/web/I/O port comm enabled |
| FTP | FTP transfer | S/R | `FTP, On|Off` (p85); stops if USB mass storage/web enabled |
| Web | Web app | S/R | `Web, On|Off` (p85); uses ports 80/8000; disables Timer Auto, Trigger Mode, Delay Time, I/O port comm, USB, LAN TCP/FTP while active |
| USB Class | USB comm/mass storage | S/R | `USB Class, Off|CDC|CDC/MSC` (p83); CDC/MSC blocks LAN TCP/FTP |

## Data Output Commands (fields)
- **DOD?**: Snapshot; main/sub channel Lp, Leq, LE, Lmax, Lmin, LN1–LN5, Lpeak, LIeq, Leq,mov, Ltm5, over/under flags. RT variant may include band/POA data; wait ≥1 s between requests.
- **DRD?**: Continuous every 100 ms; counter + main/sub Lp/Leq/Lmax/Lmin/Lpeak/LIeq + over/under. Stop with `SUB` (0x1A). Baud constraints on RS-232C only.
- **DRD?status**: DRD payload + timestamp, power source (I/E/U), battery level (F/M/L/D/E), SD remaining MB, measurement state (M/S).
- **DLC?**: Final calculation set (similar to DOD); RT variant includes band data + over/under flags.

## Condensed Command List (Section 5.6)
| Command | Function | Type | Notes / Page |
| --- | --- | --- | --- |
| Communication Echo | Echo on/off | S/R | p39 |
| System Version | Version info | R | p39 |
| Type | Model type | R | p39 |
| Serial Number | Serial number | R | p39 |
| Clock | Current time | S/R | p40 |
| Language | Display language | S/R | p40 |
| Index Number | Index | S/R | p40 |
| Key Lock | Key lock | S/R | p41 |
| Backlight | Backlight status | S/R | p41 |
| Backlight Auto Off | Auto off | S/R | p41 |
| LCD | LCD status | S/R | p41 |
| LCD Auto Off | Auto off | S/R | p42 |
| Backlight Brightness | Brightness | S/R | p42 |
| Battery Type | Battery type | S/R | p42 |
| Battery Level | Battery level | S/R | p43 |
| SD Card Total Size | SD total | R | p43 |
| SD Card Free Size | SD free | R | p43 |
| SD Card Percentage | SD free % | R | p43 |
| Output Level Range Upper | Bar upper | S/R | p44 |
| Output Level Range Lower | Bar lower | S/R | p44 |
| Display Leq / LE / Lpeak / Lmax / Lmin | Display flags | S/R | p44–45 |
| Display LN1–LN5 | Percentiles display | S/R | p45–46 |
| Display LIeq / Ltm5 / Leqmov | Display flags | S/R | p47 |
| Time Level Time Scale | Time-level scale | S/R | p47 |
| Display Calculate Type (RT) | Calc type | S/R | p48 |
| Measure Display Sub Channel 1–3 | Sub displays | S/R | p49 |
| Octave Mode (RT) | Analysis mode | S/R | p49 |
| Additional Band (RT) | Sub band | S/R | p49 |
| Display Partial Over All (RT) | POA on/off | S/R | p50 |
| Upper/Lower Limit Frequency (+Offset) (RT) | POA bands | S/R | p50–52 |
| Lmax Type / Channel | Lmax/Lmin settings | S/R | p52 |
| Frequency Weighting (Main/Sub1–3) | Weighting | S/R | p53 |
| Frequency Weighting (Band) (RT) | Band weighting | S/R | p53 |
| Time Weighting (Main/Sub1–3) | Time weighting | S/R | p54 |
| Time Weighting (Band/Band2) (RT) | Band time weighting | S/R | p55 |
| Windscreen / Diffuse Correction | Corrections | S/R | p55–56 |
| Ldiff1/Ldiff2 (+Channel/Calc) (RT) | Differential | S/R | p56–57 |
| Store Mode / Name / Manual Address | Storage setup | S/R | p58 |
| Measure | Start/Stop measure | S/R | p58 |
| Pause | Pause | S/R | p59 |
| Manual Store | Manual store | S | p59 |
| Overwrite | Overwrite check | S/R | p59 |
| Measurement Time Preset Manual / Manual (Num/Unit) | Manual timing | S/R | p60 |
| Measurement Time Preset Auto / Auto (Num/Unit) (EX) | Auto timing | S/R | p61 |
| Lp Store Interval | Lp interval | S/R | p62 |
| Leq Calculation Interval Preset / Num / Unit | Leq interval | S/R | p62–63 |
| Store Delay Time | Delay | S/R | p63 |
| Back Erase | Back erase | S/R | p63 |
| Timer Auto Start/Stop Time | Timer | S/R | p64 |
| Timer Auto Interval (EX) | Timer interval | S/R | p65 |
| Sleep Mode | Sleep | S/R | p65 |
| Trigger Mode | Trigger | S/R | p65 |
| Level Trigger Channel (EX) | Trigger channel | S/R | p66 |
| Level Trigger Band Freq/Offset (RT) | Band trigger | S/R | p66–67 |
| Level Trigger Level (EX) | Trigger level | S/R | p67 |
| Moving Leq Interval Preset / Num / Unit | Moving Leq | S/R | p67–68 |
| TRM | LN mode sampling | S/R | p68 |
| Percentile 1–5 | LN percentiles | S/R | p69 |
| Lp Mode (RT) | Lp type | S/R | p69 |
| Wave Rec Mode / Sampling Freq / Bit Length (WR) | Waveform | S/R | p70 |
| Frequency Weighting (Wave) | Wave weighting | S/R | p71 |
| Wave Rec Range Upper / State | Wave status | S/R | p71 |
| Wave Splitting Interval | Split interval | S/R | p72 |
| Wave Manual Rec / Pre-time | Manual rec | S/R | p72 |
| Wave Level Rec / Trigger Channel (WR/RT) | Level rec | S/R | p73 |
| Wave Level Trigger Band Freq/Offset (RT) | Band trigger | S/R | p73–74 |
| Wave Level Trigger Level / Pre-time / Max Time | Thresholds | S/R | p74–75 |
| Wave Level Reference Time/Level (1–4) | Time-zone thresholds | S/R | p75–76 |
| Wave Interval Rec (Interval/Time) | Interval rec | S/R | p76–77 |
| I/O AC OUT | AC output | S/R | p78 |
| AC Out Band Freq/Offset (RT) | AC band | S/R | p78–79 |
| I/O DC OUT | DC output | S/R | p79 |
| DC Out Band Freq/Offset (RT) | DC band | S/R | p80 |
| Output Range Upper | Electrical full scale | S/R | p81 |
| Reference Signal Output | Reference signal | S/R | p81 |
| IO Func | IO port | S/R | p81 |
| Baud Rate | RS-232C baud | S/R | p82 |
| Comparator Channel | Comparator channel | S/R | p82 |
| Comparator Band Freq/Offset (RT) | Comparator band | S/R | p82–83 |
| Comparator Level (EX) | Comparator level | S/R | p83 |
| USB Class | USB comm | S/R | p83 |
| Ethernet / DHCP / IP / Subnet / Gateway (EX) | LAN config | S/R | p84–85 |
| Web (EX) | Web app | S/R | p85 |
| FTP (EX) | FTP | S/R | p85 |
| TCP (EX) | TCP control | S/R | p86 |
| DOD / DOD (RT) | Output displayed value | R | p88–89 |
| DRD / DRD (RT) | Continuous output | R | p90–91 |
| DRD?status / DRD?status (RT) | Continuous + status | R | p92–93 |
| DLC / DLC (RT) | Final calculation output | R | p94–95 |

## Full Command Catalog (pages ~30–95)
All commands from section 5.6 listed with purpose. Types: S=Setting, R=Request. Options: (EX)=NX-43EX, (RT)=NX-43RT, (WR)=NX-43WR.

Communication / System
- Communication Echo (S/R): Echo sent command strings (p39)
- System Version (R): Version info (p39)
- Type (R): Type info (p39)
- Serial Number (R): Serial number (p39)
- Clock (S/R): Current time (p40)
- Language (S/R): Display language (p40)
- Index Number (S/R): Index (p40)

UI / Power / Storage Stats
- Key Lock (S/R): Key lock (p41)
- Backlight (S/R): Backlight status (p41)
- Backlight Auto Off (S/R): Auto off (p41)
- LCD (S/R): LCD status (p41)
- LCD Auto Off (S/R): Auto off (p42)
- Backlight Brightness (S/R): Brightness (p42)
- Battery Type (S/R): Battery type (p42)
- Battery Level (S/R): Battery level (p43)
- SD Card Total Size (R): SD total (p43)
- SD Card Free Size (R): SD free (p43)
- SD Card Percentage (R): SD free % (p43)

Display/Measure Flags
- Output Level Range Upper/Lower (S/R): Bar graph ranges (p44)
- Display Leq/LE/Lpeak/Lmax/Lmin (S/R): Flags (p44–45)
- Display LN1–LN5 (S/R): Percentiles (p45–46)
- Display LIeq/Ltm5/Leqmov (S/R): Flags (p47)
- Time Level Time Scale (S/R): Time-level scale (p47)
- Display Calculate Type (RT, S/R): Calc type (p48)
- Measure Display Sub Channel 1–3 (S/R): Sub displays (p49)

Analysis / Bands (RT)
- Octave Mode (S/R): Analysis mode (p49)
- Additional Band (S/R): Sub band (p49)
- Display Partial Over All (S/R): POA (p50)
- Upper/Lower Limit Frequency (+Offset) (S/R): POA bands (p50–52)
- Lmax Type / Channel (S/R): Lmax/Lmin settings (p52)

Weighting / Corrections
- Frequency Weighting (Main/Sub1–3) (EX, S/R): Weighting (p53)
- Frequency Weighting (Band) (RT, S/R): Band weighting (p53)
- Time Weighting (Main/Sub1–3) (S/R): Time weighting (p54)
- Time Weighting (Band/Band2) (RT, S/R): Band time weighting (p55)
- Windscreen Correction (S/R): Windscreen correction (p55)
- Diffuse Sound Field Correction (S/R): Diffuse correction (p56)

Differential (RT)
- Ldiff1/Ldiff2 (S/R): Measure differential (p56)
- Ldiff1/2 Channel1/2 (S/R): Differential channel (p56)
- Ldiff1/2 Calculation1/2 (S/R): Differential calc (p57)

Store / Measurement Control
- Store Mode (S/R): Manual/Auto (p58)
- Store Name (S/R): Storage name (p58)
- Manual Address (S/R): Manual storage address (p58)
- Measure (S/R): Start/Stop measure (p58)
- Pause (S/R): Pause (p59)
- Manual Store (S): Manual store (p59)
- Overwrite (S/R): Overwrite check (p59)
- Measurement Time Preset Manual / Manual (Num/Unit) (S/R): Manual timing (p60)
- Measurement Time Preset Auto / Auto (Num/Unit) (EX, S/R): Auto timing (p61)
- Lp Store Interval (S/R): Lp interval (p62)
- Leq Calculation Interval Preset / Num / Unit (S/R): Leq interval (p62–63)
- Store Delay Time (S/R): Delay (p63)
- Back Erase (S/R): Back erase (p63)
- Timer Auto Start/Stop Time (S/R): Timer (p64)
- Timer Auto Interval (EX, S/R): Auto interval (p65)
- Sleep Mode (S/R): Sleep (p65)
- Trigger Mode (S/R): Trigger (p65)
- Level Trigger Channel (EX, S/R): Trigger channel (p66)
- Level Trigger Band Frequency/Offset (RT, S/R): Band trigger (p66–67)
- Level Trigger Level (EX, S/R): Trigger level (p67)
- Moving Leq Interval Preset / Num / Unit (S/R): Moving Leq (p67–68)
- TRM (S/R): LN mode sampling (p68)
- Percentile 1–5 (S/R): LN percentiles (p69)
- Lp Mode (RT, S/R): Lp type (p69)

Waveform Recording (WR/RT)
- Wave Rec Mode / Sampling Frequency / Bit Length (S/R): Recording config (p70)
- Frequency Weighting (Wave) (S/R): Wave weighting (p71)
- Wave Rec Range Upper / State (S/R): Rec range/status (p71)
- Wave Splitting Interval (S/R): File split interval (p72)
- Wave Manual Rec / Pre-time (S/R): Manual rec (p72)
- Wave Level Rec / Trigger Channel (WR/RT, S/R): Level rec (p73)
- Wave Level Trigger Band Frequency/Offset (RT, S/R): Band trigger (p73–74)
- Wave Level Trigger Level / Pre-time / Maximum Recording Time (S/R): Thresholds/time (p74–75)
- Wave Level Reference Time Interval 1–4 (S/R): Time-zone intervals (p75)
- Wave Level Reference Time 1–4 (S/R): Time-zone time (p75)
- Wave Level Reference Time 1–4 Level (S/R): Time-zone level (p75–76)
- Wave Interval Rec Interval / Time (S/R): Interval rec (p76–77)

I/O and Outputs
- I/O AC OUT (S/R): AC output (p78)
- AC Out Band Frequency/Offset (RT, S/R): AC band (p78–79)
- I/O DC OUT (S/R): DC output (p79)
- DC Out Band Frequency/Offset (RT, S/R): DC band (p80)
- Output Range Upper (S/R): Electrical full scale (p81)
- Reference Signal Output (S/R): Reference signal (p81)
- IO Func (S/R): IO port (p81)

Comparator / Comms
- Baud Rate (S/R): RS-232C baud (p82)
- Comparator Channel (S/R): Comparator channel (p82)
- Comparator Band Frequency/Offset (RT, S/R): Comparator band (p82–83)
- Comparator Level (EX, S/R): Comparator level (p83)
- USB Class (S/R): USB comm/mass storage (p83)
- Ethernet/DHCP/IP/Subnet/Gateway (EX, S/R): LAN config (p84–85)
- Web (EX, S/R): Web app (p85)
- FTP (EX, S/R): FTP (p85)
- TCP (EX, S/R): TCP control (p86)

Data Output (fields)
- DOD / DOD (RT) (R): Snapshot of displayed values; includes Lp/Leq/LE/Lmax/Lmin/LN1–LN5/Lpeak/LIeq/Leq,mov/Ltm5/over-under (p88–89).
- DRD / DRD (RT) (R): Continuous every 100 ms; counter + Lp/Leq/Lmax/Lmin/Lpeak/LIeq + over/under (p90–91). Stop with `SUB`.
- DRD?status / DRD?status (RT) (R): DRD + timestamp, power source, battery level, SD remaining MB, measurement state (p92–93).
- DLC / DLC (RT) (R): Final calculation result set (similar to DOD; RT includes band data) (p94–95).
