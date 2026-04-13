from configuration import COLLECT_MINUTES_BEFORE
from utils import get_time_range
from prometheus_executor import execute_query_range

def main():
    
    start_time, end_time = get_time_range(COLLECT_MINUTES_BEFORE)

    return

if __name__ == '__main__':
    main()