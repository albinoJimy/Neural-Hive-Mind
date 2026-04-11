#!/bin/bash
set -e

CERT_DIR="redis/tls/$(date +%Y%m%d_%H%M%S)"
mkdir -p $CERT_DIR

echo "Generating TLS certificates for Redis Cluster..."

openssl genrsa -out $CERT_DIR/ca.key 4096
openssl req -new -x509 -days 365 -key $CERT_DIR/ca.key -out $CERT_DIR/ca.crt \
  -subj "/CN=Redis-CA/O=Neural-Hive-Mind"

cat > $CERT_DIR/redis.cnf <<EOF
[req]
req_extensions = v3_req
distinguished_name = req_distinguished_name

[req_distinguished_name]

[v3_req]
subjectAltName = @alt_names

[alt_names]
DNS.1 = redis-cluster
DNS.2 = redis-cluster.redis-cluster.svc.cluster.local
DNS.3 = *.redis-cluster.svc.cluster.local
IP.1 = 127.0.0.1
EOF

openssl genrsa -out $CERT_DIR/redis-server.key 2048
openssl req -new -key $CERT_DIR/redis-server.key -out $CERT_DIR/redis-server.csr \
  -subj "/CN=redis-cluster/O=Neural-Hive-Mind" -config $CERT_DIR/redis.cnf
openssl x509 -req -days 365 -in $CERT_DIR/redis-server.csr \
  -CA $CERT_DIR/ca.crt -CAkey $CERT_DIR/ca.key -CAcreateserial \
  -out $CERT_DIR/redis-server.crt -extensions v3_req -extfile $CERT_DIR/redis.cnf

openssl genrsa -out $CERT_DIR/redis-client.key 2048
openssl req -new -key $CERT_DIR/redis-client.key -out $CERT_DIR/redis-client.csr \
  -subj "/CN=redis-client/O=Neural-Hive-Mind"
openssl x509 -req -days 365 -in $CERT_DIR/redis-client.csr \
  -CA $CERT_DIR/ca.crt -CAkey $CERT_DIR/ca.key -CAcreateserial \
  -out $CERT_DIR/redis-client.crt

echo "Certificates generated: $CERT_DIR"
ls -la $CERT_DIR

cat > $CERT_DIR/tls-secrets.yaml <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: redis-ca
  namespace: redis-cluster
type:Opaque
data:
  ca.crt: $(base64 -w0 $CERT_DIR/ca.crt)
---
apiVersion: v1
kind: Secret
metadata:
  name: redis-server-tls
  namespace: redis-cluster
type:Opaque
data:
  tls.crt: $(base64 -w0 $CERT_DIR/redis-server.crt)
  tls.key: $(base64 -w0 $CERT_DIR/redis-server.key)
  ca.crt: $(base64 -w0 $CERT_DIR/ca.crt)
---
apiVersion: v1
kind: Secret
metadata:
  name: redis-client-tls
  namespace: redis-cluster
type:Opaque
data:
  tls.crt: $(base64 -w0 $CERT_DIR/redis-client.crt)
  tls.key: $(base64 -w0 $CERT_DIR/redis-client.key)
  ca.crt: $(base64 -w0 $CERT_DIR/ca.crt)
EOF

echo "TLS secrets template created: $CERT_DIR/tls-secrets.yaml"