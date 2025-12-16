def assert_ticket_valid(ticket: dict) -> None:
    required_fields = ["ticket_id", "correlation_id", "task", "status", "sla_deadline_ms"]
    missing = [field for field in required_fields if field not in ticket]
    assert not missing, f"Ticket missing fields: {missing}"


def assert_workflow_completed(workflow: dict) -> None:
    assert workflow is not None, "Workflow not found"
    assert workflow.get("status") == "COMPLETED", f"Workflow status is {workflow.get('status')}"


def assert_slo_met(latency_ms: float, slo_ms: float) -> None:
    assert latency_ms < slo_ms, f"Latency {latency_ms}ms exceeds SLO {slo_ms}ms"
