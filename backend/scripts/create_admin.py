"""Create (or update) a local admin user matching a Firebase UID.

The Firebase user (email/password) is created in the Firebase console; this links
that identity to a DB user with the ``admin`` role and an ``all`` row-scope so you
can see everything on first login. Idempotent and safe to re-run: if the email
already exists with a different Firebase UID (e.g. you recreated the Firebase user),
it updates the UID and reactivates the account. Run from the ``backend`` directory:

    PYTHONPATH=. python scripts/create_admin.py --uid <FIREBASE_UID> --email you@example.com
"""

from __future__ import annotations

import argparse
import asyncio

from app.core.database import AsyncSessionLocal, engine
from app.models import Role, User, UserRole, UserScope
from sqlalchemy import select

_PLACEHOLDER_TOKENS = ("your", "paste", "firebase_uid", "<", ">", "example_uid")


def _validate(firebase_uid: str, email: str) -> None:
    low_uid = firebase_uid.lower()
    if not firebase_uid.strip() or any(tok in low_uid for tok in _PLACEHOLDER_TOKENS):
        raise SystemExit(
            f"--uid '{firebase_uid}' looks like a placeholder, not a real UID.\n"
            "Paste the actual 'User UID' from Firebase console → Authentication → Users."
        )
    if "@" not in email or "." not in email.split("@")[-1]:
        raise SystemExit(f"--email '{email}' is not a valid email address.")
    if email == "you@example.com":
        print(
            "WARNING: --email is 'you@example.com' (the example value). "
            "Make sure this matches your real Firebase user's email."
        )


async def main(firebase_uid: str, email: str) -> None:
    async with AsyncSessionLocal() as session:
        admin_role = await session.scalar(select(Role).where(Role.name == "admin"))
        if admin_role is None:
            raise SystemExit("Roles are not seeded — run 'alembic upgrade head' first.")

        user = await session.scalar(select(User).where(User.firebase_uid == firebase_uid))
        if user is not None:
            user.is_active = True
            action = "reactivated existing user (matched by UID)"
        else:
            by_email = await session.scalar(select(User).where(User.email == email))
            if by_email is not None:
                by_email.firebase_uid = firebase_uid
                by_email.is_active = True
                user = by_email
                action = "updated existing user's Firebase UID (matched by email)"
            else:
                user = User(firebase_uid=firebase_uid, email=email, is_active=True)
                session.add(user)
                await session.flush()
                action = "created new user"

        has_role = await session.scalar(
            select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == admin_role.id)
        )
        if has_role is None:
            session.add(UserRole(user_id=user.id, role_id=admin_role.id))

        has_scope = await session.scalar(
            select(UserScope).where(UserScope.user_id == user.id, UserScope.scope_type == "all")
        )
        if has_scope is None:
            session.add(UserScope(user_id=user.id, scope_type="all", scope_value=None))

        await session.commit()
        print(f"Admin ready ({action}): {user.email}  (firebase_uid={firebase_uid})")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a local admin user.")
    parser.add_argument("--uid", required=True, help="Firebase user UID")
    parser.add_argument("--email", required=True, help="User email")
    args = parser.parse_args()
    _validate(args.uid, args.email)
    asyncio.run(main(args.uid, args.email))
