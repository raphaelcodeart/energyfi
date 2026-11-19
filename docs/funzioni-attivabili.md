# Funzioni attivabili

Alcune parti della piattaforma si possono **spegnere e riaccendere** senza
toccare il codice. Spegnere **nasconde**, non cancella: dati, saldi, ordini e
movimenti restano nel database e tornano visibili appena la funzione viene
riaccesa. Ogni cambio viene registrato nel registro delle attività.

## Le funzioni

| Nome tecnico | Nome nel pannello | Predefinito | Cosa accende |
|---|---|---|---|
| `external_wallet` | Saldi MAMIX e CASHBACK (wallet partner) | **acceso** | I riquadri Saldo MAMIX, Saldo CASHBACK e Totale utilizzo nella home di promoter e clienti. |
| `profile_gate` | Profilo obbligatorio al primo accesso | spento | La finestra che blocca la dashboard finché non si compilano codice fiscale e residenza. Spento, i dati si compilano quando si vuole da **Il mio profilo**. |
| `friend_referrals` | Porta un amico | spento | La lista a un livello degli amici invitati, il conteggio e il premio: voci *Porta un amico* (clienti e promoter) e *Premi invito* (admin). |
| `wallet` | Portafoglio SosnetCash | spento | Saldi, ricariche, trasferimenti, pagamento con SosnetCash nel negozio e accredito automatico del cashback su contratti e ordini. Spento, *Movimenti contabili* e *Contabilità* mostrano solo i pagamenti con bonifico e carta. |
| `invoice_cashback` | Incassa il cashback (riscatto fatture) | spento | Il riscatto delle fatture dei partner in cashback: voci *Incassa il cashback* (clienti e promoter), *Riscatti fatture* e *Partner e forniture* (admin). **Funziona solo con `wallet` acceso.** |
| `welcome_bonus` | Omaggio di benvenuto | spento | Il riquadro *Riscatta il tuo omaggio* in home, con SosnetCash di benvenuto. **Funziona solo con `wallet` acceso.** |
| `dropshipping` | Shop dropshipping | spento | I negozi dei fornitori esterni CJ, Shopify e AliExpress, lato admin e nel Negozio dei clienti. *Fai la Spesa con Sosnet* e il catalogo restano sempre visibili. |

Una funzione che dipende da un'altra spenta risulta *In attesa*: la puoi
accendere, ma si attiva davvero solo quando accendi anche quella da cui dipende.

## Come riaccendere (dal sito)

1. Entra come **superadmin** (`admin@mamify.ai`).
2. Apri **Sistema → Impostazioni**.
3. In cima c'è il riquadro **Funzioni**: premi l'interruttore della funzione.
   - **Accendi tutto** accende ogni funzione in un colpo.
   - **Configurazione iniziale** riporta tutto ai valori predefiniti della
     tabella qui sopra.

Il cambio vale subito per tutti; chi è già nel sito lo vede entro un minuto o
ricaricando la pagina.

## Come riaccendere (da terminale)

Dal server, nella cartella `/opt/sosnet`:

```bash
# vedere com'è configurato adesso
docker compose -f docker-compose.dev.yml exec -T api python -m app.seed.features --organization-name SOSNET

# accendere tutto
docker compose -f docker-compose.dev.yml exec -T api python -m app.seed.features --organization-name SOSNET --enable all

# accendere solo alcune funzioni
docker compose -f docker-compose.dev.yml exec -T api python -m app.seed.features --organization-name SOSNET --enable wallet welcome_bonus invoice_cashback

# spegnerne una
docker compose -f docker-compose.dev.yml exec -T api python -m app.seed.features --organization-name SOSNET --disable dropshipping

# tornare alla configurazione iniziale
docker compose -f docker-compose.dev.yml exec -T api python -m app.seed.features --organization-name SOSNET --defaults
```

## Prompt pronto per Claude

Se vuoi che sia Claude a rimettere tutto com'era, puoi scrivergli:

> Nel progetto /opt/sosnet riaccendi tutte le funzioni opzionali descritte in
> `docs/funzioni-attivabili.md` (portafoglio SosnetCash, incassa il cashback,
> omaggio di benvenuto, porta un amico, shop dropshipping e profilo
> obbligatorio) usando `python -m app.seed.features --enable all` nel
> container api, poi verifica dal sito che le voci siano tornate visibili
> nelle aree admin, promoter e cliente.

## Dove sta nel codice (per gli sviluppatori)

- Elenco, valori predefiniti e dipendenze: `apps/api/app/modules/organizations/service.py` (`FEATURE_DEFAULTS`, `FEATURE_REQUIRES`).
- Valori salvati: tabella delle organizzazioni, campo `settings`, chiavi `feature_<nome>`.
- API: `GET /api/organizations/me/features` (tutti), `GET /me/features/switches` e `PATCH /me/features` (superadmin).
- Blocchi lato server: `apps/api/app/modules/organizations/features.py` (`require_feature`).
- Interfaccia: `apps/dashboard/lib/features.ts` (quali sezioni dipendono da quale funzione) e `components/admin-features-card.tsx` (il pannello).
- Comando da terminale: `apps/api/app/seed/features.py`.

## Saldi MAMIX e CASHBACK

Le due monete stanno nel wallet di un'azienda partner, che fornirà un'API.
Finché non è collegata, i riquadri mostrano «—» e «Collegamento al wallet in
arrivo». Per collegarla:

1. salvare l'indirizzo dell'API del partner nelle impostazioni
   dell'organizzazione (chiave `external_wallet_api_url`; facoltativo il nome
   del fornitore in `external_wallet_provider_name`);
2. implementare la chiamata in
   `apps/api/app/modules/external_wallet/service.py::fetch_balances`, l'unico
   punto da toccare: la pagina legge già da `GET /api/external-wallet/me`.
