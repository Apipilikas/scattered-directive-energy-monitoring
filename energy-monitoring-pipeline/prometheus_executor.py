import requests
from configuration import PROM_URL, PROM_QUERY_RANGE_STEPS

def execute_query(query: str):

    response = requests.get(
        f"{PROM_URL}/api/v1/query",
        params={query: query}
    )

    return response

def execute_query_range(query: str, start_time: float, end_time: float):
    params = {
        query: query,
        start: start_time,
        end: end_time,
        step : PROM_QUERY_RANGE_STEPS

    }
    
    response = requests.get(
        f"{PROM_URL}/api/v1/query_range",
        params=params
    )

    return response