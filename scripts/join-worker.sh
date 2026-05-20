#!/usr/bin/env bash
# Setup completo de um worker novo para juntar ao cluster Neural-Hive-Mind
# Executar via SSH como root ou com sudo no VPS recém-instalado.
# Compatível Ubuntu 24.04 LTS.
set -euo pipefail

# Required via env vars (não commitar tokens/IPs ao repo)
#   CONTROL_PLANE   ex: "1.2.3.4:6443"
#   TOKEN           gera no control plane: kubeadm token create --print-join-command
#   CA_HASH         sha256:... do CA cert do cluster
# Opcionais:
#   NODE_NAME              (default: hostname -s)
#   K8S_VERSION            (default: 1.29)
#   K8S_FULL               (default: 1.29.15-1.1)
#   CONTAINERD_VERSION     (default: 1.7.27)

NODE_NAME="${NODE_NAME:-$(hostname -s)}"
K8S_VERSION="${K8S_VERSION:-1.29}"
K8S_FULL="${K8S_FULL:-1.29.15-1.1}"
CONTAINERD_VERSION="${CONTAINERD_VERSION:-1.7.27}"
CONTROL_PLANE="${CONTROL_PLANE:?Set CONTROL_PLANE=host:6443}"
TOKEN="${TOKEN:?Set TOKEN}"
CA_HASH="${CA_HASH:?Set CA_HASH (sha256:...)}"

echo "==> Joining node: ${NODE_NAME}"

echo "==> [1/9] Update apt and install pre-requirements"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y apt-transport-https ca-certificates curl gpg gnupg lsb-release jq

echo "==> [2/9] Disable swap (K8s requirement)"
swapoff -a
sed -i '/ swap / s/^/#/' /etc/fstab

echo "==> [3/9] Load kernel modules"
cat <<EOF | tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF
modprobe overlay
modprobe br_netfilter

echo "==> [4/9] Apply K8s sysctls"
cat <<EOF | tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF
sysctl --system

echo "==> [5/9] Install containerd $CONTAINERD_VERSION (igual aos outros workers)"
ARCH=$(dpkg --print-architecture)
curl -fsSL "https://github.com/containerd/containerd/releases/download/v${CONTAINERD_VERSION}/containerd-${CONTAINERD_VERSION}-linux-${ARCH}.tar.gz" \
  | tar -C /usr/local -xz
curl -fsSL https://raw.githubusercontent.com/containerd/containerd/main/containerd.service \
  -o /etc/systemd/system/containerd.service
mkdir -p /etc/containerd
containerd config default > /etc/containerd/config.toml
# Use systemd cgroup driver (igual ao kubelet)
sed -i 's/SystemdCgroup = false/SystemdCgroup = true/g' /etc/containerd/config.toml
# Install runc
curl -fsSL "https://github.com/opencontainers/runc/releases/download/v1.1.12/runc.${ARCH}" -o /usr/local/sbin/runc
chmod +x /usr/local/sbin/runc
# Install CNI plugins
mkdir -p /opt/cni/bin
curl -fsSL "https://github.com/containernetworking/plugins/releases/download/v1.4.1/cni-plugins-linux-${ARCH}-v1.4.1.tgz" \
  | tar -C /opt/cni/bin -xz
systemctl daemon-reload
systemctl enable --now containerd

echo "==> [6/9] Install kubelet/kubeadm/kubectl ${K8S_FULL}"
mkdir -p /etc/apt/keyrings
curl -fsSL "https://pkgs.k8s.io/core:/stable:/v${K8S_VERSION}/deb/Release.key" \
  | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v${K8S_VERSION}/deb/ /" \
  | tee /etc/apt/sources.list.d/kubernetes.list
apt-get update -y
apt-get install -y --allow-downgrades "kubelet=${K8S_FULL}" "kubeadm=${K8S_FULL}" "kubectl=${K8S_FULL}"
apt-mark hold kubelet kubeadm kubectl

echo "==> [7/9] Configure crictl"
cat <<EOF | tee /etc/crictl.yaml
runtime-endpoint: unix:///run/containerd/containerd.sock
image-endpoint: unix:///run/containerd/containerd.sock
timeout: 10
debug: false
EOF

echo "==> [8/9] Pull pause image (sanity test de connectivity)"
crictl pull registry.k8s.io/pause:3.9 || {
  echo "WARN: pause image pull failed — verifica networking do nó antes de continuar"
  exit 1
}

echo "==> [9/9] Run kubeadm join"
kubeadm join "${CONTROL_PLANE}" \
  --token "${TOKEN}" \
  --discovery-token-ca-cert-hash "${CA_HASH}" \
  --node-name "${NODE_NAME}"

echo
echo "✅ Done. Verifica no control plane: kubectl get nodes"
echo "Próximo: kubectl label node ${NODE_NAME} node-role.kubernetes.io/worker=  (opcional, role label)"
