import requests
from configuration import PROM_URL, PROM_QUERY_RANGE_STEPS, get_containers, CADVISOR_LABEL, KEPLER_LABEL

METRIC_STEP = 5  # In seconds
MAX_RESOLUTION = 11_000  # Maximum resolution of Prometheus
DURATION = "1m"

def _merge(x, y):
    data = x
    for key in y:
        data[key] = x.get(key, []) + y[key]
    return data

def execute_query(query: str):
    print(f"Executing [query_range] query [{query}].")

    params = {
        "query": query
    }

    response = requests.get(
        f"{PROM_URL}/api/v1/query",
        params=params
    )

    return _filter_query_response(response)

def execute_query_range(query: str, start_time: float, end_time: float):
    # If all the data can be collected in only one request
    if not (end_time - start_time) / METRIC_STEP > MAX_RESOLUTION:
        return _execute_query_range(query, start_time, end_time)

    data = {}
    start = start_time
    end = start_time
    while end < end_time:
        end = min(end + MAX_RESOLUTION, end_time)
        d = _execute_query_range(query, start, end)
        data = _merge(data, d)
        start = end + 1
    return data

def _execute_query_range(query: str, start_time: float, end_time: float):
    print(f"Executing [query_range] query [{query}] from [{start_time}] to [{end_time}]")

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

def _filter_query_response(response: requests.Response):
    return _filter_response(response, "Query", lambda r: r["value"][1])

def _filter_query_range_response(response: requests.Response):
    return _filter_response(response, "Query range", lambda r: r["values"])

def _filter_response(response: requests.Response, caller_name: str, process_result_fnc):
    data = {}

    if response.status_code == 200:
        containers = get_containers()
        results = response.json()["data"]["result"]

        for result in results:
            metric = result["metric"]
            container = None
            
            if CADVISOR_LABEL in metric:
                container = metric[CADVISOR_LABEL]
            elif KEPLER_LABEL in metric:
                container = metric[KEPLER_LABEL]
            elif "pod_name" in metric:
                container = get_container_name_from_pod_name(str(metric["pod_name"]), containers)

            if not container is None and container in containers:
                data[container] = process_result_fnc(result)
    else:
        raise Exception(
            f"{caller_name} execution failed: Status code received [{response.status_code}]. Content: {response.content}"
            )
    
    return data

def get_container_name_from_pod_name(pod_name: str, containers):
    for container in containers:
        if pod_name.startswith(container):
            return container
    
    return None