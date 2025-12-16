import asyncio
from typing import List

from kubernetes.client import CoreV1Api


async def wait_for_pod_ready(k8s_client: CoreV1Api, namespace: str, label_selector: str, timeout: int = 300) -> List[str]:
    end_time = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end_time:
        pods = k8s_client.list_namespaced_pod(namespace=namespace, label_selector=label_selector).items
        ready = []
        for pod in pods:
            conditions = pod.status.conditions or []
            if any(c.type == "Ready" and c.status == "True" for c in conditions):
                ready.append(pod.metadata.name)
        if ready:
            return ready
        await asyncio.sleep(2)
    raise TimeoutError(f"Pods with selector {label_selector} not ready in namespace {namespace}")


def get_pod_logs(k8s_client: CoreV1Api, namespace: str, label_selector: str, tail_lines: int = 100) -> str:
    pods = k8s_client.list_namespaced_pod(namespace=namespace, label_selector=label_selector).items
    if not pods:
        return ""
    return k8s_client.read_namespaced_pod_log(name=pods[0].metadata.name, namespace=namespace, tail_lines=tail_lines)


def scale_deployment(k8s_client: CoreV1Api, namespace: str, deployment_name: str, replicas: int) -> None:
    body = {"spec": {"replicas": replicas}}
    k8s_client.patch_namespaced_deployment_scale(name=deployment_name, namespace=namespace, body=body)
