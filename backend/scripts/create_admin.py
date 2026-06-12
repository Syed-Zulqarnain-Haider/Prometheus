"""Create (or update) a local admin user matching a Firebase UID.

The Firebase user (email/password) is created in the Firebase console; this links
that identity to a DB user with the ``admin`` role and an ``all`` row-scope so you
can see everything on first login. Run from the ``backend`` directory:

    PYTHONPATH=. python scripts/create_admin.py --uid <FIREBASE_UID> --email you@example.com
"""

from __future__ import annotations

import argparse
import asyncio

from app.core.database import AsyncSessionLocal, engine
from app.models import Role, User, UserRole, UserScope
from sqlalchemy import select


async def main(firebase_uid: str, email: str) -> None:
    async with AsyncSessionLocal() as session:
        admin_role = await session.scalar(select(Role).where(Role.name == "admin"))
        if admin_role is None:
            raise SystemExit("Roles are not seeded — run 'alembic upgrade head' first.")

        user = await session.scalar(select(User).where(User.firebase_uid == firebase_uid))
        if user is None:
            user = User(firebase_uid=firebase_uid, email=email, is_active=True)
            session.add(user)
            await session.flush()

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
        print(f"Admin ready: {email}  (firebase_uid={firebase_uid})")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a local admin user.")
    parser.add_argument("--uid", required=True, help="Firebase user UID")
    parser.add_argument("--email", required=True, help="User email")
    args = parser.parse_args()
    asyncio.run(main(args.uid, args.email))
