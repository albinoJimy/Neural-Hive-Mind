# Testes para ethical-guardrails.rego
# Epic H - H003: Testes de OPA Policies

package ethicalguardrails

import future.keywords.contains
import future.keywords.if

test_ethical_guardrails_risk_score_exceeded {
  # CognitivePlan com risk_score > 0.9 deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "CognitivePlan"},
      "object": {
        "metadata": {"name": "test-plan"},
        "spec": {
          "risk_assessment": {"risk_score": 0.95}
        }
      }
    },
    "parameters": {
      "max_risk_score": 0.9
    }
  }
}

test_ethical_guardrails_risk_score_acceptable {
  # CognitivePlan com risk_score aceitável deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "CognitivePlan"},
      "object": {
        "metadata": {"name": "test-plan"},
        "spec": {
          "risk_assessment": {"risk_score": 0.7}
        }
      }
    },
    "parameters": {
      "max_risk_score": 0.9
    }
  }
}

test_ethical_guardrails_critical_decision_low_confidence {
  # Decisão crítica com baixa confiança deve violar
  violation with input as {
    "review": {
      "kind": {"kind": "CognitivePlan"},
      "object": {
        "metadata": {"name": "test-plan"},
        "spec": {
          "decision_type": "REPLANNING",
          "confidence_score": 0.5
        }
      }
    },
    "parameters": {
      "min_confidence_for_critical": 0.7
    }
  }
}

test_ethical_guardrails_critical_decision_ok_confidence {
  # Decisão crítica com confiança adequada deve passar
  not violation with input as {
    "review": {
      "kind": {"kind": "CognitivePlan"},
      "object": {
        "metadata": {"name": "test-plan"},
        "spec": {
          "decision_type": "EXCEPTION_APPROVAL",
          "confidence_score": 0.8
        }
      }
    },
    "parameters": {
      "min_confidence_for_critical": 0.7
    }
  }
}

test_ethical_guardrails_non_critical_decision {
  # Decisão não crítica não requer alta confiança
  not violation with input as {
    "review": {
      "kind": {"kind": "CognitivePlan"},
      "object": {
        "metadata": {"name": "test-plan"},
        "spec": {
          "decision_type": "ROUTINE_EXECUTION",
          "confidence_score": 0.5
        }
      }
    },
    "parameters": {
      "min_confidence_for_critical": 0.7
    }
  }
}
