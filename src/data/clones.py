from typing import Optional, List
from sqlalchemy import select, update, delete, func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from .models import AsyncSessionLocal, Clones


async def create_clone(
    origin_group_id: int,
    destiny_group_id: int,
    origin_group_title: str,
    phone_number: str,
) -> Clones:
    """
    Register a new cloner task. If the clone already exists
    update basic infos, and reactivated.
    """

    async with AsyncSessionLocal() as session:
        stmt = (
            sqlite_insert(Clones)
            .values(
                origin_group_id=origin_group_id,
                destiny_group_id=destiny_group_id,
                origin_group_title=origin_group_title,
                phone_number=phone_number,
                status='pending',
            )
            .on_conflict_do_update(
                index_elements=[
                    'origin_group_id'
                ],  # Ensure only 1 destiny have 1 one active task
                set_={
                    'origin_group_title': origin_group_title,
                    'phone_number': phone_number,
                    'status': 'pending',  # Reset the status
                    'updated_at': func.now(),
                },
            )
            .returning(Clones)
        )

        result = await session.execute(stmt)
        return result.scalar_one()


async def get_clone_by_id(clone_id: int) -> Optional[Clones]:
    """Busca pelo ID interno da tarefa (PK)."""
    async with AsyncSessionLocal() as session:
        stmt = select(Clones).where(Clones.id == clone_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


# TODO limitar por conta também, como parametro
async def get_active_clones() -> List[Clones]:
    """Lista todos os clones que não estão 'completed' ou 'stopped'."""
    async with AsyncSessionLocal() as session:
        stmt = select(Clones).where(Clones.status.in_(['pending', 'running']))
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def update_clone_progress(clone_id: int, **kwargs) -> Optional[Clones]:
    """
    Dinamically updates the progress
    Use: await update_clone_progress(
        1, last_message_id=50, status='running'
    )

    Security filter: remove the keys that doesn't exist or
    don't have to changed
    """
    async with AsyncSessionLocal() as session:
        valid_keys = {
            'status',
            'last_message_id',
            'total_messages',
            'invite_link',
            'account_id',
        }

        updates = {k: v for k, v in kwargs.items() if k in valid_keys}

        if not updates:
            return None

        stmt = (
            update(Clones)
            .where(Clones.id == clone_id)
            .values(**updates)
            .returning(Clones)
        )

        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def remove_clone(clone_id: int) -> bool:
    """
    Remove a clone task from the database
    It doesn't delete the groups, only the database register
    """
    async with AsyncSessionLocal() as session:
        stmt = delete(Clones).where(Clones.id == clone_id)
        result = await session.execute(stmt)
        return result.rowcount > 0
