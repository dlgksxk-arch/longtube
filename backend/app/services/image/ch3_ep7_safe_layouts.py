"""Deterministic safe-layout routing for CH3 episode 7 image QA fixes."""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class CH3EP7SafeLayoutRule:
    scene_prefix: str
    reference_id: str
    narration_fragment: str = ""


CH3_EP7_SAFE_LAYOUT_REFERENCE_FILENAMES: dict[str, str] = {
    "ch3_origin_livestock_crops": "ch3_origin_livestock_crops_layout_16x9.png",
    "ch3_bounty_transfer_path": "ch3_bounty_transfer_path_layout_16x9.png",
    "ch3_sacred_rice_work": "ch3_sacred_rice_work_layout_16x9.png",
    "ch3_dry_three_crop_field": "ch3_dry_three_crop_field_layout_16x9.png",
    "ch3_flooded_heavenly_rice_field": "ch3_flooded_heavenly_rice_field_layout_16x9.png",
    "ch3_modern_imperial_rice_evidence": "ch3_modern_imperial_rice_evidence_layout_16x9.png",
    "ch3_harvest_festival_offering": "ch3_harvest_festival_offering_layout_16x9.png",
    "ch3_single_sacred_rice_grain": "ch3_single_sacred_rice_grain_layout_16x9.png",
    "ch3_global_hainuwele_evidence": "ch3_global_hainuwele_evidence_layout_16x9.png",
    "ch3_everyday_itadakimasu_meal": "ch3_everyday_itadakimasu_meal_layout_16x9.png",
    "ch3_sericulture_continuity": "ch3_sericulture_continuity_layout_16x9.png",
    "ch3_weaving_hall_rice_prosperity": "ch3_weaving_hall_rice_prosperity_layout_16x9.png",
    "ch3_peace_breaking_cord": "ch3_peace_breaking_cord_layout_16x9.png",
    "ch3_storm_sun_cloud_path": "ch3_storm_sun_cloud_path_layout_16x9.png",
    "ch3_world_storm_landscape": "ch3_world_storm_landscape_layout_16x9.png",
    "ch3_battle_preparation_objects": "ch3_battle_preparation_objects_layout_16x9.png",
    "ch3_sun_storm_confrontation_ukehi": "ch3_sun_storm_confrontation_ukehi_layout_16x9.png",
    "ch3_channel_support_tokens": "ch3_channel_support_tokens_layout_16x9.png",
}


CH3_EP7_SAFE_LAYOUT_LOCKS: dict[
    str, tuple[str, str, str, tuple[str, ...]]
] = {
    "ch3_origin_livestock_crops": (
        "object-only Uke Mochi origin evidence with livestock tokens and visibly separate food crops, with no person or body part",
        "Copy the registered full-frame layout: exactly one ox-head token, exactly one horse-head token, one central earth bed, and separate millet, rice, wheat, soybean, and adzuki crop forms",
        "warm earth, unglazed clay animal-head tokens, natural grain stalks, and bean plants only",
        ("live animal", "animal body", "rider", "corpse", "map", "scroll"),
    ),
    "ch3_bounty_transfer_path": (
        "object-only recovery and transfer of Uke Mochi's bounty with no deity body",
        "Copy the registered full-frame layout: one crop-and-cocoon basket travels along one continuous red route from one earth node toward one larger sun node through a pale sky field",
        "plain woven basket, rice, beans, cocoons, unglazed route markers, earth, and pale sky only",
        ("smiling deity", "messenger figure", "flying person", "floating hand", "second basket"),
    ),
    "ch3_sacred_rice_work": (
        "object-only sacred rice-work evidence with no worker body",
        "Copy the registered full-frame layout: one flooded paddy with young rice shoots, exactly one plain wooden hoe, one rice bowl, and one sun disk, all fully visible",
        "paddy water, mud ridges, young rice shoots, unpainted wood, plain rice, and sunlight only",
        ("barefoot", "footprint", "goddess", "golden scale", "machine", "dry mature field"),
    ),
    "ch3_dry_three_crop_field": (
        "landscape-only dry-field cultivation of millet, wheat, and beans with no people",
        "Copy the registered full-frame dry field showing exactly three visibly separated crop groups in dry soil rows and no standing water",
        "dry natural soil, millet, wheat, soybean plants, and daylight only",
        ("rice paddy", "flood water", "farmer", "tool", "building"),
    ),
    "ch3_flooded_heavenly_rice_field": (
        "landscape-only sacred flooded heavenly rice paddy with no people",
        "Copy the registered full-frame flooded paddy: broad blue water remains visible around two curving mud ridges, young green rice shoots stay rooted in water, and one pale cloud band crosses the sky",
        "clear paddy water, dark mud ridges, young rice shoots, pale cloud, and sunlight only",
        ("dry field", "mature wheat", "terrace wall", "palace", "farmer", "foot"),
    ),
    "ch3_modern_imperial_rice_evidence": (
        "object-only present-day Imperial Palace rice-cultivation evidence without depicting the Emperor",
        "Copy the registered full-frame layout: one maintained flooded paddy, exactly one pair of black field boots, one dark-blue wash basin, and one rectangular seedling tray; no person is visible",
        "present-day paddy water, mud ridge, rice seedlings, black field boots, plain wash basin, and seedling tray only",
        ("woman", "empress", "goddess", "traditional costume", "palace facade", "ceremonial throne"),
    ),
    "ch3_harvest_festival_offering": (
        "object-only Shinto harvest-festival offering with no shrine architecture or participants",
        "Copy the registered full-frame altar layout: one bowl of white rice, exactly three rice panicles, and exactly four plain white shide ritual strips above one unpainted offering table",
        "unpainted wood, plain white rice, natural rice panicles, white ritual strips, and warm neutral wall only",
        ("red lantern", "festival crowd", "tiled shrine", "torii", "readable prayer"),
    ),
    "ch3_single_sacred_rice_grain": (
        "object-only belief focus with exactly one rice grain and no hand",
        "Copy the registered strict overhead layout: exactly one complete white rice grain rests at the center of one plain round wooden dish with broad empty space around it",
        "one natural white rice grain and one plain unpainted wooden dish only",
        ("second grain", "rice mound", "fingers", "glowing glyph", "face"),
    ),
    "ch3_global_hainuwele_evidence": (
        "object-only comparative Hainuwele-type crop-origin evidence with no ethnic portrait or invented writing",
        "Copy the registered full-frame comparison layout: one continuous route links exactly five blank island tokens above; below are one planted tuber, one plain vessel with three blank treasure tokens, and one sprouting tuber group",
        "warm earth, blank blue-grey clay tokens, red plant-fiber route, plain vessel, natural tubers, and green shoots only",
        ("indigenous girl", "Native American figure", "African figure", "costume", "beads", "carving", "map label", "pseudo-writing"),
    ),
    "ch3_everyday_itadakimasu_meal": (
        "object-only ordinary Japanese meal before eating with no diner or gesture",
        "Copy the registered full-frame meal tray: exactly one rice bowl, one soup bowl, one small vegetable dish, and exactly one pair of chopsticks, all resting on one plain tray",
        "plain wood, cooked white rice, simple soup, green vegetables, and wooden chopsticks only",
        ("speech bubble", "written word", "praying hands", "diner", "restaurant logo"),
    ),
    "ch3_sericulture_continuity": (
        "object-only sequence from silkworm and cocoon to silk thread, loom, folded cloth, and presentation box",
        "Copy the registered full-frame sericulture layout: exactly three silkworms on leaves, one cocoon, one upright thread frame, one folded white silk cloth, and one closed presentation box connected by one continuous white thread",
        "mulberry leaves, cream silkworms, white cocoon and silk, unpainted wood, and plain presentation box only",
        ("goddess", "empress", "mouth", "lips", "kimono", "modern spinning wheel", "family tree", "mask", "palace room"),
    ),
    "ch3_weaving_hall_rice_prosperity": (
        "landscape-only archaic unpainted weaving hall beside a prosperous rice field with no people",
        "Copy the registered full-frame layout: one plain raised timber weaving hall with exactly two visible loom frames stands beside one golden rice field under one sun disk",
        "plain unpainted archaic timber, simple vertical looms, golden rice field, pale sky, and sunlight only",
        ("floating palace", "tile", "gold roof", "silk banner", "modern building", "map"),
    ),
    "ch3_peace_breaking_cord": (
        "object-only transition from peaceful rice-and-weaving order to Susanoo's storm",
        "Copy the registered full-frame layout: rice and one loom remain on the sunlit left, one blue storm spiral remains on the right, and one red continuity cord is visibly broken once at center",
        "rice, unpainted loom, one sun disk, one storm spiral, red plant-fiber cord, and warm earth only",
        ("hourglass", "sand", "monster", "weapon", "second break"),
    ),
    "ch3_storm_sun_cloud_path": (
        "landscape-only route of Susanoo's storm rising toward Amaterasu's sun with no visible deity",
        "Copy the registered full-frame sky layout: one blue storm spiral at lower left follows one rising path through one dark-blue midpoint toward one golden sun disk at upper right between pale cloud bands",
        "pale cloud, blue-grey sky, one storm spiral, one route, and one sun disk only",
        ("palace", "staircase", "armored boot", "foot", "male figure", "female figure"),
    ),
    "ch3_world_storm_landscape": (
        "landscape-only world-shaking storm across mountain, earth, and sea with no creature",
        "Copy the registered full-frame storm landscape: dark cloud bands, two lightning strokes, one cracked mountain mass, one fissured earth path, and one large curling sea wave remain visibly separate",
        "dark natural storm cloud, mountain stone, cracked earth, river course, sea water, and lightning only",
        ("theatrical curtain", "monster", "building", "ship", "person", "foot"),
    ),
    "ch3_battle_preparation_objects": (
        "object-only Amaterasu battle-preparation evidence with archaic bow, arrows, mirror, rice, and magatama",
        "Copy the registered full-frame layout: exactly one plain bow, one tied bundle of exactly three arrows, one dark bronze mirror disk, one rice panicle, and one magatama cord are separated beneath one sun disk",
        "unpainted bow wood, reed arrows, aged bronze, green stone magatama, rice, and sunlight only",
        ("wrist", "neck", "warrior", "solar flare", "bloody knife", "steel katana", "extra arrow"),
    ),
    "ch3_sun_storm_confrontation_ukehi": (
        "object-only confrontation and ukehi oath evidence with sun, storm, ritual objects, and transformed tokens, never a sword duel",
        "Copy the registered full-frame ritual layout: one sun disk and one storm spiral oppose each other above one bow-and-arrow group, one magatama cord, one plain bronze blade, and two separate groups of blank transformed ritual tokens",
        "sunlight, blue storm token, unpainted bow, reed arrows, green stone magatama, aged bronze, plain clay tokens, and warm earth only",
        ("crossed swords", "duel", "skull", "balance scale", "teeth", "mouth", "explosion", "blood oath"),
    ),
    "ch3_channel_support_tokens": (
        "object-only channel-support closing image with exactly three sealed blank tokens and no interface text",
        "Copy the registered full-frame layout: exactly three equal sealed blank support tokens rest in one row beneath one sun disk on a warm neutral field",
        "plain blank earth-tone tokens, one sun disk, and warm neutral field only",
        ("creator", "tablet", "thumb", "button", "bell icon", "play icon", "lettering"),
    ),
    "ch3_uke_mochi_tragedy_evidence": (
        "object-only non-graphic Uke Mochi tragedy evidence with no living deity or corpse",
        "Use the registered exact tragedy layout of separated meal, torn cloth, and aged blade evidence on one continuous field",
        "plain meal vessels, earth-tone cloth, aged bronze, and bare earth only",
        ("silver sword", "rust animation", "living goddess", "wound"),
    ),
    "ch3_myth_to_niinamesai_offering": (
        "object-only continuity from Amaterasu's rice myth to present-day Niiname-sai offering",
        "Use the registered exact continuity layout joining archaic rice evidence to one present-day new-crop offering without a clock, calendar, or person",
        "rice plant, plain offering vessel, unpainted wood, and restrained continuity cord only",
        ("digital calendar", "modern farming machine", "red thread knot", "emperor portrait"),
    ),
    "ch3_niinamesai_offering_platform": (
        "object-only Niiname-sai new-rice offering on one plain platform with no officiant",
        "Use the registered exact offering layout with one shallow bowl of polished new rice on one unpainted timber platform",
        "new white rice, plain bowl, and unpainted timber only",
        ("bowing figure", "hidden altar", "lantern", "shrine facade"),
    ),
    "ch3_rice_stalk_torn_cloth": (
        "object-only return of life as one rice stalk beside non-graphic torn cloth evidence",
        "Use the registered exact layout with exactly one mature rice stalk and one torn earth-tone cloth, with no skull, corpse, or limb",
        "natural rice stalk, earth-tone plant-fiber cloth, and bare soil only",
        ("lotus", "skull", "rotting body", "bone"),
    ),
    "ch3_life_received_filled_bowl": (
        "object-only life-continuity answer centered on one filled food bowl and one living plant",
        "Use the registered exact layout with one intact rice plant connected to one filled wooden bowl on one continuous natural field",
        "living rice plant, plain cooked grain, unpainted wood, and earth only",
        ("hourglass", "theater curtain", "human heart", "golden harvest reveal"),
    ),
    "ch3_seed_death_rebirth_cross_section": (
        "object-only seed death-and-rebirth cross-section with no farmer or symbolic scale",
        "Use the registered exact soil cross-section showing one seed, one descending root, and one rising green shoot as a single natural cycle",
        "natural seed, layered soil, pale root, and green shoot only",
        ("lotus", "mud pile", "golden scale", "dry leaf", "hand"),
    ),
    "ch3_one_sacrifice_many_crops": (
        "object-only one-sacrifice-to-many-crops evidence with no deity body",
        "Use the registered exact layout showing one closed source bundle leading to exactly seven separate food-crop shoots",
        "earth-tone source bundle, natural soil, and seven distinct food crops only",
        ("pregnant goddess", "green woman", "fertility portrait", "exclamation mark"),
    ),
    "ch3_life_taken_empty_bowl_dilemma": (
        "object-only ethical tension between taking life and receiving food with no weapon or statue",
        "Use the registered exact layout centered on one knot between one empty bowl and one filled bowl on a plain continuous field",
        "unpainted wooden bowls, plain grain, plant-fiber cord, and bare earth only",
        ("blood", "knife", "blindfolded statue", "sword"),
    ),
    "ch3_continuous_spring_autumn_field": (
        "landscape-only continuous seasonal field from spring seedlings to autumn rice with zero visible people and no split panel",
        "Use the registered exact full-frame field in which green spring seedlings at far left gradually mature into golden autumn rice at far right under one continuous sky",
        "natural soil, green seedlings, golden mature rice, pale sky, and sunlight only",
        ("time-lapse explosion", "split image", "panel divider", "flower burst"),
    ),
}


CH3_EP7_LANDSCAPE_REFERENCE_IDS = frozenset(
    {
        "ch3_dry_three_crop_field",
        "ch3_flooded_heavenly_rice_field",
        "ch3_weaving_hall_rice_prosperity",
        "ch3_storm_sun_cloud_path",
        "ch3_world_storm_landscape",
        "ch3_continuous_spring_autumn_field",
    }
)


def _rules(reference_id: str, *scene_prefixes: str) -> tuple[CH3EP7SafeLayoutRule, ...]:
    return tuple(CH3EP7SafeLayoutRule(prefix, reference_id) for prefix in scene_prefixes)


CH3_EP7_SAFE_LAYOUT_SCENE_RULES: tuple[CH3EP7SafeLayoutRule, ...] = (
    CH3EP7SafeLayoutRule(
        "A perfectly balanced golden scale, with a bright white light outweighing a dark stone",
        "ch3_sacred_rice_work",
        "単なる 労働 では なく",
    ),
    CH3EP7SafeLayoutRule(
        "A perfectly balanced golden scale, with a bright white light outweighing a dark stone",
        "ch3_seed_death_rebirth_cross_section",
        "死 が 命 の 起源",
    ),
    *_rules(
        "ch3_origin_livestock_crops",
        "Countless small, glowing bundles of grains and animals appearing magically across a field",
        "A pristine ancient map of Japan covered in tiny, glowing golden sparks of expanding crops",
        "A beautifully crafted ancient Japanese scroll depicting a goddess erupting with nature's bounty",
    ),
    *_rules(
        "ch3_uke_mochi_tragedy_evidence",
        "A pristine silver sword slowly rusting and crumbling into dust over a field of golden wheat",
    ),
    *_rules(
        "ch3_bounty_transfer_path",
        "The messenger god carefully gathering golden seeds into a beautiful woven bamboo basket",
        "A glowing figure ascending rapidly through the white clouds, carrying a shining basket",
        "Amaterasu smiling warmly, her golden eyes reflecting the bright glow of the new seeds",
        "Amaterasu smiling warmly, holding a beautiful woven basket filled with glowing seeds",
    ),
    *_rules(
        "ch3_sacred_rice_work",
        "Amaterasu rolling up the sleeves of her pure white robes, ready for physical work",
        "Amaterasu stepping barefoot into the cool mud, planting bright green rice shoots",
        "A glowing golden aura surrounding a simple, muddy farming tool resting in a field",
        "A single, perfectly sharp drop of sparkling water hitting a green leaf, exploding with light",
    ),
    *_rules(
        "ch3_dry_three_crop_field",
        "Golden grains of wheat and green beans sprouting perfectly in neat, dry soil rows",
    ),
    *_rules(
        "ch3_flooded_heavenly_rice_field",
        "A breathtaking, glowing golden rice paddy in the heavens, surrounded by white clouds",
        "Perfect, mirror-like water reflecting the blue sky in an endlessly terraced celestial rice field",
    ),
    *_rules(
        "ch3_modern_imperial_rice_evidence",
        "A dignified figure in traditional clothing carefully planting rice in a pristine royal garden",
    ),
    *_rules(
        "ch3_myth_to_niinamesai_offering",
        "A glowing red thread wrapping intricately around a modern farming tool and an ancient scroll",
    ),
    *_rules(
        "ch3_harvest_festival_offering",
        "A vibrant, festive Shinto shrine decorated with golden rice stalks and red lanterns",
    ),
    *_rules(
        "ch3_niinamesai_offering_platform",
        "A pristine wooden tray holding a pure white mound of freshly steamed rice at an altar",
    ),
    *_rules(
        "ch3_rice_stalk_torn_cloth",
        "A delicate golden lotus flower blooming directly out of a dark, rotting skull",
    ),
    *_rules(
        "ch3_life_received_filled_bowl",
        "A large sand hourglass glowing brightly, the sand flowing endlessly without ever emptying",
        "A heavy theatrical black curtain pulling slowly to reveal a breathtaking, glowing harvest",
    ),
    *_rules(
        "ch3_seed_death_rebirth_cross_section",
        "A beautiful, blooming lotus flower emerging directly from a pile of foul, dark mud",
        "A dry, brown, crumbling leaf resting on the soil, with a tiny, brilliant green shoot piercing through it",
    ),
    *_rules(
        "ch3_single_sacred_rice_grain",
        "Extreme close-up of a single, flawless grain of white rice glowing with a tiny, warm light inside",
    ),
    *_rules(
        "ch3_one_sacrifice_many_crops",
        "A pregnant, glowing green earth goddess standing tall among blooming golden fields",
    ),
    *_rules(
        "ch3_global_hainuwele_evidence",
        "A vintage world map with a glowing golden line tracing mythologies across oceans",
        "A beautiful, innocent indigenous girl adorned with tropical flowers and colorful beads",
        "Golden coins and sparkling jewels spilling unnaturally out of dark, rich jungle mud",
        "Giant, flourishing taro and yam plants violently bursting from the tropical forest floor",
        "Multiple glowing dots connecting islands across a dark blue map of the Pacific Ocean",
        "An ancient Native American carving depicting a corn stalk growing out of a human figure",
    ),
    CH3EP7SafeLayoutRule(
        "A pristine silver knife suddenly dripping with thick, dark red blood",
        "ch3_life_taken_empty_bowl_dilemma",
        "命 を 奪う という 暴力 性",
    ),
    *_rules(
        "ch3_everyday_itadakimasu_meal",
        "A beautiful, warm dining table setting in a traditional Japanese home",
        "A stylized, glowing speech bubble icon floating beautifully above a clean dining table",
    ),
    *_rules(
        "ch3_sericulture_continuity",
        "Amaterasu smiling warmly, her golden eyes reflecting the bright glow of the silk",
        "Amaterasu gently holding a glowing white silk cocoon in her lips, pulling a fine, shimmering thread",
        "A beautifully crafted ancient Japanese wooden loom, glowing softly with golden light",
        "A radiant goddess in white standing proudly before a massive, complex wooden weaving loom",
        "A pristine, pure white silk kimono draped elegantly over a wooden stand, glowing magically",
        "A heavy, glowing blue aura radiating intensely from the fabric of a woven garment",
        "A glowing red thread wrapping intricately around a modern spinning wheel and an ancient loom",
        "A dignified figure in traditional clothing carefully tending to silkworms in a pristine royal room",
        "A vintage family tree scroll with a glowing silk cocoon symbol at the very top",
        "A perfectly folded, luxurious silk fabric presented gracefully in a carved wooden box",
        "An elegant Japanese map beautifully covered in an unbroken, glowing thread of white silk",
        "A beautifully crafted ancient Japanese scroll depicting a goddess weaving light",
        "A glowing golden mask of a god hovering mysteriously over a pile of pristine silk",
    ),
    *_rules(
        "ch3_weaving_hall_rice_prosperity",
        "A majestic, glowing golden divine weaving hall floating above thick, pure white clouds",
        "A breathtaking sunset reflecting perfectly on a massive, terraced rice field and silk banners",
        "A pristine ancient map of Japan glowing beautifully with a unified, warm golden light",
        "A majestic, glowing golden divine palace floating above thick, pure white clouds",
    ),
    *_rules(
        "ch3_continuous_spring_autumn_field",
        "Lush, vibrant green and gold plants rapidly sprouting and growing wildly under brilliant sunshine",
    ),
    *_rules(
        "ch3_peace_breaking_cord",
        "A large sand hourglass suddenly cracking, red sand spilling chaotically onto the floor",
    ),
    *_rules(
        "ch3_storm_sun_cloud_path",
        "A lonely, powerful god looking up towards a majestic palace floating in the bright clouds",
        "Massive, armored feet violently striking a cloudy staircase, cracking the white stone",
    ),
    *_rules(
        "ch3_world_storm_landscape",
        "A massive, swirling black storm cloud violently exploding into the clear blue sky",
        "Giant, ancient trees bending violently backwards under the force of a hurricane wind",
        "A massive, terrifying whirlpool spinning violently in the middle of a dark ocean under black clouds",
        "A heavy theatrical black curtain shaking violently, as if a monster is behind it",
    ),
    *_rules(
        "ch3_battle_preparation_objects",
        "A gentle golden flame suddenly erupting into a violent, roaring solar flare",
        "Glowing green jade beads clinking together as they are tightly wrapped around divine wrists",
        "A pristine silver knife suddenly dripping with thick, dark red blood, but made of golden light",
    ),
    *_rules(
        "ch3_sun_storm_confrontation_ukehi",
        "A brilliant flash of blue lightning striking directly against a perfectly glowing golden sun",
        "Two incredibly sharp, polished iron swords crossing violently, creating bright golden sparks",
        "A glowing golden scale perfectly balancing a dark skull and a brilliant sun emblem",
        "A beautifully crafted iron sword and green jade beads being crushed by massive divine teeth",
        "A massive, explosive spark of golden creative energy bursting from the clash of two gods",
    ),
)


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def match_ch3_ep7_safe_layout_reference(
    text: str = "",
    *,
    scene: str = "",
    narration: str = "",
) -> str:
    """Return an exact-layout id only when a registered scene/narration rule matches."""
    raw_scan = _normalized(text)
    scene_scan = _normalized(scene)
    narration_scan = _normalized(narration)
    for rule in CH3_EP7_SAFE_LAYOUT_SCENE_RULES:
        prefix = _normalized(rule.scene_prefix)
        if prefix:
            if scene_scan:
                if not scene_scan.startswith(prefix):
                    continue
            elif prefix not in raw_scan:
                continue
        narration_fragment = _normalized(rule.narration_fragment)
        if narration_fragment:
            narration_haystack = narration_scan or raw_scan
            if narration_fragment not in narration_haystack:
                continue
        return rule.reference_id
    return ""
