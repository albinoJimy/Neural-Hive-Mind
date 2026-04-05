"""
Exceções customizadas para o Consensus Engine.

Define exceções específicas para falhas de validação e erros de consenso,
permitindo tratamento granular e propagação de contexto de erro.
"""


class ConsensusValidationError(ValueError):
    """Exceção para falhas de validação no consenso.

    Lançada quando um plano cognitivo ou opinião de especialista
    não atende aos requisitos de validação estrita.

    Atributos:
        field_name: Nome do campo que falhou na validação
        expected_value: Descrição do valor esperado
        actual_value: Valor recebido (convertido para string)
    """

    def __init__(self, field_name: str, expected_value: str, actual_value: str):
        self.field_name = field_name
        self.expected_value = expected_value
        self.actual_value = actual_value
        super().__init__(
            f"Validação falhou para campo '{field_name}': "
            f"esperado '{expected_value}', recebido '{actual_value}'"
        )

    def to_dict(self) -> dict:
        """Converte a exceção para dicionário para serialização."""
        return {
            "error_type": "ConsensusValidationError",
            "field_name": self.field_name,
            "expected": self.expected_value,
            "actual": self.actual_value,
        }


class MissingCorrelationIdError(ConsensusValidationError):
    """Exceção específica para correlation_id ausente (GAPS-02).

    Lançada quando fail_on_missing_correlation_id=True e o
    correlation_id está ausente, vazio ou contém apenas espaços.
    """

    def __init__(self, actual_value: str):
        super().__init__(
            field_name="correlation_id",
            expected_value="non_empty_string",
            actual_value=actual_value,
        )
