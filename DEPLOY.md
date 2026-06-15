# Deploy do Legacy Doc

Arquitetura recomendada:

- Backend FastAPI na VPS Ubuntu 24.04, rodando em `127.0.0.1:8000` com `systemd`.
- Nginx na VPS expondo o backend em `https://api.seu-dominio.com.br`.
- Front Vite/React em hospedagem estatica, com `VITE_API_BASE_URL=https://api.seu-dominio.com.br`.

## Backend na VPS

Instale dependencias:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git nginx certbot python3-certbot-nginx
```

Crie a pasta da aplicacao:

```bash
sudo mkdir -p /opt/legacydoc/backend /opt/legacydoc/storage /opt/legacydoc/tmp
sudo chown -R $USER:$USER /opt/legacydoc
```

Envie o conteudo de `legacyDoc/legacyDoc` para `/opt/legacydoc/backend`.

Configure:

```bash
cd /opt/legacydoc/backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
nano .env
```

Variaveis principais:

```env
OPENAI_API_KEY=sua-chave
JWT_SECRET_KEY=gere-um-segredo-longo
DATABASE_PATH=/opt/legacydoc/storage/legacydoc.db
LEGACYDOC_DATA_DIR=/opt/legacydoc/storage
LEGACYDOC_TMP_DIR=/opt/legacydoc/tmp
ALLOWED_ORIGINS=https://seu-front.com.br
LEGACYDOC_LINES_PER_CHUNK=150
LEGACYDOC_MAX_REVIEW_ATTEMPTS=1
```

Crie o servico:

```ini
[Unit]
Description=Legacy Doc API
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/legacydoc/backend
EnvironmentFile=/opt/legacydoc/backend/.env
ExecStart=/opt/legacydoc/backend/.venv/bin/uvicorn api.api:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Suba:

```bash
sudo chown -R www-data:www-data /opt/legacydoc
sudo systemctl daemon-reload
sudo systemctl enable --now legacydoc
```

## Nginx

```nginx
server {
    server_name api.seu-dominio.com.br;

    client_max_body_size 10m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Ative HTTPS:

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d api.seu-dominio.com.br
```

## Front

Na hospedagem estatica, configure:

```env
VITE_API_BASE_URL=https://api.seu-dominio.com.br
```

Build:

```bash
npm ci
npm run build
```

Publique a pasta `dist`.
