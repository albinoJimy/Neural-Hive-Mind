#!/bin/bash

# Testes unitários do CLI de validação

test_cli_help() {
    ./scripts/validate.sh --help > /dev/null
    assertEquals "Help deve retornar 0" 0 $?
}

test_cli_invalid_target() {
    ./scripts/validate.sh --target invalid 2>&1 | grep -q "Target inválido"
    assertEquals "Target inválido deve mostrar erro" 0 $?
}

test_cli_all_target() {
    # Mock kubectl para testes
    export KUBECTL_MOCK=true
    ./scripts/validate.sh --target all --quick > /dev/null
    # Deve executar sem erros
}

# Executar testes
. shunit2
