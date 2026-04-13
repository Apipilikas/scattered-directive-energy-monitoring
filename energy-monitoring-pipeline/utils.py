import time

def get_time_range(minutes_before: int) -> tuple[float, float]:

    end_time = time.time()
    start_time = end_time - (minutes_before * 60)

    return start_time, end_time