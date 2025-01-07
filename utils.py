import requests
import json
from os import environ
from openai import OpenAI
from dotenv import load_dotenv
from fuzzywuzzy import fuzz
from SPARQLWrapper import SPARQLWrapper, JSON
import logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv(override=True)
pizza_api_base = environ.get('PIZZA_API_BASE')
openai_api_key = environ.get('OPENAI_API_KEY')
openai_api_base = environ.get('OPENAI_API_BASE')
qanary_api_base = environ.get('QANARY_API_BASE')

client = OpenAI(
    api_key=openai_api_key,
    base_url=openai_api_base,
)


def generate_pizza_description(_input, context) -> str:
    final_prompt = f"""
Here is the context with pizza descriptions: {context}

Here is the user message: {_input}
"""

    chat_response = client.chat.completions.create(
        model=environ.get("MODEL_NAME"),
        messages=[
            {"role": "system", "content": """You are a Pizza Salesman.
Given the context that has multiple pizza descriptions and the user's question generate a pizza description.
**Output only the description**"""},
            {"role": "user", "content": final_prompt}
        ]
    )

    received_message = chat_response.choices[0].message.content

    return received_message


def execute(query: str, endpoint_url: str = 'https://query.wikidata.org/bigdata/namespace/wdq/sparql'):
    """
    https://query.wikidata.org/bigdata/namespace/wdq/sparql
    """
    try:
        sparql = SPARQLWrapper(endpoint_url)
        sparql.timeout = 20
        sparql.setQuery(query)
        sparql.setReturnFormat(JSON)
        response = sparql.query().convert()
        return response
    except Exception as e:
        logger.error(str(e))
        if 'MalformedQueryException' in str(e) or 'bad formed' in str(e):
            return {'error': str(e)}
        return {'error': str(e)}


def call_qanary_pipeline(question: str):
    """
    Call Qanary pipeline to get the answer for the given question
    """
    try:
        url = f'{qanary_api_base}/startquestionansweringwithtextquestion'

        headers = {
            'Origin': qanary_api_base,
            'Referer': url
        }

        data = {
            'question': question,
            'componentfilterinput': '',
            'componentlist[]': ['Wikidata_Lookup_NEL_component', 'Wikidata_Query_Builder_component', 'QE-Python-SPARQLExecuter']
        }

        response = requests.post(url, headers=headers, data=data, timeout=60)

        uuid = response.json()['inGraph']
        sparql_endpoint = response.json()['endpoint']

        query = f"""
        PREFIX qa: <http://www.wdaqua.eu/qa#>
        PREFIX oa: <http://www.w3.org/ns/openannotation/core/>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

        SELECT ?value
        FROM <{uuid}>
        WHERE {{
            ?answerJson a qa:AnswerJson ;
                rdf:value ?value .
        }}"""

        result = execute(query, sparql_endpoint)

        rq_vars = result["head"]["vars"]

        context = ""

        for b in result["results"]["bindings"]:
            context += " ".join([f'{b[var]["value"]}' for var in rq_vars]) + "\n"
            logger.info(f"Var1: {b[rq_vars[0]]['value']}")

        return context
    except Exception as e:
        logger.error(str(e))
        return ""

def fetch_pizza_descriptions_from_wikidata() -> dict:
    # note, this is a static SPARQL query that returns descriptions for all available pizzas
    sparql_query = """
PREFIX schema: <http://schema.org/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT * WHERE {
    ?pizza wdt:P31 wd:Q116392487 . # get all entities URIs that are an instance of the pizza type 
    ?pizza rdfs:label ?label .  # get the names of the pizza
    FILTER (lang(?label) = 'en')  # filter for English pizza names only
    ?pizza schema:description ?description # get the descriptions of the pizza
    FILTER (lang(?description) = 'en')  # filter for English pizza description only
}
ORDER BY ?label # sort by name
"""
    result = execute(sparql_query)
    return result


def check_order_intention(_input):
    example_string_1 = "I wanna order a pizza."
    assistant_docstring_1 = """{"intention": True}"""

    example_string_2 = "How are you doing today?"
    assistant_docstring_2 = """{"intention": False}"""

    chat_response = client.chat.completions.create(
        model=environ.get("MODEL_NAME"),
        messages=[
            {"role": "system", "content": """You are an Input Validation Tools.
Recognize whether the user wants to order a pizza or he/she has another intention and output the structured data as a JSON. **Output ONLY the structured data.**
Below is a text for you to analyze."""},
            {"role": "user", "content": example_string_1},
            {"role": "assistant", "content": assistant_docstring_1},
            {"role": "user", "content": example_string_2},
            {"role": "assistant", "content": assistant_docstring_2},
            {"role": "user", "content": _input}
        ]
    )

    received_message = chat_response.choices[0].message.content
    logger.info(received_message)
    return eval(received_message)["intention"]


def check_customer_address(_input):
    example_string = "My address is Gustav-Freytag Straße 12A in Leipzig."
    assistant_docstring = """[{"Leipzig": "CITY"}, {"Gustav-Freytag Straße": "STREET"}, {"12A": "HOUSE_NUMBER"}]"""
    chat_response = client.chat.completions.create(
        model=environ.get("MODEL_NAME"),
        messages=[
            {"role": "system", "content": """You are a Named Entity Recognition Tool.
Recognize named entities and output the structured data as a JSON. **Output ONLY the structured data.**
Below is a text for you to analyze."""},
            {"role": "user", "content": example_string},
            {"role": "assistant", "content": assistant_docstring},
            {"role": "user", "content": _input}
        ]
    )

    received_message = chat_response.choices[0].message.content
    logger.info(received_message)

    response_dictionary = {}
    for d in json.loads(received_message):
        response_dictionary.update(d)

    city = [k for (k, v) in response_dictionary.items() if v == "CITY"][0]
    street = [k for (k, v) in response_dictionary.items() if v == "STREET"][0]
    house_number = [
        k for (k, v) in response_dictionary.items() if v == "HOUSE_NUMBER"][0]

    payload = {"city": city, "street": street, "house_number": house_number}
    response = requests.post(
        f"{pizza_api_base}/address/validate", json=payload, timeout=5)

    if response.status_code != 200:
        return None

    logger.info("Potential Address found: " +
                str((city, street, house_number)))
    return (city, street, house_number)


def get_pizza_menu():
    response = requests.get(f"{pizza_api_base}/pizza", timeout=5)
    return ", ".join([item["name"] for item in response.json()])


def validate_pizza_name(_input):
    threshold = 80
    response = requests.get(f"{pizza_api_base}/pizza", timeout=5)
    menu = response.json()
    for item in menu:
        current_ratio = fuzz.partial_ratio(_input, list(item.values())[1])
        if (current_ratio >= threshold):
            # print("debugging: " + str(list(item.values())[1]) + " was determined type")
            return str(list(item.values())[0])
    return None


def post_order(pizza_id, address):
    city, street, house_number = address
    post = {"pizza_id": pizza_id, "city": city,
            "street": street, "house_number": house_number}
    response = requests.post(f"{pizza_api_base}/order", json=post, timeout=5)

    if response.status_code != 200:
        return None

    order_id = response.json()["order_id"]
    status = response.json()["status"]

    if status != "received":
        return None

    return order_id


def get_order(order_id):
    response = requests.get(
        f"{pizza_api_base}/address/validate/" + order_id, timeout=5)
    order = response.json()
    # TODO return order information if asked


class BasicFunctions:
    def get_last_missing_slots(state, required_slots):
        return [slot.value for slot in required_slots if slot.value not in state['slots'].keys()]

    def get_last_function_message(outputs):
        from langchain_core.messages import FunctionMessage
        return [m for m in outputs["messages"] if isinstance(m, FunctionMessage)][-1]

    def get_last_message_or_no_message(state):
        return state["messages"][-1] if len(state["messages"]) > 0 else "No message"
