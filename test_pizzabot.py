"""Optional LangSmith evaluation CLI.

Despite the historical filename, importing this module performs no network
calls and creates no datasets. Run it explicitly with
`python test_pizzabot.py` when a configured LangSmith account is available.
"""

from langchain_core.messages import AIMessage, FunctionMessage

from data.test_dialogue import correct_dialogue
from pizzabot import (
    INPUT,
    MESSAGES,
    SLOTS,
    Intents,
    build_graph,
)
from settings import settings

judge_llm = None


def correct(outputs: dict, reference_outputs: dict) -> bool:
    instructions = (
        "Given an actual answer and an expected answer, determine whether"
        " the actual answer contains all of the information in the"
        " expected answer. Respond with 'CORRECT' if the actual answer"
        " does contain all of the expected information and 'INCORRECT'"
        " otherwise. Do not include anything else in your response."
    )
    # Our graph outputs a State dictionary, which in this case means
    # we'll have a 'messages' key and the final message should
    # be our actual answer.
    ai_messages = [
        msg for msg in outputs["messages"] if isinstance(msg, AIMessage)
    ]
    if not ai_messages:
        return False
    actual_answer = ai_messages[-1].content
    expected_answer = reference_outputs["expected"]
    user_msg = (
        f"ACTUAL ANSWER: {actual_answer}"
        f"\n\nEXPECTED ANSWER: {expected_answer}"
    )
    response = judge_llm.invoke(
        [
            {"role": "system", "content": instructions},
            {"role": "user", "content": user_msg},
        ]
    )
    return response.content.upper() == "CORRECT"


def convert_dict_to_message(message):
    """
    Convert a dictionary to a message object.
    """
    if message["type"] == "ai":
        return AIMessage(
            content=message["content"],
            additional_kwargs=message["additional_kwargs"],
            response_metadata=message["response_metadata"],
        )
    elif message["type"] == "function":
        return FunctionMessage(
            content=message["content"],
            additional_kwargs=message["additional_kwargs"],
            response_metadata=message["response_metadata"],
            name=message["name"],
        )
    else:
        return message


def example_to_state(inputs: dict) -> dict:
    formatted_input = {
        INPUT: inputs[INPUT],
        SLOTS: inputs[SLOTS],
        MESSAGES: [convert_dict_to_message(m) for m in inputs[MESSAGES]],
        "active_order": inputs["active_order"],
        "confirm_order": inputs["confirm_order"],
        "pizza_id": inputs["pizza_id"],
        "current_intent": inputs.get(
            "current_intent", Intents.DEFAULT.value),
        "customer_address": inputs["customer_address"],
        "invalid": inputs["invalid"],
        "ended": inputs["ended"],
        "order_id": inputs.get("order_id"),
    }

    return formatted_input


def main() -> None:
    """Create the LangSmith dataset if needed and run the remote evaluation."""
    global judge_llm

    from langchain.chat_models import init_chat_model
    from langsmith import Client, evaluate

    dataset_name = "pizzabot"
    client = Client()
    dataset = next(
        client.list_datasets(dataset_name=dataset_name),
        None,
    )
    if dataset is None:
        dataset = client.create_dataset(dataset_name=dataset_name)
        client.create_examples(
            inputs=[example["inputs"] for example in correct_dialogue],
            outputs=[example["outputs"] for example in correct_dialogue],
            dataset_id=dataset.id,
        )

    judge_llm = init_chat_model(settings.model_name)
    target = example_to_state | build_graph()
    experiment_results = evaluate(
        target,
        data=dataset_name,
        evaluators=[correct],
    )
    print(f"Experiment {experiment_results.experiment_name} completed.")


if __name__ == "__main__":
    main()