"""Validate integration metadata and translated diagnostic entities."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).parents[1]
INTEGRATION = ROOT / "custom_components" / "hacs_marstek_api_connect"

SPEC = importlib.util.spec_from_file_location(
    "marstek_const", INTEGRATION / "const.py"
)
assert SPEC is not None and SPEC.loader is not None
CONST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONST)


def translation_files() -> list[Path]:
    """Return the development strings and supported translations."""
    return [
        INTEGRATION / "strings.json",
        *(INTEGRATION / "translations").glob("*.json"),
    ]


class MetadataTests(unittest.TestCase):
    """Guard release metadata and translation completeness."""

    def test_manifest_version(self) -> None:
        manifest = json.loads(
            (INTEGRATION / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual("2.10.1", manifest["version"])

    def test_manifest_and_hacs_metadata_agree(self) -> None:
        manifest = json.loads(
            (INTEGRATION / "manifest.json").read_text(encoding="utf-8")
        )
        hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
        manifest_keys = list(manifest)
        self.assertEqual(
            ["domain", "name", *sorted(manifest_keys[2:])],
            manifest_keys,
        )
        self.assertEqual(CONST.DOMAIN, manifest["domain"])
        self.assertEqual("local_polling", manifest["iot_class"])
        self.assertEqual([], manifest["requirements"])
        self.assertEqual(
            {"name", "render_readme", "homeassistant", "content_in_root"},
            set(hacs),
        )
        self.assertRegex(
            manifest["version"],
            r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$",
        )

        init_source = (INTEGRATION / "__init__.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("cv.config_entry_only_config_schema(DOMAIN)", init_source)

    def test_ci_runs_required_validators(self) -> None:
        """Keep local tests, HACS and hassfest in the validation workflow."""
        workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("python -m unittest discover -s tests -v", workflow)
        self.assertIn("hacs/action@main", workflow)
        self.assertIn("home-assistant/actions/hassfest@master", workflow)
        self.assertIn("contents: read", workflow)

        dependabot = (ROOT / ".github" / "dependabot.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("package-ecosystem: github-actions", dependabot)

    def test_setup_starts_discovery_without_confirmation_checkbox(self) -> None:
        config_flow = (INTEGRATION / "config_flow.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('vol.Required("confirm"', config_flow)
        self.assertIn(
            '"""Start device discovery immediately when the flow opens."""',
            config_flow,
        )

    def test_dynamic_translation_keys_are_set_before_entity_init(self) -> None:
        """Prevent Home Assistant from caching an empty entity name."""
        for filename, class_name in (
            ("sensor.py", "MarstekSensor"),
            ("binary_sensor.py", "MarstekBinarySensor"),
        ):
            source = (INTEGRATION / filename).read_text(encoding="utf-8")
            constructor = source.split(f"class {class_name}", 1)[1]
            with self.subTest(platform=filename):
                self.assertLess(
                    constructor.index("self._attr_translation_key"),
                    constructor.index("super().__init__(coordinator)"),
                )

    def test_translated_entities_do_not_override_name_with_none(self) -> None:
        """An explicit null name suppresses translations in current HA."""
        for filename in (
            "sensor.py",
            "binary_sensor.py",
            "select.py",
            "button.py",
            "number.py",
            "switch.py",
        ):
            with self.subTest(platform=filename):
                source = (INTEGRATION / filename).read_text(encoding="utf-8")
                self.assertNotIn("_attr_name = None", source)

    def test_user_modes_separate_direct_power_and_schedules(self) -> None:
        self.assertIn("Manual", CONST.SELECTABLE_MODES)
        self.assertIn("Schedule", CONST.SELECTABLE_MODES)
        self.assertNotIn("Passive", CONST.SELECTABLE_MODES)

    def test_public_services_are_consistent(self) -> None:
        """Service UI, registration and unload lists must not drift apart."""
        expected = {
            "set_mode",
            "set_manual_schedule",
            "clear_all_schedules",
            "set_ble_adv",
            "set_led_ctrl",
        }
        services_yaml = (INTEGRATION / "services.yaml").read_text(
            encoding="utf-8"
        )
        described = {
            line[:-1]
            for line in services_yaml.splitlines()
            if line and not line[0].isspace() and line.endswith(":")
        }
        self.assertEqual(expected, described)

        service_source = (INTEGRATION / "services.py").read_text(
            encoding="utf-8"
        )
        init_source = (INTEGRATION / "__init__.py").read_text(
            encoding="utf-8"
        )
        for service in expected:
            self.assertIn(f'"{service}"', service_source)
        self.assertIn("await async_setup_services(hass)", init_source)
        self.assertNotIn('"set_passive_mode"', service_source)
        self.assertNotIn('"change_operating_mode"', service_source)

    def test_only_german_and_english_are_shipped(self) -> None:
        """Do not silently reintroduce incomplete language files."""
        translations = {
            path.name for path in (INTEGRATION / "translations").glob("*.json")
        }
        self.assertEqual({"de.json", "en.json"}, translations)

    def test_translation_key_trees_match(self) -> None:
        """English, German and development strings must stay structurally equal."""
        def key_tree(value):
            if isinstance(value, dict):
                return {key: key_tree(child) for key, child in value.items()}
            return None

        trees = []
        for path in translation_files():
            data = json.loads(path.read_text(encoding="utf-8"))
            trees.append((path.name, key_tree(data)))
        for name, tree in trees[1:]:
            with self.subTest(path=name):
                self.assertEqual(trees[0][1], tree)

    def test_development_strings_equal_english_runtime_translation(self) -> None:
        """Keep strings.json and en.json from drifting in values."""
        strings = json.loads(
            (INTEGRATION / "strings.json").read_text(encoding="utf-8")
        )
        english = json.loads(
            (INTEGRATION / "translations" / "en.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(strings, english)

    def test_translation_placeholders_match(self) -> None:
        """Translated messages must expose the same format placeholders."""
        placeholder = re.compile(r"\{([^{}]+)\}")

        def placeholders(value):
            if isinstance(value, dict):
                return {
                    key: placeholders(child) for key, child in value.items()
                }
            if isinstance(value, str):
                return set(placeholder.findall(value))
            return set()

        reference = placeholders(
            json.loads(
                (INTEGRATION / "strings.json").read_text(encoding="utf-8")
            )
        )
        for path in translation_files():
            with self.subTest(path=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(reference, placeholders(data))

    def test_selector_options_are_fully_translated(self) -> None:
        """Every selector value displayed by a form needs a translation."""
        expected = {
            "solar_start_source": {"solar", "ct"},
            "device_selection": {"retry_discovery", "manual"},
            "operating_mode_options": {
                mode.lower() for mode in CONST.SELECTABLE_MODES
            },
            "weekdays": {
                "monday", "tuesday", "wednesday", "thursday", "friday",
                "saturday", "sunday",
            },
            "schedule_direction": {"charging", "discharging"},
        }
        for path in translation_files():
            selectors = json.loads(path.read_text(encoding="utf-8"))["selector"]
            with self.subTest(path=path.name):
                self.assertEqual(set(expected), set(selectors))
            for key, options in expected.items():
                with self.subTest(path=path.name, selector=key):
                    self.assertEqual(options, set(selectors[key]["options"]))

    def test_operating_mode_labels_match_configuration(self) -> None:
        """The select entity and options form must show identical labels."""
        expected_options = {mode.lower() for mode in CONST.SELECTABLE_MODES}
        for path in translation_files():
            with self.subTest(path=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                configured = data["selector"]["operating_mode_options"][
                    "options"
                ]
                select_states = data["entity"]["select"][
                    "operating_mode"
                ]["state"]
                self.assertEqual(expected_options, set(select_states))
                self.assertEqual(configured, select_states)

    def test_every_entity_has_a_translation(self) -> None:
        """Every entity description key needs a visible localized name."""
        for path in translation_files():
            data = json.loads(path.read_text(encoding="utf-8"))["entity"]
            with self.subTest(path=path.name, platform="sensor"):
                self.assertEqual(set(CONST.ALL_SENSORS), set(data["sensor"]))
            with self.subTest(path=path.name, platform="binary_sensor"):
                self.assertEqual(
                    set(CONST.BINARY_SENSORS), set(data["binary_sensor"])
                )
            expected_fixed = {
                "select": {"operating_mode"},
                "switch": {"led_ctrl", "automatic_storage"},
                "number": {"manual_power"},
                "button": {"clear_schedules"},
            }
            for platform, keys in expected_fixed.items():
                with self.subTest(path=path.name, platform=platform):
                    self.assertEqual(keys, set(data[platform]))

    def test_entity_configs_do_not_duplicate_translated_names(self) -> None:
        """English fallback names must live in translation files only."""
        for key, config in {
            **CONST.ALL_SENSORS,
            **CONST.BINARY_SENSORS,
        }.items():
            with self.subTest(entity=key):
                self.assertNotIn("name", config)

    def test_service_fields_are_fully_translated(self) -> None:
        """All active service fields need names and descriptions."""
        expected = {
            "set_mode": {"config_entry_id", "mode"},
            "set_manual_schedule": {
                "config_entry_id", "time_num", "start_time", "end_time",
                "week_set", "mode", "power", "enable",
            },
            "clear_all_schedules": {"config_entry_id"},
            "set_ble_adv": {"config_entry_id", "enable"},
            "set_led_ctrl": {"config_entry_id", "enabled"},
        }
        for path in translation_files():
            services = json.loads(path.read_text(encoding="utf-8"))["services"]
            with self.subTest(path=path.name):
                self.assertEqual(set(expected), set(services))
            for service, fields in expected.items():
                with self.subTest(path=path.name, service=service):
                    self.assertEqual(fields, set(services[service]["fields"]))
                    for field in services[service]["fields"].values():
                        self.assertTrue(field["name"])
                        self.assertTrue(field["description"])

    def test_diagnostic_entities_are_translated(self) -> None:
        for path in translation_files():
            with self.subTest(path=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                entities = data["entity"]
                self.assertIn("self_test", entities["sensor"])
                self.assertIn("solar_surplus", entities["binary_sensor"])
                self.assertIn(
                    "integration_problem", entities["binary_sensor"]
                )
                self.assertEqual(
                    {"ok", "warning", "error"},
                    set(entities["sensor"]["self_test"]["state"]),
                )

    def test_status_sensors_are_translated(self) -> None:
        """Every state the coordinator can report must be translated."""
        expected = {
            "operation_status": set(CONST.OPERATION_STATUS_STATES),
            "storage_status": set(CONST.STORAGE_STATUS_STATES),
        }
        for path in translation_files():
            for key, states in expected.items():
                with self.subTest(path=path.name, sensor=key):
                    data = json.loads(path.read_text(encoding="utf-8"))
                    sensor = data["entity"]["sensor"][key]
                    self.assertTrue(sensor["name"])
                    self.assertEqual(states, set(sensor["state"]))

    def test_enum_sensors_declare_their_options(self) -> None:
        """An enum sensor reporting a state outside options breaks in HA."""
        for key in ("operation_status", "storage_status", "self_test"):
            with self.subTest(sensor=key):
                config = CONST.ALL_SENSORS[key]
                self.assertEqual("enum", config["device_class"])
                self.assertTrue(config["options"])
                self.assertEqual(key, config["translation_key"])

    def test_observation_progress_is_a_derived_sensor(self) -> None:
        """The five-day counter must be exposed as its own plain sensor."""
        config = CONST.ALL_SENSORS["storage_observation_progress"]
        self.assertEqual("derived", config["source"])
        self.assertIsNone(config["device_class"])
        self.assertIsNone(config["attr"])

    def test_error_messages_are_translated(self) -> None:
        """A raised HomeAssistantError must resolve in every language."""
        expected = {
            "mode_not_confirmed", "unknown_config_entry", "mode_set_failed",
            "schedule_set_failed", "schedules_clear_failed",
            "schedule_slots_failed", "ble_set_failed", "led_set_failed",
            "manual_power_failed", "automatic_storage_failed",
        }
        for path in translation_files():
            with self.subTest(path=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(expected, set(data["exceptions"]))
                message = data["exceptions"]["mode_not_confirmed"]["message"]
                self.assertIn("{mode}", message)

    def test_solar_output_display_names(self) -> None:
        expected_names = {
            "strings.json": "Solar output",
            "en.json": "Solar output",
            "de.json": "Solarausgabe",
        }
        for path in translation_files():
            with self.subTest(path=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(
                    expected_names[path.name],
                    data["entity"]["binary_sensor"]["solar_surplus"][
                        "name"
                    ],
                )


if __name__ == "__main__":
    unittest.main()
