import os
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from telethon import TelegramClient
from telethon.tl.types import Message, Chat
from time import time
from typing import Callable
from tqdm import tqdm
import filetype
from typing import Optional

logger = logging.getLogger(__name__)


class PipelineStrategy(ABC):
    @abstractmethod
    async def process(
        self,
        destiny_chat: Chat,
        message: Message,
        reply_to: int | None = None,
    ):
        pass


class RestrictPipeline(PipelineStrategy):
    """
    For restrict content we:
    1. Download the midia locally, saving the text in a variable
    2. Uploads the midia to the destiny group, with the saved text
    3. Deletes the midia that was download locally.
    """

    def __init__(self, client: TelegramClient, download_dir: Path):
        self.client = client
        self.download_dir = download_dir

    @staticmethod
    def create_progress_callback(desc: str) -> Callable:
        """
        Speed formula:
        internet speed = receive_bytes / total_bytes
        """

        start_time = time()
        progress_bar = tqdm(
            total=100, unit='%', desc=desc, unit_scale=True, leave=True
        )

        def wrapped_progress_callback(received_bytes, total_bytes):
            progress = (received_bytes / total_bytes) * 100
            progress_bar.n = progress
            progress_bar.refresh()

            elapsed = time() - start_time
            speed = f'{(received_bytes / elapsed) / 1024 / 1024:.2f}'
            progress_bar.set_postfix({'Speed': speed + ' MB/s'})

        return wrapped_progress_callback

    @staticmethod
    def correct_extension(dl_path: Path, message: Message) -> Optional[Path]:
        logger.debug(f'Detecting extension for {dl_path}...')
        kind = filetype.guess(str(dl_path))

        if kind:
            new_path = dl_path.with_suffix(f'.{kind.extension}')
            os.rename(dl_path, new_path)
            logger.debug(f'Extension fixed: {dl_path.suffix}')
            return new_path
        else:
            logger.warning(
                f'Could not detect extension for message {message.id}'
            )
            return None

    async def process(
        self,
        destiny_chat: Chat,
        message: Message,
        reply_to: int | None = None,
    ):

        if not message.media:
            await self._copy_text(destiny_chat, message, reply_to)
            return

        await self._process_media(destiny_chat, message, reply_to)

    async def _copy_text(
        self, destiny_chat: Chat, message: Message, reply_to: int | None = None
    ):
        text = message.text or ''
        if message.buttons:
            for row in message.buttons:
                for btn in row:
                    if hasattr(btn, 'url') and btn.url:
                        text += f'\n\n[Acessar]({btn.url})'

        await self.client.send_message(destiny_chat, text, reply_to=reply_to)

    async def _process_media(
        self, destiny_chat: Chat, message: Message, reply_to: int | None = None
    ):
        # Define a temporary file name in case the original doesn't exist
        original_name = (
            message.file.name
            if (message.file and message.file.name)
            else f'file_{message.id}'
        )

        file_path = self.download_dir / f'{message.id}_{original_name}'

        try:
            logger.debug(f'Downloading media {message.id}...')

            downloaded_file = await self.client.download_media(
                message=message,
                file=str(file_path),
                progress_callback=self.create_progress_callback(
                    f'Downloading message_id: {message.id}'
                ),
            )

            if not downloaded_file:
                logger.error('Download failed of message_id: {message.id}')
                return

            dl_path = Path(downloaded_file)

            # We verify if the the file has an extension otherwise we try
            # To infer the extension based on the file content
            if not dl_path.suffix:
                dl_path = self.correct_extension(dl_path)

            logger.debug(f'Uploading media {message.id}...')
            await self.client.send_file(
                destiny_chat,
                file=str(dl_path),
                caption=message.text or message.caption,
                reply_to=reply_to,
                progress_callback=self.create_progress_callback(
                    f'Uploading: {message.id}'
                ),
            )

        except Exception as e:
            logger.error(f'Error processing media {message.id}: {e}')

        finally:
            if dl_path and os.path.exists(dl_path):
                try:
                    os.remove(dl_path)
                    logger.debug(f'Deleted temporary file: {dl_path}')
                except Exception as e:
                    logger.error(f'Failed to delete {dl_path}: {e}')


class ForwardPipeline(PipelineStrategy):
    """
    Pipeline for unsretricted content:
    Only when the group has no restriction, but messages can be restricted
    In that case we use the restricted RestrictPipeline.
    """

    def __init__(self, client: TelegramClient, fallback: RestrictPipeline):
        self.client = client
        self.fallback = fallback

    async def process(
        self,
        destiny_chat: int | str,
        message: Message,
        reply_to: int | None = None,
    ):
        """
        Not only groups but message as well can be restrict as well
        if it's a text message we copy the content send it.
        if it's a media message we send to the fallback that will download.
        """

        if message.noforwards:
            logger.info(f'Restricted message: {message.id}')
            await self.fallback.process(destiny_chat, message, reply_to)
            return

        await self.client.forward_messages(
            entity=destiny_chat, messages=message, from_peer=message.chat_id
        )

        logger.info(f'Forward message_id: {message.id}')
