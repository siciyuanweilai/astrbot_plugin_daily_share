import importlib
import types
import unittest
from unittest.mock import AsyncMock, patch

from . import testfailure, testidentity, testmedia, testqzonecomment
from .testqzone import _load_qzone_service, _new_qzone_service


class PromptPrefixTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        testidentity._clear_modules()

    async def test_content_prefix_survives_time_target_and_evidence_changes(self):
        module, _ = testidentity._load_daily_share_modules()
        core_package = module.__package__.rsplit(".", 1)[0]
        config = importlib.import_module(core_package + ".config")
        prompts = importlib.import_module(core_package + ".prompt")
        calls = []

        async def generate(prompt, **kwargs):
            calls.append(prompt)
            return "【本次主题】正文"

        service = module.ContentService(
            {"basic_conf": {"share_output_format": "两行短句"}},
            generate,
            context=types.SimpleNamespace(),
            db_manager=types.SimpleNamespace(record_topic=AsyncMock()),
            news_service=object(),
        )
        for task in ("greeting", "mood", "knowledge", "recommendation", "news"):
            with self.subTest(task=task):
                captured = []
                for token in ("A", "B"):
                    ctx = {
                        "date_str": f"2026-10-{token}",
                        "time_str": f"time-{token}",
                        "period_label": "下午",
                        "is_group": False,
                        "target_id": f"bot:FriendMessage:{token}",
                        "nickname": "",
                        "detect_name": f"person-{token}",
                        "life_hint": f"life-{token}",
                        "structured_history_hint": f"history-{token}",
                        "system_prompt": "persona",
                        "output_format_hint": "两行短句",
                    }
                    service.topic._agent_brainstorm_topic = AsyncMock(
                        return_value=f"keyword-{token}"
                    )
                    service.recommendation._fetch_content_reference = AsyncMock(
                        return_value=f"evidence-{token}"
                    )
                    if task == "news":
                        common = prompts.build_common_content_rules(
                            is_group=False,
                            is_qzone=False,
                            date_text=ctx["date_str"],
                            time_text=ctx["time_str"],
                            period_label="下午",
                            action="分享新闻",
                            include_time=False,
                        )
                        calls.append(
                            service.news._build_news_prompt(
                                ctx=ctx,
                                source_name="新闻源",
                                share_count=1,
                                target_label="私聊",
                                user_info_prompt=f"person-{token}",
                                news_text=f"evidence-{token}",
                                common_rules=common,
                                dynamics_prompt="",
                                is_group=False,
                            )
                        )
                    elif task in ("greeting", "mood"):
                        await getattr(service.social, "_gen_" + task)(
                            config.TimePeriod.AFTERNOON, ctx
                        )
                    elif task == "knowledge":
                        await service.knowledge._gen_knowledge(ctx)
                    else:
                        await service.recommendation._gen_rec(ctx)
                    captured.append(calls[-1])
                    fixed, dynamic = calls[-1].split("【本次输入】", 1)
                    for label in ("person", "life", "history", "time"):
                        self.assertIn(f"{label}-{token}", dynamic)
                        self.assertNotIn(f"{label}-{token}", fixed)
                        other = "B" if token == "A" else "A"
                        self.assertNotIn(f"{label}-{other}", calls[-1])
                    self.assertIn("隐私边界", fixed)
                    self.assertIn("事实边界", fixed)
                    self.assertIn("两行短句", fixed)
                    if task in ("knowledge", "recommendation", "news"):
                        self.assertIn(f"evidence-{token}", dynamic)
                self.assertEqual(
                    captured[0].split("【本次输入】")[0],
                    captured[1].split("【本次输入】")[0],
                )

    def test_qzone_post_types_share_rules_without_reusing_private_material(self):
        module, _ = testidentity._load_daily_share_modules()
        prompts = importlib.import_module(
            module.__package__.rsplit(".", 1)[0] + ".prompt"
        )
        results = []
        for token in ("A", "B"):
            ctx = {
                "date_str": token,
                "time_str": token,
                "period_label": "下午",
                "life_hint": f"current-{token}",
            }
            results.append(
                prompts.build_qzone_post_prompt(ctx, f"task-{token}", f"facts-{token}")
            )
        self.assertEqual(
            results[0].split("【本次输入】")[0],
            results[1].split("【本次输入】")[0],
        )
        for token, result in zip(("A", "B"), results):
            self.assertIn(f"current-{token}", result)
            self.assertIn(f"task-{token}", result)
            self.assertIn(f"facts-{token}", result)

    async def test_visual_rules_are_shared_across_person_and_nonperson_tasks(self):
        _, module = testidentity._load_daily_share_modules()
        calls = []

        async def generate(prompt, system_prompt="", **kwargs):
            calls.append((prompt, system_prompt))
            return "{}"

        service = module.ImageService(types.SimpleNamespace(), {}, generate)
        for involves_self in (False, True):
            await service._agent_extract_visuals(
                "current scene", None, involves_self=involves_self
            )
        self.assertEqual(calls[0][1], calls[1][1])
        self.assertIn("不加入人物", calls[0][0])
        self.assertIn("visual_mode 填写 person", calls[1][0])
        self.assertNotIn("不加入人物", calls[1][0])


class UsageReportingTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_usage_is_excluded_and_provider_totals_stay_separate(self):
        module = testmedia._load_main_module()
        service = module.LlmService(types.SimpleNamespace(), {}, lambda: False)
        for usage in (None, {}, {"input_cached": "unknown"}):
            service.record_token_usage(types.SimpleNamespace(usage=usage), "unknown")
        service.record_token_usage(
            types.SimpleNamespace(usage={"input_other": 20, "input_cached": 80}),
            "a",
        )
        service.record_token_usage(
            types.SimpleNamespace(usage={"input_other": 100, "output": 5}), "b"
        )
        self.assertEqual(service.token_usage["reported_calls"], 2)
        self.assertEqual(service.token_usage["input_tokens"], 200)
        self.assertEqual(service.token_usage["cached_input_tokens"], 80)
        self.assertNotIn("unknown", service.token_usage_by_provider)
        self.assertEqual(service.token_usage_by_provider["a"]["cached_calls"], 1)
        self.assertEqual(service.token_usage_by_provider["b"]["cached_calls"], 0)

    async def test_vision_reports_actual_provider_usage_without_retrying_for_metrics(
        self,
    ):
        module = testmedia._load_main_module()
        service = module.LlmService(types.SimpleNamespace(), {}, lambda: False)
        comment_module, _ = testqzonecomment._load_auto_comment_module()
        sight = importlib.import_module(comment_module.__package__ + ".interact.sight")
        response = types.SimpleNamespace(
            completion_text="窗边的猫",
            usage={"input_other": 50, "input_cached": 50, "output": 5},
        )
        context = types.SimpleNamespace(llm_generate=AsyncMock(return_value=response))
        owner = types.SimpleNamespace(
            plugin=types.SimpleNamespace(context=context, llm_service=service)
        )
        with (
            patch.object(
                sight,
                "_qzone_vision_provider_candidates",
                AsyncMock(return_value=[("vision", "qzone_vision")]),
            ),
            patch.object(sight, "_qzone_provider_label", return_value="vision"),
        ):
            self.assertEqual(
                await sight._describe_qzone_image(owner, "https://example.com/a.jpg"),
                "窗边的猫",
            )
            self.assertEqual(
                service.token_usage_by_provider["vision"]["input_tokens"], 100
            )
            service.record_token_usage = lambda *args, **kwargs: (_ for _ in ()).throw(
                RuntimeError("metric failure")
            )
            self.assertEqual(
                await sight._describe_qzone_image(owner, "https://example.com/b.jpg"),
                "窗边的猫",
            )
        self.assertEqual(context.llm_generate.await_count, 2)


class PublishFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_submission_never_falls_back_or_relogs_in(self):
        module = testmedia._load_main_module()
        plugin = testmedia._new_plugin_with_support(module)
        errors = importlib.import_module(module.__package__ + ".core.space.errors")
        plugin.qzone_service = types.SimpleNamespace(
            context=AsyncMock(
                return_value=types.SimpleNamespace(uin=101, nickname="bot")
            ),
            publish_post=AsyncMock(
                side_effect=errors.QzonePublishUnknownError("提交状态未知 Cookie 401")
            ),
            invalidate=unittest.mock.Mock(),
        )
        with self.assertRaises(errors.QzonePublishUnknownError):
            await plugin.publish_qzone("text", [b"image"])
        self.assertEqual(plugin.qzone_service.publish_post.await_count, 1)
        plugin.qzone_service.invalidate.assert_not_called()

        tasks = testfailure._load_tasks_module()
        errors = importlib.import_module(
            testfailure.CORE_PACKAGE_NAME + ".space.errors"
        )
        plugin = testfailure._Plugin()
        plugin.publish_qzone = AsyncMock(
            side_effect=errors.QzonePublishUnknownError("提交状态未知")
        )
        manager = testfailure._new_manager(tasks, plugin)
        with self.assertRaises(errors.QzonePublishUnknownError):
            await manager.qzone_share._publish_qzone_best_effort(
                text="text", images=[b"image"]
            )
        self.assertEqual(plugin.publish_qzone.await_count, 1)

    async def test_upload_failure_is_marked_before_any_post_is_submitted(self):
        module = _load_qzone_service()
        service = _new_qzone_service(module, types.SimpleNamespace())
        service.context = AsyncMock(return_value=types.SimpleNamespace(uin=101))
        service._upload_image = AsyncMock(side_effect=RuntimeError("upload failure"))
        service._submit_post = AsyncMock()
        with self.assertRaises(module.QzoneImageUploadError):
            await service.publish_post(text="text", images=[b"image"])
        service._submit_post.assert_not_called()

    async def test_portal_preserves_safe_upload_failure(self):
        module = testmedia._load_main_module()
        plugin = testmedia._new_plugin_with_support(module)
        errors = importlib.import_module(module.__package__ + ".core.space.errors")
        plugin.qzone_service = types.SimpleNamespace(
            context=AsyncMock(
                return_value=types.SimpleNamespace(uin=101, nickname="bot")
            ),
            publish_post=AsyncMock(
                side_effect=errors.QzoneImageUploadError("upload failed")
            ),
        )
        with self.assertRaises(errors.QzoneImageUploadError):
            await plugin.publish_qzone("text", [b"image"])
        self.assertEqual(plugin.qzone_service.publish_post.await_count, 1)

    async def test_unspecified_publish_failure_does_not_trigger_another_post(self):
        tasks = testfailure._load_tasks_module()
        plugin = testfailure._Plugin()
        plugin.publish_qzone = AsyncMock(side_effect=RuntimeError("unknown failure"))
        manager = testfailure._new_manager(tasks, plugin)
        with self.assertRaisesRegex(RuntimeError, "unknown failure"):
            await manager.qzone_share._publish_qzone_best_effort(
                text="text", images=[b"image"]
            )
        self.assertEqual(plugin.publish_qzone.await_count, 1)
