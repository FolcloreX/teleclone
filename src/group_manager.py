import logging
from telethon.tl.functions.channels import (
    EditTitleRequest,
    EditPhotoRequest,
    GetFullChannelRequest,
    CreateChannelRequest,
    InviteToChannelRequest,
    LeaveChannelRequest,
)
from telethon import TelegramClient
from telethon.tl.types import Chat, InputChatUploadedPhoto, Channel
from typing import Optional
from telethon.tl.functions.messages import (
    EditChatAboutRequest,
    ExportChatInviteRequest,
)

from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import UserAlreadyParticipantError
from functools import partial


logger = logging.getLogger(__name__)


class GroupManager:
    def __init__(self, client: TelegramClient):
        self.client = client

    async def enter_channel(
        self, invite_link: str
    ) -> Optional[Chat | Channel]:
        """
        Enter in a channel/group using private or public link.
        Return the chat or None.

        first it removes the domain because it's not important what's
        the matter ins't the url, but instead the
        username (public) or the invite hash (private)

        Private links points to a invite, we must extract the hash
        using ImportChatInviteRequest

        Public links points to the group, we ask the group if we can enter
        using JoinChannelRequest
        """

        logger.info(f'🚀 Attempting to join: {invite_link}')

        clean_link = (
            invite_link.replace('https://t.me/', '')
            .replace('t.me/', '')
            .strip()
        )

        # Check private or public, format link, uses the correct api method
        if clean_link.startswith('+') or clean_link.startswith('joinchat/'):
            invite_hash = clean_link.replace('joinchat/', '')
            invite_hash = invite_hash.replace('+', '').strip()
            logger.debug(f'🔑 Joining private chat with hash: {invite_hash}')

            join_function = partial(
                self.client, ImportChatInviteRequest(invite_hash)
            )

        else:
            username = clean_link.split('/')[0].strip()
            logger.debug(f'📢 Joining public chat with username: {username}')

            join_function = partial(self.client, JoinChannelRequest(username))

        try:
            updates = await join_function()

            if updates.chats:
                new_chat = updates.chats[0]
                logger.info(f'✅ Successfully joined chat: {new_chat.title}')
                return new_chat

        except UserAlreadyParticipantError:
            logger.info('ℹ️ User already in chat. Fetching entity...')
            return await self.client.get_entity(invite_link)

        return None

    async def create_channel(
        self, title: str, description: str = ''
    ) -> Optional[Channel]:
        """
        Creates a Broadcast Channel (Only admins can post).
        INFO: You can't create a group defining a photo you must
        use the clone_metadada
        """
        logger.info(f'📢 Creating new broadcast channel: "{title}"...')
        try:
            # broadcast=True: It's a channel only the admin can talk
            # megagroup=False: Set it to not be a chat group
            result = await self.client(
                CreateChannelRequest(
                    title=title,
                    about=description,
                    broadcast=True,
                    megagroup=False,
                )
            )

            new_channel = result.chats[0]
            logger.info(
                f'✅ Channel created successfully! ID: {new_channel.id}'
            )
            return new_channel

        except Exception as e:
            logger.error(f'❌ Failed to create channel: {e}')
            return None

    async def create_invite_link(
        self, entity: Chat | Channel
    ) -> Optional[str]:
        """
        Generates a permanent invite link for the channel/group.
        """
        try:
            logger.info(f'🔗 Generating invite link for ID {entity.id}...')

            # ExportChatInviteRequest funciona tanto para Canais
            # quanto para Grupos
            invite = await self.client(
                ExportChatInviteRequest(
                    peer=entity,
                    legacy_revoke_permanent=True,
                    expire_date=None,
                    usage_limit=None,
                )
            )

            link = invite.link
            logger.info(f'✅ Invite link created: {link}')
            return link

        except Exception as e:
            logger.warning(f'⚠️ Failed to generate invite link: {e}')
            return None

    async def clone_metadata(self, origin: Chat, destiny: Chat) -> None:
        """
        Clones Title, Description, and Photo independently.
        If one fails, the others still attempt to run.
        """
        logger.info('🎨 Starting Metadata Cloning...')

        # Copying the origin title
        if origin.title != destiny.title:
            try:
                logger.info(f'Updating Title to: {origin.title}')
                await self.client(
                    EditTitleRequest(channel=destiny, title=origin.title)
                )
            except Exception as e:
                logger.warning(f'⚠️ Failed to update Title: {e}')

        logging.info('Destiny group already has the same title as the origin')

        # Copying the origin description
        try:
            # Getting full chat info is required
            full_origin = await self.client(GetFullChannelRequest(origin))

            if description := getattr(full_origin.full_chat, 'about', None):
                logger.info('Updating Description...')
                await self.client(
                    EditChatAboutRequest(peer=destiny, about=description)
                )
        except Exception as e:
            logger.warning(f'⚠️ Failed to update Description: {e}')

        # Copying the photo
        if not getattr(origin, 'photo', None):
            logger.info('ℹ️ Origin has no profile photo.')
            return

        try:
            logger.info('Downloading Profile Photo...')
            photo_bytes = await self.client.download_profile_photo(
                origin, file=bytes
            )

            if not photo_bytes:
                return

            logger.info('Uploading and Setting Profile Photo...')
            uploaded_file = await self.client.upload_file(
                photo_bytes, file_name='profile_photo.jpg'
            )

            await self.client(
                EditPhotoRequest(
                    channel=destiny,
                    photo=InputChatUploadedPhoto(file=uploaded_file),
                )
            )
            logger.info('✅ Photo updated successfully.')

        except Exception as e:
            logger.warning(f'⚠️ Failed to update Photo: {e}')

        logger.info('🏁 Metadata cloning process finished.')

    async def hold_channel(self, channel_entity, bot_usernames: list[str]):
        """
        Add multiple bot users to hold channel, because if you leave the
        channel with 0 members it's automatically deleted, that
        """

        if not bot_usernames:
            logger.warning(
                'Nenhum bot fornecido! O canal será excluído se você sair.'
            )
            return

        try:
            await self.client(
                InviteToChannelRequest(
                    channel=channel_entity, users=bot_usernames
                )
            )

            logger.info(f'Canal protegido por {len(bot_usernames)} bots.')
            await self.client(LeaveChannelRequest(channel_entity))

        except Exception as e:
            logger.error(f'Erro ao segurar canal: {e}')

    async def get_user_groups(self):
        """
        Retrieves ALL open chats (Private, Small Groups, Supergroups, Channels).
        """
        all_chats = []

        # Iterating without limit=None fetches everything until the list ends
        async for dialog in self.client.iter_dialogs():
            all_chats.append({
                'id': dialog.id,
                'name': dialog.name,
                'type': self._get_chat_type(dialog),
            })

        return all_chats

    @staticmethod
    def _get_chat_type(dialog):
        """Helper to identify the type of chat for your frontend."""
        if dialog.is_user:
            return 'User (Private)'
        elif dialog.is_channel:
            # Telethon distinguishes Broadcast Channels vs Megagroups
            return (
                'Broadcast Channel'
                if dialog.entity.broadcast
                else 'Supergroup'
            )
        elif dialog.is_group:
            return 'Small Group'
        return 'Unknown'
