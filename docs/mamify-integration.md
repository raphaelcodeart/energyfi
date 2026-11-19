# SOS Affiliate collegato a Mamify (sola lettura)

Fonte: *Mamify — Documentazione API per la web app* (1 novembre 2026,
`https://condividiamo.club/documentazione_api_mamify_per_la_web_app-1.pdf`),
più le risposte vere delle API lette il 4 novembre 2026 con la chiave della
web app.

## 0. Regola principale: Mamify si legge e basta

Mamify è la fonte. SOS Affiliate **non crea, non modifica e non cancella mai
nulla su Mamify**: niente registrazione di webhook, niente voucher o accrediti
sui portafogli, niente cambi di stato degli ordini. Lo ha chiesto l'utente il
4/11/2026 ed è imposto dal codice:

- `client.READ_ONLY_PATHS` elenca gli unici percorsi chiamabili: le API di
  servizio `plugins/mamify/rag/*` («Sola lettura» nella documentazione) e
  `plugins/mamify/auth/login`, che controlla la password di chi entra in SOS e
  non cambia i dati di Mamify;
- qualunque altro percorso viene rifiutato **prima** di partire
  (`write_blocked`). Il test `test_client_blocks_writes_before_any_request` lo
  verifica, e il finto Mamify dei test fallisce se riceve un percorso fuori
  lista.

Aggiungere un percorso alla lista è una decisione esplicita, da prendere solo
per percorsi che leggono.

## 1. Chi fa cosa

| | Mamify | SOS Affiliate (questa app) |
|---|---|---|
| Persone, account, password | sì | legge (accesso con le credenziali Mamify) |
| Albero sponsor | sì | ne tiene una copia identica |
| Acquisti e pagamenti | sì | legge gli ordini pagati |
| Piano compensi (BC, BD, BM, rivendite) | no | sì: `modules/affiliate`, invariato |
| Pagamento dei compensi su MamiCash/Mamix | sì, lo staff Mamify | dà la lista dei dovuti con il cliente Mamify di ognuno |

## 2. Dove sta il codice

```
apps/api/app/modules/mamify/
  client.py    chiamate HTTP: lista dei percorsi ammessi, limite di chiamate, 429
  parsing.py   lettura delle risposte (forme vere), riconoscimento dei prodotti
  models.py    sn_mamify_config, _members, _products, _orders, _webhook_events (+ _payouts, solo storico)
  service.py   configurazione, copia della rete, nuovi iscritti, ordini, prodotti, accesso
  router.py    /api/mamify/admin/* e il webhook pubblico
apps/api/app/modules/affiliate/tree.py   l'albero a rami per l'interfaccia
apps/api/alembic/versions/0008_mamify.py, 0009_mamify_read_only.py
apps/api/tests/test_mamify_{parsing,flows}.py
apps/dashboard/components/affiliate/mamify-panel.tsx   «Collegamento Mamify»
apps/dashboard/components/affiliate/network-tree.tsx   l'albero (admin e Digital Ambassador)
```

## 3. Le API vere (4/11/2026)

- Ogni chiave ha **60 chiamate al minuto** (`X-RateLimit-*` su ogni risposta).
- `rag/customer/find` → `{"customer": {id, first_name, last_name, email, phone,
  registration_date, invite_code}, "sponsor": {...}|null, "network": {"direct", "total"}}`.
- `rag/customer/network` con `scope: "all"` → tutta la rete sotto la persona,
  **50 righe per pagina** (anche se si chiede di più), **dalla più recente**:
  `{id, first_name, last_name, email, phone, registration_date, level,
  sponsor_id, direct, total}`. Senza `scope` dà solo i diretti. Il parametro
  `app` non è accettato (`wrong_params`).
- `rag/customer/orders` vuole sempre il cliente: **non esiste un elenco di
  tutti gli ordini**. Righe: `{id, date, status ("0", "3"…), status_label,
  paid, total, products: [{name, quantity, price, type, app}], status_history}`,
  dalla più recente. **Le righe non hanno l'id del prodotto.**
- `rag/products/search` con `app` → i prodotti di un'app, con id, nome,
  prezzo, prezzo promozionale, categorie.
- Stati visti finora: `0` «In attesa di pagamento» (`paid: false`), `3`
  «Completato» (`paid: true`). Gli altri (annullato, rimborsato…) non sono
  ancora comparsi: i loro nomi sono configurabili.

La cima vera della rete è **Condividiamo Ltd (cliente 317)**, senza sponsor:
50.822 persone, 47.714 dirette (4/11/2026).

## 4. La rete

- **Copia completa** (`sync_network`): legge tutte le pagine di `scope: "all"`
  sotto la cima configurata (circa 1.020 chiamate, 20 minuti) e porta l'albero
  SOS a essere identico. Persone nuove aggiunte, sponsor cambiati spostati con
  tutto il ramo (`network.service.move_agent`, storico conservato, mesi chiusi
  intatti), persone sparite segnate «uscito» con i loro punti. Chi non cambia
  non costa scritture. Gira ogni notte alle 2:15 UTC e dal pulsante «Copia
  tutta la rete adesso»; la pagina mostra l'avanzamento.
- **Nuovi iscritti** (`sync_new_members`): legge le prime pagine finché trova
  qualcuno già copiato (gli id crescono nel tempo e la lista parte dal più
  recente): una o due chiamate. Ogni 5 minuti, e subito quando arriva un avviso
  `customers/new`. Sponsor cambiati e uscite aspettano la copia della notte.
- La cima è l'azienda: non entra nell'albero, i suoi diretti sono la prima
  riga. Ogni persona è un nodo con codice `MF<id Mamify>`.
- Una sola copia per volta (campo `network_sync_started_at`, scade dopo due ore
  se un giro si interrompe).
- **Aggiorna rete di una persona** (`sync_branch`, pulsante «Aggiorna rete» nella
  scheda del collaboratore, nell'albero e nella rete del collaboratore): rilegge
  da Mamify solo il ramo di quella persona (`find` + `network` con `scope: "all"`
  sotto di lei, 1 chiamata ogni 50 persone; Michele Novarese, 304 persone: 9
  chiamate, 15 secondi). Aggiunge i nuovi, sposta chi ha cambiato sponsor; chi è
  nel ramo SOS ma non più in quello Mamify viene cercato uno per uno (al massimo
  40): spostato sotto il nuovo sponsor o segnato uscito (`customer_not_found`).
  I livelli che Mamify dà sotto una persona partono da lei e vengono riportati a
  quelli dalla cima. Rami oltre 10.000 persone: lasciati alla copia della notte.
  Gira nella coda `mamify` (`mamify_branch_task`), una lettura di rete per volta;
  si può ripetere dopo 1 minuto (admin) o 15 minuti (il Digital Ambassador per sé).
  Esito salvato in `sn_mamify_members.branch_sync_*` (migrazione 0010).

## 5. Gli ordini

1. **Lettura a turno** (`poll_orders`): Mamify dà gli ordini una persona alla
   volta, quindi ogni 2 minuti si leggono gli ultimi 50 ordini di N persone
   (N = «persone al minuto» × 2, predefinito 30 al minuto). Metà delle
   chiamate va a chi ha una rete sotto o ordini già salvati, se non è stato
   letto nell'ultima ora; l'altra metà a chi è stato letto da più tempo (prima
   chi non lo è mai stato). Con 50.000 persone e 30 al minuto, ognuno è letto
   circa una volta al giorno, chi conta di più ogni ora.
2. **Solo gli ordini SOS si salvano**: almeno una riga di un'app SOS
   (`order_apps`, predefinito `sos-affiliate` e `digitalambassador`) o di un
   prodotto abbinato. Il resto (gift card, altre app) non viene registrato.
3. **Riconoscimento del prodotto**: dato che le righe hanno solo app, nome e
   prezzo, `parsing.resolve_line` le confronta con il catalogo
   (`rag/products/search` delle app SOS, riletto a ogni copia completa). Stesso
   nome in due prodotti (il «Pacchetto Start» annuale da 1.000 € e mensile da
   97 €): decide il prezzo, anche promozionale. Se resta ambiguo, la riga non
   viene indovinata: compare tra i «non abbinati».
4. Un ordine pagato (`paid: true`, o uno stato in «altri stati pagato»)
   diventa un'operazione **già confermata** per ogni unità di ogni prodotto
   abbinato. Chiave di idempotenza `MAMIFY:<ordine>:<riga>:<unità>`: lo stesso
   ordine letto cento volte conta una volta.
   - Mensilità, licenze e biglietti: compratore = Digital Ambassador.
   - Pack e ricariche MamiCash: compratore = impresa cliente, venditore = il
     suo sponsor Mamify. Per la ricarica la base del BM è il valore della riga.
5. Uno stato «annullato o rimborsato» rettifica le operazioni
   (`reverse_operation`). Gli altri cambi di stato di un ordine già applicato
   non cambiano nulla.
6. Gli ordini non applicabili restano visibili con il motivo: acquirente non
   ancora nella rete (si riapplicano dopo la copia), prodotto non abbinato (si
   riapplicano appena lo si abbina), errore.
7. **Webhook facoltativi**: se lo staff Mamify registra dal CRM gli avvisi
   `orders/new`, `orders/status_update`, `customers/new` verso gli indirizzi
   della pagina, gli ordini arrivano in pochi secondi. SOS non li registra (è
   una scrittura). Gli avvisi passano dallo stesso percorso di prima: salvati,
   doppioni scartati, ordine applicato una volta.

### Schermate Vendite → Ordini e Vendite → Clienti

- **Ordini** (`GET /mamify/admin/orders/page`): ordini SOS letti da Mamify, 25 per
  pagina, ricerca per acquirente, email o numero, schede per esito, totale
  pagato, avanzamento della lettura (persone lette sul totale).
- **Clienti** (`GET /mamify/admin/customers/page`): i clienti Mamify con i loro
  ordini SOS (predefinito: solo chi ha ordini; oppure tutti), sponsor, contatti,
  quando sono stati letti; «Leggi ordini ora» legge subito un cliente (una
  chiamata, `POST /mamify/admin/customers/{id}/read-orders`). Le anagrafiche del
  vecchio modulo contratti restano nella seconda scheda.

## 6. Prodotti abbinati (4/11/2026)

| Prodotto Mamify | id | Prezzo | Piano |
|---|---|---|---|
| Digital Ambassador (sos-affiliate) | 17292 | 49 € | DIGITAL_AMBASSADOR |
| 2 Licenze (digitalambassador) | 17294 | 400 € (listino 1.000) | SMALL |
| 5 Licenze (digitalambassador) | 17296 | 800 € (listino 2.500) | MEDIUM |
| 12 Licenze (digitalambassador) | 17297 | 1.600 € (listino 6.000) | LARGE |
| Pacchetto Start annuale | 17280 | 1.000 € | START |
| Pacchetto Business annuale | 17281 | 2.000 € | BUSINESS |
| Pacchetto Premium annuale | 17282 | 4.000 € | PREMIUM |
| Pacchetto International annuale | 17290 | 10.000 € | INTERNATIONAL |

Il codice del piano `LICENSE_RESALE` («Rivendita licenza a un'impresa»,
17/11/2026) serve per abbinare il «Licenze» 500 €: vedi `sos-affiliate.md`
§5b. Finché non lo si abbina, nulla cambia.

Non abbinati, da decidere (`open-questions.md` §21): «Licenze» 500 € (17293,
categoria Business Partner, 500 MamiCash all'acquirente: sembra la rivendita
di una licenza a un'impresa) e i quattro pacchetti mensili (97, 197, 397,
997 €: 17285, 17284, 17283, 17291), che il piano non prevede.

## 7. Compensi

Si calcolano qui come sempre. Li paga lo staff Mamify: la scheda «Compensi da
pagare» elenca i dovuti con id ed email Mamify del beneficiario e li scarica in
CSV. Pagati, si segnano come pagati in «Compensi BC · BD · BM». La vecchia
modalità con i voucher è stata tolta (migrazione 0009 cancella la password
salvata); la tabella `sn_mamify_payouts` resta come storico.

## 7b. Saldi nella home

La home del Digital Ambassador mostra i saldi veri dei suoi portafogli Mamify:
`rag/customer/wallets` (sola lettura) per il suo cliente Mamify, con MAMIX,
MamiCash personale e aziendale. La risposta resta in memoria 2 minuti; se
Mamify non risponde si vedono gli ultimi saldi letti. I movimenti
(`rag/customer/transactions`) chiedono `wallet=mamix` o `wallet=mamicash`.

## 8. Accesso

Chi è nella rete entra con email e password di Mamify. Se l'accesso locale
fallisce, Sosnet prova `auth/login` su Mamify: è un controllo della password e
non cambia nulla dei dati di Mamify. Se va a buon fine e la persona è nella
rete copiata, crea (o allinea) il suo accesso locale con ruolo PROMOTER. Un
account locale che non è di quella persona non viene mai toccato.

## 9. L'albero nell'interfaccia

Con decine di migliaia di persone l'albero non si manda intero al browser.
`affiliate/tree.py` calcola una volta (in memoria per 90 secondi) volumi del
mese, grandezza dei rami, gambe, livelli e contatti, e le API danno un ramo
per volta: `GET /affiliate/admin/network/branch?root=&offset=&limit=&sort=&active=`
e `/affiliate/admin/network/search?q=`; per il Digital Ambassador le stesse
sotto `/affiliate/me/network/*`, limitate al suo ramo (nessuno sopra di lui è
mai mostrato). L'interfaccia apre i rami uno alla volta, 100 persone per
volta, prima i più grandi. La copia in memoria, passati i 90 secondi, viene
servita subito e ricostruita in sottofondo.

Solo per il Digital Ambassador c'è anche la **versione virtuale** (3D):
`/affiliate/me/network/galaxy` manda tutto il suo ramo in una volta (massimo
5.000 persone, senza email e telefono), così nella scena non si aspetta mai il
server. Per l'admin non esiste: l'intera rete sarebbe troppo grande.

## 10. Lavori Celery

Tutte le letture di Mamify girano in una coda propria, `mamify`, servita dal
worker `celery-mamify` con una sola esecuzione alla volta, così il limite di
60 chiamate al minuto si divide in ordine:

| Lavoro | Quando |
|---|---|
| `mamify_sync_network_task` (copia completa) | 2:15 UTC ogni notte |
| `mamify_new_members_periodic_task` | ogni 5 minuti (scade dopo 4 se in coda) |
| `mamify_orders_task` (ordini a turno + riapplica in sospeso) | ogni 2 minuti (scade dopo 100 s se in coda) |
| `mamify_full_sync_task`, `mamify_new_members_task` | dai pulsanti e dall'avviso `customers/new` |
