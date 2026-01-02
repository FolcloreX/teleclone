import logging
from typing import Optional
from sqlalchemy import select, delete
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from .models import AsyncSessionLocal, Account

logger = logging.getLogger(__name__)


async def store_account(
    phone_number: str,
    api_id: int,
    api_hash: str,
    session_string: str,
    account_name: str,
    image_slug: Optional[str] = None,
    username: Optional[str] = None,
    proxy_url: Optional[str] = None,
) -> Account:
    """
    Create or Update (Upsert) an account.
    If the phone number exists, it updates the session and status.
    If not, it creates a new one.
    """
    async with AsyncSessionLocal() as session:
        try:
            # Prepare the Insert Statement
            insert_stmt = sqlite_insert(Account).values(
                phone_number=phone_number,
                api_id=api_id,
                api_hash=api_hash,
                session_string=session_string,
                proxy_url=proxy_url,
                account_name=account_name,
                image_slug=image_slug,
                username=username,
                status='active',
            )

            # If phone_number exists, update these fields:
            upsert_stmt = insert_stmt.on_conflict_do_update(
                index_elements=[
                    'phone_number'
                ],  # The unique constraint column
                set_={
                    'session_string': session_string,
                    'api_id': api_id,
                    'api_hash': api_hash,
                    'account_name': account_name,
                    'image_slug': image_slug,
                    'username': username,
                    'proxy_url': proxy_url,
                    'status': 'active',  # Reactivate if it was inactive
                    'last_used_at': insert_stmt.excluded.last_used_at,
                },
            ).returning(Account)

            # 3. Execute
            result = await session.execute(upsert_stmt)
            await session.commit()

            account = result.scalar_one()
            logger.info(f'✅ Account {phone_number} stored successfully.')
            return account

        except Exception as e:
            logger.error(f'❌ Failed to store account {phone_number}: {e}')
            await session.rollback()
            raise e


async def delete_account(self, phone_number: str) -> bool:
    """
    Hard delete an account from the database.
    Returns True if deleted, False if not found.
    """
    async with AsyncSessionLocal() as session:
        try:
            # 1. Execute Delete
            stmt = delete(Account).where(Account.phone_number == phone_number)
            result = await session.execute(stmt)

            await session.commit()

            # 2. Check if a row was actually deleted
            if result.rowcount > 0:
                logger.info(f'🗑️ Account {phone_number} deleted.')
                return True
            else:
                logger.warning(
                    f'⚠️ Account {phone_number} not found to delete.'
                )
                return False

        except Exception as e:
            logger.error(f'❌ Failed to delete account {phone_number}: {e}')
            await session.rollback()
            raise e


async def get_account(phone_number: str) -> Optional[Account]:
    """Helper to fetch account details."""
    async with AsyncSessionLocal() as session:
        stmt = select(Account).where(Account.phone_number == phone_number)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
