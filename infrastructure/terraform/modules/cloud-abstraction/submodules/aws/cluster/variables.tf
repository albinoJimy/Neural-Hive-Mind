variable "environment" {
  type = string
}

variable "region" {
  type = string
}

variable "cluster_name" {
  type = string
}

variable "kubernetes_version" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "availability_zones" {
  type = list(string)
}

variable "node_instance_types" {
  type = list(string)
}

variable "min_nodes_per_zone" {
  type = number
}

variable "max_nodes_per_zone" {
  type = number
}

variable "desired_nodes_per_zone" {
  type = number
}

variable "enable_private_endpoint" {
  type = bool
}

variable "tags" {
  type = map(string)
}
