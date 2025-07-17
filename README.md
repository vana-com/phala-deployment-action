# Phala Cloud CVM Deployment Action

A reusable GitHub Action to deploy a Confidential Virtual Machine (CVM) to [Phala Cloud](https://phala.network/cloud/).

This action automates the process of creating or updating a CVM by wrapping the Phala Cloud API in a simple, configurable workflow step. It handles everything from selecting an available node to encrypting environment variables.

## Usage

To use this action, add the following step to your GitHub workflow file (e.g., `.github/workflows/deploy.yml`).

```yaml
name: Deploy to Phala Cloud

on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Deploy CVM to Phala
        id: phala-deployment
        uses: vana-com/phala-deployment-action@v1 # Use your action's repository
        with:
          phala-cloud-api-key: ${{ secrets.PHALA_CLOUD_API_KEY }}
          vm-name: 'my-cvm-app'
          docker-compose-file: 'docker-compose.prod.yml'
          docker-tag: ${{ github.sha }}
          # Optional: Pass secrets as environment variables
          env-vars-from-secrets: |
            {
              "MY_API_KEY_SECRET": "API_KEY",
              "DATABASE_URL_SECRET": "DATABASE_URL"
            }
        env:
          # Define the secrets that env-vars-from-secrets maps
          MY_API_KEY_SECRET: ${{ secrets.MY_API_KEY }}
          DATABASE_URL_SECRET: ${{ secrets.DATABASE_URL }}

      - name: Display Deployment Output
        run: |
          echo "Deployment Status: ${{ steps.phala-deployment.outputs.status }}"
          echo "CVM ID: ${{ steps.phala-deployment.outputs.vm-id }}"
```

## Inputs

| Input                     | Description                                                                                             | Required | Default                    |
| ------------------------- | ------------------------------------------------------------------------------------------------------- | -------- | -------------------------- |
| `phala-cloud-api-key`     | The API key for authenticating with the Phala Cloud API. Store this as a [GitHub secret](https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions). | `true`   |                            |
| `vm-name`                 | Name for the CVM. Defaults to the GitHub repository name if not provided.                               | `false`  | (repo name)                |
| `vm-id`                   | The ID of an existing VM to update. If provided, the action performs an update instead of a creation.     | `false`  |                            |
| `image`                   | The base image for the CVM.                                                                             | `false`  | `dstack-dev-0.3.5`         |
| `docker-compose-file`     | Path to the Docker Compose file, relative to the repository root.                                       | `true`   | `docker-compose.phala.yml` |
| `docker-tag`              | The tag for the Docker image specified in the compose file.                                             | `false`  | `latest`                   |
| `prelaunch-script-file`   | Optional path to a pre-launch script to be executed in the CVM.                                         | `false`  |                            |
| `teepod-id`               | Specific Teepod ID to deploy to. If omitted, an available one is chosen automatically.                    | `false`  |                            |
| `vcpu`                    | Number of virtual CPUs for the CVM.                                                                     | `false`  | `2`                        |
| `memory`                  | Memory in MB for the CVM.                                                                               | `false`  | `8192`                     |
| `disk-size`               | Disk size in GB for the CVM.                                                                            | `false`  | `40`                       |
| `env-vars-from-secrets`   | A JSON string mapping GitHub secret names to the target environment variable names inside the CVM.        | `false`  | `{}`                       |

## Outputs

| Output    | Description                                                 |
| --------- | ----------------------------------------------------------- |
| `status`  | The final status of the deployment (`success` or `failed`). |
| `vm-id`   | The ID of the created or updated CVM.                       |
| `vm-name` | The name of the CVM.                                        |
| `operation` | The operation performed (`create` or `update_skipped`).   |
