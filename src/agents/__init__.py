from .base_agent import BaseAgent
from .orchestrator import OrchestratorAgent
from .game_agents import ContentAgent, NarrativeAgent, AnalyticsAgent
from .dynamic_agent import DynamicAgent
from .research_agents import DeepResearchOrchestrator
from .edu_agents import (
    EducationalAgent,
    create_all_edu_agents,
    ALL_EDU_AGENT_CLASSES,
    POLYGLOT_CONFIGS,
)
from .specialist_agents import (
    SpecialistAgent,
    SystemsEngineerAgent,
    GameDevAgent,
    LiteraryAgent,
    ComicAgent,
    BoardGameAgent,
    WebDevAgent,
    create_all_specialist_agents,
    ALL_SPECIALIST_AGENT_CLASSES,
)
from .novelty_search import (
    GridArchive,
    GaussianEmitter,
    MapElitesScheduler,
    NoveltyEvaluator,
)

from .youth_agents import (
    YouthAgent,
    SkarbnikAgent,
    BioOptymizer,
    StylistaCyfrowy,
    StratEsportowy,
    AgorAgent,
    DuchowyKompas,
    KustoszHypeu,
    RegulatorEnergii,
    ArchiwistaMemo,
    OrgImprez,
    CoachRelacjiAI,
    create_all_youth_agents,
    ALL_YOUTH_AGENT_CLASSES,
)
from .agent_registry import (
    AgentRegistryEntry,
    AgentRegistry,
    DynamicRegistryAgent,
    get_default_registry,
)
from .cross_agent_protocol import (
    CrossAgentBus,
    SafetyCoordinator,
    get_default_bus,
)
from .exotic_agents import (
    ExoticAgent,
    XenobotAgent,
    DishBrainAgent,
    HybrotAgent,
    Terra0Agent,
    PlantoidAgent,
    TruthTerminalAgent,
    MrGoxxAgent,
    ChaosGPTAgent,
    TayAgent,
    AARONAgent,
    PaintingFoolAgent,
    BottoAgent,
    PolyworldAgent,
    LeniaAgent,
    AIStevePoliticianAgent,
    AliceBobAgent,
    ChemCrowAgent,
    GeneferAgent,
    create_all_exotic_agents,
    ALL_EXOTIC_AGENT_CLASSES,
)

__all__ = [
    # Core
    "BaseAgent",
    "OrchestratorAgent",
    # Game
    "ContentAgent",
    "NarrativeAgent",
    "AnalyticsAgent",
    "DynamicAgent",
    # Research
    "DeepResearchOrchestrator",
    # Education (AAK – Cyfrowa Agora Wiedzy)
    "EducationalAgent",
    "create_all_edu_agents",
    "ALL_EDU_AGENT_CLASSES",
    "POLYGLOT_CONFIGS",
    # Specialist (Inżynieria / GameDev / Pisarstwo / Komiks / Planszowe / Web)
    "SpecialistAgent",
    "SystemsEngineerAgent",
    "GameDevAgent",
    "LiteraryAgent",
    "ComicAgent",
    "BoardGameAgent",
    "WebDevAgent",
    "create_all_specialist_agents",
    "ALL_SPECIALIST_AGENT_CLASSES",
    # MAP-Elites / Novelty Search
    "GridArchive",
    "GaussianEmitter",
    "MapElitesScheduler",
    "NoveltyEvaluator",
    # Youth Alpha/Z agents
    "YouthAgent",
    "SkarbnikAgent",
    "BioOptymizer",
    "StylistaCyfrowy",
    "StratEsportowy",
    "AgorAgent",
    "DuchowyKompas",
    "KustoszHypeu",
    "RegulatorEnergii",
    "ArchiwistaMemo",
    "OrgImprez",
    "CoachRelacjiAI",
    "create_all_youth_agents",
    "ALL_YOUTH_AGENT_CLASSES",
    # 6666-Agent Registry
    "AgentRegistryEntry",
    "AgentRegistry",
    "DynamicRegistryAgent",
    "get_default_registry",
    # Cross-Agent Protocol
    "CrossAgentBus",
    "SafetyCoordinator",
    "get_default_bus",
    # Exotic / Niche Agents (Kompendium Anomalii Agentowych)
    "ExoticAgent",
    "XenobotAgent",
    "DishBrainAgent",
    "HybrotAgent",
    "Terra0Agent",
    "PlantoidAgent",
    "TruthTerminalAgent",
    "MrGoxxAgent",
    "ChaosGPTAgent",
    "TayAgent",
    "AARONAgent",
    "PaintingFoolAgent",
    "BottoAgent",
    "PolyworldAgent",
    "LeniaAgent",
    "AIStevePoliticianAgent",
    "AliceBobAgent",
    "ChemCrowAgent",
    "GeneferAgent",
    "create_all_exotic_agents",
    "ALL_EXOTIC_AGENT_CLASSES",
]
