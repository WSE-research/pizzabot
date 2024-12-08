import requests
import json
from os import environ
from openai import OpenAI
from dotenv import load_dotenv
from fuzzywuzzy import fuzz
import logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
openai_api_key = environ.get('OPENAI_API_KEY')
openai_api_base = environ.get('OPENAI_API_BASE')

client = OpenAI(
    api_key=openai_api_key,
    base_url=openai_api_base,
)

def check_customer_address(input):    
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
            {"role": "user", "content": input}
        ]
    )
    
    received_message = chat_response.choices[0].message.content
    logger.info(received_message)
    
    response_dictionary = {}
    for d in json.loads(received_message):
        response_dictionary.update(d)
        
    city = [k for(k , v) in response_dictionary.items() if v == "CITY"][0]
    street = [k for (k , v) in response_dictionary.items() if v == "STREET"][0]
    house_number = [k for (k , v) in response_dictionary.items() if v == "HOUSE_NUMBER"][0]

    payload = {"city": city, "street": street, "house_number": house_number}
    response = requests.post("https://demos.swe.htwk-leipzig.de/pizza-api/address/validate", json=payload, timeout=1) 

    if response.status_code != 200:
        return None

    logger.info("Potential Address found: " + str((city, street, house_number)))
    return (city, street, house_number)


def validate_pizza_name(input):
    threshold = 80
    response = requests.get("https://demos.swe.htwk-leipzig.de/pizza-api/pizza", timeout=1)
    menu = response.json()
    for item in menu:
        current_ratio = fuzz.partial_ratio(input, list(item.values())[1])
        if(current_ratio >= threshold):
            #print("debugging: " + str(list(item.values())[1]) + " was determined type")
            return str(list(item.values())[0])
    return None

def post_order(pizza_id, address):
    city, street, house_number = address
    post = {"pizza_id": pizza_id, "city": city, "street": street, "house_number": house_number}
    response = requests.post("https://demos.swe.htwk-leipzig.de/pizza-api/order", json=post, timeout=1)

    if response.status_code != 200:
        return None
    
    order_id = response.json()["order_id"]
    status = response.json()["status"]

    if status != "received":
        return None
    
    return order_id
    

    
def get_order(order_id):
    response = requests.get("https://demos.swe.htwk-leipzig.de/pizza-api/address/validate/" + order_id, timeout=1)
    order = response.json()
    #TODO return order information if asked