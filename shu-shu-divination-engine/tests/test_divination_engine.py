import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
ENGINE_SCRIPT = SCRIPTS_DIR / "divination_engine.py"


def load_module(name: str, path: Path):
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


engine = load_module("shu_shu_divination_engine", ENGINE_SCRIPT)


class RoutingTests(unittest.TestCase):
    def test_lost_item_routes_to_meihua(self) -> None:
        result = engine.analyze_prompt("我钥匙今天早上突然找不到了，最后一次确认是在卧室书桌。数字是 3、8、2。")
        self.assertEqual("meihua", result["routing"]["selected_method"])
        self.assertEqual("computed", result["execution"]["status"])
        self.assertEqual(2, result["execution"]["moving_line"])

    def test_meihua_requires_complete_random_numbers_or_time_anchor(self) -> None:
        result = engine.analyze_prompt("我钥匙找不到了，我现在只想到两个数字 3 和 8，帮我看看今天还能不能找到。")
        self.assertEqual("meihua", result["routing"]["selected_method"])
        self.assertEqual("needs_input", result["execution"]["status"])
        self.assertIn("补足 3 个随机数字", result["execution"]["missing_inputs"][0])

    def test_relative_time_can_anchor_meihua_execution(self) -> None:
        result = engine.analyze_prompt(
            "今天下午 3 点我突然发现钥匙不见了，你帮我看看今天还能不能找到。",
            reference_time="2026-03-19T09:00:00",
        )
        self.assertEqual("meihua", result["routing"]["selected_method"])
        self.assertEqual("2026-03-19T15:00:00", result["compound_analysis"]["breakdown"][0]["recognized_inputs"]["event_time"])
        self.assertEqual("computed", result["execution"]["status"])
        self.assertEqual("event_time", result["execution"]["basis"])

    def test_relationship_result_routes_to_liuyao(self) -> None:
        result = engine.analyze_prompt("我和前任最近又开始联系了，我想知道这段感情有没有复合并稳定走下去的可能，大概什么时候会有明确结果。")
        self.assertEqual("liuyao", result["routing"]["selected_method"])
        self.assertIn("成败", result["execution"]["framework"])

    def test_strategy_routes_to_qimen(self) -> None:
        result = engine.analyze_prompt("下周去上海见客户，我有周二上午和周四下午两个时间，你帮我看哪次去谈更顺。")
        self.assertEqual("qimen", result["routing"]["selected_method"])
        self.assertIn("择时", result["execution"]["framework"])
        self.assertIn("周二上午", result["execution"]["recognized_inputs"]["candidate_slots"])

    def test_hidden_motives_route_to_liuren(self) -> None:
        result = engine.analyze_prompt("我怀疑合伙人最近有别的盘算，想看他真实想法，还有这件事后面会怎么演变。")
        self.assertEqual("liuren", result["routing"]["selected_method"])
        self.assertIn("隐藏动机", result["execution"]["framework"])
        self.assertIn("合伙人", result["execution"]["recognized_inputs"]["roles"])

    def test_bazi_is_routed_out(self) -> None:
        result = engine.analyze_prompt("大师，我的八字是身强还是身弱，喜神和忌神分别是什么？")
        self.assertIsNone(result["routing"]["selected_method"])
        self.assertEqual("bazi", result["routing"]["adjacent_system"])
        self.assertEqual("adjacent-rewrite", result["execution"]["status"])

    def test_bazi_dominant_compound_prompt_is_routed_out(self) -> None:
        result = engine.analyze_prompt("请你分析这个八字命盘，推演从 2026 年开始的大运流年走势。再告诉我 2026 年适不适合把写作当主业。")
        self.assertIsNone(result["routing"]["selected_method"])
        self.assertEqual("bazi", result["routing"]["adjacent_system"])
        self.assertEqual("adjacent-rewrite", result["execution"]["status"])

    def test_compound_prompt_is_split(self) -> None:
        result = engine.analyze_prompt("我适合打工还是创业？什么时候能走财运？2026 年把写作当主业行不行？")
        self.assertTrue(result["compound"])
        self.assertGreaterEqual(len(result["sub_questions"]), 3)
        self.assertEqual("liuyao", result["routing"]["selected_method"])

    def test_method_only_request_stops_after_routing(self) -> None:
        result = engine.analyze_prompt("先别算，只告诉我下周见客户哪天更顺，这类问题更适合六爻还是奇门？")
        self.assertTrue(result["method_only_request"])
        self.assertEqual("method-only", result["execution"]["status"])


class ExecutionTests(unittest.TestCase):
    def test_liuyao_computes_when_event_time_is_available(self) -> None:
        result = engine.analyze_prompt("这个合作能不能成，什么时候能有结果？", event_time="2026-03-18T15:00:00")
        payload = result["execution"]["computed_payload"]
        self.assertEqual("liuyao", result["routing"]["selected_method"])
        self.assertEqual("computed", result["execution"]["status"])
        self.assertEqual("liuyao.time-adapter", result["execution"]["engine"])
        self.assertEqual("蒙", payload["hexagrams"]["main"]["name"])
        self.assertEqual("渙", payload["hexagrams"]["changed"]["name"])
        self.assertEqual("世", payload["hexagrams"]["main"]["lines"][3]["role"])
        self.assertEqual("應", payload["hexagrams"]["main"]["lines"][5]["role"])
        self.assertEqual("六五", payload["movement"]["focus_line"])
        self.assertEqual("蒙之渙", payload["movement"]["pair_name"])
        self.assertEqual("阴变阳", payload["movement"]["moving_lines"][0]["movement"])
        self.assertEqual("四世卦", payload["hexagrams"]["main"]["shi_ying_pattern"])
        self.assertEqual("官丙子水", payload["hexagrams"]["main"]["body_line"])
        self.assertEqual("丙午年辛卯月辛卯日丙申時", payload["time_anchor"]["ganzhi"])

    def test_qimen_computes_from_explicit_candidate_times(self) -> None:
        result = engine.analyze_prompt("2026-03-20 09:00 和 2026-03-22 15:00 这两个时间，哪个更适合去见客户谈合作？")
        interpretation = result["execution"]["computed_payload"]["interpretation"]
        self.assertEqual("qimen", result["routing"]["selected_method"])
        self.assertEqual([], result["compound_analysis"]["breakdown"][0]["recognized_inputs"]["numbers"])
        self.assertEqual("computed", result["execution"]["status"])
        self.assertEqual("candidate-comparison", result["execution"]["computed_payload"]["mode"])
        self.assertEqual(2, len(result["execution"]["computed_payload"]["candidates"]))
        self.assertEqual("西北", interpretation["recommended_direction"])
        self.assertEqual("生", interpretation["recommended_door"])

    def test_liuren_computes_when_event_time_is_available(self) -> None:
        result = engine.analyze_prompt(
            "我怀疑合伙人最近有别的盘算，想看他真实想法，还有这件事后面会怎么演变。",
            event_time="2026-03-18T15:00:00",
        )
        interpretation = result["execution"]["computed_payload"]["interpretation"]
        self.assertEqual("liuren", result["routing"]["selected_method"])
        self.assertEqual("computed", result["execution"]["status"])
        self.assertEqual("賊尅", result["execution"]["computed_payload"]["pattern"][0])
        self.assertIn("core_dynamic", interpretation)
        self.assertIn("development_path", interpretation)
        self.assertIn("surface_vs_hidden", interpretation)
        self.assertGreaterEqual(len(interpretation["action_guidance"]), 3)


class CompoundPriorityTests(unittest.TestCase):
    def test_compound_analysis_marks_primary_question_and_deferred_questions(self) -> None:
        result = engine.analyze_prompt("我适合打工还是创业？什么时候能走财运？2026年把写作当主业行不行？")
        self.assertTrue(result["compound"])
        self.assertEqual(2, result["compound_analysis"]["primary_index"])
        self.assertEqual("2026年把写作当主业行不行", result["compound_analysis"]["primary_question"])
        self.assertEqual("liuyao", result["routing"]["selected_method"])
        self.assertEqual(0, len(result["execution"]["deferred_questions"]))

    def test_compound_prompt_prioritizes_executable_question_over_first_question(self) -> None:
        result = engine.analyze_prompt("我适合打工还是创业？2026-03-20 09:00 和 2026-03-22 15:00 哪个时间更适合去见客户谈合作？")
        self.assertTrue(result["compound"])
        self.assertEqual("qimen", result["routing"]["selected_method"])
        self.assertEqual("2026-03-20 09:00 和 2026-03-22 15:00 哪个时间更适合去见客户谈合作", result["compound_analysis"]["primary_question"])
        self.assertEqual("candidate-comparison", result["execution"]["computed_payload"]["mode"])
        self.assertEqual(0, len(result["execution"]["deferred_questions"]))

    def test_compound_analysis_exposes_user_facing_summary(self) -> None:
        result = engine.analyze_prompt("我适合打工还是创业？什么时候能走财运？2026年把写作当主业行不行？")
        self.assertIn("summary", result["compound_analysis"])
        self.assertIn("this_round", result["compound_analysis"]["summary"])
        self.assertIn("selection_logic", result["compound_analysis"]["summary"])

    def test_numeric_fragment_is_merged_into_supporting_inputs(self) -> None:
        result = engine.analyze_prompt("今天下午3点我突然发现钥匙不见了，最后在卧室书桌见过。数字是3、8、2。", reference_time="2026-03-19T09:00:00")
        self.assertEqual("meihua", result["routing"]["selected_method"])
        self.assertEqual(1, len(result["compound_analysis"]["supporting_fragments"]))
        self.assertEqual(0, len(result["execution"]["deferred_questions"]))
        self.assertEqual("supporting", result["compound_analysis"]["breakdown"][1]["bucket"])


class AnswerCardAndResponseTests(unittest.TestCase):
    def test_answer_cards_are_exposed(self) -> None:
        meihua = engine.analyze_prompt("今天下午3点我突然发现钥匙不见了，最后在卧室书桌见过。数字是3、8、2。", reference_time="2026-03-19T09:00:00")
        liuyao = engine.analyze_prompt("这个合作能不能成，什么时候能有结果？", event_time="2026-03-18T15:00:00")
        qimen = engine.analyze_prompt("2026-03-20 09:00 和 2026-03-22 15:00 这两个时间，哪个更适合去见客户谈合作？")
        liuren = engine.analyze_prompt("我怀疑合伙人最近有别的盘算，想看他真实想法，还有这件事后面会怎么演变。", event_time="2026-03-18T15:00:00")

        self.assertEqual("meihua", meihua["execution"]["answer_card"]["method"])
        self.assertEqual("liuyao", liuyao["execution"]["answer_card"]["method"])
        self.assertEqual("qimen", qimen["execution"]["answer_card"]["method"])
        self.assertEqual("liuren", liuren["execution"]["answer_card"]["method"])
        self.assertGreaterEqual(len(meihua["execution"]["answer_card"]["action_advice"]), 3)
        self.assertGreaterEqual(len(liuyao["execution"]["answer_card"]["key_signals"]), 2)
        self.assertGreaterEqual(len(qimen["execution"]["answer_card"]["action_advice"]), 3)
        self.assertGreaterEqual(len(liuren["execution"]["answer_card"]["follow_up_focus"]), 1)
        self.assertIn("末传", liuren["execution"]["answer_card"]["follow_up_focus"][0])

    def test_final_response_collects_answer_card_sections(self) -> None:
        result = engine.analyze_prompt("2026-03-20 09:00 和 2026-03-22 15:00 这两个时间，哪个更适合去见客户谈合作？")
        final_response = result["final_response"]
        titles = [section["title"] for section in final_response["sections"]]
        self.assertEqual("computed", final_response["status"])
        self.assertTrue(final_response["headline"])
        self.assertTrue(final_response["reply"])
        self.assertIn("适用术数", titles)
        self.assertIn("测算结论", titles)
        self.assertIn("下一步建议", titles)


class CliTests(unittest.TestCase):
    def test_cli_outputs_json(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ENGINE_SCRIPT), "--prompt", "今天下午 3 点我突然发现钥匙不见了，最后在卧室书桌见过。数字是 3、8、2。", "--reference-time", "2026-03-19T09:00:00", "--output", "json"],
            check=True,
            text=True,
            capture_output=True,
            encoding="utf-8",
        )
        payload = json.loads(completed.stdout)
        self.assertEqual("meihua", payload["routing"]["selected_method"])
        self.assertEqual("computed", payload["execution"]["status"])

    def test_cli_outputs_text_report(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ENGINE_SCRIPT), "--prompt", "2026-03-20 09:00 和 2026-03-22 15:00 这两个时间，哪个更适合去见客户谈合作？", "--output", "text"],
            check=True,
            text=True,
            capture_output=True,
            encoding="utf-8",
        )
        self.assertIn("适用术数:", completed.stdout)
        self.assertIn("测算结论:", completed.stdout)


if __name__ == "__main__":
    unittest.main()
