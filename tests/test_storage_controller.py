"""Exercise production coordinator methods with mocked I/O, without HA or hardware.

Extract method ASTs to avoid importing Home Assistant. The control methods run
unchanged; only device, persistence, listeners and wall-clock boundaries are mocked.
"""
import ast
import asyncio
import importlib.util
import logging
import math
from collections import deque
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).parents[1] / 'custom_components/hacs_marstek_api_connect'
def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
LOGIC, CONST = load('logic'), load('const')
CLOCK = SimpleNamespace(value=datetime(2026, 9, 6, 5, 1))
NS = {**vars(LOGIC), **vars(CONST), 'Any': Any, 'math': math,
      'datetime': datetime, 'date': date, 'timedelta': timedelta, 'asyncio': SimpleNamespace(sleep=AsyncMock()),
      'dt_util': SimpleNamespace(now=lambda: CLOCK.value),
      '_LOGGER': logging.getLogger('storage_test')}
tree = ast.parse((ROOT / 'coordinator.py').read_text(encoding='utf-8'))
cls = next(x for x in tree.body if isinstance(x, ast.ClassDef))
names = {'_async_update_storage_mode', '_reset_mode_enforcement', '_async_apply_storage_phase', '_async_update_automatic_storage', '_async_finalize_tracking_day', '_reset_day_tracking', '_async_exit_automatic_storage', '_automatic_storage_data', 'storage_status_attributes', 'storage_decision_reason', 'storage_observation_progress', '_async_record_storage_command', '_diagnostics_data', 'async_load_diagnostics', '_mode_dropouts_last_24h', 'async_load_automatic_storage'}
methods = [x for x in cls.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name in names]
module = ast.Module(body=[ast.ClassDef(name='Controller', bases=[], keywords=[], body=methods, decorator_list=[])], type_ignores=[])
exec(compile(ast.fix_missing_locations(module), str(ROOT / 'coordinator.py'), 'exec'), NS)

class StorageControllerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        CLOCK.value = datetime(2026, 9, 6, 5, 1)
        self.now = CLOCK.value
        c = self.c = NS['Controller']()
        c._storage_command_history = []
        c._last_storage_charge = None
        c._mode_dropouts = deque(maxlen=100)
        c._diagnostics_store = SimpleNamespace(async_save=AsyncMock(), async_load=AsyncMock(return_value={}))
        c._automatic_controller_state = 'storage'
        c.storage_mode_enabled = True
        c._full_soc_days = 0
        c._low_soc_days = 0
        c.storage_observation_days = 5
        c._tracking_full_charge_event = False
        c._last_invalid_tracking_day = None
        c._storage_phase = 'recharging'
        c.storage_recharge_start = time(22)
        c.storage_recharge_end = time(5)
        c.storage_recharge_start_soc = 45
        c.storage_recharge_stop_soc = 50
        c._solar_discharge_started = None
        c._solar_check_started = None
        c._solar_check_cooldown_until = None
        c._battery_power_samples = deque()
        c.automatic_storage_enabled = True
        c.solar_start_source = 'ct'
        c.solar_surplus = False
        c._tracking_had_solar_charge = False
        c.mode_data = {'mode': 'Passive'}
        c.data = {}
        c._storage_command_due = self.now + timedelta(minutes=4)
        c._reset_mode_enforcement()
        c._last_mode_feedback_at = None
        c.client = SimpleNamespace(set_passive_mode=AsyncMock(return_value={'set_result': True}),
            set_mode=AsyncMock(return_value={'set_result': True}),
            get_energy_system_mode=AsyncMock(return_value={'mode': 'Passive'}))
        c._schedule_automatic_storage_save = Mock()
        c.async_update_listeners = Mock()
        c._schedule_mode_enforcement_retry = Mock()
        c._record_mode_dropout = Mock()

    async def update(self, soc=50, battery=0):
        await self.c._async_update_storage_mode(soc, CLOCK.value, battery)

    async def test_window_end_stops_recharge_without_valid_soc(self):
        for soc in (None, 'unknown', float('nan'), float('inf'), -1, 101):
            with self.subTest(soc=soc):
                self.setUp()
                await self.update(soc, 500)
                self.assertEqual('holding', self.c._storage_phase)
                self.c.client.set_passive_mode.assert_awaited_once_with(power=0, cd_time=600)

    async def test_exact_end_boundary_stops_but_before_end_continues(self):
        CLOCK.value = self.now.replace(hour=4, minute=59, second=59)
        await self.update(None, 500)
        self.assertEqual('recharging', self.c._storage_phase)
        CLOCK.value = self.now.replace(hour=5, minute=0)
        await self.update(None, 500)
        self.assertEqual('holding', self.c._storage_phase)

    async def test_passive_feedback_cannot_confirm_failed_stop(self):
        c = self.c
        c.client.set_passive_mode.side_effect = [TimeoutError(), {'set_result': True}]
        await self.update(50, 500)
        self.assertEqual('recharging', c._storage_phase)
        c._last_mode_feedback_at = datetime.now() + timedelta(seconds=1)
        await self.update(50, 500)
        self.assertEqual(2, c.client.set_passive_mode.await_count)
        self.assertEqual('holding', c._storage_phase)
        self.assertTrue(all(call.kwargs['power'] == 0 for call in c.client.set_passive_mode.await_args_list))

    async def test_rejected_stop_never_reports_holding(self):
        self.c.client.set_passive_mode.return_value = {'set_result': False}
        await self.update()
        self.assertEqual('recharging', self.c._storage_phase)

    async def test_restored_passive_phases_rearm_keepalive(self):
        for phase, soc, power in [('holding', 48, 0), ('recharging', 48, -500)]:
            with self.subTest(phase=phase):
                self.setUp()
                CLOCK.value = self.now.replace(hour=23)
                self.c._storage_phase = phase
                self.c._storage_command_due = None
                await self.update(soc)
                self.c.client.set_passive_mode.assert_awaited_once_with(power=power, cd_time=600)
                self.assertIsNotNone(self.c._storage_command_due)
                self.c._storage_command_due = CLOCK.value + timedelta(minutes=5)
                await self.update(soc)
                self.assertEqual(1, self.c.client.set_passive_mode.await_count)
                self.c._storage_command_due = CLOCK.value
                await self.update(soc)
                self.assertEqual(2, self.c.client.set_passive_mode.await_count)

    async def test_ct_confirms_useful_low_charge_but_not_idle(self):
        for power, expected in [(90, 'solar_charging'), (100, 'solar_charging'), (10, 'holding'), (0, 'holding'), (-5, 'holding')]:
            with self.subTest(power=power):
                self.setUp()
                self.c._storage_phase = 'solar_check'
                self.c.solar_surplus = True
                self.c.mode_data = {'mode':'Auto'}
                self.c._solar_check_started = self.now - timedelta(minutes=5)
                self.c._battery_power_samples = deque([(self.now-timedelta(minutes=2), power), (self.now, power)])
                await self.update(45, power)
                self.assertEqual(expected, self.c._storage_phase)
                self.assertEqual(expected == 'solar_charging', self.c._tracking_had_solar_charge)

    async def test_ct_auto_detects_new_charge_on_each_day(self):
        for day in (6, 7):
            CLOCK.value = self.now.replace(day=day)
            self.c._storage_phase = 'auto'
            self.c.mode_data = {'mode':'Auto'}
            self.c.solar_surplus = False
            self.c._tracking_had_solar_charge = False
            self.c._battery_power_samples = deque([(CLOCK.value-timedelta(minutes=2), 90), (CLOCK.value, 90)])
            await self.update(80, 90)
            self.assertEqual('solar_charging', self.c._storage_phase)
            self.assertTrue(self.c._tracking_had_solar_charge)
            self.c.client.set_mode.assert_not_awaited()

    async def test_two_real_ct_charge_days_exit_winter(self):
        c = self.c
        c._automatic_controller_state = 'storage'
        c.storage_mode_enabled = True
        c._full_soc_days = 0
        c._low_soc_days = 0
        c._tracking_day = None
        c._automatic_storage = SimpleNamespace(async_save=AsyncMock())
        c._storage = SimpleNamespace(async_save=AsyncMock())
        c.set_mode = AsyncMock()
        # Real production daily tracking plus real charging recognition.
        for day in (6, 7):
            CLOCK.value = self.now.replace(day=day, hour=1, minute=0)
            await c._async_update_automatic_storage(80)
            c._storage_phase = 'auto'
            c.mode_data = {'mode': 'Auto'}
            c.solar_surplus = False
            c._battery_power_samples = deque([(CLOCK.value-timedelta(minutes=2),90),(CLOCK.value,90)])
            await self.update(80,90)
            self.assertTrue(c._tracking_had_solar_charge)
            CLOCK.value = CLOCK.value.replace(hour=23)
            await c._async_update_automatic_storage(99)
        self.assertEqual('observing', c._automatic_controller_state)
        self.assertFalse(c.storage_mode_enabled)
        c.set_mode.assert_awaited_once_with('Auto')

    async def test_solar_power_mode_keeps_existing_confirmation_threshold(self):
        self.c.solar_start_source = 'solar'
        self.c._storage_phase = 'solar_check'
        self.c.mode_data = {'mode':'Auto'}
        self.c.solar_surplus = True
        self.c._solar_check_started = self.now-timedelta(minutes=5)
        self.c._battery_power_samples = deque([(self.now-timedelta(minutes=2),90),(self.now,90)])
        await self.update(45,90)
        self.assertEqual('holding',self.c._storage_phase)


    async def test_progress_switches_between_entry_exit_and_disabled(self):
        c = self.c
        self.assertEqual('0/2', c.storage_observation_progress)
        c._tracking_full_charge_event = True
        self.assertEqual('1/2', c.storage_observation_progress)
        c._full_soc_days = 1
        self.assertEqual('2/2', c.storage_observation_progress)
        c._automatic_controller_state = 'observing'
        c._low_soc_days = 3
        self.assertEqual('3/5', c.storage_observation_progress)
        self.assertEqual('entry', c.storage_status_attributes['progress_kind'])
        c.automatic_storage_enabled = False
        self.assertEqual('–', c.storage_observation_progress)

    async def test_charge_history_survives_stop_and_reload(self):
        c = self.c
        CLOCK.value = self.now.replace(hour=23)
        c._storage_phase = 'holding'
        await self.update(44)
        saved_charge = dict(c._last_storage_charge)
        self.assertIsNotNone(datetime.fromisoformat(saved_charge['timestamp']).tzinfo)
        self.assertEqual(44, saved_charge['soc'])
        self.assertEqual(-500, saved_charge['power_w'])
        self.assertEqual('automatic_storage', saved_charge['source'])
        self.assertIn('Nachladezeitfenster', saved_charge['reason'])
        await self.update(50)
        self.assertEqual(saved_charge, c._last_storage_charge)
        self.assertEqual(0, c._storage_command_history[-1]['power_w'])
        stored = c._diagnostics_store.async_save.call_args.args[0]
        c._last_storage_charge = None
        c._storage_command_history = []
        c._diagnostics_store.async_load.return_value = stored
        await c.async_load_diagnostics()
        self.assertEqual(saved_charge, c._last_storage_charge)
        self.assertEqual(2, len(c._storage_command_history))

    async def test_failed_charge_does_not_replace_history(self):
        c = self.c
        CLOCK.value = self.now.replace(hour=23)
        c._storage_phase = 'holding'
        for failure in ({'set_result': False}, TimeoutError()):
            c.client.set_passive_mode.side_effect = [failure]
            await self.update(44)
            self.assertIsNone(c._last_storage_charge)
            self.assertEqual([], c._storage_command_history)

    async def test_history_is_bounded_and_keepalive_is_identified(self):
        CLOCK.value = self.now.replace(hour=23)
        for _ in range(25):
            self.c._storage_command_due = CLOCK.value
            await self.update(48)
        self.assertEqual(20, len(self.c._storage_command_history))
        self.assertIn('Periodische', self.c._last_storage_charge['reason'])

    async def test_persistence_failure_does_not_repeat_control_transition(self):
        self.c._diagnostics_store.async_save.side_effect = OSError('disk unavailable')
        with self.assertLogs('storage_test', level='ERROR'):
            await self.update(50)
        self.assertEqual('holding', self.c._storage_phase)
        await self.update(50)
        self.c.client.set_passive_mode.assert_awaited_once()

    async def test_decision_reason_reports_retry_and_cooldown(self):
        c = self.c
        c._pending_storage_phase = 'holding'
        self.assertIn('nicht bestätigt', c.storage_decision_reason)
        c._pending_storage_phase = None
        c._storage_phase = 'holding'
        c._solar_check_cooldown_until = CLOCK.value + timedelta(minutes=10)
        self.assertIn('Wartezeit', c.storage_decision_reason)
        c._solar_check_cooldown_until = None
        self.assertIn('Solarüberschuss', c.storage_decision_reason)

    async def test_short_day_resets_exit_counter(self):
        c = self.c
        c._reset_day_tracking(CLOCK.value)
        c._tracking_last_seen = CLOCK.value + timedelta(hours=1)
        c._tracking_max_soc = 99
        c._tracking_full_charge_event = True
        c._full_soc_days = 1
        await c._async_finalize_tracking_day(CLOCK.value.date() + timedelta(days=1))
        self.assertEqual(0, c._full_soc_days)
        self.assertIsNotNone(c.storage_status_attributes['last_invalid_tracking_day'])

    async def test_restored_first_full_day_allows_next_day_exit(self):
        c = self.c
        c._reset_day_tracking(CLOCK.value.replace(hour=1))
        c._tracking_last_seen = CLOCK.value.replace(hour=23)
        c._tracking_max_soc = 99
        c._tracking_min_soc = 80
        c._tracking_had_solar_charge = True
        c._tracking_full_charge_event = True
        c._automatic_storage = SimpleNamespace(async_save=AsyncMock())
        stored = c._automatic_storage_data()
        c._automatic_storage.async_load = AsyncMock(return_value=stored)
        await c.async_load_automatic_storage()
        c._storage = SimpleNamespace(async_save=AsyncMock())
        c.set_mode = AsyncMock()
        CLOCK.value = CLOCK.value.replace(day=7, hour=1)
        await c._async_update_automatic_storage(80)
        self.assertEqual(1, c._full_soc_days)
        c._tracking_had_solar_charge = True
        await c._async_update_automatic_storage(99)
        c.set_mode.assert_awaited_once_with('Auto')


    async def test_ha_aware_clock_with_naive_cooldown_keeps_sensors_readable(self):
        c = self.c
        c._storage_phase = 'holding'
        naive_now = CLOCK.value
        # Production controller uses datetime.now(); HA dt_util.now() is aware.
        CLOCK.value = naive_now.astimezone(timezone(timedelta(hours=2)))
        for minutes, waiting in ((10, True), (-1, False), (0, False)):
            with self.subTest(minutes=minutes):
                c._solar_check_cooldown_until = naive_now + timedelta(minutes=minutes)
                attributes = c.storage_status_attributes
                self.assertEqual(waiting, 'Wartezeit' in attributes['decision_reason'])
                self.assertEqual('0/2', c.storage_observation_progress)

    async def test_aware_cooldown_in_other_timezone(self):
        c = self.c
        c._storage_phase = 'holding'
        CLOCK.value = CLOCK.value.astimezone(timezone(timedelta(hours=2)))
        c._solar_check_cooldown_until = (CLOCK.value + timedelta(minutes=10)).astimezone(timezone.utc)
        self.assertIn('Wartezeit', c.storage_status_attributes['decision_reason'])
        self.assertEqual('0/2', c.storage_observation_progress)

if __name__ == '__main__':
    unittest.main()
