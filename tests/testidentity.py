import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "daily_share_identity_testpkg"
CORE_PACKAGE_NAME = f"{PACKAGE_NAME}.core"
CONFIG_MODULE_NAME = f"{CORE_PACKAGE_NAME}.config"
CONTENT_MODULE_NAME = f"{CORE_PACKAGE_NAME}.content"
IMAGE_MODULE_NAME = f"{CORE_PACKAGE_NAME}.image"


class _Logger:
    def debug(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None


class _CaptureLogger(_Logger):
    def __init__(self):
        self.infos = []

    def info(self, *args, **kwargs):
        self.infos.append(" ".join(str(arg) for arg in args))


class _PersonaManager:
    def __init__(self, prompt):
        self.prompt = prompt

    async def get_default_persona_v3(self):
        return {"prompt": self.prompt, "bot_name": "测试机器人", "user_name": ""}


def _clear_modules():
    for name in list(sys.modules):
        if name.startswith(PACKAGE_NAME) or name in {
            "astrbot",
            "astrbot.api",
            "aiofiles",
            "aiohttp",
        }:
            sys.modules.pop(name, None)


def _install_stub_module(name: str, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _load_module(name: str, path: Path):
    package_locations = [str(path.parent)] if path.name == "__init__.py" else None
    spec = importlib.util.spec_from_file_location(
        name, path, submodule_search_locations=package_locations
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _load_daily_share_modules():
    _clear_modules()

    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(ROOT)]
    sys.modules[PACKAGE_NAME] = package

    core_package = types.ModuleType(CORE_PACKAGE_NAME)
    core_package.__path__ = [str(ROOT / "core")]
    sys.modules[CORE_PACKAGE_NAME] = core_package

    _install_stub_module("astrbot")
    _install_stub_module("astrbot.api", logger=_Logger())
    _install_stub_module("aiofiles")
    _install_stub_module("aiohttp")

    _load_module(CONFIG_MODULE_NAME, ROOT / "core" / "config.py")
    content_module = _load_module(
        CONTENT_MODULE_NAME, ROOT / "core" / "content" / "__init__.py"
    )
    image_module = _load_module(
        IMAGE_MODULE_NAME, ROOT / "core" / "image" / "__init__.py"
    )
    return content_module, image_module


class IdentityPromptTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        _clear_modules()

    async def test_content_service_keeps_persona_only_in_system_prompt(self):
        content_module, _ = _load_daily_share_modules()
        calls = []

        async def call_llm(prompt, system_prompt="", **kwargs):
            calls.append({"prompt": prompt, "system_prompt": system_prompt})
            return "今天状态还不错。$$happy$$"

        context = types.SimpleNamespace(
            persona_manager=_PersonaManager("你的名字叫测试人格。性别女，18岁。")
        )
        service = content_module.ContentService(
            {"news_conf": {}, "basic_conf": {}, "context_conf": {}},
            call_llm,
            context=context,
            db_manager=types.SimpleNamespace(),
            news_service=None,
        )

        await service.generate(
            sys.modules[CONFIG_MODULE_NAME].ShareType.MOOD,
            sys.modules[CONFIG_MODULE_NAME].TimePeriod.AFTERNOON,
            "target",
            False,
            "",
        )

        persona = "你的名字叫测试人格。性别女，18岁。"
        self.assertIn(persona, calls[0]["system_prompt"])
        self.assertIn("【身份边界】", calls[0]["system_prompt"])
        self.assertNotIn(persona, calls[0]["prompt"])
        self.assertEqual(
            (calls[0]["prompt"] + calls[0]["system_prompt"]).count(persona),
            1,
        )

    async def test_content_service_receives_structured_history_prompt(self):
        content_module, _ = _load_daily_share_modules()
        calls = []

        async def call_llm(prompt, system_prompt="", **kwargs):
            calls.append(
                {"prompt": prompt, "system_prompt": system_prompt, "kwargs": kwargs}
            )
            return "今天状态还不错。$$happy$$"

        context = types.SimpleNamespace(
            persona_manager=_PersonaManager("你的名字叫测试人格。性别女，18岁。")
        )
        service = content_module.ContentService(
            {"news_conf": {}, "basic_conf": {}, "context_conf": {}},
            call_llm,
            context=context,
            db_manager=types.SimpleNamespace(),
            news_service=None,
        )

        await service.generate(
            sys.modules[CONFIG_MODULE_NAME].ShareType.MOOD,
            sys.modules[CONFIG_MODULE_NAME].TimePeriod.AFTERNOON,
            "target",
            False,
            "",
            nickname="阿林",
            structured_history="<structured_history>\n- [12:00] 阿林 (图片): 今天适合散步。\n</structured_history>",
        )

        self.assertIn("【最近的真实消息流】", calls[0]["prompt"])
        self.assertIn("今天适合散步。", calls[0]["prompt"])
        self.assertIn("阿林", calls[0]["prompt"])

    async def test_content_service_injects_share_output_format(self):
        content_module, _ = _load_daily_share_modules()
        calls = []

        async def call_llm(prompt, system_prompt="", **kwargs):
            calls.append({"prompt": prompt, "system_prompt": system_prompt})
            return "ok"

        context = types.SimpleNamespace(persona_manager=_PersonaManager(""))
        service = content_module.ContentService(
            {
                "news_conf": {},
                "basic_conf": {
                    "share_output_format": "使用两行短句，每行不超过 25 字。"
                },
                "context_conf": {},
            },
            call_llm,
            context=context,
            db_manager=types.SimpleNamespace(),
            news_service=None,
        )

        await service.generate(
            sys.modules[CONFIG_MODULE_NAME].ShareType.MOOD,
            sys.modules[CONFIG_MODULE_NAME].TimePeriod.AFTERNOON,
            "target",
            False,
            "",
        )

        self.assertIn("【分享文案输出格式】", calls[0]["prompt"])
        self.assertIn("使用两行短句，每行不超过 25 字。", calls[0]["prompt"])

    async def test_content_service_prefers_qzone_output_format_for_qzone(self):
        content_module, _ = _load_daily_share_modules()
        calls = []

        async def call_llm(prompt, system_prompt="", **kwargs):
            calls.append({"prompt": prompt, "system_prompt": system_prompt})
            return "ok"

        context = types.SimpleNamespace(persona_manager=_PersonaManager(""))
        service = content_module.ContentService(
            {
                "news_conf": {},
                "basic_conf": {"share_output_format": "普通分享两行短句。"},
                "qzone_conf": {
                    "qzone_share_output_format": "像 QQ 空间说说一样自然分行。"
                },
                "context_conf": {},
            },
            call_llm,
            context=context,
            db_manager=types.SimpleNamespace(),
            news_service=None,
        )

        await service.generate(
            sys.modules[CONFIG_MODULE_NAME].ShareType.MOOD,
            sys.modules[CONFIG_MODULE_NAME].TimePeriod.AFTERNOON,
            "qzone_broadcast",
            False,
            "",
        )

        self.assertIn("【QQ 空间说说输出格式】", calls[0]["prompt"])
        self.assertIn("像 QQ 空间说说一样自然分行。", calls[0]["prompt"])
        self.assertNotIn("普通分享两行短句。", calls[0]["prompt"])

    def test_private_user_prompt_checks_relationship_sections(self):
        content_module, _ = _load_daily_share_modules()

        async def call_llm(prompt, system_prompt="", **kwargs):
            return "ok"

        context = types.SimpleNamespace(persona_manager=_PersonaManager(""))
        service = content_module.ContentService(
            {"news_conf": {}, "basic_conf": {}, "context_conf": {}},
            call_llm,
            context=context,
            db_manager=types.SimpleNamespace(),
            news_service=None,
        )

        prompt = service.support._build_user_prompt(
            "", "阿林", "bot-main:FriendMessage:user-test"
        )

        self.assertIn("【关系档案】", prompt)
        self.assertIn("【聊天记忆摘要】", prompt)
        self.assertIn("【近期事件】", prompt)
        self.assertIn("当前对象不能写成第三者", prompt)
        self.assertIn("bot-main:FriendMessage:user-test", prompt)
        self.assertIn("和你一起", prompt)

    async def test_image_prompt_uses_persona_source_text_without_girl_fallback(self):
        _, image_module = _load_daily_share_modules()

        async def call_llm(*args, **kwargs):
            return ""

        context = types.SimpleNamespace(
            persona_manager=_PersonaManager("你的名字叫小舟。性别男，20岁。"),
            get_all_stars=lambda: [],
        )
        service = image_module.ImageService(
            context,
            {"image_conf": {"enable_ai_image": True}},
            call_llm,
        )

        prompt = await service._assemble_final_prompt(
            "今天去咖啡店坐了一会儿。",
            sys.modules[CONFIG_MODULE_NAME].ShareType.MOOD,
            True,
            {"environment": "咖啡店", "lighting": "暖光", "scene_type": "室内公共场所"},
        )

        self.assertIn("画面主体是当前角色本人", prompt)
        self.assertIn("人物形象遵循角色人设原文", prompt)
        self.assertIn("你的名字叫小舟。性别男，20岁。", prompt)
        self.assertNotIn("1个女孩", prompt)

    async def test_image_visual_extraction_keeps_outfit_on_protagonist(self):
        _, image_module = _load_daily_share_modules()
        calls = []

        async def call_llm(prompt, system_prompt="", **kwargs):
            calls.append({"prompt": prompt, "system_prompt": system_prompt})
            return json.dumps(
                {
                    "hair_style": "蓬松短卷发",
                    "hair": "金色短发",
                    "makeup": "浓艳舞台妆",
                    "nails": "黑色尖甲",
                },
                ensure_ascii=False,
            )

        context = types.SimpleNamespace(
            persona_manager=_PersonaManager("你的名字叫小舟。"),
            get_all_stars=lambda: [],
        )
        service = image_module.ImageService(
            context,
            {"image_conf": {"enable_ai_image": True}},
            call_llm,
        )

        visuals = await service._agent_extract_visuals(
            "和阿林去展览馆。",
            "【今日穿搭】浅蓝外套和白裙子\n"
            "【当前外观】发型名称: 松散低马尾 | 发型细节: 黑色中长直发，碎发自然垂落 | "
            "妆容: 清透自然妆 | 美甲: 奶白色短圆甲\n"
            "【关系档案】\n- 阿林：人设线索：朋友",
            share_type=sys.modules[CONFIG_MODULE_NAME].ShareType.MOOD,
            involves_self=True,
        )

        self.assertEqual(visuals["outfit"], "浅蓝外套和白裙子")
        self.assertEqual(visuals["outfit_source"], "daily_life")
        self.assertEqual(visuals["hair_style"], "松散低马尾")
        self.assertEqual(visuals["hair"], "黑色中长直发，碎发自然垂落")
        self.assertEqual(visuals["makeup"], "清透自然妆")
        self.assertEqual(visuals["nails"], "奶白色短圆甲")
        self.assertEqual(visuals["appearance_source"], "daily_life")
        self.assertIn(
            "【今日穿搭】和【当前外观】只属于主角/你本人",
            calls[0]["system_prompt"],
        )
        self.assertIn(
            "其他人物只按文案或关系原文明确写出的外观处理", calls[0]["system_prompt"]
        )
        self.assertIn("优先于角色人设中的固定造型", calls[0]["system_prompt"])
        self.assertIn(
            "【今日穿搭】是主角当前已经穿上的事实",
            calls[0]["system_prompt"],
        )
        self.assertIn("不要描写其他人的衣着", calls[0]["system_prompt"])
        self.assertIn(
            "只描述主角/你本人在 composition 里能看见的穿搭", calls[0]["system_prompt"]
        )
        self.assertIn("不要按分享类型固定镜头", calls[0]["system_prompt"])
        self.assertIn("近景、半身、中景、远景、全景", calls[0]["system_prompt"])
        self.assertIn("composition", calls[0]["system_prompt"])
        self.assertIn("frame_logic", calls[0]["system_prompt"])
        for field in ('"hair_style"', '"hair"', '"makeup"', '"nails"'):
            self.assertIn(field, calls[0]["system_prompt"])
        self.assertIn("不把生活状态里未入镜的内容写进画面词", calls[0]["system_prompt"])
        self.assertNotIn("脚部状态必须写进 outfit", calls[0]["system_prompt"])

    async def test_image_visual_extraction_keeps_explicit_outfit_over_sleepwear(self):
        _, image_module = _load_daily_share_modules()
        calls = []

        async def call_llm(prompt, system_prompt="", **kwargs):
            calls.append({"prompt": prompt, "system_prompt": system_prompt})
            return json.dumps(
                {
                    "environment": "卧室床边",
                    "composition": "半身近景",
                    "outfit": "浅色轻薄睡衣领口",
                    "outfit_logic": "当前是深夜卧床场景",
                },
                ensure_ascii=False,
            )

        context = types.SimpleNamespace(
            persona_manager=_PersonaManager("你的名字叫小舟。"),
            get_all_stars=lambda: [],
        )
        service = image_module.ImageService(
            context,
            {"image_conf": {"enable_ai_image": True}},
            call_llm,
        )
        current_outfit = (
            "水手领荷叶边露脐短上衣，白色，浅蓝色水手翻领；双层荷叶边蝴蝶结超短裙裤"
        )

        visuals = await service._agent_extract_visuals(
            "别熬太晚啦，快睡吧，晚安。",
            f"【今日穿搭】{current_outfit}\n【当前外观】发型名称: 自然披散长发",
            share_type=sys.modules[CONFIG_MODULE_NAME].ShareType.GREETING,
            involves_self=True,
        )

        self.assertEqual(visuals["outfit"], current_outfit)
        self.assertEqual(visuals["outfit_source"], "daily_life")
        self.assertEqual(visuals["outfit_logic"], "使用生活插件明确提供的当前穿搭")
        self.assertEqual(visuals["hair_style"], "自然披散长发")
        self.assertEqual(visuals["appearance_source"], "daily_life")
        self.assertIn("不得因场景或时段替换成睡衣", calls[0]["system_prompt"])

        inferred = await service._agent_extract_visuals(
            "别熬太晚啦，快睡吧，晚安。",
            "【今日天气】多云",
            share_type=sys.modules[CONFIG_MODULE_NAME].ShareType.GREETING,
            involves_self=True,
        )

        self.assertEqual(inferred["outfit"], "浅色轻薄睡衣领口")
        self.assertNotIn("outfit_source", inferred)

    async def test_image_prompt_prefers_daily_life_dynamic_appearance(self):
        _, image_module = _load_daily_share_modules()

        async def call_llm(*args, **kwargs):
            return "东亚女性，黑色长卷发，棕色眼睛"

        context = types.SimpleNamespace(
            persona_manager=_PersonaManager("你的名字叫小舟，平时留黑色长卷发。"),
            get_all_stars=lambda: [],
        )
        service = image_module.ImageService(
            context,
            {"image_conf": {"enable_ai_image": True}},
            call_llm,
        )

        prompt = await service._assemble_final_prompt(
            "今天去看展。",
            sys.modules[CONFIG_MODULE_NAME].ShareType.MOOD,
            True,
            {
                "environment": "展览馆",
                "lighting": "柔和室内光",
                "hair_style": "松散低马尾",
                "hair": "黑色中长直发，碎发自然垂落",
                "makeup": "清透自然妆",
                "nails": "奶白色短圆甲",
                "outfit": "浅蓝外套和白裙子",
                "outfit_source": "daily_life",
                "appearance_source": "daily_life",
            },
        )

        self.assertIn("东亚女性，黑色长卷发，棕色眼睛", prompt)
        self.assertIn("角色参考图身份锚点（最高优先级）", prompt)
        self.assertIn("脸型、五官比例、眼睛、鼻子、嘴唇、肤色、年龄感和体态", prompt)
        self.assertIn("当天动态外观硬性约束", prompt)
        self.assertIn("只覆盖发型、妆容、美甲和服装", prompt)
        self.assertIn("发型名称：松散低马尾", prompt)
        self.assertIn("发型细节：黑色中长直发，碎发自然垂落", prompt)
        self.assertIn("妆容：清透自然妆", prompt)
        self.assertIn("美甲：奶白色短圆甲", prompt)
        self.assertIn("当前穿搭硬性约束", prompt)
        self.assertIn("不得因时段或场景替换为睡衣或其他服装", prompt)
        self.assertIn("浅蓝外套和白裙子", prompt)

    async def test_image_self_judge_prompt_uses_first_person_hidden_reasoning(self):
        _, image_module = _load_daily_share_modules()
        calls = []

        async def call_llm(prompt, system_prompt="", **kwargs):
            calls.append({"prompt": prompt, "system_prompt": system_prompt})
            return "YES"

        context = types.SimpleNamespace(
            persona_manager=_PersonaManager("你的名字叫小舟。"),
            get_all_stars=lambda: [],
        )
        service = image_module.ImageService(
            context,
            {"image_conf": {"enable_ai_image": True}},
            call_llm,
        )

        result = await service._check_involves_self(
            "我坐在广场长椅上吃甜筒，走走停停有点舍不得回去。",
            sys.modules[CONFIG_MODULE_NAME].ShareType.MOOD,
        )

        self.assertTrue(result)
        self.assertIn("隐藏推理口吻", calls[0]["system_prompt"])
        self.assertIn("只保留一句以“我”开头的角色内心判断", calls[0]["system_prompt"])
        self.assertIn("不要写“我们分析”“我们根据”", calls[0]["system_prompt"])

    async def test_image_prompt_uses_llm_selected_composition(self):
        _, image_module = _load_daily_share_modules()

        async def call_llm(*args, **kwargs):
            return ""

        context = types.SimpleNamespace(
            persona_manager=_PersonaManager("你的名字叫小舟。"),
            get_all_stars=lambda: [],
        )
        service = image_module.ImageService(
            context,
            {"image_conf": {"enable_ai_image": True}},
            call_llm,
        )

        prompt = await service._assemble_final_prompt(
            "窝在地毯上翻手账。",
            sys.modules[CONFIG_MODULE_NAME].ShareType.MOOD,
            True,
            {
                "environment": "客厅地毯旁",
                "lighting": "暖黄台灯",
                "scene_type": "家里",
                "temperature_feel": "温暖",
                "weather_condition": "雨",
                "composition": "远景生活照，人物靠窗坐在客厅角落，室内环境占主要画面",
                "frame_logic": "文案重点是雨夜和安静氛围，所以用远景保留房间、窗外雨和人物关系。",
                "outfit": "浅灰色长袖睡衣上衣，头发半湿",
                "action": "坐在窗边翻活页本",
            },
        )

        self.assertIn("远景生活照", prompt)
        self.assertIn("室内环境占主要画面", prompt)
        self.assertIn("雨夜和安静氛围", prompt)
        self.assertIn("浅灰色长袖睡衣上衣", prompt)
        self.assertIn("头发半湿", prompt)
        self.assertIn("坐在窗边翻活页本", prompt)
        self.assertNotIn("脸部或上半身近景", prompt)

    async def test_image_prompt_accepts_full_scene_composition(self):
        _, image_module = _load_daily_share_modules()

        async def call_llm(*args, **kwargs):
            return ""

        context = types.SimpleNamespace(
            persona_manager=_PersonaManager("你的名字叫小舟。"),
            get_all_stars=lambda: [],
        )
        service = image_module.ImageService(
            context,
            {"image_conf": {"enable_ai_image": True}},
            call_llm,
        )

        prompt = await service._assemble_final_prompt(
            "路过街边看到新闻大屏。",
            sys.modules[CONFIG_MODULE_NAME].ShareType.NEWS,
            True,
            {
                "environment": "街边",
                "lighting": "自然光",
                "scene_type": "室外",
                "temperature_feel": "舒适",
                "weather_condition": "晴",
                "composition": "全景街景，人物与新闻大屏同处画面",
                "frame_logic": "文案重点是街边大屏和路过感，所以用全景呈现人物、街道和屏幕关系。",
                "outfit": "白色衬衫配牛仔裤和白色运动鞋",
                "action": "站在街边看屏幕",
            },
        )

        self.assertIn("全景街景", prompt)
        self.assertIn("新闻大屏同处画面", prompt)
        self.assertIn("街边大屏和路过感", prompt)
        self.assertIn("白色衬衫", prompt)
        self.assertIn("牛仔裤", prompt)
        self.assertIn("白色运动鞋", prompt)

    async def test_image_non_character_mode_rejects_person_composition(self):
        _, image_module = _load_daily_share_modules()

        async def call_llm(*args, **kwargs):
            return ""

        context = types.SimpleNamespace(
            persona_manager=_PersonaManager("你的名字叫小舟。"),
            get_all_stars=lambda: [],
        )
        service = image_module.ImageService(
            context,
            {"image_conf": {"enable_ai_image": True}},
            call_llm,
        )
        visuals = service._enforce_visual_mode(
            {
                "subject": "一杯冒着热气的咖啡",
                "environment": "窗边木桌",
                "lighting": "清晨自然光",
                "composition": "半身人像中景，主角手中捧着咖啡",
                "frame_logic": "突出主角神态和手部动作",
            },
            False,
        )

        prompt = await service._assemble_final_prompt(
            "清晨喝杯咖啡。",
            sys.modules[CONFIG_MODULE_NAME].ShareType.MOOD,
            False,
            visuals,
        )

        self.assertEqual(visuals["visual_mode"], "object")
        self.assertEqual(visuals["composition"], "")
        self.assertIn("无人, 静物", prompt)
        self.assertIn("自然静物构图", prompt)
        self.assertNotIn("主角", prompt)
        self.assertNotIn("半身人像", prompt)

    async def test_image_landscape_mode_rejects_person_composition(self):
        _, image_module = _load_daily_share_modules()

        async def call_llm(*args, **kwargs):
            return ""

        context = types.SimpleNamespace(
            persona_manager=_PersonaManager("你的名字叫小舟。"),
            get_all_stars=lambda: [],
        )
        service = image_module.ImageService(
            context,
            {"image_conf": {"enable_ai_image": True}},
            call_llm,
        )
        visuals = service._enforce_visual_mode(
            {
                "subject": "无",
                "environment": "雨后的城市街道",
                "composition": "人物全身远景，主角走在街道中央",
            },
            False,
        )

        prompt = await service._assemble_final_prompt(
            "雨停了。",
            sys.modules[CONFIG_MODULE_NAME].ShareType.MOOD,
            False,
            visuals,
        )

        self.assertEqual(visuals["visual_mode"], "landscape")
        self.assertIn("无人, 风景", prompt)
        self.assertIn("自然风景构图", prompt)
        self.assertNotIn("主角", prompt)
        self.assertNotIn("人物全身", prompt)

    async def test_image_decision_log_does_not_include_provider_mode(self):
        _, image_module = _load_daily_share_modules()
        capture_logger = _CaptureLogger()
        image_module.logger = capture_logger

        async def call_llm(*args, **kwargs):
            return ""

        context = types.SimpleNamespace(
            persona_manager=_PersonaManager("你的名字叫小舟。"),
            get_all_stars=lambda: [],
        )
        service = image_module.ImageService(
            context,
            {
                "image_conf": {"enable_ai_image": True},
            },
            call_llm,
        )

        async def check_involves_self(content, share_type, target_umo=None):
            return True

        async def extract_visuals(*args, **kwargs):
            return {}

        service._check_involves_self = check_involves_self
        service._agent_extract_visuals = extract_visuals

        await service.generate_image(
            "今天去咖啡店坐了一会儿。", sys.modules[CONFIG_MODULE_NAME].ShareType.MOOD
        )

        decision_log = next(item for item in capture_logger.infos if "配图决策" in item)
        self.assertIn("人物+场景", decision_log)
        self.assertNotIn("形象模式", decision_log)


if __name__ == "__main__":
    unittest.main()
