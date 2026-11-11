import asyncio
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lab.backends.demo import DemoBackend
from lab.catalog import load_catalog, DEFAULT_TASK
from lab.config import ROOT, load_config
from lab.generate import generate
from lab.reselect import reselect_recording
from lab.runner import ModeRunner
from lab.schema import response_schema, validate_answer
from lab.selection import choose_answer
from lab.suite import run_suite
from lab.storage import suite_lock
from lab.reselect import reselect_path
from lab.task import check_candidate, evaluate, load_task, rows_from_solution, solve


class CountingBackend(DemoBackend):
    def __init__(self, task):
        super().__init__(task)
        self.count = 0

    async def call(self, *args):
        self.count += 1
        return await super().call(*args)


class SelectionAndCatalogTests(unittest.TestCase):
    def setUp(self):
        self.task = load_task(DEFAULT_TASK)
        self.solution = solve(self.task)[0]
        self.answer = {'schedule': rows_from_solution(self.task, self.solution), 'message': 'Candidate', 'assignments': []}

    def candidates(self):
        wrong = copy.deepcopy(self.answer)
        wrong['schedule'][0]['room'], wrong['schedule'][1]['room'] = wrong['schedule'][1]['room'], wrong['schedule'][0]['room']
        return [{'agent':f'worker-{i}', 'id':str(i), 'answer':copy.deepcopy(a)}
                for i,a in [(1,wrong),(2,wrong),(3,self.answer),(4,wrong)]]

    def test_public_checker_beats_wrong_majority_without_reference(self):
        records = self.candidates()
        self.assertNotEqual(choose_answer(records)[0], self.answer)
        with patch('lab.task.solve', side_effect=AssertionError('No solver during selection')), \
             patch('lab.task.evaluate', side_effect=AssertionError('No reference during selection')):
            selected, ids = choose_answer(records, self.task, 'public-checker')
        self.assertEqual(selected, self.answer)
        self.assertEqual(ids, ['3'])

    def test_historical_case_109_correct_candidate_is_preserved(self):
        fixture=json.loads((ROOT/'tests/fixtures/selection-case-109.json').read_text())
        task=fixture['task']; records=fixture['candidates']
        old,_=choose_answer(records)
        revised,ids=choose_answer(records,task,'public-checker')
        solution=solve(task)[0]
        self.assertEqual(evaluate(task,old,solution)['score'],62.5)
        self.assertEqual(ids,fixture['expected_selected_call_ids'])
        self.assertTrue(evaluate(task,revised,solution)['exact'])

    def test_structural_validity_precedes_clue_count(self):
        invalid = copy.deepcopy(self.answer)
        invalid['schedule'].append(invalid['schedule'][0])
        candidates = [{'agent':'a','id':'1','answer':invalid}, {'agent':'b','id':'2','answer':self.answer}]
        self.assertEqual(choose_answer(candidates,self.task,'public-checker')[1], ['2'])
        self.assertFalse(check_candidate(self.task,invalid)['fully_satisfied'])

    def test_deterministic_tie_preserves_all_supporting_ids(self):
        candidates = [{'agent':f'worker-{i}','id':str(i),'answer':self.answer} for i in [4,2,1,3]]
        self.assertEqual(choose_answer(candidates,self.task,'public-checker')[1], ['1','2','3','4'])

    def test_catalog_is_ten_cases_with_three_four_three_levels(self):
        tasks=load_catalog()
        self.assertEqual(len(tasks),10)
        for level,count,n,categories in [('easy',3,4,3),('medium',4,5,4),('hard',3,6,4)]:
            subset=[t for t in tasks if t['difficulty']==level]
            self.assertEqual(len(subset),count)
            for task in subset:
                self.assertEqual(len(task['slots']),n)
                self.assertEqual(len(task['categories']),categories)
                solutions=solve(task)
                self.assertEqual(len(solutions),1)
                answer={'schedule':rows_from_solution(task,solutions[0]),'message':'Done','assignments':[]}
                validate_answer(answer,task)
                self.assertEqual(response_schema(task)['properties']['schedule']['minItems'],n)
                self.assertTrue(check_candidate(task,answer)['fully_satisfied'])

    def test_suite_directory_cannot_have_two_controllers(self):
        with tempfile.TemporaryDirectory() as tmp:
            with suite_lock(tmp):
                with self.assertRaisesRegex(ValueError, 'Another suite controller'):
                    with suite_lock(tmp):
                        self.fail('Second controller acquired the lock.')
            with suite_lock(tmp):
                pass

    def test_unsafe_offline_task_id_cannot_write_outside_output(self):
        data={'task':{**self.task,'id':'../../escape'},'synthetic':False,'config':{},'results':[]}
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'experiment.json'; source.write_text(json.dumps(data))
            out=Path(tmp)/'out'
            with self.assertRaisesRegex(ValueError,'Unsafe'):
                reselect_path(source,out)
            self.assertFalse(out.exists())

    def test_new_levels_are_reproducible(self):
        for level in ['easy','medium','hard']:
            self.assertEqual(generate(23,level),generate(23,level))

    def test_reselection_keeps_calls_and_token_costs(self):
        records=self.candidates()
        for r in records:
            r.update(round=1,status='ok',usage={'input_tokens':10,'output_tokens':5},own_call_id=None,
                     visible_call_ids=[],start_seconds=0,end_seconds=1)
        original={'task':self.task,'synthetic':False,'config':{},'results':[{'mode':'exchange','repeat':1,
            'calls':records,'final_answer':records[0]['answer'],'selected_call_ids':['1'],
            'totals':{'calls':4,'input_tokens':40,'output_tokens':20},'status':'complete',
            'evaluation':evaluate(self.task,records[0]['answer'],self.solution)}]}
        revised=reselect_recording(original,'public-checker')
        self.assertEqual(revised['offline_reselection']['new_model_calls'],0)
        self.assertTrue(revised['results'][0]['evaluation']['exact'])
        self.assertEqual(revised['results'][0]['totals'],original['results'][0]['totals'])
        self.assertEqual(revised['results'][0]['selected_call_ids'],['3'])
        self.assertEqual(original['results'][0]['selected_call_ids'],['1'])


class ResumeAndSuiteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.task=load_task(DEFAULT_TASK)
        self.config=load_config(ROOT/'configs/classroom.toml')
        self.backend=CountingBackend(self.task)

    async def run_mode(self,mode='solo',saved=None,checkpoint=None):
        return await ModeRunner(self.task,self.config,self.backend,mode,progress=lambda _:None,
            saved_state=saved,call_checkpoint=checkpoint).run()

    async def test_completed_call_is_reused_and_remaining_calls_run_once(self):
        initial=await self.run_mode()
        saved={'calls':[initial['calls'][0]],'elapsed_seconds':initial['calls'][0]['end_seconds']}
        self.backend.count=0
        resumed=await self.run_mode(saved=saved)
        self.assertEqual(self.backend.count,2)
        self.assertEqual(resumed['totals']['calls'],3)
        self.assertEqual(resumed['calls'][0],initial['calls'][0])

    async def test_interrupted_parallel_wave_launches_no_calls(self):
        initial=await self.run_mode('exchange')
        calls=copy.deepcopy(initial['calls'][:4])
        calls[1].update(status='running',answer=None,usage=None)
        self.backend.count=0
        result=await self.run_mode('exchange',{'calls':calls,'elapsed_seconds':1})
        self.assertEqual(self.backend.count,0)
        self.assertEqual(result['status'],'stopped')
        self.assertFalse(result['totals']['usage_complete'])
        self.assertIn('interrupted',result['stop_reason'])
        self.assertEqual(len(result['calls']),4)

    async def test_time_budget_is_not_reset_by_resume(self):
        initial=await self.run_mode()
        self.backend.count=0
        result=await self.run_mode(saved={'calls':initial['calls'][:1],
            'elapsed_seconds':self.config['budget']['max_seconds']+1})
        self.assertEqual(self.backend.count,0)
        self.assertEqual(len(result['calls']),1)
        self.assertIn('time',result['stop_reason'])

    async def test_journal_written_before_backend_call(self):
        snapshots=[]
        original=self.backend.call
        async def guarded(*args):
            self.assertTrue(snapshots)
            self.assertEqual(snapshots[-1]['calls'][-1]['status'],'running')
            return await original(*args)
        self.backend.call=guarded
        result=await self.run_mode(checkpoint=lambda state:snapshots.append(copy.deepcopy(state)))
        self.assertEqual(result['status'],'complete')
        self.assertEqual(len(snapshots),6)
        self.assertEqual(snapshots[-1]['calls'][-1]['status'],'ok')

    async def test_solo_budget_is_twelve_real_or_synthetic_calls(self):
        result=await self.run_mode('solo-budget')
        self.assertEqual(self.backend.count,12)
        self.assertEqual(result['totals']['calls'],12)
        self.assertEqual(len(result['diagnostics']['round_curve']),12)

    async def test_suite_resume_skips_terminal_modes_and_validates_identity(self):
        backend=self.backend
        factory=lambda task:backend
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'suite'
            a=await run_suite([self.task],self.config,'demo','synthetic-fixture',out,
                modes=['solo','exchange'],progress=lambda _:None,backend_factory=factory)
            count=backend.count
            b=await run_suite([self.task],self.config,'demo','synthetic-fixture',out,
                modes=['solo','exchange'],resume=True,progress=lambda _:None,backend_factory=factory)
            self.assertEqual(backend.count,count)
            self.assertEqual(a['results'],b['results'])
            self.assertEqual(b['recorded_runs'],2)
            self.assertTrue((out/'index.html').is_file())
            self.assertTrue((out/'summary.csv').is_file())
            changed=copy.deepcopy(self.config);changed['rounds']=4
            with self.assertRaisesRegex(ValueError,'differs'):
                await run_suite([self.task],changed,'demo','synthetic-fixture',out,
                    modes=['solo','exchange'],resume=True,progress=lambda _:None,backend_factory=factory)
            self.assertEqual(backend.count,count)

    async def test_suite_replays_completed_call_after_process_style_interruption(self):
        backend=self.backend
        factory=lambda task:backend
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'suite'
            await run_suite([self.task],self.config,'demo','synthetic-fixture',out,
                modes=['solo'],progress=lambda _:None,backend_factory=factory)
            path=next(out.rglob('state.json'))
            state=json.loads(path.read_text())
            state={'calls':state['calls'][:1],'elapsed_seconds':state['calls'][0]['end_seconds']}
            path.write_text(json.dumps(state))
            backend.count=0
            await run_suite([self.task],self.config,'demo','synthetic-fixture',out,
                modes=['solo'],resume=True,progress=lambda _:None,backend_factory=factory)
            self.assertEqual(backend.count,2)

    async def test_suite_unknown_call_is_stopped_and_never_retried(self):
        factory=lambda task:self.backend
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'suite'
            await run_suite([self.task],self.config,'demo','synthetic-fixture',out,
                modes=['solo'],progress=lambda _:None,backend_factory=factory)
            path=next(out.rglob('state.json'))
            state=json.loads(path.read_text())
            call=state['calls'][0]
            call.update(status='running',answer=None,usage=None,estimated_usd=0)
            path.write_text(json.dumps({'calls':[call],'elapsed_seconds':.01}))
            self.backend.count=0
            for _ in range(2):
                result=await run_suite([self.task],self.config,'demo','synthetic-fixture',out,
                    modes=['solo'],resume=True,progress=lambda _:None,backend_factory=factory)
                self.assertEqual(result['by_mode']['solo']['stopped'],1)
                self.assertEqual(result['by_mode']['solo']['unknown_usage_runs'],1)
                self.assertEqual(self.backend.count,0)

    async def test_source_call_and_result_changes_are_diagnosed(self):
        result=await self.run_mode('exchange')
        self.assertEqual(len(result['diagnostics']['round_curve']),3)
        changes=result['diagnostics']['revisions']
        self.assertEqual(sum(changes.values()),8)
        self.assertFalse(result['diagnostics']['correct_worker_lost'])


if __name__=='__main__':unittest.main()
