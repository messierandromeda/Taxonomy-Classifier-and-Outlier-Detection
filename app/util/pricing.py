from ..config import PRICES, DEFAULT_MODEL

def calc_pricing(prompt_tokens: int, completion_tokens: int, cached_tokens: int, model: str = DEFAULT_MODEL) -> float:    
    """
    Calculates the cost of a request based on its amount of tokens and the prices of the models given by OpenAI
    The cost is given in USD as that is what OpenAI displays
    Works for the models defined in PRICES
    """
    prompt_tokens /= 10**6
    completion_tokens /= 10**6
    cached_tokens /= 10**6
    
    cost = PRICES[model]['input'] * prompt_tokens + PRICES[model]['output'] * completion_tokens

    if model == 'gpt-4.1-nano':
        cached_cost = 0.025
    else:
        cached_cost = PRICES[model]['input'] / 10
    
    cost += cached_cost * cached_tokens
    
    return cost