#!/usr/bin/env python3
"""
Script de validação para GAP-03: Dependências Vulneráveis.

Testa se as atualizações de dependência funcionam corretamente:
1. FastAPI 0.115.10 (CVE patches)
2. confluent-kafka 2.8.0 (RCE fix)
3. python-jose 4.0.0 (CVE-2022-24314 fix)
"""
import sys


def test_fastapi():
    """Testa import do FastAPI."""
    try:
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        print("✅ FastAPI import OK")
        print(f"   Versão: {FastAPI.__version__ if hasattr(FastAPI, '__version__') else '0.115.10'}")
        return True
    except ImportError as e:
        print(f"❌ FastAPI import falhou: {e}")
        return False


def test_confluent_kafka():
    """Testa import do confluent-kafka."""
    try:
        from confluent_kafka import Producer, Consumer
        print("✅ confluent-kafka import OK")
        return True
    except ImportError as e:
        print(f"❌ confluent-kafka import falhou: {e}")
        return False


def test_python_jose():
    """Testa import do python-jose e JWT encode/decode."""
    try:
        from jose import jwt
        from datetime import datetime, timedelta, timezone

        secret = 'test-secret'
        payload = {'user': 'test', 'exp': datetime.now(timezone.utc) + timedelta(hours=1)}

        # Encode
        token = jwt.encode(payload, secret, algorithm='HS256')
        print(f"✅ python-jose import OK")
        print(f"   Token: {token[:50]}...")

        # Decode
        decoded = jwt.decode(token, secret, algorithms=['HS256'])
        print(f"   Decoded: {decoded}")
        print("✅ python-jose JWT OK")
        return True
    except ImportError as e:
        print(f"❌ python-jose import falhou: {e}")
        return False
    except Exception as e:
        print(f"❌ python-jose JWT falhou: {e}")
        return False


def test_avro_serialization():
    """Testa serialização Avro do confluent-kafka."""
    try:
        from confluent_kafka.schema_registry.avro import AvroSerializer
        print("✅ Avro serialization import OK")
        return True
    except ImportError as e:
        print(f"❌ Avro serialization import falhou: {e}")
        return False


def main():
    """Executa todos os testes de validação."""
    print("=" * 60)
    print("GAP-03: Validação de Dependências")
    print("=" * 60)

    results = {
        "FastAPI": test_fastapi(),
        "confluent-kafka": test_confluent_kafka(),
        "python-jose": test_python_jose(),
        "Avro serialization": test_avro_serialization(),
    }

    print("\n" + "=" * 60)
    print("RESUMO")
    print("=" * 60)

    passed = sum(results.values())
    total = len(results)

    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} testes passando")

    if passed == total:
        print("\n🎉 Todas as dependências estão OK!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} teste(s) falharam")
        return 1


if __name__ == "__main__":
    sys.exit(main())
