FROM homeassistant/home-assistant:stable

LABEL org.opencontainers.image.title="Marstek Venus E Home Assistant Test Image" \
      org.opencontainers.image.description="Home Assistant image with the Marstek Venus E integration preinstalled" \
      org.opencontainers.image.authors="Jens Saffrich (JS TechSector)" \
      org.opencontainers.image.source="https://github.com/JS-DE-Tech/hacs-marstek-api-connect"

# Copy the integration into Home Assistant's custom_components directory.
# Build with the repository root as the Docker context.
COPY custom_components/hacs_marstek_api_connect /config/custom_components/hacs_marstek_api_connect

EXPOSE 8123
