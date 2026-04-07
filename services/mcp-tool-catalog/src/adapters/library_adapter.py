"""
LIBRARYAdapter para execução de ferramentas via import dinâmico.

Permite execução in-process de funções Python de bibliotecas.
"""

import importlib
import inspect
import json
import time
from typing import Any, Dict, Optional

from .base_adapter import BaseToolAdapter, ExecutionResult


class LIBRARYAdapter(BaseToolAdapter):
    """
    Adapter para execução de ferramentas via import dinâmico de bibliotecas Python.

    Suporta:
    - Import dinâmico de módulos
    - Execução de funções síncronas e assíncronas
    - Cache de imports para performance
    - Validação de disponibilidade
    - Tratamento de erros
    - Controle de segurança (bloqueio de módulos perigosos)
    """

    # Módulos considerados perigosos que podem ser bloqueados
    DANGEROUS_MODULES = {
        "subprocess",
        "os.system",
        "os.popen",
        "eval",
        "exec",
        "__import__",
    }

    def __init__(
        self,
        block_dangerous_modules: bool = False,
        cache_imports: bool = True,
    ):
        """
        Inicializa o LIBRARYAdapter.

        Args:
            block_dangerous_modules: Se deve bloquear módulos perigosos
            cache_imports: Se deve fazer cache de imports
        """
        super().__init__()
        self.block_dangerous_modules = block_dangerous_modules
        self.cache_imports = cache_imports
        self._import_cache: Dict[str, Any] = {}

    async def execute(
        self,
        tool_id: str,
        tool_name: str,
        command: str,
        parameters: Dict[str, Any],
        context: Dict[str, Any],
    ) -> ExecutionResult:
        """
        Executa uma ferramenta via import dinâmico.

        Args:
            tool_id: ID único da ferramenta
            tool_name: Nome da ferramenta (usado como módulo)
            command: Comando no formato "module:function" ou "module.submodule:function"
            parameters: Parâmetros para passar à função
            context: Contexto adicional (não usado diretamente, mas pode ter metadados)

        Returns:
            ExecutionResult com resultado da execução
        """
        start_time = time.time()
        module_name, function_name = None, None

        try:
            # Parse do command para extrair module e function
            module_name, function_name = self._parse_command(command or tool_name)

            # Verificar bloqueio de módulos perigosos
            if self.block_dangerous_modules and self._is_dangerous(module_name, function_name):
                execution_time_ms = (time.time() - start_time) * 1000
                return ExecutionResult(
                    success=False,
                    output="",
                    error=f"Module '{module_name}' is blocked for security reasons",
                    execution_time_ms=execution_time_ms,
                    metadata={"module": module_name, "blocked": True},
                )

            # Importar função
            func = self._import_function(module_name, function_name)

            # Executar função
            result = await self._execute_function(func, parameters)

            execution_time_ms = (time.time() - start_time) * 1000

            # Converter resultado para string
            output = self._convert_output_to_string(result)

            return ExecutionResult(
                success=True,
                output=output,
                execution_time_ms=execution_time_ms,
                metadata={
                    "module": module_name,
                    "function": function_name,
                    "execution_time_ms": execution_time_ms,
                },
            )

        except ImportError as e:
            execution_time_ms = (time.time() - start_time) * 1000
            return ExecutionResult(
                success=False,
                output="",
                error=f"Module not found: {str(e)}",
                execution_time_ms=execution_time_ms,
                metadata={
                    "error_type": "ImportError",
                    "module": module_name,
                    "function": function_name,
                },
            )
        except AttributeError as e:
            execution_time_ms = (time.time() - start_time) * 1000
            return ExecutionResult(
                success=False,
                output="",
                error=f"Function not found: {str(e)}",
                execution_time_ms=execution_time_ms,
                metadata={
                    "error_type": "AttributeError",
                    "module": module_name,
                    "function": function_name,
                },
            )
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            self.logger.error(
                "library_function_execution_failed",
                tool_name=tool_name,
                command=command,
                error=str(e),
                error_type=type(e).__name__,
            )
            return ExecutionResult(
                success=False,
                output="",
                error=f"{type(e).__name__}: {str(e)}",
                execution_time_ms=execution_time_ms,
                metadata={
                    "error_type": type(e).__name__,
                    "module": module_name,
                    "function": function_name,
                },
            )

    async def validate_tool_availability(self, tool_name: str) -> bool:
        """
        Valida se a ferramenta (módulo/função) está disponível.

        Args:
            tool_name: Nome no formato "module" ou "module:function"

        Returns:
            True se disponível, False caso contrário
        """
        try:
            module_name, function_name = self._parse_command(tool_name)

            # Tentar importar módulo
            module = importlib.import_module(module_name)

            # Se não há função especificada, apenas o módulo basta
            if function_name is None:
                return True

            # Verificar se função/atributo existe
            return hasattr(module, function_name)

        except (ImportError, AttributeError):
            return False

    def _parse_command(self, command: str) -> tuple[str, Optional[str]]:
        """
        Faz parse do command para extrair nome do módulo e função.

        Args:
            command: Comando no formato "module" ou "module:function"

        Returns:
            Tupla (module_name, function_name)
        """
        if ":" in command:
            parts = command.rsplit(":", 1)
            return parts[0], parts[1]
        return command, None

    def _import_function(self, module_name: str, function_name: Optional[str] = None):
        """
        Importa função de módulo com cache.

        Args:
            module_name: Nome do módulo (suporta submódulos com ponto)
            function_name: Nome da função (opcional)

        Returns:
            Função ou módulo importado

        Raises:
            ImportError: Se módulo não existe
            AttributeError: Se função não existe no módulo
        """
        cache_key = f"{module_name}:{function_name or ''}"

        # Verificar cache
        if self.cache_imports and cache_key in self._import_cache:
            return self._import_cache[cache_key]

        # Importar módulo
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as e:
            raise ImportError(f"Module '{module_name}' not found") from e

        # Se não há função especificada, retornar módulo
        if function_name is None:
            if self.cache_imports:
                self._import_cache[cache_key] = module
            return module

        # Obter função do módulo
        if not hasattr(module, function_name):
            raise AttributeError(f"Function '{function_name}' not found in module '{module_name}'")

        func = getattr(module, function_name)

        if self.cache_imports:
            self._import_cache[cache_key] = func

        return func

    async def _execute_function(self, func, parameters: Dict[str, Any]) -> Any:
        """
        Executa função síncrona ou assíncrona com parâmetros.

        Args:
            func: Função a executar
            parameters: Dicionário de parâmetros

        Returns:
            Resultado da execução

        Raises:
            Exception: Se a função falhar
        """
        # Verificar se é função assíncrona
        is_async = inspect.iscoroutinefunction(func)

        # Tentar obter assinatura para ordenar parâmetros (não funciona para builtins)
        try:
            sig = inspect.signature(func)
            param_names = list(sig.parameters.keys())

            # Ordenar valores dos parâmetros conforme a assinatura
            ordered_args = [parameters[name] for name in param_names if name in parameters]

            if is_async:
                if ordered_args:
                    return await func(*ordered_args)
                elif parameters:
                    return await func(**parameters)
                else:
                    return await func()
            else:
                if ordered_args:
                    return func(*ordered_args)
                elif parameters:
                    return func(**parameters)
                else:
                    return func()
        except (ValueError, TypeError):
            # Builtin functions don't have signature, try direct call
            if is_async:
                if parameters:
                    return await func(**parameters)
                else:
                    return await func()
            else:
                if parameters:
                    return func(**parameters)
                else:
                    return func()

    def _convert_output_to_string(self, output: Any) -> str:
        """
        Converte output para string.

        Args:
            output: Output da função

        Returns:
            String representando o output
        """
        if output is None:
            return "null"
        if isinstance(output, str):
            return output
        if isinstance(output, (dict, list)):
            return json.dumps(output)
        if isinstance(output, bytes):
            return output.decode("utf-8", errors="replace")
        return str(output)

    def _is_dangerous(self, module_name: str, function_name: Optional[str]) -> bool:
        """
        Verifica se módulo/função é considerado perigoso.

        Args:
            module_name: Nome do módulo
            function_name: Nome da função

        Returns:
            True se for perigoso
        """
        full_path = f"{module_name}.{function_name}" if function_name else module_name

        for dangerous in self.DANGEROUS_MODULES:
            if dangerous in full_path:
                return True

        return False

    def clear_import_cache(self):
        """Limpa cache de imports."""
        self._import_cache.clear()
