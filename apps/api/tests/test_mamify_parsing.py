"""Readers of Mamify's answers: the plausible shapes of the same data."""

from decimal import Decimal

from app.modules.mamify import parsing


def test_items_accepts_list_or_wrapped_list():
    assert parsing.items([{"id": 1}, "x"]) == [{"id": 1}]
    assert parsing.items({"list": [{"id": 1}], "count": 1}) == [{"id": 1}]
    assert parsing.items({"data": {"list": [{"id": 2}]}}) == [{"id": 2}]
    assert parsing.items({"count": 3}) == []


def test_member_reads_italian_and_english_keys():
    m = parsing.member({"id": 12, "nome": "Anna", "cognome": "Rossi", "upline": {"id": 7}, "livello": "2",
                        "email": "Anna@Example.it", "telefono": "333", "data_registrazione": "2026-10-01 10:00:00"})
    assert (m.customer_id, m.sponsor_id, m.first_name, m.last_name, m.level) == ("12", "7", "Anna", "Rossi", 2)
    assert m.email == "anna@example.it"
    assert m.registered_at.year == 2026
    m = parsing.member({"customer_id": "9", "name": "Bo", "surname": "Li", "parent_id": 0})
    assert m.sponsor_id is None
    assert parsing.member({"name": "senza id"}) is None


def test_money_formats():
    assert parsing.money("1.234,50") == Decimal("1234.50")
    assert parsing.money("€ 1,234.50") == Decimal("1234.50")
    assert parsing.money(49) == Decimal("49.00")
    assert parsing.money("49,9") == Decimal("49.90")
    assert parsing.money(None) is None


def test_webhook_order_takes_new_status_and_lines():
    o = parsing.order({
        "order": {"id": 501, "customer_id": 12, "status": "1", "total": "1600.00",
                  "products": [{"product_id": 77, "quantity": 2, "price": "800"}]},
        "status": {"id": 3, "title": "Pagato"},
    })
    assert (o.order_id, o.buyer_id, o.status_code, o.status_title) == ("501", "12", "3", "Pagato")
    assert [(line.product_id, line.quantity, line.amount) for line in o.lines] == [("77", 2, Decimal("1600.00"))]
    assert parsing.matches_status(o, ["pagato"]) and parsing.matches_status(o, ["3"])
    assert not parsing.matches_status(o, ["annullato"])


def test_order_list_row_with_single_product():
    o = parsing.order({"id": "8", "stato": "Completato", "pagato": 1, "prodotto": None, "product": {"id": 5}})
    assert o.paid is True
    assert o.status_title == "Completato"
    assert [line.product_id for line in o.lines] == ["5"]


def test_real_shapes_of_find_network_and_orders():
    found = {"customer": {"id": 5, "first_name": "Michele", "last_name": "N", "email": "M@x.it",
                          "registration_date": "2024-09-06 08:30"}, "sponsor": {"id": 317}, "network": {"total": 304}}
    m = parsing.member(parsing.customer_of(found))
    assert (m.customer_id, m.first_name, m.email, m.registered_at.year) == ("5", "Michele", "m@x.it", 2024)
    row = parsing.member({"id": 51507, "first_name": "Petro", "last_name": "A", "level": 1, "sponsor_id": 5,
                          "direct": 0, "total": 0})
    assert (row.sponsor_id, row.level) == ("5", 1)
    o = parsing.order({"id": 4211, "date": "2026-10-09 14:07", "status": "0", "status_label": "In attesa di pagamento",
                       "paid": False, "total": 40, "products": [{"name": "Gift Card Glovo IT", "quantity": 1, "price": 40,
                                                                  "type": "giftcard", "app": "mamicash"}]})
    assert (o.status_code, o.status_title, o.paid) == ("0", "In attesa di pagamento", False)
    line = o.lines[0]
    assert (line.product_id, line.name, line.app, line.unit_price) == (None, "Gift Card Glovo IT", "mamicash", Decimal("40.00"))
    assert line.label == "mamicash · Gift Card Glovo IT 40.00"


def test_resolve_line_by_app_name_and_price():
    catalog = [{"id": "17280", "app": "sos-affiliate", "name": "Pacchetto Start", "price": 1000, "promo_price": None},
               {"id": "17285", "app": "sos-affiliate", "name": "Pacchetto Start", "price": 97, "promo_price": None},
               {"id": "17297", "app": "digitalambassador", "name": "12 Licenze", "price": 6000, "promo_price": 1600}]

    def line(name, price, app="sos-affiliate"):
        return parsing.OrderLine(None, 1, None, name=name, app=app, unit_price=parsing.money(price))

    assert parsing.resolve_line(line("Pacchetto Start", 97), catalog) == "17285"
    assert parsing.resolve_line(line("pacchetto start", 1000), catalog) == "17280"
    assert parsing.resolve_line(line("Pacchetto Start", 500), catalog) is None  # ambiguous: not guessed
    assert parsing.resolve_line(line("12 Licenze", 1600, "digitalambassador"), catalog) == "17297"  # promo price
    # Mamify moved the product to another app: same name and price still find it.
    assert parsing.resolve_line(line("12 Licenze", 1600, "altra-app"), catalog) == "17297"
    assert parsing.resolve_line(line("12 Licenze", 999, "altra-app"), catalog) is None
    moved = [{"id": "17292", "app": "sos-affiliate", "name": "Digital Ambassador", "price": 49, "promo_price": None}]
    assert parsing.resolve_line(line("Digital Ambassador", 49, "digitalambassador"), moved) == "17292"
