"""
Skrypt generujący 6666 unikalnych agentów i zapisujący ich do
data/agent_registry.json.

Każdy agent posiada:
  - agent_id   : unikalny identyfikator (np. "agent_0001")
  - display_name: czytelna nazwa
  - domain     : dziedzina działania
  - role       : rola/typ agenta
  - specialization: specjalizacja
  - mission    : krótki opis misji
  - category   : kategoria taksonomiczna (kompatybilna z ExoticCategory)
  - safety     : poziom bezpieczeństwa (safe / monitored / sandboxed)
  - system_prompt: prompt systemowy

Uruchomienie:
    python scripts/generate_agents.py
"""
from __future__ import annotations

import json
import random
from pathlib import Path

SEED = 42
TARGET = 6666
OUTPUT = Path(__file__).parent.parent / "data" / "agent_registry.json"

# ---------------------------------------------------------------------------
# Słowniki składowych
# ---------------------------------------------------------------------------

DOMAINS = [
    "Medycyna", "Prawo", "Finanse", "Edukacja", "Nauka", "Sztuka", "Muzyka",
    "Sport", "Polityka", "Technologia", "Środowisko", "Rolnictwo", "Turystyka",
    "Architektura", "Filozofia", "Psychologia", "Socjologia", "Historia",
    "Językoznawstwo", "Matematyka", "Fizyka", "Chemia", "Biologia", "Astronomia",
    "Informatyka", "Robotyka", "Cyberbezpieczeństwo", "Kryptografia", "Blockchain",
    "Sztuczna Inteligencja", "Uczenie Maszynowe", "Bioinformatyka", "Genomika",
    "Neurologia", "Psychiatria", "Farmakologia", "Chirurgia", "Dietetyka",
    "Rehabilitacja", "Kardiologia", "Onkologia", "Pediatria", "Geriatria",
    "Stomatologia", "Okulistyka", "Dermatologia", "Endokrynologia", "Immunologia",
    "Epidemiologia", "Weterynaria", "Ogrodnictwo", "Leśnictwo", "Oceanografia",
    "Klimatologia", "Geologia", "Archeologia", "Paleontologia", "Antropologia",
    "Etnografia", "Kulturoznawstwo", "Religioznawstwo", "Teologia", "Etyka",
    "Logika", "Estetyka", "Ontologia", "Epistemologia", "Metafizyka",
    "Ekonomia", "Marketing", "Zarządzanie", "Rachunkowość", "Bankowość",
    "Ubezpieczenia", "Handel", "Logistyka", "Transport", "Energetyka",
    "Górnictwo", "Hutnictwo", "Budownictwo", "Elektrotechnika", "Mechanika",
    "Automatyka", "Lotnictwo", "Astronautyka", "Oceanotechnika", "Inżynieria",
    "Przemysł", "Ekologia", "Ochrona Środowiska", "Recykling", "Urbanistyka",
    "Planowanie Przestrzenne", "Demografia", "Statystyka", "Geopolityka",
    "Dyplomacja", "Bezpieczeństwo", "Obronność", "Wywiad", "Prawo Międzynarodowe",
    "Kryminologia", "Kryminalistyka", "Penologia", "Resocjalizacja", "Mediacja",
    "Literatura", "Teatr", "Film", "Fotografia", "Taniec", "Cyrk", "Komiks",
    "Gry Wideo", "Gry Planszowe", "Esport", "Szachy", "Poker", "Brydż",
]

ROLES = [
    "Analityk", "Asystent", "Audytor", "Badacz", "Coach", "Consul",
    "Detektyw", "Doradca", "Edukator", "Ekspert", "Generał", "Inspektor",
    "Koordynator", "Kurator", "Mediator", "Mentor", "Moderator", "Monitor",
    "Negocjator", "Operator", "Optymalizator", "Planista", "Predyktor",
    "Profiler", "Propagator", "Protokolant", "Rzecznik", "Specjalista",
    "Strateg", "Syntetyzator", "Tłumacz", "Trener", "Validator", "Weryfikator",
    "Wizjoner", "Wykonawca", "Zarządca", "Strażnik", "Odkrywca", "Konstruktor",
]

SPECIALIZATIONS = [
    "Danych", "Ryzyka", "Procesów", "Zasobów", "Relacji", "Wiedzy",
    "Jakości", "Innowacji", "Bezpieczeństwa", "Zgodności", "Wzrostu",
    "Wydajności", "Transformacji", "Diagnostyki", "Syntezy", "Integracji",
    "Automatyzacji", "Predykcji", "Optymalizacji", "Wizualizacji",
    "Komunikacji", "Dokumentacji", "Konfiguracji", "Monitoringu", "Alertów",
    "Raportowania", "Audytu", "Kontroli", "Ewaluacji", "Rekomendacji",
    "Klasyfikacji", "Klasteryzacji", "Segmentacji", "Personalizacji",
    "Adaptacji", "Symulacji", "Testowania", "Walidacji", "Wdrożenia",
    "Migracji", "Archiwizacji", "Odzyskiwania", "Replikacji", "Skalowania",
]

CATEGORIES = [
    "education", "research", "creative", "scientific", "social",
    "blockchain", "alife", "wetware", "specialist", "youth",
]

SAFETY_WEIGHTS = {
    "safe":      0.60,
    "monitored": 0.35,
    "sandboxed": 0.05,
}

MISSION_TEMPLATES = [
    "Wspieranie decyzji w dziedzinie {domain} poprzez analizę {spec}.",
    "Automatyzacja procesów {spec} w kontekście {domain}.",
    "Optymalizacja {spec} dla specjalistów {domain}.",
    "Dostarczanie rekomendacji w obszarze {domain} z fokusem na {spec}.",
    "Monitorowanie i alertowanie w zakresie {domain} – moduł {spec}.",
    "Edukacja i trening w dziedzinie {domain}: aspekt {spec}.",
    "Badanie i eksploracja {spec} w kontekście {domain}.",
    "Integracja wiedzy {domain} z systemami {spec}.",
    "Zapewnienie jakości i zgodności w {domain} – focus {spec}.",
    "Predykcja trendów {spec} w obszarze {domain}.",
]

PROMPT_TEMPLATES = [
    (
        "Jesteś {role} {spec} w dziedzinie {domain}. "
        "Odpowiadasz precyzyjnie, profesjonalnie i na temat. "
        "Twoje odpowiedzi są oparte na aktualnej wiedzy z {domain}."
    ),
    (
        "Jesteś zaawansowanym {role} specjalizującym się w {spec} w kontekście {domain}. "
        "Udzielasz eksperckich porad, analizujesz dane i proponujesz rozwiązania."
    ),
    (
        "Działasz jako {role} ds. {spec} w sektorze {domain}. "
        "Twoja misja to dostarczanie precyzyjnych analiz i rekomendacji."
    ),
    (
        "Jesteś autonomicznym agentem {role} skupionym na {spec} w obszarze {domain}. "
        "Analizujesz, syntezujesz i komunikujesz wyniki w zwięzłej formie."
    ),
]


def _pick_safety(rng: random.Random) -> str:
    choices = list(SAFETY_WEIGHTS.keys())
    weights = list(SAFETY_WEIGHTS.values())
    return rng.choices(choices, weights=weights, k=1)[0]


def generate_agents(n: int = TARGET, seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    agents: list[dict] = []
    used_ids: set[str] = set()

    i = 0
    while len(agents) < n:
        i += 1
        domain = rng.choice(DOMAINS)
        role   = rng.choice(ROLES)
        spec   = rng.choice(SPECIALIZATIONS)
        cat    = rng.choice(CATEGORIES)
        safety = _pick_safety(rng)

        agent_id = f"agent_{len(agents) + 1:04d}"
        assert agent_id not in used_ids
        used_ids.add(agent_id)

        display_name = f"{role} {spec} – {domain}"

        mission_tpl  = rng.choice(MISSION_TEMPLATES)
        mission      = mission_tpl.format(domain=domain, spec=spec, role=role)

        prompt_tpl   = rng.choice(PROMPT_TEMPLATES)
        system_prompt = prompt_tpl.format(domain=domain, spec=spec, role=role)

        agents.append({
            "agent_id":     agent_id,
            "display_name": display_name,
            "domain":       domain,
            "role":         role,
            "specialization": spec,
            "mission":      mission,
            "category":     cat,
            "safety":       safety,
            "system_prompt": system_prompt,
        })

    return agents


def main() -> None:
    print(f"Generowanie {TARGET} agentów (seed={SEED})…")
    agents = generate_agents()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(agents, fh, ensure_ascii=False, indent=2)
    print(f"✓ Zapisano {len(agents)} agentów → {OUTPUT}")
    # Verify uniqueness
    ids = [a["agent_id"] for a in agents]
    names = [a["display_name"] for a in agents]
    assert len(set(ids)) == len(agents), "Duplikaty agent_id!"
    print(f"✓ Wszystkie {len(agents)} agent_id są unikalne.")
    unique_names = len(set(names))
    print(f"  Unikalne display_name: {unique_names}/{len(agents)}")


if __name__ == "__main__":
    main()
