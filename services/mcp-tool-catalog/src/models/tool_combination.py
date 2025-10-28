"""Pydantic model for Tool Combination used in genetic algorithm."""
import random
from typing import Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from .tool_descriptor import ToolDescriptor
from .tool_selection import SelectionConstraints


class ToolCombination(BaseModel):
    """Tool combination representing an individual in genetic algorithm."""

    combination_id: str = Field(default_factory=lambda: str(uuid4()))
    tools: List[ToolDescriptor]
    fitness_score: float = 0.0
    generation: int = 0
    parent_ids: List[str] = Field(default_factory=list)
    mutation_applied: bool = False
    crossover_applied: bool = False

    def calculate_fitness(self, constraints: SelectionConstraints) -> float:
        """Calculate fitness score based on tools and constraints."""
        if not self.tools:
            return 0.0

        # Calculate average reputation
        avg_reputation = sum(t.reputation_score for t in self.tools) / len(self.tools)

        # Calculate average cost (inverted so lower cost = higher score)
        avg_cost = sum(t.cost_score for t in self.tools) / len(self.tools)

        # Calculate category coverage (diversity bonus)
        unique_categories = len(set(t.category for t in self.tools))
        category_coverage = unique_categories / 6.0  # 6 total categories

        # Calculate normalized execution time
        total_time = sum(t.average_execution_time_ms for t in self.tools)
        max_allowed_time = constraints.max_execution_time_ms or 300000  # 5 min default
        normalized_time = min(total_time / max_allowed_time, 1.0)

        # Fitness function: weighted combination
        fitness = (
            avg_reputation * 0.4  # 40% reputation
            + (1.0 - avg_cost) * 0.3  # 30% cost (inverted)
            + category_coverage * 0.2  # 20% diversity
            + (1.0 - normalized_time) * 0.1  # 10% speed
        )

        # Apply penalties for constraint violations
        if constraints.max_cost_score and avg_cost > constraints.max_cost_score:
            fitness *= 0.5  # 50% penalty

        if constraints.min_reputation_score and avg_reputation < constraints.min_reputation_score:
            fitness *= 0.5  # 50% penalty

        self.fitness_score = max(0.0, min(fitness, 1.0))
        return self.fitness_score

    def mutate(self, mutation_rate: float, available_tools: List[ToolDescriptor]) -> "ToolCombination":
        """Apply mutation by randomly replacing a tool."""
        if random.random() > mutation_rate or not self.tools:
            return self

        # Select random tool to replace
        idx = random.randint(0, len(self.tools) - 1)
        old_tool = self.tools[idx]

        # Find alternative tools in same category
        alternatives = [t for t in available_tools if t.category == old_tool.category and t.tool_id != old_tool.tool_id]

        if alternatives:
            self.tools[idx] = random.choice(alternatives)
            self.mutation_applied = True

        return self

    def crossover(self, other: "ToolCombination") -> "ToolCombination":
        """Perform single-point crossover with another combination."""
        if not self.tools or not other.tools:
            return self

        # Find compatible crossover point (ensure no duplicate categories)
        min_length = min(len(self.tools), len(other.tools))
        if min_length < 2:
            return self

        crossover_point = random.randint(1, min_length - 1)

        # Create new combination
        new_tools = self.tools[:crossover_point] + other.tools[crossover_point:]

        # Remove duplicates (keep first occurrence)
        seen_categories = set()
        unique_tools = []
        for tool in new_tools:
            if tool.category not in seen_categories:
                unique_tools.append(tool)
                seen_categories.add(tool.category)

        return ToolCombination(
            tools=unique_tools,
            generation=max(self.generation, other.generation) + 1,
            parent_ids=[self.combination_id, other.combination_id],
            crossover_applied=True,
        )

    def validate_constraints(self, constraints: SelectionConstraints) -> bool:
        """Validate if combination meets all constraints."""
        if not self.tools:
            return False

        total_time = sum(t.average_execution_time_ms for t in self.tools)
        avg_cost = sum(t.cost_score for t in self.tools) / len(self.tools)
        avg_reputation = sum(t.reputation_score for t in self.tools) / len(self.tools)

        if constraints.max_execution_time_ms and total_time > constraints.max_execution_time_ms:
            return False

        if constraints.max_cost_score and avg_cost > constraints.max_cost_score:
            return False

        if constraints.min_reputation_score and avg_reputation < constraints.min_reputation_score:
            return False

        return True

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "combination_id": self.combination_id,
            "tools": [t.to_dict() for t in self.tools],
            "fitness_score": self.fitness_score,
            "generation": self.generation,
            "parent_ids": self.parent_ids,
            "mutation_applied": self.mutation_applied,
            "crossover_applied": self.crossover_applied,
        }

    class Config:
        """Pydantic configuration."""

        arbitrary_types_allowed = True
