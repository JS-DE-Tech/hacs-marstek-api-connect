"""Home Assistant-independent tests for the UDP client."""
from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest


INTEGRATION = (
    Path(__file__).parents[1]
    / "custom_components"
    / "hacs_marstek_api_connect"
)
PACKAGE = "marstek_udp_test"

package = types.ModuleType(PACKAGE)
package.__path__ = [str(INTEGRATION)]
sys.modules[PACKAGE] = package

for module_name in ("const", "udp_client"):
    spec = importlib.util.spec_from_file_location(
        f"{PACKAGE}.{module_name}", INTEGRATION / f"{module_name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

UDP = sys.modules[f"{PACKAGE}.udp_client"]


class _FakeTransport:
    """Record whether a test transport was closed."""

    def __init__(self) -> None:
        self.closed = False
        self.payloads: list[bytes] = []

    def sendto(self, payload: bytes) -> None:
        """Record a datagram without sending it."""
        self.payloads.append(payload)

    def close(self) -> None:
        """Record transport cleanup."""
        self.closed = True


class _TimeoutProtocol:
    """Simulate a device that never returns a response."""

    async def get_response(self) -> dict:
        """Raise the timeout observed by the client."""
        raise asyncio.TimeoutError


class _FakeLoop:
    """Create an inspectable transport for every retry."""

    def __init__(self) -> None:
        self.transports: list[_FakeTransport] = []

    async def create_datagram_endpoint(self, *_args, **_kwargs):
        """Return a new transport and a timeout protocol."""
        transport = _FakeTransport()
        self.transports.append(transport)
        return transport, _TimeoutProtocol()


class _ResponseProtocol:
    """Return one predefined UDP response."""

    def __init__(self, response: dict) -> None:
        self.response = response

    async def get_response(self) -> dict:
        return self.response


class _ResponseLoop:
    """Create a transport with one predefined response."""

    def __init__(self, response: dict) -> None:
        self.response = response
        self.transport = _FakeTransport()

    async def create_datagram_endpoint(self, *_args, **_kwargs):
        return self.transport, _ResponseProtocol(self.response)


class UDPClientTests(unittest.IsolatedAsyncioTestCase):
    """Verify request serialization and transport cleanup."""

    async def test_requests_are_serialized(self) -> None:
        client = UDP.MarstekUDPClient("192.0.2.1")
        active_requests = 0
        maximum_active_requests = 0

        async def fake_request(_method: str, _params=None) -> dict:
            nonlocal active_requests, maximum_active_requests
            active_requests += 1
            maximum_active_requests = max(
                maximum_active_requests, active_requests
            )
            await asyncio.sleep(0.01)
            active_requests -= 1
            return {}

        client._send_request_locked = fake_request
        await asyncio.gather(
            client._send_request("first"),
            client._send_request("second"),
            client._send_request("third"),
        )

        self.assertEqual(1, maximum_active_requests)

    async def test_every_transport_is_closed_after_final_timeout(self) -> None:
        client = UDP.MarstekUDPClient("192.0.2.1", timeout=0.1)
        fake_loop = _FakeLoop()
        original_get_running_loop = UDP.asyncio.get_running_loop
        UDP.asyncio.get_running_loop = lambda: fake_loop
        try:
            with self.assertRaises(asyncio.TimeoutError):
                await client._send_request("ES.GetStatus", {"id": 0})
        finally:
            UDP.asyncio.get_running_loop = original_get_running_loop

        self.assertEqual(2, len(fake_loop.transports))
        self.assertTrue(
            all(transport.closed for transport in fake_loop.transports)
        )

    async def test_successful_request_returns_result_and_closes_transport(
        self,
    ) -> None:
        client = UDP.MarstekUDPClient("192.0.2.1", timeout=0.1)
        fake_loop = _ResponseLoop({"id": 0, "result": {"bat_soc": 72}})
        original_get_running_loop = UDP.asyncio.get_running_loop
        UDP.asyncio.get_running_loop = lambda: fake_loop
        try:
            result = await client._send_request(
                "ES.GetStatus", {"id": 0}
            )
        finally:
            UDP.asyncio.get_running_loop = original_get_running_loop

        self.assertEqual({"bat_soc": 72}, result)
        self.assertTrue(fake_loop.transport.closed)
        payload = json.loads(fake_loop.transport.payloads[0])
        self.assertEqual("ES.GetStatus", payload["method"])
        self.assertEqual({"id": 0}, payload["params"])

    async def test_rpc_error_is_raised_and_transport_is_closed(self) -> None:
        client = UDP.MarstekUDPClient("192.0.2.1", timeout=0.1)
        fake_loop = _ResponseLoop(
            {"id": 0, "error": {"message": "Rejected", "code": -1}}
        )
        original_get_running_loop = UDP.asyncio.get_running_loop
        UDP.asyncio.get_running_loop = lambda: fake_loop
        try:
            with self.assertRaisesRegex(Exception, "Rejected"):
                await client._send_request("ES.SetMode")
        finally:
            UDP.asyncio.get_running_loop = original_get_running_loop

        self.assertTrue(fake_loop.transport.closed)

    async def test_mode_payloads_match_the_device_protocol(self) -> None:
        client = UDP.MarstekUDPClient("192.0.2.1")
        calls: list[tuple[str, dict | None]] = []

        async def record(method: str, params=None) -> dict:
            calls.append((method, params))
            return {"set_result": True}

        client._send_request = record
        await client.set_mode("Auto")
        await client.set_mode("AI")
        await client.set_passive_mode(-500, 600)

        self.assertEqual(
            {"id": 0, "config": {"mode": "Auto", "auto_cfg": {"enable": 1}}},
            calls[0][1],
        )
        self.assertEqual(
            {"id": 0, "config": {"mode": "AI", "ai_cfg": {"enable": 1}}},
            calls[1][1],
        )
        self.assertEqual(
            {
                "id": 0,
                "config": {
                    "mode": "Passive",
                    "passive_cfg": {"power": -500, "cd_time": 600},
                },
            },
            calls[2][1],
        )

    async def test_read_methods_use_the_documented_rpc_names(self) -> None:
        client = UDP.MarstekUDPClient("192.0.2.1")
        calls: list[tuple[str, dict | None]] = []

        async def record(method: str, params=None) -> dict:
            calls.append((method, params))
            return {}

        client._send_request = record
        await client.get_device_info()
        await client.get_battery_status()
        await client.get_wifi_status()
        await client.get_ble_status()
        await client.get_energy_system_status()
        await client.get_energy_system_mode()
        await client.get_energy_meter_status()
        await client.get_schedule()
        self.assertEqual(
            [
                ("Marstek.GetDevice", {"ble_mac": "0"}),
                ("Bat.GetStatus", {"id": 0}),
                ("Wifi.GetStatus", {"id": 0}),
                ("BLE.GetStatus", {"id": 0}),
                ("ES.GetStatus", {"id": 0}),
                ("ES.GetMode", {"id": 0}),
                ("EM.GetStatus", {"id": 0}),
                ("ES.GetSchedule", {"id": 0}),
            ],
            calls,
        )

    async def test_manual_schedule_updates_and_pads_slots(self) -> None:
        client = UDP.MarstekUDPClient("192.0.2.1")
        client.get_schedule = lambda: _async_result(
            {"schedules": [{"time_num": 0, "enable": 0}]}
        )
        sent: list[list[dict]] = []

        async def set_schedule(schedules: list[dict]) -> dict:
            sent.append(schedules)
            return {"set_result": True}

        client.set_schedule = set_schedule
        result = await client.set_manual_schedule(
            3, "08:00", "10:00", 31, -500, True
        )

        self.assertEqual({"set_result": True}, result)
        self.assertEqual(10, len(sent[0]))
        self.assertEqual(
            {
                "time_num": 3,
                "start_time": "08:00",
                "end_time": "10:00",
                "week_set": 31,
                "power": -500,
                "enable": 1,
            },
            sent[0][3],
        )

    async def test_manual_schedule_falls_back_when_readback_fails(self) -> None:
        client = UDP.MarstekUDPClient("192.0.2.1")

        async def fail_readback() -> dict:
            raise TimeoutError

        fallback: list[tuple[str, dict | None]] = []

        async def set_mode(mode: str, manual_cfg=None, passive_cfg=None):
            fallback.append((mode, manual_cfg))
            return {"set_result": True}

        client.get_schedule = fail_readback
        client.set_mode = set_mode
        await client.set_manual_schedule(
            2, "11:00", "12:00", 127, 600, False
        )

        self.assertEqual("Manual", fallback[0][0])
        self.assertEqual(0, fallback[0][1]["enable"])
        self.assertEqual(600, fallback[0][1]["power"])

    async def test_manual_schedule_rejects_an_invalid_slot(self) -> None:
        client = UDP.MarstekUDPClient("192.0.2.1")
        with self.assertRaises(ValueError):
            await client.set_manual_schedule(
                10, "08:00", "10:00", 127, -500, True
            )

    async def test_clear_schedules_reports_rejected_slots(self) -> None:
        client = UDP.MarstekUDPClient("192.0.2.1")
        calls: list[dict] = []

        async def set_mode(mode: str, manual_cfg=None, passive_cfg=None):
            calls.append(manual_cfg)
            slot = manual_cfg["time_num"]
            if slot == 4:
                raise TimeoutError
            return {"set_result": slot != 7}

        client.set_mode = set_mode
        result = await client.clear_all_manual_schedules()

        self.assertEqual(10, len(calls))
        self.assertEqual(8, result["success_count"])
        self.assertEqual([4, 7], result["failed_slots"])
        self.assertTrue(all(call["enable"] == 0 for call in calls))

    async def test_boolean_control_payloads(self) -> None:
        client = UDP.MarstekUDPClient("192.0.2.1")
        calls: list[tuple[str, dict | None]] = []

        async def record(method: str, params=None) -> dict:
            calls.append((method, params))
            return {"set_result": True}

        client._send_request = record
        await client.set_ble_adv(True)
        await client.set_ble_adv(False)
        await client.set_led_ctrl(True)
        await client.set_led_ctrl(False)
        self.assertEqual(
            [
                ("Ble.Adv", {"enable": 0}),
                ("Ble.Adv", {"enable": 1}),
                ("Led.Ctrl", {"state": 1}),
                ("Led.Ctrl", {"state": 0}),
            ],
            calls,
        )

    def test_discovery_targets_are_unique_and_include_subnets(self) -> None:
        targets = UDP.MarstekUDPClient._get_discovery_targets(
            30000, {"192.168.5.20", "10.20.30.40"}
        )
        self.assertEqual(len(targets), len(set(targets)))
        self.assertIn(("255.255.255.255", 30000), targets)
        self.assertIn(("192.168.5.255", 30000), targets)
        self.assertIn(("10.20.30.255", 30000), targets)

    async def test_protocol_ignores_unexpected_and_duplicate_packets(
        self,
    ) -> None:
        protocol = UDP._UDPClientProtocol(42)
        protocol.datagram_received(b'{"id": 7, "result": {}}', ("x", 1))
        self.assertFalse(protocol._response_future.done())
        protocol.datagram_received(
            b'{"id": 0, "result": {"ok": true}}', ("x", 1)
        )
        protocol.datagram_received(
            b'{"id": 0, "result": {"ok": true}}', ("x", 1)
        )
        self.assertEqual(
            {"id": 0, "result": {"ok": True}},
            await protocol.get_response(),
        )

    async def test_protocol_reports_invalid_json_and_socket_errors(self) -> None:
        invalid_json = UDP._UDPClientProtocol(0)
        invalid_json.datagram_received(b"not-json", ("x", 1))
        with self.assertRaises(json.JSONDecodeError):
            await invalid_json.get_response()

        socket_error = UDP._UDPClientProtocol(0)
        socket_error.error_received(ConnectionError("network down"))
        with self.assertRaisesRegex(ConnectionError, "network down"):
            await socket_error.get_response()


async def _async_result(value):
    """Return a value from a tiny test coroutine."""
    return value


if __name__ == "__main__":
    unittest.main()
