import ast
import unittest


class VideoInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open("addon.py", "r", encoding="utf-8") as addon_file:
            cls.source = addon_file.read()
        cls.tree = ast.parse(cls.source)
        with open("core/core.py", "r", encoding="utf-8") as core_file:
            cls.core_source = core_file.read()
        with open("core/secret.py", "r", encoding="utf-8") as secret_file:
            cls.secret_source = secret_file.read()
        cls.functions = {
            node.name: node
            for node in cls.tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

    def test_detail_page_exposes_all_interactions(self):
        for function_name in (
            "video_like",
            "video_coin",
            "video_favorite",
            "video_triple",
        ):
            self.assertIn(function_name, self.functions)
        self.assertIn("items.extend(_interaction_items(bv, data, cover))", self.source)

    def test_mutation_endpoints_use_web_cookie_apis(self):
        for endpoint in (
            "/x/web-interface/archive/like",
            "/x/web-interface/coin/add",
            "/x/v3/fav/resource/deal",
            "/x/web-interface/archive/like/triple",
        ):
            self.assertIn(endpoint, self.source)
        self.assertIn('"csrf": _interaction_csrf()', self.source)
        self.assertIn("c.interaction_post", self.source)

    def test_mutations_warm_and_persist_the_web_session_without_retrying(self):
        self.assertIn("warmup_url", self.core_source)
        self.assertIn("srt.merge_cookies(session.cookies.get_dict())", self.core_source)
        self.assertIn('headers["Origin"] = "https://www.bilibili.com"', self.core_source)
        self.assertIn('payload.setdefault("csrf_token", csrf)', self.core_source)
        self.assertIn("def merge_cookies", self.secret_source)
        interaction_source = self.core_source[
            self.core_source.index("def interaction_post"):self.core_source.index("# 记录历史")
        ]
        self.assertEqual(1, interaction_source.count("return postjson("))

    def test_risk_control_errors_do_not_claim_success(self):
        self.assertIn("code in (-403, -352, -412)", self.source)
        self.assertIn("请勿连续重试", self.source)

    def test_irreversible_coin_actions_require_confirmation(self):
        for function_name in ("video_coin", "video_triple"):
            calls = [
                node
                for node in ast.walk(self.functions[function_name])
                if isinstance(node, ast.Call)
            ]
            self.assertTrue(
                any(
                    isinstance(call.func, ast.Attribute)
                    and call.func.attr == "yesno"
                    for call in calls
                )
            )


if __name__ == "__main__":
    unittest.main()
