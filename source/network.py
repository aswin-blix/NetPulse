"""Network byte counters and sampling, independent of the desktop UI.

Windows IP Helper supplies cumulative, unsigned 64-bit adapter octet counts.
We measure their change over actual monotonic time; this is current adapter
traffic (including LAN traffic), not a test of the connection's capacity.
"""

from __future__ import annotations

import ctypes
import math
import sys
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Adapter:
    id: str
    name: str
    received: int
    sent: int
    is_up: bool
    # Eligible physical hardware: Windows filter/endpoint rows are excluded.
    hardware: bool
    loopback: bool
    tunnel: bool


@dataclass(frozen=True)
class Reading:
    download: float = 0.0
    upload: float = 0.0
    status: str = "warming"
    names: tuple[str, ...] = ()


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _MIB_IF_ROW2(ctypes.Structure):
    # Fixed-width WCHAR arrays preserve the Windows ABI when tests run elsewhere.
    # Source: learn.microsoft.com/windows/win32/api/netioapi/ns-netioapi-mib_if_row2
    _fields_ = [
        ("InterfaceLuid", ctypes.c_uint64),
        ("InterfaceIndex", ctypes.c_uint32),
        ("InterfaceGuid", _GUID),
        ("Alias", ctypes.c_uint16 * 257),
        ("Description", ctypes.c_uint16 * 257),
        ("PhysicalAddressLength", ctypes.c_uint32),
        ("PhysicalAddress", ctypes.c_ubyte * 32),
        ("PermanentPhysicalAddress", ctypes.c_ubyte * 32),
        ("Mtu", ctypes.c_uint32),
        ("Type", ctypes.c_uint32),
        ("TunnelType", ctypes.c_uint32),
        ("MediaType", ctypes.c_uint32),
        ("PhysicalMediumType", ctypes.c_uint32),
        ("AccessType", ctypes.c_uint32),
        ("DirectionType", ctypes.c_uint32),
        ("InterfaceAndOperStatusFlags", ctypes.c_ubyte),
        ("OperStatus", ctypes.c_uint32),
        ("AdminStatus", ctypes.c_uint32),
        ("MediaConnectState", ctypes.c_uint32),
        ("NetworkGuid", _GUID),
        ("ConnectionType", ctypes.c_uint32),
        ("TransmitLinkSpeed", ctypes.c_uint64),
        ("ReceiveLinkSpeed", ctypes.c_uint64),
        ("InOctets", ctypes.c_uint64),
        ("InUcastPkts", ctypes.c_uint64),
        ("InNUcastPkts", ctypes.c_uint64),
        ("InDiscards", ctypes.c_uint64),
        ("InErrors", ctypes.c_uint64),
        ("InUnknownProtos", ctypes.c_uint64),
        ("InUcastOctets", ctypes.c_uint64),
        ("InMulticastOctets", ctypes.c_uint64),
        ("InBroadcastOctets", ctypes.c_uint64),
        ("OutOctets", ctypes.c_uint64),
        ("OutUcastPkts", ctypes.c_uint64),
        ("OutNUcastPkts", ctypes.c_uint64),
        ("OutDiscards", ctypes.c_uint64),
        ("OutErrors", ctypes.c_uint64),
        ("OutUcastOctets", ctypes.c_uint64),
        ("OutMulticastOctets", ctypes.c_uint64),
        ("OutBroadcastOctets", ctypes.c_uint64),
        ("OutQLen", ctypes.c_uint64),
    ]


class _MIB_IF_TABLE2(ctypes.Structure):
    _fields_ = [("NumEntries", ctypes.c_uint32), ("Table", _MIB_IF_ROW2 * 1)]


def _wide_text(value: ctypes.Array) -> str:
    return bytes(value).decode("utf-16-le", errors="replace").split("\0", 1)[0]


def _adapter_from_row(row: _MIB_IF_ROW2) -> Adapter:
    flags = row.InterfaceAndOperStatusFlags
    raw_guid = bytes(row.InterfaceGuid)
    adapter_id = str(uuid.UUID(bytes_le=raw_guid)) if any(raw_guid) else f"luid:{row.InterfaceLuid}"
    return Adapter(
        id=adapter_id,
        name=_wide_text(row.Alias)
        or _wide_text(row.Description)
        or f"Adapter {row.InterfaceIndex}",
        received=int(row.InOctets),
        sent=int(row.OutOctets),
        is_up=row.OperStatus == 1 and row.MediaConnectState != 2 and not (flags & 0x78),
        hardware=bool(flags & 0x01) and not bool(flags & 0x82),
        loopback=row.Type == 24 or row.AccessType == 1,
        tunnel=row.Type == 131 or row.TunnelType != 0,
    )


class WindowsNetworkReader:
    """Read Windows adapter counters without a subprocess or third-party module.

    Raises OSError when counters cannot be read. The caller should display an
    unavailable state and clear the RateSampler baseline before retrying.
    """

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("Live network counters require Windows.")
        self._api = ctypes.WinDLL("iphlpapi.dll", use_last_error=True)
        self._api.GetIfTable2.argtypes = [ctypes.POINTER(ctypes.POINTER(_MIB_IF_TABLE2))]
        self._api.GetIfTable2.restype = ctypes.c_uint32
        self._api.FreeMibTable.argtypes = [ctypes.c_void_p]
        self._api.FreeMibTable.restype = None

    def read(self) -> list[Adapter]:
        table = ctypes.POINTER(_MIB_IF_TABLE2)()
        try:
            result = self._api.GetIfTable2(ctypes.byref(table))
            if result:
                raise ctypes.WinError(result)
            if not table:
                raise OSError("Windows returned no network table.")
            count = table.contents.NumEntries
            if count > 65536:
                raise OSError("Windows returned an invalid network table.")
            # NumEntries is followed by alignment padding, then the row array.
            start = ctypes.addressof(table.contents) + _MIB_IF_TABLE2.Table.offset
            rows = (_MIB_IF_ROW2 * count).from_address(start)
            # Filter/endpoint rows are implementation layers, not useful adapter
            # choices. Several repeat their parent adapter's complete counters.
            adapters = [
                _adapter_from_row(row)
                for row in rows
                if not (row.InterfaceAndOperStatusFlags & 0x82)
            ]
            return sorted(adapters, key=lambda adapter: (adapter.name.casefold(), adapter.id))
        finally:
            if table:
                self._api.FreeMibTable(table)


class RateSampler:
    """Calculate rates using exact elapsed time, resetting on discontinuities."""

    MAX_GAP_SECONDS = 10.0

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._previous: dict[str, tuple[int, int]] = {}
        self._time: float | None = None
        self._selection: str | None = None

    def update(self, adapters: list[Adapter], now: float, selection: str = "auto") -> Reading:
        if not isinstance(now, (int, float)) or not math.isfinite(now) or now < 0:
            self.reset()
            return Reading(status="unavailable")

        if selection == "auto":
            candidates = [a for a in adapters if a.hardware and not a.loopback and not a.tunnel]
        else:
            candidates = [a for a in adapters if a.id == selection]
        active = sorted((a for a in candidates if a.is_up), key=lambda adapter: adapter.id)
        if not active:
            self.reset()
            return Reading(status="offline" if candidates else "unavailable")

        names = tuple(a.name for a in active)
        current = {a.id: (a.received, a.sent) for a in active}
        if len(current) != len(active) or any(
            type(value) is not int or not 0 <= value <= (1 << 64) - 1
            for counts in current.values()
            for value in counts
        ):
            self.reset()
            return Reading(status="unavailable", names=names)

        elapsed = now - self._time if self._time is not None else 0.0
        discontinuity = (
            self._selection != selection
            or current.keys() != self._previous.keys()
            or not 0 < elapsed <= self.MAX_GAP_SECONDS
            or any(
                new < old
                for adapter_id, counts in current.items()
                for new, old in zip(counts, self._previous.get(adapter_id, counts), strict=True)
            )
        )
        if discontinuity:
            reading = Reading(status="warming", names=names)
        else:
            download = (
                sum(counts[0] - self._previous[key][0] for key, counts in current.items()) / elapsed
            )
            upload = (
                sum(counts[1] - self._previous[key][1] for key, counts in current.items()) / elapsed
            )
            if math.isfinite(download) and math.isfinite(upload):
                reading = Reading(download, upload, "live", names)
            else:
                reading = Reading(status="warming", names=names)
        self._previous = current
        self._time = now
        self._selection = selection
        return reading


def format_rate(bytes_per_second: float, units: str = "bits") -> tuple[str, str]:
    """Return a compact value and SI unit; values above 999 G show ``999+``."""
    if units not in {"bits", "bytes"}:
        raise ValueError("units must be 'bits' or 'bytes'")
    try:
        value = float(bytes_per_second)
    except (TypeError, ValueError, OverflowError):
        value = 0.0
    if not math.isfinite(value) or value < 0:
        value = 0.0
    suffixes = (
        ("bps", "Kbps", "Mbps", "Gbps") if units == "bits" else ("B/s", "KB/s", "MB/s", "GB/s")
    )
    # Bound before multiplying to avoid overflow for invalid external values.
    if value >= (999.5e9 / (8 if units == "bits" else 1)):
        return "999+", suffixes[-1]
    value *= 8 if units == "bits" else 1
    index = 0
    while value >= 999.5 and index < len(suffixes) - 1:
        value /= 1000
        index += 1
    decimals = 2 if 0 < value < 10 else 1 if value < 100 else 0
    text = f"{value:.{decimals}f}" if value else "0"
    return text, suffixes[index]
