import unittest
from unittest.mock import patch, Mock, MagicMock
import os

# Assuming the class is in bot.helper.mirror_leech_utils.youtube_utils.youtube_upload
# Adjust the import path according to your project structure
from bot.helper.mirror_leech_utils.youtube_utils.youtube_upload import YouTubeUpload
from bot.helper.mirror_leech_utils.status_utils.yt_status import YtStatus # Needed for listener context

class TestYouTubeUpload(unittest.TestCase):

    def setUp(self):
        self.mock_listener = Mock()
        self.mock_listener.name = "test_upload"
        self.mock_listener.is_cancelled = False
        self.mock_listener.user_id = "12345"
        self.mock_listener.up_dest = "" # Default, can be overridden in tests
        self.mock_listener.message = Mock() # Mock the message attribute
        self.mock_listener.message.chat.id = "chat_id" # Mock chat_id for status updates


        # Path for YouTubeUpload instance
        self.test_path = "/test/path"

        # Patch 'user_setting' and 'authorize' as they depend on listener specifics
        # or have external dependencies not relevant for these unit tests if self.service is mocked.
        self.patcher_user_setting = patch.object(YouTubeUpload, 'user_setting')
        self.patcher_authorize = patch.object(YouTubeUpload, 'authorize')

        self.mock_user_setting = self.patcher_user_setting.start()
        self.mock_authorize_service = self.patcher_authorize.start()

        # Instantiate YouTubeUpload AFTER starting the patches for its methods if they are called in __init__
        # (though in this case, user_setting and authorize are not called in __init__)
        self.youtube_upload = YouTubeUpload(listener=self.mock_listener, path=self.test_path)

        # Mock the YouTube API service object
        self.youtube_upload.service = MagicMock()
        self.mock_authorize_service.return_value = self.youtube_upload.service

        # Common mocks for SetInterval, LOGGER, and other utilities if needed
        self.patcher_set_interval = patch('bot.helper.mirror_leech_utils.youtube_utils.youtube_upload.SetInterval')
        self.mock_set_interval = self.patcher_set_interval.start()

        self.patcher_logger = patch('bot.helper.mirror_leech_utils.youtube_utils.youtube_upload.LOGGER')
        self.mock_logger = self.patcher_logger.start()

        # Mock async_to_sync which is used for listener callbacks
        self.patcher_async_to_sync = patch('bot.helper.mirror_leech_utils.youtube_utils.youtube_upload.async_to_sync')
        self.mock_async_to_sync = self.patcher_async_to_sync.start()

        # Mock get_mime_type
        self.patcher_get_mime_type = patch('bot.helper.mirror_leech_utils.youtube_utils.youtube_upload.get_mime_type')
        self.mock_get_mime_type = self.patcher_get_mime_type.start()

        # Mock os.remove
        self.patcher_os_remove = patch('bot.helper.mirror_leech_utils.youtube_utils.youtube_upload.remove')
        self.mock_os_remove = self.patcher_os_remove.start()


    def tearDown(self):
        self.patcher_user_setting.stop()
        self.patcher_authorize.stop()
        self.patcher_set_interval.stop()
        self.patcher_logger.stop()
        self.patcher_async_to_sync.stop()
        self.patcher_get_mime_type.stop()
        self.patcher_os_remove.stop()


    @patch('os.path.isdir', return_value=True)
    @patch('os.listdir')
    @patch('os.path.join', side_effect=lambda *args: "/".join(args))
    @patch('os.path.isfile') # Also mock isfile for items within listdir
    def test_upload_playlist_successful(self, mock_os_isfile_item, mock_os_join, mock_os_listdir, mock_os_isdir):
        self.youtube_upload._path = "/fake/folder"
        mock_os_listdir.return_value = ['video1.mp4', 'video2.mkv', 'notes.txt']

        # Mock isfile for items returned by listdir
        def isfile_side_effect(path):
            if path in ["/fake/folder/video1.mp4", "/fake/folder/video2.mkv", "/fake/folder/notes.txt"]:
                return True
            return False
        mock_os_isfile_item.side_effect = isfile_side_effect

        self.mock_get_mime_type.side_effect = lambda path: "video/mp4" if path.endswith(('.mp4', '.mkv')) else "text/plain"

        # Mock _upload_video internal calls to YouTube API
        mock_video_insert = self.youtube_upload.service.videos().insert
        mock_video_insert().execute.side_effect = [
            {'id': 'vid1', 'kind': 'youtube#video'},
            {'id': 'vid2', 'kind': 'youtube#video'}
        ]
        # Mock MediaFileUpload
        with patch('bot.helper.mirror_leech_utils.youtube_utils.youtube_upload.MediaFileUpload') as mock_media_file_upload:
            mock_media_file_upload.return_value = Mock() # Dummy media object

            # Mock playlist creation
            mock_playlist_insert = self.youtube_upload.service.playlists().insert
            mock_playlist_insert().execute.return_value = {'id': 'pl123', 'kind': 'youtube#playlist'}

            # Mock adding items to playlist
            mock_playlist_item_insert = self.youtube_upload.service.playlistItems().insert
            mock_playlist_item_insert().execute.return_value = {'id': 'pli1', 'kind': 'youtube#playlistItem'}

            self.youtube_upload.upload()

        # Assert _upload_playlist was effectively called (playlist creation was attempted)
        mock_playlist_insert.assert_called_once()
        self.assertEqual(mock_playlist_item_insert.call_count, 2) # Two videos added

        # Assert on_upload_complete was called with correct args
        # self.mock_listener.on_upload_complete.assert_called_once() # This is called via async_to_sync
        self.mock_async_to_sync.assert_any_call(
            self.mock_listener.on_upload_complete,
            'https://www.youtube.com/playlist?list=pl123', # Expected playlist URL
            2, # Total files (videos)
            1, # Total folders (the playlist itself)
            'Playlist' # Mime type
        )
        self.assertEqual(self.youtube_upload.total_files, 2) # Check total_files set in _upload_playlist

    @patch('os.path.isdir', return_value=True)
    @patch('os.listdir', return_value=[]) # Empty folder
    def test_upload_folder_empty(self, mock_os_listdir, mock_os_isdir):
        self.youtube_upload._path = "/fake/empty_folder"
        self.youtube_upload.upload()

        # self.mock_listener.on_upload_error.assert_called_once() # Called via async_to_sync
        self.mock_async_to_sync.assert_any_call(
            self.mock_listener.on_upload_error,
            "No videos found in the folder to upload to playlist."
        )

    @patch('os.path.isdir', return_value=True)
    @patch('os.listdir', return_value=['notes.txt', 'image.jpg'])
    @patch('os.path.join', side_effect=lambda *args: "/".join(args))
    @patch('os.path.isfile', return_value=True) # All items are files
    def test_upload_folder_no_video_files(self, mock_os_isfile_item, mock_os_join, mock_os_listdir, mock_os_isdir):
        self.youtube_upload._path = "/fake/no_videos_folder"
        self.mock_get_mime_type.return_value = "text/plain" # All files are non-video

        self.youtube_upload.upload()

        # self.mock_listener.on_upload_error.assert_called_once() # Called via async_to_sync
        self.mock_async_to_sync.assert_any_call(
            self.mock_listener.on_upload_error,
            "No videos found in the folder to upload to playlist."
        )

    @patch('os.path.isfile', return_value=True) # Path is a file
    @patch('os.path.isdir', return_value=False) # Path is not a directory
    def test_upload_single_video_file_successful(self, mock_os_isdir, mock_os_isfile):
        self.youtube_upload._path = "/fake/video.mp4"
        self.mock_get_mime_type.return_value = "video/mp4"

        # Mock the _upload_video method itself for this test to simplify
        with patch.object(self.youtube_upload, '_upload_video', return_value="https://www.youtube.com/watch?v=vid123") as mock_internal_upload_video:
            self.youtube_upload.upload()

            mock_internal_upload_video.assert_called_once_with("/fake/video.mp4", self.mock_listener.name, "video/mp4")

        # self.mock_listener.on_upload_complete.assert_called_once() # Called via async_to_sync
        self.mock_async_to_sync.assert_any_call(
            self.mock_listener.on_upload_complete,
            'https://www.youtube.com/watch?v=vid123',
            1, # Total files
            0, # Total folders
            'Video' # Mime type
        )

if __name__ == '__main__':
    unittest.main()
