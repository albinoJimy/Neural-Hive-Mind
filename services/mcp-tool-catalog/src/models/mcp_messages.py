"""Modelos Pydantic para mensagens JSON-RPC 2.0 e protocolo MCP."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class JSONRPCRequest(BaseModel):
    """Modelo base para requisições JSON-RPC 2.0."""

    jsonrpc: str = Field(default="2.0", description="Versão do protocolo JSON-RPC")
    id: int = Field(..., description="Identificador único da requisição", ge=1)
    method: str = Field(..., description="Nome do método a ser invocado")
    params: Dict[str, Any] = Field(default_factory=dict, description="Parâmetros do método")

    @field_validator("jsonrpc")
    @classmethod
    def validate_jsonrpc_version(cls, v: str) -> str:
        """Valida que a versão é sempre 2.0."""
        if v != "2.0":
            raise ValueError("jsonrpc deve ser '2.0'")
        return v


class JSONRPCError(BaseModel):
    """Modelo para erros JSON-RPC 2.0."""

    code: int = Field(..., description="Código de erro")
    message: str = Field(..., description="Mensagem de erro")
    data: Optional[Any] = Field(default=None, description="Dados adicionais do erro")


class JSONRPCResponse(BaseModel):
    """Modelo base para respostas JSON-RPC 2.0."""

    jsonrpc: str = Field(default="2.0", description="Versão do protocolo JSON-RPC")
    id: int = Field(..., description="Identificador da requisição correspondente")
    result: Optional[Dict[str, Any]] = Field(default=None, description="Resultado da chamada")
    error: Optional[JSONRPCError] = Field(default=None, description="Erro da chamada")

    @field_validator("jsonrpc")
    @classmethod
    def validate_jsonrpc_version(cls, v: str) -> str:
        """Valida que a versão é sempre 2.0."""
        if v != "2.0":
            raise ValueError("jsonrpc deve ser '2.0'")
        return v


class MCPToolDescriptor(BaseModel):
    """Modelo para descrição de ferramentas MCP."""

    name: str = Field(..., description="Nome único da ferramenta")
    title: Optional[str] = Field(default=None, description="Título legível da ferramenta")
    description: str = Field(..., description="Descrição da funcionalidade")
    inputSchema: Dict[str, Any] = Field(..., description="Schema JSON para parâmetros de entrada")
    outputSchema: Optional[Dict[str, Any]] = Field(default=None, description="Schema JSON para saída")
    annotations: Optional[Dict[str, Any]] = Field(default=None, description="Metadados adicionais")


class MCPToolsListResponse(BaseModel):
    """Modelo para resposta de tools/list."""

    tools: List[MCPToolDescriptor] = Field(default_factory=list, description="Lista de ferramentas disponíveis")


class MCPToolCallRequest(BaseModel):
    """Modelo para requisição de tools/call."""

    name: str = Field(..., description="Nome da ferramenta a executar", min_length=1)
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Argumentos para a ferramenta")


class MCPContentItem(BaseModel):
    """Modelo para items de conteúdo na resposta de tools/call."""

    type: str = Field(..., description="Tipo do conteúdo (text, image, etc)")
    text: Optional[str] = Field(default=None, description="Conteúdo textual")
    data: Optional[Any] = Field(default=None, description="Dados adicionais")


class MCPToolCallResponse(BaseModel):
    """Modelo para resposta de tools/call."""

    content: List[MCPContentItem] = Field(default_factory=list, description="Lista de items de conteúdo")
    structuredContent: Optional[Dict[str, Any]] = Field(default=None, description="Conteúdo estruturado")
    isError: bool = Field(default=False, description="Indica se a execução resultou em erro")


class MCPResource(BaseModel):
    """Modelo para recursos MCP."""

    uri: str = Field(..., description="URI do recurso")
    name: Optional[str] = Field(default=None, description="Nome do recurso")
    description: Optional[str] = Field(default=None, description="Descrição do recurso")
    mimeType: Optional[str] = Field(default=None, description="Tipo MIME do recurso")


class MCPResourceContent(BaseModel):
    """Modelo para conteúdo de recurso MCP."""

    uri: str = Field(..., description="URI do recurso")
    mimeType: str = Field(..., description="Tipo MIME do conteúdo")
    text: Optional[str] = Field(default=None, description="Conteúdo textual")
    blob: Optional[str] = Field(default=None, description="Conteúdo binário em base64")


class MCPPromptArgument(BaseModel):
    """Modelo para argumento de prompt MCP."""

    name: str = Field(..., description="Nome do argumento")
    description: Optional[str] = Field(default=None, description="Descrição do argumento")
    required: bool = Field(default=False, description="Se o argumento é obrigatório")


class MCPPrompt(BaseModel):
    """Modelo para prompts MCP."""

    name: str = Field(..., description="Nome do prompt")
    description: Optional[str] = Field(default=None, description="Descrição do prompt")
    arguments: Optional[List[MCPPromptArgument]] = Field(default=None, description="Argumentos do prompt")
