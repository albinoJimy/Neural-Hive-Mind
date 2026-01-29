#!/bin/bash
#
# Script para configurar worker nodes do Kubernetes
# Versão: 1.29.15
# Execute este script em cada VM que será adicionada como worker
#

set -e

echo "=========================================="
echo "Configuração de Worker Node - Kubernetes"
echo "=========================================="
echo ""

# Verificar se está rodando como root
if [[ $EUID -ne 0 ]]; then
   echo "Este script precisa ser executado como root (sudo)"
   exit 1
fi

# Variáveis
K8S_VERSION="1.29.15"
CONTAINERD_VERSION="1.7.27"

echo "[1/7] Desabilitando swap..."
swapoff -a
sed -i '/ swap / s/^\(.*\)$/#\1/g' /etc/fstab

echo "[2/7] Configurando módulos do kernel..."
cat <<EOF | tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF

modprobe overlay
modprobe br_netfilter

cat <<EOF | tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF

sysctl --system

echo "[3/7] Instalando containerd..."
apt-get update
apt-get install -y apt-transport-https ca-certificates curl software-properties-common

# Instalar containerd
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -
add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
apt-get update
apt-get install -y containerd.io

# Configurar containerd
mkdir -p /etc/containerd
containerd config default | tee /etc/containerd/config.toml
sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml

systemctl restart containerd
systemctl enable containerd

echo "[4/7] Instalando kubeadm, kubelet e kubectl..."
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.29/deb/Release.key | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.29/deb/ /' | tee /etc/apt/sources.list.d/kubernetes.list

apt-get update
apt-get install -y kubelet kubeadm kubectl
apt-mark hold kubelet kubeadm kubectl

systemctl enable kubelet

echo "[5/7] Configurações de rede..."
# Permitir tráfego necessário no firewall (se ufw estiver ativo)
if systemctl is-active --quiet ufw; then
    echo "Configurando firewall..."
    ufw allow 10250/tcp  # Kubelet API
    ufw allow 30000:32767/tcp  # NodePort Services
fi

echo "[6/7] Verificando instalação..."
echo "Versão do containerd: $(containerd --version)"
echo "Versão do kubeadm: $(kubeadm version -o short)"
echo "Versão do kubelet: $(kubelet --version)"

echo ""
echo "=========================================="
echo "✓ Instalação concluída com sucesso!"
echo "=========================================="
echo ""
echo "[7/7] Próximo passo: Fazer join ao cluster"
echo ""
echo "Execute o seguinte comando NESTE servidor para adicionar como worker:"
echo ""
echo "sudo kubeadm join 37.60.241.150:6443 --token vcknwv.u965dgbhjcgv5gre --discovery-token-ca-cert-hash sha256:aa809c60d71383b75447b3573683af29c57643feb8862bc5cfe1e1853bfd6562"
echo ""
echo "NOTA: Este token é válido por 24 horas"
echo ""
