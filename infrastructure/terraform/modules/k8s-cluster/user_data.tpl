#!/bin/bash
# User data script para nodes EKS com configurações de segurança aprimoradas

# Bootstrap do node EKS
/etc/eks/bootstrap.sh ${cluster_name} \
  --b64-cluster-ca ${ca_cert} \
  --apiserver-endpoint ${endpoint} \
  --kubelet-extra-args '--node-labels=node.kubernetes.io/lifecycle=normal --max-pods=110 --cluster-dns=10.100.0.10'

# Configurações de segurança do kernel
cat <<EOF >> /etc/sysctl.conf
# Proteção contra ataques de rede
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.icmp_ignore_bogus_error_responses = 1

# Otimizações de memória e performance
vm.overcommit_memory = 1
vm.max_map_count = 262144
kernel.panic = 10
kernel.panic_on_oops = 1

# Proteção contra ataques de DDOS
net.ipv4.tcp_max_syn_backlog = 2048
net.ipv4.tcp_synack_retries = 2
net.ipv4.tcp_syn_retries = 5
EOF
sysctl -p

# Configurar auditd para monitoramento de segurança
yum install -y audit audit-libs
systemctl enable auditd
systemctl start auditd

# Regras de auditoria básicas
cat <<EOF >> /etc/audit/rules.d/kubernetes.rules
# Monitorar modificações em arquivos críticos
-w /etc/passwd -p wa -k passwd_changes
-w /etc/shadow -p wa -k shadow_changes
-w /etc/group -p wa -k group_changes
-w /etc/sudoers -p wa -k sudoers_changes
-w /var/lib/kubelet -p wa -k kubelet_changes
-w /etc/kubernetes -p wa -k kubernetes_config

# Monitorar execução de comandos privilegiados
-a always,exit -F arch=b64 -S execve -F uid=0 -F key=root_commands
EOF
systemctl restart auditd

# Configurar iptables para segurança adicional
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -p tcp --dport 22 -m conntrack --ctstate NEW -m limit --limit 2/min --limit-burst 2 -j ACCEPT
iptables -A INPUT -p icmp --icmp-type echo-request -m limit --limit 1/s -j ACCEPT
iptables-save > /etc/sysconfig/iptables

# Script de verificação de saúde do node
cat <<'HEALTH_SCRIPT' > /usr/local/bin/node-health-check.sh
#!/bin/bash
# Envia métricas de saúde do node para CloudWatch

INSTANCE_ID=$(ec2-metadata --instance-id | cut -d " " -f 2)
REGION=$(ec2-metadata --availability-zone | cut -d " " -f 2 | sed 's/.$//')

# Verificar uso de CPU
CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
aws cloudwatch put-metric-data --metric-name CPUUtilization --namespace "EKS/NodeHealth" \
  --value $CPU_USAGE --dimensions Instance=$INSTANCE_ID --region $REGION

# Verificar uso de memória
MEM_USAGE=$(free | grep Mem | awk '{print ($3/$2) * 100.0}')
aws cloudwatch put-metric-data --metric-name MemoryUtilization --namespace "EKS/NodeHealth" \
  --value $MEM_USAGE --dimensions Instance=$INSTANCE_ID --region $REGION

# Verificar uso de disco
DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
aws cloudwatch put-metric-data --metric-name DiskUtilization --namespace "EKS/NodeHealth" \
  --value $DISK_USAGE --dimensions Instance=$INSTANCE_ID --region $REGION
HEALTH_SCRIPT

chmod +x /usr/local/bin/node-health-check.sh

# Adicionar ao cron para execução a cada 5 minutos
echo "*/5 * * * * /usr/local/bin/node-health-check.sh" | crontab -

# Log rotation aprimorado
cat <<EOF > /etc/logrotate.d/kubernetes
/var/log/pods/*/*.log {
    rotate 7
    daily
    maxsize 100M
    missingok
    compress
    delaycompress
    notifempty
    sharedscripts
    postrotate
        /usr/bin/killall -SIGUSR1 kubelet 2>/dev/null || true
    endscript
}

/var/log/messages {
    rotate 7
    daily
    maxsize 100M
    compress
    delaycompress
    missingok
    notifempty
}

/var/log/secure {
    rotate 7
    daily
    maxsize 50M
    compress
    delaycompress
    missingok
    notifempty
}
EOF

# Configurar monitoramento de recursos com CloudWatch agent
wget https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/amazon-cloudwatch-agent.rpm
rpm -U ./amazon-cloudwatch-agent.rpm

# Configuração básica do CloudWatch agent
cat <<EOF > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
{
  "metrics": {
    "namespace": "EKS/Nodes",
    "metrics_collected": {
      "cpu": {
        "measurement": [
          {"name": "cpu_usage_idle", "rename": "CPU_IDLE", "unit": "Percent"},
          {"name": "cpu_usage_iowait", "rename": "CPU_IOWAIT", "unit": "Percent"}
        ],
        "totalcpu": false
      },
      "disk": {
        "measurement": [
          {"name": "used_percent", "rename": "DISK_USED", "unit": "Percent"}
        ],
        "resources": ["/"]
      },
      "mem": {
        "measurement": [
          {"name": "mem_used_percent", "rename": "MEM_USED", "unit": "Percent"}
        ]
      },
      "net": {
        "measurement": [
          {"name": "bytes_sent", "rename": "NET_SENT", "unit": "Bytes"},
          {"name": "bytes_recv", "rename": "NET_RECV", "unit": "Bytes"}
        ]
      }
    }
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/messages",
            "log_group_name": "/aws/eks/${cluster_name}/system",
            "log_stream_name": "{instance_id}/messages"
          },
          {
            "file_path": "/var/log/secure",
            "log_group_name": "/aws/eks/${cluster_name}/security",
            "log_stream_name": "{instance_id}/secure"
          }
        ]
      }
    }
  }
}
EOF

# Iniciar CloudWatch agent
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 -s -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json