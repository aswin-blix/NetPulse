NETPULSE 1.0 — Your connection, at a glance
Windows 10/11, 64-bit

GET STARTED
Double-click NetPulse.exe. No Python installation or administrator access is needed.
The widget opens near the bottom-right corner of your desktop.
Drag it anywhere. Your position and preferences are remembered.

MAKE IT YOURS
Click the sliders icon in the upper-right, or right-click the widget.
Choose Midnight, Daylight, or Follow Windows; four accent colors; Mini,
Compact, or Comfortable size; transparency; refresh speed; and bits/bytes.
Use Corner radius to choose 0–24 px, from square to rounded corners.
The shape changes immediately and is remembered. The default is 12 px;
Mini mode limits the effective radius to half its height for a pill shape.
Toggle Always on top or the little activity graphs.
Mini mode shows only the two speed readings in a 226 x 38 pixel strip.
It has no name header or buttons; right-click it for customization or exit.
Click Done to close settings. Changes apply immediately.
Reset defaults restores the display preferences but keeps your chosen adapter
and screen position.

QUICK CONTROLS
Drag the body: move the widget.
Sliders icon / Ctrl+comma: customize.
Right-click: quick theme, always-on-top, help and exit options.
X / Ctrl+Q / right-click > Exit: close NetPulse.
Escape: close settings or a tooltip.
Keyboard shortcuts work while the app has focus; they are not global hotkeys.
Only one widget runs per Windows session.

WHAT THE NUMBERS MEAN
Download and upload show current network adapter traffic. An idle connection
will show zero even if your broadband plan is fast. This is not a speed test.
Mbps means megabits per second; MB/s means megabytes per second.
8 Mbps = 1 MB/s. Units automatically adapt using decimal (1000-based) scales.

The app reads Windows' 64-bit byte counters and divides their difference by
the actual elapsed time. Rates are interval averages, not smoothed estimates.
Local-network transfers and network protocol overhead can also be included;
the app cannot isolate Internet-only traffic from ordinary adapter counters.

Auto mode adds connected physical adapters and excludes loopback, virtual,
VPN and duplicate filter layers. This avoids counting the same transfer at
both physical and virtual layers. Select an individual adapter when needed.
If Auto cannot find physical hardware (for example, in a virtual machine),
choose an adapter in settings. A connected adapter does not prove Internet
access. "Measuring" briefly appears after launch, reconnects, counter resets,
or long pauses; this prevents misleading spikes.

Graphs show up to 48 recent readings, independently scaled per direction.
Their duration depends on the chosen refresh interval. Mini mode hides graphs.

PRIVACY AND STORAGE
No account, telemetry, advertising, remote service, or test downloads.
The app does not request administrative access or add itself to startup.
Settings are stored in %LOCALAPPDATA%\NetPulse\settings.json.
Close NetPulse and delete that file to reset all preferences.
Delete the portable app to remove it; no installer is used.

SOURCE AND VALIDATION
The source folder contains the editable Python app, tests, and build instructions.
The previews folder contains screenshots from the actual app using sample rates.
See source\BUILDING.txt for implementation and verification details.
