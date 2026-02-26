"""
Register the python-runner flow with the Prefect kubernetes-pool work pool.
Run this once after the Prefect server and work pool are up.

Usage:
    PREFECT_API_URL=http://localhost:4200/api python deploy_flow.py
"""

from prefect.deployments import Deployment
from prefect_kubernetes.job import KubernetesJob

from python_runner_flow import run_python_code


def main():
    k8s_job = KubernetesJob(
        image="localhost/atlas-prefect-runner:latest",
        namespace="atlas",
        finished_job_ttl=300,
        job_watch_timeout_seconds=600,
        pod_watch_timeout_seconds=600,
        customizations=[
            {
                "op": "add",
                "path": "/spec/template/spec/automountServiceAccountToken",
                "value": False,
            },
            {
                "op": "add",
                "path": "/spec/template/spec/containers/0/securityContext",
                "value": {
                    "runAsUser": 1000,
                    "runAsGroup": 1000,
                    "allowPrivilegeEscalation": False,
                    "readOnlyRootFilesystem": True,
                    "capabilities": {"drop": ["ALL"]},
                },
            },
            {
                "op": "add",
                "path": "/spec/template/spec/containers/0/resources",
                "value": {
                    "requests": {"memory": "128Mi", "cpu": "250m"},
                    "limits": {"memory": "256Mi", "cpu": "500m"},
                },
            },
            {
                "op": "add",
                "path": "/spec/template/spec/containers/0/env",
                "value": [
                    {
                        "name": "PREFECT_API_URL",
                        "value": "http://prefect-server.atlas:4200/api",
                    }
                ],
            },
        ],
    )

    deployment = Deployment.build_from_flow(
        flow=run_python_code,
        name="python-runner-k8s",
        work_pool_name="kubernetes-pool",
        infrastructure=k8s_job,
    )

    deployment_id = deployment.apply()
    print(f"Deployment created: python-runner-k8s (id={deployment_id})")
    print("The flow is now available for execution via the Prefect API.")


if __name__ == "__main__":
    main()
