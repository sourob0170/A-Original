import gc
import math
from asyncio import create_subprocess_exec, sleep, wait_for
from asyncio.subprocess import PIPE
from os import path as ospath
from os import readlink, walk
from re import IGNORECASE, escape
from re import search as re_search
from re import split as re_split

from aioshutil import rmtree as aiormtree
from magic import Magic

from bot import DOWNLOAD_DIR, LOGGER
from bot.core.torrent_manager import TorrentManager
from bot.helper.ext_utils.aiofiles_compat import listdir, remove, rmdir, symlink
from bot.helper.ext_utils.aiofiles_compat import makedirs as aiomakedirs
from bot.helper.ext_utils.aiofiles_compat import path as aiopath
from bot.helper.ext_utils.aiofiles_compat import readlink as aioreadlink

from .bot_utils import cmd_exec, sync_to_async
from .exceptions import NotSupportedExtractionArchive
from .gc_utils import smart_garbage_collection

ARCH_EXT = [
    ".tar.bz2",
    ".tar.gz",
    ".bz2",
    ".gz",
    ".tar.xz",
    ".tar",
    ".tbz2",
    ".tgz",
    ".lzma2",
    ".zip",
    ".7z",
    ".z",
    ".rar",
    ".iso",
    ".wim",
    ".cab",
    ".apm",
    ".arj",
    ".chm",
    ".cpio",
    ".cramfs",
    ".deb",
    ".dmg",
    ".fat",
    ".hfs",
    ".lzh",
    ".lzma",
    ".mbr",
    ".msi",
    ".mslz",
    ".nsis",
    ".ntfs",
    ".rpm",
    ".squashfs",
    ".udf",
    ".vhd",
    ".xar",
    ".zst",
    ".zstd",
    ".cbz",
    ".apfs",
    ".ar",
    ".qcow",
    ".macho",
    ".exe",
    ".dll",
    ".sys",
    ".pmd",
    ".swf",
    ".swfc",
    ".simg",
    ".vdi",
    ".vhdx",
    ".vmdk",
    ".gzip",
    ".lzma86",
    ".sha256",
    ".sha512",
    ".sha224",
    ".sha384",
    ".sha1",
    ".md5",
    ".crc32",
    ".crc64",
]

FIRST_SPLIT_REGEX = (
    r"\.part0*1\.rar$|\.7z\.0*1$|\.zip\.0*1$|^(?!.*\.part\d+\.rar$).*\.rar$"
)

SPLIT_REGEX = r"\.r\d+$|\.7z\.\d+$|\.z\d+$|\.zip\.\d+$|\.part\d+\.rar$"


def is_first_archive_split(file):
    return bool(re_search(FIRST_SPLIT_REGEX, file.lower(), IGNORECASE))


def is_archive(file):
    return file.strip().lower().endswith(tuple(ARCH_EXT))


def is_archive_split(file):
    return bool(re_search(SPLIT_REGEX, file.lower(), IGNORECASE))


async def clean_target(path):
    if await aiopath.exists(path):
        LOGGER.info(f"Cleaning Target: {path}")
        try:
            if await aiopath.isdir(path):
                await aiormtree(path, ignore_errors=True)
            else:
                await remove(path)
        except Exception as e:
            LOGGER.error(str(e))


async def clean_download(path):
    if await aiopath.exists(path):
        LOGGER.info(f"Cleaning Download: {path}")
        try:
            await aiormtree(path, ignore_errors=True)
        except Exception as e:
            LOGGER.error(str(e))


async def clean_all():
    await TorrentManager.remove_all()
    try:
        LOGGER.info("Cleaning Download Directory")
        await aiormtree(DOWNLOAD_DIR, ignore_errors=True)
    except Exception as e:
        LOGGER.error(f"Error cleaning download directory: {e}")
        # Fallback to using rm command if aiormtree fails
        LOGGER.info("Falling back to rm command")
        await (await create_subprocess_exec("rm", "-rf", DOWNLOAD_DIR)).wait()

    # Ensure the download directory exists
    await aiomakedirs(DOWNLOAD_DIR, exist_ok=True)

    # Force garbage collection after cleaning
    smart_garbage_collection(aggressive=True)


async def clean_unwanted(opath):
    LOGGER.info(f"Cleaning unwanted files/folders: {opath}")
    for dirpath, _, files in await sync_to_async(walk, opath, topdown=False):
        for filee in files:
            f_path = ospath.join(dirpath, filee)
            if filee.strip().endswith(".parts") and filee.startswith("."):
                await remove(f_path)
        if dirpath.strip().endswith(".unwanted"):
            await aiormtree(dirpath, ignore_errors=True)
    for dirpath, _, __ in await sync_to_async(walk, opath, topdown=False):
        if not await listdir(dirpath):
            await rmdir(dirpath)


async def get_path_size(opath):
    total_size = 0
    if await aiopath.isfile(opath):
        if await aiopath.islink(opath):
            opath = await aioreadlink(opath)
        return await aiopath.getsize(opath)
    for root, _, files in await sync_to_async(walk, opath):
        for f in files:
            abs_path = ospath.join(root, f)
            if await aiopath.islink(abs_path):
                abs_path = await aioreadlink(abs_path)
            total_size += await aiopath.getsize(abs_path)
    return total_size


async def count_files_and_folders(opath):
    total_files = 0
    total_folders = 0
    for _, dirs, files in await sync_to_async(walk, opath):
        total_files += len(files)
        total_folders += len(dirs)
    return total_folders, total_files


def get_base_name(orig_path):
    extension = next(
        (ext for ext in ARCH_EXT if orig_path.strip().lower().endswith(ext)),
        "",
    )
    if extension != "":
        return re_split(f"{extension}$", orig_path, maxsplit=1, flags=IGNORECASE)[0]
    raise NotSupportedExtractionArchive("File format not supported for extraction")


async def create_recursive_symlink(source, destination):
    if ospath.isdir(source):
        await aiomakedirs(destination, exist_ok=True)
        for item in await listdir(source):
            item_source = ospath.join(source, item)
            item_dest = ospath.join(destination, item)
            await create_recursive_symlink(item_source, item_dest)
    elif ospath.isfile(source):
        try:
            await symlink(source, destination)
        except FileExistsError:
            LOGGER.error(f"Shortcut already exists: {destination}")
        except Exception as e:
            LOGGER.error(f"Error creating shortcut for {source}: {e}")


async def get_mime_type(file_path):
    if ospath.islink(file_path):
        file_path = readlink(file_path)
    try:
        mime = Magic(mime=True)
        mime_type = mime.from_file(file_path)
        return mime_type or "text/plain"
    except Exception as e:
        LOGGER.error(f"Error getting mime type for {file_path}: {e}")
        return "text/plain"
    finally:
        # Explicitly delete the Magic object to free resources
        del mime
        # Force garbage collection after handling large files
        if ospath.getsize(file_path) > 100 * 1024 * 1024:  # 100MB
            smart_garbage_collection(aggressive=False)


# Non-async version for backward compatibility
def get_mime_type_sync(file_path):
    if ospath.islink(file_path):
        file_path = readlink(file_path)
    mime = None
    try:
        mime = Magic(mime=True)
        mime_type = mime.from_file(file_path)
        return mime_type or "text/plain"
    except Exception as e:
        LOGGER.error(f"Error getting mime type for {file_path}: {e}")
        return "text/plain"
    finally:
        # Explicitly delete the Magic object to free resources
        if mime:
            del mime
        # Optimized garbage collection only for very large files
        if (
            ospath.getsize(file_path) > 500 * 1024 * 1024
        ):  # Increased threshold to 500MB
            gc.collect(0)  # Only collect generation 0 for better performance


async def remove_excluded_files(fpath, ee):
    for root, _, files in await sync_to_async(walk, fpath):
        for f in files:
            if f.strip().lower().endswith(tuple(ee)):
                await remove(ospath.join(root, f))


async def join_files(opath):
    files = await listdir(opath)
    results = []
    exists = False
    for file_ in files:
        if re_search(r"\.0+2$", file_) and await get_mime_type(
            f"{opath}/{file_}"
        ) not in ["application/x-7z-compressed", "application/zip"]:
            exists = True
            final_name = file_.rsplit(".", 1)[0]
            fpath = f"{opath}/{final_name}"

            # Execute the command
            cmd = f'cat "{fpath}."* > "{fpath}"'
            _, stderr, code = await cmd_exec(
                cmd,
                shell=True,
            )
            if code != 0:
                LOGGER.error(f"Failed to join {final_name}, stderr: {stderr}")
                if await aiopath.isfile(fpath):
                    await remove(fpath)
            else:
                results.append(final_name)

    if not exists:
        pass
    elif results:
        LOGGER.info("Join Completed!")
        for res in results:
            for file_ in files:
                if re_search(rf"{escape(res)}\.0[0-9]+$", file_):
                    await remove(f"{opath}/{file_}")


async def split_file(f_path, split_size, listener):
    """
    Split a file into multiple parts using the Linux split command.

    Args:
        f_path: Path to the file to split
        split_size: Size of each split in bytes
        listener: Listener object for tracking progress and cancellation

    Returns:
        bool: True if splitting was successful, False otherwise
    """
    out_path = f"{f_path}."
    if listener.is_cancelled:
        return False

    # Get file size for logging
    try:
        file_size = await aiopath.getsize(f_path)
        file_size_gb = file_size / (1024 * 1024 * 1024)
        parts = math.ceil(file_size / split_size)

        # Log detailed information about the splitting operation
        LOGGER.info(f"Splitting file: {f_path}")
        LOGGER.info(f"File size: {file_size_gb:.2f} GiB")
        LOGGER.info(f"Split size: {split_size / (1024 * 1024 * 1024):.2f} GiB")
        LOGGER.info(f"Expected parts: {parts}")

        # Add a safety check - if split size is too close to Telegram's limit, reduce it further
        # This is an additional safety measure beyond what's in get_user_split_size
        from bot.core.aeon_client import TgClient

        # For non-premium accounts, Telegram's limit is 2GB
        telegram_limit = (
            2000 * 1024 * 1024
        )  # 2000 MiB (slightly less than 2 GiB for safety)

        # If user is premium, use premium limit (4GB) but still with safety margin
        if TgClient.IS_PREMIUM_USER:
            telegram_limit = (
                4000 * 1024 * 1024
            )  # 4000 MiB (slightly less than 4 GiB for safety)

        # Add a larger safety margin to ensure we're well under the limit
        safety_margin = 50 * 1024 * 1024  # 50 MiB safety margin

        # Ensure split size is always below Telegram's limit with safety margin
        if split_size > (telegram_limit - safety_margin):
            split_size = telegram_limit - safety_margin
            LOGGER.info(
                f"Adjusted split size to {split_size / (1024 * 1024 * 1024):.2f} GiB for extra safety"
            )
    except Exception as e:
        LOGGER.error(f"Error calculating file size: {e}")
        # Continue with the split operation anyway

    # Create the command
    # Ensure split size is in bytes and is an integer
    split_size_bytes = int(split_size)

    # For extra safety, ensure split size is always below Telegram's limit
    # For non-premium accounts, Telegram's limit is 2GB
    telegram_limit = (
        2000 * 1024 * 1024
    )  # 2000 MiB (slightly less than 2 GiB for safety)

    # If user is premium, use premium limit (4GB) but still with safety margin
    if TgClient.IS_PREMIUM_USER:
        telegram_limit = (
            4000 * 1024 * 1024
        )  # 4000 MiB (slightly less than 4 GiB for safety)

    # Add a larger safety margin to ensure we're well under the limit
    safety_margin = 50 * 1024 * 1024  # 50 MiB safety margin

    # Final check to ensure split size is safe
    if split_size_bytes > (telegram_limit - safety_margin):
        split_size_bytes = telegram_limit - safety_margin
        LOGGER.info(
            f"Final adjustment: split size set to {split_size_bytes / (1024 * 1024 * 1024):.2f} GiB"
        )

    cmd = [
        "split",
        "--numeric-suffixes=1",
        "--suffix-length=3",
        f"--bytes={split_size_bytes}",
        f_path,
        out_path,
    ]

    # Execute the command
    try:
        listener.subproc = await create_subprocess_exec(
            *cmd,
            stderr=PIPE,
        )

        _, stderr = await listener.subproc.communicate()
        code = listener.subproc.returncode

        if listener.is_cancelled:
            return False
        if code == -9:
            listener.is_cancelled = True
            return False
        if code != 0:
            try:
                stderr = stderr.decode().strip()
            except Exception:
                stderr = "Unable to decode the error!"
            LOGGER.error(f"Split error: {stderr}. File: {f_path}")
            return False

        # Verify the split was successful by checking if at least one split file exists
        import glob

        split_pattern = f"{out_path}*"
        split_files = glob.glob(split_pattern)

        if not split_files:
            LOGGER.error(
                f"Split command completed but no split files were created: {f_path}"
            )
            return False

        # Check the size of each split file to ensure none exceed Telegram's limit
        oversized_files = []
        for split_file in split_files:
            try:
                split_file_size = await aiopath.getsize(split_file)
                split_size_gb = split_file_size / (1024 * 1024 * 1024)

                # For non-premium accounts, Telegram's limit is 2GB
                telegram_limit = (
                    2000 * 1024 * 1024
                )  # 2000 MiB (slightly less than 2 GiB for safety)

                # If user is premium, use premium limit (4GB) but still with safety margin
                if TgClient.IS_PREMIUM_USER:
                    telegram_limit = (
                        4000 * 1024 * 1024
                    )  # 4000 MiB (slightly less than 4 GiB for safety)

                if split_file_size > telegram_limit:
                    LOGGER.error(
                        f"Split file {split_file} is {split_size_gb:.2f} GiB, which exceeds "
                        f"Telegram's {telegram_limit / (1024 * 1024 * 1024):.2f} GiB limit!"
                    )
                    oversized_files.append(split_file)
            except Exception as e:
                LOGGER.error(f"Error checking split file size: {e}")

        # If we found oversized files, we need to re-split them with a smaller split size
        if oversized_files:
            LOGGER.warning(
                f"Found {len(oversized_files)} oversized files that need to be re-split"
            )

            # Try to re-split with a smaller size if there are oversized files
            # We don't return False here because we want to continue with the upload
            # The upload will fail for these files, but other files might still work

            # Log a clear warning for the user
            LOGGER.warning(
                "Some split files are still too large for Telegram. "
                "Consider using a smaller split size in your command with the -s parameter."
            )

        LOGGER.info(f"Successfully split {f_path} into {len(split_files)} parts")
        return True
    except Exception as e:
        LOGGER.error(f"Error during file splitting: {e}")
        return False


class SevenZ:
    def __init__(self, listener):
        self._listener = listener
        self._processed_bytes = 0
        self._percentage = "0%"

    @property
    def processed_bytes(self):
        return self._processed_bytes

    @property
    def progress(self):
        return self._percentage

    async def _sevenz_progress(self):
        pattern = r"(\d+)\s+bytes|Total Physical Size\s*=\s*(\d+)"
        while not (
            self._listener.subproc.returncode is not None
            or self._listener.is_cancelled
            or self._listener.subproc.stdout.at_eof()
        ):
            try:
                line = await wait_for(self._listener.subproc.stdout.readline(), 2)
            except Exception:
                break
            line = line.decode().strip()
            if match := re_search(pattern, line):
                self._listener.subsize = int(match[1] or match[2])
            await sleep(0.05)
        s = b""
        while not (
            self._listener.is_cancelled
            or self._listener.subproc.returncode is not None
            or self._listener.subproc.stdout.at_eof()
        ):
            try:
                char = await wait_for(self._listener.subproc.stdout.read(1), 60)
            except Exception:
                break
            if not char:
                break
            s += char
            if char == b"%":
                try:
                    self._percentage = s.decode().rsplit(" ", 1)[-1].strip()
                    self._processed_bytes = (
                        int(self._percentage.strip("%")) / 100
                    ) * self._listener.subsize
                except Exception:
                    self._processed_bytes = 0
                    self._percentage = "0%"
                s = b""
            await sleep(0.05)

        self._processed_bytes = 0
        self._percentage = "0%"

    async def extract(self, f_path, t_path, pswd):
        cmd = [
            "7z",
            "x",
            f"-p{pswd}",
            f_path,
            f"-o{t_path}",
            "-aot",
            "-xr!@PaxHeader",
            "-bsp1",
            "-bse1",
            "-bb3",
        ]
        if not pswd:
            del cmd[2]
        if self._listener.is_cancelled:
            return False

        # Execute the command
        self._listener.subproc = await create_subprocess_exec(
            *cmd,
            stdout=PIPE,
            stderr=PIPE,
        )
        await self._sevenz_progress()
        _, stderr = await self._listener.subproc.communicate()
        code = self._listener.subproc.returncode

        if self._listener.is_cancelled:
            return False
        if code == -9:
            self._listener.is_cancelled = True
            return False
        if code != 0:
            try:
                stderr = stderr.decode().strip()
            except Exception:
                stderr = "Unable to decode the error!"
            LOGGER.error(f"{stderr}. Unable to extract archive!. Path: {f_path}")
        return code

    async def zip(self, dl_path, up_path, pswd):
        size = await get_path_size(dl_path)
        split_size = self._listener.split_size
        cmd = [
            "7z",
            f"-v{split_size}b",
            "a",
            "-mx=0",
            f"-p{pswd}",
            up_path,
            dl_path,
            "-bsp1",
            "-bse1",
            "-bb3",
        ]
        if self._listener.is_leech and int(size) > self._listener.split_size:
            if not pswd:
                del cmd[4]
            LOGGER.info(f"Zip: orig_path: {dl_path}, zip_path: {up_path}.0*")
        else:
            del cmd[1]
            if not pswd:
                del cmd[3]
            LOGGER.info(f"Zip: orig_path: {dl_path}, zip_path: {up_path}")
        if self._listener.is_cancelled:
            return False

        # Execute the command
        self._listener.subproc = await create_subprocess_exec(
            *cmd,
            stdout=PIPE,
            stderr=PIPE,
        )
        await self._sevenz_progress()
        _, stderr = await self._listener.subproc.communicate()
        code = self._listener.subproc.returncode

        if self._listener.is_cancelled:
            return False
        if code == -9:
            self._listener.is_cancelled = True
            return False
        if code == 0:
            await clean_target(dl_path)
            return up_path
        if await aiopath.exists(up_path):
            await remove(up_path)
        try:
            stderr = stderr.decode().strip()
        except Exception:
            stderr = "Unable to decode the error!"
        LOGGER.error(f"{stderr}. Unable to zip this path: {dl_path}")
        return dl_path
