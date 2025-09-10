

# Updated templates
FRPC_TOML_TEMPLATE = """serverAddr = "{host}"
serverPort = 7000

[auth]
method = "token"
token = "supersecret"

[[proxies]]
name = "client-app"
type = "http"
localPort = 8003
customDomains = ["{identifier}.{host}.nip.io"]

"""

DOCKERFILE_TEMPLATE = """FROM alpine:3.19

WORKDIR /app

# Install wget + tar
RUN apk add --no-cache wget tar

# Download FRP client binary
ARG FRP_VERSION=0.60.0
RUN wget https://github.com/fatedier/frp/releases/download/v${FRP_VERSION}/frp_${FRP_VERSION}_linux_amd64.tar.gz \\
    && tar -xzf frp_${FRP_VERSION}_linux_amd64.tar.gz \\
    && mv frp_${FRP_VERSION}_linux_amd64/frpc /usr/local/bin/frpc \\
    && rm -rf frp*

# Copy client config
COPY frpc.toml /etc/frpc.toml

CMD ["frpc", "-c", "/etc/frpc.toml"]
"""

DOCKER_COMPOSE_TEMPLATE = """services:
  frpc:
    build: .
    container_name: frpc
    network_mode: "host"
    volumes:
      - ./frpc.toml:/etc/frpc.toml:ro
    restart: unless-stopped
"""
