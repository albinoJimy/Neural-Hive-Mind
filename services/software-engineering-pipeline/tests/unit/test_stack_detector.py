from src.generators.stack_detector import StackDetector


def test_detect_python_project():
    files = [
        "requirements.txt",
        "app.py",
        "Dockerfile",
    ]
    detector = StackDetector(files)
    result = detector.detect()

    assert result.detected is True
    assert result.stack.language == "python"
    assert result.stack.package_manager == "pip"
    assert result.stack.has_dockerfile is True
    assert result.confidence > 0.5


def test_detect_node_project():
    files = [
        "package.json",
        "yarn.lock",
        "src/index.js",
        "docker-compose.yml",
    ]
    detector = StackDetector(files)
    result = detector.detect()

    assert result.detected is True
    assert result.stack.language == "node"
    assert result.stack.package_manager == "npm"
    assert result.stack.has_docker_compose is True


def test_detect_golang_project():
    files = [
        "go.mod",
        "main.go",
        "Dockerfile",
    ]
    detector = StackDetector(files)
    result = detector.detect()

    assert result.detected is True
    assert result.stack.language == "go"
    assert result.stack.has_dockerfile is True


def test_detect_kubernetes_manifests():
    files = [
        "requirements.txt",
        "app.py",
        "k8s/deployment.yaml",
        "k8s/service.yaml",
    ]
    detector = StackDetector(files)
    result = detector.detect()

    assert result.stack.kubernetes_manifests is True


def test_detect_helm_chart():
    files = [
        "requirements.txt",
        "helm/Chart.yaml",
        "helm/values.yaml",
    ]
    detector = StackDetector(files)
    result = detector.detect()

    assert result.stack.has_helm_chart is True


def test_detect_framework_django():
    files = ["requirements.txt"]
    contents = {"requirements.txt": "django==4.2\npytest\n"}
    detector = StackDetector(files, file_contents=contents)
    result = detector.detect()

    assert result.stack.framework == "django"


def test_detect_framework_fastapi():
    files = ["requirements.txt"]
    contents = {"requirements.txt": "fastapi==0.100\nuvicorn\n"}
    detector = StackDetector(files, file_contents=contents)
    result = detector.detect()

    assert result.stack.framework == "fastapi"


def test_low_confidence_no_indicators():
    files = ["README.md", ".gitignore"]
    detector = StackDetector(files)
    result = detector.detect()

    assert result.detected is False
    assert result.confidence == 0.0


def test_java_project():
    files = ["pom.xml", "src/main/java/App.java"]
    detector = StackDetector(files)
    result = detector.detect()

    assert result.detected is True
    assert result.stack.language == "java"
    assert result.stack.package_manager == "maven"
