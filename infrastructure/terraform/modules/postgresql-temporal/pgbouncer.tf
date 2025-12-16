resource "kubernetes_config_map" "pgbouncer_config" {
  metadata {
    name      = "pgbouncer-temporal-config"
    namespace = kubernetes_namespace.postgres_temporal.metadata[0].name
    labels = {
      "app" = "pgbouncer-temporal"
    }
  }

  data = {
    "pgbouncer.ini" = <<-EOT
[databases]
temporal = host=${var.cluster_name}-headless port=5432 dbname=temporal auth_user=temporal

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = plain
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 25
min_pool_size = 5
reserve_pool_size = 10
server_reset_query = DISCARD ALL
ignore_startup_parameters = extra_float_digits
    EOT
  }
}

resource "kubernetes_secret" "pgbouncer_users" {
  metadata {
    name      = "pgbouncer-temporal-users"
    namespace = kubernetes_namespace.postgres_temporal.metadata[0].name
    labels = {
      "app" = "pgbouncer-temporal"
    }
  }

  string_data = {
    "userlist.txt" = <<-EOT
"temporal" "${var.temporal_password}"
    EOT
  }
}

resource "kubernetes_deployment" "pgbouncer" {
  metadata {
    name      = "pgbouncer-temporal"
    namespace = kubernetes_namespace.postgres_temporal.metadata[0].name
  }
  spec {
    replicas = 2
    selector {
      match_labels = {
        "app" = "pgbouncer-temporal"
      }
    }
    template {
      metadata {
        labels = {
          "app" = "pgbouncer-temporal"
        }
      }
      spec {
        container {
          name  = "pgbouncer"
          image = "pgbouncer/pgbouncer:1.21"
          command = [
            "pgbouncer",
            "/etc/pgbouncer/pgbouncer.ini"
          ]
          port {
            container_port = 6432
            name           = "postgres"
            protocol       = "TCP"
          }
          volume_mount {
            name       = "pgbouncer-config"
            mount_path = "/etc/pgbouncer/pgbouncer.ini"
            sub_path   = "pgbouncer.ini"
          }
          volume_mount {
            name       = "pgbouncer-users"
            mount_path = "/etc/pgbouncer/userlist.txt"
            sub_path   = "userlist.txt"
          }
        }

        volume {
          name = "pgbouncer-config"
          config_map {
            name = kubernetes_config_map.pgbouncer_config.metadata[0].name
          }
        }

        volume {
          name = "pgbouncer-users"
          secret {
            secret_name = kubernetes_secret.pgbouncer_users.metadata[0].name
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "pgbouncer" {
  metadata {
    name      = "pgbouncer-temporal"
    namespace = kubernetes_namespace.postgres_temporal.metadata[0].name
    labels = {
      "app" = "pgbouncer-temporal"
    }
  }

  spec {
    selector = {
      "app" = "pgbouncer-temporal"
    }
    port {
      name        = "postgres"
      port        = 6432
      target_port = 6432
      protocol    = "TCP"
    }
    type = "ClusterIP"
  }
}
