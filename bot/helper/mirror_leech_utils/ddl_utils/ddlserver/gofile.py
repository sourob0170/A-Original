#!/usr/bin/env python3
from os import path as ospath
from os import walk
from random import choice

from aiofiles.os import path as aiopath
from aiofiles.os import rename as aiorename
from aiohttp import ClientSession, ClientTimeout

from bot import LOGGER, user_data
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import sync_to_async


class Gofile:
    def __init__(self, dluploader=None, token=None):
        self.api_url = "https://api.gofile.io/"
        self.dluploader = dluploader
        self.token = token

    @staticmethod
    async def is_goapi(token):
        if token is None:
            LOGGER.info("Gofile: No API token provided")
            return False

        try:
            async with ClientSession() as session:
                async with session.get(
                    f"https://api.gofile.io/accounts/getid?token={token}"
                ) as resp:
                    if resp.status != 200:
                        LOGGER.error(
                            f"Gofile: API validation failed with HTTP {resp.status}"
                        )
                        return False

                    res = await resp.json()
                    if res.get("status") != "ok":
                        LOGGER.error(f"Gofile: API token validation failed: {res}")
                        return False

                    acc_id = res["data"]["id"]
                    async with session.get(
                        f"https://api.gofile.io/accounts/{acc_id}?token={token}"
                    ) as resp:
                        if resp.status != 200:
                            LOGGER.error(
                                f"Gofile: Account details request failed with HTTP {resp.status}"
                            )
                            return False

                        account_res = await resp.json()
                        is_valid = account_res.get("status") == "ok"
                        if is_valid:
                            LOGGER.info("Gofile: API token validation successful")
                        else:
                            LOGGER.error(
                                f"Gofile: Account validation failed: {account_res}"
                            )
                        return is_valid
        except Exception as e:
            LOGGER.error(f"Gofile: API validation error - {e!s}")
            return False

    async def __resp_handler(self, response):
        if not response:
            raise Exception("Gofile API Error: Empty response received")

        if not isinstance(response, dict):
            raise Exception(
                f"Gofile API Error: Invalid response format: {type(response)}"
            )

        status = response.get("status")
        if status != "ok":
            error_msg = response.get("error", {})
            if isinstance(error_msg, dict):
                error_code = error_msg.get("code", "unknown")
                error_description = error_msg.get(
                    "description", "No description provided"
                )
                raise Exception(
                    f"Gofile API Error [{error_code}]: {error_description}"
                )
            raise Exception(f"Gofile API Error: {response}")

        data = response.get("data")
        if data is None:
            raise Exception("Gofile API Error: No data in response")

        return data

    async def __getServer(self):
        try:
            timeout = ClientTimeout(total=30, connect=10)
            async with ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.api_url}servers") as resp:
                    if resp.status != 200:
                        raise Exception(f"Failed to get servers: HTTP {resp.status}")
                    response_data = await resp.json()
                    return await self.__resp_handler(response_data)
        except Exception as e:
            LOGGER.error(f"Gofile: Failed to get server list - {e!s}")
            raise Exception(f"Failed to get Gofile servers: {e!s}")

    async def __getAccount(self, check_account=False):
        if self.token is None:
            raise Exception("Invalid Gofile API Key, Recheck your account !!")

        try:
            async with ClientSession() as session:
                # Get account ID
                async with session.get(
                    f"{self.api_url}accounts/getid?token={self.token}"
                ) as resp:
                    if resp.status != 200:
                        raise Exception(
                            f"Failed to get account ID: HTTP {resp.status}"
                        )

                    res = await resp.json()
                    if res.get("status") != "ok":
                        error_msg = res.get("error", {})
                        if isinstance(error_msg, dict):
                            error_desc = error_msg.get(
                                "description", "Unknown error"
                            )
                        else:
                            error_desc = str(error_msg)
                        raise Exception(f"Account ID request failed: {error_desc}")

                    acc_id = res["data"]["id"]
                    LOGGER.info(f"Gofile: Account ID retrieved: {acc_id}")

                    # Get account details
                    async with session.get(
                        f"{self.api_url}accounts/{acc_id}?token={self.token}"
                    ) as resp:
                        if resp.status != 200:
                            raise Exception(
                                f"Failed to get account details: HTTP {resp.status}"
                            )

                        res = await resp.json()
                        if check_account:
                            return res.get("status") == "ok"
                        return await self.__resp_handler(res)
        except Exception as e:
            LOGGER.error(f"Gofile: Account validation failed - {e!s}")
            if check_account:
                return False
            raise Exception(f"Failed to validate Gofile account: {e!s}")

        return False

    async def upload_folder(self, path, folderId=None):
        if not await aiopath.isdir(path):
            raise Exception(f"Path: {path} is not a valid directory")

        folder_data = await self.create_folder(
            (await self.__getAccount())["rootFolder"], ospath.basename(path)
        )
        await self.__setOptions(
            contentId=folder_data["folderId"], option="public", value="true"
        )

        folderId = folderId or folder_data["folderId"]
        folder_ids = {".": folderId}
        for root, _, files in await sync_to_async(walk, path):
            rel_path = ospath.relpath(root, path)
            parentFolderId = folder_ids.get(ospath.dirname(rel_path), folderId)
            folder_name = ospath.basename(rel_path)
            currFolderId = (await self.create_folder(parentFolderId, folder_name))[
                "folderId"
            ]
            await self.__setOptions(
                contentId=currFolderId, option="public", value="true"
            )
            folder_ids[rel_path] = currFolderId

            for file in files:
                file_path = ospath.join(root, file)
                await self.upload_file(file_path, currFolderId)

        return folder_data["code"]

    async def upload_file(
        self,
        path: str,
        folderId: str = "",
        description: str = "",
        password: str = "",
        tags: str = "",
        expire: str = "",
    ):
        """Upload file to Gofile with user settings integration"""
        if password and len(password) < 4:
            raise ValueError("Password Length must be greater than 4")

        # Get user settings with fallback to owner settings
        user_id = (
            self.dluploader._DDLUploader__user_id
            if hasattr(self.dluploader, "_DDLUploader__user_id")
            else None
        )
        user_dict = user_data.get(user_id, {}) if user_id else {}

        def get_gofile_setting(user_key, owner_attr, default_value=None):
            user_value = user_dict.get(user_key)
            if user_value is not None:
                return user_value
            return getattr(Config, owner_attr, default_value)

        # Apply user settings with fallback to owner settings
        if not folderId:
            folder_name = get_gofile_setting(
                "GOFILE_FOLDER_NAME", "GOFILE_FOLDER_NAME", ""
            )
            if folder_name:
                # Create folder if specified
                folder_data = await self.create_folder(
                    (await self.__getAccount())["rootFolder"], folder_name
                )
                folderId = folder_data["folderId"]

        if not description:
            description = ""  # Could be extended to use user settings

        if not password and get_gofile_setting(
            "GOFILE_PASSWORD_PROTECTION", "GOFILE_PASSWORD_PROTECTION", False
        ):
            password = get_gofile_setting(
                "GOFILE_DEFAULT_PASSWORD", "GOFILE_DEFAULT_PASSWORD", ""
            )

        if not expire:
            expiry_days = get_gofile_setting(
                "GOFILE_LINK_EXPIRY_DAYS", "GOFILE_LINK_EXPIRY_DAYS", 0
            )
            if expiry_days > 0:
                expire = str(expiry_days)

        # Get available servers and select one
        try:
            servers_data = await self.__getServer()
            available_servers = servers_data.get("servers", [])
            if not available_servers:
                raise Exception("No Gofile servers available")

            server = choice(available_servers)["name"]
            LOGGER.info(f"Gofile: Selected server: {server}")
        except Exception as e:
            LOGGER.error(f"Gofile: Failed to get server - {e!s}")
            raise Exception(f"Failed to get Gofile server: {e!s}")
        req_dict = {}
        if token := self.token or "":
            req_dict["token"] = token
        if folderId:
            req_dict["folderId"] = folderId
        if description:
            req_dict["description"] = description
        if password:
            req_dict["password"] = password
        if tags:
            req_dict["tags"] = tags
        if expire:
            req_dict["expire"] = expire

        if self.dluploader.is_cancelled:
            return None

        # Rename file to replace spaces with dots for better compatibility
        new_path = ospath.join(
            ospath.dirname(path), ospath.basename(path).replace(" ", ".")
        )
        await aiorename(path, new_path)

        LOGGER.info(f"Gofile: Starting upload to server {server}")
        LOGGER.info(
            f"Gofile: Upload URL: https://{server}.gofile.io/contents/uploadfile"
        )
        LOGGER.info(f"Gofile: File path: {new_path}")

        self.dluploader.last_uploaded = 0
        upload_file = await self.dluploader.upload_aiohttp(
            f"https://{server}.gofile.io/contents/uploadfile",
            new_path,
            "file",
            req_dict,
        )

        if upload_file is None:
            raise Exception("Upload failed: No response from Gofile server")

        LOGGER.info(f"Gofile: Raw upload response: {upload_file}")
        result = await self.__resp_handler(upload_file)

        # Apply public link setting if configured
        if (
            result
            and result.get("id")
            and get_gofile_setting(
                "GOFILE_PUBLIC_LINKS", "GOFILE_PUBLIC_LINKS", True
            )
        ):
            try:
                await self.__setOptions(
                    contentId=result["id"], option="public", value="true"
                )
            except Exception:
                pass  # Continue even if setting public fails

        return result

    async def upload(self, file_path):
        try:
            LOGGER.info("Gofile: Validating API token")
            if not await self.is_goapi(self.token):
                raise Exception("Invalid Gofile API Key, Recheck your account !!")

            LOGGER.info(f"Gofile: Starting upload for path: {file_path}")

            if await aiopath.isfile(file_path):
                LOGGER.info(f"Gofile: Uploading file: {file_path}")
                gCode = await self.upload_file(path=file_path)

                if not gCode:
                    raise Exception(
                        "Upload failed: No response data from Gofile API"
                    )

                download_page = gCode.get("downloadPage")
                if not download_page:
                    LOGGER.error(f"Gofile: No downloadPage in response: {gCode}")
                    raise Exception(
                        "Upload failed: No download page URL in response"
                    )

                LOGGER.info(f"Gofile: File upload successful: {download_page}")
                return download_page

            if await aiopath.isdir(file_path):
                LOGGER.info(f"Gofile: Uploading folder: {file_path}")
                gCode = await self.upload_folder(path=file_path)

                if not gCode:
                    raise Exception("Upload failed: No folder code from Gofile API")

                folder_url = f"https://gofile.io/d/{gCode}"
                LOGGER.info(f"Gofile: Folder upload successful: {folder_url}")
                return folder_url
            raise Exception(f"Path does not exist or is not accessible: {file_path}")

        except Exception as e:
            if self.dluploader.is_cancelled:
                LOGGER.info("Gofile: Upload cancelled by user")
                return None

            error_msg = str(e)
            LOGGER.error(f"Gofile: Upload failed - {error_msg}")
            raise Exception(f"Gofile upload failed: {error_msg}")

    async def create_folder(self, parentFolderId, folderName):
        if self.token is None:
            raise Exception("Invalid Gofile API Key, Recheck your account !!")

        async with (
            ClientSession() as session,
            session.post(
                url=f"{self.api_url}contents/createFolder",
                data={
                    "token": self.token,
                    "parentFolderId": parentFolderId,
                    "folderName": folderName,
                },
            ) as resp,
        ):
            return await self.__resp_handler(await resp.json())

    async def __setOptions(self, contentId, option, value):
        if self.token is None:
            raise Exception("Invalid Gofile API Key, Recheck your account !!")

        if option not in [
            "name",
            "description",
            "tags",
            "public",
            "expiry",
            "password",
        ]:
            raise Exception(f"Invalid GoFile Option Specified : {option}")
        async with (
            ClientSession() as session,
            session.put(
                url=f"{self.api_url}contents/{contentId}/update",
                data={
                    "token": self.token,
                    "attribute": option,
                    "attributeValue": value,
                },
            ) as resp,
        ):
            return await self.__resp_handler(await resp.json())

    async def get_content(self, contentId):
        if self.token is None:
            raise Exception("Invalid Gofile API Key, Recheck your account !!")

        async with (
            ClientSession() as session,
            session.get(
                url=f"{self.api_url}contents/{contentId}&token={self.token}&cache=true"
            ) as resp,
        ):
            return await self.__resp_handler(await resp.json())

    async def copy_content(self, contentsId, folderIdDest):
        if self.token is None:
            raise Exception("Invalid Gofile API Key, Recheck your account !!")

        async with (
            ClientSession() as session,
            session.post(
                url=f"{self.api_url}contents/copy",
                data={
                    "token": self.token,
                    "contentsId": contentsId,
                    "folderId": folderIdDest,
                },
            ) as resp,
        ):
            return await self.__resp_handler(await resp.json())
