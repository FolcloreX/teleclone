import asyncio
from src.engine import CloneEngine
from src.settings import setup_logging, settings
from src.data.models import init_db
from src.data.accounts import get_account

setup_logging()


async def main():
    await init_db()
    # Chat to catch from
    origin_group_id = -1002327540853
    # Chat to send to
    destiny_group_id = -1003360919673
    # offset_id
    offset_id = 209

    account = await get_account(settings.phone_number)
    session_string = str(account.session_string) if account else None

    clone_engine = CloneEngine(
        api_id=settings.api_id,
        api_hash=settings.api_hash,
        phone=settings.phone_number,
        password=settings.password,
        session_string=session_string,
    )

    await clone_engine.start_clone(
        origin=origin_group_id, destiny=destiny_group_id, offset_id=offset_id
    )


if __name__ == '__main__':
    asyncio.run(main())
