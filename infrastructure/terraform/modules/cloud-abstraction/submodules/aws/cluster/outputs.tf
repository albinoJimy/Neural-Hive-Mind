output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "cluster_ca_certificate" {
  value = module.eks.cluster_ca_certificate
}

output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_id" {
  value = module.eks.cluster_id
}

output "node_security_group_id" {
  value = module.eks.cluster_security_group_id
}

output "oidc_provider_arn" {
  value = module.eks.oidc_provider_arn
}

output "oidc_provider_url" {
  value = module.eks.oidc_issuer_url
}
