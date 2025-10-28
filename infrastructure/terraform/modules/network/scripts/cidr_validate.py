#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de validação CIDR para o módulo Terraform network.
Valida se todos os subnets estão contidos no VPC e se não há sobreposições.

Entrada: JSON stdin com vpc_cidr e subnets
Saída: JSON stdout com contains e overlap
"""

import json
import sys
import ipaddress
from typing import List, Dict


def validate_cidr_containment_and_overlap(vpc_cidr: str, subnets: List[str]) -> Dict[str, str]:
    """
    Valida se todos os subnets estão contidos no VPC e se não há sobreposições.

    Args:
        vpc_cidr: CIDR do VPC (ex: "10.0.0.0/16")
        subnets: Lista de CIDRs dos subnets (ex: ["10.0.1.0/24", "10.0.2.0/24"])

    Returns:
        Dict com:
        - contains: "true" se todos os subnets estão contidos no VPC, "false" caso contrário
        - overlap: "true" se há sobreposições entre subnets, "false" caso contrário
    """
    try:
        # Parse do VPC CIDR
        vpc_network = ipaddress.ip_network(vpc_cidr, strict=False)

        # Parse dos subnet CIDRs
        subnet_networks = []
        for subnet_cidr in subnets:
            subnet_network = ipaddress.ip_network(subnet_cidr, strict=False)
            subnet_networks.append(subnet_network)

        # Verifica contenção - todos os subnets devem estar dentro do VPC
        contains = True
        for subnet_network in subnet_networks:
            if not subnet_network.subnet_of(vpc_network):
                contains = False
                break

        # Verifica sobreposições - nenhum par de subnets deve se sobrepor
        overlap = False
        for i in range(len(subnet_networks)):
            for j in range(i + 1, len(subnet_networks)):
                if subnet_networks[i].overlaps(subnet_networks[j]):
                    overlap = True
                    break
            if overlap:
                break

        return {
            "contains": "true" if contains else "false",
            "overlap": "true" if overlap else "false"
        }

    except (ipaddress.AddressValueError, ValueError) as e:
        # Em caso de erro de parsing, considera como inválido
        return {
            "contains": "false",
            "overlap": "true"
        }


def main():
    """Função principal que lê stdin e escreve stdout."""
    try:
        # Lê entrada JSON do stdin
        input_data = json.load(sys.stdin)

        vpc_cidr = input_data.get("vpc_cidr", "")
        subnets_json = input_data.get("subnets", "[]")

        # Parse da lista de subnets (pode vir como string JSON)
        if isinstance(subnets_json, str):
            subnets = json.loads(subnets_json)
        else:
            subnets = subnets_json

        # Executa validação
        result = validate_cidr_containment_and_overlap(vpc_cidr, subnets)

        # Escreve resultado JSON no stdout
        json.dump(result, sys.stdout)

    except Exception as e:
        # Em caso de qualquer erro, retorna validação falhando
        error_result = {
            "contains": "false",
            "overlap": "true"
        }
        json.dump(error_result, sys.stdout)


if __name__ == "__main__":
    main()