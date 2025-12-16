#!/usr/bin/env python3
"""
Script para gerar chave de criptografia Fernet.

Uso:
    python generate_encryption_key.py --output-path /path/to/encryption.key
    python generate_encryption_key.py --print-key
"""
import argparse
import os
import sys
from pathlib import Path


def generate_key():
    """Gera chave Fernet."""
    try:
        from cryptography.fernet import Fernet
        return Fernet.generate_key()
    except ImportError:
        print("ERRO: cryptography não instalado. Instale com: pip install cryptography>=41.0.0", file=sys.stderr)
        sys.exit(1)


def save_key(key: bytes, path: str, force: bool = False):
    """
    Salva chave em arquivo com permissões restritas.

    Args:
        key: Chave Fernet
        path: Caminho do arquivo
        force: Sobrescrever arquivo existente
    """
    file_path = Path(path)

    # Verificar se arquivo já existe
    if file_path.exists() and not force:
        print(f"ERRO: Arquivo {path} já existe. Use --force para sobrescrever.", file=sys.stderr)
        sys.exit(1)

    # Criar diretório pai se não existir
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Salvar chave
    try:
        with open(file_path, 'wb') as f:
            f.write(key)

        # Definir permissões 0600 (apenas owner pode ler/escrever)
        os.chmod(file_path, 0o600)

        print(f"✅ Chave de criptografia gerada e salva em: {path}")
        print(f"   Permissões: 0600 (leitura/escrita apenas pelo owner)")

    except Exception as e:
        print(f"ERRO ao salvar chave: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description='Gera chave de criptografia Fernet para Neural Hive Compliance Layer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Gerar e salvar em arquivo
  python generate_encryption_key.py --output-path /etc/neural-hive/encryption.key

  # Gerar e exibir no stdout (para copiar para variável de ambiente)
  python generate_encryption_key.py --print-key

  # Sobrescrever arquivo existente
  python generate_encryption_key.py --output-path ./encryption.key --force

Configuração:
  Para usar a chave gerada, configure uma das variáveis de ambiente:

  # Opção 1: Path para arquivo de chave
  export ENCRYPTION_KEY_PATH=/etc/neural-hive/encryption.key

  # Opção 2: Chave em base64 (use --print-key)
  export ENCRYPTION_KEY=$(python generate_encryption_key.py --print-key)

Segurança:
  ⚠️  IMPORTANTE: Faça backup da chave em local seguro!
  ⚠️  Se a chave for perdida, dados criptografados não poderão ser recuperados.
  ⚠️  Não commit a chave no git. Adicione ao .gitignore:
      echo "*.key" >> .gitignore
        """
    )

    parser.add_argument(
        '--output-path',
        type=str,
        help='Caminho para salvar chave (default: ./encryption.key)'
    )

    parser.add_argument(
        '--print-key',
        action='store_true',
        help='Exibir chave no stdout (útil para variável de ambiente)'
    )

    parser.add_argument(
        '--force',
        action='store_true',
        help='Sobrescrever arquivo existente'
    )

    args = parser.parse_args()

    # Validar argumentos
    if not args.output_path and not args.print_key:
        # Default: salvar em ./encryption.key
        args.output_path = './encryption.key'

    if args.output_path and args.print_key:
        print("ERRO: Use --output-path OU --print-key, não ambos.", file=sys.stderr)
        sys.exit(1)

    # Gerar chave
    print("🔑 Gerando chave de criptografia Fernet...", file=sys.stderr)
    key = generate_key()

    if args.print_key:
        # Exibir chave no stdout (apenas a chave, sem mensagens)
        print(key.decode('utf-8'))
        print("\n💡 Para usar como variável de ambiente:", file=sys.stderr)
        print(f"   export ENCRYPTION_KEY='{key.decode('utf-8')}'", file=sys.stderr)
    else:
        # Salvar em arquivo
        save_key(key, args.output_path, args.force)
        print("\n📝 Configuração:")
        print(f"   export ENCRYPTION_KEY_PATH={os.path.abspath(args.output_path)}")
        print("\n⚠️  IMPORTANTE:")
        print("   - Faça backup desta chave em local seguro")
        print("   - Adicione *.key ao .gitignore")
        print("   - Sem a chave, dados criptografados não podem ser recuperados")


if __name__ == '__main__':
    main()
