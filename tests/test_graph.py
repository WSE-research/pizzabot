import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage

import pizzabot
import test_runs
from settings import HERE


def completed_order_state():
    state = pizzabot.new_state("")
    state["slots"] = {
        pizzabot.OrderSlots.PIZZA_NAME.value: "hawaiian",
        pizzabot.OrderSlots.CUSTOMER_ADDRESS.value: "Leipzig, Street 1",
    }
    state["pizza_id"] = "3"
    state["customer_address"] = ("Leipzig", "Street", "1")
    return state


class StateTransitionTests(unittest.TestCase):
    def test_failed_order_returns_ended_state(self):
        state = completed_order_state()
        with (
            patch.dict(
                os.environ,
                {
                    "PIZZABOT_DEPLOYMENT": "local",
                    "PIZZABOT_ENABLE_ORDERS": "1",
                },
                clear=False,
            ),
            patch("pizzabot.post_order", return_value=None),
        ):
            update = pizzabot.OrderNode().invoke(state)

        self.assertIs(update["ended"], True)
        self.assertIn("Something went wrong", update["messages"][-1].content)

    def test_shared_deployment_does_not_call_order_api_by_default(self):
        state = completed_order_state()
        with (
            patch.dict(
                os.environ,
                {
                    "PIZZABOT_DEPLOYMENT": "shared",
                    "PIZZABOT_ENABLE_ORDERS": "",
                },
                clear=False,
            ),
            patch("pizzabot.post_order") as post_order,
        ):
            update = pizzabot.OrderNode().invoke(state)

        post_order.assert_not_called()
        self.assertIs(update["ended"], True)
        self.assertIn("disabled", update["messages"][-1].content)

    def test_router_tolerates_missing_current_intent(self):
        route = pizzabot.CheckerNode().route({"active_order": False})
        self.assertEqual(route, pizzabot.END)


def run_turn(state: dict, user_input: str) -> dict:
    """One turn through the same nodes the compiled graph uses.

    Invoking the compiled graph here would import the optional `langchain`
    package for debug callbacks, which this environment does not pin.
    """
    current = dict(state)
    current[pizzabot.INPUT] = user_input
    checker = pizzabot.CheckerNode()
    current.update(checker.invoke(current))
    route = checker.route(current)
    if route == pizzabot.Nodes.RETRIEVAL.value:
        current.update(pizzabot.RetrievalNode().invoke(current))
        current.update(pizzabot.OrderNode().invoke(current))
    elif route == pizzabot.Nodes.DESCRIPTION.value:
        current.update(pizzabot.DescriptionNode().invoke(current))
    return current


class GraphConversationTests(unittest.TestCase):
    def test_graph_compiles(self):
        graph = pizzabot.build_graph()
        self.assertTrue(callable(getattr(graph, "invoke", None)))
        self.assertTrue(callable(getattr(graph, "stream", None)))

    def test_complete_dialogue_without_network(self):
        with (
            patch.dict(
                os.environ,
                {
                    "PIZZABOT_DEPLOYMENT": "local",
                    "PIZZABOT_ENABLE_ORDERS": "1",
                },
                clear=False,
            ),
            patch("pizzabot.check_order_intention", return_value=True),
            patch("pizzabot.get_pizza_menu", return_value="Hawaiian"),
            patch("pizzabot.validate_pizza_name", return_value="3"),
            patch(
                "pizzabot.check_customer_address",
                return_value=("Leipzig", "Street", "1"),
            ),
            patch("pizzabot.post_order", return_value="order-123"),
        ):
            state = run_turn(
                pizzabot.new_state(""), "I want to order a pizza")
            state = run_turn(state, "Hawaiian")
            state = run_turn(state, "Leipzig, Street 1")

        self.assertIs(state["ended"], True)
        self.assertEqual(state["order_id"], "order-123")
        answers = [
            message.content
            for message in state[pizzabot.MESSAGES]
            if isinstance(message, AIMessage)
        ]
        self.assertIn("order-123", answers[-1])


class TestRunJudgeTests(unittest.TestCase):
    def test_placeholder_match_and_case_folding(self):
        passed, similarity = test_runs.verdict(
            "Keep your order id ready: <SOME UUID>.",
            "Keep your order id ready: 72ee0f12-ce97-4c2d-9386-e6b40bbb55ff.",
        )
        self.assertTrue(passed)
        self.assertGreater(similarity, 0.4)

    def test_place_order_is_ignored_when_orders_are_disabled(self):
        seen = []

        class Graph:
            def stream(self, state, config=None, stream_mode=None):
                seen.append(state.get("input"))
                return []

        app = SimpleNamespace(
            key="demo",
            title="demo",
            spec=SimpleNamespace(module="pizzabot", root=HERE),
            input_key="input",
            new_state=lambda user_input="": {"input": user_input, "messages": []},
            messages=lambda state: state.get("messages") or [],
            answer_of=lambda _state: "",
            graph=Graph(),
        )
        with patch.dict(
            os.environ,
            {
                "PIZZABOT_DEPLOYMENT": "shared",
                "PIZZABOT_ENABLE_ORDERS": "",
            },
            clear=False,
        ):
            run = test_runs.execute(app, place_order=True)

        self.assertEqual(len(seen), len(test_runs.dialogue()) - 1)
        self.assertTrue(run["turns"][-1]["skipped"])


if __name__ == "__main__":
    unittest.main()
