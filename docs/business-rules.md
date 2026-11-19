# Business Rules

Status: no source document (`Allegato_A_Piano_Carriera_Regolamento_Provvigionale.pdf`)
was present in the repository at the time this was written. Every numeric threshold,
percentage and formula below is a **placeholder** used to make the system runnable and
testable. None of it should be treated as the real SOSNET commercial policy until
confirmed. Every placeholder is also listed in `open-questions.md` with the exact
config location to change once real figures are available.

## Money

- All monetary amounts are stored as integer cents (`*_cents BIGINT`) in the database
  and as `Decimal` in Python at the API boundary. `float` is never used for money,
  percentages, or any economic quantity.
- Currency is EUR only in v1; a `currency` column exists on ledger rows for future
  multi-currency support but is not exercised.
- Rounding: half-up to the nearest cent, applied only at the point a figure is
  persisted to `sn_payout_entries` — intermediate calculation steps keep full
  precision (`Decimal` with explicit context), see `commission-engine-specification.md`.

## Rete unica, ruoli commerciali e Split Plan {#split-plan}

La specifica completa è in `commission-engine-specification.md`; qui le regole.

- **Una sola rete**: sponsor → persona introdotta. La posizione nella rete non
  dipende da prodotto, tipo di vendita, piano o ruolo. È storicizzata: si può
  sempre sapere chi era lo sponsor di chi a una certa data.
- **Il ruolo commerciale** (Networker, Agente porta a porta, Direttore
  commerciale, Influencer, Delegato, Promoter, e quelli che l'amministrazione
  aggiunge) dice come si vende, non quanto si guadagna. È storicizzato: una
  vendita usa il ruolo del venditore **alla data della vendita**. Chi entra nella
  rete riceve il ruolo predefinito. È diverso dal ruolo di accesso al software.
- **Il prodotto** porta il **margine** (fisso o % dell'importo netto). Senza
  margine un contratto non si può approvare.
- **Lo Split Plan** (prodotto o categoria + ruolo del venditore + validità)
  divide il margine. Un piano attivo non si modifica: si crea la versione
  successiva. Una vendita usa il piano valido alla sua data e lo congela: cambiare
  un piano **non ricalcola mai il passato**. Senza piano attivo un contratto non si
  può approvare.
- **Il 100%**: un piano a distribuzione completa distribuisce esattamente il
  margine (una regola Residuo, oppure percentuali che fanno 100). Somma delle
  righe di una vendita = margine, sempre, compresa la quota dell'azienda
  registrata come riga propria.
- **Livello mancante** (la rete si ferma prima, la persona non è attiva, nessuno
  ha il ruolo cercato, nessun segnalatore): lo decide il piano, per piano o per
  regola — all'azienda, al primo idoneo più in alto, oppure non distribuita.
  Chi non è attivo tiene il suo livello: i livelli non si accorciano.
- **Profondità**: la rete raggiungibile nel calcolo è limitata dalla profondità
  del ruolo del venditore.
- **Influencer e delegati**: il delegato è un nodo della rete unica, di norma
  sponsorizzato dall'influencer; una delega esplicita (datata) serve quando è in
  un altro ramo e ha la precedenza.
- **Promoter (segnalatore)**: non chiude vendite. Se il cliente arriva dal suo
  link, la vendita va al primo collaboratore sopra di lui che può chiuderla e lui
  riceve la fee della regola PROMOTER; la segnalazione diventa CONVERTED
  all'attivazione del contratto. Una segnalazione non convertita non paga niente.
- **Ciclo di vita**: PENDING → APPROVED → PAYABLE → PAID. Approvare e pagare sono
  permessi distinti (`commissions.approve`, `commissions.pay`). Annullare un
  contratto annulla le quote non pagate e storna con una riga negativa quelle
  pagate. Nessun movimento si cancella.
- **Arrotondamento**: al centesimo, mezzo in su, riga per riga; il centesimo che
  avanza va alla regola Residuo, altrimenti alla quota più grande.

### Promoter disattivato: il contratto risale allo sponsor attivo {#terminated-promoter-fallback}

A customer's referring promoter can be deactivated (`agent_profiles.status =
TERMINATED`) months after that customer signed up. `create_contract` refuses
to attribute a contract to a non-ACTIVE agent — correctly: a contract that
activates and pays nobody is the failure documented in
`paid-contract-commission-audit.md`. The result was a customer who could not
activate anything, ever, and saw only "Si è verificato un errore imprevisto"
(the refusal escaped `POST /contracts/mine` as an unhandled 500). Three real
customers were in this state when it was found.

**Rule, chosen explicitly by the business**: walk **up** to the nearest ACTIVE
sponsor rather than block.

- `network/service.py::resolve_nearest_active_agent` returns the agent if they
  are ACTIVE, otherwise the closest ACTIVE ancestor, otherwise `None`. It
  reads the closure table for structurally open edges and then filters by the
  agent's own status — the two are independent (`effective_to IS NULL` means
  "this edge is current", not "this person is still working").
- Walking up, rather than falling back to the root, is the point: the branch
  that actually built the relationship keeps it.
- **The original referrer is still recorded** on the contract
  (`first_referrer_agent_id`), so nothing is rewritten — and the substitution
  writes an `sn_activity_log` row (`contract.producer_substituted`, with the old and
  new agent), because somebody other than the customer's own referrer is being
  credited and "why is this Rossi's and not Bianchi's?" deserves an
  answer, not an inference from two statuses.
- **The same rule widens the CRM path**: the inheriting sponsor may activate a
  contract for that customer. Without it, a customer whose promoter left is
  unreachable from both sides — they cannot self-activate and nobody can do it
  for them. It widens access to the **upline only**; a promoter on a different
  branch is still refused.
- **No active upline at all** → still blocked, but with a sentence a customer
  can act on ("contatta l'assistenza: ti verrà assegnato un nuovo referente"),
  never an English exception string with a UUID in it, and never a 500.
- The **first-referrer bonus does NOT follow this walk-up**
  (`_maybe_add_first_referrer_bonus` skips a non-ACTIVE referrer). That bonus
  is defined as belonging to the person who brought the customer in; if they
  have left, nobody earns it. The recursive commission is a different thing
  and does transfer. No product enables the bonus today, so this is currently
  theoretical — flag it if that changes.

## Pagamento del contratto: unica, 3 rate, 12 rate {#contract-payment}

**Contracts only.** The Shop's own checkout (orders, imported orders) is a
separate, already-working flow and is untouched: an order is a purchase, a
contract is a subscription to a service.

### Sconto per il pagamento in unica soluzione {#full-payment-discount}

Chi paga il contratto (o l'intera pratica) **tutto subito con carta** ha uno
sconto sul prezzo: **32%** di default, impostabile in Impostazioni (0 = nessuno
sconto). 3 e 12 rate restano a prezzo pieno.

- Lo sconto si applica al prezzo IVA inclusa, arrotondato al centesimo: è lo
  stesso che scontare il prezzo netto e poi aggiungere l'IVA (180 − 32% + IVA).
- Il prezzo del contratto (`gross_amount_cents`) non cambia; lo sconto scelto si
  congela sul contratto (`payment_discount_cents`) quando il cliente sceglie la
  soluzione unica, e tutto ciò che segue (rata registrata, cashback, anteprima
  provvigioni) usa quanto pagato davvero. Un cambio dell'impostazione vale solo
  per i pagamenti successivi.
- Il **cashback** di un pagamento unico scontato è calcolato su quanto pagato
  (open-questions #18). I gettoni provvigionali non cambiano.
- **Bonifico della pratica**: il cliente può scegliere "Paga con
  bonifico" nel checkout finale. È sempre una soluzione unica, con lo stesso
  sconto, congelato su ogni contratto al momento della scelta. I contratti
  risultano pagati solo quando un amministratore conferma "bonifico ricevuto"
  dalla pratica: da lì tutto (rata registrata, cashback, attivazione) segue lo
  stesso percorso del pagamento con carta. Il cliente può caricare la ricevuta;
  un pagamento con carta fatto dopo chiude comunque la pratica.
- Un bonifico confermato a mano dallo staff su un contratto per cui il cliente
  non l'aveva scelto è a prezzo pieno.
- Percentuale confermata dall'azienda: 32%. Cambiandola, i pagamenti già
  scelti o fatti restano con lo sconto di allora.

### Quando si può pagare {#contract-prepayment}

**Regola attuale: subito, senza aspettare i documenti.** Per explicit
business request, the customer can pay as soon as the contract exists —
straight from the activation wizard, documents skipped, nothing approved yet.
`contracts/service.py::PREPAYABLE_STATUSES` = `SUBMITTED`,
`DOCUMENTS_PENDING`, `UNDER_REVIEW`, `APPROVED`, `PAYMENT_PENDING`;
`is_payable` also requires a frozen amount and `paid_at IS NULL`.

**Paying is not activating.** Business rule, restated by the business in the
same session: *le provvigioni partono solo all'approvazione*. So:

- Payment confirmed while the documents are not yet approved → `paid_at` is
  set, the SosnetCash is credited, staff are notified
  (`CONTRACT_PAID_BEFORE_APPROVAL`, audit `contract.paid_before_approval`) —
  and **the status does not move**.
- Administrator approves → `APPROVED → PAYMENT_PENDING` as always, and
  `transition_contract` sees `paid_at` already set and continues straight to
  `PAID → ACTIVATION_PENDING → ACTIVE`. That is the only point commissions
  and the network snapshot are produced, exactly as before.
- Payment confirmed when the documents are already approved
  (`PAYMENT_PENDING`) → unchanged: `PAID` → `ACTIVE` immediately.
- **Rejecting a paid contract** notifies staff (`CONTRACT_PAID_REJECTED`):
  refund, the credited SosnetCash and, on an instalment plan, cancelling the
  Stripe subscription are human decisions, never automatic. A payment that
  lands on a contract already rejected is still recorded (the money moved),
  earns no SosnetCash, and raises the same notification.

### Le tre modalità

| Piano | Come funziona |
|---|---|
| **Soluzione unica** | Un addebito, `mode="payment"`. |
| **3 rate mensili** | Abbonamento Stripe, prima rata subito, altre due addebitate da sole. |
| **12 rate mensili** | Identico, con 12 rate. |

3 rate and 12 rate are **the same mechanism** and differ only in the count.
No external financing provider is involved — SOSNET splits its own
invoice — so this needs no capability beyond ordinary card payments. (This is
what the earlier "finanziaria Stripe" question turned out to mean; see
`open-questions.md` #12.)

**Everything is created through the API, per contract.** No Stripe Product or
Price is defined in the dashboard: the Price is built inline from
`sn_agreements.gross_amount_cents`, the amount already frozen on that contract
with that customer's VAT. A fixed Price would have to be re-made by hand on
every price change and would know nothing about who is buying.

**A subscription runs forever unless told to stop**, so "12 rate" is made
true explicitly: `cancel_at` is set on the subscription right after it
exists, rather than counting invoices as they arrive — one missed webhook
delivery would otherwise keep charging somebody who had finished paying.

### Gli arrotondamenti, detti e non nascosti

A Stripe subscription bills the **same** amount every period, and a price
rarely divides evenly by 3 or 12. The instalment is rounded to the cent and
the plan's real total (`instalment × N`) is **shown next to each option**,
with the difference from the contract spelled out when there is one — at most
6 cents for 12 instalments, and exactly 0 for every price currently in the
catalog (249,00 divides cleanly by both 3 and 12).

The two obvious alternatives are worse: adding the remainder to the first
invoice requires a Stripe Product created **per contract**
(`add_invoice_items` cannot take an inline product), littering the account
with one object per sale to recover a few cents; and silently rounding up
overcharges without saying so.

### Cosa rende un contratto pagato

Only the **verified webhook**. The success URL is never proof — a customer
can open it by hand. On `checkout.session.completed` a contract already
approved moves `PAYMENT_PENDING → PAID` (one not yet approved only gets
`paid_at`, see above), which auto-cascades to `ACTIVE` through the
existing state machine, so commissions are calculated at exactly the same
point as for any other contract. For an instalment plan this happens on the
**first** payment: the contract is in force and the rest is collected
automatically.

### Prezzo del contratto: il canone per tutti i mesi {#contract-price-periods}

**Only for recurring product types** (`pricing.RECURRING_PRODUCT_TYPES` =
`ENERGY_CONTRACT`, `SUBSCRIPTION`). A `PHYSICAL` or `DIGITAL` product always
costs its listed price once, whatever `billing_period` / duration its version
carries (the admin form defaults every version to MONTHLY / 12). Shop orders
never went through this function and still charge `base_price_cents` once.

Business decision: `base_price_cents` is the **canone per
billing period** (the catalog has always printed "/mese" next to it), and a
contract costs that canone for every period of its term.
`catalog/pricing.py::contract_net_amount_cents` = `base_price_cents ×
contract_billing_periods(version)` where the periods are
`contract_duration_months / months-per-period` (MONTHLY 1, QUARTERLY 3,
ANNUAL 12), or 1 when the version has no duration. Example: *Luce Energia
Circolare privati*, 15 € /mese × 12 = **180 €** (+ IVA 22% = 219,60 € for a
business; a privato still pays no VAT, unchanged). 12 rate therefore charge
exactly the monthly canone, 3 rate a quarter of the year, soluzione unica the
year.

Before this, a 12-month contract was priced as one month. Contracts not yet
paid at deploy time had their frozen amounts recomputed once (see
`implementation-progress.md`); a paid contract is never restated.

### Cashback SosnetCash sul contratto: quando arriva {#contract-cashback-timing}

`sn_offer_versions.contract_cashback_percentage` of what the customer pays
(VAT included) — set to **100** on the SOSNET products
(*cashback dell'intero importo*). It is credited **when the money arrives**,
not at activation:

- **Soluzione unica** (or a bank transfer an admin confirms): the whole
  amount at once, key `contract-cashback:{contract_id}`, guard
  `sn_agreements.cashback_credited_at`.
- **3 / 12 rate**: **one instalment at a time** (business decision: a
  customer who stops paying after month one must not already hold the year
  in SosnetCash). The first instalment is credited by the
  `checkout.session.completed` handler (key `…:first`); every later one by
  `invoice.paid` with `billing_reason = subscription_cycle` (key
  `…:{invoice_id}`). The first invoice's own `invoice.paid`
  (`subscription_create`) deliberately credits nothing, so it can never
  double the first month. The amount is the plan's instalment, never the
  invoice's own figure. Approval of a prepaid instalment contract adds
  nothing on top.

### Rate successive

**Stripe configuration required**: the webhook endpoint must have
`invoice.paid` and `invoice.payment_failed` enabled in addition to
`checkout.session.completed` — without them Stripe still charges every month
but the app never hears of it. The subscription id is read from both invoice
shapes (`invoice.subscription` before API "basil",
`invoice.parent.subscription_details.subscription` after).

`invoice.paid` / `invoice.payment_failed` are recorded in the audit log. A
failed monthly charge notifies **both** the staff and the customer and
**does not** suspend the contract: one declined card is not grounds for
automatically cutting off somebody's energy supply — that is a decision for a
human with the context.

### Idempotenza a livello di evento {#stripe-event-idempotency}

`sn_stripe_events` records the Stripe `event.id` **before** any handler
runs; the UNIQUE constraint decides which of two concurrent deliveries
proceeds. Previously the webhook relied on each handler happening to be
idempotent on its own — true for the flows that existed, but an instalment
plan fires `invoice.paid` every month for the same subscription, so "the same
event again" and "the next instalment" had to stop being indistinguishable.
Stripe promises at-least-once delivery, not exactly-once.

## Anteprima provvigioni e provvigioni per rata {#commission-preview}

Business rules stated by the business: *solo i contratti danno provvigioni*;
the administrator's approval is what sets them going, so the administrator
must **see and accept a preview** first; a contract paid in one go pays its
commissions once, a contract paid in 3 or 12 instalments pays them 3 or 12
times, **each slice when that instalment has really been paid**.

### L'anteprima {#commission-preview-gate}

- `GET /contracts/{id}/commission-preview` (`sn_agreements.review`) —
  `commissions/services/preview.py`, read-only. Same sale resolution the
  activation will freeze (sale date, seller role at that date, chain at that
  date, Split Plan, margin), same engine, same `instalment_share`. Shows the
  plan applied, the margin, each beneficiary (rule, role, movement type,
  total), the company share, how it is spread over the customer's payments
  (schedule with dates if paid; every possible split if not), the customer's
  SosnetCash cashback (explicitly *not* a commission) and warnings.
- **Blocking errors**: if the commission cannot be calculated (no margin on the
  product, no active Split Plan for product and seller role, seller without a
  commercial role…) the preview lists them in `blocking_errors` and **cannot be
  accepted** — the contract does not start without knowing who is paid what.
- **Server-enforced gate** (`contracts/router.py::transition_contract`): a
  transition into `APPROVED / PAYMENT_PENDING / PAID / ACTIVATION_PENDING /
  ACTIVE` on a contract never activated before (and not SUSPENDED) is refused
  unless a preview was already accepted or the request carries
  `accept_commission_preview_checksum`. The server **recomputes** the preview
  and refuses (409) if the checksum no longer matches what was on screen.
- Accepted previews are stored verbatim in `sn_agreement_payout_plans` (one
  per contract, audit `contract.commission_preview_accepted`) and reopened
  from the contract's **Provvigioni** button as a log, next to the movements
  actually written. If the network changes between acceptance and activation
  the frozen snapshot at activation wins — the log shows both, it does not
  pretend they are the same.
- A contract approved before this existed and paid through Stripe does **not**
  activate on its own: the payment is recorded and it waits for an
  administrator to accept the preview.

### Le rate e le quote di provvigione {#commission-instalments}

- `sn_agreement_instalments`: one row per payment owed (1, 3 or 12), created at the
  first recorded payment (the count comes from the plan actually paid; a
  bank transfer confirmed by staff is always 1).
- Each beneficiary's commission is split with
  `run_calculation.py::instalment_share`: equal shares, remainder on the last
  one, so the slices add up **exactly** to the whole commission (e.g. 40,00 €
  on 3 rate = 13,33 + 13,33 + 13,34). Never the whole commission N times. The
  first-referrer bonus is a one-off and goes out whole with instalment 1.
- **Nothing is released before ACTIVE.** At activation every instalment
  already paid is released (`instalments.release_paid_instalments`); after
  that each newly paid instalment releases immediately.
- A paid instalment is released by emitting exactly one
  `ContractInstalmentPaid` outbox event, claimed with a conditional UPDATE on
  `sn_agreement_instalments.commission_event_id`; the dispatcher runs the engine
  for that slice (`instalment_number` of `instalments_total`) against the
  snapshot frozen at activation. `ContractActivated` no longer calculates
  anything for a contract that has instalment rows (it would pay the first
  slice twice); `ContractRenewed` is unchanged.
- Who confirms a payment: instalment 1 → the checkout webhook (or staff
  confirming a bank transfer); later ones → `invoice.paid`
  (`billing_reason = subscription_cycle`), matched by Stripe invoice id.
  A failed charge marks the row FAILED with its invoice id and releases
  nothing; staff can confirm it by hand
  (`POST /contracts/{id}/instalments/{n}/confirm`, audit
  `contract.instalment_confirmed_manually`), and Stripe's later retry of that
  same invoice then finds it already paid. `UNIQUE (contract_id, number)` and
  `UNIQUE stripe_invoice_id` make a double release impossible.

## Cashback dei contratti pagati a rate: intero in anticipo o rata per rata {#instalment-cashback}

Il cashback SosnetCash di un contratto SOSNET (percentuale del prodotto sul
totale IVA inclusa) arriva **tutto subito** se il contratto è
pagato in unica soluzione. Per 3 o 12 rate lo decide l'amministratore in
**Impostazioni → Cashback dei contratti pagati a rate**
(`organizations.settings.contract_instalment_cashback_mode`):

- `PER_INSTALMENT` — **predefinito**, la regola ora : una parte a
  ogni rata incassata (Stripe o confermata a mano), così chi smette di pagare
  non ha ricevuto il cashback delle rate mancanti.
- `UPFRONT` — alla **prima rata** il cliente riceve in un'unica ricarica il
  cashback dell'**intero contratto**, e nulla sulle rate successive. Rischio
  accettato scegliendola: se il cliente smette di pagare, il cashback è già
  stato dato (respingere o interrompere il contratto non lo storna da solo).

Regole che valgono in entrambi i casi (`contracts/service.py::
credit_contract_instalment_cashback`):

- **La scelta si applica al pagamento della prima rata e vale per tutta la vita
  del contratto.** Un contratto già accreditato in anticipo (riga di wallet con
  chiave `contract-cashback:<contratto>`, la stessa del pagamento unico) non
  riceve mai il cashback per rata, anche se l'impostazione viene cambiata dopo.
- La chiave di idempotenza per rata è il **numero della rata**
  (`contract-cashback:<contratto>:rata-<n>`), non la fattura Stripe: una rata
  fallita, confermata a mano dall'amministratore e poi riaddebitata con
  successo da Stripe sulla stessa fattura dà cashback una volta sola.
- **Una rata confermata a mano** dall'amministratore (bonifico, carta
  sistemata al telefono) dà il suo cashback come una incassata da Stripe:
  prima non ne dava nessuno.
- Nessun cashback su un contratto respinto o cessato.
- La schermata di pagamento del cliente dice come arriverà il cashback, secondo
  l'impostazione.

## La pratica di attivazione {#contract-request}

**Regola, detta dal business:** un cliente con 10 POD firma **10 contratti** —
10 per il cliente, 10 per il promoter, ognuno con il suo pacchetto, la sua
approvazione, le sue rate e le sue provvigioni — ma compila i propri dati una
volta, carica il documento d'identità una volta, sceglie il pacchetto punto per
punto e **paga una volta**.

La pratica (`sn_agreement_requests`) è il contenitore che rende possibile tutto
questo. **Non possiede niente che possieda già un contratto**: stato,
pacchetto, prezzo congelato, approvazione, rate, provvigioni restano sul
singolo contratto. Un contratto respinto, sospeso o cessato dentro una pratica
non tocca gli altri.

**Ogni contratto appartiene a una pratica** (`sn_agreements.contract_request_id`,
NOT NULL). Un contratto creato fuori dal flusso (admin "Nuovo Contratto", le
vecchie rotte `/contracts/mine` e `/contracts/for-customer`) riceve una pratica
di un solo contratto. I contratti esistenti prima della migrazione 0042 hanno
ciascuno la propria, con **lo stesso id del contratto**.

### Il percorso

Ridisegnato  su richiesta esplicita: **tutti i dati una volta
all'inizio, poi "quanti POD hai?", poi i POD sono già creati e si sceglie solo
il contratto per ciascuno. Il codice POD non si chiede.**

1. **Dati**, in un'unica schermata: intestatario (nome, cognome, email, PEC,
   IBAN), **indirizzo di fornitura** (`contract_requests.street/city/
   province/postal_code`) e **"Quanti POD hai?"** (contatore o numero, 1–50).
   La pratica nasce `DRAFT` con quel numero di POD già creati: ognuno è un
   contratto `DRAFT` senza pacchetto, con un supply point all'indirizzo della
   pratica e **nessun codice POD/PDR** e **nessun tipo energia**
   (`sn_utility_points.energy_type` nullable). Cambiare il numero in bozza
   aggiunge POD o toglie **prima quelli senza contratto scelto**, i più
   recenti per primi; un POD tolto va in `CANCELLED` (nuova transizione `DRAFT
   → CANCELLED`). Cambiare l'indirizzo della pratica sposta tutti i POD che
   erano ancora a quell'indirizzo; un POD spostato su un indirizzo suo lo
   tiene.
   - Il produttore delle provvigioni si risolve **per POD**, con le stesse
     regole di sempre (promoter che compila, o referente del cliente con
     risalita al primo sponsor attivo, auditata).
2. **Documenti d'identità** sulla pratica: identità, codice fiscale, visura
   (per chi la deve dare), più una **bolletta facoltativa** per chi ha
   un'unica bolletta con tutti i punti.
3. **Un contratto per ogni POD**: tutti i pacchetti INTERNAL attivi adatti
   alla tipologia di cliente, oppure "Stesso contratto per tutti i POD".
   **È il pacchetto a decidere se il POD è luce o gas** (il supply point prende
   `energy_type` del prodotto) e **il prezzo si congela sul contratto in quel
   momento** (`contracts/service.py::freeze_price`). Un vincolo CHECK
   (`ck_contracts_product_required`) impedisce a un contratto senza pacchetto
   di uscire da `DRAFT`. Facoltativi per POD: un indirizzo diverso, la bolletta
   o la foto del contatore.
4. **Invio** (`submit`): tutti i POD passano insieme `DRAFT → SUBMITTED →
   DOCUMENTS_PENDING`, e ciascuno va da solo in `UNDER_REVIEW` appena i
   **suoi** documenti obbligatori ci sono. Lo staff riceve **una** notifica
   per pratica. Dopo l'invio POD e contratti scelti non si modificano più: un
   altro POD è una nuova pratica.
5. **Pagamento**, solo dal cliente (il promoter compila e invia, non paga).

Senza codice POD non c'è più il controllo "stesso POD con due contratti in
corso": l'identificazione del punto reale avviene sulla bolletta, in verifica
documenti.

### Documenti: pratica o contratto

Un documento appartiene **a un contratto oppure a una pratica, mai a
entrambi** (`ck_documents_one_owner`). Per ogni casella di un contratto vale
il documento **del contratto se c'è, altrimenti quello della pratica**: la
bolletta del singolo punto vince su quella comune. Caricare un documento sulla
pratica rivaluta tutti i suoi contratti (`maybe_advance_to_under_review`). Il
fascicolo (zip/Drive) di ogni contratto include anche i documenti della
pratica.

### Un pagamento, N contratti

Paga **ogni contratto della pratica inviato, prezzato e non ancora pagato**
(`is_payable`). Un solo piano per pagamento (unica soluzione, 3 o 12 rate).

- **Unica soluzione**: una Checkout Session con **una riga per contratto**.
- **Rate**: **un solo abbonamento Stripe con una voce per contratto**. Ogni
  mese un solo addebito sulla carta, una fattura con N righe.
- L'importo di ogni riga è la rata **di quel contratto**
  (`breakdown_for(piano, prezzo del contratto)`), quindi ogni contratto
  registra esattamente la sua rata e il suo cashback; il cliente vede la somma.
- **Limite Stripe: 20 voci per abbonamento.** Oltre 20 contratti da pagare
  insieme le rate non sono offerte (resta l'unica soluzione, o due pratiche).
- Ogni sessione aperta viene congelata in `sn_agreement_checkouts`
  (quali contratti, quali importi) **prima** di mandare il cliente su Stripe;
  il webhook paga quello che dice quella riga. Le sessioni precedenti ancora
  aperte vengono fatte scadere. Se comunque due sessioni arrivano a buon fine,
  i contratti già pagati **non vengono ripagati**: lo staff riceve l'avviso
  "Pagamento doppio" e rimborsa quelle righe.
- Ogni riga del prodotto inline porta `metadata.contract_id`; al completamento
  si legge l'abbonamento e si salva su ogni contratto il suo
  `stripe_subscription_item_id`. Ogni `invoice.paid` successivo viene letto
  **riga per riga dall'API** (il payload del webhook non contiene tutte le
  righe) e ogni riga registra la rata del suo contratto: cashback con chiave
  `contract-cashback:{contract}:{invoice}`, provvigioni per rata come da
  . `sn_agreement_instalments.stripe_invoice_id` è ora unico **per
  contratto**, non globalmente.
- Una rata non riscossa manda **un** avviso allo staff e **uno** al cliente
  per tutta la pratica.
- **Cosa legge il cliente su Stripe**. Per un abbonamento la
  pagina di Stripe mostra solo "X € al mese": un cliente ha visto "340,00 € al
  mese" per una pratica da 1.020 € e non ha capito che erano 3 rate. Ogni
  Checkout della pratica porta ora sopra il pulsante di pagamento
  (`custom_text.submit`) il piano scritto per intero — "Paghi 3 rate mensili da
  340,00 €, per un totale di 1.020,00 € (3 contratti)… gli addebiti si fermano
  da soli dopo la 3ª rata" — e ogni riga la sua descrizione ("3 rate mensili da
  140,00 € · totale 420,00 €", oppure "Pagamento unico").

### Interrompere gli addebiti di un contratto

"Interrompi addebiti" (`POST /contracts/{id}/stop-billing`, staff) toglie
dall'abbonamento **solo la voce di quel contratto** (senza proration); se era
l'ultima voce, o l'abbonamento era di quel contratto soltanto, annulla
l'abbonamento. Segna `billing_stopped_at`. Il rimborso di quanto già incassato
resta una decisione umana sul pannello Stripe.

### Il catalogo è una vetrina; il promoter compila per il cliente

- **Si attiva solo con la pratica.** In "I miei Contratti" e in Home i pacchetti
  SOSNET hanno il pulsante **Dettagli**, non più "Attiva Contratto": si
  leggono, e il popup porta a "Attiva nuovo contratto", cioè la stessa pratica
  del pulsante in alto (con quel pacchetto già scelto per ogni POD).
- **Il promoter fa la stessa procedura al posto del cliente**, da "Miei
  Clienti": per un cliente appena registrato (la pratica si apre subito dopo
  la registrazione) o per uno già esistente. La pratica e ogni contratto
  registrano `activated_by_promoter_id` e `created_by_role = PROMOTER` —
  "compilata da X" lo vedono cliente, promoter e amministrazione — ma **tutto
  appartiene al cliente**: `customer_id`, documenti, pagamento.
- All'invio di una pratica compilata da un promoter il cliente riceve una
  **notifica** e un'**email** ("I tuoi contratti sono pronti") con il link a
  "I miei Contratti", dove controlla e **paga lui**. L'email è best-effort,
  dopo il commit.
- **Documenti: file o foto.** Ogni casella e gli allegati aggiuntivi hanno,
  oltre a "Carica", un pulsante **Foto** che apre direttamente la fotocamera
  del telefono (`capture="environment"`, JPG/PNG), per il cliente e per il
  promoter.
- **Accesso ai documenti di un contratto** (`documents/router.py::
  _assert_contract_document_access`): il cliente del contratto; il promoter
  che ne è produttore **o** che ha compilato la sua pratica; lo staff. Si
  controllano **entrambe** le relazioni qualunque sia il primo ruolo nel
  token: un promoter entrato con "Lavora con noi" mantiene il ruolo CUSTOMER e
  prima veniva rifiutato sui documenti dei propri clienti.

### Chi può fare cosa (`/contract-requests`)

- **Cliente**: le proprie pratiche, tutto compreso il pagamento.
- **Promoter**: le pratiche dei clienti per cui può agire (propri, o
  ereditati da un promoter disattivato sotto di lui) — compilare, documenti,
  inviare; **non pagare**.
- **Staff** (`sn_agreements.review`): vede tutte le pratiche e i tentativi di
  pagamento. Approvare e respingere restano **per contratto**, con la stessa
  anteprima provvigioni obbligatoria; "Approva i N contratti in revisione"
  manda N transizioni, ciascuna con il checksum della sua anteprima.

Un utente può essere cliente e promoter insieme: si controllano entrambe le
relazioni, non il primo ruolo del token.

### Correggere il pacchetto di un POD {#staff-repackage}

Il cliente sceglie il pacchetto punto per punto, e può sbagliarlo o non
sceglierlo affatto. Fino alla  nessuno poteva più rimediare: la
pratica del cliente non era modificabile dall'amministrazione (che poteva
riprendere solo le proprie bozze) e dopo l'invio non era modificabile da
nessuno — restava respingere il contratto e rifare la pratica.

Ora lo **staff** può scegliere o cambiare il pacchetto di un singolo POD dal
dettaglio della pratica (bottone "Scegli pacchetto" / "Cambia pacchetto",
`requests.py::staff_set_point_product`, stessa rotta
`PUT /contract-requests/{id}/points/{contract_id}/product` che usa il
cliente: è l'accesso a decidere quale delle due regole si applica).

Il confine è il denaro, non lo stato della pratica: si cambia finché quel
contratto è in `DRAFT`, `SUBMITTED`, `DOCUMENTS_PENDING`, `UNDER_REVIEW`,
`APPROVED` o `PAYMENT_PENDING` **e** non è pagato (`paid_at`), non ha
addebiti Stripe attivi e non è attivo. Il prezzo viene ricongelato subito e
il punto di fornitura diventa luce o gas secondo il pacchetto scelto; il
cambio finisce nell'audit log (`contract.package_changed_by_staff`) con
pacchetto e importo di prima e di dopo. Un link di pagamento già inviato al
cliente resta all'importo vecchio: dopo la correzione il cliente deve
riaprire il pagamento dalla sua area.

## Contract economics: IVA, tipo cliente, cashback, bonus {#contract-economics}

Three rules that had **no server-side implementation at all** before this,
plus the two configuration switches they hang off.

### IVA -- one rule, one module {#vat}

`apps/api/app/modules/catalog/pricing.py` is the single place VAT is decided.
Before it, VAT existed only as a number two React components multiplied the
displayed price by; nothing on the server ever computed it, so "the price the
customer saw" and "the price the backend would charge" were two independent
implementations.

- **Contratto per un privato: nessuna IVA.** **Contratto per azienda / P.IVA:
  prezzo + IVA.** The *customer's* kind decides whether VAT applies at all;
  the product only decides *which rate* applies when it does
  (`product_versions.tax_configuration->>'vat_percentage'`, unchanged -- there
  is still no VAT percentage hardcoded anywhere in this codebase).
- `VAT_LIABLE_CUSTOMER_KINDS = {SOLE_PROPRIETOR, COMPANY, CONDOMINIUM}`.
  Deliberately **not** the same grouping as
  `customers/service.py::PRIVATE_LIKE_KINDS`, which puts SOLE_PROPRIETOR with
  PRIVATE: that answers a different question (first/last name vs. company
  name). A ditta individuale has a person's name *and* a P.IVA.
- **Snapshotted, never recomputed**: `contracts.net_amount_cents / vat_rate /
  vat_amount_cents / gross_amount_cents` plus `sn_agreements.customer_kind` are
  frozen at creation, so an admin editing the product tomorrow can never
  restate a contract somebody already signed -- the same discipline as network
  snapshots and commission calculations.
- Rounding is `Decimal`, half-up on the cent (249,00 x 22% is exactly 54,78;
  in binary floating point it is 5477.999...).
- `catalog/pricing.py::contract_net_amount_cents` defines the taxable amount as
  `base_price_cents` -- the single figure the dashboard has always shown as the
  product price. `initial_fee_cents` / `recurring_fee_cents` have never been
  charged by any code path, so folding them in would start billing amounts
  nobody agreed to. **If the business means something else by "il totale del
  contratto", that one function is the only place that changes.**

### Chi puo comprare cosa {#product-audience}

`sn_offers.customer_type` existed but nothing ever read it, and its vocabulary
(PMI, ENERGY_INTENSIVE, ...) did not line up with `sn_clients.kind` (COMPANY,
...), so the two could never be compared. It now holds the binary business
answer: **PRIVATE / BUSINESS / BOTH** (legacy values still parse and collapse
onto BUSINESS). A customer is only offered contracts their kind may activate,
and the server rejects the rest independently -- hiding a card is never the
enforcement. Existing rows were migrated to **BOTH**, not to their literal old
value: nothing filtered on this column before, so BOTH is the only
behaviour-preserving choice.

### Cashback: tre regole distinte, mai confuse {#cashback-modes}

`catalog/pricing.py::cashback_mode_for` classifies every product into exactly
one of three, **derived** from the fields that actually drive behaviour rather
than stored in a fourth column that could drift:

| Modalita | Chi | Regola |
|---|---|---|
| `STANDARD` | Prodotti DROPSHIPPING/PARTNER (`cashback_enabled`) | Opt-in: il cliente paga il **+5%** al checkout e riceve 100% + 5% come SosnetCash. **Invariata.** |
| `AUTOMATIC_INTERNAL_SERVICE` | Contratti SOSNET e formazione (`contract_cashback_percentage > 0`) | **Automatico, senza il +5%**: pagare il contratto e' esso stesso cio' che genera il credito. |
| `NO_CASHBACK` | Tutto il resto, incluso ogni prodotto esistente oggi | Nessun accredito. |

The partner-invoice redemption (`sn_receipt_claims`, the other 5% rule) is a
separate domain entirely and is **not touched** by any of this.

The contract credit is a percentage of the **gross** (VAT included), i.e. of
what the customer actually handed over -- never a pre-discount or otherwise
inflated base. Exactly-once is enforced twice: `sn_agreements.cashback_credited_at`
as the readable guard, and the deterministic wallet idempotency key
`contract-cashback:{contract_id}` against the UNIQUE constraint on
`sn_credit_ledger` for the case the guard is raced (a replayed webhook).
`source = "CONTRACT_CASHBACK"`, distinct from `ORDER_CASHBACK_BASE` and
`INVOICE_REDEMPTION_BASE` precisely so accounting can tell the three apart.

### Bonus primo segnalatore {#first-referrer-bonus}

Sostituito dalla regola PROMOTER degli Split Plan (vedi #split-plan). Le
colonne `first_referrer_bonus_*` del prodotto restano per storico e non sono più
lette. `sn_agreements.first_referrer_agent_id` resta: dice chi ha portato il
cliente.

### Chi ha costruito il contratto {#contract-authorship}

`sn_agreements.created_by_user_id` / `created_by_role` /
`activated_by_promoter_id`. The last is set **only** when a promoter completed
the contract in place of the customer, so "Contratto attivato dal promoter X"
is shown exactly when it is true, never inferred from who happens to earn the
commission. `sn_agreement_status_log` and `sn_activity_log` remain the full
technical trail; these are the denormalized answer to the one question the
admin screen asks constantly.

## Contract state machine

```
DRAFT → SUBMITTED → DOCUMENTS_PENDING → UNDER_REVIEW → APPROVED
      → PAYMENT_PENDING → PAID → ACTIVATION_PENDING → ACTIVE
ACTIVE → SUSPENDED → ACTIVE
ACTIVE → CANCELLED
ACTIVE → EXPIRED
ACTIVE → RENEWED
RENEWED → SUSPENDED / CANCELLED / EXPIRED / RENEWED   (a renewed contract is still
                                                        in force -- it renews again
                                                        every subsequent term, not once)
EXPIRED → RENEWED / CANCELLED                          (a lapsed contract can be revived)
any pre-ACTIVE state → REJECTED
```

Only the transitions enumerated in `apps/api/app/modules/contracts/state_machine.py`
are permitted; every other transition raises `InvalidTransitionError`. Every transition
is recorded in `sn_agreement_status_log` with actor, reason, and correlation id, and
emits a domain event (`ContractSubmitted`, `ContractApproved`, `PaymentConfirmed`,
`ContractActivated`, `ContractCancelled`, `ContractRenewed`).

**Rule**: creating a contract (`DRAFT`/`SUBMITTED`) never generates a commission.
Commissions are generated exactly once, when a contract transitions into `ACTIVE`
(see `commission-engine-specification.md §Trigger`).

**Term / expiry**: entering `ACTIVE` or `RENEWED` sets `sn_agreements.activated_at` to
that moment and computes `sn_agreements.expires_at` as `activated_at +
product_versions.contract_duration_months` (12 by default for an energy contract;
`NULL` for a one-off `DIGITAL`/`PHYSICAL` product with no renewal concept). Every
renewal restarts both fields from the renewal's own timestamp — `expires_at` is never
retroactively recomputed if the product version's duration later changes, matching the
"frozen at the moment it happens" pattern used for network snapshots and commission
calculations elsewhere in this document.

**Who can move a contract through this pipeline (confirmed, then extended)**: `PATCH /contracts/{id}/status` (manual, per-hop transitions)
still requires `sn_agreements.review`, held by
ADMIN/BACK_OFFICE_OPERATOR/SUPER_ADMIN/ORGANIZATION_ADMIN, **never** by
CUSTOMER or PROMOTER (see `rbac/models.py`'s `DEFAULT_ROLE_PERMISSIONS`) --
a customer still cannot approve or activate a contract by taking a status-
transition action directly. What changed: a customer CAN now originate and
carry a SOSNET contract most of the way there themselves, through a
dedicated self-service path -- see "Self-service contract activation"
below. The two surfaces coexist: `POST /contracts` (staff, any producer)
and `POST /contracts/mine` (self-service, own account only, own referring
promoter only) both land on the exact same `Contract` row shape and the
exact same state machine.

### Self-service contract activation ("Attiva Contratto") {#contract-self-service}

Per explicit request, a customer can now activate a SOSNET (`category
= INTERNAL`) product without any promoter/admin action to get it started:

- **`POST /contracts/mine`** (`contracts/router.py::create_my_contract`,
  no special permission -- `get_current_user` only, same "self-checkout,
  own account only" shape as `POST /orders/mine`): takes a
  `product_version_id` plus the supply-point details (address, POD/PDR,
  meter number) collected by the new `contract-activation-wizard.tsx`.
  `contracts/service.py::create_contract_self_service`:
  1. Resolves the customer's own record from `current_user.user_id`.
  2. Rejects anything that isn't an `INTERNAL` product (DROPSHIPPING/
     PARTNER products go through `sn_shop_orders`, never here).
  3. Resolves the commission producer from the customer's own referral
     attribution (`_resolve_referring_agent_id_for_customer` -- same
     `CustomerAttribution`→`PromoterCode` lookup "lavora con noi"
     auto-activation uses) -- there is no self-service way to pick a
     different one; registration being invite-only is exactly what
     guarantees this attribution always exists. No attribution found ->
     `SelfServiceContractError`, loudly, rather than silently attributing
     to nobody and breaking commissions later.
  4. Creates the `SupplyPoint`/`Address` (reusing
     `customers/service.py::add_supply_point` directly -- bypassing its
     normal `sn_clients.update`-gated router, the same "call the service,
     skip the staff-only endpoint" pattern used elsewhere for self-service).
  5. Creates the `Contract` (`DRAFT`) and immediately transitions it
     `SUBMITTED` → `DOCUMENTS_PENDING` -- self-service has no "save as
     draft, decide whether to send it later" step the way a promoter/admin
     building one up by hand does.
- The customer then uploads the required documents through the same
  `ContractDocumentsPanel` every contract already used (no new upload
  mechanism) -- embedded directly in the wizard's second step, and always
  available again later from "I miei Contratti".
- **Auto-advance to `UNDER_REVIEW`** (`documents/service.py::
  upload_document` → `_maybe_advance_to_under_review`): once every required
  document type for the contract's customer kind has at least one uploaded
  document (any status -- this only means "the customer is done", not "a
  human already approved them"), the contract advances itself
  `SUBMITTED|DOCUMENTS_PENDING` → `UNDER_REVIEW` with no staff action. Not
  self-service-specific: a staff-created contract gets the identical
  courtesy advance once its documents are all in.
- **Two staff clicks left, by explicit product decision** (the user was
  asked: auto-approve documents entirely, or keep one human check before
  payment -- chose the latter): `contracts/service.py::transition_contract`
  gained `AUTO_CASCADE_AFTER = {"APPROVED": "PAYMENT_PENDING", "PAID":
  "ACTIVATION_PENDING", "ACTIVATION_PENDING": "ACTIVE"}` -- every hop is
  still a real, individually audited `transition_contract` call (network
  snapshot, outbox event, `ContractStatusHistory` row, all per-hop, exactly
  as if a human had clicked each one), just chained automatically. So:
  - Staff clicks **"Approva"** (`UNDER_REVIEW`→`APPROVED`) after actually
    looking at the uploaded documents -- the contract lands in
    `PAYMENT_PENDING` without a second click.
  - Staff clicks **"Conferma pagamento"** (`PAYMENT_PENDING`→`PAID`) once
    the initial-fee bank transfer arrives -- the contract cascades through
    `ACTIVATION_PENDING` straight into `ACTIVE` (which is exactly the hop
    that enqueues the `ContractActivated` event and triggers commission
    calculation, unchanged from before).
  - This cascade is general, not gated to self-service-originated
    contracts -- a staff-created contract gets the same two-click path.
  - The admin contracts panel's status-transition dropdown needed **no
    changes**: it already only ever offers the next state-machine-valid
    target for a manual click; the cascade happens server-side, so picking
    "APPROVED" there simply comes back already at `PAYMENT_PENDING`.

## Condivisione dei link: bottoni per app, non solo copia {#share-buttons}

Every place a link is shared — the promoter's personal link, "Invita un
amico", a single product a promoter recommends, and the personal link an
admin hands to a newly created root promoter — offers the same set:

**WhatsApp · Telegram · SMS · Email · Altro · Copia link**

- Each destination is a **plain link**, not an SDK: no third-party script, no
  tracking pixel, nothing added to the bundle. The target app opens with the
  message and the URL already filled in.
- **SMS** and **Altro** (the phone's own share sheet, for Messenger, Signal,
  AirDrop, whatever is installed) appear only on touch devices, via a
  `@media (pointer: coarse)` rule rather than a JavaScript check — no
  hydration mismatch, no state to keep in sync.
- **Copia link** copies straight to the clipboard and deliberately does NOT
  open the native sheet first: somebody who pressed "Copia link" has already
  decided.
- **Inline nearly everywhere**: Invita un amico, the admin's root-promoter
  result, and the promoter header bar. In the header the labels are hidden
  below `sm` and only the icons show — that bar is on every page of the
  promoter dashboard, and six labelled pills would wrap onto three lines on a
  phone and push the page down. The labels are hidden, never removed, so a
  screen reader and a long-press still name the destination.
- The one exception is a **product card in a grid**, where a row per card
  would crowd out the product itself: there the same set opens in a small
  sheet.

One component, `components/share-buttons.tsx`, backs all of it: adding a
destination is one entry in its `TARGETS` list and it appears everywhere at
once.

## "Invita un amico": rete a un livello, staccata, senza provvigioni {#friend-referrals}

A **second, completely separate** referral structure, added on explicit
request: "non c'entra nulla con l'attuale rete, è una cosa staccata e separata
che ogni cliente ha".

- **Naming (corrected same day)**: the feature is **"Invita un
  amico"** everywhere a person can read it. The first pass used
  "segnala/segnalatore", which the business rejected -- in Italian *segnalare*
  carries a reporting-on-somebody connotation, wrong for what is meant to be
  a warm invitation. Internal identifiers keep the neutral English
  `sn_friend_invites`. The commission-side "Bonus primo segnalatore" label was
  renamed for the same reason ("Bonus primo invito"); the stored
  `movement_type` is unchanged.
- **Who has one**: everyone with a login, promoter or not. Each gets a
  personal invite code (`sn_friend_invite_codes`, prefix `INV-`), created
  lazily the first time they open "Invita un amico". Codes issued before the
  rename (prefix `SEG-`) keep working -- resolution is an exact match on the
  whole code, never on the prefix.
- **What it holds**: one flat level. `sn_friend_invites` records who signed up
  through whose link. No hierarchy, no closure table, **no commissions** --
  the whole thing could be dropped tomorrow without changing a single euro.
- **Where the invited customer actually lands in the COMMERCIAL tree** is
  decided by the existing rules and is untouched by this:
  - the referrer **is** an active promoter → their own tree, exactly as
    before;
  - the referrer is **not** → under the referrer's **own** promoter
    (`friend_referrals/service.py::promoter_code_for_referrer`), because a
    plain customer earns nothing and cannot have a downline. If that promoter
    has since been deactivated, the same walk-up applies as everywhere else
    (see #terminated-promoter-fallback).
  A promoter's normal link feeds the list too, so their segnalati list and
  their tree agree — the list is purely additive.
- **When somebody "counts"**: only once one of their contracts is genuinely in
  force (`ACTIVE`/`RENEWED`), which is the business's explicit choice over
  "has started a contract". The list shows three states so progress is still
  visible: `INVITED` / `IN_PROGRESS` / `ACTIVE`. State is **derived** from
  sn_agreements at read time, never stored: a stored flag would need an event hook
  on every path that activates, renews or cancels, and the first one anybody
  forgot would leave the count permanently wrong.
- **The reward, one every 10**: at 10, 20, 30 ... activated invitees the
  person may request **un bonus di 10 € in cashback omaggio**; it repeats at
  every multiple. The wording lives in ONE place,
  `friend_referrals/models.py::REWARD_DESCRIPTION`, and is sent to the
  dashboard; the amount is `REWARD_CENTS`. Milestones are absolute, and
  `uq_friend_referral_claim_user_milestone` makes each claimable exactly once,
  ever. Somebody who never claimed at 10 and is now at 23 is offered 10 first,
  then 20 — they are not silently skipped past what they earned.
- **Credited on confirmation**: a claim is a *request* that notifies staff
  ("Premi invito" in the admin dashboard). Marking it delivered credits the
  10 € of SosnetCash to the referrer's wallet, once per claim (idempotency key
  `friend-referral-reward:<claim id>`), and the note is shown to the customer.
- **Privacy**: the list shows an invited person's **name and state only** —
  never their email, phone or address. Sharing a link with somebody does not
  entitle you to their contact details.
- **Notifications**: the inviter is told when one of their people goes
  active, and whether that unlocked a gift (`FRIEND_REFERRAL_ACTIVATED`);
  staff are told about a request (`FRIEND_REFERRAL_REWARD_REQUESTED`); the
  requester is told the outcome (`FRIEND_REFERRAL_REWARD_HANDLED`).

## "Lavora con noi": quali documenti si firmano {#collaboration-documents}

Becoming a promoter has always required accepting a collaboration agreement
and confirming with an emailed OTP. Two things were wrong with it until now:

1. **The text shown was not the contract.** It was a one-paragraph summary
   hardcoded in `customer-promoter-application-card.tsx` — so the app
   displayed something nobody had drafted as a contract, and updating the
   real one would not have changed what people saw.
2. **There was one acceptance where the paper form has more than one.**

### Dove vive il testo

`apps/api/app/modules/network/collaboration_documents.py`, on the server, and
served to the dashboard by `GET /network/agents/apply/documents`. Deliberately
not in a React component:

- it is what people legally sign, so there must be exactly one copy of it;
- the acceptance record stores the **version** somebody actually saw, which is
  only meaningful if text and version are defined together;
- changing it needs no frontend release.

It travels as **structured blocks** (heading / paragraph / clause / bullets /
table / signature), never as markup: the dashboard decides typography and
never interprets HTML. A test asserts no document contains `<` or `>`.

### I documenti

| Chiave | Cosa | Perché è separato |
|---|---|---|
| `CONTRACT` | Il contratto di procacciamento di affari, integrale (16 articoli, 77 clausole numerate) | — |
| `SPECIFIC_CLAUSES` | **Allegato al contratto**: approvazione specifica delle clausole (artt. 1341 e ss. c.c.) + Allegato A e Allegato B | La legge richiede che le clausole vessatorie siano approvate separatamente dal contratto, quindi non può essere accorpato al documento sopra. |

**Le tabelle di Allegato A e B mancano ancora.** I due allegati sono
dichiarati e descritti, ma le cifre non ci sono: il testo fornito per
l'allegato era un duplicato del contratto e non conteneva alcuna tabella.
Sono numeri che le persone firmano, quindi non sono stati inventati. I due
paragrafi segnati `DA COMPLETARE` in `_ATTACHMENT_BLOCKS` vanno sostituiti
con `table(columns=[...], rows=[[...]])` e la `version` del documento
incrementata; la dashboard rende la tabella da sé.

**Il testo non parla mai della carta.** Il contratto cartaceo è la *fonte*
di queste parole, non il loro argomento: a chi legge sullo schermo non si
dice cosa richiederebbe un foglio che non ha mai visto. Un test lo verifica.

### Come si firma

Immutato: si leggono i documenti, si spunta **una casella per documento**, poi
si conferma con il **codice OTP** che arriva via email — la prova che ha
acconsentito il titolare dell'account e non solo chi è loggato.

### Cosa viene registrato

`sn_promoter_profiles.collaboration_accepted_documents`, JSONB:
`{chiave: {"version": ..., "accepted_at": ...}}`, una voce per documento. Una
mappa e non una coppia di colonne per documento, perché l'elenco dei documenti
è una decisione di business che cambierà ancora e ogni cambio non deve costare
una migrazione. Le colonne preesistenti
(`collaboration_contract_version`/`collaboration_accepted_at`) restano e
continuano a essere allineate per il contratto principale.

**Il server non si fida della casella.** L'applicazione deve inviare
`{chiave: versione}` per **ogni** documento attualmente richiesto, e il server
rifiuta se ne manca uno o se la versione è vecchia (la pagina era aperta
mentre il testo cambiava). Una casella dice solo che qualcuno ha cliccato;
una versione dice **quale testo** è stato accettato.

**Aggiungere o cambiare un documento**: si aggiunge una voce a
`COLLABORATION_DOCUMENTS`, o si incrementa la sua `version`. La dashboard
rende automaticamente un pannello e una casella in più, e il backend inizia a
pretendere quell'accettazione dal deploy successivo. Mai modificare un testo
senza incrementare la versione: significherebbe riscrivere in silenzio ciò che
qualcuno ha già firmato. Le accettazioni già registrate non vengono mai
riscritte, e i promoter esistenti hanno la mappa vuota — non è stato inventato
un consenso a un testo che non avevano mai visto.

## Commercial network rules

- No cycles, no self-parenting, no duplicate active edges, no cross-organization
  edges. Enforced in `network` domain service before any closure-table write.
- Every move of an agent to a new parent is a single DB transaction: update
  `sn_tree_nodes.direct_parent_agent_id`, insert a closed-off `sn_tree_links` row and
  a new one, recompute affected `sn_tree_paths` rows, insert
  `sn_tree_moves`, write an audit row, invalidate branch-count caches.
  Moves require `requested_by`; `approved_by` is required unless the mover has
  `network.manage` and self-approval is explicitly allowed for that role (PLACEHOLDER —
  see open-questions.md #2).
- A contract's commercial chain is frozen at activation via `sn_tree_snapshots` /
  `network_snapshot_id` on the contract. Subsequent moves of any agent in that chain
  never retroactively change attribution, past calculations, or past ledger entries.

### New promoter suggest-then-approve workflow

Every new collaborator, however they're created, only ever gets SUGGESTED --
never immediately live:

- `POST /network/agents` (an ADMIN adding a promoter anywhere in the org
  tree) and `POST /network/agents/recruit` (a promoter enrolling their own
  direct collaborator) both now create the agent with
  `status = PENDING_APPROVAL`, not `ACTIVE`.
- A `PENDING_APPROVAL` agent already exists and is visible in the network
  tree (it's a real row, a real node) but cannot be used as a contract
  producer -- `contracts/service.py::create_contract` already rejected any
  non-`ACTIVE` producer before this feature existed, so no new guard was
  needed there; the approval workflow rides entirely on a check that was
  already correct.
- Only `network.approve` holders can turn a suggestion into a real
  collaborator: `PATCH /network/agents/{id}/approve` (→ `ACTIVE`) or `PATCH
  /network/agents/{id}/reject` (→ `TERMINATED`, with an optional reason kept
  on the row, never a hard delete). `network.approve` is granted only to
  `SUPER_ADMIN`/`ORGANIZATION_ADMIN` -- the "amministratore principale" the
  user asked for -- deliberately NOT to a plain `ADMIN`, who already holds
  `network.manage` (can suggest) but not `network.approve` (cannot confirm
  their own suggestion). Re-approving/re-rejecting an already-decided agent
  is rejected (`AgentApprovalError`), not silently accepted.
- Both creation paths and both approval outcomes fire a notification (see
  `database-model.md §7`) -- `PROMOTER_APPROVAL_REQUESTED` to every
  `network.approve` holder when something needs a decision,
  `PROMOTER_APPROVED`/`PROMOTER_REJECTED` back to the suggested agent's own
  `user_id` if they already have a login.

## Commission payment tracking

Stati del movimento: PENDING (calcolato) → APPROVED → PAYABLE → PAID, con
CANCELLED (annullato prima del pagamento) e le righe REVERSAL negative degli
storni; le quote dell'azienda nascono RETAINED. Tutte le transizioni passano da
`commissions/services/lifecycle.py::transition`, anche in blocco
(`POST /commissions/movements/transition`), tutto-o-niente, con le righe
bloccate durante l'operazione e una riga di audit ciascuna. Pagare richiede di
aver prima approvato. `PATCH /commissions/movements/{id}/pay` e
`/contracts/{id}/pay-all` restano, sulle sole righe già approvate.

### Admin commission traceability (`GET /commissions/movements`)

Every `CommissionMovement` already had a matching `CommissionCalculationStep`
row (contract → calculation → per-beneficiary step, computed at activation
time by `run_calculation_for_contract`) carrying `rank_at_calculation`,
`base_amount_cents`, `already_distributed_cents`,
`entrepreneurial_difference_cents`, and a human-readable `explanation` string
-- none of it was ever exposed through any endpoint before this. The new
endpoint (admin-tier only -- it is org-wide, unlike `commissions.read_branch`
which `TEAM_LEADER`/`PROMOTER` also hold for their own branch, so it cannot
reuse that permission) joins all of this together per movement: which
contract, which customer, which promoter earned it, their depth below the
contract's producer (`sn_tree_snapshot_nodes.depth`, frozen at activation --
0 is the producer themselves), their rank AT calculation time vs. their rank
NOW, and the full breakdown of how the amount was derived. Surfaced in the
admin "Provvigioni" tab (`admin-commissions-panel.tsx`) as an expandable
ledger row per movement, plus `GET /commissions/movements/by-level`
(`commissions/services/admin_ledger.py::get_commission_totals_by_level`) for
the per-network-level rollup (contracts / revenue / commission generated at
each depth).

## Il vecchio modello a gradi (dismesso)

Gradi (oggi SosPromoter 1-3, SosLeader 1-4, SosManager 1-5), gettoni per grado, differenza imprenditoriale, regola del 33%,
valutazione mensile dei gradi e bonus primo segnalatore appartenevano al
modello precedente e non sono più usati dal motore. Le tabelle dei gradi
restano per storico; la funzione della regola del 33% (`policies/branch_cap.py`)
resta isolata e non collegata. Il bonus a chi porta un cliente ora è la regola
PROMOTER di uno Split Plan.

## Renewals & reversals

- A renewal is a status transition on the **same** contract row (`ACTIVE`/`EXPIRED` →
  `RENEWED`, or `RENEWED` → `RENEWED` for the year after that), not a new contract --
  see "Term / expiry" above for how `activated_at`/`expires_at` are recomputed each
  time. It is also a new `sn_agreement_events` row of type `RENEWED` plus a new commission
  calculation; it does not mutate the original calculation or its movements.
- A reversal ("storno") never deletes or edits a prior `sn_payout_entries` row. It
  creates a new movement with `movement_type = REVERSAL`, linked via
  `sn_payout_reversals.original_movement_id`, carrying a negative amount, an
  explanation, and the recovered period. Formula for partial-period recovery
  (PLACEHOLDER — see open-questions.md #4):
  `refund_cents = original_amount_cents * remaining_months / total_contract_months`.

## Support tickets

- Anyone opening a ticket (a `CUSTOMER` or `PROMOTER`) can only ever see and reply to
  their **own** tickets -- there is no shared inbox between a customer and the
  promoter who referred them. Staff (any admin-tier role with `sn_support_cases.respond`) sees
  every ticket in the organization and can reply to any of them.
- `Ticket.opened_by_role` and `TicketMessage.author_role` are snapshots taken at
  creation time, not derived from the user's current roles at read time -- the same
  "frozen at the moment it happens" rule used for network snapshots and commission
  calculations. A later role change never rewrites who a past ticket/message
  "belongs to".
- A staff reply on an `OPEN` ticket automatically moves it to `IN_PROGRESS` -- the
  ticket owner should see "someone is looking at this" without the admin having to
  remember a separate status update. Only staff (`sn_support_cases.respond`) can set
  `RESOLVED`/`CLOSED`; the ticket owner can only imply it's solved via a message.
- A ticket can optionally reference a `contract_id`, letting a customer or promoter
  open a ticket directly "about this contract" instead of the admin having to guess
  which one they mean from free text.

### Search, filter, and deletion

- The admin ticket list (`AdminTicketsPanel`) can be filtered by opener
  (customer/promoter), category, and status, plus a free-text search over
  subject and opener name. Filtering is entirely client-side (the ticket
  list for one organization is small enough that this is simpler than
  adding query params to `GET /support/tickets`) -- if the dataset grows
  large enough to matter, move this filtering server-side rather than
  fetching the whole list.
- A ticket can be **permanently deleted only once its status is
  `RESOLVED`** (not `CLOSED` -- deliberately narrower, matching exactly
  what was asked for; revisit if `CLOSED` should also be eligible). The
  delete control (in both the ticket list row and the ticket detail view)
  is disabled for any other status, so there is no way to trigger the
  attempt from the UI on a non-resolved ticket. The backend enforces the
  same rule independently (`support/service.py::delete_ticket`, raising
  `TicketDeletionError` -> `400`) -- the frontend disabled-state is a UX
  courtesy, not the actual guard.
- Deletion always shows a confirmation dialog naming the ticket subject
  before calling `DELETE /support/tickets/{id}`; there is no direct delete
  with no confirmation step anywhere in the UI.
- Gated by a new `sn_support_cases.delete` permission, deliberately narrower than
  `sn_support_cases.respond` (granted to `SUPER_ADMIN`/`ORGANIZATION_ADMIN`/`ADMIN`
  only, not `BACK_OFFICE_OPERATOR`) -- same "narrower than the capability
  that looks like it should cover it" pattern as `network.approve` (see
  `security-model.md`), since permanently destroying a ticket is more
  consequential than replying to one.
- Deleting a ticket also deletes its `TicketMessage` rows in the same
  transaction (no FK `ondelete` cascade exists at the DB level) and
  records an audit entry (`action="ticket.deleted"`, with the subject/
  category/status snapshotted into `previous_value`) before the rows are
  removed -- the audit trail survives even though the ticket itself no
  longer does.

## Notifications

See `database-model.md §7` for the table shape. Behavior:

- **Who gets what**: `CONTRACT_CREATED`/`TICKET_CREATED`/
  `PROMOTER_APPROVAL_REQUESTED` fan out to every user holding a role in a
  fixed set (`notifications/service.py::STAFF_NOTIFY_ROLES` for the first
  two, the narrower `APPROVAL_NOTIFY_ROLES` for the third -- only
  `network.approve` holders can act on an approval request, so only they
  are told about one). `COMMISSION_EARNED`/`PROMOTER_APPROVED`/
  `PROMOTER_REJECTED` go to exactly one specific user -- the beneficiary
  agent's own `user_id`, when they have a login at all (an agent with no
  `user_id` -- a collaborator who predates having their own account --
  simply generates no notification for that event, not an error).
- **The actor never notifies themselves**: whoever triggered the event
  (created the contract, opened the ticket) is excluded from that event's
  own fan-out (`notify_roles(..., exclude_user_id=actor_user_id)`) -- an
  admin creating a contract doesn't need to be told they just did that.
- **Read state is per person**: marking a notification read only affects
  the row for that recipient; a fanned-out event that reached five admins
  produces five independent rows, so one admin dismissing it doesn't
  silently clear it for the other four.
- **No push, no email** -- notifications are in-app only, polled every 25s
  by the frontend. Real-time delivery (WebSockets/SSE) and email digests are
  future work, not built here.

## Promoter reassignment

- An admin can move a customer's attribution from one promoter to another
  (`POST /customers/{id}/reassign-promoter`) -- but a customer can never end up
  with NO promoter ("nessuno può stare senza promoter che lo invita" is a closed
  circuit both at registration and afterward): reassignment is rejected if the
  customer has no existing `sn_client_attributions` row to correct in the first
  place (e.g. a customer created directly by admin, never through a referral
  link, has none).
- Reassigning to the SAME promoter the customer is already attributed to is
  rejected as a no-op, not silently accepted -- it would create a meaningless
  `sn_attribution_fixes` audit row.
- Every reassignment writes an `sn_attribution_fixes` row (previous promoter,
  new promoter, who requested it, why) -- this table existed since the first
  session's schema but had no code path writing to it until this feature.
- Reassignment only changes future commission attribution going forward; it never
  retroactively touches `sn_tree_snapshots` or past `sn_payout_entries` for
  contracts already activated under the previous promoter (same "frozen at
  activation" rule as everywhere else commission chains are involved).

## Photo uploads

- Customer, promoter, and product photos are stored in a bucket
  (`sosnet-media`/`S3_BUCKET_MEDIA`) that is deliberately SEPARATE from and less
  restrictive than the documents bucket (`sosnet-documents`): public-read, no
  signed URLs, because these are ordinary profile/product photos, not sensitive
  documents. Never put anything sensitive in this bucket -- see
  `security-model.md §Documents`.
- Uploads are validated server-side regardless of what the browser claims:
  content-type must be one of `image/jpeg|png|webp|gif`, max 5 MB
  (`foundation/storage.py::upload_media`). A new upload never overwrites the
  previous photo's object in place -- it gets a fresh random key and the
  `photo_url` column is repointed; the old object is simply orphaned (not worth
  a cleanup job for a handful of KB-sized images).
- If no photo has been uploaded, `photo_url` is `NULL` and every list/detail view
  shows a generic person icon -- never a broken `<img>` tag.

## Contract documents

- Every contract requires `IDENTITY`, `FISCAL_CODE`, and `UTILITY_BILL`
  (`documents/service.py::BASE_REQUIRED_DOCUMENT_TYPES`); a customer of kind
  `COMPANY` or `CONDOMINIUM` additionally requires `CHAMBER_OF_COMMERCE`
  (`COMPANY_LIKE_KINDS`). This is a hardcoded, honest default in the service
  layer, not read from the pre-existing `sn_offer_versions.required_documents`
  jsonb column -- that column has never actually been populated or wired to
  any behavior, so treating it as configurable today would be pretending.
- A `SOLE_PROPRIETOR` (ditta individuale / partita IVA) is **offered** the
  `CHAMBER_OF_COMMERCE` slot but is never blocked by it
  (`CHAMBER_OF_COMMERCE_OPTIONAL_KINDS`). They are a
  business for VAT (`catalog/pricing.py`), but a professionista with a
  partita IVA is not in the Registro Imprese and has no visura to give:
  demanding one would strand exactly the customers who cannot produce it,
  while hiding the slot would leave the ones who can with nowhere to put it.
  The slot carries `required: false`, and the auto-advance to `UNDER_REVIEW`
  gates only on the required ones.
- Beyond the fixed slots, anyone who can upload to a contract can attach
  **extra documents** of type `OTHER`, each carrying a
  `description` its uploader writes ("Carta d'identità retro", "Delega
  firmata", "Contratto di locazione"). The description is mandatory for
  `OTHER` and ignored for every other type: a slot document is already named
  by its type, and accepting a caller-supplied label there would let a file
  land in the identity slot calling itself something else. Extra documents
  accumulate -- a second one does not supersede the first, unlike a second
  upload into the same slot -- and never gate the contract.
- `GET /contracts/{id}/documents` returns one row per *slot* for that
  customer's kind -- each with `required`, and with `document: null` when
  nothing has been uploaded yet, so "missing" is a first-class, visible
  state, not silence -- plus an `extra` array holding every attachment no
  slot accounts for. That second list also catches a document whose slot has
  since disappeared (a visura uploaded while the customer was registered as
  a company, later corrected to `PRIVATE`): the file is still in the bucket
  either way, and a documents list must never quietly hide one.
- Either the customer (their own contract only) or staff can upload a
  document; only staff can review (approve/reject with a note). This covers
  both the normal flow (customer uploads, admin reviews) and the exception
  the user specifically asked for: a customer sends a document some other
  way (email, in person) and an admin uploads it into the system on their
  behalf.
- Uploading a document does not, by itself, change contract status --
  reviewing/transitioning is a separate, explicit action. The state machine's
  `SUBMITTED`/`UNDER_REVIEW` → `DOCUMENTS_PENDING` transition is how staff
  flags "this contract can't proceed until the customer completes their
  paperwork"; the transition's `notes` field is where staff records *which*
  document is missing, surfaced back to the promoter's own network view
  (`get_branch_contracts`'s `admin_note` field) so they know what to chase.
- See `security-model.md §Documents` for how these files are stored --
  private bucket, presigned-URL-only access, never a public or guessable
  link.

## Il fascicolo di un contratto {#contract-dossier}

Un contratto non vive solo qui dentro: prima o poi la pratica va mandata a
un fornitore, a un commercialista, a un legale. Fino a  l'unico
modo era aprire gli allegati uno per uno dai link a scadenza, risalvarli a
mano, e ricopiare i dati del cliente da tre schermate diverse.

- **Il contenuto lo costruisce un solo modulo**, `contracts/dossier.py`:
  tutti gli allegati del contratto più un PDF riassuntivo di contratto e
  cliente. Due sbocchi -- uno zip scaricato dal browser
  (`GET /contracts/{id}/dossier.zip`) o una cartella su Google Drive
  (`POST /contracts/{id}/dossier/drive`) -- e un solo posto che decide cosa
  ci finisce dentro, così le due strade non possono divergere.
- **Nome**: `<nome cliente>-<id contratto>`, per l'archivio e per la
  cartella. Il nome cliente è quello mostrato ovunque nel gestionale
  (`customers/service.py::display_name_for`), l'id è l'UUID intero. Gli
  accenti restano; spariscono solo i caratteri che romperebbero un percorso
  (`/ \ : * ? " < > |`, i controlli), i punti e gli spazi finali (Windows li
  taglierebbe comunque, e un nome tagliato da altri non è più quello scritto
  nel database) e i nomi riservati DOS.
- **Il PDF contiene tutto** quello che serve a chi legge la pratica senza
  avere accesso al gestionale: intestatario, tipologia, codice fiscale e
  P.IVA, dati societari, recapiti, indirizzi, punto di fornitura con POD/PDR
  e matricola, prodotto, importi netto/IVA/lordo, modalità e stato del
  pagamento, IBAN, promoter che ha attivato e promoter che ha portato il
  cliente, e l'elenco degli allegati con il loro stato di verifica.
- **Un allegato irrecuperabile non fa fallire il fascicolo.** Se un file non
  si legge dal bucket (cancellato a mano, migrazione storage andata storta),
  al suo posto entra un `.txt` che dice quale documento manca e perché. Il
  resto del dossier serve comunque, e chi apre la cartella deve *leggere*
  cosa non c'è invece di accorgersene contando i file.
- **Permesso: `sn_stored_files.review`**, non `sn_stored_files.download`. Il secondo ce
  l'ha anche il cliente per i propri documenti; qui si scarica l'intero
  fascicolo di una pratica -- anagrafica, IBAN, riferimenti di pagamento --
  ed è roba da amministrazione, cioè esattamente le stesse persone che quei
  documenti li verificano uno per uno. Ogni download e ogni invio su Drive
  finiscono nell'audit log (`contract.dossier_downloaded`,
  `contract.dossier_sent_to_drive`).
- **Google Drive** (`integrations/google_drive.py`): un amministratore
  autorizza una volta il proprio account, e da lì in poi il pulsante
  funziona per tutti gli amministratori dell'organizzazione. Lo scope è
  `drive.file`, non `drive`: l'applicazione vede e tocca soltanto ciò che ha
  creato lei, non può leggere né elencare il resto di quel Drive. Il refresh
  token vive in `Organization.settings` con lo stesso trattamento delle
  chiavi Stripe: non torna mai indietro da nessuna risposta.
- **Premere due volte "Invia su Drive" non duplica niente**: se la cartella
  esiste già viene riusata, e un file con lo stesso nome viene sostituito,
  non affiancato. Il criterio è il nome, perché il nome è ciò che vede chi
  apre la cartella.
- L'upload è **resumable**, non multipart: Drive documenta il multipart fino
  a 5 MB e un allegato qui può arrivare a 15 (`MAX_DOCUMENT_BYTES`).
  Scegliere la strada che funziona solo per i file piccoli significa
  aspettare la prima foto di bolletta fatta con un telefono recente per
  scoprirlo.

## Password reset

- `POST /auth/forgot-password` always returns success regardless of whether the
  email exists for that organization -- the same enumeration-safety principle as
  login. If the account is real, a `sn_password_recoveries` row is created: an
  opaque random token (only its sha256 hash persisted), expiring in 60 minutes,
  single-use (`used_at`).
- Email delivery is real SMTP when `SMTP_HOST` is configured (`foundation/email.py`); if
  not, the reset link is written to the API process log only
  (`docker compose logs api`) -- **never** to `sn_activity_log` or any other place a
  web-UI role could read it, since that would let staff take over any account by
  reading its reset link. This is a genuine, working fallback, not a stub: the
  link is real and valid the moment it's generated, only its delivery channel
  differs.
- **Branded HTML email**: this was the one email in the
  whole platform still sent as plain text via a separate, since-removed
  `foundation/email.py::send_email` helper -- every other email (OTP codes,
  cashback credited, order/redemption notifications, ...) already used the
  shared branded template (`foundation/email_templates.py::render_email`, logo +
  consistent styling + a CTA button). Password reset now uses the exact
  same `send_html_email`/`render_email` path as everything else, so it is
  never the odd one out.
- `POST /auth/reset-password` (token + new password) revokes every active session
  for that user on success -- a password reset is exactly the moment to assume the
  old password may have leaked, so anyone still logged in with it is logged out.
  It also clears `failed_login_attempts`/`locked_until`, so completing a reset is
  the normal way out of a lockout, and marks the account email-verified if it
  wasn't already (see `#account-gates`: clicking an emailed link is
  the same proof of inbox control the dedicated verification link gives).
- Both endpoints are rate-limited per client IP (`foundation/rate_limit.py`, Redis
  fixed-window counter) -- 5 requests/5min for `forgot-password`, 10/5min for
  `reset-password` -- independent of the per-account lockout in `authenticate`.

### Nessuna deviazione del recapito

Il link di reset va **sempre e solo** alla casella dell'account che lo
richiede, amministratori compresi. Non esiste alcun indirizzo di delega né
un elenco di account il cui reset venga recapitato altrove: chi controlla
una casella diversa da quella dell'account non deve mai poter prendere il
controllo di quell'account. `sn_activity_log.new_value` registra solo
l'esito dell'invio (`sent` / `logged_only`), mai il token.

## Internal wallet

Every user (customer or promoter, whether or not they also hold the other
role) has an internal EUR wallet, styled after a cryptocurrency wallet: an
address (`0x` + 40 hex chars, cosmetic only -- no real blockchain), an
integer-cents balance, and a global append-only transaction ledger
(`sn_credit_accounts`/`sn_credit_ledger`, see `database-model.md §9`). This is a
purely internal, virtual balance -- there is no connection to real banking
rails, no payment provider integration, and no withdrawal path to real
money, by design.

- **Cashback / top-up**: after a customer buys a product, an admin can
  credit ("bonifica") an arbitrary amount to that customer's wallet,
  optionally linked to the contract that earned it (`reference_contract_id`)
  -- or as a plain, purchase-unrelated recharge. Gated by `wallet.manage`
  (`SUPER_ADMIN`/`ORGANIZATION_ADMIN`/`ADMIN` only, deliberately not
  `BACK_OFFICE_OPERATOR` -- same sensitivity tier as
  `commissions.evaluate_ranks`). The wallet is created lazily on first
  credit if the recipient never had one.
- **Omaggio di benvenuto**: every account can claim a one-off
  **20 SosnetCash** welcome bonus (`wallets/service.py::WELCOME_BONUS_CENTS`,
  `source = "WELCOME_BONUS"`), via a card on the dashboard home that
  disappears for good once claimed. Self-service, authentication-only, and
  always credited to the caller's **own** wallet -- the user id comes from
  the session, never the request.
  - **"Exactly once, forever" is enforced by the ledger itself**, not a
    separate flag: the transaction's `idempotency_key` is derived from the
    user id (`welcome-bonus:{user_id}`) and `sn_credit_ledger` has a
    UNIQUE constraint on it. A double-click, a retry, or two concurrent
    requests can only ever produce one row -- and a repeat claim is a
    harmless no-op returning the original row, not an error. There is
    deliberately no second "claimed" column that could drift out of sync.
  - Like the admin top-up, this **mints credit from nothing**, a conscious
    exception to the anti-loop rule below. It is a fixed code constant
    rather than an admin-editable setting precisely because of that:
    changing the amount takes a deploy and leaves a git trail.
  - Eligibility was an explicit business decision: it applies to **every**
    account, including the ones that already existed when it shipped, not
    only new signups.
- **Peer-to-peer transfer**: any wallet holder can send money to any other
  wallet in the same organization by address, no relationship required
  (like a real crypto wallet) -- self-transfer and cross-organization
  transfers are both rejected. Self-service, gated only by authentication
  (the caller's own wallet is always the source, resolved from their own
  login, never from the request body) plus a per-IP rate limit (20
  requests/60s on `POST /wallets/transfer`) against scripted abuse.
- **Balance integrity**: a debit can never take a wallet below zero --
  enforced both by an atomic compare-and-swap `UPDATE` at write time and by
  a DB `CHECK (balance_cents >= 0)` constraint as defense in depth. Every
  credit/transfer/reversal request carries a client-generated
  `idempotency_key`; a retried request with the same key returns the
  original result instead of double-applying.
- **Reversal**: an admin can correct a mistaken `ADMIN_CREDIT` or `TRANSFER`
  (`wallet.manage`-gated `POST /wallets/admin/transactions/{id}/reverse`).
  This inserts a new, linked `REVERSAL` row -- the original is never
  mutated, same append-only discipline as `sn_payout_reversals`. Reversing
  a `TRANSFER` re-debits the original recipient, which can itself fail with
  "saldo insufficiente" if they've since spent the funds; this is an
  accepted, documented outcome, not a bug. A `REVERSAL` row can never itself
  be reversed.
- **Notifications**: the recipient of a credit or transfer gets an in-app
  notification (`CASHBACK_RECEIVED` / `WALLET_TRANSFER_RECEIVED`). An
  `ADMIN_CREDIT` (the "Ricarica" top-up above) also gets a branded email
  (`wallets/service.py::credit_wallet` → `_send_wallet_credited_email`) -- best-effort, fires after the credit is already
  committed. The one exception: a partner-invoice cashback credit
  (`reference_invoice_redemption_id` set) is skipped here on purpose, since
  `invoice_redemptions/service.py::confirm_payment` already sends its own
  richer email (partner name, base+bonus split) right after calling
  `credit_wallet` -- this flag is exactly how the two are told apart, so
  a redemption credit never doubles up on emails.
- **Admin visibility**: `GET /wallets/admin` lists every wallet's balance
  org-wide; `GET /wallets/admin/{user_id}` and
  `GET /wallets/admin/{user_id}/transactions` show one user's wallet and
  history (does **not** lazily create a wallet just by viewing -- an admin
  looking at a user who never transacted sees "no wallet yet");
  `GET /wallets/admin/transactions` is the global ledger, filterable by
  type/user, with CSV export in the dashboard.
- **Peer-to-peer transfer is denied by default** (`Wallet.can_transfer`) for every wallet, customer or promoter -- an admin must
  enable it individually per promoter (`PATCH
  /wallets/admin/{user_id}/transfer-permission`, `wallet.manage`-gated).
  Deliberately per-wallet, not a role grant: opening it for "all promoters"
  would be wrong the first time only some of them should have it, which is
  exactly today's situation.

## Partner-invoice cashback

A second, entirely separate way wallet credit enters the system, alongside
the plain admin `ADMIN_CREDIT` top-up above -- see
`docs/cashback-partner-invoices-plan.md` for the full design rationale and
`database-model.md` for the schema. Summary:

- **What it is**: SOSNET brokers for external energy suppliers
  (`sn_merchants`, e.g. Eviso). A customer or promoter who already pays one of
  these directly can redeem part of that spend as internal wallet credit,
  by uploading proof of payment (`sn_receipt_claims`) and then paying Sosnet
  5% of the confirmed amount by bank transfer (or card -- see  below). Once that 5% is confirmed
  received, the wallet is credited 100% + a further 5% bonus.
- **Cardinal rule**: credit is minted **only** against a real, confirmed
  external payment (the 5%, bank transfer or card) -- never against spending existing credit.
  Paying a Sosnet product with wallet credit (once Phase 4/checkout exists)
  must never itself generate more credit, or the system would create value
  from nothing.
- **Lifecycle**: `SUBMITTED` (uploaded) → `PAYMENT_PENDING` (an admin
  confirmed the real amount and a payment reference code was generated) →
  `CREDITED` (the 5% payment arrived, confirmed by an admin or automatically by the Stripe webhook; two `sn_credit_ledger`
  rows are written -- `INVOICE_REDEMPTION_BASE` and `INVOICE_REDEMPTION_BONUS`,
  never one combined row, both carrying `reference_invoice_redemption_id`).
  `REJECTED` is reachable from `SUBMITTED` or `PAYMENT_PENDING`.
- **Percentage unified to 5%**: was 3% , changed
  to match `orders/service.py::ORDER_CASHBACK_PERCENTAGE` (the per-product
  "riscuoti subito cashback" figure, see below) at explicit user request --
  one consistent number wherever "cashback" appears in the product, not two
  different ones depending on which flow. Still two separate constants in
  two files (`invoice_redemptions/models.py::CASHBACK_PERCENTAGE` and
  `orders/service.py::ORDER_CASHBACK_PERCENTAGE`), just kept in sync by
  convention, not by sharing an import.
- **No OCR today**: the customer types the amount they read; an admin always
  verifies against the uploaded document before anything is unlocked. This
  is a deliberate simplification, not a stub -- the flow is fully functional
  without automated reading, just slower per-request for the admin.
- **Real partners configured**: the org previously had zero
  `Partner` rows -- the redemption dropdown was empty and the "Nuova
  richiesta" button correctly disabled itself (see the empty-state fix
  earlier in this same file's history). Three real partners were added via
  the existing `POST /partners` admin endpoint: **SOSNET** itself
  (deliberately included first -- lets a customer redeem cashback on their
  own SOSNET bill too, not only on an external supplier's), **Eviso**,
  and **Aenergy**. Logos: SOSNET's own (`sosnet.mamify.ai/img/logo.png`)
  and a verified real Eviso logo (hotlinked from `eviso.it`, visually
  confirmed before use) are set; Aenergy's `logo_url` was deliberately left
  `null` rather than guessing at an unverified company/logo for a
  real third-party trademark shown to customers -- set it via the admin
  Partner panel once the correct one is confirmed.
- **Where the document lives**: NOT the `sn_stored_files` table (that one's
  `contract_id` is NOT NULL by design, for contract KYC documents) --
  `sn_receipt_claims` carries its own `storage_key` in the same private
  bucket via `foundation/storage.py`.
- **Spending side (Phase 4, with self-checkout and card payments)**: `Product.category` (`INTERNAL`/`DROPSHIPPING`/
  `PARTNER`) and `ProductVersion.credit_discount_percentage` (0-100,
  enforced to 0 for `INTERNAL`) gate a new `sn_shop_orders` domain -- deliberately
  NOT `Contract` (`Contract.supply_point_id` is NOT NULL by design, every
  contract is an energy supply; an order for e.g. a partner t-shirt has no
  equivalent). Either an admin or the customer themselves (self-checkout)
  picks a DROPSHIPPING/PARTNER product version and how much wallet credit
  to apply (capped by both the product's percentage and the customer's
  balance, previewed via `GET /orders/quote` or `/orders/quote/mine` first);
  that amount is debited immediately via a `PURCHASE_DEBIT` wallet-transaction
  type (the mirror of `ADMIN_CREDIT`: `to_wallet_id` NULL instead of
  `from_wallet_id` NULL). The residual is paid one of two ways: **bank
  transfer**, confirmed by an admin exactly like a contract's `PAID`
  transition, or **card via Stripe** (`app/modules/payments/`), confirmed
  automatically by a webhook once `checkout.session.completed` fires -- the
  only case in this domain where `PAID` is reached with no human actor. If
  credit alone covers 100%, the order skips straight to `PAID` regardless of
  payment method. Cancelling an `AWAITING_PAYMENT` order reverses the exact
  `PURCHASE_DEBIT` row via `reverse_transaction` (extended to handle a
  debit with no recipient wallet), refunding the customer precisely.
- **Payment method availability is gated, not just visually disabled**:
  bank transfer requires an IBAN set in `Organization.settings`
  (`bank_iban`, admin-editable, `organization.manage` permission); card
  requires BOTH a Stripe secret key and publishable key set (a separate,
  stricter `organization.manage_payments` permission -- **SUPER_ADMIN
  only**, deliberately narrower than the bank IBAN's permission tier). A
  frontend must never render a payment-method button for an unconfigured
  method; `create_order` independently rejects the request server-side
  regardless (`PaymentMethodNotAvailableError`), so this is enforced even if
  the frontend were bypassed. Stripe secret/webhook keys are never returned
  in full by any endpoint, only "configured yes/no" plus the secret key's
  last 4 characters -- same principle as a password never round-tripped in
  plaintext.
- **Stripe webhook is per-organization and unauthenticated by design**:
  `POST /payments/stripe/webhook/{organization_id}` takes no auth
  dependency -- the Stripe signature, verified against THAT organization's
  own webhook secret, is the authentication. The organization id in the URL
  is what a SUPER_ADMIN pastes into their own Stripe Dashboard's webhook
  config, and is what keeps one endpoint correct for every tenant in
  principle, even though this deployment currently has one organization.
  **Needs a dedicated nginx location to actually be reachable (bug found and
  fixed )**: this route lives under `/api/`, which nginx normally
  routes entirely to the dashboard's BFF, not FastAPI -- see
  `infrastructure/nginx/nginx.conf`'s `location /api/payments/stripe/webhook/`
  and `server-migration-guide.md §8` bug #15. Without it every webhook
  delivery 404s and no card order/redemption is ever auto-confirmed.
- **Redemption fee now also payable by card, with a proof-upload option for
  bank transfer**: originally the redemption fee could only
  be paid by bank transfer with a reference code, manually reconciled by an
  admin with no self-service card option and no proof upload. It now works
  exactly like an order's residual: `sn_receipt_claims.payment_method`
  (default `BANK_TRANSFER` at `verify` time, switchable to `CARD` via
  `PATCH /invoice-redemptions/mine/{id}/payment-method` while still
  `PAYMENT_PENDING`), a Stripe Checkout Session for exactly
  `payment_due_cents` (`POST
  /invoice-redemptions/mine/{id}/checkout-session`), and an optional
  bank-transfer receipt upload (`POST
  /invoice-redemptions/mine/{id}/payment-proof`, purely advisory, same
  private-bucket pattern as an order's payment proof). `confirm_payment`
  (the manual admin action) refuses a `CARD`-method redemption
  server-side -- only the Stripe webhook may credit those, same anti-fraud
  rule as an order (see `security-model.md`).

## Product cashback -- "riscuoti subito cashback"

A third, separate way wallet credit enters the system (alongside the plain
admin top-up and the partner-invoice redemption above), this time earned
directly from a Shop purchase rather than an external bill:

- **Per-product toggle**: an admin can enable `cashback_enabled` on any
  DROPSHIPPING/PARTNER product version (never on an INTERNAL SOSNET
  product -- same forced-off invariant, same single enforcement point
  pattern, as `credit_discount_percentage`).
- **At checkout**: if the product allows it, the customer sees a
  "riscuoti subito cashback" option. Opting in adds a flat
  `ORDER_CASHBACK_PERCENTAGE` (5%) surcharge on top of whatever is actually
  still owed in new money (`amount_cents - credit_applied_cents` -- i.e.
  AFTER any wallet-credit discount is already applied, never before it).
  Cashback can only be requested when that residual is greater than zero --
  a 100%-credit-covered order has nothing left to earn cashback on.
- **Payout**: once the order reaches `PAID` -- an admin confirming a bank
  transfer, or the Stripe webhook for a card charge -- the whole extra
  payment (the residual actually paid + the 5% surcharge) is credited back
  to the customer's wallet as SosnetCash, as two separate transaction rows
  (`ORDER_CASHBACK_BASE`/`ORDER_CASHBACK_BONUS`), exactly mirroring the
  partner-invoice redemption's base+bonus split above.
- **Anti-fraud, by explicit request**: the credited amount is always
  computed from the real new money paid in *that* order, never a
  pre-discount or otherwise inflated base -- so a customer can never use
  wallet credit to pay, then have cashback computed as if they'd paid more,
  manufacturing credit from credit. Crediting is idempotent
  (`sn_shop_orders.cashback_credited_at` guard + deterministic idempotency keys).
- **Spending existing credit now needs an OTP**: see the OTP bullet under
  "Internal wallet" above / `security-model.md` -- any self-checkout order
  that applies `credit_applied_cents > 0` requires a fresh emailed OTP,
  regardless of whether cashback was also requested on the same order.

## "SosnetCash" -- wallet balance/transaction labeling

Purely a dashboard label, not a new concept: every wallet balance and
transaction amount (top-ups, redemption/cashback credits, peer transfers,
purchase debits) is displayed with a "SosnetCash" suffix instead of a euro
sign, to keep it visually unmistakable from *real* money. Real-money
amounts -- what a customer actually paid via Stripe or bank transfer on an
order or a redemption fee -- are always shown in genuine EUR, labeled with
the payment method. No schema or currency-field change; `sn_credit_accounts.currency`
is still `"EUR"` in the database, this is presentation-only.

## Accounting / "Contabilità"

A new customer-facing dashboard section (`GET /accounting/mine`, no
permission beyond authentication -- same pattern as `GET /wallets/me`)
merges a user's own `sn_credit_ledger` (SosnetCash movements) and their
own paid orders' real-money payments (EUR, tagged Bonifico/Carta) into one
chronological, filterable feed with running totals per category and a CSV
export. Computed on the fly from the two existing tables (see
`database-model.md` §14) -- deliberately not a new persisted table, so
there is nothing here that can drift from the wallet ledger or the orders
table, which remain the actual source of truth for their own domains.

### : totali, pagamenti dei contratti, dettaglio collegato {#accounting-detail}

- **I pagamenti dei contratti ci sono.** Ogni rata pagata
  (`contract_instalments.status = PAID`) è un movimento `CONTRACT_PAYMENT`
  in euro: carta se incassata da Stripe (`STRIPE_CHECKOUT`/`STRIPE_INVOICE`),
  bonifico se confermata a mano dall'amministrazione (`ADMIN`). Una rata = una
  riga, alla data in cui è stata incassata. Anche il cashback SosnetCash di un
  contratto porta ora il suo `contract_id`.
- **I totali li calcola il server** (`GET /accounting/mine/summary`,
  `accounting/service.py::my_summary`) dagli stessi movimenti dell'elenco, così
  le card e la lista non possono dire cose diverse: totale speso (carta +
  bonifico) e ripartizione, speso nel mese corrente, per ordini / riscatti /
  contratti, saldo SosnetCash (dal wallet), SosnetCash ricevuti e spesi, cashback
  ricevuto (fonti `*_CASHBACK_*` e `CONTRACT_CASHBACK`), contratti attivi,
  rate pagate e **prossima rata** (somma delle rate previste nello stesso
  giorno, contratti con addebiti non interrotti). **Provvigioni** solo se
  l'account è anche un promoter: totale maturato, da incassare (`ACCRUED`/
  `PAYABLE`/`SCHEDULED`), pagate; `REVERSED`/`CANCELLED` escluse.
- **Dettaglio** (`GET /accounting/mine/detail?ref=…`, e
  `/accounting/admin/detail` per lo staff con `wallet.manage`;
  `accounting/details.py`): `wallet:<id>`, `order:<id>` (ordine normale o
  "Acquisti SOSNET"), `redemption:<id>`, `contract:<id>`. Stessa forma per
  tutti: dati, **cronologia con data e ora al secondo e chi ha agito**
  (creazione, ricevuta del bonifico caricata, pagamento confermato "Stripe
  (automatico)" o dall'amministratore, cashback accreditato, annullamento,
  approvazione, ogni rata incassata, prossima rata), le rate di un contratto,
  e i riferimenti collegati. Lato cliente tutto è limitato alle proprie cose:
  ciò che non è suo risulta "non trovato", mai "vietato".
- **Tutto collegato**: ogni riga apre il suo dettaglio; il chip "Ordine /
  Riscatto / Contratto #…" apre quella cosa, che elenca tutti i movimenti che
  ha prodotto (pagamento in euro, SosnetCash usati, cashback), ognuno apribile a
  sua volta.

## Account gates

Three independent, self-service gates block dashboard use until satisfied,
each with its own acceptance state persisted on `sn_accounts`/`sn_promoter_profiles` and
visible to admins (Anagrafiche Clienti/Promoter, small badges next to each
account). None of these are enforced client-side only -- every corresponding
backend action independently requires the same state.

- **Privacy consent**: `sn_accounts.privacy_accepted_at`, set once at
  self-registration (`RegisterRequest.accept_privacy`, a required checkbox --
  the request is rejected server-side if unticked). NULL for every account
  that predates this field (admin-created accounts, or older self-registered ones) -- there is no retroactive consent to backfill, so it
  simply stays NULL for those.
- **Email verification** (new registrations only): `sn_accounts.email_verified_at`
  (a column that already existed, previously unused). Registration sends a
  branded confirmation email (`foundation/email_templates.py`) with a link to
  `/verify-email?token=...`, backed by `sn_email_confirmations` (opaque
  token, hashed at rest, 24h expiry, single-use -- same pattern as
  password-reset tokens). **Explicit product decision**: every account that
  existed before this feature shipped is grandfathered as already-verified
  (the 0026 migration backfills `email_verified_at = COALESCE(email_verified_at,
  created_at)` for every NULL row) -- nobody who was already using the
  product gets a surprise "confirm your email" wall. The rule applies only
  going forward, to accounts created .
- **Profile completion** (fiscal code + residence address): `sn_accounts.fiscal_code`
  + `residence_street/city/province/postal_code/country`. Unlike email
  verification, this one is deliberately retroactive -- **every** account,
  existing or new, sees the blocking popup at next login until filled in
  (`PATCH /auth/me/profile`, `users/service.py::is_profile_complete`).
  Demo/seed accounts are pre-filled so they're never blocked.
- **Promoter collaboration agreement + OTP** ("lavora con noi"):
  `sn_promoter_profiles.collaboration_accepted_at` /
  `collaboration_contract_version` / `collaboration_otp_verified_at`.
  Becoming a promoter now requires ticking a collaboration-agreement
  checkbox (`accept_contract`) AND typing back a 6-digit code emailed via
  `POST /network/agents/apply/request-otp` (`sn_one_time_codes` table, purpose
  `PROMOTER_APPLICATION_OTP_PURPOSE`, 10-minute expiry, single-use, verified
  server-side in `apply_as_promoter` before any of the existing
  auto-activation/reapplication branching runs) -- proof the account holder,
  not just whoever is logged in, actually agreed.
- All four gates apply only to CUSTOMER/PROMOTER accounts, not admin-tier
  roles (`account-gate.tsx` checks live roles from `GET /auth/me` before
  rendering the blocking modal) -- there is no scenario where blocking a
  SUPER_ADMIN's own dashboard behind a fiscal-code popup makes sense.

**Notification emails** (also , same branded-HTML-shell mechanism):
cashback credited (`invoice_redemptions/service.py::confirm_payment`, fires
after the wallet credit) and a new support ticket opened
(`support/service.py::create_ticket`, sent to
`Organization.settings.admin_notification_email`, defaulting to
`info@sosnet.mamify.ai` -- `organizations/service.py::DEFAULT_ADMIN_NOTIFICATION_EMAIL`,
admin-editable via the existing company-settings PATCH). All best-effort:
an SMTP hiccup is logged, never blocks the underlying action (ticket
creation, cashback crediting, registration all already committed by the
time the email send is attempted).

## Store orders vs. SOSNET contracts -- and the  e-commerce pass

Two structurally different things both live under "products", and this
distinction is load-bearing, not cosmetic:

- **SOSNET (`category=INTERNAL`) products** are the matrix a real
  energy-supply **Contract** is created from (`POST /contracts`) -- these
  are what a promoter earns commissions on, and what shows up in the
  network/commission engine. They never go through the `sn_shop_orders` domain at
  all (`orders/service.py::_get_sellable_product_version` explicitly
  rejects INTERNAL products with a "si acquistano come contratto" error).
- **DROPSHIPPING/PARTNER products** are a separate, purely additional perk:
  a customer's cashback wallet balance can be spent on them via the `sn_shop_orders`
  domain (self-checkout, `POST /orders/mine`) -- no commission, no network
  effect, just an e-commerce-style purchase paid partly in wallet credit and
  partly by bank transfer or card.

**** brought the store/order side of this up to a real e-commerce
standard, per explicit request ("rendilo un ecommerce professionale"):

- **Product photo everywhere a product/order shows one**: `ProductVersion.
  image_url` (already existed, admin-uploadable since an earlier session)
  now also flows through to `OrderRead.product_image_url`
  (`orders/service.py::to_read_dict` joins it in) -- the same photo appears
  as a thumbnail on every order row, admin or customer side, not just the
  shop grid. A shared `product-thumbnail.tsx` component renders it (or a
  neutral package-icon placeholder when there is none) everywhere, so the
  "no photo yet" look is consistent instead of each screen inventing its
  own fallback.
- **Product detail page before checkout**: clicking a purchasable
  (DROPSHIPPING/PARTNER) product card opens `product-detail-modal.tsx`
  first -- full description, price breakdown, photo -- rather than jumping
  straight from the grid card into the checkout flow, matching how a real
  storefront works. INTERNAL (SOSNET) products never get this
  treatment; those stay contract-only.
- **"I miei Ordini"** (`customer-orders-panel.tsx`, new customer-dashboard
  tab): every order the customer has placed, with its status (in attesa di
  pagamento / pagato / annullato) and a "Paga ora" action on an unpaid one
  -- exactly the "reservation list" the request asked for, so a customer
  never has to remember what they bought or track down how to finish
  paying for it. The existing `admin-orders-panel.tsx` (already a full
  gestionale -- create, confirm bank transfer, cancel, filter by status)
  gained the same photo thumbnails for consistency.
- **Order-confirmation email** (`orders/service.py::_send_order_confirmation_email`,
  fires at the end of `create_order`, after the order is already
  committed): summarizes what was bought and explains exactly how to pay --
  the IBAN + causale for a bank-transfer residual, or a real, freshly-minted
  Stripe payment link for a card residual, or a simple "no payment needed"
  confirmation when credit covered everything. Best-effort like every other
  email in this project: both `EmailNotConfiguredError` (SMTP off) and any
  `stripe.error.StripeError` (bad/revoked key, Stripe outage) are caught so
  a payment-provider hiccup can never take an already-created order down
  with it -- the customer can still get a fresh Stripe link later from "I
  miei Ordini".
- **Stripe checkout opens in a new tab, never a full-page redirect**
  (`window.open(checkout_url, "_blank", "noopener,noreferrer")` in both
  `product-checkout-modal.tsx` and `customer-orders-panel.tsx`) -- per
  explicit request: if Stripe fails or the customer changes their mind
  mid-payment, the dashboard tab they were already on is never lost.
- **Dashboard header images**: the Wikimedia-hotlinked `SectionBanner`
  images (dim/dark, and "commissions"/"wallets" sharing one photo) were
  replaced with brighter, distinct, locally-bundled photos per section
  (`apps/dashboard/public/images/header-*.jpg`) -- same "bundle it locally,
  don't hotlink" convention `documentation-header.jpg` already established.

###  follow-up: verified, then polished further

The user asked to re-verify two things before continuing -- both checked
against the live database, not just the code:

- **Per-product credit-discount percentage**: confirmed correct end-to-end,
  no bug found. `ProductVersion.credit_discount_percentage` is clamped to 0
  for `INTERNAL` products and 0-100 for DROPSHIPPING/PARTNER
  (`catalog/service.py::_clamp_credit_discount`); `orders/service.py::
  get_quote`/`max_creditable_cents` read that product's own value, never
  a global constant. Live-verified: a 69,00€ PARTNER product with a
  30%-in-credits version correctly quoted `max_creditable_cents: 2070`
  (exactly 30% of 6900) via `GET /orders/quote/mine`.
- **Contract flow authority**: see "Who can move a contract through this
  pipeline" above -- confirmed staff-only, not a customer self-service
  flow; documented since the user asked to double check their own mental
  model of it.

Then, cosmetic/UX polish on top of the already-correct backend:

- **Product showcase redesign** (`customer-products-panel.tsx`): bigger,
  bolder price and "crediti usabili" (computed from that product's own
  price × discount %, shown in euro, not just a percentage badge) side by
  side at the bottom of each card; a discount ribbon and category chip
  overlaid on the photo; hover zoom on the image, card lift + glow, and a
  staggered fade-in on the grid; the whole photo stays clickable through to
  `product-detail-modal.tsx`, which got the same bigger price/credits
  treatment plus a full-width gradient "Acquista ora" button.
- **Energy header photo swapped again**: from a ground-level solar-panel
  row to a bright aerial shot of a full solar farm (blue sky, vivid green)
  -- more strikingly "energia" and more luminous than the previous pick,
  per explicit feedback that the header art should lean into energy/light
  themes and brightness specifically.
- **Cashback-redemption camera capture upgraded to a real live viewfinder**
  (`camera-capture-modal.tsx`, `getUserMedia` + a `<video>` preview +
  canvas-frame capture) -- the previous "Scatta foto" button
  used a plain `<input capture="environment">`, which only opens a camera
  on some mobile browsers and does nothing at all on desktop (no webcam
  access). The new modal opens an actual live camera preview everywhere a
  camera exists, with a clear error+fallback state (close and use "Carica
  file") when it can't get camera access at all.
- **Desktop top nav bar added** alongside the existing sidebar
  (`app-shell.tsx`) -- big pill buttons for every nav item, pinned under
  the header on every page, mirroring the mobile bottom bar's "always one
  tap away" idea; the mobile bottom bar's own touch targets were also
  enlarged. This closes the gap left  only shipped the
  mobile half of "primary tools as big buttons, bottom on mobile / top on
  desktop."

## Chi può aprire una pratica di attivazione {#pratica-authors}

Una pratica è sempre la stessa cosa — intestatario, N POD, un'offerta per POD,
documenti — e cambia solo chi la compila:

- **il cliente**, per sé (`created_by_role="CUSTOMER"`): guadagna il promoter
  che lo ha portato (o il primo sponsor attivo sopra di lui);
- **il promoter**, per un cliente suo (`PROMOTER`): guadagna lui, e il cliente
  riceve notifica ed email per pagare dalla propria area;
- **l'amministrazione** (`ADMIN`): può indicare a quale promoter
  attribuirla (validato ACTIVE); senza indicazione vale la regola del
  self-service. Il cliente riceve lo stesso avviso.

**Il pagamento è sempre del cliente**: promoter e staff non possono aprire il
checkout né pagarlo (la pratica accetta il pagamento solo dall'intestatario);
lo staff può però confermare un bonifico ricevuto. Chi ha compilato la pratica
resta scritto sulla pratica e su ogni contratto.

## Marketplace: i tre shop di prodotti importati {#marketplace}

Tre fonti, tre tabelle separate, una sola promessa al cliente:

| Nello Shop del cliente | Fonte | Dominio / tabelle | Admin |
|---|---|---|---|
| **Marketplace 1** | CJ Dropshipping (API) | `cj_dropshipping` | Shop CJ |
| **Marketplace 2** | Shopify (Admin API) | `shopify_dropshipping` | Shop Shopify |
| **Marketplace 3** | AliExpress (Dropshipping API) | `aliexpress_dropshipping` | Shop AliExpress |

(Numerazione e nomi del menu decisi dall'utente .)

Il vecchio plugin "a mano" (`sn_supplier_items`) resta in piedi
sotto lo stesso Marketplace 3, come scheda secondaria "Prodotti inseriti a
mano": serviva quando AliExpress non aveva API e continua a funzionare per
qualunque prodotto si voglia vendere senza fornitore collegato. I suoi 5
prodotti di prova sono stati cancellati  (nessun ordine li
aveva mai usati).

I tre shop sono **domini isolati**: tabelle proprie, client proprio, ordini
propri. Quello che NON è isolato, per scelta esplicita dell'utente (Session
34), è la gestione: "I miei Ordini" del cliente, "Ordini" dell'admin e la
Contabilità mostrano un elenco unico, con un tag interno `source` che il
cliente non vede mai.

### La spedizione AliExpress: costo reale, con un minimo {#marketplace-shipping}

Ora la spedizione dei prodotti AliExpress **non è un forfait**.
Si chiede ad AliExpress quanto costa davvero
(`aliexpress.ds.freight.query`, per prodotto / SKU / quantità /
destinazione) e si addebita:

    spedizione addebitata = max(costo reale AliExpress, minimo configurato)

Il minimo è il campo delle impostazioni che prima era il forfait
(`shipping_minimum_cents`): cambiarlo dall'admin cambia il checkout subito,
senza toccare codice. **A zero il minimo non esiste** e si paga esattamente
il costo reale — è la configurazione scelta dall'utente il 21/09/2026, dopo
aver visto che il catalogo va da 1,99 a 44,16 EUR di spedizione vera. Il
meccanismo resta nel codice e si riattiva rimettendo un importo.

**Il minimo vale una volta per ordine, mai per articolo.** Tre prodotti con
1,20 di spedizione ciascuno fanno 3,60 di costo reale e 5,90 addebitati,
non 17,70. Il costo reale di un ordine è la **somma delle righe**: la DS API
di AliExpress quota il freight per prodotto e non espone una quotazione di
carrello, quindi sommare è un'operazione nostra, non sua.

**Se non si riesce a sapere quanto costa spedire, non si vende.** È l'unico
errore del dominio senza ripiego (`AliexpressShippingUnavailableError`):
addebitare il minimo vorrebbe dire decidere che AliExpress spedisce a meno
di 5,90 senza averglielo chiesto, e incassare 5,90 su una spedizione da 20
euro; addebitare zero è peggio. Un'opzione senza prezzo non è una
spedizione gratis: è un'opzione di cui AliExpress non ha detto il costo. Nel
carrello questo si vede come sezione non acquistabile con la ragione
scritta, non come errore.

**Tre numeri congelati sull'ordine**, non uno: quanto è costata
(`supplier_shipping_cents`, e per riga sugli item), il minimo in vigore quel
giorno (`minimum_shipping_cents`) e quanto ha pagato il cliente
(`shipping_cents`). Il margine di spedizione è la differenza fra l'ultimo e
il primo, e senza tutti e tre non sarebbe ricostruibile. Sugli ordini
precedenti i primi due sono NULL — "non rilevato", che è la verità: uno zero
direbbe che spedire non costava niente e gonfierebbe ogni margine passato.

**Ad AliExpress non si manda mai il nostro numero.** Il minimo riguarda solo
ciò che addebitiamo al cliente; l'ordine verso il fornitore porta i suoi
dati logistici reali.

Il freight si tiene in cache mezz'ora per (organizzazione, prodotto, SKU,
quantità, destinazione): un cliente che alza e abbassa la quantità non deve
costare una chiamata ogni volta, e la chiave contiene tutto ciò che può
cambiare il prezzo, quindi cambiare variante o quantità produce una chiave
nuova senza che nessuno debba invalidare niente.

**Attenzione al nome di un campo**: nella risposta di `ds.freight.query`
`shipping_fee_cent` **non porta centesimi**, porta un importo ("1.99" =
1,99 EUR). Verificato sul gateway vero , dopo che la
 lo aveva lasciato segnato come da verificare. Leggerlo come
centesimi divideva ogni spedizione per cento, ed è il tipo di errore che
non si vede finché il numero non tocca il prezzo.

Con `shipping_mode = INCLUDED` non cambia nulla rispetto a prima: il minimo
entra nel prezzo di listino e al checkout non si addebita spedizione.

### Marketplace 4: «Fai la Spesa con Sosnet» {#sosnet-market}

Il quarto negozio segue tutte le regole di questa sezione --
SosnetCash solo da spendere e mai per intero, niente cashback, bonifico
scontato, IVA aggiunta al prezzo, carrello con una spedizione sola -- e ne
ha una sua: **il catalogo lo scrive l'amministratore**, non un fornitore.

Ne discende il resto. Non ci sono prezzi ricalcolati a ogni sync, né cambio
valuta, né ricarico su un costo: il prezzo è quello di vendita. La
spedizione è un importo fisso e non un minimo, perché senza fornitore non
esiste un costo reale da confrontare. E non c'è un ordine da inoltrare: un
ordine pagato aspetta che l'amministratore lo spedisca e ne segni il
tracking, che è anche il momento in cui il cliente riceve l'email.

**L'ordine pagato va all'azienda**, a mano con un pulsante o da solo se
`auto_forward` è acceso (nasce spento: mandare una email a un'azienda vera
è un'azione verso l'esterno). Parte **una email per azienda**, con solo le
sue righe, l'indirizzo di consegna e le note del cliente — mai i prezzi che
il cliente ha pagato, che mostrerebbero il ricarico. Solo un ordine già
pagato si inoltra. Un'azienda senza email o una riga senza azienda vengono
segnalate allo staff e scritte in `forward_error`, mai saltate in silenzio.
Il reinvio è ammesso: qui non si crea niente dall'altra parte, a differenza
di AliExpress dove un secondo invio sarebbe un secondo acquisto.

**L'azienda produttrice ha una scheda sua** e il suo nome si congela sulla
riga d'ordine: è il motivo per cui questo negozio esiste — qui si sa chi fa
la merce — e rinominarla non deve cambiare cosa dice un ordine di sei mesi
fa. Al cliente si mostrano nome, descrizione e sito; partita IVA, email,
telefono e sede restano all'amministrazione.

### Il carrello {#marketplace-cart}

Un carrello per **(cliente, negozio)**, non uno solo per tutto. Al cliente
se ne mostra uno, diviso in sezioni: il totale in cima è la somma, il
pulsante di pagamento è per sezione. Il motivo non è tecnico ma di regole:

- i Marketplace hanno indirizzo di consegna, spedizione, IVA congelata e
  sconto bonifico; il catalogo interno non ha niente di tutto questo e ha
  invece il «riscuoti subito cashback», che nei Marketplace **è vietato**;
- righe con regole che si escludono a vicenda non possono finire nello
  stesso ordine, quindi non stanno nello stesso carrello.

Conseguenze da conoscere, tutte già implementate:

- **Nel carrello non ci sono prezzi.** Ogni lettura li ricalcola dal
  listino di quel momento; il prezzo si congela solo sull'ordine. Un
  articolo messo nel carrello a gennaio si paga al prezzo di quando lo si
  compra, che è anche l'unico che il cliente vede prima di confermare.
- **La spedizione si conta una volta per ordine**, non per riga.
- **Il tetto SosnetCash si calcola riga per riga**: la percentuale di ogni
  prodotto sul valore di quel prodotto, quantità compresa. Il tetto
  dell'ordine è la loro somma, mai oltre l'intero ordine meno un centesimo.
  **La spedizione non conta**: i SosnetCash scontano la merce, non il
  corriere. Così il tetto è esattamente quello che il cliente ottiene
  sommando a mano le percentuali dei prodotti che ha nel carrello, e un
  numero che si può rifare a mano è un numero di cui ci si fida.

  Quello che la finestra mostra è `min(tetto, saldo del wallet)`: se il
  saldo è più basso, è lui il limite, e va detto — altrimenti il cliente
  crede che il tetto sia sbagliato.

  Nella  era una media pesata sull'ordine, e **era sbagliata**:
  la media va arrotondata a percentuale intera, e l'arrotondamento non
  rispetta i singoli prodotti. Un articolo da 5 EUR al 99% accanto a uno da
  500 EUR allo 0% dava una media dell'1%, cioè 5,05 EUR spendibili — più di
  quanto il primo concedesse, presi da un prodotto che di SosnetCash non ne
  accetta affatto; in altre combinazioni toglieva mezzo euro a chi ne aveva
  diritto. **Un prodotto non presta mai il suo diritto a un altro.**

  Con una riga sola il calcolo torna identico a un acquisto singolo (la
  quota di spedizione è tutta sua), quindi comprare un articolo dal
  carrello o dalla sua scheda dà lo stesso tetto.
- **Un OTP solo** per checkout, non uno per riga.
- **Una riga invendibile non blocca il carrello**: si apre lo stesso, la
  riga è segnata con il motivo e il pagamento è sospeso finché non la si
  toglie. Pagare il resto in silenzio consegnerebbe un ordine diverso da
  quello composto dal cliente.
- **L'ordine si crea prima, il carrello si svuota dopo.** Se la creazione
  fallisce il cliente ritrova il carrello intatto.

Un ordine porta N righe (`<shop>_order_items`); **il denaro resta sulla
testata** — importo, spedizione, IVA, sconto bonifico, SosnetCash, sessione
Stripe. È la ragione per cui pagamenti, webhook, Contabilità ed email non
sono cambiati quando il carrello è arrivato.

**Ogni ordine ha un numero progressivo** (`sn_order_number_seq`,
`marketplaces/models.py`), assegnato dal database e condiviso da tutti i
negozi: in "I miei Ordini" i tre Marketplace stanno insieme, e tre "ordine
1042" diversi non si potrebbero distinguere. Si parte da 1000. È il numero
che finisce nelle email e che il cliente detta al telefono; gli ordini
creati prima della sequenza continuano a chiamarsi con le prime cifre del
loro UUID, perché rinominarli li renderebbe irrintracciabili.

**L'ordine vero al fornitore parte solo a pagamento avvenuto**, e solo se
l'amministratore ha acceso l'invio automatico. Con `auto_forward` spento
— com'è dal 21/09/2026 — un ordine pagato aspetta in "Marketplace
AliExpress → Ordini" che qualcuno prema "Crea su AliExpress": una verifica
umana prima di spendere davvero.

**Le email di un ordine sono tre, non una.** Conferma d'ordine alla
creazione (cosa hai ordinato, come pagarlo), **ricevuta al pagamento
confermato** (cosa hai pagato: articoli, spedizione, SosnetCash, sconto
bonifico, totale, metodo, IVA contenuta), spedito/consegnato con il
tracking. La ricevuta ripete l'elenco invece di rimandare alla prima
email: una ricevuta che non si basta da sola non è una ricevuta. Parte da
`_mark_paid` e da nessun altro punto, ed è protetta dal doppio invio
dalle guardie `AWAITING_PAYMENT` dei due chiamanti — un webhook Stripe
ripetuto non manda una seconda ricevuta.

**Il cliente non sa mai da quale fornitore arriva la merce.** Nessuna
stringa rivolta al cliente nomina AliExpress, CJ o Shopify: le schede si
chiamano «Marketplace 1/2/3» (rinominabili dall'amministratore), le email
sono firmate SOSNET, `tracking_company` è salvato ma non mostrato, e
i nomi dei fornitori compaiono solo nelle notifiche allo staff. L'unico
residuo è il link di tracciamento, che punta al sito del corriere quando il
fornitore lo restituisce, altrimenti a 17track.

**Il margine si misura su tutte le righe.** Il costo fornitore di un ordine
è la somma delle righe: contare solo la testata dichiarerebbe i ricavi di
tutte e i costi di una.

**CJ quota il carrello intero in una chiamata**, perché `sn_offers` nella
sua API di freight è una lista: il prezzo che torna è quello della
spedizione unica. Sommare quotazioni separate farebbe pagare al cliente più
spedizioni di quante ne partono. Per lo stesso motivo un ordine CJ non può
mettere insieme righe da **magazzini diversi**: `startCountryCode` è uno
solo, e magazzino e corriere stanno sulla testata dell'ordine fornitore.
Chi ci prova legge il perché invece di vedersi creare un ordine che CJ
rifiuta.

**Lo split del fornitore.** Le API accettano già più righe (AliExpress
`product_items`, CJ `sn_offers`, Shopify `line_items`), ma un ordine Sosnet
può diventare più ordini fornitore: AliExpress li spezza per venditore e
risponde con una lista di numeri, CJ tiene magazzino e corriere sulla
testata. Per questo il numero d'ordine del fornitore e il tracking stanno
**sulla riga**, non solo sulla testata. Quando i numeri non si possono
abbinare con certezza alle righe, lo staff riceve un avviso invece di
vedersi attribuire un tracking a caso.

### Come si collega ciascuno {#marketplace-credentials}

| Shop | Credenziali | Dove si mettono |
|---|---|---|
| CJ | API key (cjdropshipping.com → My CJ → Authorization → API) | Shop CJ → Impostazioni |
| Shopify | App del **Dev Dashboard**: Client ID + Client secret, oppure un vecchio token `shpat_` | Shop Shopify → Impostazioni |
| AliExpress | App **Drop Shipping** di openservice.aliexpress.com: App Key + App Secret | Shop AliExpress → Impostazioni |

Shopify e AliExpress richiedono, dopo le credenziali, **l'installazione/
autorizzazione sul negozio o sull'account**, che è un giro OAuth: l'admin
preme "Collega", approva sul portale del fornitore e torna su una pagina di
esito (`/admin/shopify-connected`, `/admin/aliexpress-connected`). Gli
indirizzi da registrare nei due portali:

- Shopify — URL dell'app `https://sosnet.mamify.ai`, URL di
  reindirizzamento `https://sosnet.mamify.ai/api/shopify/oauth/callback`;
- AliExpress — Callback URL
  `https://sosnet.mamify.ai/api/aliexpress/oauth/callback`.

I token non si scrivono mai a mano: Shopify con l'app del Dev Dashboard usa
il *client credentials grant* (token di 24 ore, rinnovato 5 minuti prima
della scadenza e dopo un 401) o il token offline dell'installazione;
AliExpress rilascia un token a scadenza con il suo `refresh_token`, rinnovato
allo stesso modo. Nessun secret viene mai restituito da un endpoint: solo
"configurato" e le ultime 4 cifre.

I nomi "Marketplace 1/2/3" sono impostazioni (`organizations.settings.marketplace_labels`,
card "Regole dei Marketplace" in cima a ciascuna delle tre pagine admin). Il
cliente non vede mai la fonte.

**Ogni sezione dello Shop si accende, si spegne e si rinomina**.
Le tre schede che vengono dal catalogo nostro — "SOSNET" (INTERNAL),
"Prodotti Partner" (PARTNER), "Offerte Sosnet" (DROPSHIPPING) — hanno nome e
interruttore in `organizations.settings.shop_sections`
(`{internal|partner|dropshipping: {label, enabled}}`, tutto acceso finché un
amministratore non dice il contrario), card **"Sezioni dello Shop del
cliente"** nella pagina Prodotti. Le tre schede dei Marketplace hanno il
proprio interruttore ("Shop visibile ai clienti") nelle impostazioni del
rispettivo shop e il nome nella card Regole dei Marketplace. Due regole che
si sommano: **una scheda Marketplace compare solo se è accesa E ha almeno un
prodotto in vendita** — accesa con catalogo vuoto, il cliente non vede
niente. L'interruttore di visibilità dei tre shop **si salva da solo** al
clic: prima cambiava solo il modulo e chi non premeva "Salva" credeva di
aver acceso lo shop mentre i clienti continuavano a non vederlo. Il titolo dello Shop del cliente è **"Fai la
spesa con SOSNET"**; la vecchia scheda di catalogo DROPSHIPPING, che
aveva quel nome, ora si chiama "Offerte Sosnet".

Regole comuni (`apps/api/app/modules/marketplaces/rules.py`, l'unico posto dove vivono):

- **Il bonifico costa di meno (mai un aumento sulla carta).** Il prezzo
  mostrato è quello pieno, uguale con carta; pagando con bonifico istantaneo
  la parte in euro (dopo il SosnetCash) scende di
  `marketplace_bank_transfer_discount_percentage` (default **5%**, 0 =
  spento), arrotondato al centesimo per eccesso da ,5. Lo calcola sempre il
  server e lo congela sull'ordine (`bank_transfer_discount_cents`) quando il
  metodo viene scelto, cambiato, e subito prima di ogni Checkout Stripe (che
  lo azzera: con carta si paga il prezzo pieno); un ordine pagato non cambia
  più. Vale solo per i Marketplace: contratti, catalogo Sosnet e partner no. Lo
  sconto riduce il margine: il ricarico di CJ/Shopify è calcolato sul prezzo
  pieno.
- **IVA inclusa nel prezzo**. Il prezzo mostrato è quello
  finale, come impone il Codice del Consumo (artt. 14-15) verso i
  consumatori: nessun "+IVA" da aggiungere al totale. L'IVA **contenuta**
  nel prezzo si legge nel checkout, nell'email di conferma e nel dettaglio
  dell'ordine ("IVA inclusa nel prezzo (22%)"), e viene congelata
  sull'ordine (`vat_percentage`, `vat_amount_cents`). Aliquota:
  `marketplace_vat_percentage`, default **22**, massimo 30, modificabile
  nella card Regole dei Marketplace; un cambio non tocca gli ordini già
  fatti. Base imponibile = importo − sconto bonifico: lo sconto abbassa il
  prezzo, quindi abbassa l'IVA, mentre **il SosnetCash non la riduce** perché
  è un mezzo di pagamento, non uno sconto (conseguenza visibile: con molto
  SosnetCash l'IVA contenuta può superare l'importo ancora da pagare). Il
  margine mostrato all'amministratore è al netto di IVA e sconto: l'IVA non
  è un nostro ricavo.
- **Niente cashback, SosnetCash solo in parte.** I prodotti dei Marketplace non
  generano cashback: servono a spendere il SosnetCash, mai per il 100% del
  prezzo. Un prodotto nuovo entra al **30%**; l'amministratore può alzarlo
  fino al **99%** (vincolo anche nel database). Con SosnetCash serve l'OTP.
- **Perché uno sconto e non un aumento**: in Italia la maggiorazione sui
  pagamenti con carta dei consumatori è vietata (PSD2 art. 62(4), D.Lgs.
  11/2010 art. 3 c. 4, Codice del Consumo art. 62); uno sconto per chi paga
  con un altro metodo è ammesso. Le  avevano un +5% sulla carta,
  mai andato in produzione: sostituito prima del deploy.

## Shop Sosnet Partner: CJ Dropshipping {#partner-shop}

Un secondo negozio "importato", accanto ad "Acquisti SOSNET", collegato
davvero all'API di CJ Dropshipping. Tabelle e gestione proprie
(`cj_dropshipping`), esperienza del cliente identica agli altri negozi.

**Per il cliente, uguale a tutto lo Shop.** I prodotti compaiono nella
categoria **"Marketplace 1"** dello Shop:
al cliente non si dice mai da dove arriva un prodotto (né CJ né "Partner" in
finestra prodotto, pagina Stripe, Contabilità). Checkout con SosnetCash (codice via email), bonifico o carta, ordine in "I miei
Ordini", movimenti in Contabilità. Questi prodotti **non generano cashback**:
servono a spendere SosnetCash, come gli Acquisti SOSNET. In più: variante,
quantità (1–10), indirizzo di consegna (precompilato dal profilo, telefono
obbligatorio per il corriere), stato della spedizione e tracking.

**Nessun importo arriva dal browser.** Prezzo della variante e spedizione si
ricalcolano sul server alla creazione dell'ordine; la spedizione è il
preventivo reale di CJ per quella variante, quantità e destinazione (l'opzione
più economica), con cache di 30 minuti. Conta `totalPostageFee`, ciò che CJ
addebita davvero (sdoganamento incluso), non il prezzo base `logisticPrice`. Il costo CJ di un ordine comprende anche l'IVA di importazione
IOSS (~22% del prodotto): stimata per i margini finché CJ non restituisce
l'importo reale.

**Prezzo di vendita.** `costo CJ (USD) × cambio × (1 + ricarico%) + ricarico
fisso`, poi arrotondato **sempre per eccesso** a ,90 / ,99 o al centesimo: un
arrotondamento non può mai abbassare il margine. Ricarico generale predefinito 100% (costo 10 → prezzo 20 prima di cambio e
arrotondamento). Ricarico per singolo prodotto
opzionale, già sceglibile nella finestra di importazione (se uguale al
generale non viene salvato e il prodotto segue le Impostazioni); prezzo fisso per variante opzionale (non segue più il costo).
Spedizione: la paga il cliente al costo reale (predefinito) oppure è inclusa
nel prezzo (stima della spedizione più economica sommata al prezzo, e al
checkout spedizione 0). Ogni cambio delle regole ricalcola subito tutti i
prezzi; il costo e il cambio usati restano congelati sull'ordine, così il
margine di un ordine passato non cambia.

**SosnetCash usabili.** Percentuale per prodotto (predefinita 100%, impostabile),
calcolata sul totale compresa la spedizione.

**Stati.** `status` è il pagamento del cliente (come ogni ordine);
`fulfillment_status` è il pacco: NOT_SENT → SENDING → SENT (su CJ, non pagato)
→ PROCESSING (pagato su CJ) → SHIPPED → DELIVERED, oppure ERROR (invio
rifiutato) / CJ_CANCELLED. Un ordine si invia a CJ **solo se pagato dal
cliente**. Si annulla (con restituzione dei SosnetCash) solo finché non è pagato.

**Pagamento a CJ senza saldo precaricato {#partner-shop-payment}.**
Tre fatti distinti per ogni ordine: pagamento del cliente (`status`), ordine su
CJ (`fulfillment_status`), pagamento a CJ (`cj_payment_status`). Flusso
ibrido, automatico di default:

1. Il cliente paga (bonifico confermato, Stripe, o tutto in SosnetCash).
2. L'ordine si crea su CJ **una sola volta** con `payType=1`: CJ lo conferma e
   restituisce la sua pagina di pagamento (`cjPayUrl`).
3. Si legge lo stato su CJ: se risulta già pagato (sandbox, oppure pagato a
   mano sulla pagina CJ) si registra e basta.
4. Altrimenti si legge il saldo CJ: se copre il costo reale dell'ordine si paga
   dal saldo; se no l'ordine resta **Pagamento CJ richiesto**. Non è un errore:
   nessun messaggio al cliente, una notifica allo staff ("CJ richiede $X; saldo
   $Y, mancano $Z").
5. Lo sblocchi pagando dalla pagina CJ dell'ordine ("Apri pagamento CJ") o
   ricaricando il saldo: il controllo ogni 10 minuti (o "Verifica pagamento
   CJ") vede il pagamento, oppure paga dal saldo appena basta, dal più vecchio,
   senza mai spendere due volte la stessa ricarica.

Il cliente vede **Ordine ricevuto** finché CJ non è pagato, poi **In
preparazione**, **Spedito** (con tracking solo quando esiste), **Consegnato**.
Mai ricariche automatiche. Riepilogo di cassa in admin: ordini da pagare a CJ,
totale necessario, saldo, differenza.

**Mai due ordini, mai due pagamenti.** Presa in carico con UPDATE
condizionale. Prima di creare si chiede a CJ il nostro numero `SOSNET-<id>`: si
crea solo se CJ risponde "order not found"; timeout o CJ occupato fermano e si
riprova dopo. Prima di pagare si rilegge lo stato su CJ.

**Errori.** Classificati: temporanei e di accesso si riprovano da soli (attesa
crescente, massimo 6 tentativi); dati rifiutati e casi non riconosciuti
chiedono un controllo dello staff (notifica); saldo insufficiente è uno stato,
non un errore.

**Invio a CJ.** A mano ("Invia a CJ") o automatico dopo il pagamento
(impostazione). L'ordine viene creato su CJ con numero `SOSNET-<id>` e pagato dal
**saldo CJ** dell'azienda. Una sola presa in carico per ordine (UPDATE
condizionale): clic e invio automatico non creano mai due ordini. Se CJ rifiuta,
l'errore resta sull'ordine e lo staff riceve una notifica; se l'ordine è
creato ma il saldo non basta, resta "Su CJ, da pagare" e il tentativo
successivo paga soltanto. Un invio interrotto a metà si riprende dopo 10 minuti
cercando prima su CJ il numero `SOSNET-<id>`. Merce extra-UE verso l'UE: IOSS di
CJ (`iossType=3`, vedi open-questions #17).

**Sandbox.** Con sandbox accesa gli ordini sono di prova su CJ (nessuna
spedizione, nessun addebito): il cliente però paga davvero. Lo shop si tiene
spento finché la prova non è conclusa.

**Stock e magazzino.** Lo stock di ogni variante si legge da
`getInventoryByPid` (il dettaglio prodotto spesso non lo contiene). Un prodotto
parte da un solo magazzino: quello dove sono disponibili più varianti, a parità
il più vicino (Italia, resto d'Europa, USA, Cina).

**Aggiornamenti da CJ.** Ogni 30 minuti stato, tracking e consegna degli
ordini in viaggio; al passaggio a "Spedito" e "Consegnato" il cliente riceve
notifica ed email (con link di tracciamento). Ogni notte alle 03:30 costo,
stock e disponibilità dei prodotti; una variante non più offerta da CJ resta
nel database (gli ordini la citano) ma non è più vendibile.

**Chiave API.** Salvata solo nel database, mai restituita dalle API (solo le
ultime 4 cifre), mai nel repository. Cambiarla cancella i token salvati.
Permessi: catalogo e impostazioni `sn_supplier_items.manage`, ordini
`wallet.manage` (come gli altri negozi).

## Categorie degli shop {#shop-categories}

Ogni shop ha le **sue** categorie: il nostro catalogo (una serie per
sezione: `internal`, `partner`, `dropshipping`) e i tre Marketplace
(`aliexpress`, `cj`, `shopify`). "Casa" di CJ e "Casa" di Shopify sono due
righe diverse, perché i cataloghi sono separati e un prodotto non passa mai
da uno shop all'altro. I prodotti fatti a mano del vecchio plugin
(`sn_supplier_items`) si categorizzano insieme a quelli AliExpress: il
cliente li vede nella stessa scheda.

Dominio a sé (`modules/shop_categories`, migrazione 0053), pensato per
essere rimosso senza toccare niente: **nessuna colonna aggiunta alle cinque
tabelle dei prodotti**.

- `sn_catalog_sections`: nome (unico per shop, senza distinzione fra maiuscole
  e minuscole), `position` (ordine nella barra del cliente), `active`.
- `sn_catalog_section_items`: l'appartenenza. `product_id` è un UUID **senza
  vincolo di chiave esterna**, perché punta a una riga di cinque tabelle
  diverse: è l'unico punto in cui l'isolamento dei domini si paga, ed è
  scritto nel docstring del modello.

Chi fa cosa: creare, rinominare, riordinare, nascondere ed eliminare vuole
`sn_offers.manage` (eliminare una categoria **non elimina i prodotti**);
leggere l'elenco basta essere loggati, perché al cliente servono i nomi.
Ogni lettura di prodotto (catalogo, i tre Marketplace, prodotti a mano)
porta con sé `category_ids`, caricati con **una query per pagina**, mai una
per prodotto.

Come si assegna un prodotto: spuntando le categorie **nella finestra di
importazione** (così un catalogo importato in blocco nasce già ordinato),
nel modulo di modifica del prodotto, oppure in blocco dalla card Categorie
("Assegna più prodotti a una categoria": si sceglie la categoria, si
spuntano i prodotti e si aggiungono o si tolgono — utile sui cataloghi già
importati).

Nello Shop del cliente: i negozi si scelgono con bottoni grandi, sotto
compaiono le categorie di quel negozio (solo quelle attive e con almeno un
prodotto in elenco) e una casella di ricerca su nome e descrizione. I due
filtri si sommano.

## Shop AliExpress: la Dropshipping API {#aliexpress-shop}

Il terzo shop collegato davvero a un fornitore, dopo CJ e
Shopify. Stesso schema dei due precedenti — dominio isolato
(`aliexpress_dropshipping`: `sn_aliexpress_config`, `sn_aliexpress_items`,
`sn_aliexpress_item_variants`, `sn_aliexpress_orders`), stessa esperienza per il
cliente, stesse regole comuni dei Marketplace (sconto bonifico, SosnetCash
parziale, niente cashback).

**L'app e l'autorizzazione.** L'app si crea su openservice.aliexpress.com,
categoria *Drop Shipping*; dà **App Key** e **App Secret**, e va autorizzata
sull'account venditore (il giro OAuth descritto in
[#marketplace-credentials](#marketplace-credentials)). Il token ha una
scadenza: `client.py` lo rinnova con il `refresh_token` dieci minuti prima
e dopo un rifiuto del gateway. Il permesso **DS va concesso all'app a
parte**: senza, le chiamate al catalogo rispondono "no permission" anche con
l'app approvata.

**La firma.** Gateway "iop" di Alibaba: parametri ordinati per nome,
concatenati nome+valore, HMAC-SHA256 con l'App Secret, esadecimale
maiuscolo. Le chiamate di sistema (`/auth/token/create`, `/auth/token/refresh`)
vanno su `/rest<path>` e includono il path nella firma; le chiamate DS
(`aliexpress.ds.*`) vanno su `/sync` con il parametro `method`, senza path
nella firma e con il token nel parametro `session`.

**Prezzo di vendita.** Come Shopify: `costo × cambio × (1 + ricarico%) +
ricarico fisso`, arrotondato **sempre per eccesso** a ,90 / ,99 o al
centesimo; ricarico predefinito 100%, override per prodotto; spedizione
pagata dal cliente (importo fisso) o inclusa. Costo e cambio restano
congelati sull'ordine. Le impostazioni hanno in più `ship_to_country` (IT),
`target_currency` (EUR) e `target_language` (it): sono i parametri con cui
si interroga il catalogo, quindi decidono i prezzi che AliExpress ci mostra.

**L'ordine al fornitore.** Quando il cliente ha pagato, l'ordine viene
creato su AliExpress con `aliexpress.ds.order.create` (indirizzo di
consegna, `sku_attr` della variante, il nostro riferimento `out_order_id`);
il tracking arriva con `aliexpress.ds.order.tracking.get` e porta l'ordine
a `SHIPPED` e poi `DELIVERED`, avvisando il cliente. Attenzione: `SENT`
significa "creato presso il fornitore", **non pagato**: il pagamento ad
AliExpress resta un passaggio manuale nell'account AliExpress.

**Una divergenza voluta rispetto a Shopify.** A Shopify si poteva chiedere
"hai già un ordine con il mio tag?", quindi una risposta persa si
riprovava da sola. La DS API non offre quella domanda: se `ds.order.create`
fallisce *dopo* che la richiesta è partita, o risponde senza numero
d'ordine, l'ordine va in `ERROR` **senza alcun riprovo automatico** e lo
staff riceve un avviso con l'`out_order_id` da cercare su AliExpress.
Decide una persona: spedire due colli è peggio che aspettare. I fallimenti
*prima* dell'invio mantengono il riprovo automatico con backoff.

**Da verificare dal vivo** (l'account non era ancora autorizzato quando il
dominio è stato scritto; ogni punto è marcato nel codice con un commento
`Da verificare dal vivo:`): l'involucro della richiesta di
`ds.order.create` e se `out_order_id` renda l'ordine idempotente; i nomi
dei prezzi SKU in `ds.product.get` (`offer_sale_price` vs `sku_price` —
sbagliarli alzerebbe tutti i prezzi); i parametri e l'annidamento di
`ds.text.search`; `ds.freight.query`; la forma della risposta di
`ds.order.tracking.get`; come si riconosce un ordine annullato dal
fornitore. Tutte le risposte sono lette in modo difensivo (più forme
accettate, errori del gateway riportati con le parole del gateway, mai un
risultato vuoto silenzioso).

## Account freeze

`PATCH /users/{id}/freeze` / `/unfreeze`, gated by a new, deliberately
narrow `sn_accounts.manage_lifecycle` permission (**SUPER_ADMIN only** -- the
user's own explicit request, since this is more sensitive than the
ADMIN/ORGANIZATION_ADMIN tier that already manages day-to-day
customer/promoter records). Freezing sets `users.status = "FROZEN"`,
which `auth/service.py::authenticate` now checks before even looking at
the password (reuses `AccountLockedError`/423, same as the existing
too-many-failed-attempts lock, just with a different message) -- AND
revokes every one of that user's existing sessions immediately
(`revoke_all_sessions`), so an already-logged-in frozen account is kicked
out right away, not just blocked on its next fresh login. Deliberately
does **not** touch any other data -- contracts, orders, wallet history,
network position all stay exactly as they were; unfreezing is a full,
lossless undo. An admin cannot freeze their own account.

### A frozen member disappears from the network

Freezing used to have **zero** effect on the network tree: the person kept
showing up in their upline's "Rete Commerciale" looking completely normal,
which is not what an admin freezing an account expects. Now
(`network/service.py::get_branch`, `include_frozen`):

- **Promoters/team leaders no longer see a frozen member at all** -- and
  neither does anyone below them: the frozen person's **entire subtree**
  is pruned with them. Explicit business choice ("nascondi lui e tutto il
  suo ramo"): leaving the downline behind would orphan rows the UI builds
  its tree from (`parent_agent_id`) and misrepresent depth, which is what
  the 12-level commission structure is counted on.
- **Only the admin tier still sees them** (`_FROZEN_VISIBLE_ROLES` in
  `network/router.py`: SUPER_ADMIN / ORGANIZATION_ADMIN / ADMIN), flagged
  `is_frozen` and rendered as a red **CONGELATO** badge. Deliberately
  narrower than `_BRANCH_ACCESS_BYPASS_ROLES`, which also contains
  SALES_MANAGER: seeing *every* branch and seeing *frozen people* are two
  different privileges, and only the admin tier gets the second.
- `get_branch_summary` passes the same flag through, so a hidden member
  never silently inflates an upline's headcount or contract/commission
  totals.
- **Careful:** `BranchMemberRead.is_frozen` is the OWNER'S ACCOUNT status
  (`sn_accounts.status`), not `status`, which remains the AgentProfile's own
  lifecycle (ACTIVE/SUSPENDED/TERMINATED/...). The two are independent and
  easy to confuse -- freezing has never touched the agent record, and
  still doesn't.
- Commissions are untouched: this is a **visibility** rule only. Frozen or
  not, past commissions stay frozen in their contract's network snapshot,
  and the person's real tree position is unchanged (unfreezing restores
  the previous view exactly).

**"Elimina utente" (hard delete/anonymize) was explicitly deferred by the
user** after being shown the tradeoff: a true cascading delete of
contracts/orders/wallet transactions risks breaking other promoters'
commission history (their network position and commission chain reference
this user) and conflicts with Italian fiscal record-retention requirements
for contracts/invoices. Freeze-only ships for now; a real delete/anonymize
flow is future work, to be designed once the user decides how to reconcile
those two constraints (most likely: anonymize personal data while
preserving the underlying ledger rows, not a literal `DELETE`).

## GDPR notes

Consent versions, retention periods, and the legal basis for each processing purpose
are **not** implemented as final policy in this phase — schema hooks exist
(`sn_stored_files.expires_at`, audit of all document access) but retention windows and the
lawful basis registry require legal sign-off before being treated as authoritative.
See `open-questions.md #5`.

## Companies behind products and the per-product network

- Every contract product can belong to a **company** (`sn_suppliers`, admin
  section "Aziende"): the energy supplier, the telco, and so on. A company
  has `max_network_depth` (null = no cap): how many levels of a
  collaborator's network its products reach.
- A Split Plan scoped to a product cannot pay beyond its company's depth:
  plan validation refuses an `UPLINE_LEVEL` rule deeper than the cap.
- **Per-product network** (promoter area, "I miei piani" → "La mia rete"):
  the collaborator's global network is unchanged; for one product it shows
  only the people who bought it (contracts in force), down to the company's
  depth. A customer sits one level below the collaborator who referred them;
  a collaborator who bought for themselves sits on their own node.
  Endpoint: `GET /network/agents/{id}/product-network/{product_id}`, same
  branch-access rule as the tree.
- **A promoter is also a customer**: every active promoter with a login has
  the CUSTOMER role and a customer record, attributed to their sponsor (or to
  themselves at the root), so they can buy for themselves and switch areas.
  `bootstrap` backfills this idempotently.

## Mamify {#mamify}

- **Mamify si legge e basta.** È la fonte di persone, albero sponsor, ordini e
  portafogli. SOS Affiliate ne tiene una copia e non scrive mai su Mamify:
  niente webhook registrati, niente accrediti, niente cambi di stato. Il
  client accetta solo i percorsi di `READ_ONLY_PATHS` (`rag/*` e
  `auth/login`). Uno sponsor si cambia su Mamify e la copia lo segue.
- **Il piano resta l'unica fonte dei numeri.** Un prodotto Mamify vale quello
  del prodotto del piano a cui è abbinato. L'unico importo preso dall'ordine
  è il valore di una ricarica MamiCash, base del BM.
- **Un ordine conta una volta**: chiave `MAMIFY:<ordine>:<riga>:<unità>`
  UNIQUE. Solo uno stato «pagato» genera punti e bonus. Un «annullato o
  rimborsato» li rettifica, e nient'altro li toglie.
- **Pack e ricariche**: il venditore è lo sponsor Mamify dell'impresa che
  compra.
- **I compensi li paga Mamify**: SOS li calcola e dà la lista dei dovuti con il
  cliente Mamify di ognuno; una volta pagati si segnano come pagati.
- **Un prodotto non si indovina**: le righe d'ordine Mamify hanno app, nome e
  prezzo. Se nome e prezzo non individuano un solo prodotto del catalogo, la
  riga resta «non abbinata».
- **L'accesso con Mamify** crea o allinea solo il login della persona della
  rete. Non tocca mai un account locale di qualcun altro con la stessa email.
