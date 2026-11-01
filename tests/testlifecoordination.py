"""跨插件共享节奏的公开契约与结构化事实消费。"""
import asyncio
import importlib
import json
import time
import unittest
from datetime import datetime
from unittest.mock import AsyncMock

from tests import testsharepacing as fixtures


class CoordinationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.case = fixtures.PacingTests()
        self.case.setUp()
        self.pacing = self.case.pacing
        self.plugin = self.case.plugin
        self.target = self.case.target

    async def test_life_claim_blocks_share_and_same_user_bili_but_not_other_user(self):
        gate = await self.pacing.coordinate(self.target, owner="life:one", action="submit")
        self.assertTrue(gate["ready"])
        self.assertFalse((await self.pacing.check(self.target))["ready"])
        self.assertFalse((await self.pacing.coordinate(self.target, owner="bili:two", action="submit"))["ready"])
        self.assertTrue((await self.pacing.coordinate("qq:FriendMessage:other"))["ready"])

    async def test_share_claim_blocks_life_without_recursive_context_read(self):
        await self.case.record(age=60)
        self.plugin.daily_life_bridge.get_share_context.reset_mock()
        gate = await self.pacing.coordinate(self.target, rhythm={"last_received_at": 0})
        self.assertFalse(gate["ready"])
        self.plugin.daily_life_bridge.get_share_context.assert_not_awaited()

    async def test_nested_readonly_check_does_not_deadlock_submit_lock(self):
        await self.case.record(age=4 * 3600, episode=None)
        async def context(target):
            received = time.time() - 30
            gate = await self.pacing.coordinate(target, rhythm={"last_received_at": received})
            return {"contact_rhythm": {**gate, "last_received_at": received}}
        self.plugin.daily_life_bridge.get_share_context = context
        async def check():
            async with self.pacing.lock:
                return await self.pacing.check(self.target)
        self.assertTrue((await asyncio.wait_for(check(), timeout=1))["ready"])

    async def test_simultaneous_life_and_bili_claims_only_one_succeeds(self):
        results = await asyncio.gather(*[self.pacing.coordinate(self.target, owner=key, action="submit")
                                          for key in ("life:a", "bili:b")])
        self.assertEqual(sum(item["ready"] for item in results), 1)

    async def test_bili_dynamic_separate_setting_and_cross_channel_material(self):
        self.plugin.config["bilibili_conf"] = {"autonomous_share_interval_minutes": 120}
        self.assertEqual(self.pacing.interval("bilibili_broadcast"), 7200)
        await self.pacing.coordinate(self.target, owner="life:a", action="submit", selected=["video:a"])
        self.assertFalse((await self.pacing.coordinate("bilibili_broadcast", selected=["video:a"]))["ready"])
        self.assertTrue((await self.pacing.coordinate("bilibili_broadcast", selected=["video:b"]))["ready"])

    async def test_completed_step_does_not_become_completed_episode(self):
        module = self.case.material
        now = datetime.now(module.SHANGHAI)
        row = {"activity": "准备完成", "execution_state": "completed", "execution_evidence": "confirmed",
               "execution_updated_at": now.isoformat(), "episode_id": "chain:a", "episode_state": "pending"}
        data = {"current_facts": {"valid": True}, "timeline": [row]}
        self.assertEqual(module.share_material(data, now), [])
        row["episode_state"] = "completed"
        first = module.share_material(data, now)[0]
        row["activity"] = "这次活动已结束"
        second = module.share_material(data, now)[0]
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["episode_id"], second["episode_id"])

    async def test_running_steps_share_same_identity_without_text_matching(self):
        module = self.case.material
        now = datetime.now(module.SHANGHAI)
        action = {"status": "running", "observation_state": "observed", "observed_at": now.isoformat(),
                  "action_id": "step1", "episode_id": "chain1", "activity": "第一步"}
        data = {"current_facts": {"valid": True, "current_action": action}}
        first = module.share_material(data, now)[0]
        action.update(action_id="step2", activity="完全不同的描述")
        second = module.share_material(data, now)[0]
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first["episode_id"], second["episode_id"])

    async def test_search_preserves_actual_engine_quality_sources_and_missing_aspects(self):
        module = importlib.import_module(fixtures.fixtures.CORE_PACKAGE_NAME + ".content.evidencepayload")
        payload = {"status": "ok", "content": "查到部分资料", "quality": "partial", "providers": ["grok-web"],
                   "missing_aspects": ["缺少时间依据"], "sources": [{"url": "https://example.test/evidence", "title": "依据", "private": "excluded"}]}
        result = json.loads(module.search_reference(payload))
        self.assertEqual(result["providers"], ["grok-web"])
        self.assertEqual(result["quality"], "partial")
        self.assertEqual(result["missing_aspects"], payload["missing_aspects"])
        self.assertNotIn("private", result["sources"][0])
        self.assertEqual(module.search_reference({"status": "ok", "content": None}), "")
        self.assertEqual(module.search_reference({**payload, "status": "error"}), "")


if __name__ == "__main__":
    unittest.main()
