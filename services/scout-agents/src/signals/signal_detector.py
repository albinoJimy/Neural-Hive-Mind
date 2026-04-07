"""
SignalDetector - Detecta sinais de mudança e interesse em código.

Responsável por:
- Detectar mudanças em arquivos (modificação, criação, deleção)
- Identificar sinais de "atividade suspeita"
- Calcular intensidade de sinais
- Agregar sinais por timeframe
"""

import hashlib
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog

logger = structlog.get_logger()


class FileSignal:
    """Representa um sinal detectado em um arquivo."""

    def __init__(
        self, filepath: str, signal_type: str, intensity: float, metadata: Optional[Dict] = None
    ):
        self.filepath = filepath
        self.signal_type = signal_type  # 'created', 'modified', 'deleted', 'high_activity'
        self.intensity = intensity  # 0.0 a 1.0
        self.metadata = metadata or {}
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict:
        """Converte para dicionário."""
        return {
            "filepath": self.filepath,
            "signal_type": self.signal_type,
            "intensity": self.intensity,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


class SignalDetector:
    """Detecta sinais de mudança e interesse em código."""

    def __init__(self, window_minutes: int = 60):
        """
        Inicializa SignalDetector.

        Args:
            window_minutes: Janela de tempo para agregação de sinais
        """
        self.window_minutes = window_minutes

        # Rastreamento de estado
        self._file_hashes: Dict[str, str] = {}
        self._file_timestamps: Dict[str, datetime] = {}

        # Sinais detectados
        self._signals: List[FileSignal] = []

        # Contagem de atividade por arquivo
        self._activity_counts: Dict[str, int] = defaultdict(int)

    def scan_directory(
        self, directory: str, extensions: Optional[Set[str]] = None
    ) -> List[FileSignal]:
        """
        Escaneia diretório em busca de sinais.

        Args:
            directory: Diretório para escanear
            extensions: Extensões para considerar (default: todas)

        Returns:
            Lista de sinais detectados
        """
        new_signals = []
        dir_path = Path(directory)

        if not dir_path.exists():
            logger.warning("directory_not_found", directory=directory)
            return new_signals

        extensions = extensions or {".py", ".ts", ".js", ".yaml", ".yml", ".json"}

        # Arquivos atuais
        current_files = set()

        for filepath in dir_path.rglob("*"):
            if not filepath.is_file():
                continue

            if extensions and filepath.suffix not in extensions:
                continue

            full_path = str(filepath)
            current_files.add(full_path)

            # Detectar mudança
            signal = self._check_file(full_path)
            if signal:
                new_signals.append(signal)
                self._signals.append(signal)
                self._activity_counts[full_path] += 1

        # Detectar arquivos deletados
        deleted_files = set(self._file_hashes.keys()) - current_files
        for deleted in deleted_files:
            signal = FileSignal(
                deleted, "deleted", 0.5, {"previous_hash": self._file_hashes[deleted]}
            )
            new_signals.append(signal)
            self._signals.append(signal)
            del self._file_hashes[deleted]
            del self._file_timestamps[deleted]

        return new_signals

    def _check_file(self, filepath: str) -> Optional[FileSignal]:
        """Verifica arquivo e detecta sinais."""
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Calcular hash do conteúdo
            file_hash = hashlib.md5(content.encode()).hexdigest()
            mtime = datetime.fromtimestamp(Path(filepath).stat().st_mtime)

            # Arquivo novo
            if filepath not in self._file_hashes:
                self._file_hashes[filepath] = file_hash
                self._file_timestamps[filepath] = mtime
                return FileSignal(filepath, "created", self._calculate_creation_intensity(content))

            # Arquivo modificado
            if file_hash != self._file_hashes[filepath]:
                old_hash = self._file_hashes[filepath]
                self._file_hashes[filepath] = file_hash
                self._file_timestamps[filepath] = mtime

                # Calcular intensidade da mudança
                intensity = self._calculate_modification_intensity(content, old_hash)

                return FileSignal(
                    filepath, "modified", intensity, {"old_hash": old_hash, "new_hash": file_hash}
                )

            return None

        except Exception as e:
            logger.warning("file_check_failed", filepath=filepath, error=str(e))
            return None

    def _calculate_creation_intensity(self, content: str) -> float:
        """Calcula intensidade de criação baseada no conteúdo."""
        # Base intensity
        intensity = 0.3

        # Tamanho do arquivo
        size_factor = min(len(content) / 10000, 1.0) * 0.2
        intensity += size_factor

        # Complexidade (número de linhas)
        lines = len(content.split("\n"))
        complexity_factor = min(lines / 500, 1.0) * 0.2
        intensity += complexity_factor

        # Palavras-chave interessantes
        interesting = ["class", "def", "function", "interface", "type", "import", "require"]
        keyword_count = sum(content.count(kw) for kw in interesting)
        keyword_factor = min(keyword_count / 50, 1.0) * 0.3
        intensity += keyword_factor

        return min(1.0, intensity)

    def _calculate_modification_intensity(self, content: str, old_hash: str) -> float:
        """Calcula intensidade de modificação."""
        # Base intensity
        intensity = 0.2

        # Diferença de tamanho
        size_change = abs(len(content) - len(old_hash)) / max(len(old_hash), 1)
        size_factor = min(size_change, 1.0) * 0.3
        intensity += size_factor

        # Número de linhas modificadas
        lines = len(content.split("\n"))
        line_factor = min(lines / 200, 1.0) * 0.2
        intensity += line_factor

        # Contagem de atividade anterior (arquivos com muitas mudanças são mais interessantes)
        activity_factor = min(self._activity_counts.get(old_hash, 0) / 10, 1.0) * 0.3
        intensity += activity_factor

        return min(1.0, intensity)

    def get_high_activity_files(self, threshold: int = 5) -> List[Tuple[str, int]]:
        """
        Retorna arquivos com alta atividade.

        Args:
            threshold: Número mínimo de mudanças

        Returns:
            Lista de (filepath, activity_count)
        """
        high_activity = [
            (fp, count) for fp, count in self._activity_counts.items() if count >= threshold
        ]
        return sorted(high_activity, key=lambda x: x[1], reverse=True)

    def get_signals_in_window(self, minutes: Optional[int] = None) -> List[FileSignal]:
        """
        Retorna sinais dentro de uma janela de tempo.

        Args:
            minutes: Minutos a olhar para trás (default: self.window_minutes)

        Returns:
            Lista de sinais na janela
        """
        window = minutes or self.window_minutes
        cutoff = datetime.now() - timedelta(minutes=window)

        return [signal for signal in self._signals if signal.timestamp >= cutoff]

    def get_signal_summary(self, minutes: Optional[int] = None) -> Dict[str, Any]:
        """
        Retorna resumo de sinais.

        Args:
            minutes: Minutos a olhar para trás

        Returns:
            Dict com contagem e agregação
        """
        signals = self.get_signals_in_window(minutes)

        summary = {
            "total_signals": len(signals),
            "by_type": defaultdict(int),
            "by_file": defaultdict(int),
            "total_intensity": 0.0,
            "signals": [],
        }

        for signal in signals:
            summary["by_type"][signal.signal_type] += 1
            summary["by_file"][signal.filepath] += 1
            summary["total_intensity"] += signal.intensity
            summary["signals"].append(signal.to_dict())

        # Converter defaultdict para dict
        summary["by_type"] = dict(summary["by_type"])
        summary["by_file"] = dict(summary["by_file"])
        summary["average_intensity"] = summary["total_intensity"] / len(signals) if signals else 0.0

        return summary

    def get_hotspots(self, limit: int = 10) -> List[Dict]:
        """
        Retorna os "hotspots" - arquivos com mais atividade recente.

        Args:
            limit: Máximo de hotspots a retornar

        Returns:
            Lista de dicts com filepath, activity_count, intensity
        """
        window = self.window_minutes
        cutoff = datetime.now() - timedelta(minutes=window)

        # Contar sinais recentes por arquivo
        recent_activity = defaultdict(lambda: {"count": 0, "intensity": 0.0})

        for signal in self._signals:
            if signal.timestamp >= cutoff:
                recent_activity[signal.filepath]["count"] += 1
                recent_activity[signal.filepath]["intensity"] += signal.intensity

        # Converter para lista e ordenar
        hotspots = [
            {
                "filepath": fp,
                "activity_count": data["count"],
                "total_intensity": data["intensity"],
                "average_intensity": data["intensity"] / data["count"] if data["count"] > 0 else 0,
            }
            for fp, data in recent_activity.items()
        ]

        hotspots.sort(key=lambda x: x["activity_count"], reverse=True)
        return hotspots[:limit]

    def detect_burst_activity(self, threshold: float = 3.0) -> List[str]:
        """
        Detecta "burst" de atividade - mudanças rápidas em um arquivo.

        Args:
            threshold: Múltiplo da média de atividade para considerar burst

        Returns:
            Lista de filepaths com burst activity
        """
        if not self._signals:
            return []

        # Calcular média de atividade
        window = self.window_minutes
        cutoff = datetime.now() - timedelta(minutes=window)
        recent_signals = [s for s in self._signals if s.timestamp >= cutoff]

        if not recent_signals:
            return []

        # Contar sinais por arquivo
        file_counts = defaultdict(int)
        for signal in recent_signals:
            file_counts[signal.filepath] += 1

        # Calcular média
        avg_activity = sum(file_counts.values()) / len(file_counts)

        # Arquivos acima do threshold
        burst_files = [fp for fp, count in file_counts.items() if count > avg_activity * threshold]

        return burst_files

    def reset(self):
        """Reset todo o estado do detector."""
        self._file_hashes.clear()
        self._file_timestamps.clear()
        self._signals.clear()
        self._activity_counts.clear()
