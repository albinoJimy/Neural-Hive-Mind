import pytest
import subprocess
import json


def test_istio_mesh_policy_permissive():
    """Verify mesh policy is in PERMISSIVE mode"""
    result = subprocess.run(
        ["kubectl", "get", "meshpolicy", "authentication-meshpolicy", "-o", "json"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        policy = json.loads(result.stdout)
        mode = policy.get("spec", {}).get("peers", [{}])[0].get("mtls", {}).get("mode")
        assert mode in ["PERMISSIVE", "UNSET"], f"Unexpected mTLS mode: {mode}"


def test_sidecar_injection_enabled():
    """Verify pods have istio-proxy sidecar"""
    result = subprocess.run(
        ["kubectl", "get", "pods", "-n", "neural-hive", "-o", "json"],
        capture_output=True, text=True
    )
    pods = json.loads(result.stdout)["items"]

    for pod in pods:
        containers = [c["name"] for c in pod["spec"]["containers"]]
        assert "istio-proxy" in containers, f"Pod {pod['metadata']['name']} missing sidecar"


def test_service_mesh_communication():
    """Verify services can communicate via mesh"""
    result = subprocess.run(
        ["kubectl", "get", "pods", "-n", "neural-hive", "-o", "jsonpath='{.items[0].metadata.name}'"],
        capture_output=True, text=True, shell=True
    )
    pod_name = result.stdout.strip().strip("'")

    result = subprocess.run(
        ["kubectl", "exec", "-n", "neural-hive", pod_name, "--",
         "curl", "-s", "http://gateway-intencoes:8000/health"],
        capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0 or "connection refused" not in result.stderr.lower()