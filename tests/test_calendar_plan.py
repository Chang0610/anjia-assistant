import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from calendar_plan import augment_model_result, build_proposal, clean_calendar, clean_event


def operation(action, event_id='', title='看房', due_date='2026-10-09'):
    return {
        'action': action, 'id': event_id, 'title': title, 'due_date': due_date,
        'due_time': None, 'detail': '核对房屋条件', 'kind': 'task',
        'date_basis': '建议日期', 'source_note': '信息待确认：与房东核验',
    }


class CalendarProposalTest(unittest.TestCase):
    def test_first_plan_does_not_ask_whether_to_generate_the_plan_again(self):
        model = {
            'response_mode': 'B', 'calendar_intent': 'propose',
            'operations': [operation('add', title='完成搬家', due_date='2026-10-14')],
            'answer': '已整理计划。是否需要我按张江通勤优先生成搬家计划？',
            'follow_ups': ['是否需要我按张江通勤优先生成搬家计划？'],
            'quick_choices': ['按张江通勤优先安排'],
        }
        result = augment_model_result(clean_calendar(None), model,
            {'start_date': '2026-10-15', 'move_deadline': '2026-10-14'},
            '请给我搬家计划表', date(2026, 9, 29))
        self.assertNotIn('是否需要我', result['answer'])
        self.assertEqual(result['follow_ups'], [])
        self.assertEqual(result['quick_choices'], [])

    def test_first_plan_removes_confirmation_question_even_without_question_mark(self):
        model = {'response_mode': 'B', 'calendar_intent': 'propose', 'operations': [operation('add')],
                 'answer': '已整理计划，请确认是否按此顺序生成待确认日程。'}
        result = augment_model_result(clean_calendar(None), model,
            {'start_date': '2026-10-15', 'move_deadline': '2026-10-14'},
            '请给我搬家计划表', date(2026, 9, 29))
        self.assertNotIn('请确认是否', result['answer'])

    def test_first_plan_fills_missing_prd_stages(self):
        state = clean_calendar(None)
        profile = {'start_date': '2026-10-15', 'move_deadline': '2026-10-14'}
        model = {'response_mode': 'B', 'calendar_intent': 'propose', 'operations': [
            operation('add', title='完成租房并确认租赁关键细节', due_date='2026-10-12'),
            operation('add', title='搬入新住处并完成入住检查', due_date='2026-10-14'),
            operation('add', title='向HR确认入职事项', due_date='2026-10-10'),
        ]}
        result = augment_model_result(state, model, profile, '请给我计划表', date(2026, 9, 29))
        proposal = build_proposal(state, result, profile, date(2026, 9, 29))
        titles = [item['title'] for item in proposal['events']]
        for word in ('区域', '看房', '交房', '宽带', '水电', '通勤试走', '居住登记'):
            self.assertTrue(any(word in title for title in titles), word)
        self.assertEqual(len(titles), len(set(titles)))

    def test_chat_rejection_clears_pending_without_changing_confirmed(self):
        confirmed = clean_event({'id': 'saved', 'title': '入职报到', 'due_date': '2026-10-15'})
        draft = clean_event({'id': 'draft', 'title': '看房', 'due_date': '2026-10-11'})
        state = clean_calendar({'confirmed': [confirmed], 'pending': [confirmed, draft]})
        result = augment_model_result(state, {'response_mode': 'D', 'calendar_intent': 'propose', 'operations': [operation('add')]}, {}, '不需要改动当前日程表。', date(2026, 9, 29))
        self.assertTrue(result['clear_pending'])
        self.assertEqual(result['operations'], [])
        self.assertEqual(state['confirmed'], [confirmed])

    def test_plan_source_survives_proposal_and_next_request(self):
        op = operation('add', title='核验居住登记', due_date='2026-10-17')
        op['sources'] = [{'source_name': '随申办', 'source_url': 'https://example.gov.cn/residence', 'source_status': '官方来源已核验', 'verified_at': '2026-09-23'}]
        proposal = build_proposal(clean_calendar(None), {'calendar_intent': 'propose', 'operations': [op]}, {}, date(2026, 9, 28))
        restored = clean_calendar({'confirmed': proposal['events']})
        self.assertEqual(restored['confirmed'][0]['sources'][0]['source_name'], '随申办')

    def test_empty_calendar_profile_arrangement_creates_pending_plan(self):
        state = clean_calendar(None)
        profile = {'company_location': '张江高科', 'start_date': '2026-10-20', 'move_deadline': '2026-10-17'}
        result = augment_model_result(state, {'response_mode': 'C', 'answer': '你可以开始安排。', 'calendar_intent': 'none', 'operations': []}, profile, '根据我现在资料，告诉我如何安排', date(2026, 9, 28))
        proposal = build_proposal(state, result, profile, date(2026, 9, 28))
        self.assertEqual(result['response_mode'], 'B')
        self.assertEqual(result['calendar_intent'], 'propose')
        self.assertGreaterEqual(len(proposal['changes']), 8)
        self.assertEqual(state['confirmed'], [])

    def test_initial_plan_with_model_operations_keeps_pending_list(self):
        state = clean_calendar(None)
        result = augment_model_result(state, {'response_mode': 'C', 'answer': '已有计划', 'calendar_intent': 'none', 'operations': [operation('add')]}, {}, '根据我现在资料，告诉我如何安排', date(2026, 9, 28))
        self.assertEqual(result['response_mode'], 'B')
        self.assertEqual(result['calendar_intent'], 'propose')
        self.assertEqual(len(build_proposal(state, result)['changes']), 1)

    def test_initial_plan_does_not_confuse_same_round_tasks_with_existing_calendar(self):
        state = clean_calendar(None)
        result = build_proposal(state, {'calendar_intent': 'propose', 'operations': [
            operation('add', title='到岗入职并核对单位参保、公积金', due_date='2026-10-30'),
            operation('add', title='核对社保医保与公积金缴存状态', due_date='2026-11-29'),
        ]})
        self.assertEqual(len(result['changes']), 2)
        self.assertEqual(result['clarifications'], [])

    def test_pending_draft_is_labelled_pending_in_clarification(self):
        draft = clean_event({'id': 'draft', 'title': '到岗入职并核对单位参保、公积金', 'due_date': '2026-10-30'})
        state = clean_calendar({'confirmed': [], 'pending': [draft]})
        result = build_proposal(state, {'calendar_intent': 'propose', 'operations': [
            operation('add', title='核对社保医保与公积金缴存状态', due_date='2026-11-29'),
        ]})
        self.assertEqual(result['clarifications'][0]['existing_status'], 'pending')

    def test_delete_all_creates_reviewable_deletions_even_when_model_only_answers(self):
        confirmed = [clean_event({'id': f'item_{index}', 'title': f'事项{index}', 'due_date': '2026-10-09'}) for index in range(35)]
        state = clean_calendar({'confirmed': confirmed})
        result = augment_model_result(state, {'response_mode': 'D', 'answer': '将删除所有计划。', 'calendar_intent': 'none', 'operations': []}, {}, '删除所有计划', date(2026, 9, 23))
        proposal = build_proposal(state, result, {}, date(2026, 9, 23))
        self.assertEqual(len(proposal['changes']), 35)
        self.assertEqual(proposal['events'], [])
        self.assertTrue(proposal['bulk_delete_all'])
        self.assertEqual(len(state['confirmed']), 35)

    def test_delete_all_pending_only_still_requires_confirmation(self):
        draft = clean_event({'id': 'draft', 'title': '准备搬家', 'due_date': '2026-10-09'})
        state = clean_calendar({'confirmed': [], 'pending': [draft]})
        result = augment_model_result(state, {'response_mode': 'D', 'answer': '删除计划', 'operations': []}, {}, '删除所有计划', date(2026, 9, 23))
        proposal = build_proposal(state, result, {}, date(2026, 9, 23))
        self.assertTrue(proposal['pending_only_delete'])
        self.assertEqual(proposal['changes'][0]['type'], '删除')
        self.assertEqual(state['pending'], [draft])

    def test_negated_delete_all_does_not_create_deletions(self):
        state = clean_calendar({'confirmed': [clean_event({'id': 'a', 'title': '搬家', 'due_date': '2026-10-09'})]})
        result = augment_model_result(state, {'response_mode': 'C', 'answer': '好的', 'calendar_intent': 'none', 'operations': []}, {}, '不要删除所有计划', date(2026, 9, 23))
        self.assertFalse(result.get('delete_all'))

    def test_ai_suggested_date_is_one_day_even_if_model_returns_range(self):
        op = operation('add', title='安排搬家', due_date='2026-10-14')
        op['start_date'] = '2026-10-12'
        proposal = build_proposal(clean_calendar(None), {'calendar_intent': 'propose', 'operations': [op]}, {}, date(2026, 9, 23))
        self.assertEqual(proposal['events'][0]['start_date'], '2026-10-14')
        self.assertEqual(proposal['events'][0]['due_date'], '2026-10-14')

    def test_linked_task_moves_with_prerequisite_but_hard_deadline_blocks_conflict(self):
        state = clean_calendar({'confirmed': [
            clean_event({'id': 'handover', 'title': '交房', 'due_date': '2026-10-10'}),
            clean_event({'id': 'wifi', 'title': '安装宽带', 'due_date': '2026-10-11', 'depends_on_ids': ['handover']}),
        ]})
        moved = build_proposal(state, {'calendar_intent': 'propose', 'operations': [operation('update', 'handover', title='交房', due_date='2026-10-13')]}, {}, date(2026, 9, 23))
        self.assertEqual(next(item for item in moved['events'] if item['id'] == 'wifi')['due_date'], '2026-10-14')
        state['confirmed'][1]['hard_deadline'] = True
        conflict = build_proposal(state, {'calendar_intent': 'propose', 'operations': [operation('update', 'handover', title='交房', due_date='2026-10-13')]}, {}, date(2026, 9, 23))
        self.assertTrue(conflict['conflicts'])
        self.assertEqual(conflict['changes'], [])

    def test_model_can_create_range_and_user_hard_deadline(self):
        op = operation('add', title='搬家', due_date='2026-10-14')
        op.update(start_date='2026-10-12', hard_deadline=True, date_basis='用户明确', depends_on_ids=[])
        result = build_proposal(clean_calendar(None), {'calendar_intent': 'propose', 'operations': [op]}, {}, date(2026, 9, 23))
        self.assertEqual(result['events'][0]['start_date'], '2026-10-12')
        self.assertTrue(result['events'][0]['hard_deadline'])

    def test_initial_plan_resolves_title_dependencies_to_ids(self):
        handover = operation('add', title='交房', due_date='2026-10-10')
        wifi = operation('add', title='安装宽带', due_date='2026-10-11')
        wifi['depends_on_titles'] = ['交房']
        result = build_proposal(clean_calendar(None), {'calendar_intent': 'propose', 'operations': [handover, wifi]}, {}, date(2026, 9, 23))
        events = {item['title']: item for item in result['events']}
        self.assertEqual(events['安装宽带']['depends_on_ids'], [events['交房']['id']])

    def test_legacy_hard_handover_conflict_blocks_move_change(self):
        state = clean_calendar({'confirmed': [
            clean_event({'id': 'move', 'title': '完成搬家', 'due_date': '2026-10-14'}),
            clean_event({'id': 'handoff', 'title': '旧住处交接', 'due_date': '2026-10-12', 'hard_deadline': True}),
        ]})
        result = build_proposal(state, {'calendar_intent': 'propose', 'operations': [operation('update', 'move', title='完成搬家', due_date='2026-10-13')]}, {}, date(2026, 9, 23))
        self.assertTrue(result['conflicts'])
        self.assertEqual(result['changes'], [])

    def test_found_housing_removes_search_and_unlocks_handover_chain(self):
        state = clean_calendar({'confirmed': [], 'pending': [
            clean_event({'id': 'rent', 'title': '安排找房看房', 'due_date': None}),
            clean_event({'id': 'move', 'title': '确认搬家安排与旧住处收尾', 'due_date': None}),
        ]})
        model = {'calendar_intent': 'none', 'operations': []}
        profile = {'current_housing': '已找到房子', 'housing_handover_date': '10月15日'}
        augmented = augment_model_result(state, model, profile, '我已经找到房子了，10月15号交房。', date(2026, 9, 23))
        result = build_proposal(state, augmented, profile, date(2026, 9, 23))
        titles = {item['title'] for item in result['events']}
        self.assertNotIn('安排找房看房', titles)
        self.assertTrue({'交房并完成入住验收', '核验网络安装条件', '确认搬家安排并约定服务时间', '搬入新住处并核对水电交接'} <= titles)
        self.assertEqual(next(item for item in result['events'] if item['title'] == '交房并完成入住验收')['due_date'], '2026-10-15')

    def test_completed_handover_proposes_search_removal_and_downstream_tasks(self):
        state = clean_calendar({'confirmed': [
            clean_event({'id': 'search', 'title': '安排找房和看房', 'due_date': '2026-10-05'}),
            clean_event({'id': 'handover', 'title': '交房完成', 'due_date': '2026-10-12', 'done': True}),
            clean_event({'id': 'hire', 'title': '到岗入职', 'due_date': '2026-10-19'}),
        ]})
        result = augment_model_result(state, {'response_mode': 'C', 'calendar_intent': 'none', 'operations': []},
                                      {'housing_handover_date': '2026-10-12'}, '我已经交房完成，接下来做什么？', date(2026, 10, 12))
        proposal = build_proposal(state, result, {}, date(2026, 10, 12))
        titles = {item['title'] for item in proposal['events']}
        self.assertEqual(result['response_mode'], 'D')
        self.assertNotIn('安排找房和看房', titles)
        self.assertTrue({'核验网络安装条件', '确认搬家方案和服务时间', '搬入并核对水电燃气交接', '核验居住登记办理条件'} <= titles)
        self.assertIn('交房完成', titles)
        self.assertIn('到岗入职', titles)
        self.assertEqual(len(proposal['changes']), 5)

    def test_completed_handover_moves_stale_unfinished_move_after_access(self):
        state = clean_calendar({'confirmed': [
            clean_event({'id': 'move', 'title': '完成搬家', 'due_date': '2026-10-10'}),
            clean_event({'id': 'handover', 'title': '交房完成', 'due_date': '2026-10-12', 'done': True}),
        ]})
        profile = {'housing_handover_date': '2026-10-12', 'move_deadline': '2026-10-10'}
        result = augment_model_result(state, {'response_mode': 'C', 'calendar_intent': 'none', 'operations': []},
                                      profile, '我已经交房完成，接下来做什么？', date(2026, 10, 12))
        proposal = build_proposal(state, result, profile, date(2026, 10, 12))
        self.assertGreaterEqual(next(item for item in proposal['events'] if item['id'] == 'move')['due_date'], '2026-10-12')
        self.assertIn({'id': 'move', 'type': '修改', 'title': '完成搬家'}, proposal['changes'])

    def test_move_after_hire_requires_choice_without_operations(self):
        state = clean_calendar({'confirmed': [clean_event({'id': 'move', 'title': '完成搬家', 'due_date': '2026-10-12'})]})
        result = augment_model_result(state, {'response_mode': 'D', 'calendar_intent': 'propose', 'operations': [operation('update', 'move', title='完成搬家', due_date='2026-10-18')]},
                                      {'start_date': '2026-10-15', 'move_deadline': '2026-10-18'}, '把搬家改到2026年10月18日', date(2026, 9, 23))
        self.assertEqual(result['response_mode'], 'E')
        self.assertEqual(result['operations'], [])
        self.assertIsNone(build_proposal(state, result))
        self.assertEqual(len(result['quick_choices']), 2)
        self.assertIn('2026-10-18', result['quick_choices'][1])

    def test_move_after_hire_user_choice_creates_reviewable_change(self):
        state = clean_calendar({'confirmed': [clean_event({'id': 'move', 'title': '完成搬家', 'due_date': '2026-10-12'})]})
        result = augment_model_result(state, {'response_mode': 'E', 'calendar_intent': 'none', 'operations': []},
                                      {'start_date': '2026-10-15', 'move_deadline': '2026-10-18'},
                                      '接受入职后搬家（目标2026-10-18），核验过渡条件', date(2026, 9, 23))
        proposal = build_proposal(state, result, {}, date(2026, 9, 23))
        self.assertEqual(result['response_mode'], 'D')
        self.assertIn({'id': 'move', 'type': '修改', 'title': '完成搬家'}, proposal['changes'])
        self.assertEqual(next(item for item in proposal['events'] if item['id'] == 'move')['due_date'], '2026-10-18')
        self.assertIn('核验入职后搬家期间的过渡住所与通勤', {item['title'] for item in proposal['events']})

    def test_reminder_request_proposes_local_change_without_wechat_claim(self):
        state = clean_calendar({'confirmed': [clean_event({'id': 'move', 'title': '完成搬家', 'due_date': '2026-10-14'})]})
        result = augment_model_result(state, {'response_mode': 'C', 'calendar_intent': 'none', 'operations': []},
                                      {}, '把搬家提醒改成提前三天，并开微信提醒。', date(2026, 9, 23))
        self.assertEqual(result['response_mode'], 'C')
        self.assertEqual(result['operations'], [])
        self.assertIn('微信订阅和后台推送尚未接入', result['answer'])
        self.assertEqual(state['confirmed'][0]['reminder_at'], None)
        self.assertIsNone(build_proposal(state, result, {}, date(2026, 9, 23)))
        task_wording = augment_model_result(state, {'response_mode': 'D', 'calendar_intent': 'propose', 'operations': [operation('update', 'move', title='完成搬家', due_date='2026-10-10')]},
                                            {}, '把搬家这个任务改到10月10日上午9点提醒', date(2026, 9, 23))
        self.assertEqual(task_wording['operations'], [])

    def test_casual_rejection_clears_pending(self):
        event = clean_event({'id': 'draft', 'title': '看房', 'due_date': '2026-10-11'})
        state = clean_calendar({'confirmed': [], 'pending': [event]})
        result = augment_model_result(state, {'response_mode': 'D', 'calendar_intent': 'propose', 'operations': []}, {}, '算了，先别改。', date(2026, 9, 23))
        self.assertTrue(result['clear_pending'])
        self.assertEqual(result['operations'], [])

    def test_reminder_change_redirects_to_profile_settings_without_plan_proposal(self):
        event = clean_event({'id': 'hr', 'title': '向单位确认入职事项', 'due_date': '2026-10-09', 'reminder_at': '2026-10-09T09:00'})
        state = clean_calendar({'confirmed': [event]})
        result = augment_model_result(state, {'response_mode': 'C', 'calendar_intent': 'none', 'operations': []}, {}, '帮我把“向单位确认入职”这个任务改到10/10上午9点提醒。', date(2026, 9, 23))
        self.assertEqual(result['response_mode'], 'C')
        self.assertEqual(result['calendar_intent'], 'none')
        self.assertEqual(result['operations'], [])
        self.assertIn('我的', result['answer'])
        self.assertEqual(state['confirmed'][0]['reminder_at'], '2026-10-09T09:00')
        self.assertIsNone(build_proposal(state, result, {}, date(2026, 9, 23)))

    def test_ambiguous_arrangement_asks_before_changing_existing_move(self):
        event = clean_event({'id': 'move', 'title': '完成搬家', 'due_date': '2026-10-14'})
        state = clean_calendar({'confirmed': [event]})
        result = augment_model_result(state, {'response_mode': 'D', 'calendar_intent': 'propose', 'operations': [operation('update', 'move')]}, {'move_deadline': '2026-10-13'}, '请安排2026年10月13日搬家。', date(2026, 9, 23))
        self.assertEqual(result['response_mode'], 'E')
        self.assertEqual(result['operations'], [])
        self.assertIn('move_deadline', result['suppress_profile_fields'])

    def test_region_budget_scope_is_asked_before_recommendation(self):
        result = augment_model_result(clean_calendar(None), {'response_mode': 'C', 'answer': '张江合租适合你。', 'calendar_intent': 'none', 'operations': []},
                                      {'monthly_rent_budget': '3000元以内'}, '租金3000元以内，哪些区域适合我？', date(2026, 9, 23))
        self.assertNotIn('张江合租适合你', result['answer'])
        self.assertIn('水电', result['follow_ups'][0])

    def test_delayed_handover_with_existing_booking_proposes_self_rebooking(self):
        state = clean_calendar({'confirmed': [
            clean_event({'id': 'handover', 'title': '交房', 'due_date': '2026-10-12'}),
            clean_event({'id': 'broadband', 'title': '已预约宽带安装', 'due_date': '2026-10-12'}),
            clean_event({'id': 'move', 'title': '完成搬家', 'due_date': '2026-10-13'}),
            clean_event({'id': 'in', 'title': '搬入新住处并完成入住交接', 'due_date': '2026-10-13'}),
        ]})
        profile = {'housing_handover_date': '2026-10-14', 'move_deadline': '2026-10-13'}
        result = augment_model_result(state, {'response_mode': 'E', 'calendar_intent': 'none', 'operations': []}, profile,
                                      '交房从10月12日延到10月14日，宽带已经自己约好了。', date(2026, 9, 23))
        proposal = build_proposal(state, result, profile, date(2026, 9, 23))
        titles = {item['title']: item for item in proposal['events']}
        self.assertEqual(result['response_mode'], 'D')
        self.assertEqual(titles['交房']['due_date'], '2026-10-14')
        self.assertGreaterEqual(titles['待确认宽带安装改约']['due_date'], '2026-10-14')
        self.assertGreaterEqual(titles['完成搬家']['due_date'], '2026-10-14')
        self.assertEqual(titles['搬入新住处并完成入住交接']['due_date'], '2026-10-14')
        self.assertIn('联系运营商确认安装改约', titles)

    def test_handover_delay_without_new_date_asks_instead_of_reusing_old_date(self):
        state = clean_calendar({'confirmed': [clean_event({'id': 'handover', 'title': '交房', 'due_date': '2026-10-12'})]})
        result = augment_model_result(state, {'response_mode': 'D', 'calendar_intent': 'propose', 'operations': [operation('update', 'handover', title='交房', due_date='2026-10-12')]},
                                      {'housing_handover_date': '2026-10-12'}, '交房延期了，房东还没说新日期。', date(2026, 9, 23))
        self.assertEqual(result['response_mode'], 'E')
        self.assertEqual(result['operations'], [])
        self.assertIn('新的交房日期', result['follow_ups'][0])

    def test_delayed_handover_prevents_booked_services_before_access_date(self):
        state = clean_calendar({'confirmed': [
            clean_event({'id': 'broadband', 'title': '已预约宽带安装', 'due_date': '2026-10-16'}),
            clean_event({'id': 'moving', 'title': '已预约搬家服务', 'due_date': '2026-10-16'}),
        ]})
        model = {'calendar_intent': 'propose', 'operations': [
            operation('update', 'broadband', title='已预约宽带安装', due_date='2026-10-19'),
            operation('update', 'moving', title='已预约搬家服务', due_date='2026-10-19'),
        ]}
        result = build_proposal(state, model, {'housing_handover_date': '2026-10-20'}, date(2026, 9, 23))
        self.assertEqual({item['due_date'] for item in result['events']}, {'2026-10-20'})

    def test_delayed_handover_separates_rebooking_tasks_from_service_dates(self):
        state = clean_calendar({'confirmed': [
            clean_event({'id': 'handover', 'title': '交房并完成入住验收', 'due_date': '2026-10-17'}),
            clean_event({'id': 'broadband', 'title': '已预约宽带安装', 'due_date': '2026-10-16'}),
            clean_event({'id': 'moving', 'title': '已预约搬家服务', 'due_date': '2026-10-16'}),
        ]})
        profile = {'housing_handover_date': '2026-10-20'}
        augmented = augment_model_result(state, {'calendar_intent': 'none', 'operations': []}, profile, '房东说交房晚了三天，改到10月20日了。', date(2026, 9, 23))
        result = build_proposal(state, augmented, profile, date(2026, 9, 23))
        events = {item['title']: item for item in result['events']}
        self.assertEqual(events['交房并完成入住验收']['due_date'], '2026-10-20')
        self.assertEqual(events['待确认搬家服务改约']['due_date'], '2026-10-20')
        self.assertEqual(events['待确认宽带安装改约']['due_date'], '2026-10-21')
        self.assertEqual(events['联系运营商确认安装改约']['due_date'], '2026-09-23')
        self.assertEqual(events['联系搬运服务方确认改约']['due_date'], '2026-09-23')

    def test_half_day_capacity_moves_low_priority_tasks_off_crowded_date(self):
        state = clean_calendar({'confirmed': [
            clean_event({'id': 'view', 'title': '看房', 'due_date': '2026-10-11'}),
            clean_event({'id': 'hr', 'title': '核验单位入职要求', 'due_date': '2026-10-11'}),
            clean_event({'id': 'inventory', 'title': '盘点物品', 'due_date': '2026-10-11'}),
            clean_event({'id': 'quote', 'title': '咨询搬家报价', 'due_date': '2026-10-11'}),
        ]})
        augmented = augment_model_result(state, {'calendar_intent': 'none', 'operations': []}, {}, '这个周末我只有半天有空，帮我重新安排。', date(2026, 9, 23))
        self.assertEqual(augmented['response_mode'], 'D')
        result = build_proposal(state, augmented, {}, date(2026, 9, 23))
        dates = {item['id']: item['due_date'] for item in result['events']}
        self.assertEqual(dates['view'], '2026-10-11')
        self.assertEqual(dates['hr'], '2026-10-11')
        self.assertEqual(dates['inventory'], '2026-10-12')
        self.assertEqual(dates['quote'], '2026-10-09')
        self.assertTrue(all(value >= '2026-10-09' for value in dates.values()))

    def test_relative_full_process_deadline_adds_separate_milestone(self):
        state = clean_calendar(None)
        profile = {'planning_start_date': '2026-10-09', 'full_process_deadline': '2026-10-23', 'start_date': '2026-10-19'}
        augmented = augment_model_result(state, {'calendar_intent': 'none', 'operations': []}, profile, '希望2周内完成搬家全流程', date(2026, 9, 23))
        result = build_proposal(state, augmented, profile, date(2026, 9, 23))
        milestone = next(item for item in result['events'] if item['title'] == '全流程目标完成里程碑')
        self.assertEqual(milestone['due_date'], '2026-10-23')

    def test_model_full_process_milestone_is_normalized_without_duplicate(self):
        state = clean_calendar(None)
        profile = {'planning_start_date': '2026-10-09', 'full_process_deadline': '2026-10-23'}
        model = {'calendar_intent': 'propose', 'operations': [
            operation('add', title='完成搬家全流程里程碑', due_date='2026-10-22'),
        ]}
        augmented = augment_model_result(state, model, profile, '希望2周内完成搬家全流程', date(2026, 9, 23))
        result = build_proposal(state, augmented, profile, date(2026, 9, 23))
        milestones = [item for item in result['events'] if '全流程' in item['title'] and '里程碑' in item['title']]
        self.assertEqual(len(milestones), 1)
        self.assertEqual(milestones[0]['due_date'], '2026-10-23')

    def test_repeated_task_is_not_added_again(self):
        first = build_proposal(clean_calendar(None), {'calendar_intent': 'propose', 'operations': [operation('add', title='确认入职信息', due_date='2026-10-01')]})
        repeated = build_proposal({'confirmed': first['events'], 'pending': None}, {'calendar_intent': 'propose', 'operations': [operation('add', title='确认 入职信息', due_date='2026-10-01')]})
        self.assertIsNone(repeated)

    def test_similar_task_requires_clarification_instead_of_silent_update(self):
        first = build_proposal(clean_calendar(None), {
            'calendar_intent': 'propose',
            'operations': [operation('add', title='向HR确认入职地点、日期及体检要求', due_date='2026-10-01')],
        })
        existing = first['events'][0]
        updated = build_proposal({'confirmed': [existing], 'pending': None}, {
            'calendar_intent': 'propose',
            'operations': [operation('add', title='确认最终报到地点和体检要求', due_date='2026-10-02')],
        })
        self.assertEqual(len(updated['events']), 1)
        self.assertEqual(updated['events'][0]['id'], existing['id'])
        self.assertEqual(updated['events'][0]['due_date'], '2026-10-01')
        self.assertEqual(updated['changes'], [])
        self.assertEqual(updated['clarifications'][0]['existing_id'], existing['id'])
        self.assertEqual(updated['clarifications'][0]['proposed_date'], '2026-10-02')

    def test_same_title_with_new_date_requires_clarification(self):
        existing = clean_event({'id': 'view', 'title': '看房', 'due_date': '2026-10-09', 'detail': '核对房屋条件', 'date_basis': '建议日期', 'source_note': '信息待确认：与房东核验'})
        result = build_proposal(clean_calendar({'confirmed': [existing]}), {
            'calendar_intent': 'propose', 'operations': [operation('add', title='看房', due_date='2026-10-11')],
        })
        self.assertEqual(result['changes'], [])
        self.assertEqual(result['events'][0]['due_date'], '2026-10-09')
        self.assertIn('due_date', result['clarifications'][0]['different_fields'])

    def test_explicit_update_after_clarification_changes_existing_event(self):
        existing = clean_event({'id': 'view', 'title': '看房', 'due_date': '2026-10-09'})
        result = build_proposal(clean_calendar({'confirmed': [existing]}), {
            'calendar_intent': 'propose', 'operations': [operation('update', 'view', title='看房', due_date='2026-10-11')],
        })
        self.assertEqual(result['events'][0]['id'], 'view')
        self.assertEqual(result['events'][0]['due_date'], '2026-10-11')
        self.assertEqual(result['changes'][0]['type'], '修改')
        self.assertEqual(result['clarifications'], [])

    def test_duplicate_against_unconfirmed_pending_plan_is_also_blocked(self):
        pending = clean_event({'id': 'pending_view', 'title': '筛选并看房', 'due_date': '2026-10-09'})
        state = clean_calendar({'confirmed': [], 'pending': [pending]})
        result = build_proposal(state, {
            'calendar_intent': 'propose',
            'operations': [operation('add', title='看房并核对房屋条件', due_date='2026-10-11')],
        })
        self.assertEqual(result['events'], [pending])
        self.assertEqual(result['changes'], [])
        self.assertEqual(result['clarifications'][0]['existing_id'], 'pending_view')

    def test_undated_tasks_with_different_meanings_are_not_deduplicated(self):
        state = clean_calendar({'confirmed': [
            clean_event({'id': 'medical', 'title': '向单位核验医保转入', 'due_date': None}),
            clean_event({'id': 'move', 'title': '完成搬家与新住所入住', 'due_date': None}),
        ]})
        result = build_proposal(state, {'calendar_intent': 'propose', 'operations': [
            operation('add', title='向单位核验社保转入', due_date=None),
            operation('add', title='确认搬家安排与入住条件', due_date=None),
        ]})
        self.assertEqual(len(result['events']), 4)
        self.assertEqual(len(result['clarifications']), 0)

    def test_distinct_undated_steps_in_same_area_are_kept_separate(self):
        state = clean_calendar({'confirmed': [
            clean_event({'id': 'screen', 'title': '筛选房源', 'due_date': None}),
            clean_event({'id': 'electric', 'title': '核验水电过户', 'due_date': None}),
            clean_event({'id': 'onboarding', 'title': '向HR确认入职信息', 'due_date': None}),
        ]})
        result = build_proposal(state, {'calendar_intent': 'propose', 'operations': [
            operation('add', title='预约实地看房', due_date=None),
            operation('add', title='核验燃气过户', due_date=None),
            operation('add', title='向HR核验入职体检要求', due_date=None),
        ]})
        self.assertEqual(len(result['events']), 6)
        self.assertEqual(result['clarifications'], [])

    def test_undated_duplicate_asks_before_setting_a_date(self):
        state = clean_calendar({'confirmed': [clean_event({'id': 'view', 'title': '看房', 'due_date': None})]})
        result = build_proposal(state, {'calendar_intent': 'propose', 'operations': [
            operation('add', title='看房', due_date='2026-10-01'),
        ]})
        self.assertEqual(result['events'][0]['due_date'], None)
        self.assertEqual(result['changes'], [])
        self.assertEqual(result['clarifications'][0]['existing_id'], 'view')

    def test_cancelling_only_pending_undated_item_clears_pending_proposal(self):
        state = clean_calendar({'confirmed': [], 'pending': [clean_event({'id': 'draft', 'title': '核验宽带办理条件', 'due_date': None})]})
        result = build_proposal(state, {'calendar_intent': 'propose', 'operations': [operation('delete', 'draft')]})
        self.assertTrue(result['clear_pending'])
        self.assertEqual(result['events'], [])
        self.assertEqual(result['changes'], [])
        self.assertEqual(result['removed_pending'], [{'id': 'draft', 'title': '核验宽带办理条件'}])

    def test_cancelling_one_of_multiple_pending_undated_items_keeps_the_rest(self):
        state = clean_calendar({'confirmed': [], 'pending': [
            clean_event({'id': 'broadband', 'title': '核验宽带办理条件', 'due_date': None}),
            clean_event({'id': 'fund', 'title': '核验公积金转移条件', 'due_date': None}),
        ]})
        result = build_proposal(state, {'calendar_intent': 'propose', 'operations': [operation('delete', 'broadband')]})
        self.assertEqual([item['id'] for item in result['events']], ['fund'])
        self.assertEqual(result['removed_pending'], [{'id': 'broadband', 'title': '核验宽带办理条件'}])
        self.assertEqual(result['changes'], [{"id": "broadband", "type": "删除", "title": "核验宽带办理条件"}])

    def test_move_deadline_does_not_propose_unrelated_hr_edit(self):
        state = clean_calendar({'confirmed': [
            clean_event({'id': 'move', 'title': '完成搬家、旧住处交接与新住所入住', 'due_date': '2026-10-03'}),
            clean_event({'id': 'hr', 'title': '向HR确认入职事项', 'due_date': '2026-09-26'}),
        ]})
        model = {'calendar_intent': 'propose', 'operations': [
            operation('update', 'move', title='完成搬家、旧住处交接与新住所入住', due_date='2026-04-23'),
            operation('update', 'hr', title='向HR确认入职事项', due_date='2026-09-26'),
        ]}
        profile = {'move_deadline': '2026年10月2日'}
        augmented = augment_model_result(state, model, profile, '把搬家完成时间改到2026年10月2日，入职时间仍是2026年10月7日。', date(2026, 9, 23))
        result = build_proposal(state, augmented, profile, date(2026, 9, 23))
        self.assertEqual(result['changes'], [{"id": "move", "type": "修改", "title": "完成搬家、旧住处交接与新住所入住"}])

    def test_hire_date_change_moves_commute_trial_before_hire_date(self):
        state = clean_calendar({'confirmed': [
            clean_event({'id': 'commute', 'title': '通勤试走', 'due_date': '2026-10-10'}),
        ]})
        model = {'calendar_intent': 'none', 'operations': []}
        augmented = augment_model_result(state, model, {}, 'HR突然说入职日期改到了10月9号', date(2026, 9, 23))
        result = build_proposal(state, augmented, {}, date(2026, 9, 23))
        self.assertEqual(result['events'][0]['due_date'], '2026-10-08')

    def test_hire_change_uses_real_commute_diff_even_when_model_returns_conflict_mode(self):
        state = clean_calendar({'confirmed': [
            clean_event({'id': 'commute', 'title': '通勤试走', 'due_date': '2026-10-20'}),
            clean_event({'id': 'move', 'title': '完成搬家', 'due_date': '2026-10-14'}),
        ]})
        result = augment_model_result(state, {'response_mode': 'E', 'answer': '暂不修改日历', 'calendar_intent': 'none', 'operations': [],
                                              'quick_choices': ['保持搬家和通勤试走同日', '搬家提前到2026-10-13']},
                                      {'start_date': '2026-10-15'}, '我的入职日期改为2026年10月15日，请同步调整安排。', date(2026, 9, 23))
        proposal = build_proposal(state, result, {}, date(2026, 9, 23))
        self.assertEqual(result['response_mode'], 'D')
        self.assertEqual(proposal['changes'], [{'id': 'commute', 'type': '修改', 'title': '通勤试走'}])
        self.assertEqual(next(item for item in proposal['events'] if item['id'] == 'commute')['due_date'], '2026-10-14')
        self.assertEqual(result['quick_choices'], [])

    def test_earlier_hire_moves_later_move_completion_into_confirmation(self):
        state = clean_calendar({'confirmed': [
            clean_event({'id': 'move', 'title': '完成搬家', 'due_date': '2026-10-12'}),
        ]})
        augmented = augment_model_result(
            state, {'calendar_intent': 'none', 'operations': []}, {},
            '我的入职日期改到2026年10月9日，请同步调整安排。', date(2026, 9, 23),
        )
        proposal = build_proposal(state, augmented, {}, date(2026, 9, 23))
        self.assertEqual(proposal['changes'], [{'id': 'move', 'type': '修改', 'title': '完成搬家'}])
        self.assertEqual(proposal['events'][0]['due_date'], '2026-10-08')

    def test_earlier_hire_keeps_already_earlier_move_out_of_confirmation(self):
        state = clean_calendar({'confirmed': [
            clean_event({'id': 'move', 'title': '完成搬家', 'due_date': '2026-10-06'}),
        ]})
        # Simulate an over-eager model returning an unchanged move update.
        augmented = augment_model_result(
            state, {'calendar_intent': 'propose', 'operations': [operation('update', 'move', title='完成搬家', due_date='2026-10-06')]}, {},
            '我的入职日期改到2026年10月9日，请同步调整安排。', date(2026, 9, 23),
        )
        self.assertEqual(augmented['calendar_intent'], 'none')
        self.assertEqual(augmented['operations'], [])
        self.assertIn('保持不变', augmented['answer'])

    def test搬家完成先询问再删除相关日程(self):
        state = clean_calendar({'confirmed': [
            clean_event({'id': 'move', 'title': '搬家完成', 'due_date': '2026-10-02'}),
            clean_event({'id': 'hr', 'title': '向HR确认入职要求', 'due_date': '2026-10-03'}),
        ]})
        first = augment_model_result(state, {'calendar_intent': 'propose', 'operations': []}, {}, '我已经搬好家了', date(2026, 9, 23))
        self.assertEqual(first['calendar_intent'], 'propose')
        self.assertEqual(first['operations'][0]['action'], 'delete')
        second = augment_model_result(state, {'calendar_intent': 'none', 'operations': []}, {}, '已完成，删除相关日程', date(2026, 9, 23))
        self.assertEqual([item['action'] for item in second['operations']], ['delete'])
        self.assertEqual(second['operations'][0]['id'], 'move')

    def test_deleting_confirmed_undated_item_has_visible_delete_change(self):
        state = clean_calendar({'confirmed': [clean_event({'id': 'undated', 'title': '核验宽带办理条件', 'due_date': None})]})
        result = build_proposal(state, {'calendar_intent': 'propose', 'operations': [operation('delete', 'undated')]})
        self.assertEqual(result['changes'], [{'id': 'undated', 'type': '删除', 'title': '核验宽带办理条件'}])

    def test_mixed_update_and_delete_only_reports_real_differences(self):
        state = clean_calendar({'confirmed': [
            clean_event({'id': 'view', 'title': '看房', 'due_date': '2026-10-09'}),
            clean_event({'id': 'broadband', 'title': '办理宽带', 'due_date': '2026-10-16'}),
        ]})
        result = build_proposal(state, {'calendar_intent': 'propose', 'operations': [
            operation('update', 'view', title='看房', due_date='2026-10-11'),
            operation('delete', 'broadband', title='', due_date=None),
        ]})
        self.assertEqual({item['id'] for item in result['events']}, {'view'})
        self.assertEqual([item['type'] for item in result['changes']], ['修改', '删除'])

    def test_past_suggested_event_is_preserved_when_proposed(self):
        result = build_proposal(clean_calendar(None), {'calendar_intent': 'propose', 'operations': [operation('add', due_date='2026-09-13')]})
        self.assertEqual(result['events'][0]['due_date'], '2026-09-13')

    def test_add_then_edit_pending_without_confirming(self):
        original = clean_calendar(None)
        first = build_proposal(original, {'calendar_intent': 'propose', 'operations': [operation('add')]})
        self.assertEqual(original['confirmed'], [])
        self.assertEqual(len(first['events']), 1)
        event_id = first['events'][0]['id']
        second_state = clean_calendar({'confirmed': [], 'pending': first['events']})
        second = build_proposal(second_state, {'calendar_intent': 'propose', 'operations': [operation('update', event_id, due_date='2026-10-11')]})
        self.assertEqual(second['events'][0]['id'], event_id)
        self.assertEqual(second['events'][0]['due_date'], '2026-10-11')
        self.assertEqual(second['changes'][0]['type'], '修改')

    def test_delete_and_invalid_date(self):
        first = build_proposal(clean_calendar(None), {'calendar_intent': 'propose', 'operations': [operation('add')]})
        state = clean_calendar({'confirmed': first['events']})
        deleted = build_proposal(state, {'calendar_intent': 'propose', 'operations': [operation('delete', first['events'][0]['id'])]})
        self.assertEqual(deleted['events'], [])
        self.assertEqual(deleted['changes'][0]['type'], '删除')
        bad = build_proposal(clean_calendar(None), {'calendar_intent': 'propose', 'operations': [operation('add', due_date='2026-02-30')]})
        self.assertIsNone(bad)

    def test_no_calendar_intent_leaves_state_unchanged(self):
        self.assertIsNone(build_proposal(clean_calendar(None), {'calendar_intent': 'none', 'operations': []}))

    def test_custom_date_range_and_hard_deadline_survive_model_update(self):
        custom = clean_event({
            'id': 'm_test', 'title': '办理材料', 'start_date': '2026-10-09',
            'due_date': '2026-10-11', 'hard_deadline': True,
        })
        self.assertTrue(custom['hard_deadline'])
        state = clean_calendar({'confirmed': [custom]})
        updated = build_proposal(state, {'calendar_intent': 'propose', 'operations': [operation('update', 'm_test', title='准备办理材料', due_date='2026-10-12')]})
        self.assertEqual(updated['events'][0]['start_date'], '2026-10-09')
        self.assertEqual(updated['events'][0]['due_date'], '2026-10-12')
        self.assertTrue(updated['events'][0]['hard_deadline'])
        with self.assertRaises(ValueError):
            clean_event({'id': 'bad', 'title': '错误区间', 'start_date': '2026-10-12', 'due_date': '2026-10-11'})

    def test_move_date_shifts_handoff_task(self):
        state = clean_calendar({'confirmed': [
            clean_event({'id': 'move', 'title': '搬入新住处并完成入住检查', 'due_date': '2026-10-14'}),
            clean_event({'id': 'handoff', 'title': '确认搬家安排与旧住处交接', 'due_date': '2026-10-13'}),
        ]})
        result = build_proposal(state, {'calendar_intent': 'propose', 'operations': [operation('update', 'move', title='搬入新住处并完成入住检查', due_date='2026-10-05')]})
        dates = {item['id']: item['due_date'] for item in result['events']}
        self.assertEqual(dates['move'], '2026-10-05')
        self.assertEqual(dates['handoff'], '2026-10-04')

    def test_move_date_does_not_drag_unrelated_old_handoff_into_february(self):
        state = clean_calendar({'confirmed': [
            clean_event({'id': 'move', 'title': '搬入新住处并完成入住检查', 'due_date': '2026-10-14'}),
            clean_event({'id': 'old_handoff', 'title': '旧住处交接', 'due_date': '2026-02-26'}),
        ]})
        result = build_proposal(state, {'calendar_intent': 'propose', 'operations': [
            operation('update', 'move', title='搬入新住处并完成入住检查', due_date='2026-10-02'),
        ]})
        dates = {item['id']: item['due_date'] for item in result['events']}
        self.assertEqual(dates['move'], '2026-10-02')
        self.assertEqual(dates['old_handoff'], '2026-02-26')
        self.assertNotIn('2026-02-14', dates.values())

    def test_explicit_move_deadline_overrides_contradictory_model_dates(self):
        state = clean_calendar({'confirmed': [
            clean_event({'id': 'complete', 'title': '完成搬家、旧住处交接与新住所入住', 'due_date': '2026-10-14'}),
            clean_event({'id': 'prepare', 'title': '确认搬家安排与新住所入住条件', 'due_date': '2026-10-01'}),
        ]})
        result = build_proposal(state, {'calendar_intent': 'propose', 'operations': [
            operation('update', 'complete', title='完成搬家、旧住处交接与新住所入住', due_date='2026-04-23'),
            operation('update', 'prepare', title='确认搬家安排与新住所入住条件', due_date='2026-07-13'),
        ]}, {'move_deadline': '2026年10月2日'}, date(2026, 9, 23))
        dates = {item['id']: item['due_date'] for item in result['events']}
        self.assertEqual(dates['complete'], '2026-10-02')
        self.assertEqual(dates['prepare'], '2026-09-23')

    def test_explicit_move_date_updates_pending_draft_when_profile_is_stale(self):
        state = clean_calendar({'confirmed': [], 'pending': [
            clean_event({'id': 'move', 'title': '完成搬家并办理新旧住处交接', 'due_date': '2026-10-15'})
        ]})
        augmented = augment_model_result(
            state,
            {'response_mode': 'D', 'calendar_intent': 'propose', 'operations': [], 'answer': ''},
            {'move_deadline': '2026-10-15'},
            '搬家改到10月13日',
            date(2026, 9, 29),
        )
        self.assertEqual(augmented['operations'][0]['due_date'], '2026-10-13')
        proposal = build_proposal(state, augmented, {'move_deadline': '2026-10-15'}, date(2026, 9, 29))
        changed = next(item for item in proposal['changes'] if item['id'] == 'move')
        self.assertEqual(changed['type'], '修改')
        self.assertEqual(proposal['events'][0]['due_date'], '2026-10-13')


if __name__ == '__main__':
    unittest.main()
