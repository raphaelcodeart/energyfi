# Stato dei lavori

Aggiornato alla fine di ogni sessione di lavoro: una voce per sessione, in
italiano, che dice cosa è cambiato **e perché**. `architecture.md` descrive
l'obiettivo, questo file descrive la realtà.

## 2026-11-04 — Mamify in sola lettura, sui dati veri

**Perché.** L'utente ha dato la chiave API e ha posto una regola: Mamify non
si modifica mai, si legge soltanto. Con i dati veri sono cambiate anche le
ipotesi: la rete ha 50.822 persone sotto Condividiamo Ltd, Mamify ne dà 50 per
chiamata con 60 chiamate al minuto, non esiste un elenco di tutti gli ordini e
le righe d'ordine non hanno l'id del prodotto.

**Cosa.**
- `client.py`: lista chiusa dei percorsi ammessi (`rag/*` e `auth/login`),
  tutto il resto rifiutato prima di partire; rispetto del limite di chiamate
  e attesa sui 429. Tolti voucher, storico voucher e registrazione webhook;
  migrazione 0009 cancella la password del conto aziendale salvata.
- Rete: copia completa notturna (circa 20 minuti) con avanzamento visibile, e
  nuovi iscritti ogni 5 minuti e su avviso `customers/new` (una o due
  chiamate). Worker dedicato `celery-mamify`, coda `mamify`, una esecuzione
  alla volta.
- Ordini: lettura a turno persona per persona, prima chi ha una rete o ordini
  aperti; salvati solo gli ordini delle app SOS; prodotto riconosciuto da app,
  nome e prezzo sul catalogo `rag/products/search`.
- Albero: `affiliate/tree.py` e le API `network/branch` e `network/search`;
  l'interfaccia apre un ramo alla volta. Elenco affiliati limitato ai primi
  300 con ricerca.
- Compensi: lista dei dovuti con cliente Mamify e CSV, pagati dallo staff
  Mamify.
- Verificato: 728 test; collegamento provato sulla chiave vera; 8 prodotti
  abbinati (tabella in `mamify-integration.md` §6).
- Errore trovato alla prima copia vera: il worker Celery importava a mano solo
  una parte dei modelli, e senza `commercial` ogni nuovo nodo falliva con
  NoReferencedTableError (i test non lo vedevano perché importano tutto).
  Ora `celery_app` importa tutti i `app.modules.*.models`; il test
  `test_celery_models.py` lo controlla in un processo separato.

## 2026-11-03 — Dominio net.mamify.ai

**Perché.** Serve un indirizzo vero con certificato valido, anche perché
Mamify possa mandare i webhook. Le porte 80/443 sono di Aginet, che ora
inoltra `net.mamify.ai` al nginx di Sosnet (8443). Dettagli e passi in
`server-migration-guide.md`, «Dominio pubblico». Verificato: certificato Let's
Encrypt valido, login amministratore e `webhook_url` su `https://net.mamify.ai`.

## 2026-11-03 — SOS Affiliate collegato a Mamify

**Perché.** Le persone comprano su Mamify, che ha già account, rete e
portafogli MamiCash/Mamix. SOS Affiliate deve solo leggere rete e ordini da
lì, calcolare il piano e accreditare i compensi sui portafogli Mamify, da cui
le persone chiedono il prelievo. Dettagli: `mamify-integration.md`.

- [x] Modulo `mamify` (client API, lettura tollerante delle risposte, servizi,
  rotte) e migrazione `0008`: sei tabelle `sn_mamify_*` e l'id Mamify sulle
  imprese clienti.
- [x] Copia della rete Mamify nell'albero SOS ogni 15 minuti, con spostamenti
  storicizzati e persone uscite segnate, non cancellate.
- [x] Ordini pagati su Mamify → operazioni confermate, una per unità, con la
  riga d'ordine come chiave di idempotenza; ordini annullati o rimborsati →
  rettifica. Webhook su `/api/mamify/webhook/<token>/…` (nginx) più un
  controllo ogni 10 minuti per i webhook persi.
- [x] Compensi accreditati sui portafogli Mamify con un voucher del conto
  aziendale, al più una volta per compenso; esito incerto mai rimandato da
  solo.
- [x] Accesso degli affiliati con email e password di Mamify.
- [x] Nuovo albero della rete (admin «Albero della rete», affiliato «La mia
  rete»): rami apribili, ricerca, apertura di un solo ramo con percorso,
  riepilogo per profondità, scheda con gambe e requisiti del livello
  successivo. Pagina admin «Collegamento Mamify». «Acquista» rimanda a Mamify
  quando il collegamento è attivo.
- [x] Test: `test_mamify_parsing.py`, `test_mamify_flows.py` (finto server
  Mamify).
- [ ] Prova con la chiave API vera, dominio con certificato valido per i
  webhook, domande di `open-questions.md` §21.

## 2026-11-03 — Nascita di SOSNET come applicazione indipendente

**Perché.** Serviva un secondo software con la stessa base tecnica ma
nessun legame con l'installazione da cui è nato: due prodotti separati che
possono evolvere ciascuno per conto suo.

- [x] Codice copiato in `/opt/sosnet` senza storia git, `.env`, backup,
  certificati né dipendenze installate; repository git nuovo.
- [x] Nomi interni tutti SOSNET: tabelle `sn_*`, modulo `sosnet_market`,
  SosnetCash, bucket `sosnet-documents`/`sosnet-media`, database `sosnet`
  (test su `sosnet_test`). Gradi SosPromoter SP1-3, SosLeader SL1-4,
  SosManager SM1-5.
- [x] Identità provvisoria blu (`#0a54e0`) con accento ciano: i rossi e i
  magenta della scena sono stati ruotati di tonalità mantenendo luminosità e
  saturazione, quindi i contrasti restano quelli già verificati. Wordmark e
  icone provvisori in `apps/dashboard/public` e `app/`.
- [x] Stack Compose `sosnet` con segreti propri, nginx su 8080/8443, dominio
  temporaneo sslip.io con certificato autofirmato. Le email usano
  `PUBLIC_APP_BASE_URL` per logo e link: nessun dominio è più scritto nel
  codice.
- [ ] Dominio definitivo, certificato Let's Encrypt, casella SMTP propria,
  logo vero.

## 2026-11-03 — SOS Affiliate: il progetto unico di questa installazione

**Perché.** SOSNET ospita una sola rete aziendale, quella di SOS Affiliate,
con regole precise e verificabili (specifica tecnica v1.1 e piano compensi
del 29/10/2026). Il motore Split Plan ereditato è generico e non conosce
punti di volume, gambe o posizioni provvigionali: serviva un motore dedicato,
puro e testato caso per caso contro la specifica.

- [x] Modulo `affiliate` (piano versionato, motore puro, servizi, rotte) e
  migrazione `0007` con nove tabelle `sn_aff_*`. Dettagli: `sos-affiliate.md`.
- [x] BC mensile con chiusura automatica il 1° del mese e bonus pagabile il 15;
  BD e BM su 13 posizioni pagati subito; rivendita licenze 450/50 con 500
  MamiCash all'impresa; biglietti Evento Roma; licenza in omaggio ogni 6
  mensilità; obiettivo evento di lancio.
- [x] Area Digital Ambassador (il mio piano, acquista, licenze, imprese
  clienti, bonus, volumi della rete, storico) e console admin (panoramica,
  operazioni e pagamenti, affiliati, compensi, chiusure, registri, piano,
  export CSV). Le sezioni del modello energia/contratti sono fuori dai menu.
- [x] Identità SOS Affiliate: logo originale estratto dal piano compensi,
  versione bianca per lo sfondo scuro, icone col marchio SOS.
- [x] Test: TEST-01…33 della specifica più promozioni, rettifiche, chiusure e
  rotte HTTP; suite completa verde.
- [x] `packaging` dichiarato fra le dipendenze: il kombu recente lo importa
  senza dichiararlo e Celery non partiva con un'immagine nuova.
- [ ] Scelte da confermare: `open-questions.md` §20.

Le voci seguenti sono la storia del codice base, tradotta nei nomi SOSNET.

## 2026-09-22 — Rete unica e Split Plan al posto dei gradi a gettoni

**Perché.** Il progetto SOSNET vende prodotti diversi (energia, fibra,
mobile…) attraverso figure diverse (agenti porta a porta, direttori,
networker, influencer e delegati, segnalatori). Il vecchio modello — un
gettone fisso per grado più la differenza imprenditoriale su tutta la catena —
non sa distinguere né il prodotto né il modo di vendere. Il nuovo separa due
cose che prima erano la stessa: **chi è collegato a chi** (la rete, una sola) e
**chi guadagna cosa** (lo Split Plan, per prodotto + ruolo + data).

- [x] Ruoli commerciali configurabili (`commercial/`), storicizzati, con
  deleghe influencer; distinti dai ruoli di accesso al software. Sei ruoli di
  partenza, solo struttura, nessuna percentuale.
- [x] Margine sul prodotto (fisso o % del netto) e categorie commerciali
  (Energia con punto di fornitura, TLC senza).
- [x] Split Plan versionati sulle tabelle `sn_payout_plans` / `sn_payout_rules`
  (esistevano e non erano mai state usate): bozza → attivo → ritirato, nuova
  versione che chiude la precedente, nessuna sovrapposizione (vincolo nel DB).
- [x] Motore puro (`commissions/engine/`): fissi, percentuali, minimi, tetti,
  residuo; strategie per il livello mancante; arrotondamento deterministico;
  invarianti verificate a ogni calcolo. Stesso codice per calcolo reale,
  anteprima e simulatore.
- [x] Vendita congelata all'attivazione alla **data della firma**: catena,
  ruoli, piano, importo e margine. Cambi di rete, ruolo o piano non toccano il
  passato (test dedicati).
- [x] Movimenti con piano, versione, regola, livello, ruolo, margine e snapshot;
  quota azienda come riga propria (somma righe = margine). Ciclo PENDING →
  APPROVED → PAYABLE → PAID, approvazione e pagamento come permessi separati,
  annullamento con storni negativi.
- [x] Segnalazioni (`leads/`): il cliente arrivato da un Promoter va al primo
  collaboratore sopra che può chiudere e il Promoter prende la fee del piano.
- [x] Contratti senza punto di fornitura per le categorie che non lo richiedono.
- [x] Anteprima del contratto non accettabile se manca piano, margine o ruolo:
  nessun contratto parte senza sapere chi paga.
- [x] Report direzionali e riepilogo del venditore; ruoli software FINANCE e
  NETWORK_MANAGER; permessi `split_plans.*`, `commercial_roles.manage`,
  `commissions.pay`, `leads.*`.
- [x] Interfaccia: pannelli Ruoli e deleghe, Split Plan (editor con validazione
  dal server e prova su una vendita), Simula commissione, Segnalazioni, Report
  provvigioni; Compensi con azioni in blocco; prodotti con margine; collaboratori
  con ruolo e storico; area collaboratore con ruolo, sponsor, compensi
  dirette/indirette/fee, segnalazioni.
- [x] Tolti: valutazione mensile dei gradi, gettoni per grado, bonus primo
  segnalatore (ora regola PROMOTER). Tabelle dei gradi conservate per storico.
- [x] Migrazione `0002` incrementale e reversibile (provata su/giù/su e sui dati
  reali), `alembic check` pulito. 603 test verdi (26 sul motore puro con 3.000
  casi casuali, 13 d'integrazione nuovi), build della dashboard riuscita.
- [ ] Deploy in produzione: script pronto in `/root/backup/deploy-rete-unica.sh`.
- [ ] Configurare margini dei prodotti reali e primi Split Plan (senza, nessun
  contratto si può approvare). Scelte di partenza da confermare:
  `open-questions.md` #19.

## 2026-09-22 — Schema del database consolidato, email e recupero password

**Schema.** L'intera struttura del database nasce ora da un'unica
migrazione, `0001_schema_iniziale.py`, e tutte le tabelle seguono una
convenzione di nomi coerente con prefisso `sn_` (`sn_accounts`,
`sn_agreements`, `sn_payout_entries`, `sn_credit_ledger`, …; l'elenco
completo è in `database-model.md` e `database-schema.sql`). La sequenza
condivisa dei numeri d'ordine si chiama `sn_order_number_seq`.

- [x] Migrazione generata dai modelli e verificata confrontando, colonna per
  colonna e vincolo per vincolo, la struttura ottenuta con quella precedente:
  identica, salvo tre colonne data (`sn_receipt_claims.payment_proof_uploaded_at`,
  `sn_shop_orders.cashback_credited_at`, `sn_shop_orders.payment_proof_uploaded_at`)
  che ora hanno il fuso orario come tutte le altre — i modelli lo dichiaravano
  già, il database no.
- [x] Le foreign key si creano in coda alla migrazione: ordini e movimenti
  del wallet si puntano a vicenda e nessun ordine di creazione delle tabelle
  le soddisfa tutte.
- [x] I vincoli `vat_mode IN ('INCLUDED','ADDED')` degli ordini CJ, Shopify,
  AliExpress e Acquisti ora sono dichiarati nei modelli (prima esistevano
  solo nel database).
- [x] `alembic check`: nessuna differenza fra modelli e database.
- [x] Database di produzione ricreato dal nuovo schema, conservando
  organizzazione, amministratore (stessa password), ruoli, permessi, livelli
  di carriera e piano provvigioni. Backup completo prima dell'operazione.

**Recupero password.** Il link di reset va sempre e solo alla casella
dell'account che lo richiede, amministratori compresi: eliminato ogni
meccanismo di recapito a un indirizzo diverso (`business-rules.md`
§Password reset). Chi controlla una casella che non è quella dell'account
non deve poter prendere il controllo di quell'account.

**Email.** Tutte le email (conferma iscrizione, reset password, codici OTP,
ordini, wallet, ticket, cashback) passano dal template unico
`foundation/email_templates.py`: logo SOSNET (`public/email-logo.png`, su
fondo bianco e leggero, adatto ai client di posta), colore del brand rosso
`#e00a1e` al posto dell'arancione, mittente con nome visualizzato «SOSNET».
Stesso rosso per i titoli del PDF di riepilogo contratto.

**Catalogo demo.** Le offerte di esempio si chiamano «Luce/Gas Energia
Plus» (codici `LUCE-PLUS`, `GAS-PLUS`).


## 2026-11-04 (sera) — Liste a pagine, Aggiorna rete, Ordini e Clienti Mamify

- Causa della lentezza: 8 schermate scaricavano l'intera rete (`GET /network/agents`,
  50.832 righe, 32 MB) e la ricomponevano nel browser. Ora: `GET /network/agents/page`
  (filtri, ricerca nome/codice/email anche Mamify, diretti e grandezza rete per riga,
  conteggi per stato), `GET /network/agents/lookup` (campi «scegli collaboratore»,
  componente `AgentPicker`), `GET /network/agents/export.csv` (in streaming).
  La vecchia `GET /network/agents` resta per compatibilità ma nessuna schermata la usa.
- Rete commerciale (admin) usa l'albero a rami (`NetworkTree`); la cache dell'albero
  si rifà quando cambia `sn_tree_nodes` (anche per spostamenti fatti dal worker).
- «Aggiorna rete» per persona (vedi mamify-integration.md §4), migrazione 0010.
- Barra colorata di caricamento in alto (`LoadingBar`) su ogni richiesta; le
  risposte restano in memoria 1 minuto tornando su una sezione.
- Vendite → Ordini (nuova) e Vendite → Clienti sui dati Mamify, a pagine.
- Corretto: `GET /mamify/admin/orders` dava errore 500 (`MamifyOrder.updated_at` non
  esiste): la scheda «Ordini ricevuti» non mostrava nulla.
- Due «Michele Novarese» nella rete: MF5 (304 persone) e MF8664 (nessuno sotto); ora
  la lista mostra email e grandezza rete per distinguerli.
- Test: 738 (nuovi: pagine collaboratori, lookup, ramo, richiesta ramo, ordini/clienti).

## 2026-11-05

- Albero della rete (Digital Ambassador e admin): nuova vista **Albero** orizzontale
  (cima a sinistra, rami che si aprono verso destra con il tasto +, linee di
  collegamento, 100 per volta con "Mostra altri"); la vecchia vista resta come
  **Elenco**. La scelta resta nel browser (`sosnet.tree.layout`).
  File: `apps/dashboard/components/affiliate/network-tree.tsx` (HBranch, HChildren, Rows).
- **Rete virtuale 3D** (solo Digital Ambassador, solo il proprio ramo; nessuna
  versione admin). Pulsante "Passa alla versione virtuale" in La mia rete; l'albero
  resta com'è. `GET /affiliate/me/network/galaxy` manda tutto il ramo in una
  risposta compatta (massimo 5.000 persone, `tree.galaxy`, niente contatti);
  three.js 0.180 si scarica solo all'apertura (`next/dynamic`). Scena:
  `components/affiliate/galaxy-scene.ts`; interfaccia: `network-galaxy.tsx`;
  posizioni: `lib/galaxy.ts`. Stelle = persone (grandezza = ramo, colore =
  livello, luce = punti nel mese), scie dorate = punti che salgono lungo gli
  sponsor, volo tra i rami, tour guidato, ricerca, tastiera, ripiego senza WebGL
  e con "riduci movimento".
- Albero più veloce: `tree.snapshot` ora serve subito la copia scaduta e la
  ricostruisce in sottofondo (una sola alla volta); attende solo il primo
  visitatore o dopo un cambio della rete da Mamify.
- **Saldi veri nella home**: i riquadri "Saldo MAMIX / CASHBACK / Totale utilizzo"
  erano segnaposto (wallet partner mai collegato, da qui il "—"). Ora
  `external_wallet/service.py` legge `rag/customer/wallets` di Mamify (sola
  lettura) per il cliente Mamify collegato all'accesso: MAMIX, MamiCash
  personale e aziendale (più il totale), in memoria 2 minuti, pulsante
  "Aggiorna saldi" (`?fresh=true`). Chi non è nella rete vede "non disponibile".
  Nota: `rag/customer/transactions` vuole `wallet=mamix|mamicash`.
- Correzione: il promoter ha due "La mia rete" (sezione SOS con `NetworkTree`,
  e "Rete" con l'organigramma `NetworkChart` via `BranchVisualizer`).
  Pulsante 3D (`components/affiliate/virtual-network-button.tsx`) ora in tutte
  e due; l'organigramma è **orizzontale** di base (CSS `.org-canvas[data-orient]`
  in globals.css, selettore "Orizzontale → / Verticale ↓", scelta salvata nel
  browser `sosnet.orgchart.orient`). Vale anche per l'organigramma admin e
  per la rete prodotti, che usano lo stesso componente.

- 2026-11-05 · Link promoter nascosto (temporaneo): il box "Condividi il tuo link" nella testata del Digital Ambassador è spento con `SHOW_PROMOTER_LINK = false` in `apps/dashboard/components/promoter-client-page.tsx`. Per riaccenderlo: rimettere `true` e ricostruire la dashboard. Il link /r/<codice> continua a funzionare per chi lo ha già.

- 2026-11-05 · Area cliente: nascosti "I miei contratti" (pratiche luce e gas) e "Negozio", con il carrello e i pacchetti della home che aprivano la pratica. Interruttore `HIDDEN_KEYS = new Set(["contracts", "products"])` in `apps/dashboard/components/customer-client-page.tsx`: togliere una chiave per riaccendere la sezione. I vecchi link (?tab=contracts, ?tab=products, activate-contract) portano alla home. Il codice resta tutto, nulla è stato cancellato.

- 2026-11-05 · Tolti i riferimenti a contratti e luce e gas dove li vedono clienti e Digital Ambassador: area cliente (descrizioni, "Invita amici" nascosto perché il premio conta i contratti degli amici), Contabilità (niente filtro né riquadro "Contratti"), menu utente, ticket (categoria "Contratto" non più selezionabile, resta per i vecchi), wallet ("Cashback SOSNET"), profilo, riscatto ("fattura", "Richiesta"), scheda del collaboratore (nascoste le schede Piani e guadagni, Rete per prodotto, Vendite e contratti con `HIDDEN_TABS` in agent-card-page.tsx). Il codice e i pannelli admin dei contratti restano, solo nascosti.

- 2026-11-05 · Admin: nascosti Clienti (anagrafiche con punti di fornitura e contratti), Premi invito e tutto il gruppo Shop (Partner e forniture, Ordini negozi, Shop CJ, Shopify, AliExpress, Fai la Spesa con Sosnet) con `HIDDEN_KEYS` in admin-client-page.tsx. Impostazioni: spenti Listino contratti, Cashback dei contratti a rate e cartella Google Drive dei contratti (`SHOW_CONTRACT_SETTINGS = false` in admin-organization-settings-panel.tsx). Restano Ordini SOS da Mamify, Collaboratori, Albero, Portafogli, Riscatti fatture, Contabilità, Assistenza, Documentazione, Impostazioni.

- 2026-11-06 · Pulsante "← Indietro" in testata su ogni sezione di tutte e tre le console (AppFrame): ricorda le sezioni visitate, comunque aperte (menu, barra, riquadri, link interni), e riporta alla precedente; senza storia porta alla home; salta le sezioni nascoste.

- 2026-11-06 · Ordini Mamify più veloci e più robusti: (1) un prodotto spostato da Mamify in un'altra app (il «Digital Ambassador» 49 € passato da sos-affiliate a digitalambassador) si riconosce ancora da nome e prezzo (`parsing.resolve_line`); (2) quando un Digital Ambassador apre la sua console, il server rilegge in sola lettura i suoi ultimi ordini (`request_own_orders` → `mamify_own_orders_task`, coda mamify, al massimo ogni 2 minuti) e la pagina si aggiorna da sola 20 secondi dopo. Prima il giro sui 50.859 iscritti raggiungeva una persona circa una volta l'ora. Ordine 4544 di MF5 riapplicato: abbonamento 40 BC. Test: 34 passati (mamify e affiliate).

## 2026-11-06 — "I miei ordini Mamify" visibili al Digital Ambassador

- Gli ordini Mamify registrati comparivano solo come operazioni in "Storico operazioni"; la pagina "I tuoi ordini" mostra solo gli ordini del negozio.
- API: `GET /affiliate/me/mamify-orders` (solo dati locali, nessuna chiamata a Mamify): ordini dove l'acquirente è il proprio cliente Mamify, con prodotti, totale, stato, BC accreditati e operazioni generate (`mamify.service.list_own_orders`).
- Dashboard: nuova voce "I miei ordini Mamify" (`sos-orders`) nella console SOS Affiliate; lo stesso elenco compare in cima a "I tuoi ordini" dell'area cliente (nascosto per chi non ha profilo o ordini).
- Test: `test_opening_the_dashboard_reads_ones_own_orders` controlla anche l'elenco.

## 2026-11-06 — Bottone Indietro e contatori negli ordini

- "← Indietro" ora sta sopra il titolo (riga a sé) con sfondo azzurro chiaro e testo scuro.
- "I tuoi ordini": il box vuoto degli ordini Shop è nascosto insieme al negozio; sopra l'elenco Mamify quattro contatori: punti personali del mese, punti dagli ordini, licenze acquistate, licenze da assegnare.

## 2026-11-07 — Contabilità: solo punti, licenze e saldi Mamify

- `accounting-panel.tsx`: i contatori in euro (totale speso, carta, bonifico, shop, SosnetCash, provvigioni) sono nascosti con `SHOW_MONEY_COUNTERS = false`; al loro posto i saldi MAMIX/MamiCash (`ExternalWalletStats`) e `PointsCounters` (punti del mese, punti dagli ordini Mamify, licenze acquistate, licenze da assegnare), estratto da `affiliate/mamify-orders.tsx`.

## 2026-11-07 — Assistenza via WhatsApp

- `lib/support.ts`: `SUPPORT_WHATSAPP_NUMBER` (da impostare, solo cifre con prefisso) e `SHOW_SUPPORT_TICKETS = false`.
- `components/whatsapp-support.tsx`: pagina "Assistenza su WhatsApp" con pulsante grande (sostituisce l'apertura dei ticket nelle aree cliente e promoter, i ticket restano nel codice) e icona rotonda blu in basso a destra su ogni pagina (`app-frame`), sopra la barra del telefono. Numero: 351914313866, lo stesso del widget WhatsApp di mamify.ai; il messaggio termina con "Rif. MAMIFY" come quello del widget.
