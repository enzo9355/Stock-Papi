"""LINE Login 一次性請求、session 與使用者 Firestore 儲存。"""

import re


class AuthStoreError(RuntimeError):
    pass


class FirestoreAuthStore:
    def __init__(self, project_id):
        if not isinstance(project_id, str) or re.fullmatch(
            r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project_id
        ) is None:
            raise ValueError("project_id is invalid")
        self.project_id = project_id
        self._firestore_client = None

    def _client(self):
        if self._firestore_client is None:
            from google.cloud import firestore

            self._firestore_client = firestore.Client(project=self.project_id)
        return self._firestore_client

    def create_oauth_attempt(self, attempt_id, value):
        try:
            self._client().collection("oauth_attempts").document(attempt_id).create(dict(value))
        except Exception as exc:
            raise AuthStoreError("OAuth attempt could not be stored") from exc

    def consume_oauth_attempt(self, attempt_id, now):
        try:
            from google.cloud import firestore

            client = self._client()
            reference = client.collection("oauth_attempts").document(attempt_id)
            transaction = client.transaction()

            @firestore.transactional
            def consume(transaction):
                snapshot = reference.get(transaction=transaction)
                if not snapshot.exists:
                    return None
                value = snapshot.to_dict() or {}
                if value.get("consumed_at") is not None or value.get("expires_at") is None or value["expires_at"] <= now:
                    return None
                transaction.update(reference, {"consumed_at": firestore.SERVER_TIMESTAMP})
                return value

            return consume(transaction)
        except Exception as exc:
            raise AuthStoreError("OAuth attempt could not be consumed") from exc

    def create_session(self, session_id, value):
        try:
            self._client().collection("web_sessions").document(session_id).create(dict(value))
        except Exception as exc:
            raise AuthStoreError("session could not be stored") from exc

    def load_session(self, session_id, now):
        try:
            snapshot = self._client().collection("web_sessions").document(session_id).get()
            if not snapshot.exists:
                return None
            value = snapshot.to_dict() or {}
            if value.get("expires_at") is None or value["expires_at"] <= now:
                return None
            return {
                "line_user_id": value.get("line_user_id"),
                "csrf_token": value.get("csrf_token"),
                "expires_at": value.get("expires_at"),
            }
        except Exception as exc:
            raise AuthStoreError("session could not be read") from exc

    def delete_session(self, session_id):
        try:
            self._client().collection("web_sessions").document(session_id).delete()
        except Exception as exc:
            raise AuthStoreError("session could not be invalidated") from exc

    def upsert_user(self, user_id, profile):
        try:
            from google.cloud import firestore

            reference = self._client().collection("users").document(user_id)
            snapshot = reference.get()
            value = {
                "line_user_id": user_id,
                "display_name": profile["display_name"],
                "picture_url": profile.get("picture_url"),
                "account_status": "active",
                "plan": "free",
                "schema_version": 1,
                "updated_at": firestore.SERVER_TIMESTAMP,
                "last_login_at": firestore.SERVER_TIMESTAMP,
                "login_count": firestore.Increment(1),
            }
            if not snapshot.exists:
                value["created_at"] = firestore.SERVER_TIMESTAMP
            reference.set(value, merge=True)
            return self.get_user(user_id) or dict(profile)
        except Exception as exc:
            raise AuthStoreError("user profile could not be stored") from exc

    def get_user(self, user_id):
        try:
            snapshot = self._client().collection("users").document(user_id).get()
            if not snapshot.exists:
                return None
            value = snapshot.to_dict() or {}
            return {
                "line_user_id": user_id,
                "display_name": value.get("display_name"),
                "picture_url": value.get("picture_url"),
                "account_status": value.get("account_status"),
                "plan": value.get("plan"),
                "schema_version": value.get("schema_version"),
                "login_count": value.get("login_count"),
            }
        except Exception as exc:
            raise AuthStoreError("user profile could not be read") from exc
