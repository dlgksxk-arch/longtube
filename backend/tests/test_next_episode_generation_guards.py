import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.image.comfyui_service import (  # noqa: E402
    _BAEKJE_EP02_SHICHISHITO_REFERENCE_PATH,
    _EXACT_LAYOUT_REFERENCE_COPY_IDS,
    _EXACT_LAYOUT_REFERENCE_COPY_MODEL,
    _EXACT_LAYOUT_REFERENCE_PATHS,
    _exact_layout_reference_spec,
    _face_count_confirms_face_only_pair,
    _should_use_baekje_ep02_mixed_settlers_layout,
    _should_use_baekje_ep02_shichishito_reference,
    _should_ignore_internal_text_detector,
    _should_ignore_object_person_segmentation,
    _should_check_split_panel_after_generation,
    _validate_baekje_ep02_shichishito_reference_geometry,
    _validate_exact_layout_reference_geometry,
    expected_effective_image_model_id,
)
from app.services.image.asset_guard import image_matches_prompt, write_prompt_sidecar  # noqa: E402
from app.services.image.prompt_compiler import (  # noqa: E402
    _BAEKJE_EP02_CHRONOLOGY_BLOCK_LOCKS,
    _BAEKJE_EP02_GUTHE_POLITICS_LOCKS,
    _BAEKJE_EP02_OPENING_LOCKS,
    _BAEKJE_EP02_RECORD_CONFLICT_LOCKS,
    _BAEKJE_EP02_REMAINING_LOCKS,
    _JAPANESE_MYTH_ADDITIONAL_FACE_SCENE_LOCKS,
    _JAPANESE_MYTH_ADDITIONAL_OBJECT_SCENE_LOCKS,
    compile_image_prompt,
    prepare_scene_contract_source,
)
from app.services.image.ch3_ep7_safe_layouts import (  # noqa: E402
    CH3_EP7_LANDSCAPE_REFERENCE_IDS,
    CH3_EP7_SAFE_LAYOUT_LOCKS,
    CH3_EP7_SAFE_LAYOUT_REFERENCE_FILENAMES,
    CH3_EP7_SAFE_LAYOUT_SCENE_RULES,
)


class NextEpisodeGenerationGuardTests(unittest.TestCase):
    def test_yamnaya_runtime_alignment_does_not_replace_people_with_artifact_wallpaper(self):
        cases = (
            (
                "Kurgan cemetery emphasizing richly furnished male graves beside sparse ordinary burials",
                "That interpretation remains a model, but graves plainly reveal hierarchy, gender, and concentrated privilege.",
                "exactly two separate full-body bioarchaeologists",
            ),
            (
                "Corded Ware settlement containing mixed families, local farming tools, steppe customs, and new graves",
                "Corded Ware communities became their own societies, mixing migrants with people already living there.",
                "mixed local and migrant Corded Ware families work together",
            ),
            (
                "Updated research map moving the earliest language origin toward the Caucasus-Lower Volga zone",
                "Recent research has shifted the deepest origin toward the Caucasus-Lower Volga region.",
                "mixed full-body team of women and men in modern field jackets",
            ),
            (
                "Yamnaya chief judging a dispute before several clan representatives and tethered herds",
                "Chiefdoms coordinated movement, settled disputes, and controlled relationships extending far beyond one camp.",
                "Exactly three fully clothed adult Yamnaya men",
            ),
            (
                "Rival heirs arguing over cattle while allied camps split and armed followers choose sides",
                "It could also fracture when heirs competed, herds failed, or subordinate chiefs rebelled.",
                "widely separated complete bodies inside one visibly divided camp",
            ),
            (
                "Ancient skull, wagon track, kurgan, and mixed family joined in a final cinematic tableau",
                "And like this episode if buried bones made Europe's transformation feel suddenly human.",
                "Exactly four living prehistoric relatives",
            ),
        )
        for scene, narration, expected in cases:
            with self.subTest(scene=scene):
                source = (
                    "Year/period: 3500 BCE to 2000 BCE; Yamnaya cultural horizon; "
                    f"Scene evidence: Source workbook scene: {scene}; Scene: {scene}; "
                    "NARRATION VISUAL ALIGNMENT: match this cut's spoken moment through visible action; "
                    f"Narration context: {narration}"
                )
                compiled = compile_image_prompt(
                    source,
                    model_id="comfyui-z-image-turbo",
                )

                self.assertNotEqual(compiled.person_count, 0)
                self.assertNotEqual(compiled.scene_kind, "object")
                self.assertIn(expected, compiled.positive)

    def test_baekje_ep02_mixed_settlers_layout_route_is_narrow(self):
        prompt = (
            "Scene evidence: Source workbook row 02-103 anchors this scene; "
            "Narration context: 여기에 예계 주민과 중국 군현에서 이동한 사람들까지 섞이며,"
        )
        self.assertTrue(_should_use_baekje_ep02_mixed_settlers_layout(prompt))
        self.assertFalse(
            _should_use_baekje_ep02_mixed_settlers_layout(
                prompt.replace("02-103", "02-104")
            )
        )
        self.assertFalse(
            _should_use_baekje_ep02_mixed_settlers_layout(
                prompt.replace("예계 주민", "다른 주민")
            )
        )

    def test_baekje_ep02_shichishito_uses_exact_reference_only_for_row_136(self):
        prompt = (
            "Scene evidence: Source workbook row 02-136 anchors this scene to Baekje history; "
            "Narration context: 칠지도 같은 유물은 그 복잡한 관계가 물질로 남은 사례죠"
        )

        self.assertTrue(_should_use_baekje_ep02_shichishito_reference(prompt))
        self.assertFalse(
            _should_use_baekje_ep02_shichishito_reference(
                prompt.replace("02-136", "02-137")
            )
        )
        self.assertFalse(
            _should_use_baekje_ep02_shichishito_reference(
                prompt.replace("칠지도 같은 유물은 그 복잡한 관계가 물질로 남은 사례죠", "다른 유물")
            )
        )
        scores = _validate_baekje_ep02_shichishito_reference_geometry(
            _BAEKJE_EP02_SHICHISHITO_REFERENCE_PATH
        )
        self.assertEqual(scores, (1.0, 1.0, 1.0))

    def test_exact_layout_references_are_narrow_and_self_validate(self):
        cases = {
            "baekje_ep02_row156": (
                "Source workbook row 02-156 anchors this scene; "
                "Narration context: 낙랑과 대방의 전쟁으로 마한의 질서가 흔들리는 바로 그 틈에서,"
            ),
            "baekje_ep02_row157": (
                "Source workbook row 02-157 anchors this scene; "
                "Narration context: 고이왕은 주변 세력을 누르고 관등과 법, 군사 지휘권을 손에 쥡니다."
            ),
            "ch2_yamnaya_elite_grave": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Ochre-covered male burial beneath "
                "a kurgan with wagon wheels, dagger, animal offerings, and silent mourners"
            ),
            "ch2_yamnaya_alliance": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Yamnaya chief and farmer elder facing "
                "each other between armed followers and exchanged prestige gifts"
            ),
            "ch2_yamnaya_mobile_tools": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Seasonal Yamnaya camp being dismantled "
                "as wagons form a departing column"
            ),
            "ch2_yamnaya_pit_grave": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Cross-section of a simple pit grave "
                "beneath an earthen kurgan beside a living steppe camp"
            ),
            "ch2_gorodtsov_three_graves": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Gorodtsov comparing three distinct "
                "grave plans on a field table beside excavated mounds"
            ),
            "ch2_gorodtsov_identity": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Gorodtsov recording an exposed pit "
                "grave near the Donets River with early excavation workers"
            ),
            "ch2_yamnaya_social_actors": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Yamnaya chief, young herder, "
                "metalworker, women, children, and cattle gathered around a council fire"
            ),
            "ch2_mykhailivka_mobile_settlement": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Mobile wagons approaching the "
                "fortified riverside settlement of Mykhailivka on the lower Dnieper"
            ),
            "ch2_yamnaya_livelihoods": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Busy Yamnaya camp with herding, "
                "fishing, pottery making, food preparation, and copper working"
            ),
            "ch2_yamnaya_chiefdom_coordination": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Yamnaya chief judging a dispute "
                "before several clan representatives and tethered herds"
            ),
            "ch2_yamnaya_herd_wealth_risk": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Young herder guarding a dense cattle "
                "herd while armed strangers watch from a distant ridge"
            ),
            "ch2_yamnaya_mobility_command": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Long wagon column crossing exposed "
                "grassland under the watch of mounted scouts and armed leaders"
            ),
            "ch2_yamnaya_mobility_command_early": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Young herder driving cattle while "
                "families repair an ox-drawn wagon during a cold migration"
            ),
            "ch2_yamnaya_open_steppe_origin_landscape": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Wide Pontic-Caspian grassland between "
                "distant rivers with cattle camps and wooden wagons"
            ),
            "ch2_yamnaya_cold_dry_grazing_risk_landscape": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Cattle searching sparse winter grass "
                "beside a frozen river and a worried pastoral camp"
            ),
            "ch2_yamnaya_single_kurgan": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Workers piling earth into a tall "
                "kurgan visible across an otherwise flat steppe"
            ),
            "ch2_yamnaya_successive_burials": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Layered kurgan cross-section with "
                "successive burials arranged above the founding grave"
            ),
            "ch2_yamnaya_animal_offerings": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Slaughtered sheep and cattle portions "
                "placed beside an elite burial during a solemn rite"
            ),
            "ch2_yamnaya_authority_stela": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Anthropomorphic stone stela with carved "
                "belt, hands, axe, and dagger overlooking a burial"
            ),
            "ch2_yamnaya_rare_elite_ratio": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Small group of elite male graves "
                "contrasted with a much larger living Yamnaya population"
            ),
            "ch2_yamnaya_two_regional_burials": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Two regional Yamnaya burials with "
                "distinct body positions and sharply different grave goods"
            ),
            "ch2_yamnaya_complete_wagon_grave": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Complete four-wheeled wooden wagon "
                "lowered into a deep grave beside the deceased chief"
            ),
            "ch2_yamnaya_wagon_burial_labor": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Exhausted workers and oxen surrounding "
                "the chief's wagon burial as elite relatives supervise"
            ),
            "ch2_yamnaya_copper_specialist": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Metalworker raising a newly cast copper "
                "blade beside a glowing crucible and watching chiefs"
            ),
            "ch2_yamnaya_ten_copper_artifacts": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Copper daggers, axes, spearheads, and "
                "ornaments arranged around one richly furnished burial"
            ),
            "ch2_yamnaya_oligarchy_model": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Reich comparing ancient Y chromosomes, "
                "rich male graves, and a narrowing ancestry chart"
            ),
            "ch2_yamnaya_hierarchy_privilege": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Kurgan cemetery emphasizing richly "
                "furnished male graves beside sparse ordinary burials"
            ),
            "ch2_yamnaya_monumental_inequality": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Row of kurgans growing across the "
                "steppe behind a commanding Yamnaya chief"
            ),
            "ch2_yamnaya_household_transport": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Ox-drawn carts and wagons loaded with "
                "hides, vessels, food, tools, and families"
            ),
            "ch2_yamnaya_ox_traction": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Powerful oxen straining against a "
                "loaded four-wheeled wagon on rough steppe ground"
            ),
            "ch2_yamnaya_riding_osteology": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Young herder riding a compact steppe "
                "horse beside cattle with anatomical bone details inset"
            ),
            "ch2_yamnaya_horse_research": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Archaeologists comparing disputed "
                "riding traces, horse teeth, and genetic timelines at an excavation"
            ),
            "ch2_yamnaya_non_cavalry_migration": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Yamnaya migrants with ox wagons and "
                "a few riders, deliberately avoiding a mass cavalry charge"
            ),
            "ch2_yamnaya_mobile_network": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Families, cattle, wagons, ritual "
                "objects, and messengers moving along interconnected steppe routes"
            ),
            "ch2_yamnaya_camp_fission": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Yamnaya families dividing between "
                "two wagon columns while chiefs negotiate beside a fire"
            ),
            "ch2_yamnaya_peer_network": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Multiple independent chiefs connected "
                "by marriage gifts, cattle exchanges, and shared burial customs"
            ),
            "ch2_yamnaya_three_rivers_kurgans": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Chain of matching kurgans stretching "
                "between the Dnieper, Don, and Volga river landscapes"
            ),
            "ch2_yamnaya_danube_frontier": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Wagon column descending toward Danube "
                "farmland, timber houses, fields, and defensive fences"
            ),
            "ch2_yamnaya_wealth_systems": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Yamnaya chief and farmer elder studying "
                "each other's cattle, fields, weapons, and households"
            ),
            "ch2_yamnaya_village_camp_river": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Central European farming village facing "
                "a temporary Yamnaya camp across a river"
            ),
            "ch2_yamnaya_frontier_four_outcomes": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Exchange feast shadowed by armed guards, "
                "a marriage procession, tense bargaining, and burned fencing"
            ),
            "ch2_yamnaya_cautious_excavation": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Excavators carefully examining a burned "
                "house and injured skeleton without assigning an attacker"
            ),
            "ch2_yamnaya_demographic_shift": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Population silhouettes shifting "
                "dramatically as steppe ancestry spreads into Central Europe"
            ),
            "ch2_corded_ware_adna_signature": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Corded Ware cemetery in Germany with "
                "sampled teeth and a glowing ancient-DNA profile"
            ),
            "ch2_corded_ware_funeral": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Corded Ware funeral with cord-decorated "
                "pottery, stone battle-axe, wool clothing, and single burial"
            ),
            "ch2_corded_ware_beaker": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Close view of hands pressing twisted "
                "cord into the surface of a wet clay beaker"
            ),
            "ch2_corded_ware_single_grave": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Corded Ware warrior buried alone with "
                "polished battle-axe and corded beaker"
            ),
            "ch2_yamnaya_corded_burial_link": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Yamnaya kurgan and Corded Ware grave "
                "linked by ancestry strands despite different burial arrangements"
            ),
            "ch2_haak_adna_sampling": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Ancient-DNA researchers sampling teeth "
                "and sequencing genomes across a map of prehistoric Europe"
            ),
            "ch2_corded_ware_75_ratio": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Corded Ware warrior portrait formed "
                "from three parts steppe ancestry and one part local ancestry"
            ),
            "ch2_steppe_migration_demographic": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Dense east-to-west migration arrows "
                "carrying families into Central European river valleys"
            ),
            "ch2_living_household_migration": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Yamnaya-related families arriving with "
                "children, livestock, wagons, tools, and household goods"
            ),
            "ch2_steppe_ancestry_persistence": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Generations of Central European "
                "families connected through an enduring steppe ancestry line"
            ),
            "ch2_multiple_ancestry_mixture": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Layered portraits of later European "
                "populations built from multiple ancestry streams without racial typology"
            ),
            "ch2_farming_valley_transition": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Farming valley transforming as new "
                "households, graves, animals, and customs fill the region"
            ),
            "ch2_local_lineage_outcomes": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Farmer families choosing among retreat, "
                "guarded resistance, intermarriage, and alliance with migrants"
            ),
            "ch2_neolithic_corded_stratigraphy": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Abandoned Neolithic house beneath a "
                "later Corded Ware settlement with missing family silhouettes"
            ),
            "ch2_genetic_conversations_unknown": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Ancient DNA chart fading into a tense "
                "face-to-face meeting between chiefs and villagers"
            ),
            "ch2_corded_institutions_table": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Table of battle-axes, copper daggers, "
                "beakers, marriage gifts, and burial plans under study"
            ),
            "ch2_corded_zone_landscape": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Panoramic Corded Ware cultural zone "
                "spanning forests, rivers, farmland, and eastern grassland"
            ),
            "ch2_corded_regional_diversity": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Several distinct Corded Ware communities "
                "with varied houses, clothing, graves, and landscapes"
            ),
            "ch2_corded_settlement_network": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Travelers carrying corded pottery and "
                "axes between distant but related settlements"
            ),
            "ch2_bell_beaker_mixed_ancestry": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Bell Beaker archer arriving in western "
                "Europe with distinctive vessel, wrist guard, and mixed ancestry"
            ),
            "ch2_sintashta_andronovo_network": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Migration paths continuing east toward "
                "fortified Sintashta settlements and later Andronovo herders"
            ),
            "ch2_repeated_migration_routes": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Branching migration routes crossing, "
                "merging, and turning back across Eurasia over generations"
            ),
            "ch2_partial_cultural_packages": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Separate migrant columns carrying different "
                "combinations of livestock, tools, rituals, and ancestry"
            ),
            "ch2_language_ancestry_mismatch": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Family tree of languages crossing but not "
                "perfectly matching an ancient ancestry map"
            ),
            "ch2_language_shift_question": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Village assembly divided between steppe "
                "migrants and local speakers during a tense negotiation"
            ),
            "ch2_gimbutas_research_table": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Gimbutas arranging kurgan maps, warrior "
                "stelae, and Old European settlement photographs"
            ),
            "ch2_kurgan_hypothesis": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Gimbutas tracing a connection from kurgans "
                "to a branching Proto-Indo-European language map"
            ),
            "ch2_gimbutas_old_europe_model": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Armed mobile herders approaching a prosperous "
                "Neolithic farming settlement under Gimbutas's model"
            ),
            "ch2_gimbutas_imposition_model": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Victorious Yamnaya-style leaders presiding "
                "over a subdued village in a clearly labeled interpretive tableau"
            ),
            "ch2_weapons_patrilineal_model": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Male war band displaying axes and spears "
                "beneath a lineage tree centered on fathers and sons"
            ),
            "ch2_no_continent_battlefield": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Dramatic invasion mural breaking apart into "
                "scattered graves, settlements, and uncertain archaeological traces"
            ),
            "ch2_anthony_mechanism_revision": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Anthony comparing Gimbutas's invasion arrows "
                "with a network of alliances and elite contacts"
            ),
            "ch2_elite_recruitment_network": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Local leaders joining a prestigious steppe "
                "council while villagers observe the political shift"
            ),
            "ch2_small_group_power_package": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Compact Yamnaya delegation entering a village "
                "with copper weapons, horses, cattle, and ceremonial gifts"
            ),
            "ch2_chief_network_choice": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Farmer elder weighing a stone axe against "
                "offered copper weapon and marriage bracelet"
            ),
            "ch2_resist_or_join_network": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Village factions split as the farmer elder "
                "chooses between armed resistance and alliance"
            ),
            "ch2_parpola_small_powerful_groups": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Local chiefs entering a compact migrant "
                "coalition around a shared feast and weapons display"
            ),
            "ch2_prestige_trade_weapon_cost": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Copper dagger, rare ornament, livestock gift, "
                "and polished axe displayed before watching villagers"
            ),
            "ch2_marriage_alliance_dual_claims": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Wedding between steppe migrant and farming "
                "family before two watchful kin groups"
            ),
            "ch2_elite_language_diffusion": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Local chief addressing retainers in a new "
                "language as interpreters and scribeless memory keepers listen"
            ),
            "ch2_language_social_access": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Young villagers learning elite speech during "
                "feasting, oath making, guard service, and courtship"
            ),
            "ch2_three_generation_language_shift": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Three generations of one mixed household "
                "shifting gradually from local speech to steppe-derived speech"
            ),
            "ch2_recruitment_coercion_cost": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Armed retainers standing behind negotiators "
                "as a reluctant village accepts new obligations"
            ),
            "ch2_raid_protection_mechanism": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Night cattle raid followed by frightened "
                "villagers seeking protection from a powerful chief"
            ),
            "ch2_feast_loyalty_intimidation": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Yamnaya chief distributing meat and gifts "
                "during a feast guarded by armed followers"
            ),
            "ch2_kurgan_landscape_dominance": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Towering kurgan overlooking smaller farms, "
                "paths, and graves across a settled valley"
            ),
            "ch2_service_status_resources": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Young herder accepting a weapon and oath "
                "before joining the chief's mobile retinue"
            ),
            "ch2_craft_patron_authority": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Metalworker presenting a polished copper "
                "axe to the Yamnaya chief before assembled followers"
            ),
            "ch2_alliance_expansion_network": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Network of allied camps expanding around "
                "shared grazing land and marriage connections"
            ),
            "ch2_network_fracture": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Rival heirs arguing over cattle while allied "
                "camps split and armed followers choose sides"
            ),
            "ch2_branching_wagon_routes": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Single wagon route dividing into several "
                "independent migration columns under rival leaders"
            ),
            "ch2_speech_contact_loss": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: One ancestral speech line dividing into "
                "increasingly distinct regional conversations"
            ),
            "ch2_shared_word_echoes": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Kin group, cattle, wagon wheel, and ritual "
                "fire linked to reconstructed word roots"
            ),
            "ch2_local_vocabulary_inputs": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Steppe speakers learning local words while "
                "working fields and entering European forests"
            ),
            "ch2_language_four_processes": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Mixed household speaking across generations "
                "during farming, herding, marriage, and ritual"
            ),
            "ch2_ancestral_language_branches": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Branching language tree rising behind early "
                "European communities without modern national symbols"
            ),
            "ch2_writing_gap_uncertainty": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Blank centuries between prehistoric migration "
                "maps and the first written Indo-European texts"
            ),
            "ch2_three_evidence_columns": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Battle-axe, ancient skeleton, and comparative "
                "word list aligned as three evidence columns"
            ),
            "ch2_mismatched_evidence_fields": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Three overlapping maps from archaeology, "
                "genetics, and linguistics with mismatched boundaries"
            ),
            "ch2_yamnaya_two_ancestry_sources": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Yamnaya family emerging from two older "
                "ancestry streams meeting north of the Caucasus"
            ),
            "ch2_clv_population_network": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Pre-Yamnaya communities connected between "
                "the Caucasus foothills and lower Volga river"
            ),
            "ch2_source_population_mixture": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Multiple older communities merging into "
                "the Yamnaya horizon before its expansion"
            ),
            "ch2_four_predecessor_model": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Four predecessor cultural zones converging "
                "around early Yamnaya settlements and graves"
            ),
            "ch2_language_ancestry_structure_dispute": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Researchers debating separate maps of "
                "language origin, ancestry formation, and cultural development"
            ),
            "ch2_paternal_lineage_mismatch": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Y chromosome lineages from Yamnaya graves "
                "failing to align perfectly with Corded Ware men"
            ),
            "ch2_complex_steppe_ancestry_network": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Complex ancestry network replacing a "
                "simplistic arrow from one Yamnaya man to all Europeans"
            ),
            "ch2_corded_ware_mixed_society": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Corded Ware settlement containing mixed "
                "families, local farming tools, steppe customs, and new graves"
            ),
            "ch2_corded_beaker_bronze_sequence": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Corded Ware community transitioning into "
                "Bell Beaker and later Bronze Age cultural scenes"
            ),
            "ch2_population_power_chain_reaction": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Successive generations passing movement, "
                "authority, and ancestry across a changing European map"
            ),
            "ch2_grave_sample_archive": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Modern researchers entering a museum store "
                "filled with carefully boxed prehistoric skeletons"
            ),
            "ch2_adna_sterile_sampling_station": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Reich's laboratory sampling a petrous bone "
                "in a sterile clean room"
            ),
            "ch2_adna_powder_extraction_pipeline": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Gloved technicians processing ancient bone "
                "powder through clean laboratory equipment"
            ),
            "ch2_fragment_comparison_matrix": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Sequencing screens linking prehistoric "
                "individuals across a time-scaled map of Europe"
            ),
            "ch2_haak_2015_steppe_cluster": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Scientists watching a clear steppe ancestry "
                "cluster emerge from ancient genome data"
            ),
            "ch2_central_europe_demographic_influx": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Ancient population map showing a major "
                "influx from the steppe into Central Europe"
            ),
            "ch2_migration_not_invasion_model": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Gimbutas's kurgan map beside DNA results "
                "with confirmed migration and unconfirmed battle scenes separated"
            ),
            "ch2_genes_cannot_show_consent": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Mixed-ancestry couple at a prehistoric "
                "wedding with uncertain expressions and armed relatives"
            ),
            "ch2_village_response_unknown": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Two neighboring villages responding "
                "differently to the same approaching migrant group"
            ),
            "ch2_five_missing_decisions": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Rapid tableau of a shouted insult, sworn "
                "oath, guarded hostage, cattle raid, and handshake"
            ),
            "ch2_ancestry_to_human_decisions": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Individual faces in a tense frontier crowd "
                "emerging from an impersonal ancestry graph"
            ),
            "ch2_klejn_route_critique": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Klejn challenging a straight migration "
                "arrow with alternative ancestry distributions on a map"
            ),
            "ch2_competing_homeland_models": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Competing homeland circles around the "
                "steppe, Caucasus, and western Asia"
            ),
            "ch2_clv_deep_origin_update": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Updated research map moving the earliest "
                "language origin toward the Caucasus-Lower Volga zone"
            ),
            "ch2_narrow_migration_conclusion": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Firm evidence panel connecting Yamnaya-"
                "related groups to major Central European ancestry change"
            ),
            "ch2_some_language_branches": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Steppe migration routes aligned with "
                "several, but not all, Indo-European language branches"
            ),
            "ch2_anonymous_chief_fresh_kurgan": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Yamnaya chief alive beside a fresh kurgan "
                "as followers, wagons, and herds assemble"
            ),
            "ch2_chief_unseen_future": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Yamnaya chief looking west across empty "
                "grassland with distant future maps hidden in clouds"
            ),
            "ch2_chief_immediate_horizon": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Chief surveying thin pasture, rival "
                "campfires, a marriage delegation, and dark winter clouds"
            ),
            "ch2_three_way_camp_decision": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Chief pointing as one wagon group prepares "
                "westward and another negotiates with visitors"
            ),
            "ch2_network_over_skirmish": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Small cattle skirmish contrasted with a "
                "vast allied route of camps, rivers, and kurgans"
            ),
            "ch2_mobility_status_force_system": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Wagons, marriage bonds, elite graves, "
                "armed retainers, and herds forming one power system"
            ),
            "ch2_leader_language_households": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Successive farmer leaders joining the "
                "network while children learn the prestige language"
            ),
            "ch2_new_corded_identity": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Mixed children growing into a distinct "
                "Corded Ware community unlike either original group"
            ),
            "ch2_camp_grave_gradual_change": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Night-to-dawn sequence of camps and graves "
                "spreading gradually across a European landscape"
            ),
            "ch2_dead_scale_living_motives": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Opened graves and DNA charts surrounding "
                "unseen prehistoric negotiations beneath the soil"
            ),
            "ch2_royal_horse_power_teaser": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Horse beside an Indo-European royal "
                "sacrifice ground as priests and a tense claimant approach"
            ),
            "ch2_ritual_authority_mechanism": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Priests arranging a horse sacrifice while "
                "the future king faces assembled warriors"
            ),
            "ch2_four_horse_ritual_traditions": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Horse-sacrifice traditions connected across "
                "the steppe, ancient India, Rome, and medieval Ireland"
            ),
            "ch2_royal_horse_enclosure": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Royal horse entering a guarded ritual "
                "enclosure before a crowd of rival nobles"
            ),
            "ch2_final_bones_migration_synthesis": (
                "Year/period: 3500 BCE to 2000 BCE; Scene: Ancient skull, wagon track, kurgan, and "
                "mixed family joined in a final cinematic tableau"
            ),
            "ch3_day_night_separation_sky": (
                "Year/period: Japanese mythic creation era; Scene: An abstract visual showing a "
                "pure white sky perfectly separated from a dark, starry night"
            ),
            "ch3_amaterasu_command_objects": (
                "Year/period: Japanese mythic creation era; Scene: Amaterasu handing a glowing "
                "golden scroll to a kneeling heavenly messenger"
            ),
            "ch3_messenger_descent_objects": (
                "Year/period: Japanese mythic creation era; Scene: A god rushing anxiously through "
                "a dark, foggy forest to find the fallen goddess"
            ),
            "ch3_uke_mochi_crime_evidence": (
                "Year/period: Japanese mythic creation era; Scene: Dark red blood pooling heavily "
                "on the bright green grass in a quiet, lonely clearing"
            ),
            "ch3_life_from_death_crops": (
                "Year/period: Japanese mythic creation era; Scene: A delicate, beautiful flower "
                "blooming instantly from a crack in a hard, dark stone"
            ),
            "ch3_uke_mochi_tragedy_evidence": (
                "Year/period: Japanese mythic creation era; Scene: A heavy, bloody iron blade "
                "cleanly slicing through an elegant, peaceful dinner setting"
            ),
            "ch3_closed_shroud_three_shoots": (
                "Year/period: Japanese mythic creation era; Scene: A dead body on the ground, "
                "violently glowing with bright, warm golden light from within"
            ),
            "ch3_three_seed_groups_bowl": (
                "Year/period: Japanese mythic creation era; Scene: Amaterasu holding a single, "
                "glowing grain of rice gently in the palm of her hand"
            ),
            "ch3_continuous_spring_autumn_field": (
                "Year/period: Japanese mythic creation era; Scene: A split image showing green "
                "spring planting on the left and golden autumn harvest on the right"
            ),
            "ch3_myth_to_niinamesai_offering": (
                "Year/period: Japanese mythic creation era; Scene: A beautiful ancient Japanese "
                "clock blending seamlessly into a modern digital calendar"
            ),
            "ch3_niinamesai_offering_platform": (
                "Year/period: Japanese mythic creation era; Scene: A dignified figure bowing "
                "deeply before a hidden, glowing altar in the dark"
            ),
            "ch3_amaterasu_rice_myth_source": (
                "Year/period: Japanese mythic creation era; Scene: An ancient scroll depicting "
                "a sun goddess handing a glowing rice plant to a human king"
            ),
            "ch3_rice_stalk_torn_cloth": (
                "Year/period: Japanese mythic creation era; Scene: A baby's hand reaching out "
                "from dark, rich soil to grab a golden stalk of rice"
            ),
            "ch3_hainuwele_type_comparison": (
                "Year/period: Japanese mythic creation era; Scene: An elegant, old leather-bound "
                "book titled an abstract emblem resting on a wooden desk"
            ),
            "ch3_seed_death_rebirth_cross_section": (
                "Year/period: Japanese mythic creation era; Scene: A rugged, ancient farmer staring "
                "in awe at a sprouting seed in his dirt-covered hands"
            ),
            "ch3_one_sacrifice_many_crops": (
                "Year/period: Japanese mythic creation era; Scene: A large, glowing red exclamation "
                "mark hovering mysteriously over a sharp iron blade"
            ),
            "ch3_life_taken_empty_bowl_dilemma": (
                "Year/period: Japanese mythic creation era; Scene: A completely blindfolded silver "
                "statue holding a sword, representing the dilemma of survival"
            ),
            "ch3_life_received_filled_bowl": (
                "Year/period: Japanese mythic creation era; Scene: A glowing golden thread connecting "
                "a fresh, vibrant green plant to a human heart"
            ),
            "ch3_three_silkworms_mulberry_tray": (
                "Year/period: Japanese mythic creation era; Scene: Divine hands gently offering fresh, "
                "green mulberry leaves to a cluster of white silkworms"
            ),
            "ch3_head_ox_horse_tokens": (
                "Year/period: Japanese mythic creation era; Scene: Powerful, majestic wild horses "
                "galloping proudly out of a glowing, magical mist"
            ),
            "ch3_forehead_millet_shroud": (
                "Year/period: Japanese mythic creation era; Scene: Bright, golden stalks of millet "
                "erupting rapidly from the forehead of the serene corpse"
            ),
            "ch3_brow_silkworm_shroud": (
                "Year/period: Japanese mythic creation era; Scene: Thick, perfectly healthy silkworms "
                "weaving pure white silk threads on green leaves"
            ),
            "ch3_eye_millet_belly_rice_shroud": (
                "Year/period: Japanese mythic creation era; Scene: Lush, vibrant green rice stalks "
                "rapidly sprouting and growing wildly out of a glowing belly"
            ),
            "ch3_lower_wheat_soy_adzuki_shroud": (
                "Year/period: Japanese mythic creation era; Scene: A beautiful, natural cascade of "
                "diverse beans and wheat pouring over the rich soil"
            ),
            "ch3_four_heavenly_weavers_hidden_limbs": (
                "Year/period: Japanese mythic creation era; Scene: Multiple ethereal, beautiful maidens "
                "working diligently at large wooden looms in a sunlit hall"
            ),
            "ch3_four_takamagahara_fear_faces": (
                "Year/period: Japanese mythic creation era; Scene: Multiple ethereal maidens dropping "
                "their weaving shuttles, covering their ears in sheer panic"
            ),
            "ch3_four_team_comment_readers_hidden_limbs": (
                "Year/period: Japanese mythic creation era; Scene: A group of diverse, happy creators "
                "reading off a glowing tablet together in a cozy studio"
            ),
        }
        for reference_id, prompt in cases.items():
            with self.subTest(reference_id=reference_id):
                spec = _exact_layout_reference_spec(prompt)
                self.assertIsNotNone(spec)
                self.assertEqual(spec[0], reference_id)
                self.assertEqual(spec[1], _EXACT_LAYOUT_REFERENCE_PATHS[reference_id])
                expected_model = (
                    _EXACT_LAYOUT_REFERENCE_COPY_MODEL
                    if reference_id in _EXACT_LAYOUT_REFERENCE_COPY_IDS
                    else "nano-banana-3"
                )
                self.assertEqual(
                    expected_effective_image_model_id("comfyui-flux2-klein-4b", prompt),
                    expected_model,
                )
                self.assertEqual(
                    _validate_exact_layout_reference_geometry(reference_id, spec[1]),
                    (1.0, 1.0, 1.0),
                )

        self.assertIsNone(
            _exact_layout_reference_spec(cases["baekje_ep02_row156"].replace("02-156", "02-155"))
        )
        self.assertIsNone(
            _exact_layout_reference_spec(
                cases["ch2_yamnaya_mobile_tools"].replace("3500 BCE to 2000 BCE", "1901 AD")
            )
        )
        with self.assertRaises(RuntimeError):
            _validate_exact_layout_reference_geometry(
                "baekje_ep02_row157",
                _EXACT_LAYOUT_REFERENCE_PATHS["baekje_ep02_row156"],
            )

    def test_ch2_ep2_early_steppe_routes_use_safe_exact_layouts(self):
        prompt = (
            "Year/period: 3500 BCE to 2000 BCE; Scene: High panoramic view of steppe routes "
            "between the Black Sea, Caspian Sea, Dnieper, Don, and Volga"
        )
        spec = _exact_layout_reference_spec(prompt)
        self.assertIsNotNone(spec)
        self.assertEqual(spec[0], "ch2_yamnaya_three_rivers_kurgans")
        self.assertEqual(
            expected_effective_image_model_id("comfyui-flux2-klein-4b", prompt),
            _EXACT_LAYOUT_REFERENCE_COPY_MODEL,
        )

    def test_ch2_ep2_early_steppe_scenes_remove_anatomy_and_modern_materials(self):
        cases = (
            (
                "Wide Pontic-Caspian grassland between distant rivers with cattle camps and wooden wagons",
                "landscape",
                "one winding river crosses an empty ochre plain",
            ),
            (
                "High panoramic view of steppe routes between the Black Sea, Caspian Sea, Dnieper, Don, and Volga",
                "landscape",
                "exactly three broad river bands",
            ),
            (
                "Cattle searching sparse winter grass beside a frozen river and a worried pastoral camp",
                "landscape",
                "one frozen blue-grey river",
            ),
            (
                "Young herder driving cattle while families repair an ox-drawn wagon during a cold migration",
                "object",
                "exactly four solid disk wheels",
            ),
        )
        for scene, expected_kind, expected_evidence in cases:
            with self.subTest(scene=scene):
                prompt = prepare_scene_contract_source(
                    (
                        "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene; "
                        "Exact place: Pontic-Caspian Steppe; Yamnaya cultural horizon; "
                        f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; "
                        f"Scene: {scene}, archaeologically grounded late Neolithic and early Bronze Age "
                        "reconstruction with tense human storytelling, 3500 BCE to 2000 BCE, "
                        "Pontic-Caspian Steppe, Yamnaya cultural horizon, period-accurate clothing, "
                        "architecture, tools, and material culture"
                    ),
                    narration_context="This spoken moment describes the Pontic-Caspian steppe and mobile pastoral life.",
                )
                compiled = compile_image_prompt(
                    prompt,
                    model_id="comfyui-flux2-klein-4b",
                )
                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, 0)
                self.assertIn(expected_evidence, compiled.positive)
                for forbidden in (
                    "hand",
                    "finger",
                    "leg",
                    "button-up shirt",
                    "modern collared shirt",
                    "modern trousers",
                    "modern coat",
                    "permanent house",
                    "chimney",
                ):
                    self.assertIn(forbidden, compiled.negative)
                self.assertNotIn(f"Visible action: {scene}", compiled.positive)
                self.assertNotIn(f"Primary subject: {scene}", compiled.positive)

    def test_ch3_ep7_safe_layout_rules_route_and_remove_anatomy(self):
        routed_reference_ids = set()
        for rule in CH3_EP7_SAFE_LAYOUT_SCENE_RULES:
            with self.subTest(
                reference_id=rule.reference_id,
                scene=rule.scene_prefix,
                narration=rule.narration_fragment,
            ):
                scene = rule.scene_prefix or (
                    "Landscape-only closing tableau of one golden sun disk, one silver "
                    "moon disk and one blue storm spiral above the calm primordial river"
                )
                narration = rule.narration_fragment or "神話 の 出来事 を 語ります。"
                prompt = prepare_scene_contract_source(
                    (
                        "Year/period: Japanese mythic creation era; "
                        "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
                        "Exact place: primordial natural landscape of mythic Japan; "
                        f"Scene: {scene}."
                    ),
                    narration_context=narration,
                )
                spec = _exact_layout_reference_spec(prompt)
                self.assertIsNotNone(spec)
                self.assertEqual(spec[0], rule.reference_id)
                self.assertEqual(
                    expected_effective_image_model_id(
                        "comfyui-flux2-klein-4b",
                        prompt,
                    ),
                    _EXACT_LAYOUT_REFERENCE_COPY_MODEL,
                )

                compiled = compile_image_prompt(
                    prompt,
                    model_id="comfyui-flux2-klein-4b",
                )
                expected_kind = (
                    "landscape"
                    if rule.reference_id in CH3_EP7_LANDSCAPE_REFERENCE_IDS
                    else "object"
                )
                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, None)
                expected_action = CH3_EP7_SAFE_LAYOUT_LOCKS[rule.reference_id][1]
                self.assertIn(expected_action[:60], compiled.positive)
                if rule.scene_prefix:
                    self.assertNotIn(rule.scene_prefix, compiled.positive)
                for anatomy_term in ("hand", "finger", "leg", "foot"):
                    self.assertIn(anatomy_term, compiled.negative)
                self.assertIn("readable writing", compiled.negative)
                routed_reference_ids.add(rule.reference_id)

        self.assertTrue(
            set(CH3_EP7_SAFE_LAYOUT_REFERENCE_FILENAMES).issubset(
                routed_reference_ids
            )
        )
        for reference_id in routed_reference_ids:
            with self.subTest(reference_geometry=reference_id):
                self.assertIn(reference_id, _EXACT_LAYOUT_REFERENCE_COPY_IDS)
                self.assertTrue(_EXACT_LAYOUT_REFERENCE_PATHS[reference_id].is_file())
                self.assertEqual(
                    _validate_exact_layout_reference_geometry(
                        reference_id,
                        _EXACT_LAYOUT_REFERENCE_PATHS[reference_id],
                    ),
                    (1.0, 1.0, 1.0),
                )

    def test_effective_model_change_marks_existing_sidecar_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "cut_1.png"
            image_path.write_bytes(b"placeholder-image-bytes" * 8)
            source_prompt = "Source workbook row 02-156"
            final_prompt = "compiled final prompt"
            write_prompt_sidecar(
                image_path,
                cut_number=1,
                image_model="comfyui-flux2-klein-4b",
                source_prompt=source_prompt,
                final_prompt=final_prompt,
            )
            matches, reason = image_matches_prompt(
                image_path,
                source_prompt=source_prompt,
                final_prompt=final_prompt,
                image_model="comfyui-flux2-klein-4b",
                effective_image_model="nano-banana-3",
            )
            self.assertFalse(matches)
            self.assertEqual(reason, "sidecar_effective_model_mismatch")

            write_prompt_sidecar(
                image_path,
                cut_number=1,
                image_model="comfyui-flux2-klein-4b",
                effective_image_model="nano-banana-3",
                source_prompt=source_prompt,
                final_prompt=final_prompt,
            )
            matches, reason = image_matches_prompt(
                image_path,
                source_prompt=source_prompt,
                final_prompt=final_prompt,
                image_model="comfyui-flux2-klein-4b",
                effective_image_model="nano-banana-3",
            )
            self.assertTrue(matches)
            self.assertEqual(reason, "sidecar_final_prompt_match")

    def test_plain_portrait_does_not_enable_inset_panel_detection(self):
        self.assertFalse(
            _should_check_split_panel_after_generation(
                "Heroic portrait photography, one continuous full-bleed frame"
            )
        )
        self.assertTrue(
            _should_check_split_panel_after_generation(
                "A framed portrait hangs above a split panel composition"
            )
        )

    def test_baekje_ep02_bamboo_slip_texture_ignores_false_text_detection(self):
        prompt = (
            "Scene evidence: Source workbook row 02-133 anchors this scene to Baekje history; "
            "Visible action: Bright overhead on pale clay: exactly three objects rest apart, "
            "one narrow leaf-shaped weathered iron spearhead, one short tied blank bamboo-slip bundle, "
            "and one coarse unglazed trade jar; no readable text"
        )

        self.assertTrue(_should_ignore_internal_text_detector(prompt))
        self.assertFalse(
            _should_ignore_internal_text_detector(prompt.replace("02-133", "02-134"))
        )
        self.assertFalse(
            _should_ignore_internal_text_detector(prompt.replace("trade jar", "storage jar"))
        )

    def test_baekje_ep02_harbor_material_texture_ignores_false_text_detection(self):
        prompt = (
            "Scene evidence: Source workbook row 02-124 anchors this scene to Baekje history; "
            "Scene: Small ancient boats moving between the Han River estuary and Yellow Sea islands, "
            "carrying grain, salt, metal, and travelers; no readable text"
        )

        self.assertTrue(_should_ignore_internal_text_detector(prompt))
        self.assertFalse(
            _should_ignore_internal_text_detector(prompt.replace("02-124", "02-125"))
        )

    def test_baekje_ep02_multiple_origin_objects_ignore_verified_texture_false_positive(self):
        prompt = (
            "Scene evidence: Source workbook row 02-145 anchors this scene to Baekje history; "
            "Scene: Multiple Baekje origin memories converging into one kingdom while King Goi "
            "prepares officials and soldiers for centralized rule; no readable text"
        )

        self.assertTrue(_should_ignore_internal_text_detector(prompt))
        self.assertFalse(
            _should_ignore_internal_text_detector(prompt.replace("02-145", "02-146"))
        )
        self.assertFalse(
            _should_ignore_internal_text_detector(prompt.replace("no readable text", "visible writing"))
        )

    def test_baekje_ep02_guthe_daifang_cut_uses_blank_object_evidence(self):
        image_prompt = (
            "Year/period: Baekje foundation traditions preserved in conflicting later records; "
            "Culture scope: Baekje, Goguryeo, and Daifang Commandery; "
            "Scene evidence: Source workbook row 02-011 anchors this scene to Baekje foundation traditions; "
            "Scene: Ancient Korean royal genealogies on silk beside two shadowed founders, coastal settlements and the Yellow Sea in the distance."
        )
        source = prepare_scene_contract_source(
            image_prompt,
            narration_context="그 기록은 동명의 후손 구태가 대방 땅에서 나라를 세웠다고 하죠.",
        )

        compiled = compile_image_prompt(
            source,
            model_id="comfyui-flux2-klein-4b",
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertIn("blank silk-wrapped sealed later-source bundle", compiled.positive)
        self.assertIn("flat frameless clay coastline tile", compiled.positive)
        self.assertIn("readable writing", compiled.negative)
        self.assertIn("roof tile", compiled.negative)
        self.assertIn("figurative carving", compiled.negative)
        self.assertIn("horse", compiled.negative)
        self.assertIn("person", compiled.negative)

    def test_baekje_ep02_chronology_cut_uses_object_only_stratigraphy(self):
        image_prompt = (
            "Year/period: Baekje foundation traditions preserved in conflicting later records; "
            "Culture scope: Baekje, Goguryeo, and Daifang Commandery; "
            "Scene evidence: Source workbook row 02-060 anchors this scene to Baekje foundation traditions; "
            "Scene: Ancient chronological markers separating the early Baekje founding era from late Han Liaodong and the later Daifang commandery."
        )
        source = prepare_scene_contract_source(
            image_prompt,
            narration_context="그렇다면 구태가 온조와 같은 시대의 경쟁 창업자였다는 해석은 흔들리고,",
        )

        compiled = compile_image_prompt(
            source,
            model_id="comfyui-flux2-klein-4b",
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertIn("exactly two separate flat rectangular clay chronology blocks", compiled.positive)
        self.assertIn("one broad empty bare-wood gap", compiled.positive)
        self.assertIn("person", compiled.negative)
        self.assertIn("uniform", compiled.negative)
        self.assertIn("badge", compiled.negative)

    def test_baekje_ep02_marriage_chronology_cut_uses_two_blank_horizons(self):
        image_prompt = (
            "Year/period: Baekje foundation traditions preserved in conflicting later records; "
            "Culture scope: Baekje, Goguryeo, and Daifang Commandery; "
            "Scene evidence: Source workbook row 02-012 anchors this scene to Baekje foundation traditions; "
            "Scene: Ancient Korean royal genealogies on silk beside two shadowed founders, coastal settlements and the Yellow Sea in the distance."
        )
        source = prepare_scene_contract_source(
            image_prompt,
            narration_context="그런데 구태의 혼인 상대를 따라가면 건국 연대가 수백 년 흔들립니다.",
        )

        compiled = compile_image_prompt(source, model_id="comfyui-flux2-klein-4b")

        self.assertEqual(compiled.scene_kind, "object")
        self.assertIn("one coarse reddish clay sample", compiled.positive)
        self.assertIn("one smooth grey clay sample", compiled.positive)
        self.assertIn("exactly two sealed blank", compiled.positive)
        self.assertIn("modern suit", compiled.negative)
        self.assertIn("Chinese character", compiled.negative)
        self.assertIn("tiled roof", compiled.negative)

    def test_baekje_ep02_opening_block_uses_narration_specific_object_scenes(self):
        expected_rows = {f"02-{row:03d}" for row in range(10, 25)} - {"02-011", "02-012"}
        self.assertEqual(
            {lock[0] for lock in _BAEKJE_EP02_OPENING_LOCKS.values()},
            expected_rows,
        )
        expected_positive_by_row = {
            "02-010": "outside one empty shallow circular seat",
            "02-013": "stays entirely inside the tray",
            "02-014": "exactly two separate rectangular clay horizon tiles",
            "02-015": "one shallow blue-grey river groove",
            "02-016": "exactly three tiny undecorated boat-shaped clay tokens",
            "02-017": "only inside the upper layer",
            "02-018": "one separate smooth reddish-brown circular clay token",
            "02-019": "exactly two flat rectangular markers appear",
            "02-020": "exactly one small low oval rammed-earth enclosure footprint",
            "02-021": "one single intermingled cluster",
            "02-022": "exactly two fully sealed blank silk-wrapped source bundles",
            "02-023": "one separate smooth angular grey clay token",
            "02-024": "exactly three objects total",
        }
        expected_extra_negative_by_row = {
            "02-015": "blank featureless tile",
            "02-019": "third object",
            "02-021": "tokens outside ring",
            "02-023": "codex",
            "02-024": "disk on disk",
        }

        for narration, (row, _subject, _action, _material) in _BAEKJE_EP02_OPENING_LOCKS.items():
            with self.subTest(row=row):
                image_prompt = (
                    "Year/period: Baekje foundation traditions preserved in conflicting later records; "
                    "Culture scope: Baekje, Goguryeo, and Daifang Commandery; "
                    f"Scene evidence: Source workbook row {row} anchors this scene to Baekje foundation traditions; "
                    "Scene: Ancient Korean royal genealogies on silk beside two shadowed founders, "
                    "coastal settlements and the Yellow Sea in the distance."
                )
                source = prepare_scene_contract_source(
                    image_prompt,
                    narration_context=narration,
                )

                compiled = compile_image_prompt(
                    source,
                    model_id="comfyui-flux2-klein-4b",
                )

                self.assertEqual(compiled.scene_kind, "object")
                self.assertEqual(compiled.person_count, None)
                self.assertIn(expected_positive_by_row[row], compiled.positive)
                self.assertNotIn("Ancient Korean royal genealogies", compiled.positive)
                self.assertIn("person", compiled.negative)
                self.assertIn("hand", compiled.negative)
                self.assertIn("readable writing", compiled.negative)
                self.assertIn("tiled roof", compiled.negative)
                self.assertIn("modern suit", compiled.negative)
                if row in expected_extra_negative_by_row:
                    self.assertIn(expected_extra_negative_by_row[row], compiled.negative)
                if row == "02-023":
                    self.assertNotIn(
                        "exactly two closed face-down blank thread-bound manuscripts",
                        compiled.positive,
                    )
                    self.assertIn("composition=object_close", compiled.diagnostics)

    def test_baekje_ep02_record_conflict_block_uses_narration_specific_objects(self):
        expected_rows = {f"02-{row:03d}" for row in range(25, 40)}
        self.assertEqual(
            {lock[0] for lock in _BAEKJE_EP02_RECORD_CONFLICT_LOCKS.values()},
            expected_rows,
        )
        expected_positive_by_row = {
            "02-025": "exactly three silk-wrapped bundles appear",
            "02-026": "one empty shallow grey clay seat remains centered",
            "02-027": "exactly two objects total appear",
            "02-028": "exactly two tokens total occupy opposite approach grooves",
            "02-029": "one continuous narrow land corridor",
            "02-030": "exactly two long flat tapered clay route bars",
            "02-031": "one single broad unknotted silk band",
            "02-032": "Exactly four objects total rest directly on uninterrupted natural bare wood",
            "02-033": "exactly three objects total appear",
            "02-034": "one long flat vertical earth-brown chronology strip lies centered",
            "02-035": "one large deeply weathered earth-brown kingdom disk",
            "02-036": "exactly three small flat grey rectangular repair patches",
            "02-037": "one physically separate empty square of undisturbed ancient earth",
            "02-038": "exactly two objects total appear",
            "02-039": "one empty reddish-brown archive pad lies far left",
        }

        for narration, (row, _subject, _action, _material) in _BAEKJE_EP02_RECORD_CONFLICT_LOCKS.items():
            with self.subTest(row=row):
                image_prompt = (
                    "Year/period: Baekje foundation traditions preserved in conflicting later records; "
                    "Culture scope: Baekje, Goguryeo, and Daifang Commandery; "
                    f"Scene evidence: Source workbook row {row} anchors this scene to Baekje foundation traditions; "
                    "Scene: Two contrasting ancient origin journeys, princes moving south through mountains "
                    "and envoys approaching a fortified Daifang settlement."
                )
                compiled = compile_image_prompt(
                    prepare_scene_contract_source(
                        image_prompt,
                        narration_context=narration,
                    ),
                    model_id="comfyui-flux2-klein-4b",
                )

                self.assertEqual(compiled.scene_kind, "object")
                self.assertEqual(compiled.person_count, None)
                self.assertIn(expected_positive_by_row[row], compiled.positive)
                self.assertNotIn("princes moving south", compiled.positive)
                self.assertNotIn("fortified Daifang settlement", compiled.positive)
                self.assertIn("person", compiled.negative)
                self.assertIn("hand", compiled.negative)
                self.assertIn("readable writing", compiled.negative)
                self.assertIn("tiled roof", compiled.negative)
                if row == "02-032":
                    self.assertIn("hollow ring", compiled.negative)
                if row == "02-034":
                    self.assertIn("glyph", compiled.negative)
                    self.assertIn("sky", compiled.negative)
                if row == "02-036":
                    self.assertIn("crack", compiled.negative)

    def test_baekje_ep02_guthe_politics_block_uses_narration_specific_objects(self):
        expected_rows = {f"02-{row:03d}" for row in range(40, 55)}
        self.assertEqual(
            {lock[0] for lock in _BAEKJE_EP02_GUTHE_POLITICS_LOCKS.values()},
            expected_rows,
        )
        expected_positive_by_row = {
            "02-040": "exactly two objects total appear",
            "02-041": "one single flat trident-shaped clay lineage piece",
            "02-042": "one blank reddish descendant disk inside one low state ring",
            "02-043": "one small solid reddish Gutae disk at lower left",
            "02-044": "exactly one large raised solid grey power disk",
            "02-045": "one single broad flat grey expansion band",
            "02-046": "exactly three objects total appear",
            "02-047": "one reddish Gutae disk rests fully inside",
            "02-048": "one large raised earth-brown kingdom disk",
            "02-049": "exactly one long horizontal rectangular clay sequence bar",
            "02-050": "one solid grey disk and one solid reddish disk touch",
            "02-051": "one continuous narrow earth-brown corridor",
            "02-052": "one reddish Baekje disk stays centered",
            "02-053": "one flawless smooth reddish claim tile",
            "02-054": "one long blank earth-brown clay chronology strip",
        }

        for narration, (row, _subject, _action, _material) in _BAEKJE_EP02_GUTHE_POLITICS_LOCKS.items():
            with self.subTest(row=row):
                image_prompt = (
                    "Year/period: Baekje foundation traditions preserved in conflicting later records; "
                    "Culture scope: Baekje, Goguryeo, and Daifang Commandery; "
                    f"Scene evidence: Source workbook row {row} anchors this scene to Baekje foundation traditions; "
                    "Scene: Gutae meeting Gongsun Du during a formal political marriage alliance "
                    "inside a fortified hall."
                )
                compiled = compile_image_prompt(
                    prepare_scene_contract_source(image_prompt, narration_context=narration),
                    model_id="comfyui-flux2-klein-4b",
                )

                self.assertEqual(compiled.scene_kind, "object")
                self.assertEqual(compiled.person_count, None)
                self.assertIn(expected_positive_by_row[row], compiled.positive)
                self.assertNotIn("Gutae meeting Gongsun Du", compiled.positive)
                self.assertNotIn("fortified hall", compiled.positive)
                self.assertIn("person", compiled.negative)
                self.assertIn("hand", compiled.negative)
                self.assertIn("readable writing", compiled.negative)

    def test_baekje_ep02_chronology_block_uses_narration_specific_objects(self):
        expected_rows = {f"02-{row:03d}" for row in (*range(55, 60), *range(61, 70))}
        self.assertEqual(
            {lock[0] for lock in _BAEKJE_EP02_CHRONOLOGY_BLOCK_LOCKS.values()},
            expected_rows,
        )
        expected_positive_by_row = {
            "02-055": "one long blank earth-brown clay chronology strip spans bare wood",
            "02-056": "one long blank earth-brown clay chronology strip spans bare wood",
            "02-057": "one reddish disk stays at the far-left end",
            "02-058": "the lower early earth-brown layer remains completely empty",
            "02-059": "one broad grey northern clay tile is divided",
            "02-061": "one empty shallow round founder seat remains centered",
            "02-062": "exactly two solid featureless markers only at its far-right later end",
            "02-063": "exactly three small reddish, brown, and grey lineage disks",
            "02-064": "exactly two nearly identical flat grey oval clay tokens lie directly on wood",
            "02-065": "one flat grey oval token rests on one pale clay pad",
            "02-066": "exactly three solid blank disks total",
            "02-067": "exactly three small grey square markers sit",
            "02-068": "one long blank earth-brown chronology strip has one broad central fracture",
            "02-069": "exactly two long earth-brown clay chronology fragments",
        }

        for narration, (row, _subject, _action, _material) in _BAEKJE_EP02_CHRONOLOGY_BLOCK_LOCKS.items():
            with self.subTest(row=row):
                image_prompt = (
                    "Year/period: Baekje foundation traditions preserved in conflicting later records; "
                    "Culture scope: Baekje, Goguryeo, and Daifang Commandery; "
                    f"Scene evidence: Source workbook row {row} anchors this scene to Baekje foundation traditions; "
                    "Scene: Ancient chronological markers separating early Baekje from late Han Liaodong."
                )
                compiled = compile_image_prompt(
                    prepare_scene_contract_source(image_prompt, narration_context=narration),
                    model_id="comfyui-flux2-klein-4b",
                )

                self.assertEqual(compiled.scene_kind, "object")
                self.assertEqual(compiled.person_count, None)
                self.assertIn(expected_positive_by_row[row], compiled.positive)
                self.assertNotIn("Ancient chronological markers", compiled.positive)
                self.assertIn("person", compiled.negative)
                self.assertIn("hand", compiled.negative)
                self.assertIn("readable writing", compiled.negative)

    def test_baekje_ep02_remaining_blocks_cover_rows_070_through_159(self):
        expected_rows = {f"02-{row:03d}" for row in range(70, 160)}
        actual_rows = {entry[0] for entry in _BAEKJE_EP02_REMAINING_LOCKS.values()}

        self.assertEqual(len(_BAEKJE_EP02_REMAINING_LOCKS), 90)
        self.assertEqual(actual_rows, expected_rows)

        repeated_source_scene = (
            "Baekje royal priests conducting a solemn ancestral rite at a shrine dedicated "
            "to Gutae inside an ancient walled capital."
        )
        for narration, (row, _subject, action, _material) in _BAEKJE_EP02_REMAINING_LOCKS.items():
            with self.subTest(row=row):
                image_prompt = (
                    "Year/period: Baekje foundation traditions preserved in conflicting later records; "
                    "Culture scope: Baekje, Goguryeo, and Daifang Commandery; "
                    f"Scene evidence: Source workbook row {row} anchors this scene to Baekje history; "
                    f"Scene: {repeated_source_scene}"
                )
                compiled = compile_image_prompt(
                    prepare_scene_contract_source(image_prompt, narration_context=narration),
                    model_id="comfyui-flux2-klein-4b",
                )

                action_prefix = action[:80].rsplit(" ", 1)[0]
                self.assertIn(compiled.scene_kind, {"object", "landscape"})
                self.assertEqual(compiled.person_count, None)
                self.assertIn(action_prefix, compiled.positive)
                self.assertNotIn("royal priests conducting", compiled.positive)
                self.assertIn("hand", compiled.negative)
                self.assertIn("leg", compiled.negative)
                self.assertIn("Latin letter", compiled.negative)
                self.assertIn("modern vehicle", compiled.negative)

    def test_baekje_ep02_seven_branched_sword_has_exact_historical_silhouette(self):
        narration = "칠지도 같은 유물은 그 복잡한 관계가 물질로 남은 사례죠"
        row, _subject, _action, _material = _BAEKJE_EP02_REMAINING_LOCKS[narration]
        image_prompt = (
            "Year/period: fourth-century Baekje; "
            "Culture scope: Baekje, Goguryeo, and Daifang Commandery; "
            f"Scene evidence: Source workbook row {row} anchors this scene to Baekje history; "
            "Scene: Mature Baekje envoys and merchants crossing ancient sea routes."
        )
        compiled = compile_image_prompt(
            prepare_scene_contract_source(image_prompt, narration_context=narration),
            model_id="comfyui-flux2-klein-4b",
        )

        self.assertIn(
            "actual Seven-Branched Sword, Shichishito, from Isonokami Shrine",
            compiled.positive,
        )
        self.assertIn("three branch blades sprouting from each side", compiled.positive)
        self.assertIn("Exactly seven blade tips total", compiled.positive)
        self.assertIn("one central tip plus six side tips", compiled.positive)
        self.assertIn("four branches total", compiled.negative)
        self.assertIn("four lateral branches", compiled.negative)
        self.assertIn("two branches on left", compiled.negative)
        self.assertIn("two branches on right", compiled.negative)
        self.assertIn("eight branches total", compiled.negative)
        self.assertIn("four branches on left", compiled.negative)
        self.assertIn("four branches on right", compiled.negative)
        self.assertIn("ten branches total", compiled.negative)
        self.assertIn("five branches on left", compiled.negative)
        self.assertIn("five branches on right", compiled.negative)
        self.assertIn("ladder-shaped sword", compiled.negative)
        self.assertIn("detached hooks", compiled.negative)
        self.assertIn("branches clustered at top", compiled.negative)
        self.assertIn("top crossguard cluster", compiled.negative)
        self.assertIn("six hooks at one height", compiled.negative)
        self.assertIn("five lateral branches", compiled.negative)
        self.assertIn("seven lateral branches", compiled.negative)
        self.assertIn("symmetric star", compiled.negative)
        self.assertIn("bottom blade point", compiled.negative)
        self.assertIn("horizontal crossbar", compiled.negative)

    def test_baekje_ep02_cultural_transfer_cargo_has_three_period_objects(self):
        narration = "학자와 기술, 불교와 문자 문화도 배를 타고 오가게 됩니다"
        row, _subject, _action, _material = _BAEKJE_EP02_REMAINING_LOCKS[narration]
        source = prepare_scene_contract_source(
            (
                "Year/period: Baekje foundation traditions preserved in conflicting later records; "
                "Culture scope: Baekje, Goguryeo, and Daifang Commandery; "
                f"Scene evidence: Source workbook row {row} anchors this scene to Baekje history; "
                "Scene: Mature Baekje envoys and merchants crossing ancient sea routes."
            ),
            narration_context=narration,
        )
        compiled = compile_image_prompt(source, model_id="comfyui-flux2-klein-4b")

        self.assertIn("exactly three separate objects", compiled.positive)
        self.assertIn("one tied closed tan bamboo-slip bundle", compiled.positive)
        self.assertIn("one short uniform-width rectangular bronze craft strip", compiled.positive)
        self.assertIn("one shallow round bronze lotus dish", compiled.positive)
        self.assertIn("steel tool", compiled.negative)
        self.assertIn("tool grip", compiled.negative)

    def test_baekje_ep02_multiple_origin_sources_keep_one_hemp_packet(self):
        narration = "결국 백제의 출생증명서는 한 장이 아니라 여러 장이었습니다"
        row, _subject, _action, _material = _BAEKJE_EP02_REMAINING_LOCKS[narration]
        source = prepare_scene_contract_source(
            (
                "Year/period: Baekje foundation traditions preserved in conflicting later records; "
                "Culture scope: Baekje, Goguryeo, and Daifang Commandery; "
                f"Scene evidence: Source workbook row {row} anchors this scene to Baekje history; "
                "Scene: Multiple Baekje origin memories converge into one kingdom."
            ),
            narration_context=narration,
        )
        compiled = compile_image_prompt(source, model_id="comfyui-flux2-klein-4b")

        self.assertIn("exactly four objects", compiled.positive)
        self.assertIn("one undivided brown hemp packet", compiled.positive)
        self.assertIn("exactly one dark-red clay disk", compiled.positive)
        self.assertIn("One disk total in frame", compiled.positive)
        self.assertIn("second red disk", compiled.negative)
        self.assertIn("two red disks", compiled.negative)
        self.assertIn("paired red disks", compiled.negative)
        self.assertIn("second hemp packet", compiled.negative)
        self.assertIn("split hemp packet", compiled.negative)

    def test_baekje_ep02_final_teaser_object_counts_use_simple_layouts(self):
        cases = {
            "국호도 백성이 즐겨 따랐다는 설명과 백가가 바다를 건넜다는 설명으로 갈렸죠": (
                "many fused round lobes",
                "exactly three separate tan packets",
                "smooth circular community disk",
            ),
            "다음 편은 백제를 연맹의 한 나라에서 중앙집권 국가로 끌어올린 고이왕입니다": (
                "exactly four equal grey square blocks form a clean two-by-two grid",
                "Exactly five objects total",
                "missing fourth rank block",
            ),
            "낙랑과 대방의 전쟁으로 마한의 질서가 흔들리는 바로 그 틈에서": (
                "exactly six objects total",
                "exactly four smaller brown blocks form a two-by-two grid",
                "only two brown blocks",
            ),
            "고이왕은 주변 세력을 누르고 관등과 법, 군사 지휘권을 손에 쥡니다": (
                "one flat matte dark-red unglazed clay disk with a smooth blank face",
                "one narrow iron spearhead at right",
                "decorated royal disk",
            ),
        }

        for narration, (first_positive, second_positive, negative) in cases.items():
            with self.subTest(narration=narration):
                row, _subject, _action, _material = _BAEKJE_EP02_REMAINING_LOCKS[narration]
                source = prepare_scene_contract_source(
                    (
                        "Year/period: Baekje foundation traditions preserved in conflicting later records; "
                        "Culture scope: Baekje, Goguryeo, and Daifang Commandery; "
                        f"Scene evidence: Source workbook row {row} anchors this scene to Baekje history; "
                        "Scene: Multiple Baekje origin memories converge into centralized rule."
                    ),
                    narration_context=narration,
                )
                compiled = compile_image_prompt(source, model_id="comfyui-flux2-klein-4b")

                self.assertIn(first_positive, compiled.positive)
                self.assertIn(second_positive, compiled.positive)
                self.assertIn(negative, compiled.negative)

    def test_baekje_ep02_goi_rank_colors_are_purple_red_and_blue(self):
        narration = "왕의 옷 색깔까지 권력의 서열이 되는 순간을 다음 편에서 이어가겠습니다"
        row, _subject, _action, _material = _BAEKJE_EP02_REMAINING_LOCKS[narration]
        image_prompt = (
            "Year/period: King Goi reign in third-century Baekje; "
            "Culture scope: Baekje, Goguryeo, and Daifang Commandery; "
            f"Scene evidence: Source workbook row {row} anchors this scene to Baekje history; "
            "Scene: King Goi prepares officials and soldiers for centralized rule."
        )
        compiled = compile_image_prompt(
            prepare_scene_contract_source(image_prompt, narration_context=narration),
            model_id="comfyui-flux2-klein-4b",
        )

        self.assertIn("one deep purple, one red, and one blue", compiled.positive)
        self.assertIn("green cloth", compiled.negative)
        self.assertIn("yellow cloth", compiled.negative)

    def test_ch2_yamnaya_dispute_now_uses_hand_free_object_coordination_evidence(self):
        image_prompt = (
            "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene, 3500 BCE to 2000 BCE; "
            "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; Yamnaya cultural horizon, Neolithic European communities; "
            "Scene evidence: Source workbook scene: Yamnaya chief judging a dispute before several clan representatives and tethered herds; "
            "Main subject: Yamnaya chief judging a dispute before several clan representatives and tethered herds; "
            "Scene: Yamnaya chief judging a dispute before several clan representatives and tethered herds, archaeologically grounded late Neolithic and early Bronze Age reconstruction with tense human storytelling, 3500 BCE to 2000 BCE, Pontic-Caspian Steppe, Balkans, Central Europe, Yamnaya cultural horizon, Neolithic European communities, character continuity: Yamnaya chief: powerful middle-aged steppe pastoralist, dark hair and beard, ochre-stained wool cloak, copper dagger, carved wooden staff, period-accurate clothing, architecture, tools, and material culture, overhead environmental shot, 28mm lens, dusty interior window light, cinematic documentary realism, natural skin and fabric texture, 16:9, image only, no text, no watermark"
        )
        source = prepare_scene_contract_source(
            image_prompt,
            narration_context=(
                "Chiefdoms coordinated movement, settled disputes, and controlled relationships extending far beyond one camp."
            ),
        )

        compiled = compile_image_prompt(
            source,
            model_id="comfyui-flux2-klein-4b",
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("exactly two equal balance stones", compiled.positive)
        self.assertIn("exactly three smaller blank camp disks", compiled.positive)
        self.assertNotIn("several adult clan representatives", compiled.positive)
        self.assertIn("person", compiled.negative)
        self.assertIn("hand", compiled.negative)
        self.assertIn("leg", compiled.negative)

    def test_ch2_seventy_five_percent_ancestry_uses_object_only_ratio(self):
        image_prompt = (
            "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene, 3500 BCE to 2000 BCE; "
            "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; Yamnaya cultural horizon, Neolithic European communities; "
            "Scene evidence: Source workbook scene: Ancient skeleton overlaid with a bold seventy-five percent ancestry connection to the Pontic-Caspian grasslands; "
            "Main subject: Ancient skeleton overlaid with a bold seventy-five percent ancestry connection to the Pontic-Caspian grasslands; "
            "Scene: Ancient skeleton overlaid with a bold seventy-five percent ancestry connection to the Pontic-Caspian grasslands, archaeologically grounded late Neolithic and early Bronze Age reconstruction with tense human storytelling, 3500 BCE to 2000 BCE, Pontic-Caspian Steppe, Balkans, Central Europe, Yamnaya cultural horizon, Neolithic European communities, period-accurate clothing, architecture, tools, and material culture, eye-level medium shot, 50mm documentary lens, soft overcast daylight, cinematic documentary realism, natural skin and fabric texture, 16:9, image only, no text, no watermark"
        )
        source = prepare_scene_contract_source(
            image_prompt,
            narration_context=(
                "Three quarters of that dead person's ancestry traced back toward herders from the eastern steppe."
            ),
        )

        compiled = compile_image_prompt(
            source,
            model_id="comfyui-flux2-klein-4b",
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("one small isolated weathered molar", compiled.positive)
        self.assertIn("four equal separated square tiles", compiled.positive)
        self.assertIn("ochre-brown, ochre-brown, ochre-brown, pale-grey", compiled.positive)
        self.assertNotIn("Ancient skeleton overlaid", compiled.positive)
        self.assertIn("standing skeleton", compiled.negative)
        self.assertIn("two grey tiles", compiled.negative)

    def test_ch2_wagon_language_cut_uses_four_object_migration_assemblage(self):
        image_prompt = (
            "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene, 3500 BCE to 2000 BCE; "
            "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; Yamnaya cultural horizon, Neolithic European communities; "
            "Scene evidence: Source workbook scene: Yamnaya wagon column with copper weapons and families moving beneath branching Indo-European language symbols; "
            "Main subject: Yamnaya wagon column with copper weapons and families moving beneath branching Indo-European language symbols; "
            "Scene: Yamnaya wagon column with copper weapons and families moving beneath branching Indo-European language symbols, archaeologically grounded late Neolithic and early Bronze Age reconstruction with tense human storytelling, 3500 BCE to 2000 BCE, Pontic-Caspian Steppe, Balkans, Central Europe, Yamnaya cultural horizon, Neolithic European communities, period-accurate clothing, architecture, tools, and material culture, tight character close-up, 85mm portrait lens, warm firelight with natural shadows, cinematic documentary realism, natural skin and fabric texture, 16:9, image only, no text, no watermark"
        )
        source = prepare_scene_contract_source(
            image_prompt,
            narration_context=(
                "Those migrants carried wagons, weapons, powerful bloodlines, and languages that would outlive their names."
            ),
        )

        compiled = compile_image_prompt(source, model_id="comfyui-flux2-klein-4b")

        self.assertEqual(compiled.scene_kind, "object")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("exactly four objects", compiled.positive)
        self.assertIn("one solid three-plank wooden transport disk with one axle hole", compiled.positive)
        self.assertIn("one flat leaf-shaped copper blade blank", compiled.positive)
        self.assertIn("one compact closed rectangular woven-fibre packet", compiled.positive)
        self.assertIn("one small clay tile with one shallow Y-groove", compiled.positive)
        self.assertNotIn("branching Indo-European language symbols", compiled.positive)
        self.assertIn("spoked wheel", compiled.negative)
        self.assertIn("wagon body", compiled.negative)
        self.assertIn("map", compiled.negative)
        self.assertIn("readable writing", compiled.negative)
        self.assertIn("stone axe", compiled.negative)
        self.assertIn("rope coil", compiled.negative)
        self.assertIn("knife handle", compiled.negative)
        self.assertIn("sword", compiled.negative)
        self.assertIn("white background", compiled.negative)

    def test_ch2_kurgan_burial_cut_removes_mourners_and_spoked_wheels(self):
        image_prompt = (
            "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene, 3500 BCE to 2000 BCE; "
            "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; Yamnaya cultural horizon, Neolithic European communities; "
            "Scene evidence: Source workbook scene: Ochre-covered male burial beneath a kurgan with wagon wheels; "
            "Main subject: Ochre-covered male burial beneath a kurgan with wagon wheels; "
            "Scene: Ochre-covered male burial beneath a kurgan with wagon wheels, dagger, animal offerings, and silent mourners, archaeologically grounded late Neolithic and early Bronze Age reconstruction with tense human storytelling, 3500 BCE to 2000 BCE, Pontic-Caspian Steppe, Balkans, Central Europe, Yamnaya cultural horizon, Neolithic European communities, period-accurate clothing, architecture, tools, and material culture, overhead environmental shot, 28mm lens, late-afternoon side light, cinematic documentary realism, natural skin and fabric texture, 16:9, image only, no text, no watermark"
        )
        source = prepare_scene_contract_source(
            image_prompt,
            narration_context=(
                "No king recorded the campaign, yet graves reveal an elite world dominated by selected men."
            ),
        )

        compiled = compile_image_prompt(source, model_id="comfyui-flux2-klein-4b")

        self.assertEqual(compiled.scene_kind, "object")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("exactly five separated groups on ochre earth", compiled.positive)
        self.assertIn("upper-left one leaf-shaped copper blade blank", compiled.positive)
        self.assertIn("center-left one flat hide grave cover", compiled.positive)
        self.assertIn("upper-right one solid wooden disk", compiled.positive)
        self.assertIn("lower-right a second equal disk", compiled.positive)
        self.assertIn("lower-center one pale ivory knobby-ended animal-bone cluster", compiled.positive)
        self.assertIn("Bare gaps; nothing overlaps", compiled.positive)
        self.assertNotIn("head and face", compiled.positive)
        self.assertNotIn("body-length hide shroud", compiled.positive)
        self.assertNotIn("silent mourners", compiled.positive)
        self.assertIn("human body", compiled.negative)
        self.assertIn("third wooden disk", compiled.negative)
        self.assertIn("missing second wooden disk", compiled.negative)
        self.assertIn("missing copper blade", compiled.negative)
        self.assertIn("bone cluster on wooden disk", compiled.negative)
        self.assertIn("wooden sticks replacing bones", compiled.negative)
        self.assertIn("twigs replacing bones", compiled.negative)
        self.assertIn("white background", compiled.negative)
        self.assertIn("mourner", compiled.negative)
        self.assertIn("spoked wheel", compiled.negative)
        self.assertIn("crossguard", compiled.negative)

    def test_ch2_yamnaya_violence_or_alliance_cut_is_object_only(self):
        image_prompt = (
            "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene, 3500 BCE to 2000 BCE; "
            "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; Yamnaya cultural horizon, Neolithic European communities; "
            "Scene evidence: Source workbook scene: Yamnaya chief and farmer elder facing each other between armed followers and exchanged prestige gifts; "
            "Main subject: Yamnaya chief and farmer elder facing each other between armed followers and exchanged prestige gifts; "
            "Scene: Yamnaya chief and farmer elder facing each other between armed followers and exchanged prestige gifts, archaeologically grounded late Neolithic and early Bronze Age reconstruction with tense human storytelling, 3500 BCE to 2000 BCE, Pontic-Caspian Steppe, Balkans, Central Europe, Yamnaya cultural horizon, Neolithic European communities, period-accurate clothing, architecture, tools, and material culture, 16:9, image only, no text, no watermark"
        )
        source = prepare_scene_contract_source(
            image_prompt,
            narration_context=(
                "Did they conquer Europe by violence, or make local rulers desperate to join them?"
            ),
        )

        compiled = compile_image_prompt(source, model_id="comfyui-flux2-klein-4b")

        self.assertEqual(compiled.scene_kind, "object")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("exactly five separated objects", compiled.positive)
        self.assertIn("one smooth blank ochre clan disk", compiled.positive)
        self.assertIn("upper-right one grey alliance disk", compiled.positive)
        self.assertIn("lower-right a second equal grey disk", compiled.positive)
        self.assertIn("lower-center one closed woven packet", compiled.positive)
        self.assertIn("Bare earth gaps; nothing overlaps", compiled.positive)
        self.assertNotIn("Yamnaya chief and farmer elder", compiled.positive)
        self.assertIn("person", compiled.negative)
        self.assertIn("gold vessel", compiled.negative)
        self.assertIn("sword", compiled.negative)
        self.assertIn("pseudo-writing", compiled.negative)
        self.assertIn("decorative border", compiled.negative)
        self.assertIn("only one alliance disk", compiled.negative)
        self.assertIn("packet on alliance disk", compiled.negative)

    def test_ch2_mobile_pastoralism_cut_uses_object_only_transport_evidence(self):
        image_prompt = (
            "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene, 3500 BCE to 2000 BCE; "
            "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; Yamnaya cultural horizon, Neolithic European communities; "
            "Scene evidence: Source workbook scene: Seasonal Yamnaya camp being dismantled as wagons form a departing column; "
            "Main subject: Seasonal Yamnaya camp being dismantled as wagons form a departing column; "
            "Scene: Seasonal Yamnaya camp being dismantled as wagons form a departing column, archaeologically grounded late Neolithic and early Bronze Age reconstruction with tense human storytelling, 3500 BCE to 2000 BCE, Pontic-Caspian Steppe, Balkans, Central Europe, Yamnaya cultural horizon, Neolithic European communities, period-accurate clothing, architecture, tools, and material culture, tight character close-up, 85mm portrait lens, late-afternoon side light, cinematic documentary realism, natural skin and fabric texture, 16:9, image only, no text, no watermark"
        )
        source = prepare_scene_contract_source(
            image_prompt,
            narration_context=(
                "That pressure helped create a more mobile form of pastoral life across the open country."
            ),
        )

        compiled = compile_image_prompt(source, model_id="comfyui-flux2-klein-4b")

        self.assertEqual(compiled.scene_kind, "object")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("exactly four separated mobility tools", compiled.positive)
        self.assertIn("one solid three-plank wooden wheel disk", compiled.positive)
        self.assertIn("upper-right one plain cattle yoke", compiled.positive)
        self.assertIn("lower-left one pale flexible rolled hide shelter with two fibre ties", compiled.positive)
        self.assertIn("lower-right one closed woven packet", compiled.positive)
        self.assertNotIn("wagons form a departing column", compiled.positive)
        self.assertIn("wagon column", compiled.negative)
        self.assertIn("star badge", compiled.negative)
        self.assertIn("spoked wheel", compiled.negative)
        self.assertIn("hand", compiled.negative)
        self.assertIn("finger", compiled.negative)
        self.assertIn("leg", compiled.negative)
        self.assertIn("wooden barrel", compiled.negative)
        self.assertIn("cask", compiled.negative)
        self.assertIn("wood grain on hide roll", compiled.negative)

    def test_ch2_pit_grave_definition_cut_is_object_only_archaeological_cutaway(self):
        scene = "Cross-section of a simple pit grave beneath an earthen kurgan beside a living steppe camp"
        image_prompt = (
            "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene, 3500 BCE to 2000 BCE; "
            "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; Yamnaya cultural horizon, Neolithic European communities; "
            f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; "
            f"Scene: {scene}, archaeologically grounded late Neolithic and early Bronze Age reconstruction "
            "with tense human storytelling, 3500 BCE to 2000 BCE, Pontic-Caspian Steppe, Balkans, Central "
            "Europe, Yamnaya cultural horizon, Neolithic European communities, period-accurate clothing, "
            "architecture, tools, and material culture, 16:9, image only, no text"
        )
        compiled = compile_image_prompt(
            prepare_scene_contract_source(
                image_prompt,
                narration_context=(
                    "Archaeologists call these communities Yamnaya, meaning people associated with simple pit graves."
                ),
            ),
            model_id="comfyui-flux2-klein-4b",
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("one low rounded earthen kurgan", compiled.positive)
        self.assertIn("one simple straight-sided rectangular pit", compiled.positive)
        self.assertIn("One flat ochre hide cover seals the pit floor", compiled.positive)
        self.assertNotIn("living steppe camp", compiled.positive)
        self.assertIn("human remains", compiled.negative)
        self.assertIn("catacomb", compiled.negative)
        self.assertIn("standing hut", compiled.negative)

    def test_ch2_gorodtsov_cut_uses_1901_fieldwork_not_bronze_age_workers(self):
        scene = "Gorodtsov recording an exposed pit grave near the Donets River with early excavation workers"
        image_prompt = (
            "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene, 3500 BCE to 2000 BCE; "
            "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; Yamnaya cultural horizon; "
            f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; Scene: {scene}, "
            "character continuity: Gorodtsov: Russian archaeologist Vasily Gorodtsov in early twentieth-century "
            "field clothes, trimmed moustache, notebook and measuring rod, 16:9, image only, no text"
        )
        compiled = compile_image_prompt(
            prepare_scene_contract_source(
                image_prompt,
                narration_context=(
                    "Russian archaeologist Vasily Gorodtsov identified their pattern after Donets excavations beginning in 1901."
                ),
            ),
            model_id="comfyui-flux2-klein-4b",
        )

        self.assertEqual(compiled.scene_kind, "face")
        self.assertEqual(compiled.person_count, 1)
        self.assertIn("1901-1903 AD", compiled.positive)
        self.assertIn("Russian Empire", compiled.positive)
        self.assertIn("Seversky Donets River", compiled.positive)
        self.assertIn("exactly one clean-shaven Vasily Gorodtsov", compiled.positive)
        self.assertIn("Extreme face-only crop", compiled.positive)
        self.assertIn("zero visible shoulders, arms, hands, fingers, torsos, or legs", compiled.positive)
        self.assertIn("clean-shaven cheeks and chin", compiled.positive)
        self.assertIn("short side-parted", compiled.positive)
        self.assertIn("pencil-thin narrow light moustache", compiled.positive)
        self.assertNotIn("3500 BCE to 2000 BCE", compiled.positive)
        self.assertNotIn("Yamnaya cultural horizon", compiled.positive)
        self.assertIn("excavation worker", compiled.negative)
        self.assertIn("worker crowd", compiled.negative)
        self.assertIn("notebook", compiled.negative)
        self.assertIn("modern hard hat", compiled.negative)
        self.assertIn("full beard", compiled.negative)
        self.assertIn("handlebar moustache", compiled.negative)
        self.assertIn("thick moustache", compiled.negative)
        self.assertIn("bushy moustache", compiled.negative)
        self.assertIn("visible shoulder", compiled.negative)

    def test_ch2_gorodtsov_classification_cut_is_three_textless_grave_types(self):
        scene = "Gorodtsov comparing three distinct grave plans on a field table beside excavated mounds"
        image_prompt = (
            "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene, 3500 BCE to 2000 BCE; "
            "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; Yamnaya cultural horizon; "
            f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; Scene: {scene}, "
            "archaeologically grounded late Neolithic and early Bronze Age reconstruction with tense human "
            "storytelling, 3500 BCE to 2000 BCE, Pontic-Caspian Steppe, Balkans, Central Europe, Yamnaya "
            "cultural horizon, period-accurate clothing, architecture, tools, and material culture, 16:9, "
            "image only, no text"
        )
        compiled = compile_image_prompt(
            prepare_scene_contract_source(
                image_prompt,
                narration_context=(
                    "He separated those graves from later Catacomb and Srubnaya burials occupying the same region."
                ),
            ),
            model_id="comfyui-flux2-klein-4b",
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("1901-1903 AD", compiled.positive)
        self.assertIn("exactly three separated low mounds", compiled.positive)
        self.assertIn("left one straight vertical pit", compiled.positive)
        self.assertIn("center one entrance shaft, short passage, and side chamber", compiled.positive)
        self.assertIn("right one rectangular pit lined with exactly five horizontal timber courses", compiled.positive)
        self.assertNotIn("3500 BCE to 2000 BCE", compiled.positive)
        self.assertIn("field table", compiled.negative)
        self.assertIn("paper plan", compiled.negative)
        self.assertIn("hand", compiled.negative)
        self.assertIn("panel frame", compiled.negative)

    def test_ch2_unnamed_chief_cut_is_one_hand_free_person(self):
        scene = "Anonymous Yamnaya chief silhouetted before assembled clans with no inscription or written record"
        image_prompt = (
            "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene, 3500 BCE to 2000 BCE; "
            "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; Yamnaya cultural horizon; "
            f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; Scene: {scene}, "
            "archaeologically grounded late Neolithic and early Bronze Age reconstruction with tense human "
            "storytelling, 3500 BCE to 2000 BCE, Pontic-Caspian Steppe, Balkans, Central Europe, Yamnaya "
            "cultural horizon, period-accurate clothing, architecture, tools, and material culture, 16:9, "
            "image only, no text"
        )
        compiled = compile_image_prompt(
            prepare_scene_contract_source(
                image_prompt,
                narration_context=(
                    "The Yamnaya left no royal list, so none of their chiefs survives by name."
                ),
            ),
            model_id="comfyui-flux2-klein-4b",
        )

        self.assertEqual(compiled.scene_kind, "face")
        self.assertEqual(compiled.person_count, 1)
        self.assertIn("3300-2600 BCE", compiled.positive)
        self.assertIn("exactly one unnamed bearded Yamnaya elder", compiled.positive)
        self.assertIn("Extreme face-only crop", compiled.positive)
        self.assertIn("zero visible shoulders, arms, hands, fingers, torsos, or legs", compiled.positive)
        self.assertNotIn("assembled clans", compiled.positive)
        self.assertIn("assembled clans", compiled.negative)
        self.assertIn("crowd", compiled.negative)
        self.assertIn("royal list", compiled.negative)
        self.assertIn("crown", compiled.negative)
        self.assertIn("visible shoulder", compiled.negative)

    def test_ch2_unnamed_chief_ignores_verified_wrinkle_text_false_positive_only(self):
        verified_prompt = (
            "Source workbook scene: Anonymous Yamnaya chief silhouetted before assembled clans "
            "with no inscription or written record. Primary subject: exactly one unnamed bearded "
            "Yamnaya elder. No readable writing."
        )
        self.assertTrue(_should_ignore_internal_text_detector(verified_prompt))
        self.assertTrue(
            _should_ignore_internal_text_detector(
                "Source workbook scene: Anonymous Yamnaya chief silhouetted before assembled clans "
                "with no inscription or written record."
            )
        )
        self.assertFalse(
            _should_ignore_internal_text_detector(
                "Anonymous Yamnaya chief beside an actual inscribed tablet."
            )
        )

    def test_ch2_social_actor_cut_uses_four_object_groups_without_people_or_regalia(self):
        scene = "Yamnaya chief, Young herder, Metalworker, women, children, and cattle gathered around a council fire"
        image_prompt = (
            "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene; "
            "Exact place: Pontic-Caspian Steppe; Yamnaya cultural horizon; "
            f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; Scene: {scene}, "
            "archaeologically grounded reconstruction, period-accurate clothing, architecture, tools, "
            "and material culture, 16:9, image only, no text"
        )
        compiled = compile_image_prompt(
            prepare_scene_contract_source(
                image_prompt,
                narration_context=(
                    "Our principal actors are therefore families, herders, craft specialists, and ambitious male leaders."
                ),
            ),
            model_id="comfyui-flux2-klein-4b",
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("3300-2600 BCE", compiled.positive)
        self.assertIn("exactly four separated evidence groups", compiled.positive)
        self.assertIn("upper-left one woven household packet", compiled.positive)
        self.assertIn("upper-right one wooden cattle yoke", compiled.positive)
        self.assertIn("lower-left one clay crucible and one hammerstone", compiled.positive)
        self.assertIn("lower-right one copper prestige blade blank", compiled.positive)
        self.assertNotIn("council fire", compiled.positive)
        self.assertIn("person", compiled.negative)
        self.assertIn("hand", compiled.negative)
        self.assertIn("leg", compiled.negative)
        self.assertIn("crown", compiled.negative)
        self.assertIn("medieval object", compiled.negative)
        self.assertIn("panel divider", compiled.negative)

    def test_ch2_mykhailivka_cut_uses_excavated_stone_wall_and_ditch_not_modern_village(self):
        scene = "Mobile wagons approaching the fortified riverside settlement of Mykhailivka on the lower Dnieper"
        image_prompt = (
            "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene; "
            "Exact place: Pontic-Caspian Steppe; Yamnaya cultural horizon; "
            f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; Scene: {scene}, "
            "archaeologically grounded reconstruction, period-accurate clothing, architecture, tools, "
            "and material culture, 16:9, image only, no text"
        )
        compiled = compile_image_prompt(
            prepare_scene_contract_source(
                image_prompt,
                narration_context=(
                    "Most lived as nomads or semi-nomads, although river settlements and fortified Mykhailivka complicate that image."
                ),
            ),
            model_id="comfyui-flux2-klein-4b",
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("3000-2500 BCE", compiled.positive)
        self.assertIn("Mykhailivka on the lower Dnieper", compiled.positive)
        self.assertIn("one solid three-plank wooden wheel disk", compiled.positive)
        self.assertIn("one high irregular dry-stone wall", compiled.positive)
        self.assertIn("one deep earthen ditch", compiled.positive)
        self.assertIn("low stone-founded houses", compiled.positive)
        self.assertNotIn("Mobile wagons approaching", compiled.positive)
        self.assertIn("spoked wheel", compiled.negative)
        self.assertIn("telegraph pole", compiled.negative)
        self.assertIn("palisade", compiled.negative)
        self.assertIn("castle", compiled.negative)
        self.assertIn("modern village", compiled.negative)
        self.assertIn("stone wall behind wheel", compiled.negative)
        self.assertIn("wall on left half", compiled.negative)
        self.assertIn("hand", compiled.negative)
        self.assertIn("leg", compiled.negative)

    def test_ch2_livelihood_cut_maps_every_narrated_activity_to_object_evidence(self):
        scene = "Busy Yamnaya camp with herding, fishing, pottery making, food preparation, and copper working"
        image_prompt = (
            "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene; "
            "Exact place: Pontic-Caspian Steppe; Yamnaya cultural horizon; "
            f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; Scene: {scene}, "
            "archaeologically grounded reconstruction, period-accurate clothing, architecture, tools, "
            "and material culture, 16:9, image only, no text"
        )
        compiled = compile_image_prompt(
            prepare_scene_contract_source(
                image_prompt,
                narration_context=(
                    "They raised animals, fished, gathered plants, shaped pottery, and forged increasingly prestigious metal objects."
                ),
            ),
            model_id="comfyui-flux2-klein-4b",
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("3300-2600 BCE", compiled.positive)
        self.assertIn("exactly five separated evidence groups", compiled.positive)
        self.assertIn("upper-left cattle yoke", compiled.positive)
        self.assertIn("plant-fibre net with four stone sinkers", compiled.positive)
        self.assertIn("basket of wild plants", compiled.positive)
        self.assertIn("lower-left handmade clay pot", compiled.positive)
        self.assertIn("lower-right crucible, copper blade blank, and hammerstone", compiled.positive)
        self.assertNotIn("Busy Yamnaya camp", compiled.positive)
        self.assertIn("person", compiled.negative)
        self.assertIn("hand", compiled.negative)
        self.assertIn("leg", compiled.negative)
        self.assertIn("metal fishing hook", compiled.negative)
        self.assertIn("glazed pottery", compiled.negative)
        self.assertIn("iron tool", compiled.negative)

    def test_ch2_governance_herd_and_mobility_cuts_use_object_evidence_without_medieval_people(self):
        cases = {
            "Yamnaya chief judging a dispute before several clan representatives and tethered herds": (
                "Chiefdoms coordinated movement, settled disputes, and controlled relationships extending far beyond one camp.",
                "exactly two equal balance stones",
                "exactly three smaller blank camp disks",
                "fur crown",
            ),
            "Young herder guarding a dense cattle herd while armed strangers watch from a distant ridge": (
                "A large herd created wealth, but it also created enemies, obligations, and constant logistical risk.",
                "one plain wooden cattle yoke",
                "one closed woven provisions packet",
                "spoked wheel",
            ),
            "Long wagon column crossing exposed grassland under the watch of mounted scouts and armed leaders": (
                "Mobility was not freedom alone; it was a weapon against distance and a test of command.",
                "exactly four solid disk wheels",
                "one plain wooden staff head",
                "mounted scout",
            ),
        }

        for scene, (narration, expected_a, expected_b, expected_negative) in cases.items():
            with self.subTest(scene=scene):
                image_prompt = (
                    "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene; "
                    "Exact place: Pontic-Caspian Steppe; Yamnaya cultural horizon; "
                    f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; Scene: {scene}, "
                    "archaeologically grounded reconstruction, period-accurate clothing, architecture, tools, "
                    "and material culture, 16:9, image only, no text"
                )
                compiled = compile_image_prompt(
                    prepare_scene_contract_source(image_prompt, narration_context=narration),
                    model_id="comfyui-flux2-klein-4b",
                )

                self.assertEqual(compiled.scene_kind, "object")
                self.assertEqual(compiled.person_count, 0)
                self.assertIn("3300-2600 BCE", compiled.positive)
                self.assertIn(expected_a, compiled.positive)
                self.assertIn(expected_b, compiled.positive)
                self.assertIn("person", compiled.negative)
                self.assertIn("hand", compiled.negative)
                self.assertIn("finger", compiled.negative)
                self.assertIn("leg", compiled.negative)
                self.assertIn(expected_negative, compiled.negative)
                self.assertNotIn(scene, compiled.positive)

    def test_ch2_burial_sequence_cuts_remove_mourners_workers_and_exposed_limbs(self):
        cases = {
            "Mourners lowering an elite Yamnaya chief into a rectangular grave lined with hides": (
                "When an important Yamnaya adult died, power was displayed inside a carefully prepared pit.",
                "object",
                "one fully closed ochre shroud",
                "one copper blade blank",
            ),
            "Red ochre scattered across the chief's wrapped body while mourners stand around the grave": (
                "The body was often covered with red ochre, turning burial into a vivid public spectacle.",
                "object",
                "densely dusted with vivid red ochre",
                "no body part protruding",
            ),
            "Workers piling earth into a tall kurgan visible across an otherwise flat steppe": (
                "An earthen kurgan rose above him, marking territory long after the mourners disappeared.",
                "landscape",
                "exactly one tall rounded earthen kurgan",
                "no person, animal, tool, road, house, or second mound",
            ),
            "Layered kurgan cross-section with successive burials arranged above the founding grave": (
                "Later graves could enter the same mound, binding descendants physically to an honored predecessor.",
                "object",
                "one deep founding rectangular pit",
                "exactly two smaller later rectangular pits",
            ),
            "Slaughtered sheep and cattle portions placed beside an elite burial during a solemn rite": (
                "Animal offerings showed that death consumed real wealth, not merely words and gestures.",
                "object",
                "one pale cattle horn core",
                "one smaller curled sheep horn core",
            ),
        }

        for scene, (narration, expected_kind, expected_a, expected_b) in cases.items():
            with self.subTest(scene=scene):
                image_prompt = (
                    "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene; "
                    "Exact place: Pontic-Caspian Steppe; Yamnaya cultural horizon; "
                    f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; Scene: {scene}, "
                    "archaeologically grounded reconstruction, period-accurate clothing, architecture, tools, "
                    "and material culture, 16:9, image only, no text"
                )
                compiled = compile_image_prompt(
                    prepare_scene_contract_source(image_prompt, narration_context=narration),
                    model_id="comfyui-flux2-klein-4b",
                )

                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, 0)
                self.assertIn("3300-2600 BCE", compiled.positive)
                self.assertIn(expected_a, compiled.positive)
                self.assertIn(expected_b, compiled.positive)
                self.assertIn("person", compiled.negative)
                self.assertIn("hand", compiled.negative)
                self.assertIn("finger", compiled.negative)
                self.assertIn("leg", compiled.negative)
                self.assertNotIn(scene, compiled.positive)

    def test_ch2_elite_inequality_wagon_and_oligarchy_cuts_use_hand_free_material_evidence(self):
        cases = {
            "Small group of elite male graves contrasted with a much larger living Yamnaya population": (
                "Only a small share of men received these elite burials compared with the much larger living population.",
                "3300-2600 BCE",
                "exactly three large ochre grave-cover disks",
                "exactly twelve much smaller plain grey household pebbles",
                "living population",
            ),
            "Two regional Yamnaya burials with distinct body positions and sharply different grave goods": (
                "Regional burial positions and grave goods varied sharply, exposing differences of rank and custom.",
                "3300-2600 BCE",
                "exactly two separated rectangular pits",
                "one bent L-shaped closed ochre shroud",
                "open shroud",
            ),
            "Complete four-wheeled wooden wagon lowered into a deep grave beside the deceased chief": (
                "Some elite graves received complete four-wheeled wagons, an exceptional investment in one dead leader.",
                "3300-2600 BCE",
                "one plain wooden wagon bed",
                "exactly four solid disk wheels",
                "spoked wheel",
            ),
            "Exhausted workers and oxen surrounding the chief's wagon burial as elite relatives supervise": (
                "The wagon burial concentrated extraordinary labor, traction equipment, and transport wealth.",
                "3300-2600 BCE",
                "exactly four separated labor groups",
                "exactly four thick plant-fibre rope coils",
                "worker",
            ),
            "Metalworker raising a newly cast copper blade beside a glowing crucible and watching chiefs": (
                "Specialist copper working could bring prestige, influence, and danger close to chiefly power.",
                "3300-2600 BCE",
                "one clay crucible with small copper droplets",
                "one plain copper blade blank without handle",
                "metalworker",
            ),
            "Copper daggers, axes, spearheads, and ornaments arranged around one richly furnished burial": (
                "Copper weapons and ornaments clustered in richly furnished graves instead of being shared evenly.",
                "3300-2600 BCE",
                "exactly ten separated copper artifacts",
                "three small plain spiral ornaments",
                "dagger handle",
            ),
            "Reich comparing ancient Y chromosomes, rich male graves, and a narrowing ancestry chart": (
                "David Reich linked ancient Y chromosomes and rich male graves to a narrowing oligarchy model.",
                "Era/period: present-day",
                "one isolated ancient molar",
                "exactly three smaller pale grave disks",
                "David Reich",
            ),
        }

        for scene, (narration, expected_era, expected_a, expected_b, expected_negative) in cases.items():
            with self.subTest(scene=scene):
                image_prompt = (
                    "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene; "
                    "Exact place: Pontic-Caspian Steppe; Yamnaya cultural horizon; "
                    f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; Scene: {scene}, "
                    "archaeologically grounded reconstruction, period-accurate clothing, architecture, tools, "
                    "and material culture, 16:9, image only, no text"
                )
                compiled = compile_image_prompt(
                    prepare_scene_contract_source(image_prompt, narration_context=narration),
                    model_id="comfyui-flux2-klein-4b",
                )

                self.assertEqual(compiled.scene_kind, "object")
                self.assertEqual(compiled.person_count, 0)
                self.assertIn(expected_era, compiled.positive)
                self.assertIn(expected_a, compiled.positive)
                self.assertIn(expected_b, compiled.positive)
                self.assertIn("hand", compiled.negative)
                self.assertIn("finger", compiled.negative)
                self.assertIn("leg", compiled.negative)
                self.assertIn(expected_negative, compiled.negative)
                self.assertNotIn(scene, compiled.positive)

    def test_ch2_hierarchy_transport_and_horse_claims_use_cautious_hand_free_evidence(self):
        cases = {
            "Kurgan cemetery emphasizing richly furnished male graves beside sparse ordinary burials": (
                "That interpretation remains a model, but graves plainly reveal hierarchy, gender, and concentrated privilege.",
                "object",
                "a sparse group of smaller plain graves",
                "one small flat unhafted crescent-shaped copper sheet",
                "modern belt buckle",
            ),
            "Row of kurgans growing across the steppe behind a commanding Yamnaya chief": (
                "Before their descendants moved west, Yamnaya society had already learned to make inequality monumental.",
                "landscape",
                "exactly seven rounded earthen kurgans",
                "six progressively smaller distant mounds",
                "chief",
            ),
            "Ox-drawn carts and wagons loaded with hides, vessels, food, tools, and families": (
                "Two-wheeled carts and four-wheeled wagons allowed households to carry shelter, supplies, and children.",
                "object",
                "one two-wheeled cart with two solid wooden disk wheels",
                "one four-wheeled wagon with four solid wooden disk wheels",
                "spoked wheel",
            ),
            "Powerful oxen straining against a loaded four-wheeled wagon on rough steppe ground": (
                "Oxen probably pulled those heavy vehicles, slowly extending the range of pastoral life.",
                "object",
                "exactly two oval collar loops",
                "exactly four solid disk wheels",
                "live ox",
            ),
            "Young herder riding a compact steppe horse beside cattle with anatomical bone details inset": (
                "Some skeletons show changes consistent with long riding, suggesting horses helped manage distant herds.",
                "object",
                "human pelvic-bone group",
                "one isolated ancient horse molar",
                "cavalry",
            ),
            "Archaeologists comparing disputed riding traces, horse teeth, and genetic timelines at an excavation": (
                "But modern horse research has unsettled older claims about exactly when domestication became widespread.",
                "object",
                "Era/period: present-day",
                "one six-sample archaeogenetic rack",
                "date",
            ),
            "Yamnaya migrants with ox wagons and a few riders, deliberately avoiding a mass cavalry charge": (
                "So these were not proven cavalry armies thundering west in a single invasion.",
                "landscape",
                "exactly two separated heavy household wagon groups",
                "exactly four solid disk wheels",
                "cavalry",
            ),
        }

        for scene, (narration, expected_kind, expected_a, expected_b, expected_negative) in cases.items():
            with self.subTest(scene=scene):
                image_prompt = (
                    "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene; "
                    "Exact place: Pontic-Caspian Steppe; Yamnaya cultural horizon; "
                    f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; Scene: {scene}, "
                    "archaeologically grounded reconstruction, period-accurate clothing, architecture, tools, "
                    "and material culture, 16:9, image only, no text"
                )
                compiled = compile_image_prompt(
                    prepare_scene_contract_source(image_prompt, narration_context=narration),
                    model_id="comfyui-flux2-klein-4b",
                )

                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, 0)
                self.assertIn(expected_a, compiled.positive)
                self.assertIn(expected_b, compiled.positive)
                self.assertIn("hand", compiled.negative)
                self.assertIn("finger", compiled.negative)
                self.assertIn("leg", compiled.negative)
                self.assertIn(expected_negative, compiled.negative)
                self.assertNotIn(scene, compiled.positive)

    def test_ch2_mobile_network_and_frontier_cuts_use_period_safe_material_evidence(self):
        cases = {
            "Families, cattle, wagons, ritual objects, and messengers moving along interconnected steppe routes": (
                "object", "exactly three equal blank clan disks", "mobile-community network linking household transport", "covered wagon"
            ),
            "Yamnaya families dividing between two wagon columns while chiefs negotiate beside a fire": (
                "object", "exactly two touching pale alliance disks", "camp-fission model with two solid-wheel wagon branches", "fire"
            ),
            "Multiple independent chiefs connected by marriage gifts, cattle exchanges, and shared burial customs": (
                "object", "exactly four equal ochre clan disks", "one low shared-kurgan token", "large central ruler disk"
            ),
            "Chain of matching kurgans stretching between the Dnieper, Don, and Volga river landscapes": (
                "landscape", "exactly three broad blue-grey river bands", "exactly six matching rounded earthen kurgans", "river label"
            ),
            "Wagon column descending toward Danube farmland, timber houses, fields, and defensive fences": (
                "landscape", "one four-solid-wheel Yamnaya wagon", "one low timber longhouse", "covered wagon"
            ),
            "Yamnaya chief and farmer elder studying each other's cattle, fields, weapons, and households": (
                "object", "one solid wheel disk", "one fenced field grid", "live cattle"
            ),
            "Central European farming village facing a temporary Yamnaya camp across a river": (
                "landscape", "exactly two low timber longhouses", "exactly two low hide shelters", "modern house"
            ),
            "Exchange feast shadowed by armed guards, a marriage procession, tense bargaining, and burned fencing": (
                "object", "exactly two touching alliance disks", "four-part archaeological frontier evidence", "feast crowd"
            ),
            "Excavators carefully examining a burned house and injured skeleton without assigning an attacker": (
                "object", "Era/period: present-day", "one isolated fractured human long bone", "attacker"
            ),
            "Population silhouettes shifting dramatically as steppe ancestry spreads into Central Europe": (
                "object", "Era/period: present-day", "exactly sixteen equal ancestry tiles", "population silhouette"
            ),
        }

        for scene, (kind, expected_a, expected_b, expected_negative) in cases.items():
            with self.subTest(scene=scene):
                image_prompt = (
                    "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene; "
                    "Exact place: Pontic-Caspian Steppe; Yamnaya cultural horizon; "
                    f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; Scene: {scene}, "
                    "archaeologically grounded reconstruction, period-accurate clothing, architecture, tools, "
                    "and material culture, 16:9, image only, no text"
                )
                compiled = compile_image_prompt(
                    prepare_scene_contract_source(
                        image_prompt,
                        narration_context="The spoken line is matched by the visible material evidence.",
                    ),
                    model_id="comfyui-flux2-klein-4b",
                )

                self.assertEqual(compiled.scene_kind, kind)
                self.assertEqual(compiled.person_count, 0)
                self.assertIn(expected_a, compiled.positive)
                self.assertIn(expected_b, compiled.positive)
                self.assertIn("hand", compiled.negative)
                self.assertIn("finger", compiled.negative)
                self.assertIn("leg", compiled.negative)
                self.assertIn(expected_negative, compiled.negative)
                self.assertNotIn(scene, compiled.positive)

    def test_ch2_corded_ware_and_adna_cuts_remove_warriors_hands_and_maps(self):
        cases = {
            "Corded Ware cemetery in Germany with sampled teeth and a glowing ancient-DNA profile": (
                "Around 2500 BCE, Central European graves began yielding a startling genetic signature.",
                "2900-2300 BCE",
                "exactly four equal ancestry tiles",
            ),
            "Corded Ware funeral with cord-decorated pottery, stone battle-axe, wool clothing, and single burial": (
                "The people buried there belonged to what archaeologists call the Corded Ware culture.",
                "2900-2300 BCE",
                "Corded Ware single grave",
            ),
            "Corded Ware warrior buried alone with polished battle-axe and corded beaker": (
                "Many men were buried individually with battle-axes, drinking vessels, and carefully oriented bodies.",
                "2900-2300 BCE",
                "Corded Ware single grave",
            ),
            "Yamnaya kurgan and Corded Ware grave linked by ancestry strands despite different burial arrangements": (
                "Those customs were not identical to Yamnaya practice, but the biological connection proved enormous.",
                "2900-2300 BCE",
                "exactly three ochre ancestry disks",
            ),
            "Ancient-DNA researchers sampling teeth and sequencing genomes across a map of prehistoric Europe": (
                "In a landmark 2015 study, Wolfgang Haak's team analyzed ancient genomes from across Europe.",
                "Era/period: present-day",
                "six sampled molars",
            ),
            "Corded Ware warrior portrait formed from three parts steppe ancestry and one part local ancestry": (
                "German Corded Ware individuals traced roughly seventy-five percent of their ancestry to Yamnaya-related people.",
                "Era/period: present-day",
                "three-to-one ancestry ratio",
            ),
            "Dense east-to-west migration arrows carrying families into Central European river valleys": (
                "That number documented massive migration from Europe's eastern edge into its central heartland.",
                "Era/period: present-day",
                "demographic migration evidence",
            ),
            "Yamnaya-related families arriving with children, livestock, wagons, tools, and household goods": (
                "The movement involved living communities, not a fashion copied from distant neighbors.",
                "around 2500 BCE",
                "household migration evidence",
            ),
            "Generations of Central European families connected through an enduring steppe ancestry line": (
                "Steppe ancestry then persisted in sampled Central Europeans for thousands of years.",
                "Era/period: present-day",
                "five ancient molars",
            ),
        }

        for scene, (narration, expected_era, expected_positive) in cases.items():
            with self.subTest(scene=scene):
                image_prompt = (
                    "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene; "
                    "Exact place: Central Europe; Corded Ware and Yamnaya-related communities; "
                    f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; Scene: {scene}, "
                    "archaeologically grounded reconstruction, period-accurate clothing, architecture, tools, "
                    "and material culture, 16:9, image only, no text"
                )
                compiled = compile_image_prompt(
                    prepare_scene_contract_source(image_prompt, narration_context=narration),
                    model_id="comfyui-flux2-klein-4b",
                )

                self.assertEqual(compiled.scene_kind, "object")
                self.assertEqual(compiled.person_count, 0)
                self.assertIn(expected_era, compiled.positive)
                self.assertIn(expected_positive, compiled.positive)
                self.assertIn("hand", compiled.negative)
                self.assertIn("finger", compiled.negative)
                self.assertIn("leg", compiled.negative)
                self.assertNotIn(scene, compiled.positive)

    def test_ch2_later_mixture_corded_network_and_bell_beaker_cuts_are_body_free(self):
        cases = {
            "Layered portraits of later European populations built from multiple ancestry streams without racial typology": ("object", "present-day"),
            "Farming valley transforming as new households, graves, animals, and customs fill the region": ("landscape", "2900-2300 BCE"),
            "Farmer families choosing among retreat, guarded resistance, intermarriage, and alliance with migrants": ("object", "2900-2300 BCE"),
            "Abandoned Neolithic house beneath a later Corded Ware settlement with missing family silhouettes": ("object", "2900-2300 BCE"),
            "Ancient DNA chart fading into a tense face-to-face meeting between chiefs and villagers": ("object", "present-day"),
            "Table of battle-axes, copper daggers, beakers, marriage gifts, and burial plans under study": ("object", "present-day"),
            "Panoramic Corded Ware cultural zone spanning forests, rivers, farmland, and eastern grassland": ("landscape", "2900-2300 BCE"),
            "Several distinct Corded Ware communities with varied houses, clothing, graves, and landscapes": ("object", "2900-2300 BCE"),
            "Travelers carrying corded pottery and axes between distant but related settlements": ("object", "2900-2300 BCE"),
            "Bell Beaker archer arriving in western Europe with distinctive vessel, wrist guard, and mixed ancestry": ("object", "2800-1800 BCE"),
        }

        for scene, (kind, era) in cases.items():
            with self.subTest(scene=scene):
                image_prompt = (
                    "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene; "
                    "Exact place: Central and Western Europe; Yamnaya cultural horizon; "
                    f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; Scene: {scene}, "
                    "archaeologically grounded reconstruction, period-accurate clothing, architecture, tools, "
                    "and material culture, 16:9, image only, no text"
                )
                compiled = compile_image_prompt(
                    prepare_scene_contract_source(
                        image_prompt,
                        narration_context="The visible material evidence follows the spoken line.",
                    ),
                    model_id="comfyui-flux2-klein-4b",
                )
                self.assertEqual(compiled.scene_kind, kind)
                self.assertEqual(compiled.person_count, 0)
                self.assertIn(era, compiled.positive)
                self.assertIn("hand", compiled.negative)
                self.assertIn("finger", compiled.negative)
                self.assertIn("leg", compiled.negative)
                self.assertNotIn(scene, compiled.positive)

    def test_ch2_eastern_network_language_and_gimbutas_model_cuts_are_body_free_and_era_locked(self):
        cases = {
            "Migration paths continuing east toward fortified Sintashta settlements and later Andronovo herders": (
                "3300-1450 BCE",
                "chronological archaeological sequence",
            ),
            "Branching migration routes crossing, merging, and turning back across Eurasia over generations": (
                "present-day",
                "repeated-migration model",
            ),
            "Separate migrant columns carrying different combinations of livestock, tools, rituals, and ancestry": (
                "present-day",
                "partial cultural-package comparison",
            ),
            "Family tree of languages crossing but not perfectly matching an ancient ancestry map": (
                "present-day",
                "non-lockstep comparison",
            ),
            "Village assembly divided between steppe migrants and local speakers during a tense negotiation": (
                "present-day",
                "unresolved language-shift question",
            ),
            "Gimbutas arranging kurgan maps, warrior stelae, and Old European settlement photographs": (
                "1956-1994 AD",
                "Marija Gimbutas research assemblage",
            ),
            "Gimbutas tracing a connection from kurgans to a branching Proto-Indo-European language map": (
                "1956-1994 AD",
                "Kurgan-hypothesis diagram",
            ),
            "Armed mobile herders approaching a prosperous Neolithic farming settlement under Gimbutas's model": (
                "1956-1994 AD",
                "two-field reconstruction",
            ),
            "Victorious Yamnaya-style leaders presiding over a subdued village in a clearly labeled interpretive tableau": (
                "1956-1994 AD",
                "four-domain diagram",
            ),
            "Male war band displaying axes and spears beneath a lineage tree centered on fathers and sons": (
                "1956-1994 AD",
                "weapons, warrior-image, and patrilineal-organization evidence",
            ),
        }

        for scene, (expected_era, expected_positive) in cases.items():
            with self.subTest(scene=scene):
                image_prompt = (
                    "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene; "
                    "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; "
                    "Yamnaya cultural horizon, Neolithic European communities; "
                    f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; Scene: {scene}, "
                    "archaeologically grounded reconstruction, period-accurate clothing, architecture, tools, "
                    "and material culture, 16:9, image only, no text"
                )
                compiled = compile_image_prompt(
                    prepare_scene_contract_source(
                        image_prompt,
                        narration_context="The visible evidence must distinguish archaeology from a later interpretive model.",
                    ),
                    model_id="comfyui-flux2-klein-4b",
                )

                self.assertEqual(compiled.scene_kind, "object")
                self.assertEqual(compiled.person_count, 0)
                self.assertIn(expected_era, compiled.positive)
                self.assertIn(expected_positive, compiled.positive)
                self.assertIn("hand", compiled.negative)
                self.assertIn("finger", compiled.negative)
                self.assertIn("leg", compiled.negative)
                self.assertNotIn(scene, compiled.positive)

    def test_ch2_anthony_parpola_and_elite_language_model_cuts_are_body_free_and_era_locked(self):
        cases = {
            "Dramatic invasion mural breaking apart into scattered graves, settlements, and uncertain archaeological traces": (
                "present-day",
                "archaeological review",
            ),
            "Anthony comparing Gimbutas's invasion arrows with a network of alliances and elite contacts": (
                "2007 AD",
                "scholarly comparison",
            ),
            "Local leaders joining a prestigious steppe council while villagers observe the political shift": (
                "2007 AD",
                "elite-recruitment network model",
            ),
            "Compact Yamnaya delegation entering a village with copper weapons, horses, cattle, and ceremonial gifts": (
                "2007 AD",
                "small-group power package",
            ),
            "Farmer elder weighing a stone axe against offered copper weapon and marriage bracelet": (
                "2007 AD",
                "network decision model",
            ),
            "Village factions split as the farmer elder chooses between armed resistance and alliance": (
                "2007 AD",
                "two-outcome model",
            ),
            "Local chiefs entering a compact migrant coalition around a shared feast and weapons display": (
                "2012 AD",
                "Asko Parpola scholarly model",
            ),
            "Copper dagger, rare ornament, livestock gift, and polished axe displayed before watching villagers": (
                "2012 AD",
                "prestige, trade-access",
            ),
            "Wedding between steppe migrant and farming family before two watchful kin groups": (
                "2012 AD",
                "marriage-alliance kinship model",
            ),
            "Local chief addressing retainers in a new language as interpreters and scribeless memory keepers listen": (
                "present-day",
                "unwritten elite-language diffusion model",
            ),
        }

        for scene, (expected_era, expected_positive) in cases.items():
            with self.subTest(scene=scene):
                image_prompt = (
                    "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene; "
                    "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; "
                    "Yamnaya cultural horizon, Neolithic European communities; "
                    f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; Scene: {scene}, "
                    "archaeologically grounded reconstruction, period-accurate clothing, architecture, tools, "
                    "and material culture, 16:9, image only, no text"
                )
                compiled = compile_image_prompt(
                    prepare_scene_contract_source(
                        image_prompt,
                        narration_context="The visible evidence must distinguish a named modern model from prehistoric fact.",
                    ),
                    model_id="comfyui-flux2-klein-4b",
                )

                self.assertEqual(compiled.scene_kind, "object")
                self.assertEqual(compiled.person_count, 0)
                self.assertIn(expected_era, compiled.positive)
                self.assertIn(expected_positive, compiled.positive)
                self.assertIn("hand", compiled.negative)
                self.assertIn("finger", compiled.negative)
                self.assertIn("leg", compiled.negative)
                self.assertNotIn(scene, compiled.positive)

    def test_ch2_language_power_kurgan_and_network_dynamics_cuts_are_body_free_and_era_locked(self):
        cases = {
            "Young villagers learning elite speech during feasting, oath making, guard service, and courtship": (
                "object", "present-day", "five-benefit language-access model"
            ),
            "Three generations of one mixed household shifting gradually from local speech to steppe-derived speech": (
                "object", "present-day", "three-generation household sequence"
            ),
            "Armed retainers standing behind negotiators as a reluctant village accepts new obligations": (
                "object", "present-day", "coercion-and-alliance model"
            ),
            "Night cattle raid followed by frightened villagers seeking protection from a powerful chief": (
                "object", "present-day", "raid-and-protection mechanism"
            ),
            "Yamnaya chief distributing meat and gifts during a feast guarded by armed followers": (
                "object", "present-day", "feast-loyalty mechanism"
            ),
            "Towering kurgan overlooking smaller farms, paths, and graves across a settled valley": (
                "landscape", "3300-2600 BCE", "landscape-only Yamnaya kurgan"
            ),
            "Young herder accepting a weapon and oath before joining the chief's mobile retinue": (
                "object", "present-day", "service-for-status model"
            ),
            "Metalworker presenting a polished copper axe to the Yamnaya chief before assembled followers": (
                "object", "present-day", "craft-patronage model"
            ),
            "Network of allied camps expanding around shared grazing land and marriage connections": (
                "object", "present-day", "alliance-expansion network"
            ),
            "Rival heirs arguing over cattle while allied camps split and armed followers choose sides": (
                "object", "present-day", "three-cause network-fracture model"
            ),
        }

        for scene, (expected_kind, expected_era, expected_positive) in cases.items():
            with self.subTest(scene=scene):
                image_prompt = (
                    "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene; "
                    "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; "
                    "Yamnaya cultural horizon, Neolithic European communities; "
                    f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; Scene: {scene}, "
                    "archaeologically grounded reconstruction, period-accurate clothing, architecture, tools, "
                    "and material culture, 16:9, image only, no text"
                )
                compiled = compile_image_prompt(
                    prepare_scene_contract_source(
                        image_prompt,
                        narration_context="The scene must show the narrated mechanism without inventing undocumented people.",
                    ),
                    model_id="comfyui-flux2-klein-4b",
                )

                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, 0)
                self.assertIn(expected_era, compiled.positive)
                self.assertIn(expected_positive, compiled.positive)
                self.assertIn("hand", compiled.negative)
                self.assertIn("finger", compiled.negative)
                self.assertIn("leg", compiled.negative)
                self.assertNotIn(scene, compiled.positive)

    def test_ch2_language_evidence_and_yamnaya_ancestry_cuts_are_body_free_and_present_day_models(self):
        cases = {
            "Single wagon route dividing into several independent migration columns under rival leaders": "branching-migration model",
            "One ancestral speech line dividing into increasingly distinct regional conversations": "contact-loss language model",
            "Kin group, cattle, wagon wheel, and ritual fire linked to reconstructed word roots": "shared-word evidence model",
            "Steppe speakers learning local words while working fields and entering European forests": "local-vocabulary input model",
            "Mixed household speaking across generations during farming, herding, marriage, and ritual": "four-process model",
            "Branching language tree rising behind early European communities without modern national symbols": "ancestral language model",
            "Blank centuries between prehistoric migration maps and the first written Indo-European texts": "evidence-gap model",
            "Battle-axe, ancient skeleton, and comparative word list aligned as three evidence columns": "three-column comparison",
            "Three overlapping maps from archaeology, genetics, and linguistics with mismatched boundaries": "mismatch model",
            "Yamnaya family emerging from two older ancestry streams meeting north of the Caucasus": "ancient-DNA mixture model",
        }

        for scene, expected_positive in cases.items():
            with self.subTest(scene=scene):
                image_prompt = (
                    "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene; "
                    "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; "
                    "Yamnaya cultural horizon, Neolithic European communities; "
                    f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; Scene: {scene}, "
                    "archaeologically grounded reconstruction, period-accurate clothing, architecture, tools, "
                    "and material culture, 16:9, image only, no text"
                )
                compiled = compile_image_prompt(
                    prepare_scene_contract_source(
                        image_prompt,
                        narration_context="The spoken line is represented by a present-day evidence model, not a literal reenactment.",
                    ),
                    model_id="comfyui-flux2-klein-4b",
                )

                self.assertEqual(compiled.scene_kind, "object")
                self.assertEqual(compiled.person_count, 0)
                self.assertIn("present-day", compiled.positive)
                self.assertIn(expected_positive, compiled.positive)
                self.assertIn("hand", compiled.negative)
                self.assertIn("finger", compiled.negative)
                self.assertIn("leg", compiled.negative)
                self.assertNotIn(scene, compiled.positive)

    def test_ch2_latest_formation_lineage_and_cultural_sequence_cuts_are_body_free_and_era_locked(self):
        cases = {
            "Pre-Yamnaya communities connected between the Caucasus foothills and lower Volga river": (
                "2025 AD", "Caucasus-Lower-Volga population-network model"
            ),
            "Multiple older communities merging into the Yamnaya horizon before its expansion": (
                "2025 AD", "source-population mixture model"
            ),
            "Four predecessor cultural zones converging around early Yamnaya settlements and graves": (
                "2025 AD", "four-predecessor archaeological model"
            ),
            "Researchers debating separate maps of language origin, ancestry formation, and cultural development": (
                "2025 AD", "three-column scholarly-dispute model"
            ),
            "Y chromosome lineages from Yamnaya graves failing to align perfectly with Corded Ware men": (
                "2025 AD", "paternal-lineage mismatch model"
            ),
            "Complex ancestry network replacing a simplistic arrow from one Yamnaya man to all Europeans": (
                "2025 AD", "complex steppe-ancestry network"
            ),
            "Corded Ware settlement containing mixed families, local farming tools, steppe customs, and new graves": (
                "2900-2300 BCE", "Corded Ware mixed-society assemblage"
            ),
            "Corded Ware community transitioning into Bell Beaker and later Bronze Age cultural scenes": (
                "2900-1200 BCE", "chronological material sequence"
            ),
            "Successive generations passing movement, authority, and ancestry across a changing European map": (
                "present-day", "population-and-power chain-reaction model"
            ),
            "Modern researchers entering a museum store filled with carefully boxed prehistoric skeletons": (
                "present-day", "grave-sample archive"
            ),
        }

        for scene, (expected_era, expected_positive) in cases.items():
            with self.subTest(scene=scene):
                image_prompt = (
                    "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene; "
                    "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; "
                    "Yamnaya cultural horizon, Neolithic European communities; "
                    f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; Scene: {scene}, "
                    "archaeologically grounded reconstruction, period-accurate clothing, architecture, tools, "
                    "and material culture, 16:9, image only, no text"
                )
                compiled = compile_image_prompt(
                    prepare_scene_contract_source(
                        image_prompt,
                        narration_context="Use the narrated evidence and chronology without inventing people or bodies.",
                    ),
                    model_id="comfyui-flux2-klein-4b",
                )

                self.assertEqual(compiled.scene_kind, "object")
                self.assertEqual(compiled.person_count, 0)
                self.assertIn(expected_era, compiled.positive)
                self.assertIn(expected_positive, compiled.positive)
                self.assertIn("person", compiled.negative)
                self.assertIn("hand", compiled.negative)
                self.assertIn("finger", compiled.negative)
                self.assertIn("leg", compiled.negative)
                self.assertNotIn(scene, compiled.positive)

    def test_ch2_adna_methods_2015_result_and_human_limit_cuts_are_body_free_and_era_locked(self):
        cases = {
            "Reich's laboratory sampling a petrous bone in a sterile clean room": (
                "present-day", "sterile ancient-DNA sampling station"
            ),
            "Gloved technicians processing ancient bone powder through clean laboratory equipment": (
                "present-day", "four-stage ancient-DNA powder-and-extraction pipeline"
            ),
            "Sequencing screens linking prehistoric individuals across a time-scaled map of Europe": (
                "present-day", "computational ancient-DNA comparison matrix"
            ),
            "Scientists watching a clear steppe ancestry cluster emerge from ancient genome data": (
                "2015 AD", "2015 ancient-genome cluster model"
            ),
            "Ancient population map showing a major influx from the steppe into Central Europe": (
                "2015 AD", "demographic-influx model"
            ),
            "Gimbutas's kurgan map beside DNA results with confirmed migration and unconfirmed battle scenes separated": (
                "2015 AD", "migration-not-invasion evidence comparison"
            ),
            "Mixed-ancestry couple at a prehistoric wedding with uncertain expressions and armed relatives": (
                "present-day", "genetics-limit model"
            ),
            "Two neighboring villages responding differently to the same approaching migrant group": (
                "present-day", "unknown-response model"
            ),
            "Rapid tableau of a shouted insult, sworn oath, guarded hostage, cattle raid, and handshake": (
                "present-day", "five-missing-decisions model"
            ),
            "Individual faces in a tense frontier crowd emerging from an impersonal ancestry graph": (
                "present-day", "ancestry-to-human-decisions model"
            ),
        }

        for scene, (expected_era, expected_positive) in cases.items():
            with self.subTest(scene=scene):
                image_prompt = (
                    "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene; "
                    "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; "
                    "Yamnaya cultural horizon, Neolithic European communities; "
                    f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; Scene: {scene}, "
                    "archaeologically grounded reconstruction, period-accurate clothing, architecture, tools, "
                    "and material culture, 16:9, image only, no text"
                )
                compiled = compile_image_prompt(
                    prepare_scene_contract_source(
                        image_prompt,
                        narration_context="Show the scientific evidence or its limit without inventing people, gestures, or battle scenes.",
                    ),
                    model_id="comfyui-flux2-klein-4b",
                )

                self.assertEqual(compiled.scene_kind, "object")
                self.assertEqual(compiled.person_count, 0)
                self.assertIn(expected_era, compiled.positive)
                self.assertIn(expected_positive, compiled.positive)
                self.assertIn("person", compiled.negative)
                self.assertIn("hand", compiled.negative)
                self.assertIn("finger", compiled.negative)
                self.assertIn("leg", compiled.negative)
                self.assertIn("medieval clothing", compiled.negative)
                self.assertNotIn(scene, compiled.positive)

    def test_ch2_homeland_debate_and_chief_decision_cuts_are_era_locked_with_safe_anatomy(self):
        cases = {
            "Klejn challenging a straight migration arrow with alternative ancestry distributions on a map": (
                "object", 0, "present-day", "route-critique model"
            ),
            "Competing homeland circles around the steppe, Caucasus, and western Asia": (
                "object", 0, "present-day", "three-model homeland comparison"
            ),
            "Updated research map moving the earliest language origin toward the Caucasus-Lower Volga zone": (
                "object", 0, "2025 AD", "Caucasus-Lower-Volga deep-origin update model"
            ),
            "Firm evidence panel connecting Yamnaya-related groups to major Central European ancestry change": (
                "object", 0, "2015 AD", "narrow-conclusion model"
            ),
            "Steppe migration routes aligned with several, but not all, Indo-European language branches": (
                "object", 0, "present-day", "partial-language-branch alignment model"
            ),
            "Yamnaya chief alive beside a fresh kurgan as followers, wagons, and herds assemble": (
                "single", 1, "3300-2600 BCE", "one anonymous hand-hidden chief"
            ),
            "Yamnaya chief looking west across empty grassland with distant future maps hidden in clouds": (
                "single", 1, "3300-2600 BCE", "one anonymous hand-hidden chief"
            ),
            "Chief surveying thin pasture, rival campfires, a marriage delegation, and dark winter clouds": (
                "object", 0, "3300-2600 BCE", "four-part immediate-horizon model"
            ),
            "Chief pointing as one wagon group prepares westward and another negotiates with visitors": (
                "object", 0, "3300-2600 BCE", "three-way camp decision model"
            ),
            "Small cattle skirmish contrasted with a vast allied route of camps, rivers, and kurgans": (
                "object", 0, "3300-2600 BCE", "herd-skirmish versus alliance-network comparison"
            ),
        }

        for scene, (expected_kind, expected_count, expected_era, expected_positive) in cases.items():
            with self.subTest(scene=scene):
                image_prompt = (
                    "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene; "
                    "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; "
                    "Yamnaya cultural horizon, Neolithic European communities; "
                    f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; Scene: {scene}, "
                    "archaeologically grounded reconstruction, period-accurate clothing, architecture, tools, "
                    "and material culture, 16:9, image only, no text"
                )
                compiled = compile_image_prompt(
                    prepare_scene_contract_source(
                        image_prompt,
                        narration_context="Keep scholarly claims separate and show only count-safe anatomy where the narration returns to the chief.",
                    ),
                    model_id="comfyui-flux2-klein-4b",
                )

                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, expected_count)
                self.assertIn(expected_era, compiled.positive)
                self.assertIn(expected_positive, compiled.positive)
                self.assertIn("hand", compiled.negative)
                self.assertIn("finger", compiled.negative)
                self.assertIn("leg", compiled.negative)
                self.assertIn("medieval", compiled.negative)
                self.assertNotIn(scene, compiled.positive)

    def test_ch2_final_power_transition_and_horse_teaser_cuts_are_body_free_and_era_locked(self):
        cases = {
            "Wagons, marriage bonds, elite graves, armed retainers, and herds forming one power system": (
                "object", "3300-2600 BCE", "integrated mobility-status-kinship-force system"
            ),
            "Successive farmer leaders joining the network while children learn the prestige language": (
                "object", "present-day", "three-generation leader-and-household language-transmission model"
            ),
            "Mixed children growing into a distinct Corded Ware community unlike either original group": (
                "object", "2900-2300 BCE", "Corded Ware new-identity mixture model"
            ),
            "Night-to-dawn sequence of camps and graves spreading gradually across a European landscape": (
                "landscape", "3300-2300 BCE", "gradual camp-by-camp and grave-by-grave transition"
            ),
            "Opened graves and DNA charts surrounding unseen prehistoric negotiations beneath the soil": (
                "object", "present-day", "dead-scale versus living-motives evidence model"
            ),
            "Horse beside an Indo-European royal sacrifice ground as priests and a tense claimant approach": (
                "object", "present-day", "flat four-legged horse token"
            ),
            "Priests arranging a horse sacrifice while the future king faces assembled warriors": (
                "object", "present-day", "four-legged horse token rests inside one ritual ring"
            ),
            "Horse-sacrifice traditions connected across the steppe, ancient India, Rome, and medieval Ireland": (
                "object", "present-day", "Exactly four separate evidence fields each contain one flat clay horse token with exactly four separated legs"
            ),
            "Royal horse entering a guarded ritual enclosure before a crowd of rival nobles": (
                "object", "present-day", "One four-legged horse token rests inside one open dashed ritual enclosure"
            ),
            "Ancient skull, wagon track, kurgan, and mixed family joined in a final cinematic tableau": (
                "object", "present-day", "final archaeology-and-migration evidence synthesis"
            ),
        }

        for scene, (expected_kind, expected_era, expected_positive) in cases.items():
            with self.subTest(scene=scene):
                image_prompt = (
                    "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene; "
                    "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; "
                    "Yamnaya cultural horizon, Neolithic European communities; "
                    f"Scene evidence: Source workbook scene: {scene}; Main subject: {scene}; Scene: {scene}, "
                    "archaeologically grounded reconstruction, period-accurate clothing, architecture, tools, "
                    "and material culture, 16:9, image only, no text"
                )
                compiled = compile_image_prompt(
                    prepare_scene_contract_source(
                        image_prompt,
                        narration_context="Close the episode with narration-matched material evidence and keep the next-episode horse ritual explicitly comparative.",
                    ),
                    model_id="comfyui-flux2-klein-4b",
                )

                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, 0)
                self.assertIn(expected_era, compiled.positive)
                self.assertIn(expected_positive, compiled.positive)
                self.assertIn("hand", compiled.negative)
                self.assertIn("finger", compiled.negative)
                self.assertIn("leg", compiled.negative)
                self.assertIn("medieval", compiled.negative)
                self.assertNotIn(scene, compiled.positive)

    def test_ch2_registered_hand_risk_scenes_use_object_only_evidence(self):
        cases = {
            "Anthropomorphic stone stela with carved belt, hands, axe, and dagger overlooking a burial": (
                "one shallow oval head outline",
                "carved hand",
            ),
            "Close view of hands pressing twisted cord into the surface of a wet clay beaker": (
                "fresh horizontal twisted-cord impressions",
                "hand",
            ),
            "Chief pointing as one wagon group prepares westward and another negotiates with visitors": (
                "exactly two small touching grey alliance disks",
                "pointing gesture",
            ),
        }

        for scene, (expected_positive, expected_negative) in cases.items():
            with self.subTest(scene=scene):
                image_prompt = (
                    "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene, 3500 BCE to 2000 BCE; "
                    "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; "
                    "Yamnaya cultural horizon, Neolithic European communities; "
                    f"Scene evidence: Source workbook scene: {scene}; "
                    f"Main subject: {scene}; Scene: {scene}, archaeologically grounded late Neolithic and early Bronze Age "
                    "reconstruction with tense human storytelling, 3500 BCE to 2000 BCE, Pontic-Caspian Steppe, Balkans, "
                    "Central Europe, Yamnaya cultural horizon, Neolithic European communities, period-accurate clothing, "
                    "architecture, tools, and material culture, overhead environmental shot, 28mm lens, natural daylight, "
                    "cinematic documentary realism, natural texture, 16:9, image only, no text, no watermark"
                )
                compiled = compile_image_prompt(
                    prepare_scene_contract_source(
                        image_prompt,
                        narration_context="The archaeological scene supplies direct material evidence.",
                    ),
                    model_id="comfyui-flux2-klein-4b",
                )

                self.assertEqual(compiled.scene_kind, "object")
                self.assertEqual(compiled.person_count, 0)
                self.assertIn(expected_positive, compiled.positive)
                self.assertIn(expected_negative, compiled.negative)
                self.assertNotIn("Source workbook scene", compiled.positive)

    def test_japanese_primordial_rocky_coast_ignores_person_segmentation(self):
        prompt = (
            "Scene: A beautiful ancient Japanese coastal landscape. "
            "High ocean waves crashing against jagged rocks. "
            "No person, body, face, hand, clothing, or human silhouette."
        )

        self.assertTrue(_should_ignore_object_person_segmentation(prompt))

    def test_baekje_ep02_cross_sea_clay_markers_ignore_person_segmentation(self):
        prompt = (
            "Overhead on one continuous matte blue-grey clay sea between narrow brown shores: "
            "one small solid dark-brown oval migration pebble rests on the left shore and "
            "one small blank pale rectangular source block rests on the opposite right shore."
        )

        self.assertTrue(_should_ignore_object_person_segmentation(prompt))
        self.assertFalse(
            _should_ignore_object_person_segmentation(
                "One human traveler stands on the left shore opposite a source block."
            )
        )

    def test_japanese_world_myth_comparison_is_textless_and_person_free(self):
        image_prompt = (
            "Year/period: Japanese mythic creation era; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Exact place: bare primordial shore of the Japanese islands; "
            "Scene: A vintage world map with a glowing golden line tracing mythologies across oceans. "
            "Conceptual macro photography, 50mm lens, highlighting global legends."
        )
        source = prepare_scene_contract_source(
            image_prompt,
            narration_context="実は これ、 日本 だけ の 特別 な お話 では ありません。",
        )

        compiled = compile_image_prompt(
            source,
            model_id="comfyui-flux2-klein-4b",
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertIn(
            "one continuous route links exactly five blank island tokens",
            compiled.positive,
        )
        self.assertIn("person", compiled.negative)
        self.assertIn("map label", compiled.negative)
        self.assertIn("pseudo-writing", compiled.negative)
        self.assertIn("indigenous girl", compiled.negative)
        self.assertIn("black border", compiled.negative)
        self.assertIn("hand", compiled.negative)

    def test_japanese_sun_moon_separation_has_no_extra_deities(self):
        image_prompt = (
            "Year/period: Japanese mythic creation era; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Scene: A glowing golden sun and a brilliant silver moon hovering perfectly balanced, but cracked in the middle. "
            "Conceptual macro photography, 50mm lens, highlighting cosmic tension."
        )
        source = prepare_scene_contract_source(
            image_prompt,
            narration_context="前回 は、 太陽 と 月 が 永遠 に 別れた 衝撃 的 な 事件 を お 話 しました。",
        )

        compiled = compile_image_prompt(source, model_id="comfyui-flux2-klein-4b")

        self.assertEqual(compiled.scene_kind, "landscape")
        self.assertIn("broad uninterrupted band of deep-blue empty sky", compiled.positive)
        self.assertIn("person", compiled.negative)
        self.assertIn("bow", compiled.negative)
        self.assertIn("duplicate moon", compiled.negative)

    def test_japanese_sun_moon_landscape_ignores_false_person_segmentation(self):
        prompt = (
            "Primary subject: landscape-only exactly one golden sun disk and exactly one "
            "silver moon disk permanently separated with no people. "
            "Visible action: Wide empty sky with rocky foreground and no person."
        )

        self.assertTrue(_should_ignore_object_person_segmentation(prompt))

    def test_japanese_two_face_only_crop_uses_two_faces_when_body_detector_misses_one(self):
        prompt = (
            "Extreme opposing-profile two-face-only close-up ending at both jawlines: "
            "Amaterasu faces Tsukuyomi; zero visible necks, shoulders, arms, hands, fingers."
        )

        self.assertTrue(
            _face_count_confirms_face_only_pair(
                prompt,
                expected_person_count=2,
                detected_person_count=1,
                detected_face_count=2,
            )
        )
        self.assertFalse(
            _face_count_confirms_face_only_pair(
                prompt,
                expected_person_count=2,
                detected_person_count=1,
                detected_face_count=1,
            )
        )

    def test_japanese_myth_additional_object_locks_remove_hand_only_and_text_scenes(self):
        expected_positive_by_prefix = {
            "Tsukuyomi standing over a corpse": "exactly three objects total",
            "An abstract visual showing a pure white sky": "exactly one small golden sun disk remains far left",
            "A large, glowing red question mark": "one completely closed uninterrupted earth-tone woven shroud",
            "An endless sea of ancient": "one empty cracked unpainted wooden food bowl",
            "A gentle, golden messenger bird": "exactly one much smaller plain golden messenger disk",
            "Amaterasu handing a glowing golden scroll": "one small irregular folded pale undyed plant-fiber command cloth",
            "A god rushing anxiously": "exactly one small plain golden messenger disk descends",
            "Dark red blood pooling": "one dull aged-bronze straight blade",
            "A dead body on the ground": "exactly three small green grain shoots",
            "Powerful, majestic wild horses": "exactly two separate rectangular unglazed-clay relief tokens",
            "Bright, golden stalks of millet": "exactly three separate golden millet stalks",
            "Thick, perfectly healthy silkworms": "exactly three silkworms",
            "Lush, vibrant green rice stalks": "exactly one sparse branching barnyard-millet tuft",
            "A beautiful, natural cascade": "exactly three separate crop groups",
            "A delicate, beautiful flower": "one rice-like blade cluster",
            "A baby's hand reaching": "exactly one mature golden rice stalk",
            "An elegant, old leather-bound book": "exactly two separate crop-origin evidence clusters",
            "Amaterasu holding a single": "exactly three separated small seed groups",
            "A split image showing green spring": "green spring seedlings at far left gradually mature",
            "A beautiful ancient Japanese clock": "present-day Niiname-sai new-crop offering",
            "A dignified figure bowing deeply": "one shallow bowl of polished new rice",
            "An ancient scroll depicting a sun goddess": "exactly three separate objects lie in one row",
            "A rugged, ancient farmer": "one asymmetrical tapering white root descends",
            "A large, glowing red exclamation mark": "exactly seven separate food-crop shoots",
            "A completely blindfolded silver statue": "exactly one central knot",
            "A glowing golden thread connecting": "exactly one intact living green rice plant",
            "Two highly detailed hands": "one low unpainted wooden bowl filled with plain cooked white rice",
            "Divine hands gently offering": "exactly three separate small cream-white silkworms",
            "Amaterasu gripping a massive": "one dense tied bundle of plain reed arrows",
            "The cute fox spirit pointing": "exactly three fully sealed blank earth-tone source bundles",
        }

        for scene_prefix in _JAPANESE_MYTH_ADDITIONAL_OBJECT_SCENE_LOCKS:
            with self.subTest(scene=scene_prefix):
                image_prompt = (
                    "Year/period: Japanese mythic creation era; "
                    "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
                    "Exact place: primordial natural landscape of mythic Japan; "
                    f"Scene: {scene_prefix}."
                )
                compiled = compile_image_prompt(
                    prepare_scene_contract_source(
                        image_prompt,
                        narration_context="神話 の 出来事 を 語ります。",
                    ),
                    model_id="comfyui-flux2-klein-4b",
                )
                expected = next(
                    value
                    for prefix, value in expected_positive_by_prefix.items()
                    if scene_prefix.startswith(prefix)
                )

                expected_kind = (
                    "landscape"
                    if scene_prefix.startswith(
                        (
                            "An abstract visual showing",
                            "A split image showing green spring",
                        )
                    )
                    else "object"
                )
                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, None)
                self.assertIn(expected, compiled.positive)
                self.assertIn("hand", compiled.negative)
                self.assertIn("readable writing", compiled.negative)
                self.assertNotIn("question mark hovering", compiled.positive)
                self.assertNotIn("baby's hand", compiled.positive)
                self.assertNotIn("thumbs-up symbol", compiled.positive)

    def test_japanese_myth_additional_face_locks_exclude_hands_limbs_and_weapons(self):
        for scene_prefix in _JAPANESE_MYTH_ADDITIONAL_FACE_SCENE_LOCKS:
            with self.subTest(scene=scene_prefix):
                image_prompt = (
                    "Year/period: Japanese mythic creation era; "
                    "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
                    "Exact place: primordial natural landscape of mythic Japan; "
                    f"Scene: {scene_prefix}."
                )
                compiled = compile_image_prompt(
                    prepare_scene_contract_source(
                        image_prompt,
                        narration_context="神 が 強い 感情 を 見せます。",
                    ),
                    model_id="comfyui-flux2-klein-4b",
                )

                self.assertEqual(compiled.scene_kind, "single")
                self.assertEqual(compiled.person_count, 1)
                self.assertIn("face-only close-up ending at the jawline", compiled.positive)
                self.assertIn("zero visible neck, shoulders, arms, hands, fingers", compiled.positive)
                self.assertIn("composition=japanese_myth_jawline_face_only", compiled.diagnostics)
                self.assertIn("visible hand", compiled.negative)
                self.assertNotIn("pressing his hands together", compiled.positive)
                self.assertNotIn("gripping a sharp iron katana", compiled.positive)
                self.assertNotIn("raising his empty hands", compiled.positive)

    def test_japanese_heavenly_weavers_use_exact_four_hidden_limb_busts(self):
        image_prompt = (
            "Year/period: Japanese mythic creation era; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Exact place: primordial natural landscape of mythic Japan; "
            "Scene: Multiple ethereal, beautiful maidens working diligently at large wooden looms "
            "in a sunlit hall."
        )
        compiled = compile_image_prompt(
            prepare_scene_contract_source(
                image_prompt,
                narration_context="そこでは多くの天の服織女たちが日夜織物をしています。",
            ),
            model_id="comfyui-flux2-klein-4b",
        )

        self.assertEqual(compiled.scene_kind, "group")
        self.assertEqual(compiled.person_count, 4)
        self.assertIn("exactly four adult women appear in one row", compiled.positive)
        self.assertIn(
            "all arms, hands, fingers, lower torsos, legs, and feet remain fully occluded",
            compiled.positive,
        )
        self.assertIn("composition=japanese_myth_four_weavers_hidden_limbs", compiled.diagnostics)
        self.assertIn("visible hand", compiled.negative)
        self.assertIn("fifth person", compiled.negative)
        self.assertNotIn("two attached arms and two grounded legs", compiled.positive)

    def test_japanese_takamagahara_group_fear_uses_four_faces_without_limbs(self):
        image_prompt = (
            "Year/period: Japanese mythic creation era; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Exact place: Takamagahara divine realm in Japanese creation myth; "
            "Scene: Multiple ethereal maidens dropping their weaving shuttles, covering their ears "
            "in sheer panic."
        )
        compiled = compile_image_prompt(
            prepare_scene_contract_source(
                image_prompt,
                narration_context="高天原にいる神々は、何事かと恐怖に震え上がります。",
            ),
            model_id="comfyui-flux2-klein-4b",
        )

        self.assertEqual(compiled.scene_kind, "group")
        self.assertEqual(compiled.person_count, 4)
        self.assertIn("exactly four separated complete adult faces", compiled.positive)
        self.assertIn("zero visible necks, shoulders, arms, hands, fingers", compiled.positive)
        self.assertIn("composition=japanese_myth_four_fear_faces_only", compiled.diagnostics)
        self.assertIn("visible hand", compiled.negative)
        self.assertIn("fifth face", compiled.negative)
        self.assertNotIn("covering their ears", compiled.positive)
        self.assertNotIn("two attached arms and two grounded legs", compiled.positive)

    def test_present_day_comment_team_uses_four_faces_and_one_blank_tablet(self):
        image_prompt = (
            "Year/period: Japanese mythic creation era; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Exact place: primordial natural landscape of mythic Japan; "
            "Scene: A group of diverse, happy creators reading off a glowing tablet together in a "
            "cozy studio."
        )
        compiled = compile_image_prompt(
            prepare_scene_contract_source(
                image_prompt,
                narration_context="チーム一同、楽しくコメントを読ませて頂いております。",
            ),
            model_id="comfyui-flux2-klein-4b",
        )

        self.assertEqual(compiled.scene_kind, "group")
        self.assertEqual(compiled.person_count, 4)
        self.assertIn("exactly four separated complete adult faces", compiled.positive)
        self.assertIn("exactly one central modern tablet", compiled.positive)
        self.assertIn("zero visible necks, shoulders, arms, hands, fingers", compiled.positive)
        self.assertIn(
            "composition=present_day_four_comment_readers_hidden_limbs",
            compiled.diagnostics,
        )
        self.assertIn("visible hand", compiled.negative)
        self.assertIn("readable writing", compiled.negative)
        self.assertNotIn("two attached arms and two grounded legs", compiled.positive)

    def test_japanese_uke_mochi_death_recap_is_non_graphic_object_evidence(self):
        image_prompt = (
            "Year/period: Japanese mythic creation era; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Main subject: exactly one adult female Uke Mochi; "
            "Scene: A heavy, bloody iron blade cleanly slicing through an elegant, peaceful dinner setting. "
            "Macro action photography, 100mm lens, definitive and brutal cruelty."
        )
        source = prepare_scene_contract_source(
            image_prompt,
            narration_context="食べ物 を 司る 女神、 ウケモチ が 残酷 に 殺される という 悲劇 です。",
        )

        compiled = compile_image_prompt(source, model_id="comfyui-flux2-klein-4b")

        self.assertEqual(compiled.scene_kind, "object")
        self.assertIn("aged-bronze straight blade", compiled.positive)
        self.assertIn("torn earth-tone woven sash", compiled.positive)
        self.assertIn("blood", compiled.negative)
        self.assertIn("tiled roof", compiled.negative)
        self.assertIn("hand", compiled.negative)

    def test_japanese_amaterasu_scolding_is_hand_free_two_shot(self):
        image_prompt = (
            "Year/period: Japanese mythic creation era; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Main subject: exactly one adult female Amaterasu; "
            "Scene: Amaterasu pointing a harsh, judging finger directly at the silver moon god. "
            "Cinematic action photography, absolute condemnation."
        )
        source = prepare_scene_contract_source(
            image_prompt,
            narration_context="これ を 知った 太陽 の 女神 アマテラス は、 弟 を 激しく 叱りつけ ます。",
        )

        compiled = compile_image_prompt(source, model_id="comfyui-flux2-klein-4b")

        self.assertEqual(compiled.scene_kind, "pair")
        self.assertEqual(compiled.person_count, 2)
        self.assertIn("Amaterasu at left angrily scolds Tsukuyomi", compiled.positive)
        self.assertIn("zero visible necks, shoulders, arms, hands, fingers", compiled.positive)
        self.assertIn("composition=japanese_myth_two_jawline_faces_only", compiled.diagnostics)
        self.assertIn("pointing gesture", compiled.negative)

    def test_japanese_tsukuyomi_banishment_is_hand_free_separation(self):
        image_prompt = (
            "Year/period: Japanese mythic creation era; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Main subject: exactly two adult Japanese deities: Amaterasu and Tsukuyomi; "
            "Scene: A lonely silver god walking away into an endless, dark, starry void. "
            "Minimalist landscape photography, eerie silence, banishment."
        )
        source = prepare_scene_contract_source(
            image_prompt,
            narration_context="怒った アマテラス は、 ツクヨミ を 天上 界 の 中心 から 追放 します。",
        )

        compiled = compile_image_prompt(source, model_id="comfyui-flux2-klein-4b")

        self.assertEqual(compiled.scene_kind, "pair")
        self.assertEqual(compiled.person_count, 2)
        self.assertIn("Amaterasu's strict left-facing profile", compiled.positive)
        self.assertIn("Tsukuyomi's strict right-facing profile", compiled.positive)
        self.assertIn("zero visible necks, shoulders, arms, hands, fingers", compiled.positive)
        self.assertIn("composition=japanese_myth_outward_banishment_faces_only", compiled.diagnostics)
        self.assertIn("giant sunburst crown", compiled.negative)
        self.assertIn("faces looking at each other", compiled.negative)

    def test_japanese_uke_mochi_motionless_cut_excludes_all_limbs(self):
        image_prompt = (
            "Year/period: Japanese mythic creation era; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Main subject: exactly one adult female Uke Mochi; "
            "Scene: A faint, ghostly silhouette of the food goddess lying motionless in a dark forest. "
            "Surreal fantasy photography, deep moody shadows."
        )
        source = prepare_scene_contract_source(
            image_prompt,
            narration_context="殺されて しまった 食べ物 の 女神、 ウケモチ の 安否 です。",
        )

        compiled = compile_image_prompt(source, model_id="comfyui-flux2-klein-4b")

        self.assertEqual(compiled.scene_kind, "single")
        self.assertEqual(compiled.person_count, 1)
        self.assertIn("frame ending at the jawline", compiled.positive)
        self.assertIn("legs, feet and toes", compiled.positive)
        self.assertIn("detached foot", compiled.negative)
        self.assertIn("black outer frame", compiled.negative)


if __name__ == "__main__":
    unittest.main()
