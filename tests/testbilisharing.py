"""B站分享决策使用真实分享数据库，媒体与发布接口使用模拟回执。"""
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from astrbot_plugin_daily_share.core.db import DatabaseManager
from astrbot_plugin_daily_share.core.integrations.bilibili import BiliDynamicShare
from astrbot_plugin_daily_share.core.integrations.dailylife import DailyLifeBridge
from astrbot_plugin_daily_share.core.config import ShareType, TimePeriod
from astrbot_plugin_daily_share.core.content import ContentService
from astrbot_plugin_daily_share.core.image.result import GeneratedImage


class BiliSharingTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name))
        self.life = types.SimpleNamespace(generate_share_image_task=AsyncMock(return_value={'status':'ready','path':'public.png'}),
            get_share_image_task=AsyncMock(return_value={'status':'pending'}))
        metadata = types.SimpleNamespace(name='astrbot_plugin_daily_life', root_dir_name='astrbot_plugin_daily_life', activated=True, star_cls=self.life)
        bridge = DailyLifeBridge(types.SimpleNamespace(get_all_stars=lambda:[metadata]), db=self.db)
        self.plugin = types.SimpleNamespace(config={'enable_auto_share':True,'bilibili_conf':{'enabled':True}, 'image_conf':{'enable_ai_image':True}},
            _is_initialized=True, _is_terminated=False, db=self.db, daily_life_bridge=bridge,
            llm_service=types.SimpleNamespace(call=AsyncMock()),
            ctx_service=types.SimpleNamespace(get_qzone_share_context=AsyncMock(return_value={'life_context':'【今日穿搭】蓝外套'})),
            content_service=types.SimpleNamespace(generate=AsyncMock(return_value='今天这件穿起来很舒服')),
            task_manager=types.SimpleNamespace(executor_helpers=types.SimpleNamespace(
                period=types.SimpleNamespace(get_curr_period=lambda:TimePeriod.EVENING))))
        async def image(text, share_type, life_context, *, target_umo):
            path = await bridge.generate_image(None, text + life_context, contains_character=True)
            return GeneratedImage(path=path, description=life_context, contains_character=True) if path else None
        self.plugin.image_service = types.SimpleNamespace(generate_image=AsyncMock(side_effect=image))
        self.service = BiliDynamicShare(self.plugin)
        self.opportunity = {'account':'1234','persona':'角色本人', 'materials':[
            {'id':'look1','title':'当前穿搭','evidence':[{'quote':'实际穿着蓝外套'}], 'appearance':'蓝外套',
             'images':[]}], 'assets':{'pic1':'existing.png'}, 'recent_public_actions':[]}
        self.decision = {'decision':'share','source_id':'look1','text':'今天这件穿起来很舒服', 'image_ids':[],
                         'image_prompt':'角色当前穿搭照','contains_character':True}
        self.plugin.llm_service.call.return_value = json.dumps(self.decision)

    async def asyncTearDown(self):
        await self.db.close()
        self.temp.cleanup()

    async def test_generated_draft_uses_public_durable_task_and_keeps_original(self):
        draft = await self.service.prepare(self.opportunity)
        self.assertEqual((draft['status'], draft['images']), ('ready',['public.png']))
        args = self.life.generate_share_image_task.await_args
        self.assertTrue(args.kwargs['public_only'])
        self.assertEqual(args.kwargs['target_umo'],'bilibili_broadcast')
        self.assertIn('蓝外套',args.args[1])
        restarted = BiliDynamicShare(self.plugin)
        again = await restarted.prepare(self.opportunity)
        self.assertEqual(again,draft)
        self.life.generate_share_image_task.assert_awaited_once()
        self.plugin.llm_service.call.assert_awaited_once()
        self.plugin.content_service.generate.assert_awaited_once()
        self.plugin.ctx_service.get_qzone_share_context.assert_awaited_once()
        self.plugin.image_service.generate_image.assert_awaited_once()

    async def test_pending_image_queries_original_after_restart(self):
        self.life.generate_share_image_task.return_value = {'status':'pending'}
        pending = await self.service.prepare(self.opportunity)
        self.assertEqual(pending['status'],'pending')
        again = await BiliDynamicShare(self.plugin).prepare(self.opportunity)
        self.assertEqual(again, pending)
        self.life.get_share_image_task.return_value = {'status':'ready','path':'resumed.png'}
        ready = await BiliDynamicShare(self.plugin).prepare(self.opportunity)
        self.assertEqual(ready['images'],['resumed.png'])
        self.life.generate_share_image_task.assert_awaited_once()
        self.assertEqual(self.life.get_share_image_task.await_count, 2)
        self.plugin.image_service.generate_image.assert_awaited_once()
        self.plugin.ctx_service.get_qzone_share_context.assert_awaited_once()

    async def test_bili_post_does_not_depend_on_qzone_switch_or_post_history(self):
        self.plugin.config['qzone_conf'] = {'enable_qzone':False,'qzone_enable_image':False}
        await self.db.set_share_state('qzone_broadcast', {'last_post':'空间旧正文不能作为B站正文'})
        draft = await self.service.prepare(self.opportunity)
        self.assertEqual((draft['status'], draft['text'], draft['images']),
                         ('ready','今天这件穿起来很舒服',['public.png']))
        self.assertNotIn('空间旧正文', str(self.plugin.content_service.generate.await_args))
        self.assertEqual(await self.db.get_share_state('qzone_broadcast'),
                         {'last_post':'空间旧正文不能作为B站正文'})

    async def test_generation_error_does_not_downgrade_to_text_or_regenerate(self):
        self.life.generate_share_image_task.return_value = {'status':'failed','error':'原任务失败'}
        self.assertEqual((await self.service.prepare(self.opportunity))['status'],'failed')
        self.assertEqual((await self.service.prepare(self.opportunity))['status'],'wait')
        self.life.generate_share_image_task.assert_awaited_once()

    async def test_existing_image_selection_never_exposes_path_to_model(self):
        self.opportunity['materials'][0]['images'] = [{'id':'pic1','description':'公开作品'}]
        self.plugin.llm_service.call.return_value = json.dumps({**self.decision, 'image_prompt':'','image_ids':['pic1']})
        draft = await self.service.prepare(self.opportunity)
        self.assertEqual(draft['images'],['existing.png'])
        self.assertNotIn('existing.png',self.plugin.llm_service.call.await_args.args[0])
        self.life.generate_share_image_task.assert_not_awaited()

    async def test_unlisted_image_or_invalid_selection_is_rejected(self):
        for decision in ({**self.decision,'image_ids':['other']}, {**self.decision,'image_ids':'pic1'}):
            await self.db.set_share_state('bili_dynamic:1234',{})
            self.plugin.llm_service.call.return_value = json.dumps(decision)
            with self.assertRaises(ValueError):
                await self.service.prepare(self.opportunity)
        self.life.generate_share_image_task.assert_not_awaited()

    async def test_confirmed_receipt_prevents_new_draft_for_same_source(self):
        draft = await self.service.prepare(self.opportunity)
        await self.service.receipt('1234',draft['intent'],{'status':'accepted','remote_id':'999'})
        self.assertEqual((await self.service.prepare(self.opportunity))['status'],'wait')
        state = await self.db.get_share_state('bili_dynamic:1234')
        self.assertEqual(state['seen'],['look1'])
        self.assertEqual(state['last_receipt']['remote_id'],'999')
        self.assertNotIn('job',state)

    async def test_uncertain_receipt_blocks_new_post_and_checks_original(self):
        draft = await self.service.prepare(self.opportunity)
        await self.service.receipt('1234',draft['intent'],{'status':'uncertain','phase':'submitting'})
        result = await BiliDynamicShare(self.plugin).prepare({**self.opportunity,'materials':[]})
        self.assertEqual(result, {'status':'check','intent':draft['intent'],'source_id':'look1'})
        self.plugin.llm_service.call.assert_awaited_once()

    async def test_revoked_source_is_checked_before_being_cancelled(self):
        draft = await self.service.prepare(self.opportunity)
        result = await self.service.prepare({**self.opportunity,'materials':[]})
        self.assertEqual(result['status'],'check')
        self.assertTrue(result['source_expired'])

    async def test_disabling_auto_share_keeps_ownership_without_publishing(self):
        self.plugin.config['enable_auto_share'] = False
        self.assertTrue(self.service.owns_channel())
        self.assertEqual((await self.service.prepare(self.opportunity))['status'],'wait')
        self.assertEqual(await self.service.interact({'allowed_actions':['comment','wait']}), {'action':'wait'})
        self.plugin.llm_service.call.assert_not_awaited()

    async def test_images_disabled_explicitly_allows_text_only(self):
        self.plugin.config['bilibili_conf']['enable_image'] = False
        draft = await self.service.prepare(self.opportunity)
        self.assertEqual((draft['status'],draft['images']),('ready',[]))
        self.life.generate_share_image_task.assert_not_awaited()
        self.assertFalse(json.loads(self.plugin.llm_service.call.await_args.args[0])['allow_images'])

    async def test_interaction_contract_excludes_life_actions_and_passive_dm(self):
        self.plugin.llm_service.call.return_value = json.dumps({'action':'favorite','id':'1'})
        result = await self.service.interact({'allowed_actions':['favorite','join','dm','comment','wait'], 'schedule':'私人日程'})
        self.assertEqual(result, {'action':'wait'})
        payload = json.loads(self.plugin.llm_service.call.await_args.args[0])
        self.assertEqual(payload['allowed_actions'],['comment','wait'])
        self.assertNotIn('schedule',payload)

    async def test_public_expression_excludes_dm_and_contact_fields(self):
        self.plugin.llm_service.call.return_value = json.dumps({'action':'comment','text':'实验很有意思'})
        await self.service.interact({'allowed_actions':['comment','wait'],'bili_dialogue':['私密正文'],
                                    'contact':{'scope':'private:a'},'public_material':[{'title':'实验'}]}, expression=True)
        payload = self.plugin.llm_service.call.await_args.args[0]
        self.assertNotIn('私密正文',payload)
        self.assertNotIn('private:a',payload)

    async def test_accounts_have_independent_jobs_and_receipts(self):
        first = await self.service.prepare(self.opportunity)
        second = await self.service.prepare({**self.opportunity,'account':'5678'})
        self.assertNotEqual(first['intent'],second['intent'])
        await self.service.receipt('5678',first['intent'],{'status':'accepted'})
        self.assertIn('job',await self.db.get_share_state('bili_dynamic:5678'))

    async def test_disabling_auto_share_during_decision_prevents_media_generation(self):
        async def decide(*args, **kwargs):
            self.plugin.config['enable_auto_share'] = False
            return json.dumps(self.decision)
        self.plugin.llm_service.call.side_effect = decide
        self.assertEqual((await self.service.prepare(self.opportunity))['status'],'wait')
        self.life.generate_share_image_task.assert_not_awaited()

    async def test_paused_image_setting_preserves_job_without_querying_media(self):
        self.life.generate_share_image_task.return_value = {'status':'pending'}
        await self.service.prepare(self.opportunity)
        self.plugin.config['bilibili_conf']['enable_image'] = False
        self.assertEqual((await self.service.prepare(self.opportunity))['status'],'wait')
        self.life.get_share_image_task.assert_not_awaited()
        self.plugin.config['bilibili_conf']['enable_image'] = True
        self.life.get_share_image_task.return_value = {'status':'ready','path':'resumed.png'}
        self.assertEqual((await self.service.prepare(self.opportunity))['images'],['resumed.png'])
        self.life.generate_share_image_task.assert_awaited_once()

    async def test_decision_text_is_not_used_as_published_body(self):
        self.plugin.llm_service.call.return_value = json.dumps({**self.decision, 'text':'长篇观后感'*100})
        draft = await self.service.prepare(self.opportunity)
        self.assertEqual(draft['text'], '今天这件穿起来很舒服')
        args = self.plugin.content_service.generate.await_args
        self.assertEqual(args.args[:4], (ShareType.MOOD,TimePeriod.EVENING,'bilibili_broadcast',False))
        self.assertIn('蓝外套',args.args[4])
        self.assertEqual(args.kwargs['structured_history'],'')
        self.assertEqual(self.plugin.image_service.generate_image.await_args.args[0],draft['text'])

    async def test_images_enabled_without_selected_images_still_generates(self):
        self.plugin.llm_service.call.return_value = json.dumps({'decision':'share','source_id':'look1','image_ids':[]})
        draft = await self.service.prepare(self.opportunity)
        self.assertEqual(draft['images'],['public.png'])
        self.plugin.image_service.generate_image.assert_awaited_once()

    async def test_existing_source_image_is_used_before_generating(self):
        self.opportunity['materials'][0]['images'] = [{'id':'pic1','description':'公开作品'}]
        draft = await self.service.prepare(self.opportunity)
        self.assertEqual(draft['images'],['existing.png'])
        self.plugin.image_service.generate_image.assert_not_awaited()

    async def test_long_or_empty_composition_cannot_reach_media_or_publication(self):
        for text in ('长'*81, '', None):
            await self.db.set_share_state('bili_dynamic:1234',{})
            self.plugin.content_service.generate.return_value = text
            self.assertEqual((await self.service.prepare(self.opportunity))['status'],'wait')
            state = await self.db.get_share_state('bili_dynamic:1234')
            self.assertNotIn('job',state)
        self.plugin.image_service.generate_image.assert_not_awaited()

    async def test_generation_switch_is_respected_without_silent_text_fallback(self):
        self.plugin.config['image_conf']['enable_ai_image'] = False
        draft = await self.service.prepare(self.opportunity)
        self.assertEqual(draft['status'],'wait')
        self.plugin.image_service.generate_image.assert_not_awaited()
        self.plugin.content_service.generate.assert_not_awaited()

    async def test_content_and_history_are_isolated_from_private_context(self):
        self.opportunity['materials'][0]['private_chat'] = '私密聊天不能入帖'
        self.opportunity['recent_public_actions'] = [
            {'kind':'dynamic','status':'accepted','text':'本账号已发布'},
            {'kind':'dm','status':'accepted','text':'私信不能入帖'},
            {'kind':'dynamic','status':'rejected','text':'失败草稿'},
        ]
        await self.service.prepare(self.opportunity)
        args = self.plugin.content_service.generate.await_args
        self.assertEqual(args.kwargs['recent_post_contents'],['本账号已发布'])
        self.assertNotIn('私密聊天',str(args))
        self.assertNotIn('私信不能',str(args))
        self.assertNotIn('existing.png',str(args))

    async def test_switch_off_during_composition_does_not_create_media(self):
        async def compose(*args, **kwargs):
            self.plugin.config['enable_auto_share'] = False
            return '短动态'
        self.plugin.content_service.generate.side_effect = compose
        self.assertEqual((await self.service.prepare(self.opportunity))['status'],'wait')
        self.plugin.image_service.generate_image.assert_not_awaited()

    async def test_legacy_pending_draft_checks_receipt_without_rewriting(self):
        await self.db.set_share_state('bili_dynamic:1234',{'job':{
            'id':'legacy','source_id':'look1','status':'ready','text':'旧长文'*40}})
        result = await self.service.prepare(self.opportunity)
        self.assertEqual(result,{'status':'check','intent':'legacy','source_id':'look1','source_expired':True})
        self.plugin.content_service.generate.assert_not_awaited()
        self.plugin.image_service.generate_image.assert_not_awaited()

    async def test_enabling_images_during_composition_discards_stale_text_only_choice(self):
        self.plugin.config['bilibili_conf']['enable_image'] = False
        async def compose(*args, **kwargs):
            self.plugin.config['bilibili_conf']['enable_image'] = True
            return '写文案时开启了配图'
        self.plugin.content_service.generate.side_effect = compose
        self.assertEqual((await self.service.prepare(self.opportunity))['status'],'wait')
        self.assertNotIn('job',await self.db.get_share_state('bili_dynamic:1234'))
        self.plugin.image_service.generate_image.assert_not_awaited()

    async def test_disabling_images_during_composition_discards_stale_image_choice(self):
        async def compose(*args, **kwargs):
            self.plugin.config['bilibili_conf']['enable_image'] = False
            return '写文案时关闭了配图'
        self.plugin.content_service.generate.side_effect = compose
        self.assertEqual((await self.service.prepare(self.opportunity))['status'],'wait')
        self.assertNotIn('job',await self.db.get_share_state('bili_dynamic:1234'))
        self.plugin.image_service.generate_image.assert_not_awaited()

    async def test_shared_public_composer_uses_bili_label_cleaning_and_length_check(self):
        llm = AsyncMock(return_value='这件蓝外套穿起来很舒服')
        bridge = types.SimpleNamespace(
            get_share_chat_style_prompt=AsyncMock(return_value='自然短句'),
            prepare_expression=AsyncMock(return_value={'text':'蓝外套穿起来很舒服'}))
        service = ContentService({}, llm, None, self.db, daily_life_bridge=bridge)
        service.get_persona_info = AsyncMock(return_value={'prompt':'角色本人','user_name':'私聊昵称'})
        text = await service.generate(ShareType.MOOD,TimePeriod.EVENING,'bilibili_broadcast',False,'公开穿搭',
                                      recent_post_contents=[])
        self.assertEqual(text,'蓝外套穿起来很舒服')
        prompt = llm.await_args.kwargs['prompt']
        self.assertIn('本次 B站状态',prompt)
        self.assertIn('不超过80字',prompt)
        self.assertNotIn('本次 QQ 空间',prompt)
        self.assertNotIn('私聊昵称',prompt)
        bridge.prepare_expression.assert_awaited_once_with('这件蓝外套穿起来很舒服',scene='qzone_post')
        bridge.prepare_expression.return_value = {'text':'长'*81}
        self.assertIsNone(await service.generate(ShareType.MOOD,TimePeriod.EVENING,'bilibili_broadcast',False,'公开事实'))

    async def test_recent_bili_dynamic_is_not_repeated(self):
        self.opportunity['recent_public_actions'] = [{'kind':'dynamic','status':'confirmed','text':'今天这件穿起来很舒服'}]
        self.assertEqual((await self.service.prepare(self.opportunity))['status'],'wait')
        self.plugin.image_service.generate_image.assert_not_awaited()
