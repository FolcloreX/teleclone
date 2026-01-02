import asyncio
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Integer,
    String,
    Boolean,
    Text,
    TIMESTAMP,
    ForeignKey,
    BigInteger,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    async_sessionmaker,
    create_async_engine,
)

DATABASE_URL = 'sqlite+aiosqlite:///tracker.db'
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = 'accounts'

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    phone_number: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False
    )
    api_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    api_hash: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False
    )
    session_string: Mapped[str] = mapped_column(
        Text, unique=True, nullable=False
    )
    proxy_url: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default='active')

    last_used_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    account_name: Mapped[str] = mapped_column(String(64), nullable=False)
    username: Mapped[str] = mapped_column(String(32))
    image_slug: Mapped[str] = mapped_column(String(80), unique=True)

    clones: Mapped[List['Clones']] = relationship(back_populates='account')

    def __repr__(self):
        return f'<Account(phone={self.phone_number}, status={self.status})>'


class Clones(Base):
    __tablename__ = 'clones'

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    origin_group_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False
    )

    destiny_group_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False
    )

    origin_group_title: Mapped[str] = mapped_column(String(80), nullable=False)

    origin_group_invite: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True
    )
    destiny_group_invite: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True
    )

    phone_number: Mapped[str] = mapped_column(
        ForeignKey('accounts.phone_number')
    )

    # Possible values are: "pending", "running", "completed", "failed"
    status: Mapped[str] = mapped_column(String(20), default='active')
    offset_id: Mapped[int] = mapped_column(Integer, default=0)
    last_message_id: Mapped[int] = mapped_column(Integer, default=0)
    keep_track: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    account: Mapped[Optional['Account']] = relationship(
        back_populates='clones'
    )

    def __repr__(self):
        return (
            f'<Clones(origin={self.origin_group_id},'
            f'title={self.origin_group_title})>'
        )


async def init_db():
    """Cria as tabelas se não existirem"""
    async with engine.begin() as conn:
        # Descomente para resetar o banco
        # await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        print('Banco de dados inicializado com sucesso!')


if __name__ == '__main__':
    asyncio.run(init_db())
    print('Banco de dados inicializado com sucesso!')
