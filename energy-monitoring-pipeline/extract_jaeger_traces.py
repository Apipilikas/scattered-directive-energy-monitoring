import configuration as conf
import os
import json
import requests
import statistics
import argparse
import matplotlib.pyplot as plt

JAEGER_TRACES_ENDPOINT = "http://localhost:16686/jaeger/api/traces"
TRACE_OPERATION = "/func: requestHandler"

def get_traces(service, operation):
    """
    Returns list of all traces for a service and an operation
    """
    params = {
        "limit": 20000,
        "service": service,
        "operation": operation
    }
    
    try:
        response = requests.get(JAEGER_TRACES_ENDPOINT, params=params)
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        raise err

    response = json.loads(response.text)
    return response

def _calculate_metrics(durations):
    """
    Calculates the count, mean, and standard deviation for a list of durations.
    """
    count = len(durations)
    
    if count == 0:
        return {}

    mean_val = statistics.mean(durations)
    std_val = statistics.stdev(durations) if count > 1 else 0.0

    return {
        "count": count,
        "mean": mean_val,
        "std": std_val
    }

def _extract_durations(traces, service: str, operation: str):
    """
    Parses Jaeger trace JSON to find specific spans and extracts their durations.
    Converts durations from microseconds to milliseconds.
    """
    durations = []

    for trace in traces:
        should_excluded = any(
            span.get("operationName") == f"{service}/func: generateChainAndDeploy" 
            for span in trace.get("spans", [])
        )
        if should_excluded:
            continue

        processes = trace.get("processes", {})
        
        target_process_ids = {
            pid for pid, process in processes.items()
            if process.get("serviceName") == service
        }

        for span in trace.get("spans", []):
            if span.get("operationName") == operation and span.get("processID") in target_process_ids:
                durations.append(span.get("duration", 0))

    return durations

def _set_font_size(plt):
    plt.rcParams.update({'font.size': 12})

def extract_traces(filepath):
    print("Extracting traces...")
    results = {}
    all_durations = []


    for service in conf.TRACE_SERVICES:
        operation = f"{service}{TRACE_OPERATION}"
        response = get_traces(service, operation)
        traces = response["data"]

        trace_filepath = f"{filepath}/trace_{service}.json"

        with open(trace_filepath, 'w') as f:
            json.dump(response, f, indent=4)
        print(f"Successfully saved metrics to: {trace_filepath}")

        durations = _extract_durations(traces, service, operation)
        
        metrics = _calculate_metrics(durations)
        results[service] = metrics

        all_durations.extend(durations)

    results["total"] = _calculate_metrics(all_durations)

    traces_filepath = f"{filepath}/{conf.TRACE_FILENAME}"

    with open(traces_filepath, 'w') as f:
        json.dump(results, f, indent=4)
    print(f"Successfully saved metrics to: {traces_filepath}")

    return results

def _print_results(results):
    print("\n> Results (in seconds)")
    for service, metrics in results.items():
        count = metrics.get('count', 0)
        
        if count > 0:            
            # Divide by 1000000 μs -> s
            mean_s = metrics['mean'] / 1000000.0
            std_s = metrics['std'] / 1000000.0
            
            svc_name = service.capitalize() if service == "total" else service
            print(f"{svc_name:<13} | Count: {count:<5} | Mean: {mean_s:>8.4f} s | Std: {std_s:>8.4f} s")

def _print_latex_table(results):
    print("\n> Printing LaTeX table: \n")
    print(r"\begin{table}[!htbp]")
    print(r"    \centering")
    print(r"    \makebox[\textwidth][c]{")
    print(r"    \begin{tabular}{lccc}")
    print(r"        \toprule")
    print(r"        \textbf{Service} & \textbf{Count} & \textbf{Mean (s)} & \textbf{Std (s)} \\")
    print(r"        \midrule")

    for service, metrics in results.items():
        if service == "overall":
            continue
            
        count = metrics.get('count', 0)
        svc_name = service.capitalize()
        
        if count == 0:
            print(f"        {svc_name} & 0 & - & - \\\\")
        else:
            mean_s = metrics['mean'] / 1000000.0
            std_s = metrics['std'] / 1000000.0
            print(f"        {svc_name} & {count} & {mean_s:.4f} & {std_s:.4f} \\\\")

    if "overall" in results:
        print(r"        \midrule")
        count = results["overall"].get('count', 0)
        
        if count == 0:
            print(r"        \textbf{Overall} & 0 & - & - \\")
        else:
            mean_s = results["overall"]['mean'] / 1000000.0
            std_s = results["overall"]['std'] / 1000000.0
            print(f"        \\textbf{{Overall}} & {count} & {mean_s:.4f} & {std_s:.4f} \\\\")

    print(r"        \bottomrule")
    print(r"    \end{tabular}}")
    print(r"    \caption{Average latency and standard deviation per service}")
    print(r"    \label{tab:latency_results}")
    print(r"\end{table}")

def _read_results(filepath):
    filename = f"{filepath}/{conf.TRACE_FILENAME}"

    print(f"Reading the results from: {filename}...")
    with open(filename, 'r') as file:
        return json.load(file)

def _generate_box_plot(filepath):
    print("> Generating box plot")

    _set_font_size(plt)
    plt.figure(figsize=(6, 5))
    data = {}

    # Read the data for each service
    for service in conf.TRACE_SERVICES:
        operation = f"{service}{TRACE_OPERATION}"
        file_path = f"{filepath}/trace_{service}.json"
        
        try:
            with open(file_path, 'r') as f:
                trace_data = json.load(f)
                
                traces = trace_data.get("data", trace_data) if isinstance(trace_data, dict) else trace_data
                
                durations = _extract_durations(traces, service, operation)
                
                if durations:
                    # FIX: Convert microseconds to seconds here for the plot
                    data[service] = [d / 1000000.0 for d in durations]
                else:
                    print(f"Warning: No matching spans found for {service} in {file_path}")
                    
        except FileNotFoundError:
            print(f"Warning: File not found -> {file_path}")

    if not data:
        print("Error: No data available to plot.")
        return

    labels = list(data.keys())
    x = [data[label] for label in labels]

    plt.boxplot(x, tick_labels=labels)
    plt.xticks(rotation=20, ha='right')

    plt.ylabel("Latency (s)")
    plt.xlabel("Services")

    plt.grid(True, axis='y', linestyle='--', alpha=0.7)

    # Save the plot
    file_name = f"{conf.PLOT_OUTPUT_FOLDER}/trace_durations_box_plot.pdf"
    plt.tight_layout()
    
    # Ensure the plot output folder exists before saving
    os.makedirs(conf.PLOT_OUTPUT_FOLDER, exist_ok=True)
    
    plt.savefig(file_name)
    plt.close()
    print(f"Plot saved in {file_name}!")

def main():
    print(f"============= Extract Jaeger traces =============")

    filepath, read, plot_box = _resolve_args()

    if read:
        results = _read_results(filepath)
    else:
        results = extract_traces(filepath)

    if plot_box:
        _generate_box_plot(filepath)

    _print_results(results)
    
def _resolve_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--filepath")
    parser.add_argument("-r", "--read", action='store_true')
    parser.add_argument("-box", "--box-plot", action='store_true')
    
    args = parser.parse_args()
    filepath_arg = args.filepath
    read_arg = args.read
    plot_box = args.box_plot

    filepath = f"{conf.TRACE_OUTPUT_PATH}/{filepath_arg}"

    os.makedirs(filepath, exist_ok=True)

    return filepath, read_arg, plot_box

if __name__ == '__main__':
    main()