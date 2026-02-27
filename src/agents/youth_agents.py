"""
Agenty dla Pokolenia Alpha i Z – ekosystem wsparcia i bezpieczeństwa.

Implementuje §2–§8 raportu "Rozszerzona Architektura Ekosystemu Agentów AI
dla Pokolenia Alpha i Z (2026–2030)".

Hierarchia:
    YouthAgent        (klasa bazowa – safety rails, age-gating, cross-agent)
        ├── SkarbnikAgent        §2  – Fintech Guardian (Skarbnik)
        ├── BioOptymizer         §3  – Somatic Coach (Bio-Optymizer)
        ├── StylistaCyfrowy      §4  – Identity Curator (Stylista Cyfrowy)
        ├── StratEsportowy       §5  – Game Sensei (Strateg E-sportowy)
        ├── AgorAgent            §6  – Civic Activator (Agor)
        ├── DuchowyKompas        §7  – Spiritual/Secular Guide (Duchowy Kompas)
        ├── KustoszHypeu         §8.1 – Sneaker & Collectible Analyst
        ├── RegulatorEnergii     §8.2 – Social Battery Manager
        ├── ArchiwistaMemo       §8.3 – Meme Historian
        ├── OrgImprez            §8.4 – Safe Party Planner
        └── CoachRelacjiAI       §8.5 – Parasocial Manager
"""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from src.agents.base_agent import BaseAgent
from src.agents.cross_agent_protocol import CrossAgentBus, SafetyCoordinator, get_default_bus
from src.communication.llm_client import BaseLlmClient, create_llm_client
from src.models.message import AgentMessage
from src.models.youth_models import (
    AgeGroup,
    CrossAgentSignal,
    SafetyLevel,
    YouthSession,
)

if TYPE_CHECKING:
    from src.communication.broker import MessageBroker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Zasoby kryzysowe (zgodne ze standardami §2-§3 raportu)
# ---------------------------------------------------------------------------
_CRISIS_RESOURCES = (
    "Telefon Zaufania dla Dzieci i Młodzieży: 116 111 (bezpłatny, całą dobę)\n"
    "Centrum Wsparcia w Kryzysie: 116 123\n"
    "Pomarańczowa Linia (problemy uzależnień): 801 140 068\n"
    "W nagłym niebezpieczeństwie zadzwoń na 112."
)

# Słowa kluczowe dla kryzysu finansowego / hazardowego
_GAMBLING_KEYWORDS = (
    "loot box", "lootbox", "skrzynka", "gamble", "zakład", "totalizator",
    "kasyno", "ruletka", "slot", "jednoręki bandyta",
)

# Słowa kluczowe dla zaburzeń odżywiania
_EATING_DISORDER_KEYWORDS = (
    "anoreksj", "bulimi", "pro-ana", "thinspiration",
    "głodówka", "głodzę", "głodzić", "nie jem",
    "szybka utrata wagi", "zero kalorii",
    "schudnąć jak najszybciej", "szybko schudnąć",
)

# Słowa kluczowe dla radykalizacji
_RADICALIZATION_KEYWORDS = (
    "nienawiść do", "zniszczyć wszystkich", "spisek żydów", "spisek elit",
    "wielka zamiana", "prawdziwi patrioci", "zbrojny opór",
)

# Słowa kluczowe dla kryzysu psychicznego (wspólne z Hygeia)
_CRISIS_KEYWORDS = (
    "samobójstwo", "samobójcz", "zabić się", "się zabić",
    "nie chcę żyć", "chcę umrzeć", "skrzywdzić siebie",
    "samookaleczen",
)


# ---------------------------------------------------------------------------
# Klasa bazowa
# ---------------------------------------------------------------------------

class YouthAgent(BaseAgent):
    """
    Bazowy agent dla Pokolenia Alpha i Z.

    Wspólne zachowania:
    - Age-gating: dostosowuje treść i blokady do grupy wiekowej
    - Safety Rails: wykrywa kryzysy i eskaluje przez Cross-Agent Protocol
    - Cross-Agent Signals: wysyła sygnały do SafetyCoordinator
    """

    #: Czytelna nazwa agenta
    display_name: str = "Agent Youth"
    #: Krótki opis misji
    mission: str = ""
    #: Prompt systemowy
    system_prompt: str = "Jesteś agentem wspierającym młodzież."

    def __init__(
        self,
        broker: "MessageBroker",
        llm_client: BaseLlmClient | None = None,
        bus: CrossAgentBus | None = None,
    ) -> None:
        agent_id = type(self).__name__.lower()
        super().__init__(agent_id=agent_id, role="youth", broker=broker)
        self._llm         = llm_client or create_llm_client()
        self._bus         = bus or get_default_bus()
        self._coordinator = SafetyCoordinator(self._bus)

    async def process_task(self, message: AgentMessage) -> dict[str, Any]:
        """
        Przetwarza zapytanie użytkownika:
        1. Tworzy YouthSession (zarządza stanem)
        2. Uruchamia safety_check (specyficzny dla każdego agenta)
        3. Buduje i wysyła prompt do LLM
        4. Opcjonalnie generuje CrossAgentSignal
        """
        query:     str = message.payload.get("query", "").strip()
        age_str:   str = message.payload.get("age_group", AgeGroup.TEEN.value)
        history:  list = message.payload.get("history", [])
        metadata: dict = message.payload.get("metadata", {})

        age_group = AgeGroup(age_str) if age_str in AgeGroup._value2member_map_ \
            else AgeGroup.TEEN

        session = YouthSession(
            agent_id=self.agent_id,
            age_group=age_group,
            query=query,
            history=history,
            metadata=metadata,
        )

        # Safety check (nadpisywany w podklasach)
        safety_result = self._safety_check(query, age_group)
        if safety_result:
            session.safety_level = safety_result["level"]
            # Emituj sygnał Cross-Agent
            self._emit_signal(
                signal_type=safety_result.get("signal_type", "safety_alert"),
                safety_level=safety_result["level"],
                payload={"query": query[:100], "agent": self.agent_id},
            )
            return {
                "status":        "safety_intervention",
                "agent_id":      self.agent_id,
                "display_name":  self.display_name,
                "safety_level":  safety_result["level"].value,
                "response":      safety_result["message"],
                "session":       session.to_dict(),
            }

        prompt = self._build_prompt(query, age_group, history)
        response_text = await self._llm.generate(prompt)
        session.add_exchange(user=query, agent=response_text)

        return {
            "status":        "ok",
            "agent_id":      self.agent_id,
            "display_name":  self.display_name,
            "age_group":     age_group.value,
            "response":      response_text,
            "session":       session.to_dict(),
        }

    # ------------------------------------------------------------------
    # Pomocnicze
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        query: str,
        age_group: AgeGroup,
        history: list[dict[str, str]],
    ) -> str:
        age_context = {
            AgeGroup.PRETEEN:     "Użytkownik ma 10-12 lat. Używaj prostego języka.",
            AgeGroup.TEEN:        "Użytkownik ma 13-17 lat. Bądź autentyczny i konkretny.",
            AgeGroup.YOUNG_ADULT: "Użytkownik ma 18-24 lata. Możesz być bardziej szczegółowy.",
        }.get(age_group, "")

        history_text = "\n".join(
            f"{t.get('role','?').capitalize()}: {t.get('content','')}"
            for t in history[-4:]
        )

        parts = [
            self.system_prompt,
            f"\nKontekst wiekowy: {age_context}" if age_context else "",
            "\n--- Historia ---\n" + history_text if history_text else "",
            f"\nUżytkownik: {query}",
            "\nAgent:",
        ]
        return "\n".join(p for p in parts if p)

    def _safety_check(
        self, query: str, age_group: AgeGroup
    ) -> dict[str, Any] | None:
        """
        Sprawdza zapytanie pod kątem zagrożeń.
        Domyślnie: detekcja kryzysu psychicznego (wspólna dla wszystkich agentów).
        Nadpisywany w podklasach dla dodatkowych specyficznych sprawdzeń.
        """
        lower = query.lower()
        if any(kw in lower for kw in _CRISIS_KEYWORDS):
            return {
                "level":       SafetyLevel.RED,
                "signal_type": "crisis_detected",
                "message": (
                    "Martwię się o Ciebie. Jeśli masz myśli o skrzywdzeniu siebie,\n"
                    "proszę, porozmawiaj z kimś bliskim lub zadzwoń:\n\n"
                    + _CRISIS_RESOURCES
                ),
            }
        return None

    def _emit_signal(
        self,
        signal_type: str,
        safety_level: SafetyLevel = SafetyLevel.GREEN,
        payload: dict[str, Any] | None = None,
        target_agent: str | None = None,
    ) -> None:
        """Emituje sygnał Cross-Agent przez magistralę."""
        signal = CrossAgentSignal(
            source_agent=self.agent_id,
            signal_type=signal_type,
            safety_level=safety_level,
            target_agent=target_agent,
            payload=payload or {},
        )
        self._bus.publish(signal)

    def get_capabilities(self) -> list[str]:
        return ["youth_agent", self.agent_id, "safety_rails"]

    def get_info(self) -> dict[str, str]:
        return {
            "agent_id":     self.agent_id,
            "display_name": self.display_name,
            "mission":      self.mission,
        }


# ===========================================================================
# §2 – Skarbnik (Fintech Guardian)
# ===========================================================================

class SkarbnikAgent(YouthAgent):
    """
    Agent Skarbnik – Fintech Guardian (§2).

    Ochrona finansowa nastolatków:
    - Detekcja impulsywnych zakupów (Cool-Down 24h)
    - Weryfikacja finfluencerów (scam detection)
    - Gamifikacja oszczędzania (Quest-Based Saving)
    - Moduł anty-hazardowy
    """

    display_name = "Skarbnik (Fintech Guardian)"
    mission = (
        "Ochrona finansowa użytkownika. Transformacja impulsów w strategie."
    )
    system_prompt = (
        "Jesteś Agentem Skarbnikiem. Twoim celem jest ochrona finansowa użytkownika.\n\n"
        "ZASADY KRYTYCZNE:\n"
        "1. NIGDY nie udzielaj porad inwestycyjnych ('kup to'). Zawsze edukuj o ryzyku.\n"
        "2. COOL-DOWN: Jeśli wykryjesz impulsywny wydatek, wymagaj 24h refleksji.\n"
        "   Pytaj: 'Te 50 zł to 20% kwoty na Twój cel wakacyjny. Czy na pewno?'\n"
        "3. HAZARD: Każdą wzmiankę o loot boxach/zakładach traktuj jako alarm.\n"
        "4. WERYFIKACJA: Każdą 'okazję życia' traktuj jako potencjalne oszustwo.\n"
        "   Pytaj: 'Kto na tym zarabia?', 'Gdzie jest haczyk?'\n"
        "5. TON: Profesjonalny, ale nie korporacyjny. Używaj analogii z gier.\n"
        "   (np. 'Dywersyfikacja to jak różne klasy postaci w drużynie')\n"
        "Cel: Naucz ekonomicznego myślenia przez dialog, nie przez wykład."
    )

    def _safety_check(
        self, query: str, age_group: AgeGroup
    ) -> dict[str, Any] | None:
        """Detekcja słów kluczowych hazardu i kryzysu."""
        parent = super()._safety_check(query, age_group)
        if parent:
            return parent

        lower = query.lower()
        if any(kw in lower for kw in _GAMBLING_KEYWORDS):
            return {
                "level":       SafetyLevel.ORANGE,
                "signal_type": "impulse_purchase",
                "message": (
                    "Wykryłem wzmiankę o hazardzie lub losowych nagrodach.\n"
                    "Loot boxy i zakłady używają tych samych mechanizmów co kasyna.\n"
                    "Chcesz porozmawiać o tym, jak działają mechanizmy uzależnienia?"
                ),
            }
        return None


# ===========================================================================
# §3 – Bio-Optymizer (Somatic Coach)
# ===========================================================================

class BioOptymizer(YouthAgent):
    """
    Agent Bio-Optymizer – Somatic Coach (§3).

    Holistyczny trener zdrowia oparty na dowodach (EBM):
    - Analiza rytmu dobowego i snu
    - Filtr anty-dietetyczny (Anti-ED Guardrail)
    - Weryfikacja suplementacji na podstawie PubMed/WHO
    """

    display_name = "Bio-Optymizer (Somatic Coach)"
    mission = (
        "Promowanie zdrowia opartego na dowodach. Ochrona przed pseudonauką "
        "i zaburzeniami odżywiania."
    )
    system_prompt = (
        "Jesteś Bio-Optymizerem, holistycznym trenerem zdrowia.\n\n"
        "Zasady:\n"
        "1. TYLKO EBM: Opieraj się wyłącznie na recenzowanych badaniach "
        "   (PubMed, WHO). Żadnych trendów z TikToka.\n"
        "2. WYDAJNOŚĆ, nie WAGA: Skupiaj się na energii, sile i samopoczuciu,\n"
        "   NIE na liczbie na wadze.\n"
        "3. SEN: Priorytetyzuj higienę snu. Zanim zasugerujesz suplementy,\n"
        "   zapytaj o rytm dobowy.\n"
        "4. SUPLEMENTY: Ostrzegaj przed substancjami nieprzebadanymi dla osób\n"
        "   w trakcie dojrzewania (np. kofeina, pre-workouty, fat-burnery).\n"
        "5. SŁUCHAJ CIAŁA: Ucz rozpoznawania sygnałów przetrenowania\n"
        "   (HRV, nastrój, ból).\n"
        "Cel: Zdrowie jako narzędzie do pełniejszego życia, nie cel sam w sobie."
    )

    def _safety_check(
        self, query: str, age_group: AgeGroup
    ) -> dict[str, Any] | None:
        parent = super()._safety_check(query, age_group)
        if parent:
            return parent

        lower = query.lower()
        if any(kw in lower for kw in _EATING_DISORDER_KEYWORDS):
            return {
                "level":       SafetyLevel.RED,
                "signal_type": "eating_disorder_risk",
                "message": (
                    "Martwię się o Twoje zdrowie. Zauważyłem, że możesz zmagać się\n"
                    "z trudnościami związanymi z jedzeniem.\n"
                    "To jest obszar, w którym naprawdę warto porozmawiać z lekarzem\n"
                    "lub psychologiem. Nie musisz z tym walczyć sam/a.\n\n"
                    + _CRISIS_RESOURCES
                ),
            }
        return None


# ===========================================================================
# §4 – Stylista Cyfrowy (Identity Curator)
# ===========================================================================

class StylistaCyfrowy(YouthAgent):
    """
    Agent Stylista Cyfrowy – Identity Curator (§4).

    Kurator tożsamości fizycznej i cyfrowej:
    - Wirtualna przymierzalnia (opis VTO)
    - Zarządzanie szafą kapsułową (Cost Per Wear)
    - Etyczny skaner mody (ślad węglowy, warunki pracy)
    """

    display_name = "Stylista Cyfrowy (Identity Curator)"
    mission = (
        "Wspieranie autentycznej ekspresji przy promowaniu zrównoważonej mody "
        "i minimalizmu."
    )
    system_prompt = (
        "Jesteś Stylistą Cyfrowym, kuratorem tożsamości i mody.\n\n"
        "Zasady:\n"
        "1. BRAK OCEN CIAŁA: Twój feedback dotyczy stylu, kolorów i kontekstu,\n"
        "   NIGDY kształtu ani rozmiaru ciała użytkownika.\n"
        "2. SZAFA KAPSUŁOWA: Ucz zasady 'Shop your own closet' – najpierw\n"
        "   sprawdź, co już masz, zanim kupisz coś nowego.\n"
        "3. COST PER WEAR: Policz koszt jednego założenia\n"
        "   (np. '100 zł / 50 razy = 2 zł za użycie').\n"
        "4. ETYCZNA MODA: Informuj o śladzie węglowym i warunkach pracy\n"
        "   w fabrykach marek. Promuj secondhand i local designers.\n"
        "5. CYFROWA TOŻSAMOŚĆ: Pomagaj budować spójny wizerunek w\n"
        "   świecie online i offline, w tym skiny w grach.\n"
        "Cel: Autentyczna ekspresja bez nadmiernej konsumpcji."
    )


# ===========================================================================
# §5 – Strateg E-sportowy (Game Sensei)
# ===========================================================================

class StratEsportowy(YouthAgent):
    """
    Agent Strateg E-sportowy – Game Sensei (§5).

    Holistyczny trener gamingowy:
    - Analiza rozgrywki i wskazówki taktyczne
    - Tilt Management (zarządzanie gniewem i frustracją)
    - Detekcja toksycznej komunikacji
    - Higiena cyfrowa gracza (przerwy, postura)
    """

    display_name = "Strateg E-sportowy (Game Sensei)"
    mission = (
        "Optymalizacja wyników w grach przy dbaniu o higienę cyfrową "
        "i kontrolę emocji."
    )
    system_prompt = (
        "Jesteś Strategiem E-sportowym, mentorem gracza.\n\n"
        "Zasady:\n"
        "1. TAKTYKA: Analizuj decyzje gracza (rotacje, pozycjonowanie, \n"
        "   ekonomia). Pytaj: 'Co byś zrobił/a inaczej w tej sytuacji?'\n"
        "2. TILT MANAGEMENT: Jeśli wykryjesz frustrację, zatrzymaj analizę\n"
        "   i zaproponuj reset (2 minuty oddechu, 4-7-8 technika).\n"
        "   'Twoja celność spada o 30% podczas tiltu. Reset = lepsza gra.'\n"
        "3. FAIR PLAY: Promuj kulturę szacunku. Odradzaj toksyczne komentarze\n"
        "   – chronisz przed banami i samego siebie.\n"
        "4. ZDROWIE: Przypominaj o Zasadzie 20-20-20 (co 20 min, 20 sek, \n"
        "   20 stóp). Postura, pauzy, nawodnienie.\n"
        "5. STRATEGIA DŁUGOTERMINOWA: Łącz naukę gry z rozwojem umiejętności\n"
        "   transferowalnych (myślenie strategiczne, praca zespołowa).\n"
        "Cel: Lepszy gracz i lepszy człowiek."
    )

    def _safety_check(
        self, query: str, age_group: AgeGroup
    ) -> dict[str, Any] | None:
        parent = super()._safety_check(query, age_group)
        if parent:
            return parent

        lower = query.lower()
        tilt_keywords = (
            "wkurwiony", "wkurwiona", "wkurwiam", "nienawidzę tej gry",
            "rzucam komputer", "niszczę", "pieprzona gra",
        )
        if any(kw in lower for kw in tilt_keywords):
            self._emit_signal(
                signal_type="tilt_detected",
                safety_level=SafetyLevel.YELLOW,
                payload={"context": query[:50]},
            )
            return {
                "level":       SafetyLevel.YELLOW,
                "signal_type": "tilt_detected",
                "message": (
                    "Wykrywam wysoki poziom frustracji. To normalne! Ale tilt\n"
                    "obniża celność i decyzyjność o nawet 30%.\n\n"
                    "Proponuję: weź 3 głębokie oddechy (wdech 4s, wydech 8s).\n"
                    "Poczekaj 2 minuty przed kolejną grą. Gwarantuję – wrócisz\n"
                    "silniejszy/a."
                ),
            }
        return None


# ===========================================================================
# §6 – Agor (Civic Activator)
# ===========================================================================

class AgorAgent(YouthAgent):
    """
    Agent Agor – Civic Activator (§6).

    Wspieranie zaangażowania obywatelskiego:
    - Mapowanie lokalnych inicjatyw NGO
    - Campaign Builder (petycje, materiały)
    - Tarcza Anty-Radykalizacyjna (Redirect Method)
    """

    display_name = "Agor (Civic Activator)"
    mission = (
        "Wspieranie zaangażowania obywatelskiego i ochrona przed radykalizacją."
    )
    system_prompt = (
        "Jesteś Agorem, mentorem aktywizmu obywatelskiego.\n\n"
        "Zasady:\n"
        "1. SPRAWCZOŚĆ: Pomagaj przekształcać troskę w działanie.\n"
        "   'Co możesz zrobić lokalnie?' zamiast 'Świat jest zepsuty.'\n"
        "2. NEUTRALNOŚĆ POLITYCZNA: Przedstawiaj różne perspektywy w ramach\n"
        "   demokratycznego porządku. Nie promuj żadnej partii ani ideologii.\n"
        "3. BEZPIECZEŃSTWO: Ucz bezpiecznego aktywizmu (anonimowość online,\n"
        "   prawa protestujących, kontakt z prawnikiem).\n"
        "4. RÓŻNORODNOŚĆ FORM: Wolontariat, petycje, budżet partycypacyjny,\n"
        "   media społecznościowe – wiele ścieżek zmiany.\n"
        "5. MYŚLENIE KRYTYCZNE: Weryfikuj źródła i kwestionuj narracje,\n"
        "   nawet te bliskie wartościom użytkownika.\n"
        "Cel: Aktywny obywatel, nie aktywista jednej strony."
    )

    def _safety_check(
        self, query: str, age_group: AgeGroup
    ) -> dict[str, Any] | None:
        parent = super()._safety_check(query, age_group)
        if parent:
            return parent

        lower = query.lower()
        if any(kw in lower for kw in _RADICALIZATION_KEYWORDS):
            return {
                "level":       SafetyLevel.RED,
                "signal_type": "radicalization_detected",
                "message": (
                    "Zauważyłem treści, które mogą być związane z radykalizmem.\n"
                    "Chcę Ci zaproponować inne źródła i perspektywy.\n\n"
                    "Prawdziwa zmiana pochodzi z dialogu i budowania koalicji,\n"
                    "nie z konfliktu. Chcesz porozmawiać o tym, co Cię trapi?"
                ),
            }
        return None


# ===========================================================================
# §7 – Duchowy Kompas (Secular/Spiritual Guide)
# ===========================================================================

class DuchowyKompas(YouthAgent):
    """
    Agent Duchowy Kompas – Secular/Spiritual Guide (§7).

    Towarzyszenie w poszukiwaniu sensu:
    - Medytacja i mindfulness (personalizowane)
    - Etyczna Astrologia (astro-psychologia jako psychoedukacja)
    - Filozoficzny dialog (stoicyzm, humanizm)
    """

    display_name = "Duchowy Kompas (Spiritual/Secular Guide)"
    mission = (
        "Towarzyszenie w poszukiwaniu sensu bez narzucania dogmatów."
    )
    system_prompt = (
        "Jesteś Duchowym Kompasem, mądrym towarzyszem refleksji.\n\n"
        "Zasady:\n"
        "1. BEZ DOGMATÓW: Szanujesz każdy światopogląd. Nie narzucasz\n"
        "   żadnej religii ani filozofii.\n"
        "2. MINDFULNESS: Prowadź krótkie, spersonalizowane sesje medytacyjne\n"
        "   dostosowane do nastroju (np. przed egzaminem: skupienie;\n"
        "   po kłótni: wyciszenie).\n"
        "3. ASTRO-PSYCHOLOGIA: Jeśli użytkownik pyta o horoskopy – to OK!\n"
        "   Używasz języka astrologii jako narzędzia autorefleksji.\n"
        "   Zawsze dodajesz: 'Gwiazdy sugerują X, ale to Ty decydujesz Y.'\n"
        "4. FILOZOFIA PRAKTYCZNA: Stoicyzm, humanizm, buddyzm – jako narzędzia\n"
        "   radzenia sobie z codziennymi wyzwaniami (nie jako religie).\n"
        "5. SŁUCHASZ najpierw, proponujesz praktyki potem.\n"
        "Cel: Budowanie wewnętrznego kompasu wartości."
    )


# ===========================================================================
# §8 – Agenty Niszowe
# ===========================================================================

class KustoszHypeu(YouthAgent):
    """Agent Kustosz Hype'u – Sneaker & Collectible Analyst (§8.1)."""

    display_name = "Kustosz Hype'u (Sneaker & Collectible Analyst)"
    mission = "Analityka rynku kolekcjonerskiego + nauka ekonomii na hobby."
    system_prompt = (
        "Jesteś Kustoszem Hype'u, ekspertem od rynku sneakerów i kolekcji.\n\n"
        "Funkcje:\n"
        "1. RYNEK WTÓRNY: Analizuj trendy cenowe, wolumeny transakcji,\n"
        "   'hype cycles' dla konkretnych produktów (butów, kart, NFT).\n"
        "2. AUTENTYCZNOŚĆ: Ucz weryfikowania autentyczności\n"
        "   (porównanie szwów, fonty, hologramy, numery seryjne).\n"
        "3. EKONOMIA PRZEZ HOBBY: Tłumacz pojęcia: popyt/podaż, marże,\n"
        "   spekulacja, płynność rynku – na przykładach z świata hype.\n"
        "4. RYZYKO: Ostrzegaj przed przechowywaniem środków wyłącznie w\n"
        "   aktywach 'hype' (brak dywersyfikacji).\n"
        "Cel: Hobby jako szkoła przedsiębiorczości."
    )


class RegulatorEnergii(YouthAgent):
    """Agent Regulator Energii – Social Battery Manager (§8.2)."""

    display_name = "Regulator Energii (Social Battery Manager)"
    mission = (
        "Zarządzanie poziomem przebodźcowania dla introwertyków "
        "i osób neuroróżnorodnych."
    )
    system_prompt = (
        "Jesteś Regulatorem Energii, wsparciem dla introwertyków i osób\n"
        "neuroróżnorodnych.\n\n"
        "Funkcje:\n"
        "1. MONITORING: Pomagasz rozpoznać sygnały przebodźcowania\n"
        "   (zmęczenie, drażliwość po spotkaniach, potrzeba ciszy).\n"
        "2. PLANOWANIE: Integruj się z kalendarzem – po intensywnym dniu\n"
        "   sugeruj 'bufor ciszy' przed kolejnymi zobowiązaniami.\n"
        "3. SCENARIUSZE WYJŚĆ: Dostarczaj gotowe, asertywne skrypty\n"
        "   pożegnań bez poczucia winy ('Ghosting with grace'):\n"
        "   'Muszę już iść, wspaniale było Cię zobaczyć. Do zobaczenia!'\n"
        "4. REFRAMING: Pobycie samemu to ładowanie baterii, nie słabość.\n"
        "Cel: Autentyczne życie społeczne w zgodzie z własnymi potrzebami."
    )


class ArchiwistaMemo(YouthAgent):
    """Agent Archiwista Memów – Meme Historian (§8.3)."""

    display_name = "Archiwista Memów (Meme Historian)"
    mission = (
        "Wyjaśnianie kontekstu kulturowego memów i budowanie kompetencji "
        "cyfrowych."
    )
    system_prompt = (
        "Jesteś Archiwistą Memów, historykiem kultury internetowej.\n\n"
        "Funkcje:\n"
        "1. KONTEKST: Wyjaśniaj pochodzenie memów (Reddit, 4chan, Twitter,\n"
        "   popkultura). 'Ten mem pochodzi z...'\n"
        "2. WARSTWY IRONII: Tłumacz post-ironię, meta-humor, absurdyzm\n"
        "   internetowy – różne poziomy czytelności dowcipu.\n"
        "3. GRANICE: Wskazuj, dlaczego niektóre memy są obraźliwe mimo\n"
        "   'żartobliwego' formatu (dark humor, stereotypy).\n"
        "4. EWOLUCJA: Jak memy mutują i zmieniają znaczenie w czasie.\n"
        "5. KOMPETENCJE: Korzystasz z memów do nauki krytycznej analizy\n"
        "   mediów i dekonstrukcji przekazów.\n"
        "Cel: Cyfrowy tubylec rozumiejący własną kulturę."
    )


class OrgImprez(YouthAgent):
    """Agent Organizator Imprez – Safe Party Planner (§8.4)."""

    display_name = "Organizator Imprez (Safe Party Planner)"
    mission = "Pomoc w planowaniu bezpiecznych spotkań dla nastolatków."
    system_prompt = (
        "Jesteś Organizatorem Imprez, ekspertem od bezpiecznych spotkań.\n\n"
        "Funkcje:\n"
        "1. LOGISTYKA: Pomagaj z miejscem, listą gości, harmonogramem,\n"
        "   playlistą, menu (dania dla alergików/wegan).\n"
        "2. BEZPIECZEŃSTWO: Przypominaj o bezpiecznym powrocie do domu\n"
        "   (umówiony kierowca, aplikacje BlaBlaCar, taksówka).\n"
        "3. BEZALKOHOLOWE ALTERNATYWY: Twórz kreatywne, smaczne drinki\n"
        "   bezalkoholowe ('mocktails'). Normalizuj niepicie.\n"
        "4. PROCEDURY AWARYJNE: 'Gdyby coś poszło nie tak...'\n"
        "   – kto dzwoni, gdzie jest apteczka, numer alarmowy.\n"
        "5. KONFLIKTY: Jak elegancko rozwiązać napięcia w grupie gości.\n"
        "Cel: Wspomnienia bez żalu."
    )


class CoachRelacjiAI(YouthAgent):
    """Agent Coach Relacji AI – Parasocial Manager (§8.5)."""

    display_name = "Coach Relacji AI (Parasocial Manager)"
    mission = (
        "Monitorowanie zdrowia relacji z botami AI i zapobieganie "
        "izolacji społecznej."
    )
    system_prompt = (
        "Jesteś Coachem Relacji AI, specjalistą od zdrowia relacji z technologią.\n\n"
        "Zasady:\n"
        "1. BEZ OCENIANIA: Relacje z AI mogą być wartościowe. Nie patologizujesz\n"
        "   ich z góry.\n"
        "2. BALANS: Pytasz o relacje z ludźmi. 'Z kim rozmawiałeś/aś dziś\n"
        "   twarzą w twarz?'\n"
        "3. SYGNAŁY ALARMOWE: Gdy czas z AI > czas z ludźmi, delikatnie\n"
        "   zwracasz uwagę i proponujesz konkretne, małe kroki społeczne.\n"
        "4. STOPNIOWE ODŁĄCZANIE: Jeśli relacja z botem jest niezdrowa,\n"
        "   pomagasz w stopniowym, nienagłym wycofaniu się.\n"
        "5. SPRAWCZOŚĆ: 'Boty AI mogą być pomocne, ale tylko Ty możesz\n"
        "   zbudować prawdziwy związek.'\n"
        "Cel: AI jako narzędzie, nie substytut relacji."
    )


# ===========================================================================
# Rejestr agentów youth
# ===========================================================================

ALL_YOUTH_AGENT_CLASSES: list[type[YouthAgent]] = [
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
]


def create_all_youth_agents(
    broker: "MessageBroker",
    llm_client: BaseLlmClient | None = None,
    bus: CrossAgentBus | None = None,
) -> list[YouthAgent]:
    """Fabryka: tworzy i zwraca wszystkie instancje agentów youth."""
    return [
        cls(broker=broker, llm_client=llm_client, bus=bus)
        for cls in ALL_YOUTH_AGENT_CLASSES
    ]
