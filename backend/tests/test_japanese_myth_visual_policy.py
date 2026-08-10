import copy
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.image.prompt_compiler import (  # noqa: E402
    compile_image_prompt,
    prepare_scene_contract_source,
)
from app.services.image.comfyui_service import (  # noqa: E402
    _apply_longtube_dark_manhwa_style,
    _z_image_japanese_myth_positive_guard,
    _should_ignore_object_person_segmentation,
    _should_ignore_strict_nonhuman_person_segmentation,
    _should_use_ch3_ep7_oath_items_layout,
    expected_effective_image_model_id,
)
from app.services.llm.visual_policy import apply_script_visual_policy  # noqa: E402
from app.routers.image import _resume_prompt_mismatch_requires_regeneration  # noqa: E402


class JapaneseMythVisualPolicyTests(unittest.TestCase):
    def _script(self):
        common = {
            "visual_year": "신화시대",
            "visual_period": "신화 시대",
            "visual_location": "미소기 의식 (정화) / 태양, 달, 폭풍신의 탄생과 우주 질서의 분할",
            "visual_evidence": "source workbook 제1장_대본.xlsx",
        }
        cuts = [
            {
                **common,
                "cut_number": 1,
                "narration": "皆さん、 こんにちは。 日本 の 歴史 の 秘密 を 探る 時間 です。",
                "image_prompt": "A beautiful ancient Japanese coastal landscape. High ocean waves crashing against jagged rocks. Editorial landscape photography.",
            },
            {
                **common,
                "cut_number": 2,
                "narration": "前回 は、 恐ろしい 地下 世界 から 逃げ帰った 伊邪那岐 の お話 でした。",
                "image_prompt": "A lone, exhausted god panting heavily on a green grassy hill, looking back at a dark cave. Gritty documentary photography.",
            },
            {
                **common,
                "cut_number": 3,
                "narration": "妻 の 恐ろしい 呪い を 退け、 なんとか 地上 へ と 生還 した の です。",
                "image_prompt": "A perfectly balanced golden scale, with a bright white light outweighing a dark stone. Conceptual macro photography.",
            },
            {
                **common,
                "cut_number": 4,
                "narration": "しかし、 助かった と 安堵 する の は まだ 早 すぎ ました。",
                "image_prompt": "A heavy black cloud creeping over the sun. Action weather photography.",
            },
            {
                **common,
                "cut_number": 5,
                "narration": "伊邪那岐 の 身体 は、 想像 を 絶する ほど 汚れて いた から です。",
                "image_prompt": "Dark oily stains covering his elegant clothes and emitting black smoke. Conceptual horror photography.",
            },
            {
                **common,
                "cut_number": 6,
                "narration": "黄泉の国 という の は、 死 と 腐敗 が 支配 する 空間 です。",
                "image_prompt": "A glowing flower instantly withering in darkness. Macro nature photography.",
            },
            {
                **common,
                "cut_number": 7,
                "narration": "日本 の 神道 において は、 この 死 の 匂い を 穢れ と 呼び ます。",
                "image_prompt": "A pristine bronze mirror covered in sticky dark mud. Macro product photography.",
            },
            {
                **common,
                "cut_number": 14,
                "narration": "これ が、 現代 の 神社 でも 行われる 禊ぎ の ルーツ と なる の です。",
                "image_prompt": "A wooden ladle pouring crystal clear water over hands at a traditional Shinto shrine.",
            },
            {
                **common,
                "cut_number": 15,
                "narration": "神様 が 自ら 身体 を 洗う という、 日本 神話 独特 の 展開 です。",
                "image_prompt": "A divine figure stepping into a glowing river.",
            },
            {
                **common,
                "cut_number": 16,
                "narration": "伊邪那岐 は 川辺 に 立つ と、 身 に 着けて いた 物 を 脱ぎ 始め ました。",
                "image_prompt": "Elegant silk robes and golden belts tossed on riverbank stones.",
            },
            {
                **common,
                "cut_number": 17,
                "narration": "杖 を 投げ捨て、 帯 を ほどき、 衣服 を 順番 に 脱いで いき ます。",
                "image_prompt": "A wooden walking staff falling into grass beside the water.",
            },
            {
                **common,
                "cut_number": 18,
                "narration": "すると 驚く べき こと に、 その 脱ぎ捨てた 物 から も 神 が 生まれ ます。",
                "image_prompt": "Glowing orbs floating from discarded clothing.",
            },
            {
                **common,
                "cut_number": 20,
                "narration": "たった 一つ の 動作 から も、 無数 の 命 が 誕生 する 創造 の 力。",
                "image_prompt": "An ancient Japanese amulet glowing on a wooden table.",
            },
            {
                **common,
                "cut_number": 34,
                "narration": "海 の 底 から、 中間 から、 そして 水面 から、 次々 と 命 が 溢れ出し ました。",
                "image_prompt": "A glowing underwater city of divine spirits among coral reefs.",
            },
            {
                **common,
                "cut_number": 37,
                "narration": "彼 の 肉体 は、 かつて ない ほど の 清浄 な 力 で 満ち溢れて いました。",
                "image_prompt": "A golden aura radiating from a muscular divine chest.",
            },
            {
                **common,
                "cut_number": 38,
                "narration": "マイナス の 状態 から ゼロ を 経て、 究極 の プラス へ と 転じた 瞬間 です。",
                "image_prompt": "A dark gauge exploding into a white star.",
            },
            {
                **common,
                "cut_number": 43,
                "narration": "この 最後 の 洗浄 から、 日本 神話 の 最高 傑作 たち が 産声を上げ ます。",
                "image_prompt": "An explosive golden spark bursting from splashing water.",
            },
            {
                **common,
                "cut_number": 60,
                "narration": "その 宝石 を 太陽 の 女神 に 授け ました。",
                "image_prompt": "Izanagi hands a necklace to Amaterasu.",
            },
            {
                **common,
                "cut_number": 89,
                "narration": "吹き荒れる 暴風 の 中 から、 筋骨 隆々 と した 男神 が 姿 を 現し ました。",
                "image_prompt": "A shirtless muscular god emerges from a tornado.",
            },
            {
                **common,
                "cut_number": 90,
                "narration": "海 と 嵐 を 司る 破壊 の 神、 須佐之男命 の 誕生 です。",
                "image_prompt": "Susanoo grips a katana.",
            },
            {
                **common,
                "cut_number": 91,
                "narration": "彼 が 産声を上げる と、 雷 が 鳴り響き 大地 が 激しく 揺れ ました。",
                "image_prompt": "Lightning strikes a tiled house.",
            },
            {
                **common,
                "cut_number": 92,
                "narration": "太陽 と 月 が 秩序 の 象徴 なら ば、 彼 は 完全 なる カオス の 象徴 です。",
                "image_prompt": "A broken golden balance scale.",
            },
            {
                **common,
                "cut_number": 94,
                "narration": "あなた は 海原、 つまり 荒れ狂う 海 の 世界 を 治め なさい。",
                "image_prompt": "A traveler watches a whirlpool.",
            },
            {
                **common,
                "cut_number": 95,
                "narration": "こうして 天、 夜、 海 という 世界 の 三 大 領域 が 分割 され ました。",
                "image_prompt": "A split map with books and coins.",
            },
            {
                **common,
                "cut_number": 96,
                "narration": "この 三柱 の 神々 は、 三貴子 と 呼ばれる 最高位 の 存在 と なります。",
                "image_prompt": "Three rainbow rays strike a tiled shrine.",
            },
            {
                **common,
                "cut_number": 97,
                "narration": "泥だらけ の 禊ぎ から 生まれた 彼ら が、 日本 神話 の 主役 と なる の です。",
                "image_prompt": "A lotus blooms from mud.",
            },
            {
                **common,
                "cut_number": 99,
                "narration": "これ にて、 国作り から 始まった 伊邪那岐 の 長い 物語 は 幕 を 下ろし ます。",
                "image_prompt": "Izanagi closes a theater curtain.",
            },
            {
                **common,
                "cut_number": 101,
                "narration": "世界 の 全て の 役割 が 決まり、 完璧 な 平和 が 訪れた か に 見え ました。",
                "image_prompt": "A glowing map of Japan.",
            },
            {
                **common,
                "cut_number": 102,
                "narration": "天照大御神 は 高天原 を 暖かく 照らし、 命 を 育んで い ます。",
                "image_prompt": "An ornate goddess with a forehead jewel.",
            },
            {
                **common,
                "cut_number": 104,
                "narration": "しかし、 トラブル メーカー は 常に 身内 の 中 に いる もの です。",
                "image_prompt": "Men surround a cracked hourglass.",
            },
            {
                **common,
                "cut_number": 106,
                "narration": "彼 は 父親 の 命令 を 無視 して、 海 の 統治 を 全く しよう と しません。",
                "image_prompt": "An empty sea throne with a brass bowl.",
            },
            {
                **common,
                "cut_number": 109,
                "narration": "嵐 の 神 が 泣く こと で、 世界中 の 自然 破壊 が 始まって しまった の です。",
                "image_prompt": "A man runs into a tree.",
            },
            {
                **common,
                "cut_number": 110,
                "narration": "青々 と 茂って いた 山 の 木々 は、 全て 枯れ果て て しまい ました。",
                "image_prompt": "A green glowing volcano.",
            },
            {
                **common,
                "cut_number": 111,
                "narration": "豊か だった 川 や 海 の 水 も、 すっかり 干上がって しまい ます。",
                "image_prompt": "A full river splashes across cracked mud.",
            },
            {
                **common,
                "cut_number": 112,
                "narration": "さら に 恐ろしい こと に、 悪霊 たち が 騒ぎ 出し 疫病 が 蔓延 し 始めました。",
                "image_prompt": "A karate fighter leads shadow monsters.",
            },
            {
                **common,
                "cut_number": 113,
                "narration": "泣き叫ぶ だけ で 世界 を 滅亡 の 危機 に 陥れる、 規格外 の パワー。",
                "image_prompt": "A golden feather breaks a scale.",
            },
            {
                **common,
                "cut_number": 115,
                "narration": "なぜ お前 は 言いつけ を 守ら ず、 世界 を 壊す ほど 泣いて いる の か。",
                "image_prompt": "A red exclamation mark over a sword.",
            },
            {
                **common,
                "cut_number": 119,
                "narration": "彼 は 母親 の いない 孤独 に 耐えられない、 大きな 赤ん坊 だった の です。",
                "image_prompt": "A warrior with boots drops a katana.",
            },
            {
                **common,
                "cut_number": 120,
                "narration": "最強 の 破壊 神 が マザコン だった という、 日本 神話 独特 の 人間味。",
                "image_prompt": "A giant katana beside a baby doll.",
            },
            {
                **common,
                "cut_number": 124,
                "narration": "青い 山 は 枯れ果て、 川 や 海 の 水 は 完全に 干上がって しまい ました。",
                "image_prompt": "River water splashes across cracked mud.",
            },
            {
                **common,
                "cut_number": 126,
                "narration": "亡くなった 母親 の いる 死者 の 世界、 黄泉の国 へ 行きたい の だ と。",
                "image_prompt": "Smiling Izanagi stands in a black void.",
            },
            {
                **common,
                "cut_number": 131,
                "narration": "海 の 統治 者 に 任命 された ばかり なの に、 即座 に 追放 された の です。",
                "image_prompt": "A sea throne shatters beside a broom.",
            },
            {
                **common,
                "cut_number": 132,
                "narration": "須佐之男命 は 父親 の 決定 を 受け入れ、 旅立つ 準備 を 始め ました。",
                "image_prompt": "Susanoo picks up a katana.",
            },
            {
                **common,
                "cut_number": 133,
                "narration": "しかし 地下 に 行く 前 に、 姉 の 天照大御神 に お 別れ を 言おう と し ます。",
                "image_prompt": "Amaterasu looks at a floating castle.",
            },
            {
                **common,
                "cut_number": 134,
                "narration": "これ が、 天上 界 を 巻き込む 神話 最大 の 兄弟 喧嘩 の 始まり でした。",
                "image_prompt": "A warrior runs through theater curtains.",
            },
            {
                **common,
                "cut_number": 135,
                "narration": "乱暴 者 の 弟 が 天上 へ 向かう こと で、 宇宙 の 危機 が 訪れ ます。",
                "image_prompt": "Two karate fighters clash beneath text.",
            },
            {
                **common,
                "cut_number": 137,
                "narration": "最悪 の 死 の 淵 から、 最高 の 太陽 神 が 生まれる という カタルシス。",
                "image_prompt": "A skeleton child watches a golden feather in a bowl.",
            },
            {
                **common,
                "cut_number": 114,
                "narration": "伊邪那岐 は 激怒 し、 泣いて ばかり いる 息子 を 呼び出し ました。",
                "image_prompt": "Izanagi confronts his crying son.",
            },
            {
                **common,
                "cut_number": 121,
                "narration": "父親 の 伊邪那岐 から、 海 の 世界 を 治める よう 命じられた 須佐之男命。",
                "image_prompt": "Izanagi commands Susanoo to rule the sea.",
            },
            {
                **common,
                "cut_number": 139,
                "narration": "荒ぶる 神 須佐之男命 の 人間 臭い マザコン ぶり も 魅力 的 です よ ね。",
                "image_prompt": "A fierce warrior drops a katana.",
            },
            {
                **common,
                "cut_number": 141,
                "narration": "皆さん は この 三 兄弟 の 中 で、 どの 神様 が 一番 好き です か。",
                "image_prompt": "A glowing question mark over an open journal.",
            },
            {
                **common,
                "cut_number": 142,
                "narration": "是非 コメント 欄 で、 皆さん の 推し 神様 を 教えて ください ね。",
                "image_prompt": "A speech bubble above a modern desk.",
            },
            {
                **common,
                "cut_number": 146,
                "narration": "次回、 月 の 神 月読命 は、 食物 の 女神 保食神 の もと を 訪れ ます。",
                "image_prompt": "Scene evidence: queue EP06 topic/core-content alignment correction; Scene: two deities meet.",
            },
            {
                **common,
                "cut_number": 147,
                "narration": "保食神 は、 自ら の 体 から 食べ物 を 取り出し、 月読命 を もてなし ました。",
                "image_prompt": "Two figures stand by the sea.",
            },
            {
                **common,
                "cut_number": 148,
                "narration": "その 光景 を 穢らわしい と 感じた 月読命 は、 怒り に 任せて 保食神 を 斬り殺し ます。",
                "image_prompt": "Two identical men face each other.",
            },
            {
                **common,
                "cut_number": 149,
                "narration": "事件 を 知った 天照大御神 は 月読命 を 拒絶し、 二度 と 会わない と 告げ ます。",
                "image_prompt": "Two identical men stand in a cave.",
            },
            {
                **common,
                "cut_number": 150,
                "narration": "なぜ 太陽 と 月 は 永遠 に 別れた のか。 次回、 昼 と 夜 の 起源 に 迫り ます。",
                "image_prompt": "Two warriors argue in a forest.",
            },
        ]
        return {
            "title": "일본사 시크릿-EP05: 세 귀공자의 탄생",
            "topic": "세 귀공자의 탄생",
            "cuts": cuts,
        }

    def test_prepared_japanese_myth_script_gets_fact_locked_english_context(self):
        applied = apply_script_visual_policy(self._script())

        self.assertEqual(applied["visual_world"]["time_range"], "Japanese mythic creation era")
        first = applied["cuts"][0]["image_prompt"]
        second = applied["cuts"][1]["image_prompt"]
        third = applied["cuts"][2]["image_prompt"]
        sixth = applied["cuts"][5]["image_prompt"]
        seventh = applied["cuts"][6]["image_prompt"]

        self.assertIn("exactly one adult male Izanagi, lean angular middle-aged East Asian face", first)
        self.assertIn("high black topknot, pointed chin beard", first)
        self.assertIn("archaic white wide-sleeve robe", first)
        self.assertIn("Golden sun disk, silver moon disk, and blue storm spiral", first)
        self.assertIn("Extreme facial close-up of white-robed Izanagi", second)
        self.assertIn("face filling most of the frame", second)
        self.assertIn("Extreme facial close-up of torn white-robed Izanagi", third)
        self.assertNotIn("golden scale", third.lower())
        self.assertIn("Empty nonhuman view into Yomi underworld", sixth)
        self.assertNotIn("flower instantly withering", sixth.lower())
        self.assertNotIn("Main subject:", sixth)
        self.assertIn("handleless flat solid round bronze ritual mirror disk", seventh)
        self.assertIn("standing upright", seventh)

    def test_scene_contract_keeps_japanese_identity_and_material_culture(self):
        applied = apply_script_visual_policy(self._script())
        source = prepare_scene_contract_source(
            applied["cuts"][1]["image_prompt"],
            "mature adult graphic novel, thick black outlines",
        )
        compiled = compile_image_prompt(
            source,
            model_id="comfyui-flux2-klein-4b",
            base_negative="modern vehicle, utility pole, power line, European building",
        )

        self.assertIn("Izanagi", compiled.positive)
        self.assertIn("Yomi", compiled.positive)
        self.assertIn("Kojiki and Nihon Shoki Japanese creation", compiled.positive)
        self.assertIn("rough stone, unpainted timber only when named", compiled.positive)
        self.assertIn("modern vehicle", compiled.negative)
        self.assertIn("European building", compiled.negative)
        self.assertIn("utility pole", compiled.negative)

    def test_face_only_myth_scene_removes_full_body_geometry(self):
        applied = apply_script_visual_policy(self._script())
        source = prepare_scene_contract_source(
            applied["cuts"][1]["image_prompt"],
            "mature adult graphic novel, thick black outlines",
        )
        compiled = compile_image_prompt(
            source,
            model_id="comfyui-flux2-klein-4b",
            base_negative="extra fingers, extra arms, extra legs",
        )

        self.assertIn("face occupies 65-75 percent of frame height", compiled.positive)
        self.assertIn("lower frame ends at the collarbones", compiled.positive)
        self.assertNotIn("two connected arms", compiled.positive)
        self.assertIn("high black topknot", compiled.positive)
        self.assertIn("pointed chin beard", compiled.positive)
        self.assertIn("clean-shaven cheeks", compiled.positive)
        self.assertIn("archaic white wide-sleeve robe", compiled.positive)
        self.assertNotIn("hands", compiled.positive.lower())
        self.assertNotIn("waist", compiled.positive.lower())
        self.assertNotIn("belt", compiled.positive.lower())
        self.assertIn("visible hands", compiled.negative)
        self.assertIn("visible belt", compiled.negative)
        self.assertIn("full body", compiled.negative)
        self.assertIn("full jaw beard", compiled.negative)

    def test_susanoo_departure_removes_iron_sword_anachronism(self):
        source = prepare_scene_contract_source(
            (
                "Global visual world: Time range: Japanese mythic creation era; "
                "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
                "Year/period: Japanese mythic creation era; "
                "Exact place: bare primordial shore of the Japanese islands; "
                "Scene: Susanoo standing up slowly, picking up his heavy iron sword from the dirt"
            ),
            "mature adult graphic novel, thick black outlines",
        )
        compiled = compile_image_prompt(
            source,
            model_id="comfyui-z-image-turbo",
            base_negative="extra fingers, extra arms, extra legs",
        )

        self.assertIn("grief hardens into resolve", compiled.positive)
        self.assertNotIn("iron sword", compiled.positive.lower())
        self.assertNotIn("heavy iron", compiled.positive.lower())
        self.assertNotIn("picking up", compiled.positive.lower())
        self.assertIn("iron", compiled.negative.lower())
        self.assertIn("sword", compiled.negative.lower())

    def test_japanese_myth_policy_is_idempotent(self):
        once = apply_script_visual_policy(self._script())
        twice = apply_script_visual_policy(copy.deepcopy(once))

        self.assertEqual(
            [cut["image_prompt"] for cut in once["cuts"]],
            [cut["image_prompt"] for cut in twice["cuts"]],
        )

    def test_existing_structured_scene_is_not_wrapped_as_year_period_action(self):
        script = {
            "title": "태양과 달이 영원히 갈라선 이유 EP.06",
            "topic": "태양과 달이 영원히 갈라선 이유",
            "cuts": [
                {
                    "cut_number": 999,
                    "narration": "構造化された場面の回帰確認です。",
                    "visual_year": "Japanese mythic creation era",
                    "visual_period": "Kojiki and Nihon Shoki Japanese creation myth",
                    "visual_location": "primordial river valley",
                    "visual_evidence": "one continuous river and bare mountains",
                    "image_prompt": (
                        "Global visual world: Time range: Japanese mythic creation era; "
                        "Place scope: primordial Japanese islands; "
                        "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
                        "Material culture: rough stone and woven cloth; "
                        "Year/period: Japanese mythic creation era; "
                        "Exact place: primordial river valley; "
                        "Scene evidence: one continuous river and bare mountains; "
                        "Style: serious adult graphic novel illustration; "
                        "Scene: Landscape-only one clear river crossing a bare primordial valley"
                    ),
                }
            ],
        }

        applied = apply_script_visual_policy(script)
        prompt = applied["cuts"][0]["image_prompt"]
        compiled = compile_image_prompt(
            prepare_scene_contract_source(prompt, "mature adult graphic novel"),
            model_id="comfyui-flux2-klein-4b",
            base_negative="extra fingers, extra arms, extra legs",
        )

        self.assertNotIn("Scene: Year/period:", prompt)
        self.assertIn("Landscape-only one clear river crossing a bare primordial valley", compiled.positive)
        self.assertNotIn("Visible action: Year/period:", compiled.positive)

    def test_sun_moon_missing_dialogue_cuts_compile_to_hand_safe_actions(self):
        narrations = {
            12: "ある 日、 太陽 の 女神 アマテラス は、 地上 の 世界 が 気 に なりました。",
            14: "保食神 と 書いて、 ウケモチ と 呼ばれる 豊穣 の 神様 です。",
            17: "月の神 ツクヨミ は、 姉 の 頼み を 快く 引き受け ました。",
            19: "これ が、 日本 神話 に 深い 傷跡 を 残す 悲劇 の 始まり でした。",
            20: "ウケモチ の 歓迎 の 宴 が、 血塗られた 惨劇 へ と 変わる の です。",
            21: "太陽 の 女神 アマテラス と、 月 の 男神 ツクヨミ。",
            27: "最高 の おもてなし を しよう と、 彼女 は 盛大 な 宴 を 準備 します。",
            28: "しかし ツクヨミ は、 そこで 衝撃 的 な 光景 を 目の当たり に しました。",
            29: "ウケモチ が 陸 の 方 を 向いて 口 を 開ける と、",
            30: "なんと 口 の 中 から、 大量 の ほかほか な ご飯 が 吐き出された の です。",
            33: "最後 に 山 の 方 を 向く と、 獣 の 肉 が どっさり と 吐き出され ました。",
            36: "これ が、 日本 神話 に おける 食べ物 誕生 の シーン です。",
            38: "ウケモチ という 名前 は、 食べ物 を 持つ 者 という 意味 が あります。",
            39: "体 の 中 から 生命 を 生み出す の は、 大地 の 豊か さ の 象徴 でした。",
            40: "しかし、 綺麗好き で 気位 の 高い ツクヨミ の 反応 は 違いました。",
            42: "猛烈 な 嫌悪 感 と 屈辱 感 が、 彼 の 心 を 支配 しました。",
            43: "ウケモチ に 悪意 は なく、 彼女 なり の 最大 の おもてなし でした。",
            45: "怒り狂った ツクヨミ の 行動 は、 あまりにも 極端 で 残酷 でした。",
            47: "そして なんと、 宴 を 準備 した ウケモチ を 一刀両断 に した の です。",
            48: "美しい 女神 は、 理由 も わからない まま 血 の 海 に 倒れ ました。",
            50: "こうして お 使い は、 最悪 の 結末 を 迎えて しまった の です。",
            51: "食べ物 の 女神 ウケモチ が 準備 した、 衝撃 的 な おもてなし。",
            52: "口 から ご飯 や 魚、 獣 の 肉 を 吐き出して 盛り付けた の です。",
            53: "彼女 に とって は それ が、 命 を 生み出す 神聖 な 行為 でした。",
            56: "プライド を 傷つけられた ツクヨミ は、 怒り で 我 を 忘れ ました。",
            57: "腰 の 剣 を 抜く と、 満面の笑み を 浮かべる ウケモチ に 斬りかかり ます。",
            58: "そして なんと、 罪 の ない 女神 を 無残 に 切り殺して しまった の です。",
            60: "ツクヨミ は 倒れた 遺体 を 見下ろし、 冷酷 に 吐き捨て ます。",
            61: "なんて 汚らわしく、 気持ち の 悪い 女神 だった の だ。",
            64: "そして 姉 の アマテラス に、 地上 で 起きた 出来事 を 報告 します。",
            66: "ツクヨミ は 全く 悪びれる 様子 も なく、 堂々 と 語り ました。",
            67: "あの 女神 は 口 から 汚い 食べ物 を 出して、 私 に 食べさせよう と した の です。",
            69: "姉 に 褒めて もらえる と さえ 思って いた の かも しれ ません。",
            70: "しかし、 それ を 聞いた アマテラス の 表情 は 凍りつき ました。",
            73: "太陽 の 女神 の 驚き は、 やがて 凄まじい 激怒 へ と 変わり ました。",
            74: "アマテラス は 立ち上がり、 ツクヨミ を 激しく 叱りつけ ました。",
            77: "ツクヨミ に とって は、 全く 予想外 の 怒られ 方 でした。",
            80: "これ が 決定打 と なり、 アマテラス は 究極 の 決断 を 下し ます。",
            81: "もう 二度と、 お前 の 顔 など 見たく ない。",
            82: "同じ 場所 に いる こと すら 許せない ほど の、 強い 拒絶 でした。",
            83: "ツクヨミ は 天上 の 中心 から 追放 され、 夜 の 世界 へ と 追いやられ ます。",
            84: "太陽 と 月 が 共に 輝いて いた 黄金 時代 は、 ここ に 終わり を 告げ ました。",
            86: "食べ物 の 女神 を 斬り殺して しまった、 月の神 ツクヨミ。",
            87: "彼は 天上 界 へ と 戻り、 姉 の 太陽 神 アマテラス に 報告 しました。",
            89: "しかし それ を 聞いた アマテラス は、 激しく 怒り狂い ました。",
            92: "褒められる と 思って いた ツクヨミ は、 予想外 の 怒り に 困惑 します。",
            93: "生み出す 行為 を 汚い と 感じた 月 の 神 と、 尊い と 感じた 太陽 の 神。",
            95: "アマテラス は 弟 に 向かって、 冷たく 絶縁 を 宣言 しました。",
            96: "もう 二度と お前 と 顔 を 合わせる こと は ない。",
            97: "こうして アマテラス と ツクヨミ は、 完全に 別々 の 領域 を 歩み ます。",
            104: "神様 で あって も、 怒り や 嫌悪 感 という 感情 を コントロール できない。",
            110: "しかし、 残念 な こと に ウケモチ は すでに 命 を 落として しまい ました。",
            111: "食べ物 の 女神 が 死んで しまった 地上 の 食糧 は、 どう なって しまう の でしょう か。",
            115: "そこで 派遣 された 神様 が 目 に した の は、 さらに 驚く べき 光景 でした。",
            118: "頭 や 目、 お腹 など、 遺体 の あらゆる 部分 から 奇跡 が 起こり ます。",
            120: "悲劇 的 な 死 は、 決して 全て の 終わり では ない という メッセージ。",
            121: "ウケモチ を 斬り殺した 弟 に 激怒 し、 永遠 の 離縁 を 突きつけた アマテラス。",
        }
        common = {
            "visual_year": "Japanese mythic creation era",
            "visual_period": "Kojiki and Nihon Shoki Japanese creation myth",
            "visual_location": "primordial natural landscape of mythic Japan",
            "visual_evidence": "dialogue-aligned visible action",
        }
        script = {
            "title": "태양과 달이 영원히 갈라선 이유 EP.06",
            "topic": "태양과 달이 영원히 갈라선 이유",
            "cuts": [
                {
                    **common,
                    "cut_number": number,
                    "narration": narration,
                    "image_prompt": "A generic cave portrait with open hands and a tiled palace.",
                }
                for number, narration in narrations.items()
            ],
        }

        applied = apply_script_visual_policy(script)
        for cut in applied["cuts"]:
            prompt = cut["image_prompt"]
            lowered_prompt = prompt.lower()
            compiled = compile_image_prompt(
                prepare_scene_contract_source(prompt, "mature adult graphic novel"),
                model_id="comfyui-flux2-klein-4b",
                base_negative="extra fingers, extra arms, extra legs",
            )
            self.assertNotIn("Scene: Year/period:", prompt, cut["cut_number"])
            self.assertNotIn("Visible action: Year/period:", compiled.positive, cut["cut_number"])
            self.assertNotIn("katana", lowered_prompt, cut["cut_number"])
            self.assertNotIn("palace", lowered_prompt, cut["cut_number"])
            self.assertNotIn("throne", lowered_prompt, cut["cut_number"])
            self.assertNotIn("armor", lowered_prompt, cut["cut_number"])
            if cut.get("visual_subject"):
                self.assertTrue(
                    "hand-free" in lowered_prompt or "face-dominant" in lowered_prompt or "face-only" in lowered_prompt or "two-face" in lowered_prompt or "extreme macro" in lowered_prompt,
                    cut["cut_number"],
                )
                self.assertNotIn("full-body", lowered_prompt, cut["cut_number"])
            if "Object-only" in prompt:
                self.assertEqual("object", compiled.scene_kind, cut["cut_number"])
            if "Landscape-only" in prompt:
                self.assertEqual("landscape", compiled.scene_kind, cut["cut_number"])
            if cut["cut_number"] == 84:
                self.assertIn("straight-down aerial view", compiled.positive.lower())
                self.assertIn("entire left half is warm gold daylight", compiled.positive.lower())
                self.assertIn("entire right half is deep silver-blue night", compiled.positive.lower())
                self.assertIn("camera points straight downward", compiled.positive.lower())
                self.assertIn("warm gold daylight occupies the entire left half", compiled.positive.lower())
                self.assertNotIn(" road", compiled.positive.lower())
                self.assertNotIn("building", compiled.positive.lower())
                self.assertIn("sun disk", compiled.negative.lower())
                self.assertIn("moon disk", compiled.negative.lower())
                self.assertIn("isolated boulder", compiled.negative.lower())
                self.assertTrue(_should_ignore_object_person_segmentation(prompt))
                self.assertTrue(_should_ignore_strict_nonhuman_person_segmentation(prompt))
            if cut["cut_number"] == 18:
                self.assertIn("descends through open silver-lit sky", compiled.positive.lower())
                self.assertIn("open air surrounds both fully visible feet", compiled.positive.lower())
                self.assertIn("composition=tsukuyomi_visible_descent", compiled.diagnostics)
                self.assertNotIn("two grounded legs", compiled.positive.lower())
            if cut["cut_number"] == 34:
                self.assertIn("adult woman uke mochi occupies the right half", compiled.positive.lower())
                self.assertIn("face-only crop at both jawlines", compiled.positive.lower())
                self.assertIn("composition=uke_mochi_satisfied_tsukuyomi_disbelief_faces", compiled.diagnostics)
                self.assertNotIn("hand", compiled.positive.lower())
            if cut["cut_number"] == 51:
                self.assertIn("face-only crop at both jawlines", compiled.positive.lower())
                self.assertIn("exactly two enormous mature faces", compiled.positive.lower())
                self.assertIn("composition=uke_mochi_satisfied_tsukuyomi_disbelief_faces", compiled.diagnostics)
                self.assertNotIn("hand", compiled.positive.lower())
            if cut["cut_number"] == 19:
                self.assertEqual("pair", compiled.scene_kind)
                self.assertEqual(2, compiled.person_count)
                self.assertIn("tsukuyomi recoiling in cold anger", compiled.positive.lower())
                self.assertIn("uke mochi faces him in shocked restraint", compiled.positive.lower())
                self.assertNotIn("object-only", compiled.positive.lower())
                self.assertIn("straight leaf-shaped aged-bronze", compiled.positive.lower())
            if cut["cut_number"] == 33:
                lowered = compiled.positive.lower()
                negative = compiled.negative.lower()
                self.assertEqual("single", compiled.scene_kind)
                self.assertEqual(1, compiled.person_count)
                self.assertIn("exactly three clean separate game-meat portions", lowered)
                self.assertIn("travel outward through empty air", lowered)
                self.assertIn("visible hand", negative)
                self.assertIn("platter", negative)
                self.assertIn("porcelain", negative)
                self.assertIn("fourth meat portion", negative)
                self.assertIn("tsukuyomi", negative)
            if cut["cut_number"] == 36:
                lowered = compiled.positive.lower()
                self.assertEqual("pair", compiled.scene_kind)
                self.assertEqual(2, compiled.person_count)
                self.assertIn("uke mochi welcomes", lowered)
                self.assertIn("both complete faces dominant", lowered)
                self.assertNotIn("feast-origin tableau", lowered)
            if cut["cut_number"] in {27, 51}:
                lowered = compiled.positive.lower()
                self.assertEqual("pair", compiled.scene_kind)
                self.assertEqual(2, compiled.person_count)
                self.assertIn("uke mochi", lowered)
                self.assertIn("tsukuyomi", lowered)
                self.assertIn("face", lowered)
                self.assertNotIn("strict overhead view", lowered)
                self.assertFalse(_should_ignore_object_person_segmentation(prompt))
            if cut["cut_number"] == 58:
                self.assertEqual("single", compiled.scene_kind)
                self.assertEqual(1, compiled.person_count)
                self.assertIn("tsukuyomi turning away", compiled.positive.lower())
                self.assertIn("non-graphic", compiled.positive.lower())
            if cut["cut_number"] == 73:
                lowered = compiled.positive.lower()
                negative = compiled.negative.lower()
                self.assertIn("bare unadorned forehead", lowered)
                self.assertIn("ends exactly at the jawline", lowered)
                self.assertIn("sun ornament", negative)
                self.assertIn("forehead jewel", negative)
            if cut["cut_number"] in {60, 61, 67, 92}:
                lowered = compiled.positive.lower()
                negative = compiled.negative.lower()
                self.assertEqual("single", compiled.scene_kind)
                self.assertEqual(1, compiled.person_count)
                self.assertIn("bare unadorned forehead", lowered)
                self.assertIn("moon ornament", negative)
                self.assertIn("forehead jewel", negative)
                self.assertIn("visible hand", negative)
            if cut["cut_number"] == 82:
                lowered = compiled.positive.lower()
                negative = compiled.negative.lower()
                self.assertEqual("single", compiled.scene_kind)
                self.assertEqual(1, compiled.person_count)
                self.assertIn("declaring final rejection", lowered)
                self.assertIn("away from tsukuyomi outside the right edge", lowered)
                self.assertIn("bare unadorned forehead", lowered)
                self.assertIn("shoulder armor", negative)
                self.assertIn("forehead jewel", negative)
                self.assertIn("visible hand", negative)
                self.assertIn("tsukuyomi in frame", negative)
            if cut["cut_number"] == 104:
                lowered = compiled.positive.lower()
                self.assertEqual("single", compiled.scene_kind)
                self.assertEqual(1, compiled.person_count)
                self.assertIn("extreme face-only tsukuyomi close-up", lowered)
                self.assertIn("anger overwhelms restraint", lowered)
                self.assertIn("smooth bare forehead", lowered)
            if cut["cut_number"] == 115:
                self.assertEqual("single", compiled.scene_kind)
                self.assertEqual(1, compiled.person_count)
                self.assertIn("staring downward in unmistakable astonishment", compiled.positive.lower())
                self.assertIn("both eyes widened", compiled.positive.lower())
                self.assertIn("mouth visibly open", compiled.positive.lower())
                self.assertIn("visible hand", compiled.negative.lower())
            if cut["cut_number"] == 111:
                lowered = compiled.positive.lower()
                self.assertEqual("landscape", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("landscape-only famine threat", lowered)
                self.assertIn("no person, body, bowl, basket", prompt.lower())
            if cut["cut_number"] == 121:
                lowered = compiled.positive.lower()
                negative = compiled.negative.lower()
                self.assertEqual("single", compiled.scene_kind)
                self.assertEqual(1, compiled.person_count)
                self.assertIn("furious final rejection", lowered)
                self.assertIn("permanently ends the sibling bond", lowered)
                self.assertIn("bare unadorned forehead", lowered)
                self.assertIn("uke mochi", negative)
                self.assertIn("tsukuyomi in frame", negative)
                self.assertIn("sun hair ornament", negative)

    def test_bronze_ritual_mirror_excludes_cookware(self):
        applied = apply_script_visual_policy(self._script())
        source = prepare_scene_contract_source(
            applied["cuts"][6]["image_prompt"],
            "mature adult graphic novel, thick black outlines",
        )
        compiled = compile_image_prompt(
            source,
            model_id="comfyui-flux2-klein-4b",
            base_negative="extra fingers, extra arms, extra legs",
        )

        self.assertIn("bronze ritual mirror disk", compiled.positive)
        self.assertIn("standing upright", compiled.positive)
        self.assertIn("frying pan", compiled.negative)
        self.assertIn("skillet", compiled.negative)
        self.assertIn("handle", compiled.negative)

    def test_yomi_contamination_stays_on_robe_in_face_crop(self):
        applied = apply_script_visual_policy(self._script())
        source = prepare_scene_contract_source(
            applied["cuts"][4]["image_prompt"],
            "mature adult graphic novel, thick black outlines",
        )
        compiled = compile_image_prompt(
            source,
            model_id="comfyui-flux2-klein-4b",
            base_negative="extra fingers, extra arms, extra legs",
        )

        self.assertIn("composition=face_close", compiled.diagnostics)
        self.assertIn("Yomi contamination", compiled.positive)
        self.assertNotIn("hands", compiled.positive.lower())
        self.assertIn("black liquid pool", compiled.negative)
        self.assertIn("hand holding black sludge", compiled.negative)

    def test_identity_face_descriptor_does_not_force_walking_scene_to_closeup(self):
        source = (
            "Year/period: Japanese mythic creation era; "
            "Main subject: exactly one adult male Izanagi, lean angular middle-aged East Asian face, "
            "high black topknot, pointed chin beard, archaic white wide-sleeve robe; "
            "Scene: White-robed Izanagi strides along a bare rocky bank toward rushing water"
        )
        compiled = compile_image_prompt(
            source,
            model_id="comfyui-flux2-klein-4b",
            base_negative="extra fingers, extra arms, extra legs",
        )

        self.assertNotIn("composition=face_close", compiled.diagnostics)
        self.assertIn("Medium three-quarter story composition", compiled.positive)

    def test_modern_shrine_continuity_uses_single_ladle_without_hands(self):
        applied = apply_script_visual_policy(self._script())
        cut = applied["cuts"][7]
        self.assertEqual(cut["visual_year"], "present-day Japan")
        self.assertIn("present-day Shinto shrine", cut["visual_location"])
        self.assertIn("exactly one slender bamboo purification ladle", cut["image_prompt"])

        compiled = compile_image_prompt(
            prepare_scene_contract_source(
                cut["image_prompt"],
                "mature adult graphic novel, thick black outlines",
            ),
            model_id="comfyui-flux2-klein-4b",
            base_negative="extra fingers, extra arms, extra legs",
        )
        self.assertIn("bamboo purification ladle", compiled.positive)
        self.assertIn("second ladle", compiled.negative)
        self.assertIn("human hand", compiled.negative)
        self.assertIn("wooden beam", compiled.negative)

    def test_discarded_ritual_objects_do_not_inject_a_person(self):
        applied = apply_script_visual_policy(self._script())
        by_number = {cut["cut_number"]: cut for cut in applied["cuts"]}
        self.assertIn("exactly one adult male Izanagi", by_number[15]["image_prompt"])
        self.assertIn("exactly one adult male Izanagi", by_number[17]["image_prompt"])
        for cut_number in (16, 18, 20):
            self.assertNotIn("Main subject:", by_number[cut_number]["image_prompt"])
            self.assertIn("Object-only", by_number[cut_number]["image_prompt"])
        self.assertNotIn("amulet", by_number[20]["image_prompt"].lower())

    def test_underwater_life_layers_exclude_fantasy_city(self):
        applied = apply_script_visual_policy(self._script())
        cut = next(cut for cut in applied["cuts"] if cut["cut_number"] == 34)
        self.assertIn("exactly three natural depth layers", cut["image_prompt"])
        self.assertNotIn("underwater city", cut["image_prompt"].lower())

        compiled = compile_image_prompt(
            prepare_scene_contract_source(cut["image_prompt"], "mature adult graphic novel"),
            model_id="comfyui-flux2-klein-4b",
            base_negative="extra fingers, extra arms, extra legs",
        )
        self.assertIn("underwater city", compiled.negative)
        self.assertIn("clock tower", compiled.negative)
        self.assertIn("scroll", compiled.negative)
        self.assertIn("book", compiled.negative)
        self.assertIn("rolled mat", compiled.negative)
        self.assertNotIn("Material culture:", compiled.positive)

    def test_magatama_gift_excludes_people_round_beads_and_cute_sun(self):
        applied = apply_script_visual_policy(self._script())
        cut = next(cut for cut in applied["cuts"] if cut["cut_number"] == 60)
        self.assertIn("one large comma-shaped jade pendant", cut["image_prompt"])
        self.assertNotIn("Main subject:", cut["image_prompt"])

        compiled = compile_image_prompt(
            prepare_scene_contract_source(cut["image_prompt"], "mature adult graphic novel"),
            model_id="comfyui-flux2-klein-4b",
            base_negative="extra fingers, extra arms, extra legs",
        )
        self.assertIn("round bead", compiled.negative)
        self.assertIn("anthropomorphic sun", compiled.negative)
        self.assertIn("cute face", compiled.negative)

    def test_izanagi_susanoo_conflict_beats_use_one_reliable_action_per_cut(self):
        applied = apply_script_visual_policy(self._script())
        by_number = {cut["cut_number"]: cut for cut in applied["cuts"]}
        angry_prompt = by_number[114]["image_prompt"]
        command_prompt = by_number[121]["image_prompt"]
        self.assertIn("exactly one adult male Izanagi", angry_prompt)
        self.assertIn("Extreme facial close-up", angry_prompt)
        self.assertIn("hands outside the frame", angry_prompt)
        self.assertIn("exactly one adult male Izanagi", command_prompt)
        self.assertIn("one open pointing hand and one index finger", command_prompt)

        compiled_angry = compile_image_prompt(
            prepare_scene_contract_source(angry_prompt, "mature adult graphic novel"),
            model_id="comfyui-flux2-klein-4b",
            base_negative="extra fingers, extra arms, extra legs",
        )
        self.assertIn("mouth visibly open in a shout", compiled_angry.positive)
        self.assertNotIn("hands outside", compiled_angry.positive)

        compiled_command = compile_image_prompt(
            prepare_scene_contract_source(command_prompt, "mature adult graphic novel"),
            model_id="comfyui-flux2-klein-4b",
            base_negative="extra fingers, extra arms, extra legs",
        )
        self.assertIn("at the real ocean", compiled_command.positive)
        self.assertIn("one open pointing hand", compiled_command.positive)
        self.assertIn("second person", compiled_command.negative)
        self.assertIn("extra pointing hand", compiled_command.negative)
        self.assertIn("vertical divider", compiled_command.negative)

    def test_susanoo_birth_and_storm_sequence_excludes_drift_objects(self):
        applied = apply_script_visual_policy(self._script())
        by_number = {cut["cut_number"]: cut for cut in applied["cuts"]}
        self.assertIn("robe fully covering his torso and shoulders", by_number[89]["image_prompt"])
        self.assertNotIn("shirtless", by_number[89]["image_prompt"].lower())
        self.assertIn("Extreme facial close-up", by_number[90]["image_prompt"])
        self.assertNotIn("katana", by_number[90]["image_prompt"].lower())
        self.assertIn("only natural rock, river water", by_number[91]["image_prompt"])
        self.assertIn("one chaotic blue-black storm spiral", by_number[92]["image_prompt"])
        self.assertNotIn("balance scale", by_number[92]["image_prompt"].lower())
        self.assertIn("one massive dark whirlpool", by_number[94]["image_prompt"])
        self.assertNotIn("Main subject:", by_number[94]["image_prompt"])

        compiled_89 = compile_image_prompt(
            prepare_scene_contract_source(by_number[89]["image_prompt"], "mature adult graphic novel"),
            model_id="comfyui-flux2-klein-4b",
            base_negative="extra fingers, extra arms, extra legs",
        )
        self.assertIn("shirtless", compiled_89.negative)
        self.assertIn("katana", compiled_89.negative)

        compiled_91 = compile_image_prompt(
            prepare_scene_contract_source(by_number[91]["image_prompt"], "mature adult graphic novel"),
            model_id="comfyui-flux2-klein-4b",
            base_negative="extra fingers, extra arms, extra legs",
        )
        self.assertNotIn("Material culture:", compiled_91.positive)
        self.assertIn("tiled roof", compiled_91.negative)

        compiled_94 = compile_image_prompt(
            prepare_scene_contract_source(by_number[94]["image_prompt"], "mature adult graphic novel"),
            model_id="comfyui-flux2-klein-4b",
            base_negative="extra fingers, extra arms, extra legs",
        )
        self.assertIn("traveler", compiled_94.negative)
        self.assertIn("staff", compiled_94.negative)

    def test_three_realms_and_izanagi_exit_use_in_world_visuals(self):
        applied = apply_script_visual_policy(self._script())
        by_number = {cut["cut_number"]: cut for cut in applied["cuts"]}
        self.assertIn("one uninterrupted natural horizon", by_number[95]["image_prompt"])
        self.assertIn("exactly three separated celestial forms", by_number[96]["image_prompt"])
        self.assertNotIn("shrine", by_number[96]["image_prompt"].lower())
        self.assertIn("rise from muddy purification water", by_number[97]["image_prompt"])
        self.assertNotIn("lotus", by_number[97]["image_prompt"].lower())
        self.assertIn("Izanagi walking away alone", by_number[99]["image_prompt"])
        self.assertNotIn("curtain", by_number[99]["image_prompt"].lower())

        for cut_number, forbidden in ((95, "split panel"), (96, "tiled roof"), (97, "lotus"), (99, "black curtain")):
            compiled = compile_image_prompt(
                prepare_scene_contract_source(by_number[cut_number]["image_prompt"], "mature adult graphic novel"),
                model_id="comfyui-flux2-klein-4b",
                base_negative="extra fingers, extra arms, extra legs",
            )
            self.assertIn(forbidden, compiled.negative)

    def test_apparent_peace_and_susanoo_refusal_stay_grounded(self):
        applied = apply_script_visual_policy(self._script())
        by_number = {cut["cut_number"]: cut for cut in applied["cuts"]}
        self.assertIn("tranquil primordial island valley", by_number[101]["image_prompt"])
        self.assertNotIn("map of Japan", by_number[101]["image_prompt"])
        self.assertIn("fresh green shoots", by_number[102]["image_prompt"])
        self.assertNotIn("Main subject:", by_number[102]["image_prompt"])
        self.assertIn("stubborn sideways gaze", by_number[104]["image_prompt"])
        self.assertNotIn("hourglass", by_number[104]["image_prompt"].lower())
        self.assertIn("shoulders turned away from the real ocean", by_number[106]["image_prompt"])
        self.assertNotIn("throne", by_number[106]["image_prompt"].lower())

        for cut_number, forbidden in ((101, "map of Japan"), (102, "forehead jewel"), (104, "hourglass"), (106, "throne")):
            compiled = compile_image_prompt(
                prepare_scene_contract_source(by_number[cut_number]["image_prompt"], "mature adult graphic novel"),
                model_id="comfyui-flux2-klein-4b",
                base_negative="extra fingers, extra arms, extra legs",
            )
            self.assertIn(forbidden, compiled.negative)

    def test_susanoo_disaster_sequence_uses_natural_consequences(self):
        applied = apply_script_visual_policy(self._script())
        by_number = {cut["cut_number"]: cut for cut in applied["cuts"]}
        expected = {
            109: ("giant ancient trees bend", "running man"),
            110: ("leafless dead trees", "volcano"),
            111: ("vast arid basin", "flowing water"),
            112: ("shadow-smoke tendrils", "karate gi"),
            113: ("storm shockwave", "golden feather"),
        }
        for cut_number, (required, forbidden) in expected.items():
            prompt = by_number[cut_number]["image_prompt"]
            self.assertIn(required, prompt)
            compiled = compile_image_prompt(
                prepare_scene_contract_source(prompt, "mature adult graphic novel"),
                model_id="comfyui-flux2-klein-4b",
                base_negative="extra fingers, extra arms, extra legs",
            )
            self.assertNotIn("Material culture:", compiled.positive)
            self.assertIn(forbidden, compiled.negative)

    def test_family_conflict_sequence_excludes_symbols_weapons_and_toys(self):
        applied = apply_script_visual_policy(self._script())
        by_number = {cut["cut_number"]: cut for cut in applied["cuts"]}
        expected = {
            115: ("stern demand", "exclamation mark"),
            119: ("hugging both knees", "katana"),
            120: ("softened by longing", "baby doll"),
            124: ("vast arid basin", "flowing water"),
        }
        for cut_number, (required, forbidden) in expected.items():
            prompt = by_number[cut_number]["image_prompt"]
            self.assertIn(required, prompt)
            compiled = compile_image_prompt(
                prepare_scene_contract_source(prompt, "mature adult graphic novel"),
                model_id="comfyui-flux2-klein-4b",
                base_negative="extra fingers, extra arms, extra legs",
            )
            self.assertIn(forbidden, compiled.negative)

    def test_exile_and_departure_keep_susanoo_identity_and_period_props(self):
        applied = apply_script_visual_policy(self._script())
        by_number = {cut["cut_number"]: cut for cut in applied["cuts"]}
        expected = {
            126: ("sealed black Yomi cave reflected in one eye", "Izanagi"),
            131: ("walking away alone from the real ocean after exile", "throne"),
            132: ("exactly one small tied plant-fiber travel bundle", "katana"),
        }
        for cut_number, (required, forbidden) in expected.items():
            prompt = by_number[cut_number]["image_prompt"]
            self.assertIn(required, prompt)
            compiled = compile_image_prompt(
                prepare_scene_contract_source(prompt, "mature adult graphic novel"),
                model_id="comfyui-flux2-klein-4b",
                base_negative="extra fingers, extra arms, extra legs",
            )
            self.assertIn(forbidden, compiled.negative)
        self.assertIn("exactly one adult male Susanoo", by_number[126]["image_prompt"])
        self.assertIn("exactly one adult male Susanoo", by_number[131]["image_prompt"])
        self.assertNotIn("Main subject:", by_number[132]["image_prompt"])
        compiled_126 = compile_image_prompt(
            prepare_scene_contract_source(by_number[126]["image_prompt"], "mature adult graphic novel"),
            model_id="comfyui-flux2-klein-4b",
            base_negative="extra fingers, extra arms, extra legs",
        )
        self.assertNotIn("hands outside", compiled_126.positive)
        self.assertIn("visible hands", compiled_126.negative)

    def test_takamagahara_teaser_excludes_castles_text_and_skeletons(self):
        applied = apply_script_visual_policy(self._script())
        by_number = {cut["cut_number"]: cut for cut in applied["cuts"]}
        expected = {
            133: ("Susanoo standing on a bare rocky ridge", "castle"),
            134: ("storm front advances toward a calm golden sunlit cloud plain", "theater curtain"),
            135: ("one continuous line of fresh barefoot footprints", "fighting men"),
            137: ("continuous natural transition from a sealed black Yomi cave", "skeleton"),
        }
        for cut_number, (required, forbidden) in expected.items():
            prompt = by_number[cut_number]["image_prompt"]
            self.assertIn(required, prompt)
            compiled = compile_image_prompt(
                prepare_scene_contract_source(prompt, "mature adult graphic novel"),
                model_id="comfyui-flux2-klein-4b",
                base_negative="extra fingers, extra arms, extra legs",
            )
            self.assertIn(forbidden, compiled.negative)

    def test_outro_and_next_episode_teaser_keep_roles_actions_and_period(self):
        applied = apply_script_visual_policy(self._script())
        by_number = {cut["cut_number"]: cut for cut in applied["cuts"]}

        self.assertIn("two visible tear tracks", by_number[139]["image_prompt"])
        self.assertNotIn("katana", by_number[139]["image_prompt"].lower())
        self.assertIn("exactly three separated flat stone medallions", by_number[141]["image_prompt"])
        self.assertIn("flat unmarked wooden vote chips", by_number[142]["image_prompt"])
        self.assertIn("female Uke Mochi", by_number[146]["image_prompt"])
        self.assertIn("open-sided unpainted timber food shelter", by_number[146]["image_prompt"])
        self.assertIn("one arm's length apart", by_number[146]["image_prompt"])
        self.assertIn("fall from gold light", by_number[147]["image_prompt"])
        self.assertIn("straight leaf-shaped bronze double-edged blade", by_number[148]["image_prompt"])
        self.assertIn("adult female Amaterasu", by_number[149]["image_prompt"])
        self.assertNotIn("Main subject:", by_number[150]["image_prompt"])

        for cut_number in (146, 147, 148, 149):
            compiled = compile_image_prompt(
                prepare_scene_contract_source(by_number[cut_number]["image_prompt"], "mature adult graphic novel"),
                model_id="comfyui-flux2-klein-4b",
                base_negative="extra fingers, extra arms, extra legs",
            )
            self.assertIn("Tsukuyomi", compiled.positive)
            self.assertLessEqual(len(compiled.positive), 950)
            retry_compiled = compile_image_prompt(
                prepare_scene_contract_source(by_number[cut_number]["image_prompt"], "mature adult graphic novel"),
                model_id="comfyui-flux2-klein-4b",
                base_negative="extra fingers, extra arms, extra legs",
                quality_hint="Full-bleed edge-to-edge crop: named scene material continues beyond all four canvas edges",
            )
            self.assertLessEqual(len(retry_compiled.positive), 950)
            self.assertIn("Tsukuyomi", retry_compiled.positive)
        retry_139 = compile_image_prompt(
            prepare_scene_contract_source(by_number[139]["image_prompt"], "mature adult graphic novel"),
            model_id="comfyui-flux2-klein-4b",
            quality_hint="Full-bleed edge-to-edge crop: named scene material continues beyond all four canvas edges",
        )
        self.assertLessEqual(len(retry_139.positive), 950)
        self.assertIn("two visible tear tracks", retry_139.positive)
        self.assertIn("Uke Mochi", compile_image_prompt(
            prepare_scene_contract_source(by_number[146]["image_prompt"], "mature adult graphic novel"),
            model_id="comfyui-flux2-klein-4b",
        ).positive)
        self.assertIn("male Uke Mochi", compile_image_prompt(
            prepare_scene_contract_source(by_number[148]["image_prompt"], "mature adult graphic novel"),
            model_id="comfyui-flux2-klein-4b",
        ).negative)
        compiled_sdxl = compile_image_prompt(
            prepare_scene_contract_source(by_number[149]["image_prompt"], "mature adult graphic novel"),
            model_id="comfyui-dreamshaper-xl-longtube-v15",
        )
        self.assertIn("Amaterasu", compiled_sdxl.positive)
        self.assertIn("Tsukuyomi", compiled_sdxl.positive)

    def test_transition_and_birth_cuts_do_not_become_martial_scenes(self):
        applied = apply_script_visual_policy(self._script())
        by_number = {cut["cut_number"]: cut for cut in applied["cuts"]}
        self.assertIn("robe intact", by_number[37]["image_prompt"])
        self.assertNotIn("muscular divine chest", by_number[37]["image_prompt"])
        self.assertIn("Object-only river view", by_number[38]["image_prompt"])
        self.assertIn("exactly three separated seed-like light cores", by_number[43]["image_prompt"])

        compiled = compile_image_prompt(
            prepare_scene_contract_source(by_number[43]["image_prompt"], "mature adult graphic novel"),
            model_id="comfyui-flux2-klein-4b",
            base_negative="extra fingers, extra arms, extra legs",
        )
        self.assertIn("martial artist", compiled.negative)
        self.assertIn("staff", compiled.negative)

    def test_sun_moon_episode_uses_dialogue_aligned_hand_safe_scenes(self):
        common = {
            "visual_year": "신화시대",
            "visual_period": "신화 시대",
            "visual_location": "고천원과 지상",
        }
        rows = (
            (1, "皆さん、 こんにちは。 日本 の 歴史 の 秘密 を 探る 時間 です。", "High waves crash against jagged rocks."),
            (2, "前回 は、 恐ろしい 穢れ を 落とす 禊ぎ の 儀式 から、", "Shadows bleed off a god's skin."),
            (3, "宇宙 の 秩序 を 司る 三柱 の 尊い 神々 が 誕生 した お話 でした。", "Three stars over a map of Japan."),
            (4, "太陽 の 女神 天照大御神、 月 の 男神 月読命、 そして 嵐 の 神 須佐之男命。", "Three abstract rays."),
            (5, "今日 は、 その 中 でも 太陽 と 月 に まつわる 衝撃 的 な エピソード を ご 紹介 します。", "A cracked sun and moon macro."),
            (6, "実は 日本 の 神話 において、 太陽 と 月 の 神 は 元々 仲 が 良かった の です。", "Amaterasu, Tsukuyomi and Susanoo stand in a palace."),
            (8, "しかし 現在、 太陽 と 月 が 同時に 空 に 昇る こと は ありません。", "Two deities stand in a split screen."),
            (9, "昼 と 夜 が 完全に 分離 し、 決して 交わらない 運命 に あります。", "A Japanese map is divided in half."),
            (16, "私 の 代わりに、 ウケモチ の 様子 を 見て きて くれない かしら。", "Amaterasu pointing her delicate finger toward earth."),
            (18, "そして 天上 界 から、 ウケモチ が 住む 地上 へ と 降りて いき ます。", "A pale silver beam descends."),
            (22, "二柱 の 神 は 天上 界 で、 共に 平和 に 暮らし て いました。", "A divine palace floats above clouds."),
            (24, "地上 の 世界 に 住む 食べ物 の 女神、 ウケモチ の 様子 を 見て こい と。", "A goddess stands among dark rocks with open hands."),
            (32, "すると 今度 は、 大小 さまざま な 新鮮な 魚 が 勢いよく 飛び出し ます。", "Raw fish erupt from the goddess's throat."),
            (33, "最後 に 山 の 方 を 向く と、 獣 の 肉 が どっさり と 吐き出され ました。", "Bloody game meat spills onto the floor."),
            (34, "女神 は 自分 の 吐き出した もの を 綺麗 に 盛り付け、", "Uke Mochi arranges food by hand on white square plates in a cave."),
            (35, "さあ、 どうぞ 召し上がれ、 と にこやか に 差し出した の です。", "A modern feast is offered."),
            (36, "これ が、 日本 神話 に 描かれた 食べ物 の 誕生 シーン です。", "A scroll depicts the food origin."),
            (37, "現代 の 感覚 から すると、 あまりにも 衝撃 的 で 奇怪 な 描写 です。", "A modern viewer's hand holding a magnifying glass."),
            (41, "吐き出した 汚い もの を、 尊い 私 に 食べさせる つもり か。", "Tsukuyomi clenches his fist in macro close-up."),
            (44, "しかし、 価値 観 の 違い が 取り返し の つかない 悲劇 を 呼び ます。", "Two glowing threads snap."),
            (46, "激怒 した 月の神 は、 腰 に 差して いた 剣 を 抜き放ち ます。", "A pristine silver katana is drawn in a dark cave."),
            (49, "最高 の 食材 が 並ぶ はず だった 食卓 は、 凄惨 な 殺人 現場 に 変わり ます。", "A bloody modern feast."),
            (54, "しかし、 招かれた 月の神 ツクヨミ の 受け取り 方 は 全く 違いました。", "A split panel portrait beside an empty bench."),
            (59, "豊穣 の 女神 の 血 が、 吐き出された 食べ物 を 赤く 染め上げ ました。", "Surreal horror food macro."),
            (62, "神話 に おける、 最も 理不尽 で 衝動 的 な 殺人 事件 です。", "A memorial boulder with writing in an Edo village."),
            (72, "生み出す という 尊い 行為 を、 汚い と 勘違い した 弟 の 愚か さ。", "A blindfolded silver statue holds a sword."),
            (84, "太陽 と 月 が 共に 空 を 照らした 黄金 の 時代 は 終わり ました。", "An ancient Japanese clock shows day and night."),
            (85, "昼 と 夜 が 交代 で 訪れる という、 新しい 宇宙 の ルール の 始まり です。", "A giant sun pushes the moon."),
            (88, "汚い 食べ物 を 出された ので、 罰 として 殺して やり ました よ と。", "Tsukuyomi stands in a stone gate with a katana."),
            (98, "日本 神話 が 描く、 太陽 と 月 が 決して 出会わない 理由 です。", "A glowing sun and moon hover in balance."),
            (99, "一つ の 悲惨 な 殺人 事件 が、 昼 と 夜 という 宇宙 の 摂理 を 生み出し ました。", "A sword rests on an ancient map."),
            (100, "残酷 な 暴力 と 嫌悪 の 果て に、 世界 の バランス が 完成 した の です。", "A perfectly balanced golden scale."),
            (101, "昼 と 夜 が 交代 で 空 を 支配 する という、 完璧 な 秩序。", "A massive sun pushes a moon away."),
            (105, "その 不完全 さ こそ が、 日本 神話 の キャラクター たち の 魅力 で も あります。", "Two highly detailed hands shaking."),
            (106, "潔癖 すぎる 月の神 が 起こした 悲劇 は、 大きな 教訓 を 含んで います。", "A mirror reflects a horrific crime."),
            (107, "表面 的 な 汚さ だけ を 見て、 その 奥 に ある 命 の 尊さ を 見失って は ならない。", "A lotus rises from mud."),
            (108, "アマテラス は ウケモチ の 命 を 生み出す 力 を、 誰 より も 理解 して いました。", "Amaterasu holds one grain in her palm."),
            (109, "だからこそ、 その 命 を 奪った 弟 を 決して 許さなかった の です。", "Full-body Amaterasu raises both hands among dark rocks."),
            (111, "食べ物 の 女神 が 死んで しまった こと で、 地上 の 食糧 事情 は どう なる の か。", "A red question mark over a bowl."),
            (113, "アマテラス は 心配 して、 別 の 神様 を 地上 へ と 派遣 します。", "A golden messenger bird descends."),
            (114, "急いで ウケモチ が 倒れている 現場 を 確認 させる ため でした。", "Two exposed bodies lie in a timber hall."),
            (116, "ウケモチ の 死体 は、 ただ 朽ち果てる だけ では ありません でした。", "A generic dead body glows."),
            (117, "死 という 究極 の 破壊 から、 全く 新しい 命 が 芽吹き 始めて いた の です。", "A flower blooms from stone."),
            (118, "頭 や 目、 お腹 など、 遺体 の あらゆる 部分 から 奇跡 が 起こり ます。", "A generic seated messenger."),
            (119, "彼女 の 犠牲 が、 日本 という 国 を 永遠 に 豊か に する 贈り物 へ と 変わる の です。", "A map of Japan glows."),
            (120, "悲劇 的 な 死 は、 決して 全て の 終わり では ない という メッセージ。", "A generic seated messenger."),
            (121, "ウケモチ を 斬り殺した 弟 に 激怒 し、 永遠 の 離縁 を 突きつけた アマテラス。", "Amaterasu holds hands with Uke Mochi inside a dark rock arch."),
            (122, "昼 と 夜 が 完全に 分離 し、 太陽 と 月 は 決して 交わらなく なります。", "A divided map of Japan."),
            (123, "アマテラス は、 地上 で 殺された ウケモチ の 遺体 を 心配 しました。", "Amaterasu and a living Uke Mochi gesture with open hands in Yomi."),
            (124, "そこで 別 の 神様 を お 使い に 出して、 現場 を 確認 させ ます。", "A full-body messenger descends barefoot with both hands exposed."),
            (125, "派遣 された 神様 が ウケモチ の 元 へ と 到着 すると、", "A messenger stands beside an exposed male corpse."),
            (126, "なんと その 死体 から、 驚く べき 奇跡 が 起こって いました。", "A living woman reclines with both hands and feet visible."),
            (127, "女神 の 頭 から は、 立派 な 牛 や 馬 が 誕生 して いました。", "Horses emerge from mist."),
            (128, "額 から は 粟 が、 眉毛 から は 絹 を 作る 蚕 が 生み出されて います。", "A living woman pulls silk by hand from giant silkworms."),
            (129, "さらに 目 から は 稗 が、 お腹 から は 稲 が 力強く 育って いました。", "A barefoot woman opens both hands in a rice field."),
            (130, "遺体 の あらゆる 箇所 から、 人間 を 救う 作物 や 動物 が 溢れ出した の です。", "Countless animals appear."),
            (131, "ツクヨミ が 汚い と 感じて 切り捨てた その 命 の 源 こそ が、", "Full-body Tsukuyomi clenches both fists beneath three moons."),
            (132, "死して なお、 世界 を 豊か に する 究極 の 恵み だった の です。", "A baby's hand grabs rice."),
            (133, "アマテラス は これら を 回収 し、 農業 を 始める きっかけ と します。", "Full-body Amaterasu holds grain in both hands."),
            (135, "日本 神話 の 豊穣 信仰 は、 この よう な 犠牲 の 上 に 成り立って います。", "A bloody stone grows a flower."),
            (136, "今回 の ツクヨミ の 暴走 と、 昼夜 分離 の お話 は いかが でした か。", "Full-body Tsukuyomi asks a question."),
            (137, "口 から 吐き出した 食べ物 で もてなす という、 衝撃 的 な 神話 の 描写。", "A scroll records the feast."),
            (138, "潔癖 な 月の神 と、 命 を 尊ぶ 太陽 の 神 の 決定 的 な 対立。", "Tsukuyomi stands alone beneath the moon."),
            (139, "価値 観 の 違い が 殺意 に 変わり、 宇宙 の 構造 さえ 変えて しまい ます。", "A sun pushes a moon."),
            (140, "しかし その 悲劇 の 中 から、 農耕 という 新たな 豊か さ が 生まれ ました。", "Full-body Tsukuyomi stands in crops."),
            (141, "皆さん は この 食べ物 の 起源 と、 神々 の 喧嘩 について どう 感じ ました か。", "A question mark over a journal."),
            (142, "是非 コメント 欄 で、 皆さん の 自由 な ご 意見 を お 聞かせ ください。", "A comment bubble above a desk."),
            (143, "チーム 一同、 楽しく コメント を 読ま せ て 頂いて おります。", "Paper comments surround a fire."),
            (144, "面白い と 思って 頂け たら、 チャンネル 登録 と 高評価 を お願い します。", "A modern subscribe button."),
            (145, "皆さん の 応援 が、 いつも 動画 制作 の 大きな 励み に なって います。", "A fox points at a thumbs-up hand symbol."),
            (146, "さて、 食べ物 の 神 の 死 により、 地上 に は 五穀 が もたらされ ました。", "A map of Japan fills with crops."),
            (147, "一方 で、 海 の 統治 を 放棄 して 追放 された 末っ子 スサノオ は、", "Full-body Susanoo clenches both fists on a beach."),
            (148, "姉 の アマテラス に 別れ を 告げる ため、 高天原 へ と 登って いき ます。", "Full-body Susanoo climbs a mountain."),
            (149, "これ が、 天上 界 を 恐怖 の どん底 に 陥れる 大 事件 の 幕開け と なります。", "A theatrical black curtain opens."),
            (150, "次回、 荒ぶる 弟 と 太陽 神 の 激突、 誓約 の 儀式 に 迫り ます！", "Lightning strikes the sun."),
        )
        script = {
            "title": "태양과 달이 영원히 갈라선 이유 EP.06",
            "topic": "태양과 달이 영원히 갈라선 이유",
            "cuts": [
                {
                    **common,
                    "cut_number": number,
                    "narration": narration,
                    "image_prompt": prompt,
                }
                for number, narration, prompt in rows
            ],
        }

        applied = apply_script_visual_policy(script)
        by_number = {cut["cut_number"]: cut for cut in applied["cuts"]}

        self.assertIn("one curving sand-and-gravel shore", by_number[1]["image_prompt"])
        self.assertNotIn("god's skin", by_number[2]["image_prompt"].lower())
        self.assertIn("strict top-down view", by_number[2]["image_prompt"])
        self.assertIn("small diffuse gray-brown sediment cloud", by_number[2]["image_prompt"])
        self.assertNotIn("ink-like", by_number[2]["image_prompt"].lower())
        self.assertIn("exactly three separated natural light columns", by_number[3]["image_prompt"])
        self.assertIn("exactly three separated natural celestial forms", by_number[4]["image_prompt"])
        self.assertNotIn("visual_subject", by_number[4])
        self.assertNotIn("scene-named adult woman", by_number[4]["image_prompt"].lower())
        self.assertTrue(_should_ignore_object_person_segmentation(by_number[4]["image_prompt"]))
        self.assertTrue(_should_ignore_strict_nonhuman_person_segmentation(by_number[4]["image_prompt"]))
        self.assertNotIn("macro", by_number[5]["image_prompt"].lower())
        self.assertIn("Landscape-only one warm golden sunbeam", by_number[6]["image_prompt"])
        self.assertIn("overlap across the same primordial river valley", by_number[6]["image_prompt"])
        self.assertNotIn("visual_subject", by_number[6])
        self.assertNotIn("palace", by_number[6]["image_prompt"].lower())
        self.assertIn("very broad S-curving primordial river", by_number[8]["image_prompt"])
        self.assertIn("lower two-thirds of the frame", by_number[8]["image_prompt"])
        self.assertNotIn("visual_subject", by_number[8])
        self.assertFalse(_should_ignore_object_person_segmentation(by_number[8]["image_prompt"]))
        self.assertFalse(_should_ignore_strict_nonhuman_person_segmentation(by_number[8]["image_prompt"]))
        self.assertNotIn("map", by_number[9]["image_prompt"].lower())
        self.assertTrue(_should_ignore_object_person_segmentation(by_number[9]["image_prompt"]))
        self.assertTrue(_should_ignore_strict_nonhuman_person_segmentation(by_number[9]["image_prompt"]))
        self.assertIn("Amaterasu", by_number[16]["image_prompt"])
        self.assertIn("Tsukuyomi", by_number[16]["image_prompt"])
        self.assertNotIn("Uke Mochi", by_number[16]["visual_subject"])
        self.assertIn("Tsukuyomi", by_number[18]["visual_subject"])
        self.assertNotIn("Uke Mochi", by_number[18]["visual_subject"])
        self.assertNotIn("palace", by_number[22]["image_prompt"].lower())
        self.assertIn("calm open cloud-lit Takamagahara plain", by_number[22]["image_prompt"])
        self.assertIn("open green primordial field beside a clear river", by_number[24]["image_prompt"])
        self.assertIn("face filling seventy percent of frame height", by_number[24]["image_prompt"])
        self.assertIn("hard lower crop at both collarbones", by_number[24]["image_prompt"])
        self.assertIn("silver fish arc outward", by_number[32]["image_prompt"])
        self.assertNotIn("bloody", by_number[33]["image_prompt"].lower())
        self.assertIn("exactly three clean prepared game-meat portions", by_number[33]["image_prompt"])
        self.assertIn("Right adult woman Uke Mochi smiles with one sealed lip line", by_number[34]["image_prompt"])
        self.assertIn("flat hair crowns and long loose hair flowing past the shoulders", by_number[34]["image_prompt"])
        self.assertNotIn("Object-only", by_number[34]["image_prompt"])
        self.assertNotIn("white square", by_number[34]["image_prompt"].lower())
        self.assertNotIn("cave", by_number[34]["image_prompt"].lower())
        self.assertIn("Uke Mochi smiles warmly", by_number[35]["image_prompt"])
        self.assertNotIn("scroll", by_number[36]["image_prompt"].lower())
        self.assertIn("narration-led two-shot", by_number[37]["image_prompt"])
        self.assertNotIn("ritual mirror disk", by_number[37]["image_prompt"])
        self.assertNotIn("magnifying glass", by_number[37]["image_prompt"].lower())
        self.assertIn("lower frame ending at the collarbones", by_number[41]["image_prompt"])
        self.assertNotIn("threads", by_number[44]["image_prompt"].lower())
        self.assertIn("opposing conviction", by_number[44]["image_prompt"])
        self.assertIn("Tsukuyomi steps forward", by_number[46]["image_prompt"])
        self.assertNotIn("katana", by_number[46]["image_prompt"].lower())
        self.assertIn("Uke Mochi", by_number[46]["visual_subject"])
        self.assertIn("no blood pool or artifact layout", by_number[49]["image_prompt"])
        self.assertNotIn("surreal horror", by_number[59]["image_prompt"].lower())
        self.assertNotIn("statue", by_number[72]["image_prompt"].lower())
        self.assertIn("straight-down aerial view", by_number[84]["image_prompt"])
        self.assertIn("one smooth natural boundary follows the river", by_number[84]["image_prompt"])
        self.assertNotIn("moon rising", by_number[84]["image_prompt"].lower())
        self.assertNotIn("clock", by_number[84]["image_prompt"].lower())
        self.assertNotIn("push", by_number[85]["image_prompt"].lower())
        self.assertNotIn("sun and moon hover", by_number[98]["image_prompt"].lower())
        self.assertNotIn("map", by_number[99]["image_prompt"].lower())
        self.assertIn("Tsukuyomi turning away", by_number[99]["image_prompt"])
        self.assertNotIn("scale", by_number[100]["image_prompt"].lower())
        self.assertIn("stable natural twilight gradient", by_number[100]["image_prompt"])
        self.assertIn("river completely filling the narrow canyon floor", by_number[100]["image_prompt"])
        self.assertNotIn("broad twilight boundary permanently separating day from night", by_number[100]["image_prompt"])
        self.assertTrue(_should_ignore_object_person_segmentation(by_number[100]["image_prompt"]))
        self.assertTrue(_should_ignore_strict_nonhuman_person_segmentation(by_number[100]["image_prompt"]))
        self.assertNotIn("sun pushes", by_number[101]["image_prompt"].lower())
        self.assertIn("long closed sleeves covering every wrist area", by_number[105]["image_prompt"])
        self.assertNotIn("horrific", by_number[106]["image_prompt"].lower())
        self.assertIn("face-only Amaterasu", by_number[107]["image_prompt"])
        self.assertIn("one cracked grain husk with one green shoot", by_number[107]["image_prompt"])
        self.assertNotIn("Object-only", by_number[107]["image_prompt"])
        self.assertIn("Amaterasu", by_number[108]["visual_subject"])
        self.assertIn("Face-only Amaterasu", by_number[108]["image_prompt"])
        self.assertIn("Face-only Amaterasu grieving", by_number[108]["image_prompt"])
        self.assertIn("no body, garment or hands", by_number[108]["image_prompt"])
        self.assertIn("Extreme hand-free facial close-up", by_number[109]["image_prompt"])
        self.assertIn("bare unadorned forehead", by_number[109]["visual_subject"])
        self.assertNotIn("sun ornament", by_number[109]["visual_subject"].lower())
        self.assertNotIn("question mark", by_number[111]["image_prompt"].lower())
        self.assertIn("unnamed adult Japanese messenger deity", by_number[113]["image_prompt"])
        self.assertIn("Extreme hand-free facial close-up", by_number[113]["image_prompt"])
        self.assertIn("both shoulders and every limb outside the frame", by_number[113]["image_prompt"])
        self.assertNotIn("bird", by_number[113]["image_prompt"].lower())
        self.assertIn("face-only messenger stares downward", by_number[114]["image_prompt"])
        self.assertIn("no object, body, garment or hands", by_number[114]["image_prompt"])
        self.assertIn("Object-only low close view", by_number[116]["image_prompt"])
        self.assertIn("tiny fresh-green shoots rises along its edge", by_number[116]["image_prompt"])
        self.assertIn("Object-only", by_number[116]["image_prompt"])
        self.assertIn("Landscape-only famine threat", by_number[111]["image_prompt"])
        self.assertIn("irregular rice, millet and green shoots", by_number[118]["image_prompt"])
        self.assertIn("one vigorous green seedling", by_number[120]["image_prompt"])
        self.assertIn("one irregular wild cluster of newly sprouted fresh-green two-leaf seedlings", by_number[117]["image_prompt"])
        self.assertIn("varied small sizes and uneven natural spacing", by_number[117]["image_prompt"])
        self.assertNotIn("map", by_number[119]["image_prompt"].lower())
        self.assertIn("furious final rejection", by_number[121]["image_prompt"])
        self.assertIn("permanently ends the sibling bond", by_number[121]["image_prompt"])
        self.assertNotIn("Uke Mochi", by_number[121]["visual_subject"])
        self.assertNotIn("ornament", by_number[121]["visual_subject"].lower())
        self.assertNotIn("map", by_number[122]["image_prompt"].lower())
        self.assertIn("all sky outside the crop", by_number[122]["image_prompt"])
        self.assertTrue(_should_ignore_object_person_segmentation(by_number[122]["image_prompt"]))
        self.assertTrue(_should_ignore_strict_nonhuman_person_segmentation(by_number[122]["image_prompt"]))
        self.assertIn("looking downward in grief toward the unseen earth", by_number[123]["image_prompt"])
        self.assertNotIn("Uke Mochi", by_number[123]["visual_subject"])
        self.assertIn("Extreme hand-free facial close-up", by_number[124]["image_prompt"])
        self.assertIn("both shoulders and every limb outside the frame", by_number[124]["image_prompt"])
        self.assertIn("Landscape-only empty packed-earth path", by_number[125]["image_prompt"])
        self.assertIn("no person, body, garment, limb", by_number[125]["image_prompt"])
        self.assertIn("one vigorous green shoot", by_number[126]["image_prompt"])
        self.assertIn("exactly one cow and one horse", by_number[127]["image_prompt"])
        self.assertNotIn("visual_subject", by_number[127])
        self.assertIn("one plain silk cocoon", by_number[128]["image_prompt"])
        self.assertIn("one young rice seedling", by_number[129]["image_prompt"])
        self.assertIn("no person, exposed body, object row", by_number[130]["image_prompt"])
        self.assertIn("one living green shoot", by_number[131]["image_prompt"])
        self.assertIn("cold silver moonlit band visibly recedes away", by_number[131]["image_prompt"])
        self.assertNotIn("visual_subject", by_number[131])
        self.assertIn("irregular green grain shoots spread naturally", by_number[132]["image_prompt"])
        self.assertNotIn("baby", by_number[132]["image_prompt"].lower())
        self.assertIn("adult Amaterasu looking downward at a small irregular patch", by_number[133]["image_prompt"])
        self.assertIn("Amaterasu", by_number[133]["visual_subject"])
        self.assertIn("bare unadorned forehead", by_number[133]["visual_subject"])
        self.assertNotIn("ornament", by_number[133]["visual_subject"].lower())
        self.assertNotIn("bloody", by_number[135]["image_prompt"].lower())
        self.assertIn("Landscape-only empty primordial river valley", by_number[136]["image_prompt"])
        self.assertIn("no person, body, garment", by_number[136]["image_prompt"])
        self.assertIn("one small irregular arc of clean rice grains", by_number[137]["image_prompt"])
        self.assertIn("no person, face, mouth, body part, garment, hand", by_number[137]["image_prompt"])
        self.assertNotIn("visual_subject", by_number[137])
        self.assertIn("Landscape-only one empty primordial river valley", by_number[138]["image_prompt"])
        self.assertNotIn("visual_subject", by_number[138])
        self.assertNotIn("Object-only", by_number[138]["image_prompt"])
        self.assertNotIn("push", by_number[139]["image_prompt"].lower())
        self.assertIn("living green grain shoots spread naturally", by_number[140]["image_prompt"])
        self.assertNotIn("visual_subject", by_number[140])
        self.assertNotIn("question mark", by_number[141]["image_prompt"].lower())
        self.assertIn("Landscape-only empty twilight river", by_number[141]["image_prompt"])
        self.assertNotIn("stone medallions", by_number[141]["image_prompt"])
        self.assertNotIn("comment bubble", by_number[142]["image_prompt"].lower())
        self.assertIn("Landscape-only calm empty riverbank", by_number[142]["image_prompt"])
        self.assertIn("Landscape-only calm primordial river at twilight", by_number[143]["image_prompt"])
        self.assertNotIn("visual_subject", by_number[143])
        self.assertIn("one broad blue storm bank recedes", by_number[144]["image_prompt"])
        self.assertIn("no person, celestial disk, spiral, circle", by_number[144]["image_prompt"])
        self.assertNotIn("thumbs-up", by_number[145]["image_prompt"].lower())
        self.assertNotIn("map", by_number[146]["image_prompt"].lower())
        self.assertIn("broad mixed field of rice, millet and other grains", by_number[146]["image_prompt"])
        self.assertIn("one broad diffuse blue-grey light band fading naturally", by_number[147]["image_prompt"])
        self.assertIn("no person, body part, footprint, track, sash", by_number[147]["image_prompt"])
        self.assertIn("one broad diffuse blue storm shadow climbs naturally", by_number[148]["image_prompt"])
        self.assertIn("no person, body part, footprint, track, sash, rope, cable", by_number[148]["image_prompt"])
        self.assertNotIn("curtain", by_number[149]["image_prompt"].lower())
        self.assertIn("broad horizontal blue-black storm shelf", by_number[149]["image_prompt"])
        self.assertTrue(_should_ignore_object_person_segmentation(by_number[149]["image_prompt"]))
        self.assertTrue(_should_ignore_strict_nonhuman_person_segmentation(by_number[149]["image_prompt"]))
        self.assertIn("adult woman Amaterasu at left faces strict right", by_number[150]["image_prompt"])
        self.assertIn("adult man Susanoo at right faces strict left", by_number[150]["image_prompt"])
        self.assertIn("Amaterasu", by_number[150]["visual_subject"])
        self.assertIn("Susanoo", by_number[150]["visual_subject"])
        self.assertIn("smooth bare forehead", by_number[150]["visual_subject"])
        self.assertNotIn("sun ornament", by_number[150]["visual_subject"].lower())

        forbidden_positive = (
            "modern viewer's hand",
            "magnifying glass",
            "two highly detailed hands",
            "baby's hand",
            "question mark",
            "comment bubble",
            "thumbs-up",
            "theatrical black curtain",
        )
        for number in by_number:
            compiled = compile_image_prompt(
                prepare_scene_contract_source(
                    by_number[number]["image_prompt"],
                    "mature adult graphic novel",
                ),
                model_id="comfyui-flux2-klein-4b",
                base_negative="extra fingers, extra arms, extra legs",
            )
            lowered = compiled.positive.lower()
            for phrase in forbidden_positive:
                self.assertNotIn(phrase, lowered, f"cut {number}: {phrase}")
            if number in {37, 84, 127, 130, 132, 142, 145, 149}:
                negative = compiled.negative.lower()
                self.assertIn("utility pole", negative, f"cut {number}")
                self.assertIn("power line", negative, f"cut {number}")
                self.assertIn("car", negative, f"cut {number}")
            if number == 100:
                negative = compiled.negative.lower()
                self.assertIn("balance scale", negative)
                self.assertIn("chinese imperial crown", negative)
                self.assertIn("forehead jewel", negative)
                self.assertIn("farmer", negative)
                self.assertIn("farm tool", negative)
                self.assertIn("building", negative)
                self.assertEqual("landscape", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
            if number == 4:
                self.assertEqual("landscape", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
            if number == 2:
                negative = compiled.negative.lower()
                self.assertEqual("landscape", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("human body", negative)
                self.assertIn("hand", negative)
                self.assertIn("building", negative)
                self.assertIn("village", negative)
            if number in {8, 9}:
                negative = compiled.negative.lower()
                self.assertEqual("landscape", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("split screen", negative)
                self.assertIn("solid black background", negative)
                self.assertIn("map", negative)
                self.assertIn("person", negative)
                self.assertIn("cart", negative)
            if number == 85:
                negative = compiled.negative.lower()
                self.assertEqual("landscape", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("one continuous empty primordial river valley", lowered)
                self.assertIn("both sun and moon outside the crop", lowered)
                self.assertIn("person", negative)
                self.assertIn("sun disk", negative)
                self.assertIn("moon disk", negative)
                self.assertIn("clock face", negative)
                self.assertIn("map", negative)
                self.assertIn("building", negative)
                self.assertIn("road", negative)
            if number == 88:
                negative = compiled.negative.lower()
                self.assertEqual("single", compiled.scene_kind)
                self.assertEqual(1, compiled.person_count)
                self.assertIn("reporting the killing without remorse", lowered)
                self.assertIn("one continuous extreme facial close-up view", lowered)
                self.assertIn("smooth pale-gold sky", lowered)
                self.assertIn("second person", negative)
                self.assertIn("visible hand", negative)
                self.assertIn("torso below collarbones", negative)
                self.assertIn("katana", negative)
                self.assertIn("sword hilt", negative)
                self.assertIn("stone arch", negative)
                self.assertIn("stone wall", negative)
                self.assertIn("black outer frame", negative)
            if number == 98:
                negative = compiled.negative.lower()
                self.assertEqual("landscape", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("one broad empty twilight corridor", lowered)
                self.assertIn("person", negative)
                self.assertIn("split screen", negative)
                self.assertIn("map", negative)
                self.assertIn("sun disk", negative)
                self.assertIn("moon disk", negative)
                self.assertIn("building", negative)
            if number == 99:
                self.assertEqual("single", compiled.scene_kind)
                self.assertEqual(1, compiled.person_count)
                self.assertIn("tsukuyomi turning away", lowered)
                self.assertIn("fully covered earth-tone shroud", lowered)
                self.assertIn("no blood pool or artifact layout", by_number[number]["image_prompt"].lower())
            if number == 107:
                self.assertEqual("single", compiled.scene_kind)
                self.assertEqual(1, compiled.person_count)
                self.assertIn("face-only amaterasu", lowered)
                self.assertIn("cracked grain husk", lowered)
                self.assertIn("one green shoot", lowered)
            if number in {113, 124}:
                negative = compiled.negative.lower()
                self.assertEqual("single", compiled.scene_kind)
                self.assertEqual(1, compiled.person_count)
                self.assertIn("extreme hand-free facial close-up", lowered)
                self.assertIn("smooth natural golden light", lowered)
                self.assertIn("face filling ninety percent", lowered)
                self.assertIn("both shoulders and every limb outside the frame", lowered)
                self.assertIn("complete face occupies 88-92 percent", lowered)
                self.assertIn("both shoulders, chest, torso", lowered)
                self.assertIn("visible hand", negative)
                self.assertIn("visible fingers", negative)
                self.assertIn("visible shoulder", negative)
                self.assertIn("torso below collarbones", negative)
                self.assertIn("full body", negative)
                self.assertIn("bare feet", negative)
                self.assertIn("building", negative)
            if number == 114:
                self.assertEqual("single", compiled.scene_kind)
                self.assertEqual(1, compiled.person_count)
                self.assertIn("face-only messenger", lowered)
                self.assertIn("stares downward", lowered)
                self.assertFalse(_should_ignore_object_person_segmentation(by_number[number]["image_prompt"]))
            if number == 125:
                self.assertEqual("landscape", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("empty packed-earth path", lowered)
            if number == 116:
                self.assertEqual("object", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("plain earth-tone shroud mound", lowered)
                self.assertIn("tiny fresh-green shoots rises along its edge", lowered)
            if number == 126:
                self.assertEqual("object", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("one vigorous green shoot", lowered)
            if number == 118:
                self.assertEqual("object", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("object-only overhead view", lowered)
                self.assertIn("irregular rice, millet", lowered)
            if number == 109:
                negative = compiled.negative.lower()
                self.assertEqual("single", compiled.scene_kind)
                self.assertEqual(1, compiled.person_count)
                self.assertIn("extreme hand-free facial close-up", lowered)
                self.assertIn("refusing to forgive tsukuyomi", lowered)
                self.assertIn("furious face and golden eyes fill eighty-five percent", lowered)
                self.assertIn("hard collarbone crop", lowered)
                self.assertIn("both shoulders outside frame", lowered)
                self.assertIn("smooth empty pale-gold sky at every corner", lowered)
                self.assertIn("face occupies 80-85 percent", lowered)
                self.assertIn("both shoulders, torso, arms, wrists, hands", lowered)
                self.assertIn("second person", negative)
                self.assertIn("tsukuyomi in frame", negative)
                self.assertIn("visible hand", negative)
                self.assertIn("visible fingers", negative)
                self.assertIn("torso below collarbones", negative)
                self.assertIn("full body", negative)
                self.assertIn("bare feet", negative)
                self.assertIn("large crown", negative)
                self.assertIn("forehead jewel", negative)
                self.assertIn("gold forehead ornament", negative)
                self.assertIn("sun ornament on forehead", negative)
                self.assertIn("fantasy armor", negative)
                self.assertIn("rock arch", negative)
                self.assertIn("black outer frame", negative)
                self.assertIn("building", negative)
                self.assertIn("tiled roof", negative)
            if number == 121:
                negative = compiled.negative.lower()
                self.assertEqual("single", compiled.scene_kind)
                self.assertEqual(1, compiled.person_count)
                self.assertIn("extreme hand-free facial close-up", lowered)
                self.assertIn("furious final rejection", lowered)
                self.assertIn("permanently ends the sibling bond", lowered)
                self.assertIn("bare unadorned forehead", lowered)
                self.assertIn("uke mochi", negative)
                self.assertIn("tsukuyomi in frame", negative)
                self.assertIn("visible fingers", negative)
                self.assertIn("large crown", negative)
                self.assertIn("sun hair ornament", negative)
                self.assertIn("moon hair ornament", negative)
                self.assertIn("crescent hair clip", negative)
                self.assertIn("rock arch", negative)
                self.assertIn("black outer frame", negative)
            if number == 122:
                negative = compiled.negative.lower()
                self.assertEqual("landscape", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("all sky outside the crop", lowered)
                self.assertIn("permanent curved natural twilight corridor", lowered)
                self.assertIn("person", negative)
                self.assertIn("sun disk", negative)
                self.assertIn("moon disk", negative)
                self.assertIn("building", negative)
            if number == 123:
                negative = compiled.negative.lower()
                self.assertEqual("single", compiled.scene_kind)
                self.assertEqual(1, compiled.person_count)
                self.assertIn("looking downward in grief toward the unseen earth", lowered)
                self.assertIn("bare unadorned forehead", lowered)
                self.assertNotIn("sun ornament", lowered)
                self.assertIn("uke mochi in frame", negative)
                self.assertIn("visible hand", negative)
                self.assertIn("visible fingers", negative)
                self.assertIn("full body", negative)
                self.assertIn("sun hair ornament", negative)
                self.assertIn("forehead jewel", negative)
                self.assertIn("rock wall", negative)
                self.assertIn("building", negative)
            if number == 35:
                negative = compiled.negative.lower()
                self.assertIn("white ceramic plate", negative)
                self.assertIn("square plate", negative)
                self.assertIn("visible fingers", negative)
                self.assertIn("cave interior", negative)
            if number in {34, 36}:
                self.assertEqual("pair", compiled.scene_kind)
                self.assertEqual(2, compiled.person_count)
                self.assertIn("uke mochi", lowered)
                self.assertIn("tsukuyomi", lowered)
                self.assertIn("exactly two enormous mature faces" if number == 34 else "two complete adult faces", lowered)
                self.assertNotIn("hand", lowered)
            if number == 20:
                negative = compiled.negative.lower()
                self.assertEqual("pair", compiled.scene_kind)
                self.assertEqual(2, compiled.person_count)
                self.assertIn("welcome turns to dread", lowered)
                self.assertIn("uke mochi", lowered)
                self.assertIn("tsukuyomi", lowered)
                self.assertIn("only both complete faces", lowered)
                self.assertIn("katana", negative)
                self.assertIn("sword", negative)
                self.assertIn("weapon", negative)
                self.assertIn("samurai armor", negative)
                self.assertNotIn("blade", lowered)
                self.assertNotIn("weapon", lowered)
            if number == 63:
                negative = compiled.negative.lower()
                self.assertEqual("single", compiled.scene_kind)
                self.assertEqual(1, compiled.person_count)
                self.assertIn("tsukuyomi holds one clean leaf-shaped bronze blade down", lowered)
                self.assertIn("one red-stained wiping cloth is tied below its hilt", lowered)
                self.assertIn("second blade", negative)
                self.assertIn("duplicate blade", negative)
                self.assertIn("katana", negative)
                self.assertIn("visible left hand", negative)
                self.assertNotIn("sheathed", lowered)
            if number == 104:
                negative = compiled.negative.lower()
                self.assertEqual("single", compiled.scene_kind)
                self.assertEqual(1, compiled.person_count)
                self.assertIn("extreme face-only tsukuyomi close-up", lowered)
                self.assertIn("nose wrinkles, jaw clenches and eyes narrow", lowered)
                self.assertIn("anger overwhelms restraint", lowered)
                self.assertIn("amaterasu", negative)
                self.assertIn("sun ornament", negative)
                self.assertIn("moon ornament", negative)
                self.assertIn("visible hand", negative)
                self.assertIn("patterned robe", negative)
            if number == 51:
                self.assertEqual("pair", compiled.scene_kind)
                self.assertEqual(2, compiled.person_count)
                self.assertIn("exactly two enormous mature faces", lowered)
                self.assertIn("long plain black hair", lowered)
                self.assertIn("long loose hair flowing past the shoulders", lowered)
                self.assertIn("sealed lip line", lowered)
                self.assertNotIn("silver moon ornament", lowered)
                self.assertNotIn("hand", lowered)
            if number == 24:
                negative = compiled.negative.lower()
                self.assertEqual("single", compiled.scene_kind)
                self.assertEqual(1, compiled.person_count)
                self.assertIn("visible hand", negative)
                self.assertIn("visible fingers", negative)
                self.assertIn("third hand", negative)
                self.assertIn("arms in frame", negative)
                self.assertIn("waist", negative)
                self.assertIn("abdomen", negative)
                self.assertIn("black outer frame", negative)
                self.assertIn("tiled roof", negative)
            if number == 46:
                negative = compiled.negative.lower()
                self.assertEqual("pair", compiled.scene_kind)
                self.assertEqual(2, compiled.person_count)
                self.assertIn("tsukuyomi steps forward", lowered)
                self.assertIn("uke mochi recoils", lowered)
                self.assertIn("both hands outside frame", lowered)
            if number == 54:
                negative = compiled.negative.lower()
                self.assertEqual("single", compiled.scene_kind)
                self.assertEqual(1, compiled.person_count)
                self.assertIn("extreme hand-free face-only close-up", lowered)
                self.assertIn("recoiling from the unseen feast", lowered)
                self.assertIn("rigid disgust", lowered)
                self.assertIn("complete face filling ninety-five percent", lowered)
                self.assertIn("hard lower crop at the jaw", lowered)
                self.assertIn("featureless open blue-black sky", lowered)
                self.assertIn("flat featureless natural sky", lowered)
                self.assertIn("both shoulders outside frame", lowered)
                self.assertIn("ends exactly at the jawline", lowered)
                self.assertNotIn("shoulder tops", lowered)
                self.assertIn("visible hands", negative)
                self.assertIn("visible fingers", negative)
                self.assertIn("visible waist", negative)
                self.assertIn("visible legs", negative)
                self.assertIn("full body", negative)
                self.assertIn("edo tiled house", negative)
                self.assertIn("split panel", negative)
            if number == 62:
                self.assertEqual("single", compiled.scene_kind)
                self.assertEqual(1, compiled.person_count)
                self.assertIn("tsukuyomi turning away", lowered)
                self.assertIn("fully covered earth-tone shroud", lowered)
                self.assertIn("no blood pool or artifact layout", by_number[number]["image_prompt"].lower())
            if number == 146:
                self.assertEqual("landscape", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("broad mixed field of rice, millet", lowered)
            if number == 117:
                negative = compiled.negative.lower()
                self.assertIn("one irregular wild cluster of newly sprouted fresh-green two-leaf seedlings", lowered)
                self.assertIn("varied sizes, uneven gaps and natural asymmetry", lowered)
                self.assertIn("composition=irregular_wild_seedling_cluster", compiled.diagnostics)
                self.assertIn("farmhouse", negative)
                self.assertIn("roof tiles", negative)
                self.assertIn("cultivated field", negative)
                self.assertIn("repeated spacing", negative)
                self.assertIn("regular grid", negative)
                self.assertIn("large crop field", negative)
                self.assertIn("mature wheat", negative)
                self.assertIn("mature barley", negative)
                self.assertIn("golden grain head", negative)
                self.assertIn("seed head", negative)
                self.assertIn("person", negative)
                self.assertEqual("landscape", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
            if number in {127, 130}:
                self.assertEqual("animal", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("exactly one cow and one horse", lowered)
                self.assertIn("no person", by_number[number]["image_prompt"].lower())
            if number == 128:
                self.assertEqual("object", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("one plain silk cocoon", lowered)
            if number == 129:
                self.assertEqual("object", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("one young rice seedling", lowered)
            if number == 131:
                self.assertEqual("landscape", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("cold silver moonlit band visibly recedes away", lowered)
                self.assertIn("one living green shoot", lowered)
            if number == 132:
                self.assertEqual("landscape", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("green grain shoots spread naturally", lowered)
            if number == 133:
                self.assertEqual("single", compiled.scene_kind)
                self.assertEqual(1, compiled.person_count)
                self.assertIn("amaterasu looking downward at a small irregular patch", lowered)
                self.assertIn("face fills eighty-five percent of the frame", lowered)
                self.assertIn("tiny two-leaf seedlings form one irregular narrow distant wild-soil strip", lowered)
                self.assertIn("composition=amaterasu_first_seedlings_face_only", compiled.diagnostics)
                self.assertNotIn("hand", lowered)
            if number == 136:
                self.assertEqual("landscape", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("empty primordial river valley", lowered)
            if number == 137:
                negative = compiled.negative.lower()
                self.assertEqual("object", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("one small irregular arc of clean rice grains", lowered)
                self.assertIn("person", negative)
                self.assertIn("hands", negative)
            if number == 138:
                self.assertEqual("landscape", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("sharp natural twilight boundary", lowered)
            if number == 140:
                self.assertEqual("landscape", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("living green grain shoots spread naturally", lowered)
            if number in {141, 142, 143}:
                self.assertEqual("landscape", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("landscape-only", lowered)
                self.assertIn("no person, body, garment", by_number[number]["image_prompt"].lower())
            if number == 144:
                self.assertEqual("landscape", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("one broad blue storm bank recedes", lowered)
                self.assertNotIn("sealed blank support tokens", lowered)
            if number in {147, 148}:
                negative = compiled.negative.lower()
                self.assertEqual("landscape", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("one broad diffuse blue", lowered)
                self.assertIn("person", negative)
                self.assertIn("hand", negative)
            if number == 149:
                negative = compiled.negative.lower()
                self.assertEqual("landscape", compiled.scene_kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn("broad horizontal blue-black storm shelf", lowered)
                self.assertIn("vertical tornado", negative)
                self.assertIn("vertical cloud column", negative)
                self.assertIn("human silhouette", negative)
                self.assertTrue(_should_ignore_object_person_segmentation(by_number[number]["image_prompt"]))
                self.assertTrue(_should_ignore_strict_nonhuman_person_segmentation(by_number[number]["image_prompt"]))
            if number == 150:
                self.assertEqual("pair", compiled.scene_kind)
                self.assertEqual(2, compiled.person_count)
                self.assertIn("adult woman amaterasu at left faces strict right", lowered)
                self.assertIn("adult man susanoo at right faces strict left", lowered)
                self.assertIn("eyes lock directly", lowered)
                self.assertIn("composition=amaterasu_susanoo_face_only_confrontation", compiled.diagnostics)
                self.assertNotIn("hand", lowered)
                self.assertNotIn("sun ornament", lowered)

        reapplied = apply_script_visual_policy(applied)
        reapplied_cut4 = next(cut for cut in reapplied["cuts"] if cut["cut_number"] == 4)
        self.assertNotIn("visual_subject", reapplied_cut4)
        self.assertNotIn("scene-named adult woman", reapplied_cut4["image_prompt"].lower())
        reapplied_compiled_cut4 = compile_image_prompt(
            prepare_scene_contract_source(
                reapplied_cut4["image_prompt"],
                "mature adult graphic novel",
            ),
            model_id="comfyui-flux2-klein-4b",
            base_negative="extra fingers, extra arms, extra legs",
        )
        self.assertEqual("landscape", reapplied_compiled_cut4.scene_kind)
        self.assertIsNone(reapplied_compiled_cut4.person_count)

    def test_generated_japanese_myth_location_and_object_scene_survive_policy(self):
        script = {
            "title": "ころされた女神のからだに、米とカイコが生まれた EP.07",
            "description": "ウケモチの死体から米と蚕が生まれる神話。",
            "visual_world": {
                "time_range": "Japanese mythic age",
                "place_scope": "Takamagahara agrarian ritual spaces",
                "culture_scope": "Japanese mythic deity world",
                "material_culture": "wood, reeds, grain, silkworms, and water",
                "continuity_rule": "No modern objects.",
            },
            "cuts": [
                {
                    "cut_number": 3,
                    "narration": "でも、その死体から人を養う命が出ます",
                    "visual_year": "Japanese mythic age",
                    "visual_period": "Japanese creation myth",
                    "visual_location": "packed-earth food shelter court in Takamagahara",
                    "visual_subject": "exactly two adult deities, Uke Mochi and Tsukuyomi",
                    "visual_scene": (
                        "close-up, rice shoots split through damp earth beside pale beans "
                        "and tight silkworm cocoons against a torn reed mat"
                    ),
                    "image_prompt": (
                        "Material culture: wood, reeds, grain, silkworms, and water; "
                        "Style: dark underworld tension; "
                        "Main subject: exactly two adult deities, Uke Mochi and Tsukuyomi; "
                        "Scene: close-up, rice shoots split through damp earth beside pale beans "
                        "and tight silkworm cocoons against a torn reed mat"
                    ),
                }
            ],
        }

        cut = apply_script_visual_policy(script)["cuts"][0]

        self.assertEqual(
            cut["visual_location"],
            "packed-earth food shelter court in Takamagahara",
        )
        self.assertNotIn("visual_subject", cut)
        self.assertNotIn("Main subject:", cut["image_prompt"])
        self.assertNotIn("purification riverbank", cut["image_prompt"])
        self.assertNotIn("Yomi underworld", cut["image_prompt"])

    def test_generated_uke_mochi_and_messenger_aliases_restore_scene_cast(self):
        script = {
            "title": "ころされた女神のからだに、米とカイコが生まれた EP.07",
            "description": "ウケモチの死体から米と蚕が生まれる神話。",
            "visual_world": {
                "time_range": "Japanese mythic age",
                "place_scope": "Takamagahara agrarian ritual spaces",
                "culture_scope": "Japanese mythic deity world",
                "material_culture": "wood, reeds, grain, silkworms, and water",
                "continuity_rule": "No modern objects.",
            },
            "cuts": [
                {
                    "cut_number": 8,
                    "narration": "ウケモチはツクヨミを迎えました",
                    "visual_year": "Japanese mythic age",
                    "visual_period": "Japanese creation myth",
                    "visual_location": "Ukemochi's heavenly food hall",
                    "visual_subject": "exactly one adult male Tsukuyomi",
                    "visual_scene": "Ukemochi welcomes Tsukuyomi inside the hall",
                    "image_prompt": (
                        "Main subject: exactly one adult male Tsukuyomi; "
                        "Scene: Ukemochi welcomes Tsukuyomi inside the hall"
                    ),
                },
                {
                    "cut_number": 16,
                    "narration": "アマテラスは使者に命じました",
                    "visual_year": "Japanese mythic age",
                    "visual_period": "Japanese creation myth",
                    "visual_location": "Amaterasu's heavenly hall",
                    "visual_subject": "exactly one adult female Amaterasu",
                    "visual_scene": "the messenger receives an order from Amaterasu",
                    "image_prompt": (
                        "Main subject: exactly one adult female Amaterasu; "
                        "Scene: the messenger receives an order from Amaterasu"
                    ),
                },
            ],
        }

        applied = apply_script_visual_policy(script)
        by_number = {cut["cut_number"]: cut for cut in applied["cuts"]}

        self.assertIn("exactly two adult Japanese deities", by_number[8]["visual_subject"])
        self.assertIn("Uke Mochi", by_number[8]["visual_subject"])
        self.assertIn("Tsukuyomi", by_number[8]["visual_subject"])
        self.assertIn("exactly two adult Japanese deities", by_number[16]["visual_subject"])
        self.assertIn("Amaterasu", by_number[16]["visual_subject"])
        self.assertIn("adult messenger deity", by_number[16]["visual_subject"])

    def test_generated_nonhuman_and_single_person_scenes_get_z_image_cast_locks(self):
        script = {
            "title": "ころされた女神のからだに、米とカイコが生まれた EP.07",
            "description": "ウケモチの死体から米と蚕が生まれる神話。",
            "visual_world": {
                "time_range": "Japanese mythic age",
                "place_scope": "Takamagahara agrarian ritual spaces",
                "culture_scope": "Japanese mythic deity world",
                "material_culture": "wood, reeds, grain, silkworms, and water",
                "continuity_rule": "No modern objects.",
            },
            "cuts": [
                {
                    "cut_number": 3,
                    "narration": "稲と蚕のはじまりです",
                    "visual_year": "Japanese mythic age",
                    "visual_period": "Japanese creation myth",
                    "visual_location": "floor beside Ukemochi in the heavenly hall",
                    "visual_scene": "rice shoots beside silkworms, no people, no visible hands",
                    "image_prompt": "Scene: rice shoots beside silkworms, no people, no visible hands",
                }
            ],
        }

        cut = apply_script_visual_policy(script)["cuts"][0]
        self.assertTrue(cut["visual_scene"].startswith("Object-only "))
        self.assertNotIn("visual_subject", cut)
        object_guard = _z_image_japanese_myth_positive_guard(cut["image_prompt"])
        self.assertNotIn("Adult figure lock:", object_guard)

        single_guard = _z_image_japanese_myth_positive_guard(
            (
                "Year/period: Japanese mythic creation era; "
                "Main subject: exactly one adult male Tsukuyomi; "
                "Scene: Tsukuyomi approaches a thatched hall"
            )
        )
        self.assertIn("exactly one visible adult appears in the entire frame", single_guard)
        self.assertIn("no other person appears", single_guard)

    def test_uke_mochi_generated_pair_risk_scenes_rewrite_to_single_narration_actor(self):
        script = {
            "title": "ころされた女神のからだに、米とカイコが生まれた EP.07",
            "description": "ウケモチの死体から米と蚕が生まれる神話。",
            "cuts": [
                {
                    "cut_number": 12,
                    "narration": "でも、怒りの理由は一つに決めきれません",
                    "visual_location": "dim food hall",
                    "visual_scene": (
                        "wide tense view with Ukemochi lowered at left and Tsukuyomi half-shadowed "
                        "at right, overturned vessels between them, exactly zero visible hands"
                    ),
                    "image_prompt": "Main subject: Uke Mochi and Tsukuyomi; Scene: tense hall",
                },
                {
                    "cut_number": 16,
                    "narration": "知らせは使いの口からアマテラスに届きます",
                    "visual_location": "bright heavenly council space",
                    "visual_scene": (
                        "medium-wide view with Amaterasu seated upright at center, messenger kneeling "
                        "at left in alarm, woven mats and plain pillars"
                    ),
                    "image_prompt": "Main subject: Amaterasu and messenger; Scene: council report",
                },
                {
                    "cut_number": 24,
                    "narration": "使いはおそれながら、その変化を見ました",
                    "visual_location": "inside the heavenly hall",
                    "visual_scene": (
                        "close-up of the messenger's frightened face reflected in a dark clay bowl, "
                        "sprouts rising below the frame"
                    ),
                    "image_prompt": "Main subject: messenger; Scene: bowl reflection",
                },
                {
                    "cut_number": 29,
                    "narration": "アマテラスの側は、それを残そうとします",
                    "visual_location": "Amaterasu's audience chamber",
                    "visual_scene": (
                        "medium view with messenger presenting a covered basket at left and "
                        "Amaterasu leaning forward at center"
                    ),
                    "image_prompt": "Main subject: Amaterasu and messenger; Scene: basket",
                },
                {
                    "cut_number": 35,
                    "narration": "近づくほど、からだの変化が見えてきます",
                    "visual_location": "beside Ukemochi's fallen body",
                    "visual_scene": (
                        "intense close-up of sprouting grains and pale silkworms clustered along "
                        "the edge of white hemp cloth, shadows deepen around the mat, no people, "
                        "no visible hands"
                    ),
                    "image_prompt": "Scene: grains and silkworms beside white cloth",
                },
                {
                    "cut_number": 34,
                    "narration": "それでも、芽吹く穀物を見なければ答えは出ません",
                    "visual_location": "inside the death hall",
                    "visual_scene": (
                        "medium view of the messenger leaning forward with fearful eyes toward "
                        "sprouting grains, robe sleeve brushing a pillar, exactly zero visible hands"
                    ),
                    "image_prompt": "Main subject: messenger; Scene: messenger examines sprouts",
                },
                {
                    "cut_number": 38,
                    "narration": "けれど、稲と蚕が出る点は強く残ります",
                    "visual_location": "mat display of rice shoots and silkworms",
                    "visual_scene": (
                        "close-up of vivid rice shoots rising beside white silkworms on mulberry "
                        "leaves, both framed by plain clay dishes and woven fibers, no visible hands"
                    ),
                    "image_prompt": "Scene: rice shoots and silkworms",
                },
                {
                    "cut_number": 40,
                    "narration": "ここから、まず稲の意味が大きくなります",
                    "visual_location": "edge of a mythic wet rice paddy",
                    "visual_scene": (
                        "low close-up of young rice plants bending over dark paddy water, a woven "
                        "seed basket lying nearby, thatched granary blurred behind, no visible hands"
                    ),
                    "image_prompt": "Scene: rice plants and seed basket",
                },
                {
                    "cut_number": 49,
                    "narration": "小さな白い虫が、暮らしの重みを背負います",
                    "visual_location": "mulberry grove beside a simple dwelling",
                    "visual_scene": (
                        "macro view of one pale silkworm gripping a mulberry leaf edge, a blurred "
                        "thatched dwelling and hanging plain cloth behind, no people, no visible hands"
                    ),
                    "image_prompt": "Main subject: Amaterasu; Scene: one silkworm",
                },
                {
                    "cut_number": 50,
                    "narration": "こうして、豊かさは食だけを越えていきます",
                    "visual_location": "field edge with grain basket and cocoon tray",
                    "visual_scene": (
                        "wide close-ground view of a full woven grain basket beside a shallow tray "
                        "of cocoons, paddy water and mulberry leaves behind, no visible hands"
                    ),
                    "image_prompt": "Scene: grain basket and cocoon tray",
                },
                {
                    "cut_number": 52,
                    "narration": "作物名は伝えで少しずつ変わります",
                    "visual_location": "reed mat beside stored grains",
                    "visual_subject": (
                        "exactly one adult female Amaterasu, mature East Asian face, "
                        "long center-parted black hair"
                    ),
                    "visual_scene": (
                        "medium-close of an elder storyteller leaning toward several grain piles, "
                        "lined face serious, plain robe, exactly zero visible hands"
                    ),
                    "image_prompt": (
                        "Main subject: exactly one adult female Amaterasu; "
                        "Scene: elder storyteller and grain piles; adult woman with attractive charisma"
                    ),
                },
                {
                    "cut_number": 56,
                    "narration": "ここで、散らばる種を集める役目が重くなります",
                    "visual_location": "heavenly hall floor with seed baskets",
                    "visual_scene": (
                        "close-up of two empty woven baskets set beside scattered grains and cocoons "
                        "on reed mats, their shadows crossing like a choice, no visible hands"
                    ),
                    "image_prompt": "Scene: two empty baskets",
                },
                {
                    "cut_number": 62,
                    "narration": "こわい床から、泥の田んぼへ場面が移ります",
                    "visual_scene": (
                        "split close-ground view with reed mat edge fading into wet paddy mud, "
                        "rice seeds scattered along the boundary, no people, no visible hands"
                    ),
                    "image_prompt": "Scene: adult woman standing in a rice field",
                },
                {
                    "cut_number": 64,
                    "narration": "死んだ神は戻らず、種だけが進みます",
                    "visual_scene": (
                        "view from an empty reed mat through an open doorway toward green paddy shoots, "
                        "folded white robe in shadow, no people, no visible hands"
                    ),
                    "image_prompt": "Scene: one person in a white robe at the doorway",
                },
                {
                    "cut_number": 70,
                    "narration": "その手間は、桑の葉摘みや蚕の世話にもつながります",
                    "visual_scene": (
                        "low close-up of a rice basket beside freshly cut mulberry leaves on a field path "
                        "between paddy water and grove shade, no visible hands"
                    ),
                    "image_prompt": "Scene: cropped person carrying a basket",
                },
                {
                    "cut_number": 73,
                    "narration": "やがて白い繭が枝にでき、糸のもとになります",
                    "visual_scene": (
                        "close-up of pale cocoons clustered among twig frames in a woven tray, "
                        "thin fibers catching amber hearth light, no people, no visible hands"
                    ),
                    "image_prompt": "Scene: cocoons burning beside a hearth",
                },
                {
                    "cut_number": 84,
                    "narration": "それでも、閉じた籠の奥に残された種は消えません",
                    "visual_scene": (
                        "close-up of sealed woven seed baskets under a raised-floor granary, "
                        "light and shadow crossing the wood posts, no people, no visible hands"
                    ),
                    "image_prompt": "Scene: several open baskets",
                },
                {
                    "cut_number": 85,
                    "narration": "神々が離れても、田には芽が残ります",
                    "visual_subject": (
                        "exactly two adult Japanese deities: adult female Amaterasu and adult male Tsukuyomi"
                    ),
                    "visual_scene": (
                        "low close view of rice sprouts standing in shallow water, split light from the sky "
                        "reflected on the surface, no people, no visible hands"
                    ),
                    "image_prompt": (
                        "Main subject: the scene-named adult woman; Scene: stylish medium-close entrance "
                        "of the scene-named adult woman, adult woman with attractive charisma"
                    ),
                },
                {
                    "cut_number": 86,
                    "narration": "ウケモチは戻らず、命だけが受け継がれます",
                    "visual_scene": (
                        "close-up of a folded white robe on reed mats, doorway behind opening to bright "
                        "rice shoots, no people, no visible hands"
                    ),
                    "image_prompt": "Scene: body-shaped white robe on a mat",
                },
                {
                    "cut_number": 87,
                    "narration": "強い神でなく、小さな粒が世界を支えます",
                    "visual_scene": (
                        "macro view of one rice grain resting on rough wooden granary planks, "
                        "huge shadow of a basket rising behind it, no people, no visible hands"
                    ),
                    "image_prompt": "Scene: large basket and bowl",
                },
                {
                    "cut_number": 89,
                    "narration": "残ったものこそ、この話の主役になりました",
                    "visual_scene": (
                        "overhead close-up of rice, beans, millet, and cocoons gathered under a single "
                        "clay lamp, darkness around the mat, no people, no visible hands"
                    ),
                    "image_prompt": "Scene: grains and a boar around a lamp",
                },
            ],
        }

        applied = apply_script_visual_policy(script)
        by_number = {cut["cut_number"]: cut for cut in applied["cuts"]}

        self.assertIn("exactly one adult male Tsukuyomi", by_number[12]["visual_subject"])
        self.assertIn("strict head-and-shoulders close-up", by_number[12]["visual_scene"])
        self.assertIn("vessel rim small at the bottom edge", by_number[12]["visual_scene"])
        self.assertIn("exactly zero visible arms, hands or fingers", by_number[12]["visual_scene"])
        self.assertIn("messenger alone", by_number[16]["visual_scene"])
        self.assertIn("strict head-and-shoulders close-up", by_number[16]["visual_scene"])
        self.assertIn("exactly zero visible arms, hands or fingers", by_number[16]["visual_scene"])
        self.assertIn("exactly one adult male unnamed Japanese messenger deity", by_number[16]["visual_subject"])
        self.assertIn("messenger alone", by_number[24]["visual_scene"])
        self.assertIn("exactly one adult male unnamed Japanese messenger deity", by_number[24]["visual_subject"])
        self.assertIn("Amaterasu alone", by_number[29]["visual_scene"])
        self.assertIn("strict head-and-shoulders close-up", by_number[29]["visual_scene"])
        self.assertIn("basket small at the bottom edge", by_number[29]["visual_scene"])
        self.assertIn("exactly zero visible arms, hands or fingers", by_number[29]["visual_scene"])
        self.assertIn("exactly one adult female Amaterasu", by_number[29]["visual_subject"])
        self.assertIn("adult male messenger alone", by_number[34]["visual_scene"])
        self.assertIn("strict head-and-shoulders close-up", by_number[34]["visual_scene"])
        self.assertIn("exactly one adult male unnamed Japanese messenger deity", by_number[34]["visual_subject"])
        self.assertIn("exactly one elderly adult East Asian male storyteller", by_number[52]["visual_scene"])
        self.assertIn("inside one enclosed reed-mat timber hall", by_number[52]["visual_scene"])
        self.assertIn("three separated grain piles", by_number[52]["visual_scene"])
        self.assertIn("elderly adult East Asian male storyteller", by_number[52]["visual_subject"])
        self.assertNotIn("Amaterasu", by_number[52]["visual_subject"])
        self.assertIn("elderly adult East Asian male storyteller", by_number[52]["image_prompt"])
        self.assertNotIn("scene-named adult woman", by_number[52]["image_prompt"])
        self.assertNotIn("attractive charisma", by_number[52]["image_prompt"])
        for cut_number in (35, 38, 40, 49, 50, 56):
            self.assertNotIn("visual_subject", by_number[cut_number])
            self.assertIn("no people", by_number[cut_number]["visual_scene"])
        for cut_number in (35, 38, 40, 49, 50, 56):
            self.assertTrue(
                by_number[cut_number]["visual_scene"].startswith("Object-only"),
                cut_number,
            )
        self.assertTrue(by_number[62]["visual_scene"].startswith("Landscape-only"))
        self.assertNotIn("visual_subject", by_number[62])
        self.assertIn("no animal, no silkworm, no cocoon", by_number[62]["visual_scene"])
        self.assertIn("compact flat rectangular stack of white cloth", by_number[64]["visual_scene"])
        self.assertIn("no upright robe, no body-shaped garment", by_number[64]["visual_scene"])
        self.assertIn("exactly one full woven rice basket", by_number[70]["visual_scene"])
        self.assertIn("no cropped body, no arm, no hand, no feet", by_number[70]["visual_scene"])
        self.assertIn("no flame, no fire, no smoke", by_number[73]["visual_scene"])
        self.assertIn("exactly one closed woven seed basket", by_number[84]["visual_scene"])
        self.assertIn("one fitted flat woven lid", by_number[84]["visual_scene"])
        self.assertTrue(by_number[85]["visual_scene"].startswith("Landscape-only"))
        self.assertNotIn("visual_subject", by_number[85])
        self.assertNotIn("scene-named adult woman", by_number[85]["image_prompt"])
        self.assertIn("no animal, no silkworm, no cocoon", by_number[85]["visual_scene"])
        self.assertIn("compact flat rectangular stack", by_number[86]["visual_scene"])
        self.assertIn("no body-shaped mound", by_number[86]["visual_scene"])
        self.assertIn("exactly one raw unhulled rice seed", by_number[87]["visual_scene"])
        self.assertIn("one narrow tapered pale hull", by_number[87]["visual_scene"])
        self.assertIn("no shadow, no basket, no bowl, no tray, no sack", by_number[87]["visual_scene"])
        self.assertIn("exactly four separated groups", by_number[89]["visual_scene"])
        self.assertIn("no animal, no meat, no fish", by_number[89]["visual_scene"])

    def test_uke_mochi_afterlife_episode_keeps_people_and_nature_instead_of_artifact_grids(self):
        rows = (
            (3, "食べ物 を 司る 女神、 ウケモチ が 残酷 に 殺される という 悲劇 です。", "A tragic mythic encounter."),
            (4, "ツクヨミ は 冷たい 目 で 地上 を 見下ろし ました。", "Tsukuyomi looks down."),
            (6, "アマテラス は ツクヨミ を 厳しく 叱り ました。", "Amaterasu rebukes Tsukuyomi."),
            (14, "アマテラス は 天熊人 を 地上 へ 遣わし ました。", "Amaterasu sends a messenger."),
            (16, "天熊人 は 地上 へ 降りて 行き ます。", "The messenger descends."),
            (17, "天熊人 は ウケモチ の 元 へ 到着 しました。", "The messenger arrives beside the fallen goddess."),
            (18, "血 の 海 に 沈む 女神 の 姿 を 覚悟 して いた 天熊人 です が。", "The messenger god stopping dead in his tracks, his eyes wide with absolute shock."),
            (26, "彼女 の 頭部 から は、 立派 な 牛 と 馬 が 鳴き声 を 上げて いました。", "A cow and horse appear."),
            (28, "眉毛 の 辺り から は、 絹糸 を 生み出す 蚕 が 生まれて いました。", "Silkworms appear."),
            (34, "この 劇的 な 変化 に、 使者 の 天熊人 は 息 を 呑み ました。", "A golden scale beside a scroll."),
            (40, "アマテラス は 種 を 育てる ため 田 に 立ち ました。", "Amaterasu cultivates rice."),
            (47, "現代 でも 天皇 陛下 は、 皇居 の 中 で 自ら 稲作 を 行って います。", "A historic castle paddy."),
            (48, "春 に 田植え を し、 秋 に 収穫 する という 伝統 的 な 儀式 です。", "A shroud beside seedlings."),
            (49, "これ は 全て、 アマテラス の 稲作 神話 を 現代 に 受け継いで いる の です。", "A historic castle paddy."),
            (50, "古代 の 神話 が、 現代 の 国家 行事 に まで 直結 して いる 面白 さ です。", "A historic castle paddy."),
            (51, "ウケモチ の 死体 から 生まれた 種 を 受け取った アマテラス。", "Amaterasu holds a glowing basket."),
            (52, "アマテラス は 粟 と 豆 と 稲 を 育て 始め ました。", "Amaterasu begins cultivation."),
            (54, "アマテラス は 泥 の 中 で 稲 を 植え ました。", "Amaterasu plants rice."),
            (57, "その ため 日本 中 の 神社 では、 今 でも 豊作 を 祈る お 祭り が 行われ ます。", "A historic castle paddy."),
            (58, "秋 に 収穫 された 新米 を 神様 に 捧げる、 新嘗祭 も その 一つ です。", "A historic castle paddy."),
            (59, "天皇 陛下 自ら が、 毎年 感謝 を 込めて 祈り を 捧げ ます。", "A historic castle paddy."),
            (61, "殺された 食べ物 の 女神 の 命 が、 稲穂 と なって 甦り。", "An empty barren shore."),
            (62, "それ を 太陽 の 女神 が 育て、 人間 の 命 を 繋ぐ という 壮大 な サイクル。", "A symbolic cycle diagram."),
            (63, "悲劇 的 な 死 から 始まった 物語 が、 永遠 の 豊か さ へ と 繋がり ました。", "An empty barren shore."),
            (64, "古代 の 人々 は、 自然 の サイクル を この ように 美しく 捉えた の です。", "A glass timeline display."),
            (65, "米 一 粒 に 神様 が 宿る という 思想 の、 まさに 原点 と 言え ます。", "An empty barren shore."),
            (66, "ウケモチ の ように、 殺された 神 の 体 から 作物 が 生まれる という 神話。", "A collage of objects."),
            (67, "実は これ、 日本 だけ の 特別 な お話 では ありません。", "An empty barren shore."),
            (68, "世界中 の 神話 学 で は、 これ を ハイヌウェレ 型 神話 と 呼び ます。", "A glowing world map."),
            (69, "ハイヌウェレ と は、 インドネシア の 神話 に 登場 する 少女 の 名前 です。", "A carved idol display."),
            (70, "彼女 の 大便 から は 宝物 が 出る ため、 嫉妬 されて 殺されて しまい ます。", "A treasure grid."),
            (71, "しかし その バラバラ に された 死体 から、 さまざま な イモ 類 が 生まれ ました。", "A tuber display."),
            (72, "全く 同じ 構造 の 物語 が、 東南 アジア や オセアニア に 広く 存在 します。", "A map with icons."),
            (73, "南米 や アフリカ、 さら に は アメリカ 先住民 の 間 に も 見られ ます。", "A map with artifacts."),
            (74, "これら の 神話 に 共通 して いる の は、 死 が 命 の 起源 だ という 哲学 です。", "A cycle diagram."),
            (75, "植物 は 一度 枯れて 土 に 還ら なければ、 新しい 芽 を 出し ません。", "A glass timeline."),
            (76, "古代 の 人々 は 農耕 の サイクル の 中 に、 死 と 再生 の 真理 を 見た の です。", "A symbolic wheel."),
            (77, "一 つ の 大きな 犠牲 が なければ、 多く の 命 は 養えない という 厳しい 現実。", "A shroud and artifact row."),
            (78, "食べ物 を 頂く という こと は、 命 を 奪う という 暴力 性 を 伴い ます。", "Three people in old robes outdoors."),
            (80, "命 を 奪う 罪悪 感 と、 それ でも 食べ なければ 生きられない 矛盾。", "Three cloned men in a historic field."),
            (82, "命 を 犠牲 に して くれた 存在 への、 深い 感謝 と 祈り。", "Three farmers bow outdoors."),
            (83, "日本人 が 食事 の 前 に 言う、 いただき ます という 言葉。", "Three speech bubbles above cloned diners."),
            (84, "あなた の 命 を、 私 の 命 として 頂き ます、 という 意味 が 込められて います。", "A glowing inscription above a meal."),
            (85, "日常 の 何気ない 挨拶 に も、 この 古代 の 精神 が 息づいて いる の です。", "Three people in robes outdoors."),
            (87, "ウケモチ の 眉毛 から は、 糸 を 吐き出す 蚕 が 誕生 して います。", "One cocoon on a rocky seashore."),
            (88, "アマテラス は この 蚕 も 大切 に 扱い、 天上 界 で 育て 始め ました。", "A woman beside silkworms on a barren shore."),
            (90, "そして 繭 が できる と、 それ を 口 に 含んで 糸 を 引き出し ました。", "A face with no silk thread."),
            (91, "これ が、 日本 における 養蚕、 つまり シルク 作り の 始まり です。", "A giant silkworm on a coast."),
            (92, "太陽 の 女神 は 農業 だけでなく、 織物 の 技術 も 確立 した の です。", "A woman holding cloth on a barren shore."),
            (93, "引き出した 美しい 絹糸 で、 神々 の 着る 神聖 な 衣服 を 織り上げ ます。", "Three cloned women in robes outdoors."),
            (94, "衣服 は 寒 さ から 身 を 守る だけでなく、 呪術 的 な 力 を 持ち ました。", "Giant silkworms emitting threads."),
            (95, "この 養蚕 の 技術 も また、 現代 の 皇室 に 深く 受け継がれて います。", "An old palace exterior."),
            (96, "現在 でも 皇后 陛下 は、 皇居 の 中 で 蚕 を 育てる ご 養蚕 を 行って います。", "A dignified figure in traditional clothing carefully tending to silkworms in a pristine royal room."),
            (97, "歴代 の 皇后 が 大切 に 受け継いできた、 非常に 伝統 的 な 行事 です。", "A woman outdoors before tiled gates."),
            (98, "そこで 作られた 絹 は、 神社 への 奉納 や 国賓 への 贈り物 に されます。", "A woman holding silk outdoors."),
            (99, "アマテラス が 始めた 糸紡ぎ が、 千 年 以上 も 絶え ず 続いて いる の です。", "A woman in a kimono outdoors."),
            (100, "日本 の 歴史 の 奥深 さ を 感じ させる、 素晴らしい エピソード です。", "An empty coast field."),
            (101, "アマテラス は 機屋 と 呼ばれる 神聖 な 建物 を 建て ました。", "A generic building."),
            (102, "そこ では 多く の 天の服織女 たち が、 日夜 織物 を しています。", "Cloned women in robes."),
            (103, "神々 の 着る 衣 を 織る という の は、 極めて 重要 な 仕事 でした。", "An artifact display."),
            (104, "天上 界 で ある 高天原 は、 農業 と 織物 により 大変 豊か に なります。", "A symbolic collage."),
            (105, "太陽 の 光 が 燦々 と 降り注ぎ、 黄金 色 の 稲穂 が 揺れる 理想郷。", "A barren coast."),
            (106, "平和 で 秩序立った、 完璧 な 神々 の 世界 が 完成 した か に 見え ました。", "A diagram."),
            (107, "アマテラス は 偉大 な 統治 者 として、 世界 を 優しく 包み込み ます。", "A generic ruler."),
            (108, "しかし、 この 完璧 な 平和 は 長く は 続き ません でした。", "A shrine gate."),
            (109, "あの トラブル メーカー の 存在 を 忘れて は いけ ません。", "A generic man."),
            (110, "海 を 追放 された 末っ子 の 暴風 神、 スサノオ の 存在 です。", "A man in a kimono."),
            (111, "スサノオ は 母親 の いる 根の国 へ 向かう 前 に、 ある 行動 を 起こし ます。", "A generic man."),
            (112, "姉 の アマテラス に、 最後 の 挨拶 を して おこう と 考えた の です。", "A generic man."),
            (113, "彼 は 巨大 な 足音 を 立て ながら、 天上 界 へ と 登って き ました。", "A man in a kimono."),
            (114, "強大 な 破壊 の 力 を 持つ 彼 が 動く と、 凄まじい 現象 が 起き ます。", "An artifact collage."),
            (115, "山々 は 激しく 鳴り動 き、 大地 は 地震 の ように 揺れ ました。", "A diagram."),
            (116, "海 の 水 は 逆巻き、 空 に は 黒い 嵐 の 雲 が 渦巻き ます。", "A shrine gate."),
            (117, "まるで 世界 の 終わり の ような、 恐ろしい 轟音 が 響き渡り ました。", "A black curtain shaking behind a shrine gate."),
            (118, "高天原 に いる 神々 は、 何事 か と 恐怖 に 震え上がり ます。", "Cloned people in robes."),
            (119, "アマテラス も また、 この 異変 に すぐさま 気づき ました。", "A generic woman."),
            (120, "あの 乱暴 な 弟 が、 ついに 私 の 国 を 奪い に きた の だ。", "A generic woman."),
            (121, "農業 と 織物 により、 完璧 な 平和 を 謳歌 して いた 高天原。", "A symbolic collage."),
            (122, "しかし その 平和 な 空 を、 突突 と して 黒い 嵐 の 雲 が 覆い尽くし ます。", "A shrine gate."),
            (123, "海 を 追放 された 破壊 の 神、 スサノオ が 登って きた の です。", "A man in a kimono."),
            (124, "彼 が 一 歩 足 を 踏み出す たびに、 大地 が 轟音 を 立てて 揺れ動き ました。", "A man in a kimono."),
            (125, "山 は 叫び、 川 は 枯れ、 世界中 が 恐怖 に 包まれる 凄まじい パワー。", "A diagram."),
            (126, "これ を 察知 した 太陽 の 女神 アマテラス は、 激しく 警戒 します。", "A generic woman."),
            (127, "弟 は 挨拶 に きた の ではなく、 国 を 奪い に きた の だ と 確信 しました。", "A generic woman."),
            (128, "アマテラス は すぐさま、 戦闘 の ため の 恐ろしい 姿 へ と 変身 します。", "A woman in ornate armor."),
            (129, "髪 を 結び 直し、 男 の ような 勇ましい 髪型 に 変え ました。", "A woman in ornate armor."),
            (130, "腕 や 首 に は 無数 の 勾玉 を 巻き付け、 防御 を 固め ます。", "Glowing green jade beads clinking together as they are tightly wrapped around divine wrists."),
            (131, "背中 に は 千 本 の 矢 を 背負い、 巨大 な 弓 を 握りしめ ました。", "A woman in ornate armor."),
            (132, "足 は 地面 に 深く 埋まる ほど 踏み踏んば り、 弟 を 待ち構え ます。", "A woman in ornate armor."),
            (133, "まるで 鬼神 の ような、 荒々しい 太陽 神 の 戦闘 モード です。", "Amaterasu in ornate armor."),
            (134, "平和 な 農業 の 女神 は、 一瞬 に して 最強 の 武神 と なりました。", "A woman in ornate armor."),
            (135, "宇宙 の 存亡 を 賭けた、 姉 と 弟 の 恐ろしい 激突 の 始まり です。", "Two generic faces."),
            (136, "今回 の ウケモチ の 死 と、 農業 の 始まり の お話 は いかが でした か。", "A generic outro card."),
            (137, "殺された 遺体 から 命 が 生まれる という、 衝撃 的 な 神話 の 構造。", "A generic outro card."),
            (138, "しかし それ は、 命 の 循環 を 描いた 非常に 美しい 哲学 で も あり ました。", "A generic outro card."),
            (139, "そして 現代 の 天皇 陛下 の 儀式 に まで 繋がって いる という 事実。", "A generic outro card."),
            (140, "神話 が ただ の 昔話 で は なく、 生きた 文化 だ と いう こと が 分かり ます。", "A generic outro card."),
            (141, "皆さん は この 食べ物 の 起源 と、 神々 の 喧嘩 について どう 感じ ました か。", "A question-mark artifact card."),
            (142, "是非 コメント 欄 で、 皆さん の 自由 な ご 意見 を お 聞かせ ください。", "A glowing comment interface."),
            (143, "チーム 一同、 楽しく コメント を 読ま せ て 頂いて おります。", "A group of diverse, happy creators reading off a glowing tablet together in a cozy studio."),
            (144, "面白い と 思って 頂け たら、 チャンネル 登録 と 高評価 を お願い します。", "A subscribe button and thumbs-up symbol."),
            (145, "皆さん の 応援 が、 いつも 動画 制作 の 大きな 励み に なって います。", "A glowing studio interface."),
            (146, "宇宙 の 存亡 を 賭けた 姉 と 弟 の 対決 が 始まります。", "Two generic faces."),
            (147, "スサノオ は 邪心 が ない と 強く 訴えます。", "A generic man."),
            (148, "二柱 は 誓約 の 儀式 で 意図 を 証明する こと に 合意しました。", "A generic pair."),
            (149, "武器 と 装飾 品 を 噛み砕いて 吐き出す という、 血 塗られた 誓い です。", "A beautifully crafted iron sword and green jade beads being crushed by massive divine teeth."),
            (150, "次回 は、 天上 界 の 運命 を 決める この 誓約 の 儀式 に 迫り ます！", "A massive, explosive spark of golden creative energy bursting from the clash of two gods."),
        )
        script = {
            "title": "일본사 시크릿 죽은 여신의 시신에서 피어난 생명 EP.07",
            "topic": "죽은 여신의 시신에서 피어난 생명",
            "cuts": [
                {
                    "cut_number": number,
                    "narration": narration,
                    "image_prompt": prompt,
                    "visual_year": "신화시대",
                    "visual_period": "신화 시대",
                    "visual_location": "고천원과 지상",
                }
                for number, narration, prompt in rows
            ],
        }

        applied = apply_script_visual_policy(script)
        by_number = {cut["cut_number"]: cut for cut in applied["cuts"]}
        compiled = {
            number: compile_image_prompt(
                prepare_scene_contract_source(cut["image_prompt"], "mature adult graphic novel"),
                model_id="comfyui-z-image-turbo",
                base_negative="extra fingers, extra arms, extra legs",
            )
            for number, cut in by_number.items()
        }

        for number, result in compiled.items():
            lowered = result.positive.lower()
            if number != 149:
                self.assertNotEqual("object", result.scene_kind, number)
            for forbidden in (
                "copy the registered",
                "artifact display",
                "comment bubble",
                "modern tablet",
                "golden scale",
                "massive divine teeth",
            ):
                self.assertNotIn(forbidden, lowered, number)
        for number in (18, 34, 51, 133, 150):
            self.assertEqual("landscape", compiled[number].scene_kind)
            self.assertIsNone(compiled[number].person_count)
            self.assertNotIn("visual_subject", by_number[number])
        self.assertIn("fully covered earth-tone shroud", compiled[18].positive.lower())
        self.assertIn("animal-only landscape", compiled[26].positive.lower())
        self.assertNotIn("adult figure lock", _z_image_japanese_myth_positive_guard(by_number[26]["image_prompt"]).lower())
        self.assertIn("exactly three living white silkworms", compiled[28].positive.lower())
        self.assertNotIn("weaving shelter", compiled[28].positive.lower())
        self.assertIn("rice, millet and bean shoots", compiled[34].positive.lower())
        self.assertIn("clear shallow water fills the foreground", compiled[51].positive.lower())
        self.assertNotIn("three irregular", compiled[51].positive.lower())
        for number in (40, 52, 54):
            self.assertIn("exactly one visible adult", compiled[number].positive.lower())
            self.assertEqual(1, compiled[number].person_count)
        self.assertIn("ep07 rice-planting hands", compiled[54].positive.lower())
        self.assertIn("exactly two natural adult female hands", compiled[54].positive.lower())
        self.assertIn("plant one young rice shoot", compiled[54].positive.lower())
        cut54_guard = _z_image_japanese_myth_positive_guard(by_number[54]["image_prompt"])
        self.assertIn("hand-action crop lock", cut54_guard.lower())
        self.assertIn("exactly two natural adult female hands", cut54_guard.lower())
        self.assertIn("each with five separated fingers", cut54_guard.lower())
        self.assertIn("t-shaped pullover sleeves", cut54_guard.lower())
        self.assertNotIn("men wear", cut54_guard.lower())
        cut54_styled = _apply_longtube_dark_manhwa_style(
            compiled[54].positive,
            model_id="comfyui-z-image-turbo",
        ).lower()
        self.assertIn("final framing lock: extreme close-up of exactly two planting hands", cut54_styled)
        self.assertIn("no face, torso, pelvis, knees, legs or feet appear anywhere", cut54_styled)
        self.assertNotIn("one coherent adult body and the named natural setting", cut54_styled)
        for number in (47, 48, 49, 50):
            self.assertEqual("landscape", compiled[number].scene_kind)
            self.assertIn("present-day imperial palace rice paddy", compiled[number].positive.lower())
            self.assertNotIn("shroud", compiled[number].positive.lower())
        self.assertIn("present-day shinto harvest-festival grounds", compiled[57].positive.lower())
        self.assertIn("white modern pop-up canopy", compiled[57].positive.lower())
        self.assertIn("newly cut rice sheaves", compiled[58].positive.lower())
        self.assertIn("dark rubber hose", compiled[58].positive.lower())
        self.assertIn("clean metal irrigation outlet", compiled[59].positive.lower())
        self.assertIn("central tokyo ceremonial rice paddy", compiled[59].positive.lower())
        self.assertIn("rectangular glass office tower", compiled[59].positive.lower())
        self.assertNotIn("imperial palace", compiled[59].positive.lower())
        for number in (57, 58, 59):
            self.assertEqual("landscape", compiled[number].scene_kind)
            self.assertNotIn("castle", compiled[number].positive.lower())
            self.assertNotIn("traditional village", compiled[number].positive.lower())
        self.assertIn("wide continuous primordial cultivation field", compiled[62].positive.lower())
        self.assertIn("real winding irrigation channel", compiled[62].positive.lower())
        self.assertNotIn("shroud", compiled[62].positive.lower())
        self.assertIn("ground-level real primordial field", compiled[64].positive.lower())
        self.assertIn("one fallen dry stalk", compiled[64].positive.lower())
        self.assertNotIn("cross-section", compiled[64].positive.lower())
        for number in (62, 64):
            self.assertEqual("landscape", compiled[number].scene_kind)
        self.assertIn("irregular new green grain shoots", compiled[61].positive.lower())
        self.assertIn("naturally mixed mature rice", compiled[63].positive.lower())
        self.assertIn("exactly one natural rice grain germinating", compiled[65].positive.lower())
        for number in (61, 62, 63, 64):
            styled_field = _apply_longtube_dark_manhwa_style(
                compiled[number].positive,
                model_id="comfyui-z-image-turbo",
            ).lower()
            self.assertIn("fertile cultivation manhwa landscape style lock", styled_field)
            self.assertNotIn("named sea, shore", styled_field)
        styled_grain = _apply_longtube_dark_manhwa_style(
            compiled[65].positive,
            model_id="comfyui-z-image-turbo",
        ).lower()
        self.assertIn("single grain germination macro style lock", styled_grain)
        self.assertIn("flat two-dimensional hand-drawn ink manhwa", styled_grain)
        self.assertIn("without a distant horizon or additional seeds", styled_grain)
        self.assertIn("exactly one fully covered earth-tone shroud", compiled[66].positive.lower())
        self.assertEqual("landscape", compiled[66].scene_kind)
        self.assertIn("ep07 face-crop only", compiled[69].positive.lower())
        self.assertEqual("single", compiled[69].scene_kind)
        hainuwele_guard = _z_image_japanese_myth_positive_guard(by_number[69]["image_prompt"]).lower()
        self.assertIn("exactly one mature young southeast asian woman", hainuwele_guard)
        self.assertNotIn("natural east asian facial proportions", hainuwele_guard)
        for number in (66, 67, 74, 75, 76, 77):
            styled_field = _apply_longtube_dark_manhwa_style(
                compiled[number].positive,
                model_id="comfyui-z-image-turbo",
            ).lower()
            self.assertIn("fertile cultivation manhwa landscape style lock", styled_field)
            self.assertNotIn("named sea, shore", styled_field)
        self.assertIn("uninhabited vegetation-only ground-level field", compiled[74].positive.lower())
        self.assertIn("plain brown leaf litter", compiled[74].positive.lower())
        self.assertIn("dark decomposed plant matter", compiled[75].positive.lower())
        self.assertIn("newly opened green sprouts", compiled[75].positive.lower())
        self.assertIn("one continuous real cultivation field", compiled[76].positive.lower())
        self.assertIn("uninhabited vegetation-only wide fertile river field", compiled[77].positive.lower())
        for number in (74, 75, 76, 77):
            styled_cycle = _apply_longtube_dark_manhwa_style(
                compiled[number].positive,
                model_id="comfyui-z-image-turbo",
            ).lower()
            self.assertIn("every visible pixel belongs to natural soil", styled_cycle)
        for number in (68, 70, 71, 72, 73):
            styled_tropical = _apply_longtube_dark_manhwa_style(
                compiled[number].positive,
                model_id="comfyui-z-image-turbo",
            ).lower()
            self.assertIn("tropical food garden manhwa landscape style lock", styled_tropical)
            self.assertIn("completely blank", styled_tropical)
            self.assertIn("no title, caption, label", styled_tropical)
            self.assertNotIn("map", compiled[number].positive.lower())
            self.assertNotIn("artifact", compiled[number].positive.lower())
        modern_styled = _apply_longtube_dark_manhwa_style(
            compiled[47].positive,
            model_id="comfyui-z-image-turbo",
        ).lower()
        self.assertIn("present-day natural manhwa landscape style lock", modern_styled)
        self.assertNotIn("historical manhwa landscape style lock", modern_styled)
        self.assertNotIn("historic castle", modern_styled)
        self.assertEqual("landscape", compiled[84].scene_kind)
        self.assertIn("continuous natural-wood dining tabletop", compiled[84].positive.lower())
        empty_meal_styled = _apply_longtube_dark_manhwa_style(
            compiled[84].positive,
            model_id="comfyui-z-image-turbo",
        ).lower()
        self.assertIn("present-day empty meal room style lock", empty_meal_styled)
        self.assertIn("exactly one simple centered place setting", empty_meal_styled)
        self.assertIn("one rice bowl, one soup bowl and one pair of chopsticks", empty_meal_styled)
        self.assertIn("continuous natural-wood tabletop filling the full 16:9 frame", empty_meal_styled)
        self.assertNotIn("historical illustration", empty_meal_styled)
        for number in (78, 80, 82, 83, 85):
            family_styled = _apply_longtube_dark_manhwa_style(
                compiled[number].positive,
                model_id="comfyui-z-image-turbo",
            ).lower()
            self.assertTrue(family_styled.startswith("flat two-dimensional hand-drawn ink-and-wash mature manhwa illustration"))
            self.assertIn("present-day family meal style lock", family_styled)
            self.assertIn("plain contemporary crewneck shirt", family_styled)
            self.assertIn("exactly three distinct contemporary adult japanese people", family_styled)
            self.assertNotIn("historical illustration", family_styled)
        self.assertNotIn("speech bubble", compiled[83].positive.lower())
        cut87_styled = _apply_longtube_dark_manhwa_style(
            compiled[87].positive,
            model_id="comfyui-z-image-turbo",
        ).lower()
        self.assertIn("mulberry sericulture manhwa landscape style lock", cut87_styled)
        self.assertIn("exact three-silkworm lock", cut87_styled)
        self.assertIn("mulberry foliage and shaded garden soil", cut87_styled)
        self.assertNotIn("named sea, shore", cut87_styled)
        self.assertIn("mulberry-garden lock", _z_image_japanese_myth_positive_guard(by_number[88]["image_prompt"]).lower())
        self.assertIn("ep07 silk-filament facial action", compiled[90].positive.lower())
        self.assertIn("exactly one fine white silk filament", compiled[90].positive.lower())
        self.assertIn("slightly parted lips", compiled[90].positive.lower())
        cut91_styled = _apply_longtube_dark_manhwa_style(
            compiled[91].positive,
            model_id="comfyui-z-image-turbo",
        ).lower()
        self.assertIn("mulberry sericulture manhwa landscape style lock", cut91_styled)
        self.assertIn("exact three-silkworm lock", cut91_styled)
        cut94_styled = _apply_longtube_dark_manhwa_style(
            compiled[94].positive,
            model_id="comfyui-z-image-turbo",
        ).lower()
        self.assertIn("finished garment shelter style lock", cut94_styled)
        self.assertIn("no diagonal line, overlap", cut94_styled)
        self.assertIn("no distant horizon, sea, coast", cut94_styled)
        cut100_styled = _apply_longtube_dark_manhwa_style(
            compiled[100].positive,
            model_id="comfyui-z-image-turbo",
        ).lower()
        self.assertIn("rice mulberry legacy landscape style lock", cut100_styled)
        self.assertIn("no person, animal, silkworm, cocoon, sea, coast", cut100_styled)
        self.assertIn("vertical loom", compiled[92].positive.lower())
        self.assertIn("weaving-shelter lock", _z_image_japanese_myth_positive_guard(by_number[92]["image_prompt"]).lower())
        self.assertIn("ep07 attire topology", compiled[93].positive.lower())
        self.assertEqual(3, compiled[93].person_count)
        self.assertNotIn("archaic woven robes", compiled[93].positive.lower())
        self.assertIn("finished plain ivory short-sleeve crewneck shirt", compiled[94].positive.lower())
        for number in (96, 97, 99):
            sericulture_styled = _apply_longtube_dark_manhwa_style(
                compiled[number].positive,
                model_id="comfyui-z-image-turbo",
            ).lower()
            self.assertTrue(sericulture_styled.startswith("flat two-dimensional hand-drawn ink-and-wash mature manhwa illustration"))
            self.assertIn("present-day sericulture figure style lock", sericulture_styled)
            self.assertIn("plain light-grey collarless modern work jacket", sericulture_styled)
            self.assertNotIn("historical illustration", sericulture_styled)
        ceremony_styled = _apply_longtube_dark_manhwa_style(
            compiled[98].positive,
            model_id="comfyui-z-image-turbo",
        ).lower()
        self.assertIn("present-day silk ceremony figure style lock", ceremony_styled)
        self.assertIn("plain charcoal contemporary business suit", ceremony_styled)
        self.assertNotIn("historical illustration", ceremony_styled)
        self.assertNotIn("building", compiled[117].positive.lower())
        self.assertNotIn("structure", compiled[117].positive.lower())
        self.assertIn("one living silkworm tray", compiled[96].positive.lower())
        self.assertNotIn("scene-named adult woman", compiled[96].positive.lower())
        self.assertEqual("landscape", compiled[101].scene_kind)
        self.assertIn("exactly three separated vertical looms", compiled[101].positive.lower())
        self.assertNotIn("silkworm", compiled[101].positive.lower())
        cut101_styled = _apply_longtube_dark_manhwa_style(
            compiled[101].positive,
            model_id="comfyui-z-image-turbo",
        ).lower()
        self.assertIn("sacred weaving hall landscape style lock", cut101_styled)
        self.assertIn("no person, animal, silkworm, cocoon, water, sea, coast", cut101_styled)
        self.assertEqual(3, compiled[102].person_count)
        self.assertIn("ep07 attire topology", compiled[102].positive.lower())
        self.assertIn("three-age identity lock", _z_image_japanese_myth_positive_guard(by_number[102]["image_prompt"]).lower())
        self.assertEqual(1, compiled[103].person_count)
        self.assertIn("ep07 attire topology", compiled[103].positive.lower())
        self.assertIn("operates exactly one vertical loom", compiled[103].positive.lower())
        for number in (104,):
            legacy_styled = _apply_longtube_dark_manhwa_style(
                compiled[number].positive,
                model_id="comfyui-z-image-turbo",
            ).lower()
            self.assertIn("rice mulberry legacy landscape style lock", legacy_styled)
            self.assertIn("no person, animal, silkworm, cocoon, sea, coast", legacy_styled)
            self.assertIn("no additional building, house, roof, road, utility pole or wire", legacy_styled)
        cut105_styled = _apply_longtube_dark_manhwa_style(
            compiled[105].positive,
            model_id="comfyui-z-image-turbo",
        ).lower()
        self.assertIn("fertile cultivation manhwa landscape style lock", cut105_styled)
        cut106_styled = _apply_longtube_dark_manhwa_style(
            compiled[106].positive,
            model_id="comfyui-z-image-turbo",
        ).lower()
        self.assertIn("fertile cultivation manhwa landscape style lock", cut106_styled)
        self.assertNotIn("building", compiled[106].positive.lower())
        self.assertNotIn("structure", compiled[108].positive.lower())
        self.assertNotIn("sea", compiled[108].positive.lower())
        self.assertIn("head-and-shoulders portrait", compiled[109].positive.lower())
        self.assertIn("wild shoulder-length black hair", compiled[109].positive.lower())
        self.assertIn("smooth beardless jaw", compiled[109].positive.lower())
        self.assertIn("ep07 attire topology", compiled[110].positive.lower())
        self.assertNotIn("earth-blue wrap", compiled[110].positive.lower())
        self.assertIn("three-quarter rear view", compiled[110].positive.lower())
        self.assertIn("thick shoulder-length black hair", compiled[110].positive.lower())
        self.assertIn("barefoot", compiled[110].positive.lower())
        for number in (111, 112):
            self.assertEqual(1, compiled[number].person_count)
            self.assertIn("head-and-shoulders portrait of exactly one", compiled[number].positive.lower())
            self.assertIn("smooth beardless jaw", compiled[number].positive.lower())
            self.assertIn("wild shoulder-length black hair", compiled[number].positive.lower())
        self.assertIn("ep07 attire topology", compiled[113].positive.lower())
        self.assertIn("thick shoulder-length black hair", compiled[113].positive.lower())
        self.assertNotIn("earth-blue wrap", compiled[113].positive.lower())
        for number in (114, 115, 116, 117):
            self.assertEqual("landscape", compiled[number].scene_kind)
            self.assertIsNone(compiled[number].person_count)
            self.assertNotIn("artifact display", compiled[number].positive.lower())
        self.assertEqual(3, compiled[118].person_count)
        self.assertIn("ep07 attire topology", compiled[118].positive.lower())
        self.assertIn("exactly three visibly different", compiled[118].positive.lower())
        self.assertIn("recoiling open-mouthed and wide-eyed", compiled[118].positive.lower())
        self.assertIn("waist and legs remain outside the crop", compiled[118].positive.lower())
        self.assertIn("ep07 face-crop only", compiled[119].positive.lower())
        self.assertIn("ep07 face-crop only", compiled[120].positive.lower())
        self.assertEqual("landscape", compiled[121].scene_kind)
        self.assertIn(
            "rice mulberry legacy landscape style lock",
            _apply_longtube_dark_manhwa_style(
                compiled[121].positive,
                model_id="comfyui-z-image-turbo",
            ).lower(),
        )
        for number in (122, 125):
            self.assertEqual("landscape", compiled[number].scene_kind)
            self.assertIsNone(compiled[number].person_count)
        self.assertNotIn("sea", compiled[122].positive.lower())
        self.assertIn("dry cracked bed", compiled[125].positive.lower())
        self.assertIn("ep07 attire topology", compiled[123].positive.lower())
        self.assertRegex(compiled[123].positive.lower(), r"hair\s+extend(?:s|ing)\s+below\s+both\s+shoulders")
        self.assertNotIn("earth-blue wrap", compiled[123].positive.lower())
        self.assertIn("ep07 foot-impact crop", compiled[124].positive.lower())
        self.assertIn("clean five-toed foot on dry brown rock", compiled[124].positive.lower())
        self.assertIn("foot skin smooth and unmarked", compiled[124].positive.lower())
        cut124_guard = _z_image_japanese_myth_positive_guard(by_number[124]["image_prompt"]).lower()
        self.assertIn("foot-impact anatomy lock", cut124_guard)
        self.assertIn("ep07 attire topology", compiled[128].positive.lower())
        self.assertNotIn("ivory wrap", compiled[128].positive.lower())
        self.assertNotIn("ivory wrap", compiled[130].positive.lower())
        self.assertIn("two green comma-bead strands both visible", compiled[130].positive.lower())
        self.assertIn("one per upper arm", compiled[130].positive.lower())
        self.assertIn("one green comma-bead necklace", compiled[130].positive.lower())
        cut125_guard = _z_image_japanese_myth_positive_guard(by_number[125]["image_prompt"]).lower()
        self.assertIn("completely dry former-river lock", cut125_guard)
        cut130_guard = _z_image_japanese_myth_positive_guard(by_number[130]["image_prompt"]).lower()
        self.assertIn("magatama torso lock", cut130_guard)
        self.assertIn("hard gold sun shaft", compiled[133].positive.lower())
        for number in (131, 132, 134):
            self.assertIn("ep07 dry-takamagahara figure", compiled[number].positive.lower())
            self.assertIn("dry takamagahara lock", _z_image_japanese_myth_positive_guard(by_number[number]["image_prompt"]).lower())
        self.assertIn("ep07 dry-takamagahara landscape", compiled[133].positive.lower())
        self.assertIn("becomes armed defender", compiled[134].positive.lower())
        self.assertNotIn("archaic wrap", compiled[134].positive.lower())
        self.assertIn("clean-shaven upper lip", compiled[135].positive.lower())
        self.assertIn("ep07 strict-profile faces", compiled[135].positive.lower())
        self.assertIn("extreme inward-facing two-profile confrontation", compiled[135].positive.lower())
        self.assertIn("composition=amaterasu_susanoo_face_only_confrontation", compiled[135].diagnostics)
        cut135_guard = _z_image_japanese_myth_positive_guard(by_number[135]["image_prompt"]).lower()
        self.assertIn("clean-shaven male identity lock", cut135_guard)
        self.assertIn("distinct sister-brother identity lock", cut135_guard)
        self.assertIn("left profile is one adult east asian woman", cut135_guard)
        dry133_styled = _apply_longtube_dark_manhwa_style(compiled[133].positive, model_id="comfyui-z-image-turbo").lower()
        self.assertIn("dry takamagahara landscape style lock", dry133_styled)
        self.assertIn("ep07 covered-mound field", compiled[136].positive.lower())
        self.assertIn("living grain shoots", compiled[137].positive.lower())
        self.assertIn("ep07 covered-mound field", compiled[137].positive.lower())
        for number in (136, 137):
            covered_mound_styled = _apply_longtube_dark_manhwa_style(
                compiled[number].positive,
                model_id="comfyui-z-image-turbo",
            ).lower()
            self.assertIn("covered mound fertile field style lock", covered_mound_styled)
            self.assertIn("fully sealed beneath one continuous", covered_mound_styled)
        self.assertIn("one continuous soil-and-field view", compiled[138].positive.lower())
        self.assertIn("present-day imperial palace ceremonial rice paddy", compiled[139].positive.lower())
        self.assertIn("ep07 present-day living-culture landscape", compiled[140].positive.lower())
        self.assertIn("flat two-dimensional mature dark manhwa ink-and-wash illustration", compiled[140].positive.lower())
        living_culture_styled = _apply_longtube_dark_manhwa_style(
            compiled[140].positive,
            model_id="comfyui-z-image-turbo",
        ).lower()
        self.assertIn("present-day living culture landscape style lock", living_culture_styled)
        self.assertIn("small white rectangular flat-roof sericulture workroom", living_culture_styled)
        self.assertIn("flat two-dimensional mature dark manhwa ink-and-wash illustration", compiled[141].positive.lower())
        cut141_styled = _apply_longtube_dark_manhwa_style(
            compiled[141].positive,
            model_id="comfyui-z-image-turbo",
        ).lower()
        self.assertIn("fertile cultivation manhwa landscape style lock", cut141_styled)
        for number in (142, 143, 144, 145):
            self.assertIn("ep07 present-day creator group", compiled[number].positive.lower())
            self.assertIn("flat 2d ink manhwa chest portrait", compiled[number].positive.lower())
            self.assertIn("woman, man, woman, man", compiled[number].positive.lower())
            self.assertIn("plain modern crewneck shirts", compiled[number].positive.lower())
            creator_styled = _apply_longtube_dark_manhwa_style(
                compiled[number].positive,
                model_id="comfyui-z-image-turbo",
            ).lower()
            self.assertIn("present-day creator group style lock", creator_styled)
            self.assertIn("exactly four distinct adult japanese creators", creator_styled)
            self.assertNotIn("historical illustration", creator_styled)
        self.assertIn("ep07 strict-profile faces", compiled[146].positive.lower())
        self.assertIn("ep07 eyes-only crop", compiled[147].positive.lower())
        self.assertIn("no evil intent", compiled[147].positive.lower())
        self.assertIn("nose, mouth, upper lip, cheeks", compiled[147].positive.lower())
        cut147_styled = _apply_longtube_dark_manhwa_style(
            compiled[147].positive,
            model_id="comfyui-z-image-turbo",
        ).lower()
        self.assertIn("eyes-only manhwa style lock", cut147_styled)
        self.assertIn("exactly one enormous", cut147_styled)
        self.assertIn("second eye, cheeks, mouth", cut147_styled)
        self.assertIn("outside every image edge", cut147_styled)
        self.assertIn("ep07 attire topology", compiled[148].positive.lower())
        self.assertIn("left adult woman amaterasu", compiled[148].positive.lower())
        self.assertIn("long straight skirt", compiled[148].positive.lower())
        self.assertIn("right adult man susanoo", compiled[148].positive.lower())
        self.assertIn("loose ankle trousers", compiled[148].positive.lower())
        self.assertIn("ep07 oath-items macro", compiled[149].positive.lower())
        self.assertTrue(
            _should_use_ch3_ep7_oath_items_layout(by_number[149]["image_prompt"])
        )
        self.assertEqual(
            "comfyui-z-image-turbo",
            expected_effective_image_model_id(
                "comfyui-z-image-turbo",
                by_number[149]["image_prompt"],
            ),
        )
        self.assertIn("dull-bronze shard", compiled[149].positive.lower())
        self.assertEqual("object", compiled[149].scene_kind)
        self.assertIsNone(compiled[149].person_count)
        cut149_styled = _apply_longtube_dark_manhwa_style(
            compiled[149].positive,
            model_id="comfyui-z-image-turbo",
        ).lower()
        self.assertIn("oath items object style lock", cut149_styled)
        self.assertIn("exactly two separated objects", cut149_styled)
        self.assertIn("green crescent-comma ornament stone", cut149_styled)
        self.assertIn("no handle", cut149_styled)
        self.assertIn("no person, face, hand, blood", cut149_styled)
        self.assertIn("ep07 dry-takamagahara landscape", compiled[150].positive.lower())
        self.assertIn("natural gold sunlight", compiled[150].positive.lower())
        cut150_styled = _apply_longtube_dark_manhwa_style(
            compiled[150].positive,
            model_id="comfyui-z-image-turbo",
        ).lower()
        self.assertIn("dry takamagahara landscape style lock", cut150_styled)
        for number in (3, 4, 6, 14, 16):
            subject = by_number[number].get("visual_subject", "").lower()
            self.assertNotIn("wrap", subject)
            self.assertNotIn("robe", subject)
        self.assertIn("composition=japanese_myth_two_face_macro_no_garment", compiled[3].diagnostics)
        self.assertIn("composition=japanese_myth_facial_macro_no_garment", compiled[4].diagnostics)
        self.assertIn("ep07 attire topology", compiled[17].positive.lower())
        self.assertNotIn("ep07 face-crop only", compiled[17].positive.lower())
        self.assertIn("exactly one adult messenger man", compiled[17].positive.lower())
        self.assertNotIn("adult east asian woman", compiled[17].positive.lower())
        self.assertIn("uke mochi's dread opposed by tsukuyomi's cold anger", compiled[3].positive.lower())
        self.assertIn("face scaled taller than the full frame", compiled[4].positive.lower())
        face_guard = _z_image_japanese_myth_positive_guard(by_number[3]["image_prompt"])
        self.assertIn("face-crop background lock", face_guard.lower())
        self.assertNotIn("open sky", face_guard.lower())
        self.assertIn("adult face lock", face_guard.lower())
        self.assertIn("chin, jaw and natural hair continue through the entire lower image edge", face_guard.lower())
        self.assertNotIn("garment", face_guard.lower())
        self.assertNotIn("collar", face_guard.lower())
        self.assertNotIn("wrap robe", face_guard.lower())
        styled_face = _apply_longtube_dark_manhwa_style(
            compiled[4].positive,
            model_id="comfyui-z-image-turbo",
        ).lower()
        self.assertNotIn("tsukuyomi", styled_face)
        self.assertNotIn("japanese mythic creation era", styled_face)
        self.assertNotIn("kojiki", styled_face)
        self.assertNotIn("garment", styled_face)
        self.assertIn("mature adult east asian man", styled_face)
        self.assertIn("flat two-dimensional hand-drawn ink manhwa", styled_face)
        guard = _z_image_japanese_myth_positive_guard(by_number[16]["image_prompt"])
        self.assertIn("t-shaped pullover shirt", guard.lower())
        self.assertIn("continuous uninterrupted rear panel", guard.lower())
        self.assertNotIn("circular neck hole", guard.lower())
        self.assertNotIn("wrap robe", guard.lower())
        styled_figure = _apply_longtube_dark_manhwa_style(
            compiled[16].positive,
            model_id="comfyui-z-image-turbo",
        ).lower()
        self.assertNotIn("kojiki", styled_figure)
        self.assertNotIn("pre-state japanese", styled_figure)
        self.assertIn("t-shaped pullover shirt", styled_figure)
        self.assertNotIn("tunic", styled_figure)
        self.assertNotIn("belt", styled_figure)
        self.assertIn("flat two-dimensional hand-drawn ink manhwa adult figure", styled_figure)
        cut17_guard = _z_image_japanese_myth_positive_guard(by_number[17]["image_prompt"])
        self.assertIn("exactly one visible adult east asian messenger man", cut17_guard.lower())
        self.assertNotIn("women wear", cut17_guard.lower())

    def test_named_myth_deity_is_not_replaced_by_generic_entrance(self):
        script = {
            "title": "세 귀공자의 탄생",
            "cuts": [
                {
                    "cut_number": 55,
                    "narration": "闇 を 打ち払う その 光 の 中 から、 美しい 女神 が 姿 を 現し ます。",
                    "image_prompt": "A graceful feminine silhouette forming within golden light.",
                    "visual_year": "신화시대",
                    "visual_period": "신화 시대",
                    "visual_location": "미소기 의식",
                }
            ],
        }
        applied = apply_script_visual_policy(script)
        prompt = applied["cuts"][0]["image_prompt"]
        self.assertIn("adult female Amaterasu", prompt)
        self.assertNotIn("scene-named adult woman", prompt)

    def test_mulberry_landscape_style_uses_concrete_action_not_episode_context(self):
        rice_prompt = (
            "Global visual world: Japanese mythic rice agriculture, mulberry leaves, silkworms, and cocoons. "
            "Visible action: Landscape-only wide view of green rice shoots under split light and shadow, "
            "a dark reed hall silhouette behind the field, no people. "
            "Primary subject: green rice shoots. Era/period: Japanese mythic creation era."
        )
        rice_styled = _apply_longtube_dark_manhwa_style(
            rice_prompt,
            model_id="comfyui-z-image-turbo",
        )
        self.assertNotIn(
            "MULBERRY SERICULTURE MANHWA LANDSCAPE STYLE LOCK",
            rice_styled,
        )
        self.assertIn("PRIMORDIAL NATURAL MANHWA LANDSCAPE STYLE LOCK", rice_styled)

        silkworm_prompt = (
            "Global visual world: Japanese mythic rice agriculture and sericulture. "
            "Visible action: Landscape-only close garden view of three living silkworms on fresh mulberry leaves. "
            "Primary subject: three silkworms. Era/period: Japanese mythic creation era."
        )
        silkworm_styled = _apply_longtube_dark_manhwa_style(
            silkworm_prompt,
            model_id="comfyui-z-image-turbo",
        )
        self.assertIn(
            "MULBERRY SERICULTURE MANHWA LANDSCAPE STYLE LOCK",
            silkworm_styled,
        )

        rice_seed_prompt = (
            "Global visual world: Japanese mythic rice agriculture, mulberry leaves, silkworms, and cocoons. "
            "Visible action: Object-only extreme macro of exactly one raw unhulled rice seed filling sixty "
            "percent of the frame width on rough wooden granary planks. "
            "Primary subject: exactly one rice seed. Era/period: Japanese mythic creation era."
        )
        rice_seed_styled = _apply_longtube_dark_manhwa_style(
            rice_seed_prompt,
            model_id="comfyui-z-image-turbo",
        )
        self.assertIn(
            "SINGLE RAW RICE SEED MACRO STYLE LOCK",
            rice_seed_styled,
        )
        self.assertIn("No second seed, grain pile, bowl, tray, basket", rice_seed_styled)

        granary_prompt = (
            "Global visual world: Japanese mythic rice agriculture, mulberry leaves, silkworms, and cocoons. "
            "Visible action: Landscape-only dramatic low exterior view of exactly one raised-floor thatched "
            "granary standing on tall plain timber posts above wind-bent night grass. "
            "Primary subject: one raised-floor granary. Exact place: raised-floor granary exterior. "
            "Era/period: Japanese mythic creation era."
        )
        granary_styled = _apply_longtube_dark_manhwa_style(
            granary_prompt,
            model_id="comfyui-z-image-turbo",
        )
        self.assertIn(
            "RAISED-FLOOR GRANARY EXTERIOR STYLE LOCK",
            granary_styled,
        )
        self.assertNotIn("CLOSED OBJECT-INTERIOR LOCK", granary_styled)
        self.assertNotIn("MULBERRY SERICULTURE MANHWA LANDSCAPE STYLE LOCK", granary_styled)

    def test_generic_ep7_roles_replace_stale_deity_identity_without_becoming_nonhuman(self):
        stale_uke = (
            "exactly one adult female Uke Mochi, mature East Asian face, long loose dark hair, "
            "bare forehead, plain earth-tone wrap"
        )
        script = {
            "title": "ころされた女神から、稲と蚕が生まれた EP.07",
            "description": "ウケモチの死体から米と蚕が生まれる神話。",
            "cuts": [
                {
                    "cut_number": 91,
                    "narration": "食べることは、命を受け取ることでもあります",
                    "visual_subject": stale_uke,
                    "visual_scene": (
                        "medium-close of a villager staring solemnly at a clay rice bowl on reed mats, "
                        "hearth light on tired face, exactly zero visible hands"
                    ),
                    "image_prompt": f"Main subject: {stale_uke}; Scene: worried villager",
                },
                {
                    "cut_number": 101,
                    "narration": "蚕の世話は、静かで細かな仕事です",
                    "visual_scene": (
                        "medium-close of a caretaker anxiously checking silkworm trays by firelight, "
                        "simple hemp robe, exactly zero visible hands"
                    ),
                    "image_prompt": "Scene: caretaker checking silkworm trays",
                },
                {
                    "cut_number": 105,
                    "narration": "日本の手仕事は、こうした持続を大切にしました",
                    "visual_subject": stale_uke,
                    "visual_scene": (
                        "medium-wide view of two adult caretakers moving trays in a simple craft room, "
                        "focused faces, plain robes, exactly zero visible hands"
                    ),
                    "image_prompt": f"Main subject: {stale_uke}; Scene: two adult caretakers",
                },
                {
                    "cut_number": 106,
                    "narration": "けれど、衣を残して、ウケモチ本人は戻りません",
                    "visual_scene": (
                        "wide interior of an empty reed sleeping space, white robe folded where Ukemochi "
                        "once lay, faint rice shoots near the doorway, no visible hands"
                    ),
                    "image_prompt": "Scene: body-shaped white robe where Ukemochi once lay",
                },
                {
                    "cut_number": 110,
                    "narration": "その重さが、語り継がれる理由になります",
                    "visual_scene": (
                        "medium-wide hearth scene with storyteller centered, two listeners leaning in from "
                        "sides, grain basket between them, exactly zero visible hands"
                    ),
                    "image_prompt": "Scene: storyteller and two listeners",
                },
                {
                    "cut_number": 111,
                    "narration": "この話は、神話として伝えられたものです",
                    "visual_subject": stale_uke,
                    "visual_scene": (
                        "close-up of an elder storyteller speaking beside a clay lamp, lined face solemn, "
                        "plain robe, exactly zero visible hands"
                    ),
                    "image_prompt": f"Main subject: {stale_uke}; Scene: elder storyteller",
                },
                {
                    "cut_number": 113,
                    "narration": "記録は、不思議なまま出来事を残します",
                    "visual_subject": stale_uke,
                    "visual_scene": (
                        "medium-close of a Nara-period scribe bending over a blank wooden writing board, "
                        "face intent, court robe plain, exactly zero visible hands"
                    ),
                    "image_prompt": f"Main subject: {stale_uke}; Scene: Nara-period scribe",
                },
                {
                    "cut_number": 114,
                    "narration": "だから、史実の殺人としては扱いません",
                    "visual_scene": (
                        "medium view of storyteller at left and listener at right separated by a hearth flame, "
                        "grain basket between them, exactly zero visible hands"
                    ),
                    "image_prompt": "Scene: storyteller at left and listener at right",
                },
                {
                    "cut_number": 118,
                    "narration": "人物を入れ替えると、話の重さが変わります",
                    "visual_subject": (
                        "exactly two adult Japanese deities: adult male Tsukuyomi; adult female Uke Mochi"
                    ),
                    "visual_scene": (
                        "medium-close of storyteller sternly dividing two grain baskets with body posture, "
                        "plain robe, exactly zero visible hands"
                    ),
                    "image_prompt": "Main subject: Tsukuyomi and Uke Mochi; Scene: storyteller with baskets",
                },
            ],
        }
        applied = apply_script_visual_policy(script)
        by_number = {cut["cut_number"]: cut for cut in applied["cuts"]}

        self.assertIn("agrarian villager", by_number[91]["visual_subject"])
        self.assertNotIn("Uke Mochi", by_number[91]["image_prompt"])
        self.assertIn("exactly one adult East Asian sericulture caretaker", by_number[101]["visual_subject"])
        self.assertNotIn("no people", by_number[101]["visual_scene"])
        self.assertIn("exactly two adult East Asian sericulture caretakers", by_number[105]["visual_subject"])
        self.assertNotIn("scene-named adult woman", by_number[105]["image_prompt"])
        self.assertTrue(by_number[106]["visual_scene"].startswith("Landscape-only"))
        self.assertIn("compact flat rectangular stack", by_number[106]["visual_scene"])
        self.assertNotIn("visual_subject", by_number[106])
        self.assertIn("exactly three adult East Asian villagers", by_number[110]["visual_subject"])
        self.assertNotIn("no people", by_number[110]["visual_scene"])
        self.assertIn("elderly adult East Asian male storyteller", by_number[111]["visual_subject"])
        self.assertIn("adult East Asian Nara-period scribe", by_number[113]["visual_subject"])
        self.assertNotIn("Uke Mochi", by_number[113]["image_prompt"])
        self.assertIn("exactly two adult East Asian villagers", by_number[114]["visual_subject"])
        self.assertIn("elderly adult East Asian male storyteller", by_number[118]["visual_subject"])
        self.assertNotIn("Tsukuyomi", by_number[118]["image_prompt"])
        self.assertNotIn("Uke Mochi", by_number[118]["image_prompt"])

    def test_ep7_storage_memory_objects_stay_closed_blank_and_person_free(self):
        script = {
            "title": "ころされた女神から、稲と蚕が生まれた EP.07",
            "description": "ウケモチの死体から米と蚕が生まれる神話。",
            "cuts": [
                {
                    "cut_number": 92,
                    "narration": "この神話は、その重さを忘れさせません",
                    "visual_scene": (
                        "close-up of a rice bowl casting a long shadow shaped by a folded robe behind it, "
                        "clay hearth glow trembling, no people, no visible hands"
                    ),
                    "image_prompt": "Scene: standing person behind a rice bowl",
                },
                {
                    "cut_number": 97,
                    "narration": "籠の底に残した種は、未来の米そのものでした",
                    "visual_scene": (
                        "medium close view of sealed clay jars beside woven seed baskets inside a raised-floor "
                        "granary, slatted light striping the containers, no people, no visible hands"
                    ),
                    "image_prompt": "Scene: jars and baskets beside an open sea",
                },
                {
                    "cut_number": 98,
                    "narration": "ここに、倉で種籠を守る農のきびしさが見えます",
                    "visual_subject": "exactly one adult female Uke Mochi",
                    "visual_scene": (
                        "medium view of a worried villager at a granary doorway, seed baskets behind, "
                        "gaunt face lit by cold dawn, exactly zero visible hands"
                    ),
                    "image_prompt": "Main subject: Uke Mochi; Scene: worried villager with a second woman",
                },
                {
                    "cut_number": 99,
                    "narration": "神話の種は、高床の倉で守られていきます",
                    "visual_scene": (
                        "dramatic low view of a raised-floor thatched granary, seed baskets visible through "
                        "open slats, night wind bending grass below, no people, no visible hands"
                    ),
                    "image_prompt": "Scene: open seaside shelter",
                },
                {
                    "cut_number": 109,
                    "narration": "豊かさの下には、取り消せない犠牲があります",
                    "visual_scene": (
                        "close-up of a plain unmarked stone at the edge of a lush paddy, rice heads leaning "
                        "over it, no people, no visible hands"
                    ),
                    "image_prompt": "Scene: inscribed upright stone monument",
                },
                {
                    "cut_number": 117,
                    "narration": "ただ今回は、ウケモチとツクヨミの筋です",
                    "visual_scene": (
                        "close-up of a folded white robe opposite a plain blade on reed mats, rice grains "
                        "scattered in between, no people, no visible hands"
                    ),
                    "image_prompt": "Scene: body-shaped robe beside a blade",
                },
                {
                    "cut_number": 123,
                    "narration": "神話は、その流れを女神のからだで語りました",
                    "visual_scene": (
                        "close-up of a white robe edge laid beside seeds and new sprouts in wet soil, "
                        "plain stone behind, no people, no visible hands"
                    ),
                    "image_prompt": "Scene: person in a white robe beside sprouts",
                },
                {
                    "cut_number": 127,
                    "narration": "ウケモチの話は、米や繭でそれを強く見せます",
                    "visual_scene": (
                        "close-up of white hemp robe folds surrounded by rice grains, beans, and cocoons, "
                        "one clay lamp throwing severe shadows, no people, no visible hands"
                    ),
                    "image_prompt": "Scene: body-shaped robe among grains",
                },
                {
                    "cut_number": 137,
                    "narration": "豊かさは、犠牲をなかったことにしません",
                    "visual_scene": (
                        "wide view of full rice heads swaying before a dark empty reed hall, "
                        "no figures, no markings, no visible hands"
                    ),
                    "image_prompt": "Scene: full rice heads and an empty hall",
                },
                {
                    "cut_number": 138,
                    "narration": "むしろ、その上に毎日の米が立っています",
                    "visual_scene": (
                        "low close-up of a rice bowl on a reed mat, dark shadow of a folded robe "
                        "stretching under it, no people, no visible hands"
                    ),
                    "image_prompt": "Scene: standing person casting a shadow over a bowl",
                },
                {
                    "cut_number": 139,
                    "narration": "蚕の繭も、同じ死の記憶をまといます",
                    "visual_scene": (
                        "close-up of pale cocoons clustered beside the shadow of a white robe, "
                        "mulberry leaves darkened around them, no people, no visible hands"
                    ),
                    "image_prompt": "Scene: person in a white robe beside cocoons",
                },
                {
                    "cut_number": 140,
                    "narration": "ウケモチの死は、食と衣の起源として残りました",
                    "visual_scene": (
                        "dramatic overhead view of rice grains and cocoons placed on a plain wooden platform, "
                        "folded white cloth at the edge, no people, no visible hands"
                    ),
                    "image_prompt": "Scene: landscape with giant silkworms",
                },
                {
                    "cut_number": 121,
                    "narration": "土の中で米の種が根を伸ばします",
                    "visual_scene": (
                        "Object-only macro cutaway-like view of a rice seed partly buried in dark wet soil, "
                        "tiny root pushing downward, surface water above, no people, no visible hands"
                    ),
                    "image_prompt": "Scene: a farmer planting a mature rice plant",
                },
                {
                    "cut_number": 122,
                    "narration": "古い殻から新しい芽が出ます",
                    "visual_scene": (
                        "Object-only close-up of a bright rice sprout breaking through dark mud, old husk "
                        "fragments clinging to its base, water shining around it, no visible hands, no people"
                    ),
                    "image_prompt": "Scene: mature rice plants beside a village",
                },
            ],
        }
        applied = apply_script_visual_policy(script)
        by_number = {cut["cut_number"]: cut for cut in applied["cuts"]}

        self.assertIn("compact flat rectangular stack", by_number[92]["visual_scene"])
        self.assertNotIn("visual_subject", by_number[92])
        self.assertTrue(by_number[97]["visual_scene"].startswith("Object-only closed interior"))
        self.assertIn("no sea, no shore", by_number[97]["visual_scene"])
        self.assertIn("exactly one worried adult East Asian agrarian villager", by_number[98]["visual_scene"])
        self.assertIn("agrarian villager", by_number[98]["visual_subject"])
        self.assertNotIn("Uke Mochi", by_number[98]["image_prompt"])
        self.assertTrue(by_number[99]["visual_scene"].startswith("Landscape-only"))
        self.assertIn("raised-floor thatched granary", by_number[99]["visual_scene"])
        self.assertIn("no sea, no shore, no coast", by_number[99]["visual_scene"])
        self.assertIn("low irregular natural fieldstone lying flat", by_number[109]["visual_scene"])
        self.assertIn("no carving, no inscription, no mark, no text", by_number[109]["visual_scene"])
        self.assertIn("compact flat rectangular stack at left", by_number[117]["visual_scene"])
        self.assertIn("no body-shaped garment", by_number[117]["visual_scene"])
        self.assertIn("narrow flat strip of empty white woven cloth", by_number[123]["visual_scene"])
        self.assertIn("compact flat rectangular stack at center", by_number[127]["visual_scene"])
        self.assertTrue(by_number[137]["visual_scene"].startswith("Landscape-only"))
        self.assertIn("no interior room", by_number[137]["visual_scene"])
        self.assertIn("no silkworm, no cocoon", by_number[137]["visual_scene"])
        self.assertIn("compact flat rectangular stack of folded white cloth", by_number[138]["visual_scene"])
        self.assertIn("compact flat rectangular stack", by_number[139]["visual_scene"])
        self.assertTrue(by_number[140]["visual_scene"].startswith("Object-only"))
        self.assertIn("twenty thumb-sized smooth ivory oval silk cocoons", by_number[140]["visual_scene"])
        self.assertIn("no potato, no tuber, no fruit, no stone", by_number[140]["visual_scene"])
        self.assertIn("extreme macro soil cross-section", by_number[121]["visual_scene"])
        self.assertIn("no mature rice stalk", by_number[121]["visual_scene"])
        self.assertIn("exactly one tiny two-leaf fresh green sprout", by_number[122]["visual_scene"])
        self.assertIn("no mature rice stalk", by_number[122]["visual_scene"])

        for number in (121, 122, 140):
            compiled = compile_image_prompt(
                prepare_scene_contract_source(
                    by_number[number]["image_prompt"],
                    "mature adult graphic novel",
                ),
                model_id="comfyui-z-image-turbo",
                base_negative="extra fingers, extra arms, extra legs",
            )
            styled = _apply_longtube_dark_manhwa_style(
                compiled.positive,
                model_id="comfyui-z-image-turbo",
            ).lower()
            if number in (121, 122):
                self.assertIn("single grain germination macro style lock", styled)
                self.assertIn("no mature rice plant", styled)
                self.assertIn("no mature rice stalk", by_number[number]["image_prompt"].lower())
            else:
                self.assertIn("rice cocoon cloth platform style lock", styled)
                self.assertIn("no potato, tuber", styled)

    def test_resume_preserves_committed_policy_mismatch_without_global_force_flag(self):
        self.assertFalse(
            _resume_prompt_mismatch_requires_regeneration(
                "sidecar_final_prompt_mismatch",
                False,
            )
        )
        self.assertTrue(
            _resume_prompt_mismatch_requires_regeneration(
                "missing_prompt_sidecar",
                False,
            )
        )
        self.assertTrue(
            _resume_prompt_mismatch_requires_regeneration(
                "sidecar_effective_model_mismatch",
                False,
            )
        )
        self.assertFalse(
            _resume_prompt_mismatch_requires_regeneration(
                "prompt_token_mismatch:0.10",
                False,
            )
        )


if __name__ == "__main__":
    unittest.main()
