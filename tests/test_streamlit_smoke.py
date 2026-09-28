import unittest
import os
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


class StreamlitSmokeTests(unittest.TestCase):
    def test_first_page_renders_without_exception(self):
        app_file = Path(__file__).resolve().parents[1] / "streamlit_chat.py"
        app = AppTest.from_file(str(app_file)).run(timeout=15)
        self.assertEqual(list(app.exception), [])
        self.assertTrue(app.button)
        app.text_input[0].set_value("Test Shop")
        app.button[-1].click().run(timeout=15)
        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.selectbox[0].label, "Implementation")
        self.assertEqual(len(app.chat_input), 1)

    def test_shared_page_stays_locked_without_access_token(self):
        app_file = Path(__file__).resolve().parents[1] / "streamlit_chat.py"
        with patch.dict(
            os.environ,
            {
                "PIZZABOT_DEPLOYMENT": "shared",
                "PIZZABOT_ACCESS_TOKEN": "",
            },
            clear=False,
        ):
            app = AppTest.from_file(str(app_file)).run(timeout=15)
        self.assertEqual(list(app.exception), [])
        self.assertTrue(app.error)
        self.assertIn("locked", app.error[0].value.lower())


if __name__ == "__main__":
    unittest.main()
