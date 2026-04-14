import requests
from configuration import PROM_URL, PROM_QUERY_RANGE_STEPS, get_namespaces

def execute_query(query: str):

    response = requests.get(
        f"{PROM_URL}/api/v1/query",
        params={"query": query}
    )

    return response

def execute_query_range(query: str, start_time: float, end_time: float):
    print(f"Executing [query_range] query: [{query}]")

    params = {
        "query": query,
        "start": start_time,
        "end": end_time,
        "step" : PROM_QUERY_RANGE_STEPS

    }
    
    response = requests.get(
        f"{PROM_URL}/api/v1/query_range",
        params=params
    )

    return _filter_query_range_response(response)

def _filter_query_range_response(response: requests.Response):
    data = {}

    if response.status_code == 200:
        namespaces = get_namespaces()
        results = response.json()["data"]["result"]

        for result in results:
            metric = result["metric"]
            namespace = None

            if not "namespace" in metric:
                continue
            else:
                namespace = metric["namespace"]

            if not namespace is None and namespace in namespaces:
                data[namespace] = result["values"]
    else:
        raise Exception(
            f"Query range execution failed: Status code received [{response.status_code}]. Content: {response.content}"
            )
    
    return data