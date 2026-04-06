"""Teste de compatibilidade Python 3.10 para datetime.UTC."""
import sys
import pytest


class TestDatetimeCompatPython310:
    """Testa que o polyfill UTC funciona corretamente em Python 3.10."""
    
    def test_neural_hive_domain_utc_import(self):
        """Testa que UTC pode ser importado de neural_hive_domain."""
        from neural_hive_domain import UTC
        
        # UTC deve ser um timezone
        assert UTC is not None
        assert hasattr(UTC, 'utcoffset')
    
    def test_utc_is_timezone_utc(self):
        """Testa que UTC e timezone.utc."""
        from datetime import timezone
        from neural_hive_domain import UTC
        
        assert UTC == timezone.utc
    
    def test_utc_with_datetime_now(self):
        """Testa que UTC funciona com datetime.now()."""
        from datetime import datetime
        from neural_hive_domain import UTC
        
        # Deve funcionar sem erros
        now = datetime.now(UTC)
        assert now is not None
        assert now.tzinfo is not None
    
    def test_utc_with_datetime_combine(self):
        """Testa que UTC funciona com datetime.combine()."""
        from datetime import datetime, date
        from neural_hive_domain import UTC
        
        today = date.today()
        dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        assert dt is not None
        assert dt.tzinfo is not None
    
    def test_py310_compat_flag(self):
        """Testa que a flag PY311_PLUS funciona corretamente."""
        from neural_hive_domain import PY311_PLUS
        
        # Em Python 3.10, deve ser False
        if sys.version_info >= (3, 11):
            assert PY311_PLUS is True
        else:
            assert PY311_PLUS is False
    
    def test_strenum_available(self):
        """Testa que StrEnum esta disponivel."""
        from neural_hive_domain import StrEnum
        
        # Deve ser possivel criar um StrEnum
        class TestEnum(StrEnum):
            A = "a"
            B = "b"
        
        assert TestEnum.A == "a"
        assert TestEnum.A.value == "a"
    
    def test_utc_aware_datetime_comparison(self):
        """Testa comparacao de datetime com UTC."""
        from datetime import datetime, timedelta
        from neural_hive_domain import UTC
        
        now1 = datetime.now(UTC)
        now2 = datetime.now(UTC)
        
        # now2 deve ser maior ou igual a now1
        assert now2 >= now1
        
        # Teste com timedelta
        later = now1 + timedelta(hours=1)
        assert later > now1
    
    def test_utc_isoformat(self):
        """Testa que datetime com UTC tem isoformat correto."""
        from datetime import datetime
        from neural_hive_domain import UTC
        
        now = datetime.now(UTC)
        iso_str = now.isoformat()
        
        # Deve terminar com +00:00
        assert iso_str.endswith('+00:00') or iso_str.endswith('Z')


class TestDatetimeCompatWorkerAgents:
    """Testa que o compat.py em worker-agents tambem funciona."""
    
    def test_worker_agents_compat_module(self):
        """Testa que o modulo compat em worker-agents funciona."""
        try:
            from services.worker_agents.src.compat import UTC, StrEnum, PY311_PLUS
            
            assert UTC is not None
            assert StrEnum is not None
            assert isinstance(PY311_PLUS, bool)
        except ImportError:
            # Se worker-agents nao estiver instalado, skip
            pytest.skip("worker-agents not installed")


def test_no_direct_utc_import_needed():
    """Testa que nao precisamos importar UTC diretamente de datetime."""
    import datetime
    
    # Em Python 3.10, UTC nao deve estar disponivel diretamente
    # a menos que tenha sido definido pelo codigo
    py310 = sys.version_info < (3, 11)
    
    if py310:
        # Nao deve ter UTC em datetime (a menos que polyfill)
        # O importante e que neural_hive_domain.UTC funciona
        from neural_hive_domain import UTC
        assert UTC is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
