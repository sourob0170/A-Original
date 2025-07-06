"""
Authentication and User Management System
Handles user registration, login, JWT tokens, and role-based access control
"""

import secrets
from datetime import datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from bot import LOGGER
from bot.core.config_manager import Config
from bot.helper.ext_utils.db_handler import database


class AuthHandler:
    """Handles authentication and user management"""

    def __init__(self):
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        self.secret_key = self._get_or_create_secret_key()
        self.algorithm = "HS256"
        self.access_token_expire_minutes = 30
        self.refresh_token_expire_days = 7

    def _get_or_create_secret_key(self) -> str:
        """Get or create JWT secret key"""
        try:
            # Try to get from config first
            secret = getattr(Config, "JWT_SECRET_KEY", None)
            if secret:
                return secret

            # Generate a new secret key
            secret = secrets.token_urlsafe(32)
            LOGGER.info("Generated new JWT secret key")
            return secret
        except Exception as e:
            LOGGER.error(f"Error getting JWT secret key: {e}")
            return secrets.token_urlsafe(32)

    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt"""
        return self.pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return self.pwd_context.verify(plain_password, hashed_password)

    def create_access_token(
        self, data: dict, expires_delta: timedelta | None = None
    ) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                minutes=self.access_token_expire_minutes
            )

        to_encode.update({"exp": expire, "type": "access"})
        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(self, data: dict) -> str:
        """Create JWT refresh token"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)
        to_encode.update({"exp": expire, "type": "refresh"})
        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> dict | None:
        """Verify and decode JWT token"""
        try:
            return jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except JWTError as e:
            if "expired" in str(e).lower():
                LOGGER.warning("Token has expired")
            else:
                LOGGER.warning(f"JWT error: {e}")
            return None

    async def create_user(self, user_data: dict) -> tuple[bool, str]:
        """Create a new user account"""
        try:
            # Validate required fields
            required_fields = [
                "username",
                "email",
                "password",
                "first_name",
                "last_name",
            ]
            for field in required_fields:
                if not user_data.get(field):
                    return False, f"Missing required field: {field}"

            # Check if username or email already exists
            existing_user = await database.get_user_by_username(
                user_data["username"]
            )
            if existing_user:
                return False, "Username already exists"

            existing_email = await database.get_user_by_email(user_data["email"])
            if existing_email:
                return False, "Email already registered"

            # Hash password
            hashed_password = self.hash_password(user_data["password"])

            # Create user document
            user_doc = {
                "username": user_data["username"].lower().strip(),
                "email": user_data["email"].lower().strip(),
                "password_hash": hashed_password,
                "first_name": user_data["first_name"].strip(),
                "last_name": user_data["last_name"].strip(),
                "role": "user",  # Default role
                "is_active": True,
                "created_at": datetime.utcnow().timestamp(),
                "last_login": None,
                "profile": {
                    "avatar": None,
                    "bio": "",
                    "preferences": {
                        "theme": "dark",
                        "language": "en",
                        "notifications": True,
                    },
                },
                "stats": {"files_uploaded": 0, "total_views": 0, "storage_used": 0},
            }

            # Store user in database
            result = await database.create_user(user_doc)
            if result:
                LOGGER.info(f"Created new user: {user_data['username']}")
                return True, "User created successfully"
            return False, "Failed to create user"

        except Exception as e:
            LOGGER.error(f"Error creating user: {e}")
            return False, "Internal server error"

    async def authenticate_user(self, username: str, password: str) -> dict | None:
        """Authenticate user with username/email and password"""
        try:
            # Try to find user by username or email
            user = await database.get_user_by_username(username.lower().strip())
            if not user:
                user = await database.get_user_by_email(username.lower().strip())

            if not user:
                return None

            # Check if user is active
            if not user.get("is_active", True):
                return None

            # Verify password
            if not self.verify_password(password, user["password_hash"]):
                return None

            # Update last login
            await database.update_user_last_login(user["username"])

            # Return user data (without password hash)
            user_data = user.copy()
            del user_data["password_hash"]

            LOGGER.info(f"User authenticated: {user['username']}")
            return user_data

        except Exception as e:
            LOGGER.error(f"Error authenticating user: {e}")
            return None

    async def get_user_by_token(self, token: str) -> dict | None:
        """Get user data from JWT token"""
        try:
            payload = self.verify_token(token)
            if not payload:
                return None

            username = payload.get("sub")
            if not username:
                return None

            user = await database.get_user_by_username(username)
            if not user or not user.get("is_active", True):
                return None

            # Return user data (without password hash)
            user_data = user.copy()
            del user_data["password_hash"]
            return user_data

        except Exception as e:
            LOGGER.error(f"Error getting user by token: {e}")
            return None

    def generate_tokens(self, user_data: dict) -> dict:
        """Generate access and refresh tokens for user"""
        token_data = {
            "sub": user_data["username"],
            "role": user_data.get("role", "user"),
        }

        access_token = self.create_access_token(token_data)
        refresh_token = self.create_refresh_token(token_data)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": self.access_token_expire_minutes * 60,
        }

    async def refresh_access_token(self, refresh_token: str) -> dict | None:
        """Refresh access token using refresh token"""
        try:
            payload = self.verify_token(refresh_token)
            if not payload or payload.get("type") != "refresh":
                return None

            username = payload.get("sub")
            user = await database.get_user_by_username(username)
            if not user or not user.get("is_active", True):
                return None

            # Generate new access token
            token_data = {"sub": username, "role": user.get("role", "user")}
            access_token = self.create_access_token(token_data)

            return {
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": self.access_token_expire_minutes * 60,
            }

        except Exception as e:
            LOGGER.error(f"Error refreshing token: {e}")
            return None

    def is_admin(self, user_data: dict) -> bool:
        """Check if user has admin role"""
        return user_data.get("role") == "admin"

    def is_moderator(self, user_data: dict) -> bool:
        """Check if user has moderator or admin role"""
        return user_data.get("role") in ["moderator", "admin"]

    async def change_password(
        self, username: str, old_password: str, new_password: str
    ) -> tuple[bool, str]:
        """Change user password"""
        try:
            user = await database.get_user_by_username(username)
            if not user:
                return False, "User not found"

            # Verify old password
            if not self.verify_password(old_password, user["password_hash"]):
                return False, "Current password is incorrect"

            # Hash new password
            new_hash = self.hash_password(new_password)

            # Update password in database
            result = await database.update_user_password(username, new_hash)
            if result:
                LOGGER.info(f"Password changed for user: {username}")
                return True, "Password changed successfully"
            return False, "Failed to update password"

        except Exception as e:
            LOGGER.error(f"Error changing password: {e}")
            return False, "Internal server error"


# Global auth handler instance
auth_handler = AuthHandler()
