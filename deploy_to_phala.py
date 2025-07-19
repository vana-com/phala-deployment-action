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

    def _handle_error(self, e: httpx.HTTPStatusError):
        """A centralized error handler for API requests."""
        print(f"HTTP Error Status: {e.response.status_code}")
        print(f"Full error response: {e.response.text}")
        try:
            error_details = e.response.json()
            print(f"Error details: {json.dumps(error_details, indent=2)}")
        except (json.JSONDecodeError, AttributeError):
            print("Error response is not valid JSON.")
        raise

    def get_pubkey(self, vm_config: Dict[str, Any]) -> Dict[str, str]:
        """Requests the public key needed to encrypt environment variables."""
        print("Requesting pubkey with the following configuration:")
        print(json.dumps(vm_config, indent=2))
        response = self.client.post("/cvms/pubkey/from_cvm_configuration", json=vm_config)
        try:
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            self._handle_error(e)

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
            self._handle_error(e)

    def get_vm_compose(self, vm_id: str) -> Dict[str, Any]:
        """Gets the compose manifest of a VM to retrieve its public key."""
        print(f"Fetching compose details for VM ID: {vm_id}")
        response = self.client.get(f"/cvms/{vm_id}/compose")
        try:
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            self._handle_error(e)

    def update_vm_compose(self, vm_id: str, compose_manifest: Dict[str, Any], encrypted_env: Optional[str]) -> Dict[str, Any]:
        """Sends the request to update an existing VM."""
        print(f"Sending update request for VM ID: {vm_id}")
        payload = {"compose_manifest": compose_manifest}
        if encrypted_env:
            payload["encrypted_env"] = encrypted_env

        print("Updating VM with the following payload (using PATCH):")
        print(json.dumps(payload, indent=2))

        response = self.client.put(f"/cvms/{vm_id}/compose", json=payload)
        try:
            response.raise_for_status()
            print("VM update request accepted successfully.")
            return response.json()
        except httpx.HTTPStatusError as e:
            self._handle_error(e)

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

def get_env_vars_from_doppler_json() -> List[Dict[str, str]]:
    """
    Parses the Doppler secrets JSON, excludes specified keys,
    and formats the result for encryption.
    """
    secrets_json_str = os.getenv("INPUT_DOPPLER_SECRETS_JSON")
    exclude_json_str = os.getenv("INPUT_EXCLUDE_ENV_VARS", "[]")

    if not secrets_json_str:
        print("Warning: No Doppler secrets JSON was provided.")
        return []

    try:
        secrets_dict = json.loads(secrets_json_str)
        exclude_list = json.loads(exclude_json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format provided to the action: {e}")

    env_vars_to_encrypt = []
    print(f"Processing {len(secrets_dict)} secrets from Doppler...")

    for key, value in secrets_dict.items():
        if key in exclude_list:
            print(f"  - Excluding '{key}' as requested.")
            continue
        if value is not None:
            env_vars_to_encrypt.append({"key": key, "value": str(value)})
            print(f"  - Adding '{key}' for encryption.")
        else:
            print(f"  - Skipping '{key}' because its value is null.")

    return env_vars_to_encrypt


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

    client = PhalaCVMClient()

    # --- UPDATE LOGIC ---
    if vm_id and vm_id.strip():
        print(f"Updating existing VM with ID: {vm_id}")
        try:
            vm_compose = client.get_vm_compose(vm_id)
        except httpx.HTTPStatusError as e:
            print(f"Failed to get compose details for VM {vm_id}: {e}")
            raise ValueError(f"Could not retrieve details for VM ID {vm_id}. Ensure it exists and is accessible.")
        set_action_output("operation", "update")

        # For an update, we only need a minimal compose manifest.
        update_compose_manifest = {
            "name": vm_name,
            "docker_compose_file": docker_compose_content,
            "public_logs": vm_compose.get("public_logs", False),
        }
        if prelaunch_script_path and prelaunch_script_path.strip():
            pre_launch_script_content = read_file_content(prelaunch_script_path, "Pre-launch script")
            update_compose_manifest["pre_launch_script"] = pre_launch_script_content

        encrypted_env = None
        if env_vars_to_encrypt:
            # Fetch the VM's public key to re-encrypt env vars
            pubkey_info = client.get_vm_compose(vm_id)
            encrypted_env = encrypt_env_vars(env_vars_to_encrypt, pubkey_info["env_pubkey"])

        client.update_vm_compose(
            vm_id=vm_id,
            compose_manifest=update_compose_manifest,
            encrypted_env=encrypted_env
        )
        # Manually construct a success response as the update API response may be minimal
        return {"id": vm_id, "name": vm_name, "status": "success"}

    # --- CREATE LOGIC ---
    print(f"Creating new VM: {vm_name}")
    set_action_output("operation", "create")

    compose_manifest = {
        "manifest_version": 2, "name": vm_name, "docker_compose_file": docker_compose_content,
        "tproxy_enabled": True, "kms_enabled": True, "public_sysinfo": True, "public_logs": False,
    }
    if prelaunch_script_path and prelaunch_script_path.strip():
        compose_manifest["pre_launch_script"] = read_file_content(prelaunch_script_path, "Pre-launch script")

    vm_config = {
        "name": vm_name, "compose_manifest": compose_manifest, "vcpu": vcpu, "memory": memory,
        "disk_size": disk_size, "teepod_id": teepod_id, "image": image, "listed": False,
    }

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
        prelaunch_script_file = os.getenv("INPUT_PRELAUNCH_SCRIPT_FILE")
        teepod_id_str = os.getenv("INPUT_TEEPOD_ID")
        vcpu = int(os.getenv("INPUT_VCPU", "2"))
        memory = int(os.getenv("INPUT_MEMORY", "8192"))
        disk_size = int(os.getenv("INPUT_DISK_SIZE", "40"))

        env_vars_to_encrypt = get_env_vars_from_doppler_json()

        # Determine the target Teepod ID
        client = PhalaCVMClient()
        target_teepod_id = int(teepod_id_str) if teepod_id_str else None

        if not vm_id and not target_teepod_id:
            print("No Teepod ID specified, finding an available one...")
            available_teepods = client.get_available_teepods().get("nodes", [])
            if not available_teepods:
                raise ValueError("No available Teepods found. Cannot proceed.")
            target_teepod_id = available_teepods[0]['teepod_id']
            print(f"Automatically selected available Teepod ID: {target_teepod_id}")
        elif target_teepod_id:
            print(f"Using specified Teepod ID: {target_teepod_id}")
        else: # vm_id is present, teepod_id is not needed for update
            pass

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
        if final_vm_id and response.get("status") != "skipped":
            set_action_output("status", "success")
            set_action_output("vm-id", final_vm_id)
            set_action_output("vm-name", response.get("name", vm_name))
        else:
            set_action_output("status", "failed")
            set_action_output("vm-id", vm_id or "N/A")
            set_action_output("vm-name", vm_name)

    except Exception as e:
        print(f"\nAn error occurred during deployment: {e}")
        set_action_output("status", "failed")
        # Re-raise the exception to ensure the GitHub Actions step fails
        raise

if __name__ == "__main__":
    if not os.getenv("GITHUB_ACTIONS"):
        print("Running in local mode. Please ensure necessary INPUT_* env vars are set for testing.")

    asyncio.run(main())