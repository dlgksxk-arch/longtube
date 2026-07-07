"""이미지 프롬프트 빌더 + 레퍼런스 수집 유틸.

v1.1.52: pipeline_tasks._step_image 와 routers/image.py 가 동일한 로직을
공유하기 위해 분리. 라우터를 직접 import 하면 FastAPI 의존성(python-multipart 등)이
끌려오므로, 순수 함수만 이 모듈에 배치한다.

v1.1.58: 레퍼런스 이미지가 있으면 스타일은 100% 레퍼런스에서 가져온다.
global_style, 스타일 큐 제거 등 복잡한 우회 로직 삭제 — 단순하고 명확하게.

v1.1.55: 모든 이미지 생성(컷, 썸네일, 재생성) 경로에서 동일한 REFERENCE_STYLE_PREFIX
를 사용한다. 문구가 3 곳에서 제각각이던 상태를 단일 상수로 통합해 스타일 일관성을
강제한다.
"""
import re
from pathlib import Path
from app.config import resolve_project_dir


# ── 레퍼런스 스타일 락 (모든 이미지 생성 경로 공용) ──
#
# 이 프리픽스는 레퍼런스 이미지가 하나라도 첨부된 모든 프롬프트에 예외 없이
# 앞자리로 붙는다. 목적은 "이 프로젝트 안의 모든 이미지가 같은 그림체·같은
# 팔레트·같은 조명으로 나온다" 는 것을 모델 수준에서 강제하는 것이다.
#
# 사용처:
# - build_image_prompt (컷 이미지, has_reference=True 분기)
# - apply_reference_style_prefix (썸네일 자동/재생성, 그 외 외부 호출)
#
# 끝에 " || " 구분자를 두어 사용자 프롬프트가 바로 이어 붙을 수 있게 한다.
REFERENCE_STYLE_PREFIX = (
    "★ STYLE REFERENCE LOCK — the attached reference images are the absolute "
    "ground truth for art direction, color palette, lighting, texture, "
    "line/stroke character, and rendering technique. Copy that exact style "
    "pixel-for-pixel feel. Keep every new image visually indistinguishable "
    "in style from the references. Apply the requested composition, subject, "
    "pose, and action described below. || "
)

# v1.1.72: 모든 이미지 생성 경로에 공통으로 붙는 "문자 금지" 지시.
# 이미지 생성 모델이 그리는 문자는 거의 항상 깨져 나와 영상 완성도를
# 깎아먹으므로, 긍정 프롬프트(positive) 에서 강하게 차단한다.
# - ComfyUI 로컬은 추가로 DEFAULT_NEGATIVE_PROMPT 에서도 걸린다 (이중 차단).
# - OpenAI Image / Nano Banana 등 API 모델은 negative 가 없으므로 이 지시가 유일한 방벽.
NO_TEXT_DIRECTIVE = (
    " || UNMARKED SURFACE LOCK - all information-carrying surfaces stay plain "
    "physical material only. "
    "wall hangings, banners, flags, clothing surfaces, equipment surfaces, cloth bands, panels, and "
    "object surfaces are completely BLANK and unmarked. Every visible surface "
    "is plain physical "
    "material: plaster, wood grain, stone, cloth, clay, dust, "
    "and natural wear. "
    "Wall bands, lintels, door headers, eaves, and high plaster zones are "
    "continuous timber or plaster material; separate rectangular panels blend "
    "into knots, bracket shadows, hinge shadows, cracked clay repair, soot, "
    "dust, chips, and wood grain. Lower image corners are ordinary material "
    "only: packed earth, dust, shadow, roof edge, stone, grass, or open air. "
    "Lower-left and lower-right border-adjacent areas are clean natural ground, "
    "grass, stone, roof edge, dust, or shadow with separated organic blades, "
    "cracks, and material specks only. "
    "Never draw an overhead signboard, temple nameboard, gate "
    "plaque, lintel plaque, inscription panel, character board, under-eave "
    "signboard, small center board under a roof, decorative label plaque, "
    "or any framed wall board behind a seated figure. "
    "If a gate, "
    "doorway, hall front, shrine front, or entrance appears, its top beam is a "
    "continuous blank timber beam with only wood grain, knots, seams, dust, "
    "bracket shadows, and nail heads. If the Scene does not explicitly name a "
    "gate or entrance as the main subject, do not replace the requested path, "
    "garden, courtyard, room, or group action with a frontal gate facade. "
    "The image reads through faces, objects, light, action, "
    "texture, and composition. Wall surfaces, beams, lintels, door hardware, "
    "pottery, furniture, boards, cloth surfaces, and object surfaces are "
    "unmarked blank material "
    "planes. Scene-unnamed heraldry inventory is empty: identity marks do not "
    "appear on chest, sleeve, shoulder, sash, robe, protective material, banner, wall, or "
    "object panels; visible surfaces remain material-only. Vertical posts, "
    "columns, pillars, door jambs, gate posts, porch posts, and wall posts are "
    "plain structural material only: continuous wood grain, knots, cracks, "
    "nail heads, dust, chips, and shadow. They never carry a hanging tag, paper "
    "strip, talisman, vertical plaque, column label, calligraphy strip, or "
    "small rectangular sign. When the Scene does not explicitly name banners "
    "or flags, do not add vertical hanging banners, labeled fabric strips, wall "
    "scrolls, sign cloth, shop flags, or roadside placards as decoration. "
    "Historical buildings must not gain any extra identification board: no shop "
    "sign, street sign, gate title board, shrine name board, temple name board, "
    "official notice board, or separate over-door panel. Gate lintels, entrance crossbeams, and doorway wall surfaces are "
    "plain structural timber, plaster, or stone with uninterrupted material grain. "
    "Temple lintels, friezes, column headers, broad crossbeams, upper wall bands, "
    "courtyard beam faces, and wide rectangular architectural bands are "
    "blank structural surfaces: continuous stone grain, wood grain, plaster grain, "
    "geometric border blocks, bracket shadows, natural chips, dust, and light only. "
    "Cartouche-shaped, raised-oval, or panel-shaped details resolve as irregular "
    "same-material grain, knots, scratches, chips, and shadow. "
    "Upper beams, transoms, friezes, ceiling beams, beam pockets, bracket bays, "
    "and high wall bands never contain small framed plaques, paired header "
    "boards, hanging name slips, rectangular label tiles, character plates, "
    "or dark glyph clusters; those areas remain one continuous timber, plaster, "
    "stone, rope, nail-head, dust, shadow, or weather-stain surface. "
    "Background walls are broad uninterrupted plaster planes with natural "
    "cracks and soft shadows. Upper wall zones, side wall zones, alcove walls, "
    "and all wall areas from floor rail to ceiling beam are bare plaster and "
    "exposed timber only, with open empty wall planes. Plaster walls show "
    "large empty fields of plain material; cracks are sparse, uneven, branching "
    "or diagonal lines separated by wide blank space, with tiny marks absorbed "
    "into dust patches, stains, chips, or natural crack texture. "
    "Interior wall decoration inventory is empty: no suspended framed board, "
    "no nameboard behind a chair, no framed plaque above or behind a seated "
    "person, no rectangular calligraphy board on an interior wall, no black "
    "character strokes on wall plaques, and no small writing board behind an "
    "armed figure. "
    "Historical accounting or tally evidence is not ink writing: show count "
    "evidence as plain notched wooden tally sticks, cord knots, pebble groups, "
    "sealed bundle counts, tied packet edges, carved edge notches, measuring "
    "rope, or field stakes, with no ink rows, no glyph rows, and no organized "
    "marks on paper. When the Scene names a scribe, record, register, roster, "
    "tax register, ledger, tally board, tally mat, written order, or blank "
    "roster, the visible record surface is still textless: use blank folded "
    "paper backs, cord-tied bundles, seals, notched sticks, pebble counters, "
    "measuring rope, wood grain, or a brush hovering above untouched blank "
    "material. Do not show inked characters, rows, columns, check marks, "
    "diagram lines, or handwriting on any visible record face. In historical "
    "record scenes, avoid flat writing boards as the main image object; prefer "
    "notched sticks, cord knots, pebble counters, sealed bundles, measuring "
    "rope, and field stakes. Record, roster, "
    "register, and tally scenes must keep one readable textless evidence object "
    "in the frame: notched tally sticks, cord knots, pebble counters, sealed "
    "bundles, blank folded roster backs, measuring rope, and field stakes. "
    "Do not replace the record "
    "action with a lone armed portrait, generic warrior stance, or weapon-only "
    "symbol. "
    "Household relocation, family residence, or retainer residence scenes must "
    "keep ordinary moving evidence in frame: mixed adult household members or "
    "retainers' family members, carried low chests, tied cloth bundles, bedding "
    "rolls, baskets, pack ropes, wooden residence doors, and narrow residential "
    "lanes. Do not replace a moving-family or residence-entry scene with a "
    "soldier lineup, guard parade, empty street, or generic armed formation. "
    "Preindustrial craft workshop scenes must keep the named craft action and "
    "tool evidence in frame: period-local craftsman posture, hammer, tongs, "
    "anvil stone or iron stake, charcoal brazier or forge, sparks, rough wood "
    "or stone bench, tool rack, helper cloth, soot, and raw material. Do not "
    "replace a craft, forge, blacksmith, metal-fitting, carpenter, pottery, or "
    "workshop scene with a modern kitchen, stove, saucepan, kettle, faucet, "
    "notebook, wall sign, modern shirt, or blank portrait. "
    "Wall decoration inventory is empty; walls use only plaster, exposed timber, "
    "shutters, blank doors, cracks, dust, and shadow. "
    "Storage boxes, crates, trunks, low chests, shelves, drawers, table "
    "undersides, and containers show continuous wood grain, plank seams, corner "
    "joints, knots, nail heads, dust, and soft shadow as their complete visible "
    "surface detail. "
    "Covered litter bodies, carried-chair roofs, canopy boards, transport side "
    "boards, carrying poles, curtains, valances, and front panels are plain "
    "transport materials only: wood grain, woven cloth, cord knots, hinges, "
    "scratches, mud, dust, rain wear, and shadow. Small transport hardware "
    "stays as same-material knots, hinges, nail heads, or shadow only. "
    "Robe panels, sash ends, sleeve edges, hanging fabric strips, "
    "neckline folds, belt tails, and any repair seams are blank textile only: "
    "woven grain, seam lines, folds, knots, stains, dust, and shadow as the "
    "complete visible detail. "
    "Front robe panels are continuous same-color cloth from crossed neckline "
    "to sleeve edge; closures stay hidden under folds or appear only as "
    "same-color cord knots at the waist. "
    "Unnamed chest, sleeve, shoulder, waist, and back areas remain uninterrupted "
    "cloth fields. The visible chest inventory is closed: crossed neckline folds, "
    "plain robe fabric, sleeve overlap, waist sash edge, same-color folds, fabric "
    "grain, and shadow only. Both left and right upper-chest fields are broad continuous "
    "blank fabric. Every robed or cloth-clothed human upper chest is an empty "
    "fabric-detail zone made only from same-color textile folds, fabric grain, and "
    "shadows. Micro texture stays fused into the surrounding fabric color and "
    "keeps continuous cloth edges. Upper-chest contrast stays low and "
    "continuous: any isolated bright or dark fleck is absorbed into fold "
    "shadow, fabric scuff, dust, or same-color weave and does not read as a "
    "separate mark. Dust, stains, and wear sit on hems, cuffs, "
    "elbows, waist folds, road-facing robe edges, and background surfaces. "
    "Rank and role identity comes from garment cut, layer count, "
    "sleeve volume, neckline shape, hair shape, posture, face, and setting. "
    "Political, faction, court, clan, and rank identity never appears as "
    "invented chest heraldry when the Scene does not literally name a visible "
    "emblem. Angular high-contrast patches, colored applique plates, "
    "red-white applique clusters, decorative circular spots, floral spots, "
    "sunburst spots, medallion-like spots, fastener-like upper-chest spots, "
    "and high-contrast chest appliques are outside the visible clothing "
    "inventory and resolve into same-color folds, dust, or shadow. "
    "Clothing visible detail is closed to solid local fabric color, plain weave, "
    "folds, seams, same-color ties, waist knots, stains, dust, and shadow. "
    "Fine clothing texture stays low-contrast, same-color, and fused into the "
    "surrounding cloth surface. "
    "Visible cloth is solid local fabric color with plain weave, folds, "
    "seams, stains, dust, and shadow only. If a fastening is needed, show it "
    "only as a subtle same-color seam tuck or plain cord knot blended into cloth. "
    "Belt-adjacent inventory is closed; belts only have cords, knots, folds, "
    "plain straps, dust, and shadow. "
    "Over-door timber spans, transom zones, lintel centers, and ceiling-edge "
    "structural strips are continuous load-bearing beams or plaster bands with "
    "uninterrupted grain, bracket shadows, nail heads, dust, and wear only. "
    "The area above each doorway reads as one piece of beam or plaster strip "
    "from post to post. Ceiling planes use dark exposed rafters, beams, "
    "planks, soot, dust, and shadow only. Ceiling centers stay cropped out or "
    "read as dark structural timber with no visible light-source object. "
    "Active period light comes from side fire, low floor or table oil lamps, "
    "handheld or standing candles, braziers, small era-local lanterns placed "
    "low at human side height, doorway daylight, moonlight, or shadow. The "
    "upper frame stays structural timber, plaster band, smoke, soot, dust, or "
    "shadow. "
    "Gate header zones, door headers, lintel "
    "centers, and exterior entry beams contain only structural elements: roof "
    "rafters, bracket blocks, continuous horizontal timber beams, vertical posts, "
    "plank joints, long wood grain, organic knots, asymmetrical stains, small "
    "nail heads, dust, and shadows. The full header span shares the same "
    "material texture from post to post, with long grain lines crossing the "
    "central span and organic knot patterns integrated into the same beam. "
    "Small facade repairs, lintel repairs, upper-wall repairs, post-bay "
    "repairs, and eave underside repairs stay irregular and material-bound: "
    "structural plank patches, shutter slats, vent slats, bracket blocks, "
    "hinge hardware on door boards, or blank plaster repairs with wood grain, "
    "plank seams, nail heads, knots, dust, and shadow only. "
    "Door and threshold hardware appears as large hanging wooden or dark pull "
    "rings held by rope loops or dark hinge loops, horizontal wooden latch bars, "
    "rope pull loops, hinge barrels, separated square nail heads, dark fastening "
    "dots, or long wooden latch pieces on door boards with one solid material surface, dust, scratches, and "
    "soft shadow. Period hardware inventory stays limited to door boards, "
    "thresholds, posts, and beam contacts made from low-contrast timber, rope, "
    "nail, hinge, latch, plaster, clay, stone, dust, and shadow forms. "
    "Door faces are continuous plank or panel material. Any compact door-edge "
    "highlight, compact dark cluster, or isolated edge detail on a door blends "
    "into same-color wood grain, hinge shadow, plank repair, separated nail "
    "heads, or latch shadow with wide blank material around it. "
    "Clothing and role-equipment surfaces stay broad material forms: continuous "
    "fabric panels, seam lines, folded cloth shadows, same-color stitching, "
    "waist cords, cuffs, closures, edge folds, and gear straps integrated into "
    "the surrounding fabric or gear surface. "
    "Camp entrances, hall entrances, gate openings, doorway openings, and roofed "
    "entry gaps use the upper center as one uninterrupted load-bearing timber "
    "beam with the same wood grain continuing across the full width; the center "
    "area is visually defined by beam thickness, bracket shadows, rafter ends, "
    "plank seams, knots, nail heads, and dust. "
    "Visual irregularities resolve as low-contrast irregular stains, wood knots, "
    "nail groupings, grain breaks, or soft shadows. Small surface details resolve "
    "as organic wood grain, blank clay, cloth folds, natural stains, nail heads, "
    "door-edge hinge hardware, or soft shadow. Image corners, lower wall zones, "
    "bottom plaster edges, floor-wall seams, and empty margin areas remain plain "
    "material fields: broad blank plaster, wood grain, stone edge, dust, cracks, "
    "grass, or shadow only. Tiny clustered strokes in those areas resolve as "
    "single irregular stains, chipped plaster, dust smudges, grass blades, or "
    "broken crack branches separated by blank space. All four image corners "
    "remain ordinary background material only: road dust, grass, stone, wood "
    "grain, plaster, shadow, or open air. Tiny dark clusters at image corners "
    "separate into natural cracks, grass blades, stones, dust specks, or shadow "
    "fragments with wide blank spacing. Lower-left, lower-right, and bottom "
    "margin areas must not contain artist signatures, credit marks, date "
    "numerals, production-date marks, seal-like glyph clusters, calligraphic "
    "credit clusters, handwritten corner marks, or tiny decorative corner writing."
)

OBJECT_EVIDENCE_NO_TEXT_DIRECTIVE = (
    " || UNMARKED SURFACE LOCK - object-only evidence cuts keep every visible "
    "surface as plain physical material only. Information-carrying surfaces, "
    "boards, tablets, cloth planning surfaces, low table surfaces, floor mats, "
    "clay slabs, pottery, containers, cords, stones, pins, weights, lamps, and "
    "support surfaces are completely blank and unmarked. The image reads "
    "through object placement, light direction, shadow, dust, wear, material "
    "texture, marker spacing, and composition. The complete visible inventory "
    "is the Scene-named low horizontal surface, Scene-named marker objects, "
    "surface edges, dust, natural material grain, lamp light, and shadows. "
    "Lamp bases, metal rims, bronze weights, pins, and vessel surfaces are "
    "continuous blank bronze, iron, clay, wood, or stone surfaces with soot, "
    "rivets, scratches, tarnish, dust, and shadow only. "
    "The camera crop is filled edge to edge by the requested low horizontal "
    "surface and its plain material margins."
)

OUTDOOR_LOCATION_EVIDENCE_DIRECTIVE = (
    " || OUTDOOR LOCATION EVIDENCE LOCK - when the Scene or Exact place names "
    "an outdoor location such as a riverbank, road, street, lane, alley, path, "
    "route, junction, crossroads, townhouse district, shopfront lane, field, "
    "valley, mountain, shoreline, battlefield, camp, encampment, camp exterior, "
    "gate exterior, courtyard, forest, coast, harbor, or hill, the visible "
    "setting evidence is exterior terrain from that named place. Character "
    "close-ups and group shots use outdoor background strips made of water "
    "edge, reeds, stones, mud, grass, dirt path, street ground, open sky, mist, "
    "trees, terrain slope, distant roofs, gate exterior timber, exterior walls, "
    "partial eave edges, smoke, or weather pressure matching the Scene. The "
    "camera stands on the named outdoor ground, and the frame keeps at least "
    "one readable patch of open sky or smoke-filled outdoor air above or behind "
    "the subjects. When the Exact place "
    "or Scene says outside, road, street, lane, alley, path, route, junction, "
    "crossroads, military road, gate exterior, or roadside, compose an exterior "
    "frame where the dirt road, street, lane, or path ground and open sky remain readable, with "
    "buildings, gates, posts, and partial roof edges acting as side framing "
    "around the outdoor route, never as a full overhead ceiling. Do not replace Scene-named streets, lanes, alleys, roads, "
    "courtyards, camps, battlefields, harbors, fields, or exterior routes with "
    "an interior room, ceiling-dominant chamber, corridor, studio portrait, or "
    "indoor portrait. Do not move the named outdoor action under a roofed porch "
    "or inside a timber room unless the Scene explicitly names an interior. "
    "For road, street, lane, path, route, coastal road, shoreline, harbor road, "
    "or mounted travel scenes where a gate, entrance, shrine, temple, or "
    "waystation is not explicitly the main subject, do not add a freestanding "
    "gate, roofed gateway, torii-like entry frame, signboard arch, gatehouse "
    "portal, named-place entrance marker, roadside notice structure, or "
    "over-road header. Keep travel identity in terrain, water, rocks, trees, "
    "dirt, reeds, pack animals, reins, tack, side posts, partial eaves, and "
    "weather only. "
    "For field, rice field, paddy, wet paddy, farmland, agricultural land, "
    "land survey, measuring rope, or harvest-tax scenes, the frame stays in "
    "open outdoor ground: visible sky, water, mud, furrows, grasses, stakes, "
    "ropes, baskets, villagers, and distant low roofs only. Do not move field "
    "work under a roof, veranda, porch, corridor, hall, timber room, windowed "
    "wall, ceiling grid, beam header, or wall with plaques. "
    "Roofline and sky gaps contain only open air, haze, tree "
    "branches, eaves, rafters, dust, clouds, rain, smoke, birds, or mountain "
    "silhouettes. They contain no power poles, utility poles, telephone poles, "
    "overhead wires, roof-to-roof cables, or straight black cable lines. Gates, "
    "walls, and eaves remain unlabeled continuous material with no signboard, "
    "plaque, title panel, shop sign, street sign, written banner, or character marks."
)

HOUSEHOLD_RELOCATION_EVIDENCE_DIRECTIVE = (
    " || HOUSEHOLD RELOCATION EVIDENCE LOCK - when the Scene names household "
    "members, family members, retainers' families, moving into residences, "
    "entering wooden compounds, carrying chests, carried belongings, residence "
    "assignment, or relocation, the first readable subject is the moving "
    "household action. Show mixed adult civilians or retainer-family members "
    "with carried low wooden chests, tied cloth bundles, bedding rolls, baskets, "
    "pack ropes, open wooden residence doors, narrow residential lanes, and "
    "period-local house walls. Armed men may appear only as side watchers if "
    "the Scene names them; they do not replace the family move. Do not turn "
    "the scene into a soldier lineup, guard parade, army formation, empty "
    "street, generic military portrait, cauldron scene, cooking-pot scene, "
    "cart scene, or empty tray scene. Street sky and roof gaps contain no "
    "utility poles, telephone poles, crossarms, streetlights, or overhead wires."
)

HISTORICAL_ROAD_LOGISTICS_EVIDENCE_DIRECTIVE = (
    " || HISTORICAL ROAD LOGISTICS EVIDENCE LOCK - when the Scene names "
    "packhorses, porters, ashigaru, baggage, supplies, a column, or fast "
    "movement on a historical road toward a castle or route, render a "
    "premodern road movement scene, not a modern marching column. The first "
    "readable subject is pack animals, porters, dust, baggage, period-local "
    "dirt road ground, and role-appropriate local clothing. Use an open rural "
    "mountain road outside the settlement: fields, shrubs, rocks, tree trunks, "
    "low stone edges, distant mountains, dust, and a distant castle silhouette "
    "only. Avoid nearby village streets, gatehouse-centered compositions, "
    "utility-like roadside structures, and repeated tall thin posts. The sky "
    "is clean and uninterrupted; road edges contain trees, shrubs, fields, "
    "rocks, stone walls, roof eaves at the far edge, and mountains only. "
    "Clothes are period-local robes, work cloth, armor only "
    "when named, headcloths, straw sandals, simple footwear, and pack straps; "
    "no modern uniform tunics, no button rows, no peaked caps, no steel "
    "helmets, and no rifles."
)

HISTORICAL_PUBLIC_STREET_MUSTER_DIRECTIVE = (
    " || HISTORICAL PUBLIC STREET AND MUSTER LOCK - when the Scene names a "
    "historical road, public street, market street, castle town, square, "
    "mobilization, muster yard, assembled soldiers, merchants, craftsmen, "
    "stalls, supply carts, goods, or officials guiding public movement, render "
    "a premodern public scene grounded in the stated era and place. Sky and "
    "roof gaps stay clean open air with no utility poles, telephone poles, "
    "power poles, crossarms, cables, overhead wires, roofline wires, or straight "
    "black sky lines. Buildings use period-local timber, plaster, tile, thatch, "
    "stone base, open stalls, wooden gates, or earthworks with blank beams and "
    "no signboards, plaques, shop signs, street signs, or character marks. "
    "Do not add a gate arch, torii-like gate, over-road crossbeam, road header, "
    "suspended rope, or any line spanning across the street unless the Scene "
    "explicitly names that structure. People wear period-local wrap-front "
    "clothing with crossed neckline, broad plain cloth panels, tied waist sash, "
    "robe sleeves, hakama or wrapped work lower cloth, cloth leg wraps, straw "
    "sandals or local sandals, and simple tied local headwear. Armor appears only "
    "when the Scene names combat duty. Do not use modern shirts, separated "
    "shirt-and-pants outfits, modern buttoned uniform tunics, chest pockets, "
    "badges, chest patches, peaked caps, brimmed officer caps, steel helmets, "
    "rifle-era caps, black leather boots, knee-high dress boots, rubber soles, "
    "western trouser legs, belt buckles, or parade uniforms. Troops, merchants, officials, villagers, craftsmen, "
    "carts, stalls, goods, spear shafts, dust at feet, and pack loads form "
    "staggered side or three-quarter action groups, not a front-facing modern "
    "marching column or static lineup."
)

PREINDUSTRIAL_CRAFT_WORKSHOP_EVIDENCE_DIRECTIVE = (
    " || PREINDUSTRIAL CRAFT WORKSHOP EVIDENCE LOCK - when the Scene names a "
    "craftsman, craft workshop, forge, blacksmith, hammering, iron fittings, "
    "carpenter, potter, loom, weaving, metalwork, or workshop helper, the first "
    "readable subject is the named craft action and its period-local tools. "
    "Show a preindustrial workspace with rough timber or stone bench, charcoal "
    "brazier or forge for metalwork, anvil stone or iron stake, hammer, tongs, "
    "raw material, sparks or soot when named, tool racks, apron cloth, helper "
    "cloth, and hand-to-tool contact. The workshop contains no modern kitchen "
    "stove, gas burner, saucepan, kettle, faucet, sink, notebook, wall sign, "
    "modern collared shirt, or clean modern workbench."
)

HISTORICAL_TALLY_OBJECT_EVIDENCE_DIRECTIVE = (
    " || HISTORICAL TALLY OBJECT EVIDENCE LOCK - when the Scene names a "
    "scribe, record, register, roster, tax register, ledger, tally, accounting, "
    "survey result, land capacity, or military obligation in a historical "
    "setting, compose the image as a low object-evidence close-up. The first "
    "readable subject is the physical count evidence on a rough mat or low "
    "surface: plain notched wooden tally sticks, cord knots, pebble counters, "
    "sealed bundles, measuring rope, field stakes, dust, and hard side light. "
    "Only wrist-level period-local cloth sleeve edges and one or two small "
    "hands may enter the frame to arrange the counters. The camera crop "
    "excludes every face, head, neck, shoulder, chest, full torso, and standing "
    "body. Visible sleeves are era-local robe, tunic, work cloth, or wrapped "
    "cloth edges from the stated place, not a modern collared shirt, button "
    "placket, cuffed dress shirt, or jacket. No full standing person, no "
    "waist-up portrait, no weapon held in hand, and no building facade may replace the counting "
    "objects. If the Scene mentions spear shadows, show only diagonal shadow "
    "shapes crossing the mat; do not show a physical spear shaft or warrior "
    "replacing the record evidence."
)

HISTORICAL_BLANK_RECORD_EVIDENCE_DIRECTIVE = (
    " || HISTORICAL BLANK RECORD EVIDENCE LOCK - when the Scene names a blank "
    "roster, retainer roster, register, ledger, record, or document in a "
    "historical setting, it is visible only as a small closed textless object: "
    "cord-tied folded packet, short tied roll cylinder, edge-on stack, covered "
    "back edge, or sealed bundle. Do not show a broad flat sheet, open page "
    "face, blank white rectangle, blank board, poster-like page, wall-mounted "
    "notice, or large paper surface. No written roster, no ink rows, no line "
    "rows, no kanji, no kana, no hanzi, no pseudo-calligraphy, and no "
    "decorative heading. If a person checks the record, the record stays small "
    "and mostly covered by hands and sleeves; readable evidence is the tied "
    "roll, folded edge, cord knot, seal, dust, and table light. Rice bundles, "
    "supplies, baskets, or kneeling retainers may carry the scene, but open "
    "papers are absent. Background roof gaps and sky contain no utility wires, "
    "telephone wires, crossarms, or streetlights."
)

ENTRY_FACADE_SURFACE_DIRECTIVE = (
    " || ENTRY FACADE SURFACE LOCK - Scene-named shrine, temple, roadside, "
    "wayside, or waystation structures use blank architectural evidence only: "
    "continuous wooden beams, posts, rafters, blank plaster, rope loops, hooks, "
    "knots, weathered wood grain, soot, dust, stone bases, mist, and soft "
    "shadows. The upper center of every entrance is one load-bearing timber "
    "beam running post-to-post, with long wood grain, rafter ends, bracket "
    "shadows, knots, nail heads, dust, and asymmetrical weather stains "
    "integrated into the same beam. Visible identity comes from roof shape, "
    "post spacing, ropes, stone bases, mist, and surrounding terrain."
)

CLOTH_EVIDENCE_SURFACE_DIRECTIVE = (
    " || CLOTH EVIDENCE SURFACE LOCK - Scene-named vertical fabric evidence "
    "appears as plain textile folds only. Large fabric areas use woven texture, "
    "hems, seams, rope ties, wind folds, creases, stains, dust, and soft shadow "
    "as their visible detail. Scene-named banners and flags appear as side-facing "
    "or back-facing wind-folded cloth strips on poles or cords. Use narrow "
    "edge-on fabric surfaces, furled cloth rolls, folded backs, hems, edge "
    "stitching, rope ties, woven grain, soft stains, and shadow as the visible "
    "banner identity. The readable identity is the pole, cord, narrow fabric "
    "edge, folded back surface, and wind-folded silhouette. The full front face "
    "of the cloth is turned away from camera or wrapped around the pole; the "
    "visible cloth area is a slim side edge, folded back, or rolled textile tube. "
    "When the Scene names "
    "banners or flags, place at least one small off-center edge-on or furled "
    "blank cloth strip on a pole or cord near the named road, gate, shrine, camp, "
    "or exterior route. Each fabric panel is one continuous cloth surface with "
    "natural folds and edge stitching."
)

MOUNTED_TRAVEL_EVIDENCE_DIRECTIVE = (
    " || MOUNTED TRAVEL EVIDENCE LOCK - when the Scene names a horse, horses, "
    "mounted person, rider, cavalry, or mounted messenger, the frame keeps the "
    "mount and rider together as the visible travel subject. Use period-local "
    "horses with simple tack, compact saddles, visible horse necks, torsos, "
    "legs, tails, and one rider per horse. Every readable horse is one coherent "
    "animal: one head, one neck, one torso, four attached legs, one tail if "
    "visible, and simple tack attached to that same body. The rider is a separate "
    "human body seated on the horse, never fused into the horse neck, mane, head, "
    "back, or torso. Never render a centaur, a human torso growing from a horse "
    "body, or a horse body replacing the rider's human hips and legs. For receding travel or mist scenes, "
    "show one foreground or midground horse-and-rider pair plus smaller horse "
    "silhouettes fading into the named road, field, riverbank, gate exterior, "
    "or shrine-side mist. Rider upper chests are crossed or broken by reins, "
    "sleeves, straps, bow cases, scabbard straps, or overlapping rider angles; "
    "readable upper-chest surfaces stay plain fabric or protective material "
    "with same-color folds, dust, and shadow instead of repeated chest marks. "
    "Scene-named roadside shrines, banners, gates, terrain, "
    "and weather stay visible as supporting evidence around the mounted path."
)

SCENE_FIDELITY_DIRECTIVE = (
    " || SCENE FIDELITY LOCK - the final image must depict the Scene field as "
    "the binding subject and action. Do not replace Scene-named objects, animals, "
    "vehicles, banners, weapons, flames, terrain, or gestures with a generic "
    "portrait, lineup, building facade, doorway, room, or unrelated symbolic "
    "object. If the Scene names a specific object count, vehicle, animal, or "
    "weapon, that named subject must be visibly present in the frame."
)

BANNER_COUNT_EVIDENCE_DIRECTIVE = (
    " || BANNER COUNT EVIDENCE LOCK - when the Scene names banners, flags, or "
    "standards, the banners are mandatory visible subjects. If the Scene names "
    "three distinct banners, show exactly three separate blank cloth military "
    "banners on three separate poles, all visible at once, with wind folds, hems, "
    "rope ties, mud, rain, and shadow only. Do not replace named banners with "
    "standing people, soldiers, gate plaques, signboards, walls, buildings, or "
    "interior architecture."
)

MARITIME_LANDING_EVIDENCE_DIRECTIVE = (
    " || MARITIME LANDING EVIDENCE LOCK - when the Scene names boats, ships, "
    "beach, shoreline, landing, jumping off boats, torches, or swords, the "
    "visible frame must keep water, shoreline or beach, period-local wooden boat "
    "hulls, and the named landing action. People may appear only as period-local "
    "landing figures physically connected to the boat, beach, torch, or sword "
    "action. Do not replace the landing with an interior, courtyard, standing "
    "group portrait, dry street, gate, or generic soldiers without boats."
)

TRAVEL_CARRIED_VEHICLE_EVIDENCE_DIRECTIVE = (
    " || CARRIED LITTER EVIDENCE LOCK - when the Scene names a "
    "carried litter, sedan chair, or carried chair, that named carried "
    "litter or cabin stays visibly present as a primary story object. It is a "
    "shoulder-borne carried litter, supported by people and long parallel shoulder "
    "poles rather than by any ground-contact support structure. Compose the "
    "frame around one readable period-local shoulder-borne palanquin, covered "
    "carried litter, or carried chair in foreground or midground, with a roof or canopy, side "
    "curtains, long horizontal shoulder poles, rope ties, mud, rain wear, and "
    "cropped support walkers sharing the same shoulder-height crop and road "
    "context. Use a tight shoulder-height side close crop or rear three-quarter travel view with the camera "
    "parallel to the shoulder poles. The carried cabin, canopy, curtains, and "
    "long poles fill the visual center as the dominant subject; human "
    "evidence is secondary load-bearing contact evidence, not the main image "
    "subject. Visible human evidence is limited to the minimum fragments "
    "needed to prove the litter is being carried: shoulder lines pressed "
    "under poles, side/back upper arms, hands wrapped around poles, folded "
    "sleeves, waist sash edges partly hidden by poles, and narrow moving torso "
    "slices crossed by the poles. Walking lower legs or feet appear only as "
    "tiny cropped hints if needed. If a face is "
    "visible, it is a small profile or oblique edge face subordinate to the "
    "pole contact. Support-figure upper bodies "
    "stay small, side/back turned, hidden by the cabin, behind poles, behind "
    "curtains, or cropped at the frame edge. Upper chest fronts stay outside "
    "the readable frame or are physically crossed by poles, hands, sleeves, "
    "straps, curtains, or cabin edges. Visible cloth fronts are narrow oblique "
    "slices crossed by poles, hands, sleeves, straps, or curtains. "
    "Two long parallel shoulder poles are the only support structure connecting "
    "the carried cabin to the walkers; each pole visibly crosses support "
    "walker shoulder lines at front and rear. Suspension reads from horizontal shoulder poles and load-bearing "
    "shoulders, with open air, hanging curtain shadow, robe overlap, mud "
    "shadow, and a narrow strip of road dust below the cabin. The lower cabin "
    "edge is cropped or held high in open air, with open shadow below the "
    "suspended body. The lower third contains only empty shadow gap, road dust, "
    "robe hems, and cropped bearer feet at far edges. The visible load path is "
    "pole-to-shoulder-to-hand only, with the cabin floating above the road as a "
    "hanging load. Every "
    "visible support fragment is "
    "anatomically connected: the pole rests on the same figure's shoulder "
    "line, the same figure's hand or sleeve stabilizes it, and that figure's "
    "shoulder, sleeve, and hand align under the same pole load. Carrier and escort torsos "
    "use side, back, rear three-quarter, or oblique three-quarter turns with "
    "the robe front reduced to a narrow moving edge. Shoulder poles, gripping "
    "hands, folded sleeves, straps, or curtains physically cross the upper body "
    "of each readable walker. Support walkers stay behind poles, behind "
    "curtains, cropped at the side, or turned away in staggered depth. "
    "Load-bearing proof belongs to shoulder and hand contact under the poles; "
    "any road contact is limited to small cropped support-walker foot hints "
    "while the carried cabin remains "
    "suspended between the shoulder poles. The carried litter remains the "
    "main carried subject, larger than the surrounding walking people and "
    "visibly tied to the carriers. Litter "
    "panels and curtains remain blank material surfaces."
)

TRAVEL_WHEELED_VEHICLE_EVIDENCE_DIRECTIVE = (
    " || WHEELED TRAVEL VEHICLE EVIDENCE LOCK - when the Scene names a cart, "
    "carriage, wagon, handcart, ox cart, or other wheeled land travel vehicle, "
    "that named vehicle stays visibly present as a primary story object. "
    "Compose the frame around one readable period-local wheeled vehicle in "
    "foreground or midground, with side panels, wheels, axle, shafts, rope "
    "ties, mud, rain wear, and nearby attendants, drivers, or guards sharing "
    "the same road and ground plane. It is not replaced by a walking crowd, "
    "empty road, building, or generic procession. Vehicle panels and curtains "
    "remain blank material surfaces."
)

PAPER_EVIDENCE_SURFACE_DIRECTIVE = (
    " || PAPER EVIDENCE SURFACE LOCK - paper, book, document, scroll, petition, "
    "letter, page, manuscript, ledger, or archive objects appear only when the "
    "Scene names them. Scene-named paper evidence appears as cord-tied closed "
    "cream bundles held edge-on, folded packets, rolled bundles, narrow bundle "
    "spines, tied cord knots, stacked edge thickness, cloth-wrapped packets, "
    "or cover backs turned away from the camera. Broad paper faces stay folded "
    "closed, covered by hands or cloth wrap, or angled edge-on; the visible "
    "surface detail is paper grain, folded edges, tied cords, dust, and light. "
    "Open flat sheets, table route drawings, exposed page faces, brush rows, "
    "black squiggles, diagram strokes, and calligraphy-like marks stay absent "
    "unless the Scene explicitly asks for a visible marked surface. "
    "If the Scene names tally marks, account marks, counted marks, ledger marks, "
    "or accounting evidence in a historical setting, express the count as "
    "non-writing physical counters: plain notched wooden tally sticks, cord "
    "knots, pebble groups, sealed bundle counts, edge notches, or tied tags "
    "with no ink and no symbol. Do not render rows of ink marks on a paper "
    "or ledger face. "
    "When the Scene asks for blank paper, a blank book, blank imported book, "
    "blank document, blank page, blank ledger, or blank foreign paper, the blank "
    "surface contains no portrait, face drawing, figure drawing, landscape drawing, "
    "map, route, diagram, illustration, decorative cover image, symbol, or organized "
    "row of marks; it remains paper grain, cover cloth, folded edges, page thickness, "
    "cord ties, stains, and shadow only. "
    "Rolled scroll and petition exteriors stay blank unmarked cylinders: visible "
    "edges show only paper fiber, cord ties, end rings, dents, stains, and shadow. "
    "Small marks resolve as isolated stains, wrinkles, fiber "
    "speckles, or handling shadows spread irregularly across the closed object, "
    "not organized into rows. Sealed decrees, requests, letters, and court papers "
    "stay closed in hands as short cord-tied roll cylinders, folded packets, "
    "rolled bundles, tied edge-on bundles, or hand-covered objects. Tables near paper evidence remain bare wood, lamp, cloth, bowls, "
    "shadows, or empty space only. "
    "Wall decoration inventory remains empty; empty walls stay plaster, wood "
    "grain, cracks, dust, and shadow only."
)

DEPICTED_SURFACE_OBJECT_DIRECTIVE = (
    " || DEPICTED SURFACE OBJECT LOCK - when the cut asks for figures, animals, "
    "or events only as marks on a document, scroll, "
    "tablet, mural, relief, painting, or other visual surface, the first visible "
    "subject is the physical surface itself. Render the object as the dominant "
    "foreground material: paper grain, cord ties, rolled edges, folded packets, "
    "stone relief plane, plaster wall plane, carved edge depth, pigment stains, "
    "candlelight, dust, and worn material texture. Any depicted figures remain "
    "flat tiny surface marks fused into that material plane, while the live "
    "frame reads as object evidence rather than a character or battle scene."
)

INANIMATE_STATUE_OBJECT_DIRECTIVE = (
    " || INANIMATE STATUE OBJECT LOCK - when the Scene names a statue, idol, "
    "sculpture, figurine, monument, bust, relief figure, or carved deity image, "
    "the first visible subject is the inanimate physical object itself. Render "
    "it as one coherent object made of the material named or implied by the "
    "Scene and era: gold, bronze, stone, clay, wood, plaster, pigment, dust, "
    "chips, edge wear, seams, carved contours, pedestal contact, temple shadow, "
    "and directional light. Human or animal body parts named inside the statue "
    "description are sculpted object shapes fused into the same statue material. "
    "Object identity comes from material surface, silhouette, pedestal, temple "
    "placement, lighting, and age wear."
)

ANIMAL_SUBJECT_PHYSICAL_DIRECTIVE = (
    " || ANIMAL SUBJECT PHYSICAL LOCK - when the Scene asks for animals as the "
    "visible subject, render them as natural animals of that species. Cats and "
    "kittens use four-legged feline bodies, paws on the ground, real cat heads, "
    "ears, whiskers, tails, fur pattern variation, crouching, sitting, walking, "
    "or sniffing poses. Horses and other quadrupeds use one head, one neck, one "
    "torso, four attached legs, and one tail if visible, with no duplicate body "
    "or fused second animal. Place animals at animal scale beside the Scene-named "
    "objects and terrain. Clothing, armor, tools, weapons, and upright human "
    "poses belong only to living people explicitly named by the Scene."
)

ANIMAL_BARE_BODY_DIRECTIVE = (
    " || ANIMAL BARE BODY LOCK - when the Scene names animals without collars, "
    "leashes, harnesses, saddles, blankets, clothing, tags, bells, jewelry, or "
    "decorative animal gear, the visible animal inventory is natural body only: "
    "bare fur or skin across the neck, chest, back, belly, legs, and tail, with "
    "species anatomy, natural markings, dust, light, and shadow as the complete "
    "animal surface detail."
)

FINAL_CLOTHING_SURFACE_DIRECTIVE = (
    " || FINAL CLOTHING SURFACE LOCK - every visible robe, cloth garment, "
    "cloth sleeve, cloth sash, and cloth upper torso stays as uninterrupted "
    "local fabric color. Cloth upper-body surfaces are broad blank textile "
    "made from neckline overlap, sleeve overlap, long fold shadows, fabric "
    "grain, waist sash geometry, and carried-object overlap. Clothing micro "
    "texture stays same-color and blends into folds. Any isolated bright or "
    "dark fleck on an upper chest resolves as fold shadow, fabric scuff, dust, "
    "or same-color weave, not as a separate mark. Scene-unnamed heraldry "
    "inventory is empty: identity marks do not appear on chest, sleeve, "
    "shoulder, sash, robe, or protective material panels; visible cloth remains "
    "material-only. Political, faction, court, clan, and rank identity never "
    "appears as invented chest heraldry when the Scene does not literally name "
    "a visible emblem. Angular high-contrast patches, colored "
    "applique plates, red-white applique clusters, decorative circular spots, "
    "floral spots, sunburst spots, medallion-like spots, fastener-like upper-chest spots, "
    "and high-contrast chest appliques are outside the visible clothing inventory "
    "and resolve into same-color folds, dust, or shadow. Dust and wear sit on "
    "cuffs, hems, lower robe edges, ground-facing fabric, footwear, carried "
    "objects, or environment surfaces. Role identity comes from silhouette, "
    "layer count, posture, face, carried objects, and era-local garment shape."
)

CARRIED_TRAVEL_VEHICLE_NEGATIVE_PROMPT = (
    "front-facing palanquin procession, front-facing bearers, front-facing "
    "palanquin escorts, full front robe torsos in palanquin scene, parade "
    "palanquin formation, separate foreground escort row, chest crests on "
    "palanquin bearers, robe mon on palanquin attendants, white chest marks "
    "on palanquin escorts, carried cabin standing on ground posts, cabin on "
    "vertical legs, freestanding roadside shelter, hut replacing carried "
    "cabin, foreground walking row not touching shoulder poles, carriers "
    "walking in front without carrying the load, disconnected shoulder "
    "poles, carrierless carried cabin, two-wheeled cart, handcart, rickshaw, "
    "pulled cart, pushcart, cart shafts, road wheel, wooden road wheel, round "
    "transport wheel, wheel pair, ground-rolling cabin, full side cart view, "
    "full undercarriage, visible undercarriage, full transport base, lower "
    "chassis, lower vehicle chassis, cabin base touching road, visible cart wheels, "
    "mobile hut on wheels, pavilion cart, wheeled pavilion, wheeled hut, "
    "shelter cart, wagon cabin, rolling cabin, round support under litter, "
    "dark circular support under litter, ground-level round support, "
    "full lower cabin touching road"
)

NO_TEXT_NEGATIVE_PROMPT = (
    "text, letters, words, numbers, writing, typography, captions, subtitles, labels, "
    "sign, signage, readable sign, readable text, readable letters, readable words, "
    "glyphs, characters, writing on book pages, fake book text, newspaper, poster text, billboard text, screen text, "
    "fake glyphs, pseudo calligraphy, fake kanji, fake characters, decorative symbols, "
    "characters on lamp, characters on lamp base, kanji on lamp, kana on lamp, "
    "glyphs on lamp, writing on lamp, text on lamp, lamp base inscription, "
    "metal inscription, writing on metal, characters on metal, glyphs on metal, "
    "stamped characters on vessel, marked lamp base, marked metal rim, "
    "symbol marks, crests, emblems, heraldic marks, mon crest, family crest, armor emblem, "
    "coat of arms, coats of arms, coat-of-arms, heraldic shield, heraldic shield patch, "
    "shield badge, shield-shaped badge, shield-shaped chest patch, shield-shaped robe patch, "
    "badge, badges, insignia, invented insignia, clothing insignia, robe insignia, "
    "armor insignia, armor badge, chest badge, sleeve badge, shoulder badge, robe badge, garment badge, "
    "circular badge, diamond mark, flower mark, stamped emblem, embroidered emblem, "
    "embroidered patch, chest patch, sleeve patch, shoulder patch, garment emblem, "
    "robe emblem, sash emblem, sleeve crest, chest crest, shoulder crest, small mon, "
    "fake mon, circular mon, diamond crest, decorative badge, orange badge, gold badge, "
    "red badge, round badge, colored chest dot, colored sleeve dot, colored robe dot, "
    "mon-like circle, circular gold emblem, circular orange emblem, "
    "yellow chest dot, yellow robe dot, gold chest dot, small yellow emblem, "
    "rosette badge, flower badge, round floral badge, gold rosette, "
    "small floral chest emblem, chrysanthemum badge, white dot on clothing, "
    "small white chest dot, white robe dot, round white button, small white button, "
    "pin badge, lapel pin, small white circular mark, single white chest mark, "
    "white hand-shaped robe mark, white fan-shaped chest mark, fan crest on robe, "
    "folded fan crest, white folded-fan symbol, white palm-like chest mark, "
    "handprint on robe, small white fan emblem, tiny white hand emblem, "
    "white abstract chest emblem, white chest motif, left chest emblem, right chest emblem, "
    "small circular robe emblem, matching chest crests, repeated chest crests, "
    "gold circular chest crest, round gold robe mon, rider chest badge, "
    "horseman chest emblem, circular samurai robe mark, family crest on rider chest, "
    "small pink patch, pink chest patch, red-white badge, small red square mark, "
    "red white chest crest, red-white chest crest, red white robe badge, "
    "colored heraldic crest, colored robe crest, multi-color robe emblem, "
    "embroidered shield badge, embroidered shield on robe, crest patch on robe, "
    "courtier crest badge, chest coat of arms, robe coat of arms, "
    "small pink label, colored rectangular chest mark, square clothing patch, "
    "pair of square robe patches, twin square robe marks, vertical square tag, "
    "small square mark on clothing, kanji patch on robe, kana patch on robe, "
    "small square mark on armor, square armor patch, white square armor mark, "
    "round armor badge, armor chest patch, tiny armor emblem, "
    "glyph patch on robe, white square glyph, black square glyph, contrast patch, "
    "colored robe label, kamon, Japanese kamon, kimono crest, hitatare crest, "
    "chest mon, sleeve mon, robe mon, small chest crest, two chest crests, "
    "gold crest on robe, white crest on robe, gold marking on robe, white mark on robe, "
    "small decorative chest symbol, chest ornament, chest decoration, upper chest mark, "
    "tiny robe mark, small robe symbol, contrast chest speck, chest-corner mark, "
    "white floral mark on robe, flower-shaped chest mark, small flower on chest, "
    "small flower on robe, gold flower on robe, chest flower, robe flower symbol, "
    "gold flower chest mark, yellow floral chest mark, gold sunburst chest mark, "
    "yellow sunburst chest mark, gold medallion chest mark, yellow medallion chest mark, "
    "golden chest ornament, yellow chest ornament, circular chest ornament, "
    "large flower brooch, flower-shaped robe ornament, floral shoulder clasp, "
    "decorative flower on chest, decorative flower on shoulder, white glyph rows on robe, "
    "white sketch marks on robe, "
    "sunburst robe emblem, medallion robe emblem, "
    "small gold emblem, small white glyph, white character on clothing, "
    "small rectangular badge, vertical badge, label-like clothing patch, "
    "hanging tag, belt tag, wooden tag, tally tag, identity tag, waist tag, "
    "belt plaque, belt charm, charm plaque, amulet with writing, charm text, "
    "floral robe pattern, flower embroidery, embroidered flowers, brocade pattern, "
    "patterned robe, patterned kimono, floral kimono, textile motif, clothing pattern, "
    "robe pattern, decorative hem motif, fabric symbol, "
    "banner symbol, flag symbol, sail symbol, palanquin writing, palanquin signboard, "
    "kanji on palanquin, kana on palanquin, vehicle panel text, cart signboard, "
    "carriage signboard, canopy text, hanging signboard, readable nameplate, "
    "decorative nameplate, gate name board, shrine name board, temple name board, "
    "overdoor name board, hanging name board, door header board, post plaque, "
    "pillar plaque, column plaque, paper talisman on post, wooden tag on post, "
    "vertical tag on post, hanging strip on pillar, calligraphy strip on pillar, "
    "calligraphy strip on post, column label, small yellow plaque on post, "
    "narrow hanging strip on post, under-eave "
    "signboard, eave signboard, under-roof plaque, small eaves plaque, "
    "small center board under roof, two-character eaves plaque, dark strokes "
    "under eaves, decorative eaves board, calligraphy plaque board, "
    "framed kanji board, overhead signboard, gate plaque, lintel plaque, "
    "inscription panel, character board, frontal gate facade replacing garden path, "
    "frontal gate facade replacing courtyard action, wall plaque text, framed text, framed writing, "
    "freestanding gateway on road, roofed gateway over road, signboard arch over road, "
    "coastal road gate sign, roadside gate sign, roadside entry sign, gatehouse portal on travel road, "
    "named-place entrance marker, roadside notice structure, shrine-style entry gate with signboard, "
    "roofed veranda replacing field, interior porch replacing paddy, timber hall replacing rice field, "
    "ceiling grid over farmland, windowed wall behind field survey, wall plaques above field survey, "
    "upper beam plaque, paired header plaques, small framed plaques on beam, character plates on upper beam, "
    "scribe writing characters, brush writing on paper, brush touching written page, filled ledger rows, "
    "handwritten roster entries, written tally board, inked tally board, marked tally mat, visible ink columns, "
    "flat tally board with lines, writing board with rows, drawn tally board, "
    "flat writing board, board full of line marks, "
    "lone warrior replacing record scene, spear replacing roster, armed portrait replacing tally, "
    "weapon-only symbol replacing accounting evidence, missing tally object, missing roster object, "
    "soldier lineup replacing moving families, guard lineup replacing household move, "
    "retainer families replaced by army lineup, missing chests, missing bundles, "
    "missing family, missing residence entry, modern kitchen stove, gas burner, "
    "modern saucepan, modern kettle, cooking pot replacing forge, faucet, sink faucet, "
    "written notebook in workshop, wall sign in workshop, modern collared shirt in workshop, "
    "missing forge, missing anvil, missing hammer, missing tongs, "
    "wall notice, notice board, hanging record text, wall-mounted paper text, "
            "wall scroll, hanging wall scroll, framed calligraphy, hanging calligraphy, "
            "calligraphy scroll, framed kanji, framed glyphs, decorative wall scroll, "
            "wall paper plaque, mounted document frame, "
            "small wall sign with black characters, rectangular wall plaque with two black characters, "
            "Chinese characters on plaster wall, black characters on wall board, "
            "writing board behind soldier, character board behind armed figure, "
            "rows of writing on paper, line rows on document, document text lines, "
    "handwritten rows, black strokes on paper, glyph-like paper marks, "
    "open document with writing, open sheet with lines, flat paper on table, "
    "tabletop paper text, text rows on table, written decree, written sheet, "
    "writing on scroll exterior, ink strokes on scroll, text on rolled scroll, "
    "pseudo calligraphy on scroll, black marks on scroll, scroll label, "
    "writing on rolled petition, ink rows on petition roll, "
    "doorway plaque text, lintel writing, kanji on lintel, overdoor text, "
    "transom text, display plank text, wheels on palanquin, wheeled palanquin, "
    "cart wheels on litter, palanquin cart, wagon-like palanquin, cart-like litter, "
    "axle under palanquin, wheel hub under litter, road wheels under carried chair, "
    "robe text, kanji on robe, writing on clothing, "
    "calligraphy on clothing, glyphs on sash, text on sleeve, clothing crest, "
    "watermark, logo, signature, artist signature, "
    "corner signature, signature-like marks, seal stamp, maker mark, corner glyphs, "
    "corner seal stamp, bottom right seal, artist seal, Japanese artist seal, "
    "black corner seal, red seal stamp, artist chop, signature seal, "
    "lower-left writing, lower-right writing, bottom-right signature, "
    "bottom-left signature, lower margin signature, corner credit marks, "
    "calligraphic credit cluster, handwritten corner marks, date numerals, "
    "production-date marks, tiny year numbers, title text, credits"
)

COMMON_ANATOMY_NEGATIVE_PROMPT = (
    "bad anatomy, deformed anatomy, malformed body, impossible body, broken body, "
    "extra head, duplicate head, missing head, fused heads, two heads on one person, "
    "one head with two bodies, two bodies sharing one head, duplicate torso, fused torsos, "
    "merged torsos, shared torso, conjoined bodies, body growing from another body, "
    "extra face, duplicate face, melted face, distorted face, asymmetrical eyes, "
    "extra arms, missing arms, fused arms, extra hands, missing hands, fused hands, "
    "mutated hands, malformed hands, broken fingers, extra fingers, missing fingers, "
    "fused fingers, too many fingers, duplicated fingers, forked fingers, webbed fingers, "
    "melted fingers, noodle fingers, boneless fingers, claw-like human fingers, "
    "long extra thumb, missing thumb, duplicated thumb, broken thumb, extra knuckles, "
    "impossible hand pose, twisted wrist, backwards wrist, detached hand, floating hand, "
    "oversized foreground hand, distorted close-up hand, extra legs, missing legs, fused legs, malformed legs, "
    "extra feet, missing feet, impossible joints, twisted limbs, disconnected limbs, "
    "headless torso, standalone legs, cropped bearer legs, dangling duplicate feet, "
    "hidden body under carried vehicle, disconnected support limbs"
)

ANIMAL_ANATOMY_NEGATIVE_PROMPT = (
    "animal with extra legs, animal with missing legs, five-legged animal, six-legged animal, "
    "three-legged animal unless explicitly requested, two-headed animal, extra animal head, "
    "one animal head with two bodies, two animal bodies sharing one head, double-bodied animal, "
    "fused animal bodies, merged animal torsos, duplicate animal torso, duplicate animal neck, "
    "extra animal neck, horse with two bodies, horse with duplicate torso, horse with extra neck, "
    "horse head fused to second body, two horse bodies sharing one head, "
    "centaur, horse-human hybrid, human torso on horse body, human upper body fused to horse body, "
    "rider torso growing from horse back, rider torso growing from horse neck, horse body with human chest, "
    "humanoid animal, upright animal body, animal wearing human armor, animal wearing human clothing, "
    "animal wearing robe, animal wearing cloak, animal wearing costume, clothed animal, "
    "tiger wearing robe, tiger wearing human clothing, animal holding weapon, "
    "mutated paws, fused paws, malformed tail, extra tail"
)

VISUAL_QA_NEGATIVE_PROMPT = (
    "workbench QA failure, review failure anatomy, ambiguous anatomy, unreadable hand count, "
    "six fingers, seven fingers, four fingers on visible human hand, finger cluster, "
    "finger stump, melted thumb, extra thumb, hand fused to weapon, hand fused to sleeve, "
    "weapon fused to palm, disconnected arm, duplicate forearm, impossible elbow, "
    "floating foot, detached foot, leg growing from cloth, duplicate knee, extra animal legs, "
    "missing animal legs, animal-human hybrid, animal with human hands, animal holding tools, "
    "centaur, horse-human hybrid, human torso on horse body, human upper body fused to horse body, "
    "wrong-period weapon, anachronistic weapon, fantasy weapon, fantasy armor, sci-fi armor, "
    "modern tactical gear, modern rifle, modern pistol, modern helmet, modern vehicle, "
    "modern harness, impossible historical prop"
)

COMMON_STYLE_NEGATIVE_PROMPT = (
    "childlike cartoon, children's book style, toddler drawing, kindergarten drawing, "
    "cute mascot, chibi, kawaii, toy-like character, plastic doll, plush toy, "
    "flat childish colors, childish rounded shapes, goofy expression, parody style, "
    "simple cartoon, cartoon illustration, documentary cartoon style, soft cartoon, "
    "pastel storybook, cute storybook, watercolor children's book, soft pastel "
    "palette, bright cheerful fairy-tale mood, low-contrast cute illustration, "
    "photorealistic, photorealism, photographic, live-action still, raw photo"
)

COMMON_COMPOSITION_NEGATIVE_PROMPT = (
    "static lineup, flat lineup, parade lineup, full-body group lineup, "
    "evenly spaced soldiers, all figures facing camera, idle standing group, "
    "posed group portrait, passport portrait, stiff symmetrical pose, side-by-side row, "
    "equal-height lineup, soldiers in a row, row of soldiers, parade spacing, "
    "background soldiers, distant soldiers, crowd of soldiers, army crowd, "
    "crowded ranks, many soldiers, extra soldiers, extra background figures"
)

UNREQUESTED_EXTRA_PEOPLE_NEGATIVE_PROMPT = (
    "extra people not named by the Scene, additional readable companions, "
    "unrequested group portrait, unrequested bystanders, lineup replacing one person, "
    "multiple main figures when the Scene names one person, family group replacing "
    "single subject, attendants added without Scene request"
)

OUTDOOR_LOCATION_NEGATIVE_PROMPT = (
    "interior room replacing outdoor scene, indoor room replacing outdoor street, "
    "ceiling-dominant chamber replacing outdoor location, full overhead ceiling, "
    "roofed porch replacing street ground, covered veranda replacing outdoor route, "
    "corridor replacing road, studio portrait replacing outdoor action, indoor portrait, "
    "blank plaster room replacing exterior, men indoors instead of named outdoor place, "
    "missing outdoor ground, missing open sky, no visible exterior air, utility pole, "
    "power pole, telephone pole, cable pole, overhead wire, roof-to-roof wire, "
    "straight black cable line, modern street wire, crossarm utility pole, "
    "telephone pole with crossarms, pole with crossbar, sagging overhead cables, "
    "parallel wires across sky, streetlight pole, round streetlamp, telegraph pole, "
    "modern peaked cap, modern field cap, fedora, derby hat, bowler hat, homburg hat, "
    "trilby, top hat, modern felt hat, 19th century hat, 20th century hat, steel helmet, modern uniform tunic, "
    "buttoned military tunic, rifle-era marching column, "
    "gate signboard, wall sign, "
    "shop sign, street sign, temple signboard, shrine signboard, title panel, "
    "written banner, vertical banner text, hanging label strip, roadside placard"
)

SINGLE_WEAPON_NEGATIVE_PROMPT = (
    "extra weapon, duplicate weapon, multiple weapons per person, secondary weapon, "
    "spare sword, belt sword, visible sidearm, visible scabbard, weapon strapped on back, "
    "weapon at hip, hanging weapon, waist weapon, belt hilt, side scabbard, "
    "extra weapon silhouette"
)

UNREQUESTED_SWORD_NEGATIVE_PROMPT = (
    "sword, swords, blade, blades, dagger, daggers, knife, knives, tachi, saber, sabre, "
    "curved sword, short sword, scabbard, sword hilt, sword pommel, hilt at waist"
)

ADULT_FEMALE_SAFETY_NEGATIVE_PROMPT = (
    "underage, child, little girl, young girl, teenage girl, teen girl, schoolgirl, "
    "childlike female body, childlike female face, nude, naked, nipples, areola, "
    "genitals, explicit sexual act, pornographic, lingerie, bikini, swimsuit, "
    "modern pin-up costume"
)

COMMON_PERIOD_NEGATIVE_PROMPT = (
    "modern logo, watermark, modern signage, modern poster, modern screen, smartphone, "
    "mobile phone, cell phone, camera, handheld camera, recording device, black handheld rectangle, "
    "computer monitor, laptop, power line, power lines, overhead wire, overhead wires, "
    "utility cable, utility cables, electrical wire, electrical wires, roofline cable, "
    "telephone line, telephone wires, black cable in sky, utility pole, crossarm utility pole, "
    "telephone pole with crossarms, pole with crossbar, sagging overhead cables, "
    "parallel wires across sky, streetlight pole, round streetlamp, telegraph pole, neon sign, car, truck, bus, "
    "airplane, helicopter, factory machinery, industrial machinery, fluorescent light, "
    "fluorescent ceiling panel, LED ceiling light, rectangular ceiling light, modern light panel, "
    "ceiling light, electric ceiling light, modern ceiling lamp, round ceiling light, "
    "round dome ceiling lamp, pendant lamp, glowing ceiling fixture, central ceiling lamp, "
    "ceiling glow disc, dome lamp, ceiling-mounted lantern, recessed downlight, "
    "round ceiling disc, glowing ceiling dome, electric hanging lantern, "
    "modern pendant lantern, glowing overhead lantern fixture, wall switch, light switch, switch plate, "
    "outlet, electrical outlet, wall socket, modern wall socket, control panel, "
    "white plastic wall plate, outlet plate, electrical wall plate, small white wall rectangle, "
    "small gray wall rectangle, small black wall rectangle, isolated wall rectangle, "
    "isolated wall square, small wall panel, wall-mounted rectangular plate, "
    "two-dot wall panel, small rectangular wall fitting, rectangular plate on plaster, "
    "post-mounted switch plate, doorway wall switch, wall switch beside door, "
    "switch plate beside doorway, rectangular wall plate beside doorway, plastic "
    "wall button beside door, bright wall plate, modern vertical door handle, "
    "vertical metal door handle, rectangular metal door handle, modern pull handle, "
    "metal pull handle plate, door lever handle, shiny door handle, small rectangular "
    "recessed handle, rectangular lock plate, keyhole plate, modern door lock plate, "
    "compact door lock plate, digital door lock, electronic lock keypad, keypad lock, "
    "intercom panel, doorbell plate, narrow black vertical panel, modern sliding-door "
    "handle recess, transparent glass door, glass door panel, frameless glass door, "
    "modern glass wall panel, glass window wall, large transparent window pane, "
    "post plaque, plaque on post, character plaque on post, small "
    "rectangle on post, wall switch-like plate, switch-like rectangle on wall, "
    "weapon on groom, groom carrying weapon, groom holding baton, groom holding rod, "
    "groom with scabbard, baton at waist, rod at waist, weapon-shaped object at waist, modern suit, "
    "business suit, black suit jacket, blazer, jacket lapel, white shirt cuff, "
    "dress shirt cuff, office sleeve, necktie, business clothing, modern diplomat, "
    "modern envoy, collared western shirt, buttoned western shirt, rolled-sleeve "
    "shirt, belted western trousers, western trouser leg, suit trouser leg, "
    "modern peaked cap, modern field cap, fedora, derby hat, bowler hat, homburg hat, "
    "trilby, top hat, modern felt hat, 19th century hat, 20th century hat, steel helmet, modern uniform tunic, "
    "buttoned military tunic, rifle-era marching column, modern black leather boot, lace-up boot, rubber boot, combat boot, dress boot, "
    "rubber sole, zipper seam on trousers, black dress shoes, office shoes, "
    "business handshake, office handshake, two men in suits shaking hands, "
    "black suit handshake, modern diplomatic handshake, school uniform, modern clock, "
    "wall clock, clock face, wristwatch, digital clock, alarm clock, glass hourglass, "
    "hourglass timer, glass sand timer, labeled pedestal, text pedestal, thumbs-up icon, "
    "3D thumbs-up icon, social media icon, emoji icon, thought bubble, speech bubble, "
    "dialogue bubble, comic speech balloon, cartoon bubble"
)

ANCIENT_MEDITERRANEAN_MATERIAL_CULTURE_DIRECTIVE = (
    " || ANCIENT MEDITERRANEAN MATERIAL CULTURE LOCK - when the stated "
    "Year/period or Exact place is ancient Greek, Ionian, Hellenic, "
    "Macedonian, Roman, Aegean, Ephesus, or another BC/BCE classical "
    "Mediterranean context, every visible person, building, weapon, tool, "
    "lamp, and street detail must match that exact era and place. Civilians "
    "wear period-local chiton, himation, peplos, linen or wool tunic layers, "
    "cloaks, belts, tied hair, veils, and leather sandals as their role "
    "requires. Visible neck openings are draped cloth edges, pinned folds, "
    "wrapped shawls, or simple tunic openings only, with no collars, lapels, "
    "buttons, button plackets, cuffs, trouser legs, or modern jacket seams. "
    "Officials, guards, workers, artists, priests, worshippers, "
    "messengers, and crowds use role-appropriate ancient local garments, "
    "never later uniforms or modern formalwear. If armor is not literally "
    "named by the Scene, keep bodies unarmored. When armor or armed duty is "
    "named, use only period-local bronze, linen, leather, shield, spear, bow, "
    "or short blade forms appropriate to the exact culture. Architecture and "
    "streets use marble or stone temples, colonnades, mudbrick, plaster, "
    "timber roofs, oil lamps, torches, braziers, market stalls, dust, smoke, "
    "and period-local street materials. Temple friezes, lintels, doors, beams, "
    "walls, tablets, scrolls, and market surfaces remain blank material, relief "
    "carving, cracks, grain, dust, and shadow only, with no readable text and "
    "no pseudo-letters. Temple bands, friezes, pediments, lintels, and "
    "under-roof strips use plain stone joints, chips, shadow, or non-letter "
    "relief only; never alphabet rows, carved words, letter-like strokes, or "
    "caption bands. Prefer human-height oblique compositions that crop or angle "
    "away from upper temple bands, pediment centers, lintel centers, and wall "
    "notice areas unless the Scene explicitly names that surface as the subject. "
    "Default ancient building crops keep rooflines, over-door headers, broad "
    "lintels, frieze bands, and pediment centers outside the frame; show lower "
    "columns, stone walls, door shadows, people, hands, objects, and ground "
    "evidence instead. "
    "Do not center a temple facade around a horizontal inscription zone, and do "
    "not place paper notices, parchment sheets, posters, labels, or tablets on "
    "walls. Doors and gates use ancient blank planks, wooden bars, "
    "pegs, pivots, ropes, and hinges, not visible handle hardware, modern "
    "handles, or knobs. If a door appears, it is a plain plank slab or open "
    "dark doorway with no paired pull handles and no glass pane. Interior "
    "partitions are stone, plaster, timber, cloth, or shadow, never transparent "
    "glass panels. Architecture "
    "inventory is closed to triangular pediments, low tile roofs, marble or "
    "stone columns, rough plaster or mudbrick walls, timber beams, cloth "
    "awnings, stone steps, and open courtyards only. Zero roof crosses, zero "
    "church towers, zero bell towers, zero steeples, zero domes, zero modern "
    "windows, zero glass doors, zero transparent glass panels, and zero modern "
    "panel doors. Clothing inventory is closed to "
    "draped or wrapped fabric garments and period sandals; zero buttons, "
    "zero button rows, zero collars, zero lapels, zero trousers, and zero "
    "boots on civilian figures. Do not use "
    "Christian churches, steeples, crosses, medieval townhouses, Renaissance "
    "clothing, 18th to 20th century military coats, epaulets, shoulder boards, "
    "badges, shirt collars, white collars, collared shirts, neckties, suits, "
    "lapels, button plackets, modern trousers, pant legs, boots, or modern "
    "civic buildings."
)

ANCIENT_MEDITERRANEAN_WRONG_CULTURE_NEGATIVE_PROMPT = (
    "Christian church, chapel, church steeple, church tower, church cross, "
    "crucifix, gothic church, Romanesque church, medieval church, cathedral, "
    "bell tower with cross, modern European town square, Renaissance street, "
    "Victorian street, colonial uniform, Napoleonic uniform, 18th century "
    "uniform, 19th century uniform, 20th century uniform, officer coat, "
    "military coat, epaulet, epaulette, shoulder rank board, shoulder board, "
    "badge patch, star badge, medal badge, modern patrol uniform, modern "
    "field jacket, collared western shirt, buttoned western shirt, dress "
    "shirt, white shirt collar, shirt collar, buttons, buttoned garment, "
    "button placket, button row, "
    "cuff, suit lapel, jacket lapel, necktie, business suit, blazer, lapel "
    "jacket, modern trousers, pant legs, western trouser legs, black dress "
    "shoes, office shoes, modern boots, leather boots, boot shafts, modern haircut, modern "
    "procession, modern civic building, readable inscription, fake inscription, "
    "pseudo inscription, pseudo letters, Greek-like gibberish, East Asian "
    "characters, Chinese characters, Japanese characters, written signboard, "
    "shop sign, plaque with writing, door knob, round doorknob, modern door "
    "handle, vertical pull handle, rectangular lock plate, keyhole plate, "
    "transparent glass door, glass door panel, frameless glass door, modern "
    "glass wall panel, large transparent window pane, modern window frame, "
    "frieze inscription, lintel inscription, pediment inscription, under-roof "
    "letter row, carved alphabet row, engraved letters on temple, Latin capital "
    "letters, Greek capital letters, alphabet-like temple band, glass hourglass, "
    "hourglass timer, glass sand timer, labeled pedestal, text pedestal, "
    "centered temple inscription band, horizontal glyph band, wall paper notice, "
    "paper notice on wall, parchment note on wall, poster on wall, wall label, "
    "smartphone, mobile phone, cell phone, camera, handheld camera, recording device, "
    "black handheld rectangle, modern rectangular device, "
    "wall plaque behind tabletop, background wall sign in tabletop scene, "
    "cross necklace, pendant cross, cruciform pendant, "
    "medieval jester hat, jester cap, scientific tomes, modern book stack, "
    "book spine text, velvet curtain, ornate theater curtain, astrolabe, "
    "dome roof, church dome, bell tower, tower cross, "
    "roof cross, steeple cross, paired door handles, double door knobs, twin "
    "door pulls, metal door rings, paired metal rings on door"
)

HISTORICAL_SYMBOLIC_PROP_DIRECTIVE = (
    " || HISTORICAL SYMBOLIC PROP LOCK - in preindustrial or ancient scenes, "
    "symbolic ideas must appear as period-plausible physical evidence: bronze "
    "or clay tokens, seals, broken tally sticks, cord knots, pebbles, ritual "
    "objects, shadows, smoke, weather, or human gestures inside the same "
    "historical space. Do not visualize modern UI-like icons, emoji-like icons, "
    "floating cartoon bubbles, speech bubbles, dialogue balloons, social-media "
    "approval symbols, or contemporary "
    "timepieces. If the script asks for abstract support, approval, countdown, "
    "delay, choice, or consequence, translate it into period-local objects and "
    "cinematic staging rather than modern graphic symbols."
)

ACHAEMENID_EGYPTIAN_PERIOD_NEGATIVE_PROMPT = (
    "Greek hoplite helmet, Corinthian helmet, Attic helmet, crested helmet, "
    "horsehair crest helmet, Roman helmet, legionary helmet, medieval helmet, "
    "European knight armor, medieval plate armor, steel plate cuirass, fantasy armor, "
    "Viking helmet, horned helmet, crusader armor, samurai armor, metal shoulder armor, "
    "bronze shoulder armor, pauldrons, shoulder plates, round shoulder plates, "
    "metal breastplate, breastplate, cuirass, metal cuirass, plate cuirass, "
    "polished metal armor, segmented plate armor"
)

ACHAEMENID_EGYPTIAN_UNREQUESTED_ARMOR_NEGATIVE_PROMPT = (
    "scale armor, lamellar armor, metal scale armor, bronze scale armor, scale cuirass, "
    "metal chest armor, gold chest armor, ceremonial metal chest plate, metal collar plates, "
    "shoulder guards, armored shoulder pads, metal shoulder pads, bracers, greaves, "
    "metal wrist guards, heavy torso protection, rigid torso plates, broad pectoral necklace, "
    "gold pectoral necklace, metal collar necklace, decorative metal collar, ornate shoulder collar, "
    "Egyptian collar armor, gold shoulder collar"
)

EARLY_ANCIENT_CHINESE_MATERIAL_CULTURE_DIRECTIVE = (
    " || EARLY ANCIENT CHINA MATERIAL CULTURE LOCK - when the stated context is "
    "Shang, Western Zhou, Eastern Zhou, Spring and Autumn, Warring States, "
    "pre-Qin, or other early ancient China, every visible person, building, "
    "weapon, and prop follows that early Chinese Bronze Age or pre-Qin material "
    "culture. Rulers and nobles wear layered robes, sashes, compact caps or "
    "tied hair, jade or bronze ritual accessories only when scene-named, and "
    "plain textile surfaces. Guards, soldiers, scouts, and battlefield lords "
    "wear cloth tunics or robes under leather, rawhide, or bronze-scale "
    "protective layers with small overlapping plates, simple bronze helmets, "
    "belts, sandals or low boots, and period-local shields. Weapons are simple "
    "bronze spears, dagger-axes, halberds, bows, arrows, short bronze swords, "
    "or clubs only when the Scene names armed duty. Do not use medieval "
    "European plate, polished steel cuirasses, knight helmets, Roman armor, "
    "samurai armor, fantasy pauldrons, smooth breastplates, large shoulder "
    "plates, modern uniforms, or later imperial Chinese armor. Gate headers, "
    "doorway lintels, tower beams, and entrance crossbeams are continuous blank "
    "timber or plaster structural surfaces with no hanging plaques, no "
    "calligraphy boards, no inscribed signboards, and no character marks."
)

EARLY_ANCIENT_CHINESE_ARMED_ROLE_VISIBLE_SET_DIRECTIVE = (
    " || EARLY ANCIENT CHINA ARMED ROLE VISIBLE SET LOCK - for Shang, Western "
    "Zhou, Eastern Zhou, Spring and Autumn, Warring States, pre-Qin, or other "
    "early ancient Chinese armed scenes, the readable military silhouette is "
    "mostly cloth and leather, not steel armor. Visible torsos are layered "
    "cloth tunics or robes with broad sleeves, plain belts or sashes, leather "
    "straps, rawhide or leather vests, and only small dull bronze-scale patches "
    "when protective gear is needed. Shoulders remain cloth sleeves, robe "
    "folds, leather strap edges, or tiny scale rows close to the torso; no "
    "large metal shoulder guards, no rounded pauldrons, no smooth breastplate, "
    "no cuirass, no full plate, no polished steel, no knight helmet, no Roman "
    "armor, no samurai armor, and no later imperial armor. Helmets, when "
    "needed, are simple low bronze or leather helmets without crests, horns, "
    "visors, or ornamental protrusions. Role identity comes from robe layers, "
    "belt, posture, torch, spear, dagger-axe, halberd, bow, short bronze sword, "
    "dust, smoke, and tense body action."
)

EARLY_ANCIENT_CHINESE_WRONG_ARMOR_NEGATIVE_PROMPT = (
    "medieval European plate armor, European knight armor, knight helmet, "
    "closed visor helmet, crusader armor, Roman armor, Greek armor, samurai armor, "
    "Japanese armor, katana, fantasy armor, fantasy pauldrons, polished steel "
    "cuirass, smooth steel breastplate, silver breastplate, full plate armor, "
    "segmented steel cuirass, large metal shoulder plates, ornate metal "
    "pauldrons, later imperial Chinese armor, Tang armor, Song armor, Ming armor, "
    "Qing armor, modern military uniform, modern helmet, modern tactical armor, "
    "large metal shoulder guard, rounded metal shoulder plates, shiny shoulder "
    "armor, smooth metal torso armor, black steel breastplate, metal chest plate, "
    "inscribed gate plaque, calligraphy gate plaque, Chinese characters on gate, "
    "hanzi on gate, written signboard above door, character signboard above door"
)

EARLY_IMPERIAL_CHINESE_MATERIAL_CULTURE_DIRECTIVE = (
    " || EARLY IMPERIAL CHINA MATERIAL CULTURE LOCK - when the stated context "
    "is Han, Later Han, Eastern Han, early Three Kingdoms, Liaodong, Gongsun "
    "Kang, Chinese warlords, Chinese generals, or Chinese troops around the "
    "1st to 3rd century CE, every visible person, building, weapon, and prop "
    "follows late Han to early Three Kingdoms northern Chinese and Liaodong "
    "frontier material culture. Officials and warlords wear layered Han-period "
    "robes, plain sashes, compact cloth caps or tied hair, and unmarked textile "
    "surfaces. Guards, soldiers, generals, and cavalry use cloth tunics or robes "
    "under dull leather, rawhide, or dark iron lamellar and scale protection, "
    "simple low helmets or cloth caps, belts, low boots or cloth shoes, and "
    "period-local shields only when the Scene names armed duty. Weapons are "
    "spears, halberds, crossbows, bows, dao-style short blades, or plain iron "
    "swords only when the Scene names them. Architecture is packed-earth, "
    "timber hall, plain plaster wall, courtyard, frontier gate, or low tile "
    "roof only where the Liaodong/Han setting supports it. No Greek or Roman "
    "columns, no marble temples, no Mediterranean robes, no later Tang/Song/"
    "Ming/Qing court dress, no Joseon hanbok or gat, no samurai armor, no "
    "kimono, no fantasy plate armor, no modern uniforms, no epaulets, and no "
    "readable Chinese characters, plaques, chest labels, or signboards."
)

EARLY_IMPERIAL_CHINESE_WRONG_CULTURE_NEGATIVE_PROMPT = (
    "Greek columns, Roman columns, marble temple, Mediterranean robes, toga, "
    "chiton, himation, Greek crowd, Roman crowd, classical temple facade, "
    "Joseon hanbok, gat hat, tall black Korean horsehair hat, Korean palace "
    "roof, samurai armor, Japanese armor, kimono, katana, Tang robe, Song robe, "
    "Ming robe, Qing robe, Qing official hat, mandarin square, chest label, "
    "Chinese characters on chest, hanzi on chest, calligraphy chest patch, "
    "inscribed gate plaque, written signboard, calligraphy signboard, modern "
    "military uniform, epaulets, modern boots, polished steel cuirass, European "
    "plate armor, Roman armor, fantasy armor, large metal shoulder plates"
)

ACHAEMENID_EGYPTIAN_ARMED_GROUP_NEGATIVE_PROMPT = (
    "massive army, huge army, full army, army panorama, panoramic battlefield, "
    "wide army shot, full-body marching formation, walking soldier line, "
    "long line of troops, horizontal troop line, soldiers across the whole frame, "
    "background army, background troop ranks, distant spear ranks, tiny background soldiers, "
    "full body soldiers, standing full body, full-length bodies, boots visible, "
    "pants visible, visible legs, visible feet, knees visible, shins visible, lower-body lineup"
)

MEDIEVAL_CENTRAL_ASIAN_WRONG_CULTURE_NEGATIVE_PROMPT = (
    "samurai armor, Japanese armor, Japanese robe, kimono, hakama, eboshi, katana, "
    "tachi, wakizashi, Japanese timber gate, Japanese tiled roof, Japanese courtyard, "
    "European knight armor, plate armor, steel cuirass, crusader armor, Roman armor, "
    "full plate armor, polished steel cuirass, smooth metal breastplate, European "
    "breastplate, shiny metal armor, silver armor, gray steel armor, polished metal "
    "armor, segmented plate cuirass, smooth shoulder plates, steel shoulder plates, "
    "closed visor helmet, knight helmet, great helm, bascinet, sallet, armet, "
    "pauldrons, gorget, gauntlets, greaves, Greek columns, marble columns, "
    "classical temple columns, fantasy armor, chest emblem, chest crest, gold chest "
    "symbol, decorative breastplate ornament, round belt medallion, modern door "
    "handle, modern doorknob, modern room, modern map, glowing digital map"
)

WEST_AFRICAN_ASHANTI_WRONG_CULTURE_NEGATIVE_PROMPT = (
    "Japanese temple, Japanese timber gate, Japanese tiled roof, Japanese courtyard, "
    "Korean palace roof, Chinese palace roof, pagoda, torii gate, Shinto shrine, "
    "kimono, hanbok, samurai armor, Japanese lamellar armor, katana, tachi, "
    "wakizashi, East Asian official robe, East Asian palace, kanji, kana, hanzi, "
    "calligraphy signboard, European knight armor, medieval plate armor, Roman armor, "
    "Greek armor, polished steel cuirass, fantasy armor, castle battlements, "
    "European fairy-tale crown, treasure box replacing Golden Stool, bowl replacing "
    "Golden Stool, crown replacing Golden Stool, East Asian official portrait, "
    "East Asian administrator portrait, Japanese official interior, static soldier lineup, "
    "posed military group portrait, camera-facing row of soldiers, idle armed lineup, "
    "walking soldier lineup, calm marching row, group under quiet porch, East Asian "
    "administrator face, East Asian official face, forehead band on official"
)

MAP_SCENE_DIRECTIVE = (
    " || UNMARKED STRATEGIC BOARD LOCK - when the Scene asks for geographic "
    "planning evidence, render a low horizontal tactile marker layout as the "
    "main subject: a plain low wooden table surface, floor mat, clay slab, "
    "cloth planning surface, or ground-level tabletop surface appropriate to "
    "the stated era and place. Keep the camera looking down at the horizontal "
    "surface, top-down or close three-quarter tabletop view. The dominant "
    "visible shapes are physical markers resting on the surface: at least one "
    "loose route cord, two separated stone clusters, and one bronze weight, "
    "pin, or folded cloth strip. Geography appears only through these marker "
    "positions, cord paths, marker clusters, empty gaps between markers, "
    "shadows, and light. The plain surface remains visible as material gaps "
    "and margins between markers: wood grain, clay texture, cloth weave, "
    "parchment stain, broad dust, soft folds, cord shadows, pin shadows, and "
    "natural wear. Lower-left, lower-right, bottom, and corner zones remain "
    "plain material margins but still sit on the same horizontal surface. "
    "Preserve words like dark, ancient, controlled, uncontrolled, route, "
    "border, or territory as visual mood and marker placement. All geographic "
    "meaning appears through physical marker objects on the low horizontal "
    "surface. This is an unoccupied object-only tabletop or floor-surface "
    "evidence view with empty surrounding edges; visible subject inventory is "
    "only the low surface, marker objects, lamp light, shadows, surface edges, "
    "dust, and natural material texture. The camera crop stays on the low "
    "surface from edge to edge, filled by horizontal material margins and "
    "marker objects. Off-screen pressure appears only through "
    "lamp light, shadows, marker spacing, cord paths, surface dust, and edge "
    "shadows."
)

NO_MAP_DIRECTIVE = (
    " || HUMAN-SCALE GEOGRAPHY LOCK - when the story mentions territory, borders, "
    "routes, migration, kingdoms, expansion, or geography without asking for a "
    "map, render a close physical evidence scene instead: outdoor riverbank "
    "ground evidence, unmarked stones, bronze weights, sealed cord, travel-worn "
    "dirt, gate threshold, riverbank crossing, low grass, mountain haze, and "
    "open sky. The composition is a ground-level outdoor evidence shot with "
    "natural terrain, packed dirt, stones, bronze weights, and foreground objects."
)

NO_MAP_NEGATIVE_PROMPT = (
    "map labels, route labels, border labels, territory labels, place names on map, "
    "map legend, compass rose, location pin, modern map graphic, satellite map, "
    "infographic map, diagram map, UI map marker, ink map lines, drawn map borders, "
    "grid map, printed map, calligraphy on map, kanji on map, kana on map, hanzi on map, "
    "pseudo-kanji on map, pseudo-hanzi on map, pseudo-kana on map, map symbols, map arrows, "
    "faction symbols on map, readable marks on map, unreadable marks on map, "
    "signature-like marks on board, corner marks on board, lower-left board writing, "
    "lower-right board writing, clustered short strokes on board, corner glyphs on board, "
    "hands on board, hands framing board, board edge hands, cropped hands around board, "
    "business meeting hands, suit cuffs on board, shirt cuffs on board, "
    "foreground people around board, foreground samurai around board, armored figures around board, "
    "swords around board, chest armor beside board, readable people beside strategy board, "
    "faces around board, torsos around board, silhouettes around board, framed wall picture, "
    "large picture frame around people, wall-hung strategy board, vertical wall display, "
    "portrait panel replacing board, framed illustration scene, people inside a board frame, "
    "warriors painted inside strategy board, empty wall panel instead of tabletop board, "
    "plain empty framed rectangle, blank wall rectangle, vertical blank panel, "
    "empty board without marker objects, strategy board with no route cords, "
    "strategy board with no stone markers, single standing person beside table, "
    "bystander beside planning table, human figure beside table, courtier beside table, "
    "robed man beside map table, person near tactile marker layout, person in unoccupied evidence shot, "
    "room interior with standing people, standing men in room, full room interior replacing tabletop, "
    "wall-dominant empty room, doorway-dominant room"
)

CHARACTER_CLOSEUP_DIRECTIVE = (
    " || CHARACTER COMPOSITION LOCK - only when the Scene explicitly requests a "
    "close-up, portrait, face-only crop, or head-and-shoulders crop of a named character or major "
    "human figure, frame that living person as an extreme face-only close-up or tight "
    "bust portrait. Use a front-facing or three-quarter front camera angle with "
    "eye contact, the face and eyes clearly visible. Make one solitary face, "
    "natural hairline, neck, and a thin shoulder edge occupy almost the whole image area, "
    "roughly 98 percent of the frame, with background reduced to a narrow strip. "
    "Make the character's emotion or decision the visual focus, with portrait "
    "background reduced to the narrow Scene-named setting evidence: throne or "
    "seat texture, platform edge, hall wall, room wall, window edge, rain, dust, "
    "mountain haze, or plain earthen wall texture when no setting object is named. "
    "Use a bare compact human head for close portraits: visible natural hairline, "
    "simple tied hair behind the head, continuous clean forehead and cheeks, "
    "and role or rank shown through period-appropriate cloth neckline, "
    "draped chest edge, shoulders, robe, tunic, wrap garment, cloak, sash, or ordinary clothing named by "
    "the Scene and era. The portrait crop has a closed visible object set: "
    "face, hair, neck, cloth neckline or draped chest edge, shoulder clothing, the narrow "
    "Scene-named setting evidence, plain wall, rain lines, and shadow shapes "
    "only. Shoulder and back silhouettes are smooth "
    "fabric or period clothing curves against the plain wall."
)

CHARACTER_FACE_SURFACE_DIRECTIVE = (
    " || HUMAN FACE SURFACE LOCK - visible living human faces use natural skin "
    "planes, clear eyebrows, clear eyes, one nose, one mouth, plain forehead, "
    "plain cheeks, clean unpainted skin surface, and expression-driven emotion. "
    "The eye area is open skin, eyebrows, eyelids, clear pupils, and direct "
    "readable gaze as a continuous natural face surface. Gender, age, rank, and role "
    "follow the Scene wording: explicit gender words decide first, then role "
    "words such as king, queen, prince, princess, father, mother, warrior, "
    "soldier, commander, or ruler shape the face and body. Readable human face "
    "aesthetic: adult male subjects have a handsome, dignified, balanced face "
    "with strong clean features; adult female subjects have a beautiful, "
    "sensual, dignified, balanced face with graceful clean features and an "
    "alluring mature gaze. Head silhouette is "
    "compact and anatomically coherent: natural hairline and tied hair close "
    "behind the skull. The upper head area is natural hairline, tied hair, and "
    "continuous forehead skin; the full forehead from eyebrows to natural "
    "hairline is uninterrupted visible skin. Costume evidence stays on "
    "period-appropriate cloth neckline, draped chest edge, shoulders, robe, tunic, wrap garment, "
    "cloak, sash, belt, or ordinary clothing named by the Scene and era. Visible "
    "identity comes from expression, clothing, posture, light, and role."
)

ADULT_FEMALE_APPEAL_BODY_DIRECTIVE = (
    " || ADULT FEMALE APPEAL AND BODY SILHOUETTE LOCK - apply only to confirmed "
    "adult women. Render a mature adult woman with attractive, sensual, elegant "
    "presence and confident posture. Preserve the stated Year/period, Exact place, "
    "rank, role, and local clothing culture. Clothing may show period-plausible "
    "collarbones, neckline, shoulders, forearms, waist curve, hip line, and leg "
    "line through fitted or draped fabric when that is plausible for the era and "
    "role. If the Scene does not explicitly request a close-up, portrait, "
    "face-only, or head-and-shoulders crop, use a full-body, knee-up, or "
    "three-quarter-body composition so the full figure, body line, waist, hips, "
    "legs, posture, and silhouette are clearly readable. If the Scene explicitly "
    "requests a close-up or portrait, keep the mature allure in the face, gaze, "
    "neckline, shoulder line, and upper chest costume evidence. Exposure stays "
    "adult, period-plausible, role-appropriate, and grounded in local clothing "
    "culture."
)

SCENE_NAMED_IDENTITY_DIRECTIVE_PREFIX = (
    " || SCENE NAMED IDENTITY LOCK - the visible living person is the first "
    "named person from the Scene field. Render that exact named person, not "
    "the Main subject metadata, protagonist metadata, cast-list metadata, a "
    "generic warrior, a generic ruler, or a bystander. Identity facts control "
    "gender, age, rank, and role only. Visible props, equipment, animals, "
    "vehicles, and extra people come from the Scene field."
)

_KNOWN_SCENE_IDENTITY_FACTS: tuple[tuple[re.Pattern, str], ...] = (
    (
        re.compile(r"\bking\s+sansang\b|\bsansang\b|산상왕", re.IGNORECASE),
        "King Sansang is an adult man and Goguryeo ruler",
    ),
    (
        re.compile(r"\bbalgi\b|발기", re.IGNORECASE),
        "Balgi is an adult man and Goguryeo prince",
    ),
    (
        re.compile(r"\bgongsun\s+kang\b|공손강", re.IGNORECASE),
        "Gongsun Kang is an adult man and late Han Liaodong Chinese warlord",
    ),
    (
        re.compile(r"\bsoseono\b|소서노", re.IGNORECASE),
        "Soseono is an adult woman, a Goguryeo founding-era noblewoman and political leader",
    ),
    (
        re.compile(r"\byuhwa\b|유화", re.IGNORECASE),
        "Yuhwa is an adult woman, a Buyeo noblewoman and mother figure",
    ),
    (
        re.compile(r"\bjumong\b|주몽", re.IGNORECASE),
        "Jumong is an adult man and founding leader",
    ),
    (
        re.compile(r"\bking\s+dongmyeong\b|\bdongmyeong\b|동명왕", re.IGNORECASE),
        "King Dongmyeong is an adult man and ruler",
    ),
    (
        re.compile(r"\bsongyang\b|송양왕", re.IGNORECASE),
        "Songyang is an adult man and local ruler",
    ),
    (
        re.compile(r"\byeontabal\b|연타발", re.IGNORECASE),
        "Yeontabal is an adult man and clan elder",
    ),
    (
        re.compile(r"\bashikaga\s+takauji\b|아시카가\s*다카우지|다카우지", re.IGNORECASE),
        "Ashikaga Takauji is an adult man and Japanese samurai commander",
    ),
    (
        re.compile(r"\bnitta\s+yoshisada\b|닛타\s*요시사다|요시사다", re.IGNORECASE),
        "Nitta Yoshisada is an adult man and Japanese samurai commander",
    ),
    (
        re.compile(r"\bgo-?daigo\b|고다이고", re.IGNORECASE),
        "Emperor Go-Daigo is an adult man and Japanese emperor",
    ),
    (
        re.compile(r"\bcambyses(?:\s+ii)?\b|캄비세스", re.IGNORECASE),
        "Cambyses II is an adult man and Achaemenid Persian king",
    ),
)

MODERN_CHARACTER_CLOTHING_DIRECTIVE = (
    " || MODERN CHARACTER CLOTHING LOCK - when the Year/period, place, or Scene "
    "is present-day, contemporary, 20xx, 21st century, office, apartment, city, "
    "street, studio, school, hospital, or other modern setting, every visible "
    "person reads as contemporary civilian fabric clothing. Use only modern "
    "shirts, blouses, sweaters, jackets, coats, hoodies, cardigans, office wear, "
    "slacks, jeans, skirts, dresses, sneakers, bags, collars, lapels, seams, "
    "buttons, pockets, fabric folds, and soft textile highlights unless the "
    "Scene explicitly names specialized protective gear. Hard chest or shoulder "
    "shapes resolve as jacket seams, bag straps, lapels, pockets, reflections, "
    "or soft clothing folds."
)

HISTORICAL_HUMAN_CLOTHING_DIRECTIVE = (
    " || HISTORICAL HUMAN CLOTHING LOCK - every visible person wears garments "
    "from the stated Year/period and Exact place. Build clothing from the "
    "material-culture words already present in the prompt first; when the "
    "prompt does not name an exact garment, infer era-local civilian, official, "
    "traveler, messenger, worker, court, military, or ritual clothing from that "
    "specific date range and region. This applies to foreground, midground, "
    "background, doorway, corridor, window, crowd, servant, guard, envoy, and "
    "distant small figures with no exceptions. In any premodern setting, envoys, "
    "diplomats, interpreters, clerks, escorts, and attendants wear period-local "
    "formal robes, court dress, travel robes, armor, caps, sandals, boots, and "
    "hair arrangements from that era, never modern diplomatic clothing. Ancient, medieval, and early-modern people "
    "use local robe, tunic, wrap garment, cloak, sash, belt, sandal, boot, tied hair, "
    "and textile-layer forms appropriate to their role. Later historical "
    "people use period-accurate civilian, official, or military clothing of "
    "that decade and place. Visible neck openings, draped chest edges, sleeves, waistlines, leg coverings, "
    "footwear, cloth layers, hair ties, Scene-named carrying items, and role-specific outer layers all match "
    "the stated time and place. Every visible head uses compact period-local "
    "hair or head-covering forms from the exact era and culture. Ordinary "
    "figures use bare natural hairlines, tied hair, topknots, or close cloth "
    "wraps; formal or ritual figures use the compact local cap or hood shape "
    "appropriate to that role and period. Premodern footwear close-ups use "
    "period-local sandals, rawhide shoes, stitched leather turnshoes, cloth "
    "wrappings, gaiters, simple soft boots, or armor greaves appropriate to "
    "the exact era and role, without rubber soles, laces, zippers, polished "
    "modern shafts, or western trouser legs. No visible person may wear a modern "
    "business suit, blazer, lapel jacket, dress shirt, tie, modern trousers, "
    "belted western trousers, collared western shirt, rolled-sleeve shirt, "
    "office shoes, black dress shoes, uniform-like modern jacket, school-uniform "
    "jacket, or contemporary formalwear unless "
    "the stated Year/period is modern."
)

PREMODERN_FOOTWEAR_EVIDENCE_DIRECTIVE = (
    " || PREMODERN FOOTWEAR EVIDENCE CLOSE-UP LOCK - when the Scene is about "
    "a foot, shoe, sandal, gaiter, greave, or lower-leg step in a premodern "
    "setting, keep the composition as a grounded below-knee evidence shot, "
    "not a full standing character portrait. Show one or two period-local "
    "feet contacting the named ground, cloth, mud, stone, threshold, dust, "
    "or object. Footwear reads as hand-made era-local material: rawhide shoe, "
    "stitched leather turnshoe, cloth wrapping, sandal, gaiter, soft uneven "
    "leather boot, iron-shod leather edge, or strapped armor greave as the "
    "period and role require. Use dull irregular leather, cloth ties, raw "
    "seams, straps, mud, soot, and worn edges. Do not render glossy black "
    "modern boots, smooth rubber soles, lace eyelets, zipper seams, western "
    "trouser legs, knee-high dress-boot silhouettes, or a full-body warrior "
    "standing pose replacing the foot action."
)

HISTORICAL_UPPER_BODY_GROUP_CLOTHING_DIRECTIVE = (
    " || HISTORICAL HUMAN CLOTHING LOCK - every visible person wears garments "
    "from the stated Year/period and Exact place, with this armed group framed "
    "as a tight head-and-shoulders composition. Build visible clothing from the "
    "material-culture words already present in the prompt first. Visible clothing "
    "inventory is compact headwear or tied hair, robe shoulders, tunic shoulders, "
    "upper wrap cloth, sleeve openings, draped chest edges, chest cloth layers, "
    "woven trim, flat linen reinforcement tabs, hair ties, Scene-named handheld "
    "equipment, and role-specific upper outer layers from that exact date range "
    "and region. Every visible head uses compact period-local hair or "
    "head-covering forms from the exact era and culture."
)

HISTORICAL_BUILDING_HARDWARE_DIRECTIVE = (
    " || HISTORICAL BUILDING HARDWARE LOCK - for ancient, classical, medieval, "
    "early dynastic, preindustrial, or other flame-lit historical settings, "
    "building light and wall fixtures use period-local flame, daylight, and "
    "moonlight objects: clay oil lamps, candles, torches, "
    "braziers, small table, floor, doorway, or hand-carried lanterns appropriate "
    "to the era, open doorway moonlight, window slits, sun, and shadow. Ceiling "
    "centers remain exposed rafters, beams, planks, soot, dust, and shadow with "
    "no visible light-source object: no round ceiling disc, no recessed downlight, "
    "no glowing ceiling dome, no electric fixture, and no ceiling-mounted modern "
    "lamp. Active period light sits low, side-mounted "
    "below shoulder height, hand-held, table-held, floor-held, doorway-held, or "
    "off-frame according to the local era. "
    "Door and threshold details are "
    "wooden bars, rope pull loops, large hanging wooden or dark pull rings "
    "held by rope loops or dark hinge loops, hinge barrels, horizontal wooden latch bars, "
    "separated square nail heads, wooden pegs, irregular plaster repairs, clay repairs, stone chips, "
    "and bracket blocks. Historical door hardware does not use modern vertical "
    "pull handles, rectangular metal handle plates, lever handles, white switch "
    "plates, plastic wall plates, electronic lock keypads, digital door locks, "
    "intercom panels, doorbell plates, narrow black vertical panels, or modern "
    "sliding-door handle recesses beside doors. Plaster wall fields beside "
    "doors stay uninterrupted broad material surfaces from floor trim to beam; "
    "period hardware stays on door boards, beams, posts, thresholds, or latch "
    "bars rather than isolated on blank plaster. Blank plaster bays carry only "
    "same-material cracks, stains, clay repairs, dust, and shadow."
)

PREINDUSTRIAL_LAMP_PLACEMENT_DIRECTIVE = (
    " || PERIOD LAMP PLACEMENT LOCK - when the Scene names a lamp, lantern, "
    "candle, torch, brazier, or flame in a preindustrial setting, the visible "
    "flame source is low and local: one floor, table, doorway-sill, hand-held, "
    "or low-stand oil lamp, candle, torch, lantern, or brazier below shoulder "
    "height. Upper rafters, ceiling centers, high beams, and blank plaster bays "
    "remain unbroken dark material, timber grain, soot, dust, and shadow."
)

MEDIEVAL_JAPANESE_COSTUME_ARMOR_DIRECTIVE = (
    " || PERIOD-LOCAL JAPANESE COSTUME AND ARMOR LOCK - Japanese medieval, "
    "Kamakura, Kenmu, Nanboku-cho, Muromachi, or Sengoku contexts use Japanese material "
    "culture from the stated date and place. Samurai, warrior, commander, guard, "
    "retainer, armored envoy, armored messenger, escort, and military household roles "
    "wear matte cloth-covered, cord-laced "
    "Japanese protective dress built from o-yoroi, do-maru, haramaki, and "
    "kozane construction: dense tiny laced kozane rows, odoshi cord lanes, "
    "rectangular sode shoulder panels tied to shoulder cords, separated "
    "kusazuri skirt panels over hakama, hitatare sleeves under the protective "
    "dress, tied waist cords, and compact Japanese topknot or eboshi-style head "
    "forms when the role calls for it. The readable samurai silhouette is not "
    "a breastplate: it is two large hanging laced sode shoulder panels plus a "
    "flexible torso wrap made of many small scale rows. Sode panels hang "
    "outside the upper arms with squared vertical outer edges, visible attachment "
    "cords, and laced kozane rows continuing across each panel. The full chest "
    "front is an edge-to-edge field of small overlapping kozane tiles and "
    "odoshi cord lanes: at least twelve narrow horizontal rows, staggered scale "
    "divisions, scalloped lower edges, vertical lacing strands, fabric gaps, "
    "and tiny dark spaces between rows. Broad chest zones must be visually "
    "split from neck opening to waist and side edge to side edge by repeated "
    "scale rows and cords. The chest is an edge-to-edge flexible field of "
    "small overlapping scales, lacing lanes, fabric gaps, and panel edges. "
    "Role identity comes only from rows, lacing, tied cords, sode, "
    "kusazuri, cloth, and posture. The visible silhouette is strictly matte "
    "lacquered kozane rows, textile sleeves, cord lacing, and separated laced "
    "panels from shoulder to hip; chest and limbs show only small laced rows, "
    "cloth sleeves, tied cords, and separated kusazuri panels. Defensive dress "
    "chest centers, sleeve faces, and shoulder panels are uninterrupted "
    "material fields of lacing, scale rows, cord knots, matte wear, and shadow; "
    "small high-contrast squares, circles, or patches resolve as same-material "
    "lacing knots, panel gaps, scuffs, or shadows integrated into the armor rows. "
    "Defensive dress "
    "colors stay dull dark brown, black lacquer, muted cloth gray, and "
    "red-brown, with non-reflective matte surfaces and no broad continuous "
    "shine. "
    "The hips carry separated kusazuri laced skirt panels over hakama folds. "
    "Samurai hand equipment is limited to empty hands, belt posture, horse "
    "reins, document edges, or one Scene-named Japanese weapon; the other hand "
    "stays open, empty, or resting on sleeve, belt, reins, or paper. "
    "Court, messenger, monk, and civilian roles use Japanese hitatare, "
    "kariginu, kosode, hakama, court robe, monk robe, straw sandal, tabi, "
    "and tied hair silhouettes appropriate to the named role. Visible feet use "
    "waraji straw sandals, zori-style sandals, tabi socks, bare straw-soled "
    "footwear, or simple period footwear; no black leather dress shoes, glossy "
    "shoes, rubber soles, loafers, or western shoe silhouettes. Japanese gates, "
    "temple halls, roadside buildings, and military roads use timber posts, "
    "bracketed beams, tiled or thatched roof edges, plaster walls, stone bases, "
    "packed earth, mountain roads, and mist from medieval Japan."
)

MEDIEVAL_JAPANESE_WRONG_ARMOR_NEGATIVE_PROMPT = (
    "smooth metal breastplate, one-piece metal cuirass, polished steel cuirass, "
    "western plate armor, European knight armor, Roman armor, fantasy armor, "
    "generic fantasy samurai armor, Chinese court armor, Ming armor, Qing armor, "
    "Korean court armor, ornate metal shoulder guards, gold shoulder plates, "
    "decorative metal shoulder pads, oversized metal pauldrons, riveted steel breastplate, "
    "solid metal chest plate, broad metal pectoral plate, superhero chest armor, "
    "glossy black breastplate, black steel cuirass, mirror smooth torso armor, "
    "metal vambraces, metal arm guards, metal gauntlets, solid shin greaves, "
    "bronze armor, brass armor, gold armor, shiny gold cuirass, metallic gold breastplate, "
    "metallic blue armor, reflective shoulder plates, knee cops, elbow cops, "
    "tubular arm guards, full leg greaves, plated shin guards, chest emblem, "
    "armor crest, star crest, round mon emblem on armor, large flat chest apron, "
    "smooth brown chest plate, smooth leather cuirass, single-piece leather cuirass, "
    "unbroken leather breastplate, flat rectangular torso plate, vest-like armor, "
    "apron-like chest armor, smooth rectangular armor panels, gold chest design, "
    "gold chest emblem, gold chest motif, gold floral chest mark, painted chest emblem, "
    "decorative chest symbol, decorative chest mark, shiny metal lamellar, "
    "gray steel lamellar, steel scale armor, riveted leather plate vest, "
    "Chinese lamellar armor, Tang armor, Song armor, Yuan armor, Mongol lamellar, "
    "Korean lamellar armor, western plate cuirass, segmented steel breastplate, "
    "shiny silver armor, polished silver chest plate, steel chest plates, "
    "riveted chest grid, smooth segmented torso plate, black leather dress shoes, "
    "glossy black shoes, shiny black shoes, office shoes, loafers, modern loafers, "
    "western shoe silhouette, rubber sole, sneaker sole"
)

MEDIEVAL_JAPANESE_COURT_CIVILIAN_COSTUME_DIRECTIVE = (
    " || PERIOD-LOCAL JAPANESE COURT AND CIVILIAN COSTUME LOCK - Japanese "
    "medieval, Kamakura, Kenmu, Nanboku-cho, Muromachi, or Sengoku civilian, court, "
    "imperial, official, messenger, monk, household, travel, and ritual scenes "
    "use Japanese material culture from the stated date and place without "
    "invented armor. Emperors, courtiers, nobles, officials, and envoys wear "
    "layered court robes, kariginu, hitatare, kosode, hakama, eboshi or compact "
    "court headwear, soft textile collars, tied waist cords, and plain folded "
    "sleeves appropriate to rank and setting. Civilian and monk roles use "
    "kosode, hakama, monk robes, travel cloaks, straw sandals, tabi, simple "
    "bags, cord ties, and restrained local fabric layers. Chest, shoulders, "
    "waist, and forearms read as soft cloth folds, woven texture, stitched "
    "seams, robe overlap, sleeve volume, cord knots, and matte fabric. Court, "
    "civilian, monk, document, council, palace, and ritual figures remain "
    "soft-textile figures unless the Scene explicitly names samurai, armored "
    "retainers, soldiers, battle, combat, or explicit protective duty. Visible "
    "feet use waraji straw sandals, zori-style sandals, tabi socks, bare "
    "straw-soled footwear, or simple period footwear; no black leather dress "
    "shoes, glossy shoes, rubber soles, loafers, or western shoe silhouettes."
)

MEDIEVAL_JAPANESE_MARTIAL_CLOTHING_DIRECTIVE = (
    " || PERIOD-LOCAL JAPANESE MARTIAL CLOTHING LOCK - Japanese medieval, "
    "Kamakura, Kenmu, Nanboku-cho, Muromachi, or Sengoku scenes that name samurai, "
    "warriors, guards, retainers, commanders, escorts, or military household "
    "people without explicit battle, combat, or protective torso gear use "
    "period-local warrior clothing instead of chest protection. These figures "
    "wear hitatare, kosode, hakama, kariginu-like outer layers, cloth sashes, "
    "tied waist cords, compact topknots, eboshi-style head forms where formal, "
    "straw sandals or tabi, and plain scabbards or one Scene-named Japanese "
    "weapon only when the Scene names it. Chest, shoulders, forearms, waist, "
    "and hips read only as soft robe folds, layered collars, sleeve volume, "
    "tied cords, fabric seams, cloth belts, and matte textile wear in these "
    "non-combat social, court, travel, procession, document, or guard-watch "
    "scenes. Visible feet use waraji straw sandals, zori-style sandals, tabi "
    "socks, bare straw-soled footwear, or simple period footwear; no black "
    "leather dress shoes, glossy shoes, rubber soles, loafers, or western shoe "
    "silhouettes."
)

ACHAEMENID_EGYPTIAN_MATERIAL_CULTURE_DIRECTIVE = (
    " || PERIOD-LOCAL ACHAEMENID PERSIAN AND EGYPTIAN MATERIAL CULTURE LOCK - "
    "525 BC, Achaemenid Persian, Pelusium, Nile Delta, and Late Period Egyptian "
    "contexts use ancient Near Eastern and Egyptian material culture from the "
    "stated date and place. When the Scene names Persian soldiers or commanders, "
    "their visible upper-body clothing uses "
    "soft fabric tunic shoulders, robe upper folds, "
    "soft pointed caps or wrapped headcloths, and flat linen "
    "reinforcement patches when protection is needed. Broad chest "
    "areas display cloth tunics, belted robe folds, woven trim bands, "
    "woven linen layers, or small stitched linen reinforcement tabs kept "
    "flat against the fabric. When the Scene names Persian military equipment, "
    "choose one shared handheld equipment class directly named by the Scene "
    "for the whole readable formation. Generic soldier scenes use "
    "one shared short wooden spear class. When the Scene names Egyptian soldiers, "
    "priests, officials, or defenders, their visible upper-body clothing uses white or off-white "
    "linen upper wraps, plain linen chest folds, "
    "striped headcloths or close linen head wraps, linen ties, "
    "and Scene-named local defensive gear or spears when the Scene names defenders. Architecture "
    "and setting read as Nile Delta mudbrick walls, plastered Egyptian gates, "
    "papyrus reeds, palm trunks, desert sand, river edge, low sun, temple "
    "courtyards, and painted but unlettered geometric wall color fields. "
    "Faces, Scene-named equipment, animals, and clothing stay ancient Persian or "
    "Egyptian; visible torso shapes resolve as matte fabric folds, woven linen layers, "
    "flat woven trim bands, stitched linen tabs, woven reed texture on "
    "Scene-named equipment, or "
    "campaign dust. Headwear material reads as folded matte cloth with soft "
    "seams and wrapped fabric edges. Visible military headwear stays cloth-based: "
    "soft pointed caps, wrapped headcloths, or close linen headcloths; torso "
    "protection stays textile, woven linen, reed, and leather-fitted "
    "equipment with flat non-plate silhouettes."
)

ACHAEMENID_EGYPTIAN_SETTING_MATERIAL_CULTURE_DIRECTIVE = (
    " || PERIOD-LOCAL ACHAEMENID PERSIAN AND EGYPTIAN SETTING MATERIAL LOCK - "
    "525 BC Pelusium, Nile Delta, Achaemenid Persian, and Late Period Egyptian "
    "object, animal, location, document, aftermath, and evidence cuts use "
    "ancient Near Eastern and Egyptian materials from the stated date and "
    "place. Visible setting identity comes from Nile Delta mudbrick walls, "
    "plastered Egyptian gates, papyrus reeds, palm trunks, desert sand, river "
    "edge, low sun, temple courtyards, plain timber beams, clay vessels, bronze "
    "fittings, woven reed texture, linen cloth, woven cord, dust, and "
    "painted but unlettered geometric wall color fields. Scene-named animals "
    "remain animal-scale subjects in that setting. Scene-named discarded "
    "weapons or shields lie as unattended ground objects with bronze, wood, "
    "leather, reed, dust, and shadow as their visible material evidence."
)

MEDIEVAL_CENTRAL_ASIAN_MATERIAL_CULTURE_DIRECTIVE = (
    " || PERIOD-LOCAL MEDIEVAL CENTRAL ASIAN MATERIAL CULTURE LOCK - when the "
    "stated Year/period and Exact place indicate 12th-13th century Central "
    "Asia, Khwarazm, Otrar, Transoxiana, the Silk Road, or Mongol-Khwarazmian "
    "conflict, visible material culture must come from that era and region. "
    "Khwarazmian, Persianate, Islamic urban, merchant, official, governor, "
    "envoy, and market figures wear layered wool, cotton, or silk robes, tunics, "
    "caftans, wrapped turbans, soft caps, sashes, boots, cloak edges, and plain "
    "belts. Mongol, steppe, mounted, cavalry, horde, messenger, archer, or "
    "Genghis Khan figures wear deel-like robes, fur or felt hats, leather belts, "
    "lamellar or leather armor only when the Scene names military pressure, "
    "composite bows, quivers, sabers, and practical horse tack. Otrar and "
    "Khwarazmian settings use mud-brick walls, baked brick, plastered bazaars, "
    "arched gates, flat roofs, courtyard shadows, caravan goods, tents, desert "
    "dust, steppe grass, and Silk Road market materials. Do not import Japanese, "
    "European knight, Roman, Greek classical, or modern visual systems."
)

MEDIEVAL_CENTRAL_ASIAN_SETTING_MATERIAL_CULTURE_DIRECTIVE = (
    " || PERIOD-LOCAL MEDIEVAL CENTRAL ASIAN SETTING MATERIAL LOCK - 12th-13th "
    "century Central Asian, Khwarazmian, Otrar, Transoxiana, Silk Road, and "
    "Mongol-Khwarazmian object, map, city, market, room, aftermath, battlefield, "
    "and evidence cuts use local materials from the stated place. Visible "
    "setting identity comes from mud-brick city walls, baked brick, plaster, "
    "arched bazaars, flat roofs, wooden beams used sparingly, reed mats, carpets, "
    "low tables, bronze or clay lamps, leather bags, wool cloth, caravan packs, "
    "tents, desert dust, steppe grass, horses, composite bows, quivers, sabers, "
    "and plain Central Asian market goods. No Japanese timber architecture, "
    "Greek marble columns, European castle interiors, or modern rooms."
)

WEST_AFRICAN_ASHANTI_MATERIAL_CULTURE_DIRECTIVE = (
    " || PERIOD-LOCAL WEST AFRICAN ASHANTI AND GOLD COAST MATERIAL CULTURE LOCK - "
    "when the stated Year/period, Exact place, or Culture scope indicates Ashanti, "
    "Asante, Kumasi, Gold Coast, Yaa Asantewaa, Golden Stool, or British colonial "
    "Gold Coast context, visible material culture must come from that era and "
    "region. Yaa Asantewaa, Asante women leaders, Asante leaders, warriors, "
    "civilians, and court figures are Akan/Asante, "
    "Sub-Saharan West African people with dark brown to deep brown skin tones, "
    "Akan/Asante facial features, tightly curled or coiled black hair when hair "
    "is visible, wrapped strip-woven cloth, kente-like woven cloth where "
    "status is implied, plain cotton wraps, beads, sandals or bare feet, carved wooden stools, "
    "gold-weight and brass-regalia details, red earth courtyards, timber posts, "
    "plastered or earthen walls, thatch or period-local roofs, tropical forest "
    "edges, palm vegetation, and Kumasi compound architecture. Chiefs, priests, "
    "Yaa Asantewaa, Asante women leaders, warriors, markets, councils, and "
    "tradition scenes use local Asante people, "
    "status cloth, stools, staffs, beads, and packed red-earth or timber/plaster "
    "local spaces rather than East Asian court seating, East Asian villagers, or "
    "generic Asian robes. Every readable face in African chiefs, Ashanti chiefs, "
    "Asante chiefs, council, ritual, or local assembly scenes must read as Black "
    "African Akan/Asante, not East Asian, not generic Asian, and not pale-skinned "
    "court men. Do not add British soldiers, British officers, white drill "
    "uniforms, khaki colonial troops, or pith helmets to local Asante scenes unless "
    "the Scene directly names British or colonial personnel. British colonial officers or "
    "soldiers use period tropical khaki or white drill uniforms, pith or Wolseley "
    "helmets, puttees, boots, belts, and rifles only when the Scene names colonial "
    "military pressure. Ashanti warriors use period-local cloth war dress, belts, "
    "carried shields, spears, muskets, or rifles only when the Scene names armed "
    "conflict. Do not import East Asian faces or robes for local people, pale East "
    "Asian skin tones, East Asian headbands, topknots, Central Asian turbans, "
    "Middle Eastern robes, Indian robes, Japanese, Korean, Chinese, European "
    "knight, Roman, or fantasy visual systems."
)

WEST_AFRICAN_ASHANTI_SETTING_MATERIAL_CULTURE_DIRECTIVE = (
    " || PERIOD-LOCAL WEST AFRICAN ASHANTI AND GOLD COAST SETTING MATERIAL LOCK - "
    "Ashanti, Asante, Kumasi, Gold Coast, Golden Stool, and British colonial Gold "
    "Coast object, city, palace, courtyard, port, ship-arrival, aftermath, and "
    "evidence cuts use local materials from the stated place. Visible setting "
    "identity comes from Kumasi compounds, packed red earth, earthen or plastered "
    "walls, timber posts, courtyards, thatch or period-local roofs, tropical forest "
    "edges, palm vegetation, woven cloth, carved wooden stools, brass or gold "
    "regalia, clay vessels, low wooden supports, Akan/Asante Sub-Saharan West "
    "African people with dark brown to deep brown skin in wrapped strip-woven cloth "
    "when local people are named, colonial "
    "tropical uniforms only when British personnel are directly named, and humid West African light. "
    "Do not import Japanese timber gates, East Asian tiled roofs, East Asian "
    "faces or robes for local people, samurai armor, kimono, pagodas, medieval "
    "European castles, or fantasy palace architecture."
)

WEST_AFRICAN_ASHANTI_ARMED_ROLE_VISIBLE_SET_DIRECTIVE = (
    " || WEST AFRICAN ASHANTI ARMED ROLE VISIBLE SET LOCK - in Ashanti, Asante, "
    "Kumasi, Gold Coast, or British colonial Gold Coast battle, guard, soldier, "
    "warrior, officer, army, or clash scenes, visible bodies use local late "
    "19th to early 20th century clothing and equipment from the stated context. "
    "Asante fighters show wrapped cloth war dress, belts, bead or brass details, "
    "sandals or bare feet, shields, spears, muskets, or rifles only where the "
    "Scene implies armed conflict. British officers or troops show tropical "
    "khaki or white drill uniforms, pith or Wolseley helmets, puttees, boots, "
    "belts, and rifles. When the Scene says battle, battlefield, clash, armies, "
    "attack, charge, combat, or fighting, the composition must show active "
    "conflict with diagonal opposing motion, bent knees, lunging torsos, "
    "bracing, firing, recoiling, shield-raising, smoke, or dust; a calm "
    "standing lineup, camera-facing row, walking group, or posed military group "
    "portrait is invalid. Avoid metal plate cuirasses, samurai lamellar, katana, "
    "Roman armor, medieval knight armor, fantasy armor, and East Asian robes."
)

WEST_AFRICAN_ASHANTI_COLONIAL_OFFICIAL_DIRECTIVE = (
    " || WEST AFRICAN BRITISH COLONIAL OFFICIAL ROLE LOCK - in Ashanti, Asante, "
    "Kumasi, Gold Coast, Golden Stool, or British colonial Gold Coast scenes "
    "that name a British colonial officer, governor, commissioner, official, "
    "arrogant official, or an official confronting cultural artifacts, render "
    "the official as a British colonial administrator unless the Scene explicitly "
    "says Ashanti or Asante official. Make the official a late 19th to early "
    "20th century white European British colonial official of European ancestry in British "
    "tropical white drill or khaki uniform, pith or Wolseley helmet when "
    "appropriate, belt, boots, stiff collar or period field jacket, and a "
    "colonial harbor, office, courtyard, or administrative setting with Asante "
    "artifacts, carved stools, gold or brass regalia, woven cloth, and packed "
    "red-earth or plaster/timber local material where the Scene names artifacts. "
    "Do not render East Asian robes, kimono, hanbok, samurai clothing, East "
    "Asian court interiors, Japanese timber rooms, East Asian official portraits, "
    "forehead bands, East Asian faces, or East Asian administrator faces."
)

ACHAEMENID_EGYPTIAN_ARMORED_ROLE_VISIBLE_SET_DIRECTIVE = (
    " || ARMORED ROLE VISIBLE SET LOCK - when a 525 BC Achaemenid Persian, "
    "Pelusium, Nile Delta, or Late Period Egyptian Scene names armies, "
    "soldiers, guards, commanders, weapons, or battle pressure, the "
    "visible torso and shoulders read as ancient Near Eastern or Egyptian "
    "military dress from the stated place. Persian fighting figures use fabric "
    "tunic shoulders, robe upper folds, soft caps, woven trim bands, "
    "flat linen reinforcement patches, one shared Scene-selected "
    "handheld equipment class, and dusty cloth layers. Egyptian "
    "defenders use linen upper wraps, headcloths, plain linen chest folds, "
    "Scene-named defensive gear, spears, and linen ties. "
    "Broad chest areas show soft tunic fabric, belted robe folds, crossed "
    "woven trim bands, woven linen layers, or small stitched linen tabs; the "
    "torso silhouette stays straight, flat, matte, and textile-based. Military "
    "identity comes from soft fabric layers, woven trim bands, woven texture, "
    "equipment rims, linen folds, and dust."
)

ACHAEMENID_EGYPTIAN_UNARMORED_MILITARY_DRESS_DIRECTIVE = (
    " || ACHAEMENID EGYPTIAN TEXTILE MILITARY DRESS LOCK - when a 525 BC "
    "Achaemenid Persian, Pelusium, Nile Delta, or Late Period Egyptian Scene "
    "names soldiers, guards, armies, commanders, weapons, or battle pressure "
    "but does not explicitly name protective torso gear, render ordinary textile "
    "infantry dress. Persian fighting figures use soft pointed caps or wrapped cloth "
    "headgear, fabric tunic shoulders, robe upper folds, woven trim bands, "
    "linen reinforcement tabs kept flat, dusty sleeves, and one "
    "Scene-selected handheld item. Egyptian defenders use linen upper wraps: "
    "white or off-white linen upper wraps, close linen headcloths, "
    "linen ties, and desert "
    "dust. Upper torso, shoulder, and forearm zones read as cloth, linen, "
    "leather straps, cords, and dust; the torso silhouette stays straight, "
    "flat, matte, and textile-based, with soft textile-only silhouettes."
)

MEDIEVAL_CENTRAL_ASIAN_ARMORED_ROLE_VISIBLE_SET_DIRECTIVE = (
    " || MEDIEVAL CENTRAL ASIAN ARMED ROLE VISIBLE SET LOCK - when a 12th-13th "
    "century Central Asian, Khwarazmian, Otrar, Silk Road, or Mongol conflict "
    "Scene names soldiers, guards, warriors, cavalry, horde, battle, weapons, "
    "or military pressure, visible bodies use local steppe and Persianate "
    "military dress. Mongol or steppe fighters use deel-like robes, fur or felt "
    "hats, leather belts, small cord-tied lamellar scale rows, leather plates, "
    "quilted coats, simple conical or rounded helmets, composite bows, quivers, "
    "sabers, lances, and practical horse tack. Khwarazmian guards and urban "
    "soldiers use quilted coats, small lamellar rows under robes, wrapped turbans "
    "or soft caps, caftans, sashes, boots, round shields only when the Scene "
    "names shields, spears, sabers, and dusty cloth layers. Armor and weapons "
    "must not become samurai, European plate, polished steel cuirass, smooth "
    "metal breastplate, closed visor helmet, chest emblem, decorative breastplate "
    "ornament, round belt medallion, Roman, Greek, fantasy, or modern gear."
)

ACHAEMENID_EGYPTIAN_ARMED_GROUP_COMPOSITION_DIRECTIVE = (
    " || ACHAEMENID EGYPTIAN ARMED GROUP COMPOSITION LOCK - for 525 BC "
    "Achaemenid Persian, Pelusium, Nile Delta, or Late Period Egyptian scenes "
    "that name soldiers, armies, defenders, formation, marching, advancing, "
    "or battlefield group action, the first visible subject is the group action "
    "named by the Scene. Render a tight close-up collision crop with exactly four "
    "readable chest-up combat figures total, "
    "with every human inside the main foreground action cluster and dust haze "
    "behind them. Compose a staggered diagonal chest-up action cluster, compressed into a close collision cluster "
    "with exactly four separated chest-up period-clothed figures at different depths, "
    "visible air gaps between bodies and head silhouettes, foreground and midground "
    "overlap, alternating forward "
    "and rear positions, cropped edge figures, and one shared dust-haze backdrop "
    "with small upper strips of desert light, gate edge, river reeds, or wall edge. The complete visible human inventory is exactly four "
    "readable foreground figures total, all in the main action cluster; background "
    "depth is dust haze, reeds, gate edges, sky, light, and empty space. "
    "The ideal visible count is four frame-filling chest-up figures; there are "
    "zero readable people behind the cluster. The camera stays close enough that "
    "hips, thighs, knees, shins, legs, and feet are outside the image frame. "
    "Avoid a side-by-side row. Frame each readable figure from head to upper chest; "
    "the lower image edge crosses high upper chest cloth on every person. "
    "When the Scene says clash, battle, battlefield, or defenders, arrange two "
    "compact opposing subgroups facing each other from left and right, with a "
    "clear center collision zone made of crossed spear angles, dust, turned "
    "shoulders, tense faces, and braced upper bodies. When the Scene says march or "
    "advance without clash wording, show implied forward motion through leaning "
    "shoulders, angled spear shafts, tense faces, and dust, still cropped to head-through-upper-chest scale. "
    "The visible canvas contains faces, headwear, shoulders, upper chest cloth, "
    "forearms, hands, spear shafts, dust, diagonal motion, bracing shoulders, advancing or recoiling "
    "body angles, and one selected handheld equipment item per readable person. "
    "Readable Persian figures wear soft pointed caps or wrapped cloth headgear, "
    "soft fabric tunic shoulders, robe upper folds, woven trim bands, "
    "and dusty fabric layers. The visible formation "
    "uses one shared handheld equipment class directly named by the Scene. Generic "
    "soldier, army, or battlefield wording uses one shared short wooden spear "
    "class. Each readable figure shows one visible weapon total per person: one "
    "single selected item, held in a forward action angle, braced near the "
    "shoulder, or gripped by both hands on the same shaft, shield rim, or named "
    "equipment item. The other hand is open or rests on the same selected item, "
    "sleeve, or chest cloth. The selected handheld equipment item is the only "
    "weapon-shaped object on each readable figure. Readable "
    "Egyptian figures wear white or off-white linen upper wraps, striped or "
    "close linen headcloths, linen ties, and desert dust. "
    "Headwear silhouettes stay soft and cloth-based across the formation. "
    "All readable soldiers stay in tight head-to-upper-chest "
    "group scale; dust, angled weapons, shoulder rotation, face direction, depth separation, "
    "and staggered spacing carry the action pressure. One named ruler or commander "
    "may be slightly closer only when "
    "that person is named as the main action subject by the Scene."
)

ACHAEMENID_EGYPTIAN_ARMED_BODY_VISIBLE_SET_DIRECTIVE = (
    " || ARMED BODY VISIBLE SET LOCK - every readable armed person in a 525 BC "
    "Achaemenid Persian, Pelusium, Nile Delta, or Late Period Egyptian scene "
    "has one simple primary handheld equipment item from the Scene and era, two "
    "hands, sleeves, upper tunic or upper linen wrap fabric, and era-local "
    "headwear. The selected handheld equipment item is the only weapon-shaped "
    "object on each readable figure. The readable body area is head, shoulders, "
    "upper chest, sleeves, hands, and the selected handheld item. "
    "Persian bodies read through soft pointed caps or "
    "wrapped headcloths, tunic shoulders, robe upper folds, woven "
    "trim bands, dusty cloth layers, one shared "
    "Scene-selected handheld equipment class, woven linen "
    "reinforcement, and small stitched leather tabs kept flat when protection "
    "is needed. Egyptian bodies read through white linen "
    "upper wraps, headcloths, Scene-named defensive gear, spears, "
    "linen ties, and desert dust. Chest and shoulder "
    "areas resolve as cloth folds, linen layers, woven trim bands, wicker weave, "
    "or flat stitched leather reinforcement patches."
)

OVERLOOKING_VIEW_COMPOSITION_DIRECTIVE = (
    " || OVERLOOKING VIEW COMPOSITION LOCK - when the Scene says a person is "
    "looking over, looking out over, gazing over, overlooking, or standing at a "
    "window, ridge, balcony, hill, cliff, terrace, or room edge toward a valley, "
    "city, skyline, river, field, battlefield, sea, or landscape, the visible "
    "view is the main subject. Compose a medium or wide story frame: the person "
    "appears in the foreground or midground in side, back, or three-quarter-back "
    "view, looking toward the named view. For singular Scene wording such as "
    "a man, a woman, one person, or one named person, the foreground contains "
    "one visible person as the sole human focus. Compose a solitary "
    "one-person-only lookout image: the complete visible human "
    "inventory is exactly one living person total in the entire frame. Use a "
    "single-person-only composition: one isolated human body, one head, one torso "
    "silhouette, one ground shadow, and one clear ground gap around that person. "
    "Distant roads, paths, village edges, settlement marks, and skyline detail "
    "resolve as empty path, roofs, smoke, fences, carts, rocks, field marks, "
    "terrain texture, or architectural silhouettes. The named view, settlement, "
    "roads, and fields supply all other visual interest as landscape or building "
    "evidence. The landscape or city view fills most of the frame with readable "
    "depth, terrain or buildings, horizon, light, and atmosphere. The person is "
    "not a face-only portrait; posture and gaze carry the emotion."
)

GROUP_CHARACTER_COMPOSITION_DIRECTIVE = (
    " || GROUP CHARACTER COMPOSITION LOCK - this cut shows more than one living "
    "person, so compose one shared close group story moment with a compact "
    "asymmetric action cluster. Use tight waist-up framing from one offset three-quarter "
    "camera viewpoint, diagonal depth, overlapping foreground and midground "
    "figures, distinct side or three-quarter face angles, distinct posture for "
    "each person, and one principal action center. People use uneven spacing, "
    "varied heights, mixed turns, partial overlap, and diagonal depth. The lower image edge crosses waist sashes "
    "or upper hip cloth; sandals, feet, lower robe hems, and floor-length lower "
    "garment panels stay outside the frame. The upper image edge stays on "
    "plain mid-wall plaster, vertical posts, shutters, or open doorway light, "
    "with high wall bands and ceiling-dominant zones outside the crop. Keep only the number of people needed for "
    "the Scene readable; extra people dissolve into cropped shoulders, sleeves, "
    "hands, shadow, or background architecture. Group clothing and carried gear "
    "follow the stated era, place, and Scene roles. Civilians use plain "
    "single-color local fabric; any Scene-named protective gear follows "
    "era-local construction. Visible cloth and gear surfaces carry material "
    "texture, seams, cords, folds, dust, and material wear only. Place every "
    "Scene-named object, tool, animal, vehicle, furniture piece, closed tied "
    "bundle, lamp, doorway, or architectural evidence inside the same shared "
    "action center when the Scene names it. If the Scene names paper evidence, "
    "show only closed rolls or folded bundles held edge-on in hands. Each "
    "front-facing person has hands, sleeves, a closed roll, or a folded bundle "
    "crossing the upper torso; figures without a paper prop use side turns, "
    "partial overlap, or background placement. Table surfaces stay bare setting material."
)

GROUP_PLANNING_SURFACE_DIRECTIVE = (
    " || GROUP PLANNING SURFACE LOCK - when people gather for a council, "
    "campaign, strategy, war, or resistance planning scene, the visible "
    "planning evidence fills the full frame edge to edge as a bare low "
    "horizontal wood, cloth, mat, or clay surface with movable physical markers "
    "only. Compose a steep top-down tabletop or floor-surface evidence crop "
    "looking directly at the horizontal surface plane; the camera crop contains "
    "only the horizontal planning surface, marker objects, edge-cropped sleeve "
    "and hand fragments, light, dust, and shadows. People appear only as cropped hands, fingertips, sleeves, forearm "
    "edges, and shadow edges around the surface border, with every face, head, "
    "shoulder, torso, and full person outside the readable image. Show loose route cords crossing three "
    "separated marker clusters, at least seven separated stone markers, one "
    "palm-sized bronze weight or pin, low side candle or oil lamp light from "
    "table edge or floor edge, hand shadows, dust, and blank "
    "material margins as the complete planning surface detail. The camera "
    "stays locked to the horizontal surface from border to border and never "
    "leaves the surface plane. Candle or oil-lamp light comes from a low side "
    "source at the table edge, floor edge, hand, or low stand. "
    "The table or floor "
    "surface stays bare period material; tension comes from cropped hands, "
    "sleeve pressure, low side light, route cords, marker spacing, and shadow."
)

GROUP_PLANNING_SURFACE_NEGATIVE_PROMPT = (
    "open paper floor plan with writing, drawn floor plan lines, floor plan text, "
    "room diagram on paper, architectural blueprint, ink floor plan, tabletop "
    "paper map, plan labels, fake map scribbles, fake writing on plan, paper "
    "plan with glyphs, marked paper plan, strategy table covered with writing, "
    "map-like paper with line rows, paper diagram covered in lines, labeled "
    "floor plan, readable plan marks, unreadable plan marks, tactical paper "
    "covered in symbols, empty planning table, bare table with no markers, "
    "plain empty table, planning surface without route cords, planning surface "
    "without stone markers, overhead ceiling light above council, fluorescent "
    "light above table, round ceiling light above table, central round ceiling "
    "lamp, ceiling fixture over council, overhead lamp, wall switch, light "
    "switch, switch plate, outlet, electrical outlet, wall socket, modern wall "
    "socket, control panel, paper sheets on planning table, flat paper sheets "
    "on table, paper rectangles on planning table, full faces around planning surface, "
    "heads around planning table, shoulders around planning table, full torsos around planning table, "
    "seated council faces over table, large robed faces around table, human figure beside table, "
    "room wall behind planning table, windows behind planning table, doorways behind planning table, "
    "front-facing empty wall, blank room wall replacing table, vertical plaster wall replacing planning surface, "
    "interior room view without tabletop markers, empty room with lamp, floor-only empty room, "
    "lamp beside empty wall, "
    "drawn route lines without cords, thin ink route lines only, map line drawing on table, "
    "table cracks replacing route cords, markerless table scratches, natural cracks replacing route cords"
)

STEALTH_SLEEPING_WATCHMEN_STORY_DIRECTIVE = (
    " || STEALTH SLEEPING WATCHMEN STORY LOCK - this cut is a stealth escape "
    "scene with one principal moving person and inactive low figures. The principal moving person is the only upright "
    "moving human figure and shows two open palms, visible relaxed fingers, "
    "sleeves, and robe cloth as the complete hand inventory. Every other human "
    "figure is a sleeping or drunk watchman in a low inactive pose: lying "
    "horizontally on the floor, reclining against a wall, slumped low beside "
    "the doorway, or collapsed on a mat with closed eyelids, tilted head, loose "
    "arms, and relaxed hands resting on floor or cloth. The complete secondary "
    "human inventory is low bodies only: every non-principal head stays below "
    "the principal person's waistline, with shoulders touching floor, mat, wall "
    "base, or door threshold. The moonlit path, door "
    "opening, diagonal body spacing, quiet shadow, and clear gap between the "
    "moving person and the inactive watchmen carry the scene action."
)

ARMED_GROUP_REPRESENTATIVE_COMPOSITION_DIRECTIVE = (
    " || ARMED GROUP REPRESENTATIVE COMPOSITION LOCK - for armed group, army, "
    "guard, warrior, soldier, or battle scenes, compose one representative "
    "foreground fighter as the readable subject, but do not make a face-only "
    "or ID portrait. Use a medium-close or waist-up three-quarter action frame "
    "with face, shoulders, torso angle, action arm, and the selected primary "
    "weapon item visible together. Show one front, side, or three-quarter "
    "combat body, one selected primary weapon item as the only readable "
    "weapon prop, and clear emotion through eyes, jaw, posture, grip, and "
    "movement. The complete visible subject set is one foreground fighter, "
    "one selected weapon item, smoke, dust, roof edges, thick timber posts, "
    "fence rails, mountain haze, and packed ground. Background human presence "
    "reads as smoke-shadow pressure only, with no readable extra bodies, hands, "
    "belts, or props. Background vertical shapes read as thick hut posts, fence "
    "rails, roof supports, or other blunt wooden structure lines with flat "
    "chopped ends and visible timber joints."
)

ARMED_GROUP_STANDOFF_COMPOSITION_DIRECTIVE = (
    " || ARMED GROUP STANDOFF COMPOSITION LOCK - this Scene explicitly names "
    "multiple armed groups, factions, guards behind rulers, or armed sides facing "
    "each other. Do not reduce it to one representative armored portrait. Compose "
    "one shared group standoff frame with at least two readable opposing clusters, "
    "side or three-quarter body turns, visible spacing between sides, readable "
    "faces, period-local armor or guard clothing, and one simple primary weapon "
    "per readable armed person when the Scene names weapons. Rulers, queens, or "
    "protected figures named by the Scene remain visible in front of or between "
    "their guards. The pressure comes from opposing posture, spear or weapon "
    "angles, staggered depth, dust, shadow, and hard side light."
)

ARMED_ROLE_PORTRAIT_CROP_DIRECTIVE = (
    " || ARMED ROLE PORTRAIT CROP LOCK - for armed role, guard, soldier, "
    "warrior, fighter, army, or battle-atmosphere scenes where the Scene does "
    "not name a specific hand prop, compose a medium-close or waist-up "
    "three-quarter story frame of one representative foreground armed figure. "
    "Do not make it a face-only ID portrait. The camera shows the head, neck, "
    "shoulders, torso angle, sleeves, belt or sash edge when visible, upper "
    "chest protection or military clothing, action posture, smoke, dust, roof edges, thick timber posts, "
    "fence rails, mountain haze, and packed ground. Lower frame corners read as packed dirt, straw texture, a blunt "
    "wooden fence rail with flat cut ends, cloak edge, or soft smoke shadow. "
    "The role reads through armor surface, body angle, posture, eyes, smoke, and "
    "battlefield pressure."
)

MULTI_CHARACTER_CLOSEUP_DIRECTIVE = (
    " || MULTI CHARACTER CLOSEUP LOCK - this Scene explicitly requests a close-up "
    "of more than one person's face, eyes, or gaze. Preserve the requested close "
    "crop instead of widening to a waist-up group shot. Compose exactly the named "
    "close-up: two eyes or two faces when the Scene says two, tight opposing "
    "close crop, sharp gaze, readable emotion, hard side light, and only narrow "
    "period-local background strips. No full-body lineup, no casual group pose, "
    "no extra attendants, and no unrelated people."
)

SCENE_CONTENT_PRIORITY_DIRECTIVE = (
    " || SCENE CONTENT PRIORITY - the Scene field defines what is actually visible. "
    "Global visual world and Material culture fields are background constraints only, "
    "used for era and place context. Include visible subjects, props, animals, "
    "architecture, groups, tools, and action when they are named by the Scene field."
)

MAP_OBJECT_SCENE_CONTENT_PRIORITY_DIRECTIVE = (
    " || SCENE CONTENT PRIORITY - the Scene field defines what is actually "
    "visible. For a strategic planning evidence cut, visible content is limited "
    "to the requested low horizontal surface, marker objects, lamp light, "
    "shadows, dust, material edges, and period material texture named or "
    "implied by the Scene. Global visual world and Material culture fields are "
    "background constraints only for era and place material choice."
)

ARMED_FIGURE_LOADOUT_DIRECTIVE = (
    " || ARMED FIGURE LOADOUT LOCK - when soldiers, guards, warriors, fighters, "
    "archers, armies, police, security, or any armed group appear, each person "
    "has one simple visible primary weapon only. A person's entire visible "
    "loadout is the single primary weapon named or implied by the Scene and "
    "era. Translate wide or crowded armed-group scenes into one representative "
    "armed person in the foreground. Make exactly one foreground armed person "
    "readable; the remaining battlefield pressure reads through smoke, dust, "
    "roof edges, thick timber posts, fence rails, mountain haze, and packed "
    "ground. The complete readable human set is one foreground fighter only. "
    "Choose one shared primary weapon class for all readable armed people in "
    "the formation. If the Scene lists multiple weapons, select the single "
    "weapon class that best fits the action and era for the whole readable "
    "formation. Each readable armed person's primary weapon appears as one "
    "close shoulder-side prop according to the selected period weapon lock. "
    "When the selected layout uses a free hand, that hand reads as open, empty, "
    "or resting on clothing. Chest, belt, back, shoulder line, and off-hand read as "
    "empty uncluttered clothing or armor planes. Each readable armed "
    "individual shows one clear weapon item total. The selected weapon class "
    "is described once in the period weapon lock and remains binding across "
    "the readable formation. Every readable waist area resolves as a flat "
    "tied cloth sash, flat leather belt strap, center knot, robe fold, or "
    "armor layer edge. Side waist and hip zones contain only flat sash, robe "
    "folds, dust, and plain fabric shadow; the selected primary weapon is the "
    "only weapon-shaped object attached to or held by a readable person. "
    "Frame the foreground armed person as a medium-close or waist-up "
    "three-quarter action crop; visible areas include face, neck, shoulders, "
    "torso angle, sleeves, hands, belt or sash edge when visible, chest armor "
    "or military clothing, cloak, and the single selected foreground weapon "
    "prop in a physically plausible grip, guard, carry, or braced position."
)

ARMED_BODY_VISIBLE_SET_DIRECTIVE = (
    " || ARMED BODY VISIBLE SET LOCK - every readable armed person's visible "
    "personal inventory is the selected primary weapon item, two hands, "
    "sleeves, tunic or robe fabric, era-local armor surfaces when era-appropriate, one flat "
    "belt or cloth sash, one center knot, and soft folded sash tails. Waist, "
    "hip, back, chest, and shoulder areas resolve as continuous fabric, flat "
    "leather, or armor surfaces. Armor chest and shoulder surfaces read "
    "as plain material surfaces with rivets, seams, scratches, and natural "
    "light. Belt lines are uninterrupted flat stripes that end inside cloth "
    "folds or the center knot. Short dark shapes near hips "
    "resolve as folded sash tails, robe-edge shadows, flat armor edges, or belt "
    "ends with rounded fabric tips. Background upright lines read as thick "
    "timber posts, fence rails, hut edges, or roof supports with flat chopped "
    "wooden ends."
)

JAPANESE_ARMED_BODY_VISIBLE_SET_DIRECTIVE = (
    " || ARMED BODY VISIBLE SET LOCK - for medieval Japanese armed scenes, "
    "every readable armed person's visible personal inventory is the selected "
    "primary Japanese weapon item when the Scene names one, two hands, sleeves, "
    "hitatare or robe fabric, do-maru or haramaki torso wrap, large laced sode "
    "shoulder panels, kusazuri skirt panels, one flat belt or cloth sash, one "
    "center knot, and folded sash tails. Waist, hip, back, chest, and "
    "shoulder areas resolve as fabric, matte lacquered kozane rows, odoshi cord "
    "lanes, laced panel edges, and cloth gaps. Chest and shoulders read as "
    "flexible Japanese laced protective dress with visible cord lanes and "
    "separated sode panels. Chest surfaces stay material-only: matte small "
    "kozane rows, odoshi cord lanes, fabric gaps, laced panel edges, and "
    "natural wear. "
    "Belt lines are uninterrupted flat stripes that end inside "
    "cloth folds or the center knot. Short dark shapes near hips resolve as "
    "folded sash tails, robe-edge shadows, kusazuri panel edges, or belt ends "
    "with rounded fabric tips. Background upright lines read as thick timber "
    "posts, fence rails, gate edges, or roof supports with flat chopped wooden "
    "ends."
)

ARMORED_ROLE_VISIBLE_SET_DIRECTIVE = (
    " || ARMORED ROLE VISIBLE SET LOCK - when the Scene names armor, armour, "
    "lamellar, armored roles, samurai, warriors, soldiers, guards, retainers, "
    "commanders, or military household roles, the visible torso and shoulders "
    "read as role armor from the stated era and place. Chest, shoulder, waist, "
    "hip, and forearm areas are built from era-local armor layers, laced panels, "
    "cord knots, shoulder guards, skirt panels, cloth sleeves under armor, "
    "hakama or robe folds under armor, tied waist cords, leather or lacquer "
    "surfaces, rivets, scratches, and natural material wear. The armor surface "
    "carries the role identity while hands stay on the named action or empty "
    "belt posture."
)

JAPANESE_ARMORED_ROLE_VISIBLE_SET_DIRECTIVE = (
    " || ARMORED ROLE VISIBLE SET LOCK - when a medieval Japanese Scene names "
    "samurai, warriors, guards, retainers, commanders, armored envoys, armored "
    "messengers, escorts, or military household roles, the visible torso and shoulders read as matte cord-laced Japanese "
    "kozane defensive dress from the stated date and place. Chest, shoulder, "
    "waist, hip, and forearm areas are built from repeated small kozane rows, "
    "odoshi cord lanes, laced sode shoulder panels, kusazuri skirt panels, "
    "cloth sleeves, hakama or robe folds, tied waist cords, dark lacquer, "
    "fabric gaps, and non-reflective material wear. Chest surfaces are plain "
    "material-only laced rows, cord lanes, panel edges, textile gaps, and "
    "matte surface wear. Chest centers, sleeve faces, and shoulder panels are "
    "uninterrupted material fields; small high-contrast squares, circles, or "
    "patches resolve as same-material lacing knots, panel gaps, scuffs, or "
    "shadows integrated into the armor rows. "
    "Samurai hands stay empty, on "
    "reins, on document edges, or on one Scene-named Japanese weapon. The "
    "defensive dress carries role identity through lacing, scale rows, sode, "
    "kusazuri, and cord knots. Visible feet use waraji straw sandals, zori-style "
    "sandals, tabi socks, bare straw-soled footwear, or simple period footwear; "
    "no black leather dress shoes, glossy shoes, rubber soles, loafers, or "
    "western shoe silhouettes."
)

JAPANESE_MARTIAL_ROLE_VISIBLE_SET_DIRECTIVE = (
    " || MARTIAL ROLE CLOTHING VISIBLE SET LOCK - when a medieval Japanese Scene "
    "names samurai, warriors, guards, retainers, commanders, escorts, or military "
    "household roles without explicit battle, combat, or protective torso gear, "
    "the visible body reads as period-local warrior clothing, not chest "
    "protection. Visible inventory is hitatare, kosode, hakama, kariginu-like "
    "outer cloth, layered collars, broad sleeves, cloth sash or tied waist cord, "
    "plain scabbard or one Scene-named Japanese weapon only when named, topknot "
    "or eboshi-style head form, and ordinary fabric wear. Chest and shoulder "
    "areas stay material-only soft textile folds, layered collars, sleeve "
    "overlap, same-color cords, dust, stains, and shadow. Visible feet use "
    "waraji straw sandals, zori-style sandals, tabi socks, bare straw-soled "
    "footwear, or simple period footwear; no black leather dress shoes, glossy "
    "shoes, rubber soles, loafers, or western shoe silhouettes."
)

UNARMED_HUMAN_VISIBLE_SET_DIRECTIVE = (
    " || ORDINARY HUMAN VISIBLE SET LOCK - for civilian, social, household, "
    "work, travel, ritual, court, family, village, camp, settlement, or modern "
    "daily-life scenes, visible people carry ordinary clothing and the everyday "
    "objects named by the Scene only. Hands are empty or interact with the named "
    "work, household, travel, ritual, furniture, shelter, or daily-life objects. "
    "Waist, hip, back, chest, and shoulder areas read as smooth continuous "
    "civilian fabric, flat belts, cloth sashes, robe folds, bags, straps, "
    "aprons, cloaks, tunics, wrap garments, or other ordinary clothing surfaces "
    "appropriate to the exact era and role named by the Scene. Upper-chest "
    "areas remain blank continuous cloth fields containing only same-color "
    "folds, fabric grain, stains, dust, and shadow."
)

CAMP_WORK_VISIBLE_SET_DIRECTIVE = (
    " || CAMP WORK VISIBLE SET LOCK - for camps, refugees, settlers, workers, "
    "farmers, villagers, or migration scenes without armed action, visible "
    "hands use camp and work objects named by the Scene field, such as straw bundles, rope ties, "
    "pottery, baskets, timber poles, woven mats, sacks, cloth bundles, wooden "
    "digging tools, or shelter materials. Group tension comes from posture, "
    "work gestures, weather, and shared pressure inside one continuous camp "
    "space. The complete visible torso material set is soft woven cloth, hemp, "
    "wool, fur cloak edges, rope, basket straps, apron fabric, straw, wood, "
    "pottery, and packed earth."
)

MILITARY_LOGISTICS_VISIBLE_SET_DIRECTIVE = (
    " || MILITARY LOGISTICS GROUP VISIBLE SET LOCK - for Scene-named military "
    "camp, retreat, arrival, baggage, supply, flat armor stack, or field-support "
    "moments, keep the group as one shared logistics action. Visible people "
    "use the roles named by the Scene field, such as warriors, retainers, messengers, camp "
    "workers, officials, or civilians. Scene-named military objects stay visible "
    "at the action center as dark lacquered lamellar armor rolls, stacked "
    "rows of small overlapping laced scale layers, cloth-wrapped armor packets, "
    "flat folded armor panels, cord-bound laced armor packets, plain dark leather "
    "armor surfaces, and simple wooden carrying racks. The visible bundle "
    "texture is layered scale edges, dark leather, lacquer, cloth wrap, tight "
    "cord bands, and hard armor contours. In Japanese medieval contexts, armor "
    "flat armor stacks read as flat stacks of laced kozane scale rows, "
    "folded sode shoulder panels, do-maru torso wraps, haramaki torso wraps, "
    "kusazuri skirt panels, odoshi cords, dark lacquer surfaces, leather straps, "
    "and many small scale-layer edges tied together with cords. If a camp entrance or roofed opening "
    "is visible, its upper span is a continuous timber beam, rafters, bracket "
    "blocks, plank seams, knots, and wood grain. Weapons appear only when the "
    "Scene names a weapon."
)


def _selected_period_weapon_loadout_directive(prompt: str) -> str:
    target = ((_scene_text(prompt) or prompt or "")).lower()
    selected_is_shield = False
    if _scene_requests_achaemenid_egyptian_armed_group(prompt):
        if re.search(r"\b(shield|shields|wicker\s+shield|leather-covered\s+shield)\b|방패", target):
            equipment = (
                "one plain period shield per readable defender, held high at upper "
                "chest level as one continuous wicker or leather-covered shield "
                "face with one rim and one central grip"
            )
        elif re.search(
            r"\b(bow|bows|archer|archers|arrow|arrows|shoot|shooting|aim|aiming|"
            r"ranged|long-distance|target)\b|활|화살|궁수|사격|쏘|겨냥|백보|100보",
            target,
        ):
            equipment = (
                "one compact bow or one bow-and-arrow combined prop per readable "
                "archer, held at upper chest and shoulder level as one connected "
                "object"
            )
        elif re.search(r"\b(sword|swords|blade|blades|knife|knives)\b|검|칼|도검", target):
            equipment = (
                "one plain short sword per readable fighter, held across the upper "
                "chest as one connected blade-and-grip object"
            )
        else:
            equipment = (
                "one single vertical short wooden spear per readable soldier, "
                "one shaft with one small leaf-shaped spearhead held upright near "
                "the shoulder line"
            )
        return (
            " || SELECTED PERIOD WEAPON LOCK - for this armed group scene, "
            f"each readable person shows one visible weapon total per person: {equipment}. "
            "Hands hold that same single item or rest open on sleeve or chest cloth. "
            "The readable frame remains head-to-upper-chest; the lower image edge "
            "crosses upper chest cloth on every person. "
            "The selected item is the only weapon-shaped object on each readable figure."
        )
    if re.search(
        r"\b(bow|bows|archer|archers|arrow|arrows|shoot|shooting|aim|aiming|"
        r"ranged|long-distance|target)\b|활|화살|궁수|사격|쏘|겨냥|백보|100보",
        target,
    ):
        if re.search(r"\b(arrow|arrows|shoot|shooting|aim|aiming|target)\b|화살|사격|쏘|겨냥|백보|100보", target):
            weapon = (
                "one curved wooden bow with one fitted arrow as a single combined "
                "foreground prop: one continuous bent wooden bow body, one string "
                "line, one arrow shaft, one small arrowhead, one cord-wrapped grip, "
                "and one representative foreground archer holding that combined prop. "
                "Whole-image readable weapon inventory is one bow-and-one-arrow "
                "combined prop total, paired with the foreground archer. The "
                "bow-and-arrow prop stays in front of the torso and hands. The back "
                "shoulder plane is uninterrupted cloak, fur, tunic cloth, armor "
                "surface, or one flat leather strap. Background long shapes read as "
                "blunt timber posts or fence rails separated from the body silhouette. "
                "Waists and backs read as plain empty belts, tunic cloth, and armor "
                "surfaces"
            )
        else:
            weapon = (
                "one curved wooden bow as the single foreground prop in a close "
                "upper-body bow-evidence portrait: one unstrung ceremonial display "
                "bow, one vertical C-shaped wooden bow limb cropped along the right "
                "image edge, visible bow geometry made from curved wood and one "
                "small cord-wrapped grip patch at hand or shoulder height, and one "
                "representative foreground person paired with that side-edge bow. "
                "Whole-image readable weapon inventory is one bow prop total. "
                "The readable body area is face, shoulders, upper chest, neckline, "
                "cloak, tunic cloth, armor surface, belt edge, sash edge, "
                "and one flat leather strap. Hands and lower weapon geometry fall "
                "outside the lower or right frame edge. Background long shapes "
                "read as blunt timber posts, roof beams, or fence rails separated "
                "from the body silhouette. Spare visible hand detail rests on the "
                "bow grip patch, sleeve, neckline, belt edge, or cloth fold"
            )
    elif re.search(r"\b(spear|spears|lance|lances|pole|spear-line)\b|창|장창", target):
        weapon = (
            "one simple wooden spear as the selected shoulder-side prop: a "
            "single short visible shaft section with one small leaf-shaped iron "
            "tip beside the representative foreground fighter's shoulder. "
            "Whole-image readable weapon inventory is one spear prop total and "
            "one metal spearhead total, paired with the foreground fighter. "
            "Hands stay as body-gesture hands resting on chest armor, cloak "
            "edge, neckline, or cloth fold. Background vertical marks read as "
            "thick blunt timber posts, fence rails, hut edges, or roof supports "
            "with flat chopped wooden ends. Waists and backs read as plain "
            "empty clothing and armor surfaces"
        )
    elif re.search(r"\btachi\b", target, re.IGNORECASE):
        weapon = (
            "one sheathed tachi as the only visible weapon item in the whole "
            "image: one connected scabbard-and-hilt object at the waist, plain "
            "scabbard surface, and one wrapped grip. Both hands rest together "
            "on that same connected object. The metal blade area remains "
            "inside the plain scabbard. Waist area and lower frame are clean "
            "empty leather belt, tunic cloth, and armor surfaces"
        )
    elif re.search(r"\b(shield|shields|wicker\s+shield|leather-covered\s+shield)\b|방패", target):
        selected_is_shield = True
        weapon = (
            "one plain period shield as the only visible handheld equipment item "
            "in the whole image: one wicker or leather-covered shield face from "
            "the Scene, one simple rim, one central grip or strap. The visible "
            "handheld inventory stays shield-only. Whole-image readable equipment "
            "inventory is one shield item total per readable fighter. Hands rest "
            "on the shield grip, shield rim, sleeve, neckline, belt edge, or cloth "
            "fold. Waist area and lower frame are clean empty leather belt, tunic "
            "cloth, and armor surfaces"
        )
    elif re.search(r"\b(sword|swords|blade|blades|knife|knives)\b|검|칼|도검", target):
        weapon = (
            "one plain short iron sword as the only visible weapon item in "
            "the whole image: one continuous single-blade item with one simple "
            "wood or cord-wrapped grip held by one representative foreground "
            "fighter. The complete visible handheld set is this one sword: one "
            "blade and one grip. Both hands stack together on that same single "
            "grip, fingers wrapped around the same handle. Waist area and "
            "lower frame are clean empty leather belt, tunic cloth, and armor "
            "surfaces"
        )
    else:
        weapon = (
            "one plain short iron sword as the selected close chest-side prop: "
            "one flat short blade section and one simple grip crossing near the "
            "foreground fighter's upper chest. Whole-image readable weapon "
            "inventory is one short sword prop total, paired with the foreground "
            "fighter. Hands stay as body-gesture hands resting on chest armor, "
            "cloak edge, neckline, or cloth fold. Background vertical marks read "
            "as thick blunt timber posts, fence rails, hut edges, or roof "
            "supports with flat chopped wooden ends. Waists and backs read as "
            "plain empty clothing and armor surfaces"
        )
    inventory_item = "weapon or shield item" if selected_is_shield else "weapon item"
    readable_shape = "weapon or shield shape" if selected_is_shield else "weapon shape"
    return (
        " || SELECTED PERIOD WEAPON LOCK - For this armed historical scene, "
        f"the readable frame uses {weapon}. Belts, backs, chests, shoulder "
        "lines, and spare hands stay as empty plain clothing or armor surfaces. "
        "Visible belt straps are uninterrupted blank leather lines, flat cloth "
        "sashes, center knots, robe folds, or layered armor edges. "
        f"The only readable {readable_shape} for each fighter is that fighter's "
        f"selected primary {inventory_item}. "
        "The full visible loadout inventory per readable fighter is one primary "
        f"{inventory_item} plus cloth, belt, sash, robe, and armor surfaces on "
        "the body. Back shoulder silhouettes resolve as smooth garment planes "
        "and flat straps; background long shapes resolve as blunt timber posts "
        "or fence rails outside the body silhouette. Secondary-looking shapes "
        "read as folds, straps, armor layers, folded sash tails, belt ends, or soft "
        "shadow shapes."
    )

ACTION_EMOTION_DIRECTIVE = (
    " || STORY MOMENT LOCK - render one clear story-critical moment. Use visible "
    "action, tension, decision, danger, betrayal, fear, grief, anger, resolve, "
    "protection, pursuit, accusation, discovery, or physical consequence as the "
    "main image engine. If the Scene has a character, make the emotion readable "
    "in the face, posture, and body angle. If the Scene is object or location based, "
    "make a close foreground evidence composition with hard directional lighting, "
    "impact, damage, concealment, pressure, or a symbolic object under tension. "
    "Keep the moment specific to the narration."
)

MAP_OBJECT_STORY_MOMENT_DIRECTIVE = (
    " || STORY MOMENT LOCK - render one clear strategic evidence moment. The "
    "story tension comes from the route cord placement, separated stone "
    "clusters, bronze weight or pin position, disturbed dust, hard directional "
    "lamp light, long shadows, and empty margins on the low horizontal surface. "
    "Keep the moment specific to the narration through object placement and "
    "material pressure."
)

CONTINUOUS_SCENE_DIRECTIVE = (
    " || CONTINUOUS SCENE LOCK - compose a single uninterrupted full-frame "
    "documentary scene from one camera viewpoint. All visible figures, props, "
    "architecture, and ground details share the same physical space, same ground "
    "plane, same lighting direction, and one story action center. The full 16:9 "
    "canvas is one continuous unpartitioned view with internal frame boundaries absent."
)

FORMAL_ROLE_SETTING_LAYOUT_DIRECTIVE = (
    " || FORMAL ROLE AND SETTING LAYOUT LOCK - when the Scene names a court, "
    "palace, hall, office, council room, gate, threshold, ritual, blinds, "
    "officials, courtiers, messengers, or servants, "
    "the named setting and named action are the strongest layout anchors. "
    "Architecture, threshold, table surface, blinds, ritual "
    "objects, and role positions stay readable in the frame. Officials, "
    "courtiers, messengers, and servants wear period-correct civilian or formal "
    "role clothing. Rulers, kings, queens, emperors, and empresses wear "
    "period-correct formal authority clothing. Warriors, soldiers, and other "
    "explicit armed duty roles wear era-local protective clothing or carry weapons only where the Scene names those roles. "
    "Furniture surfaces, wall surfaces, threshold surfaces, and gate "
    "surfaces stay unmarked material surfaces. In formal rooms, the background "
    "wall is plain plaster, exposed timber, shutter, mat edge, or open doorway "
    "light only. Do not add wall scrolls, framed calligraphy, hanging papers, "
    "wall plaques, notice boards, labeled panels, character boards, or "
    "decorative writing behind officials, envoys, rulers, or courtiers. Do not "
    "replace missing wall decoration with a blank framed rectangle, white panel, "
    "wall board, or display panel. Interior light comes from doorway daylight, "
    "side window daylight, low oil lamps, candles, fire bowls, or braziers; no "
    "ceiling light fixture, fluorescent strip, glowing rectangular panel, bulb, "
    "switch plate, light switch, socket, outlet plate, hand-height wall plate, "
    "small rectangular wall plate, thermostat-like box, keypad-like plate, or "
    "modern hardware appears. Wall plate inventory is zero: no small square, "
    "paired rectangle, outlined wall box, bright wall plate, or isolated "
    "hand-height mark on plaster or timber. If the Scene names "
    "envoys, petitioners, messengers, servants, or officials bowing, receiving, "
    "delivering, or negotiating, show the named action through bent posture, "
    "kneeling, lowered heads, guarded faces, hand-to-bundle contact, and a "
    "nearby low table, threshold, or floor mat. Do not reduce the moment to a "
    "symmetrical upright standing row or idle group portrait. Formal historical "
    "rooms do not contain whiteboards, display panels, mugs, cups, modern pots, "
    "kettles, saucepans, notebooks, food baskets, vegetable baskets, or table "
    "items not named by the Scene."
)

SPLIT_SIDE_COMPOSITION_DIRECTIVE = (
    " || SPLIT-SIDE COMPOSITION LOCK - when the Scene names divided roads, "
    "a fork, two sides, one side and the other side, inside and outside, or a "
    "threshold separating roles, or a person choosing between one named side "
    "and another named side, the physical divider is a major visible "
    "shape. Show the forked road, threshold line, doorway edge, table line, "
    "or hall boundary clearly. Arrange the named people or groups on their "
    "correct sides. When the Scene says a person turns away from one object, "
    "group, role, or side toward another, keep both named sides visible and "
    "place the principal figure at the decision point or boundary with readable "
    "eye-line tension between sides. The departed side remains readable behind "
    "or beside the turning body, and the destination side stays readable in the "
    "person's gaze or forward body direction. In a turn-away action, the "
    "principal person's face, chest angle, forward foot direction, and eye-line "
    "point toward the destination side; the departed side is behind the back or "
    "beside the turned shoulder. If the Scene does not explicitly name left or "
    "right, assign the destination side and departed side to opposite left/right "
    "image zones and do not mix their people, props, or role objects. When the "
    "Scene says a person chooses "
    "between A and B, both named options appear as separate readable props, "
    "roles, or groups on opposite sides of the person. Choice options do not "
    "collapse into clothing decoration, belt ornament, wall mark, or random "
    "symbol. If a named side is an armed role group, show the group as separate "
    "people with era-local weapons or protective duty equipment visible on that "
    "side; armed-side people are not replaced by document holders, attendants, or "
    "empty-handed civilians unless the Scene explicitly names those roles. If a "
    "named side is clothing, robes, regalia, or ceremonial dress, show "
    "the named garment itself as a separate non-human physical choice: an empty "
    "hanging garment, folded garment bundle, or laid-out layered garment on a low "
    "stand, with sleeves, collar, sash, and cloth volume visible on that side. "
    "No head, face, arms, legs, or body is inside the garment choice. A person "
    "wearing clothing does not satisfy a garment-choice side. The garment choice "
    "cannot be replaced by a person, helmet, cap, lamp, weapon, small ornament, "
    "wall mark, or unrelated prop. Headwear or cap options appear as a "
    "real standalone headwear prop or worn/held headwear object."
)

NO_UNREQUESTED_HUMANS_DIRECTIVE = (
    " || EMPTY EVIDENCE FRAME LOCK - the Scene field is object, animal, or location based. "
    "The frame is an unoccupied evidence shot: requested location, animal, or object only, "
    "with no unrequested people, soldiers, guards, commanders, crowds, or bystanders. "
    "foreground evidence, hard shadows, blocked doorway, concealment, damage, "
    "pressure, or directional light. Visible content is listed physical terrain, "
    "objects, architecture, natural materials, and natural light only. Use close "
    "foreground evidence composition, terrain-only landscape composition, or "
    "ground-level interior composition as the main subject."
)

MAP_OBJECT_EMPTY_EVIDENCE_DIRECTIVE = (
    " || EMPTY EVIDENCE FRAME LOCK - the frame is an unoccupied strategic "
    "evidence shot. Visible content is limited to the requested low horizontal "
    "surface, marker objects, lamp light, shadows, surface edges, dust, and "
    "natural material texture. All visual pressure comes from marker spacing, "
    "cord paths, separated object clusters, hard directional light, and empty "
    "plain material margins on the same low horizontal surface."
)

LANDSCAPE_VISIBLE_SET_DIRECTIVE = (
    " || LANDSCAPE VISIBLE SET LOCK - for terrain or valley cuts, the complete "
    "visible subject set is mountain cliffs, valley floor, riverbank or field "
    "edge when named, packed dirt path, scattered stones, low grass, empty "
    "timber-and-thatch huts when settlement context is needed, sky, clouds, "
    "mist, and natural light. The composition is an empty establishing "
    "landscape where terrain, huts, paths, rocks, grass, and haze fill the "
    "frame edge to edge."
)

NO_UNREQUESTED_MOUNTS_DIRECTIVE = (
    " || REQUESTED-SUBJECT PROP LOCK - the frame uses the location, objects, "
    "materials, and evidence named by the Scene field. "
    "All visual energy comes from composition, lighting, pressure, and foreground "
    "story evidence."
)

NON_CHARACTER_EVIDENCE_OVERRIDE_PREFIX = (
    " || OBJECT-LOCATION PRIMARY SUBJECT LOCK - this object or location cut uses "
    "a close foreground evidence object or empty interior pressure moment as the "
    "primary visible subject. "
)

SINGLE_CHARACTER_FOCUS_DIRECTIVE = (
    " || SINGLE CHARACTER LOCK - this cut explicitly asks for a close-up of one principal character as the sole "
    "focus. The frame contains one visible living human figure: the principal character. "
    "Use an extreme solo face-only close-up portrait shot: one solitary face, eyes, "
    "natural hairline, neck, and a thin shoulder edge filling roughly 98 percent of the frame. "
    "Keep the face large and centered with eye contact, readable emotion, and a "
    "clear decision. Use a bare compact human head: visible natural hairline, "
    "simple tied hair behind the head, continuous clean forehead and cheeks, "
    "and role or rank shown through period-appropriate cloth neckline, draped chest edge, "
    "shoulders, robe, tunic, wrap garment, cloak, sash, belt, or ordinary clothing "
    "named by the Scene and era. Portrait background is a narrow Scene-named "
    "setting evidence strip: throne or seat texture, platform edge, hall wall, "
    "room wall, window edge, rain, dust, mountain haze, or plain wall texture "
    "when no setting object is named. The visible shoulder line is a plain "
    "fabric or period clothing surface."
)

CHARACTER_STORY_FRAMING_DIRECTIVE = (
    " || CHARACTER STORY FRAMING LOCK - this cut has one principal living person "
    "but does not explicitly ask for a close-up. Do not reduce it to a face-only "
    "ID portrait. Compose a medium, waist-up, knee-up, three-quarter-body, or "
    "full-body story frame selected from the Scene. Keep the face readable, but "
    "make emotion and narration visible through body angle, hands, shoulders, "
    "stance, movement, prop contact, clothing tension, light, weather, and "
    "Scene-named setting evidence. Use side, three-quarter, over-shoulder, "
    "low-angle, or diagonal camera language when it fits the action, instead "
    "of repeating flat front-facing close-ups. If the narration implies fear, "
    "anger, grief, shock, resolve, seduction, pursuit, attack, retreat, or "
    "decision pressure, show it through expressive posture and a stronger "
    "cinematic action pose tied to the Scene."
)

SINGLE_CHARACTER_ACTION_STORY_DIRECTIVE = (
    " || SINGLE CHARACTER ACTION STORY LOCK - this cut has one principal living "
    "person performing a Scene-named gesture or body action. Do not reduce the "
    "image to a face-only ID portrait. Compose a medium-close, waist-up, or "
    "three-quarter story frame with the face, shoulders, torso angle, and the "
    "action arm or sleeve-covered hand visible together. Unless the Scene "
    "explicitly names companions, a crowd, guards, family, or a group, the frame "
    "contains one readable living human figure total; extra readable companions, "
    "bystanders, lineups, and group portraits stay absent. The camera uses an "
    "offset three-quarter or side three-quarter angle when the action allows it; "
    "emotion comes from the face plus posture, hand placement, hunched shoulders, "
    "body lean, object contact, and hard side light. Keep all body parts in "
    "ordinary anatomy and keep the Scene-named action readable."
)

CHARACTER_PORTRAIT_PROP_SET_DIRECTIVE = (
    " || CHARACTER PORTRAIT VISIBLE SET LOCK - when the Scene does not name a "
    "held object, weapon, mount, tool, seat, throne, platform, architecture, or "
    "location evidence, the portrait crop shows only the face, hair, neck, "
    "cloth neckline or draped chest edge, shoulder clothing, plain wall, rain, dust, and shadow "
    "shapes. When the Scene names a seat, throne, platform, room, hall, window, "
    "landscape edge, or other location evidence, keep that evidence as a narrow "
    "background strip behind the shoulders. Belt, back, shoulder, and background "
    "strip read as smooth plain costume surfaces and plain period material texture."
)

SINGLE_CHARACTER_SETTING_STORY_DIRECTIVE = (
    " || SINGLE CHARACTER SETTING STORY LOCK - when one named person is placed "
    "inside a named exterior or threshold story setting, the Scene-named setting "
    "evidence stays readable in a setting-inclusive character story frame. "
    "Compose a medium-close or waist-up story frame with the principal named "
    "person as the largest human subject in foreground or midground, front or "
    "three-quarter-front eyes and expression visible, upper body and posture "
    "readable, and the named road, fork, gate, threshold, entrance, shrine, "
    "temple, exterior terrain, blank fabric strips, banners, flags, weather, or "
    "architectural evidence visible beside or behind the person in the same "
    "physical space. If the Scene names banners, flags, or fabric strips, include "
    "a small off-center edge-on or furled blank cloth strip tied to a pole or cord "
    "beside the named road, gate, shrine, camp, or route. The person remains the "
    "emotional focus, while the visible setting supplies the decision pressure "
    "and historical context."
)

BOOK_RENDER_DIRECTIVE = (
    " || BOOK RENDERING LOCK - if any book, notebook, manuscript, codex, ledger, "
    "journal, scripture, archive volume, page spread, or document appears, draw it "
    "as one coherent physical object. For an open book: exactly one book, exactly "
    "two facing pages, one central spine/gutter, aligned covers, curved page edges, "
    "and stacked page thickness visible at the outer edges. Pages and covers are "
    "blank paper or subtle paper grain, with a simple stable book silhouette and "
    "coherent spine geometry."
)

BOOK_RENDER_NEGATIVE_PROMPT = (
    "extra book pages, three page spread, multiple fused books, duplicated open book, "
    "warped book spine, broken book geometry, floating pages, detached pages, "
    "impossible folded pages, melted book, fake writing on pages, rows of text lines, "
    "pseudo text, scribbles on book, glyphs on book, symbols on pages"
)

_FLAG_MOTIF_POSITIVE_PATTERNS: tuple[str, ...] = (
    r"\bmodern\s+national\s+flags?\b",
    r"\bnational\s+flags?\b",
    r"\bcountry\s+flags?\b",
    r"\bstate\s+flags?\b",
    r"\bflagpoles?\b",
    r"\bflags?\b",
    r"\bnational\s+emblems?\b",
    r"\bnational\s+symbols?\b",
    r"\btricolor\b",
    r"\bstars\s+and\s+stripes\b",
    r"\bcanton\s+stars\b",
    r"\bflag\s+stripes\b",
    r"\bnational\s+color\s+blocks\b",
    r"\bJapanese\s+flags?\b",
    r"\bhinomaru\b",
    r"\brising\s+sun\s+flags?\b",
    r"\brising\s+sun\s+rays\b",
    r"\bred\s+sun\s+disc\b",
    r"\bred\s+circle\s+on\s+white\s+background\b",
    r"\bcentered\s+red\s+(?:circle|disc)\b",
    r"\bwhite\s+field\s+with\s+red\s+circle\b",
    r"\bred\s+radial\s+rays\b",
    r"\bsunburst\s+flags?\b",
    r"\bimperial\s+Japanese\s+flags?\b",
)

KOREAN_HISTORY_ACCURACY_DIRECTIVE = (
    " || HISTORICAL ACCURACY LOCK - this scene is Korean history. Match the exact "
    "This fixed lock has higher priority than any user-entered image prompt or style prompt. "
    "era, kingdom, region, material culture, clothing, hairstyle, "
    "jewelry and accessories, architecture, weapons, armor, tools, everyday "
    "objects, ritual objects, vehicles, vessels, landscape, and materials implied "
    "by the subject. If the subject is "
    "Goguryeo, Baekje, Silla, Gaya, Balhae, Gojoseon, Buyeo, Three Kingdoms, "
    "Goryeo, or Joseon, use period-correct Korean visual culture only. "
    "The specified time period, region, and place in the prompt are non-negotiable "
    "and must be considered before choosing any costume, prop, architecture, or vehicle. "
    "Visible costume, hair, armor, tools, and props must prove the exact period; "
    "use sober local clothing, plain local banners, period-correct Korean rooflines, "
    "wooden or earthen architecture, bronze or iron period objects where appropriate, "
    "and landscapes tied to the named Korean region."
)

KOREAN_HISTORY_NEGATIVE_PROMPT = (
    "Japanese flag, rising sun flag, red sun disc flag, hinomaru, torii gate, "
    "Shinto shrine, samurai, ninja, katana, kimono, Japanese castle, Japanese text, "
    "steamship, steamboat, steam engine, locomotive, train, railroad, railway, "
    "factory chimney, smokestack, industrial machinery, modern flag, modern national "
    "flag, modern uniform, modern building, car, truck, power line, neon sign, logo"
)

GENERAL_HISTORY_NEGATIVE_PROMPT = (
    "anachronism, wrong era, mixed era, mixed culture, out of period object, "
    "wrong-era clothing, wrong-era hairstyle, wrong-era armor, "
    "wrong-era weapon, wrong-era tool, wrong-era jewelry, fantasy costume, cosplay, "
    "theatrical costume, generic historical costume, modern jewelry, modern accessory, "
    "modern clothing, modern uniform, modern business suit, suit lapel, necktie, "
    "modern brimmed felt hat, fedora, derby hat, bowler hat, homburg hat, trilby, "
    "top hat, 19th century coat, 20th century coat, modern overcoat, modern building, skyscraper, concrete city, "
    "car, truck, bus, motorcycle, bicycle, train, railroad, railway, airplane, "
    "helicopter, steamship, steamboat, steam engine, locomotive, factory, factory "
    "chimney, smokestack, industrial machinery, gun, rifle, pistol, cannon unless "
    "period-correct, electric light, power line, utility pole, neon sign, screen, "
    "computer, phone, camera, printed newspaper, modern book, modern national flag, "
    "logo, watermark, readable text"
)

_MODERN_SETTING_RE = re.compile(
    r"\b(modern|office|workplace|desk|laptop|computer|screen|phone|water\s+cooler|"
    r"coffee\s+cup|city|skyscraper|car|truck|bus|motorcycle|bicycle|neon|"
    r"electric|power\s+line|utility\s+pole)\b",
    re.IGNORECASE,
)

_EXPLICIT_MODERN_PERIOD_RE = re.compile(
    r"\b(20\d{2}|2020s|21st\s+century|twenty[-\s]*first\s+century|"
    r"present[-\s]*day|present\s+day|contemporary|current\s+era|today|modern)\b|"
    r"(現代|令和)",
    re.IGNORECASE,
)


def _is_modern_context(prompt: str) -> bool:
    p = prompt or ""
    year = _prompt_field(p, "Year/period")
    if year and re.search(
        r"\b(?:[1-9]\d{2}|1[0-8]\d{2}|19[0-4]\d)\b|"
        r"\b(?:BCE|BC|Kamakura|Muromachi|Kenmu|Nanboku|medieval|ancient)\b",
        year,
        re.IGNORECASE,
    ) and not re.search(
        r"\b(?:20\d{2}|2020s|21st\s+century|present[-\s]*day|"
        r"contemporary|current\s+era|today|modern)\b",
        year,
        re.IGNORECASE,
    ):
        return False
    p = re.sub(
        r"\b(?:no|without|avoid|forbidden|exclude|not|never)\b[^.;|]{0,120}\bmodern\b[^.;|]*",
        " ",
        p,
        flags=re.IGNORECASE,
    )
    p = re.sub(r"\b(?:non|pre|early)[-\s]*modern\b", " ", p, flags=re.IGNORECASE)
    if _EXPLICIT_MODERN_PERIOD_RE.search(p):
        return True
    return bool(
        re.search(
            r"\b(apartment|office|workplace|school|hospital|studio|urban|"
            r"skyscraper|high-rise|subway|bus|car|taxi|neon|phone|"
            r"laptop|computer|screen|elevator|shopping mall|cafe)\b|"
            r"아파트|사무실|현대|도시|빌딩|고층|서울|지하철|버스|자동차|카페",
            p,
            re.IGNORECASE,
        )
    )


def _is_historical_period_context(prompt: str) -> bool:
    p = prompt or ""
    if _is_modern_context(p):
        return False
    year = _prompt_field(p, "Year/period")
    text = f"{year} {p}"
    return bool(
        re.search(
            r"\b(?:BCE|BC|ancient|medieval|early[-\s]*modern|classical|"
            r"Nara|Heian|Kamakura|Muromachi|Kenmu|Nanboku|Edo|Sengoku|"
            r"Goguryeo|Gojoseon|Buyeo|Goryeo|Joseon|Achaemenid|Persian|Egyptian|"
            r"Roman|Greek|Macedonian|Maurya|Gupta|Mughal|Ottoman|Ming|Qing|"
            r"[1-9]\d{2}|1[0-8]\d{2}|19[0-4]\d|c\.\s*\d{3,4})\b",
            text,
            re.IGNORECASE,
        )
    )


def _is_preindustrial_historical_context(prompt: str) -> bool:
    p = prompt or ""
    if _is_modern_context(p):
        return False
    year = _prompt_field(p, "Year/period")
    text = f"{year} {p}"
    return bool(
        re.search(
            r"\b(?:BCE|BC|ancient|classical|medieval|early[-\s]*modern|"
            r"Nara|Heian|Kamakura|Muromachi|Kenmu|Nanboku|Edo|Sengoku|"
            r"Goguryeo|Gojoseon|Buyeo|Goryeo|Joseon|Achaemenid|Persian|Egyptian|"
            r"Roman|Greek|Macedonian|Maurya|Gupta|Mughal|Ottoman|Ming|Qing|"
            r"[1-9]\d{2}|1[0-7]\d{2}|c\.\s*(?:[1-9]\d{2}|1[0-7]\d{2}))\b",
            text,
            re.IGNORECASE,
        )
    )


def _is_ancient_mediterranean_context(prompt: str) -> bool:
    p = prompt or ""
    if _is_modern_context(p):
        return False
    year = _prompt_field(p, "Year/period")
    place = _prompt_field(p, "Exact place")
    culture = _prompt_field(p, "Culture scope")
    scene = _scene_text(p)
    scene_explicit_classical = bool(
        re.search(
            r"\b(?:ancient|classical|archaic|hellenistic|BCE|BC|Aeschylus)\b",
            scene,
            re.IGNORECASE,
        )
        and re.search(
            r"\b(?:Greek|Greece|Hellenic|Hellenistic|Ionian|Ionia|Aeschylus|amphitheater|theater|theatre)\b",
            scene,
            re.IGNORECASE,
        )
    )
    if year and re.search(
        r"\b(?:1[3-9]\d{2}|13th|14th|15th|16th|17th|18th|19th|"
        r"Renaissance|early[-\s]*modern)\b",
        " ".join(part for part in (year, place, culture) if part),
        re.IGNORECASE,
    ) and not re.search(r"\b(?:BCE|BC|ancient|classical|archaic|hellenistic)\b", year, re.IGNORECASE) and not scene_explicit_classical:
        return False
    if re.search(r"\bHoly\s+Roman\s+Empire\b", place or "", re.IGNORECASE) and not re.search(
        r"\b(?:BCE|BC|ancient|classical|archaic|hellenistic)\b",
        " ".join(part for part in (year, culture) if part),
        re.IGNORECASE,
    ) and not scene_explicit_classical:
        return False
    field_text = " ".join(part for part in (year, place, culture, scene) if part)
    text = field_text or p
    has_period = bool(
        re.search(
            r"\b(?:BCE|BC|ancient|classical|archaic|hellenistic|"
            r"[1-9]\d{2}\s*BC|[1-9]\d{2}\s*BCE)\b",
            text,
            re.IGNORECASE,
        )
    )
    has_region = bool(
        re.search(
            r"\b(?:Greek|Greece|Hellenic|Hellenistic|Ionian|Ionia|Ephesus|"
            r"Artemis|Macedonian|Aegean|Roman|Rome)\b",
            text,
            re.IGNORECASE,
        )
    )
    return bool((has_period and has_region) or scene_explicit_classical)


def _normalize_ancient_mediterranean_scene_language(prompt: str) -> str:
    p = prompt or ""
    if not _is_ancient_mediterranean_context(p):
        return p
    replacements = [
        (
            r"\ba\s+split\s+screen\s+showing\s+the\s+ancient\s+arsonist\s+with\s+a\s+torch,\s*and\s+a\s+modern\s+troll\s+with\s+a\s+smartphone\b",
            "a single ancient Mediterranean scene showing a torch-bearing arsonist confronted by a hostile robed bystander pointing accusingly, no device",
        ),
        (
            r"\ba\s+person\s+casually\s+knocking\s+over\s+a\s+beautiful\s+display\s+in\s+a\s+store\b",
            "a full-frame top-down tabletop action crop: only robed ancient Mediterranean hands knocking over unmarked clay and bronze ritual objects on a low wooden table, no faces, no wall, no doorway, no wall sign, no overhead beam",
        ),
        (
            r"\bholding\s+a\s+camera\s+to\s+record\s+the\s+damage\b",
            "watched by robed witnesses pointing at the damage with empty hands",
        ),
        (
            r"\bcamera\s+to\s+record\s+the\s+damage\b",
            "robed witnesses pointing at the damage",
        ),
        (
            r"\bmodern\s+troll\s+with\s+a\s+smartphone\b",
            "hostile robed bystander pointing accusingly, no device",
        ),
        (
            r"\bmodern\s+troll\b",
            "hostile robed bystander",
        ),
        (
            r"\bsmartphone\b",
            "empty hand raised in accusation",
        ),
        (
            r"\bbeautiful\s+display\b",
            "unmarked ritual display table",
        ),
        (
            r"\bstore\b",
            "period-local stall table cropped below the roofline with no doorway or sign",
        ),
        (
            r"\ban\s+astrolabe\s+pointing\s+towards?\s+the\s+stars?,\s*framed\s+by\s+a\s+heavy\s+velvet\s+curtain\b",
            "a bronze sighting ring and gnomon casting a star-aligned shadow beside a plain heavy wool curtain, no wall, no roofline, no inscription",
        ),
        (
            r"\bastrolabe\b",
            "bronze sighting ring and gnomon",
        ),
        (
            r"\bheavy\s+velvet\s+curtain\b|\bvelvet\s+curtain\b",
            "plain heavy wool curtain",
        ),
        (
            r"\ba\s+jester'?s\s+hat\s+resting\s+on\s+top\s+of\s+a\s+stack\s+of\s+heavy\s+scientific\s+tomes\b",
            "an ancient Greek comic theatre mask resting on unmarked papyrus scroll bundles and blank wax tablets, close object crop, no doorway, no temple facade",
        ),
        (
            r"\bjester'?s\s+hat\b",
            "ancient Greek comic theatre mask",
        ),
        (
            r"\bheavy\s+scientific\s+tomes\b|\bscientific\s+tomes\b|\btomes\b",
            "unmarked papyrus scroll bundles and blank wax tablets",
        ),
        (
            r"\bsinister\s+figure\b",
            "hooded figure wrapped in a plain dark himation cloak over a simple chiton, bare neck, no buttons",
        ),
        (
            r"\bplain,\s*unkempt\s+ancient\s+Greek\s+man\b",
            "plain unkempt ancient Greek man in a rough sleeveless or short-sleeved chiton with a plain himation cloak and leather sandals",
        ),
        (
            r"\bExtreme\s+close-up\s+of\s+a\s+man's\s+eyes\b",
            "Extreme close-up of an ancient Greek man's eyes above a plain draped chiton neckline",
        ),
        (
            r"\bwealthy\s+procession\b",
            "ancient Greek procession in draped chitons, himations, veils, simple belts, and sandals",
        ),
    ]
    for pattern, replacement in replacements:
        p = re.sub(pattern, replacement, p, flags=re.IGNORECASE)
    return p


def _is_early_modern_europe_context(prompt: str) -> bool:
    p = prompt or ""
    if _is_modern_context(p):
        return False
    year = _prompt_field(p, "Year/period")
    place = _prompt_field(p, "Exact place")
    culture = _prompt_field(p, "Culture scope")
    scene = _scene_text(p)
    if re.search(
        r"\b(?:ancient|classical|archaic|hellenistic|BCE|BC|Aeschylus)\b",
        scene,
        re.IGNORECASE,
    ) and re.search(
        r"\b(?:Greek|Greece|Hellenic|Hellenistic|Ionian|Ionia|Aeschylus|amphitheater|theater|theatre)\b",
        scene,
        re.IGNORECASE,
    ):
        return False
    text = " ".join(part for part in (year, place, culture, scene, p) if part)
    has_region = bool(
        re.search(
            r"\b(?:Europe|European|Holy\s+Roman\s+Empire|Prague|Bohemia|"
            r"Czech|German|Germany|Danish|Denmark|Habsburg|Renaissance|"
            r"Tycho|Brahe|Kepler|astronomer|astronomy)\b",
            text,
            re.IGNORECASE,
        )
    )
    has_period = bool(
        re.search(
            r"\b(?:14\d{2}|15\d{2}|16\d{2}|17\d{2})\s*(?:AD|CE)?\b|"
            r"\b(?:15th|16th|17th)\s+century\b|"
            r"\b(?:Renaissance|early[-\s]*modern)\b",
            text,
            re.IGNORECASE,
        )
    )
    return bool(has_region and has_period)


def _normalize_early_modern_europe_scene_language(prompt: str) -> str:
    p = prompt or ""
    if not _is_early_modern_europe_context(p):
        return p
    replacements = [
        (
            r"\b(?:a\s+)?brilliant\s+Renaissance\s+scholar\s+looking\s+up\s+at\s+a\s+starry\s+night\s+sky\s+through\s+an?\s+[^,.;]*astrolabe[^;]*",
            "a single late Renaissance astronomer in a dark scholar robe and cloak, white ruff or standing linen collar, looking up at a starry night sky from a Prague observatory window while holding one brass astrolabe near his face",
        ),
        (
            r"\ba\s+well-dressed\s+man\s+clutching\s+his\s+stomach\b",
            "one solitary late Renaissance nobleman sitting alone in one ornate wooden chair, wearing a dark velvet cloak over a doublet, white ruff or standing linen collar, with one sleeve-covered hand pressed near his abdomen",
        ),
        (
            r"\ba\s+group\s+of\s+historical\s+scholars\s+laughing\s+and\s+pointing\s+fingers\b",
            "exactly three late Renaissance scholars only, wearing dark robes, cloaks, and white ruffs, laughing in a candlelit library, with hands tucked into sleeves or resting on a plain table",
        ),
        (
            r"\ba\s+group\s+of\s+historical\s+scholars\s+laughing\s+and\s+pointing\s+small\s+arm\s+gesture\b",
            "exactly three late Renaissance scholars only, wearing dark robes, cloaks, and white ruffs, laughing in a candlelit library, with hands tucked into sleeves or resting on a plain table",
        ),
        (
            r"\bcomplex\s+astronomical\s+star\s+chart\b",
            "plain blank circular parchment astronomy disk with irregular stains and scratches only",
        ),
        (
            r"\bbrilliant\s+star\s+chart\b",
            "plain blank circular parchment astronomy disk with irregular stains and scratches only",
        ),
        (
            r"\bstar\s+chart\b",
            "plain blank circular parchment astronomy disk with irregular stains and scratches only",
        ),
        (
            r"\ba\s+grand\s+procession\s+of\s+horse-drawn\s+carriages\s+carrying\s+massive\s+brass\s+astronomical\s+tools\s+into\s+the\s+city\s+of\s+Prague\b",
            "one close horse-drawn wooden carriage with a horse, large wheels, harness, reins, and massive unlabeled brass astronomical tools strapped onto the carriage, moving along a Prague street, with only tiny secondary workers",
        ),
        (
            r"\ban\s+ornate,\s*ancient\s+calendar[^.;]*revealing\s+the\s+month\s+of\s+\w+\b",
            "one blank cord-tied parchment calendar roll with a curled blank edge and ribbon on a wooden tabletop, no words and no numerals",
        ),
        (
            r"\brevealing\s+the\s+month\s+of\s+\w+\b",
            "showing only a blank curled paper edge",
        ),
        (
            r"\bintricate,\s*glowing\s+model\s+of\s+the\s+solar\s+system\b",
            "unlabeled brass armillary solar-system model with plain rings and rods",
        ),
        (
            r"\bspinning\s+ancient\s+globe\s+made\s+of\s+brass\s+and\s+wood\b",
            "unmarked early modern brass-and-wood globe with blank landmass shapes",
        ),
        (
            r"\bancient\s+brass\s+astrolabe\b",
            "early modern brass astrolabe",
        ),
        (
            r"\bancient\s+astrolabe\b",
            "early modern brass astrolabe",
        ),
        (
            r"\bmassive\s+brass\s+telescope\b",
            "plain unlabeled brass armillary ring instrument on a wooden stand",
        ),
        (
            r"\bbrass\s+telescope\b",
            "plain unlabeled brass armillary ring instrument on a wooden stand",
        ),
    ]
    for pattern, replacement in replacements:
        p = re.sub(pattern, replacement, p, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", p).strip()


def _scene_requests_early_modern_europe_astronomy_observation(prompt: str) -> bool:
    if not _is_early_modern_europe_context(prompt):
        return False
    scene = _scene_text(prompt)
    return bool(
        scene
        and re.search(
            r"\b(astronomer|scholar|nobleman|person|man)\b",
            scene,
            re.IGNORECASE,
        )
        and re.search(
            r"\b(looking\s+up|look(?:ing)?\s+(?:at|toward|towards)\s+(?:the\s+)?(?:sky|stars?|heavens?)|"
            r"observ(?:e|es|ing)\s+(?:the\s+)?(?:sky|stars?|heavens?)|"
            r"watch(?:es|ing)?\s+(?:the\s+)?(?:sky|stars?|heavens?)|"
            r"starry\s+night\s+sky|starry\s+sky)\b",
            scene,
            re.IGNORECASE,
        )
        and re.search(
            r"\b(astrolabe|armillary|quadrant|starry|stars?)\b",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_requests_historical_bed_rest(prompt: str) -> bool:
    if not _is_preindustrial_historical_context(prompt):
        return False
    scene = _scene_text(prompt)
    if not scene or not _scene_requests_humans(prompt):
        return False
    has_bed_place = bool(re.search(r"\b(bed|sickroom|bedroom|deathbed)\b", scene, re.IGNORECASE))
    has_resting_on_bed = bool(
        re.search(r"\b(resting|peacefully|ill|dying)\b", scene, re.IGNORECASE)
        and re.search(r"\bbed\b", scene, re.IGNORECASE)
    )
    return has_bed_place or has_resting_on_bed


def _scene_requests_astronomical_surface_or_instrument(prompt: str) -> bool:
    scene = _scene_text(prompt)
    text = scene or prompt or ""
    return bool(
        re.search(
            r"\b(astronomical|astronomy|star\s+chart|celestial|astrolabe|"
            r"armillary|quadrant|solar\s+system|globe|instrument\s+rings?|"
            r"constellation|zodiac)\b",
            text,
            re.IGNORECASE,
        )
    )


def _scene_requests_astronomical_chart_surface_object(prompt: str) -> bool:
    scene = _scene_text(prompt)
    if not scene:
        return False
    has_chart_surface = bool(
        re.search(
            r"\b(star\s+chart|astronomical\s+(?:chart|diagram)|celestial\s+(?:chart|diagram)|"
            r"parchment\s+circle|circular\s+astronomical\s+diagram)\b",
            scene,
            re.IGNORECASE,
        )
    )
    if not has_chart_surface:
        return False
    return _scene_requests_generic_object_evidence(prompt) or not _scene_requests_humans(prompt)


def _scene_requests_single_early_modern_person(prompt: str) -> bool:
    if not _is_early_modern_europe_context(prompt):
        return False
    scene = _scene_text(prompt)
    return bool(
        scene
        and not _scene_requests_multiple_characters(prompt)
        and re.search(
            r"\b(?:a|one|single)\s+(?:wealthy\s+|well-dressed\s+|brilliant\s+|old\s+|young\s+|late\s+Renaissance\s+)?"
            r"(?:astronomer|scholar|nobleman|man|person|woman)\b|"
            r"\b(?:astronomer|nobleman)\b",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_requests_early_modern_three_scholar_group(prompt: str) -> bool:
    if not _is_early_modern_europe_context(prompt):
        return False
    scene = _scene_text(prompt)
    return bool(
        scene
        and re.search(
            r"\b(?:small\s+group\s+of\s+three|group\s+of\s+historical\s+scholars|"
            r"group\s+of\s+scholars|exactly\s+three[^.;]*scholars|scholars\s+laughing)\b",
            scene,
            re.IGNORECASE,
        )
    )


def _is_early_ancient_chinese_context(prompt: str) -> bool:
    p = prompt or ""
    if _is_modern_context(p):
        return False
    year = _prompt_field(p, "Year/period")
    place = _prompt_field(p, "Exact place")
    culture = _prompt_field(p, "Culture scope")
    scene = _scene_text(p)
    scoped_text = " ".join(part for part in (year, place, culture, scene) if part)
    text = scoped_text or p
    has_region = bool(
        re.search(
            r"\b(?:China|Chinese|Shang|Zhou|Western\s+Zhou|Eastern\s+Zhou|"
            r"Spring\s+and\s+Autumn|Warring\s+States|pre[-\s]*Qin|Haojing|"
            r"Mount\s+Li|Quanrong|Baosi|King\s+You)\b|"
            r"(서주|동주|주나라|상나라|중국|춘추|전국|선진|호경|포사|유왕)",
            text,
            re.IGNORECASE,
        )
    )
    has_period = bool(
        re.search(
            r"\b(?:1[0-5]\d{2}|[2-9]\d{2})\s*(?:BCE|BC)\b|"
            r"\b(?:BCE|BC|ancient|Bronze\s+Age|pre[-\s]*Qin|"
            r"Shang|Western\s+Zhou|Eastern\s+Zhou|Spring\s+and\s+Autumn|"
            r"Warring\s+States)\b|기원전",
            text,
            re.IGNORECASE,
        )
    )
    return bool(has_region and has_period)


def _is_early_imperial_chinese_context(prompt: str) -> bool:
    p = prompt or ""
    if _is_modern_context(p):
        return False
    year = _prompt_field(p, "Year/period")
    place = _prompt_field(p, "Exact place")
    culture = _prompt_field(p, "Culture scope")
    scene = _scene_text(p)
    scoped_text = " ".join(part for part in (year, place, culture, scene) if part)
    text = scoped_text or p
    has_region = bool(
        re.search(
            r"\b(?:China|Chinese|Han|Later\s+Han|Eastern\s+Han|"
            r"Three\s+Kingdoms|Cao\s+Wei|Wei|Gongsun\s+Kang|"
            r"Gongsun|Chinese\s+warlord|Chinese\s+generals?|Chinese\s+troops?)\b|"
            r"(중국|후한|동한|한나라|삼국|위나라|공손강|공손|중국군|중국\s*장군|군벌)",
            text,
            re.IGNORECASE,
        )
    )
    has_period = bool(
        re.search(
            r"\b(?:[1-9][0-9]?|[12][0-9]{2}|3[0-2][0-9])\s*(?:CE|AD)\b|"
            r"\b(?:1st|2nd|3rd)\s+century\s+(?:CE|AD)\b|"
            r"서기\s*(?:[1-9][0-9]?|[12][0-9]{2}|3[0-2][0-9])"
            r"(?:\s*[~\-–]\s*(?:[1-9][0-9]?|[12][0-9]{2}|3[0-2][0-9]))?\s*년(?:경)?|"
            r"(?<!\d)(?:[1-9][0-9]?|[12][0-9]{2}|3[0-2][0-9])"
            r"(?:\s*[~\-–]\s*(?:[1-9][0-9]?|[12][0-9]{2}|3[0-2][0-9]))?\s*년경|"
            r"[1-3]\s*세기",
            text,
            re.IGNORECASE,
        )
    )
    return bool(has_region and has_period)


def _is_medieval_japanese_context(prompt: str) -> bool:
    p = prompt or ""
    if _is_modern_context(p):
        return False
    year = _prompt_field(p, "Year/period")
    place = _prompt_field(p, "Exact place")
    culture = _prompt_field(p, "Culture scope")
    scene = _scene_text(p)
    scoped_text = " ".join(part for part in (year, place, culture, scene) if part)
    text = scoped_text or p
    has_japan = bool(
        re.search(
            r"\b(Japan|Japanese|Kyoto|Kamakura|Muromachi|Kenmu|Nanboku|"
            r"Yoshino|Minatogawa|Kyushu|samurai|shugo|shogunate|Ashikaga|"
            r"Takauji|Nitta|Go-?Daigo|Sengoku|daimyo|daimyō|ashigaru|"
            r"Oda|Nobunaga|Takeda|Shingen|Hojo|Hōjō|Soun|Sōun|Izu|Sagami)\b|"
            r"(日本|京都|鎌倉|吉野|九州|足利|尊氏|新田|後醍醐|侍|武士|戦国|"
            r"戰國|大名|足軽|織田|信長|武田|信玄|北条|北條|早雲|伊豆|相模)",
            text,
            re.IGNORECASE,
        )
    )
    has_medieval = bool(
        re.search(
            r"\b(Kamakura|Muromachi|Kenmu|Nanboku|medieval|late\s+Kamakura|"
            r"early\s+Muromachi|Sengoku|late\s+medieval|15th\s+century|"
            r"16th\s+century|13\d{2}|14\d{2}|15\d{2}|16\d{2}|"
            r"c\.\s*13\d{2}|c\.\s*14\d{2}|c\.\s*15\d{2}|c\.\s*16\d{2})\b|"
            r"(鎌倉|室町|建武|南北朝|戦国|戰國|十五世紀|十六世紀)",
            text,
            re.IGNORECASE,
        )
    )
    return bool(has_japan and has_medieval)


def _scene_requests_household_relocation(prompt: str) -> bool:
    scene = _scene_text(prompt)
    return bool(
        scene
        and re.search(
            r"\b(household\s+members?|family\s+members?|families|retainers?'\s+families|"
            r"retainer\s+families|moving\s+into\s+residences?|move\s+into\s+residences?|"
            r"entering\s+wooden\s+compounds?|wooden\s+compounds?|residence\s+assignment|"
            r"relocation|relocating|carried\s+belongings)\b|"
            r"(가족|가문|가솔|가정|이주|거처|저택|주거지|목조\s*가옥)",
            scene,
            re.IGNORECASE,
        )
        and re.search(
            r"\b(carry(?:ing)?\s+chests?|chests?|bundles?|bedding\s+rolls?|belongings)\b|"
            r"(상자|궤짝|짐|보따리)",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_requests_historical_road_logistics(prompt: str) -> bool:
    scene = _scene_text(prompt)
    if not scene:
        return False
    return bool(
        re.search(
            r"\b(packhorses?|packhorse\s+column|porters?|ashigaru|supply\s+road|"
            r"logistics|baggage|main\s+road|road\s+toward\s+a\s+castle|"
            r"moving\s+fast|kicking\s+dust|column)\b|"
            r"(보급|군수|짐말|짐꾼|행렬|도로|성으로|먼지)",
            scene,
            re.IGNORECASE,
        )
        and re.search(
            r"\b(road|route|castle|packhorse|porter|ashigaru|column|baggage|supply)\b|"
            r"(길|도로|성|짐말|짐꾼|보급|군수|행렬)",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_requests_historical_public_street_or_muster(prompt: str) -> bool:
    if not _is_medieval_japanese_context(prompt):
        return False
    scene = _scene_text(prompt)
    if not scene:
        return False
    return bool(
        re.search(
            r"\b(road|street|market|market\s+street|castle\s+town|town\s+street|"
            r"square|mobilization|muster|muster\s+yard|assembled\s+soldiers?|"
            r"assembled\s+spear\s+troops?|troops?|merchants?|craftsmen|stalls?|"
            r"supply\s+carts?|goods|officials?\s+guide)\b|"
            r"(도로|길|시장|장터|성하|광장|동원|소집|병사|상인|장인|수레)",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_requests_preindustrial_craft_workshop(prompt: str) -> bool:
    scene = _scene_text(prompt)
    return bool(
        scene
        and re.search(
            r"\b(craftsman|craftsmen|craft\s+workshop|workshop|forge|blacksmith|"
            r"hammering|hammer|hammers|tongs|anvil|iron\s+fittings|metalwork|"
            r"carpenter|carpentry|potter|pottery|loom|weaving|artisan|helper\s+shields\s+face)\b|"
            r"(장인|공방|대장간|단조|망치|집게|모루|철물|철제|목수|도공|도예|직조)",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_requests_historical_tally_object_evidence(prompt: str) -> bool:
    scene = _scene_text(prompt)
    if not scene:
        return False
    return bool(
        re.search(
            r"\b(scribe|record|records|register|roster|tax\s+register|ledger|"
            r"tally|tallies|account|accounting|survey\s+results?|land\s+capacity|"
            r"military\s+obligation|field-side\s+counting\s+mat|counting\s+mat)\b|"
            r"(서기|기록|장부|명부|호적|계수|측량|토지|군역|세금)",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_requests_historical_blank_record_document(prompt: str) -> bool:
    scene = _scene_text(prompt)
    if not scene:
        return False
    return bool(
        re.search(
            r"\b(blank\s+rosters?|retainer\s+rosters?|rosters?|registers?|"
            r"tax\s+registers?|ledger|ledgers|obligations?|steward\s+checking|"
            r"records?|documents?|orders?|assignments?)\b|"
            r"(명부|장부|기록|문서|의무|군역)",
            scene,
            re.IGNORECASE,
        )
    )


def _is_achaemenid_egyptian_context(prompt: str) -> bool:
    p = prompt or ""
    if (
        "PERIOD-LOCAL ACHAEMENID PERSIAN AND EGYPTIAN MATERIAL CULTURE LOCK" in p
        or "ACHAEMENID EGYPTIAN ARMED GROUP COMPOSITION LOCK" in p
        or "525 BC Achaemenid Persian, Pelusium" in p
    ):
        return True
    if _is_modern_context(p):
        return False
    year = _prompt_field(p, "Year/period")
    place = _prompt_field(p, "Exact place")
    culture = _prompt_field(p, "Culture scope")
    text = " ".join(part for part in (year, place, culture, p) if part)
    has_region = bool(
        re.search(
            r"\b(Achaemenid|Persian|Persia|Cambyses|Pelusium|Nile\s+Delta|"
            r"Egypt|Egyptian|Pharaoh|Psamtik|Amasis|Phanes)\b|"
            r"(페르시아|이집트|캄비세스|펠루시움|파라오)",
            text,
            re.IGNORECASE,
        )
    )
    has_period = bool(
        re.search(
            r"\b(?:525|52\d|5\d{2})\s*(?:BCE|BC)\b|"
            r"\b(?:BCE|BC|ancient|Late\s+Period)\b|기원전",
            text,
            re.IGNORECASE,
        )
    )
    return bool(has_region and has_period)


def _is_medieval_central_asian_context(prompt: str) -> bool:
    p = prompt or ""
    if "PERIOD-LOCAL MEDIEVAL CENTRAL ASIAN MATERIAL CULTURE LOCK" in p:
        return True
    if _is_modern_context(p):
        return False
    year = _prompt_field(p, "Year/period")
    place = _prompt_field(p, "Exact place")
    culture = _prompt_field(p, "Culture scope")
    scene = _scene_text(p)
    text = " ".join(part for part in (year, place, culture, scene, p) if part)
    has_region = bool(
        re.search(
            r"\b(Khwarazm|Khwarezm|Khwarazmian|Khwarezmian|Otrar|"
            r"Transoxiana|Central\s+Asia|Silk\s+Road|Genghis|Chinggis|Mongol|"
            r"Mongolia|Khan|Khanate|Samarkand|Bukhara|Khorasan|Steppe|"
            r"Persianate|Islamic\s+urban)\b|"
            r"(호라즘|오트라르|중앙아시아|몽골|칭기즈|실크로드)",
            text,
            re.IGNORECASE,
        )
    )
    has_period = bool(
        re.search(
            r"\b(?:11\d{2}|12\d{2}|13\d{2})\s*(?:AD|CE)?\b|"
            r"\b(?:12th|13th)\s+century\b|\bmedieval\b|서기\s*1[12]\d{2}|"
            r"12세기|13세기",
            text,
            re.IGNORECASE,
        )
    )
    return bool(has_region and has_period)


def _is_west_african_ashanti_british_context(prompt: str) -> bool:
    p = prompt or ""
    if "PERIOD-LOCAL WEST AFRICAN ASHANTI AND GOLD COAST" in p:
        return True
    if _is_modern_context(p):
        return False
    year = _prompt_field(p, "Year/period")
    place = _prompt_field(p, "Exact place")
    culture = _prompt_field(p, "Culture scope")
    scene = _scene_text(p)
    text = " ".join(part for part in (year, place, culture, scene, p) if part)
    has_region = bool(
        re.search(
            r"\b(Ashanti|Asante|Kumasi|Gold\s+Coast|Golden\s+Stool|"
            r"Yaa\s+Asantewaa|British\s+colonial|British\s+Empire)\b|"
            r"(아샨티|아산테|쿠마시|황금\s*의자)",
            text,
            re.IGNORECASE,
        )
    )
    has_period = bool(
        re.search(
            r"\b(?:18\d{2}|19\d{2}|1900|189\d|late\s+19th|early\s+20th|"
            r"19th\s+century|20th\s+century|colonial)\b|"
            r"19세기|20세기|식민",
            text,
            re.IGNORECASE,
        )
    )
    return bool(has_region and has_period)


def _scene_requests_overlooking_view(prompt: str) -> bool:
    scene = _scene_text(prompt)
    if not scene:
        scene = prompt or ""
    has_view_action = bool(
        re.search(
            r"\b(looking|gazing|watching|staring|standing|arriving|arrives|reaching|entering)"
            r"(?:\s+\w+){0,5}\s+(?:out\s+)?(?:over|toward|at|from|into)\b|"
            r"\boverlook(?:ing)?\b|창밖|내려다보|바라보|응시",
            scene,
            re.IGNORECASE,
        )
    )
    has_view_target = bool(
        re.search(
            r"\b(valley|city|skyline|urban|river|field|battlefield|sea|ocean|"
            r"landscape|mountain|mountains|horizon|view|window|balcony|ridge|"
            r"hill|cliff|terrace)\b|계곡|도시|전망|풍경|창문|창밖|산|강|들판|전장",
            scene,
            re.IGNORECASE,
        )
    )
    return has_view_action and has_view_target

_GLOBAL_STYLE_PUBLIC_PATTERNS: tuple[str, ...] = (
    r"\bColoringBookAF\b",
    r"\bColoring Book\b",
    r"\bsubject[- ]faithful\b",
    r"\b2D webtoon cartoon frame\b",
    r"\bstrict 2D webtoon cartoon only\b",
    r"\bflat vector[- ]like colors\b",
    r"\bthick clean black outlines\b",
    r"\bsimple cel shading\b",
    r"\bdrawn illustration only\b",
    r"\bnon[- ]photographic\b",
    r"\billustration not photo\b",
)

_GLOBAL_STYLE_NON_STYLE_PATTERNS: tuple[str, ...] = (
    r"\badult office fable mood\b",
    r"\boffice fable mood\b",
    r"\bmodern office mood\b",
    r"\bmodern office\b",
    r"\bworkplace mood\b",
)


def _clean_prompt_commas(text: str) -> str:
    out = re.sub(r"\s+", " ", text or "").strip()
    out = re.sub(r"\s+,", ",", out)
    out = re.sub(r",\s*,+", ", ", out)
    return out.strip(" ,.;")


def _sanitize_flag_motif_positive_prompt(text: str) -> str:
    """Keep forbidden flag words out of the positive prompt."""
    out = text or ""
    for pattern in _FLAG_MOTIF_POSITIVE_PATTERNS:
        out = re.sub(pattern, "plain unmarked cloth", out, flags=re.IGNORECASE)
    out = re.sub(
        r"\b(?:unmarked\s+)?allied\s+banners?\s+(?:snapping|wavering|whipping|whip|waver|snap)[^.;]*messengers\s+run\s+between\s+the\s+two\s+camps\b",
        "messengers run through one continuous open command boundary between adjacent Oda and Tokugawa positions, passing bare rope-tied vertical standard poles with wood shafts, rope knots, spear tips, dust, and shadow",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"\b(?:unmarked\s+)?(?:red\s+)?banners?\s+(?:snapping|wavering|whipping|whip|waver|snap)[^.;]*",
        "bare rope-tied vertical standard poles with wood shafts, rope knots, spear tips, empty pole tops, dust, and shadow",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"\b(?:unmarked\s+)?(?:allied\s+)?banners?\b",
        "bare rope-tied vertical standard poles",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(r"\bplain unmarked cloth(?:\s*,\s*plain unmarked cloth)+\b", "plain unmarked cloth", out, flags=re.IGNORECASE)
    return _clean_prompt_commas(out)


_POSITIVE_STYLE_LEAK_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\bsimple\s+cartoon\s+illustration\b", "serious adult graphic novel illustration"),
    (r"\bdocumentary\s+cartoon\s+style\b", "mature documentary graphic novel style"),
    (r"\bcartoon\s+illustration\b", "graphic novel illustration"),
    (r"\bsoft\s+cartoon\b", "controlled inked comic rendering"),
    (r"\bclean\s*,\s*soft\s+natural\s+shadows\b", "controlled natural light and gritty period shadows"),
    (r"\bphoto[-\s]?realistic\b", "hand-painted adult documentary comic rendering"),
    (r"\bphoto[-\s]?realism\b", "hand-painted adult documentary comic rendering"),
    (r"\bphotographic\b", "hand-painted adult documentary comic rendering"),
    (r"\blive[-\s]?action\s+still\b", "hand-painted adult documentary comic frame"),
    (r"\braw\s+photo\b", "hand-painted adult documentary comic frame"),
    (r"\bcute\s*,\s*fluffy\s+(?=(?:kitten|cat|puppy|dog|animal)s?\b)", "natural-furred "),
    (r"\bfluffy\s*,\s*cute\s+(?=(?:kitten|cat|puppy|dog|animal)s?\b)", "natural-furred "),
    (r"\bcute\s+(?=(?:kitten|cat|puppy|dog|animal)s?\b)", "natural "),
    (r"\badorable\s+(?=(?:kitten|cat|puppy|dog|animal)s?\b)", "natural "),
    (r"\bfluffy\s+(?=(?:kitten|cat|puppy|dog|animal)s?\b)", "natural-furred "),
)


def _sanitize_positive_style_leaks(text: str) -> str:
    out = text or ""
    for pattern, replacement in _POSITIVE_STYLE_LEAK_REPLACEMENTS:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return _clean_prompt_commas(out)


def sanitize_global_style_for_prompt(global_style: str, image_prompt: str = "") -> str:
    """Keep channel style as style only; do not let it inject scene settings."""
    style = global_style or ""
    if not re.search(r"\b(korea|korean|joseon|goryeo|hanbok|seoul)\b", image_prompt or "", re.IGNORECASE):
        style = re.sub(r"\bKorean\s+YouTube\b", "YouTube", style, flags=re.IGNORECASE)
        style = re.sub(r"\bKorean\s+", "", style, flags=re.IGNORECASE)
    for pattern in _GLOBAL_STYLE_PUBLIC_PATTERNS:
        style = re.sub(pattern, "", style, flags=re.IGNORECASE)

    # Global style is shared by every cut. Setting words in it must not turn
    # source-story meadow/winter cuts into office/city scenes.
    if not _MODERN_SETTING_RE.search(image_prompt or ""):
        for pattern in _GLOBAL_STYLE_NON_STYLE_PATTERNS:
            style = re.sub(pattern, "", style, flags=re.IGNORECASE)

    return _sanitize_positive_style_leaks(_sanitize_flag_motif_positive_prompt(style))

INDIAN_HISTORY_ACCURACY_DIRECTIVE = (
    " For Indian history scenes, use period-correct South Asian visual culture only: "
    "regional clothing, architecture, tools, vehicles, ritual objects, landscapes, "
    "and materials appropriate to the exact era named in the prompt. Use local "
    "South Asian forms throughout the scene unless the narration explicitly places "
    "another culture or later technology there."
)

INDIAN_HISTORY_NEGATIVE_PROMPT = (
    "Japanese flag, rising sun flag, red sun disc flag, hinomaru, torii gate, "
    "Shinto shrine, samurai, ninja, katana, kimono, Japanese castle, Japanese text, "
    "East Asian temple, pagoda unless historically specified, steamship, steamboat, "
    "steam engine, locomotive, train, railroad, railway, factory chimney, smokestack, "
    "industrial machinery, British colonial uniform unless narration says colonial "
    "period, modern Indian flag unless modern period, modern flag, modern building, "
    "car, truck, power line, neon sign, logo"
)

GENERAL_HISTORY_ACCURACY_DIRECTIVE = (
    "HARD HISTORICAL MATERIAL CULTURE LOCK - FIRST RENDERING RULE. Treat "
    "Year/period and Exact place as the binding source of truth for the image. "
    "Before rendering, infer the real "
    "material culture of that exact date range, region, place type, interior/exterior "
    "setting, and social setting. Choose visible clothing cuts, hairstyles, headwear, "
    "role-specific equipment named by the Scene, tools, weapons only when the narration requires them, "
    "vehicles, vessels, furniture, architecture, ritual objects, everyday objects, "
    "landscape, and materials from that time and place. The image depicts a concrete "
    "local scene from the specified world with conservative period-plausible local "
    "objects made from materials available in that era. Style words may change rendering only; "
    "era, culture, place, props, clothing, architecture, "
    "vehicles, and materials remain fixed to the source context. Background horizons "
    "use local natural terrain, earthen walls, wooden structures, thatch or "
    "straw-thatched roof forms where the early period calls for them, stone "
    "thresholds, courtyards, riverbanks, fields, or mountain haze from the same "
    "period and place."
)

SETTING_HISTORY_ACCURACY_DIRECTIVE = (
    "HARD HISTORICAL SETTING MATERIAL CULTURE LOCK - FIRST RENDERING RULE. "
    "Treat Year/period and Exact place as the binding source of truth for the "
    "image. For object, location, landscape, weather, atmosphere, stillness, "
    "aftermath, evidence, or empty-space cuts, render the concrete local setting "
    "named by the Scene field, including terrain, ground, walls, roofs, thresholds, courtyards, "
    "furniture, vessels, tools, everyday objects, plants, weather, light, dust, "
    "smoke, leaves, shadows, and period materials from that time and place. "
    "Visible content comes from the Scene field and the exact environment, with "
    "conservative period-plausible local objects made from materials available "
    "in that era. Style words affect rendering surface while era, place, "
    "architecture, terrain, materials, weather, light, and Scene-named objects "
    "remain fixed to the source context."
)

OBJECT_EVIDENCE_HISTORY_ACCURACY_DIRECTIVE = (
    "HARD HISTORICAL OBJECT EVIDENCE MATERIAL CULTURE LOCK - FIRST RENDERING "
    "RULE. Treat Year/period and Exact place as the binding source of truth "
    "for the image. For strategic planning boards, tactile marker layouts, "
    "tabletop evidence, documents, artifacts, or other object-first evidence "
    "cuts, render only the Scene-named object, its immediate support surface, "
    "Scene-named small props, light, dust, shadow, wear, and period materials "
    "available in that exact era and place. The visible materials, object "
    "construction, tool forms, cords, stones, pins, weights, cloth, clay, wood, "
    "metal, and lamp light remain conservative and period-plausible. Style "
    "words affect rendering surface only; era, place, object materials, "
    "support surface, light, and Scene-named evidence remain fixed to the "
    "source context. Do not add live hands, pointing fingers, forearms, or "
    "human body parts to object-first evidence cuts unless the Scene explicitly "
    "names the hand action as the subject. Background strips contain no wall "
    "plates, switch-like rectangles, screw plates, labels, plaques, or mounted "
    "boards. Preindustrial Scene-named lamp light resolves as clay oil "
    "lamps, candle stands, braziers, or simple period-local lantern forms made "
    "from materials available in the stated era and place."
    " If the Scene names a calendar, month, or date page, show a blank "
    "cord-tied parchment calendar roll, blank page bundle, or blank notched "
    "wooden calendar tally; use curl, ribbon, shadow, and material layers "
    "instead of ink marks, month names, numerals, or glyphs. If the Scene names "
    "a glowing door or distant relief door, show one single distant open plain "
    "wooden doorway with warm light through a dark period corridor; no paired "
    "doors, exterior gate, roofline, wall plate, or modern handle. If the Scene "
    "names an anatomical drawing or bladder, show one full-frame blank parchment "
    "medical diagram lying flat on a tabletop with a simple red stretched "
    "bladder shape only; crop out the room, walls, doors, windows, beams, gates, "
    "rooflines, and architecture."
)

CIVILIAN_HISTORY_ACCURACY_DIRECTIVE = (
    "HARD HISTORICAL CIVILIAN MATERIAL CULTURE LOCK - FIRST RENDERING RULE. "
    "Treat Year/period and Exact place as the binding source of truth for the "
    "image. Before rendering, infer the real civilian material culture of that "
    "exact date range, region, place type, interior/exterior setting, and social "
    "setting. The complete visible human role set follows the Scene field, including "
    "civilian residents, refugees, settlers, workers, farmers, villagers, "
    "household members, travelers, officials, family members, or other ordinary "
    "non-combat roles named by the Scene. Choose visible clothing cuts, "
    "hairstyles, fabric layers, belts, sashes, Scene-named carrying items, tools, furniture, "
    "architecture, ritual objects, everyday objects, landscape, and materials "
    "from that time and place. The image depicts a concrete local civilian "
    "scene with conservative period-plausible local objects made from materials "
    "available in that era. Style words affect rendering surface while era, "
    "culture, place, props, clothing, architecture, vehicles, and materials "
    "remain fixed to the source context."
)

MODERN_PERIOD_ACCURACY_DIRECTIVE = (
    "HARD PERIOD AND PLACE ACCURACY LOCK - FIRST RENDERING RULE. Treat "
    "Year/period and Exact place as the binding source of truth for the image. "
    "For present-day, contemporary, 20xx, 21st century, office, apartment, city, "
    "street, studio, school, hospital, or other modern contexts, render the real "
    "modern local material world: contemporary civilian fabric clothing, modern "
    "hair styling, current furniture, current architecture, current vehicles, "
    "current devices when the Scene names them, glass windows, concrete or drywall "
    "interiors, city streets, elevators, desks, bags, collars, lapels, seams, "
    "buttons, pockets, fabric folds, and soft textile highlights. Style words "
    "affect rendering surface while the visible era, clothing, props, buildings, "
    "vehicles, and everyday objects stay contemporary to the source context."
)

EARLY_MODERN_EUROPE_MATERIAL_CULTURE_DIRECTIVE = (
    " || EARLY MODERN EUROPE MATERIAL CULTURE LOCK - for Renaissance, early "
    "modern, 15th-century, 16th-century, and 17th-century European scenes, "
    "the stated Year/period and Exact place control every visible person, "
    "room, object, street, and building. Human figures use conservative "
    "period-local European clothing for the stated date and role: linen or "
    "wool shirts, doublets, jerkins, gowns, scholar robes, cloaks, ruffs or "
    "standing collars only when period-appropriate, hose or breeches, leather "
    "shoes or simple boots, soft period caps or bare tied hair, trimmed beards, and tied or shoulder-length "
    "hair. Scholars and nobles use late Renaissance Central European dress, "
    "not modern suits. Torso shapes are robes, cloaks, doublets, linen collars, "
    "ruffs, and cloth folds, never suit lapels, neckties, modern felt hats, fedoras, "
    "derby hats, bowler hats, top hats, epaulettes, shoulder "
    "boards, officer tunics, or modern button-placket jackets. Interiors use plaster, timber beams, plain wood "
    "paneling, carved wooden beds or chairs, linen bedding, trestle tables, "
    "candles, oil lamps, braziers, brass astronomical instruments, and blank "
    "charts or folded papers with no readable writing. Exteriors use local "
    "Renaissance or early Baroque stone, plaster, timber-framed buildings, "
    "courtyards, narrow streets, and period Prague or Central European urban "
    "materials. Do not use ancient Greek or Roman temples, marble colonnades, "
    "togas, chitons, himations, peplos, classical ruins, modern business suits, "
    "neckties, epaulettes, shoulder boards, officer tunics, Victorian coats, 18th-20th century uniforms, modern offices, "
    "modern overcoats, frock coats, tailcoats, modern hospital rooms, modern wall art, electric lighting, switches, or "
    "power outlets."
)

EARLY_MODERN_EUROPE_ASTRONOMY_OBSERVATION_DIRECTIVE = (
    " || EARLY MODERN EUROPE ASTRONOMY OBSERVATION LOCK - astronomy "
    "observation scenes in Renaissance or early modern Europe must keep the "
    "named sky and instrument visible: one late Renaissance scholar at a "
    "window, rooftop, observatory balcony, or dark timber room opening toward "
    "a starry sky, with one brass astrolabe, armillary ring, or quadrant near "
    "the face or hands. Do not replace the sky, instrument, and scholar action "
    "with an indoor wall, map wall, officer portrait, empty room, second "
    "visitor, modern uniform, or modern suit."
)

HISTORICAL_BED_REST_DIRECTIVE = (
    " || HISTORICAL BED REST LOCK - bed-rest, sickroom, peaceful deathbed, or "
    "resting-on-bed scenes in historical contexts show the requested person in "
    "or on a period-local bed with bedding, wearing a loose linen nightshirt, "
    "bed gown, scholar robe, plain indoor robe, or locally appropriate sleeping "
    "garment. No suit jacket, no military coat, no necktie, no epaulettes, no "
    "office clothing, and no extra bedside visitor unless the Scene explicitly "
    "names one. Hands remain relaxed, small, and anatomically ordinary on the "
    "blank bedding or robe."
)

UNLABELED_ASTRONOMICAL_SURFACE_DIRECTIVE = (
    " || UNLABELED ASTRONOMICAL SURFACE LOCK - astronomical charts, star "
    "charts, celestial diagrams, armillary spheres, astrolabes, quadrants, "
    "solar-system models, globes, instrument rings, instrument rims, parchment "
    "circles, and brass or wooden astronomy surfaces remain unlabeled physical "
    "objects. Chart or diagram surfaces are blank material with irregular "
    "paper grain, stains, scratches, and shadow only; do not draw concentric "
    "rings, dots, pinholes, decorative perimeter divisions, or measured marks. "
    "Brass instruments show plain "
    "rings, rods, holes, rivets, shadows, stains, scratches, and unlabeled "
    "landmass shapes when a globe is named. No letters, no numbers, no zodiac "
    "symbols, no coordinate numerals, no tick marks, no degree scale, no "
    "tick-number labels, no pseudo glyphs, no alphabet rings, no star-shaped "
    "icons, no written constellations, no map labels, and no readable markings."
)

ASTRONOMICAL_CHART_OBJECT_DIRECTIVE = (
    " || ASTRONOMICAL CHART OBJECT STILL-LIFE LOCK - when the Scene names a "
    "star chart, astronomical chart, or celestial diagram as an object-first "
    "surface, render a low tabletop still life with no people, no hand, no "
    "forearm, and no fingers. The chart is a plain blank circular parchment or "
    "wood disk under the named props, empty material with irregular stains, "
    "creases, scratches, and shadow only. The disk edge is plain blank material "
    "with no concentric rings, no dots, no pinholes, no perimeter ticks, no rim "
    "divisions, no degree scale, no letters, no numbers, no zodiac signs, no "
    "glyphs, and no star icons. If the Scene uses a split-screen wording, ignore the split-screen "
    "format and place all named objects together on one continuous tabletop "
    "still life surface. If the Scene names a beer mug, wooden mug, broken mug, "
    "goblet, or vessel with the chart, that vessel stays in the foreground, "
    "touching or partly covering the blank disk, and remains plainly visible. "
    "Meaning comes from the named prop placement, spilled liquid, stains, "
    "dust, shadow, and hard side light."
)

EARLY_MODERN_SINGLE_PERSON_COUNT_DIRECTIVE = (
    " || EARLY MODERN SINGLE PERSON COUNT LOCK - when a Renaissance or early "
    "modern European Scene names one person, show exactly one complete readable "
    "living person total. Do not add a second face, second torso, duplicate "
    "twin, companion, visitor, assistant, mirror reflection person, portrait "
    "duplicate, or partial extra body. Use one chair only when the Scene says "
    "seated or sitting, with empty visible wall, empty chair arm, shadow, or "
    "negative space on both sides of the single person. Hands remain small, "
    "ordinary, and partly sleeve-covered unless the named action requires them. "
    "If an astronomy instrument is present, it stays beside, behind, or "
    "below the one person and never covers the head, face, neck, or torso as a "
    "replacement body."
)

EARLY_MODERN_THREE_SCHOLAR_GROUP_DIRECTIVE = (
    " || EARLY MODERN THREE SCHOLAR GROUP LOCK - when a Renaissance or early "
    "modern European Scene names a group of scholars without a different count, "
    "show exactly three separate scholars total, not four, five, six, or a crowd. "
    "They wear dark scholar robes, cloaks, doublets, and white ruffs or standing "
    "linen collars, not business suits, neckties, fedoras, derby hats, bowler hats, "
    "top hats, or modern felt hats. Hands stay tucked into "
    "sleeves, relaxed near waists, or resting on one plain empty wooden table; "
    "no large foreground fingers, no exposed finger spread, no wristwatch, no modern watch, and no bracelet. "
    "The table surface is plain wood with hand shadows only: no paper sheet, no "
    "document, no notebook, no writing, and no ink marks. Use a tight waist-up "
    "library crop against plain wooden bookshelves and blank plaster only. Crop "
    "out doors, windows, modern handles, wall switches, power outlets, table "
    "lamps, desk lamps, fabric lampshades, and modern lamp bases. Interior light "
    "is candle or simple oil-lamp glow implied by shadow only; the lamp object "
    "itself does not need to appear."
)

EARLY_MODERN_EUROPE_WRONG_CULTURE_NEGATIVE_PROMPT = (
    "ancient Greek temple, Roman temple, classical temple, marble colonnade, "
    "Greek colonnade, Roman colonnade, toga, chiton, himation, peplos, ancient "
    "Greek robe, ancient Roman robe, leather sandals, classical ruins, modern "
    "business suit, black suit, grey suit, suit jacket, necktie, tie, dress "
    "shirt, modern white shirt collar, modern shirt cuffs, blazer, office suit, "
    "Victorian suit, Victorian coat, frock coat, 18th century coat, 19th century "
    "coat, 20th century suit, double-breasted suit, officer tunic, fedora, derby hat, "
    "bowler hat, homburg hat, trilby, top hat, modern felt hat, modern overcoat, epaulettes, "
    "shoulder boards, military uniform, modern bedroom, hospital bed, modern office room, "
    "modern framed wall art, printed poster, electric lamp, ceiling light, wall "
    "switch, switch plate, power outlet, modern door handle"
)

IMAGE_QUALITY_DIRECTIVE = (
    " || IMAGE QUALITY LOCK - top-tier 16:9 1080p-ready story frame, crisp "
    "readable silhouettes, bold hand-painted linework, extra-thick black "
    "outer contours, clean matte cel shading, controlled natural light, sharp "
    "faces, stable anatomy for the body parts visible in the chosen camera "
    "crop, clean object edges, finished production illustration."
)

ADULT_GRAPHIC_NOVEL_STYLE_DIRECTIVE = (
    " || ADULT GRAPHIC NOVEL STYLE LOCK - render with a serious adult graphic "
    "novel and mature documentary manhwa tone: extra-thick black ink contour "
    "lines, bold outer silhouettes, heavy brush-ink line weight, hard shadow "
    "masses, low-key dark cinematic atmosphere, high-contrast shadow shapes, "
    "gritty period material texture, desaturated restrained color grading, "
    "dramatic rim light, angular stylish single-frame composition, dynamic cropping, "
    "varied camera rhythm, emotion-forward staging, and weighty facial acting. "
    "Across adjacent cuts, do not repeat the same camera distance, same flat "
    "front-facing group arrangement, or same crawling/fallen body layout when "
    "the narration allows a different factual angle; alternate readable faces, "
    "object evidence, command reactions, low-angle danger, and wide consequence "
    "shots while preserving the exact story event. Historical material "
    "accuracy outranks style: clothing, role-specific equipment, animals, architecture, "
    "props, and terrain must stay exact to the stated era, place, and culture. "
    "Avoid bright "
    "pastel skies, cute rounded forms, clean storybook softness, and cheerful "
    "children's illustration color balance. "
    "The style is mature and severe, not childlike, cute, chibi, mascot-like, "
    "toy-like, or children's book illustration."
)

COMMON_SENSE_ANATOMY_DIRECTIVE = (
    " || COMMON-SENSE ANATOMY LOCK - all visible living bodies obey ordinary "
    "physical anatomy. Each visible human has one head, one face, one neck, "
    "one torso, two arms, two hands, two legs when legs are visible, and natural "
    "left-right body symmetry around one spine. A readable human can never share "
    "a head, torso, shoulder line, waist, or limb set with another body. Two "
    "people must appear as two separated silhouettes with two separated heads, "
    "two separated necks, two separated torsos, and visible negative space, "
    "clothing boundaries, or overlap edges between them. "
    "joint directions. Default visible hand budget is zero. Do not add hands, "
    "fingers, palms, or hand close-ups just to satisfy anatomy; visible hands "
    "appear only when the Scene action, gesture, object contact, weapon grip, "
    "reins, armrest grip, or body pose already requires them. When hands are "
    "not required, hide them inside sleeves, behind bodies, behind objects, "
    "below the crop, in shadow, or outside the frame. When a hand is required, "
    "keep it conservative and physically readable: one coherent palm when "
    "visible, one thumb, four fingers, ordinary knuckle spacing, and a plausible "
    "wrist connection. Fingers do not multiply, fuse, fork, melt together, bend "
    "backwards, or grow from the wrong side of the palm. If the Scene does not "
    "make hands the main subject, keep hands small, partly sleeve-covered, "
    "clenched, gripping one named object, holding reins, or cropped at the frame "
    "edge; do not make large foreground hand close-ups, spread fingers, splayed "
    "fingers, or detailed fingernail close-ups. If hands are the main action "
    "subject, limit the frame to one or two readable hands doing one simple "
    "action, with the exact thumb/finger layout visible and no extra background hands. "
    "Every visible supporting body is fully connected from head or torso through "
    "the visible weight-bearing limbs. Each visible "
    "animal keeps the species' normal body plan: horses, cats, wolves, dogs, "
    "cattle, deer, and similar quadrupeds have one head, one neck, one torso, "
    "four attached legs or hooves or paws, one tail when visible, and all body "
    "parts belonging to the same animal silhouette. A horse or other quadruped "
    "can never have one head attached to two torsos, a duplicate torso, an extra "
    "neck, fused bodies, or legs from another animal. Prefer side-view or "
    "three-quarter poses where the head, neck, torso, four legs, and tail read "
    "as one coherent body. No human-made carried gear appears unless the Scene "
    "explicitly names animal gear."
)

OBJECT_EVIDENCE_IMAGE_QUALITY_DIRECTIVE = (
    " || IMAGE QUALITY LOCK - top-tier 16:9 1080p-ready object evidence frame, "
    "crisp readable object silhouettes, bold hand-painted linework, extra-thick "
    "black outer contours, clean matte cel shading, controlled natural light, clean object edges, "
    "stable perspective on the requested low surface, and finished production "
    "illustration."
)

OBJECT_EVIDENCE_GRAPHIC_NOVEL_STYLE_DIRECTIVE = (
    " || ADULT GRAPHIC NOVEL STYLE LOCK - render object-only evidence with a "
    "serious adult graphic novel and mature documentary manhwa tone: extra-thick "
    "black ink outlines, bold visible object silhouettes, heavy brush-ink line "
    "weight, dark low-key cinematic atmosphere, high-contrast shadow shapes, "
    "gritty period material texture, desaturated restrained color grading, dramatic rim light, "
    "and weighty still-life tension. The style is mature and severe, not "
    "childlike, cute, chibi, mascot-like, toy-like, or children's book "
    "illustration."
)

OBJECT_EVIDENCE_PHYSICAL_COMMON_SENSE_DIRECTIVE = (
    " || OBJECT PHYSICAL COMMON-SENSE LOCK - all visible objects obey ordinary "
    "physical construction and contact. Cords lie on or slightly across the "
    "surface, stone clusters rest on the same surface, weights and pins have "
    "one coherent solid form, lamps cast one consistent light direction, and "
    "all shadows match the same low horizontal plane. No object duplicates into "
    "a second unrelated subject."
)

ROLE_EQUIPMENT_COMMON_SENSE_DIRECTIVE = (
    " || ROLE EQUIPMENT COMMON-SENSE LOCK - visible clothing, protective layers, "
    "handheld gear, "
    "tools, and status objects follow the stated Year/period, Exact place, "
    "Scene role, rank, and action. Armed protective roles use era-local practical "
    "protective clothing or ordinary military clothing; rulers and officials "
    "use era-local authority clothing; civilians use everyday local fabric "
    "layers. Grooms, brides, families, wedding or marriage visitors, silk-clothed "
    "civilians, gift bearers, elders, children, workers, and household members "
    "remain non-military unless the Scene explicitly names armed duty or combat; "
    "they wear period-local cloth, robe, tunic, sash, belt, cloak, veil, or "
    "ordinary formal garments rather than battle protection, cuirass, shoulder "
    "guards, helmet, military harness, or military loadout. A handheld combat item appears only when the Scene names an armed "
    "role, battle, protective duty, soldier, warrior, hunt, execution, or direct combat "
    "action. Protective outfits and combat gear stay practical, era-local, "
    "role-specific, and proportional to the action."
)

CUT_INVENTORY_BOUNDARY_DIRECTIVE = (
    " || CUT INVENTORY BOUNDARY LOCK - the Global visual world and Material "
    "culture fields are allowed reference inventory, not mandatory props. Render "
    "only visible things named or directly required by this cut's Main subject, "
    "Scene, Exact place, and Scene evidence. Extra loose sheets, written records, "
    "route boards, labeled boards, spare blades, protective gear, mounts, fabric "
    "standards, ships, crowns, seats, and ceremonial objects stay absent when "
    "they appear only in the global world description. If the Scene does not "
    "name records, route surfaces, labeled boards, or written surfaces, those "
    "items are absent from the frame."
)

DYNAMIC_ACTION_EMOTION_DIRECTIVE = (
    " || DYNAMIC ACTION AND EMOTION LOCK - use an active story camera instead "
    "of a static identity portrait. Choose the camera angle from the Scene: three-quarter face, side "
    "turn, over-shoulder tension, lowered head, raised chin, recoiling shoulder, "
    "leaning body, running stride, braced stance, lunge, defensive posture, "
    "or diagonal clash when the narration implies action. Close-ups still carry "
    "story motion through eye direction, jaw tension, brow shape, shoulders, "
    "hands, and background pressure. Battle, chase, charge, and fight scenes "
    "use diagonal composition, dust, motion pressure, advancing and recoiling "
    "body angles, and readable impact. Group action "
    "uses asymmetric side and three-quarter body angles, overlapping advances "
    "and recoils, bent arms and knees, dust trails, handheld motion arcs, and "
    "a clear diagonal impact path. Emotional dialogue cuts show the spoken "
    "meaning as visible expression, gesture, distance between people, object "
    "contact, or environmental pressure, not as a neutral standing portrait."
)

VISUAL_QA_READINESS_DIRECTIVE = (
    " || VISUAL QA READINESS LOCK - the image must survive frame-by-frame "
    "workbench review before video assembly. Keep the main subject readable, "
    "with no ambiguous anatomy, off-era props, accidental extra body, extra "
    "animal, or stray object. Visible separated human hands show exactly one "
    "thumb and four fingers, or stay simplified inside sleeve shadow without "
    "individual malformed digits. Visible legs and feet connect to the correct "
    "body. Animals keep a normal species body plan. Props, weapons, harnesses, "
    "and tools match the stated period, place, culture scope, and scene action."
)

CHARACTER_ENTRANCE_GRANDEUR_DIRECTIVE = (
    " || CHARACTER ENTRANCE GRANDEUR LOCK - when a named ruler, commander, "
    "or major historical figure appears, stage the moment as a stylish, "
    "large-feeling story entrance rather than a flat identity portrait. Use "
    "medium-close or close three-quarter framing when the Scene allows it, "
    "with face, eyes, shoulders, silhouette, and emotional pressure dominating "
    "the frame. The pose must carry authority, fear, rage, grief, calculation, "
    "or resolve from the narration."
)

PERIOD_WEAPON_AND_PROP_AUDIT_DIRECTIVE = (
    " || PERIOD WEAPON AND PROP AUDIT LOCK - every visible weapon, tool, "
    "armor piece, vehicle, animal harness, lamp, furniture item, document "
    "surface, and status object must pass the Year/period, Exact place, "
    "Culture scope, and Scene evidence. Do not borrow later, foreign, fantasy, "
    "or modern gear for drama. If a weapon or special object is not named or "
    "directly required by the Scene action, keep it absent or reduce it to "
    "ordinary period-local role equipment."
)

SCENE_ACTION_OBJECT_EVIDENCE_DIRECTIVE = (
    " || SCENE ACTION OBJECT EVIDENCE LOCK - every Scene-named action, hand "
    "contact, carried object, weather effect, fire effect, damage mark, and "
    "environmental pressure must be visible as physical evidence in the frame. "
    "If the Scene says holding, clutching, carrying, gripping, dragging, pulling, "
    "pushing, raising, pointing, reaching, running, fleeing, kneeling, bowing, "
    "fighting, charging, recoiling, or watching, show that body action through "
    "the hands, sleeves, shoulders, torso angle, legs when visible, and the "
    "object or direction involved. If the Scene names household goods or "
    "personal belongings, show them as concrete period objects in hand contact: "
    "a tied cloth bundle, small wooden box, bedding roll, basket, or tied sack, "
    "not blank hands or unrelated documents. If the Scene names smoke, soot, "
    "ash, embers, flame, fire, burning, burned buildings, rain, storm, dust, "
    "mud, blood, tears, ruin, or damage, make that material visible in the "
    "same physical space. Do not replace a named action with neutral standing, "
    "folded hands, posed lineup, or a clean static portrait."
)

EARLY_GOGURYEO_FRONTIER_DIRECTIVE = (
    " || EARLY GOGURYEO FRONTIER LOCK - When the stated context is early "
    "Goguryeo, Buyeo, or a Goguryeo-related ancient Northeast Asian frontier "
    "setting, use the exact Year/period and Exact place from the prompt and "
    "a modest frontier proto-state visual world: timber "
    "palisades, packed-earth ramparts, low earthen-walled timber shelters and longhouses, straw-thatched "
    "roofs with visible straw fibers, smoke-dark interiors, packed dirt courtyards, "
    "river-valley and mountain terrain, horses, iron arrowheads, bronze rings, "
    "bronze ritual vessels, hemp and coarse wool garments, fur-lined cloaks, "
    "topknots or simple tied hair. Civilian, refugee, camp, work, household, "
    "and travel scenes use cloth tunics, robes, coarse cloaks, sashes, woven "
    "bags, baskets, pots, rope, straw bundles, timber poles, and wooden tools. "
    "Armed role, guard, soldier, warrior, and battle scenes use leather or "
    "early iron lamellar armor made of many small overlapping plates over "
    "hemp or coarse cloth, tied with dark cords and leather straps; no smooth "
    "plate cuirass, no polished steel breastplate, no knight armor, no Roman "
    "armor, no samurai armor, no fantasy pauldrons, and no large rounded "
    "metal shoulder plates. A visible hand weapon appears only when the "
    "Scene names a weapon or weapon action. Every visible roof surface is straw thatch or bark "
    "grain over plain timber beams. Rooflines stay low, straight, rough, and "
    "frontier-scale. Every visible human head has tied hair, a natural hairline, "
    "and a smooth rounded skull silhouette. Do not use Joseon gat hats, black "
    "wide-brim horsehair hats, tall cylindrical black hats, scholar hats, or "
    "any later Korean formal headwear."
)

EARLY_GOGURYEO_CIVILIAN_FRONTIER_DIRECTIVE = (
    " || EARLY GOGURYEO CIVILIAN FRONTIER LOCK - When the stated context is "
    "early Goguryeo, Buyeo, or a Goguryeo-related ancient Northeast Asian "
    "civilian scene, use the exact Year/period and Exact place from the prompt "
    "and a modest frontier proto-state "
    "visual world: timber palisades, packed-earth ramparts, low earthen-walled "
    "timber shelters and longhouses, straw-thatched roofs with visible straw "
    "fibers, smoke-dark interiors, packed dirt courtyards, river-valley and "
    "mountain terrain, hemp and coarse wool garments, fur-lined cloaks, "
    "topknots or simple tied hair. Civilian, refugee, camp, work, household, "
    "and travel scenes use cloth tunics, robes, coarse cloaks, sashes, woven "
    "bags, baskets, pots, rope, straw bundles, timber shelter poles, woven "
    "mats, sacks, cloth bundles, wooden digging tools, and shelter materials. "
    "Every visible torso reads as soft cloth, fur cloak edge, rope belt, "
    "basket strap, apron fabric, or textile folds. Rooflines stay low, "
    "straight, rough, and frontier-scale. Every visible human head has tied "
    "hair, a natural hairline, and a smooth rounded skull silhouette."
)

EARLY_GOGURYEO_SETTING_DIRECTIVE = (
    " || EARLY GOGURYEO SETTING LOCK - When the stated context is early "
    "Goguryeo, Buyeo, or a Goguryeo-related ancient Northeast Asian setting, "
    "use the exact Year/period and Exact place from the prompt. Object, "
    "location, weather, stillness, aftermath, and atmosphere "
    "cuts use a modest frontier proto-state setting: packed-earth courtyards, "
    "low earthen-walled timber shelters and longhouses, straw-thatched roofs "
    "with visible straw fibers, rough timber beams, plain plaster walls, "
    "basketry, pottery, rope, straw bundles, woven mats, sacks, timber poles, "
    "river-valley and mountain terrain, dust, smoke, rain, shadows, and fallen "
    "leaves named by the Scene. The complete visible subject set is the "
    "Scene-named place, surface, weather, leaves, light, and everyday material "
    "evidence in one empty period-correct setting."
)

EARLY_GOGURYEO_ARTIFACT_DIRECTIVE = (
    " || EARLY GOGURYEO ARTIFACT LOCK - Artifact and evidence scenes from "
    "early Goguryeo, Buyeo, or Goguryeo-related ancient Northeast Asian context "
    "use the exact Year/period and Exact place from the prompt and an "
    "object-only close ground still-life. The era is shown "
    "through one small flat circular bronze ring lying flat, sealed cords, iron "
    "arrowheads, smooth river stones, dust, clay, leather, and packed earth. "
    "The packed-earth ground surface fills the frame edge to edge as one "
    "object-first still-life with hard side light and a narrow dark earthen edge. "
    "The visible frame contains only ground, stones, ring, cord, arrowheads, dust, and clay."
)

EARLY_GOGURYEO_CHARACTER_DIRECTIVE = (
    " || EARLY GOGURYEO CHARACTER LOCK - Major character scenes from early "
    "Goguryeo, Buyeo, or Goguryeo-related ancient Northeast Asian context use "
    "the exact Year/period and Exact place from the prompt and a 2D painted "
    "illustrated character story frame with visible "
    "ink contours, matte cel-shaded skin planes, stylized facial structure, and "
    "hand-painted light. Clothing is early frontier Goguryeo/Buyeo material "
    "culture: layered hemp tunic, coarse wool or fur cloak, leather belt, simple "
    "tied hair behind the head, cloth neckline, sash, and role-appropriate outer "
    "layer. Civilian, political, household, travel, work, refuge, captive, and "
    "social scenes show cloth and fur clothing layers as the readable torso "
    "surface. The visible head silhouette is natural hairline, tied hair, and "
    "a smooth rounded skull outline. Do not use Joseon gat hats, black wide-brim "
    "horsehair hats, tall cylindrical black hats, scholar hats, or any later "
    "Korean formal headwear. Interior walls contain only cracked plaster, rough "
    "timber, dust, shadow, and uneven stains: no switch plate, no paired wall "
    "buttons, no small rectangular wall control, no wall label, and no modern "
    "hardware plate. Setting evidence remains readable as "
    "plain earthen wall, rough timber beam, rain, dust, platform edge, courtyard, "
    "road, or mountain haze according to the Scene."
)

EARLY_GOGURYEO_LANDSCAPE_DIRECTIVE = (
    " || EARLY GOGURYEO LANDSCAPE LOCK - Landscape scenes from early Goguryeo, "
    "Buyeo, or Goguryeo-related ancient Northeast Asian context use the exact "
    "Year/period and Exact place from the prompt, with open mountain-valley "
    "terrain, steep rocky slopes, riverbanks, fields, "
    "mist, packed dirt paths, scattered stones, low grass, and field boundaries. "
    "The frame is filled edge to edge by terrain, river, fields, rocks, grass, "
    "and mountain haze. The main subject remains the terrain and settlement "
    "potential of the valley."
)

GOGURYEO_SILLA_415_DIRECTIVE = (
    " || GOGURYEO-SILLA 415 MATERIAL CULTURE LOCK - when the stated context "
    "names Goguryeo and Silla, the Hou bowl, King Gwanggaeto, Jangsu, 415 CE, "
    "or a 5th-century Three Kingdoms Korea episode, use the exact Year/period "
    "and Exact place from the prompt. This is mature 5th-century Three Kingdoms "
    "Korean history, not Joseon, Goryeo, modern Korea, medieval Japan, Tang, Song, "
    "or fantasy Asia. Goguryeo military or envoy figures use practical dark "
    "leather or dull iron lamellar made from small tied plates over hemp, wool, "
    "or silk layers, simple helmets only when the Scene names armed duty, tied "
    "hair, leather belts, plain boots or soft footwear, composite bows, spears, "
    "short swords, and horse tack only when named by the Scene. Silla figures "
    "and Gyeongju settings use early Silla wooden-chamber stone-mound tomb, "
    "plain timber, packed earth, stone mound, simple elite robe, modest gold "
    "ornament only when the Scene names elite tomb or royal evidence. Buildings "
    "stay low timber, earthen, or stone-bound; no Joseon gat, no black horsehair "
    "scholar hats, no later palace formalwear, no samurai armor, no katana, no "
    "Japanese gate, no modern museum display unless the Scene explicitly asks "
    "for a modern museum view."
)

HOU_BOWL_OBJECT_DIRECTIVE = (
    " || HOU BOWL OBJECT LOCK - when the Scene names the Hou bowl, Houchong "
    "bowl, Ho-u vessel, Houmyeong vessel, or the Gwanggaeto inscription bowl, "
    "the visible subject is one dull aged bronze Goguryeo hou vessel from 415 CE. "
    "Make one coherent bronze vessel only, resting on a low dark cloth, wood, "
    "packed-earth, or tomb-evidence surface. The bronze surface shows patina, "
    "cast thickness, rim edge, foot or base contact, dents, soot, dust, and hard "
    "side light. The inscription evidence is implied by shallow cast relief or "
    "shadowed underside texture only; do not draw readable Korean, Chinese, "
    "hanzi, label text, captions, museum tags, or black handwriting. Do not "
    "replace the vessel with a rice bowl, kitchen basin, helmet, crown, jar, "
    "gold treasure box, open cooking pot, or modern display case. If hands are "
    "needed for scale, show at most two cropped sleeve-covered hands touching "
    "the vessel edge, each with one thumb and four fingers."
)

GOGURYEO_SILLA_415_NEGATIVE_PROMPT = (
    "Joseon gat, Korean horsehair hat, black scholar hat, Goryeo court hat, "
    "Joseon palace robe, modern hanbok, modern museum display case unless named, "
    "samurai armor, katana, tachi, Japanese gate, torii gate, Shinto shrine, "
    "Tang palace, Song official hat, Chinese imperial dragon robe, fantasy Asia, "
    "modern Korean palace tourist scene, neon museum label, glass vitrine, "
    "modern exhibition plaque, modern national flag"
)

HOU_BOWL_NEGATIVE_PROMPT = (
    "rice bowl replacing Hou bowl, kitchen bowl replacing Hou bowl, soup bowl, "
    "mixing basin, cooking pot, cauldron, helmet replacing Hou bowl, crown "
    "replacing Hou bowl, treasure box replacing Hou bowl, gold chest replacing "
    "Hou bowl, modern glass display case, museum label beside Hou bowl, paper "
    "caption beside Hou bowl, readable inscription characters, black handwriting "
    "on bronze, large Chinese characters on vessel, Korean letters on vessel, "
    "floating bowl, missing bronze vessel, human portrait replacing Hou bowl"
)

_KOREAN_HISTORY_RE = re.compile(
    r"(고구려|goguryeo|koguryo|백제|baekje|paekche|신라|silla|가야|gaya|"
    r"발해|balhae|고조선|gojoseon|부여|buyeo|삼국시대|three kingdoms|"
    r"ancient korea|korean kingdom|korean kingdoms|"
    r"고려|goryeo|koryo|조선|joseon|choson|백제의|신라의|고구려의)",
    re.IGNORECASE,
)

_GOGURYEO_SILLA_415_CONTEXT_RE = re.compile(
    r"(호우명|호우|\bhou\s+bowl\b|\bhouchong\b|\bho[-\s]?u\b|gwanggaeto|광개토|장수왕|"
    r"jangsu|silla|신라|silseong|실성|눌지|naemul|복호|bokho|415\s*ce|"
    r"415년|을묘년|eulmyo|5th\s+century|fifth\s+century|400\s*ce|400년)",
    re.IGNORECASE,
)

_HOU_BOWL_SCENE_RE = re.compile(
    r"(호우명|호우|\bhou\s+bowl\b|\bhouchong\b|\bho[-\s]?u\s+vessel\b|gwanggaeto.*bowl|"
    r"광개토.*그릇|광개토.*호우|청동\s*그릇|bronze\s+(?:bowl|vessel))",
    re.IGNORECASE,
)

_INDIAN_HISTORY_RE = re.compile(
    r"(india|indian|bharat|harappa|harappan|mohenjo|daro|indus|vedic|veda|aryan|"
    r"sanskrit|mauryan|maurya|gupta|magadha|ashoka|chandragupta|sindhu|"
    r"hindustan|ancient india|indian civilization|indian civilisation|"
    r"भार[ततीय]|हड़प्पा|सिंधु|मोहनजोदड़ो|वैदिक|मौर्य|गुप्त)",
    re.IGNORECASE,
)

_EXPLICIT_JAPAN_RE = re.compile(
    r"(japan|japanese|일본|왜국|yamato|일장기|hinomaru|samurai|shinto|torii)",
    re.IGNORECASE,
)

_ONE_MINUTE_YEOKGONG_RE = re.compile(
    r"(1\s*분\s*역공|일\s*분\s*역공|one\s*minute\s*yeokgong|one\s*minute\s*counter)",
    re.IGNORECASE,
)

I2V_SAFE_STILL_DIRECTIVE = (
    " || sharp single-exposure still image for image-to-video, crisp subject edges, "
    "clear solid silhouettes, freeze-frame action, single visible body per subject, "
    "stable opaque forms"
)

ANATOMY_SAFE_DIRECTIVE = (
    " || ANATOMY SAFETY — every living subject must have one complete coherent body. "
    "All visible limbs are attached to the correct torso, inside the frame, and "
    "grounded in the same pose. Keep bodies separated with clear silhouettes and "
    "simple poses."
)

HUMAN_ANATOMY_DIRECTIVE = (
    " Human/character anatomy: one head, one torso, two arms, two legs, natural "
    "shoulders and elbows. Hands stay small or simplified."
)

QUADRUPED_ANATOMY_DIRECTIVE = (
    " Quadruped anatomy: every dog, cat, horse, cow, deer, wolf, fox, bear, or similar "
    "animal has exactly one head, one torso, four attached legs/paws/hooves, and one "
    "tail if visible. Prefer side-view or three-quarter standing/walking poses with "
    "all four feet grounded and separated."
)

HAND_SAFE_DIRECTIVE = (
    " || HAND SAFETY - keep arms simple and hands small, simplified, and secondary "
    "to the face, body angle, and story action."
)

LIMB_FRAME_SAFE_DIRECTIVE = (
    " || LIMB FRAMING SAFETY - use medium or wide framing with the whole subject "
    "visible and all limbs attached inside the frame."
)

CARTOON_FACELESS_DIRECTIVE = (
    " || CARTOON CHARACTER FACE LOCK — for any cartoon, simple, mascot, or stylized "
    "character, keep the head as a blank simple shape. Communicate the scene with "
    "silhouette, body pose, clothing, props, and lighting only."
)

# Local SDXL follows positive tokens too literally. Keep additional safety
# suffixes disabled in the default LoRA path.
I2V_SAFE_STILL_DIRECTIVE = " || crisp still frame, sharp subject edges, clean solid silhouette"
ANATOMY_SAFE_DIRECTIVE = " || one complete coherent body, attached simple limbs, centered readable pose"
HUMAN_ANATOMY_DIRECTIVE = " Simple character body with one head, one torso, two arms, two legs, tube-like arms and tiny four-lobed mitten hands."
HAND_SAFE_DIRECTIVE = " || tiny four-lobed mitten hands, hands kept small and away from the foreground, simple gesture"
LIMB_FRAME_SAFE_DIRECTIVE = " || medium shot, whole subject visible, centered composition"
CARTOON_FACELESS_DIRECTIVE = " || blank smooth round head, featureless face area, simple silhouette, readable body pose"

_VIDEO_UNFRIENDLY_IMAGE_PATTERNS = [
    (r"\bmotion\s+blur\s+on\s+[^,.;]+", "sharp subject edges"),
    (r"\bmotion\s+blur\b", "sharp freeze-frame motion"),
    (r"\bblurred\s+motion\b", "sharp freeze-frame motion"),
    (r"\bblurred\s+face\b", "distant face in soft shadow"),
    (r"\bspeed\s+lines?\b", "clean action pose"),
    (r"\blong\s+exposure\b", "single-exposure still"),
    (r"\bdouble\s+exposure\b", "single-exposure still"),
    (r"\bghost(?:ing)?\b", "solid silhouette"),
    (r"\bafterimage\b", "solid silhouette"),
]

_HAND_ANATOMY_RE = re.compile(
    r"\b(hand|hands|finger|fingers|fingertip|fingertips|palm|palms|knuckle|knuckles)\b",
    re.IGNORECASE,
)
_HAND_ACTION_RE = re.compile(
    r"\b(holding|gripping|grabbing|pointing|reaching|pressing|pressed|placing|sprinkling)\b",
    re.IGNORECASE,
)
_HUMAN_SUBJECT_RE = re.compile(
    r"\b(person|people|human|man|woman|boy|girl|child|kid|adult|character|figure|"
    r"researcher|scientist|engineer|explorer|worker|workers|laborer|laborers|labourer|labourers|soldier|farmer|teacher|student|"
    r"doctor|doctors|patient|patients|survivor|survivors|politician|politicians|"
    r"officer|administrator|governor|commissioner|silhouette|narrator)\b",
    re.IGNORECASE,
)
_QUADRUPED_SUBJECT_RE = re.compile(
    r"\b(dog|puppy|cat|kitten|horse|pony|cow|bull|deer|wolf|fox|bear|lion|tiger|"
    r"leopard|cheetah|goat|sheep|pig|boar|rabbit|quadruped|animal)\b",
    re.IGNORECASE,
)
_CROP_RISK_RE = re.compile(
    r"\b(cropped|cut\s*off|out\s+of\s+frame|partial\s+body|fragmented|severed|"
    r"dismembered|detached|floating\s+limb|floating\s+hand|floating\s+leg)\b",
    re.IGNORECASE,
)
_BOOK_OBJECT_RE = re.compile(
    r"\b(book|books|notebook|manuscript|codex|ledger|journal|diary|scripture|"
    r"archive\s+volume|page\s+spread|open\s+pages|page|pages|paper|papers|"
    r"document|documents|scroll|scrolls|papyrus|parchment|petition|petitions|letter|letters|library|"
    r"bookshelf)\b|"
    r"(책|서책|고서|고문서|문서|필사본|원고|두루마리|서재|책장|책상 위의 책|청원|편지|종이)",
    re.IGNORECASE,
)
_VISUAL_SURFACE_OBJECT_RE = re.compile(
    r"\b(paper|papers|document|documents|scroll|scrolls|papyrus|parchment|"
    r"tablet|tablets|relief|mural|painting|illustration|hieroglyph|hieroglyphs)\b|"
    r"(종이|문서|두루마리|벽화|부조|그림|상형문자)",
    re.IGNORECASE,
)
_STATUE_OBJECT_RE = re.compile(
    r"\b(statue|statues|idol|idols|sculpture|sculptures|figurine|figurines|"
    r"monument|monuments|bust|busts|carved\s+deity|carved\s+image|"
    r"relief\s+figure|relief\s+figures|votive\s+figure|votive\s+figures)\b|"
    r"(조각상|우상|신상|불상|석상|동상|흉상|인형|기념상)",
    re.IGNORECASE,
)
_GENERIC_OBJECT_EVIDENCE_RE = re.compile(
    r"\b("
    r"book|books|history\s+book|notebook|manuscript|codex|ledger|journal|"
    r"scripture|archive\s+volume|document|documents|scroll|scrolls|paper|papers|"
    r"calendar|calendars|date\s+page|date\s+pages|year\s+page|year\s+pages|"
    r"tablet|tablets|relief|mural|painting|paintings|illustration|canvas|artwork|"
    r"chessboard|chessboards|game\s+board|board\s+game|game\s+pieces|"
    r"boomerang|boomerangs|abacus|calculator|calculators|poisoned\s+cup|cup|cups|"
    r"target|targets|arrow|arrows|wedding\s+garment|torn\s+garment|garment|garments|"
    r"royal\s+seal|seal\s+stamp|brush|brushes|bamboo\s+scroll|severed\s+head|"
    r"clenched\s+fist|fist|eye|eyes|"
    r"golden\s+stool|sacred\s+stool|royal\s+stool|carved\s+stool|"
    r"crown|crowns|royal\s+crown|ruler\s+status\s+headpiece|authority\s+object|"
    r"crown-like\s+regalia|diadem|tiara|headpiece|regalia|circlet|"
    r"mirror|mirrors|reflective\s+mirror|polished\s+mirror|bronze\s+mirror|"
    r"chain|chains|iron\s+chain|iron\s+chains|family\s+crest|family\s+crests|"
    r"crest|crests|emblem|emblems|household\s+token|household\s+tokens|"
    r"blade|blades|broken\s+blade|sword|swords|broken\s+sword|dagger|daggers|"
    r"knife|knives|weapon|weapons|shield|shields|ring|rings|seal|seals|amulet|"
    r"amulets|wheel|wheels|wooden\s+wheel|wheels?|throne"
    r")\b|"
    r"(책|서책|고서|고문서|문서|두루마리|종이|점토판|벽화|부조|그림|회화|"
    r"왕관|관|관모|보관|거울|동경|검|칼|칼날|부러진\s*칼|무기|방패|반지|인장|부적|"
    r"그릇|항아리|잔|등잔|왕좌)",
    re.IGNORECASE,
)
_RULER_OR_AUTHORITY_ROLE_RE = re.compile(
    r"\b(king|queen|ruler|monarch|emperor|empress|shah|khan|lord|sovereign)\b|"
    r"(왕|왕비|여왕|군주|황제|칸|가한)",
    re.IGNORECASE,
)
_SEATED_THRONE_ACTION_RE = re.compile(
    r"\b(sitting|seated|sit|sits|on\s+(?:a\s+|the\s+)?(?:dark\s+|golden\s+|stone\s+|iron\s+|high\s+|grand\s+)?throne|"
    r"upon\s+(?:a\s+|the\s+)?(?:dark\s+|golden\s+|stone\s+|iron\s+|high\s+|grand\s+)?throne)\b|"
    r"(왕좌에\s*앉|앉아)",
    re.IGNORECASE,
)
_STATUE_LIVING_RELATION_RE = re.compile(
    r"\b(with|beside|next\s+to|behind|around|before|in\s+front\s+of|near|"
    r"surrounded\s+by|watched\s+by|worshipped\s+by|worshiped\s+by|held\s+by|"
    r"carried\s+by|touched\s+by|guarded\s+by)\b.{0,160}"
    r"\b(people|person|human|man|men|woman|women|priest|priests|king|queen|"
    r"ruler|soldier|soldiers|guard|guards|crowd|worshipper|worshippers|"
    r"attendant|attendants|figure|figures)\b|"
    r"\b(people|person|human|man|men|woman|women|priest|priests|king|queen|"
    r"ruler|soldier|soldiers|guard|guards|crowd|worshipper|worshippers|"
    r"attendant|attendants)\b.{0,120}"
    r"\b(bowing|kneeling|standing|walking|holding|carrying|touching|watching|"
    r"worshipping|worshiping|surrounding|guarding)\b",
    re.IGNORECASE | re.DOTALL,
)
_DEPICTION_VERB_RE = re.compile(
    r"\b(depicting|depicts|depicted|showing|shows|illustrating|illustrates|"
    r"painted|drawn|carved|engraved|inscribed)\b|"
    r"(묘사|그려|새겨|조각)",
    re.IGNORECASE,
)
_BOOK_RENDER_OBJECT_RE = re.compile(
    r"\b(book|books|notebook|manuscript|codex|ledger|journal|diary|scripture|"
    r"archive\s+volume|page\s+spread|open\s+pages|library|bookshelf)\b|"
    r"(책|서책|고서|필사본|원고|서재|책장|책상 위의 책)",
    re.IGNORECASE,
)
_PROMPT_FIELD_RE_CACHE: dict[str, re.Pattern] = {}
_BACKGROUND_SHOPPING_LIST_FIELD_RE = re.compile(
    r"(?:^|;\s*)Material\s+culture\s*:\s*.*?"
    r"(?=;\s*(?:Continuity\s+rule|Year/period|Exact\s+place|Scene\s+evidence|"
    r"Style|Main\s+subject|Scene|Time\s+range|Place\s+scope|Culture\s+scope)\s*:|$)",
    re.IGNORECASE | re.DOTALL,
)
_CONTINUITY_RULE_FIELD_RE = re.compile(
    r"(?:^|;\s*)Continuity\s+rule\s*:\s*.*?"
    r"(?=;\s*(?:Year/period|Exact\s+place|Scene\s+evidence|Style|Main\s+subject|Scene)\s*:|$)",
    re.IGNORECASE | re.DOTALL,
)
_SCENE_EVIDENCE_FIELD_RE = re.compile(
    r"((?:^|;\s*)Scene\s+evidence\s*:\s*)(.*?)"
    r"(?=;\s*(?:Style|Main\s+subject|Scene|Year/period|Exact\s+place)\s*:|$)",
    re.IGNORECASE | re.DOTALL,
)
_SCENE_EVIDENCE_CHARACTER_LABEL_RE = re.compile(
    r"^(?:핵심인물|주요인물|주요\s*인물|등장인물|인물|"
    r"main\s+subject|main\s+character|key\s+character|key\s+figure|"
    r"major\s+character|major\s+figure|characters?)\s*=",
    re.IGNORECASE,
)
_CHARACTER_SCENE_RE = re.compile(
    r"\b("
    r"jumong|songyang|haemosu|yuhwa|geumwa|yaa\s+asantewaa|asantewaa|"
    r"king|queen|prince|princess|warlord|ruler|"
    r"leader|chief|chiefs|envoy|emperor|empress|official|officials|officer|officers|"
    r"groom|grooms|bride|brides|guest|guests|visitor|visitors|traveler|travelers|traveller|travellers|"
    r"doctor|doctors|patient|patients|survivor|survivors|politician|politicians|"
    r"peasant|peasants|faction|factions|son|sons|daughter|daughters|hero|heroes|"
    r"administrator|administrators|governor|governors|commissioner|commissioners|courtier|courtiers|"
    r"noble|nobles|nobleman|noblemen|aristocrat|aristocrats|"
    r"messenger|messengers|retainer|retainers|escort|escorts|servant|servants|samurai|warrior|"
    r"fighter|soldier|archer|guard|watchman|watchmen|commander|general|friend|friends|"
    r"companion|companions|refugee|refugees|"
    r"fugitive|fugitives|settler|settlers|worker|workers|laborer|laborers|labourer|labourers|farmer|farmers|"
    r"scribe|scholar|monk|shaman|woman|man|boy|girl|"
    r"mother|father|elder|child|people|person|human|figure|tribal leaders?|she|he"
    r")\b|"
    r"(주몽|해모수|유화|금와|왕|군주|지도자|장군|전사|병사|무사|궁수|"
    r"사신|귀족|신랑|신부|손님|방문객|여행자|나그네|난민|피난민|이주민|농민|일꾼|여인|남자|여자|소년|소녀|어머니|아버지|아이|사람|인물)",
    re.IGNORECASE,
)
_NON_CHARACTER_SCENE_RE = re.compile(
    r"\b("
    r"map|landscape|river|mountain|valley|palace|fortress|wall|gate|tower|"
    r"hall|room|camp|village|city|market|bazaar|road|field|lake|egg|object|artifact|weapon|"
    r"armor|scroll|book|document|throne|clouds?|sky|forest|water|boat"
    r")\b|"
    r"(지도|풍경|강|산|계곡|궁궐|성벽|문|탑|방|마을|도시|시장|길|들판|호수|알|"
    r"물건|유물|무기|갑옷|두루마리|책|문서|왕좌|구름|하늘|숲|물|배)",
    re.IGNORECASE,
)
_MULTI_CHARACTER_SCENE_RE = re.compile(
    r"\b("
    r"people|crowd|crowds|group|groups|audience|audiences|listeners|witnesses|guests|visitors|travelers|travellers|"
    r"army|armies|soldiers|guards|escorts|watchmen|officials|officers|administrators|governors|commissioners|courtiers|nobles|noblemen|aristocrats|messengers|retainers|"
    r"servants|samurai|horsemen|riders|monks|priests|elders|"
    r"fighters|leaders|chiefs|doctors|patients|survivors|politicians|women|men|children|tribal leaders|council|assassins|"
    r"envoys|warriors|villagers|refugees|fugitives|settlers|workers|laborers|labourers|farmers|"
    r"peasants|factions|sons|daughters|heroes|"
    r"grooms|brides|"
    r"formation|family|friends|companions|parents|mother and child|king and queen|"
    r"few|two(?![-\s]*quarter)|three(?![-\s]*quarter)|several|many"
    r")\b|"
    r"(사람들|군중|무리|청중|목격자|군대|병사|호위|관리|지도자들|여인들|남자들|아이들|"
    r"승려들|스님들|성직자들|노인들|회의|조정|암살자들|전사들|마을사람|신랑들|신부들|손님들|방문객들|난민|피난민|이주민|농민|일꾼|가족|부모|둘|셋|여러|많은)",
    re.IGNORECASE,
)
_PROPER_NAME_SCENE_RE = re.compile(
    r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}|"
    r"(?:The|First|Second)\s+(?:King|Queen|Prince|Princess|Emperor|Empress))\b"
)
_PROPER_NAME_NON_PERSON_WORDS = {
    "a",
    "an",
    "scene",
    "year",
    "period",
    "exact",
    "place",
    "japan",
    "japanese",
    "kyoto",
    "kamakura",
    "kyushu",
    "yoshino",
    "minatogawa",
    "hakone",
    "tokaido",
    "pelusium",
    "egypt",
    "egyptian",
    "ashanti",
    "asante",
    "kumasi",
    "gold",
    "coast",
    "persia",
    "persian",
    "achaemenid",
    "korea",
    "korean",
    "goguryeo",
    "buyeo",
    "jolbon",
}
_CHARACTER_ACTION_SCENE_RE = re.compile(
    r"\b("
    r"look|looks|looking|gaze|gazes|gazing|glare|glares|glaring|stare|stares|"
    r"staring|watch|watches|watching|observe|observes|observing|turn|turns|turning|standing|sitting|riding|walking|"
    r"running|escaping|arriving|ordering|pointing|holding|gripping|handing|"
    r"choosing|choose|chooses|deciding|decide|decides|selecting|select|selects|"
    r"pushing|pulling|lifting|raising|raise|raises|arranging|biting|crying|weeping|"
    r"whispering|speaking|speak|speaks|declaring|declare|declares|declared|"
    r"delivering|deliver|delivers|delivered|warning|warn|warns|warned|"
    r"smiling|smile|smiles|puffing|puff|puffs|kneeling|bowing|"
    r"leading|guarding|surrounding|facing|glancing|slam|slams|slammed|slamming|"
    r"strike|strikes|struck|striking|pound|pounds|pounded|pounding|portrait|close[-\s]*up|bust"
    r")\b",
    re.IGNORECASE,
)
_MOUNT_OR_ANIMAL_SCENE_RE = re.compile(
    r"\b(horse|horses|pony|mounted|riding|ride|rider|cavalry|mare|stallion|"
    r"animal|animals|beast|beasts|cow|deer|dog|cat|bear|tiger|wolf|boar)\b|"
    r"(말|기마|타고|타는|기수|동물|짐승|소|사슴|개|고양이|곰|호랑이|늑대|멧돼지)",
    re.IGNORECASE,
)
_ANIMAL_FOCUS_SCENE_RE = re.compile(
    r"\b(horse|horses|pony|mare|stallion|animal|animals|beast|beasts|cow|"
    r"deer|dog|dogs|cat|cats|kitten|kittens|bear|tiger|wolf|boar)\b|"
    r"(말|동물|짐승|소|사슴|개|고양이|새끼\s*고양이|곰|호랑이|늑대|멧돼지)",
    re.IGNORECASE,
)
_EXPLICIT_HUMAN_OR_COMBATANT_SCENE_RE = re.compile(
    r"\b("
    r"person|people|human|humans|figure|figures|group|groups|man|men|woman|women|boy|girl|"
    r"groom|grooms|bride|brides|guest|guests|visitor|visitors|traveler|travelers|traveller|travellers|"
    r"child|children|king|queen|prince|princess|ruler|leader|chief|chiefs|envoy|"
    r"doctor|doctors|patient|patients|survivor|survivors|politician|politicians|"
    r"emperor|empress|official|officials|courtier|courtiers|messenger|"
    r"officer|officers|administrator|administrators|governor|governors|commissioner|commissioners|"
    r"messengers|retainer|retainers|escort|escorts|servant|servants|samurai|warrior|warriors|"
    r"fighter|fighters|soldier|soldiers|archer|archers|guard|guards|worker|workers|laborer|laborers|labourer|labourers|"
    r"peasant|peasants|faction|factions|son|sons|daughter|daughters|hero|heroes|"
    r"commander|commanders|general|generals|army|armies|troops|defenders|"
    r"attackers|cavalry|rider|riders|mounted|yaa\s+asantewaa|asantewaa|she|he"
    r")\b|"
    r"(사람|인물|남자|여자|소년|소녀|아이|신랑|신부|손님|방문객|여행자|나그네|왕|군주|지도자|장군|전사|병사|무사|"
    r"궁수|호위|군대|기병|기수|관리|사신|시종)",
    re.IGNORECASE,
)
_ARMED_FIGURE_SCENE_RE = re.compile(
    r"\b("
    r"soldier|soldiers|guard|guards|escort|escorts|warrior|warriors|fighter|fighters|"
    r"archer|archers|army|armies|battle|battlefield|combat|clash|formation|"
    r"police|security|militia|cavalry|spearman|spearmen|swordsman|swordsmen|"
    r"weapon|weapons|armed|spear|spears|sword|swords|tachi|bow|bows|arrow|arrows|"
    r"shoot|shooting|aim|aiming|rifle|rifles|"
    r"gun|guns|firearm|firearms|baton|batons|shield|shields"
    r")\b|"
    r"(군인|병사|호위|전사|무사|궁수|군대|전투|전장|무장|무기|창|칼|검|활|"
    r"화살|사격|겨냥|쏘|총|소총|방패)",
    re.IGNORECASE,
)

_ARMED_GROUP_OR_BATTLE_SCENE_RE = re.compile(
    r"\b("
    r"soldiers|guards|escorts|fighters|archers|armies|army|battle|battlefield|combat|"
    r"clash|formation|cavalry|militia|spearmen|swordsmen|armed group|armed crowd"
    r")\b|"
    r"(군인|병사|호위|전사들|무사들|궁수들|군대|전투|전장|대열|기병)",
    re.IGNORECASE,
)

_ARMED_FORMATION_GROUP_SCENE_RE = re.compile(
    r"\b("
    r"soldiers|guards|escorts|fighters|archers|armies|army|formation|cavalry|militia|"
    r"spearmen|swordsmen|troops|defenders|attackers|battle\s*line|"
    r"march|marching|advance|advancing|charge|charging|clash|armed group|armed crowd"
    r")\b|"
    r"(군인|병사|호위|전사들|무사들|궁수들|군대|대열|기병|행군|진격|돌격)",
    re.IGNORECASE,
)

_SPECIFIC_WEAPON_SCENE_RE = re.compile(
    r"\b(spear|spears|lance|lances|bow|bows|arrow|arrows|sword|swords|tachi|"
    r"blade|blades|knife|knives|rifle|rifles|gun|guns|firearm|firearms|"
    r"baton|batons|shield|shields)\b|"
    r"(창|장창|활|화살|검|칼|도검|소총|총|방패)",
    re.IGNORECASE,
)

_CIVILIAN_WORK_OR_CAMP_SCENE_RE = re.compile(
    r"\b("
    r"camp|refugee|refugees|fugitive|fugitives|settler|settlers|worker|workers|"
    r"farmer|farmers|peasant|peasants|villager|villagers|migration|migrants|household|family|"
    r"market|kitchen|field work|harvest|shelter|shelters"
    r")\b|"
    r"(난민|피난민|이주민|농민|일꾼|마을사람|가족|가정|시장|부엌|피난|정착|수확|움막)",
    re.IGNORECASE,
)

_MARKET_OR_BAZAAR_LOCATION_SCENE_RE = re.compile(
    r"\b("
    r"market|markets|bazaar|bazaars|trading\s+street|merchant\s+street|"
    r"marketplace|marketplaces|caravanserai|caravan\s+market|silk\s+road\s+market|"
    r"spice\s+stall|spice\s+stalls|silk\s+stall|silk\s+stalls|merchant\s+stalls?"
    r")\b|"
    r"(시장|바자르|상점가|교역로|상인\s*거리|비단\s*시장|향신료\s*시장)",
    re.IGNORECASE,
)

_EMPTY_ATMOSPHERE_SCENE_RE = re.compile(
    r"\b("
    r"everything\s+standing\s+still|standing\s+still|dead\s+leaves|falling\s+leaves|"
    r"leaves\s+falling|falling\s+slowly|stillness|silent\s+yard|empty\s+yard|"
    r"empty\s+courtyard|empty\s+room|empty\s+hall|empty\s+road|empty\s+street|"
    r"empty\s+city\s+street|silent\s+empty\s+city\s+street|silent\s+street|empty\s+field|"
    r"empty\s+farm\s+field|empty\s+farmland|empty\s+poorly\s+maintained\s+farm\s+field|"
    r"poorly\s+maintained\s+farm\s+field|abandoned\s+farm\s+field|deserted\s+farm\s+field|"
    r"quiet\s+aftermath|aftermath|rain|dust|shadow|shadows|smoke|mist"
    r")\b|"
    r"(낙엽|정적|고요|빈\s*마당|빈\s*방|빈\s*길|빈\s*거리|비|먼지|그림자|연기|안개)",
    re.IGNORECASE,
)

_EMPTY_LOCATION_SCENE_RE = re.compile(
    r"\b("
    r"empty\s+yard|silent\s+yard|empty\s+courtyard|empty\s+room|empty\s+hall|"
    r"empty\s+road|empty\s+street|empty\s+city\s+street|silent\s+empty\s+city\s+street|"
    r"silent\s+street|empty\s+field|empty\s+farm\s+field|empty\s+farmland|"
    r"empty\s+poorly\s+maintained\s+farm\s+field|poorly\s+maintained\s+farm\s+field|"
    r"abandoned\s+farm\s+field|deserted\s+farm\s+field|unoccupied\s+field|"
    r"vacant\s+field|empty\s+building|empty\s+house|empty\s+interior"
    r")\b|"
    r"(빈\s*마당|빈\s*방|빈\s*길|빈\s*들판|빈\s*밭|비어\s*있는\s*밭|아무도\s*없는\s*밭)",
    re.IGNORECASE,
)

_EMPTY_NONHUMAN_ATMOSPHERE_SCENE_RE = re.compile(
    r"\b("
    r"everything\s+standing\s+still|standing\s+still|dead\s+leaves|"
    r"falling\s+leaves|leaves\s+falling|falling\s+slowly|stillness|"
    r"silent\s+yard"
    r")\b|"
    r"(낙엽|정적|고요)",
    re.IGNORECASE,
)


def _scene_is_inanimate_statue_object_without_living_people(prompt: str) -> bool:
    scene = _scene_text(prompt)
    if not scene:
        return False
    match = _STATUE_OBJECT_RE.search(scene)
    if not match:
        return False
    living_prefix = scene[: match.start()]
    if (
        _CHARACTER_SCENE_RE.search(living_prefix)
        or _MULTI_CHARACTER_SCENE_RE.search(living_prefix)
        or _scene_mentions_multiple_named_people(living_prefix)
        or _scene_has_named_character_action(living_prefix)
    ):
        return False
    after_object_word = scene[match.end() :]
    if _STATUE_LIVING_RELATION_RE.search(after_object_word):
        return False
    return True


def _scene_requests_empty_seat_or_platform_evidence(prompt: str) -> bool:
    scene = _scene_text(prompt)
    if not scene:
        return False
    has_empty_word = bool(
        re.search(
            r"\b(empty|unoccupied|vacant|abandoned|deserted|no\s+person|"
            r"no\s+people|no\s+human|no\s+humans|without\s+(?:a\s+)?person|"
            r"without\s+people)\b|빈|비어|아무도\s*없는",
            scene,
            re.IGNORECASE,
        )
    )
    has_seat_object = bool(
        re.search(
            r"\b(throne|seat|dais|platform|low\s+timber\s+platform|chair|"
            r"bench|bed|couch|mat)\b|왕좌|좌석|단상|의자|침상|평상|자리",
            scene,
            re.IGNORECASE,
        )
    )
    if not (has_empty_word and has_seat_object):
        return False
    if re.search(
        r"\b(sitting|seated|kneeling|standing|lying|sleeping|occupied\s+by|"
        r"surrounded\s+by|guarded\s+by)\b",
        scene,
        re.IGNORECASE,
    ):
        return False
    return True


def _scene_requests_generic_object_evidence(prompt: str) -> bool:
    scene = _scene_text(prompt)
    if not scene:
        return False
    if _scene_requests_empty_seat_or_platform_evidence(prompt):
        return True
    if _scene_is_animal_focused_without_people(prompt):
        return False
    if (
        _scene_requests_map_object(prompt)
        or _scene_requests_planning_board_object(prompt)
        or _scene_requests_bell_object(prompt)
        or _scene_is_inanimate_statue_object_without_living_people(prompt)
    ):
        return False
    match = _GENERIC_OBJECT_EVIDENCE_RE.search(scene)
    if not match:
        return False
    if re.search(
        r"\b(crown|crowns|royal\s+crown|ruler\s+status\s+headpiece|"
        r"ruler\s+status\s+object|authority\s+object|crown-like\s+regalia|"
        r"diadem|tiara|headpiece|regalia|circlet)\b|왕관|관모|보관",
        scene,
        re.IGNORECASE,
    ) and re.search(
        r"\b(resting|sitting|alone|no\s+wearer|without\s+(?:a\s+)?wearer|"
        r"on\s+(?:a\s+)?(?:surface|table|support|cloth|stone|floor)|in\s+shadows)\b|"
        r"착용자\s*없|놓여|그늘",
        scene,
        re.IGNORECASE,
    ):
        return True
    living_prefix = scene[: match.start()]
    if (
        _CHARACTER_SCENE_RE.search(living_prefix)
        or _MULTI_CHARACTER_SCENE_RE.search(living_prefix)
        or _scene_mentions_multiple_named_people(living_prefix)
    ):
        return False
    living_scan = re.sub(
        r"\b(no\s+person|no\s+people|no\s+human|no\s+humans|no\s+wearer|"
        r"without\s+(?:a\s+)?(?:person|people|human|humans|wearer)|unoccupied)\b",
        "",
        scene,
        flags=re.IGNORECASE,
    )
    living_scan = re.sub(
        r"\b(ruler\s+status\s+headpiece|ruler\s+status\s+object|"
        r"authority\s+object|crown-like\s+regalia)\b",
        "",
        living_scan,
        flags=re.IGNORECASE,
    )
    scene_has_living_subject = bool(
        _CHARACTER_SCENE_RE.search(living_scan)
        or _MULTI_CHARACTER_SCENE_RE.search(living_scan)
        or _scene_mentions_multiple_named_people(living_scan)
        or _scene_has_named_character_action(living_scan)
    )
    is_surface_depiction = bool(
        _VISUAL_SURFACE_OBJECT_RE.search(scene)
        and (
            _DEPICTION_VERB_RE.search(scene)
            or re.search(r"\b(revealing|bearing)\b", scene, re.IGNORECASE)
            or re.search(r"\b(physical\s+painting\s+surface|flat\s+damaged\s+pigment|flat\s+worn\s+pigment)\b", scene, re.IGNORECASE)
            or _scene_is_depicted_surface_evidence_object(prompt)
        )
    )
    is_mirror_reflection = bool(
        re.search(r"\b(mirror|reflective\s+mirror|polished\s+mirror|bronze\s+mirror)\b|거울|동경", scene, re.IGNORECASE)
        and re.search(r"\b(reflective|reflecting|reflection|reflected)\b|반사", scene, re.IGNORECASE)
    )
    if scene_has_living_subject and not (is_surface_depiction or is_mirror_reflection):
        return False
    after_object_word = scene[match.end() :]
    if re.search(
        r"\b(worn\s+by|held\s+by|carried\s+by|guarded\s+by|beside|next\s+to|"
        r"surrounded\s+by|on\s+(?:his|her|their)\s+head)\b.{0,140}"
        r"\b(king|queen|ruler|emperor|empress|person|people|man|woman|guard|"
        r"soldier|warrior|figure|figures)\b|"
        r"(사람|인물|왕|왕비|여왕|군주|황제|호위|병사|전사)",
        after_object_word,
        re.IGNORECASE | re.DOTALL,
    ):
        return False
    return True


def _scene_requests_depicted_visual_surface_object(prompt: str) -> bool:
    scene = _scene_text(prompt)
    return bool(
        _scene_requests_generic_object_evidence(prompt)
        and _VISUAL_SURFACE_OBJECT_RE.search(scene)
        and (
            _DEPICTION_VERB_RE.search(scene)
            or re.search(r"\b(revealing|bearing)\b", scene, re.IGNORECASE)
            or re.search(r"\b(physical\s+painting\s+surface|flat\s+damaged\s+pigment|flat\s+worn\s+pigment)\b", scene, re.IGNORECASE)
            or _scene_is_depicted_surface_evidence_object(prompt)
        )
    )


def _scene_requests_seated_ruler_throne_story(prompt: str) -> bool:
    scene = _scene_text(prompt)
    if not scene:
        return False
    return bool(
        _RULER_OR_AUTHORITY_ROLE_RE.search(scene)
        and re.search(r"\b(throne|seat|dais|platform|low\s+timber\s+platform)\b|왕좌|좌석|단상", scene, re.IGNORECASE)
        and _SEATED_THRONE_ACTION_RE.search(scene)
    )


def _scene_requests_explicit_armed_group_standoff(prompt: str) -> bool:
    scene = _scene_text(prompt)
    if not scene or not _scene_requests_armed_figures(prompt):
        return False
    return bool(
        re.search(
            r"\b(two\s+massive\s+factions|factions?|opposing\s+groups?|"
            r"facing\s+off|face\s+off|stand(?:ing)?\s+behind\s+each\s+queen|"
            r"behind\s+each\s+queen|personal\s+guards?\s+with\b|"
            r"guards?\s+with\b.*\bbehind\s+each\s+queen|"
            r"armored\s+soldiers\s+facing)\b|"
            r"(두\s*세력|양쪽\s*세력|대치|사병|호위.*왕비)",
            scene,
            re.IGNORECASE | re.DOTALL,
        )
    )


def _scene_requests_multi_character_closeup(prompt: str) -> bool:
    scene = _scene_text(prompt)
    if not scene:
        return False
    return bool(
        re.search(r"\b(close[-\s]*up|extreme\s+close[-\s]*up|closeup)\b", scene, re.IGNORECASE)
        and re.search(
            r"\b(two|both|pair|two\s+faces|two\s+people|two\s+women|two\s+men|"
            r"women|men|people)\b|두|둘",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_has_named_character_action(scene: str) -> bool:
    text = scene or ""
    if not text:
        return False
    if _scene_is_inanimate_statue_object_without_living_people(f"Scene: {text}"):
        return False
    if _CHARACTER_SCENE_RE.search(text):
        return True
    for match in _PROPER_NAME_SCENE_RE.finditer(text):
        name = re.sub(r"\s+", " ", match.group(0)).strip().lower()
        if name in _PROPER_NAME_NON_PERSON_WORDS:
            continue
        if re.search(
            r"\b(close[-\s]*up|portrait|face|eyes?|gaze|expression)\b",
            text[max(0, match.start() - 90) : match.start()],
            re.IGNORECASE,
        ):
            return True
        if _CHARACTER_ACTION_SCENE_RE.search(text[match.end() : match.end() + 140]):
            return True
    return False


def _scene_mentions_multiple_named_people(scene: str) -> bool:
    text = scene or ""
    if not text:
        return False
    known_hits: set[str] = set()
    for pattern, fact in _KNOWN_SCENE_IDENTITY_FACTS:
        if pattern.search(text):
            known_hits.add(fact.lower())
    if len(known_hits) >= 2:
        return True
    known_stripped = text
    for pattern, _fact in _KNOWN_SCENE_IDENTITY_FACTS:
        known_stripped = pattern.sub(" ", known_stripped)
    proper_hits: set[str] = set()
    for match in _PROPER_NAME_SCENE_RE.finditer(known_stripped):
        name = re.sub(r"\s+", " ", match.group(0)).strip().lower()
        if name not in _PROPER_NAME_NON_PERSON_WORDS:
            proper_hits.add(name)
    return len(proper_hits) >= 2

_HAND_RISK_IMAGE_PATTERNS = [
    (
        r"\bclose-up\s+of\s+[^,.;]*\bhands?\s+pressed\s+(?:gently\s+)?together\s+in\s+a\s+prayer\s+gesture\b",
        "medium shot of a respectful seated figure bowing at the dining table",
    ),
    (
        r"\b(?:both\s+)?hands?\s+pressed\s+(?:gently\s+)?together\s+in\s+a\s+prayer\s+gesture\b",
        "respectful upper-body bowing posture",
    ),
    (
        r"\ba\s+human\s+hand\s+and\s+a\s+robotic\s+hand\s+almost\s+touching\b",
        "a human silhouette and a robotic silhouette facing the same glowing orb",
    ),
    (
        r"\btwo\s+hands?\s+(?:almost\s+)?touching\b",
        "two simplified silhouettes facing the same glowing orb",
    ),
    (
        r"\bhands?\s+(?:almost\s+)?touching\b",
        "two simplified figures facing the same glowing orb",
    ),
    (
        r"\b(?:both\s+)?hands?\s+pressed\s+(?:gently\s+)?together\b",
        "respectful upper-body bowing posture",
    ),
    (
        r"\bpressed\s+(?:gently\s+)?together\s+in\s+a\s+prayer\s+gesture\b",
        "shown with a respectful upper-body bowing posture",
    ),
    (
        r"\bprayer\s+gesture\b",
        "respectful upper-body bowing posture",
    ),
    (
        r"\bholding\s+chopsticks\b",
        "chopsticks resting beside the bowl",
    ),
    (
        r"\bholding\s+green\s+onions\b",
        "green onions arranged on the food",
    ),
    (
        r"\bplacing\s+green\s+onions\b",
        "green onions arranged on the food",
    ),
    (
        r"\bsprinkling\s+green\s+onions\b",
        "green onions scattered on the food",
    ),
    (
        r"\bholding\s+(?:a\s+)?(?:bowl|plate|cup|dish)\b",
        "bowl or dish resting on a visible table in front of the person",
    ),
    (
        r"\bholding\s+(?:a\s+)?(?:large\s+|small\s+|curved\s+|wooden\s+|ceremonial\s+|single\s+)*bow\b",
        "standing beside a single unstrung curved wooden display bow leaning vertically against a plain wall",
    ),
    (
        r"\bgripping\s+(?:a\s+)?(?:large\s+|small\s+|curved\s+|wooden\s+|ceremonial\s+|single\s+)*bow\b",
        "standing beside a single unstrung curved wooden display bow leaning vertically against a plain wall",
    ),
    (
        r"\bholding\s+(his|her|their)\s+head\b",
        r"one sleeve-covered fist pressed to \1 temple, hunched shoulders, anxious three-quarter upper-body pose",
    ),
    (
        r"\bclutching\s+(his|her|their)\s+head\b",
        r"one sleeve-covered fist pressed to \1 temple, hunched shoulders, anxious three-quarter upper-body pose",
    ),
    (
        r"\bholding\s+(?!hands\b)([^,.;]+)",
        r"holding \1 with small sleeve-covered functional grips",
    ),
    (
        r"\bgripping\s+([^,.;]+)",
        r"gripping \1 with one small sleeve-covered functional grip",
    ),
    (
        r"\bgrabbing\s+([^,.;]+)",
        r"grabbing \1 with one small sleeve-covered functional grip",
    ),
    (r"\bpointing\s+at\s+([^,.;]+)", r"looking toward \1"),
    (r"\breaching\s+toward\s+([^,.;]+)", r"leaning toward \1"),
    (r"\bfaint\s+glow\s+between\s+fingertips\b", "faint glow between two floating abstract symbols"),
    (r"\bglow\s+between\s+fingertips\b", "glow between two floating abstract symbols"),
    (r"\bbetween\s+fingertips\b", "between two floating abstract symbols"),
    (r"\bfingertips?\b", "small arm gesture"),
    (r"\bfingers?\b", "small arm gesture"),
    (r"\bclose-up\s+of\s+(?:a\s+)?hands?\b", "close-up of a symbolic object"),
    (r"\bforeground\s+hands?\b", "foreground symbolic objects"),
    (r"\bclose-up\s+hands?\b", "close-up of the main object"),
    (r"\bclose-up\s+of\s+(?:wrinkled|old|elderly|human)\s+hands?\b", "close-up of the main object"),
    (r"\b(?:wrinkled|old|elderly|human|visible|detailed|foreground)\s+hands?\b", "sleeve-covered arm gesture"),
    (r"(?<!holding\s)(?<!joined\s)(?<!clasping\s)\bhands?\b", "sleeve-covered arm gesture"),
    (r"\bpalms?\b", "sleeve-covered arm gesture"),
    (r"\bknuckles?\b", "sleeve-covered arm gesture"),
]

_ANATOMY_RISK_IMAGE_PATTERNS = [
    (r"\bclose-up\s+of\s+(?:a\s+)?(?:leg|legs|foot|feet|paw|paws|hoof|hooves)\b", "medium shot of the full subject"),
    (r"\bforeground\s+(?:leg|legs|foot|feet|paw|paws|hoof|hooves)\b", "full subject visible in the foreground"),
    (r"\bcropped\s+(?:body|person|animal|dog|cat|horse)\b", "complete subject fully inside the frame"),
    (r"\bpartial\s+(?:body|person|animal|dog|cat|horse)\b", "complete subject fully inside the frame"),
    (r"\bcut\s*off\s+(?:body|limbs?|legs?|arms?|paws?)\b", "complete subject fully inside the frame"),
    (r"\bdetached\s+(?:limbs?|legs?|arms?|hands?|paws?)\b", "all limbs attached to the correct body"),
    (r"\bfloating\s+(?:limbs?|legs?|arms?|hands?|paws?)\b", "all limbs attached to the correct body"),
    (r"\bfused\s+(?:bodies|people|animals|limbs?|legs?|arms?|hands?|paws?)\b", "separated bodies with clear silhouettes"),
    (r"\boverlapping\b", "standing apart"),
    (r"\ba\s+pack\s+of\s+dogs\b", "two separated side-view dogs"),
    (r"\bpack\s+of\s+dogs\b", "two separated side-view dogs"),
    (r"\bdog\s+running\b", "side-view dog walking with all four paws visible"),
    (r"\bdog\s+jumping\b", "side-view dog standing with all four paws visible"),
    (r"\bhorse\s+galloping\b", "side-view horse walking with all four legs visible"),
    (r"\bcat\s+jumping\b", "side-view cat standing with all four paws visible"),
]

_PHYSICS_RISK_IMAGE_PATTERNS = [
    (
        r"\b(?:person|people|man|woman|child|figure|character|soldier|worker|farmer|monk|noble|samurai)\s+standing\s+on\s+(?:the\s+)?water\b",
        "person standing on a visible wooden dock beside the water",
    ),
    (
        r"\b(?:person|people|man|woman|child|figure|character|soldier|worker|farmer|monk|noble|samurai)\s+walking\s+on\s+(?:the\s+)?water\b",
        "person walking along the shoreline beside the water",
    ),
    (
        r"\b(?:standing|walking)\s+on\s+(?:the\s+)?water\b",
        "standing on visible solid ground beside the water",
    ),
    (
        r"\bon\s+the\s+surface\s+of\s+(?:the\s+)?water\b",
        "on a visible wooden dock beside the water",
    ),
    (
        r"\bmiddle\s+of\s+(?:a\s+)?river\b",
        "riverbank beside the river",
    ),
    (
        r"\bmiddle\s+of\s+(?:a\s+)?lake\b",
        "shoreline beside the lake",
    ),
    (
        r"\b(?:person|people|man|woman|child|figure|character)\s+in\s+(?:a\s+)?boat\b",
        "person seated inside a boat with the boat hull clearly visible",
    ),
    (
        r"\b(?:floating|hovering)\s+(?:bowl|plate|cup|book|scroll|box|object|tool|weapon|sword|lantern|document)s?\b",
        "object resting firmly on a visible table or ground surface",
    ),
    (
        r"\b(?:bowl|plate|cup|book|scroll|box|object|tool|weapon|sword|lantern|document)s?\s+(?:floating|hovering)\b",
        "object resting firmly on a visible table or ground surface",
    ),
    (
        r"\bfood\s+floating\b",
        "food placed clearly on a plate or inside a bowl",
    ),
    (
        r"\bobjects?\s+floating\s+in\s+the\s+air\b",
        "objects resting on visible shelves, tables, or ground surfaces",
    ),
    (
        r"\bin\s+midair\b",
        "resting on a visible physical support",
    ),
    (
        r"\bfull\s+meal\s+of\s+rice,\s*miso\s+soup,\s*grilled\s+fish,\s*and\s*pickles\b",
        "full meal with separate visible dishes: rice bowl, miso soup bowl, grilled fish plate, and pickle dish",
    ),
    (
        r"\brice,\s*miso\s+soup,\s*grilled\s+fish,\s*and\s*pickles\b",
        "separate visible dishes of rice, miso soup, grilled fish, and pickles",
    ),
]


def _sanitize_i2v_source_prompt(text: str) -> str:
    """Remove still-image cues that Hunyuan I2V tends to turn into ghost trails."""
    out = text or ""
    for pattern, replacement in _VIDEO_UNFRIENDLY_IMAGE_PATTERNS:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", out).strip()


def _sanitize_hand_risky_prompt(text: str) -> tuple[str, bool]:
    """Avoid foreground hand anatomy, which SDXL local models often deform."""
    out = text or ""
    had_hand_risk = bool(_HAND_ANATOMY_RE.search(out) or _HAND_ACTION_RE.search(out))
    for pattern, replacement in _HAND_RISK_IMAGE_PATTERNS:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    out = re.sub(
        r"(?:exactly four short rounded cartoon\s+){2,}fingers",
        "simple sleeve-covered arm gesture",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"(?:four simple rounded|exactly four short rounded cartoon) (?:simple rounded shapes|four simple rounded fingers|exactly four short rounded cartoon fingers)",
        "simple sleeve-covered arm gesture",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"(?:tiny\s+)?four-lobed\s+mitten\s+hands(?:,\s*(?:tiny\s+)?four-lobed\s+mitten\s+hands)+",
        "simple sleeve-covered arm gesture",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out, had_hand_risk


def _sanitize_anatomy_risky_prompt(text: str) -> tuple[str, dict[str, bool]]:
    """Normalize high-risk anatomy compositions before they reach the image model."""
    out = text or ""
    flags = {
        "human": bool(_HUMAN_SUBJECT_RE.search(out)),
        "quadruped": bool(_QUADRUPED_SUBJECT_RE.search(out)),
        "crop": bool(_CROP_RISK_RE.search(out)),
    }
    for pattern, replacement in _ANATOMY_RISK_IMAGE_PATTERNS:
        if re.search(pattern, out, flags=re.IGNORECASE):
            flags["crop"] = True
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out, flags


def _sanitize_physics_risky_prompt(text: str) -> str:
    """Keep SDXL scenes physically grounded without adding negative prompt tokens."""
    out = text or ""
    for pattern, replacement in _PHYSICS_RISK_IMAGE_PATTERNS:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    out = re.sub(r"\bin\s+the\s+riverbank\b", "on the riverbank", out, flags=re.IGNORECASE)
    out = re.sub(r"\bin\s+the\s+shoreline\b", "on the shoreline", out, flags=re.IGNORECASE)
    out = re.sub(r"\bin\s+the\s+air\b", "on a visible table or ground surface", out, flags=re.IGNORECASE)
    out = re.sub(r"\bstanding\s+apart\s+people\b", "people standing apart", out, flags=re.IGNORECASE)
    out = re.sub(r"\bseparated\s+people\s+with\s+clear\s+space\s+between\s+their\s+silhouettes\s+people\b", "separated people with clear space between their silhouettes", out, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", out).strip()


def _build_anatomy_suffix(base: str, anatomy_flags: dict[str, bool], had_hand_risk: bool) -> str:
    suffix = I2V_SAFE_STILL_DIRECTIVE + ANATOMY_SAFE_DIRECTIVE
    if anatomy_flags.get("human"):
        suffix += HUMAN_ANATOMY_DIRECTIVE
    if anatomy_flags.get("quadruped"):
        suffix += QUADRUPED_ANATOMY_DIRECTIVE
    if had_hand_risk:
        suffix += HAND_SAFE_DIRECTIVE
    if anatomy_flags.get("crop"):
        suffix += LIMB_FRAME_SAFE_DIRECTIVE
    if anatomy_flags.get("human"):
        suffix += CARTOON_FACELESS_DIRECTIVE
    return suffix


def _append_no_text(prompt: str) -> str:
    """프롬프트 앞쪽에 표면 잠금을 중복 없이 부착."""
    p = _sanitize_flag_motif_positive_prompt(prompt or "")
    if not p:
        return p
    if "TEXT-FREE SURFACE LOCK" in p or "UNMARKED SURFACE LOCK" in p or "readable glyph-free image" in p:
        return p
    lock = _no_text_directive_for_prompt(p)
    lock = re.sub(r"^\|\|\s*", "", lock).strip()
    if p.startswith(REFERENCE_STYLE_PREFIX):
        rest = p[len(REFERENCE_STYLE_PREFIX):].lstrip()
        return REFERENCE_STYLE_PREFIX + lock + " || " + rest
    if " || " in p and re.match(r"^(?:HARD\s+HISTORICAL|HARD\s+PERIOD|★\s*STYLE)", p, re.IGNORECASE):
        head, rest = p.split(" || ", 1)
        if rest.startswith("PRIMARY IMAGE LOCK") and _scene_requests_achaemenid_egyptian_armed_group(p):
            primary, sep, remainder = rest.partition(" || ")
            if sep:
                return head + " || " + primary + " || " + lock + " || " + remainder
            return head + " || " + primary + " || " + lock
        return head + " || " + lock + " || " + rest
    return lock + " || " + p


def _no_text_directive_for_prompt(prompt: str) -> str:
    if (
        _scene_requests_map_object(prompt)
        or _scene_requests_planning_board_object(prompt)
        or _scene_requests_generic_object_evidence(prompt)
    ):
        return OBJECT_EVIDENCE_NO_TEXT_DIRECTIVE.strip()
    lock = NO_TEXT_DIRECTIVE.strip()
    if not re.search(
        r"\b(?:armor|armour|armored|armoured|lamellar|mail|cuirass|breastplate)\b|갑옷|鎧|具足",
        prompt or "",
        re.IGNORECASE,
    ):
        lock = lock.replace(
            "wall hangings, banners, flags, armor surfaces",
            "wall hangings, banners, flags",
        )
    return lock


def _append_no_maps(prompt: str) -> str:
    p = (prompt or "").strip()
    if not p:
        return p
    scene = _scene_text(p)
    asks_for_map = _scene_requests_map_object(p)
    if _scene_requests_group_planning_surface(p):
        return p
    if asks_for_map:
        if "UNMARKED STRATEGIC MAP LOCK" in p or "UNMARKED STRATEGIC BOARD LOCK" in p:
            return p
        return p + MAP_SCENE_DIRECTIVE
    if not re.search(
        r"\b(territory|border|route|migration|kingdoms?|expansion|expanding|geography|"
        r"buyeo\s+expanding)\b|지도|영토|국경|경계|이동로|확장|팽창|지리",
        scene,
        re.IGNORECASE,
    ):
        return p
    if "HUMAN-SCALE GEOGRAPHY LOCK" in p:
        return p
    return p + NO_MAP_DIRECTIVE


def _prompt_field(prompt: str, label: str) -> str:
    key = label.lower()
    pattern = _PROMPT_FIELD_RE_CACHE.get(key)
    if pattern is None:
        pattern = re.compile(
            rf"(?:^|;\s*|\|\|\s*){re.escape(label)}\s*:\s*(.*?)(?=;\s*(?:Year/period|Exact place|Scene evidence|Style|Main subject|Scene)\s*:|\s+\|\|\s+|$)",
            re.IGNORECASE | re.DOTALL,
        )
        _PROMPT_FIELD_RE_CACHE[key] = pattern
    match = pattern.search(prompt or "")
    if not match:
        return ""
    value = re.split(r"\s+\|\|\s+", match.group(1), maxsplit=1)[0]
    value = re.split(
        r";\s*NARRATION\s+VISUAL\s+ALIGNMENT\s*:",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    value = re.split(
        r"\s+Apply\s+this\s+as\s+rendering\s+style\s+only\b",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return _clean_prompt_commas(value)


def _replace_prompt_field(prompt: str, label: str, value: str) -> str:
    pattern = _PROMPT_FIELD_RE_CACHE.get(f"replace:{label.lower()}")
    if pattern is None:
        pattern = re.compile(
            rf"((?:^|;\s*){re.escape(label)}\s*:\s*)(.*?)(?=;\s*(?:Year/period|Exact place|Scene evidence|Style|Main subject|Scene)\s*:|$)",
            re.IGNORECASE | re.DOTALL,
        )
        _PROMPT_FIELD_RE_CACHE[f"replace:{label.lower()}"] = pattern
    if not pattern.search(prompt or ""):
        return prompt or ""
    return pattern.sub(lambda match: match.group(1) + value.strip(), prompt or "", count=1)


def _depicted_surface_material_scene_text(text: str) -> str:
    raw = _clean_prompt_commas(text or "")
    if not raw:
        return raw
    depiction_match = _DEPICTION_VERB_RE.search(raw)
    if not depiction_match or not _VISUAL_SURFACE_OBJECT_RE.search(raw):
        return raw
    prefix = raw[: depiction_match.start()].rstrip(" ,;")
    suffix = raw[depiction_match.end() :]
    clause_start = -1
    for marker in (" with ", " bearing ", " containing ", " covered with ", " covered in "):
        pos = prefix.lower().rfind(marker)
        if pos > clause_start:
            clause_start = pos
    if clause_start >= 0:
        prefix = prefix[:clause_start].rstrip(" ,;")
    suffix_after_clause = ""
    comma = suffix.find(",")
    if comma >= 0:
        suffix_after_clause = suffix[comma + 1 :].strip(" ,;")
    if _BOOK_OBJECT_RE.search(raw):
        material_subject = (
            "physical cream paper evidence as the dominant foreground object, "
            "rolled or folded material, cord "
            "ties, edge thickness, paper grain, dust, candlelight, and worn "
            "surface texture"
        )
    else:
        material_subject = (
            "physical visual-surface evidence as the dominant foreground object, "
            "flat plaster, stone, clay, pigment, carved depth, edge wear, dust, "
            "light, and worn material texture"
        )
    parts = [part for part in (prefix, material_subject, suffix_after_clause) if part]
    return _clean_prompt_commas(", ".join(parts))


def _normalize_visual_surface_depiction_language(prompt: str) -> str:
    p = prompt or ""
    if not _scene_is_depicted_people_on_object_without_living_people(p):
        return p
    scene = _prompt_field(p, "Scene")
    if scene:
        p = _replace_prompt_field(p, "Scene", _depicted_surface_material_scene_text(scene))
    subject = _prompt_field(p, "Main subject")
    if subject:
        p = _replace_prompt_field(p, "Main subject", _depicted_surface_material_scene_text(subject))
    return _clean_prompt_commas(p)


def _scene_is_depicted_surface_evidence_object(prompt: str) -> bool:
    scene = _scene_text(prompt or "")
    return bool(
        re.search(
            r"\bphysical\s+(?:cream\s+paper|visual-surface)\s+evidence\b",
            scene,
            re.IGNORECASE,
        )
    )


def _strip_unreliable_main_subject(prompt: str) -> str:
    """Drop non-English/global Main subject labels before image generation."""
    p = prompt or ""
    subject = _prompt_field(p, "Main subject")
    if not subject:
        return p
    if re.search(r"[가-힣]", subject):
        return re.sub(
            r"(?:^|;\s*)Main subject\s*:\s*.*?(?=;\s*(?:Year/period|Exact place|Scene evidence|Style|Scene)\s*:|$)",
            "; ",
            p,
            flags=re.IGNORECASE | re.DOTALL,
        ).strip(" ;")
    return p


def _strip_background_shopping_lists(prompt: str) -> str:
    """Keep era context without turning background material lists into subjects."""
    p = prompt or ""
    p = _BACKGROUND_SHOPPING_LIST_FIELD_RE.sub("; ", p)
    p = _CONTINUITY_RULE_FIELD_RE.sub(
        "; Continuity rule: consistent period-correct local setting, blank unmarked surfaces",
        p,
    )
    p = re.sub(
        r"Global\s+visual\s+world\s*:\s*",
        "Historical visual context: ",
        p,
        count=1,
        flags=re.IGNORECASE,
    )
    p = re.sub(
        r"\bpolitical\s+and\s+military\s+world\b",
        "local historical setting",
        p,
        flags=re.IGNORECASE,
    )
    p = re.sub(
        r"\bmilitary\s+world\b",
        "historical setting",
        p,
        flags=re.IGNORECASE,
    )
    p = re.sub(r";\s*;\s*", "; ", p)
    return _clean_prompt_commas(p)


def _normalize_text_prone_surface_terms(prompt: str) -> str:
    """Rewrite text-prone props as blank material surfaces in the positive prompt."""
    p = prompt or ""
    replacements = (
        (r"\bblank\s+(?:war\s+)?banners\b", "blank cloth military banners"),
        (r"\bblank\s+(?:war\s+)?banner\b", "blank cloth military banner"),
        (r"\b(?:warrior|war|military|army|battle)\s+banners\b", "blank cloth military banners"),
        (r"\b(?:warrior|war|military|army|battle)\s+banner\b", "blank cloth military banner"),
        (r"\bbanners\b", "blank cloth military banners"),
        (r"\bbanner\b", "blank cloth military banner"),
        (r"\bblank\s+flags\b", "blank cloth flags"),
        (r"\bblank\s+flag\b", "blank cloth flag"),
        (r"\bflags\b", "blank cloth flags"),
        (r"\bflag\b", "blank cloth flag"),
        (r"\bgate\s+signboards?\b", "plain uninterrupted wooden gate lintels"),
        (r"\bgate\s+plaques?\b", "plain uninterrupted wooden gate lintels"),
        (r"\bsignboards?\b", "plain uninterrupted structural material surfaces"),
        (r"\bwall\s+plaques?\b", "irregular plaster or wood-grain wall stains"),
        (r"\bblank\s+scrolls?\b", "rolled blank cream paper bundles"),
        (r"\bscrolls?\b", "rolled blank cream paper bundles"),
        (r"\bpetitions?\b", "cord-tied closed cream bundles held edge-on"),
        (r"\bdocuments?\b", "cord-tied closed cream bundles held edge-on"),
        (r"\bsealed\s+blank\s+decrees?\b", "short sealed cord-tied cream roll cylinder held between both hands"),
        (r"\bdecrees?\b", "short sealed cord-tied cream roll cylinder held between both hands"),
        (r"\bletters?\b", "short sealed cord-tied cream roll cylinder held between both hands"),
        (r"\bpages?\b", "cord-tied closed cream bundle edges"),
    )
    for pattern, replacement in replacements:
        p = re.sub(pattern, replacement, p, flags=re.IGNORECASE)
    return _clean_prompt_commas(p)


def _normalize_historical_tally_scene_language(prompt: str) -> str:
    """Avoid text-prone tally boards by preferring physical count evidence."""
    p = prompt or ""
    scene = _scene_text(p)
    if not scene or not re.search(
        r"\b(scribe|record|records|register|roster|tax\s+register|ledger|"
        r"tally|tallies|tally\s+board|tally\s+mat|survey\s+results?|"
        r"land\s+capacity|military\s+obligation|account|accounting)\b|"
        r"(서기|기록|장부|명부|호적|조사|측량|군역|세금|계수)",
        scene,
        re.IGNORECASE,
    ):
        return p
    replacements = (
        (
            r"\bA\s+scribe\s+marks\s+a\s+blank\s+tally\s+board\b",
            "A scribe arranges plain notched wooden tally sticks, cord knots, and pebble counters on a rough blank counting mat",
        ),
        (
            r"\bmarks\s+a\s+blank\s+tally\s+board\b",
            "arranges plain notched wooden tally sticks, cord knots, and pebble counters on a rough blank counting mat",
        ),
        (
            r"\bblank\s+tally\s+boards?\b",
            "plain notched wooden tally sticks, cord knots, and pebble counters",
        ),
        (
            r"\btally\s+boards?\b",
            "plain notched wooden tally sticks, cord knots, and pebble counters",
        ),
        (
            r"\bfield-side\s+writing\s+mat\b",
            "field-side rough counting mat with notched wooden tally sticks, cord knots, and pebble counters",
        ),
        (
            r"\bscribe\s+recording\s+survey\s+results\b",
            "scribe arranging physical tally counters for survey results",
        ),
    )
    for pattern, replacement in replacements:
        p = re.sub(pattern, replacement, p, flags=re.IGNORECASE)
    return _clean_prompt_commas(p)


_NEGATIVE_INSTRUCTION_FIELD_RE = re.compile(
    r"(?:^|;\s*)(?:Avoid|Forbidden|Exclude)\s*:\s*.*?"
    r"(?=;\s*(?:Global visual world|Time range|Place scope|Culture scope|"
    r"Material culture|Continuity rule|Year/period|Exact place|Scene evidence|"
    r"Style|Main subject|Scene|Composition)\s*:|$)",
    re.IGNORECASE | re.DOTALL,
)


def _strip_negative_instruction_fields(prompt: str) -> str:
    p = _NEGATIVE_INSTRUCTION_FIELD_RE.sub("; ", prompt or "")
    p = re.sub(
        r"\bComposition\s*:\s*cinematic\s+historical\s+documentary,\s*"
        r"grounded\s+realistic\s+composition,\s*",
        "Composition: cinematic illustrated documentary, grounded period illustration, ",
        p,
        flags=re.IGNORECASE,
    )
    p = re.sub(
        r"\bgrounded\s+realistic\s+composition\b",
        "grounded period illustration",
        p,
        flags=re.IGNORECASE,
    )
    p = re.sub(r";\s*;\s*", "; ", p)
    return _clean_prompt_commas(p.strip(" ;"))


def _normalize_early_goguryeo_scene_terms(prompt: str) -> str:
    p = prompt or ""
    if not _needs_early_goguryeo_frontier_guard(p):
        return p
    replacements = [
        (
            r"\bleather\s+armor,\s*lamellar\s+armor\b",
            "dark leather lamellar cuirasses over layered hemp tunics",
        ),
        (
            r"\bleather\s+or\s+lamellar\s+armor\b",
            "dark leather lamellar cuirasses over layered hemp tunics",
        ),
        (
            r"\bheavy\s+iron\s+armor\b",
            "dark leather lamellar cuirass over layered hemp tunic and coarse cloak",
        ),
        (
            r"\b((?:king|queen|prince|princess)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*,\s*an\s+arrogant\s+warlord\s+in\s+dark\s+leather\s+lamellar\s+(?:vest|cuirass)\s+over\s+layered\s+hemp\s+tunic\s+and\s+coarse\s+cloak\b",
            r"\1, stern local ruler with visible natural hairline, tied hair behind the head, coarse cloak over dark leather lamellar cuirass, arrogant eyes",
        ),
        (
            r"\b((?:king|queen|prince|princess)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*,\s*an\s+arrogant\s+warlord\b",
            r"\1, stern local ruler with visible natural hairline, tied hair behind the head, coarse cloak over dark leather lamellar cuirass, arrogant eyes",
        ),
        (
            r"\bwarlord\b",
            "local ruler",
        ),
        (
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+looking\s+down\s+mockingly\s+from\s+(?:his|her|their)\s+high\s+throne\b",
            r"\1 stern local ruler in a medium three-quarter story frame on a low timber platform, arrogant eyes, visible natural hairline, simple tied hair behind the head, coarse cloak over dark leather lamellar cuirass, platform edge and hall shadow visible",
        ),
        (
            r"\b((?:King|Queen|Prince|Princess|Emperor|Empress)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+looking\s+up\s+at\s+(?:the\s+)?high\s+throne\b",
            r"\1 in a medium three-quarter story frame looking upward under a heavy roof shadow, anxious eyes, visible natural hairline, simple tied hair behind the head, coarse cloak over dark leather lamellar cuirass, low timber platform shadow visible above",
        ),
        (
            r"\b(?:the\s+)?((?:First|Second)\s+Queen|Queen)\s+glaring\s+furiously\s+down\s+from\s+(?:a\s+)?high\s+balcony\s+at\s+([^,.;]+)\s+below\b",
            r"\1 medium three-quarter story frame with furious eyes and tense jaw at a low timber railing, \2 visible below in the same courtyard, diagonal balcony-to-courtyard tension",
        ),
        (
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+pointing\s+(?:his|her|their)\s+sword\s+down\s+aggressively\b",
            r"\1 stern local ruler in a medium three-quarter action frame, aggressive eyes, visible natural hairline, simple tied hair behind the head, coarse cloak over dark leather lamellar cuirass, one forceful arm pointing a short period sword downward",
        ),
        (
            r"\bempty\s+treasure\s+chests\s+in\s+a\s+muddy\s+military\s+camp\b",
            "empty rough wooden storage boxes and bare leather pouches on muddy packed earth inside a poor frontier camp",
        ),
        (
            r"\bwooden\s+halls?\b",
            "low timber longhouses",
        ),
        (
            r"\bfortress\s+walls?\b",
            "packed-earth ramparts and timber palisades",
        ),
        (
            r"\bfortress\b",
            "packed-earth rampart and timber palisade",
        ),
        (
            r"\bpalace\b",
            "low timber hall",
        ),
        (
            r"\bhigh\s+throne\b",
            "low timber platform",
        ),
        (
            r"\bthrone\b",
            "low timber platform",
        ),
    ]
    for pattern, replacement in replacements:
        p = re.sub(pattern, replacement, p, flags=re.IGNORECASE)
    p = re.sub(r";\s*;\s*", "; ", p)
    return _clean_prompt_commas(p)


def _needs_early_goguryeo_frontier_guard(prompt: str) -> bool:
    p = prompt or ""
    lower = p.lower()
    if _is_early_imperial_chinese_context(p):
        return False
    has_place = bool(
        re.search(
            r"\b(jolbon|goguryeo|koguryo|buyeo|nangnang|nakrang|lelang|"
            r"hwando|hwandoseong|sansang|balgi)\b|"
            r"졸본|고구려|부여|낙랑|환도성|산상왕|발기",
            p,
            re.IGNORECASE,
        )
    )
    has_early_period = bool(
        re.search(
            r"\b(?:37|1st)\s*(?:bce|bc)\b|기원전|mid\s+1st\s+century\s+bce|"
            r"\baround\s+(?:[1-9][0-9]?|[12][0-9]{2}|3[0-9]{2})\s+ce\b|"
            r"\b(?:[1-9][0-9]?|[12][0-9]{2}|3[0-9]{2})\s+ce\b|"
            r"\b(?:1st|2nd|3rd|4th)\s+century\s+ce\b|"
            r"서기\s*(?:[1-9][0-9]?|[12][0-9]{2}|3[0-9]{2})"
            r"(?:\s*[~\-–]\s*(?:[1-9][0-9]?|[12][0-9]{2}|3[0-9]{2}))?\s*년(?:경)?|"
            r"(?<!\d)(?:[1-9][0-9]?|[12][0-9]{2}|3[0-9]{2})"
            r"(?:\s*[~\-–]\s*(?:[1-9][0-9]?|[12][0-9]{2}|3[0-9]{2}))?\s*년경|"
            r"[1-4]\s*세기",
            lower,
        )
    )
    return has_place and has_early_period


def _is_goguryeo_silla_415_context(prompt: str) -> bool:
    p = prompt or ""
    if not re.search(r"고구려|goguryeo|koguryo", p, re.IGNORECASE):
        return False
    return bool(_GOGURYEO_SILLA_415_CONTEXT_RE.search(p))


def _scene_requests_hou_bowl_object(prompt: str) -> bool:
    p = prompt or ""
    scene = _scene_text(p)
    return bool(_HOU_BOWL_SCENE_RE.search(scene) or _HOU_BOWL_SCENE_RE.search(p))


def _append_early_goguryeo_frontier_guard(prompt: str) -> str:
    p = (prompt or "").strip()
    if not p or "EARLY GOGURYEO FRONTIER LOCK" in p:
        return p
    if "EARLY GOGURYEO ARTIFACT LOCK" in p:
        return p
    if not _needs_early_goguryeo_frontier_guard(p):
        return p
    scene = _scene_text(p)
    if _scene_requests_map_object(p):
        return p
    if re.search(
        r"\b(smooth undecorated bronze ring|plain bronze ring|flat circular bronze ring|sealed cord|"
        r"iron arrowheads|evidence still-life|broken sword|sword lying|blade lying|weapon lying)\b",
        p + " " + scene,
        re.IGNORECASE,
    ):
        return p + EARLY_GOGURYEO_ARTIFACT_DIRECTIVE
    if _scene_requests_armed_figures(p):
        out = p + EARLY_GOGURYEO_FRONTIER_DIRECTIVE
        if _scene_requests_armed_group_or_battle(out) and "ARMED GROUP STANDOFF COMPOSITION LOCK" not in out:
            out += ARMED_GROUP_STANDOFF_COMPOSITION_DIRECTIVE
        return out
    if re.search(r"\b(landscape|mountain|mountains|valley|field|fields|riverbank|riverbanks|terrain)\b", scene, re.IGNORECASE):
        return p + EARLY_GOGURYEO_LANDSCAPE_DIRECTIVE
    if _scene_requests_civilian_work_or_camp(p):
        return p + EARLY_GOGURYEO_CIVILIAN_FRONTIER_DIRECTIVE
    if prompt_mentions_major_character(p):
        return p + EARLY_GOGURYEO_CHARACTER_DIRECTIVE
    if _scene_requests_non_armed_humans(p):
        return p + EARLY_GOGURYEO_CIVILIAN_FRONTIER_DIRECTIVE
    if not _scene_requests_humans(p):
        return p + EARLY_GOGURYEO_SETTING_DIRECTIVE
    return p + EARLY_GOGURYEO_FRONTIER_DIRECTIVE


def _strip_scene_evidence_character_metadata(prompt: str) -> str:
    """Remove cast-list metadata; visible people come from the Scene field."""
    def repl(match: re.Match) -> str:
        prefix = match.group(1)
        value = match.group(2)
        kept: list[str] = []
        for part in re.split(r"\s*;\s*", value):
            cleaned = part.strip()
            if not cleaned:
                continue
            if _SCENE_EVIDENCE_CHARACTER_LABEL_RE.search(cleaned):
                continue
            kept.append(cleaned)
        if not kept:
            return ""
        return prefix + "; ".join(kept)

    out = _SCENE_EVIDENCE_FIELD_RE.sub(repl, prompt or "")
    out = re.sub(r";\s*;\s*", "; ", out)
    return _clean_prompt_commas(out)


def _normalize_object_cut_scene_language(prompt: str) -> str:
    if _scene_requests_humans(prompt or "") and not _scene_requests_generic_object_evidence(prompt or ""):
        return prompt or ""
    out = prompt or ""
    if _is_historical_period_context(out):
        object_replacements = [
            (
                r"\b(?:a\s+)?heavy\s+gold\s+crown\s+resting\s+on\s+(?:a\s+)?velvet\s+pillow\s+stained\s+with\s+blood\b",
                "period-local ruler status diadem strip or open cloth-metal headband regalia laid flat in a shallow crescent arc on a blood-stained coarse local cloth pad over a low wooden support, two visible open ends, flattened metal band edge, low head-ornament profile, dark stains, metal or lacquer wear, dust, hard side light, no wearer, not a closed ring, not a bowl, not a basin, not a hollow dish, not a helmet dome, not a pot, not a top-down container, not a European fairy-tale crown, not a tall fantasy crown, no ball finials, no velvet",
            ),
            (
                r"\b(?:ancient\s+)?history\s+book\b",
                "closed unmarked period record bundle or book-like document object resting on a visible local support surface, worn cover, cord binding, dust, faint dark stains, hard side light",
            ),
            (
                r"\b(?:a\s+)?torn\s+painting\s+revealing\s+([^,.;]+)",
                r"torn physical painting surface as the dominant foreground object, ripped material edge, worn pigment, dust, shadow, and \1 visible only as flat damaged pigment inside the painting surface",
            ),
            (
                r"\b(?:blood[-\s]*stained\s+)?(?:royal\s+)?crown\s+sitting\s+in\s+shadows\b",
                "head-worn period-local ruler status headpiece or crown-like circlet regalia resting alone in shadow on a visible local support surface, visible inner head opening sized for a human head, curved band silhouette, wearable lower rim, low head-ornament profile, dark stains, metal or lacquer wear, dust, hard side light, no wearer, not a bowl, not a bucket, not a pot, not a cup, not a cylindrical container",
            ),
            (
                r"\b(?:blood[-\s]*stained\s+)?(?:royal\s+)?crown(?!-like)\b",
                "head-worn period-local ruler status diadem strip or open cloth-metal headband regalia laid flat in a shallow crescent arc on a visible local support surface, two visible open ends, flattened metal band edge, low head-ornament profile, dark stains, metal or lacquer wear, dust, hard side light, no wearer, not a closed ring, not a bowl, not a basin, not a hollow dish, not a helmet dome, not a top-down container, not a European fairy-tale crown, not a tall fantasy crown, no ball finials, not a bucket, not a pot, not a cup, not a cylindrical container",
            ),
            (
                r"\bbroken\s+blade\s+(?:lying\s+)?on\s+(?:a\s+)?cold\s+stone\s+table\b",
                "broken blade sections resting flat on a cold stone table surface, visible blade edges, dull iron fracture, stone grain, dust, hard side light, no person",
            ),
            (
                r"\bbroken\s+blade\b(?!\s+sections)",
                "broken blade sections resting flat on a visible local support surface, dull iron fracture, dust, hard side light, no person",
            ),
            (
                r"\b(?:a\s+)?cracked\s+mirror\s+reflecting\s+([^,.;]+)",
                r"small round or oval period-local bronze mirror object resting on a low support surface as the dominant foreground object, visible metal rim, cracked reflective plane, dust, worn surface, hard side light, with \1 visible only as distorted reflection inside the mirror surface, no wall-mounted mirror, no rectangular picture frame, no live person, no real hand outside the mirror",
            ),
            (
                r"\b(?:a\s+)?mirror\s+reflecting\s+([^,.;]+)",
                r"small round or oval period-local bronze mirror object resting on a low support surface as the dominant foreground object, visible metal rim, reflective plane, dust, worn surface, hard side light, with \1 visible only as distorted reflection inside the mirror surface, no wall-mounted mirror, no rectangular picture frame, no live person, no real hand outside the mirror",
            ),
        ]
        for pattern, replacement in object_replacements:
            out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    if _needs_early_goguryeo_frontier_guard(out):
        early_document_replacements = [
            (
                r"\b(?:ancient\s+)?history\s+book\b",
                "dust-covered blank ancient record bundle or closed period document object resting on packed earth, unmarked cover, worn cord binding, dust, clay, and hard side light",
            ),
            (
                r"\b(?:ancient\s+)?(?:book|notebook|manuscript|codex|ledger|journal|scripture|archive\s+volume|page\s+spread|document)s?\b",
                "blank period document object resting on a visible table or packed-earth surface, unmarked pages or cover, cord binding, dust, and local material wear",
            ),
            (
                r"\b(?:ancient\s+)?map\s+of\s+goguryeo\b",
                "dark low horizontal tactile marker layout for Goguryeo on a low wooden table, loose route cords, separated small stones, bronze weights, dust, clay, and hard side light",
            ),
            (
                r"\b(?:ancient\s+)?maps?\b(?!\s+of\b)",
                "low horizontal tactile marker layout on a visible table, loose route cords, separated small stones, bronze weights, dust, clay, and hard side light",
            ),
        ]
        for pattern, replacement in early_document_replacements:
            out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
        out = re.sub(r"\ban\s+close\b", "a close", out, flags=re.IGNORECASE)
    if _is_historical_period_context(out):
        out = re.sub(
            r"\b(?:golden\s+|bronze\s+|brass\s+)?globe[-\s]+like\s+ornaments?\b",
            "smooth round gold or bronze authority ornament, plain spherical ritual object held or indicated by period-local hands, no cartographic surface, no latitude-longitude grid, no meridian rings, no armillary rings, no astronomical stand, no writing",
            out,
            flags=re.IGNORECASE,
        )
        out = re.sub(
            r"\b(?:spinning\s+)?(?:ancient\s+)?globes?\s+made\s+of\s+brass\s+and\s+wood,\s*focusing\s+on\s+([^,.;]+)",
            "round brass-and-wood cosmological globe or armillary sphere on a low wooden support, visible curved rim, spherical body, meridian ring, wooden stand, bronze bands, dust, and hard side light, focusing on \\1 as a worn pictorial surface without text",
            out,
            flags=re.IGNORECASE,
        )
        out = re.sub(
            r"\b(?:spinning\s+)?(?:ancient\s+)?globes?\b(?![-\s]*(?:like|shaped)\s+ornaments?\b)",
            "round brass-and-wood cosmological globe or armillary sphere on a low wooden support, visible curved rim, spherical body, meridian ring, wooden stand, bronze bands, dust, and hard side light",
            out,
            flags=re.IGNORECASE,
        )
    replacements = [
        (
            r"\bdark\s+ancient\s+korean\s+palace\b",
            "empty ancient Korean palace interior threshold with a wall-mounted wooden crossbar latch fixed to the inside face of the open door, empty worn stone floor in the foreground",
        ),
        (
            r"\bglowing\s+magical\s+egg\s+resting\s+on\s+a\s+silk\s+bed,\s*dark\s+room\b",
            "single uninterrupted full-frame scene, one camera viewpoint, chest-up close-up portrait of Yuhwa, an adult Buyeo noblewoman, anxious visible eyes, red silk robe, warm golden birth light rising from below the frame and illuminating her face, plain dark earthen room",
        ),
        (
            r"\bmassive\s+enigmatic\s+egg\s+wrapped\s+in\s+silk\b",
            "single uninterrupted full-frame scene, one camera viewpoint, chest-up close-up portrait of Yuhwa, an adult Buyeo noblewoman, anxious visible eyes, red silk robe, warm golden birth light rising from below the frame and illuminating her face, plain dark earthen room",
        ),
        (
            r"\bancient\s+map\s+of\s+([^,.;]+)",
            r"dark low horizontal tactile marker layout for \1 on a visible table with loose route cords, separated stone markers, bronze weights, dust, and hard side light",
        ),
        (
            r"\bmap\s+of\s+([^,.;]+)",
            r"low horizontal tactile marker layout for \1 on a visible table with loose route cords, separated stone markers, bronze weights, dust, and hard side light",
        ),
        (
            r"\bmaps?\b(?!\s+of\b)",
            "low horizontal tactile marker layout on a visible table with loose route cords, separated stone markers, bronze weights, dust, and hard side light",
        ),
        (
            r"\bvast\s+rugged\s+landscape\s+of\s+([^,.;]+),\s*dark\s+clouds\b",
            r"terrain-only rugged landscape evidence in \1, steep rocky slopes, wet stones, low grass, packed dirt path, dark clouds",
        ),
        (
            r"\bvast\s+rugged\s+landscape\b",
            "terrain-only rugged landscape evidence, steep rocky slopes, wet stones, low grass, packed dirt path",
        ),
        (
            r"\bshadows?\s+looming\b",
            "large geometric doorframe, pillar, and roof-beam shadows",
        ),
        (
            r"\blooming\s+shadows?\b",
            "large geometric doorframe, pillar, and roof-beam shadows",
        ),
        (
            r"\btense\s+atmosphere\b",
            "tense architectural silence",
        ),
    ]
    for pattern, replacement in replacements:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return _clean_prompt_commas(out)


def _normalize_map_nearby_human_pressure_scene(scene: str) -> str:
    cleaned = scene or ""
    replacements = [
        (
            r"\s+\bas\s+(?:armored\s+|unarmored\s+|court\s+|military\s+|civilian\s+)?"
            r"(?:retainers?|guards?|soldiers?|warriors?|officials?|courtiers?|nobles?|"
            r"advisers?|commanders?|people|men|women|figures)\b[^.;|]*",
            " with off-screen pressure shown only through lamp light, shadows, marker spacing, and disturbed dust",
        ),
        (
            r"\s+\bwhile\s+(?:armored\s+|unarmored\s+|court\s+|military\s+|civilian\s+)?"
            r"(?:retainers?|guards?|soldiers?|warriors?|officials?|courtiers?|nobles?|"
            r"advisers?|commanders?|people|men|women|figures)\b[^.;|]*",
            " with off-screen pressure shown only through lamp light, shadows, marker spacing, and disturbed dust",
        ),
    ]
    for pattern, replacement in replacements:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    return _clean_prompt_commas(cleaned)


def _normalize_map_object_language(prompt: str) -> str:
    """Turn text-prone map wording into physical board wording before rendering."""
    if not _scene_requests_map_object(prompt or ""):
        return prompt or ""
    out = prompt or ""
    replacements = [
        (
            r"\bblank\s+floor\s+maps?\b",
            "low horizontal tactile marker layout with loose route cords, separated stone markers, one bronze weight, broad diffuse dust, and empty unmarked material margins",
        ),
        (
            r"\b(?:plain\s+|blank\s+)?(?:field|land|land\s+guarantee|property)\s+diagram\b",
            "low horizontal tactile land-marker layout with loose route cords, separated stone markers, one bronze weight, broad diffuse dust, and empty unmarked material margins",
        ),
        (
            r"\bfloor\s+maps?\b",
            "low horizontal tactile marker layout with loose route cords, separated stone markers, one bronze weight, broad diffuse dust, and empty unmarked material margins",
        ),
        (
            r"\bancient\s+maps?\s+of\s+([^,.;]+)",
            r"low horizontal tactile marker layout for \1 with loose route cords, separated stone markers, one bronze weight, broad diffuse dust, and empty unmarked material margins",
        ),
        (
            r"\bmaps?\s+of\s+([^,.;]+)",
            r"low horizontal tactile marker layout for \1 with loose route cords, separated stone markers, one bronze weight, broad diffuse dust, and empty unmarked material margins",
        ),
        (
            r"\bancient\s+maps?\b",
            "low horizontal tactile marker layout with loose route cords, separated stone markers, one bronze weight, broad diffuse dust, and empty unmarked material margins",
        ),
        (
            r"\bmaps?\b",
            "low horizontal tactile marker layout with loose route cords, separated stone markers, one bronze weight, broad diffuse dust, and empty unmarked material margins",
        ),
    ]
    for pattern, replacement in replacements:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    scene = _prompt_field(out, "Scene")
    if scene:
        out = _replace_prompt_field(
            out,
            "Scene",
            _normalize_map_nearby_human_pressure_scene(scene),
        )
    return _clean_prompt_commas(out)


def _normalize_group_planning_surface_language(prompt: str) -> str:
    if not _scene_requests_group_planning_surface(prompt or ""):
        return prompt or ""
    p = prompt or ""
    p = re.sub(r"\bbrush documents without readable writing,\s*", "", p, flags=re.IGNORECASE)
    p = re.sub(r",\s*brush documents without readable writing\b", "", p, flags=re.IGNORECASE)
    scene = _prompt_field(p, "Scene")
    if not scene:
        return p
    scene = re.sub(
        r"\bblank\s+floor\s+plan\b",
        (
            "blank low horizontal planning surface with loose route cords "
            "crossing three separated marker clusters, at least seven separated "
            "stone markers, one palm-sized bronze weight or pin, "
            "low side candle or oil lamp light from table edge or floor edge, "
            "hand shadows, dust, and bare material margins"
        ),
        scene,
        flags=re.IGNORECASE,
    )
    scene = re.sub(
        r"\bfloor\s+plan\b",
        (
            "low horizontal planning surface with loose route cords crossing "
            "three separated marker clusters, separated stone markers, one "
            "palm-sized bronze weight or pin, low side candle or oil "
            "lamp light from table edge or floor edge, hand shadows, dust, and "
            "bare material margins"
        ),
        scene,
        flags=re.IGNORECASE,
    )
    scene = re.sub(r"\bcandlelit\b", "low side candle-lit", scene, flags=re.IGNORECASE)
    scene = re.sub(r"\blamplit\b", "low side oil-lamp-lit", scene, flags=re.IGNORECASE)
    if re.search(r"\b(planning\s+surface|floor\s+plan|marker\s+clusters?|stone\s+markers?|route\s+cords?)\b", scene, re.IGNORECASE):
        scene = (
            "Steep top-down tabletop evidence crop of a blank low horizontal "
            "planning surface with loose route cords crossing three separated "
            "marker clusters, at least seven separated stone markers, one "
            "palm-sized bronze weight or pin, low side candle or oil lamp "
            "light from the surface edge, hand shadows, dust, and bare "
            "material margins; only cropped hands, fingertips, sleeves, "
            "forearm edges, and shadows touch the surface border; the camera "
            "sees only the horizontal planning surface plane and movable "
            "marker objects"
        )
    return _replace_prompt_field(p, "Scene", _clean_prompt_commas(scene))


_PREINDUSTRIAL_LIGHT_SOURCE_RE = re.compile(
    r"\b(lamp|lamps|lantern|lanterns|candle|candles|torch|torches|brazier|braziers|flame|firelight)\b",
    re.IGNORECASE,
)


def _scene_requests_preindustrial_light_source(prompt: str) -> bool:
    return bool(_PREINDUSTRIAL_LIGHT_SOURCE_RE.search(_scene_text(prompt or "")))


def _scene_requests_low_lamp_armed_entry(prompt: str) -> bool:
    scene = _scene_text(prompt or "")
    if not scene:
        return False
    has_light = bool(_PREINDUSTRIAL_LIGHT_SOURCE_RE.search(scene))
    has_armed_role = bool(
        re.search(
            r"\b(armed\s+escorts?|escorts?|guards?|soldiers?|warriors?|retainers?)\b|"
            r"(호위|무사|전사|병사)",
            scene,
            re.IGNORECASE,
        )
    )
    has_entry_motion = bool(
        re.search(
            r"\b(climb|climbs|climbing|enter|enters|entering|arrive|arrives|"
            r"arriving|approach|approaches|approaching|come|comes|coming|"
            r"emerge|emerges|emerging|from\s+the\s+dark|from\s+the\s+valley|"
            r"from\s+outside|through\s+the\s+door|through\s+the\s+doorway)\b|"
            r"(오르|올라|들어오|다가오|나오|문으로|계곡에서)",
            scene,
            re.IGNORECASE,
        )
    )
    has_listening_tension = bool(
        re.search(
            r"\b(listen|listens|listening|distant\s+hooves?|hoofbeats?|"
            r"night\s+watch|keeps?\s+watch|watching|hears?)\b|"
            r"(듣|말발굽|야간\s*경계|경계)",
            scene,
            re.IGNORECASE,
        )
    )
    return bool(has_light and has_armed_role and (has_entry_motion or has_listening_tension))


def _normalize_preindustrial_light_scene_language(prompt: str) -> str:
    p = prompt or ""
    if _scene_requests_group_planning_surface(p):
        return p
    if _is_modern_context(p) or not _is_preindustrial_historical_context(p):
        return p
    scene = _prompt_field(p, "Scene")
    if not scene or not _PREINDUSTRIAL_LIGHT_SOURCE_RE.search(scene):
        return p
    replacements = [
        (
            r"\b(?:a\s+|one\s+|single\s+|the\s+)?(?:small\s+|dim\s+|court\s+)?lamps?\s+glows?\b",
            "one low floor or table oil lamp glows below shoulder height at the lower side of the frame",
        ),
        (
            r"\b(?:a\s+|one\s+|single\s+|the\s+)?(?:small\s+|dim\s+|court\s+)?lanterns?\s+glows?\b",
            "one small hand-carried or doorway-side lantern glows below shoulder height at the lower side of the frame",
        ),
        (
            r"\blamplit\b",
            "low side oil-lamp-lit",
        ),
        (
            r"\bcandlelit\b",
            "low side candle-lit",
        ),
    ]
    for pattern, replacement in replacements:
        scene = re.sub(pattern, replacement, scene, flags=re.IGNORECASE)
    if "below shoulder height" not in scene.lower():
        scene = (
            f"{scene}, with the visible flame source at a low table edge, floor edge, "
            "doorway sill, hand height, or low stand below shoulder height; upper "
            "rafters and blank plaster bays remain unbroken dark material"
        )
    return _replace_prompt_field(p, "Scene", _clean_prompt_commas(scene))


def _normalize_historical_symbolic_modern_object_language(prompt: str) -> str:
    p = prompt or ""
    if _is_modern_context(p) or not _is_preindustrial_historical_context(p):
        return p
    scene = _prompt_field(p, "Scene")
    if not scene:
        return p
    original_scene = scene
    replacements = [
        (
            r"\ba\s+split\s+screen\s+showing\s+the\s+ancient\s+arsonist\s+with\s+a\s+torch,\s*and\s+a\s+modern\s+troll\s+with\s+a\s+smartphone\b",
            "a single ancient-period scene showing a torch-bearing arsonist confronted by a hostile robed bystander pointing accusingly, no device",
        ),
        (
            r"\ba\s+person\s+casually\s+knocking\s+over\s+a\s+beautiful\s+display\s+in\s+a\s+store\b",
            "a full-frame top-down tabletop action crop: only robed historical hands knocking over unmarked clay and bronze ritual objects on a low wooden table, no faces, no wall, no doorway, no wall sign, no overhead beam",
        ),
        (
            r"\bholding\s+a\s+camera\s+to\s+record\s+the\s+damage\b",
            "watched by robed witnesses pointing at the damage with empty hands",
        ),
        (
            r"\bcamera\s+to\s+record\s+the\s+damage\b",
            "robed witnesses pointing at the damage",
        ),
        (
            r"\bmodern\s+troll\s+with\s+a\s+smartphone\b",
            "hostile robed bystander pointing accusingly, no device",
        ),
        (
            r"\bmodern\s+troll\b",
            "hostile robed bystander",
        ),
        (
            r"\bsmartphone\b",
            "empty hand raised in accusation",
        ),
        (
            r"\bbeautiful\s+display\b",
            "unmarked ritual display table",
        ),
        (
            r"\bstore\b",
            "period-local stall table cropped below the roofline with no doorway or sign",
        ),
        (
            r"\ban\s+hourglass\s+with\s+golden\s+sand\s+flowing\s+incredibly\s+fast,\s*destroying\s+a\s+miniature\s+temple\s+at\s+the\s+bottom\b",
            "golden dust and water spilling from an ancient clay water-clock vessel across a small broken clay temple model under a sundial shadow",
        ),
        (
            r"\bhourglass\s+slowly\s+draining,\s*transitioning\s+into\s+a\s+modern\s+clock\b",
            "unlabeled earthen clepsydra water-clock vessel beside a sharp sundial shadow, with golden sand-like grains or dust flowing across a dark wooden tabletop",
        ),
        (
            r"\bhourglass\s+[^,.;]{0,80}\btransitioning\s+into\s+a\s+modern\s+clock\b",
            "unlabeled earthen clepsydra water-clock vessel beside a sharp sundial shadow, with golden sand-like grains or dust flowing across a dark wooden tabletop",
        ),
        (
            r"\btransitioning\s+into\s+a\s+modern\s+clock\b",
            "shown through a sharp sundial shadow and an unlabeled earthen clepsydra water-clock vessel with golden dust",
        ),
        (
            r"\bmodern\s+clock\s+face\b",
            "period-appropriate sundial shadow",
        ),
        (
            r"\bmodern\s+clock\b",
            "period-appropriate sundial shadow or ancient water-clock vessel",
        ),
        (
            r"\bhourglass\b",
            "ancient water-clock vessel and sundial shadow",
        ),
        (
            r"\bstylized\s+3D\s+thumbs[-\s]?up\s+icon\s+made\s+of\s+ancient\s+gold\b",
            "period-appropriate bronze approval token embossed with a simple raised-hand relief on a dark wooden tabletop",
        ),
        (
            r"\b3D\s+thumbs[-\s]?up\s+icon\b",
            "period-appropriate bronze approval token embossed with a simple raised-hand relief on a dark wooden tabletop",
        ),
        (
            r"\bthumbs[-\s]?up\s+icon\b",
            "period-appropriate bronze approval token embossed with a simple raised-hand relief on a dark wooden tabletop",
        ),
        (
            r"\bbusiness\s+handshake\b|\bmodern\s+handshake\b",
            "period-local formal sleeve-clasp greeting between robed historical adults",
        ),
        (
            r"\bdiplomats?\b",
            "period-local envoys wearing formal robes from the stated era",
        ),
        (
            r"\bmodern\s+envoys?\b|\bmodern\s+diplomats?\b",
            "period-local envoys wearing formal robes from the stated era",
        ),
        (
            r"\bshaking\s+hands\b|\bshake\s+hands\b|\bhandshake\b",
            "period-local formal sleeve-clasp greeting, visible robed sleeves and hands meeting at chest height",
        ),
        (
            r"\bthought\s+bubble\s+showing\b",
            "symbolic vignette showing",
        ),
        (
            r"\bthought\s+bubbles?\b",
            "symbolic vignette",
        ),
        (
            r"\bspeech\s+bubble\s+showing\b",
            "spoken emotion shown by face, posture, and gesture with no text balloon, showing",
        ),
        (
            r"\bspeech\s+bubbles?\b",
            "spoken emotion shown by face, posture, and gesture with no text balloon",
        ),
        (
            r"\bdialogue\s+bubbles?\b|\bspeech\s+balloons?\b|\bcomic\s+speech\s+balloons?\b",
            "spoken emotion shown by face, posture, and gesture with no text balloon",
        ),
        (
            r"\bfloating\s+cartoon\s+bubbles?\b",
            "period-local symbolic smoke or shadow vignette",
        ),
    ]
    for pattern, replacement in replacements:
        scene = re.sub(pattern, replacement, scene, flags=re.IGNORECASE)
    changed = scene != original_scene
    if changed:
        p = _replace_prompt_field(p, "Scene", _clean_prompt_commas(scene))
    main_subject = _prompt_field(p, "Main subject")
    if main_subject:
        original_main_subject = main_subject
        for pattern, replacement in replacements:
            main_subject = re.sub(pattern, replacement, main_subject, flags=re.IGNORECASE)
        if main_subject != original_main_subject:
            p = _replace_prompt_field(p, "Main subject", _clean_prompt_commas(main_subject))
            changed = True
    if not changed:
        return p
    if "HISTORICAL SYMBOLIC PROP LOCK" not in p:
        p += HISTORICAL_SYMBOLIC_PROP_DIRECTIVE
    return p


def _normalize_premodern_footwear_scene_language(prompt: str) -> str:
    p = prompt or ""
    if not p or _is_modern_context(p):
        return p
    original = p
    replacements = (
        (
            r"\bheavy\s+iron\s+boot\b",
            "period-local armored foot: rough leather shoe or simple soft boot covered by iron greave or lamellar shin guard",
        ),
        (
            r"\biron\s+boot\b",
            "period-local iron-shod leather footwear with armor greave",
        ),
        (
            r"\bboot\s+stepping\b",
            "period-local armored foot stepping",
        ),
    )
    for pattern, repl in replacements:
        p = re.sub(pattern, repl, p, flags=re.IGNORECASE)
    scene = _prompt_field(p, "Scene")
    if scene and re.search(
        r"\b(foot|feet|shoe|shoes|sandal|sandals|boot|boots|gaiter|gaiters|greave|greaves)\b",
        scene,
        re.IGNORECASE,
    ) and re.search(
        r"\b(step|stepping|stamp|stamping|stride|walking|trampling|crushing|muddy|mud|ground|threshold|stone|dust)\b",
        scene,
        re.IGNORECASE,
    ):
        if "PREMODERN FOOTWEAR EVIDENCE CLOSE-UP LOCK" not in p:
            p += PREMODERN_FOOTWEAR_EVIDENCE_DIRECTIVE
    elif p != original and re.search(r"\bfoot|shoe|boot|greave\b", p, re.IGNORECASE):
        if "PREMODERN FOOTWEAR EVIDENCE CLOSE-UP LOCK" not in p:
            p += PREMODERN_FOOTWEAR_EVIDENCE_DIRECTIVE
    return p


def _normalize_early_ancient_chinese_armor_language(prompt: str) -> str:
    p = prompt or ""
    if not _is_early_ancient_chinese_context(p):
        return p
    scene = _prompt_field(p, "Scene")
    if not scene:
        return p
    original_scene = scene
    replacements = [
        (
            r"\bheavy\s+bronze\s+armor\b",
            "early Chinese bronze-scale and rawhide protective layers over cloth robes",
        ),
        (
            r"\bbronze\s+armor\b",
            "bronze-scale and leather protective layers",
        ),
        (
            r"\bmetal\s+armor\b",
            "small overlapping bronze or leather scale protection",
        ),
        (
            r"\bplate\s+armor\b",
            "small overlapping bronze-scale protection",
        ),
        (
            r"\barmored\s+(guards?|soldiers?|warriors?|lords?)\b",
            r"\1 in early Chinese leather or bronze-scale protection",
        ),
    ]
    for pattern, replacement in replacements:
        scene = re.sub(pattern, replacement, scene, flags=re.IGNORECASE)
    if scene == original_scene:
        return p
    return _replace_prompt_field(p, "Scene", _clean_prompt_commas(scene))


def _normalize_travel_vehicle_scene_language(prompt: str) -> str:
    p = prompt or ""
    scene = _prompt_field(p, "Scene")
    carried_litter_pattern = (
        r"\b(palanquin|sedan\s+chair|carried\s+chair)\b|가마|"
        r"(?<!palanquin\s)(?<!covered\s)(?<!carried\s)\blitter\b(?!\s+(?:the|a|an)\b)"
    )
    if not scene or not re.search(
        carried_litter_pattern,
        scene,
        re.IGNORECASE,
    ):
        return p
    scene = re.sub(
        r"\b(?:small\s+)?palanquin\b",
        "small period-local shoulder-borne palanquin or covered carried litter in a tight shoulder-height side crop with long shoulder poles resting on cropped support-walker shoulders and hands, two parallel pole lines as the only support structure, open shadow below the suspended cabin, lower third empty except shadow gap, road dust, robe hems, and cropped bearer feet at far edges",
        scene,
        flags=re.IGNORECASE,
    )
    scene = re.sub(
        r"\bsedan\s+chair\b",
        "shoulder-borne covered carried chair in a tight shoulder-height side crop with long shoulder poles resting on cropped support-walker shoulders and hands, two parallel pole lines as the only support structure, open shadow below the suspended cabin, lower third empty except shadow gap, road dust, robe hems, and cropped bearer feet at far edges",
        scene,
        flags=re.IGNORECASE,
    )
    scene = re.sub(
        r"(?<!palanquin\s)(?<!covered\s)(?<!carried\s)\blitter\b(?!\s+(?:the|a|an)\b)",
        "shoulder-borne covered carried litter in a tight shoulder-height side crop with long shoulder poles resting on cropped support-walker shoulders and hands, two parallel pole lines as the only support structure, open shadow below the suspended cabin, lower third empty except shadow gap, road dust, robe hems, and cropped bearer feet at far edges",
        scene,
        flags=re.IGNORECASE,
    )
    scene = re.sub(
        r"\bcourt\s+attendants?\b",
        "small side/back support walkers partly hidden by the carried cabin",
        scene,
        flags=re.IGNORECASE,
    )
    scene = re.sub(
        r"\bguards?\s+scan\s+the\s+slopes\b",
        "distant side/back escort silhouettes partly hidden by the cabin and trees scan the slopes",
        scene,
        flags=re.IGNORECASE,
    )
    if "shoulder-borne litter close crop" not in scene.lower():
        scene = (
            scene.rstrip(" .;")
            + "; shoulder-borne litter close crop with the carried cabin, "
            "canopy, curtains, and shoulder poles as the main visible subject; "
            "load-bearing evidence appears as cropped shoulder contact under "
            "poles, cropped gripping hands, folded sleeves, and narrow moving "
            "torso slices crossed by poles; the underside shows "
            "open shadow and road dust below the suspended cabin; support-figure upper bodies stay "
            "small, side/back turned, hidden by the cabin, behind poles, behind "
            "curtains, or cropped at the frame edge; upper chest fronts stay "
            "outside the readable frame or are physically crossed by poles, "
            "hands, sleeves, straps, curtains, or cabin edges; "
            "support figures recede as small side/back background silhouettes behind "
            "the cabin"
        )
    return _replace_prompt_field(p, "Scene", _clean_prompt_commas(scene))


def _normalize_character_scene_language(prompt: str) -> str:
    if not prompt_mentions_major_character(prompt or ""):
        return prompt or ""
    out = prompt or ""
    replacements = [
        (
            r"\bdark\s+vision\s+of\s+([^,.;]+?)\s+in\s+heavy\s+chains\b",
            r"ominous period captive group scene showing \1 in heavy chains, bare visible eyes, anxious faces, plain period clothing",
        ),
        (
            r"\bdark\s+vision\s+of\s+([^,.;]+)",
            r"ominous period scene showing \1 with bare visible eyes and plain period clothing",
        ),
        (
            r"\bsitting\s+on\s+a\s+massive\s+throne\b",
            "front-facing seated head-and-shoulders close-up portrait shot with carved throne texture behind the shoulders",
        ),
        (
            r"\bmagical\s+beam\s+of\s+sunlight\s+entering\s+a\s+dark\s+room,\s*hitting\s+a\s+woman\b",
            "solo close-up portrait of one adult woman in a warm beam of sunlight, face filling most of the frame, eye contact, anxious expression, plain earthen wall texture",
        ),
        (
            r"\bwhispering\s+in\s+the\s+dark,\s*looking\s+terrified\b",
            "whispering in warm low side light, visible faces, terrified eyes, tight group posture",
        ),
        (
            r"\bdim\s+tent\b",
            "warm lamplit tent interior with visible faces and tight group posture",
        ),
        (
            r"\bordering\s+soldiers\b",
            "Geumwa king close-up with angry eye contact, small pointing arm gesture near the chest, soldiers reduced to distant soft shoulder-line shapes behind him",
        ),
        (
            r"\byuhwa,\s*elegant\s+ancient\s+korean\s+noblewoman,\s*confident\s+smile\b",
            "front-facing adult Buyeo noblewoman chest-up portrait, large visible face, confident smile, composed eyes, robe neckline and hair visible, plain earthen wall texture",
        ),
        (
            r"\bsplit\s+screen\s+of\s+([^,.;]+?)\s+and\s+([^,.;]+?)(?=,|;|\.|$)",
            r"two contrasting people, \1 and \2, standing separated in one shared interior, both opened toward the viewer with distinct posture and readable expressions",
        ),
        (
            r"\b([^,.;]+?)\s+and\s+([^,.;]+?)\s+lined\s+up\s+side\s+by\s+side\b",
            r"\1 and \2 arranged as separated foreground subjects in one shared physical space with clear air gaps and distinct silhouettes",
        ),
    ]
    for pattern, replacement in replacements:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return _clean_prompt_commas(out)


def _normalize_armed_action_scene_language(prompt: str) -> str:
    out = prompt or ""
    replacements = [
        (
            r"\bgrips\s+(?:his|her|their)\s+tachi\b",
            "clenches both empty hands over a plain belt",
        ),
        (
            r"\bgripping\s+(?:his|her|their)\s+tachi\b",
            "clenching both empty hands over a plain belt",
        ),
        (
            r"\bholds\s+(?:his|her|their)\s+tachi\b",
            "clenches both empty hands over a plain belt",
        ),
        (
            r"\bholding\s+(?:his|her|their)\s+tachi\b",
            "clenching both empty hands over a plain belt",
        ),
        (
            r"\b(?:enemy\s+)?(?:soldiers|warriors|fighters|guards|army)\s+raising\s+their\s+weapons\s+high\s+in\s+victory\b",
            "one representative victorious fighter raising a clenched empty fist, battlefield pressure shown through smoke, dust, roof edges, thick timber posts, and mountain haze",
        ),
        (
            r"\b(?:enemy\s+)?(?:soldiers|warriors|fighters|guards|army)\s+raising\s+weapons\s+high\s+in\s+victory\b",
            "one representative victorious fighter raising a clenched empty fist, battlefield pressure shown through smoke, dust, roof edges, thick timber posts, and mountain haze",
        ),
        (
            r"\bcinematic\s+wide\s+shot,\s*massive\s+ancient\s+armies\s+clashing\s+on\s+a\s+dusty\s+desert\s+battlefield\b",
            "tight close-up collision crop of exactly four readable chest-up combat figures total in a diagonal dust-haze clash, all humans in the main foreground cluster, empty dust haze behind them, two compact opposing subgroups facing each other from left and right, crossed short spear angles at the center, turned shoulders, tense faces, advancing and recoiling chest-up poses, lower bodies outside the frame, lower frame edge at high upper chest cloth",
        ),
        (
            r"\bmassive\s+ancient\s+armies\s+clashing\s+on\s+a\s+dusty\s+desert\s+battlefield\b",
            "tight close-up collision crop of exactly four readable chest-up combat figures total in a diagonal dust-haze clash, all humans in the main foreground cluster, empty dust haze behind them, two compact opposing subgroups facing each other from left and right, crossed short spear angles at the center, turned shoulders, tense faces, advancing and recoiling chest-up poses, lower bodies outside the frame, lower frame edge at high upper chest cloth",
        ),
        (
            r"\bPhanes\s+sneaking\s+away\s+from\s+sleeping,\s*drunk\s+Egyptian\s+guards,\s*moonlight\s+shining\s+on\s+his\s+path\b",
            "Phanes sneaking along a moonlit path as the only upright moving figure, two open palms visible, relaxed fingers near his robe, past sleeping drunk Egyptian watchmen lying horizontally on the floor or slumped low with closed eyelids, loose arms, and relaxed hands resting on cloth",
        ),
        (
            r"\bsneaking\s+away\s+from\s+sleeping,\s*drunk\s+Egyptian\s+guards,\s*moonlight\s+shining\s+on\s+(?:his|her|their)\s+path\b",
            "sneaking along a moonlit path as the only upright moving figure, two open palms visible, relaxed fingers near the robe, past sleeping drunk Egyptian watchmen lying horizontally on the floor or slumped low with closed eyelids, loose arms, and relaxed hands resting on cloth",
        ),
    ]
    for pattern, replacement in replacements:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return _clean_prompt_commas(out)


def _normalize_military_logistics_scene_language(prompt: str) -> str:
    out = prompt or ""
    replacements = [
        (
            r"\blifting\s+armor\s+bundles\b",
            "lifting flat stacks of laced kozane scale rows and folded sode shoulder panels",
        ),
        (
            r"\bcarrying\s+armor\s+bundles\b",
            "carrying flat stacks of laced kozane scale rows and folded sode shoulder panels",
        ),
        (
            r"\barmor\s+bundles\b",
            "flat stacks of laced kozane scale rows and folded sode shoulder panels",
        ),
        (
            r"\barmor\s+bundle\b",
            "flat stack of laced kozane scale rows and folded sode shoulder panels",
        ),
    ]
    for pattern, replacement in replacements:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return _clean_prompt_commas(out)


def _normalize_medieval_japanese_hand_equipment_language(prompt: str) -> str:
    out = prompt or ""
    if not _is_medieval_japanese_context(out):
        return out
    replacements = [
        (
            r"\b(?:carrying|holding|gripping|raising|lifting)\s+(?:a\s+)?shields?\b",
            "holding empty off-hands near belts",
        ),
        (
            r"\bwith\s+(?:a\s+)?shields?\b",
            "with empty off-hands",
        ),
        (
            r"\bshield\s+walls?\b",
            "close samurai line with empty off-hands",
        ),
        (
            r"\bshields?\b",
            "empty off-hands",
        ),
        (
            r"방패를\s*(?:들고|쥐고|올리고|든|든 채)",
            "빈 손을 허리 가까이에 두고",
        ),
        (
            r"방패",
            "빈 손",
        ),
    ]
    for pattern, replacement in replacements:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return _clean_prompt_commas(out)


def _normalize_medieval_japanese_armor_language(prompt: str) -> str:
    out = prompt or ""
    if not _is_medieval_japanese_context(out):
        return out
    replacements = [
        (
            r"\bpractical\s+warrior\s+armor\b",
            "dull dark-brown matte lacquered kozane rows, odoshi cord lacing, cloth sleeves, rectangular sode panels, and kusazuri skirt panels",
        ),
        (
            r"\bwarrior\s+scenes\s+use\s+practical\s+armor\b",
            "warrior scenes use dull dark-brown matte lacquered kozane rows, odoshi cords, cloth sleeves, rectangular sode panels, and kusazuri skirt panels",
        ),
        (
            r"\barmored\s+(guards?|retainers?|warriors?|soldiers?|commanders?|riders?|envoys?|messengers?|escorts?)\b",
            r"\1 in dull dark-brown matte lacquered kozane rows, odoshi cords, cloth sleeves, rectangular sode panels, and kusazuri skirt panels",
        ),
        (
            r"\blamellar\s+armor\b",
            "dull dark-brown matte laced kozane rows over cloth sleeves",
        ),
        (
            r"\barmor\s+with\s+laced\s+kozane\s+rows\b",
            "dull dark-brown matte laced kozane rows with visible odoshi cords",
        ),
    ]
    for pattern, replacement in replacements:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return _clean_prompt_commas(out)


def _scene_text(prompt: str) -> str:
    scene = _prompt_field(prompt, "Scene")
    return scene or prompt or ""


def _scene_requests_map_object(prompt: str) -> bool:
    scene = _scene_text(prompt)
    return bool(
        re.search(
            r"\b(maps?|tactile\s+campaign\s+board|campaign\s+board|"
            r"tactile\s+strategy\s+board|strategy\s+board|"
            r"tactile\s+marker\s+layout|horizontal\s+tactile\s+marker\s+layout|"
            r"low\s+horizontal\s+tactile\s+marker\s+layout|"
            r"cloth\s+planning\s+surface|ground-level\s+tabletop\s+surface|"
            r"tabletop\s+campaign\s+surface|raised\s+relief\s+terrain\s+board|"
            r"relief\s+terrain\s+board|clay\s+tablet\s+map|wooden\s+board\s+map|"
            r"ground\s+plan|sand[-\s]+marked\s+ground\s+plan|ground\s+diagram|"
            r"field\s+diagram|land\s+diagram|land\s+guarantee\s+diagram|"
            r"property\s+diagram|cloth\s+board)\b|지도",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_requests_planning_board_object(prompt: str) -> bool:
    return bool(
        re.search(
            r"\b(tabletop\s+planning\s+board|planning\s+board)\b",
            _scene_text(prompt),
            re.IGNORECASE,
        )
    )


def _scene_requests_group_planning_surface(prompt: str) -> bool:
    scene = _scene_text(prompt)
    if not scene or not _scene_requests_humans(prompt):
        return False
    return bool(
        re.search(
            r"\b(?:blank\s+)?floor\s+plan\b|"
            r"\b(?:campaign|strategy|planning|war)\s+table\b|"
            r"\bcouncil\s+planning\s+surface\b|"
            r"\b(?:blank\s+|low\s+horizontal\s+)?planning\s+surface\b|"
            r"\b(?:lean|leans|leaning|gather|gathered|gathering)\b[^.;]*\bplan\b|"
            r"\bplan\s+surface\b",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_named_identity_directive(prompt: str) -> str:
    if not prompt_mentions_major_character(prompt or ""):
        return ""
    scene = _scene_text(prompt)
    if not scene:
        return ""
    if _scene_requests_achaemenid_egyptian_armed_group(prompt):
        return ""
    facts: list[str] = []
    for pattern, fact in _KNOWN_SCENE_IDENTITY_FACTS:
        if pattern.search(scene):
            facts.append(fact)
    if not facts and not _PROPER_NAME_SCENE_RE.search(scene):
        return ""
    if not facts:
        return SCENE_NAMED_IDENTITY_DIRECTIVE_PREFIX
    return (
        SCENE_NAMED_IDENTITY_DIRECTIVE_PREFIX
        + " Confirmed identity facts from the Scene: "
        + "; ".join(dict.fromkeys(facts))
        + "."
    )


def _compact_scene_context(prompt: str) -> str:
    parts: list[str] = []
    year = _prompt_field(prompt, "Year/period")
    place = _prompt_field(prompt, "Exact place")
    if year:
        parts.append(f"period {year}")
    if place:
        parts.append(f"place {place}")
    return "; ".join(parts)


def _scene_requests_open_path_or_garden_axis(prompt: str) -> bool:
    scene_blob = " ".join(
        part
        for part in (
            _prompt_field(prompt, "Main subject"),
            _prompt_field(prompt, "Exact place"),
            _prompt_field(prompt, "Scene"),
            _prompt_field(prompt, "Scene evidence"),
        )
        if part
    )
    if not scene_blob:
        return False
    if re.search(
        r"\b(?:gate|gateway|gatehouse|doorway|entrance|portal)\b|문루|대문|출입문|현관",
        scene_blob,
        re.IGNORECASE,
    ):
        return False
    return bool(
        re.search(
            r"\b(?:garden\s+axis|central\s+axis|side\s+paths?|two\s+side\s+paths?|"
            r"garden\s+path|pond\s+garden\s+path|courtyard\s+path|open\s+path|"
            r"pathway|route\s+through\s+the\s+garden)\b|정원\s*축|정원길|마당길|동선",
            scene_blob,
            re.IGNORECASE,
        )
    )


def _scene_requests_guarded_gate_or_entrance(prompt: str) -> bool:
    scene_blob = " ".join(
        part
        for part in (
            _prompt_field(prompt, "Main subject"),
            _prompt_field(prompt, "Exact place"),
            _prompt_field(prompt, "Scene"),
            _prompt_field(prompt, "Scene evidence"),
        )
        if part
    )
    if not scene_blob:
        return False
    return bool(
        re.search(
            r"\b(?:guarded\s+entrance|guards?\s+.*\bgate|gate\s+.*\bguards?|"
            r"gatehouse|entrance\s+.*\bwatch|strict\s+watch|doorway\s+guard)\b|"
            r"문루|대문|출입문|수문장|문지기",
            scene_blob,
            re.IGNORECASE,
        )
    )


def _scene_requests_modest_village_or_hamlet(prompt: str) -> bool:
    scene_blob = " ".join(
        part
        for part in (
            _prompt_field(prompt, "Main subject"),
            _prompt_field(prompt, "Exact place"),
            _prompt_field(prompt, "Scene"),
            _prompt_field(prompt, "Scene evidence"),
        )
        if part
    )
    if not scene_blob:
        return False
    if re.search(
        r"\b(?:palace|royal\s+compound|temple|shrine|mansion|elite\s+residence|"
        r"official\s+hall|court\s+hall|government\s+office|capital\s+gate)\b|"
        r"궁궐|왕궁|사찰|절|신전|저택|관청|정전|궁문",
        scene_blob,
        re.IGNORECASE,
    ):
        return False
    return bool(
        re.search(
            r"\b(?:small\s+village|fragile\s+village|poor\s+village|rural\s+village|"
            r"frontier\s+village|village|hamlet|rural\s+settlement|frontier\s+settlement|"
            r"settlement\s+edge|village\s+edge)\b|마을|촌락|취락|부락|농촌|변방\s*취락|"
            r"변방\s*마을|작은\s*마을|가난한\s*마을",
            scene_blob,
            re.IGNORECASE,
        )
    )


def _primary_image_lock(prompt: str) -> str:
    if not (prompt or "").strip() or "PRIMARY IMAGE LOCK" in (prompt or ""):
        return ""
    scene = _scene_text(prompt)
    scene_short = _clean_prompt_commas(scene)[:260]
    context = _compact_scene_context(prompt)
    context_text = f" Context: {context}." if context else ""

    if _scene_requests_banner_evidence_without_living_people(prompt):
        return (
            "PRIMARY IMAGE LOCK - BANNER EVIDENCE FRAME - first visible "
            "subject: the Scene-named banners or flags, not people and not "
            "architecture. If the Scene names three distinct banners, show "
            "exactly three separate blank cloth military banners on exactly "
            "three separate poles, all fully visible in one outdoor frame, "
            "with wind folds, hems, rope ties, mud, rain, and shadow only; the "
            "whole frame contains three banners total and three poles total, "
            "with no fourth banner, no fifth banner, no duplicate banner, and "
            "no extra background flagpole. "
            "No full person, face, standing soldier, group portrait, gate "
            "facade, roofed building, signboard, wall plaque, or interior room "
            "may replace the banners. The background stays low and secondary: "
            "muddy ground, storm air, distant earthworks, low hills, rough "
            "wooden palisade stakes, or plain period-local camp edges from the "
            "stated era and place. For early fifth century Silla or Goguryeo "
            "context, do not include a Japanese torii gate, shrine gate, "
            "Japanese temple, tiled-roof hall, polished courtyard gate, village "
            "house, roofed building, or ceremonial gate. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _scene_requests_guarded_gate_or_entrance(prompt):
        return (
            "PRIMARY IMAGE LOCK - first visible subject: the guarded entrance "
            "or gate action explicitly named by the Scene, with period-local "
            "guards and passing figures arranged around a plain unmarked timber "
            "gate. The top lintel and any header board area are continuous blank "
            "wood grain, knots, seams, nail heads, bracket shadows, dust, and "
            "plaster only. Do not place any temple nameboard, gate plaque, "
            "inscription panel, character board, modern wall panel, doorbell, "
            "intercom, keypad, switch plate, or electronic lock on the gate, post, "
            "wall, or doorway. Door hardware is limited to period-local pull rings, "
            "rope loops, hinges, wooden bars, pegs, and nail heads. All people, "
            "including guards, envoys, guests, servants, and background figures, "
            "wear period-local clothing, armor, footwear, hair, and headgear from "
            "the stated year and place. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _scene_requests_open_path_or_garden_axis(prompt):
        return (
            "PRIMARY IMAGE LOCK - first visible subject: the requested open "
            "garden axis, side paths, courtyard path, or path movement named by "
            "the Scene. Compose an open outdoor or semi-outdoor path frame where "
            "packed ground, stones, grass edges, pond-garden edges, trees, and "
            "walking or gesturing period-dressed figures reveal the route. Do "
            "not replace this with a frontal gate facade, gatehouse portrait, "
            "doorway close-up, entrance sign, or lintel signboard. If architecture "
            "appears, it stays to the side or background with plain unmarked "
            "timber and plaster. All people, including envoys, attendants, guards, "
            "and distant figures, wear period-local clothing from the stated "
            "year and place. "
            f"Scene: {scene_short}.{context_text}"
        )

    if not _scene_requests_humans(prompt) and _scene_requests_modest_village_or_hamlet(prompt):
        return (
            "PRIMARY IMAGE LOCK - MODEST VILLAGE SETTING LOCK - first visible "
            "subject: the requested small village, hamlet, rural settlement, "
            "frontier settlement, or fragile settlement named by the Scene. "
            "Compose an oblique medium-wide or wide period-local village view "
            "where the first readable surface is the packed-earth lane, rough "
            "fence line, storage jars, baskets, dust, smoke, weeds, damaged "
            "edges, and low ordinary dwellings. Visible village roof inventory "
            "is closed to modest rural materials for the stated era and place: "
            "straw thatch, reed thatch, bark, rough wooden planks, earth, mud, "
            "or other plain non-elite local roofing. Ceramic roof tiles, gray "
            "curved tile rows, formal bracket eaves, and palace/temple roof "
            "silhouettes are absent. Do not replace the village with a "
            "palace compound, temple courtyard, elite residence, formal tiled "
            "courtyard, government hall, mansion, ornamental gate facade, or "
            "close roofed veranda. If the stated era and place allow tiled roofs "
            "only for elite buildings, they are absent unless the Scene names an "
            "elite, palace, temple, or official building. Roof eaves, posts, "
            "doors, lintels, and walls remain plain structural material with no "
            "signboard, plaque, paper strip, talisman, label, calligraphy, or "
            "character-like marks. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _scene_is_inanimate_statue_object_without_living_people(prompt):
        return (
            "PRIMARY IMAGE LOCK - first visible subject: the inanimate statue, "
            "idol, sculpture, carved deity image, bust, figurine, monument, or "
            "relief figure named by the Scene. Compose an object-first temple or "
            "pedestal evidence frame with the statue as one coherent physical "
            "object. Body parts named inside the statue description are sculpted "
            "material forms fused into the same object surface. Material, "
            "pedestal contact, carved edges, chips, dust, temple shadow, and "
            "directional light carry the story. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _scene_requests_map_object(prompt):
        return (
            "PRIMARY IMAGE LOCK - first visible subject: the requested strategic "
            "planning evidence from the Scene as a low horizontal tactile "
            "marker layout on a plain low wooden table surface, floor mat, "
            "clay slab, cloth planning surface, or ground-level tabletop "
            "surface appropriate to the stated era and place. The physical "
            "marker layout dominates the frame from a top-down or close "
            "three-quarter tabletop camera view: at least one loose route cord, "
            "two separated stone clusters, and one bronze weight, pin, or "
            "folded cloth strip rest on the surface with hard directional "
            "light. Regional control and faction pressure are shown by marker "
            "positions, cord paths, clusters, shadows, and light on horizontal "
            "natural material. Lower-left, lower-right, bottom, and corner "
            "zones are plain material margins made from broad dust, grain, "
            "shadow, and wear, still on the same low horizontal surface. "
            "The surface is physically unmarked and carries unmarked marker "
            "objects only, with empty surrounding edges. This is an unoccupied "
            "object-only tabletop or floor-surface evidence view; visible "
            "subject inventory is only the low surface, marker objects, lamp "
            "light, shadows, surface edges, dust, and natural material texture. "
            "The camera crop stays on the low surface from edge to edge, "
            "filled by horizontal material margins and marker objects. "
            "Off-screen pressure "
            "appears only through lamp light, shadows, marker spacing, cord "
            "paths, surface dust, and edge shadows. This is a tight "
            "tactile marker layout shot "
            "with the camera remaining on the tabletop surface. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _scene_requests_group_planning_surface(prompt):
        return (
            "PRIMARY IMAGE LOCK - first visible subject: the shared council "
            "planning evidence on a blank low horizontal planning surface. "
            "Use a steep top-down tabletop or floor-surface evidence crop "
            "looking directly at the horizontal surface plane: the camera crop "
            "contains only the horizontal planning surface, marker objects, "
            "edge-cropped sleeve and hand fragments, light, dust, and shadows. "
            "Full faces, heads, shoulders, full torsos, and full people stay "
            "outside the main readable crop, while cropped hands, fingertips, "
            "sleeves, forearm edges, and hand shadows enter from the surface "
            "edges near physical markers. The planning evidence fills the full frame edge to edge as bare wood, cloth, mat, or clay with "
            "loose route cords crossing three separated marker clusters, at "
            "least seven separated stone markers, one palm-sized bronze weight "
            "or pin, low side candle or oil lamp light from table edge or floor "
            "edge, hand shadows, dust, and blank material margins only. "
            "The planning surface is filled by movable marker objects with "
            "clear blank material gaps. The camera stays locked to the "
            "horizontal surface from border to border and never leaves the "
            "surface plane. The table or floor surface stays bare period material with movable markers "
            "as the readable planning evidence. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _scene_requests_generic_object_evidence(prompt):
        scene_lower = scene.lower()
        if _scene_requests_depicted_visual_surface_object(prompt):
            subject = (
                "the physical visual-surface object named by the Scene as the "
                "dominant foreground evidence: torn painting, document, tablet, "
                "mural, relief, canvas, paper, pigment, carved plane, torn edge, "
                "dust, stains, worn texture, and hard side light. Any battlefield, "
                "figure, animal, or event named after the surface word stays flat "
                "inside that same material plane as painted, carved, stained, or "
                "damaged surface evidence; it does not become a live person, live "
                "battle scene, or separate environment"
            )
        elif _scene_requests_empty_seat_or_platform_evidence(prompt):
            subject = (
                "the empty Scene-named throne, seat, dais, low platform, chair, "
                "bed, mat, or support furniture as the dominant unoccupied "
                "evidence object. The seat surface, platform edge, draped cloth "
                "when named, dust, pressure marks, shadow, and surrounding local "
                "material carry the story. No living person, portrait, face, "
                "standing figure, seated figure, or wearer appears in the frame"
            )
        elif re.search(r"\b(mirror|reflective\s+mirror|polished\s+mirror|bronze\s+mirror)\b|거울|동경", scene_lower, re.IGNORECASE):
            subject = (
                "the Scene-named period-local reflective mirror object as the "
                "dominant foreground evidence: a small round or oval bronze, "
                "metal, obsidian, or other period-plausible hand mirror resting "
                "on a low support surface, not mounted on a wall and not inside "
                "a rectangular picture frame, visible rim, reflective plane, "
                "crack lines when named, dust, "
                "wear, support-surface contact, and hard side light. Any reflected "
                "face or figure named by the Scene appears only as a distorted "
                "reflection contained inside the mirror surface, not as a live "
                "person portrait or separate human in the room. No real hand, "
                "pointing finger, wrist, arm, wall plate, switch-like rectangle, "
                "or mounted plaque appears outside the mirror"
            )
        elif re.search(r"\b(crown|diadem|tiara|headpiece|regalia|circlet)\b|왕관|관모|보관", scene_lower, re.IGNORECASE):
            subject = (
                "the Scene-named ruler status headpiece, crown-like regalia, "
                "diadem, or authority object as a period-local artifact, laid "
                "flat in a shallow crescent arc on a visible local support surface. "
                "It is a head-worn status object shown as an open diadem strip or "
                "cloth-metal headband regalia with two visible open ends, flattened "
                "metal band edge, and low head-ornament profile, "
                "not a box, chest, coffer, lidded container, treasure case, bowl, "
                "basin, hollow dish, helmet dome, closed ring, bucket, pot, cup, "
                "cylindrical container, or open-top vessel. It must read as a "
                "flat wearable status band, not as a vertical-walled container, "
                "top-down bowl, or pot. It "
                "is not a European fairy-tale crown unless that era and place "
                "require one; use conservative local construction, metal, lacquer, "
                "cloth, leather, jewel, cord, or ritual material plausible for "
                "the stated source context"
            )
        elif re.search(r"\b(golden\s+stool|sacred\s+stool|royal\s+stool|carved\s+stool)\b", scene_lower, re.IGNORECASE):
            subject = (
                "the Scene-named sacred Asante or Ashanti stool object as the "
                "dominant foreground evidence: a low carved wooden stool with "
                "curved seat, visible support structure, gold-covered or gold "
                "regalia surface when named, resting on a local cloth, low "
                "wooden support, pedestal, or packed-earth courtyard surface. "
                "It must read as a ceremonial stool object, not a bowl, crown, "
                "box, chest, coffer, lidded container, altar slab, or throne "
                "chair with a backrest"
            )
        elif re.search(r"\b(blade|broken\s+blade|sword|broken\s+sword|dagger|knife|weapon|shield)\b|검|칼|칼날|무기|방패", scene_lower, re.IGNORECASE):
            subject = (
                "the Scene-named weapon evidence as the dominant still-life "
                "object, lying flat on the named table, stone, ground, mat, or "
                "support surface with visible physical contact, dull material "
                "wear, fractures when named, dust, stains, and hard directional "
                "light"
            )
        elif _BOOK_OBJECT_RE.search(scene):
            subject = (
                "the Scene-named book, document, record bundle, scroll, tablet, "
                "paper, or manuscript object as the dominant foreground evidence, "
                "closed or edge-on when text is not required, with unmarked cover, "
                "cord binding, worn edges, dust, stains, and hard directional "
                "light on a visible period-local support surface"
            )
        else:
            subject = (
                "the concrete Scene-named object as the dominant foreground "
                "evidence, resting on its visible support surface with contact "
                "shadow, period-local material, dust, wear, and hard directional "
                "light"
            )
        return (
            "PRIMARY IMAGE LOCK - first visible subject: "
            f"{subject}. Compose a close object evidence frame where the named "
            "object fills most of the image and the background is only narrow "
            "support-surface or local setting material. Do not replace the object "
            "with a gate, doorway, building facade, palace exterior, person, "
            "portrait, live battle scene, signboard, plaque, or blank panel. "
            "Visible inventory is limited to the Scene-named object, its support "
            "surface, local material edges, dust, stains, light, and shadow. "
            f"Scene: {scene_short}.{context_text}"
        )

    if (
        not _scene_requests_humans(prompt)
        and re.search(
            r"\b(city|capital|settlement|village|hamlet|compound|town|kingdom|"
            r"empire|urban|frontier\s+village|frontier\s+settlement|Kumasi|"
            r"Ashanti\s+Empire|Asante\s+Empire)\b|"
            r"(도시|수도|마을|촌락|취락|부락|주거지|왕국|제국|쿠마시|아샨티|아산테)",
            scene,
            re.IGNORECASE,
        )
    ):
        return (
            "PRIMARY IMAGE LOCK - first visible subject: the requested city, "
            "capital, settlement, village, hamlet, kingdom, empire, or urban place from the "
            "Scene as an establishing human-scale setting view, not a single "
            "foreground object close-up. Compose a medium-wide or wide "
            "period-local city and settlement frame with readable buildings, "
            "courtyards, streets, roofs, walls, ground material, vegetation, "
            "weather, smoke, dust, decay, or damage exactly where the Scene "
            "implies them. Architecture, terrain, and material culture come "
            "from the stated Year/period and Exact place. Use an oblique or "
            "wide establishing view, not a close roofed entrance, front gate "
            "facade, doorway close-up, or centered eave-board composition. "
            "Roof eaves, lintels, and gate headers stay outside the central "
            "focus when possible; if visible, each one is one continuous "
            "shadowed timber or plaster band with uninterrupted material grain, "
            "bracket shadows, dust, knots, and nail heads only. The frame stays "
            "one continuous physical setting with no signboard, no readable text, "
            "no under-eave board, no plaque-like rectangle, no short character "
            "stroke cluster under a roof, no imported palace system, and no "
            "unrelated ceremonial object replacing the city or village view. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _scene_requests_low_lamp_armed_entry(prompt):
        return (
            "PRIMARY IMAGE LOCK - LOW LAMP ARMED ENTRY LOCK - first visible "
            "subject: the low flame source, doorway threshold, and moving entry "
            "path named by the Scene, not a front-facing lineup. Compose a "
            "low side-angle story frame from lamp height or knee height. The "
            "low floor or table oil lamp, brazier, candle, or lantern sits at "
            "the lower side of the frame below shoulder height and throws one "
            "consistent side light toward the doorway, path, or listening guard. Armed escorts, "
            "guards, soldiers, warriors, retainers, or military attendants enter "
            "or listen as side, back, rear three-quarter, or oblique "
            "three-quarter figures crossing the threshold, climbing path, dark "
            "entry route, or turning toward an off-screen sound. "
            "Avoid a posed front-facing row. Any readable robe front is narrow, "
            "angled, partially shadowed, or physically crossed by sleeves, hands, "
            "waist cords, scabbard straps, doorway posts, or other Scene-named "
            "equipment. Upper chest fronts stay outside the main readable focus "
            "or are broken by folds, hands, straps, doorway edge, smoke, and "
            "shadow; no small bright chest object is a visible subject. Walls "
            "and posts remain broad period material with cracks, timber grain, "
            "dust, and shadow only; no isolated rectangular wall plate appears. "
            "The story action is the climb, entry, or listening tension through "
            "low flame light, doorway depth, mountain darkness, moving shoulders, "
            "turned heads, tense faces, and shadow pressure. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _scene_requests_carried_travel_vehicle(prompt):
        return (
            "PRIMARY IMAGE LOCK - first visible subject: the Scene-named "
            "shoulder-borne carried litter. Compose a tight "
            "shoulder-height side litter close crop or rear three-quarter "
            "exterior story frame with one readable period-local "
            "shoulder-borne palanquin, covered carried litter, or carried chair in foreground "
            "or midground as the "
            "largest non-human object. Show roof or canopy, side panels, "
            "long horizontal carrying poles, cloth curtains, rope ties, mud, "
            "rain wear, and cropped support walkers in the same shoulder-height "
            "crop with road context, terrain, weather, and buildings. "
            "Use a tight shoulder-height side or rear three-quarter travel view with the camera "
            "parallel to the shoulder poles. The carried cabin, canopy, curtains, "
            "and long poles fill the visual center as the dominant subject; "
            "human evidence is secondary load-bearing contact evidence, not the "
            "main image subject. Visible human evidence is limited to the "
            "minimum fragments needed to prove the litter is being carried: "
            "shoulder lines pressed under poles, side/back upper arms, hands "
            "wrapped around poles, folded sleeves, waist sash edges partly "
            "hidden by poles, and narrow moving torso slices crossed by poles. "
            "Walking lower legs or feet appear only as tiny cropped hints if "
            "needed. If a face is visible, it is a small "
            "profile or oblique edge face subordinate to the pole contact. "
            "Support-figure "
            "upper bodies stay small, side/back turned, hidden by the cabin, "
            "behind poles, behind curtains, or cropped at the frame edge. Upper "
            "chest fronts stay outside the readable frame or are physically "
            "crossed by poles, hands, sleeves, straps, curtains, or cabin edges. "
            "Visible cloth fronts are narrow oblique slices crossed by poles, "
            "hands, sleeves, straps, or curtains. "
            "Two long parallel shoulder poles are the only support structure "
            "connecting the carried cabin to the walkers; each pole visibly "
            "crosses support walker shoulder lines at front and rear. "
            "Suspension reads from horizontal shoulder poles and load-bearing "
            "shoulders, with open air, hanging curtain shadow, robe overlap, "
            "mud shadow, and a narrow strip of road dust below the cabin. The "
            "lower cabin edge is cropped or held high in open air, with open "
            "shadow below the suspended body. The lower third contains only empty "
            "shadow gap, road dust, robe hems, and cropped bearer feet at far "
            "edges. The visible load path is pole-to-shoulder-to-hand only, "
            "with the cabin floating above the road as a hanging load. Every visible support "
            "fragment is anatomically connected: the pole rests on the same "
            "figure's shoulder line, the same figure's hand or sleeve "
            "stabilizes it, and that figure's shoulder, sleeve, and hand align "
            "under the same pole load. Carrier and escort torsos "
            "use side, back, rear three-quarter, or oblique three-quarter turns "
            "with the robe front reduced to a narrow moving edge. "
            "Shoulder poles, gripping hands, folded sleeves, straps, or curtains "
            "physically cross the upper body of each readable walker; support walkers "
            "stay behind poles, behind curtains, cropped at the side, or turned "
            "away in staggered depth. Load-bearing proof belongs to shoulder "
            "and hand contact under the poles; any road contact is limited to "
            "small cropped support-walker foot hints while the carried cabin "
            "remains suspended between the shoulder poles. The carried litter "
            "remains the main carried subject, larger than the surrounding "
            "walking people and visibly tied to the carriers. Litter panels "
            "and curtains remain blank material surfaces. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _scene_requests_wheeled_travel_vehicle(prompt):
        return (
            "PRIMARY IMAGE LOCK - first visible subject: the Scene-named "
            "wheeled travel vehicle. Compose a medium or wide exterior story "
            "frame with one readable period-local cart, carriage, wagon, "
            "handcart, ox cart, or other wheeled land vehicle in foreground or "
            "midground as the largest non-human object. Show side panels, "
            "wheels, axle, shafts, rope ties, mud, rain wear, and attendants, "
            "drivers, or guards on the same road and ground plane as the "
            "Scene-named terrain, weather, and buildings. The named vehicle "
            "remains the largest non-human object and the main travel evidence. "
            "Vehicle panels and curtains remain blank "
            "material surfaces. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _scene_requests_mounted_travel(prompt):
        return (
            "PRIMARY IMAGE LOCK - first visible subject: the mounted travel "
            "moment named by the Scene. Compose a medium or wide exterior story "
            "frame with one readable period horse-and-rider pair in foreground "
            "or midground, one rider seated on one horse, visible horse head, "
            "neck, torso, legs, tail, simple tack, and the rider's period "
            "clothing. Additional mounted figures become smaller receding "
            "horse-and-rider silhouettes on the same road, field, riverbank, "
            "gate exterior, shrine-side path, or misty route named by the Scene. "
            "Scene-named banners, shrines, gates, terrain, weather, and road "
            "evidence stay visible beside the mounted path as supporting story "
            "evidence. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _scene_requests_overlooking_view(prompt):
        return (
            "PRIMARY IMAGE LOCK - first visible subject: the named view from "
            "the Scene, not a face-only portrait. Compose a medium or wide "
            "overlooking-view story frame with the person in foreground or "
            "midground, side/back/three-quarter-back angle, posture and gaze "
            "directed toward the valley, city, skyline, river, field, or "
            "landscape named by the Scene. For singular Scene wording such as "
            "a man, a woman, one person, or one named person, the foreground "
            "contains one visible person as the sole human focus. Compose a "
            "solitary one-person-only lookout image: the complete visible human "
            "inventory is exactly one living person total "
            "in the entire frame. Use a single-person-only composition: one "
            "isolated human body, one head, one torso silhouette, one ground "
            "shadow, and one clear ground gap around that person. Distant roads, "
            "paths, village edges, settlement marks, and skyline detail resolve "
            "as empty path, roofs, smoke, fences, carts, rocks, field marks, "
            "terrain texture, or architectural silhouettes. The named view, "
            "settlement, roads, and fields supply all other visual interest as "
            "landscape or building evidence. The view fills most of the frame "
            "with readable depth, horizon, terrain or buildings, natural light, "
            "and atmosphere. The foreground person's visible inventory is "
            "plain period clothing, cloth outer layer, fur cloak edge, belt, sash, bag, or everyday object "
            "named by the Scene and era; hands, waist, back, and hip areas read "
            "as smooth empty clothing, belt, sash, robe fold, or bag surface when the "
            "Scene names no object. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _scene_is_stealth_sleeping_guard_story(prompt):
        return (
            "PRIMARY IMAGE LOCK - first visible subject: the stealth escape "
            "story action named by the Scene. Compose one asymmetrical moonlit "
            "story frame: the sneaking principal person is the only upright "
            "moving human figure, moving side-on or three-quarter-front along "
            "the visible moonlit path, body leaning forward in quiet motion, "
            "one foot stepping, tense eyes looking toward the exit or path. "
            "The principal person's visible hand inventory is two open palms, "
            "visible relaxed fingers, sleeves, and robe cloth. Every other human "
            "figure is a sleeping or drunk watchman in a low inactive pose: "
            "lying horizontally on the floor, reclining against a wall, slumped "
            "low beside the doorway, or collapsed on a mat with closed eyelids, "
            "tilted head, loose arms, and relaxed hands resting on floor or cloth. "
            "The complete secondary human inventory is low bodies only: every "
            "non-principal head stays below the principal person's waistline, "
            "with shoulders touching floor, mat, wall base, or door threshold. "
            "The composition reads as escape past inactive watchmen: diagonal "
            "path, moonlight through the opening, quiet shadow, "
            "separated low bodies, and a clear gap between the moving person and "
            "each sleeping watchman carry the action. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _scene_requests_achaemenid_egyptian_armed_group(prompt):
        return (
            "PRIMARY IMAGE LOCK - first visible subject: the 525 BC "
            "Achaemenid Persian, Pelusium, Nile Delta, or Late Period Egyptian "
            "armed group action named by the Scene. Render a tight close-up collision crop with exactly four readable "
            "chest-up combat figures total, with every human inside the main foreground "
            "action cluster and dust haze behind them. Compose a tight "
            "staggered diagonal chest-up action-cluster story frame, compressed into a close collision-cluster story frame with exactly "
            "four separated chest-up figures at different depths, visible "
            "air gaps between bodies, foreground and midground overlap, alternating forward and rear positions, "
            "cropped edge figures, one shared dust-haze backdrop with small upper strips of desert light, gate edge, river reeds, or wall edge, "
            "and period clothing readable on each figure. The complete visible "
            "human inventory is exactly four readable foreground figures "
            "total, all in the main action cluster; background depth is dust haze, "
            "reeds, gate edges, sky, light, and empty space. The ideal "
            "visible count is four frame-filling chest-up figures; there are "
            "zero readable people behind the cluster. The camera stays close enough "
            "that hips, thighs, knees, shins, legs, and feet are outside the image frame. Frame each readable "
            "figure from head to upper chest so the lower image "
            "edge crosses high upper chest cloth on every person. Faces, headwear, "
            "shoulders, upper chest cloth, forearms, hands, spear shafts, dust, diagonal motion, bracing "
            "shoulders, advancing or recoiling body angles, and one selected "
            "handheld equipment item per readable person carry the action. When "
            "the Scene says clash, battle, battlefield, or defenders, arrange two "
            "compact opposing subgroups facing each other from left and right, "
            "with a clear center collision zone made of crossed spear angles, "
            "dust, turned shoulders, tense faces, and braced upper bodies. When the "
            "Scene says march or advance without clash wording, show implied forward "
            "motion through leaning shoulders, angled spear shafts, tense faces, and dust, "
            "still cropped to head-through-upper-chest scale. Figures use staggered "
            "diagonal depth, uneven heights, compressed overlap, and mixed body turns. "
            "Persian figures show soft "
            "pointed caps or wrapped cloth headgear, soft tunic shoulders, "
            "robe upper folds, woven trim bands, dusty fabric layers, "
            "and one shared handheld equipment class chosen from the Scene. Generic "
            "battlefield wording uses one shared short wooden spear class. Egyptian figures show "
            "white linen upper wraps, headcloths, linen ties, papyrus reeds, mudbrick or "
            "plastered Egyptian gate edges, and Nile Delta dust as the Scene "
            "requires. The formation and setting carry the visible pressure of "
            "the decision. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _is_medieval_central_asian_context(prompt) and _scene_requests_armed_group_or_battle(prompt):
        scene_for_central = scene.lower()
        if re.search(r"\b(throne|ruler|king|shah|emperor|court|palace|surrounded\s+by)\b", scene_for_central):
            subject = (
                "a guarded ruler court scene from the Scene, not a solo armored "
                "guard portrait. Keep the named ruler, throne or seat, and "
                "surrounding guards in one shared interior or courtyard space. "
                "The ruler remains readable as the central political subject; "
                "guards frame him from the sides or rear with smaller bodies, "
                "watching posture, and period-local steppe or Persianate military "
                "dress"
            )
        elif re.search(r"\b(cavalry|horsemen|mounted|riding|horde|charge|charging)\b", scene_for_central):
            subject = (
                "mounted cavalry group action from the Scene, not a single rider "
                "portrait. Keep several riders, horses, tack, dust, steppe ground, "
                "uneven spacing, forward motion, reins, bows or sabers when named, "
                "and a clear shared direction of movement"
            )
        else:
            subject = (
                "medieval Central Asian armed group story action from the Scene, "
                "not a representative solo fighter portrait. Keep the named "
                "warriors, guards, attackers, defenders, fortress, gate, arrows, "
                "horses, dust, smoke, or battlefield pressure visible in one "
                "shared action space"
            )
        return (
            "PRIMARY IMAGE LOCK - first visible subject: "
            f"{subject}. Armed clothing and protection stay local to the stated "
            "12th-13th century Central Asian, Khwarazmian, Otrar, Silk Road, "
            "or Mongol context: deel-like robes, caftans, quilted coats, small "
            "cord-tied lamellar scale rows, leather plates, fur or felt hats, "
            "wrapped turbans or soft caps, leather belts, boots, composite bows, "
            "quivers, sabers, lances, spears, and practical horse tack. No "
            "European plate silhouette, no smooth metal breastplate, no closed "
            "visor helmet, no chest emblem, and no decorative belt medallion. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _is_west_african_ashanti_british_context(prompt) and _scene_requests_armed_group_or_battle(prompt):
        return (
            "PRIMARY IMAGE LOCK - first visible subject: the West African "
            "Ashanti, Asante, Kumasi, Gold Coast, or British colonial armed "
            "group action named by the Scene, not a solo warrior portrait and "
            "not a generic ancient or medieval army. Compose a medium or wide "
            "diagonal action frame with readable opposing motion, dust, smoke, "
            "red-earth ground, tropical vegetation or Kumasi compound edges "
            "when place context requires them, and several separated figures "
            "moving, bracing, charging, recoiling, or clashing according to the "
            "Scene. Asante figures use wrapped cloth war dress, belts, bead or "
            "brass details, shields, spears, muskets, or rifles only where the "
            "Scene implies armed conflict. British colonial troops or officers "
            "use tropical khaki or white drill uniforms, pith or Wolseley "
            "helmets, puttees, boots, belts, and rifles when named. Do not "
            "answer vague words like ancient army with samurai armor, East "
            "Asian tiled roofs, medieval European plate, Roman armor, fantasy "
            "armor, katana, or kimono. The whole image remains one continuous "
            "West African colonial-period action space with stronger emotion "
            "and body motion than a static lineup. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _scene_requests_armed_group_or_battle(prompt):
        if not _scene_names_specific_weapon(prompt):
            return (
                "PRIMARY IMAGE LOCK - first visible subject: one representative "
                "foreground armored survivor from the Scene, medium-close or "
                "waist-up three-quarter action framing, readable face and emotion, "
                "torso angle, shoulders, sleeves, belt or sash edge when visible, "
                "body posture, and clear air around the main silhouette. The "
                "complete visible subject set is one armed role figure, shoulder "
                "clothing, chest protection or military clothing, cloak edge, "
                "smoke, dust, roof edges, thick timber posts, fence rails, mountain haze, and packed "
                "ground. Lower frame corners read as packed dirt, straw "
                "texture, a blunt wooden fence rail with flat cut ends, cloak "
                "edge, or soft smoke shadow. The battlefield remains one continuous physical "
                "space, one camera viewpoint, same ground plane and light. "
                f"Scene: {scene_short}.{context_text}"
            )
        return (
            "PRIMARY IMAGE LOCK - first visible subject: one representative "
            "foreground armed person from the Scene, medium-close or waist-up "
            "three-quarter action framing, one front, side, or three-quarter "
            "face readable, readable eyes and emotion, torso angle, action arm, "
            "and one selected primary weapon item as the only readable weapon prop "
            "in a plausible grip, guard, carry, or braced position, clear air around the main "
            "silhouette. Full-frame readable weapon inventory is one selected "
            "foreground weapon item only. That selected foreground item is the "
            "only pointed metal or weapon silhouette in the readable frame. "
            "The complete visible subject set is one foreground fighter, one "
            "weapon item, hands or sleeves interacting with it, smoke, dust, roof edges, thick timber posts, fence "
            "rails, mountain haze, and packed ground. Background vertical lines "
            "are thick blunt timber posts, fence rails, hut edges, or roof "
            "supports with flat chopped wooden ends. The battlefield remains "
            "one continuous physical space, one camera viewpoint, same ground "
            "plane and light. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _scene_requires_single_character_setting_story(prompt):
        return (
            "PRIMARY IMAGE LOCK - first visible subject: the named person inside "
            "the full Scene-named story setting. "
            "Compose a medium-close or waist-up story frame with the principal "
            "named person in foreground or midground as the largest human "
            "subject, front or three-quarter-front face and eyes readable, "
            "upper body posture visible, and the named road, fork, gate, "
            "threshold, entrance, shrine, temple, exterior terrain, blank "
            "fabric strips, banners, flags, weather, or architecture visible "
            "beside or behind the person in the same physical space. The "
            "frame includes a small off-center edge-on or furled blank cloth "
            "strip tied to a pole or cord when the Scene names banners, flags, "
            "or fabric strips. The "
            "setting evidence must remain readable enough to explain the "
            "decision pressure in the Scene. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _scene_requests_multiple_characters(prompt) and _scene_requests_record_evidence_group(prompt):
        return (
            "PRIMARY IMAGE LOCK - first visible subject: a sealed record group "
            "decision moment from the Scene. Compose a tight chest-to-waist "
            "group crop around the shared hands-and-rolls action center, one "
            "continuous full-frame interior scene, one camera viewpoint, "
            "people overlapping in diagonal depth, mixed side and three-quarter "
            "face angles, visible eyes and readable expressions. Every visible "
            "record object is a compact tied roll cylinder or folded bundle held "
            "in hands; the lamp or table edge appears only near the lower frame "
            "edge. The lower image edge crosses waist sashes or upper hip cloth; "
            "sandals, feet, lower robe hems, and floor-length lower garment "
            "panels stay outside the frame. The upper image edge stays on plain "
            "mid-wall plaster, vertical posts, shutters, or doorway light, with "
            "high wall zones and ceiling-dominant zones outside the crop. "
            "Wall decoration inventory is empty; visible background surfaces "
            "are blank plaster, exposed timber, shutters, blank doors, cracks, "
            "dust, and shadow. Group clothing and carried gear follow the stated "
            "era, place, and Scene roles; front robe panels are continuous "
            "same-color cloth from crossed neckline to sleeve edge; every visible "
            "upper chest remains blank same-color fabric with material texture "
            "only. Hands, sleeves, and compact record rolls overlap the "
            "upper-body area around the shared action center. Each front-facing "
            "person has hands, sleeves, a closed roll, or a folded bundle crossing "
            "the upper torso; figures without a record prop use side turns, "
            "partial overlap, or background placement. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _scene_requests_market_or_bazaar_location(prompt):
        return (
            "PRIMARY IMAGE LOCK - first visible subject: the requested market, "
            "bazaar, merchant street, or caravan trade setting from the Scene, "
            "not a solo face portrait. Compose one continuous human-scale "
            "commercial place view with the Scene-named goods, stalls, awnings, "
            "baskets, jars, cloth bundles, spice piles, metal bowls, weighing "
            "objects, dust, hard side light, and period-correct local architecture "
            "as the readable foreground and midground evidence. People may appear "
            "only as small merchants, buyers, porters, or passersby integrated "
            "into the market space; no single face or torso fills the frame. "
            "Keep the camera at a three-quarter street or stall angle with "
            "visible depth, uneven stall spacing, and blank unmarked material "
            "surfaces. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _scene_requests_bell_object(prompt):
        return (
            "PRIMARY IMAGE LOCK - first visible subject: the requested bell "
            "object from the Scene, not a person, not a doorway, and not a wall "
            "plaque. Compose a close object evidence frame with one ornate "
            "period-local metal bell dominating 80 to 90 percent of the image, "
            "visible rim, clapper, hanger, cord or support, metal wear, vibration "
            "blur, dust rings, and air ripple pressure. Crop out people, guards, "
            "full doors, doorway edges, gates, wall plaques, pottery, banners, "
            "and market background. No human figure, no armored person, no "
            "doorway, no signboard, no plaque, no pottery, no writing, and no "
            "door knobs. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _scene_requests_fortress_attack_action(prompt):
        return (
            "PRIMARY IMAGE LOCK - first visible subject: the fortress attack "
            "action named by the Scene, not a standing guard lineup and not a "
            "posed armor display. Compose a wide or medium-wide exterior action "
            "frame with attackers moving diagonally toward the fortress, gate, "
            "wall, stronghold, or citadel. Show uneven forward motion, bent "
            "knees, angled shoulders, dust, smoke, flame light, arrows in flight "
            "when named, raised bows or spears when named, and the fortress wall "
            "or gate under pressure. Figures are moving through one shared "
            "battle space rather than standing shoulder-to-shoulder. No single "
            "front-facing guard dominates the frame. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _scene_requests_seated_ruler_throne_story(prompt):
        return (
            "PRIMARY IMAGE LOCK - first visible subject: the seated ruler and "
            "the Scene-named throne or seat together, not a face-only portrait. "
            "Compose a medium-close or waist-up three-quarter story frame with "
            "the ruler seated on the visible throne, seat, dais, platform, low timber platform, or "
            "backrest. The throne structure, armrest edge, seat plane, platform "
            "edge, hall shadow, and the ruler's tense posture remain readable in "
            "one shared physical space. Use visible eyes and emotion, but keep "
            "the chair/throne evidence large enough to prove the ruler is seated. "
            "No isolated head-only close-up, no standing portrait, no empty hall, "
            "and no throne replaced by a wall texture. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _scene_requests_multi_character_closeup(prompt):
        return (
            "PRIMARY IMAGE LOCK - first visible subject: the exact multi-person "
            "close-up named by the Scene, not a waist-up group shot. Compose a "
            "tight close crop of the named faces or eyes, with two people only "
            "when the Scene says two, opposing gaze, sharp emotion, hard side "
            "light, narrow period-local background strips, and no extra people. "
            f"Scene: {scene_short}.{context_text}"
        )

    if _scene_requests_explicit_armed_group_standoff(prompt):
        return (
            "PRIMARY IMAGE LOCK - first visible subject: the multiple armed "
            "groups, factions, guards, or opposing sides named by the Scene, not "
            "one representative armored portrait. Compose a shared standoff "
            "frame with at least two readable opposing clusters, side or "
            "three-quarter body turns, visible spacing, readable faces, "
            "period-local armor or guard clothing, and one simple primary weapon "
            "per readable armed person when weapons are named. Protected queens, "
            "rulers, or principal figures named by the Scene stay visible in "
            "front of or between their guards. "
            f"Scene: {scene_short}.{context_text}"
        )

    if prompt_mentions_major_character(prompt):
        if _scene_requests_multiple_characters(prompt):
            military_logistics_group = _scene_requests_military_logistics_or_camp(prompt)
            camp_group = _scene_requests_civilian_work_or_camp(prompt)
            record_evidence_group = bool(
                re.search(
                    r"\b(short\s+sealed\s+cord-tied\s+cream\s+roll\s+cylinder|"
                    r"cord-tied\s+closed\s+cream\s+bundles|folded\s+packets?|"
                    r"rolled\s+bundles?|edge-on\s+bundles?|decrees?|letters?)\b",
                    scene,
                    re.IGNORECASE,
                )
            )
            record_group_crop = (
                "For sealed record or paper-evidence group scenes, make the shared "
                "hands-and-rolls action center the visual anchor: tight chest-to-waist "
                "crop, hands holding compact tied rolls or folded bundles, lamp or "
                "table only at the lower edge, plain mid-wall plaster, vertical "
                "posts, shutters, or doorway light behind the people, and high wall "
                "zones outside the crop. Hands, sleeves, and record rolls overlap "
                "the upper-body area around the action center. "
                if record_evidence_group
                else ""
            )
            group_visible_set = (
                "Visible people use the exact roles named by the Scene. Keep "
                "the named military logistics objects at the group action "
                "center: dark lacquered lamellar armor rolls, rectangular stacks "
                "of small overlapping laced scale layers, cloth-wrapped armor packets, "
                "flat folded armor panels, cord-bound laced armor packets, plain dark "
                "leather armor surfaces, and simple wooden carrying racks when "
                "flat armor stacks or military logistics objects are named by the "
                "Scene. The visible stack texture is layered scale edges, dark "
                "leather, lacquer, cloth wrap, tight cord bands, and hard armor "
                "contours. Weapons appear only when the Scene names a weapon. "
                if military_logistics_group
                else "Every visible torso is civilian cloth work clothing: tunic, "
                "robe, coarse cloak, sash, apron, woven bag, basket strap, and "
                "soft textile folds. Visible hand-held objects are camp work "
                    "objects named by the Scene field, such as straw bundles, rope ties, pottery, "
                "baskets, timber poles, woven mats, sacks, cloth bundles, "
                "wooden digging tools, and shelter materials. Long straight "
                "objects have blunt wooden tool or shelter-pole ends. "
                if camp_group
                else (
                    "Visible hands, waists, backs, and hips show ordinary "
                    "clothing and the everyday, work, household, travel, ritual, "
                    "furniture, or camp objects named by the Scene; when the "
                    "Scene names none, they remain smooth clothing, belt, sash, "
                    "robe, bag, fur cloak edge, or cloth outer-layer surfaces. "
                )
            )
            return (
            "PRIMARY IMAGE LOCK - first visible subject: a close group story moment "
            "from the Scene, one continuous full-frame scene, one camera viewpoint, "
            "shared ground plane, tight waist-up framing, camera placed at "
            "an offset three-quarter angle beside the action center, principal "
            "people overlapping in diagonal depth rather than standing in a row, "
            "mixed side and three-quarter face angles for foreground figures, "
            "visible eyes and readable expressions, unequal body spacing, readable "
            "emotion in posture and gaze, a compact asymmetric cluster around one "
            "action center, one clear action or decision under pressure. Figures "
            "use uneven heights, staggered depth, partial overlap, and mixed "
            "side or three-quarter turns. "
            "The lower image edge crosses waist sashes or upper hip cloth; "
            "sandals, feet, lower robe hems, and floor-length lower garment panels "
            "stay outside the frame. The upper image edge stays on plain mid-wall "
            "plaster, vertical posts, shutters, or open doorway light, with high "
            "wall bands and ceiling-dominant zones outside the crop. "
            "Group clothing and carried gear follow the stated era, place, and "
            "Scene roles. Civilians use plain single-color local fabric; any "
            "Scene-named protective gear follows era-local construction. "
            "Visible cloth and gear surfaces carry material texture, seams, "
            "cords, folds, dust, and wear only. Every visible "
            "upper chest remains blank fabric or Scene-named protective construction "
            "with same-material texture only. Hands, sleeves, "
            "tools, record rolls, or other Scene-named props overlap front-facing "
            "upper-body spaces around the action center. Each front-facing person "
            "has hands, sleeves, a closed roll, or a folded bundle crossing the "
            "upper torso; figures without a record prop use side turns, partial "
            "overlap, or background placement. "
            f"{record_group_crop}"
            "Keep every Scene-named "
            "prop, tool, animal, vehicle, furniture piece, closed tied bundle, "
            "lamp, doorway, or architectural evidence visible in or beside that "
            "same action center. If paper evidence is named, show closed rolls "
            "or folded bundles held edge-on in hands. Each front-facing person "
            "has hands, sleeves, a closed roll, or a folded bundle crossing the "
            "upper torso; figures without a paper prop use side turns, partial "
            "overlap, or background placement. Table surfaces stay bare setting material. "
                f"{group_visible_set}"
                f"Scene: {scene_short}.{context_text}"
            )
        if _scene_explicitly_requests_closeup(prompt):
            return (
                "PRIMARY IMAGE LOCK - first visible subject: solo face close-up portrait shot of the "
                "principal figure from the Scene, extreme tight head-and-shoulders framing, "
                "one visible living human figure, large centered face, eye contact, "
                "visible eyes, natural hairline, neck, a thin shoulder edge, face and "
                "shoulder edge filling roughly 98 percent of the frame, front or "
                "three-quarter-front camera angle, readable emotion, narrow background strip, "
                "clear decision, twisted shoulders, leaning posture, wind-tension in clothing, "
                "dust or shadow pressure around the body. Portrait background is the "
                "narrow Scene-named setting evidence: throne or seat texture, platform "
                "edge, hall wall, room wall, window edge, rain, dust, mountain haze, "
                "or plain earthen wall texture when no setting object is named. "
                "Visible inventory is face, hair, neck, cloth neckline, draped chest edge, shoulder clothing, "
                "and the ordinary object or narrow setting evidence named by the Scene "
                "when one is named. "
                f"Scene: {scene_short}.{context_text}"
            )
        return (
            "PRIMARY IMAGE LOCK - first visible subject: the principal figure "
            "from the Scene in a story-action frame, not a face-only portrait. "
            "Compose a medium, waist-up, knee-up, three-quarter-body, or full-body "
            "shot selected by the Scene. Keep the readable face, body angle, "
            "shoulders, hands or sleeves, posture, clothing tension, and "
            "Scene-named prop, seat, threshold, road, architecture, weather, or "
            "landscape evidence visible together. Use side, three-quarter, "
            "over-shoulder, low-angle, or diagonal framing when it fits the "
            "narration. Emotion and dialogue read through expression, stance, "
            "gesture, distance to objects, light, dust, rain, smoke, or shadow "
            "pressure inside one continuous physical setting. "
            f"Scene: {scene_short}.{context_text}"
        )

    scene_lower = scene.lower()
    if re.search(r"\b(egg|birth|newborn)\b", scene_lower):
        subject = (
            "chest-up close-up portrait of an adult mother figure, anxious visible "
            "eyes, warm golden birth light rising from below the frame and "
            "illuminating her face, one camera viewpoint, single uninterrupted "
            "full-frame scene, plain dark earthen room, sacred-birth tension"
        )
    elif re.search(r"\b(book|books|document|documents|manuscript|manuscripts|codex|ledger|journal|scripture|tablet|tablets|paper|papers|papyrus|parchment|scroll|scrolls)\b", scene_lower):
        subject = (
            "the requested blank book, document, manuscript, tablet, or scroll "
            "object from the Scene as the dominant subject, resting on a visible "
            "period-correct surface, unmarked cover or pages, cord binding or "
            "local material edges when era-appropriate, dust, wear, and hard "
            "directional light"
        )
    elif _scene_requests_planning_board_object(prompt):
        subject = (
            "the requested blank tabletop planning board from the Scene as the "
            "dominant subject, resting on a low period-correct table, plain wood "
            "or cloth surface, loose cord paths, small stone weights, bronze "
            "markers, dust, hard side light, and empty material margins"
        )
    elif _scene_requests_group_planning_surface(prompt):
        subject = (
            "the shared council planning evidence on a blank low horizontal "
            "planning surface from the Scene, with people represented only by "
            "cropped hands, fingertips, sleeves, forearm edges, and hand shadows around the "
            "surface edges, while walls, windows, doorways, ceiling, faces, "
            "heads, shoulders, torsos, and full people stay outside frame. "
            "The planning evidence is bare "
            "wood, cloth, mat, or clay with loose route cords crossing three "
            "separated marker clusters, at least seven separated stone markers, "
            "one palm-sized bronze weight or pin, candlelight, hand shadows, "
            "dust, and blank material margins only"
        )
    elif re.search(r"\b(palace|hall|room|court|gate|fortress|tower|building)\b", scene_lower):
        subject = (
            "the requested architectural space from the Scene as the dominant "
            "subject, period-correct walls, roof structure, threshold, furniture "
            "or courtyard elements when named, blank unmarked material surfaces, "
            "one continuous camera viewpoint, hard diagonal light, and visible "
            "spatial tension"
        )
    elif _scene_requests_map_object(prompt):
        subject = (
            "the requested geographic planning evidence from the Scene as a low "
            "horizontal tactile marker layout on a plain low wooden table "
            "surface, floor mat, clay slab, cloth planning surface, or "
            "ground-level tabletop surface. The physical marker layout dominates "
            "the full frame from a top-down or close three-quarter tabletop "
            "camera view: one loose route cord, two separated stone clusters, "
            "and one bronze weight, pin, or folded cloth strip rest on the "
            "horizontal surface. Regional control and faction pressure are shown "
            "by marker positions, cord paths, clusters, shadows, and light on "
            "plain natural material. Lower-left, lower-right, bottom, and corner "
            "zones are plain material margins made from broad dust, grain, "
            "shadow, and wear. This is a tight tactile marker layout shot with "
            "the camera remaining on the tabletop surface"
        )
    elif re.search(r"\b(territory|border|route|kingdom|buyeo|expanding)\b", scene_lower):
        subject = (
            "the requested territory, border, route, kingdom, or geography from "
            "the Scene rendered as human-scale physical terrain evidence: "
            "unmarked ground, stones, cord markers, low grass, horizon, river, "
            "road, or settlement cues when named, one continuous outdoor view, "
            "clear geography without readable labels"
        )
    elif _EMPTY_ATMOSPHERE_SCENE_RE.search(scene):
        subject = (
            "an empty period-correct setting from the Scene as the dominant "
            "subject: packed-earth ground, rough timber-and-thatch buildings or "
            "plain interior walls when the Scene implies settlement, fallen dead "
            "leaves drifting or resting on the ground when named, still air, "
            "hard directional light, soft shadows, dust, rain, smoke, or mist "
            "when named, one continuous unoccupied camera viewpoint"
        )
    elif re.search(r"\b(landscape|mountain|river|valley|field|cloud|forest)\b", scene_lower):
        subject = (
            "empty establishing landscape dominating the full frame: steep rocky "
            "mountain slopes, valley floor, riverbank or field edge when named, "
            "low grass, packed dirt path, scattered wet stones, empty "
            "timber-and-thatch huts when settlement context is needed, hard "
            "directional light, distant mountain haze as soft background pressure"
        )
    else:
        subject = (
            "one close foreground evidence object under hard directional light, visible "
            "pressure, consequence, and story tension"
        )
    return (
        "PRIMARY IMAGE LOCK - first visible subject: "
        f"{subject}. Scene: {scene_short}.{context_text}"
    )


def _prepend_primary_image_lock(prompt: str) -> str:
    p = (prompt or "").strip()
    lock = _primary_image_lock(p)
    if not p or not lock:
        return p
    if p.startswith(REFERENCE_STYLE_PREFIX):
        rest = p[len(REFERENCE_STYLE_PREFIX):].lstrip()
        return REFERENCE_STYLE_PREFIX + lock + " || " + rest
    return lock + " || " + p


def prompt_mentions_major_character(prompt: str) -> bool:
    """Return True only when the actual cut scene shows a human/character."""
    p = prompt or ""
    scene = _prompt_field(p, "Scene")
    subject = _prompt_field(p, "Main subject")
    if _scene_requests_generic_object_evidence(p):
        return False
    if _scene_is_inanimate_statue_object_without_living_people(p):
        return False
    if _scene_is_depicted_people_on_object_without_living_people(p):
        return False
    if scene and (_EMPTY_LOCATION_SCENE_RE.search(scene) or _EMPTY_NONHUMAN_ATMOSPHERE_SCENE_RE.search(scene)):
        return False
    if scene and _scene_requests_civilian_work_or_camp(p):
        return True
    if scene and (_scene_has_named_character_action(scene) or _scene_requests_multiple_characters(p)):
        return True
    if subject and _CHARACTER_SCENE_RE.search(subject):
        if not scene or not _NON_CHARACTER_SCENE_RE.search(scene):
            return True
    return False


def _scene_requests_multiple_characters(prompt: str) -> bool:
    if _scene_requests_generic_object_evidence(prompt):
        return False
    if _scene_is_inanimate_statue_object_without_living_people(prompt):
        return False
    if _scene_is_depicted_people_on_object_without_living_people(prompt):
        return False
    scene = _scene_text(prompt)
    if scene and (_EMPTY_LOCATION_SCENE_RE.search(scene) or _EMPTY_NONHUMAN_ATMOSPHERE_SCENE_RE.search(scene)):
        return False
    return bool(_MULTI_CHARACTER_SCENE_RE.search(scene) or _scene_mentions_multiple_named_people(scene))


def _scene_requests_record_evidence_group(prompt: str) -> bool:
    scene = _scene_text(prompt)
    return bool(
        scene
        and re.search(
            r"\b(short\s+sealed\s+cord-tied\s+cream\s+roll\s+cylinder|"
            r"cord-tied\s+closed\s+cream\s+bundles|folded\s+packets?|"
            r"rolled\s+bundles?|edge-on\s+bundles?|documents?|decrees?|letters?)\b",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_has_formal_role_terms(scene: str) -> bool:
    return bool(
        re.search(
            r"\b(court|courts|courtiers?|officials?|officers?|administrators?|governors?|commissioners?|messengers?|retainers?|servants?|"
            r"palace|hall|office|council|ritual|petition|petitions|document|documents|"
            r"scroll|scrolls|blinds|threshold|gate|ruler|king|queen|emperor|empress)\b|"
            r"(궁정|조정|관리|신하|사자|시종|궁궐|왕궁|전각|회랑|의식|문서|두루마리|"
            r"청원|발|문턱|문|왕|황제)",
            scene or "",
            re.IGNORECASE,
        )
    )


def _scene_requests_formal_role_layout(prompt: str) -> bool:
    scene = _scene_text(prompt)
    return bool(_scene_has_formal_role_terms(scene) and _scene_requests_humans(prompt))


def _scene_requests_split_side_layout(prompt: str) -> bool:
    scene = _scene_text(prompt)
    return bool(
        re.search(
            r"\b(two\s+(?:dirt\s+)?roads?\s+divide|roads?\s+divide|fork(?:ed)?\s+road|"
            r"one\s+side\b.*\b(?:the\s+)?other\b|between\b.*\band\b|"
            r"choos(?:e|es|ing)\s+between\b.*\band\b|"
            r"turn(?:s|ed|ing)?\s+away\s+from\b.*\btoward\b|"
            r"inside\b.*\boutside\b|outside\b.*\binside\b|separated\s+by|threshold)\b|"
            r"(갈림길|두\s*갈래|양쪽|한쪽|반대쪽|사이에|문턱|경계)",
            scene,
            re.IGNORECASE | re.DOTALL,
        )
    )


def _scene_requests_mount_or_animal(prompt: str) -> bool:
    return bool(_MOUNT_OR_ANIMAL_SCENE_RE.search(_scene_text(prompt)))


def _scene_requests_named_banner_or_flag(prompt: str) -> bool:
    scene = _scene_text(prompt)
    return bool(
        re.search(
            r"\b(banners?|flags?|standards?|cloth\s+standards?)\b|깃발|군기|기치",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_requests_banner_evidence_without_living_people(prompt: str) -> bool:
    scene = _scene_text(prompt)
    if not scene or not _scene_requests_named_banner_or_flag(prompt):
        return False
    if re.search(
        r"\b(?:person|people|men|women|soldiers?|warriors?|guards?|riders?|"
        r"messengers?|envoys?|king|ruler|commander|troops?|army|crowd|"
        r"faces?|bodies?|hands?)\b|"
        r"(사람|인물|병사|군사|전사|호위|기병|사신|전령|왕|군대|무리|얼굴|손)",
        scene,
        re.IGNORECASE,
    ):
        return False
    return True


def _scene_requests_maritime_landing(prompt: str) -> bool:
    scene = _scene_text(prompt)
    return bool(
        re.search(
            r"\b(boats?|ships?|wooden\s+hulls?|hulls?|beach|shoreline|coast|"
            r"landing|jumping\s+off\s+boats?|onto\s+a\s+beach|torches?|swords?)\b",
            scene,
            re.IGNORECASE,
        )
        and re.search(
            r"\b(boats?|ships?|wooden\s+hulls?|hulls?|beach|shoreline|coast|"
            r"landing|jumping\s+off\s+boats?|onto\s+a\s+beach)\b",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_requests_mounted_travel(prompt: str) -> bool:
    scene = _scene_text(prompt)
    return bool(
        re.search(
            r"\b(horse|horses|pony|mounted|riding|ride|rider|riders|cavalry|"
            r"horseman|horsemen|mare|stallion)\b|말|기마|타고|타는|기수|기병",
            scene,
            re.IGNORECASE,
        )
        or re.search(
            r"\b(?:couriers?|messengers?|envoys?|riders?)\b[^.;|]{0,80}\bmount(?:s|ing|ed)?\b|"
            r"\bmount(?:s|ing|ed)?\b[^.;|]{0,80}\b(?:couriers?|messengers?|envoys?|riders?)\b",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_requests_carried_travel_vehicle(prompt: str) -> bool:
    scene = _scene_text(prompt)
    return bool(
        re.search(
            r"\b(palanquin|sedan\s+chair|litter|carried\s+chair)\b|가마",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_requests_wheeled_travel_vehicle(prompt: str) -> bool:
    scene = _scene_text(prompt)
    return bool(
        re.search(
            r"\b(cart|carriage|wagon|handcart|ox\s+cart|oxcart|"
            r"wheeled\s+vehicle)\b|수레|마차",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_requests_travel_vehicle(prompt: str) -> bool:
    return bool(
        _scene_requests_carried_travel_vehicle(prompt)
        or _scene_requests_wheeled_travel_vehicle(prompt)
    )


def _scene_requests_landscape(prompt: str) -> bool:
    if _scene_requests_map_object(prompt):
        return False
    return bool(
        re.search(
            r"\b(landscape|mountain|mountains|river|riverbank|valley|field|fields|cloud|forest)\b|"
            r"산|계곡|강|강가|들판|숲|구름",
            _scene_text(prompt),
            re.IGNORECASE,
        )
    )


def _scene_requests_paper_evidence(prompt: str) -> bool:
    scene = _scene_text(prompt)
    return bool(
        _BOOK_OBJECT_RE.search(scene or "")
        or re.search(
            r"\b(cord-tied\s+closed\s+cream\s+bundles?|folded\s+packets?|"
            r"rolled\s+bundles?|bundle\s+spines?|tied\s+cord\s+knots?)\b",
            scene or "",
            re.IGNORECASE,
        )
    )


def _scene_requests_entry_facade_surface_guard(prompt: str) -> bool:
    scene = _scene_text(prompt)
    return bool(
        re.search(
            r"\b(shrine|temple|roadside|wayside|waystation|sanctuary|chapel|altar)\b|"
            r"신사|사찰|절|사당|제단",
            scene or "",
            re.IGNORECASE,
        )
    )


def _scene_requests_cloth_evidence(prompt: str) -> bool:
    scene = _scene_text(prompt)
    return bool(
        re.search(
            r"\b(cloth\s+panels?|fabric\s+panels?|vertical\s+cloth|hanging\s+cloth|"
            r"curtains?|fabric\s+curtains?|banners?|flags?|"
            r"(?:edge-on\s+|furled\s+)?blank\s+cloth\s+strips?|"
            r"cloth\s+evidence)\b|"
            r"깃발|천막|천\s*패널|휘장",
            scene or "",
            re.IGNORECASE,
        )
    )


def _scene_is_stealth_sleeping_guard_story(prompt: str) -> bool:
    scene = _scene_text(prompt)
    if not scene:
        return False
    has_stealth_motion = bool(
        re.search(
            r"\b(sneak|sneaks|sneaking|slip|slips|slipping|creep|creeps|creeping|"
            r"escape|escapes|escaping|flee|flees|fleeing|away|path)\b",
            scene,
            re.IGNORECASE,
        )
    )
    has_inactive_guard = bool(
        re.search(r"\b(sleeping|asleep|drunk|drunken|unconscious|drowsy)\b", scene, re.IGNORECASE)
        and re.search(r"\b(guard|guards|watchman|watchmen|soldier|soldiers)\b", scene, re.IGNORECASE)
    )
    return bool(has_stealth_motion and has_inactive_guard)


def _scene_requests_armed_figures(prompt: str) -> bool:
    if _scene_requests_generic_object_evidence(prompt):
        return False
    scene = _scene_text(prompt)
    if (
        re.search(
            r"\b(ruined\s+battlefield|storm\s+clouds?|stormy\s+sky|closing\s+shot|dark\s+closing\s+shot)\b",
            scene,
            re.IGNORECASE,
        )
        and re.search(r"\bbattlefield\b", scene, re.IGNORECASE)
        and not re.search(r"\b(clashing|fighting|charging|attacking|active\s+combat|soldiers?\s+fighting)\b", scene, re.IGNORECASE)
    ):
        return False
    if _scene_is_depicted_people_on_object_without_living_people(prompt):
        return False
    if _scene_is_animal_focused_without_people(prompt):
        return False
    if _scene_is_stealth_sleeping_guard_story(prompt):
        return False
    if _scene_requests_bow_without_arrow_action(prompt):
        return False
    if _scene_requests_overlooking_view(prompt) and not _scene_names_specific_weapon(prompt):
        return False
    if (
        _is_medieval_japanese_context(prompt)
        and not _scene_names_specific_weapon(prompt)
        and not _scene_requests_medieval_japanese_protective_dress(prompt)
    ):
        return False
    if (
        _scene_has_formal_role_terms(scene)
        and not _scene_names_specific_weapon(prompt)
        and not re.search(
            r"\b(battle|battlefield|combat|clash|charge|charging|attack|attacking|"
            r"fight|fighting|strike|striking|shoot|shooting|aim|aiming|grip|gripping|"
            r"hold|holding|raise|raising)\b|전투|전장|돌격|공격|교전|겨냥|사격|쏘|들고|쥐고",
            scene,
            re.IGNORECASE,
        )
    ):
        return False
    return bool(_ARMED_FIGURE_SCENE_RE.search(scene))


def _scene_requests_armed_group_or_battle(prompt: str) -> bool:
    if _scene_requests_generic_object_evidence(prompt):
        return False
    if _scene_is_depicted_people_on_object_without_living_people(prompt):
        return False
    if _scene_is_animal_focused_without_people(prompt):
        return False
    if _scene_is_stealth_sleeping_guard_story(prompt):
        return False
    if _scene_requests_overlooking_view(prompt) and not _scene_names_specific_weapon(prompt):
        return False
    if (
        _is_medieval_japanese_context(prompt)
        and not _scene_names_specific_weapon(prompt)
        and not _scene_requests_medieval_japanese_protective_dress(prompt)
    ):
        return False
    scene = _scene_text(prompt)
    if (
        _scene_has_formal_role_terms(scene)
        and not _scene_names_specific_weapon(prompt)
        and not re.search(
            r"\b(battle|battlefield|combat|clash|charge|charging|attack|attacking|"
            r"fight|fighting|strike|striking|shoot|shooting|aim|aiming|grip|gripping|"
            r"hold|holding|raise|raising)\b|전투|전장|돌격|공격|교전|겨냥|사격|쏘|들고|쥐고",
            scene,
            re.IGNORECASE,
        )
    ):
        return False
    return bool(_ARMED_GROUP_OR_BATTLE_SCENE_RE.search(scene))


def _scene_requests_achaemenid_egyptian_armed_group(prompt: str) -> bool:
    if not _is_achaemenid_egyptian_context(prompt):
        return False
    if _scene_is_stealth_sleeping_guard_story(prompt):
        return False
    scene = _scene_text(prompt)
    return bool(
        _scene_requests_armed_figures(prompt)
        and (
            _scene_requests_multiple_characters(prompt)
            or _ARMED_FORMATION_GROUP_SCENE_RE.search(scene)
        )
    )


def _scene_names_specific_weapon(prompt: str) -> bool:
    return bool(_SPECIFIC_WEAPON_SCENE_RE.search(_scene_text(prompt)))


def _scene_requests_bow_without_arrow_action(prompt: str) -> bool:
    scene = _scene_text(prompt)
    has_bow = bool(re.search(r"\b(bow|bows)\b|활", scene, re.IGNORECASE))
    has_arrow_action = bool(
        re.search(
            r"\b(arrow|arrows|shoot|shooting|aim|aiming|target|long-distance)\b|"
            r"화살|사격|쏘|겨냥|백보|100보",
            scene,
            re.IGNORECASE,
        )
    )
    return has_bow and not has_arrow_action


def _scene_requests_market_or_bazaar_location(prompt: str) -> bool:
    scene = _scene_text(prompt)
    if not scene:
        return False
    if _scene_requests_armed_group_or_battle(prompt):
        return False
    if _scene_has_named_character_action(scene):
        return False
    return bool(_MARKET_OR_BAZAAR_LOCATION_SCENE_RE.search(scene))


def _scene_requests_fortress_attack_action(prompt: str) -> bool:
    scene = _scene_text(prompt)
    if not scene:
        return False
    return bool(
        re.search(
            r"\b(attack|attacks|attacking|charge|charging|assault|assaulting|"
            r"storm|storming|flaming\s+arrows?|arrows?\s+in\s+the\s+sky)\b",
            scene,
            re.IGNORECASE,
        )
        and re.search(
            r"\b(fortress|fortresses|gate|gates|wall|walls|stronghold|"
            r"citadel|castle)\b|성벽|성문|요새|성채",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_requests_bell_object(prompt: str) -> bool:
    scene = _scene_text(prompt)
    if not scene:
        return False
    return bool(
        re.search(r"\b(bell|bells)\b|종", scene, re.IGNORECASE)
        and not re.search(
            r"\b(person|people|man|woman|guard|guards|soldier|soldiers|"
            r"warrior|warriors|rider|riders|crowd|group)\b|"
            r"(사람|인물|경비|병사|전사|군중)",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_requests_civilian_work_or_camp(prompt: str) -> bool:
    return bool(
        _CIVILIAN_WORK_OR_CAMP_SCENE_RE.search(_scene_text(prompt))
        and not _scene_requests_military_logistics_or_camp(prompt)
        and not _scene_requests_armed_figures(prompt)
    )


def _scene_requests_military_logistics_or_camp(prompt: str) -> bool:
    scene = _scene_text(prompt)
    if not scene:
        return False
    has_camp_or_logistics = bool(
        re.search(
            r"\b(camp|field\s+camp|baggage|supplies|supply|bundle|bundles|"
            r"packet|packets|arrival|arrive|arrives|arriving|retreat|"
            r"retreating|make\s+space|making\s+space)\b",
            scene,
            re.IGNORECASE,
        )
    )
    has_military_role_or_equipment = bool(
        re.search(
            r"\b(warrior|warriors|samurai|soldier|soldiers|officer|officers|guard|guards|"
            r"fighter|fighters|retainer|retainers|armor|armour|armored|"
            r"armoured|lamellar|kozane|military)\b",
            scene,
            re.IGNORECASE,
        )
    )
    has_combat_action = bool(
        re.search(
            r"\b(battle|battlefield|combat|clash|charge|charging|attack|"
            r"attacking|fight|fighting|strike|striking|shoot|shooting|"
            r"aim|aiming)\b|전투|전장|돌격|공격|교전|겨냥|사격|쏘",
            scene,
            re.IGNORECASE,
        )
    )
    return bool(has_camp_or_logistics and has_military_role_or_equipment and not has_combat_action)


def _scene_requests_military_role_or_armor(prompt: str) -> bool:
    if _scene_is_depicted_people_on_object_without_living_people(prompt):
        return False
    if _scene_is_animal_focused_without_people(prompt):
        return False
    if _scene_is_stealth_sleeping_guard_story(prompt):
        return False
    scene = _scene_text(prompt)
    return bool(
        re.search(
            r"\b(samurai|warrior|warriors|soldier|soldiers|officer|officers|guard|guards|"
            r"escort|escorts|fighter|fighters|retainer|retainers|commander|armor|armour|"
            r"armored|armoured|lamellar|kozane|military|battlefield|war\s+camp|"
            r"military\s+road)\b|"
            r"(무사|전사|군인|병사|호위|장수|갑옷|군사|전장)",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_explicitly_names_protective_torso_gear(prompt: str) -> bool:
    scene = _scene_text(prompt or "")
    return bool(
        re.search(
            r"\b(armor|armour|armored|armoured|cuirass|breastplate|lamellar|kozane|"
            r"scale\s+armor|mail|chainmail|protective\s+torso\s+gear)\b|"
            r"(갑옷|흉갑|찰갑|비늘갑옷)",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_requests_combat_action(prompt: str) -> bool:
    scene = _scene_text(prompt or "")
    return bool(
        re.search(
            r"\b(battle|battlefield|combat|clash|charge|charging|attack|attacking|"
            r"fight|fighting|strike|striking|shoot|shooting|aim|aiming|"
            r"ambush|raid|pursuit|duel|skirmish|siege)\b|"
            r"전투|전장|돌격|공격|교전|겨냥|사격|쏘|매복|추격|공성",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_requests_medieval_japanese_protective_dress(prompt: str) -> bool:
    has_medieval_japanese_context = bool(
        _is_medieval_japanese_context(prompt)
        or "PERIOD-LOCAL JAPANESE COSTUME AND ARMOR LOCK" in (prompt or "")
        or "PERIOD-LOCAL JAPANESE MARTIAL CLOTHING LOCK" in (prompt or "")
        or "PERIOD-LOCAL JAPANESE COURT AND CIVILIAN COSTUME LOCK" in (prompt or "")
    )
    return bool(
        has_medieval_japanese_context
        and (
            _scene_explicitly_names_protective_torso_gear(prompt)
            or _scene_requests_combat_action(prompt)
        )
    )


def _scene_requests_empty_atmosphere(prompt: str) -> bool:
    return bool(
        _EMPTY_ATMOSPHERE_SCENE_RE.search(_scene_text(prompt))
        and not _scene_requests_humans(prompt)
    )


def _scene_explicitly_requests_closeup(prompt: str) -> bool:
    scene = _scene_text(prompt or "")
    return bool(
        re.search(
            r"\b(close[-\s]*up|portrait|face[-\s]*only|head[-\s]*and[-\s]*shoulders|bust)\b",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_requests_single_character_visible_action(prompt: str) -> bool:
    scene = _scene_text(prompt or "")
    if not scene or _scene_explicitly_requests_closeup(prompt):
        return False
    if _scene_requests_generic_object_evidence(prompt):
        return False
    if _scene_requests_multiple_characters(prompt):
        return False
    return bool(
        re.search(
            r"\b(holding\s+(?:his|her|their)\s+head|clutching\s+(?:his|her|their)\s+head|"
            r"pressing\s+(?:a\s+)?hand\s+to|touching\s+(?:his|her|their)\s+temple|"
            r"slamming|clenching|clutching|clutches|clutched|carrying|carries|"
            r"carried|holding|holds|held|gripping|grips|gripped|grabbing|"
            r"grabbed|cradling|raising|pointing|reaching|kneeling|sitting|seated|"
            r"bowing|running|fleeing|walking|turning|leaning|hunched|crouching|"
            r"shouting|arguing|pleading|whispering|crying|weeping|glaring|"
            r"staring|looking|watching|hesitating|flinching|recoiling|charging|"
            r"lunging|swinging|blocking|shielding|drawing|wearing)\b|"
            r"(머리.*감싸|머리.*붙잡|주먹|무릎|달려|걷|돌아|기울|외치|소리치|"
            r"울|흐느끼|노려|바라|주시|망설|물러|피하|돌격|휘두르|막아)",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_needs_action_object_environment_evidence(prompt: str) -> bool:
    scene = _scene_text(prompt or "")
    if not scene or _scene_requests_generic_object_evidence(prompt):
        return False
    return bool(
        re.search(
            r"\b(holding|holds|held|clutching|clutches|clutched|carrying|carries|"
            r"carried|gripping|grips|gripped|dragging|pulling|pushing|raising|"
            r"pointing|reaching|running|fleeing|walking|kneeling|bowing|fighting|"
            r"charging|recoiling|watching|household\s+goods|personal\s+belongings|"
            r"bundle|box|basket|sack|smoke|soot|ash|embers?|flames?|fire|burning|"
            r"burned|rain|storm|snow|snowy|border|frontier|dust|mud|blood|tears?|ruin|damage)\b|"
            r"(들고|붙잡|움켜|쥐고|나르|끌고|밀고|달려|도망|걷|무릎|절|싸우|"
            r"돌격|물러|바라|연기|그을음|재|불씨|불길|화재|불타|비|폭풍|먼지|"
            r"진흙|피|눈물|폐허|파괴)",
            scene,
            re.IGNORECASE,
        )
    )


def _is_confirmed_adult_female_context(prompt: str) -> bool:
    p = prompt or ""
    if _scene_is_inanimate_statue_object_without_living_people(p):
        return False
    if not _scene_requests_humans(p) and not prompt_mentions_major_character(p):
        return False
    detection_text = " ".join(
        part
        for part in (
            _scene_text(p),
            _prompt_field(p, "Main subject"),
            _prompt_field(p, "Scene evidence"),
        )
        if part
    )
    for pattern, fact in _KNOWN_SCENE_IDENTITY_FACTS:
        if pattern.search(detection_text) or fact in p:
            detection_text = f"{detection_text} {fact}".strip()
    if re.search(
        r"\b(girl|child|kid|teen|teenage|minor|schoolgirl|daughter)\b|"
        r"(소녀|아이|어린|미성년|청소년|딸)",
        detection_text,
        re.IGNORECASE,
    ):
        return False
    return bool(
        re.search(
            r"\b(adult\s+woman|adult\s+women|adult\s+female|adult\s+females|"
            r"woman|women|female\s+subject|female\s+character|queen|empress|"
            r"princess|mother|noblewoman|priestess|soseono|yuhwa|"
            r"yaa\s+asantewaa|asantewaa)\b|"
            r"(성인\s*여성|여성|여자|여인|왕비|여왕|공주|어머니|소서노|유화)",
            detection_text,
            re.IGNORECASE,
        )
    )


def _append_adult_female_appeal_guard(prompt: str) -> str:
    p = (prompt or "").strip()
    if not p or "ADULT FEMALE APPEAL AND BODY SILHOUETTE LOCK" in p:
        return p
    if not _is_confirmed_adult_female_context(p):
        return p
    return p + ADULT_FEMALE_APPEAL_BODY_DIRECTIVE


def _scene_names_outdoor_location(prompt: str) -> bool:
    text = " ".join(
        part for part in (_scene_text(prompt), _prompt_field(prompt, "Exact place")) if part
    )
    return bool(
        re.search(
            r"\b(riverbank|river\s+bank|road|roads|path|paths|route|routes|"
            r"street|streets|lane|lanes|alley|alleys|junction|crossroads|"
            r"townhouse\s+district|shopfront\s+lane|field|valley|mountain|"
            r"shoreline|battlefield|camp|encampment|camp\s+exterior|camp\s+edge|"
            r"military\s+camp|gate\s+exterior|courtyard|forest|coast|harbor|"
            r"harbour|hill|ridge|slope|plain|plain\s+outside|outside)\b|"
            r"강변|길|거리|골목|교차로|갈림길|들판|계곡|산|해안|전장|진영|야영지|마당|숲|항구|언덕|능선|밖",
            text,
            re.IGNORECASE,
        )
    )


def _scene_requires_single_character_setting_story(prompt: str) -> bool:
    p = prompt or ""
    scene = _scene_text(p)
    if not scene or not prompt_mentions_major_character(p):
        return False
    if _scene_requests_multiple_characters(p):
        return False
    if _scene_requests_overlooking_view(p) or _scene_requests_mounted_travel(p):
        return False
    if re.search(r"\b(close[-\s]*up|portrait|face[-\s]*only|head[-\s]*and[-\s]*shoulders)\b", scene, re.IGNORECASE):
        return False
    has_named_setting_evidence = bool(
        _scene_requests_split_side_layout(p)
        or _scene_requests_entry_facade_surface_guard(p)
        or _scene_requests_cloth_evidence(p)
        or _scene_names_outdoor_location(p)
        or re.search(
            r"\b(road|roads|fork|forked\s+road|gate|gates|threshold|doorway|"
            r"entrance|shrine|temple|wayside|waystation|banner|banners|flag|"
            r"flags|cloth\s+panel|cloth\s+panels|vertical\s+cloth|exterior|"
            r"courtyard|bridge|riverbank|field|misty\s+route|military\s+road)\b|"
            r"(길|갈림길|문|성문|관문|문턱|사당|절|깃발|현수막|마당|다리|강변)",
            scene,
            re.IGNORECASE,
        )
    )
    has_decision_or_pressure_action = bool(
        re.search(
            r"\b(between|stare|stares|staring|watch|watches|watching|pause|"
            r"pauses|turn|turns|turning|clench|clenches|clenching|stand|"
            r"stands|standing|face|faces|facing|approach|approaches|"
            r"approaching|arrive|arrives|arriving)\b|"
            r"(사이에|바라|주시|멈춰|돌아|선다|서서|다가|도착)",
            scene,
            re.IGNORECASE,
        )
    )
    return bool(has_named_setting_evidence and has_decision_or_pressure_action)


def _scene_requests_non_armed_humans(prompt: str) -> bool:
    return bool(_scene_requests_humans(prompt) and not _scene_requests_armed_figures(prompt))


def _scene_requests_humans(prompt: str) -> bool:
    if _scene_requests_generic_object_evidence(prompt):
        return False
    if _scene_is_inanimate_statue_object_without_living_people(prompt):
        return False
    if _scene_is_depicted_people_on_object_without_living_people(prompt):
        return False
    if _scene_is_animal_focused_without_people(prompt):
        return False
    if _scene_is_stealth_sleeping_guard_story(prompt):
        return True
    if _scene_requests_mounted_travel(prompt):
        return True
    scene = _scene_text(prompt)
    if scene and (_EMPTY_LOCATION_SCENE_RE.search(scene) or _EMPTY_NONHUMAN_ATMOSPHERE_SCENE_RE.search(scene)):
        return False
    if (
        _scene_requests_carried_travel_vehicle(prompt)
        and re.search(
            r"\b(support[-\s]*walkers?|carrier\s+(?:faces|evidence|torsos)|"
            r"cropped\s+support[-\s]*walker|escort\s+silhouettes?)\b",
            scene,
            re.IGNORECASE,
        )
    ):
        return True
    return bool(
        _scene_has_named_character_action(scene)
        or _scene_requests_multiple_characters(prompt)
        or _MULTI_CHARACTER_SCENE_RE.search(scene)
        or _CIVILIAN_WORK_OR_CAMP_SCENE_RE.search(scene)
        or _ARMED_GROUP_OR_BATTLE_SCENE_RE.search(scene)
    )


def _scene_is_animal_focused_without_people(prompt: str) -> bool:
    scene = _scene_text(prompt)
    return bool(
        scene
        and _ANIMAL_FOCUS_SCENE_RE.search(scene)
        and not _EXPLICIT_HUMAN_OR_COMBATANT_SCENE_RE.search(scene)
    )


def _scene_names_animal_wearable(prompt: str) -> bool:
    scene = _scene_text(prompt)
    return bool(
        re.search(
            r"\b(collar|collars|leash|leashes|harness|harnesses|saddle|saddles|"
            r"blanket|blankets|clothing|clothes|tag|tags|bell|bells|jewelry|"
            r"jewellery|decorative\s+gear|animal\s+gear|tack)\b|"
            r"(목걸이|목줄|하네스|안장|담요|옷|방울|장식)",
            scene,
            re.IGNORECASE,
        )
    )


def _scene_is_depicted_people_on_object_without_living_people(prompt: str) -> bool:
    scene = _scene_text(prompt)
    if not scene or not _VISUAL_SURFACE_OBJECT_RE.search(scene):
        return False
    depiction_match = _DEPICTION_VERB_RE.search(scene)
    if not depiction_match:
        return False
    living_prefix = scene[: depiction_match.start()]
    return not (
        _CHARACTER_SCENE_RE.search(living_prefix)
        or _MULTI_CHARACTER_SCENE_RE.search(living_prefix)
        or _scene_mentions_multiple_named_people(living_prefix)
    )


def _non_character_evidence_override(prompt: str) -> str:
    if _scene_requests_humans(prompt or ""):
        return ""
    scene = _scene_text(prompt).lower()
    if _scene_is_inanimate_statue_object_without_living_people(prompt):
        body = (
            "Primary subject: the requested inanimate statue, idol, sculpture, "
            "carved deity image, bust, figurine, monument, or relief figure from "
            "the Scene as the dominant physical object, on its pedestal or temple "
            "surface, one coherent material body, visible carved contours, "
            "material grain, chips, dust, age wear, temple shadow, and hard "
            "directional light."
        )
    elif re.search(r"\b(egg|birth|newborn)\b", scene):
        body = (
            "Primary subject: chest-up close-up portrait of an adult mother figure, "
            "anxious visible eyes, warm golden birth light rising from below the "
            "frame and illuminating her face, one camera viewpoint, single "
            "uninterrupted full-frame scene, plain dark earthen room, sacred-birth "
            "evidence."
        )
    elif re.search(r"\b(book|books|document|documents|manuscript|manuscripts|codex|ledger|journal|scripture|tablet|tablets|paper|papers|papyrus|parchment|scroll|scrolls)\b", scene):
        body = (
            "Primary subject: the requested blank book, document, manuscript, "
            "tablet, or scroll object from the Scene, resting on a visible "
            "period-correct surface, unmarked cover or pages, cord binding or "
            "local material edges when era-appropriate, dust, wear, and hard "
            "directional light."
        )
    elif _scene_requests_planning_board_object(prompt):
        body = (
            "Primary subject: the requested blank tabletop planning board from "
            "the Scene, resting on a low period-correct table, plain wood or "
            "cloth surface, loose cord paths, small stone weights, bronze "
            "markers, dust, hard side light, and empty material margins."
        )
    elif _scene_requests_map_object(prompt):
        body = (
            "Primary subject: the requested geographic planning evidence from "
            "the Scene as a low horizontal tactile marker layout on a plain low "
            "wooden table surface, floor mat, clay slab, cloth planning surface, "
            "or ground-level tabletop surface. The physical marker layout "
            "dominates the frame from a top-down or close three-quarter tabletop "
            "camera view: one loose route cord, two separated stone clusters, "
            "and one bronze weight, pin, or folded cloth strip rest on the "
            "horizontal surface. Regional control and faction pressure are shown "
            "by marker positions, cord paths, clusters, shadows, and light on "
            "plain natural material. Lower-left, lower-right, bottom, and "
            "corner zones are plain material margins made from broad dust, "
            "grain, shadow, and wear. The surface is physically unmarked and "
            "carries unmarked marker objects only, with empty surrounding edges. "
            "This is an unoccupied object-only tabletop or floor-surface "
            "evidence view; visible subject inventory is only the low surface, "
            "marker objects, lamp light, shadows, surface edges, dust, and "
            "natural material texture. The camera crop stays on the low "
            "surface from edge to edge, filled by horizontal material margins "
            "and marker objects. "
            "Off-screen pressure appears only through lamp light, shadows, "
            "marker spacing, cord paths, surface dust, and edge shadows. This is a tight "
            "tactile marker layout shot "
            "with the camera remaining on the tabletop surface."
        )
    elif re.search(r"\b(golden\s+stool|sacred\s+stool|royal\s+stool|carved\s+stool)\b", scene):
        body = (
            "Primary subject: the requested sacred Asante or Ashanti stool from "
            "the Scene as one coherent ceremonial object, a low carved wooden "
            "stool with curved seat and visible support structure, gold-covered "
            "or gold-regalia surface when named, resting on a local support "
            "surface with cloth, dust, contact shadow, and hard side light. It "
            "is not a crown, bowl, chest, box, coffer, altar slab, or throne "
            "chair with a backrest."
        )
    elif re.search(
        r"\b(city|capital|settlement|village|hamlet|compound|town|kingdom|"
        r"empire|urban|frontier\s+village|frontier\s+settlement|kumasi|"
        r"ashanti\s+empire|asante\s+empire)\b",
        scene,
    ):
        body = (
            "Primary subject: the requested city, capital, settlement, village, "
            "hamlet, kingdom, "
            "empire, or urban place from the Scene as a period-local establishing "
            "setting view, with readable architecture, courtyards, streets, "
            "roofs, walls, ground material, vegetation, weather, smoke, dust, "
            "decay, or damage exactly where the Scene implies them. Do not "
            "collapse the setting into one unrelated foreground object, front "
            "gate facade, doorway close-up, or centered under-eave signboard "
            "composition. Any visible roof eave, lintel, or gate header is plain "
            "continuous timber or plaster with no plaque-like rectangle and no "
            "character stroke cluster."
        )
    elif re.search(r"\b(palace|hall|room|court|gate|fortress|tower|building)\b", scene):
        body = (
            "Primary subject: the requested architectural space from the Scene, "
            "period-correct walls, roof structure, threshold, furniture or "
            "courtyard elements when named, blank unmarked material surfaces, "
            "one continuous camera viewpoint, hard diagonal light, and visible "
            "spatial tension."
        )
    elif re.search(r"\b(territory|border|route|kingdom|buyeo|expanding)\b", scene):
        body = (
            "Primary subject: the requested territory, border, route, kingdom, "
            "or geography from the Scene rendered as human-scale physical terrain "
            "evidence: unmarked ground, stones, cord markers, low grass, horizon, "
            "river, road, or settlement cues when named, one continuous outdoor "
            "view, clear geography without readable labels."
        )
    elif _EMPTY_ATMOSPHERE_SCENE_RE.search(scene):
        body = (
            "Primary subject: empty period-correct setting from the Scene, "
            "packed-earth ground, rough timber-and-thatch buildings or plain "
            "interior walls when the Scene implies settlement, fallen dead leaves "
            "drifting or resting on the ground when named, still air, hard "
            "directional light, soft shadows, dust, rain, smoke, or mist when "
            "named, one continuous unoccupied camera viewpoint."
        )
    elif re.search(r"\b(landscape|mountain|river|valley|field|cloud|forest)\b", scene):
        body = (
            "Primary subject: empty establishing landscape filling the frame, "
            "steep rocky slopes, valley floor, riverbank or field edge when named, "
            "low grass, packed dirt path, scattered wet stones, empty "
            "timber-and-thatch huts when settlement context is needed, hard "
            "directional light, and mountain haze as the visible pressure."
        )
    else:
        body = (
            "Primary subject: one close foreground evidence object under hard "
            "directional light, visible pressure and consequence."
        )
    return NON_CHARACTER_EVIDENCE_OVERRIDE_PREFIX + body


def _append_character_closeup_guard(prompt: str) -> str:
    p = (prompt or "").strip()
    if not p or not prompt_mentions_major_character(p):
        return p
    if _scene_requests_travel_vehicle(p):
        return _append_adult_female_appeal_guard(p)
    if _scene_requests_overlooking_view(p):
        if "HUMAN FACE SURFACE LOCK" not in p:
            p += CHARACTER_FACE_SURFACE_DIRECTIVE
        if "OVERLOOKING VIEW COMPOSITION LOCK" not in p:
            p += OVERLOOKING_VIEW_COMPOSITION_DIRECTIVE
        return _append_adult_female_appeal_guard(p)
    if _scene_requires_single_character_setting_story(p):
        if "HUMAN FACE SURFACE LOCK" not in p:
            p += CHARACTER_FACE_SURFACE_DIRECTIVE
        if "SINGLE CHARACTER SETTING STORY LOCK" not in p:
            p += SINGLE_CHARACTER_SETTING_STORY_DIRECTIVE
        return _append_adult_female_appeal_guard(p)
    if _scene_is_stealth_sleeping_guard_story(p):
        if "HUMAN FACE SURFACE LOCK" not in p:
            p += CHARACTER_FACE_SURFACE_DIRECTIVE
        if "STEALTH SLEEPING WATCHMEN STORY LOCK" not in p:
            p += STEALTH_SLEEPING_WATCHMEN_STORY_DIRECTIVE
        return p
    if _scene_requests_fortress_attack_action(p):
        if "HUMAN FACE SURFACE LOCK" not in p:
            p += CHARACTER_FACE_SURFACE_DIRECTIVE
        if "CONTINUOUS SCENE LOCK" not in p:
            p += CONTINUOUS_SCENE_DIRECTIVE
        return _append_adult_female_appeal_guard(p)
    if "HUMAN FACE SURFACE LOCK" not in p:
        p += CHARACTER_FACE_SURFACE_DIRECTIVE
    if _scene_requests_military_logistics_or_camp(p) and _scene_requests_multiple_characters(p):
        if "GROUP CHARACTER COMPOSITION LOCK" not in p:
            p += GROUP_CHARACTER_COMPOSITION_DIRECTIVE
        return _append_adult_female_appeal_guard(p)
    if _scene_requests_achaemenid_egyptian_armed_group(p):
        if "ACHAEMENID EGYPTIAN ARMED GROUP COMPOSITION LOCK" not in p:
            p += ACHAEMENID_EGYPTIAN_ARMED_GROUP_COMPOSITION_DIRECTIVE
        if "ARMED BODY VISIBLE SET LOCK" not in p:
            p += ACHAEMENID_EGYPTIAN_ARMED_BODY_VISIBLE_SET_DIRECTIVE
        return _append_adult_female_appeal_guard(p)
    if _is_early_ancient_chinese_context(p) and _scene_requests_armed_figures(p):
        if "EARLY ANCIENT CHINA ARMED ROLE VISIBLE SET LOCK" not in p:
            p += EARLY_ANCIENT_CHINESE_ARMED_ROLE_VISIBLE_SET_DIRECTIVE
        if "GROUP CHARACTER COMPOSITION LOCK" not in p and _scene_requests_multiple_characters(p):
            p += GROUP_CHARACTER_COMPOSITION_DIRECTIVE
        return _append_adult_female_appeal_guard(p)
    if _is_medieval_central_asian_context(p) and _scene_requests_armed_figures(p):
        if "MEDIEVAL CENTRAL ASIAN ARMED ROLE VISIBLE SET LOCK" not in p:
            p += MEDIEVAL_CENTRAL_ASIAN_ARMORED_ROLE_VISIBLE_SET_DIRECTIVE
        if "GROUP CHARACTER COMPOSITION LOCK" not in p and _scene_requests_multiple_characters(p):
            p += GROUP_CHARACTER_COMPOSITION_DIRECTIVE
        return _append_adult_female_appeal_guard(p)
    if _is_west_african_ashanti_british_context(p) and _scene_requests_armed_figures(p):
        if "WEST AFRICAN ASHANTI ARMED ROLE VISIBLE SET LOCK" not in p:
            p += WEST_AFRICAN_ASHANTI_ARMED_ROLE_VISIBLE_SET_DIRECTIVE
        if "GROUP CHARACTER COMPOSITION LOCK" not in p and _scene_requests_multiple_characters(p):
            p += GROUP_CHARACTER_COMPOSITION_DIRECTIVE
        return _append_adult_female_appeal_guard(p)
    if _scene_requests_armed_figures(p):
        if _scene_requests_explicit_armed_group_standoff(p):
            if "ARMED GROUP STANDOFF COMPOSITION LOCK" not in p:
                p += ARMED_GROUP_STANDOFF_COMPOSITION_DIRECTIVE
            return _append_adult_female_appeal_guard(p)
        if not _scene_names_specific_weapon(p):
            if "ARMED ROLE PORTRAIT CROP LOCK" not in p:
                p += ARMED_ROLE_PORTRAIT_CROP_DIRECTIVE
            return _append_adult_female_appeal_guard(p)
        if "ARMED GROUP REPRESENTATIVE COMPOSITION LOCK" not in p:
            p += ARMED_GROUP_REPRESENTATIVE_COMPOSITION_DIRECTIVE
        return _append_adult_female_appeal_guard(p)
    if _scene_requests_multiple_characters(p):
        if _scene_requests_multi_character_closeup(p):
            if "MULTI CHARACTER CLOSEUP LOCK" not in p:
                p += MULTI_CHARACTER_CLOSEUP_DIRECTIVE
            return _append_adult_female_appeal_guard(p)
        if _scene_requests_armed_figures(p):
            if "ARMED GROUP REPRESENTATIVE COMPOSITION LOCK" not in p:
                p += ARMED_GROUP_REPRESENTATIVE_COMPOSITION_DIRECTIVE
            return _append_adult_female_appeal_guard(p)
        if "GROUP CHARACTER COMPOSITION LOCK" not in p:
            p += GROUP_CHARACTER_COMPOSITION_DIRECTIVE
        return _append_adult_female_appeal_guard(p)
    if _scene_requests_single_character_visible_action(p):
        if "HUMAN FACE SURFACE LOCK" not in p:
            p += CHARACTER_FACE_SURFACE_DIRECTIVE
        if "SINGLE CHARACTER ACTION STORY LOCK" not in p:
            p += SINGLE_CHARACTER_ACTION_STORY_DIRECTIVE
        return _append_adult_female_appeal_guard(p)
    if _is_confirmed_adult_female_context(p) and not _scene_explicitly_requests_closeup(p):
        return _append_adult_female_appeal_guard(p)
    if "CHARACTER COMPOSITION LOCK" in p and _scene_explicitly_requests_closeup(p):
        if not _scene_requests_armed_figures(p) and "CHARACTER PORTRAIT VISIBLE SET LOCK" not in p:
            p += CHARACTER_PORTRAIT_PROP_SET_DIRECTIVE
        return _append_adult_female_appeal_guard(p)
    if _scene_explicitly_requests_closeup(p):
        p += CHARACTER_CLOSEUP_DIRECTIVE
        p += SINGLE_CHARACTER_FOCUS_DIRECTIVE
        if not _scene_requests_armed_figures(p) and "CHARACTER PORTRAIT VISIBLE SET LOCK" not in p:
            p += CHARACTER_PORTRAIT_PROP_SET_DIRECTIVE
        return _append_adult_female_appeal_guard(p)
    if "CHARACTER STORY FRAMING LOCK" not in p:
        p += CHARACTER_STORY_FRAMING_DIRECTIVE
    return _append_adult_female_appeal_guard(p)


def needs_book_render_guard(prompt: str) -> bool:
    scene = _scene_text(prompt or "")
    return bool(_BOOK_RENDER_OBJECT_RE.search(scene or ""))


def _append_book_render_guard(prompt: str) -> str:
    p = (prompt or "").strip()
    if not p or not needs_book_render_guard(p):
        return p
    if "BOOK RENDERING LOCK" in p:
        return p
    return p + BOOK_RENDER_DIRECTIVE


def _append_paper_evidence_surface_guard(prompt: str) -> str:
    p = (prompt or "").strip()
    if not p or not _scene_requests_paper_evidence(p):
        return p
    if "PAPER EVIDENCE SURFACE LOCK" in p:
        return p
    return p + PAPER_EVIDENCE_SURFACE_DIRECTIVE


def _append_entry_facade_surface_guard(prompt: str) -> str:
    p = (prompt or "").strip()
    if not p or not _scene_requests_entry_facade_surface_guard(p):
        return p
    if "ENTRY FACADE SURFACE LOCK" in p:
        return p
    return p + ENTRY_FACADE_SURFACE_DIRECTIVE


def _append_cloth_evidence_surface_guard(prompt: str) -> str:
    p = (prompt or "").strip()
    if not p or not _scene_requests_cloth_evidence(p):
        return p
    if "CLOTH EVIDENCE SURFACE LOCK" in p:
        return p
    return p + CLOTH_EVIDENCE_SURFACE_DIRECTIVE


def _directive_body(directive: str) -> str:
    return re.sub(r"^\s*\|\|\s*", "", (directive or "").strip())


def _promote_directive_to_front(prompt: str, directive: str) -> str:
    p = (prompt or "").strip()
    body = _directive_body(directive)
    if not p or not body:
        return p
    p = p.replace(" || " + body, "")
    p = p.replace(body + " || ", "")
    p = p.replace(body, "")
    p = p.strip()
    if p.startswith(REFERENCE_STYLE_PREFIX):
        rest = p[len(REFERENCE_STYLE_PREFIX):].lstrip()
        return REFERENCE_STYLE_PREFIX + body + " || " + rest
    return body + " || " + p


def _apply_common_image_constraints(prompt: str, enable_historical_guard: bool = False) -> str:
    p = _strip_unreliable_main_subject(prompt)
    p = _strip_background_shopping_lists(p)
    p = _normalize_visual_surface_depiction_language(p)
    p = _normalize_text_prone_surface_terms(p)
    p = _normalize_historical_tally_scene_language(p)
    p = _strip_negative_instruction_fields(p)
    p = _normalize_early_goguryeo_scene_terms(p)
    p = _normalize_early_modern_europe_scene_language(p)
    p = _strip_scene_evidence_character_metadata(p)
    p = _normalize_object_cut_scene_language(p)
    p = _normalize_map_object_language(p)
    p = _normalize_travel_vehicle_scene_language(p)
    p = _normalize_character_scene_language(p)
    p = _normalize_armed_action_scene_language(p)
    p = _normalize_medieval_japanese_armor_language(p)
    p = _normalize_medieval_japanese_hand_equipment_language(p)
    p = _normalize_map_object_language(p)
    p = _normalize_group_planning_surface_language(p)
    p = _normalize_preindustrial_light_scene_language(p)
    p = _normalize_historical_symbolic_modern_object_language(p)
    p = _normalize_premodern_footwear_scene_language(p)
    p = _normalize_early_ancient_chinese_armor_language(p)
    p = _normalize_military_logistics_scene_language(p)
    p = _sanitize_flag_motif_positive_prompt(p)
    p = _sanitize_positive_style_leaks(p)
    is_modern_source_context = _is_modern_context(p)
    is_historical_source_context = _is_historical_period_context(p)
    is_preindustrial_source_context = _is_preindustrial_historical_context(p)
    is_ancient_mediterranean_source_context = _is_ancient_mediterranean_context(p)
    is_early_ancient_chinese_source_context = _is_early_ancient_chinese_context(p)
    is_early_imperial_chinese_source_context = _is_early_imperial_chinese_context(p)
    is_medieval_japanese_source_context = _is_medieval_japanese_context(p)
    is_achaemenid_egyptian_source_context = _is_achaemenid_egyptian_context(p)
    is_medieval_central_asian_source_context = _is_medieval_central_asian_context(p)
    is_early_modern_europe_source_context = _is_early_modern_europe_context(p)
    is_west_african_ashanti_source_context = _is_west_african_ashanti_british_context(p)
    is_outdoor_location_scene = _scene_names_outdoor_location(p)
    is_map_object_scene = (
        _scene_requests_map_object(p)
        or _scene_requests_planning_board_object(p)
        or _scene_requests_generic_object_evidence(p)
    )
    is_group_planning_surface_scene = _scene_requests_group_planning_surface(p)
    if is_ancient_mediterranean_source_context:
        p = _normalize_ancient_mediterranean_scene_language(p)
    p = _prepend_primary_image_lock(p)
    if "SCENE FIDELITY LOCK" not in p:
        p = _promote_directive_to_front(p, SCENE_FIDELITY_DIRECTIVE)
    p = apply_historical_accuracy_guard(p, enable_historical_guard)
    if _scene_requests_named_banner_or_flag(p) and "BANNER COUNT EVIDENCE LOCK" not in p:
        p = _promote_directive_to_front(p, BANNER_COUNT_EVIDENCE_DIRECTIVE)
    if _scene_requests_maritime_landing(p) and "MARITIME LANDING EVIDENCE LOCK" not in p:
        p = _promote_directive_to_front(p, MARITIME_LANDING_EVIDENCE_DIRECTIVE)
    if (
        is_outdoor_location_scene
        and not is_map_object_scene
        and not is_group_planning_surface_scene
        and "OUTDOOR LOCATION EVIDENCE LOCK" not in p
    ):
        p = _promote_directive_to_front(p, OUTDOOR_LOCATION_EVIDENCE_DIRECTIVE)
    if (
        _scene_requests_household_relocation(p)
        and not is_map_object_scene
        and not is_group_planning_surface_scene
        and "HOUSEHOLD RELOCATION EVIDENCE LOCK" not in p
    ):
        p += HOUSEHOLD_RELOCATION_EVIDENCE_DIRECTIVE
    if (
        _scene_requests_historical_public_street_or_muster(p)
        and not is_map_object_scene
        and not is_group_planning_surface_scene
        and "HISTORICAL PUBLIC STREET AND MUSTER LOCK" not in p
    ):
        p = _promote_directive_to_front(p, HISTORICAL_PUBLIC_STREET_MUSTER_DIRECTIVE)
    if (
        _scene_requests_historical_road_logistics(p)
        and not is_map_object_scene
        and not is_group_planning_surface_scene
        and "HISTORICAL ROAD LOGISTICS EVIDENCE LOCK" not in p
    ):
        p = _promote_directive_to_front(p, HISTORICAL_ROAD_LOGISTICS_EVIDENCE_DIRECTIVE)
    if (
        _scene_requests_preindustrial_craft_workshop(p)
        and not is_map_object_scene
        and not is_group_planning_surface_scene
        and "PREINDUSTRIAL CRAFT WORKSHOP EVIDENCE LOCK" not in p
    ):
        p += PREINDUSTRIAL_CRAFT_WORKSHOP_EVIDENCE_DIRECTIVE
    if (
        _scene_requests_historical_tally_object_evidence(p)
        and not is_group_planning_surface_scene
        and "HISTORICAL TALLY OBJECT EVIDENCE LOCK" not in p
    ):
        p = _promote_directive_to_front(p, HISTORICAL_TALLY_OBJECT_EVIDENCE_DIRECTIVE)
    if (
        _scene_requests_historical_blank_record_document(p)
        and not is_group_planning_surface_scene
        and "HISTORICAL BLANK RECORD EVIDENCE LOCK" not in p
    ):
        p = _promote_directive_to_front(p, HISTORICAL_BLANK_RECORD_EVIDENCE_DIRECTIVE)
    if is_map_object_scene or is_group_planning_surface_scene:
        if "IMAGE QUALITY LOCK" not in p:
            p += OBJECT_EVIDENCE_IMAGE_QUALITY_DIRECTIVE
        if "ADULT GRAPHIC NOVEL STYLE LOCK" not in p:
            p += OBJECT_EVIDENCE_GRAPHIC_NOVEL_STYLE_DIRECTIVE
        if "OBJECT PHYSICAL COMMON-SENSE LOCK" not in p:
            p += OBJECT_EVIDENCE_PHYSICAL_COMMON_SENSE_DIRECTIVE
        if "CUT INVENTORY BOUNDARY LOCK" not in p:
            p += CUT_INVENTORY_BOUNDARY_DIRECTIVE
    else:
        if "IMAGE QUALITY LOCK" not in p:
            p += IMAGE_QUALITY_DIRECTIVE
        if "ADULT GRAPHIC NOVEL STYLE LOCK" not in p:
            p += ADULT_GRAPHIC_NOVEL_STYLE_DIRECTIVE
        if "COMMON-SENSE ANATOMY LOCK" not in p:
            p += COMMON_SENSE_ANATOMY_DIRECTIVE
        if "ROLE EQUIPMENT COMMON-SENSE LOCK" not in p:
            p += ROLE_EQUIPMENT_COMMON_SENSE_DIRECTIVE
        if "CUT INVENTORY BOUNDARY LOCK" not in p:
            p += CUT_INVENTORY_BOUNDARY_DIRECTIVE
        if "DYNAMIC ACTION AND EMOTION LOCK" not in p:
            p += DYNAMIC_ACTION_EMOTION_DIRECTIVE
        if "VISUAL QA READINESS LOCK" not in p:
            p += VISUAL_QA_READINESS_DIRECTIVE
        if (
            prompt_mentions_major_character(p)
            and "CHARACTER ENTRANCE GRANDEUR LOCK" not in p
        ):
            p += CHARACTER_ENTRANCE_GRANDEUR_DIRECTIVE
        if (
            is_historical_source_context
            and "PERIOD WEAPON AND PROP AUDIT LOCK" not in p
        ):
            p += PERIOD_WEAPON_AND_PROP_AUDIT_DIRECTIVE
        if (
            _scene_needs_action_object_environment_evidence(p)
            and "SCENE ACTION OBJECT EVIDENCE LOCK" not in p
        ):
            p += SCENE_ACTION_OBJECT_EVIDENCE_DIRECTIVE
    if is_modern_source_context and "MODERN CHARACTER CLOTHING LOCK" not in p:
        p += MODERN_CHARACTER_CLOTHING_DIRECTIVE
    if (
        is_historical_source_context
        and not is_map_object_scene
        and not is_group_planning_surface_scene
        and _scene_requests_humans(p)
        and "HISTORICAL HUMAN CLOTHING LOCK" not in p
    ):
        p += (
            HISTORICAL_UPPER_BODY_GROUP_CLOTHING_DIRECTIVE
            if _scene_requests_achaemenid_egyptian_armed_group(p)
            else HISTORICAL_HUMAN_CLOTHING_DIRECTIVE
        )
    if (
        is_preindustrial_source_context
        and not is_map_object_scene
        and not is_group_planning_surface_scene
        and "HISTORICAL BUILDING HARDWARE LOCK" not in p
    ):
        p += HISTORICAL_BUILDING_HARDWARE_DIRECTIVE
    if (
        is_preindustrial_source_context
        and _scene_requests_preindustrial_light_source(p)
        and not is_group_planning_surface_scene
        and "PERIOD LAMP PLACEMENT LOCK" not in p
    ):
        p += PREINDUSTRIAL_LAMP_PLACEMENT_DIRECTIVE
    if (
        is_ancient_mediterranean_source_context
        and not is_map_object_scene
        and not is_group_planning_surface_scene
        and "ANCIENT MEDITERRANEAN MATERIAL CULTURE LOCK" not in p
    ):
        p += ANCIENT_MEDITERRANEAN_MATERIAL_CULTURE_DIRECTIVE
    if (
        is_early_ancient_chinese_source_context
        and not is_map_object_scene
        and not is_group_planning_surface_scene
        and _scene_requests_humans(p)
        and "EARLY ANCIENT CHINA MATERIAL CULTURE LOCK" not in p
    ):
        p += EARLY_ANCIENT_CHINESE_MATERIAL_CULTURE_DIRECTIVE
    if (
        is_early_imperial_chinese_source_context
        and not is_map_object_scene
        and not is_group_planning_surface_scene
        and _scene_requests_humans(p)
        and "EARLY IMPERIAL CHINA MATERIAL CULTURE LOCK" not in p
    ):
        p += EARLY_IMPERIAL_CHINESE_MATERIAL_CULTURE_DIRECTIVE
    if (
        is_medieval_japanese_source_context
        and not is_map_object_scene
        and not is_group_planning_surface_scene
        and _scene_requests_humans(p)
        and "PERIOD-LOCAL JAPANESE COSTUME AND ARMOR LOCK" not in p
        and "PERIOD-LOCAL JAPANESE MARTIAL CLOTHING LOCK" not in p
        and "PERIOD-LOCAL JAPANESE COURT AND CIVILIAN COSTUME LOCK" not in p
    ):
        if _scene_requests_medieval_japanese_protective_dress(p):
            p += MEDIEVAL_JAPANESE_COSTUME_ARMOR_DIRECTIVE
        elif _scene_requests_military_role_or_armor(p):
            p += MEDIEVAL_JAPANESE_MARTIAL_CLOTHING_DIRECTIVE
        else:
            p += MEDIEVAL_JAPANESE_COURT_CIVILIAN_COSTUME_DIRECTIVE
    if (
        is_achaemenid_egyptian_source_context
        and "PERIOD-LOCAL ACHAEMENID PERSIAN AND EGYPTIAN MATERIAL CULTURE LOCK" not in p
        and "PERIOD-LOCAL ACHAEMENID PERSIAN AND EGYPTIAN SETTING MATERIAL LOCK" not in p
    ):
        p += (
            ACHAEMENID_EGYPTIAN_SETTING_MATERIAL_CULTURE_DIRECTIVE
            if is_map_object_scene or not _scene_requests_humans(p)
            else ACHAEMENID_EGYPTIAN_MATERIAL_CULTURE_DIRECTIVE
        )
    if (
        is_medieval_central_asian_source_context
        and "PERIOD-LOCAL MEDIEVAL CENTRAL ASIAN MATERIAL CULTURE LOCK" not in p
        and "PERIOD-LOCAL MEDIEVAL CENTRAL ASIAN SETTING MATERIAL LOCK" not in p
    ):
        p += (
            MEDIEVAL_CENTRAL_ASIAN_SETTING_MATERIAL_CULTURE_DIRECTIVE
            if is_map_object_scene or not _scene_requests_humans(p)
            else MEDIEVAL_CENTRAL_ASIAN_MATERIAL_CULTURE_DIRECTIVE
        )
    if (
        is_early_modern_europe_source_context
        and not is_group_planning_surface_scene
        and "EARLY MODERN EUROPE MATERIAL CULTURE LOCK" not in p
    ):
        p += EARLY_MODERN_EUROPE_MATERIAL_CULTURE_DIRECTIVE
    if (
        _scene_requests_early_modern_europe_astronomy_observation(p)
        and "EARLY MODERN EUROPE ASTRONOMY OBSERVATION LOCK" not in p
    ):
        p += EARLY_MODERN_EUROPE_ASTRONOMY_OBSERVATION_DIRECTIVE
    if (
        _scene_requests_historical_bed_rest(p)
        and "HISTORICAL BED REST LOCK" not in p
    ):
        p += HISTORICAL_BED_REST_DIRECTIVE
    if (
        _scene_requests_single_early_modern_person(p)
        and "EARLY MODERN SINGLE PERSON COUNT LOCK" not in p
    ):
        p += EARLY_MODERN_SINGLE_PERSON_COUNT_DIRECTIVE
    if (
        _scene_requests_early_modern_three_scholar_group(p)
        and "EARLY MODERN THREE SCHOLAR GROUP LOCK" not in p
    ):
        p += EARLY_MODERN_THREE_SCHOLAR_GROUP_DIRECTIVE
    if (
        _scene_requests_astronomical_surface_or_instrument(p)
        and "UNLABELED ASTRONOMICAL SURFACE LOCK" not in p
    ):
        p += UNLABELED_ASTRONOMICAL_SURFACE_DIRECTIVE
    if (
        _scene_requests_astronomical_chart_surface_object(p)
        and "ASTRONOMICAL CHART OBJECT STILL-LIFE LOCK" not in p
    ):
        p += ASTRONOMICAL_CHART_OBJECT_DIRECTIVE
    if (
        is_west_african_ashanti_source_context
        and "PERIOD-LOCAL WEST AFRICAN ASHANTI AND GOLD COAST MATERIAL CULTURE LOCK" not in p
        and "PERIOD-LOCAL WEST AFRICAN ASHANTI AND GOLD COAST SETTING MATERIAL LOCK" not in p
    ):
        p += (
            WEST_AFRICAN_ASHANTI_SETTING_MATERIAL_CULTURE_DIRECTIVE
            if is_map_object_scene or not _scene_requests_humans(p)
            else WEST_AFRICAN_ASHANTI_MATERIAL_CULTURE_DIRECTIVE
        )
    if (
        is_west_african_ashanti_source_context
        and _scene_requests_humans(p)
        and re.search(
            r"\b(colonial\s+officer|British\s+colonial\s+officer|governor|commissioner|"
            r"administrator|official|arrogant\s+official|cultural\s+artifacts?|hodgson)\b",
            _scene_text(p),
            re.IGNORECASE,
        )
        and not re.search(r"\b(Ashanti|Asante)\s+official\b", _scene_text(p), re.IGNORECASE)
        and "WEST AFRICAN BRITISH COLONIAL OFFICIAL ROLE LOCK" not in p
    ):
        p += WEST_AFRICAN_ASHANTI_COLONIAL_OFFICIAL_DIRECTIVE
    if not is_early_imperial_chinese_source_context:
        p = _append_early_goguryeo_frontier_guard(p)
    if _is_goguryeo_silla_415_context(p) and "GOGURYEO-SILLA 415 MATERIAL CULTURE LOCK" not in p:
        p += GOGURYEO_SILLA_415_DIRECTIVE
    if _scene_requests_hou_bowl_object(p) and "HOU BOWL OBJECT LOCK" not in p:
        p += HOU_BOWL_OBJECT_DIRECTIVE
    if "SCENE CONTENT PRIORITY" not in p:
        p += (
            MAP_OBJECT_SCENE_CONTENT_PRIORITY_DIRECTIVE
            if is_map_object_scene or is_group_planning_surface_scene
            else SCENE_CONTENT_PRIORITY_DIRECTIVE
        )
    identity_directive = "" if is_map_object_scene or is_group_planning_surface_scene else _scene_named_identity_directive(p)
    if identity_directive and "SCENE NAMED IDENTITY LOCK" not in p:
        p += identity_directive
    if (
        not is_map_object_scene
        and not is_group_planning_surface_scene
        and _scene_requests_formal_role_layout(p)
        and "FORMAL ROLE AND SETTING LAYOUT LOCK" not in p
    ):
        p += FORMAL_ROLE_SETTING_LAYOUT_DIRECTIVE
    if _scene_requests_split_side_layout(p) and "SPLIT-SIDE COMPOSITION LOCK" not in p:
        p += SPLIT_SIDE_COMPOSITION_DIRECTIVE
    if (
        is_group_planning_surface_scene
        and "GROUP PLANNING SURFACE LOCK" not in p
    ):
        p += GROUP_PLANNING_SURFACE_DIRECTIVE
    if (
        is_outdoor_location_scene
        and not is_map_object_scene
        and not is_group_planning_surface_scene
        and "OUTDOOR LOCATION EVIDENCE LOCK" not in p
    ):
        p += OUTDOOR_LOCATION_EVIDENCE_DIRECTIVE
    if _scene_requests_mounted_travel(p) and "MOUNTED TRAVEL EVIDENCE LOCK" not in p:
        p = _promote_directive_to_front(p, MOUNTED_TRAVEL_EVIDENCE_DIRECTIVE)
    if (
        _scene_requests_carried_travel_vehicle(p)
        and "CARRIED LITTER EVIDENCE LOCK" not in p
        and "CARRIED TRAVEL VEHICLE EVIDENCE LOCK" not in p
    ):
        p += TRAVEL_CARRIED_VEHICLE_EVIDENCE_DIRECTIVE
    if (
        _scene_requests_wheeled_travel_vehicle(p)
        and "WHEELED TRAVEL VEHICLE EVIDENCE LOCK" not in p
    ):
        p += TRAVEL_WHEELED_VEHICLE_EVIDENCE_DIRECTIVE
    if _scene_requests_military_logistics_or_camp(p) and "MILITARY LOGISTICS GROUP VISIBLE SET LOCK" not in p:
        p += MILITARY_LOGISTICS_VISIBLE_SET_DIRECTIVE
    if (
        _scene_requests_achaemenid_egyptian_armed_group(p)
        and "ACHAEMENID EGYPTIAN ARMED GROUP COMPOSITION LOCK" not in p
    ):
        p += ACHAEMENID_EGYPTIAN_ARMED_GROUP_COMPOSITION_DIRECTIVE
    if (
        _scene_requests_military_role_or_armor(p)
        and not is_map_object_scene
        and not is_group_planning_surface_scene
        and "ARMORED ROLE VISIBLE SET LOCK" not in p
        and "MARTIAL ROLE CLOTHING VISIBLE SET LOCK" not in p
        and "ACHAEMENID EGYPTIAN TEXTILE MILITARY DRESS LOCK" not in p
    ):
        if is_medieval_japanese_source_context:
            p += (
                JAPANESE_ARMORED_ROLE_VISIBLE_SET_DIRECTIVE
                if _scene_requests_medieval_japanese_protective_dress(p)
                else JAPANESE_MARTIAL_ROLE_VISIBLE_SET_DIRECTIVE
            )
        elif is_achaemenid_egyptian_source_context:
            p += (
                ACHAEMENID_EGYPTIAN_ARMORED_ROLE_VISIBLE_SET_DIRECTIVE
                if _scene_explicitly_names_protective_torso_gear(p)
                else ACHAEMENID_EGYPTIAN_UNARMORED_MILITARY_DRESS_DIRECTIVE
            )
        elif is_early_ancient_chinese_source_context:
            p += EARLY_ANCIENT_CHINESE_ARMED_ROLE_VISIBLE_SET_DIRECTIVE
        elif is_medieval_central_asian_source_context:
            p += MEDIEVAL_CENTRAL_ASIAN_ARMORED_ROLE_VISIBLE_SET_DIRECTIVE
        elif is_west_african_ashanti_source_context:
            p += WEST_AFRICAN_ASHANTI_ARMED_ROLE_VISIBLE_SET_DIRECTIVE
        else:
            p += ARMORED_ROLE_VISIBLE_SET_DIRECTIVE
    if (
        _scene_requests_humans(p)
        and not is_map_object_scene
        and not is_group_planning_surface_scene
        and not _scene_requests_armed_figures(p)
        and not _scene_requests_military_logistics_or_camp(p)
        and not _scene_requests_military_role_or_armor(p)
        and "ORDINARY HUMAN VISIBLE SET LOCK" not in p
    ):
        p += UNARMED_HUMAN_VISIBLE_SET_DIRECTIVE
    if (
        _scene_requests_humans(p)
        and not is_map_object_scene
        and not is_group_planning_surface_scene
        and not _scene_requests_armed_figures(p)
        and not _scene_requests_military_logistics_or_camp(p)
        and not _scene_requests_military_role_or_armor(p)
        and _scene_requests_civilian_work_or_camp(p)
        and "CAMP WORK VISIBLE SET LOCK" not in p
    ):
        p += CAMP_WORK_VISIBLE_SET_DIRECTIVE
    if is_map_object_scene and "EMPTY EVIDENCE FRAME LOCK" not in p:
        p += MAP_OBJECT_EMPTY_EVIDENCE_DIRECTIVE
    elif not _scene_requests_humans(p) and "EMPTY EVIDENCE FRAME LOCK" not in p:
        p += NO_UNREQUESTED_HUMANS_DIRECTIVE
    if (
        _scene_requests_landscape(p)
        and not _scene_requests_humans(p)
        and "LANDSCAPE VISIBLE SET LOCK" not in p
    ):
        p += LANDSCAPE_VISIBLE_SET_DIRECTIVE
    evidence_override = _non_character_evidence_override(p)
    if evidence_override and "OBJECT-LOCATION PRIMARY SUBJECT LOCK" not in p:
        p += evidence_override
    if not _scene_requests_mount_or_animal(p) and "REQUESTED-SUBJECT PROP LOCK" not in p:
        p += NO_UNREQUESTED_MOUNTS_DIRECTIVE
    if _scene_is_animal_focused_without_people(p) and "ANIMAL SUBJECT PHYSICAL LOCK" not in p:
        p += ANIMAL_SUBJECT_PHYSICAL_DIRECTIVE
    if (
        _scene_is_animal_focused_without_people(p)
        and not _scene_names_animal_wearable(p)
        and "ANIMAL BARE BODY LOCK" not in p
    ):
        p += ANIMAL_BARE_BODY_DIRECTIVE
    if (
        (
            _scene_is_depicted_people_on_object_without_living_people(p)
            or _scene_is_depicted_surface_evidence_object(p)
        )
        and "DEPICTED SURFACE OBJECT LOCK" not in p
    ):
        p += DEPICTED_SURFACE_OBJECT_DIRECTIVE
    if "STORY MOMENT LOCK" not in p:
        p += (
            MAP_OBJECT_STORY_MOMENT_DIRECTIVE
            if is_map_object_scene or is_group_planning_surface_scene
            else ACTION_EMOTION_DIRECTIVE
        )
    if (
        not is_map_object_scene
        and not is_group_planning_surface_scene
        and _scene_requests_multiple_characters(p)
        and "CONTINUOUS SCENE LOCK" not in p
    ):
        p += CONTINUOUS_SCENE_DIRECTIVE
    if (
        _scene_requests_bow_without_arrow_action(p)
        and not is_map_object_scene
        and _scene_requests_humans(p)
        and not is_medieval_central_asian_source_context
        and "SELECTED PERIOD WEAPON LOCK" not in p
    ):
        p += _selected_period_weapon_loadout_directive(p)
    if (
        _scene_requests_armed_figures(p)
        and not is_map_object_scene
        and _scene_requests_humans(p)
        and not _scene_names_specific_weapon(p)
        and not _scene_requests_explicit_armed_group_standoff(p)
        and not _scene_requests_achaemenid_egyptian_armed_group(p)
        and not is_early_ancient_chinese_source_context
        and not is_medieval_central_asian_source_context
        and not is_west_african_ashanti_source_context
        and "ARMED ROLE PORTRAIT CROP LOCK" not in p
    ):
        p += ARMED_ROLE_PORTRAIT_CROP_DIRECTIVE
    if (
        _scene_requests_armed_figures(p)
        and not is_map_object_scene
        and _scene_requests_humans(p)
        and _scene_names_specific_weapon(p)
        and not _scene_requests_explicit_armed_group_standoff(p)
        and not _scene_requests_achaemenid_egyptian_armed_group(p)
        and not is_early_ancient_chinese_source_context
        and not is_medieval_central_asian_source_context
        and not is_west_african_ashanti_source_context
        and "ARMED FIGURE LOADOUT LOCK" not in p
    ):
        p += ARMED_FIGURE_LOADOUT_DIRECTIVE
    if (
        _scene_requests_armed_figures(p)
        and not is_map_object_scene
        and _scene_requests_humans(p)
        and _scene_names_specific_weapon(p)
        and "ARMED BODY VISIBLE SET LOCK" not in p
    ):
        p += (
            JAPANESE_ARMED_BODY_VISIBLE_SET_DIRECTIVE
            if is_medieval_japanese_source_context
            else ACHAEMENID_EGYPTIAN_ARMED_BODY_VISIBLE_SET_DIRECTIVE
            if is_achaemenid_egyptian_source_context
            else EARLY_ANCIENT_CHINESE_ARMED_ROLE_VISIBLE_SET_DIRECTIVE
            if is_early_ancient_chinese_source_context
            else MEDIEVAL_CENTRAL_ASIAN_ARMORED_ROLE_VISIBLE_SET_DIRECTIVE
            if is_medieval_central_asian_source_context
            else WEST_AFRICAN_ASHANTI_ARMED_ROLE_VISIBLE_SET_DIRECTIVE
            if is_west_african_ashanti_source_context
            else ARMED_BODY_VISIBLE_SET_DIRECTIVE
        )
    if (
        _scene_requests_armed_figures(p)
        and not is_map_object_scene
        and _scene_requests_humans(p)
        and _scene_names_specific_weapon(p)
        and not is_early_ancient_chinese_source_context
        and not is_medieval_central_asian_source_context
        and not is_west_african_ashanti_source_context
        and "SELECTED PERIOD WEAPON LOCK" not in p
    ):
        p += _selected_period_weapon_loadout_directive(p)
    p = _append_character_closeup_guard(p)
    p = _append_adult_female_appeal_guard(p)
    p = _append_book_render_guard(p)
    p = _append_no_text(p)
    p = _append_entry_facade_surface_guard(p)
    p = _append_cloth_evidence_surface_guard(p)
    p = _append_paper_evidence_surface_guard(p)
    if (
        _scene_is_inanimate_statue_object_without_living_people(p)
        and "INANIMATE STATUE OBJECT LOCK" not in p
    ):
        p += INANIMATE_STATUE_OBJECT_DIRECTIVE
    p = _append_no_maps(p)
    if (
        not is_map_object_scene
        and not is_group_planning_surface_scene
        and _scene_requests_humans(p)
        and "FINAL CLOTHING SURFACE LOCK" not in p
    ):
        p += FINAL_CLOTHING_SURFACE_DIRECTIVE
    if is_outdoor_location_scene and not is_group_planning_surface_scene:
        p = _promote_directive_to_front(p, OUTDOOR_LOCATION_EVIDENCE_DIRECTIVE)
    return p


def needs_korean_history_guard(prompt: str) -> bool:
    return bool(_KOREAN_HISTORY_RE.search(prompt or ""))


def _has_explicit_period_place_context(prompt: str) -> bool:
    return bool(
        re.search(
            r"\b(?:Year/period|Exact place|Scene evidence)\s*:",
            prompt or "",
            re.IGNORECASE,
        )
    )


def apply_historical_accuracy_guard(prompt: str, enabled: bool = False) -> str:
    p = (prompt or "").strip()
    enabled = bool(enabled) or _has_explicit_period_place_context(p)
    if not enabled:
        return p
    if (
        not p
        or "HISTORICAL ACCURACY LOCK" in p
        or "HARD HISTORICAL MATERIAL CULTURE LOCK" in p
        or "HARD HISTORICAL SETTING MATERIAL CULTURE LOCK" in p
        or "HARD HISTORICAL OBJECT EVIDENCE MATERIAL CULTURE LOCK" in p
        or "HARD HISTORICAL CIVILIAN MATERIAL CULTURE LOCK" in p
    ):
        return p
    if _is_modern_context(p):
        if "HARD PERIOD AND PLACE ACCURACY LOCK" in p:
            return p
        return MODERN_PERIOD_ACCURACY_DIRECTIVE + " || " + p
    if _scene_requests_seated_ruler_throne_story(p):
        return _general_history_accuracy_directive_for_prompt(p) + " || " + p
    if (
        _scene_requests_map_object(p)
        or _scene_requests_planning_board_object(p)
        or _scene_requests_group_planning_surface(p)
        or _scene_requests_generic_object_evidence(p)
    ):
        return OBJECT_EVIDENCE_HISTORY_ACCURACY_DIRECTIVE + " || " + p
    if not _scene_requests_humans(p):
        return SETTING_HISTORY_ACCURACY_DIRECTIVE + " || " + p
    if (
        _scene_requests_humans(p)
        and not _scene_requests_armed_figures(p)
        and not _scene_requests_military_role_or_armor(p)
    ):
        return CIVILIAN_HISTORY_ACCURACY_DIRECTIVE + " || " + p
    return _general_history_accuracy_directive_for_prompt(p) + " || " + p


def _general_history_accuracy_directive_for_prompt(prompt: str) -> str:
    directive = GENERAL_HISTORY_ACCURACY_DIRECTIVE
    if re.search(
        r"\b(?:close[-\s]*up|portrait|face[-\s]*only|head[-\s]*and[-\s]*shoulders)\b|"
        r"SINGLE CHARACTER LOCK|CHARACTER COMPOSITION LOCK",
        prompt or "",
        re.IGNORECASE,
    ):
        directive = directive.replace(
            "clothing cuts, hairstyles, headwear",
            "clothing cuts and hairstyles",
        )
    return directive


def _merge_negative_prompts(*parts: str) -> str:
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for token in [x.strip() for x in (part or "").split(",") if x.strip()]:
            key = token.lower()
            if key not in seen:
                seen.add(key)
                out.append(token)
    return ", ".join(out)


def historical_negative_prompt(prompt: str, enabled: bool = False) -> str:
    p = prompt or ""
    if not enabled and not _has_explicit_period_place_context(p):
        return ""
    parts = [
        NO_TEXT_NEGATIVE_PROMPT,
        NO_MAP_NEGATIVE_PROMPT,
        COMMON_ANATOMY_NEGATIVE_PROMPT,
        ANIMAL_ANATOMY_NEGATIVE_PROMPT,
        COMMON_STYLE_NEGATIVE_PROMPT,
    ]
    if not _is_modern_context(p):
        parts.append(COMMON_PERIOD_NEGATIVE_PROMPT)
    if _is_ancient_mediterranean_context(p):
        parts.append(ANCIENT_MEDITERRANEAN_WRONG_CULTURE_NEGATIVE_PROMPT)
    if _is_early_ancient_chinese_context(p):
        parts.append(EARLY_ANCIENT_CHINESE_WRONG_ARMOR_NEGATIVE_PROMPT)
    if _is_early_imperial_chinese_context(p):
        parts.append(EARLY_IMPERIAL_CHINESE_WRONG_CULTURE_NEGATIVE_PROMPT)
    if _is_medieval_japanese_context(p):
        parts.append(MEDIEVAL_JAPANESE_WRONG_ARMOR_NEGATIVE_PROMPT)
    if _is_achaemenid_egyptian_context(p):
        parts.append(ACHAEMENID_EGYPTIAN_PERIOD_NEGATIVE_PROMPT)
        if _scene_requests_achaemenid_egyptian_armed_group(p):
            parts.append(ACHAEMENID_EGYPTIAN_ARMED_GROUP_NEGATIVE_PROMPT)
        if not _scene_explicitly_names_protective_torso_gear(p):
            parts.append(ACHAEMENID_EGYPTIAN_UNREQUESTED_ARMOR_NEGATIVE_PROMPT)
    if _is_medieval_central_asian_context(p):
        parts.append(MEDIEVAL_CENTRAL_ASIAN_WRONG_CULTURE_NEGATIVE_PROMPT)
    if _is_early_modern_europe_context(p):
        parts.append(EARLY_MODERN_EUROPE_WRONG_CULTURE_NEGATIVE_PROMPT)
    if _is_west_african_ashanti_british_context(p):
        parts.append(WEST_AFRICAN_ASHANTI_WRONG_CULTURE_NEGATIVE_PROMPT)
    if _is_goguryeo_silla_415_context(p):
        parts.append(GOGURYEO_SILLA_415_NEGATIVE_PROMPT)
    if _scene_requests_hou_bowl_object(p):
        parts.append(HOU_BOWL_NEGATIVE_PROMPT)
    if _scene_requests_modest_village_or_hamlet(p):
        parts.append(
            "palace compound replacing village, temple courtyard replacing village, "
            "elite mansion replacing village, official hall replacing village, "
            "government office replacing village, formal tiled courtyard replacing village, "
            "ornate tiled roofs on poor village, ornamental gate facade replacing village, "
            "close roofed veranda replacing village, Japanese temple village, "
            "palace veranda village, elite residence courtyard, grand gate compound, "
            "tiled palace roofs without scene request, tiled temple roofs without scene request, "
            "paper talisman on village post, calligraphy strip on village post, "
            "post plaque in village, signboard in village"
        )
    if needs_book_render_guard(p):
        parts.append(BOOK_RENDER_NEGATIVE_PROMPT)
    if _scene_requests_generic_object_evidence(p):
        parts.append(
            "object replaced by gate, object replaced by doorway, object replaced by building facade, "
            "palace gate instead of object, empty gate instead of object, blank doorway instead of object, "
            "person replacing object, portrait replacing object, live battle replacing painting, "
            "building exterior replacing book, building exterior replacing crown, missing named object, "
            "portrait replacing mirror, live person replacing mirror reflection, missing mirror, "
            "real hand outside mirror, pointing hand outside mirror, foreground hand beside object, "
            "human arm beside object, wall plate beside object, switch-like rectangle beside object, "
            "mounted plaque beside object, screw plate on wall behind object, "
            "wall-mounted mirror, rectangular framed mirror, picture frame replacing mirror, "
            "mirror as wall portrait, wall switch beside mirror, "
            "person sitting on empty seat, portrait replacing empty seat, "
            "no named object visible, signboard replacing object, wall plaque replacing object, "
            "calendar handwriting, calendar ink marks, tiny marks on calendar, month text, October text, "
            "date numerals, month numerals, double door, paired doors, switch beside door, modern latch, "
            "exterior gate replacing door, room replacing anatomical drawing, gate replacing anatomical drawing, "
            "architecture around bladder drawing, window replacing anatomical drawing, doorway replacing anatomical drawing, "
            "treasure box replacing crown, jewelry box replacing crown, lidded box replacing crown, "
            "coffer replacing crown, chest replacing crown, rectangular container replacing crown, "
            "bowl replacing crown, bucket replacing crown, pot replacing crown, cup replacing crown, "
            "cylindrical container replacing crown, open-top vessel replacing crown, "
            "European fairy-tale crown, tall fantasy crown, oversized spiky crown, "
            "ball finials on crown, large jewel cutouts on crown, velvet pillow, "
            "velvet cushion, royal display pillow, "
            "bowl-like crown, basin-like crown, hollow dish crown, top-down bowl crown, "
            "concave crown interior, crown as container, helmet-like crown dome, "
            "closed circular crown ring, upside-down bowl crown, pot-like crown, "
            "bowl replacing Golden Stool, crown replacing Golden Stool, treasure box replacing Golden Stool, "
            "missing Golden Stool, throne chair replacing sacred stool, golden bowl replacing Golden Stool, "
            "basin replacing Golden Stool, cauldron replacing Golden Stool, cup replacing Golden Stool, "
            "pot replacing Golden Stool, hollow vessel replacing Golden Stool, open bowl-shaped Golden Stool, "
            "door knobs beside object"
        )
    return _merge_negative_prompts(*parts)


def map_negative_prompt() -> str:
    """Negative prompt tokens that block generated maps in every channel."""
    return NO_MAP_NEGATIVE_PROMPT


def text_negative_prompt() -> str:
    """Negative prompt tokens that block generated text in every channel."""
    return NO_TEXT_NEGATIVE_PROMPT


def book_negative_prompt(prompt: str) -> str:
    """Prompt-specific negative tokens for coherent blank books/documents."""
    return BOOK_RENDER_NEGATIVE_PROMPT if needs_book_render_guard(prompt or "") else ""


def append_prompt_specific_negative_prompt(base_negative: str, prompt: str) -> str:
    p = prompt or ""
    scene = _scene_text(p)
    weapon_negative = (
        SINGLE_WEAPON_NEGATIVE_PROMPT
        if re.search(
            r"\bone visible weapon total\b|\bonly weapon-shaped object\b|\bone simple primary handheld equipment item\b",
            p,
            re.IGNORECASE,
        )
        else ""
    )
    female_safety_negative = (
        ADULT_FEMALE_SAFETY_NEGATIVE_PROMPT
        if _is_confirmed_adult_female_context(p)
        else ""
    )
    sword_negative = (
        UNREQUESTED_SWORD_NEGATIVE_PROMPT
        if _scene_requests_armed_figures(p)
        and not re.search(r"\b(sword|swords|blade|blades|dagger|knife|tachi|saber|sabre)\b|검|칼", scene, re.IGNORECASE)
        else ""
    )
    carried_vehicle_negative = (
        CARRIED_TRAVEL_VEHICLE_NEGATIVE_PROMPT
        if _scene_requests_carried_travel_vehicle(p)
        else ""
    )
    mounted_travel_negative = (
        "missing horse, missing rider, rider without horse, standing people replacing horse, "
        "kneeling people replacing mounted messenger, indoor room replacing mounted road, "
        "courtyard group replacing horse-and-rider pair, horse body without head, "
        "horse head without body, horse with extra legs, horse with missing legs, "
        "two-headed horse, horse with duplicate torso, modern saddle, decorative horse medallion"
        if _scene_requests_mounted_travel(p)
        else ""
    )
    group_planning_surface_negative = (
        GROUP_PLANNING_SURFACE_NEGATIVE_PROMPT
        if _scene_requests_group_planning_surface(p)
        else ""
    )
    household_relocation_negative = (
        "soldier lineup replacing moving families, guard lineup replacing household move, "
        "retainer families replaced by army lineup, army formation replacing residence entry, "
        "missing chests, missing bundles, missing family, missing residence entry, "
        "empty street replacing relocation, generic military portrait replacing household move, "
        "cauldron replacing chest, cooking pot replacing chest, brazier replacing chest, "
        "cart replacing chest, wheelbarrow replacing chest, empty tray replacing chest"
        if _scene_requests_household_relocation(p)
        else ""
    )
    road_logistics_negative = (
        "modern marching column, 20th century rural road, utility poles receding along road, "
        "telephone poles receding along road, crossarm poles, overhead wire perspective lines, "
        "Japanese rural utility pole, overhead cable beside castle gate, village street with utility lines, "
        "gatehouse-centered logistics scene, nearby village lane replacing open road, "
        "modern uniform column, buttoned uniform tunic, peaked cap, steel helmet, rifles"
        if _scene_requests_historical_road_logistics(p)
        else ""
    )
    craft_workshop_negative = (
        "modern kitchen stove, gas burner, modern saucepan, modern kettle, cooking pot replacing forge, "
        "faucet, sink faucet, written notebook in workshop, wall sign in workshop, "
        "modern collared shirt in workshop, clean modern workbench, missing forge, missing anvil, "
        "missing hammer, missing tongs, portrait replacing workshop, kitchen replacing craft workshop"
        if _scene_requests_preindustrial_craft_workshop(p)
        else ""
    )
    tally_object_negative = (
        "standing scribe portrait replacing tally objects, waist-up portrait replacing record evidence, "
        "full standing person replacing accounting objects, visible face in tally object shot, "
        "visible head in tally object shot, visible torso in tally object shot, "
        "modern collared shirt in tally scene, buttoned shirt in tally scene, "
        "building facade replacing counting mat, "
        "physical spear replacing spear shadow, spear held in hand, weapon shaft across counting mat, "
        "missing notched sticks, missing pebble counters, missing cord knots, missing counting mat, "
        "large flat board replacing counters, blank board replacing tally evidence"
        if _scene_requests_historical_tally_object_evidence(p)
        else ""
    )
    blank_record_negative = (
        "large front-facing document, open roster page, written roster page, "
        "paper full of kanji, paper full of Chinese characters, black text rows on document, "
        "visible page lines, handwritten roster, document heading, calligraphy page, "
        "blank white sheet held toward camera, large blank white rectangle, blank board replacing roster, "
        "poster-like roster, wall-mounted blank notice, open paper sheets on table, "
        "large paper surface, broad flat sheet"
        if _scene_requests_historical_blank_record_document(p)
        else ""
    )
    early_modern_astronomy_negative = (
        "astronomy scene replaced by indoor wall, astronomy scene replaced by office portrait, "
        "missing starry sky, missing brass astrolabe, missing armillary instrument, "
        "missing astronomical quadrant, two scholars replacing one scholar, officer portrait replacing astronomer"
        if _scene_requests_early_modern_europe_astronomy_observation(p)
        else ""
    )
    bed_rest_negative = (
        "suit jacket on bed, business suit on bed, military coat on bed, necktie on bed, "
        "epaulettes on bed, office clothing on bed, extra bedside visitor, two old men on bed, "
        "doctor visitor replacing resting person, modern hospital bed, modern bedroom"
        if _scene_requests_historical_bed_rest(p)
        else ""
    )
    early_modern_single_person_negative = (
        "two men replacing one man, duplicate twin nobleman, duplicate scholar, second visitor, "
        "second torso beside single person, partial extra person, mirror reflection duplicate, "
        "portrait duplicate person, two chairs with two men, instrument covering face, "
        "instrument replacing head, large foreground hand, modern suit on Renaissance person, "
        "fedora on Renaissance person, derby hat on Renaissance person, bowler hat on Renaissance person, "
        "top hat on Renaissance person, modern overcoat on Renaissance person"
        if _scene_requests_single_early_modern_person(p)
        else ""
    )
    early_modern_three_scholar_negative = (
        "four scholars, five scholars, six scholars, scholar crowd, business suits on scholars, "
        "neckties on scholars, fedoras on scholars, derby hats on scholars, bowler hats on scholars, "
        "top hats on scholars, modern overcoats on scholars, modern office suits, electric table lamp, desk lamp, "
        "fabric lampshade, modern lamp base, power cord, door in background, window in background, "
        "wall switch, switch plate, power outlet, modern door handle, wristwatch, modern watch, "
        "watch on wrist, bracelet, paper on table, document on table, written paper, "
        "notebook on table, ink marks on paper, large foreground fingers, oversized hands"
        if _scene_requests_early_modern_three_scholar_group(p)
        else ""
    )
    astronomical_surface_negative = (
        "letters on astronomical chart, numbers on astronomical chart, zodiac symbols, "
        "zodiac glyphs, coordinate numbers, degree numbers, tick number labels, "
        "alphabet ring on astrolabe, alphabet ring on armillary sphere, glyphs on instrument rim, "
        "written constellations, map labels on globe, country names on globe, labeled globe, "
        "pseudo glyphs on astronomy instrument, readable markings on star chart, "
        "perimeter tick marks, edge tick marks, rim tick marks, degree scale marks, "
        "numbered rim, alphabet rim, decorative star icons, star-shaped marks, "
        "calendar ring on instrument, engraved instrument letters, large letters "
        "on instrument rim, giant wall-mounted measuring dial, wall astronomy "
        "chart behind person, foreground hand on chart, forearm over chart, "
        "fingers beside chart"
        if _scene_requests_astronomical_surface_or_instrument(p)
        else ""
    )
    return _merge_negative_prompts(
        base_negative or "",
        COMMON_ANATOMY_NEGATIVE_PROMPT,
        ANIMAL_ANATOMY_NEGATIVE_PROMPT,
        VISUAL_QA_NEGATIVE_PROMPT,
        COMMON_STYLE_NEGATIVE_PROMPT,
        COMMON_COMPOSITION_NEGATIVE_PROMPT,
        UNREQUESTED_EXTRA_PEOPLE_NEGATIVE_PROMPT
        if _scene_requests_humans(p) and not _scene_requests_multiple_characters(p)
        else "",
        OUTDOOR_LOCATION_NEGATIVE_PROMPT
        if _scene_names_outdoor_location(p) or "OUTDOOR LOCATION EVIDENCE LOCK" in p
        else "",
        weapon_negative,
        sword_negative,
        carried_vehicle_negative,
        mounted_travel_negative,
        group_planning_surface_negative,
        household_relocation_negative,
        road_logistics_negative,
        craft_workshop_negative,
        tally_object_negative,
        blank_record_negative,
        early_modern_astronomy_negative,
        bed_rest_negative,
        early_modern_single_person_negative,
        early_modern_three_scholar_negative,
        astronomical_surface_negative,
        female_safety_negative,
        historical_negative_prompt(p, enabled=True),
        book_negative_prompt(p),
    )


def symbol_negative_prompt() -> str:
    """Negative prompt tokens for symbol generation."""
    return ""


def should_enable_historical_guard_for_context(
    config: dict | None = None,
    *values,
) -> bool:
    cfg = config or {}
    explicit = cfg.get("historical_accuracy_guard")
    if explicit is True or str(explicit).strip().lower() in {"1", "true", "yes", "on"}:
        return True
    if explicit is False or str(explicit).strip().lower() in {"0", "false", "no", "off"}:
        return False

    haystack: list[str] = []
    for key in (
        "preset_name",
        "preset_full_name",
        "channel_name",
        "youtube_channel_name",
        "series_name",
        "project_name",
        "form_name",
        "name",
        "full_name",
    ):
        value = cfg.get(key)
        if value is not None:
            haystack.append(str(value))
    haystack.extend(str(v) for v in values if v is not None)
    joined = " ".join(haystack)
    if _ONE_MINUTE_YEOKGONG_RE.search(joined):
        return True
    if str(cfg.get("language") or "").strip().lower() == "hi":
        return True
    return bool(
        re.search(
            r"(history|historical|ancient|civilization|civilisation|empire|kingdom|"
            r"india|indian|bharat|harappa|harappan|mohenjo|indus|vedic|veda|aryan|"
            r"sanskrit|mauryan|gupta|temple|fort|palace|dynasty)",
            joined,
            re.IGNORECASE,
        )
    )


def apply_reference_style_prefix(
    prompt: str,
    has_reference: bool,
    *,
    enable_historical_guard: bool = False,
) -> str:
    """썸네일/재생성 등 외부 경로용 프리픽스 적용 헬퍼.

    이미 프리픽스가 붙어 있으면 중복 부착을 피한다. has_reference=False 이면
    스타일 프리픽스는 생략하되 **문자 금지 지시는 항상** 뒤에 붙인다
    (v1.1.72). 레퍼런스 유무와 무관하게 이미지에 텍스트가 끼어드는 걸 차단.
    """
    p = (prompt or "").strip()
    if has_reference:
        if "STYLE REFERENCE LOCK" not in p and not p.startswith("STYLE:"):
            p = REFERENCE_STYLE_PREFIX + p
    return _apply_common_image_constraints(p, enable_historical_guard)


# ── 캐릭터 컷 제한 없음 ──

def cut_has_character(cut_number: int) -> bool:
    """캐릭터 등장 비율 제한 해제.

    캐릭터 앵커(캐릭터 이미지 또는 설명)가 있으면 모든 컷이 캐릭터 등장 가능 컷이다.
    """
    if cut_number is None or cut_number < 1:
        return False
    return True


# ── 레퍼런스/캐릭터 이미지 수집 ──

def collect_reference_images(project_id: str, config: dict) -> list[str]:
    """config 의 reference_images 에서 절대 경로 목록을 반환."""
    ref_imgs = config.get("reference_images", [])
    project_dir = resolve_project_dir(project_id, config, create=False)
    paths = []
    for rel in ref_imgs:
        p = Path(rel)
        abs_path = p if p.is_absolute() else project_dir / rel
        if abs_path.exists():
            paths.append(str(abs_path))
    return paths


def collect_character_images(project_id: str, config: dict) -> list[str]:
    """config 의 character_images 에서 절대 경로 목록을 반환."""
    char_imgs = config.get("character_images", [])
    project_dir = resolve_project_dir(project_id, config, create=False)
    paths = []
    for rel in char_imgs:
        p = Path(rel)
        abs_path = p if p.is_absolute() else project_dir / rel
        if abs_path.exists():
            paths.append(str(abs_path))
    return paths


# ── 프롬프트 빌더 ──

def build_image_prompt(
    image_prompt: str,
    global_style: str,
    *,
    has_reference: bool = False,
    has_character_slot: bool = False,
    character_description: str = "",
    enable_historical_guard: bool = False,
) -> str:
    """최종 이미지 프롬프트 조합.

    v1.1.58: 레퍼런스 이미지가 있으면 스타일은 전적으로 레퍼런스에 위임.
    프롬프트에는 피사체/구도/동작만 남기고, global_style 등 스타일 텍스트는 주입하지 않는다.
    레퍼런스가 없을 때만 global_style 을 폴백으로 사용.
    """
    base = _sanitize_flag_motif_positive_prompt(image_prompt or "")
    base, _ = _sanitize_hand_risky_prompt(base)
    base, _ = _sanitize_anatomy_risky_prompt(base)
    base = _sanitize_physics_risky_prompt(base)
    style_hint = sanitize_global_style_for_prompt(global_style, base)

    if has_reference:
        # ── 레퍼런스 있음 ──
        # v1.1.61: global_style 도 항상 포함. 이유: 로컬 ComfyUI 모델 중 일부는
        # IPAdapter 가 안 깔려있어서 레퍼런스 픽셀이 모델에 안 들어갈 수 있다.
        # 그 경우 스타일 정보가 텍스트 프리픽스뿐인데 그게 "스타일 복사하라" 는
        # 메타 지시라 실제 스타일 단어(예: "cartoon illustration")가 전혀 없다.
        # 결과가 기본값(실사)로 돌아가는 원인. global_style 을 항상 끼워넣어 안전.
        parts: list[str] = [REFERENCE_STYLE_PREFIX]

        if style_hint:
            parts.append(
                f"Apply this as rendering style only while preserving the subject, action, setting, period, and props from the scene: {style_hint}."
            )

        if has_character_slot:
            char_desc = character_description.strip()
            if char_desc:
                parts.append(
                    f"This cut features the main character: {char_desc}. "
                    "From the character reference image, use ONLY shape, silhouette, and design. "
                    "Recolor and restyle the character to match the style reference images."
                )
            else:
                parts.append(
                    "This cut features the main character from the attached character "
                    "reference image. Use ONLY the character's shape and design. "
                    "Recolor and restyle the character to match the style reference images."
                )

        if base:
            parts.append(base)

        # v1.1.72: 모든 컷 프롬프트에 "문자 금지" 지시를 마지막에 강제 append
        return _apply_common_image_constraints(" ".join(parts).strip(), enable_historical_guard)

    else:
        # ── 레퍼런스 없음: global_style 폴백 ──
        parts = []
        if base:
            parts.append(base)
        if style_hint:
            parts.append(
                f"Apply this as rendering style only while preserving the subject, action, setting, period, and props from the scene: {style_hint}."
            )

        if has_character_slot:
            char_desc = character_description.strip()
            if char_desc:
                parts.append(
                    f"This cut features the main character: {char_desc}. "
                    "Place the character clearly in frame, pose matching the scene."
                )

        # v1.1.72: 레퍼런스 없는 경로에도 동일하게 "문자 금지" 지시 강제
        return _apply_common_image_constraints(" ".join(parts).strip(), enable_historical_guard)
