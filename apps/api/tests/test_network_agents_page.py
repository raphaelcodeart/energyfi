"""The collaborator registry served a page at a time: filters, counts and
network figures computed on the server, quick lookup for pickers."""

from app.modules.network import service as network_service


async def _agent(db, org, name, parent=None, code=None, status="ACTIVE"):
    agent = await network_service.create_agent(db, organization_id=org, first_name=name, last_name="Rossi",
                                               promoter_code=code or f"C-{name}", parent_agent_id=parent,
                                               status=status)
    await db.commit()
    return agent.id


async def test_pages_filters_and_network_figures(db, organization_id):
    top = await _agent(db, organization_id, "Capo")
    a = await _agent(db, organization_id, "Alfa", top)
    await _agent(db, organization_id, "Alfa1", a)
    await _agent(db, organization_id, "Beta", top)
    for i in range(30):
        await _agent(db, organization_id, f"Solo{i:02d}")
    await _agent(db, organization_id, "Attesa", status="PENDING_APPROVAL")

    first = await network_service.list_agents_page(db, organization_id=organization_id, page=1, page_size=10)
    assert (first["total"], first["pages"], len(first["items"])) == (35, 4, 10)
    assert first["counts"]["ALL"] == 35 and first["counts"]["PENDING_APPROVAL"] == 1
    last = await network_service.list_agents_page(db, organization_id=organization_id, page=4, page_size=10)
    assert len(last["items"]) == 5
    seen = {r["id"] for p in range(1, 5) for r in (await network_service.list_agents_page(
        db, organization_id=organization_id, page=p, page_size=10))["items"]}
    assert len(seen) == 35  # no row twice, none skipped

    found = await network_service.list_agents_page(db, organization_id=organization_id, search="capo")
    row = found["items"][0]
    assert found["total"] == 1 and (row["direct_count"], row["network_size"]) == (2, 3)
    alfa1 = (await network_service.list_agents_page(db, organization_id=organization_id, search="alfa1"))["items"][0]
    assert (alfa1["parent_name"], alfa1["direct_count"]) == ("Alfa Rossi", 0)
    directs = await network_service.list_agents_page(db, organization_id=organization_id, parent_id=top, sort="name")
    assert [r["first_name"] for r in directs["items"]] == ["Alfa", "Beta"]
    pending = await network_service.list_agents_page(db, organization_id=organization_id, status="PENDING_APPROVAL")
    assert [r["first_name"] for r in pending["items"]] == ["Attesa"]


async def test_lookup_by_text_and_by_id(db, organization_id):
    marco = await _agent(db, organization_id, "Marco", code="MF77")
    await _agent(db, organization_id, "Marcello")
    await _agent(db, organization_id, "Luca")
    found = await network_service.lookup_agents(db, organization_id=organization_id, q="marc")
    assert {r["display_name"] for r in found} == {"Marco Rossi", "Marcello Rossi"}
    assert (await network_service.lookup_agents(db, organization_id=organization_id, q="mf77"))[0]["id"] == marco
    assert await network_service.lookup_agents(db, organization_id=organization_id, q="") == []
    by_id = await network_service.lookup_agents(db, organization_id=organization_id, ids=[marco])
    assert [r["display_name"] for r in by_id] == ["Marco Rossi"]
