#!/bin/bash

# Lancer le serveur Ollama
ollama serve &

# Attendre que le serveur soit prêt
until curl -s http://localhost:11434 > /dev/null; do
  echo "En attente de Ollama..."
  sleep 1
done

# Charger le modèle (déclenche le téléchargement si absent)
echo "Préchargement du modèle mistral-small:latest..."
ollama run mistral-small:latest --verbose

# Garde le container en vie
wait
