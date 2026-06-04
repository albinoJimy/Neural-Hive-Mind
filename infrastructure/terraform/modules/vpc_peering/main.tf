# =============================================================================
# Neural Hive-Mind - VPC Peering Module
# =============================================================================
# Gerencia conexões de peering entre VPCs em diferentes regiões
# =============================================================================

# -----------------------------------------------------------------------------
# VPC Peering Connection
# -----------------------------------------------------------------------------

resource "aws_vpc_peering_connection" "this" {
  provider = aws.requester

  peer_owner_id = var.accepter_account
  peer_vpc_id   = var.accepter_vpc_id
  vpc_id        = var.requester_vpc_id
  peer_region   = var.accepter_region

  auto_accept = var.auto_accept

  tags = merge(
    var.tags,
    {
      Name = var.tags["Name"] || "${var.requester_region}-${var.accepter_region}-peering"
    }
  )

  accepter {
    allow_remote_vpc_dns_resolution = true
  }

  requester {
    allow_remote_vpc_dns_resolution = true
  }
}

# -----------------------------------------------------------------------------
# Peering Connection Accepter (se necessário)
# -----------------------------------------------------------------------------

resource "aws_vpc_peering_connection_accepter" "this" {
  provider = aws.accepter
  count    = var.auto_accept ? 0 : 1

  vpc_peering_connection_id = aws_vpc_peering_connection.this.id
  auto_accept               = true

  tags = var.tags
}

# -----------------------------------------------------------------------------
# Route Table Entries - Requester Side
# -----------------------------------------------------------------------------

resource "aws_route" "requester_routes" {
  provider = aws.requester
  count    = length(var.requester_route_table_ids)

  route_table_id                        = var.requester_route_table_ids[count.index]
  destination_vpc_peering_connection_id = aws_vpc_peering_connection.this.id

  depends_on = [
    aws_vpc_peering_connection_accepter.this
  ]
}

# -----------------------------------------------------------------------------
# Route Table Entries - Accepter Side
# -----------------------------------------------------------------------------

resource "aws_route" "accepter_routes" {
  provider = aws.accepter
  count    = length(var.accepter_route_table_ids)

  route_table_id                        = var.accepter_route_table_ids[count.index]
  destination_vpc_peering_connection_id = aws_vpc_peering_connection.this.id

  depends_on = [
    aws_vpc_peering_connection_accepter.this
  ]
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "peering_id" {
  description = "ID do VPC peering connection"
  value       = aws_vpc_peering_connection.this.id
}

output "accept_status" {
  description = "Status da conexão"
  value       = aws_vpc_peering_connection.this.status
}
