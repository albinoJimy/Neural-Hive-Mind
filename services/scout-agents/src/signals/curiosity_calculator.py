"""
CuriosityCalculator - Calcula score de curiosidade para exploração de código.

Responsável por:
- Calcular score de "interesse" de arquivos/diretórios
- Considerar fatores: complexidade, padrões, código desconhecido
- Aplicar decaimento para arquivos já visitados
- Agregar scores por diretório
"""
import ast
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set
import structlog

logger = structlog.get_logger()


class CuriosityCalculator:
    """Calcula scores de curiosidade para guiar exploração de código."""

    # Palavras-chave que sugerem código interessante
    INTERESTING_KEYWORDS = {
        'pattern', 'strategy', 'observer', 'factory', 'builder',
        'repository', 'service', 'controller', 'middleware',
        'abstract', 'interface', 'protocol', 'generic',
        'decorator', 'metaclass', 'proxy', 'adapter',
        'state', 'context', 'command', 'chain', 'composite',
        'singleton', 'monad', 'functor', 'coroutine', 'async',
        'concurrent', 'parallel', 'lock', 'mutex', 'semaphore',
        'queue', 'channel', 'stream', 'pipeline', 'workflow'
    }

    # Padrões que indicam complexidade
    COMPLEXITY_PATTERNS = [
        r'class\s+\w+.*:',  # Definições de classe
        r'def\s+\w+\([^)]*\).*:',  # Definições de função
        r'if\s+.*:',  # Condicionais
        r'for\s+.*:',  # Loops for
        r'while\s+.*:',  # Loops while
        r'except.*:',  # Exception handlers
        r'with\s+.*:',  # Context managers
        r'lambda\s+.*:',  # Lambda functions
        r'@\w+',  # Decorators
    ]

    def __init__(self, decay_factor: float = 0.8, decay_hours: int = 24):
        """
        Inicializa CuriosityCalculator.

        Args:
            decay_factor: Fator de decaimento por visita (0-1)
            decay_hours: Horas para reset de decaimento
        """
        self.decay_factor = decay_factor
        self.decay_hours = decay_hours

        # Rastreamento de visitas
        self._visits: Dict[str, List[datetime]] = defaultdict(list)
        self._visit_counts: Dict[str, int] = defaultdict(int)

    def calculate_score(
        self,
        code: str,
        filename: str,
        consider_visits: bool = True
    ) -> float:
        """
        Calcula score de curiosidade para um arquivo.

        Args:
            code: Código fonte
            filename: Nome do arquivo
            consider_visits: Se deve aplicar decaimento por visitas

        Returns:
            Score entre 0 e 100
        """
        base_score = self._calculate_base_score(code, filename)

        if consider_visits:
            decayed_score = self._apply_visit_decay(filename, base_score)
            return min(100, max(0, decayed_score))

        return min(100, max(0, base_score))

    def _calculate_base_score(self, code: str, filename: str) -> float:
        """Calcula score base sem considerar visitas."""
        if not code or not code.strip():
            return 0.0

        score = 0.0

        # Fator 1: Complexidade do código (0-30 pontos)
        score += self._complexity_score(code) * 0.3

        # Fator 2: Densidade de padrões (0-30 pontos)
        score += self._pattern_density_score(code) * 0.3

        # Fator 3: Palavras-chave interessantes (0-20 pontos)
        score += self._keyword_score(code) * 0.2

        # Fator 4: Desconhecido/bibliotecas não padrão (0-10 pontos)
        score += self._unknown_library_score(code) * 0.1

        # Fator 5: Tamanho e comentários (0-10 pontos)
        score += self._documentation_score(code) * 0.1

        return score

    def _complexity_score(self, code: str) -> float:
        """Calcula score baseado em complexidade ciclomática."""
        try:
            tree = ast.parse(code)

            complexity = 1  # Base
            for node in ast.walk(tree):
                if isinstance(node, (ast.If, ast.While, ast.For)):
                    complexity += 1
                elif isinstance(node, ast.ExceptHandler):
                    complexity += 1
                elif isinstance(node, ast.With):
                    complexity += 1
                elif isinstance(node, ast.BoolOp):
                    complexity += len(node.values) - 1

            # Normalizar: complexidade 1-10 -> score 0-100
            return min(100, (complexity / 10) * 100)
        except SyntaxError:
            # Para não-Python, usar regex
            count = sum(len(re.findall(pattern, code)) for pattern in self.COMPLEXITY_PATTERNS)
            return min(100, (count / 20) * 100)

    def _pattern_density_score(self, code: str) -> float:
        """Calcula score baseado em densidade de padrões de design."""
        score = 0

        # Detectar padrões via regex
        patterns = {
            'class': len(re.findall(r'class\s+\w+', code)),
            'inheritance': len(re.findall(r'class\s+\w+\([^)]+\)', code)),
            'decorator': len(re.findall(r'@\w+', code)),
            'abstract': len(re.findall(r'\b(?:ABC|abstractmethod|Protocol)\b', code)),
            'enum': len(re.findall(r'\bEnum\b', code)),
            'dataclass': len(re.findall(r'@dataclass\b', code)),
        }

        # Cada tipo de padrão contribui
        for pattern_type, count in patterns.items():
            if pattern_type == 'class':
                score += min(20, count * 5)
            elif pattern_type == 'inheritance':
                score += min(20, count * 10)
            else:
                score += min(15, count * 15)

        return min(100, score)

    def _keyword_score(self, code: str) -> float:
        """Calcula score baseado em palavras-chave interessantes."""
        code_lower = code.lower()

        matches = 0
        for keyword in self.INTERESTING_KEYWORDS:
            matches += code_lower.count(keyword)

        # Normalizar: 1 match por 10 linhas = score 100
        line_count = len(code.split('\n'))
        expected = max(1, line_count / 10)
        return min(100, (matches / expected) * 100)

    def _unknown_library_score(self, code: str) -> float:
        """Calcula score baseado em bibliotecas não padrão."""
        # Bibliotecas padrão comuns
        stdlib = {
            'os', 'sys', 'json', 're', 'datetime', 'pathlib', 'typing',
            'collections', 'itertools', 'functools', 'asyncio', 'logging',
            'math', 'random', 'hashlib', 'base64', 'time', 'uuid',
            'enum', 'dataclasses', 'abc', 'contextlib'
        }

        # Extrair imports
        imports = set()
        for match in re.finditer(r'(?:from|import)\s+(\w+)', code):
            imports.add(match.group(1))

        unknown = [imp for imp in imports if imp not in stdlib]
        return min(100, len(unknown) * 20)

    def _documentation_score(self, code: str) -> float:
        """Calcula score baseado em documentação."""
        lines = code.split('\n')
        total_lines = len(lines)

        # Contar linhas de comentário/docstring
        comment_lines = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                comment_lines += 1

        # Ratio de comentário (0-1)
        if total_lines == 0:
            return 0
        comment_ratio = comment_lines / total_lines

        # 20-40% de comentários é ideal
        if 0.2 <= comment_ratio <= 0.4:
            return 100
        elif comment_ratio < 0.2:
            return comment_ratio * 500  # 0-20% -> 0-100
        else:
            return max(0, 100 - (comment_ratio - 0.4) * 200)  # >40% decresce

    def _apply_visit_decay(self, filename: str, base_score: float) -> float:
        """Aplica decaimento baseado em visitas anteriores."""
        # Limpar visitas antigas
        cutoff = datetime.now() - timedelta(hours=self.decay_hours)
        self._visits[filename] = [
            visit for visit in self._visits[filename]
            if visit > cutoff
        ]

        # Atualizar contador
        self._visit_counts[filename] = len(self._visits[filename])

        # Aplicar decaimento
        visit_count = self._visit_counts[filename]
        decay = self.decay_factor ** visit_count

        return base_score * decay

    def mark_visited(self, filename: str):
        """Registra visita a um arquivo."""
        self._visits[filename].append(datetime.now())
        self._visit_counts[filename] += 1
        logger.debug("file_visited", filename=filename, total_visits=self._visit_counts[filename])

    def calculate_directory_curiosity(self, directory: str) -> float:
        """
        Calcula curiosidade agregada de um diretório.

        Args:
            directory: Caminho do diretório

        Returns:
            Score agregado (0-100)
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            return 0.0

        scores = []
        for filepath in dir_path.rglob('*.py'):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    code = f.read()
                score = self.calculate_score(code, str(filepath))
                scores.append(score)
            except Exception:
                continue

        if not scores:
            return 0.0

        # Usar média ponderada (arquivos mais interessantes pesam mais)
        scores.sort(reverse=True)
        weights = [1.0 / (i + 1) for i in range(len(scores))]
        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        return min(100, weighted_sum / sum(weights))

    def rank_directories(self, root: str) -> Dict[str, float]:
        """
        Rankeia subdiretórios por curiosidade.

        Args:
            root: Diretório raiz

        Returns:
            Dict {dirname: score}
        """
        root_path = Path(root)
        scores = {}

        for subdir in root_path.iterdir():
            if subdir.is_dir() and not subdir.name.startswith('.'):
                scores[subdir.name] = self.calculate_directory_curiosity(str(subdir))

        return scores

    def get_top_interesting_files(
        self,
        directory: str,
        limit: int = 10
    ) -> List[tuple[str, float]]:
        """
        Retorna os arquivos mais interessantes de um diretório.

        Args:
            directory: Diretório para escanear
            limit: Máximo de arquivos a retornar

        Returns:
            Lista de (filename, score) ordenada por score
        """
        dir_path = Path(directory)
        file_scores = []

        for filepath in dir_path.rglob('*'):
            if filepath.is_file() and filepath.suffix in {'.py', '.ts', '.js', '.yaml', '.yml', '.json'}:
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        code = f.read()
                    score = self.calculate_score(code, str(filepath))
                    file_scores.append((str(filepath), score))
                except Exception:
                    continue

        file_scores.sort(key=lambda x: x[1], reverse=True)
        return file_scores[:limit]

    def reset_visits(self, filename: Optional[str] = None):
        """
        Reset de visitas.

        Args:
            filename: Arquivo específico ou None para resetar todos
        """
        if filename:
            self._visits.pop(filename, None)
            self._visit_counts.pop(filename, None)
        else:
            self._visits.clear()
            self._visit_counts.clear()
