"""Home balances come from Mamify's wallets (read only), for the person's
own Mamify customer; someone outside the network sees "not connected"."""

from app.modules.external_wallet import service


def test_mamify_wallet_answer_becomes_cents():
    answer = {"mamix": {"balance": 116.5, "formatted": "116,50 MAMIX"},
              "mamicash": {"balance": 7015.15, "personal": 6915.15, "business": 100}}
    assert service.parse_wallets(answer) == {
        "mamix_cents": 11650, "mamicash_cents": 701515,
        "mamicash_personal_cents": 691515, "mamicash_business_cents": 10000,
    }
    assert service.parse_wallets({})["mamix_cents"] is None


async def test_someone_outside_the_network_is_not_connected(db, organization_id):
    import uuid

    out = await service.fetch_balances(db, organization_id=organization_id, user_id=uuid.uuid4())
    assert out["connected"] is False and out["mamix_cents"] is None
