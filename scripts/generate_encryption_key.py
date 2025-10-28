#!/usr/bin/env python3
"""
Script utilitário para gerar chave de criptografia Fernet.

Uso:
    python scripts/generate_encryption_key.py --output-path /etc/neural-hive/encryption.key
    python scripts/generate_encryption_key.py --print-key  # Para variável de ambiente
"""
import os
import sys
import argparse
from cryptography.fernet import Fernet


def generate_key(output_path: str = None, print_key: bool = False, force: bool = False):
    """
    Gera chave Fernet e salva em arquivo ou exibe no stdout.

    Args:
        output_path: Caminho para salvar chave (None para default)
        print_key: Exibir chave no stdout
        force: Sobrescrever arquivo existente
    """
    # Gerar chave
    key = Fernet.generate_key()
    key_str = key.decode('utf-8')

    # Exibir no stdout se solicitado
    if print_key:
        print("\n" + "="*60)
        print("CHAVE DE CRIPTOGRAFIA FERNET GERADA")
        print("="*60)
        print(f"\n{key_str}\n")
        print("Para usar como variável de ambiente:")
        print(f"export ENCRYPTION_KEY='{key_str}'")
        print("\nOu em arquivo .env:")
        print(f"ENCRYPTION_KEY={key_str}")
        print("\n" + "="*60)
        print("⚠️  IMPORTANTE: Guarde esta chave com segurança!")
        print("   Perder a chave = perder acesso aos dados criptografados")
        print("="*60 + "\n")
        return

    # Determinar caminho de saída
    if not output_path:
        output_path = './encryption.key'

    # Verificar se arquivo já existe
    if os.path.exists(output_path) and not force:
        print(f"❌ Erro: Arquivo já existe: {output_path}")
        print("   Use --force para sobrescrever")
        sys.exit(1)

    # Verificar se diretório pai existe
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        print(f"❌ Erro: Diretório não existe: {output_dir}")
        print(f"   Crie o diretório primeiro: mkdir -p {output_dir}")
        sys.exit(1)

    # Salvar chave
    try:
        with open(output_path, 'wb') as f:
            f.write(key)

        # Definir permissões 0600 (apenas owner pode ler/escrever)
        os.chmod(output_path, 0o600)

        print(f"✅ Chave gerada e salva com sucesso!")
        print(f"   Arquivo: {output_path}")
        print(f"   Permissões: 0600 (apenas owner pode ler/escrever)")
        print(f"\nConfiguração:")
        print(f"   export ENCRYPTION_KEY_PATH='{os.path.abspath(output_path)}'")
        print(f"\nOu em arquivo .env:")
        print(f"   ENCRYPTION_KEY_PATH={os.path.abspath(output_path)}")
        print(f"\n⚠️  IMPORTANTE:")
        print(f"   - Faça backup desta chave em local seguro")
        print(f"   - Não commite a chave no Git")
        print(f"   - Adicione ao .gitignore: {os.path.basename(output_path)}")

    except PermissionError:
        print(f"❌ Erro: Sem permissão para escrever em {output_path}")
        print(f"   Tente com sudo ou escolha outro diretório")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Erro ao salvar chave: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Gera chave de criptografia Fernet para Neural Hive Compliance Layer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Gerar chave e salvar em arquivo padrão (./encryption.key)
  python scripts/generate_encryption_key.py

  # Gerar e salvar em path específico
  python scripts/generate_encryption_key.py --output-path /etc/neural-hive/encryption.key

  # Exibir chave no stdout (para copiar para variável de ambiente)
  python scripts/generate_encryption_key.py --print-key

  # Sobrescrever arquivo existente
  python scripts/generate_encryption_key.py --force

Segurança:
  - A chave é gerada usando cryptography.fernet.Fernet.generate_key()
  - Arquivo é salvo com permissões 0600 (apenas owner pode ler/escrever)
  - NUNCA commite a chave no Git
  - Faça backup da chave em local seguro
  - Perder a chave = perder acesso aos dados criptografados
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
        help='Exibir chave no stdout (para variável de ambiente)'
    )

    parser.add_argument(
        '--force',
        action='store_true',
        help='Sobrescrever arquivo existente'
    )

    args = parser.parse_args()

    # Validação
    if args.print_key and args.output_path:
        print("❌ Erro: --print-key e --output-path são mutuamente exclusivos")
        sys.exit(1)

    # Gerar chave
    generate_key(
        output_path=args.output_path,
        print_key=args.print_key,
        force=args.force
    )


if __name__ == '__main__':
    main()
