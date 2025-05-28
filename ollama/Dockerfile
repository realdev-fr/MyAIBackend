FROM ollama/ollama


# Installer curl (nécessaire pour le script de préchargement)
RUN apt-get update && apt-get install -y curl && apt-get clean

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]