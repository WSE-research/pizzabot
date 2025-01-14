import streamlit as st
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
)
from pizzabot import *

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

def create_chat_app():
    # Initialize session state variables if they don't exist
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "streamlit_messages" not in st.session_state:
        st.session_state.streamlit_messages = []
    if "initialized" not in st.session_state:
        st.session_state.initialized = False
    if "slots" not in st.session_state:
        st.session_state.slots = {}
    if "active_order" not in st.session_state:
        st.session_state.active_order = False
    if "confirm_order" not in st.session_state:
        st.session_state.confirm_order = False
    if "pizza_id" not in st.session_state:
        st.session_state.pizza_id = None
    if "customer_address" not in st.session_state:
        st.session_state.customer_address = None
    if "invalid" not in st.session_state:
        st.session_state.invalid = False
    if "ended" not in st.session_state:
        st.session_state.ended = False

    # Display chat title
    st.title("Pizza Ordering Chatbot")

    # Display initial message
    if not st.session_state.initialized:
        initial_message = "Hi! I am a pizza bot. I can help you order a pizza. What would you like to order?"
        st.session_state.streamlit_messages.append(AIMessage(content=initial_message))
        st.session_state.initialized = True

    # Display chat messages
    for message in st.session_state.streamlit_messages:
        if isinstance(message, AIMessage):
            with st.chat_message("assistant"):
                st.write(message.content)
        elif isinstance(message, HumanMessage):
            with st.chat_message("user"):
                st.write(message.content)

    # Chat input
    if not st.session_state.ended:
        user_input = st.chat_input("Type your message...")
        if user_input:
            # Add user message to chat
            with st.chat_message("user"):
                st.write(user_input)
            st.session_state.streamlit_messages.append(HumanMessage(content=user_input))

            # Process user input through your graph
            outputs = graph.invoke({
                INPUT: user_input,
                SLOTS: st.session_state.slots,
                MESSAGES: st.session_state.messages,
                "active_order": st.session_state.active_order,
                "confirm_order": st.session_state.confirm_order,
                "pizza_id": st.session_state.pizza_id,
                "current_intent": Intents.DEFAULT.value,
                "customer_address": st.session_state.customer_address,
                "invalid": st.session_state.invalid,
                "ended": st.session_state.ended
            })
            
            last_ai_message = next((msg for msg in reversed(outputs[MESSAGES]) if isinstance(msg, AIMessage)), None)
            
            # Update session state with new values
            st.session_state.slots = outputs[SLOTS]
            st.session_state.messages = outputs[MESSAGES]
            st.session_state.active_order = outputs["active_order"]
            st.session_state.confirm_order = outputs["confirm_order"]
            st.session_state.pizza_id = outputs["pizza_id"]
            st.session_state.customer_address = outputs["customer_address"]
            st.session_state.invalid = outputs["invalid"]
            st.session_state.ended = outputs["ended"]

            with st.chat_message("assistant"):
                # Find the last AIMessage in the messages
                last_ai_message = next((msg for msg in reversed(st.session_state.messages) if isinstance(msg, AIMessage)), None)
                st.session_state.streamlit_messages.append(last_ai_message)
                if last_ai_message:
                    st.write(last_ai_message.content)

if __name__ == "__main__":
    create_chat_app()