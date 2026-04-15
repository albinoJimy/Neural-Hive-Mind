"""C4 Diagram generator for architecture."""

from typing import List
from src.models.architecture import Component


class C4DiagramGenerator:
    """Gera diagramas C4."""

    @staticmethod
    def generate_context(
        project_name: str,
        system_description: str,
        actors: List[str],
        external_systems: List[str]
    ) -> str:
        """Gera diagrama C4 Context."""

        actors_block = "\n".join(
            f'    Person({actor.lower()}, "{actor}", "User")'
            for actor in actors
        )

        system_block = f"""
    System(system, "{project_name}", "{system_description}")
"""

        external_block = "\n".join(
            f"""    System_Ext({ext.lower()}, "{ext}", "External System")"""
            for ext in external_systems
        )

        relationships = "\n".join([
            "    Rel(user, system, \"Usa\")",
            "    Rel(system, external1, \"Integra via API\")"
        ])

        return f"""C4Context
    title {project_name} - Context Diagram

{actors_block}
{system_block}
{external_block}

{relationships}
"""

    @staticmethod
    def generate_container(
        project_name: str,
        containers: List[Component]
    ) -> str:
        """Gera diagrama C4 Container."""

        containers_block = ""
        for container in containers:
            containers_block += f"""
    ContainerDb({container.name}_db, "{container.name} Database", "{container.stack}", "Storage")
Container({container.name}, "{container.name}", "{container.stack}", "Service Component")
    Rel({container.name}, {container.name}_db, "Lê/Escreve", "JDBC/ORM")
"""

        return f"""C4Container
    title {project_name} - Container Diagram

{containers_block}
"""

    @staticmethod
    def generate_component(
        component_name: str,
        component_description: str,
        subcomponents: List[str]
    ) -> str:
        """Gera diagrama C4 Component."""

        components_block = ""
        for sub in subcomponents:
            components_block += f"""
    Component({sub.lower()}, "{sub}", "Module", "Functionality")
"""

        return f"""C4Component
    title {component_name} - Component Diagram

Component(controller, "Controller", "REST API", "Exposes endpoints")
Component(service, "Service", "Business Logic", "Processes requests")
Component(repository, "Repository", "Data Access", "Query database")

{components_block}

Rel(controller, service, "Chama")
Rel(service, repository, "Usa")
"""
