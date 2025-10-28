"""
Especialista com suporte a multi-tenancy.

Este módulo implementa isolamento de dados, configurações customizadas
e modelos ML específicos por tenant.
"""

from typing import Dict, Any, Optional, List
import json
from pathlib import Path
from pydantic import BaseModel, Field, field_validator
import structlog

from .base_specialist import BaseSpecialist
from .config import SpecialistConfig

logger = structlog.get_logger()


class TenantConfig(BaseModel):
    """
    Configuração específica de um tenant.

    Atributos:
        tenant_id: Identificador único do tenant
        tenant_name: Nome descritivo do tenant
        is_active: Se o tenant está ativo (default: True)
        mlflow_model_name: Nome do modelo MLflow específico (None = usar padrão)
        mlflow_model_stage: Stage do modelo MLflow (None = usar padrão)
        min_confidence_score: Threshold customizado de confiança
        high_risk_threshold: Threshold customizado de risco alto
        enable_explainability: Feature flag para explicabilidade
        rate_limit_per_second: Rate limit específico (default: 100)
        metadata: Metadados adicionais do tenant
    """
    tenant_id: str = Field(..., description="Identificador único do tenant")
    tenant_name: str = Field(..., description="Nome descritivo do tenant")
    is_active: bool = Field(default=True, description="Tenant ativo")
    mlflow_model_name: Optional[str] = Field(
        default=None,
        description="Nome do modelo MLflow específico"
    )
    mlflow_model_stage: Optional[str] = Field(
        default=None,
        description="Stage do modelo MLflow"
    )
    min_confidence_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Threshold customizado de confiança mínima"
    )
    high_risk_threshold: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Threshold customizado de risco alto"
    )
    enable_explainability: Optional[bool] = Field(
        default=None,
        description="Feature flag para explicabilidade"
    )
    rate_limit_per_second: int = Field(
        default=100,
        ge=0,
        description="Rate limit específico em req/s"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadados adicionais"
    )

    @field_validator('tenant_id')
    def validate_tenant_id(cls, v):
        """Validar formato do tenant_id."""
        if not v or not v.strip():
            raise ValueError("tenant_id não pode ser vazio")
        return v.strip()


class MultiTenantSpecialist(BaseSpecialist):
    """
    Especialista base com suporte a multi-tenancy.

    Esta classe estende BaseSpecialist com:
    - Carregamento de configurações por tenant
    - Extração de tenant_id do contexto gRPC
    - Seleção de modelo e config por tenant
    - Propagação de tenant_id para ledger, cache e métricas
    - Validação de tenant ativo

    Exemplo de uso:
        class TechnicalMultiTenantSpecialist(MultiTenantSpecialist):
            def _get_specialist_type(self) -> str:
                return 'technical'

            def _evaluate_plan_internal(self, cognitive_plan, context):
                # Lógica de avaliação
                tenant_id = context.get('tenant_id', 'default')
                # tenant_id já foi validado e config aplicada
                return {...}
    """

    def __init__(self, config: SpecialistConfig):
        """
        Inicializa MultiTenantSpecialist.

        Args:
            config: Configuração do especialista

        Raises:
            ValueError: Se multi-tenancy habilitado mas tenant_configs_path ausente
            FileNotFoundError: Se arquivo de configs de tenant não existe
        """
        # Validar configuração de multi-tenancy
        if config.enable_multi_tenancy and not config.tenant_configs_path:
            raise ValueError(
                "enable_multi_tenancy=True requer tenant_configs_path configurado"
            )

        # Inicializar BaseSpecialist primeiro
        super().__init__(config)

        # Carregar configurações de tenants
        self.tenant_configs: Dict[str, TenantConfig] = {}
        self._tenant_models: Dict[str, Any] = {}  # Cache de modelos por tenant

        if config.enable_multi_tenancy:
            self._load_tenant_configs()
            logger.info(
                "Multi-tenancy habilitado",
                specialist_type=self.specialist_type,
                tenant_count=len(self.tenant_configs),
                active_tenants=len(self.get_active_tenants())
            )
        else:
            # Criar config padrão para tenant 'default'
            self.tenant_configs['default'] = TenantConfig(
                tenant_id='default',
                tenant_name='Default Tenant',
                is_active=True
            )
            logger.info("Multi-tenancy desabilitado - usando tenant padrão")

    def _load_tenant_configs(self):
        """
        Carrega configurações de tenants do arquivo JSON/YAML.

        Raises:
            FileNotFoundError: Se arquivo não existe
            ValueError: Se formato inválido ou validação falhar
        """
        config_path = Path(self.config.tenant_configs_path)

        if not config_path.exists():
            raise FileNotFoundError(
                f"Arquivo de tenant configs não encontrado: {config_path}"
            )

        logger.info("Carregando tenant configs", path=str(config_path))

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                if config_path.suffix in ['.yaml', '.yml']:
                    import yaml
                    raw_configs = yaml.safe_load(f)
                else:
                    raw_configs = json.load(f)

            # Validar cada tenant config com Pydantic
            for tenant_id, tenant_data in raw_configs.items():
                try:
                    # Garantir que tenant_id no dict corresponde à chave
                    if 'tenant_id' not in tenant_data:
                        tenant_data['tenant_id'] = tenant_id

                    tenant_config = TenantConfig(**tenant_data)
                    self.tenant_configs[tenant_id] = tenant_config

                    logger.debug(
                        "Tenant config carregado",
                        tenant_id=tenant_id,
                        tenant_name=tenant_config.tenant_name,
                        is_active=tenant_config.is_active,
                        has_custom_model=tenant_config.mlflow_model_name is not None
                    )
                except Exception as e:
                    logger.error(
                        "Falha ao validar tenant config",
                        tenant_id=tenant_id,
                        error=str(e)
                    )
                    # Continuar carregando outros tenants

            if not self.tenant_configs:
                raise ValueError("Nenhuma configuração de tenant válida encontrada")

            logger.info(
                "Tenant configs carregados com sucesso",
                total_tenants=len(self.tenant_configs),
                active_tenants=len(self.get_active_tenants())
            )

        except Exception as e:
            logger.error(
                "Erro ao carregar tenant configs",
                path=str(config_path),
                error=str(e)
            )
            raise

    def _load_model(self) -> Any:
        """
        Carrega modelo padrão (fallback para tenants sem modelo customizado).

        Returns:
            Modelo padrão carregado do MLflow
        """
        # Modelo padrão é carregado pelo BaseSpecialist
        if self.mlflow_client:
            try:
                model = self.mlflow_client.load_model_with_fallback(
                    model_name=self.config.mlflow_model_name,
                    model_stage=self.config.mlflow_model_stage
                )
                logger.info("Modelo padrão carregado", model_name=self.config.mlflow_model_name)
                return model
            except Exception as e:
                logger.warning(
                    "Falha ao carregar modelo padrão",
                    error=str(e)
                )
                return None
        return None

    def _load_tenant_model(self, tenant_id: str) -> Any:
        """
        Carrega modelo específico de um tenant.

        Args:
            tenant_id: ID do tenant

        Returns:
            Modelo do tenant (customizado ou padrão)

        Raises:
            ValueError: Se tenant desconhecido ou inativo
        """
        # Validar tenant
        if tenant_id not in self.tenant_configs:
            raise ValueError(f"Tenant desconhecido: {tenant_id}")

        tenant_config = self.tenant_configs[tenant_id]

        if not tenant_config.is_active:
            raise ValueError(f"Tenant inativo: {tenant_id}")

        # Verificar se modelo já está em cache
        if tenant_id in self._tenant_models:
            return self._tenant_models[tenant_id]

        # Carregar modelo customizado ou usar padrão
        if tenant_config.mlflow_model_name:
            if self.mlflow_client:
                try:
                    # Adicionar span OpenTelemetry
                    if self.tracer:
                        with self.tracer.start_as_current_span("specialist.load_tenant_model") as span:
                            span.set_attribute("tenant.id", tenant_id)
                            span.set_attribute("model.name", tenant_config.mlflow_model_name)

                            model = self.mlflow_client.load_model_with_fallback(
                                model_name=tenant_config.mlflow_model_name,
                                model_stage=tenant_config.mlflow_model_stage
                            )
                    else:
                        model = self.mlflow_client.load_model_with_fallback(
                            model_name=tenant_config.mlflow_model_name,
                            model_stage=tenant_config.mlflow_model_stage
                        )

                    # Cachear modelo
                    self._tenant_models[tenant_id] = model

                    logger.info(
                        "Modelo customizado carregado para tenant",
                        tenant_id=tenant_id,
                        model_name=tenant_config.mlflow_model_name,
                        model_stage=tenant_config.mlflow_model_stage or 'Production'
                    )

                    return model

                except Exception as e:
                    logger.warning(
                        "Falha ao carregar modelo customizado - usando modelo padrão",
                        tenant_id=tenant_id,
                        model_name=tenant_config.mlflow_model_name,
                        error=str(e)
                    )
                    # Fallback para modelo padrão
                    self._tenant_models[tenant_id] = self.model
                    return self.model
            else:
                logger.warning(
                    "MLflow client indisponível - usando modelo padrão",
                    tenant_id=tenant_id
                )
                self._tenant_models[tenant_id] = self.model
                return self.model
        else:
            # Tenant não tem modelo customizado - usar padrão
            logger.debug(
                "Tenant usando modelo padrão",
                tenant_id=tenant_id
            )
            self._tenant_models[tenant_id] = self.model
            return self.model

    def evaluate_plan(self, request, context=None) -> Dict[str, Any]:
        """
        Avalia plano cognitivo com suporte a multi-tenancy.

        Sobrescreve BaseSpecialist.evaluate_plan() para:
        - Extrair tenant_id do contexto gRPC ou request
        - Validar tenant existe e está ativo
        - Carregar config e modelo do tenant
        - Aplicar thresholds customizados
        - Propagar tenant_id para ledger/cache/métricas

        Args:
            request: Request gRPC com plano cognitivo
            context: Contexto gRPC com metadata

        Returns:
            Resultado da avaliação

        Raises:
            ValueError: Se tenant desconhecido ou inativo
        """
        # Extrair tenant_id do contexto
        tenant_id = self._extract_tenant_id(request, context)

        # Validar tenant
        self._validate_tenant(tenant_id)

        # Carregar tenant config
        tenant_config = self.tenant_configs[tenant_id]

        # Carregar modelo do tenant
        tenant_model = self._load_tenant_model(tenant_id)

        # Aplicar overrides de configuração do tenant
        original_config = self._apply_tenant_config_overrides(tenant_config)

        # Adicionar tenant_id ao request.context ao invés de passar como parâmetro
        if not hasattr(request, 'context'):
            # Se request não tem context, criar um
            request.context = {}

        # Injetar tenant_id no request.context
        if isinstance(request.context, dict):
            request.context['tenant_id'] = tenant_id
        else:
            # Se é protobuf map, converter para dict e adicionar
            context_dict = dict(request.context)
            context_dict['tenant_id'] = tenant_id
            request.context.clear()
            request.context.update(context_dict)

        # Temporariamente substituir modelo
        original_model = self.model
        self.model = tenant_model

        try:
            # Adicionar span OpenTelemetry
            if self.tracer:
                with self.tracer.start_as_current_span("specialist.multi_tenant.evaluate") as span:
                    span.set_attribute("tenant.id", tenant_id)
                    span.set_attribute("tenant.name", tenant_config.tenant_name)
                    span.set_attribute("specialist.type", self.specialist_type)

                    # Chamar avaliação da classe base SEM passar context
                    result = super().evaluate_plan(request)
            else:
                result = super().evaluate_plan(request)

            # Adicionar tenant_id aos metadados da resposta
            if 'metadata' not in result:
                result['metadata'] = {}
            result['metadata']['tenant_id'] = tenant_id

            # Incrementar métricas com label tenant_id
            if hasattr(self.metrics, 'increment_tenant_evaluation'):
                self.metrics.increment_tenant_evaluation(tenant_id)

            logger.debug(
                "Avaliação multi-tenant concluída",
                tenant_id=tenant_id,
                opinion_id=result.get('opinion_id')
            )

            return result

        finally:
            # Restaurar configuração e modelo original
            self.model = original_model
            self._restore_config_overrides(original_config)

    def _extract_tenant_id(self, request, context) -> str:
        """
        Extrai tenant_id do gRPC metadata ou context map.

        Ordem de precedência:
        1. gRPC metadata header 'x-tenant-id'
        2. request.context map campo 'tenant_id'
        3. config.default_tenant_id

        Args:
            request: Request gRPC
            context: Contexto gRPC

        Returns:
            tenant_id extraído
        """
        tenant_id = None

        # Tentar extrair de gRPC metadata (injetado pelo Envoy)
        if context is not None and hasattr(context, 'invocation_metadata'):
            try:
                metadata = dict(context.invocation_metadata())
                tenant_id = metadata.get('x-tenant-id')
                if tenant_id:
                    logger.debug("tenant_id extraído de gRPC metadata", tenant_id=tenant_id)
            except Exception as e:
                logger.debug("Erro ao extrair metadata gRPC", error=str(e))

        # Fallback: tentar extrair de request.context
        if not tenant_id and hasattr(request, 'context'):
            try:
                if isinstance(request.context, dict):
                    tenant_id = request.context.get('tenant_id')
                else:
                    # Protobuf map
                    tenant_id = request.context.get('tenant_id', None)

                if tenant_id:
                    logger.debug("tenant_id extraído de request.context", tenant_id=tenant_id)
            except Exception as e:
                logger.debug("Erro ao extrair context de request", error=str(e))

        # Fallback: usar tenant padrão
        if not tenant_id:
            tenant_id = self.config.default_tenant_id
            logger.debug(
                "tenant_id não fornecido - usando padrão",
                default_tenant_id=tenant_id
            )

        return tenant_id

    def _validate_tenant(self, tenant_id: str):
        """
        Valida que tenant existe e está ativo.

        Args:
            tenant_id: ID do tenant

        Raises:
            ValueError: Se tenant desconhecido ou inativo
        """
        if tenant_id not in self.tenant_configs:
            logger.error("Tenant desconhecido", tenant_id=tenant_id)
            raise ValueError(f"Tenant desconhecido: {tenant_id}")

        tenant_config = self.tenant_configs[tenant_id]

        if not tenant_config.is_active:
            logger.error("Tenant inativo", tenant_id=tenant_id)
            raise ValueError(f"Tenant inativo: {tenant_id}")

    def _apply_tenant_config_overrides(self, tenant_config: TenantConfig) -> Dict[str, Any]:
        """
        Aplica overrides de configuração do tenant.

        Args:
            tenant_config: Configuração do tenant

        Returns:
            Dict com valores originais (para restauração)
        """
        original_values = {}

        # Aplicar threshold overrides
        if tenant_config.min_confidence_score is not None:
            original_values['min_confidence_score'] = self.config.min_confidence_score
            self.config.min_confidence_score = tenant_config.min_confidence_score

        if tenant_config.high_risk_threshold is not None:
            original_values['high_risk_threshold'] = self.config.high_risk_threshold
            self.config.high_risk_threshold = tenant_config.high_risk_threshold

        # Aplicar feature flag overrides
        if tenant_config.enable_explainability is not None:
            original_values['enable_explainability'] = self.config.enable_explainability
            self.config.enable_explainability = tenant_config.enable_explainability

        return original_values

    def _restore_config_overrides(self, original_values: Dict[str, Any]):
        """
        Restaura valores originais de configuração.

        Args:
            original_values: Dict com valores originais
        """
        for key, value in original_values.items():
            setattr(self.config, key, value)

    def _get_tenant_config(self, tenant_id: str) -> TenantConfig:
        """
        Obtém configuração de um tenant.

        Args:
            tenant_id: ID do tenant

        Returns:
            TenantConfig do tenant

        Raises:
            ValueError: Se tenant não existe
        """
        if tenant_id not in self.tenant_configs:
            raise ValueError(f"Tenant não encontrado: {tenant_id}")

        return self.tenant_configs[tenant_id]

    def get_active_tenants(self) -> List[str]:
        """
        Lista tenants ativos.

        Returns:
            Lista de tenant_ids ativos
        """
        return [
            tenant_id
            for tenant_id, config in self.tenant_configs.items()
            if config.is_active
        ]
