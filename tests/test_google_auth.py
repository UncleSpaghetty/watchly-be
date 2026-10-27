import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.user import User
from app.models.user_identity import UserIdentity
from app.services.google_auth import (
    GoogleClaims,
    GoogleIdentityConflict,
    InvalidGoogleCredential,
    resolve_google_user,
    verify_google_credential,
)
from app.settings.security import hash_password, verify_password


class GoogleAuthTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[User.__table__, UserIdentity.__table__],
        )
        self.db = Session(self.engine)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_creates_google_only_user_and_reuses_subject(self) -> None:
        first = resolve_google_user(
            self.db,
            GoogleClaims("google-subject", "first@gmail.com", "First User", True),
        )
        self.assertIsNone(first.password_hash)

        returning = resolve_google_user(
            self.db,
            GoogleClaims("google-subject", "renamed@gmail.com", "Renamed User", True),
        )

        self.assertEqual(returning.id, first.id)
        identity = self.db.scalar(select(UserIdentity))
        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.email, "renamed@gmail.com")
        self.assertEqual(self.db.query(UserIdentity).count(), 1)

    def test_links_matching_classic_account_without_changing_password(self) -> None:
        password_hash = hash_password("existing-password")
        classic_user = User(
            email="existing@example.com",
            password_hash=password_hash,
            display_name="Existing",
        )
        self.db.add(classic_user)
        self.db.commit()

        linked = resolve_google_user(
            self.db,
            GoogleClaims("linked-subject", "existing@example.com", "Google Name", True),
        )

        self.assertEqual(linked.id, classic_user.id)
        self.assertTrue(verify_password(linked.password_hash, "existing-password"))
        identity = self.db.scalar(select(UserIdentity))
        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.user_id, classic_user.id)

        with self.assertRaises(GoogleIdentityConflict):
            resolve_google_user(
                self.db,
                GoogleClaims("different-subject", "existing@example.com", "Other", True),
            )

    def test_does_not_auto_link_non_authoritative_third_party_email(self) -> None:
        classic_user = User(
            email="external@example.com",
            password_hash=hash_password("existing-password"),
            display_name="Existing",
        )
        self.db.add(classic_user)
        self.db.commit()

        with self.assertRaises(GoogleIdentityConflict):
            resolve_google_user(
                self.db,
                GoogleClaims("third-party-subject", "external@example.com", "Other", False),
            )

        self.assertEqual(self.db.query(UserIdentity).count(), 0)

    @patch("app.services.google_auth.id_token.verify_oauth2_token")
    def test_verifies_audience_and_requires_verified_email(self, verify) -> None:
        verify.return_value = {
            "sub": "subject",
            "email": "USER@GMAIL.COM",
            "email_verified": True,
            "name": "  User Name  ",
        }

        claims = verify_google_credential("credential", "client-id")

        self.assertEqual(claims.email, "user@gmail.com")
        self.assertEqual(claims.display_name, "User Name")
        self.assertTrue(claims.email_authoritative)
        self.assertEqual(verify.call_args.args[2], "client-id")

        verify.return_value["email_verified"] = False
        with self.assertRaises(InvalidGoogleCredential):
            verify_google_credential("credential", "client-id")


if __name__ == "__main__":
    unittest.main()
