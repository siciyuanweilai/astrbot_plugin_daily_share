from ..config import TimePeriod
from ..database.keys import is_public_share_target, public_share_target_label
from ..prompt import (
    build_common_content_rules,
    build_current_time_context,
    build_task_prompt,
)
from .contentbase import ContentComponent


class ContentSocialService(ContentComponent):
    async def _gen_greeting(self, period: TimePeriod, ctx: dict):
        p_label = ctx["period_label"]
        is_group = ctx["is_group"]
        if ctx.get("is_qzone_post", False):
            return await self._generate_qzone_post(
                ctx, "这次想按当前时段随口打个招呼，可带一句当下状态。"
            )
        is_qzone = is_public_share_target(ctx.get("target_id"))
        public_label = public_share_target_label(ctx.get("target_id"))
        call_name = ctx.get("nickname", "")
        detect_name = ctx.get("detect_name", "")

        # 0. 获取配置
        allow_detail = self.context_conf.get("group_share_schedule", False)

        user_info_prompt = ""
        if not is_group and not is_qzone:
            user_info_prompt = self._build_user_prompt(
                call_name, detect_name, ctx.get("target_id", "")
            )

        common_rules = build_common_content_rules(
            is_group=is_group,
            is_qzone=is_qzone,
            date_text=ctx["date_str"],
            time_text=ctx["time_str"],
            period_label=p_label,
            action="问候",
            allow_detail=allow_detail,
            public_label=public_label,
            include_time=False,
        )
        greeting_constraint = ""
        opening_rule = ""

        # 清晨(6-9) -> 早间问候放开头
        if period in [TimePeriod.MORNING]:
            greeting_constraint = (
                "4. 文案开头必须是自然的早间问候语，例如“早安”“早上好”“早呀”“早哦”"
            )
            opening_rule = f'- 早间问候开头："{"大家" if is_group else ""}早上好，" / "{"大家" if is_group else ""}早安，" / "{"大家" if is_group else ""}早呀，"'

        # 深夜(22-24) 和 凌晨(0-6) -> 睡前祝福放结尾
        elif period in [TimePeriod.LATE_NIGHT, TimePeriod.DAWN]:
            greeting_constraint = "4. 文案不得以睡前祝福开头；必须在正文最后自然收束一句睡前祝福，例如“晚安”“安安”“好梦”“早点睡，做个好梦”"
            opening_rule = "- 睡前问候：不要用“晚安/安安/好梦”开头，可从当前状态、环境或困意自然切入，最后再用睡前祝福收束。"

        # 上午/下午/傍晚/晚上 -> 自然打招呼
        else:
            greeting_constraint = (
                "4. 就像平常聊天一样自然打招呼即可，不需要刻意说早间问候或睡前祝福"
            )
            opening_rule = '- 自然切入："今天心情不错呢" / "刚忙完..." / "今天有点..."'

        opening_prompt = f"""【开头方式】（自然直接）
{opening_rule}

- 心情切入："今天心情不错呢"
- 状态切入："刚忙完..." / "今天有点..."
- 天气切入：（仅在天气特殊时使用）"""
        length_requirement = (
            f"5. {'简短（80-100字）' if is_group else '可适当长一些（100-120字）'}"
        )
        dynamics_prompt = self._build_recent_dynamics_prompt(ctx.get("recent_dynamics"))

        target_str = public_label if is_qzone else ("群聊" if is_group else "私聊")

        rules = f"""
{common_rules}
你现在要向{target_str}发送一条温馨自然的问候。
{ctx.get("output_format_hint", "")}

【问候写法】
- 可以参考生活状态、天气或正在做的事，让问候更像当下自然说出口的话。
- 群聊请直接开启新问候，不评价群氛围；私聊可以更个人化；{public_label}写成自己的状态记录。

{opening_prompt}

要求：
1. 以你的人设性格说话，真实自然
2. 基于当前真实时间问候
3. 忽略群聊历史，直接开启新问候
{greeting_constraint}
{length_requirement}
6. 直接输出内容，不要解释
"""
        prompt = build_task_prompt(
            rules,
            build_current_time_context(ctx),
            user_info_prompt,
            ctx["life_hint"],
            ctx["structured_history_hint"],
            dynamics_prompt,
            output=f"请生成{p_label}问候：",
        )

        res = await self._call_llm(
            prompt=prompt,
            system_prompt=ctx["system_prompt"],
            target_umo=ctx.get("target_id"),
        )
        if res:
            return f"{res}"
        return None

    async def _gen_mood(self, period, ctx):
        is_group = ctx["is_group"]
        if ctx.get("is_qzone_post", False):
            return await self._generate_qzone_post(
                ctx, "这次想说一句当前在意的小事、心情或念头，选有依据的一点即可。"
            )
        is_qzone = is_public_share_target(ctx.get("target_id"))
        public_label = public_share_target_label(ctx.get("target_id"))
        call_name = ctx.get("nickname", "")
        detect_name = ctx.get("detect_name", "")

        # 0. 获取配置
        allow_detail = self.context_conf.get("group_share_schedule", False)

        user_info_prompt = ""
        if not is_group and not is_qzone:
            user_info_prompt = self._build_user_prompt(
                call_name, detect_name, ctx.get("target_id", "")
            )

        common_rules = build_common_content_rules(
            is_group=is_group,
            is_qzone=is_qzone,
            date_text=ctx["date_str"],
            time_text=ctx["time_str"],
            period_label=ctx["period_label"],
            action="分享心情",
            allow_detail=allow_detail,
            public_label=public_label,
            include_time=False,
        )
        # 3. 共鸣策略
        resonance_guide = ""
        if is_qzone:
            resonance_guide = (
                f"【{public_label}写法】像个人动态一样记录此刻，不需要互动提问。"
            )
        elif is_group:
            resonance_guide = """
【群聊共鸣写法】
从当下状态里提炼一种容易共情的小情绪或小观察，直接分享给群友。
可以轻描淡写地带过正在做的事，但不要变成流水账，也不要评价群聊气氛。
"""
        else:
            resonance_guide = (
                "【私聊写法】像对亲近的人聊天一样，分享一点具体、细腻、可信的小情绪。"
            )

        dynamics_prompt = self._build_recent_dynamics_prompt(ctx.get("recent_dynamics"))

        target_str = public_label if is_qzone else ("群聊" if is_group else "私聊")
        time_greeting_rule = ""
        if period in (TimePeriod.LATE_NIGHT, TimePeriod.DAWN):
            time_greeting_rule = """
【深夜表达规则】
- 不要以“晚安/安安/好梦”等睡前祝福作为开头；心情分享应先写当下状态、动作或感受。
- 如果要写睡前祝福，只能放在正文最后；可以自然使用“晚安”“安安”“好梦”“早点睡，做个好梦”等表达。
"""

        length_requirement = f"5. 字数：{'80-100字' if is_group else '100-120字'}"

        rules = f"""
{common_rules}
你想和{target_str}分享一下现在的心情或想法。
{ctx.get("output_format_hint", "")}
{resonance_guide}
{time_greeting_rule}

【状态结合方式】
- 不要干巴巴汇报行程；把正在做的事转化为可感知的情绪、画面或小念头。
- 联系不上当前状态时，直接写心情本身，不要硬凑原因。

要求：
1. 以你的人设性格说话，真实自然
2. 分享此刻的感受、想法或小感悟
3. 忽略群聊历史，直接开启新话题
4. 基于当前真实时间感悟
{length_requirement}
6. 直接输出内容
"""
        prompt = build_task_prompt(
            rules,
            build_current_time_context(ctx),
            user_info_prompt,
            ctx["life_hint"],
            ctx["structured_history_hint"],
            dynamics_prompt,
            output="你的随想：",
        )

        res = await self._call_llm(
            prompt=prompt,
            system_prompt=ctx["system_prompt"],
            target_umo=ctx.get("target_id"),
        )
        return res
