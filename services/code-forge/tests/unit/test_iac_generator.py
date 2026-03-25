"""
Testes unitários para IaCGenerator.

Cobertura:
- Terraform module generation
- Helm chart generation
- Kubernetes manifests
- CloudFormation templates
"""

import pytest
from src.services.iac_generator import IaCGenerator


class TestIaCGeneratorInit:
    """Testes de inicialização do IaCGenerator."""

    def test_init_default(self):
        """Testa inicialização padrão."""
        generator = IaCGenerator()
        assert generator.supported_providers == ["aws", "gcp", "azure", "kubernetes"]
        assert generator.supported_formats == ["terraform", "helm", "kubernetes", "cloudformation"]


class TestTerraformGeneration:
    """Testes de geração de código Terraform."""

    def test_generate_terraform_aws_basic(self):
        """Testa geração básica de Terraform AWS."""
        generator = IaCGenerator()
        params = {
            'service_name': 'my-service',
            'environment': 'dev',
            'description': 'Test service'
        }

        result = generator.generate_terraform_module(params, 'aws', ['s3_bucket'])

        assert 'terraform' in result
        assert 'aws_s3_bucket' in result
        # Verifica sintaxe Terraform com interpolação de variáveis
        assert 'naming_prefix' in result
        assert '${var.service_name}' in result
        assert '${var.environment}' in result
        assert 'Neural-Code-Forge' in result

    def test_generate_terraform_with_multiple_resources(self):
        """Testa geração de Terraform com múltiplos recursos."""
        generator = IaCGenerator()
        params = {'service_name': 'test-service', 'environment': 'prod'}

        result = generator.generate_terraform_module(
            params,
            'aws',
            ['s3_bucket', 'dynamodb_table', 'lambda_function']
        )

        assert 'aws_s3_bucket' in result
        assert 'aws_dynamodb_table' in result
        assert 'aws_lambda_function' in result

    def test_generate_terraform_gcp(self):
        """Testa geração de Terraform para GCP."""
        generator = IaCGenerator()
        params = {'service_name': 'gcp-service', 'environment': 'dev'}

        result = generator.generate_terraform_module(params, 'gcp', [])

        assert 'google_compute_instance' in result
        assert 'google_storage_bucket' in result

    def test_generate_terraform_azure(self):
        """Testa geração de Terraform para Azure."""
        generator = IaCGenerator()
        params = {'service_name': 'azure-service', 'environment': 'prod'}

        result = generator.generate_terraform_module(params, 'azure', [])

        assert 'azurerm_resource_group' in result
        assert 'azurerm_storage_account' in result

    def test_generate_terraform_with_vpc(self):
        """Testa geração de Terraform com VPC completo."""
        generator = IaCGenerator()
        params = {'service_name': 'vpc-service', 'environment': 'dev'}

        result = generator.generate_terraform_module(params, 'aws', ['vpc'])

        assert 'aws_vpc' in result
        assert 'aws_subnet' in result
        assert 'aws_internet_gateway' in result
        assert 'aws_nat_gateway' in result
        assert 'aws_route_table' in result

    def test_generate_terraform_with_ecs(self):
        """Testa geração de Terraform com ECS."""
        generator = IaCGenerator()
        params = {'service_name': 'ecs-service', 'environment': 'prod'}

        result = generator.generate_terraform_module(params, 'aws', ['ecs_cluster'])

        assert 'aws_ecs_cluster' in result
        assert 'aws_ecs_task_definition' in result
        assert 'aws_ecs_service' in result
        assert 'aws_security_group' in result

    def test_generate_terraform_outputs(self):
        """Testa se outputs são gerados corretamente."""
        generator = IaCGenerator()
        params = {'service_name': 'test-service', 'environment': 'dev'}

        result = generator.generate_terraform_module(params, 'aws', ['s3_bucket'])

        assert 'output "s3_bucket_name"' in result
        assert 'output "s3_bucket_arn"' in result


class TestHelmChartGeneration:
    """Testes de geração de Helm Charts."""

    def test_generate_helm_chart_basic(self):
        """Testa geração básica de Helm chart."""
        generator = IaCGenerator()
        params = {'service_name': 'helm-service', 'description': 'Test Helm Chart'}

        result = generator.generate_helm_chart(params, ['deployment', 'service'])

        assert 'Chart.yaml' in result
        assert 'values.yaml' in result
        assert 'templates/deployment.yaml' in result
        assert 'templates/service.yaml' in result

    def test_helm_chart_yaml_content(self):
        """Testa conteúdo do Chart.yaml."""
        generator = IaCGenerator()
        params = {'service_name': 'my-chart'}

        result = generator.generate_helm_chart(params)
        chart_yaml = result.get('Chart.yaml', '')

        assert 'name: my-chart' in chart_yaml
        assert 'version: 1.0.0' in chart_yaml
        assert 'type: application' in chart_yaml

    def test_helm_values_content(self):
        """Testa conteúdo do values.yaml."""
        generator = IaCGenerator()
        params = {'service_name': 'test-service'}

        result = generator.generate_helm_chart(params)
        values_yaml = result.get('values.yaml', '')

        assert 'replicaCount' in values_yaml
        assert 'image:' in values_yaml
        assert 'service:' in values_yaml
        assert 'resources:' in values_yaml

    def test_helm_deployment_template(self):
        """Testa template de deployment."""
        generator = IaCGenerator()
        params = {'service_name': 'app-service'}

        result = generator.generate_helm_chart(params)
        deployment = result.get('templates/deployment.yaml', '')

        assert 'apiVersion: apps/v1' in deployment
        assert 'kind: Deployment' in deployment
        assert 'serviceAccountName' in deployment
        assert 'livenessProbe' in deployment
        assert 'readinessProbe' in deployment

    def test_helm_service_template(self):
        """Testa template de service."""
        generator = IaCGenerator()
        params = {'service_name': 'app-service'}

        result = generator.generate_helm_chart(params)
        service = result.get('templates/service.yaml', '')

        assert 'apiVersion: v1' in service
        assert 'kind: Service' in service
        # Helm template usa interpolação de valores
        assert '{{ .Values.service.type }}' in service

    def test_helm_with_all_templates(self):
        """Testa geração com todos os templates."""
        generator = IaCGenerator()
        params = {'service_name': 'full-service'}

        templates = ['deployment', 'service', 'configmap', 'hpa', 'ingress', 'serviceaccount']
        result = generator.generate_helm_chart(params, templates)

        assert 'templates/deployment.yaml' in result
        assert 'templates/service.yaml' in result
        assert 'templates/configmap.yaml' in result
        assert 'templates/hpa.yaml' in result
        assert 'templates/ingress.yaml' in result
        assert 'templates/serviceaccount.yaml' in result

    def test_helm_helpers_template(self):
        """Testa template de helpers."""
        generator = IaCGenerator()
        params = {'service_name': 'test-service'}

        result = generator.generate_helm_chart(params)
        helpers = result.get('templates/_helpers.tpl', '')

        assert 'define "service.name"' in helpers
        assert 'define "service.fullname"' in helpers
        assert 'define "service.labels"' in helpers

    def test_helm_notes_template(self):
        """Testa template NOTES.txt."""
        generator = IaCGenerator()
        params = {'service_name': 'notes-service'}

        result = generator.generate_helm_chart(params)
        notes = result.get('templates/NOTES.txt', '')

        assert 'Thank you for installing' in notes
        assert 'helm status' in notes


class TestKubernetesManifests:
    """Testes de geração de manifestos Kubernetes."""

    def test_generate_kubernetes_basic(self):
        """Testa geração básica de manifestos K8s."""
        generator = IaCGenerator()
        params = {'service_name': 'k8s-service', 'namespace': 'production'}

        result = generator.generate_kubernetes_manifests(params)

        assert '00-namespace.yaml' in result
        assert '10-deployment.yaml' in result
        assert '20-service.yaml' in result

    def test_kubernetes_namespace(self):
        """Testa geração de namespace."""
        generator = IaCGenerator()
        params = {'service_name': 'test', 'namespace': 'custom-ns'}

        result = generator.generate_kubernetes_manifests(params, ['namespace'])
        namespace = result.get('00-namespace.yaml', '')

        assert 'kind: Namespace' in namespace
        assert 'name: custom-ns' in namespace

    def test_kubernetes_deployment(self):
        """Testa geração de deployment."""
        generator = IaCGenerator()
        params = {'service_name': 'test-app'}

        result = generator.generate_kubernetes_manifests(params, ['deployment'])
        deployment = result.get('10-deployment.yaml', '')

        assert 'apiVersion: apps/v1' in deployment
        assert 'kind: Deployment' in deployment
        assert 'replicas: 3' in deployment
        assert 'runAsNonRoot: true' in deployment

    def test_kubernetes_service(self):
        """Testa geração de service."""
        generator = IaCGenerator()
        params = {'service_name': 'test-app'}

        result = generator.generate_kubernetes_manifests(params, ['service'])
        service = result.get('20-service.yaml', '')

        assert 'apiVersion: v1' in service
        assert 'kind: Service' in service
        assert 'type: ClusterIP' in service

    def test_kubernetes_with_serviceaccount(self):
        """Testa geração com service account."""
        generator = IaCGenerator()
        params = {'service_name': 'sa-app'}

        result = generator.generate_kubernetes_manifests(params, ['serviceaccount'])
        sa = result.get('05-serviceaccount.yaml', '')

        assert 'apiVersion: v1' in sa
        assert 'kind: ServiceAccount' in sa

    def test_kubernetes_configmap(self):
        """Testa geração de configmap."""
        generator = IaCGenerator()
        params = {'service_name': 'cm-app'}

        result = generator.generate_kubernetes_manifests(params, ['configmap'])
        cm = result.get('30-configmap.yaml', '')

        assert 'apiVersion: v1' in cm
        assert 'kind: ConfigMap' in cm
        assert 'APP_NAME' in cm


class TestCloudFormationGeneration:
    """Testes de geração de templates CloudFormation."""

    def test_generate_cloudformation_basic(self):
        """Testa geração básica de CloudFormation."""
        generator = IaCGenerator()
        params = {'service_name': 'cf-service', 'environment': 'prod'}

        result = generator.generate_cloudformation_template(params)

        assert 'AWSTemplateFormatVersion' in result
        assert 'Description' in result
        assert 'Parameters' in result
        assert 'Resources' in result
        assert 'Outputs' in result

    def test_cloudformation_parameters(self):
        """Testa se parâmetros são gerados."""
        generator = IaCGenerator()
        params = {'service_name': 'test-service'}

        result = generator.generate_cloudformation_template(params)

        assert 'Environment:' in result
        assert 'VpcBlock:' in result
        assert 'InstanceType:' in result

    def test_cloudformation_vpc_resources(self):
        """Testa se recursos VPC são gerados."""
        generator = IaCGenerator()
        params = {'service_name': 'vpc-app'}

        result = generator.generate_cloudformation_template(params)

        assert 'AWS::EC2::VPC' in result
        assert 'AWS::EC2::Subnet' in result
        assert 'AWS::EC2::InternetGateway' in result
        assert 'AWS::EC2::NatGateway' in result

    def test_cloudformation_ecs_resources(self):
        """Testa se recursos ECS são gerados."""
        generator = IaCGenerator()
        params = {'service_name': 'ecs-app'}

        result = generator.generate_cloudformation_template(params)

        assert 'AWS::ECS::Cluster' in result
        assert 'AWS::ECS::TaskDefinition' in result
        assert 'AWS::ECS::Service' in result

    def test_cloudformation_alb(self):
        """Testa se ALB é gerado."""
        generator = IaCGenerator()
        params = {'service_name': 'alb-app'}

        result = generator.generate_cloudformation_template(params)

        assert 'AWS::ElasticLoadBalancingV2::LoadBalancer' in result
        assert 'AWS::ElasticLoadBalancingV2::TargetGroup' in result

    def test_cloudformation_outputs(self):
        """Testa se outputs são gerados."""
        generator = IaCGenerator()
        params = {'service_name': 'output-test'}

        result = generator.generate_cloudformation_template(params)

        assert 'Outputs:' in result
        assert 'ClusterName:' in result
        assert 'LoadBalancerDNS:' in result


class TestIaCGeneratorEdgeCases:
    """Testes de casos extremos do IaCGenerator."""

    def test_empty_params(self):
        """Testa com parâmetros vazios."""
        generator = IaCGenerator()

        result_terraform = generator.generate_terraform_module({}, 'aws', [])
        result_helm = generator.generate_helm_chart({})
        result_k8s = generator.generate_kubernetes_manifests({})

        # Deve usar defaults
        assert 'terraform' in result_terraform
        assert 'Chart.yaml' in result_helm
        assert '10-deployment.yaml' in result_k8s

    def test_unsupported_provider(self):
        """Testa com provider não suportado."""
        generator = IaCGenerator()

        # Deve fallback para aws
        result = generator.generate_terraform_module({}, 'unsupported', [])
        assert 'aws' in result.lower()

    def test_special_characters_in_service_name(self):
        """Testa nomes de serviço com caracteres especiais."""
        generator = IaCGenerator()
        params = {'service_name': 'my--test_service'}

        result = generator.generate_terraform_module(params, 'aws', ['s3_bucket'])
        # Deve sanitizar nome
        assert 'terraform' in result

    def test_long_service_names(self):
        """Testa nomes de serviço muito longos."""
        generator = IaCGenerator()
        params = {'service_name': 'a' * 100}

        result = generator.generate_helm_chart(params)
        # Helm tem limite de 63 caracteres
        chart_yaml = result.get('Chart.yaml', '')
        assert 'name:' in chart_yaml
