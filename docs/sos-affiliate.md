# SOS Affiliate — come è costruito

Il progetto di questa installazione è uno solo: la rete dei **Digital
Ambassador** di SOS Affiliate, con i suoi tre bonus (BC, BD, BM) e il margine
sulla rivendita delle licenze. Le fonti sono due documenti del cliente e
nient'altro:

- *SOS Affiliate — Specifica tecnica*, v1.1 del 28/10/2026 (regole, requisiti
  `AFF/NET/BC/CAR/BM/BD/LIC/ADM/UI/INT` e i 33 casi di verifica);
- *Piano Compensi SOS Affiliate* del 29/10/2026 (la presentazione: aggiunge i
  biglietti dell'Evento Roma, la ripartizione 450/50 della rivendita, le date
  di pagamento e le due promozioni).

Dove i documenti non dicono qualcosa, la scelta fatta è in fondo, al §7.

Persone, rete, acquisti e portafogli vengono da Mamify: il collegamento è
descritto in `mamify-integration.md`. Con il collegamento attivo le
operazioni nascono dagli ordini pagati su Mamify, già confermate; la
registrazione a mano resta per le eccezioni.

---

## 1. Dove sta il codice

```
apps/api/app/modules/affiliate/
  plan.py      il piano di default (numeri dei documenti) e le sue invarianti
  engine.py    i calcoli puri: livello, gambe, distribuzioni, arrotondamento
  models.py    le tabelle sn_aff_*
  service.py   operazioni, conferme, rettifiche, chiusura mensile, viste
  router.py    /api/affiliate/me/* (Digital Ambassador) e /admin/* (ufficio)
apps/api/alembic/versions/0007_sos_affiliate.py
apps/api/tests/test_sos_affiliate_{engine,flows,routes}.py
apps/dashboard/components/affiliate/   area Digital Ambassador e console admin
apps/dashboard/lib/affiliate.ts        tipi e formattazione (nessun calcolo)
```

Un Digital Ambassador **è** un collaboratore della rete esistente
(`sn_promoter_profiles`): albero sponsor, storico dei movimenti e tabella di
chiusura sono quelli di sempre, e si gestiscono dalla sezione della rete
(nuovi iscritti dal link personale, approvazioni, spostamenti). Il modulo
`affiliate` aggiunge solo ciò che serve al piano compensi.

Il vecchio motore (Split Plan, contratti energia) resta nel codice ma è fuori
dai menu: non genera nulla per SOS Affiliate.

## 2. Il ciclo di un'operazione

1. **Creata** dal Digital Ambassador (o dall'ufficio) come `PENDING`. Il
   browser manda solo un codice prodotto (`LARGE`, `ROMA_10`, `BUSINESS`…): il
   prezzo, lo sconto e i BC li prende il server dal piano. L'unico importo che
   viene dall'esterno è il valore di una ricarica MamiCash, che è la base del
   BM e non un prezzo.
2. **Confermata** dall'amministrazione quando il denaro è arrivato
   (`payments.manage`). Solo a quel punto si scrivono punti, licenze e
   compensi, sotto lock della riga (INT-07).
3. **Rettificata**, se serve, con un'operazione `REVERSAL` (`commissions.approve`
   e motivo obbligatorio): punti negativi, compensi non pagati annullati,
   compensi già pagati trasformati in un recupero. Niente si cancella (INT-05).

L'idempotenza è nel database, non nel codice: chiave deterministica
`UNIQUE` per ogni operazione (un doppio clic produce lo stesso numero di
sequenza e viene rifiutato), un solo movimento punti per operazione, una sola
riga di compenso per (operazione, tipo, posizione), un solo Bonus Carriera per
(affiliato, mese), una sola mensilità per (affiliato, mese).

## 3. Bonus Carriera (BC)

- **Punti personali (BCP)**: mensilità pagata 40, licenza 400, SMALL 350,
  MEDIUM 700, LARGE 1.500, biglietti Roma 50/270/450/600. I BC sono per
  acquisto, mai per licenza o per biglietto. Rivendite e Pack: zero BC.
- **Mese dei punti**: la mensilità vale per il mese pagato; tutto il resto per
  il mese (ora di Roma) in cui il pagamento è confermato.
- **Gambe (BCG)** e **totale (BCT)** non sono memorizzati: si ricalcolano
  dai movimenti punti risalendo l'albero sponsor fino in cima, così la stessa
  operazione conta una volta sola nel totale di ogni antenato (NET-05, NET-06).
- **Livello**: il più alto fra gli 11 per cui `BCT ≥ totale` e almeno 3 gambe
  distinte `≥ minimo`. Un solo bonus, mai la somma dei livelli inferiori.
- **Chiusura del mese**: in automatico il 1° del mese (Celery, 02:30 UTC) o a
  mano da *Chiusure mensili*. Congela BCP, gambe, BCT e livello di ogni
  affiliato (`sn_aff_monthly_results`) e scrive il bonus, **pagabile il 15 del
  mese successivo**. Un mese chiuso non si ricalcola più (INT-10); non si
  chiude un mese con mensilità ancora in attesa di pagamento.

## 4. BD e BM

Stessa meccanica, aliquote diverse, base diversa:

| | BD — Vendita Diretta | BM — MamiCash |
|---|---|---|
| Origine | vendita di un Pack START/BUSINESS/PREMIUM/INTERNATIONAL | ricarica MamiCash di un'impresa cliente |
| Base | prezzo nominale del Pack | valore della ricarica |
| Posizione 1 | 18% al venditore | 1% al venditore |
| Totale 13 posizioni | 42% | 4% |
| Pagamento | subito | subito |

Il venditore è il Digital Ambassador che segue l'impresa cliente; le
posizioni 2…13 sono i suoi sponsor, risalendo. Ogni aliquota si applica alla
base intera; importi arrotondati al centesimo, per eccesso dal mezzo
centesimo (`engine.money`, l'unica regola di arrotondamento).

## 5. Licenze e rivendite

Ogni licenza acquistata è una riga con un codice univoco (`L-XXXXXXXX-NN`),
il suo costo unitario (prezzo del pacchetto / licenze) e lo stato
`AVAILABLE → RESERVED → RESOLD`. La rivendita a un'impresa costa 500 €: alla
conferma il venditore matura **450 €** (riga `RESALE`, con il margine calcolato
sul costo della licenza), la società trattiene 50 € e l'impresa riceve **500
MamiCash**. Nessun BC.

### 5b. Registro licenze e margine commerciale (17/11/2026)

Fonte: *Piano Compensi SOS Affiliate* (presentazione, copia in
`docs/fonti/Piano-compensi-aggiuntivo.pdf`): stessi numeri del piano già in
`plan.py`; il PDF chiede in più di seguire a chi va ogni licenza e il margine.

Mamify vende le licenze ma non sa a quale impresa il Digital Ambassador ne dà
una: **l'assegnazione si ricorda solo qui** (`affiliate/licenses.py`).

- **Assegnare** = la rivendita già esistente: licenza `RESERVED` per
  quell'impresa finché non arrivano i 500 €, poi `RESOLD` con i 450 € al
  venditore. L'impresa si sceglie tra le sue o si scrive al momento
  (`POST /affiliate/{me,admin}/licenses/assign`, `new_client`). «Ritira»
  annulla un'assegnazione non pagata e libera la licenza.
- **Registro** a pagine con ricerca sul server (codice, impresa, P.IVA,
  titolare) e schede per stato: `GET /affiliate/{me,admin}/licenses/page`.
  Ogni riga dice da quale acquisto viene la licenza, quando è stata assegnata
  e pagata, se il pagamento è arrivato da Mamify, il margine.
- **Margine**: `GET /affiliate/me/licenses/margins` (e
  `/admin/licenses/margins/{agent}`) raggruppa per acquisto: libere,
  assegnate, rivendute, costo (il prezzo vero del pacchetto: 1.600 €, non
  12 × 133,33), incassato (compensi `RESALE` vivi), margine realizzato
  (incassato − costo delle licenze rivendute), margine possibile (450 × licenze
  − costo). `GET /affiliate/admin/licenses/margins` dà una riga per Digital
  Ambassador, a pagine.
- **Rivendita pagata su Mamify**: se nel collegamento Mamify un prodotto è
  abbinato a `LICENSE_RESALE` (il «Licenze» da 500 €, id 17293), l'ordine
  pagato dell'impresa diventa una rivendita già confermata del suo sponsor
  Mamify: usa la licenza che lui le aveva già assegnato (l'assegnazione in
  attesa viene chiusa e sostituita), altrimenti la sua licenza libera più
  vecchia. Senza licenze libere l'ordine resta «in verifica» e si riapplica da
  solo quando ne avrà una. Un'impresa scritta a mano con la stessa email del
  cliente Mamify viene collegata a lui invece di crearne una seconda.
- **MamiCash all'impresa**: li gestisce Mamify; il registro dice solo se sono
  arrivati con l'ordine Mamify o se la rivendita è stata registrata a mano.

## 6. Piano versionato

Il piano è una riga `sn_aff_plan_versions` con tutta la configurazione in
JSON. Ogni operazione memorizza la versione con cui è stata calcolata; una
nuova versione vale solo da una data futura. Il server rifiuta un piano che
non abbia esattamente 11 livelli, 13 aliquote BM che sommano 4% e 13 aliquote
BD che sommano 42% (checklist §14 della specifica).

## 7. Scelte prese dove i documenti tacciono

Tutte modificabili; sono anche in `open-questions.md` §20.

1. **Pagamenti confermati a mano** (bonifico, carta registrata dall'ufficio,
   contanti). Il pagamento online con Stripe è un passo successivo.
2. **Mese dei punti di un acquisto** = mese della conferma del pagamento, non
   dell'ordine.
3. **Licenza in omaggio** (ogni 6 mensilità pagate): zero BC e costo zero, quindi
   alla rivendita il margine è l'intero 450 €.
4. **I 500 MamiCash della rivendita non generano BM**: il BM nasce dalle
   ricariche fatte dai clienti.
5. **Evento Roma (6.000 punti a novembre)**: misurato sul **BCT** di novembre
   2026. Se si intendevano i soli punti personali è una riga in `service.py`.
6. **Posizioni BD/BM vuote** (catena più corta di 13): la quota resta
   all'azienda, come nell'esempio della specifica (680 € assegnati su 840 €).
7. **Bonus Carriera senza requisito di abbonamento**: i documenti non lo
   chiedono, quindi un affiliato con abbonamento sospeso che raggiunge il
   livello matura il bonus. Se serve il requisito, è un controllo nella
   chiusura.
8. **Volumi del mese in corso** calcolati con l'albero di oggi: se un affiliato
   viene spostato a metà mese, i suoi punti del mese seguono il nuovo sponsor.
   I mesi chiusi restano come sono stati congelati.
9. **Saldo MamiCash dell'impresa**: è un registro informativo; non è collegato
   a un portafoglio spendibile.

## 8. Verifiche

`tests/test_sos_affiliate_engine.py` riproduce uno per uno i casi TEST-11…31
della specifica (TEST-20/21/22 per tutti gli 11 livelli);
`test_sos_affiliate_flows.py` quelli che richiedono il database (TEST-01…10,
17…19, 30…33, più promozioni, rivendite, rettifiche e chiusure);
`test_sos_affiliate_routes.py` le rotte HTTP e i permessi.
