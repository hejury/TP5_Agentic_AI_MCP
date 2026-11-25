"""Serveur MCP du SAV : expose le tool distant rag_multimodal (transport streamable-http).

Derrière ce tool, un agent RAG cherche les passages et les figures pertinentes
dans les manuels techniques (PDF) et retourne une réponse sourcée.

Lancement :  uv run mcp_server.py
"""
import base64
from pathlib import Path

import pymupdf
from langchain.agents import create_agent
from langchain.messages import AIMessage, HumanMessage
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.tools import tool
from langchain_ollama import ChatOllama, OllamaEmbeddings
from mcp.server.fastmcp import FastMCP

DATA = Path(__file__).parent / "data"
MODELE = "qwen3-vl:2b-instruct"

llm = ChatOllama(model=MODELE, temperature=0)
embeddings = OllamaEmbeddings(model="nomic-embed-text")


# ---------- Indexation des manuels : texte + figures ----------
def extraire_manuels():
    documents = []
    (DATA / "figures").mkdir(exist_ok=True)
    for pdf in sorted((DATA / "manuels").glob("*.pdf")):
        doc = pymupdf.open(pdf)
        for numero, page in enumerate(doc, start=1):
            blocs = [b for b in page.get_text("blocks") if b[4].strip()]
            # Passages de texte (hors légendes de figures)
            for b in blocs:
                texte = " ".join(b[4].split())
                if len(texte) > 40 and not texte.startswith("Figure"):
                    documents.append(Document(texte, metadata={"type": "texte", "source": pdf.name, "page": numero}))
            # Figures : image + légende placée juste en dessous + texte à droite
            for i, info in enumerate(page.get_images(full=True)):
                cadre = page.get_image_rects(info[0])[0]
                legende = next((" ".join(b[4].split()) for b in blocs
                                if b[4].startswith("Figure") and 0 <= b[1] - cadre.y1 < 40), "")
                voisin = " ".join(" ".join(b[4].split()) for b in blocs
                                  if b[0] > cadre.x1 and b[1] < cadre.y1 and b[3] > cadre.y0)
                chemin = DATA / "figures" / f"{pdf.stem}_p{numero}_fig{i + 1}.png"
                page.get_pixmap(clip=cadre, dpi=100).save(chemin)
                documents.append(Document(f"{legende} {voisin}", metadata={
                    "type": "figure", "source": pdf.name, "page": numero,
                    "legende": legende, "chemin": str(chemin.relative_to(DATA.parent))}))
    return documents


index_dir = DATA / "index_faiss"
if index_dir.exists():
    vector_store = FAISS.load_local(str(index_dir), embeddings, allow_dangerous_deserialization=True)
else:
    vector_store = FAISS.from_documents(extraire_manuels(), embeddings)
    vector_store.save_local(str(index_dir))
print("Index prêt :", vector_store.index.ntotal, "éléments (passages + figures)")


def rechercher(requete, type_doc, k):
    return vector_store.similarity_search(requete, k=k, filter={"type": type_doc}, fetch_k=30)


# ---------- Lecture de la photo jointe ----------
def decrire_image(image_ref: str) -> str:
    """Le modèle vision décrit le pictogramme visible sur la photo du client."""
    chemin = DATA / "images" / f"{image_ref}.png"
    if not chemin.exists():
        return ""
    image_b64 = base64.b64encode(chemin.read_bytes()).decode()
    message = HumanMessage(content=[
        {"type": "text", "text": "Décris en une phrase, en français, le pictogramme affiché sur l'écran "
                                 "de cette imprimante (forme, symboles, couleur du voyant)."},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
    ])
    return llm.invoke([message]).content


# ---------- Agent RAG interne ----------
def creer_agent_rag(sources: list):
    @tool
    def chercher_passages(requete: str) -> str:
        """Chercher des passages de texte dans les manuels techniques."""
        docs = rechercher(requete, "texte", 3)
        sources.extend(docs)
        return "\n\n".join(f"[{d.metadata['source']} p.{d.metadata['page']}] {d.page_content}" for d in docs)

    @tool
    def chercher_figures(description: str) -> str:
        """Chercher les figures et pictogrammes des manuels qui correspondent à une description."""
        docs = rechercher(description, "figure", 2)
        sources.extend(docs)
        return "\n\n".join(f"[{d.metadata['legende']} — {d.metadata['source']} p.{d.metadata['page']}] "
                           f"{d.page_content}" for d in docs)

    return create_agent(
        model=llm,
        tools=[chercher_passages, chercher_figures],
        system_prompt=(
            "Tu es un agent RAG de documentation technique d'imprimantes. "
            "Si la question parle d'un pictogramme, d'un voyant ou d'une photo, appelle chercher_figures avec la "
            "description du pictogramme. Appelle aussi chercher_passages pour la procédure à suivre. "
            "Réponds en français, uniquement avec les informations trouvées, en citant la figure et la page."
        ),
    )


def formater_sources(sources):
    lignes = []
    for d in sources:
        m = d.metadata
        ligne = f"- {m['source']}, page {m['page']}" + (f" — {m['legende']} ({m['chemin']})" if m["type"] == "figure" else "")
        if ligne not in lignes:
            lignes.append(ligne)
    return "\n".join(lignes)


# ---------- Serveur MCP ----------
mcp = FastMCP(name="sav-documentation", host="0.0.0.0", port=24000)


@mcp.tool()
def rag_multimodal(question: str, image_ref: str = "") -> str:
    """Rechercher dans les manuels techniques des imprimantes (passages de texte et figures/pictogrammes)
    et retourner une réponse sourcée. image_ref : référence de la photo jointe par le client
    (par exemple img_px200_01), ou chaîne vide s'il n'y a pas de photo."""
    print(f"[rag_multimodal] question={question!r} image_ref={image_ref!r}")
    description = decrire_image(image_ref) if image_ref else ""
    if description:
        print("[rag_multimodal] description de la photo :", description)

    requete = question + (f"\nPhoto jointe : {description}" if description else "")
    sources = []
    resultat = creer_agent_rag(sources).invoke({"messages": [HumanMessage(requete)]})
    reponse = resultat["messages"][-1].content

    # Repli : si le petit modèle n'a appelé aucun outil, on fait la recherche nous-mêmes
    if not any(isinstance(m, AIMessage) and m.tool_calls for m in resultat["messages"]):
        figures = rechercher(requete, "figure", 1)
        passages = rechercher(requete, "texte", 3)
        sources = figures + passages
        contexte = "\n\n".join(f"[p.{d.metadata['page']}] {d.page_content}" for d in sources)
        reponse = llm.invoke(f"Réponds en français à la question avec ces extraits du manuel, en citant les pages.\n"
                             f"Question : {requete}\nExtraits :\n{contexte}").content

    return f"{reponse}\n\nSources :\n{formater_sources(sources)}"


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
