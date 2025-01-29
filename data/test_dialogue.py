from langchain_core.messages import AIMessage, FunctionMessage


correct_dialogue = [
    { # Initial message
        "inputs": {
            'input': 'I want to order pizza', 
            'slots': {}, 
            'messages': [], 
            'active_order': False, 
            'confirm_order': False, 
            'current_intent': 'default', 
            'invalid': False, 
            'ended': False, 
            'pizza_id': None, 
            'customer_address': None
        },
        "outputs": {
            "expected": 'What pizza would you like to order?\nOr should I describe the pizza for you? Here are the options: Margherita, Pepperoni, Hawaiian, Quattro Formaggi',
            'slots': {}, 
            'messages': [
                AIMessage(
                    content='What pizza would you like to order?\nOr should I describe the pizza for you? Here are the options: Margherita, Pepperoni, Hawaiian, Quattro Formaggi',
                    additional_kwargs={}, 
                    response_metadata={}
                ), 
                FunctionMessage(
                    content='pizza_name', 
                    additional_kwargs={}, 
                    response_metadata={}, 
                    name='pizza_name'
                )
            ], 
            'active_order': True, 
            'confirm_order': False, 
            'current_intent': 'default', 
            'invalid': False, 
            'ended': False, 
            'pizza_id': None, 
            'customer_address': None
        }
    },
    {
        "inputs": {
            'input': 'I want to order Hawaiian', 
            'slots': {}, 
            'messages': [
                AIMessage(
                    content='What pizza would you like to order?\nOr should I describe the pizza for you? Here are the options: Margherita, Pepperoni, Hawaiian, Quattro Formaggi',
                    additional_kwargs={}, 
                    response_metadata={}
                ), 
                FunctionMessage(
                    content='pizza_name', 
                    additional_kwargs={}, 
                    response_metadata={}, 
                    name='pizza_name'
                )
            ], 
            'active_order': True, 
            'confirm_order': False, 
            'current_intent': 'default', 
            'invalid': False, 
            'ended': False, 
            'pizza_id': None, 
            'customer_address': None
        },
        "outputs": {
            "expected": 'What is your delivery address?',
            'slots': {'pizza_name': 'i want to order hawaiian'}, 
            'messages': [
                AIMessage(
                    content='What pizza would you like to order?\nOr should I describe the pizza for you? Here are the options: Margherita, Pepperoni, Hawaiian, Quattro Formaggi',
                    additional_kwargs={}, 
                    response_metadata={}
                ), 
                FunctionMessage(
                    content='pizza_name', 
                    additional_kwargs={}, 
                    response_metadata={}, 
                    name='pizza_name'
                ), 
                AIMessage(
                    content='What is your delivery address?', 
                    additional_kwargs={}, 
                    response_metadata={}
                ), 
                FunctionMessage(
                    content='customer_address', 
                    additional_kwargs={}, 
                    response_metadata={}, 
                    name='customer_address'
                )
            ], 
            'active_order': True, 
            'confirm_order': False, 
            'invalid': False, 
            'ended': False, 
            'pizza_id': '3', 
            'customer_address': None
        }
    },
    {
         "inputs": {
            'input': 'Leipzig, Maksim Gorki Str. 58', 
            'slots': {'pizza_name': 'i want to order hawaiian'}, 
            'messages': [
                AIMessage(
                    content='What pizza would you like to order?\nOr should I describe the pizza for you? Here are the options: Margherita, Pepperoni, Hawaiian, Quattro Formaggi',
                    additional_kwargs={}, 
                    response_metadata={}
                ), 
                FunctionMessage(
                    content='pizza_name', 
                    additional_kwargs={}, 
                    response_metadata={}, 
                    name='pizza_name'
                ), 
                AIMessage(
                    content='What is your delivery address?', 
                    additional_kwargs={}, 
                    response_metadata={}
                ), 
                FunctionMessage(
                    content='customer_address', 
                    additional_kwargs={}, 
                    response_metadata={}, 
                    name='customer_address'
                )
            ], 
            'active_order': True, 
            'confirm_order': False, 
            'invalid': False, 
            'ended': False, 
            'pizza_id': '3', 
            'customer_address': None
        },
        "outputs": {
            "expected": 'Thank you for providing all the details. Your order is being processed! Keep your order id ready incase you have further inquiries: <SOME UUID>.',
            'slots': {'pizza_name': 'i want to order hawaiian', 'customer_address': 'leipzig, maksim gorki str 58'}, 
            'messages': [
                AIMessage(
                    content='What pizza would you like to order?\nOr should I describe the pizza for you? Here are the options: Margherita, Pepperoni, Hawaiian, Quattro Formaggi', 
                    additional_kwargs={}, 
                    response_metadata={}
                ), 
                FunctionMessage(
                    content='pizza_name',
                    additional_kwargs={}, 
                    response_metadata={}, 
                    name='pizza_name'
                ), 
                AIMessage(
                    content='What is your delivery address?', 
                    additional_kwargs={}, 
                    response_metadata={}
                ), 
                FunctionMessage(
                    content='customer_address', 
                    additional_kwargs={}, 
                    response_metadata={}, 
                    name='customer_address'
                ), 
                AIMessage(
                    content='Thank you for providing all the details. Your order is being processed! Keep your order id ready incase you have further inquiries: 2bcc9adf-d083-49a9-b2ec-5bc5688d618f .', 
                    additional_kwargs={}, 
                    response_metadata={}
                )
            ],
            'active_order': True, 
            'confirm_order': False, 
            'invalid': False, 
            'ended': True, 
            'pizza_id': '3', 
            'customer_address': ('Leipzig', 'Maksim Gorki Str', '58'), 
            'order_id': '2bcc9adf-d083-49a9-b2ec-5bc5688d618f'
        }
    }
]

