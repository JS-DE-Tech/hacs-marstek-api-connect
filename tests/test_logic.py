"""Tests for Home Assistant-independent integration logic."""
from __future__ import annotations

import importlib.util
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
import unittest


LOGIC_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "hacs_marstek_api_connect"
    / "logic.py"
)
SPEC = importlib.util.spec_from_file_location("marstek_logic", LOGIC_PATH)
assert SPEC is not None and SPEC.loader is not None
LOGIC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOGIC)

# Entry threshold of the solar-charging phase and its lower exit threshold.
ENTRY_W = 100
EXIT_W = 0


class DataNormalizationTests(unittest.TestCase):
    """Verify pure input normalization and averaging helpers."""

    def test_ipv4_leading_zeroes_are_removed(self) -> None:
        self.assertEqual(
            "10.100.1.227", LOGIC.normalize_ipv4("10.100.01.227")
        )
        self.assertEqual("192.168.1.1", LOGIC.normalize_ipv4(" 192.168.1.1 "))

    def test_invalid_ipv4_values_are_preserved(self) -> None:
        values = [None, 1234, "192.168.1", "192.168.1.999", "host.local"]
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(value, LOGIC.normalize_ipv4(value))

    def test_time_weighted_average_requires_a_complete_window(self) -> None:
        now = datetime(2026, 1, 1, 12, 5)
        samples = deque([(now - timedelta(minutes=4), 1000.0)])
        self.assertIsNone(
            LOGIC.time_weighted_average(
                samples, now, timedelta(minutes=5)
            )
        )

    def test_time_weighted_average_uses_sample_duration(self) -> None:
        now = datetime(2026, 1, 1, 12, 5)
        samples = deque(
            [
                (now - timedelta(minutes=5), 1000.0),
                (now - timedelta(minutes=3), 2000.0),
            ]
        )
        self.assertEqual(
            1600.0,
            LOGIC.time_weighted_average(
                samples, now, timedelta(minutes=5)
            ),
        )

    def test_sample_retention_keeps_one_value_before_window(self) -> None:
        now = datetime(2026, 1, 1, 12, 3)
        samples = deque(
            [
                (now - timedelta(minutes=3), 100.0),
                (now - timedelta(minutes=2), 200.0),
                (now - timedelta(minutes=1), 300.0),
            ]
        )
        LOGIC.append_sample(samples, now, 400.0, timedelta(minutes=2))
        self.assertEqual([200.0, 300.0, 400.0], [item[1] for item in samples])

    def test_weekday_bitmask(self) -> None:
        self.assertEqual(
            31,
            LOGIC.week_set_from_days(
                ["monday", "tuesday", "wednesday", "thursday", "friday"]
            ),
        )
        self.assertEqual(96, LOGIC.week_set_from_days(["saturday", "sunday"]))
        self.assertEqual(127, LOGIC.week_set_from_days([]))

    def test_battery_power_prefers_device_value_and_normalizes_fallback(
        self,
    ) -> None:
        self.assertEqual(
            500.0,
            LOGIC.normalized_battery_power(
                {"bat_power": "500", "ongrid_power": -900}
            ),
        )
        self.assertEqual(
            900.0,
            LOGIC.normalized_battery_power({"ongrid_power": -900}),
        )
        self.assertEqual(
            -400.0,
            LOGIC.normalized_battery_power({"ongrid_power": 400}),
        )
        self.assertIsNone(
            LOGIC.normalized_battery_power({"bat_power": "invalid"})
        )

    def test_operation_status_thresholds_and_priorities(self) -> None:
        expected = {
            11: "charging",
            10: "standby",
            0: "standby",
            -10: "standby",
            -11: "discharging",
            None: None,
        }
        for power, status in expected.items():
            with self.subTest(power=power):
                self.assertEqual(
                    status, LOGIC.operation_status_from_power(power)
                )
        self.assertEqual(
            "storage_holding",
            LOGIC.operation_status_from_power(
                500, storage_state="storage_holding"
            ),
        )
        self.assertEqual(
            "mode_error",
            LOGIC.operation_status_from_power(
                500, mode_error=True, storage_state="storage_holding"
            ),
        )

    def test_available_battery_capacity(self) -> None:
        self.assertEqual(
            1638.4, LOGIC.available_battery_capacity(68, 5120)
        )
        self.assertEqual(0.0, LOGIC.available_battery_capacity(100, 5120))
        self.assertIsNone(
            LOGIC.available_battery_capacity("unknown", 5120)
        )


class ManualStorageStateTests(unittest.TestCase):
    """Verify the self-contained 45/50/55 percent hysteresis."""

    def next_phase(self, current: str | None, soc: float) -> str:
        return LOGIC.manual_storage_next_phase(current, soc, 45, 50, 55)

    def test_low_soc_charges_until_target(self) -> None:
        self.assertEqual("charging", self.next_phase(None, 45))
        self.assertEqual("charging", self.next_phase("charging", 49.9))
        self.assertEqual("holding", self.next_phase("charging", 50))

    def test_high_soc_uses_auto_until_target(self) -> None:
        self.assertEqual("auto", self.next_phase(None, 55))
        self.assertEqual("auto", self.next_phase("auto", 50.1))
        self.assertEqual("holding", self.next_phase("auto", 50))

    def test_dead_band_holds(self) -> None:
        for soc in (45.1, 50, 54.9):
            with self.subTest(soc=soc):
                self.assertEqual("holding", self.next_phase("holding", soc))

    def test_initial_phase_respects_both_outer_thresholds(self) -> None:
        self.assertEqual("charging", self.next_phase(None, 44.9))
        self.assertEqual("holding", self.next_phase(None, 50))
        self.assertEqual("auto", self.next_phase(None, 55.1))


class AutomaticStorageStateTests(unittest.TestCase):
    """Verify automatic-winter solar and fallback transitions."""

    def next_phase(
        self,
        current: str | None,
        soc: float,
        *,
        surplus: bool = False,
        cooldown: bool = False,
        elapsed: float = 0,
        battery_average: float | None = None,
    ) -> str:
        return LOGIC.automatic_storage_next_phase(
            current,
            soc,
            solar_surplus=surplus,
            cooldown_active=cooldown,
            solar_check_elapsed_seconds=elapsed,
            battery_average=battery_average,
            charge_start_soc=45,
            target_soc=50,
            charge_threshold_w=ENTRY_W,
            charge_exit_w=EXIT_W,
            charge_confirmation_seconds=120,
            solar_check_max_seconds=300,
        )

    def test_low_soc_charges_to_target(self) -> None:
        self.assertEqual("charging", self.next_phase(None, 45))
        self.assertEqual("charging", self.next_phase("charging", 49.9))
        self.assertEqual("holding", self.next_phase("charging", 50))
        self.assertEqual("charging", self.next_phase("auto", 44))
        self.assertEqual("charging", self.next_phase("solar_charging", 44))
        self.assertEqual("charging", self.next_phase("solar_check", 44))

    def test_surplus_starts_check_only_outside_cooldown(self) -> None:
        self.assertEqual(
            "solar_check", self.next_phase("holding", 50, surplus=True)
        )
        self.assertEqual(
            "holding",
            self.next_phase(
                "holding", 50, surplus=True, cooldown=True
            ),
        )

    def test_solar_check_requires_sustained_battery_charge(self) -> None:
        self.assertEqual(
            "solar_check",
            self.next_phase(
                "solar_check", 60, elapsed=119, battery_average=500
            ),
        )
        self.assertEqual(
            "solar_check",
            self.next_phase(
                "solar_check", 60, elapsed=120, battery_average=100
            ),
        )
        self.assertEqual(
            "solar_charging",
            self.next_phase(
                "solar_check", 60, elapsed=120, battery_average=101
            ),
        )

    def test_failed_solar_check_falls_back_safely(self) -> None:
        self.assertEqual(
            "auto",
            self.next_phase(
                "solar_check", 60, elapsed=300, battery_average=0
            ),
        )
        self.assertEqual(
            "holding",
            self.next_phase(
                "solar_check", 50, elapsed=300, battery_average=0
            ),
        )

    def test_auto_returns_to_holding_and_detects_charge(self) -> None:
        self.assertEqual("holding", self.next_phase("auto", 50))
        self.assertEqual(
            "solar_charging",
            self.next_phase("auto", 60, battery_average=101),
        )

    def test_holding_ignores_surplus_during_cooldown(self) -> None:
        self.assertEqual(
            "holding",
            self.next_phase(
                "holding", 60, surplus=True, cooldown=True
            ),
        )


class StorageCommandTests(unittest.TestCase):
    """Verify logical phases only send distinct commands when required."""

    def test_passive_phases_have_distinct_power_targets(self) -> None:
        self.assertEqual(
            ("Passive", -500), LOGIC.storage_phase_command("charging", -500)
        )
        self.assertEqual(
            ("Passive", 0), LOGIC.storage_phase_command("holding", -500)
        )

    def test_all_solar_phases_share_the_auto_command(self) -> None:
        commands = {
            LOGIC.storage_phase_command(phase, -500)
            for phase in ("solar_check", "solar_charging", "auto")
        }
        self.assertEqual({("Auto", None)}, commands)
        self.assertFalse(
            LOGIC.storage_phase_changes_command(
                "solar_check", "solar_charging", -500
            )
        )

    def test_power_target_and_mode_changes_require_commands(self) -> None:
        self.assertTrue(
            LOGIC.storage_phase_changes_command("charging", "holding", -500)
        )
        self.assertTrue(
            LOGIC.storage_phase_changes_command("holding", "solar_check", -500)
        )

    def test_supervision_resends_only_when_required(self) -> None:
        common = {
            "actual_mode": "Auto",
            "expected_mode": "Auto",
            "keepalive_due": False,
            "confirmed_pending_transition": False,
        }
        self.assertFalse(
            LOGIC.storage_command_required(
                planned_command_change=False, **common
            )
        )
        self.assertTrue(
            LOGIC.storage_command_required(
                planned_command_change=True, **common
            )
        )
        self.assertTrue(
            LOGIC.storage_command_required(
                planned_command_change=False,
                **{**common, "actual_mode": "Passive"},
            )
        )
        self.assertTrue(
            LOGIC.storage_command_required(
                planned_command_change=False,
                **{**common, "keepalive_due": True},
            )
        )
        self.assertFalse(
            LOGIC.storage_command_required(
                planned_command_change=True,
                **{**common, "confirmed_pending_transition": True},
            )
        )

    def test_unknown_phase_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            LOGIC.storage_phase_command("invalid", -500)


class SolarChargingStateTests(unittest.TestCase):
    """Verify the exit conditions of confirmed solar charging."""

    def test_charging_continues_above_entry_threshold(self) -> None:
        self.assertEqual(
            "solar_charging",
            LOGIC.solar_charging_next_phase(70, ENTRY_W + 1, 50, EXIT_W),
        )

    def test_dead_band_keeps_the_current_phase(self) -> None:
        """A weak charge between both thresholds must not flip the phase."""
        for average in (ENTRY_W, ENTRY_W / 2, 1):
            with self.subTest(average=average):
                self.assertEqual(
                    "solar_charging",
                    LOGIC.solar_charging_next_phase(70, average, 50, EXIT_W),
                )

    def test_stopped_charge_changes_to_auto(self) -> None:
        self.assertEqual(
            "auto",
            LOGIC.solar_charging_next_phase(70, EXIT_W, 50, EXIT_W),
        )

    def test_discharge_changes_to_auto(self) -> None:
        self.assertEqual(
            "auto",
            LOGIC.solar_charging_next_phase(70, -200, 50, EXIT_W),
        )

    def test_target_soc_changes_to_holding(self) -> None:
        self.assertEqual(
            "holding",
            LOGIC.solar_charging_next_phase(50, 500, 50, EXIT_W),
        )

    def test_missing_average_does_not_end_charge_early(self) -> None:
        self.assertEqual(
            "solar_charging",
            LOGIC.solar_charging_next_phase(70, None, 50, EXIT_W),
        )


class DropoutIncidentTests(unittest.TestCase):
    """Verify that retries do not create duplicate incidents."""

    def test_first_deviation_is_a_new_incident(self) -> None:
        self.assertTrue(LOGIC.is_new_dropout(None))

    def test_retry_during_an_active_incident_is_not_new(self) -> None:
        self.assertFalse(LOGIC.is_new_dropout("Mode Auto instead of AI"))


class OperatingModeTests(unittest.TestCase):
    """Verify persistent-to-physical mode mapping and feedback checks."""

    def test_virtual_modes_map_to_physical_device_modes(self) -> None:
        expected = {
            "Auto": "Auto",
            "AI": "AI",
            "Standby": "Passive",
            "Manual": "Passive",
            "Schedule": "Manual",
        }
        for desired, physical in expected.items():
            with self.subTest(desired=desired):
                self.assertEqual(
                    physical, LOGIC.expected_physical_mode(desired)
                )

    def test_regular_mode_requires_matching_feedback(self) -> None:
        self.assertTrue(LOGIC.mode_feedback_confirmed("AI", "AI", 0))
        self.assertFalse(LOGIC.mode_feedback_confirmed("AI", "Auto", 0))

    def test_schedule_requires_physical_manual_feedback(self) -> None:
        self.assertTrue(
            LOGIC.mode_feedback_confirmed("Schedule", "Manual", 0)
        )
        self.assertFalse(
            LOGIC.mode_feedback_confirmed("Schedule", "Passive", 0)
        )

    def test_standby_requires_three_neutral_power_samples(self) -> None:
        for samples in (0, 1, 2):
            with self.subTest(samples=samples):
                self.assertFalse(
                    LOGIC.mode_feedback_confirmed(
                        "Standby", "Passive", samples
                    )
                )
        self.assertTrue(
            LOGIC.mode_feedback_confirmed("Standby", "Passive", 3)
        )


if __name__ == "__main__":
    unittest.main()
