# External Tools Setup Guide

This guide explains how to configure and use the external security and validation tools integrated with Code Forge.

## Overview

Code Forge integrates with the following external tools:

| Tool | Purpose | Auth Required | CLI/API |
|------|---------|---------------|---------|
| Snyk | Dependency vulnerability scanning | Yes (token) | CLI |
| Trivy | Container/IaC vulnerability scanning | No | CLI |
| SonarQube | Static code analysis (SAST) | Yes (token) | CLI + API |
| GitLab | Git operations, Merge Requests | Yes (token) | API |
| GitHub | Git operations, Pull Requests | Yes (token) | API |

## Snyk Setup

### Installation (Local Development)

```bash
# npm
npm install -g snyk

# Homebrew (macOS)
brew install snyk

# Direct download
curl -o /usr/local/bin/snyk https://static.snyk.io/cli/latest/snyk-linux
chmod +x /usr/local/bin/snyk
```

### Authentication

1. Create account at https://snyk.io
2. Go to https://app.snyk.io/account
3. Click "Generate API Token"
4. Set environment variable:
   ```bash
   export SNYK_TOKEN=your-token-here
   ```

### Configuration

```bash
# .env
SNYK_TOKEN=your-token-here
SNYK_ENABLED=true
SNYK_TIMEOUT=300  # seconds
```

### Usage

```python
from src.clients.snyk_client import SnykClient

client = SnykClient(token='...', enabled=True)
result = await client.scan_dependencies('/path/to/project', 'python')

print(f"Status: {result.status}")
print(f"Critical: {result.critical_issues}")
print(f"High: {result.high_issues}")
```

### Supported Languages

- Python (requirements.txt)
- JavaScript/Node.js (package.json)
- Go (go.mod)
- Java (pom.xml, build.gradle)
- Ruby (Gemfile)

## Trivy Setup

### Installation (Local Development)

```bash
# Homebrew (macOS)
brew install trivy

# apt (Debian/Ubuntu)
sudo apt-get install trivy

# Direct download
curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin v0.45.0
```

### Configuration

```bash
# .env
TRIVY_ENABLED=true
TRIVY_SEVERITY=CRITICAL,HIGH  # Filter severities
TRIVY_TIMEOUT=600  # seconds
```

### Usage

```python
from src.clients.trivy_client import TrivyClient

client = TrivyClient(enabled=True, severity='CRITICAL,HIGH')

# Scan container image
result = await client.scan_container_image('nginx:latest')

# Scan filesystem
result = await client.scan_filesystem('/path/to/project')

# Scan IaC (Terraform, Kubernetes, etc.)
result = await client.scan_iac('/path/to/terraform')
```

### Scan Types

- `image`: Docker/OCI container images
- `fs`: Filesystem (dependencies, secrets)
- `config`: IaC configurations (Terraform, Helm, Kubernetes)

## SonarQube Setup

### Installation (Local Development)

```bash
# Docker (recommended for local)
docker run -d --name sonarqube -p 9000:9000 sonarqube:community

# Install SonarQube Scanner
curl -o /tmp/sonar-scanner.zip https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-5.0.1.3006-linux.zip
unzip /tmp/sonar-scanner.zip -d /opt
ln -s /opt/sonar-scanner-5.0.1.3006-linux/bin/sonar-scanner /usr/local/bin/sonar-scanner
```

### Authentication

1. Access SonarQube at http://localhost:9000
2. Default credentials: admin/admin
3. Go to User > My Account > Security
4. Click "Generate Token"
5. Set environment variable:
   ```bash
   export SONARQUBE_TOKEN=your-token-here
   ```

### Configuration

```bash
# .env
SONARQUBE_URL=http://sonarqube:9000
SONARQUBE_TOKEN=your-token-here
SONARQUBE_ENABLED=true
SONARQUBE_SCANNER_TIMEOUT=900  # seconds
SONARQUBE_POLL_INTERVAL=5  # seconds
SONARQUBE_POLL_TIMEOUT=300  # seconds
```

### Usage

```python
from src.clients.sonarqube_client import SonarQubeClient

client = SonarQubeClient(
    url='http://sonarqube:9000',
    token='...',
    enabled=True
)

# Full analysis
result = await client.analyze_code('my-project-key', '/path/to/source')

# Check quality gate
passed = await client.get_quality_gate_status('my-project-key')

# Get issues
issues = await client.get_issues('my-project-key', severity='MAJOR')

# Get metrics
metrics = await client.get_metrics('my-project-key')
```

### Quality Gate Mapping

| SonarQube Status | ValidationStatus | Score |
|------------------|------------------|-------|
| OK | PASSED | 0.9 |
| WARN | WARNING | 0.7 |
| ERROR | FAILED | 0.4 |

### Severity Mapping

| SonarQube | ValidationResult |
|-----------|------------------|
| BLOCKER + CRITICAL | critical_issues |
| MAJOR | high_issues |
| MINOR | medium_issues |
| INFO | low_issues |

## GitLab Setup

### Authentication

1. Go to GitLab > User Settings > Access Tokens
2. Create token with scopes:
   - `api` (full API access)
   - `write_repository` (push code)
3. Set environment variable:
   ```bash
   export GITLAB_TOKEN=your-token-here
   ```

### Configuration

```bash
# .env
GITLAB_URL=https://gitlab.com  # or self-hosted URL
GITLAB_TOKEN=your-token-here
```

### Usage

```python
from src.clients.git_client import GitClient

client = GitClient(
    templates_repo='...',
    templates_branch='main',
    local_path='/tmp/templates',
    gitlab_token='...'
)

# Create branch
branch = await client.create_branch(
    'https://gitlab.com/myorg/myrepo.git',
    'feature-branch'
)

# Commit artifacts
sha = await client.commit_artifacts(
    'https://gitlab.com/myorg/myrepo.git',
    'feature-branch',
    [{'path': 'src/main.py', 'content': 'print("hello")'}],
    'Add new file'
)

# Create merge request
mr_url = await client.create_merge_request(
    'https://gitlab.com/myorg/myrepo.git',
    'feature-branch',
    'Add new feature',
    'Description of changes'
)
```

## GitHub Setup

### Authentication

1. Go to GitHub > Settings > Developer Settings > Personal Access Tokens
2. Generate new token (classic) with scopes:
   - `repo` (full repository access)
   - `workflow` (update GitHub Actions workflows)
3. Set environment variable:
   ```bash
   export GITHUB_TOKEN=your-token-here
   ```

### Configuration

```bash
# .env
GITHUB_TOKEN=your-token-here
```

### Usage

Same as GitLab, but use GitHub URLs:

```python
# Create branch
branch = await client.create_branch(
    'https://github.com/myuser/myrepo',
    'feature-branch'
)

# Create pull request
pr_url = await client.create_merge_request(
    'https://github.com/myuser/myrepo',
    'feature-branch',
    'Add new feature',
    'Description of changes'
)
```

## Troubleshooting

### Snyk

**Error: Authentication failed**
- Verify SNYK_TOKEN is set correctly
- Run `snyk auth` to re-authenticate

**Error: No manifest found**
- Ensure project has dependency file (requirements.txt, package.json, etc.)
- Use `--file` flag to specify custom location

### Trivy

**Error: Failed to download vulnerability database**
- Check network connectivity
- Use `--skip-db-update` for offline mode
- Set `TRIVY_CACHE_DIR` for custom cache location

**Error: Image not found**
- Verify image exists in registry
- Check authentication for private registries

### SonarQube

**Error: Scanner failed to connect**
- Verify SONARQUBE_URL is accessible
- Check firewall/network settings
- Verify SonarQube server is running

**Error: Analysis timeout**
- Increase `SONARQUBE_SCANNER_TIMEOUT`
- Check SonarQube server performance

### GitLab/GitHub

**Error: 401 Unauthorized**
- Verify token is valid and not expired
- Check token has required scopes

**Error: 404 Not Found**
- Verify repository URL is correct
- Check user has access to repository

## Metrics

The following Prometheus metrics are available:

```
# Snyk
code_forge_snyk_scan_duration_seconds

# Trivy
code_forge_trivy_scan_duration_seconds{scan_type="image|fs|config"}

# SonarQube
code_forge_sonarqube_analysis_duration_seconds

# Git
code_forge_git_operations_total{operation="create_branch|commit|push|create_mr", provider="gitlab|github", status="success|failure"}

# Errors
code_forge_external_tool_errors_total{tool="snyk|trivy|sonarqube|git", error_type="timeout|api_error|cli_error"}
```

## Docker Support

All CLIs are pre-installed in the Code Forge Docker image:

```dockerfile
# Snyk CLI
/usr/local/bin/snyk

# Trivy
/usr/local/bin/trivy

# SonarQube Scanner
/usr/local/bin/sonar-scanner
```

To build the image:

```bash
docker build -t code-forge:latest -f services/code-forge/Dockerfile .
```
