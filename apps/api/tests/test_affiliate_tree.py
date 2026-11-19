"""The tree view's branches: pages of directs, biggest branches first, the
path from the top, search, and a Digital Ambassador never seeing above them."""

from app.modules.affiliate import tree
from app.modules.network import service as network_service


async def _agent(db, org, name, parent=None):
    agent = await network_service.create_agent(db, organization_id=org, first_name=name, last_name="",
                                               promoter_code=f"T-{name}", parent_agent_id=parent)
    await db.commit()
    return agent.id


async def _build(db, org):
    """top1 (2 directs: a, b; a has a1) and 150 small top-level people."""
    top1 = await _agent(db, org, "Top1")
    a = await _agent(db, org, "Alfa", top1)
    await _agent(db, org, "Alfa1", a)
    b = await _agent(db, org, "Beta", top1)
    for i in range(150):
        await _agent(db, org, f"Solo{i:03d}")
    return top1, a, b


async def test_top_level_is_paged_biggest_first(db, organization_id):
    top1, _a, _b = await _build(db, organization_id)
    snap = await tree.snapshot(db, organization_id, fresh=True)
    first = tree.branch(snap, None, limit=100)
    assert first["total_children"] == 151 and len(first["children"]) == 100
    assert first["children"][0]["agent"]["id"] == top1
    assert first["children"][0]["network_size"] == 3
    rest = tree.branch(snap, None, offset=100, limit=100)
    assert len(rest["children"]) == 51
    assert tree.summary(snap, None)["people"] == 154


async def test_branch_has_path_and_summary(db, organization_id):
    top1, a, _b = await _build(db, organization_id)
    snap = await tree.snapshot(db, organization_id, fresh=True)
    out = tree.branch(snap, a)
    assert [r["agent"]["id"] for r in out["path"]] == [top1]
    assert [r["agent"]["name"] for r in out["children"]] == ["Alfa1"]
    assert tree.summary(snap, top1)["by_depth"] == [{"depth": 0, "people": 1}, {"depth": 1, "people": 2},
                                                    {"depth": 2, "people": 1}]


async def test_scope_hides_everyone_above_the_viewer(db, organization_id):
    top1, a, b = await _build(db, organization_id)
    snap = await tree.snapshot(db, organization_id, fresh=True)
    alfa1 = tree.branch(snap, a)["children"][0]["agent"]["id"]
    out = tree.branch(snap, alfa1, scope=a)
    assert [r["agent"]["id"] for r in out["path"]] == [a]  # not top1
    assert snap.within(alfa1, a) and not snap.within(b, a) and not snap.within(top1, a)
    found = tree.search(snap, "beta", scope=a)
    assert found["total"] == 0
    found = tree.search(snap, "alfa1", scope=a)
    assert [r["agent"]["id"] for r in found["results"]] == [alfa1]
    assert [p["id"] for p in found["results"][0]["path"]] == [a]


async def test_search_whole_network(db, organization_id):
    top1, a, _b = await _build(db, organization_id)
    snap = await tree.snapshot(db, organization_id, fresh=True)
    found = tree.search(snap, "solo1", scope=None)
    assert found["total"] == 50  # Solo100..Solo149
    found = tree.search(snap, "alfa1", scope=None)
    assert [p["id"] for p in found["results"][0]["path"]] == [top1, a]
    assert tree.search(snap, "a", scope=None)["total"] == 0  # too short to search


async def test_galaxy_is_the_viewers_branch_in_breadth_order(db, organization_id):
    top1, a, _b = await _build(db, organization_id)
    snap = await tree.snapshot(db, organization_id, fresh=True)
    out = tree.galaxy(snap, a)
    f = {k: i for i, k in enumerate(out["fields"])}
    names = [r[f["name"]] for r in out["nodes"]]
    assert names == ["Alfa", "Alfa1"] and out["people"] == 2 and not out["truncated"]
    assert out["nodes"][0][f["parent"]] == -1 and out["nodes"][1][f["parent"]] == 0
    assert out["nodes"][1][f["depth"]] == 1
    assert "email" not in out["fields"] and "phone" not in out["fields"]
    whole = tree.galaxy(snap, top1)
    assert [r[f["name"]] for r in whole["nodes"]][:1] == ["Top1"] and whole["people"] == 4
    for i, r in enumerate(whole["nodes"][1:], start=1):
        assert 0 <= r[f["parent"]] < i
    cut = tree.galaxy(snap, top1, limit=2)
    assert cut["shown"] == 2 and cut["truncated"]


async def test_an_old_copy_is_served_at_once(db, organization_id):
    await _build(db, organization_id)
    first = await tree.snapshot(db, organization_id, fresh=True)
    first.built_at -= tree.CACHE_SECONDS + 1
    again = await tree.snapshot(db, organization_id)
    assert again is first  # served while a new one is built in the background
    await _agent(db, organization_id, "Nuovo")
    rebuilt = await tree.snapshot(db, organization_id)
    assert rebuilt is not first and any(n.name == "Nuovo" for n in rebuilt.nodes.values())
