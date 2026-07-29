from __future__ import annotations


class QzoneServiceConstants:
    COOKIE_TTL_SECONDS = 1800
    API_TIMEOUT_SECONDS = 120
    API_TIMEOUT_MIN_SECONDS = 10
    API_TIMEOUT_MAX_SECONDS = 300

    BASE_URL = "https://user.qzone.qq.com"
    UPLOAD_IMAGE_URL = "https://up.qzone.qq.com/cgi-bin/upload/cgi_upload_image"
    PUBLISH_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_publish_v6"
    LIKE_URL = "https://user.qzone.qq.com/proxy/domain/w.qzone.qq.com/cgi-bin/likes/internal_dolike_app"
    LIST_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/emotion_cgi_msglist_v6"
    COMMENT_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_re_feeds"
    H5_COMMENT_URL = "https://h5.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_re_feeds"
    ADD_REPLY_UGC_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_addreply_ugc"
    SNS_COMMENT_URL = "https://sns.qzone.qq.com/cgi-bin/qzshare/cgi_qzshareaddcomment"
    DELETE_COMMENT_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_delcomment_ugc"
    SNS_DELETE_COMMENT_URL = (
        "https://sns.qzone.qq.com/cgi-bin/qzshare/cgi_qzsharedeletecomment"
    )
    DETAIL_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_getdetailv6"
    DETAIL_H5_URL = "https://h5.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/emotion_cgi_msgdetail_v6"
    RECENT_URL = "https://user.qzone.qq.com/proxy/domain/ic2.qzone.qq.com/cgi-bin/feeds/feeds3_html_more"
    HOME_FEED_URL = "https://user.qzone.qq.com/proxy/domain/ic2.qzone.qq.com/cgi-bin/feeds/feeds_html_module"
    ABOUT_ME_URL = "https://user.qzone.qq.com/proxy/domain/ic2.qzone.qq.com/cgi-bin/feeds/feeds2_html_pav_all"
    LAST_YEAR_URL = "https://user.qzone.qq.com/proxy/domain/ic2.qzone.qq.com/cgi-bin/feeds/feeds2_html_today_lastyear"
    FAVORITE_URL = (
        "https://user.qzone.qq.com/proxy/domain/fav.qzone.qq.com/cgi-bin/get_fav_list"
    )
    MESSAGE_BOARD_URL = (
        "https://user.qzone.qq.com/proxy/domain/m.qzone.qq.com/cgi-bin/new/get_msgb"
    )
    RELATION_URL = "https://user.qzone.qq.com/proxy/domain/r.qzone.qq.com/cgi-bin/tfriend/friend_ship_manager.cgi"
    VISITOR_URL = "https://user.qzone.qq.com/proxy/domain/g.qzone.qq.com/cgi-bin/friendshow/cgi_get_visitor_simple"
    DELETE_URL = "https://h5.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_delete_v6"

    H5_ORIGIN = "https://h5.qzone.qq.com"

    QZONE_COOKIE_DOMAINS = (
        "user.qzone.qq.com",
        "h5.qzone.qq.com",
        "qzone.qq.com",
        "i.qq.com",
        "qzs.qq.com",
        "qzs.qzone.qq.com",
        "qq.com",
    )
