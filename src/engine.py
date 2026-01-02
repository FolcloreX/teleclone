import logging
from typing import Tuple

from telethon import TelegramClient
from telethon.tl.types import MessageService, Chat
from telethon.sessions import StringSession
from src.rate_limit import TokenBucket
from src.pipelines import RestrictPipeline, ForwardPipeline
from src.group_manager import GroupManager
from .settings import settings
from typing import Optional
from slugify import slugify
from .data import clones, accounts

logger = logging.getLogger(__name__)


class CloneEngine(TelegramClient):
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        phone: str,
        session_string: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        """
        We use string session, because we want to manage
        a lot of accounts
        """
        self.download_dir = settings.download_dir
        self.rate_limit = 20
        self.interval = 60.0 / self.rate_limit
        self.bucket = TokenBucket(1, self.rate_limit, self.interval)
        self.session_string = session_string

        """
        The amount of messages being fetched in the Get_History command
        If it's restrict: 1 by one to avoid ReferenceExpiredError
        If no restriction: 50 per time to avoid floodAwaitError
        """

        self.batch_size = None
        self.main_pipeline = None

        # TODO refactor later to an authentication module
        self.profiles_dir = settings.profiles_dir

        # We store to use in the .start later
        self.phone_number = phone
        self.password = password

        super().__init__(
            session=StringSession(self.session_string),
            api_id=api_id,
            api_hash=api_hash,
        )

        # Inicialize the manager with the client already configured
        self.group_manager = GroupManager(self)

    async def _start_log_with_account(self) -> None:
        await self.start(phone=self.phone_number, password=self.password)

        me = await self.get_me()
        full_name = f'{me.first_name} {me.last_name or ""}'.strip()

        logging.info(f'✅ Sucessful start clone instance as: {full_name}')
        username = f'@{me.username}' if me.username else None

        target_path = self.profiles_dir / f'{self.phone_number}.jpg'
        result = await self.download_profile_photo(me, file=target_path)
        image_slug = target_path.name if result else None

        current_session_string = self.session.save()

        # Case it's a new account or the string session has changed
        if current_session_string != self.session_string:
            await accounts.store_account(
                phone_number=self.phone_number,
                api_id=self.api_id,
                api_hash=self.api_hash,
                session_string=current_session_string,
                username=username,
                account_name=full_name,
                image_slug=image_slug,
                # proxy...
            )

            self.session_string = current_session_string

    async def _validate_groups(
        self,
        origin: int | str,
        destiny: Optional[int | str],
    ) -> Tuple[Chat, Chat]:
        """
        Here we cover to possible scenarios:

        1. Final Users: The user are in the origin and destiny groups
        so it's only passing the ids or want to create a destiny group
        to clone to.

        2. Bot pipeline: The user have the invite link of origin
        and the destiny we have to create.
        """

        # Refresh references
        await self.get_dialogs()

        # We check if it's a id a or a invite link
        if str(origin).lstrip('-').isdigit():
            origin_chat = await self.get_entity(origin)
        else:
            origin_chat = await self.group_manager.enter_channel(origin)

        # If no destiny is provided we create one
        if destiny:
            destiny_chat = await self.get_entity(destiny)
        else:
            destiny_chat = await self.group_manager.create_channel(
                origin_chat.title
            )

        logger.info(
            f'Cloning from: {origin_chat.title} -> To: {destiny_chat.title}'
        )

        restrict_pipe = RestrictPipeline(self, self.download_dir)
        forward_pipe = ForwardPipeline(self, fallback=restrict_pipe)
        is_origin_restricted = getattr(origin_chat, 'noforwards', False)

        if is_origin_restricted:
            logger.info('🚫 Restricted Chat: (Fetching 1 by 1)')
            self.batch_size = 1
            self.main_pipeline = restrict_pipe
        else:
            logger.info('✅ Forward Allowed: (Fetching in batches)')
            self.batch_size = 50
            self.main_pipeline = forward_pipe

        return origin_chat, destiny_chat

    async def start_clone(
        self,
        origin: int | str,
        destiny: int | str,
        offset_id: int = 0,
        copy_metadata: bool = False,
    ):

        await self._start_log_with_account()

        # We validate the groups first to see if there's no problem
        origin_chat, destiny_chat = await self._validate_groups(
            origin, destiny
        )

        if copy_metadata:
            await self.group_manager.clone_metadata(origin_chat, destiny_chat)

        logging.debug(
            f'Tracking group with {origin_chat.title} | id: {origin_chat.id}\n'
            f'To {destiny_chat.title} | id: {destiny_chat.id}'
            f'with account which phone_number is: {self.phone_number}'
        )

        track_clone = await clones.create_clone(
            origin_group_id=origin_chat.id,
            destiny_group_id=destiny_chat.id,
            origin_group_title=origin_chat.title,
            phone_number=self.phone_number,
        )

        # Loop Sequencial (Fetch -> Process -> Repeat)
        last_id = offset_id if offset_id else track_clone.offset_id

        while True:
            logger.debug(
                f'Fetching next {self.batch_size}'
                f'messages after ID {last_id}...'
            )

            messages = await self.get_messages(
                origin_chat,
                limit=self.batch_size,
                offset_id=last_id,
                reverse=True,
            )

            if not messages:
                logger.info('No more messages found. Clone finished.')
                await clones.update_clone_progress(
                    clone_id=track_clone.id,
                    last_message_id=last_id,
                    status='completed',
                )
                break

            for message in messages:
                last_id = message.id

                if isinstance(message, MessageService):
                    logger.info(f'Skiping service message: {message.id}')
                    continue

                await self.bucket.wait()

                try:
                    await self.main_pipeline.process(destiny_chat, message)

                except Exception as e:
                    logger.error(
                        f'Failed to process message {message.id}: {e}'
                    )
                    await clones.update_clone_progress(
                        clone_id=track_clone.id,
                        last_processed_id=last_id,
                        status='failed',
                    )
                    raise

            logging.debug(
                f'Stored {last_id} from the origin: {origin_chat.title}'
                f'into the clone_id track {track_clone.id}'
            )

            await clones.update_clone_progress(
                clone_id=track_clone.id,
                last_processed_id=last_id,
                status='running',
            )
