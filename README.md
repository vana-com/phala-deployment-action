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
          vm-name: 'my-production-app'
          docker-compose-file: 'docker-compose.prod.yml'
          docker-tag: ${{ github.sha }}
          # Optional: Pass secrets as environment variables
          env-vars-to-encrypt: |
            [
              "API_KEY",
              "DATABASE_URL"
            ]
        env:
          # Define the secrets that env-vars-to-encrypt lists
          API_KEY: ${{ secrets.MY_API_KEY }}
          DATABASE_URL: ${{ secrets.DATABASE_URL }}

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
| `env-vars-to-encrypt`     | A JSON array of environment variable names to be encrypted and passed to the CVM.                         | `false`  | `[]`                       |

## Outputs

| Output    | Description                                                 |
| --------- | ----------------------------------------------------------- |
| `status`  | The final status of the deployment (`success` or `failed`). |
| `vm-id`   | The ID of the created or updated CVM.                       |
| `vm-name` | The name of the CVM.                                        |
| `operation` | The operation performed (`create` or `update_skipped`).   |

## Versioning and Maintenance

To ensure stable and predictable deployments, this action should be versioned using Git tags.

### Tagging a New Version

When you make changes to the action (e.g., updating the Python script or `action.yml`), follow these steps to release a new version:

1.  **Commit your changes:**
    ```bash
    git add .
    git commit -m "feat: Add new feature or fix bug"
    git push origin main
    ```

2.  **Create a Git tag:** It's best practice to use semantic versioning (e.g., `v1.0.1`, `v1.1.0`). You should also update the major version tag (like `v1`) so that users can easily receive non-breaking updates.
    ```bash
    # Create a specific patch/minor/major version tag
    git tag v1.1.0

    # Move the major version tag to point to this new release
    git tag -f v1
    ```

3.  **Push the tags to the repository:**
    ```bash
    git push origin v1.1.0
    git push origin v1 --force
    ```

### Updating the Action in a Workflow

To use the new version of the action in your service's repository (e.g., `vana-refinement-service`), simply update the version in the `uses` line of your workflow file:

```yaml
# In your service's .github/workflows/deploy.yml
...
    steps:
      - name: Deploy CVM to Phala
        # Update the version here to a specific tag or a major version
        uses: vana-com/phala-deployment-action@v1.1.0 # Or use @v1 to always get the latest v1.x.x
...
```

## Developing & Debugging Locally

You can debug the Github Actions locally by running act command.
The act can be installed from https://github.com/nektos/act.
The secerts you need to set are the same as the ones in the repository secrets to local `.env` file in the root of the repository.

Another possibility is to copy `deploy_to_phala.py` to the project repo and run it directly with Python, passing the necessary arguments.
This allows you to test the deployment logic without needing to set up a full GitHub Actions environment.

## Useful Links

- https://docs.phala.network/phala-cloud/be-production-ready/ci-cd-automation/setup-a-ci-cd-pipeline
- https://github.com/Phala-Network/cloud-tee-starter-template