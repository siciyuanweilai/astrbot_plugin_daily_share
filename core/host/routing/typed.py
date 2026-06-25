from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from ...args import find_invalid_non_news_args
from ...config import NEWS_SOURCE_MAP, ShareType
from ...constants import TYPE_CN_MAP


class PluginShareTypedRouteMixin:
    async def _handle_manual_auto_share_command(
        self,
        event: AstrMessageEvent,
        *,
        parts: list[str],
        is_broadcast: bool,
        is_qzone_target: bool,
        specific_target: str | None = None,
        share_global_scope: bool = False,
    ):
        invalid_args = find_invalid_non_news_args(parts)
        if invalid_args:
            yield event.plain_result(f"无效参数: {' '.join(invalid_args)}。非新闻类型仅支持后缀：广播、空间。")
            return

        async for result in self._start_typed_share_task(
            event,
            force_type=None,
            news_source=None,
            start_text="正在向QQ空间生成并分享内容(自动类型)..."
            if is_qzone_target
            else f"正在向{self._manual_share_target_desc(is_broadcast=is_broadcast, is_qzone_target=False)}生成并分享内容(自动类型)...",
            is_qzone_target=is_qzone_target,
            specific_target=specific_target,
            share_global_scope=share_global_scope,
        ):
            yield result

    async def _handle_manual_news_share_command(
        self,
        event: AstrMessageEvent,
        *,
        parts: list[str],
        current_uid: str,
        force_type: ShareType,
        type_cn: str,
        is_broadcast: bool,
        is_qzone_target: bool,
        specific_target: str | None = None,
        share_global_scope: bool = False,
    ):
        news_src = self._parse_manual_news_source(parts)
        if "图片" in parts:
            async for result in self._start_news_image_task(
                event,
                news_src=news_src,
                current_uid=current_uid,
                is_qzone_target=is_qzone_target,
                specific_target=specific_target,
                share_global_scope=share_global_scope,
            ):
                yield result
            return

        src_info = f" ({NEWS_SOURCE_MAP[news_src]['name']})" if news_src else ""
        async for result in self._start_typed_share_task(
            event,
            force_type=force_type,
            news_source=news_src,
            start_text=f"正在向QQ空间生成并分享{type_cn}{src_info} ..."
            if is_qzone_target
            else f"正在向{self._manual_share_target_desc(is_broadcast=is_broadcast, is_qzone_target=False)}生成并分享{type_cn}{src_info} ...",
            is_qzone_target=is_qzone_target,
            specific_target=specific_target,
            share_global_scope=share_global_scope,
        ):
            yield result

    async def _handle_manual_typed_share_command(
        self,
        event: AstrMessageEvent,
        *,
        parts: list[str],
        force_type: ShareType,
        type_cn: str,
        is_broadcast: bool,
        is_qzone_target: bool,
        specific_target: str | None = None,
        share_global_scope: bool = False,
    ):
        invalid_args = find_invalid_non_news_args(parts)
        if invalid_args:
            yield event.plain_result(f"无效参数: {' '.join(invalid_args)}。非新闻类型仅支持后缀：广播、空间。")
            return

        async for result in self._start_typed_share_task(
            event,
            force_type=force_type,
            news_source=None,
            start_text=f"正在向QQ空间生成并分享{type_cn} ..."
            if is_qzone_target
            else f"正在向{self._manual_share_target_desc(is_broadcast=is_broadcast, is_qzone_target=False)}生成并分享{type_cn} ...",
            is_qzone_target=is_qzone_target,
            specific_target=specific_target,
            share_global_scope=share_global_scope,
        ):
            yield result

    async def _dispatch_manual_typed_command(
        self,
        event: AstrMessageEvent,
        *,
        arg: str,
        parts: list[str],
        current_uid: str,
        is_broadcast: bool,
        is_qzone_target: bool,
        specific_target: str | None = None,
        share_global_scope: bool = False,
    ):
        force_type = self._resolve_manual_share_type(arg)
        if not force_type:
            yield event.plain_result(f"未知指令或无效类型: {arg}\n可用: 问候, 新闻, 心情, 知识, 推荐, 60s, ai")
            return

        type_cn = TYPE_CN_MAP.get(force_type.value, arg)
        if force_type == ShareType.NEWS:
            async for result in self._handle_manual_news_share_command(
                event,
                parts=parts,
                current_uid=current_uid,
                force_type=force_type,
                type_cn=type_cn,
                is_broadcast=is_broadcast,
                is_qzone_target=is_qzone_target,
                specific_target=specific_target,
                share_global_scope=share_global_scope,
            ):
                yield result
            return

        async for result in self._handle_manual_typed_share_command(
            event,
            parts=parts,
            force_type=force_type,
            type_cn=type_cn,
            is_broadcast=is_broadcast,
            is_qzone_target=is_qzone_target,
            specific_target=specific_target,
            share_global_scope=share_global_scope,
        ):
            yield result
