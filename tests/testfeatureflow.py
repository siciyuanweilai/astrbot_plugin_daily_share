"""功能体检修复：材料贯穿、真实进展、历史检索和新闻快照复用。"""

import importlib
import json
import types
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from . import testidentity as identity
from . import testliving as fixtures


class LivingFeatureTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.LivingTests.asyncSetUp
    consider = fixtures.LivingTests.consider
    state = fixtures.LivingTests.state
    expire_share_backoff = fixtures.LivingTests.expire_share_backoff

    async def test_new_progress_reopens_a_seen_activity_but_timestamps_do_not(self):
        self.data["current_facts"]["current_action"] = {}
        row = {
            "event_id": "baking-1",
            "title": "一起烘焙",
            "state": "active",
            "progress": "刚开始和面",
            "at": datetime.now(self.material.SHANGHAI).isoformat(),
        }
        self.data["continuity"] = {"activities": [row]}
        await self.consider()
        row["at"] = datetime.now(self.material.SHANGHAI).isoformat()
        row["progress"] = "刚开始和面。"
        self.expire_share_backoff()
        await self.consider()
        self.assertEqual(self.plugin.call_llm.await_count, 1)
        row["progress"] = "已经发酵完成，准备入炉"
        await self.consider()
        self.assertEqual(self.plugin.call_llm.await_count, 2)

    async def test_upgrade_baselines_old_seen_ids_without_replaying_them(self):
        self.data["current_facts"]["current_action"] = {}
        row = {
            "title": "烘焙",
            "state": "active",
            "progress": "和面",
            "at": datetime.now(self.material.SHANGHAI).isoformat(),
        }
        self.data["continuity"] = {"activities": [row]}
        material = self.material.share_material(
            self.data, datetime.now(self.material.SHANGHAI)
        )[0]
        self.plugin.db.state[self.living_module._STATE] = {
            self.target: {"seen": [material["legacy_id"]]}
        }
        await self.consider()
        self.plugin.call_llm.assert_not_awaited()
        row["progress"] = "烤好了"
        await self.consider()
        self.plugin.call_llm.assert_awaited_once()

    async def test_news_snapshot_is_shared_and_selected_article_reaches_both_loaders(
        self,
    ):
        self.plugin.config["news_conf"] = {
            "nycnm_api_key": "test-only",
            "enable_news_api": True,
        }
        self.data["continuity"] = {"interests": [{"label": "摄影", "state": "active"}]}
        news = self.manager.schedule.news_service
        news.get_hot_news = AsyncMock(
            return_value=(
                [
                    {
                        "title": "摄影镜头新设计",
                        "description": "新型镜头的光学设计",
                        "url": "https://example.test/photo",
                    },
                    {"title": "无关热搜", "url": "https://example.test/other"},
                ],
                "zhihu",
            )
        )
        helper = importlib.import_module(
            fixtures.fixtures.TASKS_MODULE_NAME + ".scheduler.headlines"
        )
        now = datetime.now(self.material.SHANGHAI)
        rows = await helper.news_materials(self.living, self.data, now)
        again = await helper.news_materials(
            self.living, self.data, now + timedelta(minutes=1)
        )
        self.assertEqual(rows, again)
        news.get_hot_news.assert_awaited_once()
        self.assertEqual(len(rows), 1)
        token = self.material.current_opportunity.set(
            {"target": self.target, "materials": rows}
        )
        try:
            selected = self.material.opportunity_news(self.target)
            ok, result = await self.manager.share.news.load_news(
                uid=self.target,
                stype=self.module.ShareType.NEWS,
                history_source="life",
                progress_id="",
            )
            self.assertTrue(ok)
            self.assertEqual(result, selected)
        finally:
            self.material.current_opportunity.reset(token)
        token = self.material.current_opportunity.set(
            {"target": "qzone_broadcast", "materials": rows}
        )
        try:
            ok, result = await self.manager.qzone_share._load_qzone_news_data(
                history_source="life", progress_id=""
            )
            self.assertTrue(ok)
            self.assertEqual(result, selected)
        finally:
            self.material.current_opportunity.reset(token)
        news.get_hot_news.assert_awaited_once()

    async def test_news_failure_and_disabled_mode_do_not_poll_per_target(self):
        self.plugin.config["news_conf"] = {"nycnm_api_key": "test-only"}
        self.data["continuity"] = {"interests": [{"label": "摄影", "state": "active"}]}
        helper = importlib.import_module(
            fixtures.fixtures.TASKS_MODULE_NAME + ".scheduler.headlines"
        )
        news = self.manager.schedule.news_service
        news.get_hot_news = AsyncMock(return_value=None)
        now = datetime.now(self.material.SHANGHAI)
        for _ in range(4):
            self.assertEqual(
                await helper.news_materials(self.living, self.data, now), []
            )
        news.get_hot_news.assert_awaited_once()
        self.plugin.config["news_conf"]["enable_news_api"] = False
        await helper.news_materials(self.living, self.data, now + timedelta(hours=1))
        news.get_hot_news.assert_awaited_once()

    async def test_observation_is_recorded_once_with_wait_and_like_is_separate(self):
        self.bridge.record_public_activity = AsyncMock(return_value=True)
        self.plugin.call_llm.return_value = '{"decision":"wait"}'
        await self.intent.wants_interaction(self.owner, "like", self.post)
        self.expire_interaction_backoff = (
            fixtures.LivingTests.expire_interaction_backoff.__get__(self)
        )
        self.expire_interaction_backoff()
        await self.intent.wants_interaction(self.owner, "like", self.post)
        self.bridge.record_public_activity.assert_awaited_once()
        receipt = self.bridge.record_public_activity.await_args.args[0]
        self.assertEqual(receipt["scene"], "qzone_observation")
        self.assertEqual(receipt["post_context"]["content"], self.post.text)
        self.assertNotIn("我：", receipt["content"])


class TopicFeatureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        content, _ = identity._load_daily_share_modules()
        self.service = content.ContentService(
            {"news_conf": {}, "basic_conf": {}, "context_conf": {}},
            AsyncMock(),
            context=types.SimpleNamespace(),
            db_manager=types.SimpleNamespace(
                get_used_topics=AsyncMock(return_value=[])
            ),
            news_service=types.SimpleNamespace(),
        )
        self.service.knowledge_cats = {"生活": ["烘焙"]}
        self.service.rec_cats = {"书籍": ["烹饪"]}
        self.service.support._call_llm = AsyncMock()
        self.ctx = {
            "target_id": "target",
            "is_group": False,
            "system_prompt": "人设",
            "share_materials": [{"id": "baking", "title": "面包发酵失败"}],
        }

    async def test_selected_fact_reaches_both_topic_prompts(self):
        for kind, category, tag in [
            ("knowledge", "生活", "烘焙"),
            ("rec", "书籍", "烹饪"),
        ]:
            self.service.support._call_llm.return_value = json.dumps(
                {
                    "category": category,
                    "tag": tag,
                    "topic": "面包发酵",
                    "evidence_ids": ["baking"],
                }
            )
            result = await self.service.topic.select_life_topic(self.ctx, kind=kind)
            self.assertEqual(result[2], "面包发酵")
            self.assertIn(
                "面包发酵失败",
                self.service.support._call_llm.await_args.kwargs["prompt"],
            )

    async def test_invalid_evidence_or_unrelated_category_is_rejected(self):
        for category, ids in [("生活", ["invented"]), ("不存在", ["baking"])]:
            self.service.support._call_llm.return_value = json.dumps(
                {
                    "category": category,
                    "tag": "烘焙",
                    "topic": "话题",
                    "evidence_ids": ids,
                }
            )
            self.assertIsNone(
                await self.service.topic.select_life_topic(self.ctx, kind="knowledge")
            )

    async def test_no_related_topic_does_not_fall_back_to_random_exploration(self):
        self.service.topic.select_life_topic = AsyncMock(return_value=None)
        self.service.topic._agent_brainstorm_topic = AsyncMock()
        self.assertIsNone(await self.service.knowledge._gen_knowledge(self.ctx))
        self.assertIsNone(await self.service.recommendation._gen_rec(self.ctx))
        self.service.topic._agent_brainstorm_topic.assert_not_awaited()


class HistoryFeatureTests(unittest.TestCase):
    def setUp(self):
        identity._load_daily_share_modules()
        self.module = importlib.import_module(
            identity.CORE_PACKAGE_NAME + ".context.relevance"
        )

    def test_relevant_older_messages_are_selected_with_original_metadata(self):
        older = [{"content": "无关闲聊", "timestamp": i} for i in range(40)]
        evidence = {
            "content": "面包发酵时温度要稳定",
            "timestamp": "昨天",
            "sender_name": "朋友",
        }
        older.insert(0, evidence)
        self.assertEqual(
            self.module.relevant_messages(older, "面包发酵失败"), [evidence]
        )
        self.assertEqual(self.module.relevant_messages(older, "今天现在"), [])

    def test_retrieved_older_quote_enters_prompt_with_its_original_time(self):
        from .testcontext import _service

        _, service = _service()
        messages = [
            {
                "role": "user",
                "name": "朋友",
                "content": "面包发酵时温度要稳定",
                "timestamp": "2026-10-28T12:00:00",
            }
        ]
        messages.extend({"role": "user", "content": f"无关闲聊{i}"} for i in range(40))
        prompt = service.format_structured_history_context(
            {"messages": messages}, query="面包发酵失败"
        )
        self.assertIn("面包发酵时温度要稳定", prompt)
        self.assertIn("2026-10-28 12:00:00", prompt)
        self.assertIn("较早原话", prompt)
        self.assertNotIn("无关闲聊0", prompt)

    def test_only_confirmed_history_is_labelled_as_past_and_bounded(self):
        prompt = self.module.recent_share_prompt(
            [
                {
                    "content": "确认分享",
                    "success": True,
                    "timestamp": "昨天",
                    "share_type": "mood",
                },
                {"content": "失败正文不能进入", "success": False},
            ]
        )
        self.assertIn("确认分享", prompt)
        self.assertIn("昨天", prompt)
        self.assertIn("不是当前生活事实", prompt)
        self.assertNotIn("失败正文", prompt)


class NewsCountFeatureTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_prompt_cannot_request_more_news_than_selected(self):
        content, _ = identity._load_daily_share_modules()
        service = content.ContentService(
            {
                "news_conf": {"news_share_count": 2},
                "basic_conf": {},
                "context_conf": {},
            },
            AsyncMock(),
            context=types.SimpleNamespace(),
            db_manager=types.SimpleNamespace(),
            news_service=types.SimpleNamespace(),
        )
        service.news._collect_news_backgrounds = AsyncMock(
            return_value=[("摄影镜头", "真实摘要")]
        )
        service.support._generate_qzone_post = AsyncMock(return_value="分享摄影新闻")
        result = await service.news._gen_news(
            ([{"title": "摄影镜头"}], "zhihu"),
            {"is_group": False, "is_qzone_post": True, "target_id": "qzone_broadcast"},
        )
        self.assertEqual(result, "分享摄影新闻")
        self.assertIn(
            "1条新闻", service.support._generate_qzone_post.await_args.args[1]
        )
