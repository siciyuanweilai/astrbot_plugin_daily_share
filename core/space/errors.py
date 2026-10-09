class QzoneImageUploadError(RuntimeError):
    """配图上传失败且尚未提交说说，可安全降级为纯文字。"""


class QzonePublishUnknownError(RuntimeError):
    """说说已尝试提交但结果未知，不能重试或再发纯文字。"""
