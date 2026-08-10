"""Narration-locked scenes for CH3 EP11, the Amano-Iwato episode."""

from __future__ import annotations


MYTH_MATERIAL = (
    "plain closed-front ivory, charcoal, and earth-tone plant-fiber tunics, natural black hair, "
    "rough stone, bare earth, unpainted timber, braided plant fiber, aged bronze, green jade, "
    "cold blue darkness, warm firelight, and returning golden daylight only"
)
OBJECT_MATERIAL = (
    "rough natural stone, bare earth, unpainted timber, braided plant fiber, aged bronze, "
    "green jade, cold blue darkness, warm firelight, and returning golden daylight only"
)


CH3_EP11_AMANOIWATO_NARRATION_SCENE_LOCKS: dict[str, tuple[str, str, str]] = {}


def _add(
    subject: str,
    action: str,
    material: str,
    *narrations: str,
) -> None:
    for narration in narrations:
        CH3_EP11_AMANOIWATO_NARRATION_SCENE_LOCKS[narration] = (
            subject,
            action,
            material,
        )


_add(
    "landscape-only primordial Japanese coast, zero people",
    "Extreme-wide full-bleed establishing view from wave level: cold blue-green surf strikes jagged black coastal rock while a narrow warm dawn band appears beneath layered storm clouds; no figure, building, map, writing, emblem, or arranged object",
    OBJECT_MATERIAL,
    "皆さん、 こんにちは。 日本 の 歴史 の 秘密 を 探る 時間 です。",
)
_add(
    "exactly one adult male Japanese storm deity Susanoo",
    "Extreme face-only close-up of one man only: wild-haired Susanoo's complete mature male face fills ninety percent of the frame as rain crosses clenched jaw, flared nostrils, and storm-dark eyes; hard crop ends at his jawline before every neck, shoulder, garment, body, or background figure, with zero women and zero second person",
    MYTH_MATERIAL,
    "前回 は、 暴風 の 神 スサノオ の 凄惨 な 悪行 を お 話 しました。",
)
_add(
    "exactly one adult female Japanese sun deity Amaterasu",
    "Extreme face-only close-up of Amaterasu at the instant grief overwhelms her: widened dark eyes, wet lower lashes, tightened mouth, and warm gold light withdrawing from one side of her mature face; complete face and natural long black hair fill the frame",
    MYTH_MATERIAL,
    "弟 の 乱暴 な 振る舞い に、 太陽 の 女神 アマテラス は 絶望 します。",
)
_add(
    "exactly one adult female Japanese sun deity Amaterasu",
    "Three-quarter rear action view at the cave threshold: Amaterasu retreats into black rock shadow and pushes one irregular stone slab toward the opening while the last narrow gold light falls across her attached arms and grief-stricken profile",
    MYTH_MATERIAL,
    "彼女 は 悲しみ と 恐怖 から、 天の岩戸 という 洞窟 に 隠れて しまい ました。",
)
_add(
    "landscape-only primordial world under supernatural night, zero people",
    "High wide view across one river valley and distant coast as the last natural sun disk disappears behind dense black cloud, leaving fields, water, and bare hills in cold blue darkness; no eclipse symbol, map, writing, structure, or person",
    OBJECT_MATERIAL,
    "太陽 が 姿 を 消した こと で、 世界 は 永遠 の 暗闇 に 包まれ ます。",
)
_add(
    "landscape-only dying primordial valley, zero people",
    "Ground-level wide view across deep cracked earth, frost-stiff reeds, a dark motionless river, and leafless trees beneath a sunless blue-black sky; heat and light are visibly absent, with no figure, map, sign, symbol, or building",
    OBJECT_MATERIAL,
    "光 と 熱 を 失った 宇宙 は、 まさに 滅亡 の 危機 に 瀕して いました。",
)
_add(
    "nonhuman shadow spirits only, zero human people",
    "Low oblique night view: several separate smoke-like yōkai silhouettes crawl from fissures and dead reeds toward the foreground while distant natural fire points fail in the cold darkness; every shape remains nonhuman and no writing or icon appears",
    OBJECT_MATERIAL,
    "様々 な 悪霊 たち が 騒ぎ 出し、 恐ろしい 災い が 次々 と 起こり ます。",
)
_add(
    "exactly five adult Japanese deities in a panicked group",
    "Dynamic diagonal group action: five distinct adult deities stumble and turn toward the sealed cave, one drops a plain wooden tool, two exchange terrified eye-lines, and two brace each other under cold darkness; faces and body reactions differ clearly",
    MYTH_MATERIAL,
    "この アポカリプス を 前 に して、 天上 界 の 神々 は パニック に なりました。",
)
_add(
    "group of adult Japanese deities planning beside the sealed cave",
    "Wide over-shoulder crisis meeting: the rough stone slab fills the right third while several deities at left point toward its edges and confer urgently around one empty center gap; no rope binds the door, no text, diagram, symbol, or neutral portrait",
    MYTH_MATERIAL,
    "なんとか して、 アマテラス を 洞窟 から 引きずり出さ なければ ならない。",
)
_add(
    "group of adult Japanese deities gathered for an emergency council",
    "High three-quarter riverbank view: separate deity groups form an irregular half-circle around one cold fire bowl on the stony Amano-Yasukawara bank, leaning inward with urgent faces while the black river runs behind them",
    MYTH_MATERIAL,
    "神々 は 天の安河原 と 呼ばれる 河原 に 集まり、 緊急 会議 を 開き ました。",
    "パニック に なった 神々 は、 天の安河原 に 集まって 会議 を 開き ました。",
)
_add(
    "large group of adult Japanese deities debating in darkness",
    "Eye-level compressed crowd view: many distinct adult faces argue across three staggered depth layers, one elder raises an empty palm, another points toward the unseen cave, and worried listeners answer with conflicting expressions; no repeated clones",
    MYTH_MATERIAL,
    "八百万の神 と 呼ばれる 無数 の 神様 たち が、 暗闇 の 中 で 議論 します。",
)
_add(
    "exactly one powerful adult male Japanese deity",
    "Low-angle full-body action: the powerful deity plants both bare feet and drives both attached shoulders against one immense irregular stone slab while loose gravel falls; the door remains closed and his strained face shows physical failure",
    MYTH_MATERIAL,
    "しかし 重い 岩 の 扉 は、 力ずく では 決して 開き ません でした。",
    "固く 閉ざされた 岩戸 を 開ける に は、 力ずく では 不可能 でした。",
)
_add(
    "object-only broken weapon evidence, zero people",
    "Extreme low macro of exactly two short dull-brown aged-bronze fragments from one failed ritual blade, both rough broken edges facing the same impact scar at the base of the immense stone slab; the fragments are visibly cast bronze rather than polished steel, with no complete sword, hilt, hand, writing, rune, emblem, magical glow, or extra object",
    OBJECT_MATERIAL,
    "暴力 や 武力 では、 閉ざされた 女神 の 心 を 開く こと は できない の です。",
)
_add(
    "exactly one elderly adult male Japanese wisdom deity Omoikane",
    "Tight seated three-quarter portrait: lined-faced Omoikane studies the sealed cave with narrowed thoughtful eyes, one attached hand resting against his chin and the other lowered beside smooth unmarked pebbles; no writing, diagram, rune, halo, or scroll",
    MYTH_MATERIAL,
    "そこで 立ち上がった の が、 オモイカネ という 素晴らしい 知恵 の 神様 でした。",
    "そこで 知恵 の 神 オモイカネ が、 奇想天外 な 作戦 を 立て ます。",
)
_add(
    "exactly five adult Japanese deities: elderly Omoikane and four surprised council listeners",
    "Medium low-angle story frame: Omoikane rises and speaks with one open attached palm while four listening deities lean toward him in surprise; a closed cave and bare sacred tree remain secondary, with no lightbulb, scroll, writing, symbol, or icon",
    MYTH_MATERIAL,
    "彼 は 全て の 神々 を 驚かせる、 奇想天外 な 作戦 を 提案 し ます。",
)
_add(
    "group of adult Japanese deities beginning a ritual festival plan",
    "Wide night preparation view: one group erects a plain timber perch, another carries a rough wooden tub, and a third clears bare ground before the sealed cave while Omoikane directs them from the side; varied bodies, props, and depth replace any stage curtain",
    MYTH_MATERIAL,
    "それ は アマテラス の 気 を 引く ため の、 盛大 な お 祭り を 開催 する こと。",
)
_add(
    "object-only sacred bronze mirror, zero people",
    "Object-only straight overhead macro filling the full frame with uninterrupted charcoal woven cloth and exactly one flat circular dark-umber aged-bronze mirror disk; its single smooth unbroken metal face catches one dim warm streak, with no horizon, outdoor ground, plant, tree, building, glass, frame, stand, landscape reflection, person, crown, sword, text, rune, or extra jewel",
    OBJECT_MATERIAL,
    "そして 彼女 の 代わり と なる、 美しい 鏡 を 作り出す こと でした。",
)
_add(
    "busy group of adult Japanese deities carrying out Omoikane's instructions",
    "Broad diagonal work scene: separate teams carry unpainted timber, an undecorated bronze disk, green jade blanks, braided fiber, and one wooden tub toward distinct work areas while Omoikane directs traffic; no duplicated standing portrait",
    MYTH_MATERIAL,
    "オモイカネ の 完璧 な 指示 の 下、 神々 は すぐ に 準備 に 取り掛かり ます。",
)
_add(
    "animal-only group of sacred long-crowing roosters, zero people",
    "Low wide wildlife view of exactly twelve separate red-brown roosters balanced along two rough unpainted timber perches in cold pre-dawn darkness, each bird fully formed and facing a different natural angle; no person, cage, writing, icon, or modern farm object",
    OBJECT_MATERIAL,
    "まずは 永遠 の 夜 の 中 で、 朝 を 告げる ため の 鶏 を 集め させ ました。",
    "まず 夜明け を 告げる ため の 神聖 な 鶏 を たくさん 集め させ ました。",
)
_add(
    "animal-only group of sacred long-crowing roosters, zero people",
    "Close low-angle wildlife action: six distinct roosters stretch their necks and crow toward the black sky from a rough timber perch while breath and loose feathers catch one warm firelight edge; no person, writing, sound-wave icon, or speech mark",
    OBJECT_MATERIAL,
    "常世の長鳴鳥 と 呼ばれる 神聖 な 鳥 たち が、 一斉 に 鳴き声 を 上げ ます。",
    "コケコッコー という 鳴き声 で、 朝 が きた と 勘違い させる ため です。",
)
_add(
    "landscape-only sunless primordial Japan, zero people",
    "Aerial oblique view across one real island coastline, river plain, and dark forest all buried under continuous cold night; natural terrain remains unlabeled and unoutlined, with no map, writing, compass, border, icon, or person",
    OBJECT_MATERIAL,
    "太陽 の 女神 アマテラス が 洞窟 に 隠れ、 闇 に 包まれた 世界。",
)
_add(
    "exactly one adult male Japanese blacksmith deity",
    "Three-quarter forge action: a muscular smith deity swings one rough stone maul toward a glowing bronze disk on one irregular waist-high dark stone block with no horn, feet, or metal body; his attached arms and focused face remain visible as sparks arc away from the future mirror",
    MYTH_MATERIAL,
    "次に 鍛冶屋 の 神様 に 命じて、 太陽 を 模した 巨大 な 鏡 を 作らせ ます。",
)
_add(
    "object-only sacred Yata mirror, zero people",
    "Object-only straight overhead macro filling the full frame with uninterrupted charcoal cloth and exactly one bright pale-gold polished aged-bronze Yata mirror face; the circle is one continuous unbroken smooth reflective metal surface with a warm fire streak and absolutely no center mark, center hole, boss, rim, relief, shield structure, horizon, plant, tree, building, glass, frame, landscape reflection, person, sword, crown, stand, text, emblem, or extra object",
    OBJECT_MATERIAL,
    "八咫鏡 と 呼ばれる この 鏡 は、 日本 の 三種の神器 の 一つ と なります。",
)
_add(
    "exactly one adult Japanese jade craft deity",
    "Tight over-shoulder craft view: the seated deity polishes one curved green magatama against a small wet stone, both attached hands working below a concentrated mature face while several raw jade chips remain in one shallow clay bowl",
    MYTH_MATERIAL,
    "さらに 玉 造り の 神様 に は、 美しい 曲玉 の 首飾り を 作らせ ました。",
)
_add(
    "object-only sacred Yasakani magatama cord, zero people",
    "Object-only straight overhead macro of exactly nine separate comma-shaped green jade magatama pendants joined by one short brown braided plant-fiber cord on uninterrupted charcoal cloth filling every corner; every pendant is one thick curved teardrop with one drilled hole near its blunt end, fully visible and never spherical, with no horizon, outdoor ground, plant, tree, building, person, hand, mirror, crown, writing, symbol, or extra jewelry",
    OBJECT_MATERIAL,
    "八尺瓊勾玉 と 呼ばれる これ も また、 天皇家 に 伝わる 宝物 です。",
)

_add(
    "exactly six adult Japanese deities uprooting one sacred sakaki tree",
    "Extreme-wide low-angle labor view: six distinct deities pull braided plant-fiber ropes in two directions while the complete root ball of one living sakaki rises from dark mountain soil; attached limbs, strained expressions, and exposed roots remain coherent",
    MYTH_MATERIAL,
    "そして 天の香山 という 山 から、 根っこ ごと 大きな 榊 の 木 を 掘り起こし ます。",
)
_add(
    "object-only decorated sacred sakaki tree, zero people",
    "Medium upward object view of one complete living sakaki branch holding exactly one round aged-bronze mirror and exactly one short green magatama cord on separate braided fiber ties; no paper, writing, symbol, extra treasure, hand, or person",
    OBJECT_MATERIAL,
    "その 木 の 枝 に、 完成 した 鏡 と 勾玉 を 綺麗 に 飾り付け ました。",
)
_add(
    "object-only sealed cave and prepared mirror, zero people",
    "Wide asymmetrical night view: the rough closed cave slab occupies the left half while the decorated sakaki and blank bronze mirror stand outside at right, sending one narrow warm reflection toward the stone seam; no figure, writing, emblem, or modern shrine object",
    OBJECT_MATERIAL,
    "全て は アマテラス の 気 を 引き、 洞窟 の 外 へ と 誘い出す ため の 準備。",
)
_add(
    "exactly six adult Japanese deities coordinating ritual preparation",
    "Broad diagonal action with six distinct adults on empty bare ground: two carry one rough wooden tub at left, two pull one long braided plant-fiber rope at center, one holds one blank bronze mirror disk at right, and elderly Omoikane directs them with one open palm; no table, meal, bowl, chair, seated diner, or neutral portrait",
    MYTH_MATERIAL,
    "神々 は 一丸 と なって、 宇宙 の 闇 を 打ち破る 計画 を 進めた の です。",
)
_add(
    "group of adult Japanese deities preparing the first sacred festival",
    "Wide historical ritual view before the cave: drummers test one overturned wooden tub, attendants arrange the sakaki mirror and beads, and roosters wait on rough perches as the gathered gods form an irregular arc; no scroll, readable text, torii, modern shrine, or icon",
    MYTH_MATERIAL,
    "日本 の 神社 で 行われる お 祭り の 起源 が、 まさに ここ に あります。",
)
_add(
    "object-only sealed Amano-Iwato cave, zero people",
    "Low wide suspense view of the immense irregular stone slab, empty bare ground, decorated sakaki, silent rooster perches, and one overturned tub under cold blue darkness; all props remain motionless and no figure, writing, symbol, or theatrical curtain appears",
    OBJECT_MATERIAL,
    "準備 が 整う と、 岩戸 の 前 に は 奇妙 な 緊張 感 が 漂い ました。",
)
_add(
    "exactly two adult male Japanese ritual deities Ame-no-Koyane and Futodama",
    "Symmetrical medium-wide view: the two distinct ritual deities stand on opposite sides of the decorated sakaki before the cave, one holding a plain braided offering cord and the other raising two empty palms; both mature faces remain solemn",
    MYTH_MATERIAL,
    "アメノコヤネ と フトダマ という 二柱 の 神 が、 祭壇 の 前 に 立ち ます。",
)
_add(
    "exactly two adult male Japanese ritual deities Ame-no-Koyane and Futodama",
    "Extreme opposing-profile face-only two-shot containing only two grave mature faces against a plain dark stone background: both ritual deities chant with visibly open empty mouths toward the unseen cave; the hard lower crop ends at both jawlines, so there are zero visible necks, shoulders, arms, hands, vessels, props, cups, bowls, scrolls, writing, sound waves, or magical letters",
    MYTH_MATERIAL,
    "彼ら は 太陽 の 女神 を 褒め称える ため に、 壮大 な 祝詞 を 読み上げ ました。",
)
_add(
    "exactly two adult male Japanese ritual deities chanting before the cave",
    "Tight chest-up side view of two chanting adult men on empty open ground: both mouths face one completely featureless irregular black natural boulder in the distant background, with no carved stone, stele, plaque, monument, tablet, scroll, glyph, visible text, cup, bowl, or sound-wave graphic",
    MYTH_MATERIAL,
    "美しい 言葉 で 飾られた 祈り の 儀式 が、 暗闇 の 中 に 響き渡り ます。",
)
_add(
    "object-only unmoving stone cave door, zero people",
    "Extreme low close view along the base of exactly one solid unworked natural boulder completely sealing a rough cave opening: loose dust and pebbles remain perfectly undisturbed despite distant warm firelight; no constructed door, timber panel, red surface, opening gap, fire inside, figure, writing, symbol, rope, or extra object",
    OBJECT_MATERIAL,
    "しかし それだけ では、 頑な に 閉ざされた 岩戸 は びくとも しません。",
)
_add(
    "exactly one elderly adult male Japanese wisdom deity Omoikane",
    "Extreme emotional head-and-shoulders close-up: Omoikane watches the unmoved door with tense narrowed eyes as his concern changes into final resolve; the lower frame ends above his hands and no icon, symbol, writing, or scroll appears",
    MYTH_MATERIAL,
    "アマテラス の 心 を 動かす に は、 もっと 強烈 な 刺激 が 必要 でした。",
)
_add(
    "exactly one adult female Japanese performance deity Ame-no-Uzume",
    "Low wide reveal without a stage curtain: Uzume steps into the bare center before one overturned wooden tub, the gathered gods forming a dark irregular arc behind her while the sealed cave looms at left",
    MYTH_MATERIAL,
    "そこ で ついに、 この 計画 の 最大 の 目玉 と なる 演目 が 始まり ます。",
)
_add(
    "exactly one adult female Japanese performance deity Ame-no-Uzume",
    "Heroic knee-up portrait: Uzume advances with a confident half-smile, wind lifting her loose black hair as warm firelight outlines her earth-red closed-front plant-fiber tunic against the cold darkness",
    MYTH_MATERIAL,
    "アメノウズメ という、 芸能 と 歓楽 を 司る 女神 が 進み出た の です。",
)
_add(
    "object-only large wooden tub, zero people",
    "Ground-level action still: exactly one large rough unpainted wooden tub lands upside down on packed earth, a tight ring of dust lifting from its rim; no foot, hand, person, writing, symbol, stage curtain, or extra container",
    OBJECT_MATERIAL,
    "彼女 は 足元 に 空っぽ の 大きな 桶 を 裏返し に して 置き ました。",
)
_add(
    "exactly one adult female Japanese dancer Ame-no-Uzume, lower body only",
    "High-speed low close-up of one woman only: exactly two attached bare adult female feet stomp alternating beats on the intact upside-down wooden tub, exactly two lower legs rise naturally into one single earth-red skirt hem at the top edge while dust jumps from the rim; no second skirt, second person, extra foot, or detached limb",
    MYTH_MATERIAL,
    "そして その 桶 の 上 に 飛び乗る と、 激しく 足 を 踏み鳴らし 始め ます。",
    "彼女 は 伏せた 桶 の 上 に 乗り、 ドンドン と 激しく 踏み鳴らし て 踊り 始め ました。",
)
_add(
    "object-only wooden tub under rhythmic impact, zero visible people",
    "Extreme side macro cropped below the top rim of the intact upside-down wooden tub: the curved timber side flexes as dust, exactly three pebbles, and loose plant fibers jump in one sharp pulse; the top surface and tub interior remain outside frame, with no shadow person, human-shaped silhouette, foot, hand, body, writing, musical note, sound wave, or icon",
    OBJECT_MATERIAL,
    "ドンドン という リズミカル な 音 が、 大地 を 震わせ て 響き ました。",
)
_add(
    "exactly one adult female Japanese performance deity Ame-no-Uzume",
    "Wide full-body ritual dance: Uzume bends one knee high and twists over the wooden tub with both attached arms extended in opposite directions, loose black hair tracing the motion while firelight and watching faces circle her",
    MYTH_MATERIAL,
    "これ は 神霊 を 呼び覚ます ため の、 古代 の 呪術 的 な ダンス です。",
)
_add(
    "exactly one adult female Japanese performance deity Ame-no-Uzume",
    "Tight chest-up emotional action portrait: Uzume throws her head back in ecstatic concentration, eyes bright and mouth open in one fierce breath as natural black hair arcs around her complete mature face; no duplicated head or floating energy symbol",
    MYTH_MATERIAL,
    "ウズメ の 踊り は 次第 に 激しさ を 増し、 彼女 自身 が トランス 状態 に 陥り ます。",
    "芸能 と 歓楽 の 神 で ある 彼女 は、 踊る うち に 完全 に トランス 状態 に なります。",
)
_add(
    "exactly one adult female Japanese performance deity Ame-no-Uzume",
    "Dynamic full-body silhouette against one real fire bowl: Uzume spins above the tub with attached arms and legs forming one coherent diagonal, hair and robe hems carrying the speed while spectators recoil and lean forward",
    MYTH_MATERIAL,
    "神がかり に なった 女神 の パフォーマンス は、 常軌 を 逸して いました。",
)
_add(
    "exactly four adult Japanese deity spectators",
    "Reaction close-up across four distinct mature faces: one deity gasps, one covers a surprised mouth with one attached hand, one leans forward, and one begins to laugh as Uzume dances off-screen; no exclamation mark, icon, writing, or repeated face",
    MYTH_MATERIAL,
    "その 常識 破り な 行動 が、 日本 神話 で 最も 衝撃 的 な 名 場面 を 作り出し ます。",
)
_add(
    "group of adult Japanese deities executing the Amano-Iwato plan",
    "Wide cave-front plan tableau: the sealed slab dominates left, the mirror-and-magatama sakaki stands center, Uzume waits by the overturned tub at right, and hidden helpers crouch behind rock; every element occupies a separate depth plane",
    MYTH_MATERIAL,
    "洞窟 に 隠れた 太陽 神 アマテラス を 引きずり出す ため の 大 作戦。",
)
_add(
    "exactly one adult female Japanese performance deity Ame-no-Uzume",
    "Medium-wide low-angle view: Uzume steps upright before the decorated sakaki, one round bronze mirror and one green magatama cord visible behind her while her determined face turns toward the sealed cave",
    MYTH_MATERIAL,
    "鏡 と 勾玉 を 飾った 祭壇 の 前 で、 アメノウズメ という 女神 が 立ち上がり ます。",
)
_add(
    "exactly one adult female Japanese performance deity Ame-no-Uzume",
    "Extreme emotional face-only close-up: sweat, firelight, and flying loose black hair frame Uzume's wide ecstatic eyes as she commits to the shocking next movement; no exclamation mark, question mark, icon, or second face",
    MYTH_MATERIAL,
    "髪 を 振り乱し、 神がかり に なった ウズメ は 驚く べき 行動 に 出ました。",
)
_add(
    "exactly one adult female Japanese performance deity Ame-no-Uzume",
    "Non-explicit historical dance, tight shoulder-and-face crop from behind: Uzume's loose black hair and bare upper back catch warm firelight while the front of her body remains completely outside frame; one slipped plant-fiber tunic edge stays below the shoulder blades, with no breast, nipple, genital, or voyeuristic angle",
    MYTH_MATERIAL,
    "なんと 着 て いた 衣服 の 胸元 を はだけ させ、 乳房 を 露出 させた の です。",
)
_add(
    "exactly one adult female Japanese performance deity Ame-no-Uzume",
    "Non-explicit rear three-quarter full-body dance silhouette: Uzume stamps on the tub while a securely tied opaque earth-red waist wrap covers her hips and groin; bare shoulders and back convey the transgressive ritual, with no breast, nipple, genital, exposed buttock, or erotic camera angle",
    MYTH_MATERIAL,
    "さらに 裳紐 を 押し下げて、 下半身 まで も あらわ に して しまい ました。",
)
_add(
    "group of adult Japanese deities watching adult performance deity Ame-no-Uzume",
    "Extreme-wide historical ritual on one continuous open rocky ground with a low empty rocky horizon spanning the full frame beneath uninterrupted natural sky. Uzume's non-explicit backlit dance silhouette moves above the tub at center while the fully clothed deity crowd forms a shocked semicircle. Packed soil and low natural stones fill the distant edges, with zero tree, timber post, perch, altar, shrine, cave, door, gate, plaque, sign, writing, stage curtain, or modern performance object",
    MYTH_MATERIAL,
    "神聖 な 儀式 の ど 真ん中 で 行われた、 衝撃 的 な ストリップ ショー です。",
)
_add(
    "one adult female Japanese performance deity and a distressed deity crowd",
    "Wide split-depth story scene on one continuous open rocky ground without symbolic objects: the dying cold-blue valley remains visible in the far distance while warm firelit Uzume dances non-explicitly on the tub and the surrounding gods begin to laugh despite the crisis; no cave, door, gate, plaque, sign, writing, scale, skull, or comedy mask",
    MYTH_MATERIAL,
    "世界 が 滅亡 する かも しれない 深刻 な 状況 で、 最も エロティック で ユーモラス な 踊り。",
)
_add(
    "large crowd of adult Japanese deities cheering around Ame-no-Uzume",
    "Low wide crowd-action view: Uzume remains centered on the tub while many distinct adult deities surge upward in layered arcs, laughing, clapping, and turning toward one another with varied faces and poses; no cloned row, raised weapons, writing, or icon",
    MYTH_MATERIAL,
    "この 常識 外れ の パフォーマンス に、 見て いた 八百万の神 は 大 興奮 します。",
)
_add(
    "large crowd of adult Japanese deities laughing together",
    "Ground-level wide crowd action: distinct adult deities collapse into laughter in three irregular depth layers, some clutching their knees, some leaning against companions, and others throwing open attached empty palms around Uzume's distant tub; every face and pose differs",
    MYTH_MATERIAL,
    "暗闇 の 中 に いた 無数 の 神々 が、 一斉 に どっと 笑い 転げた の です。",
)
_add(
    "object-only trembling cave-front ground, zero people",
    "Extreme low macro across loose pebbles, dust, and the base of the immense sealed natural boulder as laughter makes the ground visibly tremble; concentric dust ripples and jumping grit convey vibration without letters, sound waves, or human figures",
    OBJECT_MATERIAL,
    "高天原 が 揺れ動く ほど の、 凄まじい 大 爆笑 が 響き 渡り ました。",
)
_add(
    "large group of adult Japanese deities defeating darkness through celebration",
    "Extreme-wide valley ritual scene: laughing deities, one wooden-tub dancer, low fire bowls, and sacred roosters occupy separate zones while cold darkness visibly recedes from the real hills beneath returning natural color; no abstract spark or floating symbol",
    MYTH_MATERIAL,
    "宇宙 の 危機 を、 神々 の 笑い と お 祭り 騒ぎ で 吹き飛ばす という 奇策。",
)
_add(
    "large varied crowd of adult Japanese deities celebrating",
    "High oblique festival tableau on continuous rocky ground: drummers, dancers, laughing elders, crouching helpers, and clapping onlookers create an exuberant human-scale scene around firelight, with the sealed cave secondary in the distance; no scroll, text, banner, or modern festival object",
    MYTH_MATERIAL,
    "日本 神話 の おおらか さ と、 人間 臭 さ が 爆発 する 最高 の カタルシス です。",
)
_add(
    "object-only sealed Amano-Iwato boulder, zero people",
    "Tight exterior view of one solid irregular cave slab as dust sifts from its upper seam and tiny pebbles jump at its base under distant firelight; the rock remains closed, featureless, and natural, with no plaque, letters, face, or person",
    OBJECT_MATERIAL,
    "この 凄まじい 歓声 と 笑い声 は、 固く 閉ざされた 洞窟 の 中 に も 届き ました。",
)
_add(
    "exactly one adult female Japanese sun deity Amaterasu",
    "Extreme emotional face-only close-up inside black rock shadow: Amaterasu suddenly raises her gaze toward the unseen cave entrance, confusion interrupting grief as a faint warm flicker reaches one eye; her mature face fills the frame",
    MYTH_MATERIAL,
    "岩戸 の 中 で 塞ぎ込んで いた アマテラス は、 外 の 様子 に 気がつき ました。",
)
_add(
    "landscape-only sunless primordial Japan, zero people",
    "UNDEREXPOSED MOONLESS NIGHT LANDSCAPE: very high natural aerial view across one real island coast, river valley, and forest. A deep navy-black starless sky fills the upper half, the sun is completely absent, the sea is dark slate-blue, and the land is visible only as cold near-black silhouettes with tiny muted green traces. This is darkest night rather than daylight; terrain remains organic and unlabeled without borders, map styling, compass, writing, or person",
    OBJECT_MATERIAL,
    "自分 が 隠れた せい で、 世界 は 真っ暗 な 闇 に 包まれて いる はず だ。",
)
_add(
    "exactly one adult female Japanese sun deity Amaterasu",
    "Tight seated three-quarter emotional portrait inside the cave: Amaterasu hugs one knee and lowers her tearful mature face, imagining the gods' despair while rough black stone encloses the background; no mirror, cracked glass, duplicate face, or symbol",
    MYTH_MATERIAL,
    "神々 は 皆 悲しみ に 暮れて、 絶望 して いる に 違いない と 思って いました。",
)
_add(
    "distant group of laughing adult Japanese deities viewed from an empty cave interior, zero foreground people",
    "View from deep inside an empty black cave: two rough rock walls create a narrow central opening that reveals a softly focused celebratory crowd with raised laughing faces, one drummer, and orange firelight at least twenty paces outside. The foreground contains natural rock shadow only, with no foreground person, silhouette, head, hand, musical note, sound wave, letter, or icon",
    MYTH_MATERIAL,
    "ところが 外 から 聞こえて くる の は、 楽し そう な 音楽 と 凄まじい 笑い声 です。",
)
_add(
    "exactly one adult female Japanese sun deity Amaterasu",
    "Extreme face-only curiosity close-up: Amaterasu turns toward the sound with one eyebrow lifted, grief-softened eyes alert, and lips slightly parted in puzzled thought against cave darkness; no question mark, writing, or second face",
    MYTH_MATERIAL,
    "一体 外 では 何 が 起き て いる の だろう と、 彼女 は 不思議 に 思い 始め ます。",
)
_add(
    "exactly one adult female Japanese sun deity Amaterasu",
    "Low side full-body action inside the cave: Amaterasu rises from the stone floor and steps decisively toward the sealed slab, one attached hand reaching toward its rough inner edge while dim gold returns to her determined profile",
    MYTH_MATERIAL,
    "どうしても 気 に なった アマテラス は、 ついに 行動 を 起こし ました。",
)
_add(
    "object-only immense stone cave slab, zero people",
    "Extreme close view from outside as one solid irregular boulder shifts just enough to create one finger-wide vertical gap; loose grit falls from the seam while every other edge remains sealed, with no constructed door, writing, hand, or figure",
    OBJECT_MATERIAL,
    "決して 開け ない と 誓った 重い 岩戸 を、 ほんの 少し だけ 押し開けた の です。",
)
_add(
    "object-only narrow beam from the cave, zero people",
    "Ground-level exterior view of one thin natural golden ray escaping through the finger-wide seam of the immense dark boulder and crossing cold rocky soil; the surrounding world gains a faint blue-green tint, with no lamp, icon, text, or person",
    OBJECT_MATERIAL,
    "扉 の 隙間 から 光 が 漏れ 出し、 外 の 世界 が わずか に 明るく なります。",
)
_add(
    "exactly one adult female Japanese sun deity Amaterasu",
    "EXTREME COMPLETE-FACE CLOSE-UP BETWEEN TWO ROCK EDGES: unmistakably adult feminine Amaterasu's full face fills eighty percent of the frame from hairline to chin, with one vertical rough black rock edge at left and another at right. Her alert eyes look toward Uzume and her lips begin a natural question; the hard lower crop ends directly below her chin, excluding neck, shoulders, torso, arms, hands, standing pose, ground, and sky",
    MYTH_MATERIAL,
    "アマテラス は 隙間 から 外 を 覗き込み、 ウズメ に 向かって 問いかけ ました。",
)
_add(
    "exactly one adult female Japanese sun deity Amaterasu",
    "EXTREME FACE-ONLY PROFILE WITH ZERO BODY: Amaterasu's feminine mature eye, nose, and naturally speaking lips fill the narrow stone seam from top to bottom as black rock presses along both frame edges. Her proud confusion is clear; the hard crop excludes neck, shoulders, torso, standing pose, ground, and sky, with no bubble, letters, or second person",
    MYTH_MATERIAL,
    "私 が い なくて 世界 は 暗闇 なのに、 なぜ あなた は 踊り、 神々 は 笑って いる の です か。",
)
_add(
    "exactly one adult female Japanese performance deity Ame-no-Uzume",
    "Extreme emotional head-and-shoulders close-up: Uzume meets the cave gap with a knowing restrained smile, bright confident eyes, and warm firelight across her mature face as she begins her rehearsed answer; hands and props stay outside the crop",
    MYTH_MATERIAL,
    "すると アメノウズメ は、 待って いました と ばかり に ニッコリ と 答え ます。",
)
_add(
    "exactly one adult female Japanese performance deity Ame-no-Uzume",
    "Medium three-quarter storytelling view: Uzume gestures with one open attached palm toward the round blank bronze mirror hanging on the decorated sakaki while addressing the unseen Amaterasu; the mirror remains object-like and no extra woman, writing, emblem, or halo appears",
    MYTH_MATERIAL,
    "あなた 様 より も 尊く て 美しい、 素晴らしい 神様 が 現れた から です。",
)
_add(
    "large crowd of adult Japanese deities celebrating around Ame-no-Uzume",
    "Wide crowd response: Uzume stands near the tub as distinct deities laugh, clap, drum, and turn toward the narrow cave seam in staggered depth, proving the festival is underway; no sign, banner, text, clone row, or modern object",
    MYTH_MATERIAL,
    "だから 私 たち は こうして 喜び、 お 祭り 騒ぎ を して いる の です よ。",
)
_add(
    "exactly one adult female Japanese sun deity Amaterasu",
    "Extreme emotional face-only close-up of unmistakably adult feminine Amaterasu: long loose center-parted black hair, fine feminine jaw, smooth chin, narrow nose, and narrowed eyes fill eighty-five percent of the frame as wounded pride replaces grief; a warm gold edge brightens one cheek and the crop ends above her shoulders",
    MYTH_MATERIAL,
    "それ を 聞いた アマテラス は、 激しい プライド を 刺激 され ました。",
)
_add(
    "object-only macro of Amaterasu's single feminine eye beside one cropped bronze arc, zero visible full person",
    "STRICT TWO-ELEMENT MACRO: Amaterasu's single proud feminine eye and eyebrow fill the entire dark left half. One thin curved cropped arc of blank aged bronze fills the far right edge. The crop ends above the nose and excludes full face, neck, shoulders, body, complete mirror, mirror frame, stand, landscape, crown, text, emblem, and separate woman",
    MYTH_MATERIAL,
    "太陽 の 女神 である 自分 より も、 素晴らしい 神 が いる はず が ない。",
)
_add(
    "exactly one adult female Japanese sun deity Amaterasu",
    "Three-quarter side action at the cave threshold: Amaterasu pushes the immense slab wider with one attached hand and leans her head and shoulders into natural daylight, searching for the rival goddess with a proud intent gaze",
    MYTH_MATERIAL,
    "一体 どんな 女神 なのか、 その 顔 を 見て やろう と 身 を 乗り出し ます。",
)
_add(
    "exactly four adult Japanese deity helpers",
    "Wide diagonal action: exactly four distinct waiting helpers spring from separate rocky hiding places, two carrying the plain mirror support, one gripping a braided rope, and one signaling with an empty palm; all four bodies move toward the cave without cloned poses",
    MYTH_MATERIAL,
    "その 瞬間、 外 で 待ち構えて いた 神々 が 素早く 動きました。",
)
_add(
    "exactly two adult Japanese ritual attendants presenting one sacred mirror",
    "Dynamic medium action: two distinct attendants hold opposite edges of one large round blank aged-bronze Yata mirror and thrust its smooth face into the narrow golden beam before the unseen cave opening; attached hands remain clear and no shield, text, emblem, or extra person appears",
    MYTH_MATERIAL,
    "用意 して いた 八咫鏡 を、 アマテラス の 顔 の 前 に スッ と 差し出した の です。",
)
_add(
    "exactly one adult female Japanese sun deity Amaterasu and her single mirror reflection",
    "Intimate over-mirror view: one round blank aged-bronze mirror fills the foreground and contains one coherent reflected image of Amaterasu's luminous mature face, while only the back edge of her real black hair appears beyond it; reflection and real subject align naturally",
    MYTH_MATERIAL,
    "鏡 に 映った の は、 光り輝く アマテラス 自身 の 美しい 顔 でした。",
)
_add(
    "exactly one adult female Japanese sun deity Amaterasu",
    "Extreme captivated face close-up beside a thin aged-bronze mirror edge: Amaterasu's proud expression softens into astonished fascination, gold returning to her eyes and skin while she studies the unseen reflective face; no second woman, writing, crown, or icon",
    MYTH_MATERIAL,
    "しかし 彼女 は 自分 の 姿 だ と 気づか ず、 鏡 の 中 の 女神 に 見惚れて しまい ます。",
)
_add(
    "exactly one adult female Japanese sun deity Amaterasu",
    "Exterior medium close view of Amaterasu peering through the slightly opened irregular boulder while distant laughing faces and firelight remain softly out of focus; curiosity clearly draws her forward",
    MYTH_MATERIAL,
    "神々 の 大 爆笑 が 気 に なり、 岩戸 を 少し だけ 開けた アマテラス。",
)
_add(
    "exactly one adult female Japanese sun deity Amaterasu",
    "EXTREME FACE-ONLY SEAM CLOSE-UP WITH ZERO BODY: one feminine eye plus Amaterasu's naturally questioning lips fill the finger-wide opening between two immense black rock faces. The hard crop excludes neck, shoulders, torso, arms, standing pose, ground, and sky; rough stone frames her mature expression without bubble, letters, or icon",
    MYTH_MATERIAL,
    "彼女 は 隙間 から 外 を 覗き、 なぜ 皆 笑って いる の か と 尋ね ました。",
)
_add(
    "exactly one adult female Japanese performance deity Ame-no-Uzume",
    "EXTREME FACE-ONLY EMOTIONAL PORTRAIT: unmistakably adult feminine Uzume's complete face spans the frame from hairline to chin, her knowing sideways eyes and asymmetrical mischievous smile clearly revealing the lie in warm firelight. Loose black hair touches both side edges and the hard lower crop ends directly beneath her chin; neck, shoulders, hands, torso, full body, mirror, mirror frame, stand, second woman, and magical symbol remain outside the image",
    MYTH_MATERIAL,
    "ウズメ は、 あなた 様 より も 美しい 神 が 現れた から だ と 嘘 を つき ます。",
)
_add(
    "object-only tight action crop of Amaterasu's two attached feminine hands pushing one stone slab",
    "STRICT HAND-ACTION MACRO: exactly two attached feminine hands enter from the dark cave at left. One open palm presses flat against the immense vertical natural slab while the second hand grips its rough edge, both wrists aligned with two ivory sleeves. Dust falls from the moving seam under visible pressure; the crop excludes face, full body, raised waving palm, pointing gesture, ground, sky, and every other person",
    MYTH_MATERIAL,
    "プライド を 刺激 された 太陽 神 は、 その 姿 を 見よう と さらに 身 を 乗り出し ます。",
)
_add(
    "exactly two adult Japanese ritual attendants presenting one sacred mirror",
    "Fast diagonal action: two hidden attendants emerge from separate low rocks and thrust one large round blank aged-bronze Yata mirror directly into the beam before Amaterasu's unseen face; the mirror is smooth, undecorated, and held by exactly four attached hands",
    MYTH_MATERIAL,
    "その 瞬間、 隠れて いた 神々 が 八咫鏡 を アマテラス の 前 に 突き出し ました。",
)
_add(
    "exactly one adult female Japanese sun deity Amaterasu and her single mirror reflection",
    "Tight over-mirror emotional view: one coherent radiant reflection of Amaterasu's unmistakably feminine mature face fills the round aged-bronze mirror while her real face appears only as a narrow soft-focus profile at the edge, captivated and unaware they are the same person",
    MYTH_MATERIAL,
    "鏡 に 映った 光り輝く 自分 自身 の 姿 を、 新たな 女神 だ と 勘違い します。",
)
_add(
    "exactly one adult female Japanese sun deity Amaterasu",
    "Low side full-body threshold action: Amaterasu takes one clear barefoot step from black cave shadow onto sunlit rocky ground, her face still turned toward the mirror and her long black hair catching the first gold light",
    MYTH_MATERIAL,
    "なんて 美しい の だろう と 見惚れ、 思わず 洞窟 の 外 へ と 歩み出た の です。",
)
_add(
    "exactly one elderly adult male Japanese wisdom deity Omoikane",
    "Tight chest-up action portrait: Omoikane sees Amaterasu cross the threshold and gives one sharp concealed hand signal toward helpers outside frame, narrowed eyes showing urgent calculation rather than celebration",
    MYTH_MATERIAL,
    "この わずか な チャンス を、 知恵 の 神 オモイカネ は 逃し ません でした。",
)
_add(
    "exactly one powerful adult male Japanese deity Ame-no-Tajikarao",
    "Low-angle three-quarter concealment view: the muscular deity crouches tightly behind one rough boulder beside the cave, both empty attached hands ready and his mature face focused on the threshold; no weapon, armor, or second person",
    MYTH_MATERIAL,
    "岩戸 の 脇 に は、 天手力男神 という 怪力 の 神様 が 隠れて いました。",
)
_add(
    "exactly two adults: female Amaterasu and male Ame-no-Tajikarao",
    "Tight side action on attached arms: Tajikarao's one large hand closes securely around Amaterasu's forearm just above her wrist as she leans beyond the threshold, while both distinct faces remain visible with surprise and resolve; no dislocated joint or extra hand",
    MYTH_MATERIAL,
    "アマテラス が 身 を 乗り出した 瞬間、 彼 は 女神 の 手 を ガシッ と 掴み ます。",
)
_add(
    "exactly two adults: female Amaterasu and male Ame-no-Tajikarao",
    "Wide diagonal rescue action: Tajikarao plants both feet outside and pulls Amaterasu completely across the cave threshold by her attached forearm, her feet leaving black shadow for golden ground while the slab remains open behind them",
    MYTH_MATERIAL,
    "そして 持ち前の 凄まじい パワー で、 彼女 を 洞窟 の 外 へ 力 いっぱい 引きずり出し ました。",
)
_add(
    "exactly two adult Japanese ritual attendants",
    "Wide straight-on action: two attendants at opposite sides pull one thick braided plant-fiber shimenawa taut across the entire natural cave entrance at chest height, anchoring it to plain rocks while the empty dark opening remains behind",
    MYTH_MATERIAL,
    "同時に 別 の 神 が、 洞窟 の 入り口 に 注連縄 を ピン と 張り巡らせ ます。",
)
_add(
    "object-only sacred braided boundary rope, zero people",
    "Extreme close object view of one thick unpainted plant-fiber shimenawa stretched horizontally across the sealed natural cave seam, its coarse twists and two short plain fiber tassels sharply visible; no paper strips, writing, symbol, torii, plaque, or person",
    OBJECT_MATERIAL,
    "これ は 結界 の 役割 を 果たし、 もう 二度と 中 に は 戻れ ない という 印 です。",
)
_add(
    "exactly one adult female Japanese sun deity Amaterasu surrounded by celebrating deities",
    "Heroic low wide return: Amaterasu stands fully outside in a vertical column of warm sunlight while distinct deities lower the mirror, release the rope, and turn toward her with relieved faces; her luminous mature feminine face remains the clear focus",
    MYTH_MATERIAL,
    "こうして 太陽 の 女神 は、 ついに 天上 界 へ と 帰還 する こと と なりました。",
)
_add(
    "large group of adult Japanese deities with Amaterasu",
    "Extreme-wide decisive moment: radiant Amaterasu occupies the cave threshold, the taut boundary rope spans behind her, helpers embrace and raise empty hands, and gold daylight rolls across the real valley in layered depth",
    MYTH_MATERIAL,
    "神々 の 奇策 が 見事に 成功 し、 世界 が 救われた 劇的 な 瞬間 です。",
)
_add(
    "landscape-only cave valley at returning sunrise, zero people",
    "Wide view from the cave ridge as one expanding band of natural gold daylight races across dark hills, river, and coastline, replacing cold blue shadow with distinct green vegetation and mineral-blue water; no curtain, symbol, map, or figure",
    OBJECT_MATERIAL,
    "アマテラス が 洞窟 の 外 に 出た 途端、 世界中 に 劇的 な 変化 が 起こり ます。",
)
_add(
    "landscape-only restored Takamagahara, zero people",
    "Upward panoramic view across primordial high plain and cloud banks as a real brilliant sun clears the ridge, warm rays striking wet stone, green grass, and blue-white cloud while the last black shadow retreats",
    OBJECT_MATERIAL,
    "ずっと 闇 に 閉ざされて いた 高天原 に、 眩しい 太陽 の 光 が 戻って きた の です。",
)
_add(
    "landscape-only Ashihara-no-Nakatsukuni under returning sunlight, zero people",
    "High oblique natural view of one unlabeled river plain, reed marsh, forest, and distant coast as warm sunlight crosses the real terrain from east to west; no map border, compass, text, diagram, settlement, or person",
    OBJECT_MATERIAL,
    "それ と 同時に、 地上 の 葦原中国 に も 暖か な 陽差し が 降り注ぎ ました。",
)
_add(
    "object-only recovering primordial plants, zero people",
    "Ground-level seasonal transformation macro: frost melts into clear droplets on dark soil while separate green shoots lift among formerly dry reeds and one closed bud opens under warm sun; no magical icon, hand, building, or person",
    OBJECT_MATERIAL,
    "凍りついて いた 大地 が 溶け、 枯れ 果てて いた 植物 たち が 一斉 に 息 を 吹き返し ます。",
)
_add(
    "object-only dissolving black smoke evidence, zero people",
    "Object-like macro of black smoke wisps breaking apart into ash in one gold sunbeam above a riverbank; the smoke has no face, torso, limbs, or upright silhouette and no people appear",
    OBJECT_MATERIAL,
    "暗闇 を 徘徊 して いた 恐ろしい 悪霊 たち は、 光 に 焼かれて 消滅 しました。",
)
_add(
    "landscape-only restored primordial world, zero people",
    "Extreme-wide balanced view of blue river, green reed plain, dark forest, distant mountains, and clear coast beneath warm morning light, every natural layer calm and healthy after the crisis; no map, scale, emblem, building, or person",
    OBJECT_MATERIAL,
    "病気 や 災い も 嘘 の ように 去り、 宇宙 は 本来 の 美しい 秩序 を 取り戻した の です。",
)
_add(
    "large crowd of adult Japanese deities welcoming the restored sun",
    "Low wide crowd reaction: many distinct adult deities turn upward into gold light with relieved tears, open laughter, embraces, and raised empty palms around the cave ridge; varied faces and poses replace a cloned row",
    MYTH_MATERIAL,
    "太陽 の 復活 を 目の当たり に した 八百万の神 は、 歓喜 の 声 を 上げ ました。",
)
_add(
    "large group of adult Japanese deities celebrating with Ame-no-Uzume",
    "Wide human-scale festival scene: Uzume dances on the wooden tub while laughing deities drum, clap, and embrace under restored daylight, with sheathed tools and empty hands showing that celebration rather than battle saved the world",
    MYTH_MATERIAL,
    "世界 を 滅亡 から 救った の は、 深刻 な 戦い で は なく 笑い と お 祭り でした。",
)
_add(
    "group of adult Japanese deities preserving the Amano-Iwato ritual",
    "Quiet dawn aftermath: Uzume, Omoikane, a mirror bearer, and a rope attendant stand in distinct positions before the natural cave while younger listeners watch their expressions and ritual objects, conveying shared memory without scroll, book, text, or modern shrine",
    MYTH_MATERIAL,
    "この 岩戸隠れ の 神話 は、 日本 人 の 精神 構造 を よく 表して います。",
)
_add(
    "exactly one adult female Japanese performance deity Ame-no-Uzume and a laughing crowd",
    "Dynamic low-angle performance: Uzume stamps one foot on the wooden tub and flashes a resilient smile while the surrounding adult crowd claps through lingering hardship under mixed shadow and returning gold light",
    MYTH_MATERIAL,
    "困難 な 状況 ほど、 ユーモア と 芸能 の 力 で 乗り越えよう と する 姿勢 です。",
)
_add(
    "object-only Yata mirror and Yasakani magatama cord, zero people",
    "Overhead on full-frame charcoal cloth: exactly one flat blank bronze mirror disk at left; exactly nine separate thick green comma-shaped magatama with one drilled hole each on one short brown cord at right; wide empty cloth separates them",
    OBJECT_MATERIAL,
    "また、 この 時 使われた 八咫鏡 と 八尺瓊勾玉 は 非常に 重要 です。",
)
_add(
    "exactly three adult Japanese ritual attendants presenting the three sacred regalia",
    "Wide row of exactly three attendants. Left presents one blank bronze mirror; center presents one cord of green comma magatama; right presents one complete straight leaf-shaped bronze blade. Every item is fully visible and separated",
    MYTH_MATERIAL,
    "これら は 後 に、 天皇家 の 証 で ある 三種の神器 と して 受け継がれ ます。",
)
_add(
    "object-only archaic sacred boundary rope, zero people",
    "Close natural view of one thick braided plant-fiber shimenawa spanning between two rough uncarved stones in open primordial terrain, with two short plain fiber tassels and no paper; no torii, shrine building, plaque, writing, bell, modern object, or person",
    OBJECT_MATERIAL,
    "さらに 結界 として 張られた 注連縄 は、 現在 の 神社 でも 見る ことが できます。",
)
_add(
    "exactly one adult female Japanese performance deity Ame-no-Uzume",
    "Wide archaic kagura origin scene: Uzume performs a vigorous grounded turn on bare earth beside the wooden tub, attached arms extended and loose hair moving while a small deity circle keeps rhythm with claps; no modern miko costume, shrine building, torii, fan, writing, or stage",
    MYTH_MATERIAL,
    "神様 を 呼び寄せる ため に 踊る 神楽 も、 ウズメ の 踊り が ルーツ です。",
)
_add(
    "group of adult Japanese deities with foundational ritual objects",
    "Broad layered cave-front tableau: the natural boulder and braided boundary rope anchor the left, blank bronze mirror and magatama sakaki occupy center, and Uzume dances before a gathered deity circle at right under restored sun; no torii, shrine building, text, scroll, or modern ritual object",
    MYTH_MATERIAL,
    "つまり この 物語 は、 日本 の 神道 の 基礎 を 全て 詰め込んだ エピソード なの です。",
)
_add(
    "exactly one adult female Japanese sun deity Amaterasu",
    "Tight emotional portrait after the celebration: Amaterasu stands in warm restored light but turns her serious mature face toward a distant storm-dark ridge, relief giving way to sober resolve; no hourglass, crack, text, or smiling crowd",
    MYTH_MATERIAL,
    "しかし、 太陽 が 戻って めでたし めでたし、 と は なり ません。",
)
_add(
    "exactly one adult male Japanese storm deity Susanoo",
    "Low wide aftermath view: isolated Susanoo stands at the edge of a trampled sacred field beneath a dark remaining storm cloud, broken ridges and scattered unmarked weaving fibers around him while restored sunlight approaches from far behind",
    MYTH_MATERIAL,
    "この 宇宙 規模 の 大 パニック を 引き起こした、 張本人 が いる から です。",
)
_add(
    "exactly one adult male Japanese storm deity Susanoo beside non-graphic damage",
    "Somber three-quarter evidence scene: Susanoo lowers his gaze beside one broken archaic loom and torn white weaving cloth spread across the ground, with the absent victim represented only by one empty sandal; no body, corpse, blood, wound, weapon, or exposed anatomy",
    MYTH_MATERIAL,
    "姉 の アマテラス を 絶望 させ、 機織り の 少女 を 死 に 追いやった スサノオ。",
)
_add(
    "exactly seven adult Japanese deities judging Susanoo",
    "Frontal outdoor tribunal: restrained Susanoo kneels alone at center while six distinct elder deities form a stern arc and Omoikane stands forward delivering judgment with one open attached palm; no throne, scale, writing, weapon, or execution scene",
    MYTH_MATERIAL,
    "世界 の 秩序 を 取り戻した 神々 は、 ついに 彼 へ の 厳正 な 処罰 を 下し ます。",
)
_add(
    "group of adult Japanese deities conducting the decisive judgment of Susanoo",
    "Extreme-wide final tribunal on one continuous high plain: kneeling Susanoo faces the deity council at left while an empty descending mountain path toward the earthly coast opens at right, foreshadowing exile and the next mythic setting; no scale, courtroom building, scroll, text, border, or map",
    MYTH_MATERIAL,
    "これ は 単なる 兄弟 喧嘩 の 結末 では なく、 神話 の 舞台 を 移す 決定 的 な 裁判 と なります。",
)
_add(
    "large group of adult Japanese deities with Amaterasu and Ame-no-Tajikarao",
    "Wide triumphant action recap: Tajikarao completes the pull as Amaterasu clears the cave threshold, mirror attendants step aside, and relieved deities surge forward in separated depth under returning gold light",
    MYTH_MATERIAL,
    "奇策 によって アマテラス を 洞窟 から 引きずり出す こと に 成功 した 神々。",
)
_add(
    "object-only sacred boundary rope across the cave, zero people",
    "Straight-on close view of one thick braided plant-fiber shimenawa stretched taut across the entire natural cave entrance between two uncarved rocks, its rough fibers sharply visible against empty black shadow",
    OBJECT_MATERIAL,
    "結界 の 注連縄 を 張り、 もう 二度と 彼女 が 隠れられない よう に しました。",
)
_add(
    "landscape-only cave valley at returning sunrise, zero people",
    "Extreme-wide ridge view as one expanding natural gold sunbeam crosses the cave, river plain, forest, and distant coast, replacing cold night with distinct mineral-blue water and green vegetation",
    OBJECT_MATERIAL,
    "太陽 の 女神 が 外 の 世界 に 戻った 瞬間、 宇宙 に 劇的 な 変化 が 起き ます。",
)
_add(
    "landscape-only restored heaven and earth, zero people",
    "High panoramic view connecting bright cloud-wrapped highlands, warm mountain slopes, blue river, and green lowland coast beneath one real sun, with light and warmth visibly restored across every natural layer",
    OBJECT_MATERIAL,
    "闇 に 閉ざされて いた 天 と 地 に、 眩しい 光 と 暖か さ が 戻って きた の です。",
)
_add(
    "object-only recovering soil and plants, zero people",
    "Ground macro: clear meltwater runs through formerly frozen dark soil while green shoots rise among dry reeds and several small buds open under warm sunlight, all rooted naturally in one continuous patch",
    OBJECT_MATERIAL,
    "凍りついて いた 大地 は 溶け、 枯れた 植物 は 一斉 に 息 を 吹き返し ました。",
)
_add(
    "object-only dissolving black smoke evidence, zero people",
    "Frame-filling airborne macro cropped high above all ground: separate black smoke wisps dissolve into thousands of pale ash particles inside one diagonal gold sunbeam against an empty blue sky, with no horizon, land, face, torso, limbs, upright silhouette, or human figure",
    OBJECT_MATERIAL,
    "暗闇 に 乗じて 騒いで いた 悪霊 たち は、 太陽 の 光 に 焼かれて 消滅 します。",
)
_add(
    "landscape-only restored primordial world, zero people",
    "Balanced extreme-wide natural vista of clear blue river, green reed plain, dark healthy forest, distant mountains, and calm coast beneath warm morning light after the crisis",
    OBJECT_MATERIAL,
    "世界 が 滅亡 の 危機 を 脱し、 本来 の 美しい 秩序 を 取り戻した 瞬間 です。",
)
_add(
    "exactly three adult Japanese ritual attendants presenting the three sacred regalia",
    "Wide row of exactly three attendants. Left presents one blank bronze mirror; center presents one cord of green comma magatama; right presents one complete straight leaf-shaped bronze blade. Every item is fully visible and separated",
    MYTH_MATERIAL,
    "この 時 に 使われた 鏡 や 勾玉 は、 後 の 天皇家 の 三種の神器 と なります。",
)
_add(
    "group of adult Japanese deities with foundational ritual objects",
    "Broad archaic ritual tableau: a braided boundary rope spans natural rocks at left, Uzume dances beside the wooden tub at center, and mirror attendants stand at right before the cave under daylight",
    MYTH_MATERIAL,
    "注連縄 や 神楽 など、 現代 の 神社 に 繋がる ルーツ が 全て 詰まった 神話。",
)
_add(
    "large group of adult Japanese deities celebrating with Amaterasu",
    "Extreme-wide closing festival: radiant Amaterasu stands outside the roped cave while Uzume dances, drummers play, and many distinct deities laugh and embrace across layered rocky ground beneath restored sun",
    MYTH_MATERIAL,
    "日本 神話 の ハイライト、 岩戸隠れ の 伝説 は 大 団円 を 迎え ました。",
)
_add(
    "exactly seven adult Japanese deities beginning Susanoo's judgment",
    "Frontal outdoor tribunal: Susanoo kneels alone at center while six stern elder deities form an arc and Omoikane steps forward, the celebration and cave now distant behind them",
    MYTH_MATERIAL,
    "しかし 平和 が 戻った 天上 界 で、 避けて は 通れない 裁判 が 始まり ます。",
)
_add(
    "exactly one adult male Japanese storm deity Susanoo",
    "Low three-quarter emotional portrait: isolated Susanoo kneels on bare ground with lowered wild-haired head and clenched empty hands, broken field ridges and a dark storm remnant behind him",
    MYTH_MATERIAL,
    "この 全て の 惨劇 の 原因 を 作った 張本人、 スサノオ への 処罰 です。",
)
_add(
    "exactly six adult Japanese elder deities judging Susanoo",
    "Compressed stern council view: six distinct elders lean forward with angry mature faces while the central elder extends one open attached palm to pronounce the severe sentence toward Susanoo outside frame",
    MYTH_MATERIAL,
    "神々 は 激怒 し、 彼 に 対して 究極 の 重い 罰 を 言い渡し ました。",
)
_add(
    "exactly one adult male Japanese storm deity Susanoo after non-graphic ritual punishment",
    "Somber chest-up aftermath: Susanoo's formerly wild beard is visibly shortened and uneven, his fingernails are closely trimmed, and both intact hands rest on his knees beside a few harmless hair and nail clippings on plain cloth; no blood, wound, blade, torn skin, or severed part",
    MYTH_MATERIAL,
    "ヒゲ と 手足 の 爪 を 剥がれ、 天上 界 から 永遠 に 追放 される という 刑罰。",
)
_add(
    "exactly one adult male Japanese storm deity Susanoo",
    "Extreme-wide exile descent: lone Susanoo walks down a steep cloud-shadowed mountain path from bright highland toward the earthly green coast below, carrying one small plain cloth bundle as storm wind follows",
    MYTH_MATERIAL,
    "地上 へ と 落とされた 暴風 の 神 は、 新たな 伝説 の 舞台 へ と 降り立ち ます。",
)
_add(
    "landscape-only Amano-Iwato valley after sunrise, zero people",
    "Quiet full-color epilogue view of the roped natural cave, calm blue river, green slopes, and warm sun after the crisis, with the wooden tub and blank mirror resting separately on empty ground",
    OBJECT_MATERIAL,
    "今回 の 岩戸隠れ と 太陽 の 復活 の お 話 は いかが でした か。",
)
_add(
    "exactly one adult female Japanese performance deity Ame-no-Uzume and a laughing crowd",
    "Dynamic non-explicit rear three-quarter ritual dance: Uzume stamps on the wooden tub with opaque waist wrap secure while distinct adult deities laugh around her under returning daylight",
    MYTH_MATERIAL,
    "最悪 の 危機 を 笑い と ストリップ ショー で 解決 する という、 日本 神話 の 独自 性。",
)
_add(
    "large group of adult Japanese deities celebrating life around Ame-no-Uzume",
    "Warm low wide view: Uzume steps down from the tub smiling while laughing elders, drummers, helpers, and roosters gather in an irregular circle, faces emphasizing humor, relief, and renewed life",
    MYTH_MATERIAL,
    "厳粛 さ より も ユーモア と 生命 力 を 重んじる、 古代 人 の おおらか さ を 感じ ます。",
)
_add(
    "exactly four adult Japanese viewers discussing Ame-no-Uzume's dance",
    "Close conversational group: four distinct mature viewers face one another around the empty wooden tub, each showing a different thoughtful, amused, surprised, or skeptical expression with open empty hands",
    MYTH_MATERIAL,
    "皆さん は この アメノウズメ の 破格的 な 踊り について、 どう 感じ ました か。",
)
_add(
    "exactly four adult Japanese viewers offering different opinions",
    "Eye-level discussion frame: four distinct adults take turns speaking and listening with open attached palms around one empty center gap, their varied expressions inviting a response without cards, writing, icons, devices, or signs",
    MYTH_MATERIAL,
    "是非 コメント 欄 で、 皆さん の 自由 な ご 意見 を お 聞かせ ください。",
)
_add(
    "exactly four adult Japanese production storytellers",
    "Warm candid group portrait: four distinct adult storytellers sit around a plain low wooden table sharing amused reactions to several face-down blank unmarked paper sheets, with natural laughter and attentive eye-lines",
    MYTH_MATERIAL,
    "チーム 一同、 楽しく コメント を 読ま せ て 頂いて おります。",
)
_add(
    "exactly one adult Japanese storyteller host",
    "Friendly chest-up host portrait: one mature storyteller looks directly toward the viewer with a warm restrained smile and both open attached hands held near the chest in a polite request gesture; no thumbs-up icon, bell, text, device, logo, or sign",
    MYTH_MATERIAL,
    "面白い と 感じて 頂け たら、 チャンネル 登録 と 高評価 を お願い します。",
)
_add(
    "exactly four adult Japanese production storytellers",
    "Wide working group: four distinct adults arrange blank image boards, a plain bronze mirror prop, and braided rope on one low wooden table while exchanging encouraged smiles, all hands attached and all surfaces unmarked",
    MYTH_MATERIAL,
    "皆さん の 応援 が、 いつも 動画 制作 の 大きな 励み に なって います。",
)
_add(
    "exactly one adult male Japanese storm deity Susanoo",
    "Long-lens exile view: Susanoo walks alone away from the bright deity council toward a descending mountain path, shortened beard, plain earth-blue clothing, and one small cloth bundle marking his banishment",
    MYTH_MATERIAL,
    "さて、 全て の 原因 を 作った スサノオ は、 天上 界 から 追放 され ました。",
)
_add(
    "exactly one adult male Japanese storm deity Susanoo after non-graphic punishment",
    "Tight three-quarter descent portrait: Susanoo's shortened uneven beard, intact closely trimmed fingernails, lowered eyes, and weathered face show humiliation as he steps onto earthly ground; no blood, wound, blade, torn skin, or severed part",
    MYTH_MATERIAL,
    "ヒゲ と 爪 を 剥がされる という 屈辱 的 な 罰 を 受け、 地上 へ と 降り立ち ます。",
)
_add(
    "exactly one adult male Japanese storm deity Susanoo",
    "Wide coastal arrival: Susanoo stands on a wild southeastern Korean shoreline of dark rock, green ridge, and blue-grey sea after descending through storm cloud, with no settlement, label, map, sign, or modern object",
    MYTH_MATERIAL,
    "彼 が 落ちて きた の は、 新羅 の 曾尸茂梨 と 呼ばれる 場所 でした。",
)
_add(
    "landscape-only ancient Korea Strait, zero people",
    "High oblique natural view across two wild coastlines separated by blue-grey sea: exactly one complete archaic wooden boat with curved plank hull and one small square fiber sail occupies the central foreground water; no map, border, arrow, label, compass, writing, city, or modern object",
    OBJECT_MATERIAL,
    "ここ で 日本 神話 に、 突然 韓半島 の 地名 が 登場 する の です。",
)
_add(
    "object-only mysterious ancient connection evidence, zero people",
    "Strict overhead on full-frame charcoal cloth: one closed face-down blank plant-fiber record bundle tied with brown cord lies at left; one small plain archaic wooden boat model lies at right; both objects are separated and fully visible",
    OBJECT_MATERIAL,
    "古代 日本 と 韓半島 の 深い 繋がり を 示す、 非常に ミステリアス な 記録。",
)
_add(
    "exactly one adult male Japanese storm deity Susanoo",
    "Extreme emotional head-and-shoulders shore portrait: Susanoo's weathered mature face, focused storm-dark eyes, shortened beard, and wild black hair fill eighty percent of the frame against blurred surf, signaling the unknown deeds ahead; both hands and every weapon remain outside the crop",
    MYTH_MATERIAL,
    "天上界 の 問題児 は、 地上 で 一体 どんな 活躍 を 見せる の でしょう か。",
)
_add(
    "exactly one adult male Japanese storm deity Susanoo facing one eight-headed serpent",
    "Extreme-wide confrontation at storm dusk: Susanoo's unarmed full silhouette stands on the far left shore while exactly eight complete giant serpent heads rise at right in two clear staggered rows of four, each head attached to its own visible neck joining one massive scaled body across the river",
    MYTH_MATERIAL,
    "次回、 スサノオ が 新羅 を 経て ヤマタノオロチ と 激突 する 伝説 に 迫り ます！",
)


CH3_EP11_AMANOIWATO_COMMON_NEGATIVES = (
    "wrong recurring Amaterasu portrait",
    "generic neutral standing portrait",
    "repeated identical person",
    "cloned face",
    "readable writing",
    "Japanese letters",
    "runes",
    "numbers",
    "caption",
    "speech bubble",
    "musical note",
    "question mark",
    "exclamation mark",
    "lightbulb",
    "interface icon",
    "map label",
    "map border",
    "diagram",
    "scroll text",
    "logo",
    "watermark",
    "modern object",
    "Edo costume",
    "kimono",
    "samurai armor",
    "tiled roof",
    "torii gate",
    "monochrome sepia",
    "heavy brown wash",
    "dirty yellow color cast",
)


CH3_EP11_AMANOIWATO_EXTRA_NEGATIVES: dict[str, tuple[str, ...]] = {
    "前回 は、 暴風 の 神 スサノオ の 凄惨 な 悪行 を お 話 しました。": (
        "woman",
        "female person",
        "second person",
        "extra person",
        "couple",
        "romance",
    ),
    "暴力 や 武力 では、 閉ざされた 女神 の 心 を 開く こと は できない の です。": (
        "steel",
        "silver steel",
        "katana",
        "modern sword",
        "complete sword",
        "ornate hilt",
    ),
    "そして 彼女 の 代わり と なる、 美しい 鏡 を 作り出す こと でした。": (
        "glass mirror",
        "framed mirror",
        "standing mirror",
        "wall mirror",
        "landscape reflection",
        "house reflection",
        "outdoor background",
        "building",
        "tower",
    ),
    "次に 鍛冶屋 の 神様 に 命じて、 太陽 を 模した 巨大 な 鏡 を 作らせ ます。": (
        "steel anvil",
        "horned anvil",
        "metal hammer",
        "modern forge",
        "industrial tool",
    ),
    "八咫鏡 と 呼ばれる この 鏡 は、 日本 の 三種の神器 の 一つ と なります。": (
        "shield",
        "center hole",
        "center boss",
        "raised relief",
        "ornamental swirl",
        "glass mirror",
        "framed mirror",
        "outdoor background",
        "building",
        "tower",
    ),
    "八尺瓊勾玉 と 呼ばれる これ も また、 天皇家 に 伝わる 宝物 です。": (
        "round bead",
        "spherical bead",
        "pearl necklace",
        "modern necklace",
        "house",
        "building",
        "tower",
        "outdoor background",
    ),
    "神々 は 一丸 と なって、 宇宙 の 闇 を 打ち破る 計画 を 進めた の です。": (
        "table",
        "dining table",
        "meal",
        "food",
        "bowl",
        "chair",
        "stool",
        "seated diner",
    ),
    "彼ら は 太陽 の 女神 を 褒め称える ため に、 壮大 な 祝詞 を 読み上げ ました。": (
        "cup",
        "bowl",
        "drinking",
        "toast",
        "raised vessel",
        "hand",
        "arm",
        "shoulder",
        "scroll",
        "writing",
    ),
    "美しい 言葉 で 飾られた 祈り の 儀式 が、 暗闇 の 中 に 響き渡り ます。": (
        "stele",
        "monument",
        "plaque",
        "tablet",
        "inscription",
        "carved writing",
        "cup",
        "bowl",
    ),
    "そして その 桶 の 上 に 飛び乗る と、 激しく 足 を 踏み鳴らし 始め ます。": (
        "second person",
        "second pair of legs",
        "third foot",
        "fourth foot",
        "extra leg",
        "extra foot",
    ),
    "彼女 は 伏せた 桶 の 上 に 乗り、 ドンドン と 激しく 踏み鳴らし て 踊り 始め ました。": (
        "second person",
        "second pair of legs",
        "third foot",
        "fourth foot",
        "extra leg",
        "extra foot",
    ),
    "神聖 な 儀式 の ど 真ん中 で 行われた、 衝撃 的 な ストリップ ショー です。": (
        "plaque",
        "sign",
        "inscription",
        "shrine gate",
        "cave door",
        "tree",
        "timber post",
        "timber frame",
        "perch",
        "altar",
    ),
    "世界 が 滅亡 する かも しれない 深刻 な 状況 で、 最も エロティック で ユーモラス な 踊り。": (
        "plaque",
        "sign",
        "inscription",
        "shrine gate",
        "cave door",
    ),
    "自分 が 隠れた せい で、 世界 は 真っ暗 な 闇 に 包まれて いる はず だ。": (
        "daylight",
        "white sky",
        "bright blue sky",
        "sunny landscape",
        "pastoral daylight",
    ),
    "ところが 外 から 聞こえて くる の は、 楽し そう な 音楽 と 凄まじい 笑い声 です。": (
        "foreground person",
        "second foreground person",
        "foreground man",
        "companion inside cave",
        "two foreground adults",
        "empty exterior",
    ),
    "アマテラス は 隙間 から 外 を 覗き込み、 ウズメ に 向かって 問いかけ ました。": (
        "full body",
        "standing portrait",
        "visible torso",
        "open cave entrance",
        "wide landscape",
    ),
    "私 が い なくて 世界 は 暗闇 なのに、 なぜ あなた は 踊り、 神々 は 笑って いる の です か。": (
        "full body",
        "standing portrait",
        "visible torso",
        "open cave entrance",
        "wide landscape",
    ),
    "それ を 聞いた アマテラス は、 激しい プライド を 刺激 され ました。": (
        "male face",
        "beard",
        "mustache",
        "masculine jaw",
        "full body",
        "standing portrait",
    ),
    "太陽 の 女神 である 自分 より も、 素晴らしい 神 が いる はず が ない。": (
        "full body",
        "standing portrait",
        "complete mirror",
        "rectangular mirror",
        "mirror frame",
        "mirror stand",
    ),
    "彼女 は 隙間 から 外 を 覗き、 なぜ 皆 笑って いる の か と 尋ね ました。": (
        "full body",
        "standing portrait",
        "visible torso",
        "open cave entrance",
        "wide landscape",
    ),
    "ウズメ は、 あなた 様 より も 美しい 神 が 現れた から だ と 嘘 を つき ます。": (
        "full body",
        "standing portrait",
        "mirror",
        "mirror frame",
        "mirror stand",
        "neutral expression",
    ),
    "プライド を 刺激 された 太陽 神 は、 その 姿 を 見よう と さらに 身 を 乗り出し ます。": (
        "pointing away",
        "raised empty palm",
        "neutral standing portrait",
        "detached hand",
    ),
    "暗闇 を 徘徊 して いた 恐ろしい 悪霊 たち は、 光 に 焼かれて 消滅 しました。": (
        "human silhouette",
        "upright person",
        "human face",
        "human torso",
        "standing man",
        "standing woman",
    ),
    "また、 この 時 使われた 八咫鏡 と 八尺瓊勾玉 は 非常に 重要 です。": (
        "second mirror",
        "round bead",
        "spherical bead",
        "pearl necklace",
        "outdoor ground",
        "landscape",
        "plant",
    ),
    "これら は 後 に、 天皇家 の 証 で ある 三種の神器 と して 受け継がれ ます。": (
        "crown",
        "second mirror",
        "round bead",
        "spherical bead",
        "pearl necklace",
        "missing sword",
        "missing blade",
        "vase",
        "jar",
        "bottle",
        "pottery vessel",
        "outdoor ground",
        "landscape",
        "plant",
    ),
    "暗闇 に 乗じて 騒いで いた 悪霊 たち は、 太陽 の 光 に 焼かれて 消滅 します。": (
        "human silhouette",
        "upright person",
        "human face",
        "human torso",
        "standing figure",
        "ground shadow person",
    ),
    "ここ で 日本 神話 に、 突然 韓半島 の 地名 が 登場 する の です。": (
        "missing boat",
        "empty sea",
        "modern ship",
        "steamship",
        "map",
        "map label",
    ),
    "古代 日本 と 韓半島 の 深い 繋がり を 示す、 非常に ミステリアス な 記録。": (
        "open book",
        "open codex",
        "upright page",
        "printed page",
        "readable writing",
        "modern book",
    ),
    "天上界 の 問題児 は、 地上 で 一体 どんな 活躍 を 見せる の でしょう か。": (
        "sword",
        "katana",
        "steel blade",
        "weapon",
        "full body",
        "standing portrait",
    ),
    "次回、 スサノオ が 新羅 を 経て ヤマタノオロチ と 激突 する 伝説 に 迫り ます！": (
        "one head",
        "two heads",
        "three heads",
        "four heads",
        "five heads",
        "six heads",
        "seven heads",
        "missing head",
        "modern katana",
    ),
}
