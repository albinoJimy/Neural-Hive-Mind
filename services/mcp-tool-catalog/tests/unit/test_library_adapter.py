"""
Testes unitarios para LIBRARYAdapter.

Cobertura:
- Import dinamico de bibliotecas Python
- Execucao de funcoes in-process
- Passagem de parametros
- Validacao de disponibilidade
- Tratamento de erros (ImportError, AttributeError, Exception)
- Suporte a funcoes assincronas
- Cache de imports
"""

import asyncio
from unittest.mock import patch

import pytest


class TestLIBRARYAdapterExecution:
    """Testes de execucao de funcoes de biblioteca."""

    @pytest.mark.asyncio()
    async def test_execute_sync_function_success(self):
        """Deve executar funcao sincrona com sucesso."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        result = await adapter.execute(
            tool_id="math-tool-001",
            tool_name="math",
            command="math:sqrt",
            parameters={"x": 16},
            context={},
        )

        assert result.success is True
        assert result.output == "4.0"
        assert result.execution_time_ms > 0

    @pytest.mark.asyncio()
    async def test_execute_with_multiple_parameters(self):
        """Deve executar funcao com multiplos parametros."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        result = await adapter.execute(
            tool_id="math-tool-002",
            tool_name="math",
            command="math:pow",
            parameters={"x": 2, "y": 3},
            context={},
        )

        assert result.success is True
        assert result.output == "8.0"

    @pytest.mark.asyncio()
    async def test_execute_with_no_parameters(self):
        """Deve executar funcao sem parametros."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        result = await adapter.execute(
            tool_id="time-tool-001",
            tool_name="time",
            command="time:time",
            parameters={},
            context={},
        )

        assert result.success is True
        assert len(result.output) > 0  # timestamp string

    @pytest.mark.asyncio()
    async def test_execute_function_not_found(self):
        """Deve retornar erro quando funcao nao existe."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        result = await adapter.execute(
            tool_id="math-tool-999",
            tool_name="math",
            command="math:nonexistent_function",
            parameters={},
            context={},
        )

        assert result.success is False
        assert "not found" in result.error.lower() or "attribute" in result.error.lower()

    @pytest.mark.asyncio()
    async def test_execute_module_not_found(self):
        """Deve retornar erro quando modulo nao existe."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        result = await adapter.execute(
            tool_id="fake-tool-001",
            tool_name="nonexistent_module_xyz",
            command="nonexistent_module_xyz:function",
            parameters={},
            context={},
        )

        assert result.success is False
        assert "not found" in result.error.lower() or "import" in result.error.lower()

    @pytest.mark.asyncio()
    async def test_execute_function_exception(self):
        """Deve capturar excecao lancada pela funcao."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        result = await adapter.execute(
            tool_id="math-tool-003",
            tool_name="math",
            command="math:sqrt",
            parameters={"x": -1},  # ValueError para sqrt de numero negativo
            context={},
        )

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio()
    async def test_execute_with_class_method(self):
        """Deve executar metodo de classe."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        # Usar json.dumps como exemplo de metodo de classe (dumps aceita keyword args)
        result = await adapter.execute(
            tool_id="json-tool-001",
            tool_name="json",
            command="json:dumps",
            parameters={"obj": {"key": "value"}},
            context={},
        )

        assert result.success is True
        assert "key" in result.output
        assert "value" in result.output


class TestLIBRARYAdapterAsyncExecution:
    """Testes de execucao de funcoes assincronas."""

    @pytest.mark.asyncio()
    async def test_execute_async_function(self):
        """Deve executar funcao assincrona."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        # Criar uma funcao assincrona de teste no runtime
        import asyncio

        async def async_test_function(value: str) -> str:
            await asyncio.sleep(0.01)
            return f"processed: {value}"

        # Mock do import para retornar nossa funcao
        with patch.object(adapter, "_import_function", return_value=async_test_function):
            result = await adapter.execute(
                tool_id="async-tool-001",
                tool_name="test_module",
                command="test_module:async_function",
                parameters={"value": "test"},
                context={},
            )

            assert result.success is True
            assert "processed: test" in result.output

    @pytest.mark.asyncio()
    async def test_execute_async_function_exception(self):
        """Deve capturar excecao de funcao assincrona."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        async def failing_async_function():
            await asyncio.sleep(0.01)
            raise ValueError("Async function failed")

        with patch.object(adapter, "_import_function", return_value=failing_async_function):
            result = await adapter.execute(
                tool_id="async-tool-002",
                tool_name="test_module",
                command="test_module:failing_function",
                parameters={},
                context={},
            )

            assert result.success is False
            assert "failed" in result.error.lower()


class TestLIBRARYAdapterImportCaching:
    """Testes de cache de imports."""

    @pytest.mark.asyncio()
    async def test_import_caching(self):
        """Deve fazer cache de imports para evitar reimportacao."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        # Primeira execucao - deve importar
        result1 = await adapter.execute(
            tool_id="math-tool-004",
            tool_name="math",
            command="math:sqrt",
            parameters={"x": 25},
            context={},
        )

        assert result1.success is True

        # Segunda execucao - deve usar cache
        initial_cache_size = len(adapter._import_cache)
        result2 = await adapter.execute(
            tool_id="math-tool-005",
            tool_name="math",
            command="math:ceil",
            parameters={"x": 3.7},
            context={},
        )

        assert result2.success is True
        # Cache deve ter pelo menos um modulo
        assert len(adapter._import_cache) >= initial_cache_size

    @pytest.mark.asyncio()
    async def test_clear_import_cache(self):
        """Deve limpar cache de imports."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        # Executar para popular cache
        await adapter.execute(
            tool_id="math-tool-006",
            tool_name="math",
            command="math:sqrt",
            parameters={"x": 36},
            context={},
        )

        assert len(adapter._import_cache) > 0

        # Limpar cache
        adapter.clear_import_cache()

        assert len(adapter._import_cache) == 0


class TestLIBRARYAdapterValidation:
    """Testes de validacao de disponibilidade."""

    @pytest.mark.asyncio()
    async def test_validate_available_builtin_module(self):
        """Deve validar modulo builtin disponivel."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        is_available = await adapter.validate_tool_availability("math")

        assert is_available is True

    @pytest.mark.asyncio()
    async def test_validate_available_standard_library(self):
        """Deve validar modulo da biblioteca padrao disponivel."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        is_available = await adapter.validate_tool_availability("json")

        assert is_available is True

    @pytest.mark.asyncio()
    async def test_validate_not_available_module(self):
        """Deve retornar False para modulo inexistente."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        is_available = await adapter.validate_tool_availability("nonexistent_module_xyz_123")

        assert is_available is False

    @pytest.mark.asyncio()
    async def test_validate_with_function(self):
        """Deve validar disponibilidade de funcao especifica."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        # Validar modulo:function
        is_available = await adapter.validate_tool_availability("math:sqrt")

        assert is_available is True

    @pytest.mark.asyncio()
    async def test_validate_function_not_exists(self):
        """Deve retornar False quando funcao nao existe."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        is_available = await adapter.validate_tool_availability("math:nonexistent_func")

        assert is_available is False


class TestLIBRARYAdapterCommandParsing:
    """Testes de parsing de comandos."""

    @pytest.mark.asyncio()
    async def test_parse_command_module_only(self):
        """Deve fazer parse de comando com apenas modulo."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        module_name, function_name = adapter._parse_command("math")

        assert module_name == "math"
        assert function_name is None

    @pytest.mark.asyncio()
    async def test_parse_command_module_function(self):
        """Deve fazer parse de comando modulo:funcao."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        module_name, function_name = adapter._parse_command("math:sqrt")

        assert module_name == "math"
        assert function_name == "sqrt"

    @pytest.mark.asyncio()
    async def test_parse_command_nested_module(self):
        """Deve fazer parse de comando com modulo aninhado."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        module_name, function_name = adapter._parse_command("os.path:join")

        assert module_name == "os.path"
        assert function_name == "join"

    @pytest.mark.asyncio()
    async def test_parse_command_with_submodule_function(self):
        """Deve fazer parse de comando com submodulo e funcao."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        module_name, function_name = adapter._parse_command("collections:Counter")

        assert module_name == "collections"
        assert function_name == "Counter"


class TestLIBRARYAdapterOutputHandling:
    """Testes de tratamento de output."""

    @pytest.mark.asyncio()
    async def test_output_string_conversion(self):
        """Deve converter output para string."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        result = await adapter.execute(
            tool_id="math-tool-007",
            tool_name="math",
            command="math:factorial",
            parameters={"x": 5},
            context={},
        )

        assert result.success is True
        assert result.output == "120"  # 5! = 120

    @pytest.mark.asyncio()
    async def test_output_dict_conversion(self):
        """Deve converter dicionario para JSON string."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        result = await adapter.execute(
            tool_id="json-tool-002",
            tool_name="json",
            command="json:loads",
            parameters={"s": '{"key": "value"}'},
            context={},
        )

        assert result.success is True
        assert "key" in result.output or "value" in result.output

    @pytest.mark.asyncio()
    async def test_output_list_conversion(self):
        """Deve converter lista para string."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        result = await adapter.execute(
            tool_id="json-tool-003",
            tool_name="json",
            command="json:loads",
            parameters={"s": "[1, 2, 3]"},
            context={},
        )

        assert result.success is True
        assert result.output is not None


class TestLIBRARYAdapterMetadata:
    """Testes de metadados."""

    @pytest.mark.asyncio()
    async def test_metadata_includes_module_info(self):
        """Deve incluir informacoes do modulo no metadata."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        result = await adapter.execute(
            tool_id="math-tool-008",
            tool_name="math",
            command="math:sqrt",
            parameters={"x": 49},
            context={},
        )

        assert result.metadata is not None
        assert "module" in result.metadata
        assert result.metadata["module"] == "math"
        assert "function" in result.metadata
        assert result.metadata["function"] == "sqrt"

    @pytest.mark.asyncio()
    async def test_metadata_includes_execution_time(self):
        """Deve incluir tempo de execucao no metadata."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        result = await adapter.execute(
            tool_id="math-tool-009",
            tool_name="math",
            command="math:sqrt",
            parameters={"x": 64},
            context={},
        )

        assert result.execution_time_ms > 0
        assert "execution_time_ms" in result.metadata


class TestLIBRARYAdapterEdgeCases:
    """Testes de casos extremos."""

    @pytest.mark.asyncio()
    async def test_execute_with_none_parameter(self):
        """Deve lidar com parametro None."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        # Funcao que aceita None
        result = await adapter.execute(
            tool_id="json-tool-004",
            tool_name="json",
            command="json:dumps",
            parameters={"obj": None},
            context={},
        )

        assert result.success is True
        assert "null" in result.output

    @pytest.mark.asyncio()
    async def test_execute_with_empty_parameters(self):
        """Deve lidar com dicionario de parametros vazio."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        # time.time() não requer parâmetros
        result = await adapter.execute(
            tool_id="time-tool-002",
            tool_name="time",
            command="time:time",
            parameters={},
            context={},
        )

        # time.time() deve funcionar sem parâmetros
        assert result.success is True

    @pytest.mark.asyncio()
    async def test_execute_with_large_output(self):
        """Deve lidar com output grande."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter()

        large_list = list(range(1000))

        result = await adapter.execute(
            tool_id="json-tool-005",
            tool_name="json",
            command="json:dumps",
            parameters={"obj": large_list},
            context={},
        )

        assert result.success is True
        assert len(result.output) > 1000


class TestLIBRARYAdapterSecurity:
    """Testes de seguranca."""

    @pytest.mark.asyncio()
    async def test_block_dangerous_imports(self):
        """Deve bloquear importacoes perigosas se configurado."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter(block_dangerous_modules=True)

        result = await adapter.execute(
            tool_id="dangerous-001",
            tool_name="subprocess",
            command="subprocess:run",
            parameters={"args": ["echo", "test"]},
            context={},
        )

        assert result.success is False
        assert "blocked" in result.error.lower() or "not allowed" in result.error.lower()

    @pytest.mark.asyncio()
    async def test_allow_all_modules_when_not_blocking(self):
        """Deve permitir todos os modulos quando bloqueio desativado."""
        from src.adapters.library_adapter import LIBRARYAdapter

        adapter = LIBRARYAdapter(block_dangerous_modules=False)

        # sys.version é um atributo string, não uma função
        # Vamos usar sys.getrecursionlimit() que é uma função
        result = await adapter.execute(
            tool_id="sys-tool-001",
            tool_name="sys",
            command="sys:getrecursionlimit",
            parameters={},
            context={},
        )

        assert result.success is True
        assert int(result.output) > 0
