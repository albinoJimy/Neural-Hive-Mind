#!/usr/bin/env python3
"""
Script para gerar pares de chaves RSA para assinatura digital do ledger.

Uso:
    python scripts/generate_rsa_keys.py --output-dir ./keys --key-size 2048
    python scripts/generate_rsa_keys.py --output-dir ./keys --key-size 4096 --specialist technical
"""

import argparse
import os
import sys
from pathlib import Path

# Adicionar path da biblioteca
sys.path.insert(0, str(Path(__file__).parent.parent / 'libraries' / 'python'))

from neural_hive_specialists.ledger import DigitalSigner
import structlog

logger = structlog.get_logger()

def main():
    parser = argparse.ArgumentParser(
        description='Gera par de chaves RSA para assinatura digital do ledger'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        required=True,
        help='Diretório de saída para as chaves'
    )
    parser.add_argument(
        '--key-size',
        type=int,
        choices=[2048, 4096],
        default=2048,
        help='Tamanho da chave em bits (padrão: 2048)'
    )
    parser.add_argument(
        '--specialist',
        type=str,
        default='specialist',
        help='Nome do especialista (usado no nome do arquivo)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Sobrescrever chaves existentes'
    )

    args = parser.parse_args()

    # Criar diretório de saída
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Definir nomes dos arquivos
    private_key_path = output_dir / f'{args.specialist}_private_key.pem'
    public_key_path = output_dir / f'{args.specialist}_public_key.pem'

    # Verificar se chaves já existem
    if not args.force:
        if private_key_path.exists() or public_key_path.exists():
            logger.error(
                "Keys already exist. Use --force to overwrite.",
                private_key=str(private_key_path),
                public_key=str(public_key_path)
            )
            sys.exit(1)

    # Gerar chaves
    logger.info(
        "Generating RSA key pair",
        key_size=args.key_size,
        specialist=args.specialist
    )

    signer = DigitalSigner(config={})
    private_pem, public_pem = signer.generate_keys(key_size=args.key_size)

    # Salvar chaves
    with open(private_key_path, 'wb') as f:
        f.write(private_pem)
    os.chmod(private_key_path, 0o600)  # Apenas owner pode ler

    with open(public_key_path, 'wb') as f:
        f.write(public_pem)
    os.chmod(public_key_path, 0o644)  # Todos podem ler

    logger.info(
        "RSA key pair generated successfully",
        private_key=str(private_key_path),
        public_key=str(public_key_path)
    )

    print(f"\n✅ Chaves geradas com sucesso!")
    print(f"\n📁 Chave privada: {private_key_path}")
    print(f"📁 Chave pública: {public_key_path}")
    print(f"\n⚠️  IMPORTANTE: Mantenha a chave privada segura e nunca a commite no Git!")
    print(f"\n📝 Configure no .env:")
    print(f"   LEDGER_PRIVATE_KEY_PATH={private_key_path}")
    print(f"   LEDGER_PUBLIC_KEY_PATH={public_key_path}")

if __name__ == '__main__':
    main()
