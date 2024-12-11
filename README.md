# Python examples

## Pizza Bot (`pizzabot.py`)

A simple chatbot that runs a straightforward conversation for pizza ordering.

The Pizza Bot's dialogue graph is presented below:

![image info](./assets/pizzabot.png)

### How to run

1. Run `python pizzabot.py` within the `python_examples/`
2. Follow the dialogue in your console

#### `.env` file

```.env
OPENAI_API_KEY=SECRET
MODEL_NAME=CHECK THE AVAILABLE AT http://gpu01.imn.htwk-leipzig.de:8081/v1/models
OPENAI_API_BASE=http://gpu01.imn.htwk-leipzig.de:8081/v1
PIZZA_API_BASE=https://demos.swe.htwk-leipzig.de/pizza-api
```

## External Tools

Pizza API: https://demos.swe.htwk-leipzig.de/pizza-api/docs

## Requirements

Make sure you have:
* Python 3.9 or higher
* Installed the libs from `requirements.txt`
