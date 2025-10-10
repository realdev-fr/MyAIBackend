# MyAI - Assistant IA Multi-fonctionnel

## Description du Projet

MyAI est un système d'assistant intelligent multi-fonctionnel basé sur des LLM locaux (via Ollama) et le protocole MCP (Model Context Protocol). Le projet combine plusieurs services pour créer un assistant capable d'interagir avec différents systèmes : météo, domotique, emails, reconnaissance vocale, traduction, etc.

### Architecture

Le projet est composé de deux serveurs principaux :

1. **Serveur MCP** (`mcp_server.py`) : Expose des outils utilisables par l'agent IA via le protocole MCP
2. **Serveur API** (`api/main.py`) : API FastAPI qui orchestre l'agent conversationnel en utilisant LlamaIndex et les outils MCP

## Fonctionnalités

### 🌤️ Météo
- Récupération des prévisions météo via l'API OpenWeatherMap
- Support multilingue (français par défaut)
- Prévisions sur 5 jours avec données détaillées toutes les 3 heures

### ⏰ Heure
- Récupération de l'heure actuelle du système

### 🏠 Domotique
- Contrôle des appareils intelligents Kasa (TP-Link)
- Allumer/Éteindre les lumières et prises connectées
- Support de plusieurs appareils configurables

### 📧 Email
- Envoi d'emails via SMTP Gmail
- Support des app passwords Gmail
- Formatage automatique des emails

### 🌍 Traduction
- Service de traduction multilingue avec streaming
- Détection automatique de la langue source
- Explications et corrections grammaticales

### 🎙️ Reconnaissance Vocale
- Transcription audio en temps réel via WebSocket
- Utilise Faster-Whisper pour la reconnaissance vocale
- Support du français
- Intégration directe avec l'agent conversationnel

### 🖼️ Upload d'Images
- Endpoint pour uploader des images
- Intégration avec webhook n8n
- Support des formats : JPEG, PNG, GIF, WebP
- Limite de taille : 10MB

### 🤖 Agent Conversationnel
- Agent IA basé sur LlamaIndex
- Accès à tous les outils via MCP
- Streaming des réponses en temps réel
- Gestion des appels d'outils avec feedback

## Prérequis

### Logiciels Requis

- **Python 3.10+**
- **Ollama** : Pour exécuter les modèles LLM localement
  - Installer depuis [ollama.ai](https://ollama.ai)
  - Télécharger le modèle : `ollama pull mistral-small`
- **uv** : Gestionnaire de paquets Python rapide
  - Installer : `curl -LsSf https://astral.sh/uv/install.sh | sh`

### Dépendances Python

Toutes les dépendances sont listées dans `requirements.txt` :

```bash
pip install -r requirements.txt
```

Principales dépendances :
- `fastapi` / `uvicorn` : Framework web
- `llama-index` : Orchestration de l'agent IA
- `mcp` / `fastapi-mcp` : Protocole MCP
- `python-kasa` : Contrôle domotique
- `faster-whisper` : Reconnaissance vocale
- `httpx` : Client HTTP asynchrone
- `python-dotenv` : Gestion des variables d'environnement

## Configuration

### 1. Créer le fichier `.env`

Copier le fichier d'exemple et le compléter :

```bash
cp .env.example .env
```

### 2. Configurer les Variables d'Environnement

Éditer le fichier `.env` avec vos propres valeurs :

```env
# Port du serveur MCP
MCP_PORT=8000

# API OpenWeatherMap (gratuit sur openweathermap.org)
OPENWEATHER_API_KEY=votre_clé_api_openweather

# Kasa Smart Home (comptes TP-Link)
KASA_USERNAME=votre_email@example.com
KASA_PASSWORD=votre_mot_de_passe_kasa
KASA_FIRST_DEVICE_IP=192.168.1.40  # IP de votre premier appareil
KASA_SECOND_DEVICE_IP=192.168.1.41 # IP de votre deuxième appareil

# Gmail SMTP (nécessite un App Password)
# Créer un App Password : https://myaccount.google.com/apppasswords
GMAIL_USER=votre_email@gmail.com
GMAIL_APP_PASSWORD=votre_app_password_16_caracteres

# Webhook n8n (optionnel, pour l'upload d'images)
N8N_WEBHOOK_URL=http://votre_serveur_n8n:port/webhook/nom_webhook
```

### 3. Notes de Configuration

#### OpenWeatherMap
- Créer un compte gratuit sur [openweathermap.org](https://openweathermap.org/api)
- Récupérer votre clé API dans la section "API Keys"

#### Kasa Smart Home
- Utiliser vos identifiants de l'application Kasa/Tapo
- Trouver les IPs des appareils dans les paramètres de votre routeur ou l'application Kasa
- Les noms de devices peuvent être personnalisés dans `mcp_server.py` (lignes 70-79)

#### Gmail SMTP
- Activer la validation en 2 étapes sur votre compte Google
- Créer un "App Password" dédié pour cette application
- Ne JAMAIS utiliser votre mot de passe Gmail principal

#### n8n Webhook (Optionnel)
- Uniquement nécessaire si vous utilisez la fonctionnalité d'upload d'images
- Configurer un webhook dans votre instance n8n

## Démarrage

### 1. Démarrer le Serveur MCP

Le serveur MCP doit être démarré en premier car l'API en dépend :

```bash
uv run mcp_server.py
```

Par défaut, le serveur MCP démarre sur le port défini dans `.env` (MCP_PORT=8000).

**Options avancées :**
```bash
# Mode SSE (par défaut)
uv run mcp_server.py --server_type=sse

# Mode STDIO
uv run mcp_server.py --server_type=stdio

# Mode développement avec auto-reload
uv run mcp dev mcp_server.py
```

### 2. Démarrer le Serveur API

Dans un nouveau terminal, démarrer l'API FastAPI :

```bash
uvicorn api.main:app --port 9999 --host 0.0.0.0 --http=httptools
```

L'API sera accessible sur `http://localhost:9999`

**Options :**
- `--reload` : Auto-reload en développement
- `--workers N` : Nombre de workers (production)

### 3. Vérifier le Fonctionnement

Une fois les deux serveurs démarrés :

1. **Vérifier l'API** : Ouvrir http://localhost:9999/docs (documentation Swagger)
2. **Tester un outil** : Utiliser l'endpoint `/ask` avec une question

Exemple de requête :
```bash
curl -X POST "http://localhost:9999/ask" \
  -H "Content-Type: application/json" \
  -d '{"text": "Quelle est la météo à Paris?"}'
```

## Utilisation

### Endpoints Principaux

#### `/ask` (POST)
Agent conversationnel avec streaming et accès aux outils MCP
```json
{
  "text": "Allume la lumière du salon"
}
```

#### `/discuss` (POST)
Discussion simple avec le LLM sans outils
```json
{
  "text": "Explique-moi la relativité"
}
```

#### `/translate` (POST)
Traduction avec explications
```json
{
  "source_lang": "français",
  "target_lang": "anglais",
  "text": "Bonjour le monde"
}
```

#### `/ws/speak` (WebSocket)
Reconnaissance vocale en temps réel - envoyer des chunks audio PCM 16-bit 16kHz mono

#### `/upload-image` (POST)
Upload d'image vers webhook n8n
```
multipart/form-data:
- file: Image file
- message_text: Texte accompagnant (optionnel)
- source: Source du message (optionnel)
```

### Exemples de Commandes pour l'Agent

- "Quelle est la météo à Lyon ?"
- "Quelle heure est-il ?"
- "Allume la lumière du salon"
- "Éteins la chambre"
- "Envoie un email à contact@example.com avec comme sujet 'Test' et le message 'Ceci est un test'"

## Structure du Projet

```
MyAI/
├── mcp_server.py          # Serveur MCP avec définition des outils
├── api/
│   ├── main.py           # API FastAPI principale
│   └── models/
│       └── discussion.py # Modèles Pydantic
├── requirements.txt       # Dépendances Python
├── .env.example          # Exemple de configuration
├── .env                  # Configuration (à créer)
└── README.md             # Ce fichier
```

## Dépannage

### Le serveur MCP ne démarre pas
- Vérifier que le port MCP_PORT n'est pas déjà utilisé
- Vérifier que toutes les variables d'environnement sont définies dans `.env`

### L'API ne se connecte pas au MCP
- Vérifier que le serveur MCP est bien démarré
- Vérifier que MCP_PORT dans `.env` correspond au port utilisé
- Vérifier les logs du serveur MCP

### Les outils Kasa ne fonctionnent pas
- Vérifier les IPs des appareils (ping)
- Vérifier les identifiants Kasa
- S'assurer que les appareils sont sur le même réseau

### L'envoi d'email échoue
- Vérifier que vous utilisez un App Password Gmail (pas le mot de passe principal)
- Vérifier que la validation en 2 étapes est activée
- Vérifier les paramètres de sécurité du compte Google

### Ollama ne répond pas
- Vérifier qu'Ollama est bien installé : `ollama --version`
- Vérifier que le modèle est téléchargé : `ollama list`
- Télécharger le modèle si nécessaire : `ollama pull mistral-small`
- Vérifier qu'Ollama tourne : `ollama serve`

## Développement

### Ajouter un Nouvel Outil MCP

1. Éditer `mcp_server.py`
2. Ajouter une fonction décorée avec `@mcp.tool()`
3. Redémarrer le serveur MCP
4. L'outil sera automatiquement disponible pour l'agent

Exemple :
```python
@mcp.tool("mon_outil", "Description de mon outil")
def mon_outil(param1: str):
    # Logique de l'outil
    return json.dumps({"result": "success"})
```

### Modifier le Prompt Système

Éditer la variable `SYSTEM_PROMPT` dans `api/main.py` pour personnaliser le comportement de l'agent.

## Licence

Ce projet est à usage personnel et éducatif.

## Auteur

Développé avec passion par RealDev