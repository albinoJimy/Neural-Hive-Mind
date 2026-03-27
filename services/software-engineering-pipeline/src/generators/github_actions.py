from jinja2 import Template
from src.generators.base import BasePipelineGenerator, GeneratedPipeline
from src.models.schemas import ProjectStack


GITHUB_ACTIONS_TEMPLATE = """
name: ${ pipeline_name }

on:
  push:
    branches: [main, staging, develop]
  pull_request:
    branches: [main, staging]

env:
  REGISTRY: ${ docker_registry }
  IMAGE_NAME: ${ image_name }

jobs:
{% if stages.pre_flight %}
  pre-flight:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Validate configuration
        run: |
          echo "Validating configuration..."

{% endif %}
{% if stages.build %}
  build:
    runs-on: ubuntu-latest
    {% if stages.pre_flight %}needs: pre-flight{% endif %}
    outputs:
      image-tag: ${{ steps.meta.outputs.tags }}
      image-digest: ${{ steps.build.outputs.digest }}
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ secrets.DOCKER_USERNAME }}
          password: ${{ secrets.DOCKER_PASSWORD }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}

      - name: Build and push
        id: build
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

{% endif %}
{% if stages.test %}
  test:
    runs-on: ubuntu-latest
    needs: build
    steps:
      - uses: actions/checkout@v4

      - name: Run tests
        run: |
          echo "Running tests..."
          # Add test commands here

{% endif %}
{% if stages.security %}
  security:
    runs-on: ubuntu-latest
    needs: build
    steps:
      - uses: actions/checkout@v4

      - name: Run security scan
        run: |
          echo "Running security scan..."

{% endif %}
"""


class GitHubActionsGenerator(BasePipelineGenerator):
    """Gerador de pipelines para GitHub Actions."""

    def __init__(self) -> None:
        self.template = Template(
            GITHUB_ACTIONS_TEMPLATE,
            variable_start_string='${',
            variable_end_string='}',
        )

    async def generate(self, config: dict) -> GeneratedPipeline:
        """Gera um workflow do GitHub Actions.

        Args:
            config: Dicionário com:
                - repo_name: Nome do repositório
                - stack: ProjectStack detectado
                - stages: Dict com estágios a incluir
                - docker_registry: Registry Docker

        Returns:
            GeneratedPipeline com workflow YAML
        """
        repo_name = config.get('repo_name', 'app')
        stack = config.get('stack')
        stages = config.get('stages', {})
        docker_registry = config.get('docker_registry', 'ghcr.io')

        # Determinar estágios padrão baseado na stack
        default_stages = {
            'pre_flight': True,
            'build': stack.has_dockerfile if stack else True,
            'test': True,
            'security': True,
        }
        default_stages.update(stages)

        content = self.template.render(
            pipeline_name=repo_name.replace('_', '-').title() + ' CI',
            image_name=f'{docker_registry}/{repo_name}',
            docker_registry=docker_registry,
            stages=default_stages,
        )

        return GeneratedPipeline(
            content=content.strip(),
            filename='.github/workflows/ci.yml',
            description=f'GitHub Actions CI/CD pipeline for {repo_name}',
        )

    def get_filename(self) -> str:
        """Retorna o nome padrão do arquivo."""
        return '.github/workflows/ci.yml'
