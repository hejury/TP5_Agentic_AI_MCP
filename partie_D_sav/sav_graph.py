"""Système multi-agents du SAV orchestré par LangGraph.

orchestrateur ──documentation──► agent_documentaire (tool distant rag_multimodal via MCP)
      ▲        ──garantie──────► agent_garantie     (tool local consulter_garantie)
      └──────── retour des agents spécialisés ──────┘ ──► END quand la réponse finale est prête
"""
import json
import re
from datetime import date
from pathlib import Path
from typing import Annotated, Literal, Optional, Sequence, TypedDict

from langchain.agents import create_agent
from langchain.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.messages import BaseMessage
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

DATA = Path(__file__).parent / "data"
MODELE = "qwen3-vl:2b-instruct"
URL_MCP = "http://localhost:24000/mcp"

llm = ChatOllama(model=MODELE, temperature=0)


# ---------- Tool local (lecture seule) ----------
@tool
def consulter_garantie(numero_serie: str) -> dict:
    """Consulter le registre des garanties à partir du numéro de série d'un appareil (format PX200-XXXX)."""
    registre = json.loads((DATA / "registre_garanties.json").read_text(encoding="utf-8"))
    trouve = re.search(r"PX200-\d{4}", numero_serie.upper())
    numero = trouve.group() if trouve else numero_serie.strip().upper()
    if numero not in registre:
        return {"numero_serie": numero, "trouve": False}
    fiche = registre[numero]
    achat = date.fromisoformat(fiche["date_achat"])
    mois = achat.month - 1 + fiche["duree_mois"]
    fin = achat.replace(year=achat.year + mois // 12, month=mois % 12 + 1)
    restant = (fin - date.today()).days
    return {"numero_serie": numero, "trouve": True, "modele": fiche["modele"],
            "date_achat": fiche["date_achat"], "fin_garantie": fin.isoformat(),
            "sous_garantie": restant >= 0, "jours_restants": max(restant, 0)}


def texte(contenu) -> str:
    """Le résultat d'un tool MCP peut être une chaîne ou une liste de blocs de contenu."""
    if isinstance(contenu, str):
        return contenu
    return "\n".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in contenu)


# ---------- État partagé ----------
class SavState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    question: str
    image_ref: Optional[str]
    categorie: Optional[str]
    agent: Optional[str]
    reponse_finale: Optional[str]


# ---------- Orchestrateur ----------
def classer(question: str) -> str:
    verdict = llm.invoke(
        "Classe la demande d'un client du SAV dans une seule catégorie :\n"
        "- documentation : panne, voyant, pictogramme, photo, utilisation, procédure\n"
        "- garantie : garantie, numéro de série, date d'achat, prise en charge\n"
        f"Demande : {question}\nRéponds uniquement par documentation ou garantie."
    ).content.lower()
    if ("garantie" in verdict) != ("documentation" in verdict):
        return "garantie" if "garantie" in verdict else "documentation"
    return "garantie" if "garanti" in question.lower() else "documentation"   # repli si réponse ambiguë


async def orchestrateur(state: SavState):
    if state.get("reponse_finale"):
        print(f"[orchestrateur] réponse reçue de {state['agent']} → fin")
        return {"messages": [AIMessage(state["reponse_finale"], name="orchestrateur")]}
    categorie = classer(state["question"])
    print(f"[orchestrateur] catégorie = {categorie}")
    return {"categorie": categorie}


def router(state: SavState) -> Literal["agent_documentaire", "agent_garantie", "__end__"]:
    if state.get("reponse_finale"):
        return END
    return "agent_documentaire" if state["categorie"] == "documentation" else "agent_garantie"


# ---------- Construction du graphe ----------
async def construire_systeme(checkpointer=None, url_mcp: str = URL_MCP):
    # Le tool peut être long sur CPU (lecture de la photo + RAG) : on attend jusqu'à 20 minutes
    client = MultiServerMCPClient({"sav": {"transport": "streamable_http", "url": url_mcp,
                                           "timeout": 60, "sse_read_timeout": 1200}})
    outils_mcp = await client.get_tools()
    rag_multimodal = next(t for t in outils_mcp if t.name == "rag_multimodal")

    agent_doc = create_agent(
        model=llm, tools=[rag_multimodal],
        system_prompt=("Tu es l'agent documentaire du SAV. Appelle toujours rag_multimodal avec la question du "
                       "client et la référence de la photo (image_ref) si elle existe. "
                       "Rends ensuite la réponse en gardant les sources."),
    )
    agent_gar = create_agent(
        model=llm, tools=[consulter_garantie],
        system_prompt=("Tu es l'agent garantie du SAV. Appelle consulter_garantie avec le numéro de série, puis "
                       "indique en français si l'appareil est sous garantie, la date de fin et les jours restants."),
    )

    async def agent_documentaire(state: SavState):
        demande = state["question"] + (f"\nimage_ref : {state['image_ref']}" if state.get("image_ref") else "")
        resultat = await agent_doc.ainvoke({"messages": [HumanMessage(demande)]})
        appels = [a["args"] for m in resultat["messages"] if isinstance(m, AIMessage) for a in m.tool_calls]
        resultats_outil = [texte(m.content) for m in resultat["messages"] if isinstance(m, ToolMessage)]
        image_ok = all((a.get("image_ref") or "") == (state.get("image_ref") or "") for a in appels)
        if resultats_outil and image_ok:
            reponse = resultats_outil[-1]
        else:   # repli : le petit modèle n'a pas appelé le tool correctement → appel direct
            print("[agent_documentaire] appel direct de rag_multimodal")
            reponse = texte(await rag_multimodal.ainvoke(
                {"question": state["question"], "image_ref": state.get("image_ref") or ""}))
        return {"messages": resultat["messages"][1:], "agent": "agent_documentaire", "reponse_finale": reponse}

    async def agent_garantie(state: SavState):
        resultat = await agent_gar.ainvoke({"messages": [HumanMessage(state["question"])]})
        return {"messages": resultat["messages"][1:], "agent": "agent_garantie",
                "reponse_finale": resultat["messages"][-1].content}

    builder = StateGraph(SavState)
    builder.add_node("orchestrateur", orchestrateur)
    builder.add_node("agent_documentaire", agent_documentaire)
    builder.add_node("agent_garantie", agent_garantie)
    builder.add_edge(START, "orchestrateur")
    builder.add_conditional_edges("orchestrateur", router)
    builder.add_edge("agent_documentaire", "orchestrateur")
    builder.add_edge("agent_garantie", "orchestrateur")
    return builder.compile(checkpointer=checkpointer)


async def traiter_demande(systeme, question, image_ref=None):
    etat = {"messages": [HumanMessage(question)], "question": question, "image_ref": image_ref,
            "categorie": None, "agent": None, "reponse_finale": None}
    return await systeme.ainvoke(etat)
