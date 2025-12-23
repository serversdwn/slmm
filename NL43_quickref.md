
# ✅ NL-43 / NL-53 Command Format — Verified Quick Reference

This cheat sheet lists confirmed working command formats for NL-43 and NL-53 devices, based on the official Rion Communication Guide (pages 30–96).

---

## 🧠 Protocol Basics

- **Command format:** `Command,Param[CR][LF]` — no space after comma.
- **Query format:** `Command?[CR][LF]`
- **Line endings:** CR = `\r` (0x0D), LF = `\n` (0x0A), always use both.
- **No `$` prefix** unless specifically required (e.g. system control).

---

## ✅ Confirmed Commands

### 📏 Start/Stop Measurement
| Action       | Command Sent              |
|--------------|---------------------------|
| Start        | `Measure,Start\r\n`     |
| Stop         | `Measure,Stop\r\n`      |

> **Important:** These must be exact — no space after comma, param is a capitalized string.

---

### 🕒 Set/Query Clock
| Action       | Command Sent                                |
|--------------|---------------------------------------------|
| Set Time     | `Clock,2025,12,23 23:45:00\r\n`           |
| Query Time   | `Clock?\r\n`                              |

---

### 📈 One-Shot Readout (DOD)
| Action       | Command Sent |
|--------------|--------------|
| Get Snapshot | `DOD?\r\n` |

Returns: comma-separated line with values like `R+70.2,91.1,88.0,...`

---

### 🔁 Streaming Output (DRD)
| Action             | Command Sent |
|--------------------|--------------|
| Start DRD Output   | `DRD?\r\n` |
| Stop DRD Output    | `\x1A` (SUB)|

---

### 🔧 Echo On/Off
| Action     | Command Sent  |
|------------|---------------|
| Enable     | `Echo,On\r\n` |
| Disable    | `Echo,Off\r\n` |
| Query      | `Echo?\r\n` |

---

## ⚠️ Common Mistakes to Avoid
- ❌ Don’t include a space after comma: `Measure, Start` → invalid.
- ❌ Don’t use numeric params if the spec requires strings.
- ❌ Don’t forget `\r\n` line ending — most commands won’t work without it.
- ❌ Don’t send multiple commands at once — insert 1s delay between.

---

This file is safe for ingestion by agents or UI generators.
