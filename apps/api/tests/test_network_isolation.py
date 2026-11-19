import uuid

import pytest

from app.foundation.security import hash_password
from app.modules.network import service as network_service
from app.modules.organizations.models import Organization
from app.modules.users.models import User


async def _make_actor(db, organization_id):
    """Actor for network_assignment_history/audit_log foreign keys."""
    user = User(
        organization_id=organization_id, email=f"actor-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.id


@pytest.mark.asyncio
async def test_branch_isolation_parallel_branches_are_not_ancestors_of_each_other(db, organization_id):
    root_a = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Root", last_name="A", promoter_code="ROOT-A", parent_agent_id=None,
    )
    child_a = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Child", last_name="A", promoter_code="CHILD-A",
        parent_agent_id=root_a.id,
    )
    root_b = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Root", last_name="B", promoter_code="ROOT-B", parent_agent_id=None,
    )

    assert await network_service.is_ancestor(
        db, organization_id=organization_id, ancestor_agent_id=root_a.id, agent_id=child_a.id
    )
    # A parallel branch is never an ancestor.
    assert not await network_service.is_ancestor(
        db, organization_id=organization_id, ancestor_agent_id=root_b.id, agent_id=child_a.id
    )


@pytest.mark.asyncio
async def test_closure_table_reflects_full_chain_depth(db, organization_id):
    a = await network_service.create_agent(
        db, organization_id=organization_id, first_name="A", last_name="Tester", promoter_code="A1", parent_agent_id=None
    )
    b = await network_service.create_agent(
        db, organization_id=organization_id, first_name="B", last_name="Tester", promoter_code="B1", parent_agent_id=a.id
    )
    c = await network_service.create_agent(
        db, organization_id=organization_id, first_name="C", last_name="Tester", promoter_code="C1", parent_agent_id=b.id
    )

    branch = await network_service.get_branch(db, organization_id=organization_id, root_agent_id=a.id)
    depths = {row["agent_id"]: row["depth"] for row in branch}
    assert depths[a.id] == 0
    assert depths[b.id] == 1
    assert depths[c.id] == 2


@pytest.mark.asyncio
async def test_get_branch_returns_parent_agent_id_for_tree_reconstruction(db, organization_id):
    """Every non-root row carries its real parent_agent_id and the root has
    none. The frontend builds the tree from this field because get_branch()
    guarantees no row order."""
    a = await network_service.create_agent(
        db, organization_id=organization_id, first_name="A", last_name="Tester", promoter_code=f"PA-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None,
    )
    b = await network_service.create_agent(
        db, organization_id=organization_id, first_name="B", last_name="Tester", promoter_code=f"PB-{uuid.uuid4().hex[:8]}",
        parent_agent_id=a.id,
    )
    c = await network_service.create_agent(
        db, organization_id=organization_id, first_name="C", last_name="Tester", promoter_code=f"PC-{uuid.uuid4().hex[:8]}",
        parent_agent_id=b.id,
    )
    d = await network_service.create_agent(
        db, organization_id=organization_id, first_name="D", last_name="Tester", promoter_code=f"PD-{uuid.uuid4().hex[:8]}",
        parent_agent_id=b.id,
    )

    branch = await network_service.get_branch(db, organization_id=organization_id, root_agent_id=a.id)
    parent_by_agent = {row["agent_id"]: row["parent_agent_id"] for row in branch}

    assert parent_by_agent[a.id] is None
    assert parent_by_agent[b.id] == a.id
    assert parent_by_agent[c.id] == b.id
    assert parent_by_agent[d.id] == b.id


@pytest.mark.asyncio
async def test_get_branch_from_a_non_root_agent_hides_its_own_parent(db, organization_id):
    """A sub-branch fetch excludes the ancestors and reports the sub-root's
    parent as None, since that parent is not in the result."""
    a = await network_service.create_agent(
        db, organization_id=organization_id, first_name="A", last_name="Tester", promoter_code=f"QA-{uuid.uuid4().hex[:8]}",
        parent_agent_id=None,
    )
    b = await network_service.create_agent(
        db, organization_id=organization_id, first_name="B", last_name="Tester", promoter_code=f"QB-{uuid.uuid4().hex[:8]}",
        parent_agent_id=a.id,
    )
    c = await network_service.create_agent(
        db, organization_id=organization_id, first_name="C", last_name="Tester", promoter_code=f"QC-{uuid.uuid4().hex[:8]}",
        parent_agent_id=b.id,
    )

    branch = await network_service.get_branch(db, organization_id=organization_id, root_agent_id=b.id)
    agent_ids = {row["agent_id"] for row in branch}
    parent_by_agent = {row["agent_id"]: row["parent_agent_id"] for row in branch}

    assert a.id not in agent_ids
    assert parent_by_agent[b.id] is None
    assert parent_by_agent[c.id] == b.id


@pytest.mark.asyncio
async def test_move_agent_prevents_cycle(db, organization_id):
    a = await network_service.create_agent(
        db, organization_id=organization_id, first_name="A", last_name="Tester", promoter_code="A2", parent_agent_id=None
    )
    b = await network_service.create_agent(
        db, organization_id=organization_id, first_name="B", last_name="Tester", promoter_code="B2", parent_agent_id=a.id
    )

    actor_user_id = await _make_actor(db, organization_id)
    with pytest.raises(network_service.CycleError):
        # a is b's ancestor, so this would create a cycle.
        await network_service.move_agent(
            db, organization_id=organization_id, agent_id=a.id, new_parent_agent_id=b.id,
            requested_by=actor_user_id, approved_by=None, reason="test",
        )


@pytest.mark.asyncio
async def test_move_agent_relocates_whole_subtree_and_updates_closure(db, organization_id):
    root1 = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Root1", last_name="Tester", promoter_code="R1", parent_agent_id=None
    )
    root2 = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Root2", last_name="Tester", promoter_code="R2", parent_agent_id=None
    )
    mover = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Mover", last_name="Tester", promoter_code="MV", parent_agent_id=root1.id
    )
    movers_child = await network_service.create_agent(
        db, organization_id=organization_id, first_name="MoversChild", last_name="Tester", promoter_code="MC",
        parent_agent_id=mover.id,
    )

    actor_user_id = await _make_actor(db, organization_id)
    await network_service.move_agent(
        db, organization_id=organization_id, agent_id=mover.id, new_parent_agent_id=root2.id,
        requested_by=actor_user_id, approved_by=actor_user_id, reason="reorg test",
    )

    assert not await network_service.is_ancestor(
        db, organization_id=organization_id, ancestor_agent_id=root1.id, agent_id=mover.id
    )
    assert not await network_service.is_ancestor(
        db, organization_id=organization_id, ancestor_agent_id=root1.id, agent_id=movers_child.id
    )
    # The subtree moves to root2 with its internal structure intact.
    assert await network_service.is_ancestor(
        db, organization_id=organization_id, ancestor_agent_id=root2.id, agent_id=mover.id
    )
    assert await network_service.is_ancestor(
        db, organization_id=organization_id, ancestor_agent_id=root2.id, agent_id=movers_child.id
    )
    assert await network_service.is_ancestor(
        db, organization_id=organization_id, ancestor_agent_id=mover.id, agent_id=movers_child.id
    )


@pytest.mark.asyncio
async def test_multi_tenant_isolation_agents_are_scoped_to_their_organization(db):
    org_a = Organization(name="Org A", status="ACTIVE")
    org_b = Organization(name="Org B", status="ACTIVE")
    db.add_all([org_a, org_b])
    await db.commit()
    await db.refresh(org_a)
    await db.refresh(org_b)

    agent_a = await network_service.create_agent(
        db, organization_id=org_a.id, first_name="Agent", last_name="A", promoter_code="OA-1", parent_agent_id=None
    )

    # Tenancy backstop: an org_b-scoped query never finds an org_a agent,
    # even by its real id.
    assert not await network_service.is_ancestor(
        db, organization_id=org_b.id, ancestor_agent_id=agent_a.id, agent_id=agent_a.id
    )
