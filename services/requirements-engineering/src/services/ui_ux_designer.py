"""Serviço para design de UI/UX."""

import json
import re
import uuid
from typing import Any

import structlog
from openai import AsyncOpenAI
from src.config.settings import get_settings
from src.models.ui_ux_design import (
    Breakpoint,
    ColorPalette,
    ComponentProp,
    ComponentType,
    InteractionType,
    LayoutType,
    Screen,
    UIComponent,
    UIDesign,
    UIState,
    UserFlow,
)
from src.models.requirements import RequirementsSet

logger = structlog.get_logger(__name__)

UI_UX_DESIGN_PROMPT = """
Você é um designer de UI/UX especialista. Analise os seguintes requisitos e proponha um design de interface.

**Requisitos:**
{requirements_text}

**Instruções:**
1. Defina uma paleta de cores coerente com o domínio
2. Identifique as telas principais da aplicação
3. Para cada tela, liste os componentes necessários
4. Defina fluxos de utilizador principais
5. Retorne APENAS JSON válido

**Formato JSON:**
{{
  "name": "Nome da Aplicação",
  "description": "Descrição da aplicação",
  "colors": {{
    "primary": "#3b82f6",
    "secondary": "#64748b",
    "accent": "#8b5cf6",
    "background": "#ffffff",
    "surface": "#f8fafc",
    "text": "#1e293b",
    "text_secondary": "#64748b"
  }},
  "typography": {{
    "font_family": "Inter",
    "font_size_base": 16,
    "line_height": 1.5
  }},
  "screens": [
    {{
      "name": "Dashboard",
      "route": "/dashboard",
      "description": "Tela principal do dashboard",
      "layout": "responsive",
      "responsive_breakpoints": {{
        "mobile": "stacked",
        "tablet": "grid",
        "desktop": "sidebar + content"
      }},
      "components": [
        {{
          "name": "StatCard",
          "type": "card",
          "description": "Card com estatísticas",
          "props": [
            {{"name": "title", "type": "string", "required": true}},
            {{"name": "value", "type": "string", "required": true}},
            {{"name": "trend", "type": "string", "required": false}}
          ],
          "states": ["default", "hover"],
          "variants": ["primary", "secondary", "success"]
        }}
      ]
    }}
  ],
  "user_flows": [
    {{
      "name": "Login Flow",
      "description": "Fluxo de autenticação",
      "entry_point": "/login",
      "exit_point": "/dashboard",
      "screens": ["/login", "/dashboard"],
      "interactions": ["click", "submit"]
    }}
  ]
}}
"""


class UIUXDesigner:
    """Serviço para design de UI/UX usando LLM."""

    def __init__(self, llm_client: AsyncOpenAI | None = None):
        """Inicializa o UIUXDesigner.

        Args:
            llm_client: Cliente OpenAI (opcional, cria padrão se não fornecido)
        """
        settings = get_settings()
        self._llm_client = llm_client or AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.llm_model
        self._logger = logger

    async def design_from_requirements(
        self,
        requirements_set: RequirementsSet,
    ) -> UIDesign:
        """Desenha uma UI/UX a partir de requisitos.

        Args:
            requirements_set: Conjunto de requisitos

        Returns:
            UIDesign com cores, telas, componentes e fluxos
        """
        self._logger.info(
            "designing_ui_ux",
            requirements_set_id=requirements_set.id,
            total_requirements=len(requirements_set.requirements),
        )

        # Preparar texto dos requisitos
        requirements_text = "\n".join(
            [
                f"- {r.title}: {r.description[:200]}..."
                for r in requirements_set.requirements[:10]
            ]
        )

        prompt = UI_UX_DESIGN_PROMPT.format(requirements_text=requirements_text)

        try:
            response = await self._llm_client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": "Você é um designer de UI/UX especialista em interfaces modernas e acessíveis.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=3000,
            )

            content = response.choices[0].message.content

            # Extrair JSON da resposta
            json_match = self._extract_json(content)
            design_data = json.loads(json_match) if json_match else json.loads(content)

            # Criar UIDesign
            colors = ColorPalette(**design_data.get("colors", {}))
            typography_data = design_data.get("typography", {})

            design = UIDesign(
                id=f"UI-{uuid.uuid4().hex[:8].upper()}",
                name=design_data.get("name", "UI Design"),
                description=design_data.get("description"),
                cognitive_plan_id=requirements_set.cognitive_plan_id,
                requirements_set_id=requirements_set.id,
                colors=colors,
                typography=typography_data,
            )

            # Processar telas
            for screen_data in design_data.get("screens", []):
                screen = self._create_screen(screen_data)
                design.add_screen(screen)

            # Processar fluxos de utilizador
            for flow_data in design_data.get("user_flows", []):
                flow = self._create_user_flow(flow_data)
                design.add_user_flow(flow)

            self._logger.info(
                "ui_ux_designed",
                design_id=design.id,
                screens_count=len(design.screens),
                flows_count=len(design.user_flows),
            )

            return design

        except Exception:
            self._logger.exception("failed_to_design_ui_ux")
            raise

    def _create_screen(self, screen_data: dict[str, Any]) -> Screen:
        """Cria uma Screen a partir de dados JSON.

        Args:
            screen_data: Dados da tela

        Returns:
            Screen populada
        """
        screen_id = f"SC-{uuid.uuid4().hex[:6].upper()}"

        # Processar componentes
        components = []
        for comp_data in screen_data.get("components", []):
            component = self._create_component(comp_data)
            components.append(component)

        return Screen(
            id=screen_id,
            name=screen_data.get("name", ""),
            route=screen_data.get("route", "/"),
            description=screen_data.get("description"),
            components=components,
            layout=self._parse_layout_type(screen_data.get("layout", "responsive")),
            responsive_breakpoints=screen_data.get("responsive_breakpoints", {}),
        )

    def _create_component(self, comp_data: dict[str, Any]) -> UIComponent:
        """Cria um UIComponent a partir de dados JSON.

        Args:
            comp_data: Dados do componente

        Returns:
            UIComponent populado
        """
        comp_id = f"CP-{uuid.uuid4().hex[:6].upper()}"

        # Processar props
        props = []
        for prop_data in comp_data.get("props", []):
            prop = ComponentProp(
                name=prop_data.get("name", ""),
                prop_type=prop_data.get("type", "string"),
                required=prop_data.get("required", False),
                default_value=prop_data.get("default_value"),
                description=prop_data.get("description"),
            )
            props.append(prop)

        # Processar estados
        states = []
        for state in comp_data.get("states", ["default"]):
            try:
                states.append(UIState[state.upper()])
            except KeyError:
                states.append(UIState.DEFAULT)

        return UIComponent(
            id=comp_id,
            name=comp_data.get("name", ""),
            component_type=self._parse_component_type(comp_data.get("type", "button")),
            description=comp_data.get("description"),
            props=props,
            states=states,
            variants=comp_data.get("variants", []),
            accessibility_label=comp_data.get("accessibility_label"),
        )

    def _create_user_flow(self, flow_data: dict[str, Any]) -> UserFlow:
        """Cria um UserFlow a partir de dados JSON.

        Args:
            flow_data: Dados do fluxo

        Returns:
            UserFlow populado
        """
        flow_id = f"UF-{uuid.uuid4().hex[:6].upper()}"

        # Processar interações
        interactions = []
        for interaction in flow_data.get("interactions", []):
            try:
                interactions.append(InteractionType[interaction.upper()])
            except KeyError:
                pass

        return UserFlow(
            id=flow_id,
            name=flow_data.get("name", ""),
            description=flow_data.get("description"),
            entry_point=flow_data.get("entry_point", "/"),
            exit_point=flow_data.get("exit_point", "/"),
            screens=flow_data.get("screens", []),
            interactions=interactions,
        )

    def _parse_layout_type(self, value: str) -> LayoutType:
        """Converte string para LayoutType."""
        try:
            return LayoutType[value.upper()]
        except KeyError:
            return LayoutType.RESPONSIVE

    def _parse_component_type(self, value: str) -> ComponentType:
        """Converte string para ComponentType."""
        mapping = {
            "button": ComponentType.BUTTON,
            "input": ComponentType.INPUT,
            "select": ComponentType.SELECT,
            "checkbox": ComponentType.CHECKBOX,
            "radio": ComponentType.RADIO,
            "textarea": ComponentType.TEXTAREA,
            "dropdown": ComponentType.DROPDOWN,
            "modal": ComponentType.MODAL,
            "table": ComponentType.TABLE,
            "card": ComponentType.CARD,
            "form": ComponentType.FORM,
            "navigation": ComponentType.NAVIGATION,
            "sidebar": ComponentType.SIDEBAR,
            "header": ComponentType.HEADER,
            "footer": ComponentType.FOOTER,
            "alert": ComponentType.ALERT,
            "toast": ComponentType.TOAST,
            "progress": ComponentType.PROGRESS,
            "chart": ComponentType.CHART,
            "tabs": ComponentType.TABS,
            "accordion": ComponentType.ACCORDION,
            "pagination": ComponentType.PAGINATION,
        }
        return mapping.get(value.lower(), ComponentType.CARD)

    def _extract_json(self, text: str) -> str | None:
        """Extrai JSON de texto markdown."""
        # Tentar encontrar JSON em blocos markdown
        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            return json_match.group(1)

        # Tentar encontrar JSON sem markdown
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            return json_match.group(0)

        return None
