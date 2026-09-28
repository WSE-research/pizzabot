import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app_loader
import diagram
import streamlit_chat
from settings import Settings


class HtmlAndDiagramTests(unittest.TestCase):
    def test_access_token_compare_tolerates_length_mismatch(self):
        self.assertTrue(streamlit_chat.tokens_match("secret", "secret"))
        self.assertFalse(streamlit_chat.tokens_match("no", "secret"))
        self.assertFalse(streamlit_chat.tokens_match("", "secret"))

    def test_dynamic_html_is_escaped(self):
        payload = '<img src=x onerror="alert(1)">'
        escaped = streamlit_chat.escaped(payload)
        self.assertNotIn("<img", escaped)
        self.assertIn("&lt;img", escaped)
        self.assertIn("&quot;", escaped)

    def test_svg_labels_are_escaped(self):
        svg = diagram.to_svg(
            ["__start__", "<script>alert(1)</script>", "__end__"],
            [
                ("__start__", "<script>alert(1)</script>", False),
                ("<script>alert(1)</script>", "__end__", False),
            ],
        )
        self.assertNotIn("<script>", svg)
        self.assertIn("&lt;script&gt;", svg)

    def test_dot_values_cannot_add_statements(self):
        malicious = 'node";\n"attacker" -> "target'
        dot = diagram.to_dot(
            ["__start__", malicious, "__end__"],
            [
                ("__start__", malicious, False),
                (malicious, "__end__", False),
            ],
            title=malicious,
        )
        self.assertNotIn('\n"attacker" -> "target', dot)
        self.assertIn('\\";\\n\\"attacker\\"', dot)


class DeploymentSettingsTests(unittest.TestCase):
    def test_shared_deployment_disables_dangerous_features_by_default(self):
        with patch.dict(
            os.environ,
            {
                "PIZZABOT_DEPLOYMENT": "shared",
                "PIZZABOT_ENABLE_ORDERS": "",
                "PIZZABOT_ENABLE_TEST_RUNS": "",
                "PIZZABOT_ENABLE_LLM_LOG": "",
                "PIZZABOT_ENABLE_APP_SWITCHING": "",
                "PIZZABOT_ENABLE_EXTERNAL_APPS": "",
            },
            clear=False,
        ):
            configured = Settings()
            self.assertFalse(configured.orders_enabled)
            self.assertFalse(configured.test_runs_enabled)
            self.assertFalse(configured.llm_logging_enabled)
            self.assertFalse(configured.app_switching_enabled)
            self.assertFalse(configured.external_apps_enabled)

    def test_local_deployment_preserves_teaching_features(self):
        with patch.dict(
            os.environ,
            {
                "PIZZABOT_DEPLOYMENT": "local",
                "PIZZABOT_ENABLE_ORDERS": "",
                "PIZZABOT_ENABLE_TEST_RUNS": "",
                "PIZZABOT_ENABLE_LLM_LOG": "",
                "PIZZABOT_ENABLE_APP_SWITCHING": "",
                "PIZZABOT_ENABLE_EXTERNAL_APPS": "",
            },
            clear=False,
        ):
            configured = Settings()
            self.assertTrue(configured.orders_enabled)
            self.assertTrue(configured.test_runs_enabled)
            self.assertTrue(configured.llm_logging_enabled)
            self.assertTrue(configured.app_switching_enabled)
            self.assertTrue(configured.external_apps_enabled)


class PluginBoundaryTests(unittest.TestCase):
    def test_invalid_app_key_is_rejected(self):
        with self.assertRaises(ValueError):
            app_loader.AppSpec(
                key="../escape",
                title="bad",
                module="pizzabot",
                path=".",
            )

    def test_external_app_is_disabled_in_shared_mode(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(
                os.environ,
                {
                    "PIZZABOT_DEPLOYMENT": "shared",
                    "PIZZABOT_ENABLE_EXTERNAL_APPS": "",
                },
                clear=False,
            ),
        ):
            spec = app_loader.AppSpec(
                key="external",
                title="external",
                module="external_app",
                path=folder,
            )
            available, reason = spec.available

        self.assertFalse(available)
        self.assertIn("disabled", reason)

    def test_plugin_import_restores_path_and_environment(self):
        module_name = "pizzabot_test_plugin"
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, f"{module_name}.py").write_text(
                "import os\nCAPTURED = os.environ.get('PZ_TEST_IMPORT')\n"
            )
            spec = app_loader.AppSpec(
                key="test-plugin",
                title="test",
                module=module_name,
                path=folder,
                env={"PZ_TEST_IMPORT": "during-import"},
            )
            original_path = list(sys.path)
            with patch.dict(
                os.environ,
                {"PZ_TEST_IMPORT": "before-import"},
                clear=False,
            ):
                module = app_loader._import(spec)
                self.assertEqual(module.CAPTURED, "during-import")
                self.assertEqual(os.environ["PZ_TEST_IMPORT"], "before-import")
            self.assertEqual(sys.path, original_path)
            sys.modules.pop(module_name, None)


if __name__ == "__main__":
    unittest.main()
