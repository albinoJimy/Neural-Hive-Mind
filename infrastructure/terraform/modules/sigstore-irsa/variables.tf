variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
}

variable "oidc_provider_arn" {
  description = "ARN of the OIDC provider for the EKS cluster"
  type        = string

  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:oidc-provider/", var.oidc_provider_arn))
    error_message = "The oidc_provider_arn must be a valid IAM OIDC provider ARN."
  }
}

variable "oidc_provider_url" {
  description = "URL of the OIDC provider for the EKS cluster"
  type        = string

  validation {
    condition     = can(regex("^https://", var.oidc_provider_url))
    error_message = "The oidc_provider_url must be a valid HTTPS URL."
  }
}

variable "namespace" {
  description = "Kubernetes namespace where Sigstore Policy Controller will be deployed"
  type        = string
  default     = "cosign-system"
}

variable "service_account_name" {
  description = "Name of the Kubernetes service account for Sigstore Policy Controller"
  type        = string
  default     = "sigstore-policy-controller"
}

variable "tags" {
  description = "Tags to apply to AWS resources"
  type        = map(string)
  default     = {}
}