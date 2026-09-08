import json

def upload_file(node, local_file_path, remote_file_path):
    print(f"Uploading file from local path [{local_file_path}] to remote path [{remote_file_path}] ...");
    node.upload_file(local_file_path=local_file_path, remote_file_path=remote_file_path);

def execute_file(node, file_path, script_args=""):
    print(f"Executing file [{file_path}] ...");
    node.execute(f"sed -i 's/\\r$//' {file_path} && chmod +x {file_path} && ./{file_path} {script_args}");

def upload_and_execute_file(node, local_file_path, remote_file_path, script_args=""):
    upload_file(node, local_file_path, remote_file_path);
    execute_file(node, remote_file_path, script_args);

def _override_files(node, file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)

        for item in data:
            local_file_path = item["local_file_path"]
            remote_file_path = item["remote_file_path"]

            upload_file(node, local_file_path, remote_file_path)
            
def override_configuration_files(node):
    _override_files(node, "overriden_files/mapping.json");
    node.execute("cd scattered-directive-energy-monitoring && sed -i 's/\\r$//' dynamos.conf");

def override_vfl_scripts_files(node):
    _override_files(node, "vfl_scripts/mapping.json");