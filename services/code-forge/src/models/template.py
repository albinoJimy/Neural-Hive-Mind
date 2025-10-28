from enum import Enum
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field


class TemplateType(str, Enum):
    """Tipos de templates"""
    MICROSERVICE = 'MICROSERVICE'
    FUNCTION = 'FUNCTION'
    IAC_TERRAFORM = 'IAC_TERRAFORM'
    IAC_HELM = 'IAC_HELM'
    TEST_SUITE = 'TEST_SUITE'
    POLICY_OPA = 'POLICY_OPA'


class TemplateLanguage(str, Enum):
    """Linguagens suportadas"""
    PYTHON = 'PYTHON'
    JAVASCRIPT = 'JAVASCRIPT'
    TYPESCRIPT = 'TYPESCRIPT'
    GO = 'GO'
    JAVA = 'JAVA'
    RUST = 'RUST'
    HCL = 'HCL'
    YAML = 'YAML'


class TemplateMetadata(BaseModel):
    """Metadados de um template"""

    name: str = Field(..., description='Nome do template')
    version: str = Field(..., description='Versão do template')
    description: str = Field(..., description='Descrição do template')
    author: str = Field(..., description='Autor do template')
    tags: List[str] = Field(default_factory=list, description='Tags para classificação')
    language: TemplateLanguage = Field(..., description='Linguagem principal')
    type: TemplateType = Field(..., description='Tipo de template')

    class Config:
        use_enum_values = True


class TemplateParameter(BaseModel):
    """Parâmetro de um template"""

    name: str = Field(..., description='Nome do parâmetro')
    type: str = Field(..., description='Tipo do parâmetro (string, int, bool, etc.)')
    required: bool = Field(..., description='Se o parâmetro é obrigatório')
    default: Optional[Any] = Field(None, description='Valor padrão')
    description: str = Field(..., description='Descrição do parâmetro')


class Template(BaseModel):
    """Representa um template de código"""

    template_id: str = Field(..., description='Identificador único do template')
    metadata: TemplateMetadata = Field(..., description='Metadados do template')
    parameters: List[TemplateParameter] = Field(default_factory=list, description='Parâmetros do template')
    content_path: str = Field(..., description='Caminho para o conteúdo do template')
    examples: Dict[str, Any] = Field(default_factory=dict, description='Exemplos de uso')

    def validate_parameters(self, provided_params: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Valida se os parâmetros fornecidos são válidos"""
        errors = []

        # Verifica parâmetros obrigatórios
        required_params = {p.name for p in self.parameters if p.required}
        provided_keys = set(provided_params.keys())
        missing = required_params - provided_keys

        if missing:
            errors.append(f'Parâmetros obrigatórios faltando: {", ".join(missing)}')

        # Verifica tipos (validação básica)
        for param in self.parameters:
            if param.name in provided_params:
                value = provided_params[param.name]
                # Validação de tipo básica
                if param.type == 'int' and not isinstance(value, int):
                    errors.append(f'Parâmetro {param.name} deve ser int')
                elif param.type == 'bool' and not isinstance(value, bool):
                    errors.append(f'Parâmetro {param.name} deve ser bool')
                elif param.type == 'string' and not isinstance(value, str):
                    errors.append(f'Parâmetro {param.name} deve ser string')

        return len(errors) == 0, errors

    def calculate_match_score(self, criteria: Dict[str, Any]) -> float:
        """Calcula score de match baseado em critérios"""
        score = 0.0
        max_score = 0.0

        # Match por tipo
        max_score += 1.0
        if criteria.get('type') == self.metadata.type:
            score += 1.0

        # Match por linguagem
        max_score += 1.0
        if criteria.get('language') == self.metadata.language:
            score += 1.0

        # Match por tags
        max_score += 0.5
        if criteria.get('tags'):
            criteria_tags = set(criteria['tags'])
            template_tags = set(self.metadata.tags)
            if criteria_tags & template_tags:
                score += 0.5

        return score / max_score if max_score > 0 else 0.0


class TemplateRegistry(BaseModel):
    """Registro de templates disponíveis"""

    templates: Dict[str, Template] = Field(default_factory=dict, description='Templates indexados por ID')

    def add_template(self, template: Template):
        """Adiciona um template ao registro"""
        self.templates[template.template_id] = template

    def get_template(self, template_id: str) -> Optional[Template]:
        """Busca um template por ID"""
        return self.templates.get(template_id)

    def search(self, criteria: Dict[str, Any]) -> List[tuple[Template, float]]:
        """Busca templates que matcham critérios e retorna com scores"""
        results = []
        for template in self.templates.values():
            score = template.calculate_match_score(criteria)
            if score > 0:
                results.append((template, score))

        # Ordena por score decrescente
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def index_by_type(self, template_type: TemplateType) -> List[Template]:
        """Indexa templates por tipo"""
        return [t for t in self.templates.values() if t.metadata.type == template_type]
