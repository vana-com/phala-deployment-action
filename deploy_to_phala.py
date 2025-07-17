#!/usr/bin/env python3
import os
import json
import secrets
from typing import List, Dict, Any, Optional
import asyncio
import httpx
from dotenv import load_dotenv
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Load .env file if it exists (for local testing)
load_dotenv()

# --- Helper to set GitHub Action outputs ---
def set_action_output(name: str, value: Any):
    """Sets an output for the GitHub Action by appending to the GITHUB_OUTPUT file."""
    github_output_file = os.getenv("GITHUB_OUTPUT")
    if github_output_file:
        try:
            with open(github_output_file, "a") as f:
                f.write(f"{name}={value}\n")
            print(f"Action Output Set: {name}={value}")
        except Exception as e:
            print(f"Error writing to GITHUB_OUTPUT file: {e}")
    else:
        print(f"Local Run (No GITHUB_OUTPUT): {name}={value}")


# --- API Client ---
class PhalaCVMClient:
    def __init__(
            self,
            base_url: str = "https://cloud-api.phala.network/api/v1",
            timeout: float = 60.0
    ):
        self.base_url = base_url
        self.client = httpx.Client(
            base_url=base_url,
            headers={
                'Content-Type': 'application/json',
                'x-api-key': os.getenv('PHALA_CLOUD_API_KEY'),
            },
            timeout=timeout
        )

    def get_pubkey(self, vm_config: Dict[str, Any]) -> Dict[str, str]:
        """Requests the public key needed to encrypt environment variables."""
        print("Requesting pubkey with the following configuration:")
        print(json.dumps(vm_config, indent=2))
        response = self.client.post("/cvms/pubkey/from_cvm_configuration", json=vm_config)
        try:
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error Status: {e.response.status_code}")
            print(f"Full error response: {e.response.text}")
            try:
                error_details = e.response.json()
                print(f"Error details: {json.dumps(error_details, indent=2)}")
            except (json.JSONDecodeError, AttributeError):
                print("Error response is not valid JSON.")
            raise

    def create_vm(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Sends the request to create a new VM."""
        print("Sending VM creation request to Phala Cloud...")
        print("Creating VM with the following configuration:")
        print(json.dumps(config, indent=2))
        response = self.client.post("/cvms/from_cvm_configuration", json=config)
        try:
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error Status: {e.response.status_code}")
            print(f"Full error response: {e.response.text}")
            try:
                error_details = e.response.json()
                print(f"Error details: {json.dumps(error_details, indent=2)}")
            except (json.JSONDecodeError, AttributeError):
                print("Error response is not valid JSON.")
            raise

    def get_available_teepods(self) -> Dict[str, Any]:
        """Fetches the list of currently available teepods for deployment."""
        print("Requesting available Teepods from Phala Cloud...")
        response = self.client.get("/teepods/available")
        response.raise_for_status()
        return response.json()


# --- Helper Functions ---
def encrypt_env_vars(envs: List[Dict[str, str]], public_key_hex: str) -> str:
    """Encrypts a list of environment variables using the provided public key."""
    envs_json = json.dumps({"env": envs})
    private_key = x25519.X25519PrivateKey.generate()
    my_public_bytes = private_key.public_key().public_bytes_raw()
    remote_public_key = x25519.X25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex.replace("0x", "")))
    shared_key = private_key.exchange(remote_public_key)
    iv = secrets.token_bytes(12)
    aesgcm = AESGCM(shared_key)
    encrypted_data = aesgcm.encrypt(iv, envs_json.encode(), None)
    return (my_public_bytes + iv + encrypted_data).hex()

def read_file_content(file_path: str, purpose: str) -> str:
    """A generic file reader with error handling."""
    try:
        with open(file_path, 'r') as f:
            return f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"{purpose.capitalize()} file not found at: {file_path}")
    except Exception as e:
        raise IOError(f"Error reading {purpose} file at {file_path}: {e}")

# --- Core Deployment Logic ---
async def deploy(
        teepod_id: int,
        image: str,
        vm_name: str,
        vm_id: Optional[str],
        docker_compose_file_path: str,
        docker_tag: str,
        prelaunch_script_path: Optional[str],
        vcpu: int,
        memory: int,
        disk_size: int,
        env_vars_to_encrypt: List[Dict[str, str]],
) -> Dict[str, Any]:
    """Handles the main deployment logic for creating or updating a VM."""
    docker_compose_content = read_file_content(docker_compose_file_path, "Docker Compose").replace('${DOCKER_TAG}', docker_tag)
    print(f"Using Docker tag: {docker_tag}")

    compose_manifest = {
        "manifest_version": 2,
        "name": vm_name,
        "docker_compose_file": docker_compose_content,
        "tproxy_enabled": True,
        "kms_enabled": True,
        "public_sysinfo": True,
        "public_logs": False,
    }

    # Conditionally add the pre-launch script if the path is provided
    if prelaunch_script_path:
        print(f"Including pre-launch script from: {prelaunch_script_path}")
        pre_launch_script_content = read_file_content(prelaunch_script_path, "Pre-launch script")
        compose_manifest["pre_launch_script"] = pre_launch_script_content
    else:
        print("No pre-launch script provided, skipping.")

    vm_config = {
        "name": vm_name,
        "compose_manifest": compose_manifest,
        "vcpu": vcpu,
        "memory": memory,
        "disk_size": disk_size,
        "teepod_id": teepod_id,
        "image": image,
        "listed": False,
    }

    client = PhalaCVMClient()

    if vm_id:
        print(f"Update operation for VM ID '{vm_id}' is not yet implemented in this action.")
        set_action_output("operation", "update_skipped")
        # In a real scenario, you would implement the update logic here.
        return {"id": vm_id, "name": vm_name, "status": "skipped"}

    print(f"Creating new VM: {vm_name}")
    set_action_output("operation", "create")

    pubkey_info = client.get_pubkey(vm_config)
    encrypted_env = None
    if env_vars_to_encrypt:
        encrypted_env = encrypt_env_vars(env_vars_to_encrypt, pubkey_info["app_env_encrypt_pubkey"])

    create_payload = {**vm_config, "app_id_salt": pubkey_info["app_id_salt"]}
    if encrypted_env:
        create_payload["encrypted_env"] = encrypted_env

    response = client.create_vm(create_payload)
    print("VM creation initiated successfully.")
    return response

def get_env_vars_from_secrets() -> List[Dict[str, str]]:
    """Collects environment variables from secrets passed into the action."""
    env_vars = []
    env_file_path = os.getenv("INPUT_ENV_FILE_PATH")

    if not env_file_path or not os.path.exists(env_file_path):
        print("No secret environment variables provided or mapping file not found.")
        return env_vars

    with open(env_file_path, 'r') as f:
        for line in f:
            if '=' in line:
                target_var, secret_name = line.strip().split('=', 1)
                secret_value = os.getenv(secret_name)
                if secret_value:
                    env_vars.append({"key": target_var, "value": secret_value})
                else:
                    print(f"Warning: Secret '{secret_name}' is not set in the workflow's env context.")

    print(f"Collected {len(env_vars)} environment variables from secrets.")
    return env_vars

# --- Main Entry Point ---
async def main():
    """Main function driven by environment variables set by the GitHub Action."""
    try:
        # Read all configuration from environment variables
        vm_name = os.getenv("INPUT_VM_NAME")
        vm_id = os.getenv("INPUT_VM_ID") or None
        image = os.getenv("INPUT_IMAGE")
        docker_compose_file = os.getenv("INPUT_DOCKER_COMPOSE_FILE")
        docker_tag = os.getenv("INPUT_DOCKER_TAG")
        prelaunch_script_file = os.getenv("INPUT_PRELAUNCH_SCRIPT_FILE") # This can be empty or None
        teepod_id_str = os.getenv("INPUT_TEEPOD_ID")
        vcpu = int(os.getenv("INPUT_VCPU", "2"))
        memory = int(os.getenv("INPUT_MEMORY", "8192"))
        disk_size = int(os.getenv("INPUT_DISK_SIZE", "40"))

        env_vars_to_encrypt = get_env_vars_from_secrets()

        # Determine the target Teepod ID
        client = PhalaCVMClient()
        target_teepod_id = int(teepod_id_str) if teepod_id_str else None

        if not target_teepod_id:
            print("No Teepod ID specified, finding an available one...")
            available_teepods = client.get_available_teepods().get("nodes", [])
            if not available_teepods:
                raise ValueError("No available Teepods found. Cannot proceed.")
            target_teepod_id = available_teepods[0]['teepod_id']
            print(f"Automatically selected available Teepod ID: {target_teepod_id}")
        else:
            print(f"Using specified Teepod ID: {target_teepod_id}")

        # Execute deployment
        response = await deploy(
            teepod_id=target_teepod_id,
            image=image,
            vm_name=vm_name,
            vm_id=vm_id,
            docker_compose_file_path=docker_compose_file,
            docker_tag=docker_tag,
            prelaunch_script_path=prelaunch_script_file,
            vcpu=vcpu,
            memory=memory,
            disk_size=disk_size,
            env_vars_to_encrypt=env_vars_to_encrypt,
        )

        # Set action outputs based on the response
        final_vm_id = response.get("id")
        if final_vm_id:
            set_action_output("status", "success")
            set_action_output("vm-id", final_vm_id)
            set_action_output("vm-name", response.get("name", vm_name))
        else:
            set_action_output("status", "failed")
            set_action_output("vm-id", "N/A")
            set_action_output("vm-name", vm_name)

    except Exception as e:
        print(f"\nAn error occurred during deployment: {e}")
        set_action_output("status", "failed")
        # Re-raise the exception to ensure the GitHub Actions step fails
        raise

if __name__ == "__main__":
    asyncio.run(main())