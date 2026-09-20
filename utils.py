import re
import requests
import json
from openai import OpenAI
from fuzzywuzzy import fuzz
from SPARQLWrapper import SPARQLWrapper, JSON
import logging




logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# One place reads .env: settings.py. Everything here -- endpoints, keys, the
# model name, the offline switch -- comes from there, so the frontend, the
# console bot and this module can never disagree about the configuration.
from settings import settings

pizza_api_base = settings.pizza_api_base
openai_api_key = settings.openai_api_key
openai_api_base = settings.openai_api_base
qanary_api_base = settings.qanary_api_base

_openai = None          # the client, once something has actually needed it


def _client() -> OpenAI:
    """The OpenAI client, built on first use and never at import time.

    A fresh checkout has no .env yet, and offline mode has no endpoint at all
    -- importing this module must work in both cases. The only three callers
    are the LLM-backed functions below, and each of them checks offline_mode()
    before it gets here.
    """
    global _openai
    if _openai is None:
        if not openai_api_key:
            raise RuntimeError(
                "No OPENAI_API_KEY. Copy .env-example to .env and fill it in, "
                "or set PIZZABOT_OFFLINE=1 to use the rule implementations.")
        _openai = OpenAI(api_key=openai_api_key, base_url=openai_api_base)
    return _openai

# =========================================================================
# Offline mode
# -------------------------------------------------------------------------
# Three functions below need an OpenAI-compatible endpoint, whichever one
# OPENAI_API_BASE names. With PIZZABOT_OFFLINE=1 they are replaced by
# deterministic rules, so the bot can be demonstrated in a lecture hall with
# no endpoint reachable at all -- no VPN, no key, no network.
#
# This is not a hack: the rule version *is* the static implementation of
# iteration 1, and the LLM version is iteration 2 behind the same contract
# -- same input, same output, same defined failure (None / False).
# =========================================================================

def offline_mode() -> bool:
    """True when the rule-based stand-ins should be used instead of the LLM."""
    return settings.offline


def llm_reachable(timeout: float = 3.0) -> bool:
    """One GET against <OPENAI_API_BASE>/models -- used by run_local.sh."""
    if not openai_api_base:
        return False
    try:
        response = requests.get(
            f"{openai_api_base.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {openai_api_key}"},
            timeout=timeout,
        )
        return response.status_code < 500
    except requests.RequestException as e:
        logger.info(f"LLM endpoint not reachable: {e}")
        return False


def implementation_of(function_name: str) -> str:
    """Which implementation answers right now -- shown in the frontend."""
    return "rule" if offline_mode() else "llm"


ORDER_KEYWORDS = ("order", "pizza", "hungry", "delivery", "deliver", "buy",
                  "bestellen", "essen", "commander")
SMALLTALK_KEYWORDS = ("how are you", "weather", "joke", "who are you",
                      "your name", "hello", "hi ", "thanks", "thank you")

# Parsed out of an address: "Maksim Gorki Str 58, Leipzig",
# "Leipzig, Maksim Gorki Str. 58", "Gustav-Freytag Strasse 12A in Leipzig".
HOUSE_NUMBER_RE = re.compile(r"\b(\d{1,4}\s?[a-zA-Z]?)\b")
FILLER_WORDS = ("my address is", "i live at", "i live in", "deliver to",
                "delivery to", "please deliver", "address:", "it is", "its",
                "in", "at", "to")

STATIC_DESCRIPTIONS = {
    "margherita": "A Margherita is the classic: tomato, mozzarella and fresh basil -- the three colours of the Italian flag.",
    "pepperoni": "A Pepperoni comes with tomato, mozzarella and spicy salami slices.",
    "hawaiian": "A Hawaiian is topped with ham and pineapple pieces -- the pizza people argue about.",
    "quattro formaggi": "Quattro Formaggi means four cheeses: mozzarella, gorgonzola, parmesan and fontina. No tomato sauce needed.",
    "funghi": "A Funghi is tomato, mozzarella and mushrooms.",
    "salami": "A Salami is tomato, mozzarella and salami slices.",
    "prosciutto": "A Prosciutto carries tomato, mozzarella and thin slices of Italian ham.",
    "diavola": "A Diavola is the hot one: tomato, mozzarella, spicy salami and chilli.",
    "vegetariana": "A Vegetariana is tomato, mozzarella and whatever vegetables are in season.",
    "calzone": "A Calzone is folded shut before baking -- a pizza turned into a pocket.",
    "marinara": "A Marinara has no cheese at all: tomato, garlic, oregano and olive oil.",
    "tonno": "A Tonno is tomato, mozzarella, tuna and onions.",
    # ids 21-22 of GET /pizza, added 2026-09-20: one declared vegetarian, one
    # declared vegan. They differ by the mozzarella, which is the whole point.
    "ortolana": "An Ortolana is the vegetarian one: tomato, mozzarella and grilled courgette, aubergine and peppers.",
    "verdure": "A Verdure is our vegan pizza: grilled vegetables on tomato, with olive oil and oregano -- no cheese, no animal product at all.",
}


def rule_generate_pizza_description(_input, context) -> str:
    """Offline stand-in: look the pizza up in a static table."""
    text = _input.lower()
    for name, description in STATIC_DESCRIPTIONS.items():
        if name in text:
            return description
    if context:
        return str(context).strip().split("\n")[0]
    return ("I can only describe the pizzas on our menu -- ask me about one of "
            "them, for example \"Tell me more about the Hawaiian\".")


def generate_pizza_description(_input, context) -> str:
    if offline_mode():
        return rule_generate_pizza_description(_input, context)

    final_prompt = f"""
Here is the context with pizza descriptions: {context}

Here is the user message: {_input}
"""

    chat_response = _client().chat.completions.create(
        model=settings.model_name,
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
    if offline_mode():
        logger.info("Offline mode: skipping the Qanary pipeline")
        return ""

    try:
        url = f'{qanary_api_base}/startquestionansweringwithtextquestion'
        
        logger.info(f"Calling Qanary pipeline at: {url}")

        headers = {
            'Origin': qanary_api_base,
            'Referer': url
        }

        data = {
            'question': question,
            'componentfilterinput': '',
            'componentlist[]': ['Alex-Wikidata_Lookup_NEL_component', 'Alex-Wikidata_Query_Builder_component', 'Alex-QE-Python-SPARQLExecuter'] # our component sequence
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

        result = eval(execute(query, sparql_endpoint)["results"]["bindings"][0]["value"]["value"]) # response format from Virtuoso is weird

        rq_vars = result["head"]["vars"]

        context = ""

        for b in result["results"]["bindings"]:
            context += " ".join([f'{b[var]["value"]}' for var in rq_vars]) + "\n"

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


def rule_check_order_intention(_input) -> bool:
    """Offline stand-in: keyword rule over the input and the live menu."""
    text = _input.lower()
    if any(keyword in text for keyword in SMALLTALK_KEYWORDS) and not any(
            keyword in text for keyword in ORDER_KEYWORDS):
        return False
    if any(keyword in text for keyword in ORDER_KEYWORDS):
        return True
    try:                                   # "Hawaiian, please" is an order too
        menu = [item["name"].lower() for item in
                requests.get(f"{pizza_api_base}/pizza", timeout=5).json()]
    except (requests.RequestException, ValueError, KeyError):
        menu = list(STATIC_DESCRIPTIONS)
    return any(name in text for name in menu)


def check_order_intention(_input):
    if offline_mode():
        intention = rule_check_order_intention(_input)
        logger.info(f'{{"intention": {intention}}}  (rule)')
        return intention

    example_string_1 = "I wanna order a pizza."
    assistant_docstring_1 = """{"intention": True}"""

    example_string_2 = "How are you doing today?"
    assistant_docstring_2 = """{"intention": False}"""

    chat_response = _client().chat.completions.create(
        model=settings.model_name,
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


def rule_extract_address(_input):
    """Offline stand-in for the NER call: city, street and house number.

    The *validation* is not part of the rule -- it stays with the Pizza API,
    exactly as in the LLM version below.
    """
    text = " ".join(_input.split())
    number_match = HOUSE_NUMBER_RE.search(text)
    if not number_match:
        return None
    house_number = number_match.group(1).replace(" ", "")

    parts = [part.strip(" .,") for part in re.split(r"[,;]| in ", text) if part.strip(" .,")]
    parts = [part for part in parts if part.lower() not in FILLER_WORDS]
    if len(parts) < 2:
        return None

    street_part = next((p for p in parts if number_match.group(1) in p), parts[0])
    city_part = next((p for p in parts if p is not street_part), parts[-1])

    street = HOUSE_NUMBER_RE.sub("", street_part).strip(" .,")
    for filler in FILLER_WORDS:
        if street.lower().startswith(filler):
            street = street[len(filler):].strip(" .,")
    city = city_part.strip(" .,")

    if not street or not city:
        return None
    return city, street, house_number


def validate_address(city, street, house_number):
    """The one contract both implementations end in: the API decides."""
    payload = {"city": city, "street": street, "house_number": house_number}
    try:
        response = requests.post(
            f"{pizza_api_base}/address/validate", json=payload, timeout=5)
    except requests.RequestException as e:
        logger.error(f"Pizza API not reachable: {e}")
        return None
    if response.status_code != 200:
        return None
    logger.info("Potential Address found: " + str((city, street, house_number)))
    return (city, street, house_number)


def check_customer_address(_input):
    if offline_mode():
        parsed = rule_extract_address(_input)
        logger.info(f"{parsed}  (rule)")
        if parsed is None:
            return None
        return validate_address(*parsed)

    example_string = "My address is Gustav-Freytag Straße 12A in Leipzig."
    assistant_docstring = """[{"Leipzig": "CITY"}, {"Gustav-Freytag Straße": "STREET"}, {"12A": "HOUSE_NUMBER"}]"""
    chat_response = _client().chat.completions.create(
        model=settings.model_name,
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

    try:                       # a model may answer with anything at all
        response_dictionary = {}
        for d in json.loads(received_message):
            response_dictionary.update(d)

        city = [k for (k, v) in response_dictionary.items() if v == "CITY"][0]
        street = [k for (k, v) in response_dictionary.items() if v == "STREET"][0]
        house_number = [
            k for (k, v) in response_dictionary.items() if v == "HOUSE_NUMBER"][0]
    except (ValueError, IndexError, TypeError) as e:
        logger.error(f"Could not read an address out of the model answer: {e}")
        return None                            # the defined failure

    return validate_address(city, street, house_number)


def get_pizza_menu():
    response = requests.get(f"{pizza_api_base}/pizza", timeout=5)
    return ", ".join([item["name"] for item in response.json()])


def get_delivery_area() -> str:
    """The sentence the bot uses when an address is rejected."""
    try:
        cities = requests.get(f"{pizza_api_base}/city", timeout=5)
        total = cities.headers.get("X-Total-Count")
        if total and int(total) > 20:
            places = f"{int(total):,}".replace(",", " ")
            return ("Leipzig, Halle, Dresden and every commune of France "
                    f"({places} places).")
    except (requests.RequestException, ValueError):
        pass
    return "Leipzig, Halle and Dresden."


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
