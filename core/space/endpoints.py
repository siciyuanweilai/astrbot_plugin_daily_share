from __future__ import annotations


class QzoneServiceConstants:
    COOKIE_TTL_SECONDS = 1800
    API_TIMEOUT_SECONDS = 120
    API_TIMEOUT_MIN_SECONDS = 10
    API_TIMEOUT_MAX_SECONDS = 300
    MAX_VIDEO_LINKS = 3

    BASE_URL = "https://user.qzone.qq.com"
    UPLOAD_IMAGE_URL = "https://up.qzone.qq.com/cgi-bin/upload/cgi_upload_image"
    ALBUM_LIST_URL = "https://user.qzone.qq.com/proxy/domain/photo.qzone.qq.com/fcgi-bin/fcg_list_album_v3"
    ALBUM_LIST_JSON_URL = "https://user.qzone.qq.com/proxy/domain/photo.qzone.qq.com/cgi-bin/cgi_list_album"
    ALBUM_CREATE_URL = "https://user.qzone.qq.com/proxy/domain/photo.qzone.qq.com/cgi-bin/cgi_create_album"
    ALBUM_ADD_V2_URL = "https://user.qzone.qq.com/proxy/domain/photo.qzone.qq.com/cgi-bin/common/cgi_add_album_v2"
    VIDEO_LIST_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/video_get_data"
    PUBLISH_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_publish_v6"
    LIKE_URL = "https://user.qzone.qq.com/proxy/domain/w.qzone.qq.com/cgi-bin/likes/internal_dolike_app"
    LIST_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/emotion_cgi_msglist_v6"
    COMMENT_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_re_feeds"
    H5_COMMENT_URL = "https://h5.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_re_feeds"
    ADD_REPLY_UGC_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_addreply_ugc"
    SNS_COMMENT_URL = "https://sns.qzone.qq.com/cgi-bin/qzshare/cgi_qzshareaddcomment"
    DELETE_COMMENT_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_delcomment_ugc"
    SNS_DELETE_COMMENT_URL = "https://sns.qzone.qq.com/cgi-bin/qzshare/cgi_qzsharedeletecomment"
    DETAIL_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_getdetailv6"
    DETAIL_H5_URL = "https://h5.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/emotion_cgi_msgdetail_v6"
    RECENT_URL = "https://user.qzone.qq.com/proxy/domain/ic2.qzone.qq.com/cgi-bin/feeds/feeds3_html_more"
    HOME_FEED_URL = "https://user.qzone.qq.com/proxy/domain/ic2.qzone.qq.com/cgi-bin/feeds/feeds_html_module"
    ABOUT_ME_URL = "https://user.qzone.qq.com/proxy/domain/ic2.qzone.qq.com/cgi-bin/feeds/feeds2_html_pav_all"
    LAST_YEAR_URL = "https://user.qzone.qq.com/proxy/domain/ic2.qzone.qq.com/cgi-bin/feeds/feeds2_html_today_lastyear"
    FAVORITE_URL = "https://user.qzone.qq.com/proxy/domain/fav.qzone.qq.com/cgi-bin/get_fav_list"
    MESSAGE_BOARD_URL = "https://user.qzone.qq.com/proxy/domain/m.qzone.qq.com/cgi-bin/new/get_msgb"
    RELATION_URL = "https://user.qzone.qq.com/proxy/domain/r.qzone.qq.com/cgi-bin/tfriend/friend_ship_manager.cgi"
    VISITOR_URL = "https://user.qzone.qq.com/proxy/domain/g.qzone.qq.com/cgi-bin/friendshow/cgi_get_visitor_simple"
    DELETE_URL = "https://h5.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_delete_v6"

    H5_ORIGIN = "https://h5.qzone.qq.com"
    H5_FILE_BATCH_CONTROL_URL = "https://h5.qzone.qq.com/webapp/json/sliceUpload/FileBatchControl"
    H5_FILE_UPLOAD_URL = "https://h5.qzone.qq.com/webapp/json/sliceUpload/FileUpload"
    H5_FILE_UPLOAD_VIDEO_URL = "https://h5.qzone.qq.com/webapp/json/sliceUpload/FileUploadVideo"
    H5_UPLOAD_SLICE_SIZE = 16384

    VIDEO_CONFIRM_DELAYS_SECONDS = (2, 5, 10, 20)
    PUBLIC_VIDEO_ALBUM_NAME = "说说和视频相册"
    DEFAULT_VIDEO_ALBUM_NAME = "说说和日志相册"
    DEFAULT_VIDEO_ALBUM_TYPE_ID = 7
    PHOTO_LIST_URL = "https://h5.qzone.qq.com/proxy/domain/photo.qzone.qq.com/fcgi-bin/cgi_list_photo"
    PHOTO_FLOATVIEW_URL = "https://user.qzone.qq.com/proxy/domain/photo.qzone.qq.com/fcgi-bin/cgi_floatview_photo_list_v2"
    PHOTO_ALBUM_INFO_URL = "https://user.qzone.qq.com/proxy/domain/photo.qzone.qq.com/cgi-bin/common/cgi_get_albuminfo_v2"
    APPID4_PUBLIC_VIDEO_URL_MARKERS = ("photovideo.photo.qq.com",)
    APPID4_PUBLIC_VIDEO_URL_STATUS_CODES = {200, 206}
    RESULT_TYPE_ALBUM_VIDEO_DYNAMIC = "album_video_dynamic"

    QZONE_COOKIE_DOMAINS = (
        "user.qzone.qq.com",
        "h5.qzone.qq.com",
        "qzone.qq.com",
        "i.qq.com",
        "qzs.qq.com",
        "qzs.qzone.qq.com",
        "qq.com",
    )
    VIDEO_DEBUG_KEYWORDS = (
        "rich",
        "pic_bo",
        "picbo",
        "lloc",
        "sloc",
        "vid",
        "video",
        "album",
        "batch",
        "feed",
        "topic",
        "cell",
        "busi",
        "share",
        "url",
        "cover",
        "ret",
        "code",
        "msg",
        "message",
        "flag",
        "priv",
        "privacy",
        "right",
        "accessright",
        "video_right",
        "videoright",
        "is_video",
        "isvideo",
        "session",
        "slice",
        "photo",
    )
    VIDEO_DEBUG_SENSITIVE_KEYS = {
        "cookie",
        "cookies",
        "skey",
        "p_skey",
        "token",
        "data",
        "picfile",
        "base64",
        "content",
        "chunk",
    }
    VIDEO_DEBUG_MAX_ITEMS = 60
