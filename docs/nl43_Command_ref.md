# NL-43/NL-53 Sound Level Meter - AI Command Reference
## Quick Reference for Programming & Development

---

## 🚀 QUICK START - COMMAND SYNTAX

### Setting Command (Change device settings)
```
Format: $Command Name,Parameter[CR][LF]
Example: $LCD Auto Off,Short[CR][LF]
         $Backlight,On[CR][LF]
```

**Critical Rules:**
- **Prefix:** `$` (auto-added by device, shows command processing status)
- **Separator:** `,` (comma required after command name)
- **Spaces:** Must preserve exact spacing in command names
- **Terminator:** `[CR][LF]` (0x0D 0x0A)
- **Case:** Insensitive (LCD = lcd = Lcd)
- **Wait:** Minimum 1 second after receiving `$` response before next command

### Request Command (Get device status/data)
```
Format: Command Name?[CR][LF]
Example: Battery Level?[CR][LF]
         System Version?[CR][LF]
```

**Critical Rules:**
- **Suffix:** `?` after command name
- **No prefix:** No `$` for requests
- **Terminator:** `[CR][LF]`
- **Case:** Insensitive

---

## 📋 RESULT CODES

Every command returns a result code:

```
Format: R+####
```

| Code | Status | Meaning |
|------|--------|---------|
| `R+0000` | ✅ Success | Command executed successfully |
| `R+0001` | ❌ Command Error | Command not recognized |
| `R+0002` | ❌ Parameter Error | Wrong parameter format or count |
| `R+0003` | ❌ Specification Error | Used set when should request (or vice versa) |
| `R+0004` | ❌ Status Error | Device not in correct state for this command |

---

## ⏱️ TIMING & CONTROL VALUES

| Operation | Time | Notes |
|-----------|------|-------|
| Device response time | < 3 seconds | Max time for device to respond |
| Between characters | < 100 ms | When sending multi-char strings |
| Device idle time | < 200 ms | After device sends data |
| **Recommended wait** | **≥ 1 second** | **After `$` before next command** |

---

## 🔧 COMMUNICATION CODES

| Code | Hex | Purpose |
|------|-----|---------|
| `[CR]` | 0x0D | First terminator (Carriage Return) |
| `[LF]` | 0x0A | Second terminator (Line Feed) |
| `[SUB]` | 0x1A | Stop request |

---

## 📚 COMMAND CATEGORIES & FULL LIST

### Communication
| Command | Type | Function |
|---------|------|----------|
| `Echo` | S/R | Communication echo ON/OFF |

### System
| Command | Type | Function |
|---------|------|----------|
| `System Version` | R | Get firmware version |
| `Type` | R | Get device type (NL-43/NL-53) |
| `Serial Number` | R | Get device serial number |
| `Clock` | S/R | Set/get current time |
| `Language` | S/R | Set/get display language |
| `Index Number` | S/R | Set/get index number |
| `Key Lock` | S/R | Enable/disable key lock |

### Display
| Command | Type | Function |
|---------|------|----------|
| `Backlight` | S/R | Control backlight ON/OFF |
| `Backlight Auto Off` | S/R | Set auto-off time for backlight |
| `LCD` | S/R | Control LCD ON/OFF |
| `LCD Auto Off` | S/R | Set auto-off time for LCD |
| `Backlight Brightness` | S/R | Set backlight brightness |
| `Battery Type` | S/R | Set battery type |
| `Battery Level` | R | Get current battery level |
| `Output Level Range Upper` | S/R | Set upper limit of bar graph |
| `Output Level Range Lower` | S/R | Set lower limit of bar graph |
| `Display Leq` | S/R | Enable/disable Leq display |
| `Display LE` | S/R | Enable/disable LE display |
| `Display Lpeak` | S/R | Enable/disable Lpeak display |
| `Display Lmax` | S/R | Enable/disable Lmax display |
| `Display Lmin` | S/R | Enable/disable Lmin display |
| `Display LN1` | S/R | Enable/disable L5 display |
| `Display LN2` | S/R | Enable/disable L10 display |
| `Display LN3` | S/R | Enable/disable L50 display |
| `Display LN4` | S/R | Enable/disable L90 display |
| `Display LN5` | S/R | Enable/disable L95 display |
| `Time Level Time Scale` | S/R | Set time-level time scale |

### SD Card
| Command | Type | Function |
|---------|------|----------|
| `SD Card Total Size` | R | Get total SD card capacity |
| `SD Card Free Size` | R | Get SD card free space |
| `SD Card Percentage` | R | Get SD card free space ratio |

### Measurement
| Command | Type | Function |
|---------|------|----------|
| `Frequency Weighting (Main)` | S/R | Set main frequency weighting (A/C/Z) |
| `Frequency Weighting (Sub1/2/3)` | S/R | Set sub frequency weighting |
| `Time Weighting (Main)` | S/R | Set main time weighting (F/S/I) |
| `Time Weighting (Sub1/2/3)` | S/R | Set sub time weighting |
| `Measure` | S/R | Start/stop measurement |
| `Pause` | S/R | Pause measurement |
| `Windscreen Correction` | S/R | Enable/disable windscreen correction |

### Storage
| Command | Type | Function |
|---------|------|----------|
| `Store Mode` | S/R | Set storage mode (Manual/Auto) |
| `Store Name` | S/R | Set storage name |
| `Manual Address` | S/R | Set manual storage address |
| `Manual Store` | S | Execute manual storage |
| `Overwrite` | S/R | Enable/disable storage overwriting |
| `Measurement Time Preset Manual` | S/R | Set manual measurement time |
| `Measurement Time Preset Auto` | S/R | Set auto measurement time |

### I/O
| Command | Type | Function |
|---------|------|----------|
| `AC OUT` | S/R | Set AC output ON/OFF |
| `DC OUT` | S/R | Set DC output ON/OFF |
| `Baud Rate` | S/R | Set RS-232C baud rate |
| `USB Class` | S/R | Set USB communication mode |
| `Ethernet` | S/R | Enable/disable LAN function |
| `Ethernet DHCP` | S/R | Enable/disable DHCP |
| `Ethernet IP` | S/R | Set IP address |
| `Ethernet Subnet` | S/R | Set subnet mask |
| `Ethernet Gateway` | S/R | Set default gateway |
| `Web` | S/R | Enable/disable web application |
| `FTP` | S/R | Enable/disable FTP |
| `TCP` | S/R | Enable/disable TCP communication |

### Data Output
| Command | Type | Function |
|---------|------|----------|
| `DOD` | R | Output current displayed value |
| `DRD` | R | Continuous data output |
| `DRD?status` | R | Continuous output with status |
| `DLC` | R | Output final calculation result |

---

## 💡 DETAILED COMMAND SYNTAX

### Echo (Communication Echo)
**Purpose:** Enable/disable echo of sent commands

**Setting:**
```
$Echo,Off[CR][LF]     # Disable echo
$Echo,On[CR][LF]      # Enable echo
```

**Request:**
```
Echo?[CR][LF]
Response: Off | On
```

---

### System Version
**Purpose:** Get firmware version

**Request:**
```
System Version?[CR][LF]
Response: "xx.xx.xxxx"  # Example: "01.02.0034"
```

**Note:** No setting command available

---

### Type
**Purpose:** Get device type

**Request:**
```
Type?[CR][LF]
Response: "NL-43" | "NL-53"
```

**Note:** No setting command available

---

### Serial Number
**Purpose:** Get device serial number

**Request:**
```
Serial Number?[CR][LF]
Response: "xxxxxxxx"  # 8-digit number (00000000-99999999)
```

---

### Clock
**Purpose:** Set/get current date and time

**Setting:**
```
$Clock,2025/12/24 14:30:00[CR][LF]

Format: $Clock,YYYY/MM/DD HH:MM:SS[CR][LF]
- Year: 2023-2079
- Month: 1-12
- Day: 1-31
- Hour: 0-23
- Minute: 0-59
- Second: 0-59
```

**Request:**
```
Clock?[CR][LF]
Response: 2025/12/24 14:30:00
```

---

### Language
**Purpose:** Set/get display language

**Setting:**
```
$Language,English[CR][LF]

Options:
- Japanese
- English
- Germany
- Spanish
- French
- Simplified Chinese
- Korean
```

**Request:**
```
Language?[CR][LF]
Response: English
```

---

### Index Number
**Purpose:** Set/get index number

**Setting:**
```
$Index Number,0042[CR][LF]

Format: 0000-9999 (4 digits)
```

**Request:**
```
Index Number?[CR][LF]
Response: 0042
```

---

### Key Lock
**Purpose:** Enable/disable key lock

**Setting:**
```
$Key Lock,Off[CR][LF]
$Key Lock,On[CR][LF]
```

**Request:**
```
Key Lock?[CR][LF]
Response: Off | On
```

---

### Backlight
**Purpose:** Control backlight ON/OFF

**Setting:**
```
$Backlight,Off[CR][LF]
$Backlight,On[CR][LF]
```

**Request:**
```
Backlight?[CR][LF]
Response: Off | On
```

---

### Backlight Auto Off
**Purpose:** Set backlight auto-off timer

**Setting:**
```
$Backlight Auto Off,Short[CR][LF]
$Backlight Auto Off,Long[CR][LF]
$Backlight Auto Off,Off[CR][LF]

Options:
- Short: 30 seconds
- Long: 60 seconds
- Off: Always on
```

**Request:**
```
Backlight Auto Off?[CR][LF]
Response: Short | Long | Off
```

---

### LCD Auto Off
**Purpose:** Set LCD auto-off timer

**Setting:**
```
$LCD Auto Off,Short[CR][LF]
$LCD Auto Off,Long[CR][LF]
$LCD Auto Off,Off[CR][LF]

Options:
- Short: 5 minutes
- Long: 10 minutes
- Off: Always on
```

**Request:**
```
LCD Auto Off?[CR][LF]
Response: Short | Long | Off
```

---

### Backlight Brightness
**Purpose:** Set backlight brightness

**Setting:**
```
$Backlight Brightness,1[CR][LF]

Range: 1-4 (1=dimmest, 4=brightest)
```

**Request:**
```
Backlight Brightness?[CR][LF]
Response: 1 | 2 | 3 | 4
```

---

### Battery Type
**Purpose:** Set battery type

**Setting:**
```
$Battery Type,Alkaline[CR][LF]
$Battery Type,NiMH[CR][LF]

Options:
- Alkaline: Alkaline batteries
- NiMH: Nickel-metal hydride batteries
```

**Request:**
```
Battery Type?[CR][LF]
Response: Alkaline | NiMH
```

---

### Battery Level
**Purpose:** Get current battery level

**Request:**
```
Battery Level?[CR][LF]
Response: 0-100  # Percentage (0=empty, 100=full)
```

**Note:** Read-only command

---

### Measure
**Purpose:** Start/stop measurement

**Setting:**
```
$Measure,Run[CR][LF]     # Start measurement
$Measure,Stop[CR][LF]    # Stop measurement
```

**Request:**
```
Measure?[CR][LF]
Response: Run | Stop
```

---

### Pause
**Purpose:** Pause/resume measurement

**Setting:**
```
$Pause,On[CR][LF]      # Pause measurement
$Pause,Off[CR][LF]     # Resume measurement
```

**Request:**
```
Pause?[CR][LF]
Response: On | Off
```

---

### Frequency Weighting (Main)
**Purpose:** Set main frequency weighting

**Setting:**
```
$Frequency Weighting,A[CR][LF]
$Frequency Weighting,C[CR][LF]
$Frequency Weighting,Z[CR][LF]

Options:
- A: A-weighting (most common)
- C: C-weighting
- Z: Z-weighting (flat response)
```

**Request:**
```
Frequency Weighting?[CR][LF]
Response: A | C | Z
```

---

### Time Weighting (Main)
**Purpose:** Set main time weighting

**Setting:**
```
$Time Weighting,F[CR][LF]
$Time Weighting,S[CR][LF]
$Time Weighting,I[CR][LF]

Options:
- F: Fast (125ms)
- S: Slow (1000ms)
- I: Impulse
```

**Request:**
```
Time Weighting?[CR][LF]
Response: F | S | I
```

---

### Baud Rate
**Purpose:** Set RS-232C communication speed

**Setting:**
```
$Baud Rate,9600[CR][LF]
$Baud Rate,19200[CR][LF]
$Baud Rate,38400[CR][LF]
$Baud Rate,57600[CR][LF]
$Baud Rate,115200[CR][LF]
```

**Request:**
```
Baud Rate?[CR][LF]
Response: 9600 | 19200 | 38400 | 57600 | 115200
```

**Note:** Default is usually 38400

---

### Ethernet IP
**Purpose:** Set IP address for LAN connection

**Setting:**
```
$Ethernet IP,192.168.1.100[CR][LF]

Format: xxx.xxx.xxx.xxx (0-255 for each octet)
```

**Request:**
```
Ethernet IP?[CR][LF]
Response: 192.168.1.100
```

---

### Ethernet DHCP
**Purpose:** Enable/disable automatic IP address assignment

**Setting:**
```
$Ethernet DHCP,Off[CR][LF]   # Manual IP
$Ethernet DHCP,On[CR][LF]    # Automatic IP
```

**Request:**
```
Ethernet DHCP?[CR][LF]
Response: Off | On
```

---

### DOD (Display Output Data)
**Purpose:** Get current displayed measurement value

**Request:**
```
DOD?[CR][LF]

Response format:
ddd.d,cc.c,aa.a
- ddd.d: Main display value
- cc.c: Sub display value  
- aa.a: Additional value
```

**Example Response:**
```
075.2,072.1,080.5
# 75.2 dB main, 72.1 dB sub, 80.5 dB peak
```

---

### DRD (Data Real-time Display)
**Purpose:** Continuous output of measurement data

**Request:**
```
DRD?[CR][LF]
```

**Stop continuous output:**
```
[SUB] (0x1A)
```

**Response:** Continuous stream of measurement values until stop requested

---

### USB Class
**Purpose:** Set USB communication mode

**Setting:**
```
$USB Class,Serial[CR][LF]         # Serial communication mode
$USB Class,Mass Storage[CR][LF]   # Mass storage mode (file access)
```

**Request:**
```
USB Class?[CR][LF]
Response: Serial | Mass Storage
```

**Important:** When in Mass Storage mode, communication commands are blocked

---

## 🎯 COMMON PROGRAMMING PATTERNS

### Basic Connection Test
```python
# 1. Check device type
send("Type?[CR][LF]")
wait_for_response()  # Should get "NL-43" or "NL-53"

# 2. Get version
send("System Version?[CR][LF]")
wait_for_response()  # e.g., "01.02.0034"

# 3. Enable echo for debugging
send("$Echo,On[CR][LF]")
wait_for_response()  # Should get "R+0000"
```

### Start Basic Measurement
```python
# 1. Set frequency weighting to A
send("$Frequency Weighting,A[CR][LF]")
wait_1_second()

# 2. Set time weighting to Fast
send("$Time Weighting,F[CR][LF]")
wait_1_second()

# 3. Start measurement
send("$Measure,Run[CR][LF]")
wait_1_second()

# 4. Get current reading
send("DOD?[CR][LF]")
reading = wait_for_response()
```

### Configure Network
```python
# 1. Disable DHCP for static IP
send("$Ethernet DHCP,Off[CR][LF]")
wait_1_second()

# 2. Set IP address
send("$Ethernet IP,192.168.1.100[CR][LF]")
wait_1_second()

# 3. Set subnet
send("$Ethernet Subnet,255.255.255.0[CR][LF]")
wait_1_second()

# 4. Set gateway
send("$Ethernet Gateway,192.168.1.1[CR][LF]")
wait_1_second()

# 5. Enable Ethernet
send("$Ethernet,On[CR][LF]")
wait_1_second()
```

### Continuous Data Acquisition
```python
# Start continuous output
send("DRD?[CR][LF]")

# Read data in loop
while acquiring:
    data = read_line()
    process(data)

# Stop when done
send("[SUB]")  # 0x1A
```

---

## ⚠️ COMMON ERRORS & TROUBLESHOOTING

### R+0001 - Command Not Recognized
- Check spelling (spaces matter!)
- Verify command exists for your model
- Check for extra/missing spaces in command name

### R+0002 - Parameter Error
- Verify parameter format matches spec
- Check parameter value is in valid range
- Ensure comma separator is present

### R+0003 - Specification Error
- Using `$` prefix on request command
- Using `?` on setting command
- Command type mismatch

### R+0004 - Status Error
- Device busy (measuring, storing, etc.)
- Stop measurement before changing settings
- Check device is powered on and ready
- May need to wait longer between commands

### No Response
- Check baud rate matches (default 38400)
- Verify `[CR][LF]` line endings
- Wait minimum 1 second between commands
- Check cable connection
- Verify USB Class mode is "Serial" not "Mass Storage"

---

## 📝 NOTES FOR AI ASSISTANTS

**When helping with code:**
1. Always include the `$` prefix for setting commands
2. Always include `?` suffix for request commands
3. Always include `[CR][LF]` terminators
4. Always wait ≥1 second between commands
5. Check for `R+0000` success code after settings
6. Handle error codes appropriately

**For serial communication:**
- Use 8 data bits, no parity, 1 stop bit (8N1)
- Default baud: 38400
- Hardware flow control: None
- Hex codes: CR=0x0D, LF=0x0A, SUB=0x1A

**For network communication:**
- TCP port: Varies by configuration
- Ensure device is in correct USB/Ethernet mode
- Commands are identical over serial/network

---

## 📖 DOCUMENT SOURCE

This reference was extracted from:
- **Document:** NL-43/NL-53 Communication Guide
- **Filename:** NL-43_NL-53_Communication_Guide_66132.pdf
- **Manufacturer:** RION Co., Ltd.
- **Full manual available at:** https://rion-sv.com/nl-43_53_63/manual/

**Document Coverage:**
- Full communication protocol specification
- RS-232C and USB serial connection
- Ethernet/LAN configuration
- Complete command reference
- Data output formats
- Timing specifications

For complete technical details, measurement specifications, and advanced features, refer to the full PDF documentation.
