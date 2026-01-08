"""
Testes unitarios para o modulo grpc_channel_factory.

Cobertura:
- Criacao de canal seguro com X.509-SVID valido
- Fallback para inseguro apenas em ambiente de desenvolvimento
- Falha quando SPIFFE falha em producao/staging
- Reuso de SPIFFEManager existente
- Propagacao de erros de fetch JWT em prod/staging
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import grpc

from neural_hive_security import SPIFFEConfig
from neural_hive_security.grpc_channel_factory import (
    create_secure_grpc_channel,
    get_grpc_metadata_with_jwt,
)


class TestCreateSecureGrpcChannel:
    """Testes para create_secure_grpc_channel."""

    @pytest.fixture
    def spiffe_config_dev(self):
        """Configuracao SPIFFE para ambiente de desenvolvimento."""
        return SPIFFEConfig(
            workload_api_socket='unix:///run/spire/sockets/agent.sock',
            trust_domain='neural-hive.local',
            jwt_audience='neural-hive.local',
            jwt_ttl_seconds=3600,
            enable_x509=True,
            environment='development'
        )

    @pytest.fixture
    def spiffe_config_prod(self):
        """Configuracao SPIFFE para ambiente de producao."""
        return SPIFFEConfig(
            workload_api_socket='unix:///run/spire/sockets/agent.sock',
            trust_domain='neural-hive.local',
            jwt_audience='neural-hive.local',
            jwt_ttl_seconds=3600,
            enable_x509=True,
            environment='production'
        )

    @pytest.fixture
    def spiffe_config_staging(self):
        """Configuracao SPIFFE para ambiente de staging."""
        return SPIFFEConfig(
            workload_api_socket='unix:///run/spire/sockets/agent.sock',
            trust_domain='neural-hive.local',
            jwt_audience='neural-hive.local',
            jwt_ttl_seconds=3600,
            enable_x509=True,
            environment='staging'
        )

    @pytest.fixture
    def mock_spiffe_manager(self):
        """Mock do SPIFFEManager."""
        manager = MagicMock()
        manager.fetch_x509_svid = AsyncMock()
        # Mock do X509-SVID com certificados
        mock_svid = MagicMock()
        mock_svid.leaf = MagicMock()
        mock_svid.leaf.public_bytes.return_value = b'mock_cert'
        mock_svid.private_key = MagicMock()
        mock_svid.private_key.private_bytes.return_value = b'mock_key'
        mock_svid.cert_chain = []
        manager.fetch_x509_svid.return_value = mock_svid

        # Mock do trust bundle
        mock_bundle = MagicMock()
        mock_bundle.authorities = [MagicMock()]
        mock_bundle.authorities[0].public_bytes.return_value = b'mock_ca'
        manager.fetch_x509_bundle = AsyncMock(return_value=mock_bundle)

        return manager

    @pytest.mark.asyncio
    async def test_create_secure_channel_with_valid_x509_svid(
        self, spiffe_config_prod, mock_spiffe_manager
    ):
        """Teste: criacao de canal seguro com X.509-SVID valido."""
        with patch('neural_hive_security.grpc_channel_factory.grpc.aio.secure_channel') as mock_secure_channel:
            mock_channel = MagicMock()
            mock_secure_channel.return_value = mock_channel

            channel = await create_secure_grpc_channel(
                target='service-registry:50051',
                spiffe_config=spiffe_config_prod,
                spiffe_manager=mock_spiffe_manager,
                fallback_insecure=False
            )

            # Verifica que fetch_x509_svid foi chamado
            mock_spiffe_manager.fetch_x509_svid.assert_called_once()
            # Verifica que canal seguro foi criado
            mock_secure_channel.assert_called_once()
            assert channel == mock_channel

    @pytest.mark.asyncio
    async def test_fallback_insecure_only_in_dev_environment(
        self, spiffe_config_dev
    ):
        """Teste: fallback para inseguro apenas em ambiente de desenvolvimento."""
        # Config com X.509 desabilitado para forcar fallback
        spiffe_config_dev.enable_x509 = False

        with patch('neural_hive_security.grpc_channel_factory.grpc.aio.insecure_channel') as mock_insecure:
            mock_channel = MagicMock()
            mock_insecure.return_value = mock_channel

            channel = await create_secure_grpc_channel(
                target='service-registry:50051',
                spiffe_config=spiffe_config_dev,
                spiffe_manager=None,
                fallback_insecure=True
            )

            # Verifica que canal inseguro foi criado em dev
            mock_insecure.assert_called_once()
            assert channel == mock_channel

    @pytest.mark.asyncio
    async def test_fallback_allowed_with_dev_variant(self):
        """Teste: fallback permitido com variante 'dev' de environment."""
        spiffe_config = SPIFFEConfig(
            workload_api_socket='unix:///run/spire/sockets/agent.sock',
            trust_domain='neural-hive.local',
            jwt_audience='neural-hive.local',
            jwt_ttl_seconds=3600,
            enable_x509=False,  # Desabilitado para forcar fallback
            environment='dev'  # Variante 'dev'
        )

        with patch('neural_hive_security.grpc_channel_factory.grpc.aio.insecure_channel') as mock_insecure:
            mock_channel = MagicMock()
            mock_insecure.return_value = mock_channel

            channel = await create_secure_grpc_channel(
                target='service-registry:50051',
                spiffe_config=spiffe_config,
                spiffe_manager=None,
                fallback_insecure=True
            )

            mock_insecure.assert_called_once()
            assert channel == mock_channel

    @pytest.mark.asyncio
    async def test_fail_when_spiffe_fails_in_production(
        self, spiffe_config_prod, mock_spiffe_manager
    ):
        """Teste: falha quando SPIFFE falha em producao."""
        # Simular falha no fetch de X.509-SVID
        mock_spiffe_manager.fetch_x509_svid.side_effect = Exception('SPIFFE unavailable')

        with pytest.raises(RuntimeError) as exc_info:
            await create_secure_grpc_channel(
                target='service-registry:50051',
                spiffe_config=spiffe_config_prod,
                spiffe_manager=mock_spiffe_manager,
                fallback_insecure=False
            )

        assert 'mTLS' in str(exc_info.value) or 'SPIFFE' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fail_when_spiffe_fails_in_staging(
        self, spiffe_config_staging, mock_spiffe_manager
    ):
        """Teste: falha quando SPIFFE falha em staging."""
        mock_spiffe_manager.fetch_x509_svid.side_effect = Exception('SPIFFE unavailable')

        with pytest.raises(RuntimeError) as exc_info:
            await create_secure_grpc_channel(
                target='service-registry:50051',
                spiffe_config=spiffe_config_staging,
                spiffe_manager=mock_spiffe_manager,
                fallback_insecure=False
            )

        assert 'mTLS' in str(exc_info.value) or 'SPIFFE' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_no_fallback_in_production_even_if_allowed(
        self, spiffe_config_prod
    ):
        """Teste: fallback inseguro NAO permitido em producao mesmo com flag True."""
        spiffe_config_prod.enable_x509 = False  # Forcar fallback

        with pytest.raises(RuntimeError) as exc_info:
            await create_secure_grpc_channel(
                target='service-registry:50051',
                spiffe_config=spiffe_config_prod,
                spiffe_manager=None,
                fallback_insecure=True  # Mesmo com True, deve falhar em prod
            )

        assert 'mTLS is required' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reuse_existing_spiffe_manager(
        self, spiffe_config_prod, mock_spiffe_manager
    ):
        """Teste: reuso de SPIFFEManager existente."""
        with patch('neural_hive_security.grpc_channel_factory.grpc.aio.secure_channel') as mock_secure_channel:
            mock_channel = MagicMock()
            mock_secure_channel.return_value = mock_channel

            # Passar manager existente
            channel = await create_secure_grpc_channel(
                target='service-registry:50051',
                spiffe_config=spiffe_config_prod,
                spiffe_manager=mock_spiffe_manager,
                fallback_insecure=False
            )

            # Manager passado deve ser usado diretamente
            mock_spiffe_manager.fetch_x509_svid.assert_called_once()
            assert channel == mock_channel


class TestGetGrpcMetadataWithJwt:
    """Testes para get_grpc_metadata_with_jwt."""

    @pytest.fixture
    def mock_spiffe_manager(self):
        """Mock do SPIFFEManager para JWT."""
        manager = MagicMock()
        mock_jwt = MagicMock()
        mock_jwt.token = 'mock_jwt_token'
        manager.fetch_jwt_svid = AsyncMock(return_value=mock_jwt)
        return manager

    @pytest.mark.asyncio
    async def test_jwt_metadata_fetch_success(self, mock_spiffe_manager):
        """Teste: fetch de JWT-SVID com sucesso."""
        metadata = await get_grpc_metadata_with_jwt(
            spiffe_manager=mock_spiffe_manager,
            audience='service-registry.neural-hive.local',
            environment='production'
        )

        mock_spiffe_manager.fetch_jwt_svid.assert_called_once()
        # Verifica que metadata contem o header de autorizacao
        assert any('authorization' in key.lower() for key, value in metadata)

    @pytest.mark.asyncio
    async def test_jwt_fetch_error_propagates_in_production(self, mock_spiffe_manager):
        """Teste: erro de fetch JWT propaga em producao."""
        mock_spiffe_manager.fetch_jwt_svid.side_effect = Exception('JWT fetch failed')

        with pytest.raises(Exception) as exc_info:
            await get_grpc_metadata_with_jwt(
                spiffe_manager=mock_spiffe_manager,
                audience='service-registry.neural-hive.local',
                environment='production'
            )

        assert 'JWT fetch failed' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_jwt_fetch_error_propagates_in_staging(self, mock_spiffe_manager):
        """Teste: erro de fetch JWT propaga em staging."""
        mock_spiffe_manager.fetch_jwt_svid.side_effect = Exception('JWT fetch failed')

        with pytest.raises(Exception) as exc_info:
            await get_grpc_metadata_with_jwt(
                spiffe_manager=mock_spiffe_manager,
                audience='service-registry.neural-hive.local',
                environment='staging'
            )

        assert 'JWT fetch failed' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_jwt_fetch_error_returns_empty_in_dev(self, mock_spiffe_manager):
        """Teste: erro de fetch JWT retorna metadata vazio em dev."""
        mock_spiffe_manager.fetch_jwt_svid.side_effect = Exception('JWT fetch failed')

        # Em desenvolvimento, erro nao propaga - retorna metadata vazio
        metadata = await get_grpc_metadata_with_jwt(
            spiffe_manager=mock_spiffe_manager,
            audience='service-registry.neural-hive.local',
            environment='development'
        )

        assert metadata == []

    @pytest.mark.asyncio
    async def test_jwt_fetch_error_returns_empty_with_dev_variant(self, mock_spiffe_manager):
        """Teste: erro de fetch JWT retorna metadata vazio com variante 'dev'."""
        mock_spiffe_manager.fetch_jwt_svid.side_effect = Exception('JWT fetch failed')

        metadata = await get_grpc_metadata_with_jwt(
            spiffe_manager=mock_spiffe_manager,
            audience='service-registry.neural-hive.local',
            environment='dev'  # Variante 'dev'
        )

        assert metadata == []


class TestEnvironmentNormalization:
    """Testes para normalizacao de ambiente (dev/development)."""

    @pytest.mark.asyncio
    async def test_dev_lowercase_allows_fallback(self):
        """Teste: 'dev' minusculo permite fallback."""
        spiffe_config = SPIFFEConfig(
            workload_api_socket='unix:///run/spire/sockets/agent.sock',
            trust_domain='neural-hive.local',
            jwt_audience='neural-hive.local',
            jwt_ttl_seconds=3600,
            enable_x509=False,
            environment='dev'
        )

        with patch('neural_hive_security.grpc_channel_factory.grpc.aio.insecure_channel') as mock_insecure:
            mock_insecure.return_value = MagicMock()
            channel = await create_secure_grpc_channel(
                target='test:50051',
                spiffe_config=spiffe_config,
                spiffe_manager=None,
                fallback_insecure=True
            )
            mock_insecure.assert_called_once()

    @pytest.mark.asyncio
    async def test_development_lowercase_allows_fallback(self):
        """Teste: 'development' minusculo permite fallback."""
        spiffe_config = SPIFFEConfig(
            workload_api_socket='unix:///run/spire/sockets/agent.sock',
            trust_domain='neural-hive.local',
            jwt_audience='neural-hive.local',
            jwt_ttl_seconds=3600,
            enable_x509=False,
            environment='development'
        )

        with patch('neural_hive_security.grpc_channel_factory.grpc.aio.insecure_channel') as mock_insecure:
            mock_insecure.return_value = MagicMock()
            channel = await create_secure_grpc_channel(
                target='test:50051',
                spiffe_config=spiffe_config,
                spiffe_manager=None,
                fallback_insecure=True
            )
            mock_insecure.assert_called_once()

    @pytest.mark.asyncio
    async def test_DEV_uppercase_allows_fallback(self):
        """Teste: 'DEV' maiusculo permite fallback (case insensitive)."""
        spiffe_config = SPIFFEConfig(
            workload_api_socket='unix:///run/spire/sockets/agent.sock',
            trust_domain='neural-hive.local',
            jwt_audience='neural-hive.local',
            jwt_ttl_seconds=3600,
            enable_x509=False,
            environment='DEV'
        )

        with patch('neural_hive_security.grpc_channel_factory.grpc.aio.insecure_channel') as mock_insecure:
            mock_insecure.return_value = MagicMock()
            channel = await create_secure_grpc_channel(
                target='test:50051',
                spiffe_config=spiffe_config,
                spiffe_manager=None,
                fallback_insecure=True
            )
            mock_insecure.assert_called_once()

    @pytest.mark.asyncio
    async def test_DEVELOPMENT_uppercase_allows_fallback(self):
        """Teste: 'DEVELOPMENT' maiusculo permite fallback (case insensitive)."""
        spiffe_config = SPIFFEConfig(
            workload_api_socket='unix:///run/spire/sockets/agent.sock',
            trust_domain='neural-hive.local',
            jwt_audience='neural-hive.local',
            jwt_ttl_seconds=3600,
            enable_x509=False,
            environment='DEVELOPMENT'
        )

        with patch('neural_hive_security.grpc_channel_factory.grpc.aio.insecure_channel') as mock_insecure:
            mock_insecure.return_value = MagicMock()
            channel = await create_secure_grpc_channel(
                target='test:50051',
                spiffe_config=spiffe_config,
                spiffe_manager=None,
                fallback_insecure=True
            )
            mock_insecure.assert_called_once()

    @pytest.mark.asyncio
    async def test_prod_blocks_fallback(self):
        """Teste: 'prod' bloqueia fallback."""
        spiffe_config = SPIFFEConfig(
            workload_api_socket='unix:///run/spire/sockets/agent.sock',
            trust_domain='neural-hive.local',
            jwt_audience='neural-hive.local',
            jwt_ttl_seconds=3600,
            enable_x509=False,
            environment='prod'
        )

        with pytest.raises(RuntimeError):
            await create_secure_grpc_channel(
                target='test:50051',
                spiffe_config=spiffe_config,
                spiffe_manager=None,
                fallback_insecure=True
            )

    @pytest.mark.asyncio
    async def test_production_blocks_fallback(self):
        """Teste: 'production' bloqueia fallback."""
        spiffe_config = SPIFFEConfig(
            workload_api_socket='unix:///run/spire/sockets/agent.sock',
            trust_domain='neural-hive.local',
            jwt_audience='neural-hive.local',
            jwt_ttl_seconds=3600,
            enable_x509=False,
            environment='production'
        )

        with pytest.raises(RuntimeError):
            await create_secure_grpc_channel(
                target='test:50051',
                spiffe_config=spiffe_config,
                spiffe_manager=None,
                fallback_insecure=True
            )

    @pytest.mark.asyncio
    async def test_staging_blocks_fallback(self):
        """Teste: 'staging' bloqueia fallback."""
        spiffe_config = SPIFFEConfig(
            workload_api_socket='unix:///run/spire/sockets/agent.sock',
            trust_domain='neural-hive.local',
            jwt_audience='neural-hive.local',
            jwt_ttl_seconds=3600,
            enable_x509=False,
            environment='staging'
        )

        with pytest.raises(RuntimeError):
            await create_secure_grpc_channel(
                target='test:50051',
                spiffe_config=spiffe_config,
                spiffe_manager=None,
                fallback_insecure=True
            )
