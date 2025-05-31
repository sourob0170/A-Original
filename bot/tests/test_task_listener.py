import unittest
from unittest.mock import (  # Ensure AsyncMock is imported
    AsyncMock,
    Mock,
    patch,
)

from bot.core.config_manager import Config

# Adjust imports based on your project structure
from bot.helper.listeners.task_listener import TaskListener

# Mock task_dict and other global/module-level variables if they are accessed
# The listener tries to update task_dict, so it needs to be mockable.
MOCK_TASK_DICT = {}


class MockDownload:
    def __init__(self, name="test_download", gid="test_gid"):
        self._name = name
        self._gid = gid

    def name(self):
        return self._name

    def gid(self):
        return self._gid


class TestTaskListener(
    unittest.IsolatedAsyncioTestCase
):  # Use IsolatedAsyncioTestCase for async methods
    def common_mocks(self, listener_instance):
        # Mock attributes and methods that are accessed in on_download_complete
        listener_instance.mid = "test_mid"
        listener_instance.name = "test_task_name"
        listener_instance.dir = "/test_dir/"
        listener_instance.is_torrent = False
        listener_instance.is_qbit = False
        listener_instance.is_file = (
            True  # Assume it's a file by default after processing
        )
        listener_instance.seed = False
        listener_instance.excluded_extensions = []
        listener_instance.join = False
        listener_instance.extract = False
        listener_instance.watermark = False
        listener_instance.metadata = False
        listener_instance.ffmpeg_cmds = []
        listener_instance.name_sub = False
        listener_instance.screen_shots = False
        listener_instance.convert_audio = False
        listener_instance.convert_video = False
        listener_instance.sample_video = False
        listener_instance.compress = False
        listener_instance.up_dir = listener_instance.dir  # if not seeding
        listener_instance.message = Mock()
        listener_instance.message.chat.id = "test_chat_id"
        listener_instance.user_id = "test_user_id"
        listener_instance.tag = "@test_user"
        listener_instance.is_super_chat = (
            False  # For INCOMPLETE_TASK_NOTIFIER related logic
        )
        listener_instance.folder_name = ""  # For multi-link logic
        listener_instance.same_dir = {}  # For multi-link logic
        listener_instance.subproc = None  # For process cancellation logic
        listener_instance.is_cancelled = False

        # Mock methods called within on_download_complete that are not the focus of these tests
        listener_instance.proceed_extract = AsyncMock(
            return_value=f"{listener_instance.dir}{listener_instance.name}"
        )
        listener_instance.proceed_watermark = AsyncMock(
            return_value=f"{listener_instance.dir}{listener_instance.name}"
        )
        listener_instance.proceed_metadata = AsyncMock(
            return_value=f"{listener_instance.dir}{listener_instance.name}"
        )
        listener_instance.proceed_ffmpeg = AsyncMock(
            return_value=f"{listener_instance.dir}{listener_instance.name}"
        )
        listener_instance.substitute = AsyncMock(
            return_value=f"{listener_instance.dir}{listener_instance.name}"
        )
        listener_instance.remove_www_prefix = AsyncMock(
            return_value=f"{listener_instance.dir}{listener_instance.name}"
        )
        listener_instance.generate_screenshots = AsyncMock(
            return_value=f"{listener_instance.dir}{listener_instance.name}"
        )
        listener_instance.convert_media = AsyncMock(
            return_value=f"{listener_instance.dir}{listener_instance.name}"
        )
        listener_instance.generate_sample_video = AsyncMock(
            return_value=f"{listener_instance.dir}{listener_instance.name}"
        )
        listener_instance.proceed_compress = AsyncMock(
            return_value=f"{listener_instance.dir}{listener_instance.name}"
        )
        listener_instance.proceed_split = AsyncMock()
        listener_instance.on_upload_error = (
            AsyncMock()
        )  # To check if it's called on uploader config error

    async def create_listener_instance(self):
        # TaskListener.__init__ is simple, so we can call it.
        # If it were complex, we'd mock more parts of it.
        listener = TaskListener()
        # Mock essential attributes that would normally be set by Mirror/Leech class or arg_parser
        listener.uploader = ""  # This will be overridden by tests or DEFAULT_UPLOAD
        listener.up_dest = ""
        listener.is_leech = False
        listener.size = 1000  # Mock size, as it's used in on_upload_complete
        self.common_mocks(listener)
        return listener

    # Patch critical dependencies for on_download_complete
    @patch(
        "bot.helper.listeners.task_listener.aiopath.exists",
        new_callable=AsyncMock,
        return_value=True,
    )
    @patch(
        "bot.helper.listeners.task_listener.get_path_size",
        new_callable=AsyncMock,
        return_value=1000,
    )
    @patch(
        "bot.helper.listeners.task_listener.aiopath.isfile",
        new_callable=AsyncMock,
        return_value=True,
    )
    @patch(
        "bot.helper.listeners.task_listener.listdir",
        new_callable=AsyncMock,
        return_value=["test_task_name"],
    )
    @patch(
        "bot.helper.listeners.task_listener.remove_excluded_files",
        new_callable=AsyncMock,
    )
    @patch(
        "bot.helper.listeners.task_listener.update_status_message",
        new_callable=AsyncMock,
    )
    @patch(
        "bot.helper.listeners.task_listener.check_running_tasks",
        new_callable=AsyncMock,
        return_value=(False, Mock(wait=AsyncMock())),
    )
    @patch(
        "bot.helper.listeners.task_listener.start_from_queued",
        new_callable=AsyncMock,
    )
    @patch(
        "bot.helper.listeners.task_listener.task_dict", MOCK_TASK_DICT
    )  # Patch task_dict
    async def run_on_download_complete_with_mocks(
        self,
        listener,
        mock_start_queued,
        mock_check_running,
        mock_update_status,
        mock_remove_excluded,
        mock_listdir,
        mock_isfile,
        mock_get_path_size,
        mock_exists,
    ):
        # Store a mock download object in the task_dict for the listener to retrieve
        MOCK_TASK_DICT[listener.mid] = MockDownload(
            name=listener.name, gid=listener.mid
        )
        await listener.on_download_complete()
        del MOCK_TASK_DICT[listener.mid]  # Clean up

    @patch("bot.helper.listeners.task_listener.YouTubeUpload")
    async def test_uploader_yt_selected(self, MockYouTubeUpload):
        listener = await self.create_listener_instance()
        listener.uploader = "yt"

        await self.run_on_download_complete_with_mocks(listener)

        MockYouTubeUpload.assert_called_once_with(
            listener, f"{listener.dir}{listener.name}"
        )
        MockYouTubeUpload.return_value.upload.assert_called_once()

    @patch("bot.helper.listeners.task_listener.is_gdrive_id", return_value=True)
    @patch("bot.helper.listeners.task_listener.GoogleDriveUpload")
    async def test_uploader_gd_selected_valid_path(
        self, MockGoogleDriveUpload, mock_is_gdrive_id
    ):
        listener = await self.create_listener_instance()
        listener.uploader = "gd"
        listener.up_dest = "valid_gdrive_id"

        await self.run_on_download_complete_with_mocks(listener)

        MockGoogleDriveUpload.assert_called_once_with(
            listener, f"{listener.dir}{listener.name}"
        )
        MockGoogleDriveUpload.return_value.upload.assert_called_once()

    @patch("bot.helper.listeners.task_listener.is_gdrive_id", return_value=False)
    @patch("bot.helper.listeners.task_listener.GoogleDriveUpload")
    async def test_uploader_gd_selected_invalid_path(
        self, MockGoogleDriveUpload, mock_is_gdrive_id
    ):
        listener = await self.create_listener_instance()
        listener.uploader = "gd"
        listener.up_dest = "invalid_gdrive_id_or_empty"  # up_dest is not a gdrive_id

        await self.run_on_download_complete_with_mocks(listener)

        listener.on_upload_error.assert_called_once_with(
            f"Google Drive ID not provided or invalid in -up / UPSTREAM_REPO for -ul gd. Path: {listener.up_dest}"
        )
        MockGoogleDriveUpload.assert_not_called()

    @patch("bot.helper.listeners.task_listener.RcloneTransferHelper")
    async def test_uploader_rc_selected_valid_path(self, MockRcloneTransferHelper):
        listener = await self.create_listener_instance()
        listener.uploader = "rc"
        listener.up_dest = "myremote:myfolder"

        await self.run_on_download_complete_with_mocks(listener)

        MockRcloneTransferHelper.assert_called_once_with(listener)
        MockRcloneTransferHelper.return_value.upload.assert_called_once_with(
            f"{listener.dir}{listener.name}"
        )

    @patch("bot.helper.listeners.task_listener.RcloneTransferHelper")
    async def test_uploader_rc_selected_no_path(self, MockRcloneTransferHelper):
        listener = await self.create_listener_instance()
        listener.uploader = "rc"
        listener.up_dest = ""  # Rclone path not provided

        await self.run_on_download_complete_with_mocks(listener)

        listener.on_upload_error.assert_called_once_with(
            "Rclone destination not provided in -up / UPSTREAM_REPO for -ul rc."
        )
        MockRcloneTransferHelper.assert_not_called()

    @patch("bot.helper.listeners.task_listener.YouTubeUpload")
    async def test_default_uploader_yt(self, MockYouTubeUpload):
        with patch.object(Config, "DEFAULT_UPLOAD", "yt"):
            listener = await self.create_listener_instance()
            listener.uploader = ""  # User did not specify -ul

            await self.run_on_download_complete_with_mocks(listener)

            MockYouTubeUpload.assert_called_once_with(
                listener, f"{listener.dir}{listener.name}"
            )
            MockYouTubeUpload.return_value.upload.assert_called_once()

    @patch("bot.helper.listeners.task_listener.is_gdrive_id", return_value=True)
    @patch("bot.helper.listeners.task_listener.GoogleDriveUpload")
    async def test_fallback_gdrive_from_up_dest(
        self, MockGoogleDriveUpload, mock_is_gdrive_id
    ):
        with patch.object(Config, "DEFAULT_UPLOAD", ""):  # No default uploader
            listener = await self.create_listener_instance()
            listener.uploader = ""  # No -ul
            listener.up_dest = "valid_gdrive_id"  # -up is a GDrive ID

            await self.run_on_download_complete_with_mocks(listener)

            MockGoogleDriveUpload.assert_called_once_with(
                listener, f"{listener.dir}{listener.name}"
            )
            MockGoogleDriveUpload.return_value.upload.assert_called_once()

    @patch("bot.helper.listeners.task_listener.RcloneTransferHelper")
    async def test_fallback_rclone_from_up_dest(self, MockRcloneTransferHelper):
        with patch.object(Config, "DEFAULT_UPLOAD", ""):  # No default uploader
            with patch(
                "bot.helper.listeners.task_listener.is_gdrive_id", return_value=False
            ):  # -up is not GDrive
                listener = await self.create_listener_instance()
                listener.uploader = ""  # No -ul
                listener.up_dest = "myremote:path"  # -up is an rclone path

                await self.run_on_download_complete_with_mocks(listener)

                MockRcloneTransferHelper.assert_called_once_with(listener)
                MockRcloneTransferHelper.return_value.upload.assert_called_once_with(
                    f"{listener.dir}{listener.name}"
                )

    @patch("bot.helper.listeners.task_listener.TelegramUploader")
    async def test_fallback_leech(self, MockTelegramUploader):
        with patch.object(Config, "DEFAULT_UPLOAD", ""):  # No default uploader
            listener = await self.create_listener_instance()
            listener.uploader = ""  # No -ul
            listener.is_leech = True  # is_leech is true
            listener.up_dest = ""  # No specific -up destination

            await self.run_on_download_complete_with_mocks(listener)

            MockTelegramUploader.assert_called_once_with(
                listener, listener.dir
            )  # Leech uploads from base dir
            MockTelegramUploader.return_value.upload.assert_called_once()

    @patch("bot.helper.listeners.task_listener.RcloneTransferHelper")
    async def test_true_default_rclone_no_args(self, MockRcloneTransferHelper):
        # Test case where -ul is empty, DEFAULT_UPLOAD is empty, not leech, and -up is empty
        with patch.object(Config, "DEFAULT_UPLOAD", ""):  # No default uploader
            with patch(
                "bot.helper.listeners.task_listener.is_gdrive_id", return_value=False
            ):  # -up is not GDrive
                listener = await self.create_listener_instance()
                listener.uploader = ""
                listener.is_leech = False
                listener.up_dest = ""  # No -up destination

                await self.run_on_download_complete_with_mocks(listener)

                MockRcloneTransferHelper.assert_called_once_with(listener)
                MockRcloneTransferHelper.return_value.upload.assert_called_once_with(
                    f"{listener.dir}{listener.name}"
                )


# AsyncMock is imported from unittest.mock, so local helper is not needed.

if __name__ == "__main__":
    unittest.main()

# To run these tests:
# Ensure you are in the root directory of the bot.
# python -m unittest bot.tests.test_task_listener
# or (if your test runner supports discovery)
# python -m unittest discover bot/tests
