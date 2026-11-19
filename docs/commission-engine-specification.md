# Motore provvigionale — Split Plan

Una sola rete commerciale (chi ha introdotto chi) e, separato, un piano che
dice **chi guadagna cosa** su ogni vendita:

```
RETE DI SPONSORSHIP ──► VENDITA ─┬─ PRODOTTO (margine)
                                 └─ RUOLO DEL VENDITORE (alla data)
                                        │
                                        ▼
                                  SPLIT PLAN (versione valida alla data)
                                        │
                                        ▼
                                 MOTORE (funzione pura)
                                        │
                                        ▼
                             MOVIMENTI (congelati, immutabili)
```

La rete determina **chi è collegato a chi**. Il piano determina **chi prende
cosa**. I due concetti non si toccano: nessuna rete per prodotto o per ruolo,
nessuna percentuale nel codice.

## Dove sta il codice

```
commissions/
  engine/
    types.py         dati puri: ChainNode, RuleSpec, PlanSpec, SaleContext, Allocation
    allocate.py      il motore: divide il margine (nessun accesso al database)
    validation.py    il validatore dei piani (regole del 100%, fissi, residuo)
  services/
    sale.py          dalla vendita al contesto del motore (congelamento, anteprima, simulatore)
    run_calculation.py  calcolo reale: legge solo dati congelati, scrive movimenti
    plans.py         Split Plan: bozza, validazione, attivazione, versioni, ritiro
    lifecycle.py     PENDING → APPROVED → PAYABLE → PAID; annullamento e storno
    preview.py       anteprima del contratto (stesso motore)
    reports.py       report direzionali e riepilogo del venditore
  simulations/simulate.py   SIMULA COMMISSIONE (stesso motore, nessuna scrittura)
  tasks/dispatch.py  eventi → calcoli (attivazione, rata, rinnovo, annullamento)
commercial/          ruoli commerciali, storico ruoli, deleghe influencer
leads/               segnalazioni dei Promoter
```

Frontend, anteprima, simulatore e calcolo reale usano **lo stesso**
`engine/allocate.py`. Il browser non calcola mai un importo.

## Concetti

**Ruolo commerciale** (`sn_commercial_roles`): come una persona vende e fin dove
arriva la sua rete nel calcolo (`network_depth`), se può chiudere vendite
(`can_close_sales`), se può avere delegati (`allows_delegation`). Il
comportamento dipende dalla configurazione, **mai dal codice del ruolo**. Il
ruolo è storicizzato (`sn_seller_role_history`, periodi senza sovrapposizioni
garantiti da un vincolo di esclusione): una vendita usa il ruolo che il
venditore aveva **alla data della vendita**. È distinto dal ruolo di accesso al
software (`sn_roles`).

**Margine** (`sn_offer_versions.margin_*`): importo fisso, oppure percentuale
dell'importo netto (IVA esclusa) della vendita. Il prodotto dice quanto è
grande la torta, mai come si divide.

**Split Plan** (`sn_payout_plans`) per prodotto *oppure* categoria commerciale +
ruolo del venditore + periodo di validità. Stati DRAFT → ACTIVE → RETIRED. Un
piano ACTIVE è immutabile: si crea la versione successiva (`plan_key` uguale,
`version` + 1); attivandola, la versione precedente aperta si chiude alla sua
data di inizio. Due piani ACTIVE per lo stesso prodotto/categoria e ruolo non
possono sovrapporsi (vincolo di esclusione nel database). Scelta del piano:
prima quello del prodotto, poi quello della categoria.

**Regole** (`sn_payout_rules`), lette in ordine di `sequence`:

| beneficiary_type | chi riceve |
|---|---|
| `SELLER` | il venditore |
| `UPLINE_LEVEL` + `network_level` | la persona N livelli sopra il venditore (1 = sponsor diretto), eventualmente con un ruolo richiesto |
| `ROLE_IN_UPLINE` + `required_role_id` | il primo, salendo, con quel ruolo (entro `network_level` se indicato) |
| `INFLUENCER` | l'influencer del venditore: delega esplicita valida alla data, altrimenti il primo sopra il cui ruolo ammette delegati |
| `PROMOTER` | chi ha portato la segnalazione da cui nasce la vendita |
| `COMPANY` | l'azienda |

| calculation_type | quanto |
|---|---|
| `PERCENTAGE` | % del margine (opzionali minimo e massimo) |
| `MINIMUM_GUARANTEE` | % del margine con minimo obbligatorio |
| `FIXED_AMOUNT` | importo in euro |
| `REMAINDER` | margine meno tutte le altre quote (al massimo uno per piano) |

## L'algoritmo

1. **Congelamento** (`sale.freeze_contract`, all'attivazione): data della vendita
   (`sold_at` = firma), catena di sponsorship **alla data** (tabella dei percorsi
   storicizzata), ruolo di ciascuno alla data, stato di ciascuno, piano valido
   alla data, importo e margine. Tutto su contratto e snapshot di rete.
2. **Quanto** (`_nominal_amounts`), indipendente dal beneficiario: fissi,
   percentuali arrotondate al centesimo *mezzo in su* (Decimal, mai float),
   minimi/tetti, poi il residuo. Se le quote superano il margine → errore, niente
   scritto.
3. **A chi** (`_resolve`): ogni regola cerca il beneficiario nella catena. La
   profondità è limitata dal ruolo del venditore. Chi non è ACTIVE **tiene il suo
   livello** ma non riceve.
4. **Beneficiario mancante** → strategia della regola o del piano:
   `COMPANY` (quota all'azienda, riga esplicita), `NEXT_AVAILABLE` (primo idoneo
   più in alto, altrimenti azienda), `STOP` (non distribuita: residuo azienda).
5. **Centesimo** — un piano FULL senza residuo è di sole percentuali che fanno
   100; la differenza di arrotondamento va sulla quota più grande (a parità, la
   prima in sequenza). Con un residuo, la assorbe il residuo.
6. **Residuo azienda** — ciò che resta (piano PARTIAL, quote STOP) diventa una
   riga COMPANY esplicita.
7. **Invarianti** controllate a ogni calcolo (con `raise`, non `assert`): somma
   delle righe = margine; nessuna riga negativa.

## Scrittura (`run_calculation.py`)

Un'unica transazione: calcolo (`sn_payout_runs`, con input/output e checksum),
uno step per riga, un movimento (`sn_payout_entries`) per ogni quota non nulla —
**compresa la quota azienda** (`beneficiary_kind = COMPANY`, stato RETAINED).
Ogni movimento porta piano, versione, regola, livello, ruolo, tipo e valore del
calcolo, margine, venditore, prodotto, fallback applicato e uno `snapshot` JSON
con catena e spiegazione: il calcolo si ricostruisce anni dopo senza leggere lo
stato corrente di nulla.

Idempotenza: UNIQUE (contratto, evento) sul calcolo e UNIQUE sulla chiave
deterministica `hash(contratto, evento, regola, beneficiario)` sul movimento.
Doppio clic, webhook ripetuto, worker concorrenti: il secondo trova il lavoro
fatto.

Un calcolo impossibile (nessun piano, nessun margine, quote oltre il margine)
diventa un calcolo **FAILED** con il motivo e una riga di audit — mai un
contratto che silenziosamente non paga nessuno.

## Quando matura (`SplitPlan.accrual_trigger`)

- `PER_INSTALMENT` (default): una quota di ogni riga a ogni rata incassata
  (`instalment_share`: parti uguali, resto sull'ultima). Pagamento unico = una rata.
- `ON_ACTIVATION`: tutto all'attivazione.

Rinnovo: nuovo calcolo completo sugli stessi dati congelati.

## Ciclo di vita e storni (`lifecycle.py`)

`PENDING → APPROVED → PAYABLE → PAID` (approvare richiede `commissions.approve`,
pagare `commissions.pay`: chi approva e chi paga possono essere persone diverse).
All'annullamento del contratto (da ACTIVE, SUSPENDED, EXPIRED, RENEWED): il non
pagato diventa CANCELLED, il pagato resta PAID e nasce una riga **REVERSAL**
negativa collegata in `sn_payout_reversals`. Nessuna riga si cancella, nessun
importo si modifica.

## Segnalazioni e Promoter

Un Promoter (ruolo che non chiude vendite) porta un'opportunità (`sn_leads`).
Se un cliente arrivato dal suo link firma un contratto, la vendita va al primo
collaboratore sopra di lui che può chiuderla, e nasce una segnalazione a suo
nome: la regola `PROMOTER` del piano gli paga la fee. La segnalazione diventa
CONVERTED all'attivazione del contratto. Una segnalazione mai convertita non
genera niente.

## Anteprima e simulatore

L'anteprima del contratto usa la stessa risoluzione e lo stesso motore; se
qualcosa impedisce il calcolo lo dice in `blocking_errors` e **non si può
accettare**: il contratto non si attiva finché la configurazione non è completa.
Il simulatore (`POST /commissions/simulate`) accetta venditore, prodotto, data,
importo, un segnalatore e anche un piano in bozza da provare prima di attivarlo.

## Validazione dei piani (`engine/validation.py`)

Percentuali tra 0 e 100 e somma ≤ 100; nessun beneficiario ripetuto; al massimo
un residuo; minimo ≤ massimo; niente valori negativi. FULL = c'è un residuo,
oppure sole percentuali (senza minimi/tetti) che sommano **esattamente** 100.
PARTIAL non ammette residuo. Le quote fisse si verificano contro il margine
fisso del prodotto quando è noto; con un margine percentuale il controllo avviene
a ogni vendita.

## Test

- `tests/test_split_engine.py` — il motore senza database: gli scenari del
  progetto (Porta a porta, Networker su 4 livelli e con rete incompleta per ogni
  strategia, Influencer e delegati, Promoter con e senza segnalazione, minimi e
  tetti, arrotondamenti), il validatore, e **3.000 piani e reti casuali** su cui
  si verificano gli invarianti (somma = margine, niente negativi, beneficiario
  sempre presente, regola tracciabile, nessun doppio pagamento, determinismo).
- `tests/test_split_plans_integration.py` — sul database: versioni dei piani,
  cambio ruolo e cambio sponsor dopo la vendita, segnalatore, segnalazione non
  convertita, doppio calcolo, annullamento e storno, simulatore, contratto senza
  piano, tipi di dato del denaro.

## Il vecchio modello

Gradi (SosPromoter 1-3, SosLeader 1-4, SosManager 1-5), gettoni per grado e differenza imprenditoriale non sono più
usati dal motore. Le tabelle `sn_career_levels` e `sn_promoter_level_log`
restano per storico; la valutazione mensile dei gradi è stata tolta; le righe di
piano del vecchio modello sono marcate `LEGACY`.
