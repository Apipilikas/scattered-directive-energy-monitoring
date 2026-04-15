import time
import json
import argparse

def get_time_range(minutes_before: int) -> tuple[float, float]:

    end_time = time.time()
    start_time = end_time - (minutes_before * 60)

    return start_time, end_time


def extract_property_from_json(file_path: str, property_name: str):
    lst = []
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
            
            if isinstance(data, list):
                for item in data:
                    if property_name in item:
                        lst.append(item[property_name])

            
        return lst

    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
    except json.JSONDecodeError:
        print(f"Error: '{file_path}' is not a valid JSON file.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def add_boolean_argument(parser: argparse.ArgumentParser, arg_tuple: tuple[str, str, str]):
    arg_flag = arg_tuple[0]
    arg_name = arg_tuple[1]
    help = arg_tuple[2]
    parser.add_argument(
        arg_flag, arg_name, action='store_true', help=help
        )