# Activité Pratique N°5 — Agentic AI et MCP (LangChain, LangGraph)

LLM local open source : **qwen3-vl:2b-instruct** via **Ollama** · Embeddings : **nomic-embed-text**

## Contenu

| Dossier / fichier | Partie |
|---|---|
| `partie_D_sav/` | **Partie D — Synthèse** : système multi-agents de SAV |
| `A_langchain_agents.ipynb` | Partie A — rappel LangChain (agents, mémoire, tools, middlewares, guardrails, HITL, RAG agentique) |

## Partie D — SAV d'un distributeur d'électronique

- **Orchestrateur** (LangGraph) : classe la demande (`documentation` / `garantie`), route vers l'agent spécialisé et termine quand la réponse finale est disponible.
- **agent_documentaire** : appelle le tool distant `rag_multimodal` exposé par un **serveur MCP** (transport *streamable-http*). Derrière ce tool, un agent RAG lit la photo jointe (modèle vision), cherche les passages et les figures du manuel et retourne une réponse sourcée.
- **agent_garantie** : appelle le tool local `consulter_garantie` (registre en lecture seule).

| Fichier | Rôle |
|---|---|
| `partie_D_sav/mcp_server.py` | Serveur MCP + agent RAG multimodal (port 24000) |
| `partie_D_sav/sav_graph.py` | Orchestrateur et agents spécialisés |
| `partie_D_sav/D_synthese_sav.ipynb` | Tests : données, client MCP, tool local, graphe, exemples |
| `partie_D_sav/data/` | Manuel PX-200 (PDF texte + pictogrammes), photo `img_px200_01`, registre des garanties |
| `partie_D_sav/generer_donnees.py` | Génération des données fictives |

### Lancement

```bash
ollama pull qwen3-vl:2b-instruct
ollama pull nomic-embed-text
cd partie_D_sav
uv sync
uv run mcp_server.py          # terminal 1 : serveur MCP
```

Puis exécuter `D_synthese_sav.ipynb` avec le kernel `.venv` de `partie_D_sav`.

Test du serveur : `npx @modelcontextprotocol/inspector` → Streamable HTTP → `http://localhost:24000/mcp`.

### Exemples

| Demande | Catégorie | Agent |
|---|---|---|
| « Mon imprimante PX-200 affiche un voyant clignotant. Que signifie le pictogramme sur la photo jointe ? » + `img_px200_01` | documentation | agent_documentaire |
| « Est-ce que mon imprimante est encore sous garantie ? Son numéro de série est PX200-0042. » | garantie | agent_garantie |
