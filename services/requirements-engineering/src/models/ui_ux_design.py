"""Modelos para design de UI/UX."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ComponentType(str, Enum):
    """Tipos de componentes UI."""

    BUTTON = "button"
    INPUT = "input"
    SELECT = "select"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    TEXTAREA = "textarea"
    DROPDOWN = "dropdown"
    MODAL = "modal"
    TABLE = "table"
    CARD = "card"
    FORM = "form"
    NAVIGATION = "navigation"
    SIDEBAR = "sidebar"
    HEADER = "header"
    FOOTER = "footer"
    ALERT = "alert"
    TOAST = "toast"
    PROGRESS = "progress"
    CHART = "chart"
    TABS = "tabs"
    ACCORDION = "accordion"
    PAGINATION = "pagination"


class LayoutType(str, Enum):
    """Tipos de layout."""

    FIXED = "fixed"
    FLUID = "fluid"
    RESPONSIVE = "responsive"
    GRID = "grid"
    FLEXBOX = "flexbox"


class Breakpoint(str, Enum):
    """Breakpoints responsivos."""

    XS = "xs"  # < 576px
    SM = "sm"  # >= 576px
    MD = "md"  # >= 768px
    LG = "lg"  # >= 992px
    XL = "xl"  # >= 1200px
    XXL = "xxl"  # >= 1400px


class InteractionType(str, Enum):
    """Tipos de interação."""

    CLICK = "click"
    HOVER = "hover"
    FOCUS = "focus"
    SUBMIT = "submit"
    DRAG = "drag"
    DROP = "drop"
    SCROLL = "scroll"
    SWIPE = "swipe"
    PINCH = "pinch"


class UIState(str, Enum):
    """Estados de componentes UI."""

    DEFAULT = "default"
    HOVER = "hover"
    ACTIVE = "active"
    FOCUS = "focus"
    DISABLED = "disabled"
    ERROR = "error"
    SUCCESS = "success"
    WARNING = "warning"
    LOADING = "loading"


class ColorPalette(BaseModel):
    """Paleta de cores."""

    primary: str = Field(..., description="Cor primária (hex)")
    secondary: str = Field(..., description="Cor secundária (hex)")
    accent: str = Field(..., description="Cor de destaque (hex)")
    success: str = Field(default="#10b981", description="Cor de sucesso (hex)")
    warning: str = Field(default="#f59e0b", description="Cor de aviso (hex)")
    error: str = Field(default="#ef4444", description="Cor de erro (hex)")
    info: str = Field(default="#3b82f6", description="Cor de informação (hex)")
    background: str = Field(..., description="Cor de fundo (hex)")
    surface: str = Field(..., description="Cor de superfície (hex)")
    text: str = Field(..., description="Cor de texto principal (hex)")
    text_secondary: str = Field(..., description="Cor de texto secundário (hex)")


class Typography(BaseModel):
    """Configuração de tipografia."""

    font_family: str = Field(default="Inter", description="Família de fontes")
    font_size_base: int = Field(default=16, description="Tamanho base em px")
    line_height: float = Field(default=1.5, description="Altura de linha")
    letter_spacing: float = Field(default=0, description="Espaçamento entre letras")
    heading_sizes: dict[str, int] = Field(
        default_factory=lambda: {"h1": 32, "h2": 28, "h3": 24, "h4": 20, "h5": 16, "h6": 14},
        description="Tamanhos de headings",
    )


class Spacing(BaseModel):
    """Configuração de espaçamento."""

    unit: str = Field(default="px", description="Unidade de medida")
    scale: list[int] = Field(
        default_factory=lambda: [0, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80],
        description="Escala de espaçamentos",
    )


class ComponentProp(BaseModel):
    """Propriedade de componente."""

    name: str = Field(..., description="Nome da propriedade")
    prop_type: str = Field(..., description="Tipo da propriedade")
    required: bool = Field(default=False, description="É obrigatória")
    default_value: Any = Field(default=None, description="Valor padrão")
    description: str | None = Field(default=None, description="Descrição")


class UIComponent(BaseModel):
    """Componente UI."""

    id: str = Field(..., description="ID único")
    name: str = Field(..., description="Nome do componente")
    component_type: ComponentType = Field(..., description="Tipo do componente")
    description: str | None = Field(default=None, description="Descrição")
    props: list[ComponentProp] = Field(default_factory=list, description="Propriedades")
    states: list[UIState] = Field(default_factory=lambda: [UIState.DEFAULT], description="Estados")
    variants: list[str] = Field(
        default_factory=list, description="Variantes (ex: primary, secondary)"
    )
    accessibility_label: str | None = Field(default=None, description="Label de acessibilidade")


class Screen(BaseModel):
    """Tela/View da aplicação."""

    id: str = Field(..., description="ID único")
    name: str = Field(..., description="Nome da tela")
    route: str = Field(..., description="Rota URL")
    description: str | None = Field(default=None, description="Descrição")
    components: list[UIComponent] = Field(default_factory=list, description="Componentes")
    layout: LayoutType = Field(default=LayoutType.RESPONSIVE, description="Tipo de layout")
    responsive_breakpoints: dict[str, str] = Field(
        default_factory=dict, description="Breakpoints responsivos"
    )


class UserFlow(BaseModel):
    """Fluxo de utilizador."""

    id: str = Field(..., description="ID único")
    name: str = Field(..., description="Nome do fluxo")
    description: str | None = Field(default=None, description="Descrição")
    entry_point: str = Field(..., description="Ponto de entrada (route)")
    exit_point: str = Field(..., description="Ponto de saída (route)")
    screens: list[str] = Field(default_factory=list, description="Screens envolvidas")
    interactions: list[InteractionType] = Field(default_factory=list, description="Interações")


class UIDesign(BaseModel):
    """Design completo de UI/UX."""

    id: str = Field(..., description="ID único")
    name: str = Field(..., description="Nome do design")
    description: str | None = Field(default=None, description="Descrição")
    cognitive_plan_id: str | None = Field(default=None, description="ID do plano cognitivo")
    requirements_set_id: str | None = Field(
        default=None, description="ID do conjunto de requisitos"
    )

    colors: ColorPalette = Field(..., description="Paleta de cores")
    typography: Typography = Field(default_factory=Typography, description="Tipografia")
    spacing: Spacing = Field(default_factory=Spacing, description="Espaçamento")

    components: list[UIComponent] = Field(default_factory=list, description="Componentes globais")
    screens: list[Screen] = Field(default_factory=list, description="Telas da aplicação")
    user_flows: list[UserFlow] = Field(default_factory=list, description="Fluxos de utilizador")

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Data de criação"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Data de atualização"
    )

    def add_screen(self, screen: Screen) -> None:
        """Adiciona uma tela ao design."""
        self.screens.append(screen)
        self.updated_at = datetime.now(timezone.utc)

    def add_user_flow(self, flow: UserFlow) -> None:
        """Adiciona um fluxo de utilizador."""
        self.user_flows.append(flow)
        self.updated_at = datetime.now(timezone.utc)

    def get_screen_by_route(self, route: str) -> Screen | None:
        """Retorna tela por rota."""
        for screen in self.screens:
            if screen.route == route:
                return screen
        return None
