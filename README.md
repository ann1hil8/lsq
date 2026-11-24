# LSQ

LSQ is a script-driven laboratory instrument control and test automation framework. It separates the scripting language, runtime, device drivers, connection profiles, transport implementations, discovery, and persistent connection state.

Supported transports are:

- `serial` for RS-232, RS-422, RS-485, and USB-to-serial interfaces;
- `visa` for USBTMC, LAN VISA, and other PyVISA resources;
- `tcp` for raw SCPI socket connections;
- `gpib` for GPIB resources exposed through VISA;
- `simulated` for deterministic CI and development tests.

## Installation

```text
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e .
```

Linux/macOS activation:

```text
source .venv/bin/activate
python -m pip install -e .
```

USB VISA, LAN VISA, and GPIB operation require a PyVISA backend. On Windows, install NI-VISA and verify the backend with:

```text
python -c "import pyvisa; print(pyvisa.ResourceManager().list_resources())"
```

## Command-line usage

```text
lsq examples/identify.lsq --verbose
lsq examples/identify.lsq --dry-run
lsq examples/identify.lsq --verbosity trace
lsq examples/identify.lsq -vvv
lsq examples/mso2024b_test.lsq --output-dir results/run_001
lsq --list-ports
lsq --list-resources
lsq --validate-catalog
lsq --clear-state
lsq --hardware-test examples/device_test.lsq
lsq examples/test.lsq --loop-limit 10000
```

`--loop-limit` defaults to `100000`. Set it to `0` to permit unbounded loops.

`--list-ports` enumerates serial ports. `--list-resources` enumerates VISA resources using the configured PyVISA backend. Both commands report a clear error when the required backend is unavailable.

`--clear-state` removes the persistent discovery cache. The default state file is `%LOCALAPPDATA%\lsq\connections.json` on Windows and `$XDG_STATE_HOME/lsq/connections.json` or `~/.local/state/lsq/connections.json` on Linux/macOS. Use `--state-file PATH` to select another state file.

`--hardware-test PATH` explicitly marks a script as a live hardware test. It uses the normal runtime and does not enable simulated or dry-run behavior.

## Notepad++ syntax highlighting

Import `tools/notepadpp/lsq.xml` through `Language > User Defined Language > Define your language > Import`. The definition highlights `.lsq` files, commands, control flow, device methods, connection parameters, variables, strings, numbers, operators, and comments. Installation details are in `tools/notepadpp/README.md`.

## Script syntax

```text
connection supply type=serial
    baud=9600 data_bits=8 parity=none stop_bits=1
    match_vid=0x1234 match_pid=0x5678 match_usb_serial=PS-0017
    identify_command="*IDN?" identify_terminator=lf identify_ends=lf
end

device supply driver=generic connection=supply

discover supply
open supply
send supply "*IDN?" terminate=lf
expect supply ends=lf timeout=2s save=idn
print "${idn}"

if contains(idn, "E3634A")
    print "Correct instrument"
else
    fail "Unexpected instrument: ${idn}"
endif

repeat 3
    send supply "MEAS:VOLT?" terminate=lf
    expect supply ends=lf save=measurement
    print "${measurement}"
endrepeat

close supply
```

Supported statements:

```text
include PATH
connection NAME type=serial|visa|gpib|tcp|simulated ... end
device NAME driver=DRIVER [connection=NAME] [driver overrides]
discover NAME
open NAME
close NAME
send NAME VALUE [terminate=none|cr|lf|crlf|hex:...]
expect NAME [ends=none|cr|lf|crlf|hex:...] [contains=TEXT] [regex=REGEX] [bytes=N] [timeout=TIME] [save=VARIABLE]
device_call DEVICE METHOD [ARGUMENTS] [save=VARIABLE]
save VARIABLE file=PATH [format=json|csv|text|raw]
set NAME = EXPRESSION
print EXPRESSION
sleep TIME
function NAME [PARAMS...] ... endfunction
call FUNCTION [ARGUMENTS]
return [EXPRESSION]
if EXPRESSION ... elseif EXPRESSION ... else ... endif
repeat COUNT ... endrepeat
while EXPRESSION ... endwhile
break
continue
try ... catch ERROR_VAR ... finally ... endtry
assert EXPRESSION
assert approximately ACTUAL EXPECTED tolerance=VALUE
fail EXPRESSION
log level=quiet|normal|verbose|trace
```

Timeouts must use a positive value with an explicit unit, such as `250ms` or `5s`. The runtime temporarily applies the timeout to the single operation and restores the previous transport timeout afterward.

`save` writes runtime variables to paths relative to `--output-dir` unless the path is absolute. JSON preserves nested dictionaries and arrays; byte strings are encoded as base64. CSV supports waveform dictionaries containing `time` and `voltage` arrays. Device methods that accept `file=PATH`, such as `save_screenshot`, also use `--output-dir`.

The default verbosity is `normal`. `quiet` suppresses framework logging while preserving script `print` statements and errors. `verbose` displays complete transmitted and received messages. `trace` displays individual bytes and detailed probe failures. Command-line verbosity overrides the script's `log` setting.

Expressions support typed literals, variables, lists, dictionaries, arithmetic, comparisons, `contains(value, text)`, `matches(value, regex)`, `number(value)`, and device access through `get(device, method, arguments...)`.

## Discovery and connection state

The parser builds an AST before execution. Nested conditionals, loops, exception handlers, functions, includes, and source locations are validated before hardware access begins.

Each declared device receives one persistent driver instance. The runtime maintains its connection, lifecycle state, lock, and telemetry for the entire script.

Discovery is transport-specific:

- Serial discovery checks the cached port first, then eligible ports, and validates candidates with the driver identification command.
- VISA discovery checks the cached resource first, then enumerates VISA resources and validates candidates with `*IDN?` or the driver identification rule.
- Raw TCP uses a configured host or a cached host and port. The endpoint is validated with the driver identification command.
- TCP discovery can explicitly use VISA/LAN resources as a bootstrap mechanism with `discovery=visa`. LSQ identifies the TCPIP VISA resource, extracts its host, then opens the raw SCPI socket.
- Simulated discovery creates a deterministic in-process connection.

The cache stores the endpoint only after successful identification. A TCP entry contains the host, port, transport, identity, and optional VISA resource identity. A cached endpoint is not trusted without another identification response.

The generic TCP transport requires a host and uses an explicit port when supplied. The DG1022Z driver supplies port `5555` by default. Raw TCP discovery cannot search arbitrary networks by itself. mDNS and vendor-specific discovery are not currently enabled; they remain separate discovery mechanisms for a future implementation.

For different routed subnets, direct VISA or TCP can work when routing, gateways, and firewall rules permit it. mDNS normally remains limited to the local link unless an mDNS reflector is configured.

## TCP connection examples

### Direct DG1022Z TCP control

```text
connection dg_tcp type=tcp host=10.0.0.14 read_timeout=5s
device dg1022 driver=dg1022z connection=dg_tcp
discover dg_tcp
open dg_tcp

device_call dg1022 identify save=idn
print "IDN = ${idn}"
device_call dg1022 get_frequency channel=1 save=frequency
print "CH1 frequency = ${frequency} Hz"

close dg_tcp
```

The DG1022Z raw socket uses port `5555`. The instrument manual documents `:SYSTem:COMMunicate:LAN:CONTrol?` for querying the socket-control port.

### TCP discovery through VISA/LAN resources

```text
connection dg_tcp_auto type=tcp discovery=visa resource_prefix=TCPIP read_timeout=5s
device dg1022 driver=dg1022z connection=dg_tcp_auto
discover dg_tcp_auto
open dg_tcp_auto
device_call dg1022 identify save=idn
print "IDN = ${idn}"
close dg_tcp_auto
```

This requires the VISA backend to return a TCPIP resource. It may not discover instruments across routed subnets.

### Explicit VISA-to-TCP fallback

Fallback is opt-in and occurs only when VISA discovery fails before a usable resource is opened:

```text
connection dg1022_auto type=visa resource_prefix=TCPIP fallback_type=tcp fallback_host=10.0.0.14 read_timeout=5s
device dg1022 driver=dg1022z connection=dg1022_auto
discover dg1022_auto
open dg1022_auto
device_call dg1022 identify save=idn
print "IDN = ${idn}"
close dg1022_auto
```

LSQ does not silently change transports after a successful connection or command failure.

### Switching from TCP to USB VISA

Only one interface should control a physical DG1022Z at a time:

```text
connection dg_tcp type=tcp host=10.0.0.14
device dg_tcp_device driver=dg1022z connection=dg_tcp
discover dg_tcp
open dg_tcp
device_call dg_tcp_device identify save=tcp_idn
close dg_tcp

connection dg_usb type=visa resource_prefix=USB
device dg_usb_device driver=dg1022z connection=dg_usb
discover dg_usb
open dg_usb
device_call dg_usb_device identify save=usb_idn
print "USB IDN = ${usb_idn}"
close dg_usb
```

## Device drivers

Device-specific communication settings belong in the driver. The script contains the test procedure.

## PSP-405

The PSP-405 driver is in `lsq/devices/psp405.py`. Its complete command catalog is in `lsq/devices/catalogs/psp405.json`. The manual specifies 2400 baud, 8 data bits, no parity, 1 stop bit, no flow control, command termination with CR, and response termination with CRLF or CRCRLF. The custom GTL-232A cable is required.

After successful identification, the verified port is saved in the connection state file. The cached port is probed first; if it fails, eligible ports are scanned. The cache is never trusted without a successful identification response.

```text
lsq examples/serial_diagnostic.lsq
lsq examples/psp405_test.lsq
```

The driver exposes typed get methods for status, output voltage, output current, output power, voltage limit, current limit, power limit, flags, positive offset, negative offset, and offset status. It also exposes reusable set methods for direct settings, incremental adjustments, maximum limits, step mode, output state, EEPROM save, and offset adjustments.

## Rigol DG1022Z

The DG1022Z driver is in `lsq/devices/dg1022z.py`. Its catalog is in `lsq/devices/catalogs/dg1022z.json`, and its generated API reference is in `docs/devices/dg1022z.md`.

Supported interfaces are USB VISA, LAN VISA, and raw LAN SCPI TCP. The driver identifies the instrument with `*IDN?`. Use `set_*` methods to change settings and `get_*` methods to read settings. Use `channel=2` for channel 2 methods.

The driver provides typed waveform, frequency, amplitude, offset, output, burst, arbitrary-waveform, status, identification, and system-error methods. Catalog commands are also available through the generic `set_command` and `get_command` methods or generated typed methods.

The command:

```text
:SYSTem:KLOCk[:STATe] OFF
```

unlocks the front-panel keys. The DG1022Z driver's `close()` method sends this command before closing the active connection. This is separate from returning the instrument from remote control to local control; the manual identifies the front-panel `Help` key as the local-mode action.

Run the USB VISA test:

```text
lsq examples/dg1022z_test.lsq --verbosity verbose
```

Run the raw TCP tests:

```text
lsq examples/dg1022z_tcp_ip.lsq --verbosity verbose
lsq examples/dg1022z_tcp_auto_discovery.lsq --verbosity verbose
lsq examples/dg1022z_tcp_to_usb.lsq --verbosity verbose
```

## Agilent E3634A

The E3634A driver is in `lsq/devices/e3634a.py`. The connected instrument uses 9600 baud, 8 data bits, no parity, 2 stop bits, and DTR/DSR handshaking. SCPI commands terminate with LF. Discovery sends `SYST:REM` before `*IDN?`. The driver clears stale status, disables output during startup, and returns the supply to local mode during shutdown.

```text
lsq examples/e3634a_test.lsq --verbosity verbose
```

## Tektronix MSO2024B

The MSO2024B driver is in `lsq/devices/mso2024b.py`. It uses USB VISA discovery and identifies the oscilloscope with `*IDN?`. The catalog contains 640 command syntax entries extracted from the Tektronix MSO2000B/DPO2000 programmer manual. The driver provides typed channel, acquisition, trigger, measurement, waveform, screenshot, and file operations.

```text
lsq examples/mso2024b_test.lsq --verbosity verbose
```

## Rigol DP712

The DP712 driver is in `lsq/devices/dp712.py`. It uses the rear-panel RS-232 interface with 9600 baud, 8 data bits, no parity, 1 stop bit, no flow control, and LF command termination. Discovery identifies the instrument with `*IDN?`; startup enters remote mode with `SYST:REM`, and shutdown restores local operation.

```text
lsq examples/dp712_test.lsq --verbosity verbose
```

## Catalog documentation and tests

Regenerate device API references after changing a catalog:

```text
python tools/generate_device_docs.py
```

Validate catalog and driver synchronization:

```text
lsq --validate-catalog
```

Run all non-hardware tests:

```text
python -m unittest discover -v
```
