from os import environ
from langsmith import Client, evaluate
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage
from pizzabot import *
from data.test_dialogue import correct_dialogue
from dotenv import load_dotenv


load_dotenv(override=True)

ls_client = Client()

openai_api_key = environ.get('OPENAI_API_KEY')
openai_api_base = environ.get('OPENAI_API_BASE')
model_name = environ.get("MODEL_NAME")

# ===== START Initialize LangGraph =====
order_node = OrderNode()
checker_node = CheckerNode()
retrieval_node = RetrievalNode()
description_node = DescriptionNode()

workflow = StateGraph(ChatbotState)

workflow.add_node(Nodes.CHECKER.value, checker_node.invoke)
workflow.add_node(Nodes.RETRIEVAL.value, retrieval_node.invoke)
workflow.add_node(Nodes.ORDER_FORM.value, order_node.invoke)
workflow.add_node(Nodes.DESCRIPTION.value, description_node.invoke)

workflow.add_conditional_edges(
    Nodes.CHECKER.value,
    checker_node.route,
    {
        Nodes.RETRIEVAL.value: Nodes.RETRIEVAL.value,
        Nodes.DESCRIPTION.value: Nodes.DESCRIPTION.value,
        END: END,
    }
)
workflow.add_edge(Nodes.RETRIEVAL.value, Nodes.ORDER_FORM.value)
workflow.add_edge(Nodes.DESCRIPTION.value, END)
workflow.add_edge(Nodes.ORDER_FORM.value, END)

workflow.set_entry_point(Nodes.CHECKER.value)
graph = workflow.compile()

# ===== END Initialize LangGraph =====

# ===== START Create dataset =====

dataset_name = "pizzabot"

try:
    dataset = ls_client.create_dataset(
        dataset_name=dataset_name,
    )

    ls_client.create_examples(
        inputs=[e["inputs"] for e in correct_dialogue],
        outputs=[e["outputs"] for e in correct_dialogue],
        dataset_id=dataset.id
    )
except Exception as e:
    print(e)
    # dataset was already created
    dataset = next(ls_client.list_datasets(dataset_name=dataset_name))

# ===== END Create dataset =====

judge_llm = init_chat_model(model_name)

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
    ai_messages = [msg for msg in outputs["messages"] if type(msg) == AIMessage]
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
            {"role": "user", "content": user_msg}
        ]
    )
    return response.content.upper() == "CORRECT"

def convert_dict_to_message(message):
    """
    Convert a dictionary to a message object.
    """
    if message["type"] == 'ai':
        return AIMessage(
            content=message["content"],
            additional_kwargs=message["additional_kwargs"],
            response_metadata=message["response_metadata"]
        )   
    elif message["type"] == 'function':
        return FunctionMessage(
            content=message["content"],
            additional_kwargs=message["additional_kwargs"],
            response_metadata=message["response_metadata"],
            name=message["name"]
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
        "current_intent": inputs["current_intent"] if "current_intent" in inputs else Intents.DEFAULT.value,
        "customer_address": inputs["customer_address"],
        "invalid": inputs["invalid"],
        "ended": inputs["ended"],
    }

    return formatted_input
# We use LCEL declarative syntax here.
# Remember that langgraph graphs are also langchain runnables.
target = example_to_state | graph

experiment_results = evaluate(
    target,
    data=dataset_name,
    evaluators=[correct],
)

print(f"Experiment {experiment_results.experiment_name} completed.")