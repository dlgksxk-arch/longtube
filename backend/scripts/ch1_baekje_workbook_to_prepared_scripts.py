from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import resolve_project_dir  # noqa: E402
from app.services.llm.script_quality import inspect_script_quality  # noqa: E402
from app.services.llm.visual_policy import (  # noqa: E402
    apply_script_visual_policy,
    normalize_cut_image_prompt,
)
from app.tasks.pipeline_tasks import (  # noqa: E402
    _filter_prepared_script_quality_issues,
    _validate_prepared_script,
)
from scripts.ch2_europe_workbook_to_prepared_scripts import (  # noqa: E402
    _load_xlsx_workbook,
)


DEFAULT_WORKBOOK = Path(
    r"Z:\HDD2\longtube\CH1 10분역공\2. 삼한시대\백제사\백제사_01-40화_6000컷_통합대본_최종검수완료.xlsx"
)
TEMPLATE_PROJECT_ID = "f60d6b0b"
DEFAULT_OUTPUT_DIR = resolve_project_dir(
    TEMPLATE_PROJECT_ID,
    {"channel": 1, "youtube_channel": 1},
    create=False,
) / "prepared_scripts"

EXPECTED_SHEETS = tuple(f"{episode:02d}화" for episode in range(1, 41))
EXPECTED_HEADERS = ("컷번호", "숏츠태그", "대사", "이미지프롬프트")
VARIETY_CAPTION_HEADERS = (
    "한국식 예능 자막 (전 컷 수록)",
    "한국식 예능 자막",
)
EXPECTED_CUTS_PER_EPISODE = 150
LEGACY_SOURCE_SHA256 = "AA6F37C166B4F135823201FA5EBBC6855C2F6F1202BE0D117844096DE7C1339C"
FINAL_REVIEW_SOURCE_SHA256 = "B99193FE2645311E0CD6DF39309E029467D42BE4645830B5797C6DB7710EA137"
FINAL_REVIEW_CONTENT_SHA256 = "E5A5FFD8D4F95F1A52563049F286DAD3E8F2F4877AECF65A2B161B9B6F145067"
SOURCE_CONTRACTS: dict[str, dict[str, Any]] = {
    LEGACY_SOURCE_SHA256: {
        "schema": "baekje-integrated-v1",
        "cleaned_prompt_count": 5850,
        "shorts_cut_count": 2321,
    },
    FINAL_REVIEW_SOURCE_SHA256: {
        "schema": "baekje-final-review-v1",
        "cleaned_prompt_count": 0,
        "shorts_cut_count": 2293,
    },
}
SOURCE_CONTENT_CONTRACTS: dict[str, dict[str, Any]] = {
    FINAL_REVIEW_CONTENT_SHA256: SOURCE_CONTRACTS[FINAL_REVIEW_SOURCE_SHA256],
}
SHORTS_MARKER_RE = re.compile(r"^#([1-9]\d*)-([1-9]\d*)$")
CJK_RE = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]")
PROMPT_CONTEXT_RE = re.compile(
    r"\s*Setting:\s*.*?\s*"
    r"Narration beat for visual context only:\s*.*?\s*"
    r"(?=Korean historical-documentary image\b)",
    re.DOTALL,
)

_ANCIENT_BAEKJE_STYLE_CLAUSE = (
    "Ancient Korean historical drama, cautious early Baekje and Goguryeo material "
    "culture, plain woven garments, timber and packed-earth architecture where relevant, "
    "realistic people, restrained tension, clear staging,"
)
_PUNGNAP_ARCHAEOLOGY_STYLE_CLAUSE = (
    "Present-day South Korean archaeological documentary, Pungnap Toseong earthworks "
    "and excavated features treated as physical evidence, realistic contemporary site "
    "conditions, restrained factual staging,"
)
_NO_MODERN_OBJECTS_CLAUSE = "no modern objects, no readable text"
_PUNGNAP_ARCHAEOLOGY_OBJECT_CLAUSE = (
    "no anachronistic fantasy props, no readable text"
)

# The workbook has only four columns. Rows 6-8 are episode-wide metadata; there
# are no cut-level period/place/culture columns. EP01 rows 115-123 explicitly
# switch to modern Seoul and archaeological evidence, so these source rows are
# guarded here instead of being silently forced back into the foundation era.
_EP01_PUNGNAP_ARCHAEOLOGY_SOURCES: dict[int, tuple[str, str, str]] = {
    106: (
        "문헌이 서로 엇갈릴 때, 땅속에서 나온 흔적은 또 다른 시간표를 보여주죠.",
        "ancient manuscripts fade into an archaeological view of Pungnap earthen "
        "fortress beside the Han River in modern Seoul.",
        "modern_view",
    ),
    107: (
        "서울 송파구 한강변의 풍납토성은 초기 백제 왕성 후보로 꼽히는 거대한 흙성입니다.",
        "ancient manuscripts fade into an archaeological view of Pungnap earthen "
        "fortress beside the Han River in modern Seoul.",
        "modern_view",
    ),
    108: (
        "풍납토성은 한강 수로와 넓은 평지에 맞닿아, 도읍의 조건을 실제 공간에서 보여주죠.",
        "ancient manuscripts fade into an archaeological view of Pungnap earthen "
        "fortress beside the Han River in modern Seoul.",
        "modern_view",
    ),
    109: (
        "성벽은 흙을 여러 층으로 다져 쌓았고, 한 번에 만든 작은 마을 울타리가 아니었습니다.",
        "massive rammed-earth walls of Pungnap fortress rise above the river plain, "
        "showing organized labor and defense.",
        "fortification_evidence",
    ),
    110: (
        "성 안에서는 집터와 구덩이, 가마와 방어 시설이 여러 층으로 확인됐죠.",
        "massive rammed-earth walls of Pungnap fortress rise above the river plain, "
        "showing organized labor and defense.",
        "fortification_evidence",
    ),
    111: (
        "사람이 살고 물건을 만들며, 방어선을 고쳐온 시간이 겹겹이 남은 겁니다.",
        "massive rammed-earth walls of Pungnap fortress rise above the river plain, "
        "showing organized labor and defense.",
        "fortification_evidence",
    ),
    112: (
        "이 흔적은 도시가 어느 날 갑자기 완성되지 않고 오랜 기간 커졌음을 보여줍니다.",
        "archaeologists uncover layered dwellings, pits, kilns, and defensive features "
        "inside Pungnap fortress.",
        "excavation",
    ),
    113: (
        "전승의 기원전 18년과 발굴 자료의 연대를 한 장면처럼 겹칠 수는 없고,",
        "archaeologists uncover layered dwellings, pits, kilns, and defensive features "
        "inside Pungnap fortress.",
        "excavation",
    ),
    114: (
        "풍납토성을 온조가 세운 바로 그 위례성이라고 단정할 증거도 아직 부족합니다.",
        "archaeologists uncover layered dwellings, pits, kilns, and defensive features "
        "inside Pungnap fortress.",
        "excavation",
    ),
}

_EP01_PUNGNAP_FINAL_REVIEW_PROMPT_SHA256 = {
    106: "DDA3975B5017E96DA5E2C91CFBD3DCBB51FCB46848D339D36E8BA5BAA532C5BE",
    107: "A5609FF513757300B4193AC30FAD114BE3D9233E3FC268AEF5B6DC3349D5E705",
    108: "541F72D879101AE2A4D1D5B75A94CFBE0E16A907D9A6FFE2F48CE8D9092D4802",
    109: "ED7BF5F97C3E36CFAC88C08AE3E07B0632F020B04BD4258A7E0E384B28075407",
    110: "BEEC6547DD131B34EE5F2A843303EC1F3A1CA485E101BFCA8E6613CC9E4FE2AF",
    111: "53F69427C0B1BCC9FBF0783FC92A9CDE79D13DAF3769099693B97D47D68F9BD1",
    112: "4999941C49834BDE732BAF7B14C9A5EAD489AC4D447E29F0EB3100426F564FC2",
    113: "7FB67B6D2F86D0B6C42A148D9AA62A9F12384E38DF6939EAF9500948A8AA87BF",
    114: "A4CC422BA95A93D7535DE9BC769B6BE8712C3A9452BD123571AF5185139CC0F3",
}

_EP01_PUNGNAP_ARCHAEOLOGY_FRAMING = {
    106: "low-angle tracking view centered on decisive movement",
    107: "tight profile composition with compressed background tension",
    108: "high-angle view showing the opposing groups clearly",
    109: "ground-level action view with strong foreground detail",
    110: "lateral cinematic composition showing cause and reaction",
    111: "long-lens documentary view across atmospheric distance",
    112: "overhead composition with controlled visual tension",
    113: "wide establishing shot with layered geographic depth",
    114: "low-angle tracking view centered on decisive movement",
}

# EP03 closes by previewing King Geunchogo's 371 AD northern campaign. The
# workbook exposes only episode-wide metadata (234-286 AD), so these guarded
# rows need cut-specific time/place/scene contracts instead of inheriting King
# Goi's reign. Exact narration and prompt hashes prevent an unnoticed workbook
# revision from receiving stale overrides.
_EP03_GEUNCHOGO_PREVIEW_SOURCES: dict[int, dict[str, str]] = {
    145: {
        "narration": "그 도구를 가장 공격적으로 휘두른 인물이 근초고왕입니다.",
        "prompt_sha256": "E9572892316D1E538EEFA87B29A495D4A4E440AEB051230E82ADB8BD8D2420DE",
        "location": "Baekje royal military court in the Han River basin",
        "scene": (
            "Side-lit military council in a Baekje royal hall in 371 AD: King Geunchogo "
            "leans over a low campaign table while commanders point toward the northern "
            "route with disciplined urgency. His square mature face, trimmed beard, black "
            "court cap, and deep red robe remain clearly visible; natural hands, five fingers "
            "per hand, no ceremonial relic display, no readable text. Early Korean state-formation "
            "realism, grounded materials, natural directional light, 35mm lens, cinematic 16:9."
        ),
    },
    146: {
        "narration": "다음 편에서는 근초고왕이 남부 영향권을 넓히고 북쪽으로 진격합니다.",
        "prompt_sha256": "E558C0A79A852EB9EE9C1B1BEC72B9845B9BB91B6E16AA86B287A092AEB30642",
        "location": "Baekje campaign road across the central Korean Peninsula",
        "scene": (
            "Long-lens action view in 371 AD: King Geunchogo's Baekje column advances north "
            "along a packed-earth road after consolidating southern influence, infantry and "
            "mounted messengers moving in one readable direction. Natural marching posture, "
            "correct limb count, hands gripping only reins or spear shafts, no artifact display, "
            "no map, no readable text. Early Korean state-formation realism, grounded materials, "
            "natural directional light, 35mm lens, cinematic 16:9."
        ),
    },
    147: {
        "narration": "백제군이 평양성까지 올라가자 고구려 고국원왕도 직접 맞서게 되고,",
        "prompt_sha256": "D5BDD2D93CEF40FF416F694C4BA31AEDB08D6E7D95D5930E7EBF9A33258EBBA0",
        "location": "Pyeongyang Fortress battlefield",
        "scene": (
            "Over-the-shoulder battlefield view at Pyeongyang Fortress in 371 AD: armored "
            "King Gogukwon stands on the defensive earthwork facing the approaching Baekje "
            "army in person, commanders braced beside him and formations closing below. "
            "Natural defensive posture, anatomically correct arms and hands, no diplomatic "
            "gift exchange, no artifact display, no readable text. Early Korean state-formation "
            "realism, grounded materials, natural directional light, 35mm lens, cinematic 16:9."
        ),
    },
    148: {
        "narration": "전투 한복판에서 왕이 전사하면서 두 나라의 원한은 피로 굳어집니다.",
        "prompt_sha256": "F6DA7BFC493D05A879001872B3F5FDCCEA0C8AD0A21821BBFE4D978C56046E7E",
        "location": "Pyeongyang Fortress battlefield",
        "scene": (
            "Immediate battlefield aftermath at Pyeongyang Fortress in 371 AD: King Gogukwon "
            "has fallen among his protecting soldiers while Baekje pressure continues beyond "
            "the shield line, grief and shock visible in restrained faces and body language. "
            "One coherent fallen body, anatomically correct limbs, no gore spectacle, no relic "
            "arrangement, no readable text. Early Korean state-formation realism, grounded "
            "materials, natural directional light, 35mm lens, cinematic 16:9."
        ),
    },
    149: {
        "narration": "백제가 한반도 최강국으로 솟구친 삼백칠십일년을 다음 편에서 보시죠.",
        "prompt_sha256": "4FD7183157BCAF981EBD008ACB08A98A0B07D7304DD3A26106C85CF73CF6C630",
        "location": "Baekje field command after the 371 AD Pyeongyang campaign",
        "scene": (
            "Reaction-focused victory aftermath in 371 AD: King Geunchogo and exhausted "
            "Baekje commanders look across their assembled army after the Pyeongyang campaign, "
            "the scale of military ascendancy shown through living troops and terrain rather "
            "than displayed objects. Natural stance and hands, no artifact wall, no map, no "
            "readable text. Early Korean state-formation realism, grounded materials, natural "
            "directional light, 35mm lens, cinematic 16:9."
        ),
    },
    150: {
        "narration": "근초고왕의 북진이 궁금하시다면 구독과 좋아요로 함께해 주세요.",
        "prompt_sha256": "E66608AB1ABF7080A39A772F14E508C7C3E421EEC020FC3C3FEE98166CD01181",
        "location": "Baekje northern campaign road in 371 AD",
        "scene": (
            "Final held frame of King Geunchogo leading a Baekje column north in 371 AD, "
            "his officers and soldiers moving behind him toward the distant fortified route. "
            "Clear forward motion, natural anatomy and hand placement, no title card, no text, "
            "no artifact montage. Early Korean state-formation realism, grounded materials, "
            "natural directional light, 35mm lens, cinematic 16:9."
        ),
    },
}

# EP03 image-QA preflight found dialogue/scene failures in these exact source
# rows: map or document wallpaper, literalized metaphors, stray written dates,
# and generic figures that did not show the narrated action. Guard both the
# narration and original prompt before replacing them with living-action scenes.
_EP03_DIALOGUE_QA_SOURCES: dict[int, dict[str, str]] = {
    1: {
        "narration": "왕위를 감당하기 어렵다는 이유로 어린 왕이 밀려났습니다.",
        "prompt_sha256": "828F96F1EB76267E180B692253F18BB15E818A589D7FBB9E73F97C9906F2E6E7",
        "location": "open Baekje palace yard beside a plain earthen wall",
        "scene": (
            "Side-profile view across bare earth beside a plain unmarked earthen wall. An "
            "adolescent king in a pale robe walks away alone toward the left edge, head lowered "
            "and shoulders slumped. Three senior nobles in dark robes remain together behind him "
            "and turn their backs, while one attendant indicates the outward path with an open "
            "palm. The isolated young ruler being pushed out is unmistakable. Five living actors, "
            "natural full-body posture, relaxed empty hands with five fingers, uncluttered ground. "
            "Early Korean state-formation realism, natural directional light, 50mm lens, "
            "cinematic 16:9."
        ),
    },
    18: {
        "narration": "그 뒤를 이은 고이왕은 초고왕의 동생으로 기록돼 있지만,",
        "prompt_sha256": "8896C4809583F7960A03089E1B67352612B4AD61F0EA2196FBF0553942E60F6E",
        "location": "Baekje royal court during the succession tradition",
        "scene": (
            "Living historical reconstruction against plain unmarked timber walls: King Chogo "
            "presents his younger royal brother Goi to assembled nobles, while the younger man "
            "stands one step behind and the court studies the claimed family relationship. "
            "King Goi has a square mature face, trimmed beard, black court cap, and deep red "
            "robe. Living faces, restrained gestures, natural empty hands with five fingers, "
            "and an uncluttered courtyard floor keep the family relationship dominant. Early "
            "Korean state-formation realism, grounded materials, "
            "natural directional light, 50mm lens, cinematic 16:9."
        ),
    },
    34: {
        "narration": "마한은 중국 군현의 최고 책임자를 쓰러뜨리는 전과를 올렸지만,",
        "prompt_sha256": "1B421960B6864DEE0A9FF3A84811F49438B33E748B1945537D598BC7F6A66E1D",
        "location": "open field immediately after a Mahan victory",
        "scene": (
            "Tight open-earth surrender scene. The defeated commandery governor in a fine pale "
            "official robe kneels with head bowed at center, flanked by two plain-robed Mahan "
            "escorts standing empty-handed. A Mahan commander faces him as witnesses react in the "
            "far background. The fallen status of the highest official fills the frame. Four "
            "principal living actors, correct limb count, natural kneeling posture, calm empty "
            "hands, plain earth and open sky. Early Korean state-formation realism, natural "
            "directional light, 50mm lens, cinematic 16:9."
        ),
    },
    51: {
        "narration": "주변 세력을 왕국 안으로 넣는 일은 토지만 차지한다고 끝나지 않습니다.",
        "prompt_sha256": "F25F17D3C7053C345C8CD295A53C5D5C07E17F0078C7085CA45E7671EAFDB965",
        "location": "Baekje border settlement receiving neighboring communities",
        "scene": (
            "Ground-level action beside a simple unmarked timber palisade: a neighboring local "
            "chief and two families arrive with children while Baekje officials welcome them, "
            "residents hand grain bowls to the newcomers, and guards direct people toward homes. "
            "The living work of integrating people and administration beyond occupying land is "
            "the dominant visible event. Natural anatomy, gentle hand placement, warm eye contact, "
            "plain timber surfaces and an uncluttered earth yard. Early Korean state-formation "
            "realism, natural directional light, 35mm lens, cinematic 16:9."
        ),
    },
    67: {
        "narration": "좌평은 왕 아래에서 정사를 총괄하며 귀족회의를 대표한 자리였고,",
        "prompt_sha256": "8C36D0F4D798CDAB5ADACD97ED82C36C52DED8736AD515123447A724213EB09D",
        "location": "interior of a Baekje royal council hall",
        "scene": (
            "Interior council scene against plain unmarked timber walls: the seated king listens "
            "while the Jwapyeong stands directly below him, turns toward the gathered nobles, and "
            "summarizes their decision with one calm open-hand gesture. The king, Jwapyeong, and "
            "noble council form a clear working hierarchy. Natural seated posture, anatomically "
            "normal hands with five fingers, restrained living expressions, uncluttered floor. "
            "Early Korean state-formation realism, natural directional light, 50mm lens, "
            "cinematic 16:9."
        ),
    },
    84: {
        "narration": "좌평 아래 달솔·은솔·덕솔을 비롯한 세밀한 순서를 적어 놓았습니다.",
        "prompt_sha256": "388B814D31D63113803FEBBA9EF06F69EE5A81928C73D5F3D2B563FD1A64E267",
        "location": "Baekje royal council hall",
        "scene": (
            "Wide interior view against plain unmarked timber walls: the Jwapyeong stands nearest "
            "the seated king, while Dalsol, Eunsol, Deoksol, and lower officials occupy clearly "
            "descending rows behind him. Rank is communicated only through spatial order, robe "
            "restraint, and who awaits whose instruction. Natural seated anatomy, calm empty hands, "
            "living expressions and an uncluttered hall floor. Early Korean state-formation "
            "realism, grounded materials, natural directional light, 35mm lens, cinematic 16:9."
        ),
    },
    100: {
        "narration": "규칙을 어긴 자의 신분이 높아도 처벌할 수 있어야 왕의 법이 섭니다.",
        "prompt_sha256": "D33CDC38C56B28FB815B6AF49593F83094747140B71A2185FB1EE60F57E2550D",
        "location": "Baekje royal judgment court",
        "scene": (
            "Side-lit judgment inside a bare Baekje royal hall with plain unmarked timber walls: "
            "a visibly high-ranking noble in a "
            "fine robe kneels before the same court as common offenders while two guards escort "
            "him and King Goi watches the law being enforced without exception. The noble's loss "
            "of privilege is the dominant action. Four living actors, correct limb count, natural "
            "kneeling posture, empty hands visible and anatomically normal, uncluttered floor. "
            "Early Korean state-formation realism, grounded materials, natural directional light, "
            "50mm lens, cinematic 16:9."
        ),
    },
    117: {
        "narration": "국가는 한 왕의 명령 한 번으로 완성되는 기계가 아니며,",
        "prompt_sha256": "887E795404FA65CDE43C8FB2E205C1CDEC22F235A5FCEA662379761171B131D5",
        "location": "working Baekje royal administrative courtyard",
        "scene": (
            "Over-the-shoulder view from behind King Goi across a plain unmarked earth courtyard: "
            "one official coordinates grain distribution, another organizes guards, "
            "and a messenger departs while residents continue their duties. The simultaneous "
            "human systems show a state being built through sustained administration over time. "
            "Natural anatomy, purposeful relaxed hands, plain timber walls, active living workers "
            "and an uncluttered ground. Early Korean state-formation realism, natural directional "
            "light, 35mm lens, cinematic 16:9."
        ),
    },
    133: {
        "narration": "고이왕의 진짜 무기는 칼 한 자루가 아니라 명령의 사슬이었으며,",
        "prompt_sha256": "0FE9F6EA0DA94E60577D8F9138C1B6418717DDA995D8200F6600BDE4B322AE70",
        "location": "Baekje royal command courtyard",
        "scene": (
            "Lateral cinematic view across a plain open Baekje command ground: King Goi speaks "
            "to a senior official, the senior official turns and repeats the order to a waiting "
            "messenger, and the empty-handed messenger runs toward a disciplined formation that "
            "immediately begins moving. The human relay and synchronized reaction dominate the "
            "frame. King Goi has a square mature face, trimmed beard, black court cap, and deep red "
            "robe. Four principal living actors, empty hands, natural arms and five fingers, plain "
            "earth and timber surfaces. Early Korean state-formation realism, natural directional "
            "light, 35mm lens, cinematic 16:9."
        ),
    },
}

# Full-frame QA after all 150 EP03 images completed found additional rows where
# the source prompt was compiled as an object-only still life, rendered fake
# writing/dates, or failed to show the narrated relationship. Each correction
# is locked to the exact narration and original source-prompt SHA-256.
_EP03_FULL_FRAME_QA_SOURCES: dict[int, dict[str, str]] = {
    4: {
        "narration": "뇌물을 받은 관리는 세 배를 물어내고 평생 벼슬길까지 막히게 되며,",
        "prompt_sha256": "9620740EEDFF4BE1FC0C6F362AE45628B2E7F5B8DC25513524014830A2AD384A",
        "location": "bare Baekje judgment courtyard",
        "action": (
            "A convicted official kneels before King Goi while three witnesses return confiscated "
            "grain sacks to the court and two guards turn the disgraced official away from the line "
            "of serving officials. The repayment and permanent exclusion are visible in one action."
        ),
    },
    5: {
        "narration": "느슨한 연맹의 왕은 마침내 명령을 집행하는 국가의 왕으로 변합니다.",
        "prompt_sha256": "67BDFB94234D11E8DA8EB0FF1AF7474EC51CB62C8CB926F2124CE3AE40BC6235",
        "location": "open Baekje command courtyard",
        "action": (
            "King Goi gives one calm order to a senior official, who immediately relays it to a "
            "messenger while an ordered guard formation begins moving together. The visible chain "
            "of execution replaces the earlier loose gathering of chiefs."
        ),
    },
    14: {
        "narration": "그의 즉위부터 이미 평범한 계승과는 거리가 멀었습니다.",
        "prompt_sha256": "20E100638F245CD2862E03885836CDC1BC1F889DCD71670209C5917228F15E8F",
        "location": "plain Baekje royal courtyard",
        "action": (
            "King Goi takes the central place while three tense senior nobles exchange guarded "
            "looks and the displaced young ruler is escorted away in the far left background. "
            "The contested, unusual succession is unmistakable."
        ),
    },
    15: {
        "narration": "어린 왕의 폐위와 새 왕의 등장은 권력 개편의 시작을 알렸죠.",
        "prompt_sha256": "F5E370268206CCAC788FA4BE477A30C3D0F83E7788AF09CC4F3F962126A49505",
        "location": "open Baekje palace yard",
        "action": (
            "At left, the adolescent former king walks out with one attendant; at right, King Goi "
            "steps forward to receive the bows of three nobles whose positions visibly shift toward "
            "him. The departure and new accession share one coherent living scene."
        ),
    },
    16: {
        "narration": "고이왕 앞에 있던 사반왕은 백제의 제칠대 왕으로 전해집니다.",
        "prompt_sha256": "BA44F770BD0E5975CD1122760049BC0E428F8047C6C5EF26931421317E62D051",
        "location": "plain Baekje succession courtyard",
        "action": (
            "The young King Saban sits at center while two senior attendants stand behind him and "
            "the future King Goi waits several steps away among the nobles. Human placement alone "
            "shows Saban immediately preceding Goi."
        ),
    },
    17: {
        "narration": "그러나 나이가 어려 정사를 감당하지 못한다는 이유로 곧 왕위에서 밀려났죠.",
        "prompt_sha256": "9D160E9776BED9F475001FC36A1A73DCDB03AA464ACF2C578B7B3D3D880F4916",
        "location": "bare Baekje audience yard",
        "action": (
            "An adolescent ruler rises uncertainly as three older nobles turn away from him and one "
            "attendant gently guides him toward the open exit. The young ruler's isolation and "
            "removal dominate the frame."
        ),
    },
    20: {
        "narration": "온조계와 다른 비류계 세력이 왕권을 잡았다는 해석도 나왔고,",
        "prompt_sha256": "D4237A7064F9B1678E381FBEAF968B2D90059F66FBA42712B71A1A99B161004C",
        "location": "plain Baekje council courtyard",
        "action": (
            "Two rival noble groups face each other across bare ground while King Goi stands between "
            "them and the Biryu-aligned elders step closer to the royal position. Competing lineage "
            "interpretations are conveyed only by people, distance, and eye-lines."
        ),
    },
    24: {
        "narration": "새 왕에게 필요한 것은 한 번의 위협보다 오래 작동할 질서였습니다.",
        "prompt_sha256": "2D40327C7409284B4F1FDEC8E739F013D0C8647DAB41FC17FE5D129CEBF689F3",
        "location": "working Baekje administrative courtyard",
        "action": (
            "King Goi watches three coordinated routines continue at once: an official directs "
            "workers, a messenger receives an order, and guards rotate into formation. Repeated "
            "human routines show durable order rather than a single threat."
        ),
    },
    26: {
        "narration": "전쟁이 벌어져도 군사를 모으는 속도와 방향부터 엇갈릴 수 있었습니다.",
        "prompt_sha256": "B705282101C74504C2BA3AD5BB9293DC296892EC95FB73D3D673E84A4A30D204",
        "location": "open Baekje mustering field",
        "action": (
            "Three local chiefs pull separate groups of soldiers toward different directions while "
            "a royal messenger tries to bring them into one route. Conflicting movement and delayed "
            "assembly are readable before any clash begins."
        ),
    },
    28: {
        "narration": "기존 족장의 권위를 관등과 직책 속에 묶어 통제하기 시작합니다.",
        "prompt_sha256": "B0FDD66690B29C955122C85BCD96E3C72EE6DA6964EC35F6CE29DC4C532F3E0C",
        "location": "plain Baekje appointment courtyard",
        "action": (
            "King Goi assigns three former local chiefs fixed places in an ordered line beneath one "
            "senior royal official. Each chief turns from his own followers toward the king's chain "
            "of command, making controlled authority visible."
        ),
    },
    38: {
        "narration": "백제를 연맹의 한 구성원에서 새로운 중심 세력으로 끌어올립니다.",
        "prompt_sha256": "8CC4D69F5870F9F1137DB67440662C4FB7CB0F05CF9DFCB188A8186C7F389B6C",
        "location": "open Mahan alliance assembly ground",
        "action": (
            "King Goi and an ordered Baekje delegation move from the edge into the center of a ring "
            "of regional leaders, who turn their attention toward him. Human movement visibly shifts "
            "Baekje from one member to the new center."
        ),
    },
    39: {
        "narration": "다만 어느 날 목지국을 완전히 없앴다고 단순하게 말할 수는 없습니다.",
        "prompt_sha256": "747672CBDC58B58F42D7CED044A89D78FB0F794004E5A56BC0B71D18DBAD1209",
        "location": "open settlement boundary between Baekje and Mokjiguk",
        "action": (
            "In a tight ground-level view, two Baekje officials face two Mokjiguk elders across a low "
            "natural earth ridge while adult followers stand immediately behind both sides. Both "
            "leadership groups remain active, showing gradual coexistence rather than a single-day "
            "disappearance. Frame from knees to heads; adult bodies fill the image edge to edge and "
            "completely hide the horizon. Only people and bare earth are visible. No distant background, "
            "settlement, building, built gate, architecture, plaque, inscription, banner, document, or "
            "emblem appears anywhere."
        ),
    },
    43: {
        "narration": "고구려와 중국 군현이 싸우는 동안 낙랑 변경을 공격한 기록이 남고,",
        "prompt_sha256": "11A26A767BEE9C36460AEBAEFDC48DCA7D58B891F8DE8DF904D9173363F78A77",
        "location": "Lelang frontier earthwork",
        "action": (
            "A Baekje raiding party crosses the exposed flank of a Lelang frontier earthwork while "
            "distant Goguryeo and commandery formations remain locked against each other beyond the "
            "ridge. The opportunistic frontier attack is the sole visible event."
        ),
    },
    50: {
        "narration": "세금과 창고를 누가 관리하는지가 곧 왕권의 크기를 결정했죠.",
        "prompt_sha256": "FDE64E163A9223BBB1D0DAD56D133419EB4C82200D899E5FE600D50D0054F3B2",
        "location": "working Baekje granary yard",
        "action": (
            "Farmers deliver tied grain sacks as a royal official counts each delivery, directs "
            "workers into the granary, and reports to a waiting senior officer. The people controlling "
            "collection and storage visibly extend royal power."
        ),
    },
    58: {
        "narration": "그 변화는 족장들에게 자리를 보장하는 동시에 자유를 제한했죠.",
        "prompt_sha256": "4E718D9F3991661256F876863C029E3866A3BDE9C6C38896E9E7E1040036FD3D",
        "location": "plain Baekje council yard",
        "action": (
            "Three local chiefs retain honored seats in the royal assembly but must wait for one "
            "senior official's instruction before their followers can move. Their status remains "
            "visible while their independent freedom is visibly constrained."
        ),
    },
    62: {
        "narration": "기록에 보이는 남당은 왕과 신하의 자리가 구분된 정치 회의 공간이었고,",
        "prompt_sha256": "4CBE49BD85904669506D868F6389B13981A0808EF0D04148788B3965693234C3",
        "location": "plain Baekje Namdang council hall",
        "action": (
            "The king sits alone on a slightly raised platform while the senior minister stands below "
            "and two ordered rows of nobles face both of them. Spatial separation makes the political "
            "meeting hierarchy immediately legible."
        ),
    },
    70: {
        "narration": "귀족은 좌평을 통해 국가 결정에 영향력을 남길 수 있었습니다.",
        "prompt_sha256": "5C0B3C655CE8D7DE0C3BA97020084259AC2EEF89ADD3C3CB3653260890EFB2AB",
        "location": "open bare Baekje council ground",
        "action": (
            "Three senior nobles speak with open empty hands to one senior minister, who turns toward "
            "the seated King Goi and relays their position. The king listens and responds while the "
            "nobles watch his face, making their influence through the minister visible. People fill "
            "the frame. No building, doorway, plaque, seal, document, sign, inscription, banner, "
            "emblem, or written mark appears."
        ),
    },
    71: {
        "narration": "서로를 완전히 누르지 못한 왕과 귀족이 한 자리에 묶인 셈이죠.",
        "prompt_sha256": "3FEE70D58C8F4DDB9FE5A744E5D0F80EE6D0443A96DDA73C1C45261AD00DD72A",
        "location": "open bare Baekje council ground",
        "action": (
            "King Goi and three senior nobles form one tight standing circle around a mediating senior "
            "minister. The king and nobles face one another at equal eye level while the minister keeps "
            "both sides engaged; neither side dominates or leaves. Human balance alone shows their "
            "shared political space. No literal binding, rope, pole, chain, building, doorway, plaque, "
            "seal, document, sign, inscription, banner, emblem, or written mark appears."
        ),
    },
    72: {
        "narration": "이 균형은 언제든 충돌할 수 있었지만 행정의 중심을 만드는 데 필요했고,",
        "prompt_sha256": "1D2A13A6E15ED33F3CFA01953C3468159D5D96D8B636432786139DCB684F5068",
        "location": "plain Baekje council hall",
        "action": (
            "King Goi and the Jwapyeong face a tense line of nobles; two nobles argue from opposite "
            "sides while the Jwapyeong keeps the assembly focused on one shared decision. Human tension "
            "and mediation show the unstable but necessary balance."
        ),
    },
    73: {
        "narration": "백제는 사람의 친분보다 직책이 앞서는 국가로 조금씩 이동합니다.",
        "prompt_sha256": "71C8F7DC7088F9CACC1A52391A24831479DE597138F78C79F25B60C77F8979F1",
        "location": "working Baekje administrative yard",
        "action": (
            "A senior official assigns duties to two men by their appointed positions while one "
            "personal friend waits outside the working line. The official follows role and order "
            "instead of private familiarity."
        ),
    },
    74: {
        "narration": "그다음 단계는 눈에 보이지 않던 서열을 누구나 보게 만드는 일이었고,",
        "prompt_sha256": "FDDCC81A224BAC4B51E4AB042A65B349BA8532ACB7CD527E94BFDF42F6D3815D",
        "location": "plain Baekje court assembly yard",
        "action": (
            "Five officials stand in a clearly descending line before the king, with robe color and "
            "distance from the royal position changing step by step. Onlookers immediately recognize "
            "the visible order through human placement."
        ),
    },
    77: {
        "narration": "높은 관등은 자색 계열, 그 아래는 붉은색과 푸른색 계열로 구분됐고,",
        "prompt_sha256": "980FD3671CEB9B1C648CCACA367F710D2891043EFAC158C8ADCD57CC142E028B",
        "location": "plain Baekje rank ceremony yard",
        "action": (
            "Five adult officials form one descending rank line before the king: the highest wears a "
            "deep purple cross-collar robe, the next two wear muted red robes, and the lower two wear "
            "muted blue robes. Clothing and people fill the frame."
        ),
    },
    79: {
        "narration": "말로만 높고 낮음을 정할 때는 족장마다 자기 권위를 내세울 수 있지만,",
        "prompt_sha256": "707CE83B38716113CEFDA483DBA5B7D7B76CAC166ADDD96EE73DE2E73A6EF003",
        "location": "open Baekje council ground",
        "action": (
            "Three local chiefs step forward at once, each demanding the leading place from the "
            "others while their followers cluster separately behind them. Competing personal claims "
            "create a visibly unresolved hierarchy."
        ),
    },
    80: {
        "narration": "왕이 허락한 옷을 입는 순간 서열의 기준은 왕실로 옮겨갑니다.",
        "prompt_sha256": "16A5D7C196D6218F7D07E336BA9AC00482A4B36BCF62213643C842AC61854585",
        "location": "plain Baekje royal appointment yard",
        "action": (
            "King Goi watches as a senior attendant places approved colored outer robes on three "
            "officials already standing in descending order. The officials turn toward the king, "
            "making the royal source of rank unmistakable."
        ),
    },
    81: {
        "narration": "관등은 유력자를 없애는 제도가 아니라 한 줄로 세우는 제도였고,",
        "prompt_sha256": "CE0FCFB7B0647C1F8BC82376647DAE9174D99A247AE5D05C9D592CF7C58D0C40",
        "location": "open Baekje court assembly yard",
        "action": (
            "Formerly separate powerful chiefs remain alive and respected but now stand in one "
            "unbroken descending line before King Goi. Their individual faces remain distinct while "
            "the royal order controls their positions."
        ),
    },
    83: {
        "narration": "후대 기록은 백제에 모두 열여섯 관등이 있었다고 전하며,",
        "prompt_sha256": "FD5CFAC643C56E8FFBDBBD2AB59641A8BDBF5EE09C262487DDDE816E830DD742",
        "location": "plain Baekje court assembly yard",
        "action": (
            "A broad living reconstruction shows sixteen adult officials arranged in four visibly "
            "descending rows before the king. Spacing, posture, and restrained robe colors convey the "
            "later tradition of a complete rank system."
        ),
    },
    86: {
        "narration": "고이왕대에는 좌평과 솔급 같은 핵심 틀이 마련됐고,",
        "prompt_sha256": "FF26B30C354CAC2484DE52E80CC1D16CB1F223C8BE95AEEDACFAB9A9FA82E986",
        "location": "plain Baekje royal council yard",
        "action": (
            "A seated King Goi watches one older court adviser quietly explain civil duties to three "
            "younger court clerks standing in one lower row. The adviser stands closest to the king; "
            "the three clerks listen with both open empty hands visible. Their positions alone show "
            "the first core framework of higher and lower civil offices. This is a peaceful civilian "
            "meeting. Every person is unarmed; no sword, spear, bow, armor, shield, guard, soldier, "
            "warrior, fighting stance, or military formation appears."
        ),
    },
    88: {
        "narration": "그러므로 이 장면의 핵심은 명칭 열여섯 개를 외우는 데 있지 않고,",
        "prompt_sha256": "DCD4899BFC81B77EEA540097FBF04FFD3320AA60E7E4092CEF9F91E79EFD33DF",
        "location": "open bare Baekje rank assembly ground",
        "action": (
            "Six adult officials move from separate loose clusters into one ordered descending line "
            "before King Goi while one senior minister guides their positions with empty hands. The "
            "functioning human hierarchy, not memorized labels, fills the frame. Only people and bare "
            "earth are visible. No pot, jar, vessel, artifact, display, plaque, sign, inscription, "
            "document, emblem, symbol, or written mark appears."
        ),
    },
    90: {
        "narration": "옷 색 하나가 개인의 체면과 정치적 생존을 동시에 결정하기 시작했죠.",
        "prompt_sha256": "56A6521BF8326EA556023D16418B44A43C1CFC000029E958B8B33864307E1374",
        "location": "plain Baekje court yard",
        "action": (
            "A demoted official in a pale robe stands apart with lowered head while higher officials "
            "in purple, red, and blue pass him toward the king. His social shame and political exclusion "
            "are visible through clothing and human reactions."
        ),
    },
    91: {
        "narration": "서열을 정했다면 그다음에는 관리가 지켜야 할 선을 정해야 했습니다.",
        "prompt_sha256": "A1214382ABDAC3BA99A8C9636C5D4823E22A6FE21CB6D76151496D447020A9BD",
        "location": "working Baekje tax courtyard",
        "action": (
            "A senior official stops a tax collector from diverting a farmer's grain sack and directs "
            "it back into the public delivery line while two witnesses watch. The boundary of official "
            "conduct is shown through one clear intervention."
        ),
    },
    93: {
        "narration": "죄를 지은 관리는 받은 것의 세 배를 배상하도록 했습니다.",
        "prompt_sha256": "92A3AE5577D68338AEBFF7BD73B68B8A868A3A9E6365398FC9B2FD06FAD0A025",
        "location": "bare Baekje judgment courtyard",
        "action": (
            "A convicted official kneels empty-handed while exactly three separate adult laborers "
            "stand side by side behind him, each laborer holding one large tied grain sack. Exactly "
            "three sacks are clearly visible, no more and no fewer. The harmed farmer and one senior "
            "official face the three laborers, making the threefold repayment unmistakable."
        ),
    },
    94: {
        "narration": "재산만 돌려주고 끝나는 것도 아니어서 평생 벼슬길이 막힐 수 있었죠.",
        "prompt_sha256": "4C28BEC0D076A37F5E0242D2E4620D99AB5A6D09C9FE033C9527B5F8BE78E27D",
        "location": "open Baekje court exit",
        "action": (
            "At left, one pale-robed disgraced former official walks away with lowered head between "
            "two escorts. At right, three serving officials keep their backs turned to him and remain "
            "facing the seated king. The lone departure and the stationary royal line move in opposite "
            "directions, making permanent exclusion visible. Nobody marches toward the camera."
        ),
    },
    95: {
        "narration": "왕의 이름으로 세금을 거두는 관리가 사익을 챙기면,",
        "prompt_sha256": "97CCE36E072155403380A608C8DCBE0053E001CEAE405E30214F06788EDA3C0C",
        "location": "working Baekje tax collection yard",
        "action": (
            "A tax collector secretly pulls one grain sack from the royal delivery line toward his "
            "own side while a farmer notices and a supervising official turns to confront him. The "
            "private diversion is the immediate living action."
        ),
    },
    97: {
        "narration": "부패 처벌은 도덕 훈계가 아니라 새 행정체제를 지키는 안전장치였고,",
        "prompt_sha256": "7AC3191E0B55137A8AFDB9C15DE9B7C9FC76E45113F5ED5E63A676EFA4ED7900",
        "location": "working Baekje administrative yard",
        "action": (
            "At left, two escorts lead one pale-robed corrupt collector away with his head lowered. "
            "At right, three honest civilian officials keep receiving grain sacks from farmers without "
            "turning toward the removal. The two actions are clearly separated but simultaneous: "
            "punishment removes one offender while the protected administration continues working."
        ),
    },
    99: {
        "narration": "기록과 창고, 징세가 늘어날수록 감시할 규칙도 더 필요해졌으며,",
        "prompt_sha256": "C4C4B5ABE5974C21CCE9B304374522209FC4EDC9513722FA2913BB6C7F1B2C97",
        "location": "busy Baekje granary yard",
        "action": (
            "Three officials cross-check incoming grain by voice and hand signals while workers move "
            "sacks into separate storage bays and one supervisor watches both lines. Growing work and "
            "growing oversight are shown entirely through people."
        ),
    },
    101: {
        "narration": "실제로 모든 귀족이 똑같이 처벌됐는지는 확인할 수 없지만,",
        "prompt_sha256": "85D315DD78D399A047F85D81DC683DFD5CEC8F81DE29448369E5A9B7A4FBB0B0",
        "location": "open bare Baekje judgment ground",
        "action": (
            "Two accused nobles stand before one senior judge. At left, one pale-robed noble lowers "
            "his head between two escorts; at right, another similarly accused noble remains protected "
            "inside a tense group of powerful peers while the judge hesitates between them. The contrast "
            "shows that equal punishment cannot be confirmed. People fill the frame. No building, "
            "doorway, plaque, seal, document, sign, inscription, banner, emblem, or written mark appears."
        ),
    },
    102: {
        "narration": "그런 조항이 기록됐다는 사실만으로도 국가가 원하는 관리상이 보입니다.",
        "prompt_sha256": "A5E863F756A933D8D22C8E9D706F8E0B102A7ABCCE24D900376D1D9DFE441D86",
        "location": "plain Baekje appointment courtyard",
        "action": (
            "A senior official selects one restrained candidate who returns a farmer's dropped grain "
            "sack while rejecting another candidate reaching for private gain. The state's desired "
            "official is revealed through observed conduct."
        ),
    },
    103: {
        "narration": "족장의 충성보다 직무의 책임을 앞세우는 방향이 선명해졌고,",
        "prompt_sha256": "EA8AE35602B15D4DCFD954FDC2E36657B69AF1F1536295170393F911854E3371",
        "location": "working Baekje administrative courtyard",
        "action": (
            "An official leaves his former local chief waiting and turns instead to complete the "
            "public task assigned by the royal supervisor. Duty, residents, and the working line "
            "occupy the center while personal loyalty remains at the edge."
        ),
    },
    104: {
        "narration": "백제의 통치는 사람을 믿는 단계에서 제도로 묶는 단계로 넘어갑니다.",
        "prompt_sha256": "81EC16FE1792AA6D357C592053E4E8A326C97B6FE39139ECD0187774513B5625",
        "location": "open bare Baekje administrative ground",
        "action": (
            "A senior official receives one civil duty from King Goi, passes it to two ranked officials, "
            "and those officials immediately direct waiting messengers and grain workers. A former local "
            "chief stands outside the ordered working line. Repeated human roles show rule moving from "
            "personal trust to a lasting institution. No rope, chain, binding, ritual object, building, "
            "doorway, plaque, seal, document, sign, inscription, banner, emblem, or written mark appears."
        ),
    },
    105: {
        "narration": "하지만 교과서처럼 익숙한 한 가지 설명에는 큰 함정이 남아 있었죠.",
        "prompt_sha256": "3A81E1A153A8738A734A9D10F58D5D4069C56ED5E655B0CF20EDF74FFDA19F7C",
        "location": "plain Baekje council courtyard",
        "action": (
            "Two senior historians in period court dress disagree before a reconstructed council: "
            "one points to a fully formed six-part hierarchy while the other separates an earlier "
            "single senior role from later officials. Their disagreement exposes the trap."
        ),
    },
    106: {
        "narration": "흔히 고이왕이 여섯 좌평의 업무를 모두 완성했다고 설명합니다.",
        "prompt_sha256": "33493485480D681A59AF88D2A5757157C16379040219CFD3162B2E76BC52D04F",
        "location": "plain Baekje royal council yard",
        "action": (
            "King Goi faces six senior officials arranged as a seemingly complete set while a later "
            "observer studies the scene with visible caution. The familiar claim is reconstructed as "
            "a human hierarchy rather than presented as settled fact."
        ),
    },
    108: {
        "narration": "하지만 그 체계는 훨씬 뒤 사비시대의 제도를 앞당겨 본 것일 수 있습니다.",
        "prompt_sha256": "2274D171C4EAC4DC384BDC188507C129486C0834E97F77B1ACE6F83E85C33DD3",
        "location": "plain comparative Baekje council ground",
        "action": (
            "At left, King Goi works with one senior minister; at right, a later Sabi-period king "
            "commands six specialized senior officials. Clear human separation shows that the fuller "
            "later system may have been projected backward."
        ),
    },
    110: {
        "narration": "왕 아래에서 국사를 총괄한 한 명의 최고 관등에 가까웠다고 추정됩니다.",
        "prompt_sha256": "570036A92615AA17E15A359969948E3A8C53462DBB5A7E163C0681BC53B88AB1",
        "location": "plain Baekje royal council hall",
        "action": (
            "One senior minister stands directly below the seated king, receives reports from three "
            "working officials, and turns to summarize the affairs of state. Human posture makes one "
            "coordinating highest office unmistakable."
        ),
    },
    111: {
        "narration": "업무가 늘고 국가 규모가 커지면서 좌평의 직능도 서서히 분화했고,",
        "prompt_sha256": "BA0C18ED1BFCEED73E9951D03E21B8E22E3CFE51740308B665D82583F7FA8DD4",
        "location": "busy Baekje administrative courtyard",
        "action": (
            "A senior minister uses one open empty hand to direct three civilian officials into "
            "different living duties: one listens to a speaking farmer delegation, one guides unarmed "
            "messengers, and one directs grain workers. Expanding duties visibly divide into three "
            "specialized human roles. Every hand is empty; no paper, tablet, scroll, book, sign, "
            "inscription, written mark, or document appears."
        ),
    },
    112: {
        "narration": "사비 천도 전후에 다섯 좌평을 거쳐 여섯 좌평으로 발전했다는 견해가 있죠.",
        "prompt_sha256": "F699FE9D37FD55F732E7E32C1A3277A660D079F8E8FEF7726D498B708BC3A034",
        "location": "plain late Baekje council yard",
        "action": (
            "A transitional council shows five senior officials already at work while a sixth official "
            "steps into a newly opened place beside them as the king and court watch. The development "
            "from five roles to six is visible through people."
        ),
    },
    114: {
        "narration": "그가 한 일은 모든 방을 완성한 것이 아니라 기둥을 세운 일이었고,",
        "prompt_sha256": "CDE158555A0BC6A7176DA7902BA617C89335124AA11EFFFDFC51F79A249F3C99",
        "location": "open bare Baekje council ground",
        "action": (
            "King Goi places one senior minister and the first few ranked officials into foundational "
            "positions while several clearly empty places remain in the unfinished human hierarchy. "
            "The people show that he established an initial framework without completing every later "
            "office. No literal room, pillar, construction, building, model, object, artifact, plaque, "
            "sign, inscription, document, emblem, symbol, or written mark appears."
        ),
    },
    121: {
        "narration": "개혁의 결과는 궁정의 옷 색깔만 달라진 데서 끝나지 않았습니다.",
        "prompt_sha256": "7BD40E7DA4F42A2E50034C82C1ADD5A8A226803F66495376A587C1F868A31FB0",
        "location": "working Baekje administrative courtyard",
        "action": (
            "Ranked officials in purple, red, and blue actively direct grain workers, messengers, and "
            "guards beyond the court. The same ordered people perform practical administration, "
            "showing reform extending far beyond clothing."
        ),
    },
    122: {
        "narration": "평야의 생산력은 창고로 모이고 관리가 그 흐름을 기록했으며,",
        "prompt_sha256": "1602E70044CDE47BB11F39CC16F75262358D3969F2E7B9003A41165F5D1D42AD",
        "location": "busy Baekje granary yard beside the plain",
        "action": (
            "Farmers carry grain sacks from the open fields into a timber granary while one official "
            "counts each arrival with finger signals and another directs the storage line. The flow "
            "from production to administration is visible without a document close-up."
        ),
    },
    125: {
        "narration": "낙랑과 대방을 대하는 태도도 눈치를 보는 단계에서 맞서는 단계로 바뀌었고,",
        "prompt_sha256": "B80B089D06A7F78963D28795F98662FD5AAA505798A3425C9CF4D6E7DE22A104",
        "location": "open frontier meeting ground",
        "action": (
            "At left, one Baekje commander and two escorts face right. At right, two Lelang and "
            "Daifang envoys face left. The two groups stop one arm's length apart in a tense face-to-face "
            "standoff; the Baekje commander holds his ground and meets both envoys' eyes. Nobody marches "
            "toward the camera. The change from caution to open resistance is unmistakable."
        ),
    },
    126: {
        "narration": "백제는 한반도 중서부의 강자로 올라설 정치적 기반을 얻었습니다.",
        "prompt_sha256": "D4A712198C83A2459275B11B84583A31EBB18A2C850F8BC0E820A59CD7BF047D",
        "location": "open central-western Korean assembly ground",
        "action": (
            "King Goi stands at the center of an ordered Baekje delegation while surrounding regional "
            "leaders turn toward him and Baekje officials direct soldiers and residents behind them. "
            "Living organization makes Baekje's new political weight visible."
        ),
    },
    128: {
        "narration": "왕권과 귀족의 긴장도 이후 백제 정치에서 계속 모습을 드러냅니다.",
        "prompt_sha256": "C988EA23074AAF62989EC7D32D38EDE1DCC4F551F914491187323D29EADB6C30",
        "location": "open bare Baekje council ground",
        "action": (
            "King Goi and three senior nobles face one another in a tense close circle while one senior "
            "minister keeps both sides engaged. Neither side yields or leaves; faces, stance, and eye-lines "
            "show continuing political tension. No building, doorway, plaque, seal, document, sign, "
            "inscription, banner, emblem, symbol, or written mark appears."
        ),
    },
    137: {
        "narration": "관등은 귀족을 한 줄로 세우고 복색은 그 서열을 눈앞에 드러냈으며,",
        "prompt_sha256": "0AD5DFDED42E4095D1062DDC7D921514948635D139FDC75472F7AF95F2173A51",
        "location": "plain Baekje court assembly yard",
        "action": (
            "Powerful nobles stand in one descending line before King Goi, wearing deep purple, "
            "muted red, blue, and pale robes according to position. Ordered bodies and clothing alone "
            "make rank visible."
        ),
    },
    138: {
        "narration": "병마권과 부패 처벌은 왕의 명령이 실제로 움직이게 만들었습니다.",
        "prompt_sha256": "60A6299C6469C8F62C499FF9F2519EFFCF4CDD7CF553A1F28F082CA38AAD75FF",
        "location": "open Baekje command and judgment courtyard",
        "action": (
            "In one continuous scene, seated King Goi raises one open hand at center. At left, two "
            "civilian guards restrain the wrists of one pale-robed corrupt tax official kneeling beside "
            "one grain sack. At right, a royal commander points forward as an ordered soldier line "
            "begins moving away from the king. Both the arrest and military departure are fully visible "
            "at the same time, showing two royal powers taking effect. No split panel."
        ),
    },
    140: {
        "narration": "다만 열여섯 관등과 여섯 좌평이 한날 완성됐다는 설명은 내려놓아야 합니다.",
        "prompt_sha256": "B759EEB088CCB4E2577CD8B2E18EE283774D06680C58545D2556C0C44F6FEC0F",
        "location": "open bare Baekje rank assembly ground",
        "action": (
            "King Goi stands beside one senior minister and a small incomplete row of early officials, "
            "with several deliberate gaps left between people for later offices. The visibly unfinished "
            "human arrangement rejects a complete sixteen-rank and six-minister system appearing at once. "
            "No building, doorway, plaque, seal, document, sign, inscription, banner, emblem, or written mark."
        ),
    },
    142: {
        "narration": "왕좌를 차지한 방식에는 거친 권력투쟁의 그림자가 남지만,",
        "prompt_sha256": "2DDD07DF75E418E390226953136F6B5AE25D7AA5533788A1A863A8AE5769DA37",
        "location": "open bare Baekje succession ground",
        "action": (
            "At left, the displaced young former king leaves between two escorts. At center, King Goi "
            "stands without a chair while tense senior nobles face him from both sides, some still turned "
            "toward the departing ruler. Human movement and hostile eye-lines show the shadow of a rough "
            "power struggle. No throne, chair, artifact, building, doorway, plaque, seal, document, sign, "
            "inscription, banner, emblem, symbol, or written mark appears."
        ),
    },
    143: {
        "narration": "그 뒤의 개혁은 백제를 느슨한 연맹으로 되돌리기 어렵게 만들었죠.",
        "prompt_sha256": "C8292FB23EC01C5D8CB22B58DC44B996A01C61F91D179C12CE5DB35E3D66F58F",
        "location": "working Baekje royal administrative courtyard",
        "action": (
            "King Goi watches from the center while a senior minister directs ranked officials in two "
            "ordered rows. Messengers move between the rows, guards follow one official's hand signal, "
            "and grain workers follow another; former local chiefs now stand inside the same ordered "
            "rows. Coordinated people and simultaneous duties make a return to a loose alliance visibly "
            "difficult. No literal chain, rope, shackle, tether, restraint, or linked marching line."
        ),
    },
}


def _ep03_full_frame_qa_location(cut_number: int) -> str:
    if cut_number == 26:
        return "open bare military mustering field beneath an empty sky"
    if cut_number == 38:
        return "open bare alliance assembly ground beneath an empty sky"
    if cut_number == 39:
        return "tight ground-level frame between two adult groups on bare earth with the horizon fully hidden"
    if cut_number == 43:
        return "open bare frontier earthwork beneath an empty sky"
    if cut_number in {50, 99, 122}:
        return "open packed-earth grain work ground beside low stacked sacks"
    if cut_number == 125:
        return "open bare frontier meeting ground beneath an empty sky"
    if cut_number == 126:
        return "open bare regional assembly ground beneath an empty sky"
    return "open bare packed-earth ground beside one low featureless earthen boundary"


def _ep03_full_frame_qa_scene(action: str) -> str:
    return (
        f"{action} Living adult actors fill the frame; faces, eye-lines, and the narrated action "
        "remain dominant. Camera stays low and close; living bodies occupy at least four fifths of "
        "the image. The background consists only of open sky, bare packed earth, and one continuous "
        "low featureless earthen boundary. Natural attached arms, relaxed five-finger hands, grounded "
        "legs, restrained period clothing, uncluttered ground. "
        "Early Korean state-formation realism, natural directional light, 35mm lens, cinematic 16:9."
    )


# Each row binds the exact Korean workbook metadata to the English-only visual
# context that survives apply_script_visual_policy(). A workbook metadata change
# must be reviewed explicitly instead of silently reusing an old translation.
VISUAL_CONTEXT_ROWS = (
    (
        "기원전 1세기 말로 전하는 건국 전승부터 온조왕 초기 기사까지",
        "고구려·마한·백제",
        "졸본, 한강 유역, 위례, 미추홀, 마한 국읍·우곡성",
        "Late 1st century BC foundation tradition through the early reign of King Onjo",
        "Goguryeo, Mahan, and Baekje",
        "Jolbon, the Han River basin, Wirye, Michuhol, Mahan state centers, and Ugok Fortress",
    ),
    (
        "백제 건국 시조에 관한 서로 다른 후대 기록",
        "백제·고구려·대방군",
        "대방 지역, 황해, 한강 유역",
        "Baekje foundation traditions preserved in conflicting later records",
        "Baekje, Goguryeo, and Daifang Commandery",
        "the Daifang region, the Yellow Sea, and the Han River basin",
    ),
    (
        "234년~286년",
        "백제·마한·낙랑군·대방군",
        "한강 유역과 한반도 중서부",
        "234-286 AD",
        "Baekje, Mahan, Lelang Commandery, and Daifang Commandery",
        "the Han River basin and the central-western Korean Peninsula",
    ),
    (
        "346년~375년",
        "백제·고구려",
        "한강 유역, 황해도 평양성 일대",
        "346-375 AD",
        "Baekje and Goguryeo",
        "the Han River basin and the Pyongyang Fortress area in Hwanghae",
    ),
    (
        "4세기 후반",
        "백제·동진·왜",
        "한강 유역, 황해·남해 해로, 일본열도",
        "Late 4th century AD",
        "Baekje, Eastern Jin, and Wa",
        "the Han River basin, Yellow Sea and South Sea routes, and the Japanese archipelago",
    ),
    (
        "384년",
        "백제·동진",
        "한성, 서해 교통로",
        "384 AD",
        "Baekje and Eastern Jin",
        "Hanseong and the western sea route",
    ),
    (
        "삼국사기에 수록된 백제 도미 설화",
        "백제",
        "한강 유역과 도미 부부의 거주지로 전하는 지역",
        "Baekje period, date unspecified in the Domi legend recorded in the Samguk Sagi",
        "Baekje",
        "the Han River basin and the traditional home region of Domi and his wife",
    ),
    (
        "475년",
        "백제·고구려",
        "한성, 한강 유역, 아차산 일대",
        "475 AD",
        "Baekje and Goguryeo",
        "Hanseong, the Han River basin, and the Achasan area",
    ),
    (
        "475년~5세기 후반",
        "백제",
        "웅진, 공산성, 금강 유역",
        "475 AD through the late 5th century",
        "Baekje",
        "Ungjin, Gongsanseong Fortress, and the Geum River basin",
    ),
    (
        "479년~501년",
        "백제",
        "웅진, 가림성",
        "479-501 AD",
        "Baekje",
        "Ungjin and Garimseong Fortress",
    ),
    (
        "501년",
        "백제",
        "웅진, 가림성",
        "501 AD",
        "Baekje",
        "Ungjin and Garimseong Fortress",
    ),
    (
        "501년~523년",
        "백제",
        "웅진과 22담로 통치 지역",
        "501-523 AD",
        "Baekje",
        "Ungjin and the territories governed through the twenty-two damno",
    ),
    (
        "1971년 발굴, 523년~529년 장례",
        "대한민국",
        "충청남도 공주시 송산리 무령왕릉",
        "Burial dated 523-529 AD and excavation in 1971",
        "the Republic of Korea",
        "the Tomb of King Muryeong at Songsan-ri, Gongju, South Chungcheong Province",
    ),
    (
        "538년",
        "백제",
        "웅진, 사비, 부소산성과 나성",
        "538 AD",
        "Baekje",
        "Ungjin, Sabi, Busosanseong Fortress, and the outer city wall",
    ),
    (
        "6세기 성왕대",
        "백제·왜",
        "사비, 일본열도",
        "6th century AD during the reign of King Seong",
        "Baekje and Wa",
        "Sabi and the Japanese archipelago",
    ),
    (
        "551년~553년",
        "백제·신라·고구려",
        "한강 유역",
        "551-553 AD",
        "Baekje, Silla, and Goguryeo",
        "the Han River basin",
    ),
    (
        "553년",
        "백제·신라",
        "한강 하류와 신라 접경",
        "553 AD",
        "Baekje and Silla",
        "the lower Han River and the Silla frontier",
    ),
    (
        "554년",
        "백제·신라",
        "관산성, 현재의 충청북도 옥천 일대",
        "554 AD",
        "Baekje and Silla",
        "Gwansanseong Fortress in the present-day Okcheon area, North Chungcheong Province",
    ),
    (
        "554년~598년",
        "백제",
        "사비, 능산리, 익산",
        "554-598 AD",
        "Baekje",
        "Sabi, Neungsan-ri, and Iksan",
    ),
    (
        "600년~641년",
        "백제·신라",
        "익산, 사비, 신라 왕경",
        "600-641 AD",
        "Baekje and Silla",
        "Iksan, Sabi, and the Silla royal capital",
    ),
    (
        "무왕 재위기 설화, 639년 사리 봉안",
        "백제·신라",
        "익산, 신라 왕경",
        "Legend from the reign of King Mu and relic enshrinement in 639 AD",
        "Baekje and Silla",
        "Iksan and the Silla royal capital",
    ),
    (
        "무왕대 창건, 639년 사리 봉안",
        "백제",
        "익산 미륵사",
        "Founded during the reign of King Mu with relic enshrinement in 639 AD",
        "Baekje",
        "Mireuksa Temple in Iksan",
    ),
    (
        "641년~660년",
        "백제·신라·당",
        "사비, 신라 왕경, 당 장안",
        "641-660 AD",
        "Baekje, Silla, and Tang China",
        "Sabi, the Silla royal capital, and Tang Chang'an",
    ),
    (
        "660년 7월",
        "백제·신라",
        "황산벌, 현재의 충청남도 논산 일대",
        "July 660 AD",
        "Baekje and Silla",
        "Hwangsanbeol in the present-day Nonsan area, South Chungcheong Province",
    ),
    (
        "660년 7월",
        "백제·신라·당",
        "사비성, 부소산성, 금강",
        "July 660 AD",
        "Baekje, Silla, and Tang China",
        "Sabi Fortress, Busosanseong Fortress, and the Geum River",
    ),
    (
        "660년 항복 전후; 예식진 묘지명은 당에서 작성",
        "백제·당",
        "사비, 웅진, 당 장안",
        "Around the surrender of 660 AD, with the Ye Sik-jin epitaph composed in Tang China",
        "Baekje and Tang China",
        "Sabi, Ungjin, and Tang Chang'an",
    ),
    (
        "660년 멸망을 배경으로 형성된 후대 전승",
        "백제·당",
        "사비, 부소산 낙화암",
        "Later tradition set against the fall of Baekje in 660 AD",
        "Baekje and Tang China",
        "Sabi and Nakhwaam Rock on Busosan Mountain",
    ),
    (
        "660년 항복 뒤 당 압송",
        "백제·당",
        "사비, 서해 항로, 당 장안과 북망산",
        "After the surrender of 660 AD and forced transfer to Tang China",
        "Baekje and Tang China",
        "Sabi, the western sea route, Tang Chang'an, and Beimang Mountain",
    ),
    (
        "660~661년 백제 부흥운동 초기",
        "백제 부흥군·신라·당",
        "주류성, 임존성, 사비 일대",
        "Early Baekje revival movement, 660-661 AD",
        "Baekje revival forces, Silla, and Tang China",
        "Juryuseong Fortress, Imjonseong Fortress, and the Sabi area",
    ),
    (
        "661~663년 부흥군 내부 분열",
        "백제 부흥군·신라·당",
        "주류성, 백제 부흥군 거점",
        "Internal division of the Baekje revival forces, 661-663 AD",
        "Baekje revival forces, Silla, and Tang China",
        "Juryuseong Fortress and Baekje revival strongholds",
    ),
    (
        "663년 8월 백강 전투",
        "백제 부흥군·신라·당·왜",
        "백강, 금강 하구와 서해 연안",
        "Battle of Baekgang, August 663 AD",
        "Baekje revival forces, Silla, Tang China, and Wa",
        "Baekgang, the Geum River estuary, and the western coast",
    ),
    (
        "663년 백강 패전 이후",
        "백제 부흥군·신라·당",
        "임존성, 사비와 웅진도독부 영역",
        "After the Baekgang defeat in 663 AD",
        "Baekje revival forces, Silla, and Tang China",
        "Imjonseong Fortress, Sabi, and the Ungjin Commandery territory",
    ),
    (
        "1993년 12월 능산리 절터 발굴",
        "대한민국",
        "충청남도 부여군 능산리 절터",
        "Excavation of the Neungsan-ri temple site in December 1993",
        "the Republic of Korea",
        "the Neungsan-ri temple site in Buyeo County, South Chungcheong Province",
    ),
    (
        "6~7세기 사비기; 1993년 출토",
        "백제",
        "사비, 능산리 절터",
        "Sabi period, 6th-7th centuries AD, with excavation in 1993",
        "Baekje",
        "Sabi and the Neungsan-ri temple site",
    ),
    (
        "6~7세기 사비기",
        "백제",
        "사비, 능산리 절터",
        "Sabi period, 6th-7th centuries AD",
        "Baekje",
        "Sabi and the Neungsan-ri temple site",
    ),
    (
        "현재까지 전승되는 부여 은산 지역 공동체 제의",
        "대한민국",
        "충청남도 부여군 은산면",
        "Community rite in Eunsan, Buyeo, transmitted to the present",
        "the Republic of Korea",
        "Eunsan Township, Buyeo County, South Chungcheong Province",
    ),
    (
        "822년 김헌창의 난; 통일신라 하대",
        "신라",
        "신라 전역과 옛 백제 지역",
        "Kim Heon-chang's revolt in 822 AD during late Unified Silla",
        "Silla",
        "Silla territories and the former Baekje region",
    ),
    (
        "견훤 867~936년; 무진주 자립 892년; 후백제 선포 900년",
        "신라·후백제",
        "무진주, 상주와 서남해 지역",
        "Gyeon Hwon, 867-936, with independence at Mujinju in 892 and Later Baekje proclaimed in 900",
        "Silla and Later Baekje",
        "Mujinju, Sangju, and the southwestern coastal region",
    ),
    (
        "후백제 전성기; 경주 침공·공산 전투 927년, 고창 전투 930년",
        "후백제·신라·후고구려·고려",
        "완산주, 나주, 공산과 후삼국 전선",
        "Later Baekje at its height, with the Gyeongju invasion and Gongsan battle in 927 and the Gochang battle in 930",
        "Later Baekje, Silla, Later Goguryeo, and Goryeo",
        "Wansanju, Naju, Gongsan, and the Later Three Kingdoms front",
    ),
    (
        "935년 정변; 936년 일리천 전투와 후백제 멸망",
        "후백제·고려",
        "완산주, 금산사, 일리천",
        "Palace coup in 935, followed by the Battle of Ilicheon and the fall of Later Baekje in 936",
        "Later Baekje and Goryeo",
        "Wansanju, Geumsansa Temple, and Ilicheon",
    ),
)


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\r", " ").replace("\n", " ")).strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _source_content_sha256(workbook) -> str:
    """Hash the authoritative A:D source contract while ignoring caption column E."""
    payload = [
        [
            sheet_name,
            [
                [_text(workbook[sheet_name].cell(row, column).value) for column in range(1, 5)]
                for row in range(1, 160)
            ],
        ]
        for sheet_name in EXPECTED_SHEETS
    ]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


def clean_image_prompt(raw_prompt: Any, narration: Any) -> tuple[str, bool]:
    prompt = _text(raw_prompt)
    spoken = _text(narration)
    cleaned, replacements = PROMPT_CONTEXT_RE.subn(" ", prompt)
    cleaned = _text(cleaned)
    had_cjk = bool(CJK_RE.search(prompt))

    if had_cjk and replacements != 1:
        raise ValueError(
            "한글/CJK 이미지 프롬프트의 정리 마커가 정확히 1회가 아닙니다: "
            f"replacements={replacements}, prompt={prompt[:180]!r}"
        )
    if replacements > 1:
        raise ValueError(f"이미지 프롬프트 정리 마커가 중복되었습니다: {replacements}")
    if not cleaned:
        raise ValueError("이미지 프롬프트 정리 후 본문이 비었습니다.")
    if CJK_RE.search(cleaned):
        raise ValueError(f"이미지 프롬프트에 CJK가 남았습니다: {cleaned[:180]!r}")
    if spoken and spoken in cleaned:
        raise ValueError("이미지 프롬프트에 원문 대사가 남았습니다.")
    if "Narration beat for visual context only:" in cleaned or "Setting:" in cleaned:
        raise ValueError("이미지 프롬프트에 정리 대상 라벨이 남았습니다.")
    return cleaned, bool(replacements)


def _shorts_fields(raw_marker: Any) -> tuple[bool, int, int, str]:
    marker = _text(raw_marker)
    if not marker:
        return False, 0, 0, ""
    match = SHORTS_MARKER_RE.fullmatch(marker)
    if not match:
        raise ValueError(f"숏츠 태그 형식 오류: {marker!r}")
    return True, int(match.group(1)), int(match.group(2)), marker


def _episode_code(episode_number: int) -> str:
    return f"백제사-EP{episode_number:02d}"


def english_visual_context(
    episode_number: int,
    *,
    period: str,
    countries: str,
    region: str,
) -> tuple[str, str, str]:
    if len(VISUAL_CONTEXT_ROWS) != 40:
        raise ValueError(f"영문 시각 문맥 행 수 불일치: {len(VISUAL_CONTEXT_ROWS)}")
    try:
        row = VISUAL_CONTEXT_ROWS[episode_number - 1]
    except IndexError as exc:
        raise ValueError(f"영문 시각 문맥 회차 범위 오류: {episode_number}") from exc
    source_values = row[:3]
    actual_values = (period, countries, region)
    if source_values != actual_values:
        raise ValueError(
            f"{episode_number:02d}화 시각 메타데이터 변경 감지: "
            f"expected={source_values!r}, actual={actual_values!r}"
        )
    translated = row[3:]
    if any(not value or CJK_RE.search(value) or ";" in value for value in translated):
        raise ValueError(f"{episode_number:02d}화 영문 시각 문맥 오류: {translated!r}")
    return translated


def _rewrite_pungnap_archaeology_prompt(
    prompt: str,
    *,
    sheet_name: str,
    cut_number: int,
) -> str:
    if prompt.count(_ANCIENT_BAEKJE_STYLE_CLAUSE) != 1:
        raise ValueError(
            f"{sheet_name}: cut {cut_number} 원본 변경 감지: "
            "고대 복식 고정 문구가 정확히 1회가 아닙니다."
        )
    if prompt.count(_NO_MODERN_OBJECTS_CLAUSE) != 1:
        raise ValueError(
            f"{sheet_name}: cut {cut_number} 원본 변경 감지: "
            "현대 사물 금지 문구가 정확히 1회가 아닙니다."
        )
    return prompt.replace(
        _ANCIENT_BAEKJE_STYLE_CLAUSE,
        _PUNGNAP_ARCHAEOLOGY_STYLE_CLAUSE,
        1,
    ).replace(
        _NO_MODERN_OBJECTS_CLAUSE,
        _PUNGNAP_ARCHAEOLOGY_OBJECT_CLAUSE,
        1,
    )


def _build_final_review_pungnap_archaeology_prompt(
    *,
    scene: str,
    cut_number: int,
) -> str:
    framing = _EP01_PUNGNAP_ARCHAEOLOGY_FRAMING[cut_number]
    return (
        f"{scene} {_PUNGNAP_ARCHAEOLOGY_STYLE_CLAUSE} {framing}, "
        "directional natural light, 35mm lens, cinematic realism, "
        f"{_PUNGNAP_ARCHAEOLOGY_OBJECT_CLAUSE}, cinematic 16:9 composition."
    )


def _resolve_cut_visual_context(
    *,
    episode_number: int,
    cut_number: int,
    row: int,
    narration: str,
    image_prompt: str,
    period_en: str,
    countries_en: str,
    region_en: str,
) -> dict[str, Any]:
    sheet_name = f"{episode_number:02d}화"
    source_row = f"{episode_number:02d}-{row:03d}"
    context: dict[str, Any] = {
        "image_prompt": image_prompt,
        "visual_year": period_en,
        "visual_period": f"{countries_en} historical context",
        "visual_location": region_en,
        "visual_evidence": (
            f"Source workbook row {source_row} anchors this scene to "
            f"{period_en}, {countries_en}, and {region_en}."
        ),
        "source_context_override": False,
    }

    ep03_dialogue_qa = (
        _EP03_DIALOGUE_QA_SOURCES.get(cut_number)
        if episode_number == 3
        else None
    )
    if ep03_dialogue_qa is not None:
        if narration != ep03_dialogue_qa["narration"]:
            raise ValueError(
                f"{sheet_name}: cut {cut_number} 원본 변경 감지: EP03 이미지 QA 대사가 "
                "등록된 행과 다릅니다."
            )
        actual_hash = hashlib.sha256(image_prompt.encode("utf-8")).hexdigest().upper()
        if actual_hash != ep03_dialogue_qa["prompt_sha256"]:
            raise ValueError(
                f"{sheet_name}: cut {cut_number} 원본 변경 감지: EP03 이미지 QA 장면이 "
                "등록된 행과 다릅니다."
            )
        context.update(
            {
                "image_prompt": ep03_dialogue_qa["scene"],
                "visual_location": ep03_dialogue_qa["location"],
                "visual_evidence": (
                    f"Source workbook row {source_row} and direct EP03 image QA require the "
                    "narrated living action and human relationships to dominate the frame."
                ),
                "source_context_override": True,
            }
        )
        return context

    ep03_full_frame_qa = (
        _EP03_FULL_FRAME_QA_SOURCES.get(cut_number)
        if episode_number == 3
        else None
    )
    if ep03_full_frame_qa is not None:
        if narration != ep03_full_frame_qa["narration"]:
            raise ValueError(
                f"{sheet_name}: cut {cut_number} 원본 변경 감지: EP03 전체 이미지 QA 대사가 "
                "등록된 행과 다릅니다."
            )
        actual_hash = hashlib.sha256(image_prompt.encode("utf-8")).hexdigest().upper()
        if actual_hash != ep03_full_frame_qa["prompt_sha256"]:
            raise ValueError(
                f"{sheet_name}: cut {cut_number} 원본 변경 감지: EP03 전체 이미지 QA 장면이 "
                "등록된 행과 다릅니다."
            )
        context.update(
            {
                "image_prompt": _ep03_full_frame_qa_scene(
                    ep03_full_frame_qa["action"]
                ),
                "visual_location": _ep03_full_frame_qa_location(cut_number),
                "visual_evidence": (
                    f"Source workbook row {source_row} and full-frame EP03 image QA require "
                    "the narrated living action and human relationships to dominate the frame."
                ),
                "source_context_override": True,
            }
        )
        return context

    ep03_preview = (
        _EP03_GEUNCHOGO_PREVIEW_SOURCES.get(cut_number)
        if episode_number == 3
        else None
    )
    if ep03_preview is not None:
        if narration != ep03_preview["narration"]:
            raise ValueError(
                f"{sheet_name}: cut {cut_number} 원본 변경 감지: 근초고왕 예고 대사가 "
                "등록된 행과 다릅니다."
            )
        actual_hash = hashlib.sha256(image_prompt.encode("utf-8")).hexdigest().upper()
        if actual_hash != ep03_preview["prompt_sha256"]:
            raise ValueError(
                f"{sheet_name}: cut {cut_number} 원본 변경 감지: 근초고왕 예고 이미지 "
                "장면이 등록된 행과 다릅니다."
            )
        context.update(
            {
                "image_prompt": ep03_preview["scene"],
                "visual_year": "371 AD",
                "visual_period": (
                    "Baekje-Goguryeo conflict during King Geunchogo's northern campaign"
                ),
                "visual_location": ep03_preview["location"],
                "visual_evidence": (
                    f"Source workbook row {source_row} explicitly previews King Geunchogo's "
                    "northern campaign and the 371 AD battle at Pyeongyang Fortress; this "
                    "cut-specific preview context supersedes the episode-wide 234-286 AD range."
                ),
                "source_context_override": True,
            }
        )
        return context

    if episode_number != 1 or cut_number not in _EP01_PUNGNAP_ARCHAEOLOGY_SOURCES:
        return context

    expected_narration, expected_scene, mode = _EP01_PUNGNAP_ARCHAEOLOGY_SOURCES[cut_number]
    if narration != expected_narration:
        raise ValueError(
            f"{sheet_name}: cut {cut_number} 원본 변경 감지: 대사가 등록된 "
            "풍납토성 고고학 행과 다릅니다."
        )
    if image_prompt.startswith(expected_scene + " "):
        resolved_prompt = _rewrite_pungnap_archaeology_prompt(
            image_prompt,
            sheet_name=sheet_name,
            cut_number=cut_number,
        )
    elif (
        hashlib.sha256(image_prompt.encode("utf-8")).hexdigest().upper()
        == _EP01_PUNGNAP_FINAL_REVIEW_PROMPT_SHA256[cut_number]
    ):
        resolved_prompt = _build_final_review_pungnap_archaeology_prompt(
            scene=expected_scene,
            cut_number=cut_number,
        )
    else:
        raise ValueError(
            f"{sheet_name}: cut {cut_number} 원본 변경 감지: 이미지 장면이 등록된 "
            "풍납토성 고고학 행과 다릅니다."
        )

    context["image_prompt"] = resolved_prompt
    context["visual_location"] = (
        "Pungnap Toseong beside the Han River in Songpa District, present-day Seoul"
    )
    context["source_context_override"] = True
    if mode == "fortification_evidence":
        context["visual_year"] = (
            "Present-day archaeological documentation and evidence-based visualization "
            "of early Baekje fortification remains"
        )
        context["visual_period"] = (
            "South Korean archaeological interpretation of early Baekje fortification "
            "evidence"
        )
        context["visual_evidence"] = (
            f"Source workbook row {source_row} presents the layered rammed-earth walls "
            "and occupation evidence of Pungnap Toseong, not a generic foundation-era court scene."
        )
    else:
        context["visual_year"] = (
            "Present-day archaeological examination of early Baekje remains"
        )
        context["visual_period"] = (
            "South Korean archaeological documentary context examining early Baekje remains"
        )
        if mode == "modern_view":
            context["visual_evidence"] = (
                f"Source workbook row {source_row} explicitly presents Pungnap Toseong "
                "beside the Han River as an archaeological view in modern Seoul."
            )
        elif mode == "excavation":
            context["visual_evidence"] = (
                f"Source workbook row {source_row} explicitly presents archaeologists and "
                "layered excavated features inside Pungnap Toseong."
            )
        else:
            raise ValueError(
                f"{sheet_name}: cut {cut_number} 풍납토성 문맥 모드 오류: {mode!r}"
            )
    return context


def validate_pipeline_visual_context(payload: dict[str, Any]) -> list[str]:
    preview = apply_script_visual_policy(copy.deepcopy(payload))
    reapplied = apply_script_visual_policy(copy.deepcopy(preview))
    reuse_quality_issues = _filter_prepared_script_quality_issues(
        inspect_script_quality(reapplied, str(payload.get("topic") or ""))
    )
    if reuse_quality_issues:
        raise ValueError(
            f"{payload.get('episode_code')}: 재사용 경로 품질 검증 실패 "
            + "; ".join(reuse_quality_issues[:8])
        )
    prompts: list[str] = []
    required_labels = (
        "Global visual world:",
        "Time range:",
        "Place scope:",
        "Culture scope:",
        "Year/period:",
        "Exact place:",
        "Scene evidence:",
    )
    preview_cuts = preview.get("cuts") or []
    reapplied_cuts = reapplied.get("cuts") or []
    if len(preview_cuts) != len(reapplied_cuts):
        raise ValueError(f"{payload.get('episode_code')}: 시각 정책 재적용 컷 수 불일치")
    forbidden_drift = (
        "612 Goguryeo-Sui",
        "Sui soldiers",
        "Goguryeo northern campaigns, 402-410",
        "Japanese creation myth",
    )
    for cut, reapplied_cut in zip(preview_cuts, reapplied_cuts):
        cut_number = int(cut.get("cut_number") or 0)
        prompt = _text(cut.get("image_prompt"))
        reapplied_prompt = _text(reapplied_cut.get("image_prompt"))
        if reapplied_prompt != prompt:
            raise ValueError(
                f"{payload.get('episode_code')} cut {cut_number}: "
                "source-locked 시각 정책 재적용 결과 불일치"
            )
        final_prompt = _text(
            normalize_cut_image_prompt(
                prompt,
                str(cut.get("narration") or ""),
                f"{payload.get('title')} {payload.get('topic')}",
                enable_series_repairs=False,
            )
        )
        missing = [label for label in required_labels if label not in prompt]
        if missing:
            raise ValueError(
                f"{payload.get('episode_code')} cut {cut_number}: "
                f"파이프라인 시각 문맥 누락 {missing}"
            )
        if CJK_RE.search(prompt):
            raise ValueError(
                f"{payload.get('episode_code')} cut {cut_number}: "
                "파이프라인 이미지 프롬프트 CJK 잔존"
            )
        if final_prompt != prompt:
            raise ValueError(
                f"{payload.get('episode_code')} cut {cut_number}: "
                "이미지 단계 source-locked 정규화 결과 불일치"
            )
        drift = [token for token in forbidden_drift if token in final_prompt]
        if drift:
            raise ValueError(
                f"{payload.get('episode_code')} cut {cut_number}: "
                f"무관한 시리즈 보정 잔존 {drift}"
            )
        for key in ("visual_year", "visual_period", "visual_location", "visual_evidence"):
            value = _text(cut.get(key))
            if not value or CJK_RE.search(value):
                raise ValueError(
                    f"{payload.get('episode_code')} cut {cut_number}: "
                    f"파이프라인 {key} 영문 문맥 누락"
                )
        prompts.append(final_prompt)
    if len(prompts) != EXPECTED_CUTS_PER_EPISODE:
        raise ValueError(
            f"{payload.get('episode_code')}: 파이프라인 프롬프트 수 불일치 {len(prompts)}"
        )
    return prompts


def _build_episode(
    worksheet,
    *,
    episode_number: int,
    workbook_path: Path,
    workbook_sha256: str,
    created_at: str,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    sheet_name = f"{episode_number:02d}화"
    actual_episode = int(float(_text(worksheet.cell(2, 2).value)))
    if actual_episode != episode_number:
        raise ValueError(f"{sheet_name}: 에피소드 번호 불일치 {actual_episode}")

    title = _text(worksheet.cell(3, 2).value)
    thumbnail_hook = _text(worksheet.cell(4, 2).value)
    thumbnail_prompt = _text(worksheet.cell(5, 2).value)
    period = _text(worksheet.cell(6, 2).value)
    countries = _text(worksheet.cell(7, 2).value)
    region = _text(worksheet.cell(8, 2).value)
    metadata = {
        "title": title,
        "thumbnail_hook": thumbnail_hook,
        "thumbnail_prompt": thumbnail_prompt,
        "period": period,
        "countries": countries,
        "region": region,
    }
    missing_metadata = [key for key, value in metadata.items() if not value]
    if missing_metadata:
        raise ValueError(f"{sheet_name}: 메타데이터 누락 {missing_metadata}")
    if CJK_RE.search(thumbnail_prompt):
        raise ValueError(f"{sheet_name}: 썸네일 프롬프트에 CJK 포함")
    period_en, countries_en, region_en = english_visual_context(
        episode_number,
        period=period,
        countries=countries,
        region=region,
    )

    headers = tuple(_text(worksheet.cell(9, column).value) for column in range(1, 5))
    if headers != EXPECTED_HEADERS:
        raise ValueError(f"{sheet_name}: 헤더 불일치 {headers!r}")
    variety_caption_header = _text(worksheet.cell(9, 5).value)
    if variety_caption_header and variety_caption_header not in VARIETY_CAPTION_HEADERS:
        raise ValueError(
            f"{sheet_name}: 한국식 예능 자막 헤더 불일치 {variety_caption_header!r}"
        )

    cuts: list[dict[str, Any]] = []
    marker_sequences: dict[int, list[int]] = {}
    cleaned_prompt_count = 0
    source_context_override_count = 0
    for cut_number in range(1, EXPECTED_CUTS_PER_EPISODE + 1):
        row = cut_number + 9
        actual_cut = int(float(_text(worksheet.cell(row, 1).value)))
        if actual_cut != cut_number:
            raise ValueError(
                f"{sheet_name}: 컷 번호 불일치 row={row}, expected={cut_number}, actual={actual_cut}"
            )
        narration = _text(worksheet.cell(row, 3).value)
        if not narration:
            raise ValueError(f"{sheet_name}: cut {cut_number} 대사 누락")
        highlight_caption = _text(worksheet.cell(row, 5).value)
        if variety_caption_header and not highlight_caption:
            raise ValueError(f"{sheet_name}: cut {cut_number} 한국식 예능 자막 누락")
        image_prompt, was_cleaned = clean_image_prompt(
            worksheet.cell(row, 4).value,
            narration,
        )
        cleaned_prompt_count += int(was_cleaned)
        visual_context = _resolve_cut_visual_context(
            episode_number=episode_number,
            cut_number=cut_number,
            row=row,
            narration=narration,
            image_prompt=image_prompt,
            period_en=period_en,
            countries_en=countries_en,
            region_en=region_en,
        )
        image_prompt = str(visual_context["image_prompt"])
        source_context_override_count += int(
            bool(visual_context["source_context_override"])
        )
        shorts_candidate, shorts_group, shorts_order, marker = _shorts_fields(
            worksheet.cell(row, 2).value
        )
        if shorts_candidate:
            marker_sequences.setdefault(shorts_group, []).append(shorts_order)

        cut_payload = {
                "cut_number": cut_number,
                "narration": narration,
                "image_prompt": image_prompt,
                "visual_year": visual_context["visual_year"],
                "visual_period": visual_context["visual_period"],
                "visual_location": visual_context["visual_location"],
                "visual_evidence": visual_context["visual_evidence"],
                "source_context_override": bool(
                    visual_context["source_context_override"]
                ),
                "scene_type": "narration",
                "shorts_candidate": shorts_candidate,
                "shorts_group": shorts_group,
                "shorts_reason": f"source workbook marker {marker}" if marker else "",
                "shorts_title": "",
                "shorts_score": 0,
            }
        if highlight_caption:
            cut_payload["highlight_caption"] = highlight_caption
        cuts.append(cut_payload)

    if set(marker_sequences) != {1, 2, 3, 4}:
        raise ValueError(
            f"{sheet_name}: 숏츠 그룹 불일치 {sorted(marker_sequences)}"
        )
    for group, sequence in sorted(marker_sequences.items()):
        expected = list(range(1, len(sequence) + 1))
        if sequence != expected or len(sequence) < 10:
            raise ValueError(
                f"{sheet_name}: 숏츠 그룹 {group} 순번 불일치 {sequence!r}"
            )

    code = _episode_code(episode_number)
    payload: dict[str, Any] = {
        "script_version": "prepared-1.0",
        "prepared_source": True,
        "visual_policy_mode": "source-locked",
        "title": f"{code}: {title}",
        "description": f"백제사 {episode_number:02d}화. {period}; {countries}; {region}",
        "tags": ["백제사", title, period, countries],
        "thumbnail_prompt": thumbnail_prompt,
        "thumbnail_hook": thumbnail_hook,
        "visual_world": {
            "time_range": period_en,
            "place_scope": region_en,
            "culture_scope": countries_en,
            "material_culture": (
                "Use material culture documented for the declared time, polities, and region."
            ),
            "continuity_rule": (
                "Follow the source workbook scene, declared period, countries, and region for every cut."
            ),
        },
        "source": {
            "script_xlsx": str(workbook_path),
            "script_xlsx_sha256": workbook_sha256,
            "script_sheet": sheet_name,
            "created_at": created_at,
            "prompt_cleanup_rule": (
                "Remove generated Setting and Narration beat clauses before the English style clause; "
                "preserve the source narration separately."
            ),
            "cleaned_prompt_count": cleaned_prompt_count,
            "series": "백제사",
            "episode_code": code,
        },
        "cuts": cuts,
        "episode_number": episode_number,
        "episode": code,
        "topic": title,
        "series": "백제사",
        "episode_code": code,
        "episode_id": code,
        "source_sheet": code,
    }
    _validate_prepared_script(
        payload,
        f"{workbook_path}!{sheet_name}",
        expected_cut_count=EXPECTED_CUTS_PER_EPISODE,
    )
    policy_prompts = validate_pipeline_visual_context(payload)
    report = {
        "episode_number": episode_number,
        "episode_code": code,
        "source_sheet": sheet_name,
        "title": title,
        "cut_count": len(cuts),
        "shorts_cut_count": sum(1 for cut in cuts if cut["shorts_candidate"]),
        "shorts_groups": {str(key): len(value) for key, value in marker_sequences.items()},
        "cleaned_prompt_count": cleaned_prompt_count,
        "source_context_override_count": source_context_override_count,
        "pipeline_prompt_count": len(policy_prompts),
        "filename": f"{code}_script.json",
    }
    return payload, report, policy_prompts


def build_prepared_scripts(workbook_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    workbook_path = workbook_path.resolve()
    if not workbook_path.is_file():
        raise FileNotFoundError(workbook_path)
    workbook_sha256 = _sha256(workbook_path)
    workbook = _load_xlsx_workbook(
        workbook_path,
        sheet_names=set(EXPECTED_SHEETS),
    )
    if tuple(workbook.sheetnames) != EXPECTED_SHEETS:
        raise ValueError(
            "시트 구성 불일치: "
            f"expected={EXPECTED_SHEETS!r}, actual={tuple(workbook.sheetnames)!r}"
        )
    source_content_sha256 = _source_content_sha256(workbook)
    source_contract = SOURCE_CONTRACTS.get(workbook_sha256)
    if source_contract is None:
        source_contract = SOURCE_CONTENT_CONTRACTS.get(source_content_sha256)
    if source_contract is None:
        raise ValueError(
            "검증되지 않은 백제사 통합대본: "
            f"file_sha256={workbook_sha256}, content_sha256={source_content_sha256}"
        )

    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    scripts: list[dict[str, Any]] = []
    episodes: list[dict[str, Any]] = []
    prompt_hashes: set[str] = set()
    pipeline_prompt_hashes: set[str] = set()
    total_cleaned = 0
    total_source_context_overrides = 0
    total_shorts = 0
    for episode_number, sheet_name in enumerate(EXPECTED_SHEETS, start=1):
        payload, report, policy_prompts = _build_episode(
            workbook[sheet_name],
            episode_number=episode_number,
            workbook_path=workbook_path,
            workbook_sha256=workbook_sha256,
            created_at=created_at,
        )
        for cut in payload["cuts"]:
            key = hashlib.sha256(cut["image_prompt"].encode("utf-8")).hexdigest()
            if key in prompt_hashes:
                raise ValueError(
                    f"정리 후 이미지 프롬프트 중복: {payload['episode_code']} cut {cut['cut_number']}"
                )
            prompt_hashes.add(key)
        for prompt in policy_prompts:
            key = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            if key in pipeline_prompt_hashes:
                raise ValueError(
                    f"파이프라인 적용 후 이미지 프롬프트 중복: "
                    f"{payload['episode_code']}"
                )
            pipeline_prompt_hashes.add(key)
        scripts.append(payload)
        episodes.append(report)
        total_cleaned += report["cleaned_prompt_count"]
        total_source_context_overrides += report["source_context_override_count"]
        total_shorts += report["shorts_cut_count"]

    manifest = {
        "source_workbook": str(workbook_path),
        "source_sha256": workbook_sha256,
        "source_content_sha256": source_content_sha256,
        "source_size": workbook_path.stat().st_size,
        "source_contract": source_contract["schema"],
        "episode_count": len(scripts),
        "cut_count": sum(len(script["cuts"]) for script in scripts),
        "unique_image_prompt_count": len(prompt_hashes),
        "pipeline_unique_image_prompt_count": len(pipeline_prompt_hashes),
        "cleaned_prompt_count": total_cleaned,
        "source_context_override_count": total_source_context_overrides,
        "shorts_cut_count": total_shorts,
        "episodes": episodes,
    }
    if manifest["episode_count"] != 40 or manifest["cut_count"] != 6000:
        raise ValueError(f"전체 구성 불일치: {manifest!r}")
    if manifest["pipeline_unique_image_prompt_count"] != 6000:
        raise ValueError(
            "파이프라인 적용 후 이미지 프롬프트 고유 수 불일치: "
            f"{manifest['pipeline_unique_image_prompt_count']} != 6000"
        )
    expected_cleaned_prompt_count = int(source_contract["cleaned_prompt_count"])
    if manifest["cleaned_prompt_count"] != expected_cleaned_prompt_count:
        raise ValueError(
            "정리 대상 프롬프트 수 불일치: "
            f"{manifest['cleaned_prompt_count']} != {expected_cleaned_prompt_count}"
        )
    expected_shorts_cut_count = int(source_contract["shorts_cut_count"])
    if manifest["shorts_cut_count"] != expected_shorts_cut_count:
        raise ValueError(
            "숏츠 컷 수 불일치: "
            f"{manifest['shorts_cut_count']} != {expected_shorts_cut_count}"
        )
    if manifest["source_context_override_count"] != 80:
        raise ValueError(
            "원본 기반 컷 문맥 교정 수 불일치: "
            f"{manifest['source_context_override_count']} != 80"
        )
    return scripts, manifest


def write_prepared_scripts(
    scripts: list[dict[str, Any]],
    manifest: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    existing_targets = [
        output_dir / f"{script['episode_code']}_script.json"
        for script in scripts
        if (output_dir / f"{script['episode_code']}_script.json").exists()
    ]
    backup_dir: Path | None = None
    if existing_targets:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = output_dir / "_backup" / f"baekje_before_{stamp}"
        backup_dir.mkdir(parents=True, exist_ok=False)
        for source in existing_targets:
            shutil.copy2(source, backup_dir / source.name)
        existing_manifest = output_dir / "백제사_manifest.json"
        if existing_manifest.is_file():
            shutil.copy2(existing_manifest, backup_dir / existing_manifest.name)

    files: list[dict[str, Any]] = []
    for script in scripts:
        filename = f"{script['episode_code']}_script.json"
        target = output_dir / filename
        content = json.dumps(script, ensure_ascii=False, indent=2) + "\n"
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(target)
        files.append(
            {
                "path": str(target),
                "bytes": target.stat().st_size,
                "sha256": _sha256(target),
            }
        )

    manifest_path = output_dir / "백제사_manifest.json"
    written_manifest = dict(manifest)
    written_manifest["output_dir"] = str(output_dir)
    written_manifest["backup_dir"] = str(backup_dir) if backup_dir else ""
    written_manifest["files"] = files
    manifest_path.write_text(
        json.dumps(written_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return written_manifest


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_WORKBOOK))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    scripts, manifest = build_prepared_scripts(Path(args.input))
    result = dict(manifest)
    result["write"] = bool(args.write)
    result["output_dir"] = str(Path(args.output_dir))
    if args.write:
        result = write_prepared_scripts(scripts, manifest, Path(args.output_dir))
        result["write"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
