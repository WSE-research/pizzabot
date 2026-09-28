import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import utils


class StructuredParsingTests(unittest.TestCase):
    def test_intention_accepts_strict_json_boolean(self):
        self.assertIs(utils._parse_intention('{"intention": true}'), True)
        self.assertIs(utils._parse_intention('{"intention": false}'), False)
        self.assertIs(
            utils._parse_intention('```json\n{"intention": true}\n```'),
            True,
        )

    def test_intention_rejects_executable_python(self):
        payload = (
            "(__import__('os').system('touch /tmp/pizzabot-pwned'), "
            "{'intention': True})[1]"
        )
        with patch("os.system") as system:
            with self.assertRaises((json.JSONDecodeError, ValueError)):
                utils._parse_intention(payload)
        system.assert_not_called()

    def test_qanary_result_requires_expected_json_shape(self):
        result = utils._parse_qanary_result(
            '{"head":{"vars":["label"]},'
            '"results":{"bindings":[{"label":{"value":"Margherita"}}]}}'
        )
        self.assertEqual(result["head"]["vars"], ["label"])

        with self.assertRaises(ValueError):
            utils._parse_qanary_result('{"head": {}, "results": []}')

    def test_graph_iri_rejects_sparql_injection(self):
        self.assertEqual(
            utils._validate_graph_iri("urn:uuid:1234"),
            "urn:uuid:1234",
        )
        with self.assertRaises(ValueError):
            utils._validate_graph_iri("urn:uuid:1234> WHERE { ?s ?p ?o }")

    def test_intention_function_rejects_malicious_model_answer(self):
        answer = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            "(__import__('os').system('touch /tmp/pwned'), "
                            "{'intention': True})[1]"
                        )
                    )
                )
            ]
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **_kwargs: answer)))
        with (
            patch("utils.offline_mode", return_value=False),
            patch("utils._client", return_value=client),
            patch("os.system") as system,
        ):
            self.assertIs(utils.check_order_intention("order"), False)
        system.assert_not_called()

    def test_qanary_pipeline_parses_remote_value_as_json(self):
        response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "inGraph": "urn:uuid:1234",
                "endpoint": "https://qanary.example/sparql",
            },
        )
        result = {
            "results": {
                "bindings": [
                    {
                        "value": {
                            "value": (
                                '{"head":{"vars":["label"]},'
                                '"results":{"bindings":['
                                '{"label":{"value":"Margherita"}}]}}'
                            )
                        }
                    }
                ]
            }
        }
        with (
            patch.dict(
                os.environ,
                {"QANARY_API_BASE": "https://qanary.example"},
                clear=False,
            ),
            patch("utils.offline_mode", return_value=False),
            patch("utils.requests.post", return_value=response),
            patch("utils.execute", return_value=result),
        ):
            context = utils.call_qanary_pipeline("Describe Margherita")

        self.assertEqual(context, "Margherita")


class OutboundUrlTests(unittest.TestCase):
    def test_remote_plain_http_is_blocked_by_default(self):
        with patch.dict(
            os.environ,
            {"PIZZABOT_ALLOW_INSECURE_HTTP": "0"},
            clear=False,
        ):
            with self.assertRaises(ValueError):
                utils.validate_service_url(
                    "http://example.org/api",
                    label="test endpoint",
                )

    def test_loopback_http_is_allowed(self):
        with patch.dict(
            os.environ,
            {"PIZZABOT_ALLOW_INSECURE_HTTP": "0"},
            clear=False,
        ):
            self.assertEqual(
                utils.validate_service_url(
                    "http://127.0.0.1:8000/api",
                    label="test endpoint",
                ),
                "http://127.0.0.1:8000/api",
            )

    def test_returned_endpoint_must_use_an_allowlisted_host(self):
        self.assertEqual(
            utils.validate_service_url(
                "https://qanary.example/sparql",
                label="SPARQL endpoint",
                allowed_hosts=("qanary.example",),
            ),
            "https://qanary.example/sparql",
        )
        with self.assertRaises(ValueError):
            utils.validate_service_url(
                "https://internal.example/sparql",
                label="SPARQL endpoint",
                allowed_hosts=("qanary.example",),
            )

    def test_pizza_api_url_is_validated_on_use(self):
        with patch.dict(
            os.environ,
            {
                "PIZZA_API_BASE": "http://evil.example/pizza-api",
                "PIZZABOT_ALLOW_INSECURE_HTTP": "0",
            },
            clear=False,
        ):
            with self.assertRaises(ValueError):
                utils.pizza_api()


if __name__ == "__main__":
    unittest.main()
