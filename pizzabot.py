from typing import TypedDict

from utils import logger, post_order, validate_pizza_name, check_customer_address, BasicFunctions, get_pizza_menu, check_order_intention, generate_pizza_description, call_qanary_pipeline

from langgraph.graph import END, StateGraph
from langchain_core.messages import (
    AIMessage,
    FunctionMessage,
)
from enum import Enum

# Define keys for the state dictionary
MESSAGES = "messages"
INPUT = "input"
SLOTS = "slots"

class ChatbotState(TypedDict):
    """
    Message from langdetect import detects have the type "list". The `add_messages` function
    in the annotation defines how this state key should be updated
    (in this case, it appends messages to the list, rather than overwriting them)
    """
    input: str
    slots: dict
    messages: list
    active_order: bool
    confirm_order: bool
    current_intent: str
    invalid: bool
    ended: bool
    pizza_id: str
    customer_address: tuple[str]
    order_id: str

class Nodes(Enum):
    ENTRY = "entry"
    CHECKER = "checker"
    ORDER_FORM = "order_form"
    RETRIEVAL = "retrieval"
    DESCRIPTION = "description"
    END = "end"

class OrderSlots(Enum):
    PIZZA_NAME = "pizza_name"
    CUSTOMER_ADDRESS = "customer_address"
    ORDER_ID = "order_id"

class Intents(Enum):
    DEFAULT = "default"
    DESCRIPTION = "description"

class CheckerNode:
    """
    This node checks whether user input is valid
    """
    
    def __init__(self, order_keywords: list = ["order"], confirm_keywords: list = ["yes", "Yes"], description_keywords: list = ["tell me more", "describe"]):
        self.order_keywords = order_keywords
        self.confirm_keywords = confirm_keywords
        self.description_keywords = description_keywords
        

    def invoke(self, state: ChatbotState) -> dict:
        """
        Checks whether the input is a valid request for pizza order
        """
        _input = state[INPUT]

        if any(keyword.lower() in _input.lower() for keyword in self.description_keywords):
            state["current_intent"] = Intents.DESCRIPTION.value
            return {
                MESSAGES: state[MESSAGES],
                "current_intent": state["current_intent"]
            }
        
        if state['confirm_order']:
            if not any(keyword in _input for keyword in self.confirm_keywords):
                # customer provides no further information
                state["confirm_order"] = False
                return {
                    MESSAGES: state[MESSAGES],
                    "confirm_order": state["confirm_order"]
                }
        
        if state['active_order']: # if we are in the order process
            # TODO instead check whether states pizza_id, customer_address... are valid
            if OrderSlots.PIZZA_NAME.value in state[MESSAGES][-1].content: # checking pizza name validity
                pizza_id = validate_pizza_name(_input)
                if pizza_id is not None: # if pizza name is valid
                    state['pizza_id'] = pizza_id
                    return {
                        MESSAGES: state[MESSAGES],
                        "pizza_id": state["pizza_id"]
                    }
                else: # if pizza name is invalid
                    state["invalid"] = True
                    state['messages'].append(AIMessage(content="Invalid pizza type. Please specify a valid type (e.g. a pizza Pepperoni)'."))
                    return {
                        MESSAGES: state[MESSAGES],
                        "invalid": state["invalid"]
                    }
                    
            elif OrderSlots.CUSTOMER_ADDRESS.value in state[MESSAGES][-1].content: # checking customer address validity
                customer_address = check_customer_address(_input)
                if customer_address is not None:
                    state['customer_address'] = customer_address
                    return {
                        MESSAGES: state[MESSAGES],
                        "customer_address": state["customer_address"]
                    }
                else:
                    state["invalid"] = True
                    state['messages'].append(AIMessage(content="Invalid customer address. Please keep in mind, we only deliver to Halle, Leipzig and Dresden."))
                    return {
                        MESSAGES: state[MESSAGES],
                        "invalid": state["invalid"]
                    }
        
        if not check_order_intention(_input): # User wants to order a pizza
            state['messages'].append(AIMessage(content="Invalid order. Please specify a pizza order. Try writing e.g. 'I want to order a pizza'."))
            return {
                MESSAGES: state[MESSAGES]
            }
        else: # User wants to order a pizza
            state['active_order'] = True
            # state['messages'].append(AIMessage(content="Your pizza order is valid."))
            return {
                MESSAGES: state[MESSAGES],
                "active_order": state["active_order"]
            }
    
    def route(self, state: ChatbotState) -> str:
        """
        Routes to the next node
        """
        if state['active_order'] and ("current_intent" not in state or not state["current_intent"] == Intents.DESCRIPTION.value):
            return Nodes.RETRIEVAL.value
        elif state["current_intent"] == Intents.DESCRIPTION.value:
            return Nodes.DESCRIPTION.value
        else:
            return END

class DescriptionNode:
    """
    This node provides a description of the pizza
    """
    
    def __init__(self):
        pass

    def invoke(self, state: ChatbotState) -> dict:
        """
        Returns a description of the pizza
        """
        _input = state[INPUT] # user message
        context = call_qanary_pipeline(_input) # fetching the context from wikidata
        logger.info(f"Context from Qanary: {context}")
        description = generate_pizza_description(_input, str(context)) # generating the description with LLM
        state["messages"].append(AIMessage(content=description))

        return {
            MESSAGES: state[MESSAGES],
            "current_intent": Intents.DEFAULT.value,
        }

class OrderNode:
    """
    Collects the slots for the pizza order
    """
    
    def __init__(self):
        pass

    def invoke(self, state: ChatbotState) -> dict:
        """
        Returns fallback message
        """
        
        required_slots = [OrderSlots.PIZZA_NAME, OrderSlots.CUSTOMER_ADDRESS, OrderSlots.ORDER_ID]
        missing_slots = BasicFunctions.get_last_missing_slots(state, required_slots)
        
        
        if state["invalid"]:
            last_function_message = BasicFunctions.get_last_function_message(outputs)
            state["invalid"] = False
            state[MESSAGES].append(last_function_message)
            return {
                MESSAGES: state[MESSAGES],
                "invalid": state["invalid"]
            }

        next_slot = missing_slots[0] # get next slot to fill
        
        if next_slot == OrderSlots.ORDER_ID.value:
            order_id = post_order(state["pizza_id"], state["customer_address"]) # post order
            if order_id is not None:
                state['order_id'] = order_id
                state['messages'].append(AIMessage(content="Thank you for providing all the details. Your order is being processed! "
                    + "Keep your order id ready incase you have further inquiries: " + state["order_id"] + " ."))
                state['ended'] = True
                return {
                    MESSAGES: state[MESSAGES],
                    "order_id": state["order_id"],
                    "ended": state["ended"]
                }
            else:
                state['messages'].append(AIMessage(content="Something went wrong while submitting your order, please try again."))
                state['ended'] = True
                return {
                    MESSAGES: state[MESSAGES],
                    "invalid": state["invalid"]
                } 

        if next_slot == OrderSlots.PIZZA_NAME.value:
            menu = get_pizza_menu()
            state['messages'].append(AIMessage("What pizza would you like to order?\nOr should I describe the pizza for you? Here are the options: " + menu))
            state[MESSAGES].append(FunctionMessage(content=OrderSlots.PIZZA_NAME, name=OrderSlots.PIZZA_NAME.value))
            return {
                MESSAGES: state[MESSAGES]
            }
        
        elif next_slot == OrderSlots.CUSTOMER_ADDRESS.value:
            state['messages'].append(AIMessage("What is your delivery address?"))
            state[MESSAGES].append(FunctionMessage(content=OrderSlots.CUSTOMER_ADDRESS, name=OrderSlots.CUSTOMER_ADDRESS.value))
            return {
                MESSAGES: state[MESSAGES]
            }

class RetrievalNode:
    """
    This node extracts the information from user input
    """
    
    def __init__(self):
        pass

    def invoke(self, state: ChatbotState) -> dict:
        """
        Extracts the information from user input
        """
        last_message = BasicFunctions.get_last_message_or_no_message(state)

        if not state['active_order'] or not isinstance(last_message, FunctionMessage): # if nothing to extract
            return {
                MESSAGES: state[MESSAGES],
                SLOTS: state[SLOTS],
                "ended": state["ended"]
            }
        
        _input = state['input'].lower()

        #TODO move input saving into here

        if last_message.content == OrderSlots.PIZZA_NAME.value: # set pizza name
            state['slots'][OrderSlots.PIZZA_NAME.value] = _input
            return {
                MESSAGES: state[MESSAGES],
                SLOTS: state[SLOTS],
                "ended": state["ended"]
            }
        elif last_message.content == OrderSlots.CUSTOMER_ADDRESS.value: # set customer address
            state['slots'][OrderSlots.CUSTOMER_ADDRESS.value] = _input
            return {
                MESSAGES: state[MESSAGES],
                SLOTS: state[SLOTS],
                "ended": state["ended"]
            }
        

if __name__ == "__main__":
    # Initialize nodes
    order_node = OrderNode()
    checker_node = CheckerNode()
    retrieval_node = RetrievalNode()
    description_node = DescriptionNode()

    workflow = StateGraph(ChatbotState)
    # TODO set entrypoint as language detection-node
    #either use it to set a state (enum)
    #or route to language dependant nodes
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

    # START DIALOGUE: first message
    print("-- Chatbot: ", "Hi! I am a pizza bot. I can help you order a pizza. What would you like to order?")
    user_input = input("-> Your response: ")
    outputs = graph.invoke({
        INPUT: user_input,
        SLOTS: {},
        MESSAGES: [],
        "active_order": False,
        "confirm_order": False,
        "pizza_id": None,
        "current_intent": Intents.DEFAULT.value,
        "customer_address": None,
        "invalid": False,
        "ended": False
    })

    while True:
        print("-- Chatbot: ", [m.content for m in outputs[MESSAGES] if isinstance(m, AIMessage) ][-1]) # print chatbot response
        user_input = input("-> Your response: ")

        outputs = graph.invoke({INPUT: user_input, SLOTS: outputs[SLOTS], MESSAGES: outputs[MESSAGES], "active_order": outputs["active_order"], "confirm_order":outputs["confirm_order"], "pizza_id":outputs["pizza_id"], "customer_address":outputs["customer_address"], "invalid":outputs["invalid"], "ended": outputs["ended"]})

        # check if the conversation has ended
        if outputs["ended"]:
            print("-- Chatbot: ", [m.content for m in outputs[MESSAGES] if isinstance(m, AIMessage) ][-1]) # print chatbot response
            break