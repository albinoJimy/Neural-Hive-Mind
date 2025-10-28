"""Genetic algorithm-based tool selection service."""
import asyncio
import random
import time
from typing import Dict, List, Optional, Tuple

import structlog
from deap import base, creator, tools

from src.config.settings import Settings
from src.models.tool_combination import ToolCombination
from src.models.tool_descriptor import ToolCategory, ToolDescriptor
from src.models.tool_selection import (
    SelectedTool,
    SelectionMethod,
    ToolSelectionRequest,
    ToolSelectionResponse,
)
from src.services.tool_registry import ToolRegistry

logger = structlog.get_logger()


class GeneticToolSelector:
    """Intelligent tool selection using genetic algorithm."""

    def __init__(self, tool_registry: ToolRegistry, settings: Settings, metrics=None):
        """Initialize genetic tool selector."""
        self.tool_registry = tool_registry
        self.settings = settings
        self.metrics = metrics
        self._setup_deap()

    def _setup_deap(self):
        """Setup DEAP genetic algorithm framework."""
        # Create fitness and individual classes
        if not hasattr(creator, "FitnessMax"):
            creator.create("FitnessMax", base.Fitness, weights=(1.0,))  # Maximize fitness
        if not hasattr(creator, "Individual"):
            creator.create("Individual", list, fitness=creator.FitnessMax)

        self.toolbox = base.Toolbox()

    async def select_tools(self, request: ToolSelectionRequest) -> ToolSelectionResponse:
        """Select optimal tool combination using genetic algorithm.

        Args:
            request: Tool selection request

        Returns:
            Tool selection response with selected tools
        """
        start_time = time.time()

        # Check cache first
        request_hash = request.calculate_hash()
        cached_response = await self._check_cache(request_hash)
        if cached_response:
            logger.info("selection_served_from_cache", request_id=request.request_id)
            return cached_response

        # Get available tools for required categories
        available_tools = await self._get_available_tools(request)

        if not available_tools:
            return self._create_fallback_response(request, "No tools available for required categories")

        # Run genetic algorithm with timeout
        try:
            ga_start = time.time()
            timeout_seconds = self.settings.GA_TIMEOUT_SECONDS if hasattr(self.settings, 'GA_TIMEOUT_SECONDS') else 30

            best_combination, generations, converged = await asyncio.wait_for(
                self._run_genetic_algorithm(available_tools, request),
                timeout=timeout_seconds
            )

            ga_duration = time.time() - ga_start
            duration_ms = int((time.time() - start_time) * 1000)

            # Record GA metrics
            if self.metrics:
                self.metrics.record_genetic_algorithm(
                    converged=converged,
                    timeout=False,
                    duration=ga_duration,
                    generations=generations
                )

            # Create response
            response = self._create_response_from_combination(
                request, best_combination, SelectionMethod.GENETIC_ALGORITHM, generations, duration_ms, converged
            )

            # Cache result
            await self._cache_response(request_hash, response)

            # Record selection metrics
            if self.metrics:
                self.metrics.record_selection(
                    method=SelectionMethod.GENETIC_ALGORITHM.value,
                    cached=False,
                    duration=duration_ms / 1000.0,
                    fitness=best_combination.fitness_score
                )

            # Save to history
            await self.tool_registry.mongodb_client.save_selection_history(
                request.to_dict(), response.to_avro()
            )

            logger.info(
                "genetic_selection_completed",
                request_id=request.request_id,
                generations=generations,
                fitness=best_combination.fitness_score,
                duration_ms=duration_ms,
            )

            return response

        except asyncio.TimeoutError:
            ga_duration = time.time() - ga_start if 'ga_start' in locals() else 0
            logger.warning("genetic_algorithm_timeout", request_id=request.request_id, timeout_seconds=timeout_seconds)

            # Record timeout metrics
            if self.metrics:
                self.metrics.record_genetic_algorithm(
                    converged=False,
                    timeout=True,
                    duration=ga_duration,
                    generations=0
                )

            # Fallback to heuristic
            return await self._heuristic_selection(request, available_tools)

        except Exception as e:
            logger.error("genetic_selection_failed", error=str(e), request_id=request.request_id)
            return await self._heuristic_selection(request, available_tools)

    async def _get_available_tools(self, request: ToolSelectionRequest) -> Dict[str, List[ToolDescriptor]]:
        """Get available tools grouped by required categories."""
        tools_by_category = {}

        for category_str in request.required_categories:
            try:
                category = ToolCategory(category_str)
                tools = await self.tool_registry.list_tools_by_category(category)

                # Filter out excluded tools
                if request.excluded_tools:
                    tools = [t for t in tools if t.tool_id not in request.excluded_tools]

                # Filter active tools only
                tools = [t for t in tools if t.metadata.get("active", True) is True]

                if tools:
                    tools_by_category[category_str] = tools

            except ValueError:
                logger.warning("invalid_category", category=category_str)

        return tools_by_category

    async def _run_genetic_algorithm(
        self, available_tools: Dict[str, List[ToolDescriptor]], request: ToolSelectionRequest
    ) -> Tuple[ToolCombination, int, bool]:
        """Run genetic algorithm to find optimal tool combination."""
        # Initialize population
        population = self._create_initial_population(available_tools, request)

        # Evaluate initial fitness
        for individual in population:
            individual.calculate_fitness(request.constraints)

        # Evolution parameters
        n_generations = self.settings.GA_MAX_GENERATIONS
        crossover_prob = self.settings.GA_CROSSOVER_PROB
        mutation_prob = self.settings.GA_MUTATION_PROB

        best_fitness_history = []
        converged = False

        # Evolve population
        for generation in range(n_generations):
            # Selection: Tournament selection
            offspring = tools.selTournament(
                population, len(population), tournsize=self.settings.GA_TOURNAMENT_SIZE
            )
            offspring = list(map(lambda x: ToolCombination(**x.to_dict()), offspring))  # Clone

            # Crossover
            for child1, child2 in zip(offspring[::2], offspring[1::2]):
                if random.random() < crossover_prob:
                    child1.crossover(child2)
                    child1.generation = generation
                    child2.generation = generation

            # Mutation
            for mutant in offspring:
                if random.random() < mutation_prob:
                    all_tools = [t for tools in available_tools.values() for t in tools]
                    mutant.mutate(mutation_prob, all_tools)
                    mutant.generation = generation

            # Evaluate offspring fitness
            for individual in offspring:
                individual.calculate_fitness(request.constraints)

            # Replace population with offspring
            population[:] = offspring

            # Track best fitness
            best_individual = max(population, key=lambda x: x.fitness_score)
            best_fitness_history.append(best_individual.fitness_score)

            # Check convergence
            if len(best_fitness_history) >= 10:
                recent_improvement = best_fitness_history[-1] - best_fitness_history[-10]
                if recent_improvement < self.settings.GA_CONVERGENCE_THRESHOLD:
                    converged = True
                    logger.info("genetic_algorithm_converged", generation=generation)
                    break

        # Return best individual
        best_combination = max(population, key=lambda x: x.fitness_score)
        return best_combination, generation + 1, converged

    def _create_initial_population(
        self, available_tools: Dict[str, List[ToolDescriptor]], request: ToolSelectionRequest
    ) -> List[ToolCombination]:
        """Create initial random population."""
        population = []
        population_size = self.settings.GA_POPULATION_SIZE

        for _ in range(population_size):
            # Randomly select one tool from each required category
            selected_tools = []
            for category, tools in available_tools.items():
                # Prefer preferred_tools if specified
                if request.preferred_tools:
                    preferred = [t for t in tools if t.tool_id in request.preferred_tools]
                    if preferred:
                        selected_tools.append(random.choice(preferred))
                        continue

                selected_tools.append(random.choice(tools))

            combination = ToolCombination(tools=selected_tools, generation=0)
            population.append(combination)

        return population

    def _create_response_from_combination(
        self,
        request: ToolSelectionRequest,
        combination: ToolCombination,
        method: SelectionMethod,
        generations: int,
        duration_ms: int,
        converged: bool,
    ) -> ToolSelectionResponse:
        """Create response from tool combination."""
        selected_tools = []

        for idx, tool in enumerate(combination.tools, start=1):
            selected_tools.append(
                SelectedTool(
                    tool_id=tool.tool_id,
                    tool_name=tool.tool_name,
                    category=tool.category.value,
                    execution_order=idx,
                    fitness_score=tool.calculate_fitness(),
                    reasoning=f"Selected for {tool.category.value} - reputation: {tool.reputation_score:.2f}, cost: {tool.cost_score:.2f}",
                )
            )

        reasoning_summary = (
            f"Genetic algorithm evolved {generations} generations "
            f"to select optimal tool combination. "
            f"Final fitness: {combination.fitness_score:.3f}. "
            f"{'Converged successfully.' if converged else 'Stopped at max generations.'}"
        )

        return ToolSelectionResponse(
            request_id=request.request_id,
            selected_tools=selected_tools,
            total_fitness_score=combination.fitness_score,
            selection_method=method,
            generations_evolved=generations,
            population_size=self.settings.GA_POPULATION_SIZE,
            convergence_time_ms=duration_ms,
            reasoning_summary=reasoning_summary,
            confidence_score=min(combination.fitness_score + 0.1, 1.0),
            cached=False,
        )

    async def _heuristic_selection(
        self, request: ToolSelectionRequest, available_tools: Dict[str, List[ToolDescriptor]]
    ) -> ToolSelectionResponse:
        """Fallback heuristic selection (highest reputation)."""
        selected_tools = []
        idx = 1

        for category, tools in available_tools.items():
            # Sort by reputation and select best
            best_tool = max(tools, key=lambda t: t.reputation_score)

            selected_tools.append(
                SelectedTool(
                    tool_id=best_tool.tool_id,
                    tool_name=best_tool.tool_name,
                    category=best_tool.category.value,
                    execution_order=idx,
                    fitness_score=best_tool.calculate_fitness(),
                    reasoning=f"Heuristic selection - highest reputation: {best_tool.reputation_score:.2f}",
                )
            )
            idx += 1

        avg_fitness = sum(t.fitness_score for t in selected_tools) / len(selected_tools) if selected_tools else 0.0

        return ToolSelectionResponse(
            request_id=request.request_id,
            selected_tools=selected_tools,
            total_fitness_score=avg_fitness,
            selection_method=SelectionMethod.HEURISTIC,
            generations_evolved=0,
            population_size=0,
            convergence_time_ms=0,
            reasoning_summary="Heuristic fallback: selected tools with highest reputation scores.",
            confidence_score=0.7,
            cached=False,
        )

    def _create_fallback_response(self, request: ToolSelectionRequest, reason: str) -> ToolSelectionResponse:
        """Create fallback response when selection fails."""
        return ToolSelectionResponse(
            request_id=request.request_id,
            selected_tools=[],
            total_fitness_score=0.0,
            selection_method=SelectionMethod.FALLBACK,
            generations_evolved=0,
            population_size=0,
            convergence_time_ms=0,
            reasoning_summary=f"Fallback response: {reason}",
            confidence_score=0.0,
            cached=False,
        )

    async def _check_cache(self, request_hash: str) -> Optional[ToolSelectionResponse]:
        """Check if selection result is cached."""
        cached = await self.tool_registry.redis_client.get_cached_selection(request_hash)
        if cached:
            cached["cached"] = True
            response = ToolSelectionResponse(**cached)

            # Record cache hit metrics
            if self.metrics:
                self.metrics.record_selection(
                    method=response.selection_method.value,
                    cached=True,
                    duration=0.001,  # cached response is fast
                    fitness=response.total_fitness_score
                )

            return response
        return None

    async def _cache_response(self, request_hash: str, response: ToolSelectionResponse):
        """Cache selection response."""
        await self.tool_registry.redis_client.cache_selection(request_hash, response)
