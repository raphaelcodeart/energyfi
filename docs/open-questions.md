# Open Questions / Assumptions Requiring Confirmation

Source document `docs/Allegato_A_Piano_Carriera_Regolamento_Provvigionale.pdf` was not
present in the repository. Everything below is a placeholder that makes the system
runnable and testable; none of it is confirmed SOSNET policy. Each item names the
exact config location to update once real figures/rules are available — no formula is
silently invented into unlabelled code.

## 1. Rank table (career plan) figures

**Placeholder**: `SP1..SP3` (SosPromoter), `SL1..SL4` (SosLeader), `SM1..SM5` (SosManager) with linearly increasing
`personal_token_cents` (4000 → 9500), see `business-rules.md §Ranks`.
**Update**: `personal_volume_threshold_cents` /
`group_volume_threshold_cents` are no longer 0 -- populated with placeholder
ascending figures (seed data) at the user's explicit request ("go get
those criteria and set them yourself"), used by the new rank-promotion-progress
feature (`business-rules.md §Rank promotion progress`). Still not confirmed
SOSNET policy. `evaluation_window_months` remains unused/unknown -- the
progress calculation is lifetime-cumulative, not evaluated over any window.
**Where to fix**: `apps/api/app/seed/ranks.py`, or a new `sn_payout_rules` row once the real plan document is
available — no application code change needed, only data.
**Also**: `network/service.py::AUTO_ACTIVATION_RANK_CODE = "SP1"`
hardcodes the floor rank self-service "lavora con noi" applicants start at,
instead of deriving the lowest-`level` rank from the org's ladder. If code
`SP1` is ever renamed/removed, this silently resolves to no rank
(`_get_current_rank_id` returns `None`, no error) rather than failing loud.
**Where to fix**: same file, alongside item #1's other placeholder figures.
**Update**: a second, independent axis now exists —
`commissions/services/rank_evaluation.py` actually **writes** the agent's
rank (promotes or demotes) once a month, using a fixed single-calendar-month
window, explicitly NOT `evaluation_window_months` (still unused by anything).
This was an explicit user decision, not a resolution of this open question —
see `business-rules.md §Automatic monthly rank evaluation`. If the real plan
document specifies a genuine rolling window, both this and item #6 below need
updating together, since they'd likely share the same window definition.

## 2. Network move approval

**Assumption**: a role with `network.manage` may self-approve a branch move
(`approved_by` optional in that case); all other moves require a second approver.
**Where to fix**: `apps/api/app/modules/network/service.py::move_agent` — the
self-approval check is a single `if` guarded by this assumption; flip it once the real
approval policy is confirmed.

## 3. Energia Circolare bonus formula

**Assumption**: no distinct bonus formula exists yet; Energia Circolare contracts only
have the extension point (`sn_offer_versions` can point at a distinct
`commission_plan_version_id`), with a no-op hook in the calculator
(`commission-engine-specification.md §Algorithm` step 18).
**Where to fix**: implement the real formula in
`apps/api/app/modules/commissions/calculators/energia_circolare.py` (file reserved but
not yet created) once the rule is known.

## 4. Reversal ("storno") refund formula

**Assumption**: linear proration —
`refund_cents = original_amount_cents * remaining_months / total_contract_months`.
**Where to fix**: `apps/api/app/modules/commissions/calculators/reversal.py`.

## 5. GDPR retention & legal basis

**Assumption**: none finalized. Schema hooks exist (`sn_stored_files.expires_at`, full audit
of document access/download) but retention windows per document category and the
lawful-basis registry require legal sign-off, not an engineering guess.
**Where to fix**: this requires a decision from SOSNET's legal counsel, then a
`retention_policies` table (not yet created) keyed by document category.

## 6. 33% branch cap — exact denominator

**Assumption**: the cap applies to production aggregated at first-level-branch
granularity under the evaluated beneficiary, using the same evaluation window as the
beneficiary's rank re-evaluation (`sn_career_levels.evaluation_window_months`).
**Where to fix**: `apps/api/app/modules/commissions/policies/branch_cap.py` — the
aggregation query is isolated there specifically so the denominator can change without
touching the main calculator.
**Note**: the rank re-evaluation that now actually exists
(`rank_evaluation.py`, see item #1) does NOT use `evaluation_window_months`
either — it's a fixed single calendar month. This assumption's cross-reference
to "the same evaluation window" is therefore still unresolved/unverified, not
contradicted; revisit both together once the real window is known.

## 7. MFA and account lockout policy

**Assumption**: MFA schema is present (session/device tables support it) but not
enforced in v1; account lockout threshold is a placeholder (5 failed attempts / 15
minute window) pending a real security policy decision.
**Where to fix**: `apps/api/app/modules/auth/service.py` constants
`MAX_FAILED_ATTEMPTS`, `LOCKOUT_WINDOW_MINUTES`.

## 8. Che cosa è "il totale del contratto"

**Assumption**: the taxable/chargeable amount of a SOSNET contract is
`sn_offer_versions.base_price_cents` — the single figure the dashboard has
always shown as the product's price, and the one the wizard already renders
with "+ IVA" next to it. `initial_fee_cents` and `recurring_fee_cents` exist
on the same row but **have never been charged by any code path in this
project**, so folding them in would silently start billing amounts nobody has
agreed to.

This matters now for the first time, because contracts are about to become
payable (three plans: unico / mensile 12 mesi / finanziaria Stripe). The
business talks
about a "contratto BAR / Energia Circolare da €249", while the products
actually in the catalog are priced €15–€35 base with a small monthly
recurring fee — so either that product does not exist yet, or "il totale" is
computed differently from what the code assumes.

**Where to fix**: `apps/api/app/modules/catalog/pricing.py::
contract_net_amount_cents` — deliberately one function, so every price, VAT
figure and payment plan in the app follows from changing it in one place.

## 9. Percentuale di cashback sui contratti

**Assumption**: `sn_offer_versions.contract_cashback_percentage` is **0 on
every product**, i.e. paying a contract currently credits no SosnetCash at all.
The mechanism is built and tested; the number is a deliberate no-op until the
business sets it, because it mints credit and the safe default is "off".

The stated rule was "intero importo + IVA accreditato nel wallet SosnetCash",
which would be **100** (the credit is computed on the gross, VAT included).
That is a 1:1 return of everything the customer paid, which is a large
commitment — hence set by an admin per product, not assumed here.

**Where to fix**: admin dashboard, `Prodotti → modifica → Cashback automatico
sul contratto (%)`. No deploy needed.

## 10. Bonus primo segnalatore: su quali prodotti

**Assumption**: `first_referrer_bonus_enabled` is **false on every product**.
The stated example — €25 extra to the first referrer on the "BAR / Energia
Circolare €249" contract, on top of the existing €80 commission — cannot be
configured yet because **that product does not exist in the catalog**.

**Where to fix**: create the product, then admin dashboard, `Prodotti →
modifica → Bonus primo segnalatore`. No deploy needed.

## 11. Testo del contratto promoter "Lavora con noi"

**Assumption**: none — deliberately. The flow already requires an OTP
confirmation whose email text mentions "accettare il contratto di
collaborazione", but no contract text or version is stored, and **no
placeholder text was invented**, per explicit instruction ("NON inserire
adesso testo inventato").

The contract-side plumbing for storing proof of acceptance already exists and
is the shape this will reuse: `contracts.terms_accepted_at /
terms_accepted_by_user_id / terms_version / terms_accepted_ip /
terms_accepted_user_agent` (migration 0035).

**Where to fix**: pending the official PDF from the business.

## 12. ~~"Finanziaria Stripe"~~ — RISOLTA

The third payment plan is **3 rate**, and it needs no external financing
provider at all: it is the same Stripe subscription as the 12-instalment
plan, with N = 3. SOSNET splits its own invoice and is paid by the
customer's own card each month, so there is nothing to finance, no BNPL
capability to enable, and no account review to wait for.

Built  (`contracts/payment_plans.py`). Left here rather than
deleted because "possiamo usare Klarna?" is the kind of question that comes
back, and the answer — that the requirement never actually needed it — is
worth keeping.

## 13. Eventi del webhook Stripe per le rate — DA FARE SUL PANNELLO STRIPE

L'endpoint webhook registrato su Stripe ha abilitato **solo**
`checkout.session.completed`. Vanno aggiunti `invoice.paid` e
`invoice.payment_failed`: senza, dalla 2ª rata in poi Stripe addebita la carta
ma l'app non registra la rata (niente cashback, niente provvigioni per rata,
nessun avviso di addebito fallito). Il codice è pronto; manca solo la
configurazione, che non è stata cambiata da qui senza conferma. Vedi
`server-migration-guide.md` §11.

## 14. Il pacchetto "GAS Energia Circolare con cash back" è registrato come luce

Codice prodotto `LUCE-STD-COPY`, `energy_type = ELECTRICITY`: sembra la copia
di un pacchetto luce rinominata senza cambiare il tipo. Ora è il
pacchetto scelto a decidere se un POD è luce o gas, quindi un POD con questo
pacchetto risulta **luce**. Correzione da Prodotti → tipo energia Gas, se è
davvero un pacchetto gas. I contratti già aperti restano invariati.

## 15. Prezzi dello Shop: IVA inclusa o esclusa?

Scheda e dettaglio prodotto dello Shop mostrano "+ IVA 22% (totale)", ma
l'ordine addebita il prezzo di listino senza aggiungere IVA. Serve una
decisione: il prezzo dello Shop è IVA inclusa (e va tolta la dicitura) o IVA
esclusa (e va aggiunta al checkout)?

## 16. Stesso POD in due contratti

Il codice POD/PDR non si chiede più nella pratica (richiesta esplicita), quindi
il sistema non può accorgersi se lo stesso punto reale viene attivato due
volte: il controllo passa alla verifica della bolletta da parte
dell'amministrazione. Se diventa un problema, si può chiedere il codice come
campo **facoltativo** al momento della verifica documenti.

---

When `Allegato_A_Piano_Carriera_Regolamento_Provvigionale.pdf` (or an equivalent
written policy) becomes available, re-open this file item by item, update the
corresponding code/data location, delete the resolved item, and record the change as a
new ADR if it affects architecture (e.g. a genuinely new bonus category that doesn't
fit the current calculator extension points).

## 17. Shop Sosnet Partner: prima di accenderlo

Collegamento a CJ fatto e verificato; lo shop è **spento e in sandbox**.
Decisioni e azioni che restano all'azienda:

- **Saldo CJ**: non serve più precaricarlo. Con saldo a zero
  ogni ordine pagato dal cliente viene creato su CJ e resta "Pagamento CJ
  richiesto" finché non lo paghi dalla pagina CJ dell'ordine. Da verificare al
  primo ordine reale (non sandbox) che CJ restituisca davvero la pagina di
  pagamento (`cjPayUrl`): in sandbox CJ paga da sé e non la restituisce. Se
  mancasse, l'ordine si paga comunque dalla lista ordini del sito CJ.
- **Margini**: CJ addebita spedizione con sdoganamento e IVA IOSS (~22% del
  prodotto). Sull'unico prodotto importato: costo reale circa 29,62 $
  (≈ 27,25 €) contro 25,90 € di prezzo + spedizione pagata dal cliente.
  Controllare il margine stimato in "Ordini" e, se serve, alzare il ricarico.
- **IVA e dogana**: la merce parte quasi sempre dalla Cina. Gli ordini sono
  inviati con `iossType=3` (IVA all'importazione riscossa tramite l'IOSS di
  CJ), così il cliente non paga dazi alla consegna. Da confermare con il
  commercialista, insieme a come fatturare queste vendite (vedi anche #15).
- **Cambio USD/EUR**: è un valore fisso impostato a mano (0,92). Va
  aggiornato ogni tanto; al salvataggio tutti i prezzi si ricalcolano.
- **Traduzioni**: nomi e descrizioni arrivano in inglese; si traducono
  all'importazione (campi modificabili).
- **Resi e rimborsi**: un ordine già pagato e poi annullato da CJ viene solo
  segnalato allo staff; rimborso e restituzione SosnetCash oggi si gestiscono a
  mano.
- **Sandbox**: spegnerla solo quando si vuole spedire davvero. Con sandbox
  accesa un cliente che paga davvero non riceverebbe nulla: per questo lo
  shop resta spento finché la prova non è finita.

## 18. Sconto del pagamento unico e cashback

Con lo sconto (32%) il cashback SosnetCash di un contratto pagato tutto subito è
calcolato su quanto il cliente paga, non sul prezzo pieno. Su un prodotto con
cashback al 100%: pratica da 1.140 €, pagata 775,20 €, cashback 775,20 SosnetCash
(prima 1.140). Se il cashback deve restare sul prezzo pieno è una modifica di
una riga (`contracts/service.py::credit_contract_cashback`). Percentuale
confermata dall'azienda: 32%. Resta da confermare solo la regola
del cashback.

## IVA dei Marketplace: inclusa o aggiunta? (CHIUSA il 21/09/2026)

**Risolta **: l'utente ha scelto l'opzione **(a)** — lo
sconto bonifico non tocca l'IVA — e l'IVA aggiunta è in produzione.
Quanto segue resta come memoria di come ci si è arrivati.

Nella  si era deciso, insieme all'utente, che il prezzo mostrato
è **IVA inclusa** (Codice del Consumo artt. 14-15: verso un consumatore il
prezzo esposto dev'essere quello finale). Nella  l'utente ha
chiesto di ribaltarla: 17,90 diventa l'imponibile, l'IVA si somma sopra.

Deciso con l'utente:
- **16,38 €** su un prodotto da 17,90 con il 25% di SosnetCash — il 25% pieno,
  nessun arrotondamento intermedio (nella formula che l'utente ha scritto
  13,425 diventava 13,25: è un refuso, non una regola);
- si applica a **tutti e tre i Marketplace**; il catalogo interno resta com'è;
- in vetrina si legge **17,90 + IVA**;
- l'IVA si calcola sui **17,90 pieni**: i SosnetCash restano un modo di pagare
  e non abbassano l'imponibile;
- la **spedizione resta fuori IVA** (fiscalmente discutibile — art. 12 DPR
  633/72 vuole che segua l'aliquota del bene — ma è la scelta dell'utente,
  presa dopo averglielo fatto presente).

**Ancora da decidere, e perché il lavoro non è partito**: lo sconto bonifico
del 5% oggi abbassa l'imponibile IVA (`freeze_vat`). Con l'IVA aggiunta
l'imponibile è congelato prima di sapere il metodo di pagamento, quindi o
(a) lo sconto bonifico non tocca più l'IVA — coerente con la scelta fatta
sui SosnetCash — oppure (b) continua ad abbassarla, e allora va applicato
all'imponibile *prima* dell'IVA, cambiando l'ordine con i SosnetCash rispetto
a oggi. Raccomandazione: **(b)**, perché è una vera riduzione di prezzo
(art. 13 DPR 633/72) e mantiene la distinzione che il codice già documenta.

**Dove si tocca**: `marketplaces/rules.py` (nuova `vat_added_cents`,
`vat_included_cents` resta per rileggere gli ordini vecchi), i tre
`service.py` dei Marketplace, una migrazione con una colonna `vat_mode`
(`INCLUDED`/`ADDED`) sulle tabelle ordini — le stesse colonne avrebbero
altrimenti significato opposto fra ordini vecchi e nuovi — e le diciture
nel frontend.

## 19. Rete unica e Split Plan: le scelte di partenza (22/09/2026)

Il sistema le rende tutte configurabili; questi sono solo i valori con cui
parte, da confermare:

1. **Livello mancante nella rete** — scelta per piano (e per singola regola):
   azienda, primo idoneo più in alto, oppure non distribuita. Default nuovi
   piani: **all'azienda**.
2. **Più ruoli contemporaneamente** — no: un ruolo commerciale alla volta,
   storicizzato; le deleghe influencer coprono il caso "vendo per conto di".
3. **Split personalizzato per singola persona** — non previsto: il piano è per
   prodotto/categoria + ruolo. Si può aggiungere come livello di specificità in più.
4. **Cambio ruolo** — vale dalla data indicata in poi, mai all'indietro oltre
   l'inizio del ruolo attuale; le vendite precedenti restano col ruolo di allora.
5. **Promoter che diventa altro ruolo** — sì, con un normale cambio di ruolo.
6. **Minimi / massimi** — supportati per regola (minimo garantito e tetto).
7. **Quota influencer** — fissa, percentuale o minimo garantito: la decide la regola.
8. **Data della vendita** — la firma (creazione del contratto), non l'attivazione.
9. **Quando matura** — per piano: una quota a ogni rata incassata (default)
   oppure tutto all'attivazione.
10. **Margine percentuale** — calcolato sull'importo netto (IVA esclusa).
11. **Annullamento dopo il pagamento** — storno dell'intera quota pagata (riga
    negativa da recuperare). Un recupero proporzionale ai mesi restanti non è
    ancora previsto.
12. **Shop** — gli ordini dello shop non generano provvigioni (come prima).

## 20. SOS Affiliate: scelte di partenza da confermare (03/11/2026)

Dove la *Specifica tecnica* v1.1 e il *Piano Compensi* del 29/10/2026 non
dicono nulla. Dettaglio e motivazioni in `sos-affiliate.md` §7.

1. **Pagamenti** — confermati a mano dall'amministrazione; Stripe in seguito.
2. **Mese dei punti** — la mensilità vale per il mese pagato; ogni altro
   acquisto per il mese in cui il pagamento è confermato.
3. **Licenza in omaggio** — zero BC e costo zero (margine pieno alla rivendita).
4. **MamiCash della rivendita** — i 500 MamiCash all'impresa non generano BM.
5. **Evento Roma** — 6.000 punti misurati sul BCT di novembre 2026, non sul BCP.
6. **Posizioni BD/BM vuote** — restano all'azienda, nessuna compressione.
7. **Bonus Carriera e abbonamento** — nessun requisito di abbonamento attivo.
8. **Spostamenti nella rete** — il mese aperto segue l'albero di oggi; i mesi
   chiusi restano congelati.
9. **Saldo MamiCash** — registro informativo, non un portafoglio spendibile.

## 21. Collegamento Mamify: da decidere o verificare (aggiornato 04/11/2026)

Dettagli in `mamify-integration.md`. Il collegamento è **solo in lettura**
(decisione dell'utente del 04/11/2026): SOS non scrive mai su Mamify.

Risolti con la chiave vera (04/11/2026): campi delle risposte, sponsor in ogni
riga della rete (`sponsor_id`, `scope: "all"`), dominio con certificato
valido (`net.mamify.ai`), cima della rete (Condividiamo Ltd, cliente 317).

1. **Pacchetti mensili** — su Mamify ci sono Start, Business, Premium e
   International anche mensili (97, 197, 397, 997 €). Il piano prevede solo i
   Pack annuali. Contano per il piano, e come?
2. **«Licenze» da 500 €** (prodotto 17293, app sos-affiliate, categoria
   Business Partner, 500 MamiCash all'acquirente) — è la rivendita di una
   licenza a un'impresa (piano: 450 € al venditore, 50 € all'azienda)? Chi è il
   venditore: lo sponsor Mamify dell'impresa? Oggi non è abbinato.
3. **Stati «annullato o rimborsato»** — finora si sono visti solo `0` «In
   attesa di pagamento» e `3` «Completato». Configurati per nome: Annullato,
   Rimborsato, Cancellato, Rifiutato. Vanno confermati con Mamify.
4. **Chi è un Digital Ambassador** — l'albero copia tutte le 50.822 persone
   di Mamify (anche chi non ha mai comprato nulla di SOS), per essere identico.
   Il piano le tratta come nodi senza mensilità pagata. Va bene così, o
   l'albero deve mostrare solo chi ha la mensilità?
5. **Ordini in tempo reale** — senza webhook gli ordini si leggono a turno
   (chi conta di più ogni ora, gli altri circa una volta al giorno). Lo staff
   Mamify può registrare dal CRM gli avvisi verso gli indirizzi della pagina
   «Collegamento Mamify» (SOS non lo fa: sarebbe una scrittura). In
   alternativa: chiedere a Mamify un'API di servizio «ordini di un'app» o
   «ordini dal giorno X».
6. **Pagamento dei compensi** — li paga lo staff Mamify dalla lista «Compensi
   da pagare» (CSV). Con quale cambio € → MamiCash/Mamix e in quale
   portafoglio va ogni tipo di compenso: da decidere con Mamify.
7. **Imprese clienti** — si assume che l'impresa che compra un Pack o una
   ricarica sia nella rete Mamify sotto il Digital Ambassador che la segue.
8. **Accesso con le credenziali Mamify** — usa `auth/login`, che controlla la
   password e restituisce un token di sessione: non cambia i dati di Mamify ma
   apre una sessione. Se anche questo va evitato, gli affiliati avranno bisogno
   di una password propria di SOS.
