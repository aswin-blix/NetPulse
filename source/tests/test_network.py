"""Synthetic measurement tests: do not depend on the host's network traffic."""

import ctypes
import math
import sys
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from network import (
    _MIB_IF_ROW2,
    _MIB_IF_TABLE2,
    Adapter,
    RateSampler,
    WindowsNetworkReader,
    _adapter_from_row,
    format_rate,
)


def adapter(received=0, sent=0, **kwargs):
    return replace(Adapter("wifi", "Wi-Fi", received, sent, True, True, False, False), **kwargs)


class RateSamplerTests(unittest.TestCase):
    def setUp(self):
        self.sampler = RateSampler()

    def test_initial_read_warms_and_elapsed_time_is_exact(self):
        self.assertEqual(self.sampler.update([adapter(100, 200)], 5).status, "warming")
        result = self.sampler.update([adapter(850, 500)], 6.5)
        self.assertEqual((result.download, result.upload, result.status), (500, 200, "live"))
        self.assertEqual(result.names, ("Wi-Fi",))

    def test_idle_is_live_zero(self):
        self.sampler.update([adapter(20, 30)], 0)
        result = self.sampler.update([adapter(20, 30)], 1)
        self.assertEqual((result.download, result.upload, result.status), (0, 0, "live"))

    def test_auto_combines_physical_adapters_only(self):
        originals = [
            adapter(),
            adapter(id="ethernet", name="Ethernet"),
            adapter(id="vpn", hardware=False),
            adapter(id="loop", loopback=True),
            adapter(id="tunnel", tunnel=True),
            adapter(id="down", is_up=False),
        ]
        self.sampler.update(originals, 0)
        result = self.sampler.update([replace(a, received=1000, sent=500) for a in originals], 2)
        self.assertEqual((result.download, result.upload), (1000, 500))
        self.assertEqual(result.names, ("Ethernet", "Wi-Fi"))

    def test_virtual_only_is_unavailable_but_manual_selection_works(self):
        vpn = adapter(id="vpn", hardware=False, tunnel=True)
        self.assertEqual(self.sampler.update([vpn], 0).status, "unavailable")
        self.assertEqual(self.sampler.update([vpn], 1, "vpn").status, "warming")
        result = self.sampler.update([replace(vpn, received=100)], 2, "vpn")
        self.assertEqual((result.download, result.status), (100, "live"))

    def test_offline_and_missing_adapter(self):
        self.assertEqual(self.sampler.update([adapter(is_up=False)], 1).status, "offline")
        self.assertEqual(self.sampler.update([], 2).status, "unavailable")
        self.assertEqual(self.sampler.update([adapter()], 3, "missing").status, "unavailable")

    def test_disconnect_and_reconnect_do_not_accumulate(self):
        self.sampler.update([adapter(100)], 1)
        self.sampler.update([adapter(500, is_up=False)], 2)
        self.assertEqual(self.sampler.update([adapter(900)], 3).status, "warming")
        self.assertEqual(self.sampler.update([adapter(950)], 4).download, 50)

    def test_adapter_set_changes_warm_again(self):
        self.sampler.update([adapter(100)], 0)
        self.assertEqual(
            self.sampler.update([adapter(500), adapter(1000, id="eth")], 1).status, "warming"
        )
        self.assertEqual(self.sampler.update([adapter(600)], 2).status, "warming")
        self.assertEqual(self.sampler.update([adapter(650)], 3).download, 50)

    def test_selection_change_resets_even_with_same_adapter(self):
        self.sampler.update([adapter(100)], 0)
        self.assertEqual(self.sampler.update([adapter(200)], 1, "wifi").status, "warming")

    def test_counter_reset_in_either_direction_discards_interval(self):
        for current in [adapter(90, 250), adapter(150, 190)]:
            with self.subTest(current=current):
                self.sampler.reset()
                self.sampler.update([adapter(100, 200)], 1)
                result = self.sampler.update([current], 2)
                self.assertEqual((result.download, result.upload, result.status), (0, 0, "warming"))

    def test_large_counter_precision_uses_integer_subtraction(self):
        self.sampler.update([adapter(2**63, 2**63)], 0)
        result = self.sampler.update([adapter(2**63 + 5, 2**63 + 7)], 1)
        self.assertEqual((result.download, result.upload), (5, 7))

    def test_suspend_gap_resets_then_recovers(self):
        self.sampler.update([adapter(100)], 0)
        self.assertEqual(self.sampler.update([adapter(10000)], 10.001).status, "warming")
        self.assertAlmostEqual(self.sampler.update([adapter(10050)], 11.001).download, 50)

    def test_maximum_allowed_interval(self):
        self.sampler.update([adapter()], 0)
        self.assertEqual(self.sampler.update([adapter(1000)], 10).download, 100)

    def test_duplicate_or_backwards_time_does_not_spike(self):
        for timestamp in (1, 0.5):
            with self.subTest(timestamp=timestamp):
                self.sampler.reset()
                self.sampler.update([adapter(100)], 1)
                self.assertEqual(self.sampler.update([adapter(200)], timestamp).status, "warming")

    def test_invalid_timestamp_invalidates_baseline(self):
        for timestamp in (math.inf, math.nan, -1, "bad", None):
            with self.subTest(timestamp=timestamp):
                self.sampler.update([adapter(100)], 1)
                self.assertEqual(
                    self.sampler.update([adapter(200)], timestamp).status, "unavailable"
                )
                self.assertEqual(self.sampler.update([adapter(250)], 2).status, "warming")

    def test_invalid_counter_or_duplicate_adapter_is_unavailable(self):
        for current in (
            [adapter(-1)],
            [adapter(float("nan"))],
            [adapter(2**64)],
            [adapter(), adapter()],
        ):
            with self.subTest(current=current):
                self.assertEqual(self.sampler.update(current, 1).status, "unavailable")


class FormattingTests(unittest.TestCase):
    def test_bits_use_decimal_units(self):
        self.assertEqual(format_rate(0), ("0", "bps"))
        self.assertEqual(format_rate(125), ("1.00", "Kbps"))
        self.assertEqual(format_rate(1_550_000), ("12.4", "Mbps"))
        self.assertEqual(format_rate(125_000_000), ("1.00", "Gbps"))

    def test_bytes_use_decimal_units(self):
        self.assertEqual(format_rate(1000, "bytes"), ("1.00", "KB/s"))
        self.assertEqual(format_rate(12_400_000, "bytes"), ("12.4", "MB/s"))

    def test_rounding_promotes_units(self):
        self.assertEqual(format_rate(999.9, "bytes"), ("1.00", "KB/s"))
        self.assertEqual(format_rate(999_900, "bytes"), ("1.00", "MB/s"))

    def test_invalid_and_extreme_values_remain_bounded(self):
        for value in (-100, math.nan, math.inf, None, "bad"):
            self.assertEqual(format_rate(value), ("0", "bps"))
        self.assertEqual(format_rate(1e308), ("999+", "Gbps"))
        self.assertEqual(format_rate(1e308, "bytes"), ("999+", "GB/s"))
        with self.assertRaises(ValueError):
            format_rate(1, "binary")


class WindowsLayoutTests(unittest.TestCase):
    def test_documented_win64_abi_offsets(self):
        self.assertEqual(ctypes.sizeof(_MIB_IF_ROW2), 1352)
        self.assertEqual(_MIB_IF_TABLE2.Table.offset, 8)
        for field, expected in {
            "InterfaceGuid": 12,
            "Alias": 28,
            "Description": 542,
            "InterfaceAndOperStatusFlags": 1152,
            "OperStatus": 1156,
            "InOctets": 1208,
            "OutOctets": 1280,
        }.items():
            self.assertEqual(getattr(_MIB_IF_ROW2, field).offset, expected, field)

    def make_row(self):
        row = _MIB_IF_ROW2()
        row.InterfaceLuid = 123
        row.OperStatus = 1
        row.MediaConnectState = 1
        row.InterfaceAndOperStatusFlags = 0x05
        row.InOctets = 2**48 + 100
        row.OutOctets = 2**49 + 200
        row.Type = 71
        text = "Wi-Fi \u6d4b\u8bd5".encode("utf-16-le")
        ctypes.memmove(ctypes.addressof(row) + _MIB_IF_ROW2.Alias.offset, text, len(text))
        return row

    def test_row_preserves_unicode_and_full_counter_precision(self):
        result = _adapter_from_row(self.make_row())
        self.assertEqual(result.name, "Wi-Fi \u6d4b\u8bd5")
        self.assertEqual(result.id, "luid:123")
        self.assertEqual((result.received, result.sent), (2**48 + 100, 2**49 + 200))
        self.assertTrue(result.hardware and result.is_up)

    def test_guid_is_persistent_id_instead_of_interface_index(self):
        row = self.make_row()
        identifier = uuid.UUID("12345678-9abc-def0-1234-56789abcdef0")
        ctypes.memmove(
            ctypes.addressof(row) + _MIB_IF_ROW2.InterfaceGuid.offset, identifier.bytes_le, 16
        )
        self.assertEqual(_adapter_from_row(row).id, str(identifier))
        row.InterfaceIndex += 100
        self.assertEqual(_adapter_from_row(row).id, str(identifier))

    def test_filter_and_endpoint_are_not_auto_hardware(self):
        for excluded_flag in (0x02, 0x80):
            row = self.make_row()
            row.InterfaceAndOperStatusFlags |= excluded_flag
            self.assertFalse(_adapter_from_row(row).hardware)

    def test_paused_disconnected_and_unavailable_flags(self):
        for unavailable_flag in (0x08, 0x10, 0x20, 0x40):
            row = self.make_row()
            row.InterfaceAndOperStatusFlags |= unavailable_flag
            self.assertFalse(_adapter_from_row(row).is_up)

    def test_loopback_and_tunnel_classification(self):
        row = self.make_row()
        row.Type = 24
        self.assertTrue(_adapter_from_row(row).loopback)
        row.Type = 131
        self.assertTrue(_adapter_from_row(row).tunnel)


class ReaderTests(unittest.TestCase):
    def make_reader(self, error=0, null=False, count=3):
        class Table(ctypes.Structure):
            _fields_ = [("NumEntries", ctypes.c_uint32), ("Table", _MIB_IF_ROW2 * 3)]

        storage = Table()
        storage.NumEntries = count
        for index, row in enumerate(storage.Table):
            row.InterfaceLuid = index + 1
            row.InterfaceIndex = index + 1
            row.OperStatus = 1
        # One adapter, one filter and one endpoint; only the adapter is useful.
        storage.Table[0].InterfaceAndOperStatusFlags = 0x01
        storage.Table[1].InterfaceAndOperStatusFlags = 0x03
        storage.Table[2].InterfaceAndOperStatusFlags = 0x81

        class FakeApi:
            freed = False

            def GetIfTable2(self, output):
                if not null:
                    ctypes.cast(output, ctypes.POINTER(ctypes.POINTER(_MIB_IF_TABLE2)))[0] = (
                        ctypes.cast(ctypes.pointer(storage), ctypes.POINTER(_MIB_IF_TABLE2))
                    )
                return error

            def FreeMibTable(self, pointer):
                self.freed = True

        reader = WindowsNetworkReader.__new__(WindowsNetworkReader)
        reader._api = FakeApi()
        return reader

    def test_reader_filters_duplicate_layers_and_frees_native_memory(self):
        reader = self.make_reader()
        adapters = reader.read()
        self.assertEqual([a.id for a in adapters], ["luid:1"])
        self.assertTrue(reader._api.freed)

    def test_api_error_frees_returned_buffer(self):
        reader = self.make_reader(error=5)
        with (
            patch("network.ctypes.WinError", return_value=OSError("denied"), create=True),
            self.assertRaises(OSError),
        ):
            reader.read()
        self.assertTrue(reader._api.freed)

    def test_null_table_is_reported_without_freeing_null(self):
        reader = self.make_reader(null=True)
        with self.assertRaises(OSError):
            reader.read()
        self.assertFalse(reader._api.freed)

    def test_invalid_count_is_reported_and_buffer_is_freed(self):
        reader = self.make_reader(count=65537)
        with self.assertRaises(OSError):
            reader.read()
        self.assertTrue(reader._api.freed)


if __name__ == "__main__":
    unittest.main()
