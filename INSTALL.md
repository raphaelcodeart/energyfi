# Installazione su un server nuovo (per Claude Code)

Questa guida porta da un server Ubuntu vuoto a un'installazione **SOS
Affiliate** funzionante e online in HTTPS, per un **nuovo cliente**.
È scritta per essere eseguita da Claude Code dall'inizio alla fine: ogni passo
ha un comando e un risultato atteso. Se il risultato non torna, **fermati lì**
e risolvi prima di andare avanti.

Il repository contiene tutto il codice, la configurazione e la struttura
completa del database (`docs/database-schema.sql`, solo struttura, **nessun
dato**). Il database nasce vuoto: nessuna persona, nessun ordine, nessun dato
del cliente originale.

> Approfondimenti: `CLAUDE.md` (regole operative, da leggere prima di
> modificare il codice) e `docs/server-migration-guide.md` (guida lunga,
> problemi già risolti in §8).

---

## 0. Da chiedere all'utente prima di iniziare

Chiedi queste cose **tutte insieme**, prima di toccare il server:

| Valore | Esempio | Note |
|---|---|---|
| Nome del cliente | `SOS Rossi` | nome visibile nell'app |
| Ragione sociale | `Rossi S.r.l.` | |
| Dominio dell'app | `sos.rossi.it` | il record DNS **A** deve già puntare all'IP di questo server |
| Email del primo amministratore | `admin@rossi.it` | |
| Il server è dedicato? | sì / no | se 80/443 sono già usate da altro, usa 8080/8443 |

Non chiedere chiavi di servizi esterni (Mamify, SMTP, Stripe, Google Drive):
**non servono per installare**. Si collegano dopo, dall'interfaccia o dal `.env`.

Verifica il DNS prima di proseguire:

```bash
DOMAIN=sos.rossi.it                       # il dominio dato dall'utente
getent hosts "$DOMAIN"; curl -s -4 ifconfig.me; echo
# atteso: lo stesso IP sulle due righe
```

## 1. Prerequisiti del server

Server Ubuntu 22.04/24.04 con almeno **4 GB di RAM** e **40 GB di disco**
(le build Docker occupano molto: con meno di 10 GB liberi falliscono).

```bash
apt-get update
apt-get install -y docker.io docker-compose-v2 git openssl certbot cron
systemctl enable --now docker
docker compose version          # atteso: v2.x
df -h /                         # atteso: almeno 10 GB liberi
```

## 2. Codice

```bash
git clone <URL-del-repository> /opt/sosnet
cd /opt/sosnet
```

Usa proprio **`/opt/sosnet`**: il nome della cartella diventa il nome del
progetto Docker (`sosnet`), e gli script (es. `renew-cert.sh`, che ricarica
`sosnet-nginx-1`) si aspettano questo nome. Il nome del prodotto si cambia dopo,
non qui.

## 3. File `.env` con segreti nuovi

```bash
cd /opt/sosnet
cp .env.example .env
chmod 600 .env

PG_PASS=$(openssl rand -hex 24)
MINIO_USER=sosnet-$(openssl rand -hex 4)
MINIO_PASS=$(openssl rand -hex 24)
JWT=$(openssl rand -hex 48)

sed -i \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$PG_PASS|" \
  -e "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+psycopg://sosnet:$PG_PASS@postgres:5432/sosnet|" \
  -e "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=$JWT|" \
  -e "s|^MINIO_ROOT_USER=.*|MINIO_ROOT_USER=$MINIO_USER|" \
  -e "s|^MINIO_ROOT_PASSWORD=.*|MINIO_ROOT_PASSWORD=$MINIO_PASS|" \
  -e "s|^S3_ACCESS_KEY=.*|S3_ACCESS_KEY=$MINIO_USER|" \
  -e "s|^S3_SECRET_KEY=.*|S3_SECRET_KEY=$MINIO_PASS|" \
  -e "s|^NEXT_PUBLIC_APP_URL=.*|NEXT_PUBLIC_APP_URL=https://$DOMAIN|" \
  -e "s|^PUBLIC_APP_BASE_URL=.*|PUBLIC_APP_BASE_URL=https://$DOMAIN|" \
  .env
```

Server **non** dedicato (80/443 occupate): metti anche
`HTTP_PORT=8080` e `HTTPS_PORT=8443` nel `.env`, e usa
`https://$DOMAIN:8443` nei due URL qui sopra.

Verifica: nessun segreto vuoto.

```bash
grep -E '^(POSTGRES_PASSWORD|JWT_SECRET_KEY|MINIO_ROOT_USER|MINIO_ROOT_PASSWORD|S3_ACCESS_KEY|S3_SECRET_KEY)=$' .env
# atteso: nessuna riga
```

`ENVIRONMENT=development` e `docker-compose.dev.yml` sono **l'installazione
reale**, non un ambiente di prova (vedi `CLAUDE.md` §1). Lasciali così.

## 4. Dominio in nginx

```bash
./scripts/configure-domain.sh "$DOMAIN"           # server dedicato
# ./scripts/configure-domain.sh "$DOMAIN" 8443    # se usi 8443
```

Atteso: le righe stampate mostrano `server_name $DOMAIN _;` e i certificati
in `/etc/letsencrypt/live/$DOMAIN/`.

## 5. Certificato provvisorio, poi build e avvio

nginx non parte senza un certificato: ne creiamo uno provvisorio, valido un
giorno, che sostituiremo al passo 7.

```bash
mkdir -p certbot/www "certbot/conf/live/$DOMAIN"
openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
  -keyout "certbot/conf/live/$DOMAIN/privkey.pem" \
  -out "certbot/conf/live/$DOMAIN/fullchain.pem" -subj "/CN=$DOMAIN"

docker compose -f docker-compose.dev.yml build      # 10-20 minuti
docker compose -f docker-compose.dev.yml up -d
```

Il container `api` esegue da solo `alembic upgrade head` e crea l'intero
schema. **Non** caricare `docs/database-schema.sql` a mano: è il riferimento
per il confronto (passo 9), non il metodo di installazione.

```bash
docker compose -f docker-compose.dev.yml ps
# atteso: postgres, redis, minio, api, celery-worker, celery-beat,
#         celery-mamify, dashboard, nginx — tutti Up (healthy dove previsto)
```

## 6. Organizzazione e primo amministratore

```bash
docker compose -f docker-compose.dev.yml exec api python -m app.seed.bootstrap \
  --organization-name "SOS Rossi" \
  --legal-name "Rossi S.r.l." \
  --admin-email "admin@rossi.it"
```

L'output stampa **una sola volta** la password dell'amministratore e
l'`Organization ID`. Salva la password in un file protetto e dalla
all'utente alla fine:

```bash
umask 077; mkdir -p /root/backup
# scrivi email + password in /root/backup/sosnet-admin.txt
```

Poi scrivi l'Organization ID nel `.env` e **ricostruisci la dashboard**
(l'id entra nel codice al momento della build: senza questo passo **ogni
login fallisce** con «credenziali non valide»):

```bash
ORG_ID=<Organization ID stampato sopra>
sed -i "s|^NEXT_PUBLIC_DEFAULT_ORGANIZATION_ID=.*|NEXT_PUBLIC_DEFAULT_ORGANIZATION_ID=$ORG_ID|" .env
docker compose -f docker-compose.dev.yml build dashboard
docker compose -f docker-compose.dev.yml up -d dashboard
```

## 7. Certificato vero (Let's Encrypt)

Serve la porta 80 raggiungibile da Internet (anche con `HTTP_PORT=8080`
Let's Encrypt chiama sempre la 80: in quel caso chiedi all'utente come
instradarla).

```bash
rm -rf certbot/conf && mkdir -p certbot/conf      # via il provvisorio
certbot certonly --webroot -w certbot/www -d "$DOMAIN" \
  --config-dir certbot/conf --work-dir certbot/work --logs-dir certbot/logs \
  --register-unsafely-without-email --agree-tos --non-interactive

# Ricreare il container, non solo reload: il mount punta alla cartella vecchia
docker compose -f docker-compose.dev.yml up -d nginx --force-recreate
docker exec sosnet-nginx-1 nginx -t                # atteso: syntax is ok
curl -sI "https://$DOMAIN/login" | head -1         # atteso: HTTP/2 200
```

Se `certbot` fallisce, non andare avanti: l'app funziona solo in HTTPS
(il cookie di sessione è `Secure`, su HTTP il login non fa niente).

## 8. Attività pianificate (rinnovo certificato e backup)

```bash
( crontab -l 2>/dev/null
  echo "0 3 * * * /opt/sosnet/scripts/renew-cert.sh >> /opt/sosnet/certbot/renew.log 2>&1"
  echo "30 2 * * * cd /opt/sosnet && ./scripts/backup.sh dev >> /opt/sosnet/backups/backup.log 2>&1"
) | crontab -
crontab -l
```

## 9. Verifiche finali

```bash
cd /opt/sosnet
./scripts/health-check.sh                 # atteso: All health checks passed.

docker compose -f docker-compose.dev.yml exec -T postgres psql -U sosnet -d sosnet -tAc \
  "SELECT version_num FROM alembic_version"
# atteso: l'ultimo file in apps/api/alembic/versions/ (oggi 0010)

docker compose -f docker-compose.dev.yml exec -T postgres psql -U sosnet -d sosnet -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'"
grep -c 'CREATE TABLE' docs/database-schema.sql
# atteso: lo stesso numero (oggi 114)
```

Confronto severo dello schema (nessuna differenza attesa, a parte le righe
`\restrict`/`\unrestrict` che cambiano a ogni esecuzione):

```bash
./scripts/dump-schema.sh dev && git diff --stat docs/database-schema.sql
git checkout docs/database-schema.sql      # rimetti il file del repository
```

Infine il login vero: apri `https://$DOMAIN/login` con l'email e la password
del passo 6. Deve aprirsi la dashboard di amministrazione.

## 10. Da riferire all'utente alla fine

- URL dell'app, email dell'amministratore, dove sta la password
  (`/root/backup/sosnet-admin.txt`);
- cosa resta da collegare, tutto facoltativo e dall'interfaccia o dal `.env`:
  - **Mamify** (rete, ordini, wallet): credenziali dal pannello Mamify
    dell'app. Mamify si usa **solo in lettura**: mai scrivere, creare o
    cancellare nulla su Mamify (`docs/mamify-integration.md`);
  - **SMTP** per le email (reset password): `SMTP_*` nel `.env`, poi
    `up -d api celery-worker --force-recreate`;
  - IBAN per i bonifici: `COMPANY_BANK_IBAN`/`COMPANY_BANK_HOLDER`;
- cosa è ancora come il cliente originale e andrà personalizzato: nome e logo
  (`apps/dashboard/public/logo.png`, `logo-light.png`), colori, testi, piano
  compensi (`apps/api/app/modules/affiliate/plan.py`, modificabile come nuova
  versione dal pannello).

## Problemi tipici

| Sintomo | Causa |
|---|---|
| Login: «credenziali non valide» con la password giusta | `NEXT_PUBLIC_DEFAULT_ORGANIZATION_ID` vuoto o sbagliato, o dashboard non ricostruita dopo averlo scritto (passo 6) |
| Login: la pagina si ricarica senza errori | Il sito è in HTTP, non HTTPS (passo 7) |
| Il codice cambia ma il sito no | Le immagini sono cotte: serve `build` + `up -d`, non `restart` |
| nginx non parte | Manca il certificato in `certbot/conf/live/$DOMAIN/` (passo 5) |
| Build fallita con `no space left on device` | `docker builder prune -f && docker image prune -f` e riprova |
| `celery-worker`/`celery-beat` con il codice vecchio | servono `--force-recreate` |
