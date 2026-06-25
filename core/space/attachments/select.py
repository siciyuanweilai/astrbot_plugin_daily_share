from __future__ import annotations

from typing import Any


class QzoneAlbumSelectMixin:
    ALBUM_ID_KEYS = ("id", "albumId", "albumid", "topicId", "topicid", "album_id")
    ALBUM_NAME_KEYS = ("name", "albumName", "albumname", "title", "album_title")
    ALBUM_UPLOAD_BLOCK_KEYS = ("isDeleted", "deleted", "forbidUpload", "forbid_upload", "noUpload", "no_upload")
    ALBUM_UPLOAD_ALLOW_KEYS = ("allowUpload", "allow_upload", "canUpload", "can_upload", "uploadable")
    ALBUM_PRIVACY_KEYS = ("priv", "privacy", "viewtype", "right", "accessright")
    ALBUM_TYPE_KEYS = ("handset", "albumTypeID", "albumtype", "albumType", "type")
    ALBUM_URL_KEYS = {
        "url",
        "url2",
        "url3",
        "downloadurl",
        "download_url",
        "videourl",
        "video_url",
        "playurl",
        "play_url",
        "vvidiourl",
        "vvidioswfurl",
        "datavvidiourl",
        "datavvidioswfurl",
    }
    ALBUM_PUBLIC_VISIBILITY_KEYS = {"priv", "pypriv", "privacy", "accessright", "dataaccessright"}
    ALBUM_PUBLIC_OWNER_KEYS = {"ugcright", "ugc_right", "who"}
    ALBUM_TITLE_KEYS = {"topicname", "albumname", "albumtitle"}

    @staticmethod
    def _first_mapping_text(mapping: dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            value = mapping.get(key)
            if value not in (None, ""):
                return str(value).strip()
        return ""

    @staticmethod
    def _clean_album_text(value: Any) -> str:
        text = str(value or "").strip()
        return "" if text.lower() in {"null", "none", "undefined"} else text

    @classmethod
    def _album_identity(cls, album: dict[str, Any]) -> tuple[str, str]:
        album_id = cls._clean_album_text(cls._first_mapping_text(album, cls.ALBUM_ID_KEYS))
        album_name = cls._clean_album_text(cls._first_mapping_text(album, cls.ALBUM_NAME_KEYS))
        return album_id, album_name

    @staticmethod
    def _album_flag_enabled(value: Any) -> bool | None:
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"0", "false", "no", "off"}:
            return False
        if text in {"1", "true", "yes", "on"}:
            return True
        return None

    @classmethod
    def _album_is_uploadable(cls, album: dict[str, Any]) -> bool:
        for key in cls.ALBUM_UPLOAD_ALLOW_KEYS:
            enabled = cls._album_flag_enabled(album.get(key))
            if enabled is False:
                return False
        for key in cls.ALBUM_UPLOAD_BLOCK_KEYS:
            enabled = cls._album_flag_enabled(album.get(key))
            if enabled is True:
                return False
        return True

    @classmethod
    def _album_privacy_value(cls, album: dict[str, Any]) -> str:
        for key in cls.ALBUM_PRIVACY_KEYS:
            value = cls._clean_album_text(album.get(key))
            if value:
                return value
        return ""

    @classmethod
    def _album_type_value(cls, album: dict[str, Any]) -> str:
        for key in cls.ALBUM_TYPE_KEYS:
            value = cls._clean_album_text(album.get(key))
            if value:
                return value
        return ""

    @classmethod
    def _album_is_mood_log_album(cls, album: dict[str, Any]) -> bool:
        _, album_name = cls._album_identity(album)
        compact_name = album_name.replace(" ", "")
        default_name = str(cls.DEFAULT_VIDEO_ALBUM_NAME or "").replace(" ", "")
        return bool(
            (default_name and compact_name == default_name)
            or ("说说" in compact_name and "日志" in compact_name)
            or (cls._album_type_value(album) == "7" and cls._album_privacy_value(album) == "3")
        )

    @classmethod
    def _album_is_public(cls, album: dict[str, Any]) -> bool:
        album_id, _ = cls._album_identity(album)
        return bool(album_id and cls._album_privacy_value(album) == "1" and not cls._album_is_mood_log_album(album))

    @classmethod
    def _album_result(cls, album: dict[str, Any]) -> dict[str, Any]:
        album_id, album_name = cls._album_identity(album)
        result = {
            "id": album_id,
            "name": album_name,
        }
        album_type_id = cls._album_type_value(album)
        if album_type_id:
            result["album_type_id"] = album_type_id
        return result

    @classmethod
    def _qzone_album_candidates(cls, payload: Any) -> list[dict[str, Any]]:
        albums: list[dict[str, Any]] = []

        def append_items(items: Any) -> None:
            if isinstance(items, list):
                albums.extend(item for item in items if isinstance(item, dict))

        for root in cls._walk_mappings(payload):
            append_items(root.get("albumListModeSort"))
            append_items(root.get("albumList"))
            for category in root.get("albumListModeClass") or []:
                if isinstance(category, dict):
                    append_items(category.get("albumList"))

        result: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for album in albums:
            album_id, album_name = cls._album_identity(album)
            key = (album_id, album_name)
            if key != ("", "") and key not in seen:
                seen.add(key)
                result.append(album)
        return result

    @classmethod
    def _select_public_video_album(cls, payload: Any, *, album_name: str = "") -> dict[str, Any] | None:
        wanted_name = cls._clean_album_text(album_name)
        public_albums = [
            album
            for album in cls._qzone_album_candidates(payload)
            if cls._album_is_uploadable(album) and cls._album_is_public(album)
        ]
        if not public_albums:
            return None
        preferred_names = [wanted_name, cls.PUBLIC_VIDEO_ALBUM_NAME]
        for name in [item for item in preferred_names if item]:
            for album in public_albums:
                if cls._album_identity(album)[1] == name:
                    return cls._album_result(album)
        return None

    @classmethod
    def _created_public_video_album(cls, payload: Any, *, album_name: str) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        mappings = [payload]
        data = payload.get("data")
        if isinstance(data, dict):
            mappings.append(data)
        for mapping in mappings:
            album_id = cls._clean_album_text(
                cls._first_mapping_text(mapping, ("albumid", "albumId", "topicId", "id", "aid"))
            )
            if not album_id:
                continue
            returned_name = cls._clean_album_text(
                cls._first_mapping_text(mapping, ("albumname", "albumName", "name", "title"))
            )
            return {"id": album_id, "name": returned_name or album_name}
        return None
