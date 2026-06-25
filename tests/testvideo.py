import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "daily_share_video_testpkg"
CORE_PACKAGE_NAME = f"{PACKAGE_NAME}.core"
IMAGE_PACKAGE_NAME = f"{CORE_PACKAGE_NAME}.image"
VIDEO_MODULE_NAME = f"{IMAGE_PACKAGE_NAME}.motion"


class _Logger:
    def debug(self, *args, **kwargs):
        return None


def _extract_json_object(text: str) -> str:
    text = str(text or "").replace("```json", "").replace("```", "").strip()
    start = text.find("{")
    end = text.rfind("}")
    return text[start : end + 1] if start >= 0 and end >= start else text


def _install_stub_module(name: str, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _load_video_module():
    for name in list(sys.modules):
        if name.startswith(PACKAGE_NAME) or name in {"astrbot", "astrbot.api"}:
            sys.modules.pop(name, None)

    package = _install_stub_module(PACKAGE_NAME)
    package.__path__ = [str(ROOT)]

    core_package = _install_stub_module(CORE_PACKAGE_NAME)
    core_package.__path__ = [str(ROOT / "core")]

    image_package = _install_stub_module(IMAGE_PACKAGE_NAME)
    image_package.__path__ = [str(ROOT / "core" / "image")]

    _install_stub_module("astrbot")
    _install_stub_module("astrbot.api", logger=_Logger())
    _install_stub_module(f"{IMAGE_PACKAGE_NAME}.visual", _extract_json_object=_extract_json_object)

    spec = importlib.util.spec_from_file_location(VIDEO_MODULE_NAME, ROOT / "core" / "image" / "motion.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[VIDEO_MODULE_NAME] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class VideoPromptTests(unittest.TestCase):
    def test_motion_fallback_keeps_camera_motion_and_life_details(self):
        mod = _load_video_module()

        fallback = mod.VIDEO_MOTION_FALLBACK

        self.assertIn("轻微镜头运动", fallback)
        self.assertIn("缓慢推近", fallback)
        self.assertIn("缓慢横移", fallback)
        self.assertIn("手持呼吸感", fallback)
        self.assertIn("不改变人物比例或画面关系", fallback)

    def test_sound_fallback_keeps_life_sound_piano_and_dialogue_direction(self):
        mod = _load_video_module()

        fallback = mod.VIDEO_SOUND_FALLBACK

        self.assertIn("环境声", fallback)
        self.assertIn("动作声", fallback)
        self.assertIn("背景声", fallback)
        self.assertIn("台词", fallback)
        self.assertIn("禁止旁白、画外音、解说或朗读文案", fallback)

    def test_video_design_system_prompt_no_longer_pushes_empty_sound(self):
        mod = _load_video_module()

        class Service(mod.ImageVideoMixin):
            def __init__(self):
                self.system_prompt = ""

            async def _call_llm(self, user_prompt, system_prompt, **kwargs):
                self.system_prompt = system_prompt
                return (
                    '{"motion":"女孩轻轻抬眼，嘴唇自然动一下并与台词同步",'
                    '"sound":"窗外风声、杯子轻响，轻柔背景声铺底，女孩低声说：今天这样也挺好。"}'
                )

        service = Service()
        motion, sound = asyncio.run(
            service._build_video_design_prompts(
                "年轻女孩坐在窗边，手边有一杯热茶",
                "今天这样也挺好",
            )
        )

        self.assertIn("台词同步", motion)
        self.assertIn("轻柔背景声", sound)
        self.assertIn("motion 默认要包含自然镜头运动", service.system_prompt)
        self.assertIn("轻微推近、缓慢横移或少量手持呼吸感", service.system_prompt)
        self.assertIn("不要默认写静止镜头", service.system_prompt)
        self.assertIn("人物不要出现明显说话口型", service.system_prompt)
        self.assertIn("默认考虑环境声、动作声和轻柔背景声", service.system_prompt)
        self.assertIn("不要默认写无人声、无背景音乐", service.system_prompt)
        self.assertIn("禁止旁白、画外音、解说或朗读文案", service.system_prompt)
        self.assertNotIn("可以几乎静止", service.system_prompt)
        self.assertNotIn("不默认背景声，不默认人声", service.system_prompt)


if __name__ == "__main__":
    unittest.main()
