import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.image import prompt_builder  # noqa: E402
from app.services.llm.visual_policy import normalize_cut_image_prompt  # noqa: E402
from app.services.image.asset_guard import (  # noqa: E402
    image_matches_prompt,
    prompt_hash,
    write_prompt_sidecar,
)
from app.services.image.comfyui_service import (  # noqa: E402
    _append_common_carried_transport_final_suffix,
    _append_local_v1_final_composition_suffix,
    _compact_flux2_klein_4b_prompt,
    _enforce_comfyui_common_positive_prompt,
    _enrich_local_v1_positive_prompt,
    _enforce_local_armed_figure_loadout_prompt,
    _enforce_local_single_closeup_head_prompt,
    _flux2_klein_md_negative_contract,
    _flux2_klein_md_positive_contract,
    _flux2_klein_is_japanese_courier_exchange_context,
    _flux2_klein_is_japanese_messenger_group_context,
    _flux2_klein_is_japanese_mounted_courier_context,
    _flux2_klein_japanese_courier_exchange_retry_sentence,
    _flux2_klein_japanese_human_textless_retry_sentence,
    _flux2_klein_japanese_messenger_group_retry_sentence,
    _flux2_klein_japanese_mounted_courier_retry_sentence,
    _flux2_klein_japanese_sign_free_composition_sentence,
    _flux2_klein_japanese_sword_packet_human_retry_sentence,
    _flux2_klein_japanese_sword_order_ground_risk,
    _flux2_klein_positive_contract_cleanup,
    _flux2_klein_prepare_source_prompt_text,
    _image_has_corner_artist_mark,
    _image_has_internal_text_like_marks,
    _image_has_solid_dark_outer_frame,
    _image_has_inset_dark_rectangular_frame,
    _image_has_lower_right_signature_mark,
    _image_has_solid_light_outer_margin,
    _image_has_top_caption_like_text,
    _local_prompt_is_object_only,
    _local_scene_requests_group,
    _local_scene_requests_single_character,
    _promote_ep13_final_scene_overrides,
    _should_check_internal_text_after_generation,
    _should_check_inset_frame_after_generation,
    _should_use_japanese_document_table_retry,
    _strip_local_v1_positive_only_prompt,
    apply_longtube_local_v1_master_prompt,
)


class ImagePromptGuardTests(unittest.TestCase):
    def test_prompt_hash_uses_full_prompt_not_first_guard_segment(self):
        first = (
            "HARD HISTORICAL MATERIAL CULTURE LOCK - FIRST RENDERING RULE. || "
            "Scene: a man looking ambitiously over a fertile valley"
        )
        second = (
            "HARD HISTORICAL MATERIAL CULTURE LOCK - FIRST RENDERING RULE. || "
            "Scene: poor refugees setting up a small ancient camp"
        )

        self.assertNotEqual(prompt_hash(first), prompt_hash(second))

    def test_sidecar_final_prompt_mismatch_forces_regeneration(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "cut_1.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
            write_prompt_sidecar(
                image_path,
                cut_number=1,
                image_model="test-model",
                source_prompt="same source prompt",
                final_prompt="old final prompt",
            )

            matches, reason = image_matches_prompt(
                image_path,
                source_prompt="same source prompt",
                final_prompt="new final prompt",
                image_model="test-model",
            )

        self.assertFalse(matches)
        self.assertEqual(reason, "sidecar_final_prompt_mismatch")

    def test_sidecar_records_actual_comfyui_positive_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "cut_1.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
            write_prompt_sidecar(
                image_path,
                cut_number=1,
                image_model="test-model",
                source_prompt="source prompt",
                final_prompt="pre-service final prompt",
                comfyui_positive_prompt="actual comfyui positive prompt",
            )
            sidecar = image_path.with_suffix(image_path.suffix + ".prompt.json").read_text(encoding="utf-8")

        self.assertIn(prompt_hash("actual comfyui positive prompt"), sidecar)
        self.assertIn("pre-service final prompt", sidecar)

    def test_solid_light_outer_margin_detector_catches_white_strips(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.png"
            good = Path(tmp) / "good.png"
            bad_img = Image.new("RGB", (64, 36), (30, 35, 32))
            for y in range(3):
                for x in range(64):
                    bad_img.putpixel((x, y), (255, 255, 255))
            bad_img.save(bad)
            good_img = Image.new("RGB", (64, 36), (30, 35, 32))
            good_img.save(good)

            self.assertTrue(_image_has_solid_light_outer_margin(bad))
            self.assertFalse(_image_has_solid_light_outer_margin(good))

    def test_solid_dark_outer_frame_detector_catches_full_black_frame(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad_black_frame.png"
            bad_near_black = Path(tmp) / "bad_near_black_frame.png"
            bad_drawn_frame = Path(tmp) / "bad_drawn_black_frame.png"
            bad_thin_frame = Path(tmp) / "bad_thin_black_frame.png"
            good = Path(tmp) / "good_dark_vignette.png"

            bad_img = Image.new("RGB", (128, 72), (60, 62, 58))
            for x in range(128):
                for y in range(4):
                    bad_img.putpixel((x, y), (0, 0, 0))
                    bad_img.putpixel((x, 71 - y), (0, 0, 0))
            for y in range(72):
                for x in range(4):
                    bad_img.putpixel((x, y), (0, 0, 0))
                    bad_img.putpixel((127 - x, y), (0, 0, 0))
            bad_img.save(bad)

            near_black_img = Image.new("RGB", (128, 72), (60, 62, 58))
            for x in range(128):
                for y in range(4):
                    near_black_img.putpixel((x, y), (16, 16, 16))
                    near_black_img.putpixel((x, 71 - y), (16, 16, 16))
            for y in range(72):
                for x in range(4):
                    near_black_img.putpixel((x, y), (16, 16, 16))
                    near_black_img.putpixel((127 - x, y), (16, 16, 16))
            near_black_img.save(bad_near_black)

            drawn_frame_img = Image.new("RGB", (128, 72), (132, 132, 124))
            for x in range(128):
                for y in range(6):
                    color = (0, 0, 0) if x % 4 else (60, 60, 60)
                    drawn_frame_img.putpixel((x, y), color)
                    drawn_frame_img.putpixel((x, 71 - y), color)
            for y in range(72):
                for x in range(6):
                    drawn_frame_img.putpixel((x, y), (0, 0, 0))
                    drawn_frame_img.putpixel((127 - x, y), (0, 0, 0))
            drawn_frame_img.save(bad_drawn_frame)

            thin_frame_img = Image.new("RGB", (128, 72), (132, 132, 124))
            for x in range(128):
                thin_frame_img.putpixel((x, 0), (0, 0, 0))
                thin_frame_img.putpixel((x, 71), (0, 0, 0))
            for y in range(72):
                thin_frame_img.putpixel((0, y), (0, 0, 0))
                thin_frame_img.putpixel((127, y), (0, 0, 0))
            thin_frame_img.save(bad_thin_frame)

            good_img = Image.new("RGB", (128, 72), (35, 35, 33))
            for x in range(128):
                for y in range(4):
                    good_img.putpixel((x, y), (0, 0, 0))
            good_img.save(good)

            self.assertTrue(_image_has_solid_dark_outer_frame(bad))
            self.assertTrue(_image_has_solid_dark_outer_frame(bad_near_black))
            self.assertTrue(_image_has_solid_dark_outer_frame(bad_drawn_frame))
            self.assertTrue(_image_has_solid_dark_outer_frame(bad_thin_frame))
            self.assertFalse(_image_has_solid_dark_outer_frame(good))

    def test_top_caption_detector_catches_white_text_on_dark_sky(self):
        from PIL import Image, ImageDraw, ImageFont

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad_top_caption.png"
            bad_black = Path(tmp) / "bad_black_top_caption.png"
            good_sky = Path(tmp) / "good_bright_sky.png"
            good_dark = Path(tmp) / "good_dark_smoke.png"

            bad_img = Image.new("RGB", (1280, 720), (34, 35, 35))
            draw = ImageDraw.Draw(bad_img)
            draw.rectangle((0, 145, 1279, 719), fill=(88, 76, 64))
            for i in range(14):
                x = 360 + i * 35
                draw.rectangle((x, 28, x + 15, 82), fill=(235, 235, 230))
                draw.rectangle((x, 28, x + 28, 38), fill=(235, 235, 230))
                draw.rectangle((x, 55, x + 25, 64), fill=(235, 235, 230))
            bad_img.save(bad)

            black_text_img = Image.new("RGB", (1280, 720), (235, 236, 226))
            black_draw = ImageDraw.Draw(black_text_img)
            black_draw.rectangle((0, 145, 1279, 719), fill=(120, 118, 106))
            try:
                font = ImageFont.truetype("arial.ttf", 60)
            except Exception:
                font = ImageFont.load_default()
            black_draw.text((355, 25), "S.A'TIEN  RRACTHRA:", font=font, fill=(18, 18, 18))
            black_text_img.save(bad_black)

            Image.new("RGB", (1280, 720), (242, 244, 238)).save(good_sky)
            Image.new("RGB", (1280, 720), (34, 35, 35)).save(good_dark)

            self.assertTrue(_image_has_top_caption_like_text(bad))
            self.assertTrue(_image_has_top_caption_like_text(bad_black))
            self.assertFalse(_image_has_top_caption_like_text(good_sky))
            self.assertFalse(_image_has_top_caption_like_text(good_dark))

    def test_top_caption_detector_ignores_sparse_sky_cloud_linework(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good_sparse_cloud_linework.png"
            img = Image.new("RGB", (1280, 720), (235, 236, 226))
            x_start = int(1280 * 0.15) + 250
            for y in range(10, 82):
                for j in range(46):
                    x = x_start + j * 10 + (y % 4)
                    img.putpixel((x, y), (32, 32, 32))
            img.save(good)

            self.assertFalse(_image_has_top_caption_like_text(good))

    def test_top_caption_detector_ignores_reed_texture_in_top_corner(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good_reed_top_corner.png"
            img = Image.new("RGB", (1280, 720), (230, 232, 226))
            draw = ImageDraw.Draw(img)
            for x in range(900, 1270, 18):
                draw.line((x, 8, x - 80, 136), fill=(28, 29, 28), width=2)
                draw.line((x - 12, 18, x - 92, 142), fill=(54, 55, 54), width=1)
            for y in range(18, 138, 8):
                draw.arc((915, y - 30, 1260, y + 55), 180, 350, fill=(48, 49, 48), width=1)
            img.save(good)

            self.assertFalse(_image_has_top_caption_like_text(good))

    def test_internal_text_detector_catches_white_letters_on_fortress_wall(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad_wall_letters.png"
            good = Path(tmp) / "good_blank_wall.png"

            bad_img = Image.new("RGB", (1280, 720), (112, 115, 112))
            draw = ImageDraw.Draw(bad_img)
            draw.rectangle((0, 0, 1279, 719), fill=(118, 121, 118))
            for y in range(230, 520, 58):
                draw.line((0, y, 1279, y + 12), fill=(42, 43, 42), width=3)
            for x in range(0, 1280, 82):
                draw.line((x, 220, x + 28, 520), fill=(48, 49, 48), width=2)
            x = 570
            for _ in range(7):
                draw.rectangle((x, 374, x + 8, 392), fill=(238, 238, 232))
                draw.rectangle((x + 15, 374, x + 23, 392), fill=(238, 238, 232))
                draw.rectangle((x, 374, x + 23, 379), fill=(238, 238, 232))
                draw.rectangle((x, 383, x + 23, 388), fill=(238, 238, 232))
                x += 28
            bad_img.save(bad)

            good_img = Image.new("RGB", (1280, 720), (118, 121, 118))
            good_draw = ImageDraw.Draw(good_img)
            for y in range(230, 520, 58):
                good_draw.line((0, y, 1279, y + 12), fill=(42, 43, 42), width=3)
            for x in range(0, 1280, 82):
                good_draw.line((x, 220, x + 28, 520), fill=(48, 49, 48), width=2)
            good_img.save(good)

            self.assertTrue(_image_has_internal_text_like_marks(bad))
            self.assertFalse(_image_has_internal_text_like_marks(good))

    def test_internal_text_detector_ignores_blank_packet_highlights(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good_blank_packet_highlights.png"
            img = Image.new("RGB", (1280, 720), (96, 78, 56))
            draw = ImageDraw.Draw(img)
            draw.rectangle((70, 420, 1110, 660), fill=(103, 82, 58))
            draw.rectangle((90, 430, 420, 650), fill=(244, 239, 204), outline=(20, 20, 18), width=5)
            draw.rectangle((500, 420, 860, 650), fill=(244, 239, 204), outline=(20, 20, 18), width=5)
            for x, y in ((105, 478), (118, 482), (132, 488), (168, 490), (210, 486)):
                draw.arc((x, y, x + 18, y + 12), 180, 340, fill=(252, 249, 220), width=2)
            img.save(good)

            self.assertFalse(_image_has_internal_text_like_marks(good))

    def test_internal_text_check_includes_645_ansi_fortress_battlefield(self):
        prompt = (
            "Time range: 645year; Place scope: Ansi Fortress; "
            "Main subject: hellish landscape of endless fire; "
            "Scene: A hellish landscape of endless fire, clashing armies, and storm clouds"
        )
        closeup = (
            "Time range: 645year; Place scope: Ansi Fortress; "
            "Main subject: close-up wounded soldier face; "
            "Scene: close-up wounded soldier face before a fortress wall"
        )
        siege_texture = (
            "Time range: 645year; Place scope: Ansi Fortress; "
            "Main subject: Giant; "
            "Scene: Giant, terrifying mechanical siege weapons moving toward the wall"
        )
        siege_ladder = (
            "Time range: 645year; Place scope: Ansi Fortress; "
            "Main subject: monstrously tall folding ladder reaching the top of the fortress; "
            "Scene: A monstrously tall folding ladder reaching the top of the fortress"
        )

        self.assertTrue(_should_check_internal_text_after_generation(prompt))
        self.assertFalse(_should_check_internal_text_after_generation(closeup))
        self.assertFalse(_should_check_internal_text_after_generation(siege_texture))
        self.assertFalse(_should_check_internal_text_after_generation(siege_ladder))

    def test_inset_dark_rectangular_frame_detector_catches_inner_panel(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad_inset_frame.png"
            good = Path(tmp) / "good_material.png"

            bad_img = Image.new("RGB", (1280, 720), (80, 82, 78))
            draw = ImageDraw.Draw(bad_img)
            draw.rectangle((70, 58, 1210, 662), outline=(0, 0, 0), width=5)
            bad_img.save(bad)

            good_img = Image.new("RGB", (1280, 720), (80, 82, 78))
            good_draw = ImageDraw.Draw(good_img)
            for x in range(0, 1280, 80):
                good_draw.line((x, 0, x + 120, 720), fill=(18, 18, 18), width=2)
            good_img.save(good)

            self.assertTrue(_image_has_inset_dark_rectangular_frame(bad))
            self.assertFalse(_image_has_inset_dark_rectangular_frame(good))

    def test_inset_frame_detector_catches_u_shaped_stone_window(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad_stone_window.png"
            good = Path(tmp) / "good_rubble_field.png"

            bad_img = Image.new("RGB", (1280, 720), (145, 145, 138))
            draw = ImageDraw.Draw(bad_img)
            draw.rectangle((0, 0, 1280, 88), fill=(38, 39, 37))
            draw.rectangle((0, 0, 110, 720), fill=(36, 37, 35))
            draw.rectangle((1170, 0, 1280, 720), fill=(36, 37, 35))
            for x in range(0, 1280, 86):
                draw.line((x, 0, x + 55, 88), fill=(5, 5, 5), width=3)
            for y in range(0, 720, 90):
                draw.line((0, y, 110, y + 35), fill=(5, 5, 5), width=3)
                draw.line((1170, y + 20, 1280, y), fill=(5, 5, 5), width=3)
            bad_img.save(bad)

            good_img = Image.new("RGB", (1280, 720), (104, 105, 100))
            good_draw = ImageDraw.Draw(good_img)
            for x in range(0, 1280, 95):
                good_draw.rectangle((x, 40 + (x % 130), x + 58, 92 + (x % 130)), fill=(72, 73, 70))
                good_draw.line((x, 40 + (x % 130), x + 58, 92 + (x % 130)), fill=(18, 18, 18), width=2)
            good_img.save(good)

            self.assertTrue(_image_has_inset_dark_rectangular_frame(bad))
            self.assertFalse(_image_has_inset_dark_rectangular_frame(good))

    def test_inset_frame_generation_check_ignores_generic_fortress_context(self):
        generic_context = (
            "early seventh-century; northeastern frontier fortress area; Goguryeo-Sui military world. "
            "Scene subject: Sui infantry waiting in reeds."
        )
        stone_subject = (
            "early seventh-century; northeastern frontier fortress area; Goguryeo-Sui military world. "
            "Scene subject: cropped granite defense-block field under siege pressure."
        )

        self.assertFalse(_should_check_inset_frame_after_generation(generic_context))
        self.assertTrue(_should_check_inset_frame_after_generation(stone_subject))

    def test_lower_right_signature_detector_catches_small_corner_glyph(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad_signature.png"
            good_blank = Path(tmp) / "good_blank.png"
            good_texture = Path(tmp) / "good_texture.png"

            bad_img = Image.new("RGB", (1280, 720), (3, 3, 2))
            draw = ImageDraw.Draw(bad_img)
            draw.line([(1210, 690), (1224, 658), (1238, 696)], fill=(95, 95, 92), width=2)
            draw.line([(1214, 676), (1232, 676)], fill=(92, 92, 90), width=2)
            bad_img.save(bad)

            Image.new("RGB", (1280, 720), (3, 3, 2)).save(good_blank)

            texture = Image.new("RGB", (1280, 720), (3, 3, 2))
            tex_draw = ImageDraw.Draw(texture)
            tex_draw.rectangle((1126, 561, 1279, 719), fill=(82, 82, 78))
            texture.save(good_texture)

            self.assertTrue(_image_has_lower_right_signature_mark(bad))
            self.assertFalse(_image_has_lower_right_signature_mark(good_blank))
            self.assertFalse(_image_has_lower_right_signature_mark(good_texture))

    def test_lower_right_signature_detector_catches_dark_corner_calligraphy(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad_dark_signature.png"
            good = Path(tmp) / "good_rocks.png"

            bad_img = Image.new("RGB", (1280, 720), (188, 188, 180))
            draw = ImageDraw.Draw(bad_img)
            draw.line([(1236, 672), (1244, 705)], fill=(18, 18, 17), width=3)
            draw.line([(1248, 676), (1262, 702)], fill=(18, 18, 17), width=3)
            draw.line([(1228, 694), (1264, 694)], fill=(18, 18, 17), width=2)
            bad_img.save(bad)

            good_img = Image.new("RGB", (1280, 720), (188, 188, 180))
            good_draw = ImageDraw.Draw(good_img)
            good_draw.rectangle((1220, 662, 1279, 719), fill=(92, 92, 88))
            good_img.save(good)

            self.assertTrue(_image_has_lower_right_signature_mark(bad))
            self.assertFalse(_image_has_lower_right_signature_mark(good))

    def test_lower_right_signature_detector_ignores_short_stone_crack(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good_short_stone_crack.png"
            img = Image.new("RGB", (1280, 720), (126, 126, 118))
            draw = ImageDraw.Draw(img)
            draw.rectangle((1188, 640, 1279, 719), fill=(70, 70, 66))
            draw.line([(1210, 646), (1242, 651)], fill=(18, 18, 17), width=2)
            draw.line([(1235, 642), (1265, 647)], fill=(22, 22, 20), width=2)
            img.save(good)

            self.assertFalse(_image_has_lower_right_signature_mark(good))

    def test_corner_artist_mark_detector_catches_upper_left_calligraphy(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad_upper_left_signature.png"
            good = Path(tmp) / "good_open_sky.png"

            bad_img = Image.new("RGB", (1280, 720), (112, 114, 110))
            draw = ImageDraw.Draw(bad_img)
            draw.rectangle((0, 0, 70, 144), fill=(178, 181, 174))
            draw.rectangle((0, 145, 1279, 719), fill=(92, 88, 78))
            for i in range(4):
                x = 16 + i * 11
                draw.line((x, 20, x + 8, 128), fill=(12, 12, 12), width=3)
                draw.line((x + 10, 42, x, 58), fill=(12, 12, 12), width=2)
            draw.rectangle((18, 82, 34, 96), outline=(120, 42, 38), width=3)
            bad_img.save(bad)

            good_img = Image.new("RGB", (1280, 720), (232, 234, 228))
            good_draw = ImageDraw.Draw(good_img)
            good_draw.line((0, 130, 120, 142), fill=(25, 25, 24), width=3)
            good_img.save(good)

            self.assertTrue(_image_has_corner_artist_mark(bad))
            self.assertFalse(_image_has_corner_artist_mark(good))

    def test_corner_artist_mark_detector_ignores_sparse_cloud_contour(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            cloud = Path(tmp) / "good_sparse_cloud_contour.png"

            img = Image.new("RGB", (1280, 720), (112, 114, 110))
            draw = ImageDraw.Draw(img)
            draw.rectangle((0, 0, 178, 64), fill=(232, 234, 228))
            draw.arc((-18, 76, 120, 168), start=190, end=350, fill=(20, 20, 19), width=3)
            draw.line((0, 130, 99, 143), fill=(20, 20, 19), width=3)
            img.save(cloud)

            self.assertFalse(_image_has_corner_artist_mark(cloud))

    def test_corner_artist_mark_detector_ignores_red_horizon_smoke(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            horizon = Path(tmp) / "good_red_horizon_smoke.png"

            img = Image.new("RGB", (1280, 720), (96, 30, 28))
            draw = ImageDraw.Draw(img)
            draw.rectangle((0, 0, 1279, 160), fill=(116, 38, 36))
            draw.ellipse((-40, -60, 210, 180), fill=(18, 18, 18))
            draw.ellipse((1080, -40, 1340, 180), fill=(24, 22, 22))
            draw.line((1100, 95, 1170, 76), fill=(150, 55, 48), width=8)
            draw.rectangle((0, 560, 1279, 719), fill=(22, 16, 15))
            img.save(horizon)

            self.assertFalse(_image_has_corner_artist_mark(horizon))

    def test_corner_artist_mark_detector_catches_large_bottom_left_white_letters(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad_bottom_left_letters.png"

            img = Image.new("RGB", (1280, 720), (42, 38, 34))
            draw = ImageDraw.Draw(img)
            draw.rectangle((0, 604, 230, 719), fill=(18, 18, 18))
            x = 0
            for _ in range(5):
                draw.rectangle((x, 642, x + 6, 694), fill=(238, 238, 232))
                draw.rectangle((x + 20, 642, x + 26, 694), fill=(238, 238, 232))
                draw.rectangle((x, 642, x + 26, 648), fill=(238, 238, 232))
                draw.rectangle((x, 668, x + 26, 674), fill=(238, 238, 232))
                x += 30
            img.save(bad)

            self.assertTrue(_image_has_corner_artist_mark(bad))

    def test_historical_guard_is_prompt_prefix_with_quality_lock(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: frontier fighters in a tense courtyard; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertTrue(prompt.startswith("HARD HISTORICAL MATERIAL CULTURE LOCK"))
        self.assertIn("FIRST RENDERING RULE", prompt)
        self.assertIn("IMAGE QUALITY LOCK", prompt)
        self.assertIn("1080p-ready story frame", prompt)

    def test_generic_image_safety_locks_are_not_channel_specific(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 525 BC; Exact place: Pelusium, Nile Delta, Egypt; "
                "Scene: Persian soldiers advance while Egyptian defenders recoil beside sacred cats; "
                "Style: serious documentary illustration"
            ),
            "",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)

        self.assertIn("HARD HISTORICAL MATERIAL CULTURE LOCK", prompt)
        self.assertIn("ADULT GRAPHIC NOVEL STYLE LOCK", prompt)
        self.assertIn("COMMON-SENSE ANATOMY LOCK", prompt)
        self.assertIn("ROLE EQUIPMENT COMMON-SENSE LOCK", prompt)
        self.assertIn("DYNAMIC ACTION AND EMOTION LOCK", prompt)
        self.assertIn("extra fingers", negative)
        self.assertIn("animal with extra legs", negative)
        self.assertNotIn("channel", prompt.lower())

    def test_visual_qa_readiness_and_character_entrance_locks_are_common(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Global visual world: Time range: 612 AD; Place scope: Liaodong Fortress, Liaodong; "
                "Culture scope: Goguryeo and neighboring ancient Northeast Asian military world; "
                "Year/period: 612 AD; Exact place: Liaodong Fortress command wall; "
                "Main subject: Eulji Mundeok; "
                "Scene: Eulji Mundeok raises one hand before commanders, calm eyes cutting through siege dust"
            ),
            "",
            enable_historical_guard=True,
        )

        self.assertIn("VISUAL QA READINESS LOCK", prompt)
        self.assertIn("exactly one thumb and four fingers", prompt)
        self.assertIn("Animals keep a normal species body plan", prompt)
        self.assertIn("CHARACTER ENTRANCE GRANDEUR LOCK", prompt)
        self.assertIn("face, eyes, shoulders, silhouette, and emotional pressure", prompt)
        self.assertIn("PERIOD WEAPON AND PROP AUDIT LOCK", prompt)
        self.assertIn("Do not borrow later, foreign, fantasy, or modern gear", prompt)

    def test_visual_qa_negative_blocks_workbench_failure_types(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 375 AD; Exact place: Brigetio command camp; "
                "Culture scope: Late Roman imperial command world; "
                "Main subject: Valentinian I; "
                "Scene: Valentinian I grips a command table while horses wait outside the command tent"
            ),
            "",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)

        self.assertIn("workbench QA failure", negative)
        self.assertIn("six fingers", negative)
        self.assertIn("hand fused to weapon", negative)
        self.assertIn("extra animal legs", negative)
        self.assertIn("animal-human hybrid", negative)
        self.assertIn("wrong-period weapon", negative)
        self.assertIn("fantasy armor", negative)
        self.assertIn("modern tactical gear", negative)

    def test_global_style_uses_thick_ink_and_historical_accuracy_priority(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: Goguryeo cavalry waits outside a timber palisade; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)

        self.assertIn("extra-thick black outer contours", prompt)
        self.assertIn("Historical material accuracy outranks style", prompt)
        self.assertIn("Default visible hand budget is zero", prompt)
        self.assertIn("extra-thick black ink contour lines", comfy_prompt)
        self.assertIn("Historical material accuracy is higher priority than style", comfy_prompt)
        self.assertIn("default visible hand budget is zero", comfy_prompt)
        self.assertIn("hands added without scene reason", comfy_negative)

    def test_medieval_central_asian_context_gets_period_local_lock(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1218 - 1221 AD; "
                "Exact place: Otrar & Khwarazmian Empire (Central Asia); "
                "Culture scope: Mongol-Khwarazmian conflict; "
                "Scene: bustling ancient Middle Eastern market filled with silk, spices, and gold; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        negative = prompt_builder.historical_negative_prompt(prompt, enabled=True)

        self.assertIn("PERIOD-LOCAL MEDIEVAL CENTRAL ASIAN MATERIAL CULTURE LOCK", prompt)
        self.assertIn("mud-brick walls", prompt)
        self.assertIn("the requested market, bazaar, merchant street", prompt)
        self.assertNotIn("solo face close-up portrait shot", prompt)
        self.assertIn("MARKET GOODS FIRST COMPOSITION LOCK", comfy_prompt)
        self.assertIn("spice piles", comfy_prompt)
        self.assertIn("solo merchant portrait", comfy_negative)
        self.assertIn("Period-local medieval Central Asian material culture", comfy_prompt)
        self.assertIn("samurai armor", negative)
        self.assertIn("Japanese timber gate", comfy_negative)

    def test_early_ancient_chinese_context_gets_zhou_material_lock(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 771 BC; "
                "Exact place: Haojing and Mount Li, Western Zhou China; "
                "Culture scope: Western Zhou royal court and frontier warfare; "
                "Scene: Zhou guards in heavy bronze armor run toward a beacon tower with spears; "
                "Style: serious documentary illustration"
            ),
            "serious documentary illustration",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("EARLY ANCIENT CHINA MATERIAL CULTURE LOCK", prompt)
        self.assertIn("bronze-scale and rawhide protective layers", prompt)
        self.assertIn("simple bronze helmets", prompt)
        self.assertIn("EARLY ANCIENT CHINA MATERIAL CULTURE FIRST RULE", comfy_prompt)
        self.assertIn("pre-Qin Chinese material culture only", comfy_prompt)
        self.assertIn("medieval European plate armor", negative)
        self.assertIn("polished steel cuirass", comfy_negative)
        self.assertNotIn("heavy bronze armor run", prompt)

    def test_historical_symbolic_modern_objects_are_normalized(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 771 BC; "
                "Exact place: Haojing and Mount Li, Western Zhou China; "
                "Culture scope: Western Zhou royal court; "
                "Scene: hourglass slowly draining, transitioning into a modern clock beside a "
                "stylized 3D thumbs-up icon made of ancient gold and a thought bubble showing a balance scale; "
                "Style: serious documentary illustration"
            ),
            "serious documentary illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("HISTORICAL SYMBOLIC PROP LOCK", prompt)
        self.assertIn("period-appropriate sundial shadow", prompt)
        self.assertIn("bronze approval token", prompt)
        self.assertIn("symbolic vignette showing a balance scale", prompt)
        self.assertIn("modern clock", comfy_negative)
        self.assertIn("thumbs-up icon", comfy_negative)
        self.assertNotIn("transitioning into a modern clock", prompt)
        self.assertNotIn("stylized 3D thumbs-up icon", prompt)
        self.assertNotIn("thought bubble showing", prompt)
        self.assertNotIn("transitioning into a modern clock", comfy_prompt)

    def test_ashanti_british_context_gets_period_local_lock_and_wrong_culture_negative(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: massive ancient armies clashing in smoke and chaos outside Kumasi; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertIn("West African Ashanti", prompt)
        self.assertIn("armed group action named by the Scene", prompt)
        self.assertIn("PERIOD-LOCAL WEST AFRICAN ASHANTI AND GOLD COAST MATERIAL CULTURE LOCK", prompt)
        self.assertIn("wrapped cloth war dress", prompt)
        self.assertNotIn("one representative foreground armored survivor", prompt)
        self.assertNotIn("ARMED ROLE PORTRAIT CROP LOCK", prompt)
        self.assertIn("samurai armor", negative)
        self.assertIn("Japanese tiled roof", negative)
        self.assertIn("European knight armor", negative)
        self.assertIn("WEST AFRICAN ASHANTI ARMED BODY FIRST RULE", comfy_prompt)
        self.assertIn("WEST AFRICAN ASHANTI ACTIVE COMBAT COMPOSITION FIRST RULE", comfy_prompt)
        self.assertIn("not arrival, posing", comfy_prompt)
        self.assertIn("visibly clashing, charging, bracing, firing, or recoiling", comfy_prompt)
        self.assertIn("Japanese timber gate", comfy_negative)
        self.assertIn("walking soldier lineup", comfy_negative)
        self.assertIn("group under quiet porch", comfy_negative)
        self.assertIn("West African Ashanti and Gold Coast armed action illustration", local_prompt)
        self.assertIn("not a medieval European knight", local_prompt)

    def test_ashanti_city_view_uses_setting_frame_not_object_fallback(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: a breathtaking view of the Ashanti Empire capital of Kumasi under storm clouds; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, _ = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertIn("requested city, capital, settlement, kingdom, empire, or urban place", prompt)
        self.assertIn("PERIOD-LOCAL WEST AFRICAN ASHANTI AND GOLD COAST SETTING MATERIAL LOCK", prompt)
        self.assertIn("Kumasi compounds", prompt)
        self.assertNotIn("one close foreground evidence object", prompt)
        self.assertIn("WEST AFRICAN KUMASI SETTING FIRST RULE", comfy_prompt)
        self.assertIn("West African Kumasi and Ashanti Empire establishing setting", local_prompt)
        self.assertIn("not an East Asian gate", local_prompt)

    def test_ashanti_officer_scene_is_human_story_frame(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900; "
                "Exact place: Gold Coast harbor near Kumasi; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: a British colonial officer steps off a ship, scanning the humid coast; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, _ = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertIn("PERIOD-LOCAL WEST AFRICAN ASHANTI AND GOLD COAST MATERIAL CULTURE LOCK", prompt)
        self.assertIn("tropical khaki or white drill uniforms", prompt)
        self.assertIn("CHARACTER STORY FRAMING LOCK", prompt)
        self.assertNotIn("EMPTY EVIDENCE FRAME LOCK", prompt)
        self.assertIn("Period-local West African Ashanti and Gold Coast material culture", comfy_prompt)
        self.assertIn("British colonial official arrogance scene", local_prompt)
        self.assertIn("white drill or khaki tropical", local_prompt)

    def test_ashanti_arrogant_official_artifact_scene_becomes_british_colonial_official(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi (Ashanti Empire) & British Empire; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: Close up of an arrogant official pointing a finger dismissively at ancient cultural artifacts; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertIn("WEST AFRICAN BRITISH COLONIAL OFFICIAL ROLE LOCK", prompt)
        self.assertIn("British colonial administrator", prompt)
        self.assertIn("white European British colonial official", prompt)
        self.assertIn("European ancestry", prompt)
        self.assertIn("WEST AFRICAN BRITISH COLONIAL OFFICIAL FIRST RULE", comfy_prompt)
        self.assertIn("white European British administrator", comfy_prompt)
        self.assertIn("European ancestry", comfy_prompt)
        self.assertIn("British colonial official arrogance scene", local_prompt)
        self.assertIn("Asante artifacts", local_prompt)
        self.assertIn("East Asian official portrait", comfy_negative)
        self.assertIn("East Asian administrator face", comfy_negative)
        self.assertIn("no Japanese official interior", local_prompt)

    def test_ashanti_hodgson_name_routes_to_british_colonial_official(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi (Ashanti Empire) & British Empire; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: Hodgson raising his hand to speak, dark storm clouds gathering in the sky behind him; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertIn("WEST AFRICAN BRITISH COLONIAL OFFICIAL ROLE LOCK", prompt)
        self.assertIn("white European British colonial official", prompt)
        self.assertIn("WEST AFRICAN BRITISH COLONIAL OFFICIAL FIRST RULE", comfy_prompt)
        self.assertIn("white European British administrator", comfy_prompt)
        self.assertTrue(local_prompt.startswith("British colonial official arrogance scene"))
        self.assertIn("East Asian administrator face", comfy_negative)

    def test_ashanti_local_people_scene_gets_west_african_people_lock(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi (Ashanti Empire) & British Empire; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: Ashanti chiefs sitting in a grand council with serious expressions; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("dark brown to deep brown skin tones", prompt)
        self.assertIn("tightly curled or coiled black hair", prompt)
        self.assertIn("Do not add British soldiers", prompt)
        self.assertIn("WEST AFRICAN ASHANTI PEOPLE FIRST RULE", comfy_prompt)
        self.assertIn("Akan/Asante, Sub-Saharan West African", comfy_prompt)
        self.assertIn("dark brown to deep brown skinned people", comfy_prompt)
        self.assertIn("Every readable face in African chiefs", comfy_prompt)
        self.assertIn("Do not add British soldiers", comfy_prompt)
        self.assertIn("status cloth", comfy_prompt)
        self.assertIn("East Asian face", comfy_negative)
        self.assertIn("East Asian council", comfy_negative)
        self.assertIn("Central Asian turban", comfy_negative)
        self.assertIn("topknot", comfy_negative)

    def test_golden_stool_routes_to_sacred_stool_object_evidence(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: the Golden Stool resting in a shadowed Kumasi room; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertIn("sacred Asante or Ashanti stool object", prompt)
        self.assertIn("low carved wooden stool", prompt)
        self.assertIn("PERIOD-LOCAL WEST AFRICAN ASHANTI AND GOLD COAST SETTING MATERIAL LOCK", prompt)
        self.assertIn("bowl replacing Golden Stool", negative)
        self.assertIn("crown replacing Golden Stool", negative)
        self.assertNotIn("COMMON-SENSE ANATOMY LOCK", prompt)
        self.assertIn("GOLDEN STOOL OBJECT FIRST RULE", comfy_prompt)
        self.assertIn("bowl replacing Golden Stool", comfy_negative)
        self.assertIn("sacred Asante Golden Stool object evidence illustration", local_prompt)

    def test_golden_stool_with_bells_does_not_route_to_bell_object(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: An intricate close-up of the Golden Stool's golden bells and carvings; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, _ = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("GOLDEN STOOL OBJECT FIRST RULE", comfy_prompt)
        self.assertNotIn("BELL OBJECT EVIDENCE FIRST RULE", comfy_prompt)

    def test_ashanti_stool_shorthand_routes_to_golden_stool_object(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: Abstract visual of a glowing golden soul hovering above the stool; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, _ = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("GOLDEN STOOL OBJECT FIRST RULE", comfy_prompt)

    def test_ashanti_golden_stool_human_interaction_blocks_bowl(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: A shadowy British figure reaching out to grab a glowing golden stool, symbolic; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertIn("GOLDEN STOOL OBJECT FIRST RULE", comfy_prompt)
        self.assertIn("no basin", comfy_prompt)
        self.assertTrue(local_prompt.startswith("Sacred Asante Golden Stool story illustration"))
        self.assertIn("one single low rectangular solid carved ceremonial stool", local_prompt)
        self.assertIn("four short legs", local_prompt)
        self.assertIn("the only reaching human is a white European British colonial man", local_prompt)
        self.assertIn("do not render an Akan/Asante", local_prompt)
        self.assertIn("no bowl", local_prompt)
        self.assertIn("golden bowl replacing Golden Stool", comfy_negative)

    def test_ashanti_golden_stool_hovering_has_no_support_table(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: A golden stool hovering in the sky above a massive, charging African army; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, _ = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertIn("GOLDEN STOOL OBJECT FIRST RULE", comfy_prompt)
        self.assertTrue(local_prompt.startswith("Sacred Asante Golden Stool story illustration"))
        self.assertIn("floating unsupported in the sky", local_prompt)
        self.assertIn("no table, pedestal, support", local_prompt)
        self.assertIn("four short legs", local_prompt)

    def test_ashanti_african_chiefs_reaction_blocks_east_asian_people(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: The African chiefs staring in dead silence, their eyes wide with anger and disbelief; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertIn("WEST AFRICAN ASHANTI PEOPLE FIRST RULE", comfy_prompt)
        self.assertTrue(local_prompt.startswith("West African Ashanti chiefs and local people reaction scene"))
        self.assertIn("Every readable person is Black African Akan/Asante", local_prompt)
        self.assertIn("Do not render East Asian men", local_prompt)
        self.assertIn("East Asian chiefs replacing African chiefs", comfy_negative)

    def test_ashanti_yaa_asantewaa_scene_uses_black_african_woman_leader(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: Yaa Asantewaa wearing traditional royal kente cloth, radiating absolute authority; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertIn("WEST AFRICAN ASHANTI PEOPLE FIRST RULE", comfy_prompt)
        self.assertTrue(local_prompt.startswith("West African Ashanti woman leader story scene"))
        self.assertIn("adult Black African Akan/Asante woman leader", local_prompt)
        self.assertIn("Yaa Asantewaa when named", local_prompt)
        self.assertIn("East Asian woman replacing Yaa Asantewaa", comfy_negative)

    def test_ashanti_she_action_scene_does_not_fall_back_to_setting_only(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: She slammed her fist on a wooden table, dust flying up into the candlelight; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, _ = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertIn("PERIOD-LOCAL WEST AFRICAN ASHANTI AND GOLD COAST MATERIAL CULTURE LOCK", prompt)
        self.assertIn("WEST AFRICAN ASHANTI PEOPLE FIRST RULE", comfy_prompt)
        self.assertTrue(local_prompt.startswith("West African Ashanti woman leader story scene"))
        self.assertIn("slamming a fist", local_prompt)

    def test_ashanti_chiefs_grabbing_weapons_stays_human_action(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: The male chiefs standing up one by one, grabbing their weapons with renewed courage; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertNotIn("HARD HISTORICAL OBJECT EVIDENCE MATERIAL CULTURE LOCK", prompt)
        self.assertIn("PERIOD-LOCAL WEST AFRICAN ASHANTI AND GOLD COAST MATERIAL CULTURE LOCK", prompt)
        self.assertIn("WEST AFRICAN ASHANTI ARMED BODY FIRST RULE", comfy_prompt)
        self.assertIn("WEST AFRICAN ASHANTI PEOPLE FIRST RULE", comfy_prompt)
        self.assertTrue(local_prompt.startswith("West African Ashanti and Gold Coast armed action illustration"))
        self.assertIn("European knight armor", comfy_negative)

    def test_ashanti_british_jungle_detachment_stays_troop_action(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: A small group of British soldiers hacking through thick jungle vines with machetes; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertTrue(local_prompt.startswith("British colonial troop jungle action scene"))
        self.assertIn("hacking thick jungle vines with machetes", local_prompt)
        self.assertIn("Do not replace the soldiers with a floating book", local_prompt)
        self.assertIn("floating book replacing British soldiers", comfy_negative)

    def test_ashanti_british_fort_gate_stays_gate_not_east_asian_people(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: Heavy wooden gates of a stone fort slamming shut and being bolted tight; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, _ = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertTrue(local_prompt.startswith("British colonial fort gate action setting"))
        self.assertIn("heavy wooden gates of a British stone fort", local_prompt)
        self.assertIn("not East Asian men", local_prompt)

    def test_ashanti_tree_trunk_barricade_does_not_become_house_door(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: A solid wall of thick tree trunks, completely blocking a muddy path; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertTrue(local_prompt.startswith("West African Ashanti wartime tree-trunk barricade setting"))
        self.assertIn("not a house, gate, doorway", local_prompt)
        self.assertIn("door replacing tree-trunk barricade", comfy_negative)

    def test_ashanti_fort_doctor_patients_stays_colonial_medical_scene(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: A doctor looking overwhelmed, wiping sweat from his brow among groaning patients; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertIn("PERIOD-LOCAL WEST AFRICAN ASHANTI AND GOLD COAST MATERIAL CULTURE LOCK", prompt)
        self.assertTrue(local_prompt.startswith("British colonial fort medical crisis scene"))
        self.assertIn("overwhelmed late 19th to early 20th century colonial doctor", local_prompt)
        self.assertIn("East Asian doctor", comfy_negative)

    def test_ashanti_coastal_survivors_stay_on_beach(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: The survivors collapsing onto a sandy beach, the ocean waves crashing in the background; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertTrue(local_prompt.startswith("Gold Coast coastal survivor aftermath scene"))
        self.assertIn("open sandy beach", local_prompt)
        self.assertIn("no indoor room", local_prompt)
        self.assertIn("indoor room replacing beach survivor scene", comfy_negative)

    def test_ashanti_london_politician_stays_british_metropolitan_scene(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: London, British Empire; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: An angry British politician slamming a desk among scattered blank papers about Disaster in Ashanti; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertTrue(local_prompt.startswith("British metropolitan political humiliation scene"))
        self.assertIn("white European British politician", local_prompt)
        self.assertIn("Papers remain blank", local_prompt)
        self.assertNotIn("Disaster in Ashanti", local_prompt)
        self.assertIn("African chiefs replacing British politician", comfy_negative)

    def test_ashanti_british_flag_ruins_uses_union_jack_not_red_cross(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: The British flag flying high over the smoking ruins of Kumasi; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertTrue(local_prompt.startswith("British imperial flag over ruined Kumasi aftermath scene"))
        self.assertIn("Union Jack", local_prompt)
        self.assertIn("red cross flag replacing British flag", comfy_negative)

    def test_ashanti_british_officer_empty_box_keeps_box_and_officer(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: A British officer holding an empty wooden box, looking intensely frustrated; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertTrue(local_prompt.startswith("British colonial officer empty-box frustration scene"))
        self.assertIn("box interior is clearly empty", local_prompt)
        self.assertIn("woman replacing British officer", comfy_negative)

    def test_ashanti_golden_stool_stripping_does_not_become_single_bell(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: The golden bells and plates being pulled off the wooden base of the stool; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertTrue(local_prompt.startswith("Sacred Asante Golden Stool stripping aftermath detail"))
        self.assertIn("stripped wooden stool base must stay visible", local_prompt)
        self.assertIn("single hanging bell replacing stripped Golden Stool", comfy_negative)

    def test_ashanti_yaa_ghost_over_hidden_stool_keeps_yaa_and_stool(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: A ghostly image of Yaa Asantewaa smiling proudly over the hidden Golden Stool; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, _ = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertTrue(local_prompt.startswith("Sacred Asante Golden Stool guarded-by-Yaa story scene"))
        self.assertNotIn("GOLDEN STOOL OBJECT FIRST RULE", comfy_prompt)
        self.assertIn("semi-transparent spirit silhouette of Yaa", local_prompt)
        self.assertIn("mostly buried low rectangular Asante Golden Stool", local_prompt)
        self.assertIn("not a box, chest, coffer, table", local_prompt)

    def test_ashanti_hidden_stool_in_rain_does_not_become_exposed_table(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: Rain washing over the dirt hiding the stool, keeping it safe for years; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, _ = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertTrue(local_prompt.startswith("Hidden sacred Asante protection evidence scene"))
        self.assertNotIn("GOLDEN STOOL OBJECT FIRST RULE", comfy_prompt)
        self.assertIn("no people, no British officer", local_prompt)
        self.assertIn("below ground and completely concealed", local_prompt)
        self.assertIn("no full rectangular top plane", local_prompt)
        self.assertIn("no gold chest", local_prompt)
        self.assertIn("no visible gold or metal surface", local_prompt)
        self.assertIn("must not sit on top of the ground", local_prompt)
        self.assertIn("must not look like a closed box", local_prompt)

    def test_ashanti_laborers_uncovering_stool_stays_digging_action(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1921 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: African laborers accidentally digging up the glowing Golden Stool from the dirt; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, _ = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertTrue(local_prompt.startswith("African laborers uncovering the sacred Asante Golden Stool scene"))
        self.assertIn("laborers digging in jungle dirt", local_prompt)

    def test_ashanti_execution_intervention_keeps_executioner_and_workers(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: A British official stopping an Ashanti executioner, saving the terrified workers; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertTrue(local_prompt.startswith("British intervention stopping an Ashanti execution scene"))
        self.assertIn("Ashanti executioner", local_prompt)
        self.assertIn("terrified Black African workers", local_prompt)
        self.assertIn("decorative bust replacing execution scene", comfy_negative)

    def test_ashanti_prempeh_return_keeps_train_visible(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: King Prempeh stepping off a train in a modern suit, thousands of Ashanti people cheering wildly; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertTrue(local_prompt.startswith("King Prempeh train-return arrival scene"))
        self.assertIn("visible steam train carriage", local_prompt)
        self.assertIn("gate-only train arrival", comfy_negative)

    def test_ashanti_parliament_scene_stays_london_not_colonial_official(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: London, British Parliament; "
                "Culture scope: British Empire and Gold Coast aftermath; "
                "Scene: A politician angrily speaking in the British Parliament, holding up a report; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, _ = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertNotIn("WEST AFRICAN BRITISH COLONIAL OFFICIAL FIRST RULE", comfy_prompt)
        self.assertTrue(local_prompt.startswith("British metropolitan political humiliation scene"))
        self.assertIn("blank paper cover or edge-on blank sheet", local_prompt)

    def test_ashanti_symbolic_scale_keeps_two_pans_stool_and_skulls(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: A scale weighing a golden stool on one side, and a mountain of skulls on the other; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, _ = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertIn("SYMBOLIC BALANCE SCALE FIRST RULE", comfy_prompt)
        self.assertNotIn("GOLDEN STOOL OBJECT FIRST RULE", comfy_prompt)
        self.assertTrue(local_prompt.startswith("symbolic balance scale evidence illustration"))
        self.assertIn("two visible pans", local_prompt)
        self.assertIn("opposite pan holds a mound of skulls", local_prompt)

    def test_ashanti_hodgson_ghost_graves_stays_aftermath(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: The ghost of Governor Hodgson looking down in sorrow at the graves of fallen soldiers; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, _ = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertTrue(local_prompt.startswith("Governor Hodgson ghost over fallen soldiers' graves scene"))
        self.assertIn("grave markers", local_prompt)
        self.assertIn("not a solid living commander", local_prompt)

    def test_ashanti_empty_chair_scene_stays_unoccupied(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: The ordinary wooden chair sitting empty in the dust of a ruined city; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertTrue(local_prompt.startswith("Empty ordinary wooden chair in ruined city evidence scene"))
        self.assertIn("No people, no British soldiers", local_prompt)
        self.assertIn("people in empty chair scene", comfy_negative)

    def test_ashanti_burning_treaty_stays_blank_document(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: A burning wax seal on an ancient diplomatic treaty, dissolving into ash; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertIn("BLANK BURNING DOCUMENT FIRST RULE", comfy_prompt)
        self.assertTrue(local_prompt.startswith("blank sealed document evidence illustration"))
        self.assertIn("no handwriting, no cursive lines", local_prompt)
        self.assertIn("line rows on treaty", comfy_negative)

    def test_ashanti_ruined_battlefield_closing_is_empty_aftermath(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: a dark closing shot of storm clouds over a ruined battlefield, stormy sky; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertNotIn("WEST AFRICAN ASHANTI ARMED BODY FIRST RULE", comfy_prompt)
        self.assertTrue(local_prompt.startswith("Empty ruined battlefield storm-cloud closing shot"))
        self.assertIn("no people at all", local_prompt)
        self.assertIn("no living fighters", local_prompt)
        self.assertIn("person in empty ruined battlefield", comfy_negative)
        self.assertIn("active combat in closing battlefield", comfy_negative)

    def test_calendar_date_page_routes_to_object_evidence_not_person(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1900 AD; "
                "Exact place: Kumasi, Ashanti Empire, Gold Coast; "
                "Culture scope: Ashanti Empire and British colonial Gold Coast; "
                "Scene: An old calendar page turning to the year 1900, vintage aesthetic; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        local_prompt = _enrich_local_v1_positive_prompt(
            _strip_local_v1_positive_only_prompt(comfy_prompt)
        )

        self.assertIn("HARD HISTORICAL OBJECT EVIDENCE MATERIAL CULTURE LOCK", prompt)
        self.assertIn("object evidence still-life illustration", local_prompt)
        self.assertIn("no people", local_prompt)
        self.assertIn("person replacing object", comfy_negative)

    def test_medieval_central_asian_armed_scene_uses_local_military_set(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1218 - 1221 AD; "
                "Exact place: Otrar & Khwarazmian Empire (Central Asia); "
                "Culture scope: Mongol-Khwarazmian conflict; "
                "Scene: Mongol cavalry soldiers raise composite bows beside dusty horses; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enforce_local_armed_figure_loadout_prompt(prompt)

        self.assertIn("MEDIEVAL CENTRAL ASIAN ARMED ROLE VISIBLE SET LOCK", prompt)
        self.assertIn("deel-like robes", local_prompt)
        self.assertIn("composite bows", local_prompt)

    def test_medieval_central_asian_armed_scene_without_specific_weapon_keeps_local_armor_lock(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1218 - 1221 AD; "
                "Exact place: Otrar & Khwarazmian Empire (Central Asia); "
                "Culture scope: Mongol-Khwarazmian conflict; "
                "Scene: Shah Muhammad II sitting on a golden throne, surrounded by heavily armored guards; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enforce_local_armed_figure_loadout_prompt(prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("MEDIEVAL CENTRAL ASIAN ARMED ROLE VISIBLE SET LOCK", prompt)
        self.assertIn("a guarded ruler court scene", prompt)
        self.assertNotIn("one representative foreground armored survivor", prompt)
        self.assertIn("ARMED BODY VISIBLE SET LOCK - for medieval Central Asian", local_prompt)
        self.assertIn("CENTRAL ASIAN ARMOR SHAPE FIRST RULE", comfy_prompt)
        self.assertIn("GUARDED RULER GROUP FIRST RULE", comfy_prompt)
        self.assertIn("ARMED BODY VISIBLE SET LOCK - for medieval Central Asian", comfy_prompt)
        self.assertIn("small cord-tied lamellar scale rows", comfy_prompt)
        self.assertIn("smooth metal breastplate", comfy_negative)
        self.assertIn("closed visor helmet", comfy_negative)
        self.assertIn("decorative breastplate ornament", comfy_negative)
        self.assertIn("round belt medallion", comfy_negative)

    def test_medieval_central_asian_cavalry_stays_group_action(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1218 - 1221 AD; "
                "Exact place: Otrar & Khwarazmian Empire (Central Asia); "
                "Culture scope: Mongol-Khwarazmian conflict; "
                "Scene: a vast green steppe, thousands of Mongol cavalry riding together, epic scale; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, _ = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("the mounted travel moment named by the Scene", prompt)
        self.assertNotIn("one representative foreground armored survivor", prompt)
        self.assertIn("ARMED BODY VISIBLE SET LOCK - for medieval Central Asian", comfy_prompt)

    def test_fortress_attack_scene_gets_action_front_lock(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1218 - 1221 AD; "
                "Exact place: Otrar & Khwarazmian Empire (Central Asia); "
                "Culture scope: Mongol-Khwarazmian conflict; "
                "Scene: Mongol warriors attacking a towering Chinese fortress, flaming arrows in the sky; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("the fortress attack action named by the Scene", prompt)
        self.assertIn("attackers moving diagonally toward the fortress", prompt)
        self.assertNotIn("one representative foreground armored survivor", prompt)
        self.assertNotIn("ARMED FIGURE LOADOUT LOCK", prompt)
        self.assertIn("FORTRESS ATTACK ACTION FIRST RULE", comfy_prompt)
        self.assertIn("arrows in flight", comfy_prompt)
        self.assertIn("standing guard lineup", comfy_negative)

    def test_bell_object_scene_does_not_become_people_or_door_scene(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1218 - 1221 AD; "
                "Exact place: Otrar & Khwarazmian Empire (Central Asia); "
                "Scene: an ornate silver bell ringing, sending shockwaves through the air; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("the requested bell object from the Scene", prompt)
        self.assertIn("BELL OBJECT EVIDENCE FIRST RULE", comfy_prompt)
        self.assertIn("No human figure", comfy_prompt)
        self.assertIn("no door", comfy_prompt)
        self.assertIn("wall plaque above door", comfy_negative)
        self.assertIn("round door knob", comfy_negative)

    def test_landscape_location_prompt_stays_terrain_only(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: a lush green valley surrounded by steep rocky mountains; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("empty establishing landscape", prompt)
        self.assertIn("LANDSCAPE VISIBLE SET LOCK", prompt)
        self.assertIn("complete visible subject set is mountain cliffs", prompt)
        self.assertIn("Visible content is listed physical terrain", prompt)
        self.assertNotIn("survival evidence", prompt)
        self.assertNotIn("torn cloth", prompt)
        self.assertNotIn("muddy footprints", prompt)

    def test_map_scene_stays_physical_map_object(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: a dark map of ancient Korea, still mostly uncontrolled; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)

        self.assertIn("UNMARKED STRATEGIC BOARD LOCK", prompt)
        self.assertIn("low horizontal tactile marker layout", prompt)
        self.assertIn("tactile marker layout shot", prompt)
        self.assertIn("The dominant visible shapes are physical markers", prompt)
        self.assertIn("plain material margins", prompt)
        self.assertIn("physically unmarked", prompt)
        self.assertIn("low wooden table surface", prompt)
        self.assertIn("horizontal surface", prompt)
        self.assertIn("at least one loose route cord", prompt)
        self.assertIn("Unmarked low horizontal tactile marker layout illustration", local_prompt)
        self.assertIn("corner zones are empty plain material margins", local_prompt)
        self.assertIn("empty plain material margins made from broad dust", local_prompt)
        self.assertIn("all geographic meaning appears only through physical objects", local_prompt)
        self.assertIn("dominant visible shapes are one loose route cord", local_prompt)
        self.assertIn("horizontal surface", local_prompt)
        self.assertNotIn("frame rails", prompt.lower())
        self.assertNotIn("frame rails", local_prompt.lower())
        self.assertIn("empty surrounding edges", prompt)
        self.assertIn("Off-screen pressure appears only through lamp light", prompt)
        self.assertIn("unoccupied object-only tabletop", prompt)
        self.assertIn("visible subject inventory is only the low surface", prompt)
        self.assertIn("camera crop stays on the low surface", prompt)
        self.assertIn("Unoccupied tabletop or floor-surface evidence view", local_prompt)
        self.assertIn("camera crop stays on the low surface", local_prompt)
        self.assertIn("physically unmarked object-surface", local_prompt)
        self.assertIn("empty surrounding edges", local_prompt)
        self.assertIn("HARD HISTORICAL OBJECT EVIDENCE MATERIAL CULTURE LOCK", prompt)
        self.assertIn("OBJECT PHYSICAL COMMON-SENSE LOCK", prompt)
        self.assertIn("weighty still-life tension", prompt)
        self.assertIn("Lamp bases, metal rims, bronze weights", prompt)
        self.assertNotIn("COMMON-SENSE ANATOMY LOCK", prompt)
        self.assertNotIn("ROLE EQUIPMENT COMMON-SENSE LOCK", prompt)
        self.assertNotIn("DYNAMIC ACTION AND EMOTION LOCK", prompt)
        self.assertNotIn("sharp faces", prompt)
        self.assertNotIn("facial acting", prompt)
        self.assertNotIn("Every robed or cloth-clothed human", prompt)
        self.assertNotIn("vertical room walls", prompt)
        self.assertNotIn("doorways stay outside", prompt)
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        self.assertIn("black suit jacket", negative)
        self.assertIn("white shirt cuff", negative)
        self.assertIn("hands on board", negative)
        self.assertIn("business meeting hands", negative)
        self.assertIn("framed wall picture", negative)
        self.assertIn("people inside a board frame", negative)
        self.assertIn("empty board without marker objects", negative)
        self.assertIn("single standing person beside table", negative)
        self.assertIn("person near tactile marker layout", negative)
        self.assertIn("full room interior replacing tabletop", negative)
        self.assertIn("characters on lamp base", negative)
        self.assertIn("kanji on lamp", negative)
        self.assertIn("writing on metal", negative)
        self.assertNotIn("place names", local_prompt)
        self.assertNotIn("Scene subject:", local_prompt)
        self.assertNotIn("coastline", local_prompt)
        self.assertNotIn("river grooves", local_prompt)
        self.assertNotIn("riverbank ground evidence", prompt)
        self.assertNotIn("frontier settlement illustration", local_prompt)

    def test_field_diagram_routes_to_textless_tactile_map_object(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: c. 1340-1365; Nanboku-cho period, land guarantee; "
                "Exact place: floor of a provincial warrior residence; "
                "Scene: A warrior presses his palm on a plain field diagram while a child peers from behind a pillar; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("low horizontal tactile land-marker layout", prompt)
        self.assertIn("TEXTLESS TACTILE MAP OBJECT", comfy_prompt)
        self.assertIn("No white sheet, no parchment rectangle", comfy_prompt)
        self.assertIn("no modern round door knob", comfy_prompt)
        self.assertIn("2D painted adult graphic novel style", comfy_prompt)
        self.assertIn("paper field diagram", comfy_negative)
        self.assertIn("modern doorknob beside diagram", comfy_negative)
        self.assertIn("photorealistic photo", comfy_negative)

    def test_armored_banner_scene_blocks_gate_plaque_and_armor_emblems(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: c. 1350-1370; Nanboku-cho period, shifting warrior allegiance; "
                "Exact place: forked provincial road with plain banners; "
                "Scene evidence: Warrior allegiance became fluid during the conflict.; "
                "Style: simple cartoon illustration, documentary cartoon style, clean, soft natural shadows; "
                "Main subject: warrior between two sides; "
                "Scene: A lone armored warrior steps between two plain banners, "
                "glancing back at his worried retainers"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertTrue(comfy_prompt.startswith("TEXTLESS SURFACE FIRST RULE"))
        self.assertIn("BANNER ARMOR STORY FRAME", comfy_prompt)
        self.assertIn("2D painted adult graphic novel illustration", comfy_prompt)
        self.assertIn("BANNER CLOTH FIRST RULE", comfy_prompt)
        self.assertIn("ARMOR SURFACE FIRST RULE", comfy_prompt)
        self.assertIn("do-maru or haramaki-style torso wraps", comfy_prompt)
        self.assertIn("two separated plain blank furled cloth banners", comfy_prompt)
        self.assertIn("furled blank cloth strip", comfy_prompt)
        self.assertIn("horizontal gate plaque", comfy_negative)
        self.assertIn("banner replaced by signboard", comfy_negative)
        self.assertIn("armor crest", comfy_negative)
        self.assertIn("European plate armor", comfy_negative)
        self.assertIn("photorealistic photo", comfy_negative)

    def test_medieval_japanese_family_armor_scene_rewrites_away_from_plate(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: c. 1350-1370; Nanboku-cho period, provincial household survival; "
                "Exact place: field edge beside a warrior household; "
                "Scene evidence: Family and land security affected allegiance decisions.; "
                "Style: simple cartoon illustration, documentary cartoon style, clean, soft natural shadows; "
                "Main subject: warrior family watching fields; "
                "Scene: A mother pulls a child close as an armored father stares over threatened rice fields"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("MEDIEVAL JAPANESE ARMOR STORY FRAME", comfy_prompt)
        self.assertIn("2D painted adult graphic novel illustration", comfy_prompt)
        self.assertIn("every named person", comfy_prompt)
        self.assertIn("Only the person directly described as armored wears armor", comfy_prompt)
        self.assertIn("mothers, children, civilians", comfy_prompt)
        self.assertIn("Mixed family armor role layout", comfy_prompt)
        self.assertIn("plain unarmored mother", comfy_prompt)
        self.assertIn("This is a field-edge scene", comfy_prompt)
        self.assertIn("Keep gates, doorways, wall-mounted boards", comfy_prompt)
        self.assertIn("The chest surface is not a broad metal plate", comfy_prompt)
        self.assertIn("dense overlapping scale rows", comfy_prompt)
        self.assertIn("smooth steel breastplate", comfy_negative)
        self.assertIn("helmet crest", comfy_negative)
        self.assertIn("round gold shoulder buckle", comfy_negative)
        self.assertIn("gold belt buckle", comfy_negative)
        self.assertIn("armored mother", comfy_negative)

    def test_generic_medieval_japanese_armor_scene_does_not_become_family_rewrite(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: c. 1350-1370; Nanboku-cho period, uncertain provincial warfare; "
                "Exact place: foggy mountain battlefield; "
                "Scene evidence: The complexity of sides made conflict hard to distinguish.; "
                "Style: simple cartoon illustration, documentary cartoon style, clean, soft natural shadows; "
                "Main subject: warriors in fog; "
                "Scene: Two small armored groups halt in thick fog, arrows half raised, "
                "unable to identify the other"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertNotIn("MEDIEVAL JAPANESE ARMOR STORY FRAME", comfy_prompt)
        self.assertIn("ARMOR SURFACE FIRST RULE", comfy_prompt)
        self.assertIn("arrows half raised", comfy_prompt)
        self.assertIn("smooth steel breastplate", comfy_negative)

    def test_arrow_group_scene_keeps_arrows_not_swords(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: c. 1350-1370; Nanboku-cho period, uncertain provincial warfare; "
                "Exact place: foggy mountain battlefield; "
                "Scene: Two small armored groups halt in thick fog, arrows half raised, "
                "unable to identify the other; Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("ARROW GROUP STORY FRAME", comfy_prompt)
        self.assertIn("ZERO ARCHITECTURE BATTLEFIELD RULE", comfy_prompt)
        self.assertIn("bows and arrow shafts only", comfy_prompt)
        self.assertIn("Do not replace arrows with swords", comfy_prompt)
        self.assertIn("katana, tachi, wakizashi", comfy_prompt)
        self.assertIn("weapon inventory is bows and arrows only", comfy_prompt)
        self.assertIn("No sword-only figure appears", comfy_prompt)
        self.assertIn("Use open terrain only", comfy_prompt)
        self.assertIn("no gates, no doors, no buildings", comfy_prompt)
        self.assertIn("separate hanging rectangle", comfy_prompt)
        self.assertIn("horn-like side prongs", comfy_prompt)
        self.assertIn("upward spikes", comfy_prompt)
        self.assertIn("blank hanging plaque", comfy_negative)
        self.assertIn("helmet horns", comfy_negative)
        self.assertIn("helmet spike", comfy_negative)
        self.assertIn("gate behind archers", comfy_negative)
        self.assertIn("sword-only figure", comfy_negative)
        self.assertIn("katana on archer", comfy_negative)
        self.assertIn("castle gate", comfy_negative)
        self.assertIn("raised sword", comfy_negative)

    def test_admin_orders_scene_keeps_officials_and_blank_orders_primary(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: c. 1350-1375; Nanboku-cho period, Muromachi bakufu administration; "
                "Exact place: Muromachi bakufu writing room; "
                "Scene: Officials sort sealed blank orders as armored guards usher "
                "couriers through the doorway; Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("ADMINISTRATION ORDERS STORY FRAME", comfy_prompt)
        self.assertIn("Officials sort sealed tied packet bundles", comfy_prompt)
        self.assertIn("robed officials sorting sealed tied packet bundles", comfy_prompt)
        self.assertIn("fully closed", comfy_prompt)
        self.assertIn("Do not show loose open sheets", comfy_prompt)
        self.assertNotIn("blank folded documents", comfy_prompt)
        self.assertIn("Armored guards and couriers stay secondary", comfy_prompt)
        self.assertIn("armor torso close-up", comfy_negative)
        self.assertIn("horizontal writing lines on paper", comfy_negative)
        self.assertIn("broad white paper face", comfy_negative)

    def test_gate_action_scene_does_not_become_admin_table(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: c. 1350-1380; Nanboku-cho period, Northern Court and Muromachi bakufu; "
                "Exact place: Muromachi bakufu gate in Kyoto; "
                "Scene: Armored guards swing a timber gate shut as court envoys hurry "
                "inside with sealed packets; Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("GATE ACTION STORY FRAME", comfy_prompt)
        self.assertIn("not an office room or document table", comfy_prompt)
        self.assertIn("small closed tied bundles carried in hands", comfy_prompt)
        self.assertIn("no broad horizontal white rectangle appears above the gate", comfy_prompt)
        self.assertNotIn("ADMINISTRATION ORDERS STORY FRAME", comfy_prompt)
        self.assertIn("document table at gate", comfy_negative)
        self.assertIn("broad white rectangle above gate", comfy_negative)

    def test_courier_mounting_at_gate_routes_to_gate_action(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1392; Nanboku-cho period, Kyoto after reunification; "
                "Exact place: Kyoto street at dawn; "
                "Scene: A quiet Kyoto street brightens at dawn as a courier mounts "
                "hurriedly at a Kyoto gate for distant provinces; Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, _ = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("GATE ACTION STORY FRAME", comfy_prompt)
        self.assertIn("mounted riders move through according to the Scene", comfy_prompt)

    def test_courier_mounting_without_gate_routes_to_mounted_travel(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1392; Nanboku-cho period, Kyoto after reunification; "
                "Exact place: Kyoto street at dawn; "
                "Scene: A quiet Kyoto street brightens at dawn as a courier mounts "
                "hurriedly for distant provinces; Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, _ = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("MOUNTED TRAVEL EVIDENCE LOCK", prompt)
        self.assertIn("first visible subject: the mounted travel moment", comfy_prompt)
        self.assertIn("horse-and-rider pair", comfy_prompt)
        self.assertNotIn("EMPTY EVIDENCE FRAME LOCK", comfy_prompt)

    def test_architecture_people_scene_blocks_written_header(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: c. 1380-1392; Nanboku-cho period, powerful provincial lords; "
                "Exact place: large provincial shugo mansion; "
                "Scene: A massive timber mansion casts shadow over a bakufu envoy who "
                "pauses before guarded gates; Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("ARCHITECTURE PEOPLE TEXTLESS STORY FRAME", comfy_prompt)
        self.assertIn("not a signboard facade", comfy_prompt)
        self.assertIn("Do not draw any centered top rectangle", comfy_prompt)
        self.assertIn("written lintel board", comfy_negative)
        self.assertIn("empty plaque-shaped block", comfy_negative)

    def test_ritual_messenger_scene_keeps_vessels_and_motion(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: c. 1350-1380; Nanboku-cho period, Kyoto court and bakufu politics; "
                "Exact place: Kyoto ceremonial hall near bakufu quarter; "
                "Scene: Robed nobles prepare ritual vessels while armored messengers "
                "rush past with sealed blank orders; Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("RITUAL MESSENGER STORY FRAME", comfy_prompt)
        self.assertIn("ritual vessels clearly visible", comfy_prompt)
        self.assertIn("messengers visibly moving", comfy_prompt)
        self.assertIn("no broad horizontal white rectangle appears above it", comfy_prompt)
        self.assertNotIn("ADMINISTRATION ORDERS STORY FRAME", comfy_prompt)
        self.assertIn("missing ritual vessels", comfy_negative)
        self.assertIn("broad white rectangle above doorway", comfy_negative)

    def test_lamp_people_scene_not_empty_room(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1392; Nanboku-cho period, reunified court; "
                "Exact place: Kyoto court hall after settlement; "
                "Scene: One oil lamp burns at the center of a court hall as former "
                "rivals sit apart but still; Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("LAMP PEOPLE SEPARATION STORY FRAME", comfy_prompt)
        self.assertIn("never empty", comfy_prompt)
        self.assertIn("empty room", comfy_negative)

    def test_province_stones_council_keeps_stones_primary(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1392; Nanboku-cho period, Yoshimitsu after reunification; "
                "Exact place: Muromachi shogunal hall; "
                "Scene: Yoshimitsu sits before relieved courtiers while armored retainers "
                "point anxiously toward province stones; Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("PROVINCE STONES COUNCIL STORY FRAME", comfy_prompt)
        self.assertIn("dark province stones", comfy_prompt)
        self.assertIn("missing province stones", comfy_negative)

    def test_document_bundle_arrangement_keeps_bundles_not_lineup(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: c. 1380-1392; Nanboku-cho period, court and bakufu administration; "
                "Exact place: Kyoto administrative chamber; "
                "Scene: Officials carefully rearrange sealed blank scroll bundles while "
                "rival attendants watch every movement; Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("DOCUMENT BUNDLE ARRANGEMENT STORY FRAME", comfy_prompt)
        self.assertIn("sealed scroll bundles", comfy_prompt)
        self.assertIn("not a front-facing row", comfy_prompt)
        self.assertIn("wall sign with characters", comfy_negative)

    def test_envoy_armed_interaction_keeps_envoys_visible(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: c. 1370-1380; Nanboku-cho period, Kyoto search for settlement; "
                "Exact place: Kyoto street near court and bakufu quarters; "
                "Scene: Court envoys and armored escorts pass each other warily on a "
                "narrow wooden street; Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("CIVILIAN ARMED INTERACTION STORY FRAME", comfy_prompt)
        self.assertIn("Court envoys and escorts", comfy_prompt)
        self.assertIn("envoys, courtiers", comfy_prompt)
        self.assertIn("armor emblem", comfy_negative)

    def test_lamp_guard_listening_uses_low_lamp_lock(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: c. 1370-1380; Nanboku-cho period, Southern Court persistence; "
                "Exact place: Yoshino mountain at night; "
                "Scene: A lone lamp burns in a mountain hall as a guard listens to distant hooves; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, _ = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("LOW LAMP ARMED ENTRY LOCK", prompt)
        self.assertIn("listening tension", prompt)
        self.assertIn("Low lamp armed entry story frame", comfy_prompt)
        self.assertIn("listening direction", comfy_prompt)

    def test_armored_hand_rice_measure_scene_stays_object_closeup(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: c. 1350-1375; Nanboku-cho period, prolonged war society; "
                "Exact place: storehouse floor in a provincial village; "
                "Scene: Rice spills from a wooden measure as an armored hand reaches "
                "across a village storehouse floor; Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("HAND OBJECT EVIDENCE STORY FRAME", comfy_prompt)
        self.assertIn("wooden rice measure", comfy_prompt)
        self.assertIn("one cropped armored sleeve or hand", comfy_prompt)
        self.assertIn("full armored person", comfy_negative)

    def test_civilian_armed_interaction_keeps_farmers_visible(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: c. 1350-1380; Nanboku-cho period, provincial land control; "
                "Exact place: village fields beside warrior residence; "
                "Scene: A timber warrior residence looms over rice fields as armored men "
                "stride past anxious farmers; Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("CIVILIAN ARMED INTERACTION STORY FRAME", comfy_prompt)
        self.assertIn("named farmers, villagers, civilians", comfy_prompt)
        self.assertIn("Armed or armored retainers stay in the same space", comfy_prompt)
        self.assertIn("no farmers visible", comfy_negative)

    def test_mounted_scene_blocks_chest_crests_and_horse_medallions(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: c. 1350-1370; Nanboku-cho period, shifting communications; "
                "Exact place: forest road junction in provincial Japan; "
                "Scene evidence: Messenger routes could reflect changing allegiance or strategy.; "
                "Style: simple cartoon illustration, documentary cartoon style, clean, soft natural shadows; "
                "Main subject: messenger changing road; "
                "Scene: A messenger suddenly turns his horse onto a narrow forest path "
                "while pursuers shout behind him"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("VISIBLE CLOTHING SURFACE FIRST RULE", comfy_prompt)
        self.assertIn("MOUNTED TACK SURFACE FIRST RULE", comfy_prompt)
        self.assertIn("no laurel mark", comfy_prompt)
        self.assertIn("ring-shaped robe mark", comfy_negative)
        self.assertIn("horse medallion", comfy_negative)

    def test_historical_globe_rewrites_to_period_strategy_board(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 525 BC; Exact place: Pelusium, Nile Delta, Egypt; "
                "Scene: a spinning ancient globe made of brass and wood, focusing on the Middle East, dramatic lighting; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("blank tabletop planning board on a low wooden table", prompt)
        self.assertIn("loose cord paths", prompt)
        self.assertIn("the requested blank tabletop planning board", prompt)
        self.assertNotIn("globe", prompt.lower())
        self.assertNotIn("UNMARKED STRATEGIC BOARD LOCK", prompt)
        self.assertNotIn("Unmarked low horizontal tactile marker layout illustration", local_prompt)

    def test_modern_globe_scene_keeps_globe(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 2024; Exact place: modern Seoul classroom; "
                "Scene: a modern classroom globe on a teacher's desk; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("modern classroom globe", prompt.lower())
        self.assertNotIn("label-free tactile strategy board", prompt.lower())
        negative = prompt_builder.historical_negative_prompt(prompt, enabled=True)
        self.assertNotIn("black suit jacket", negative)
        self.assertNotIn("white shirt cuff", negative)

    def test_empty_atmosphere_scene_does_not_seed_people_or_weapons(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Main subject: Jumong; "
                "Scene: everything standing still, dead leaves falling slowly; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("HARD HISTORICAL SETTING MATERIAL CULTURE LOCK", prompt)
        self.assertIn("EARLY GOGURYEO SETTING LOCK", prompt)
        self.assertIn("empty period-correct setting", prompt)
        self.assertIn("fallen dead leaves", prompt)
        self.assertIn("EMPTY EVIDENCE FRAME LOCK", prompt)
        self.assertNotIn("EARLY GOGURYEO FRONTIER LOCK", prompt)
        self.assertNotIn("HARD HISTORICAL MATERIAL CULTURE LOCK", prompt)
        self.assertNotIn("armor", prompt.lower())
        self.assertNotIn("lamellar", prompt.lower())
        self.assertNotIn("weapon", prompt.lower())
        self.assertNotIn("sword", prompt.lower())
        self.assertNotRegex(prompt.lower(), r"\bbow\b")

    def test_group_character_prompt_uses_group_guard_without_solo_lock(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: Jumong and a few loyal friends standing below the throne; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("GROUP CHARACTER COMPOSITION LOCK", prompt)
        self.assertIn("close group story moment", prompt)
        self.assertNotIn("SINGLE CHARACTER LOCK", prompt)
        self.assertNotIn("one solitary face", prompt)

    def test_two_named_people_interaction_uses_group_path(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: Songyang kneeling and Soseono shaking hands; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("GROUP CHARACTER COMPOSITION LOCK", prompt)
        self.assertIn("close group story moment", prompt)
        self.assertIn("Early Goguryeo civilian or political group illustration", local_prompt)
        self.assertNotIn("SINGLE CHARACTER LOCK", prompt)
        self.assertNotIn("one solitary face", prompt)

    def test_listener_monk_scroll_scene_uses_group_path_with_named_props(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: c. late 14th century; Muromachi period, Southern Court memory; "
                "Exact place: Yoshino mountain temple hall; "
                "Scene: Mountain temple listeners lower their heads as a monk closes an "
                "unmarked scroll beside a dim lamp; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("GROUP CHARACTER COMPOSITION LOCK", prompt)
        self.assertIn("close group story moment", prompt)
        self.assertIn("scroll", prompt)
        self.assertIn("lamp", prompt)
        self.assertIn("same action center", prompt)
        self.assertNotIn("SINGLE CHARACTER LOCK", prompt)
        self.assertNotIn("one solitary face", prompt)

    def test_military_camp_armor_bundles_do_not_become_civilian_work_props(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1336; Early Nanboku-cho conflict, Ashikaga recovery in Kyushu; "
                "Exact place: Kyushu field camp; "
                "Scene: New warriors arrive at Takauji's camp, lifting armor bundles "
                "while tired retainers make space; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("GROUP CHARACTER COMPOSITION LOCK", prompt)
        self.assertIn("MILITARY LOGISTICS GROUP VISIBLE SET LOCK", prompt)
        self.assertIn("flat stacks of laced kozane scale rows", prompt)
        self.assertNotIn("armor bundles", prompt.lower())
        self.assertIn("dark lacquered lamellar armor rolls", prompt)
        self.assertIn("stacked rows of small overlapping laced scale layers", prompt)
        self.assertIn("folded sode shoulder panels", prompt)
        self.assertIn("do-maru torso wraps", prompt)
        self.assertIn("kusazuri skirt panels", prompt)
        self.assertIn("continuous timber beam, rafters, bracket", prompt)
        self.assertIn("one uninterrupted load-bearing timber beam", prompt)
        self.assertNotIn("CAMP WORK VISIBLE SET LOCK", prompt)
        self.assertNotIn("Every visible torso is civilian cloth work clothing", prompt)
        self.assertNotIn("straw bundles", prompt)
        self.assertNotIn("basket", prompt.lower())
        self.assertNotIn("ARMED ROLE PORTRAIT CROP LOCK", prompt)
        self.assertNotIn("one representative foreground armored survivor", prompt)
        self.assertIn("Military logistics group scene", local_prompt)
        self.assertIn("folded sode shoulder panels", local_prompt)
        self.assertIn("do-maru torso wraps", local_prompt)

    def test_outdoor_riverbank_character_keeps_exterior_evidence_and_plain_boxes(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1336; Early Nanboku-cho conflict, Minatogawa aftermath; "
                "Exact place: misty riverbank at Minatogawa; "
                "Scene: A court-side commander turns toward the battered riverbank, "
                "his plain armor wet with mist; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("OUTDOOR LOCATION EVIDENCE LOCK", prompt)
        self.assertIn("water edge, reeds, stones, mud", prompt)
        self.assertIn("Storage boxes, crates, trunks", prompt)
        self.assertIn("Storage boxes, crates, trunks", local_prompt)
        self.assertIn("Scene-named outdoor setting evidence", local_prompt)

    def test_mounted_messengers_keep_horses_banners_and_shrine_evidence(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1338; Early Muromachi period, continuing Nanboku-cho tension; "
                "Exact place: misty road from Kyoto toward the provinces; "
                "Scene: Mounted messengers vanish into morning mist as blank banners "
                "flutter beside a quiet roadside shrine; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)

        self.assertIn("MOUNTED TRAVEL EVIDENCE LOCK", prompt)
        self.assertIn("horse-and-rider pair", prompt)
        self.assertIn("Rider upper chests are crossed or broken by reins", prompt)
        self.assertIn("instead of repeated chest marks", prompt)
        self.assertIn("CLOTH EVIDENCE SURFACE LOCK", prompt)
        self.assertIn("ENTRY FACADE SURFACE LOCK", prompt)
        self.assertIn("banners and flags appear as side-facing or back-facing wind-folded cloth strips", prompt)
        self.assertIn("narrow edge-on fabric surfaces", prompt)
        self.assertIn("Mounted travel story frame", local_prompt)
        self.assertIn("Rider upper chests are crossed or broken by reins", local_prompt)
        self.assertIn("small circular robe emblem", negative)
        self.assertIn("matching chest crests", negative)
        self.assertIn("rider chest badge", negative)

    def test_single_character_prompt_routes_to_action_story_frame(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: King Arion pointing his sword down aggressively; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("the principal figure from the Scene in a story-action frame", prompt)
        self.assertIn("ARMED FIGURE LOADOUT LOCK", prompt)
        self.assertIn("medium-close or waist-up three-quarter action crop", prompt)
        self.assertIn("SELECTED PERIOD WEAPON LOCK", prompt)
        self.assertIn("HUMAN FACE SURFACE LOCK", prompt)
        self.assertIn("adult male subjects have a handsome", prompt)
        self.assertIn("adult female subjects have a beautiful", prompt)
        self.assertIn("clean unpainted skin surface", prompt)
        self.assertIn("upper head area is natural hairline", prompt)
        self.assertNotIn("compact rounded cap", prompt)
        self.assertNotIn("headwear", prompt.lower())
        self.assertIn("Costume evidence stays on period-appropriate cloth neckline", prompt)
        self.assertNotIn("face markings", prompt)
        self.assertNotIn("ritual headgear", prompt)
        self.assertNotIn("SINGLE CHARACTER LOCK", prompt)
        self.assertNotIn("CHARACTER PORTRAIT VISIBLE SET LOCK", prompt)
        self.assertNotIn("portrait crop shows only the face", prompt)
        self.assertNotIn("GROUP CHARACTER COMPOSITION LOCK", prompt)

    def test_scene_named_identity_overrides_metadata_subject(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Main subject: 주몽; "
                "Scene: Soseono looking at Jumong with calculating sharp eyes; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("SCENE NAMED IDENTITY LOCK", prompt)
        self.assertIn("Soseono is an adult woman", prompt)
        self.assertIn("the visible living person is the first named person from the Scene field", prompt)
        self.assertNotIn("Main subject: 주몽", prompt)

    def test_adult_female_character_uses_body_silhouette_not_default_closeup(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: Soseono standing beside a timber gate with calculating sharp eyes; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)

        self.assertIn("ADULT FEMALE APPEAL AND BODY SILHOUETTE LOCK", prompt)
        self.assertIn("full-body, knee-up, or three-quarter-body composition", prompt)
        self.assertIn("waist, hips, legs, posture, and silhouette", prompt)
        self.assertIn("Soseono is an adult woman", prompt)
        self.assertNotIn("SINGLE CHARACTER LOCK", prompt)
        self.assertIn("underage", negative)
        self.assertIn("nude", negative)

    def test_adult_female_explicit_closeup_keeps_closeup_with_allure(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: close-up portrait of Soseono with calculating sharp eyes; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("SINGLE CHARACTER LOCK", prompt)
        self.assertIn("ADULT FEMALE APPEAL AND BODY SILHOUETTE LOCK", prompt)
        self.assertIn("If the Scene explicitly requests a close-up or portrait", prompt)
        self.assertIn("alluring mature gaze", prompt)

    def test_scene_named_setting_evidence_survives_character_story_frame(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: King Dongmyeong sitting on a grand stone throne; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("King Dongmyeong is an adult man", prompt)
        self.assertIn("the seated ruler and the Scene-named throne or seat together", prompt)
        self.assertIn("not a face-only portrait", prompt)
        self.assertIn("medium-close or waist-up three-quarter story frame", prompt)
        self.assertIn("platform edge", prompt)
        self.assertIn("low timber platform", prompt)

    def test_local_router_keeps_single_and_group_paths_separate(self):
        single = (
            "Year/period: around 37 BCE; Exact place: Jolbon; "
            "Scene: King Arion glaring under torchlight; "
            "|| SINGLE CHARACTER LOCK - one visible living human figure"
        )
        group = (
            "Year/period: around 37 BCE; Exact place: Jolbon; "
            "Scene: Arion and a few loyal companions stand in the courtyard; "
            "|| GROUP CHARACTER COMPOSITION LOCK"
        )

        self.assertTrue(_local_scene_requests_single_character(single))
        self.assertFalse(_local_scene_requests_group(single))
        self.assertTrue(_local_scene_requests_group(group))
        self.assertFalse(_local_scene_requests_single_character(group))

    def test_local_router_does_not_treat_two_eyes_as_two_people(self):
        single = (
            "Scene: King Arion close portrait || SINGLE CHARACTER LOCK - "
            "one visible living human figure, two visible eyes as the largest shape"
        )

        self.assertFalse(_local_scene_requests_group(single))
        self.assertTrue(_local_scene_requests_single_character(single))

    def test_local_group_enrichment_requires_distinct_people_spacing(self):
        enriched = _enrich_local_v1_positive_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: Arion and a few loyal companions standing below a low platform; "
                "|| GROUP CHARACTER COMPOSITION LOCK"
            )
        )

        self.assertIn("separate individual", enriched)
        self.assertIn("clear air gap", enriched)
        self.assertIn("offset three-quarter group angle", enriched)
        self.assertNotIn("camera in front of the group", enriched)
        self.assertNotIn("foreground faces front or three-quarter-front", enriched)

    def test_local_single_closeup_uses_role_and_beauty_rules(self):
        enriched = _enrich_local_v1_positive_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: King Arion close portrait under rain; "
                "|| SINGLE CHARACTER LOCK - one visible living human figure"
            )
        )

        self.assertIn("Honor explicit gender", enriched)
        self.assertIn("adult male subjects have a handsome", enriched)
        self.assertIn("adult female subjects have a beautiful", enriched)
        self.assertIn("Plain natural human face surface", enriched)
        self.assertIn("Bare compact human head", enriched)
        self.assertIn("role or rank shown through period-appropriate cloth neckline", enriched)
        self.assertIn("clean unpainted skin surface", enriched)
        self.assertIn("full forehead from eyebrows to hairline is visible natural skin", enriched)
        self.assertIn("upper head area is natural hairline", enriched)
        self.assertNotIn("compact rounded cap", enriched)
        self.assertNotIn("headwear", enriched.lower())
        self.assertNotIn("face markings", enriched)
        self.assertNotIn("ritual headgear", enriched)

    def test_local_single_closeup_preserves_scene_identity_hint(self):
        enriched = _enrich_local_v1_positive_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: Soseono looking at Jumong with calculating sharp eyes; "
                "|| SINGLE CHARACTER LOCK - one visible living human figure"
            )
        )

        self.assertIn("Scene-named person identity is the anchor", enriched)
        self.assertIn("Soseono is an adult woman", enriched)
        self.assertIn("narrow Scene-named setting evidence background", enriched)

    def test_local_single_closeup_head_prompt_removes_headband_terms(self):
        cleaned = _enforce_local_single_closeup_head_prompt(
            "single character lock, simple tied hair or cloth headband, "
            "flat cloth band close to the skull, flat cloth headband close to the skull. "
            "Headwear, when the Scene role requires it, forms one compact rounded cap "
            "that stays close to the skull."
        )

        self.assertIn("visible natural hairline", cleaned)
        self.assertIn("Bare compact human head", cleaned)
        self.assertNotIn("headband", cleaned.lower())
        self.assertNotIn("cloth band", cleaned.lower())
        self.assertNotIn("headwear", cleaned.lower())
        self.assertNotIn("compact rounded cap", cleaned.lower())

    def test_armed_group_prompt_adds_one_weapon_per_person_lock(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1592; Exact place: fortress gate; "
                "Scene: soldiers charging with spears and swords"
            ),
            "documentary illustration",
            enable_historical_guard=True,
        )

        self.assertIn("ARMED FIGURE LOADOUT LOCK", prompt)
        self.assertIn("PRIMARY IMAGE LOCK - first visible subject: one representative foreground armed person", prompt)
        self.assertNotIn("PRIMARY IMAGE LOCK - first visible subject: a close group story moment", prompt)
        self.assertIn("each person has one simple visible primary weapon only", prompt)
        self.assertIn("Translate wide or crowded armed-group scenes into one representative armed person", prompt)
        self.assertIn("Make exactly one foreground armed person readable", prompt)
        self.assertIn("complete readable human set is one foreground fighter only", prompt)
        self.assertIn("Choose one shared primary weapon class", prompt)
        self.assertIn("SELECTED PERIOD WEAPON LOCK", prompt)
        self.assertIn("ARMED GROUP REPRESENTATIVE COMPOSITION LOCK", prompt)
        self.assertIn("one representative foreground fighter as the readable subject", prompt)
        self.assertNotIn("GROUP CHARACTER COMPOSITION LOCK", prompt)
        self.assertIn("one small leaf-shaped iron tip", prompt)
        self.assertIn("Every readable waist area resolves as a flat tied cloth sash", prompt)
        self.assertIn("ARMED BODY VISIBLE SET LOCK", prompt)
        self.assertIn("visible personal inventory is the selected primary weapon item", prompt)
        self.assertIn("Short dark shapes near hips resolve as folded sash tails", prompt)
        self.assertNotIn("soft rectangular cloth tabs", prompt)
        self.assertIn("Side waist and hip zones contain only flat sash", prompt)
        self.assertIn("the selected primary weapon is the only weapon-shaped object", prompt)
        self.assertIn("one spear prop total", prompt)
        self.assertIn("body-gesture hands resting on chest armor", prompt)
        self.assertIn("Whole-image readable weapon inventory is one spear prop total", prompt)
        self.assertIn("Background vertical marks read as thick blunt timber posts", prompt)
        self.assertIn("flat cloth sashes, center knots, robe folds", prompt)
        self.assertIn("one clear weapon item total", prompt)
        self.assertNotIn("curved wooden self bows as the shared primary weapon", prompt)
        self.assertNotIn("one shield according", prompt)

    def test_local_armed_loadout_collapses_weapon_lists(self):
        cleaned = _enforce_local_armed_figure_loadout_prompt(
            "soldiers with round wooden shields, bows, short blades, "
            "plain round shield faces, vertical props appear as plain spear shafts"
        )

        self.assertIn("Each armed person has one simple visible primary weapon only", cleaned)
        self.assertIn("translate the group into one representative armed person", cleaned)
        self.assertIn("Make exactly one foreground armed person readable", cleaned)
        self.assertIn("complete readable human set is one foreground fighter only", cleaned)
        self.assertIn("Choose one shared primary weapon class", cleaned)
        self.assertIn("one selected primary weapon per person", cleaned)
        self.assertIn("SELECTED PERIOD WEAPON LOCK", cleaned)
        self.assertIn("one small leaf-shaped iron tip", cleaned)
        self.assertIn("Every readable waist area resolves as a flat tied cloth sash", cleaned)
        self.assertIn("ARMED BODY VISIBLE SET LOCK", cleaned)
        self.assertIn("visible personal inventory is the selected primary weapon item", cleaned)
        self.assertIn("Short dark shapes near hips resolve as folded sash tails", cleaned)
        self.assertNotIn("soft rectangular cloth tabs", cleaned)
        self.assertIn("Side waist and hip zones contain only flat sash", cleaned)
        self.assertIn("the selected primary weapon is the only weapon-shaped object", cleaned)
        self.assertIn("one spear prop total", cleaned)
        self.assertIn("body-gesture hands resting on chest armor", cleaned)
        self.assertIn("Whole-image readable weapon inventory is one spear prop total", cleaned)
        self.assertIn("Background vertical marks read as thick blunt timber posts", cleaned)
        self.assertIn("one clear weapon item total", cleaned)
        self.assertNotIn("curved wooden self bows as the shared primary weapon", cleaned)
        self.assertNotIn("round wooden shields, bows, short blades", cleaned)
        self.assertNotIn("plain round shield faces", cleaned)

    def test_named_bow_without_arrow_uses_one_bow_only(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: Songyang holding a large bow, smirking proudly; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("SELECTED PERIOD WEAPON LOCK", prompt)
        self.assertIn("one curved wooden bow as the single foreground prop", prompt)
        self.assertIn("close upper-body bow-evidence portrait", prompt)
        self.assertIn("one unstrung ceremonial display bow", prompt)
        self.assertIn("one vertical C-shaped wooden bow limb cropped along the right image edge", prompt)
        self.assertIn("visible bow geometry made from curved wood", prompt)
        self.assertIn("Whole-image readable weapon inventory is one bow prop total", prompt)
        self.assertIn("Hands and lower weapon geometry fall outside", prompt)
        self.assertNotIn("ARMED FIGURE LOADOUT LOCK", prompt)
        self.assertNotIn("ARMED BODY VISIBLE SET LOCK", prompt)
        self.assertNotIn("feathered arrows", prompt)
        self.assertNotIn("bow-and-arrow weapon system", prompt)
        self.assertNotIn("bow-and-one-arrow combined prop total", prompt)

    def test_named_arrow_scene_uses_one_bow_one_arrow_combined_prop(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: Jumong aiming one arrow at a distant target; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("one curved wooden bow with one fitted arrow", prompt)
        self.assertIn("Whole-image readable weapon inventory is one bow-and-one-arrow combined prop total", prompt)
        self.assertIn("The bow-and-arrow prop stays in front of the torso and hands", prompt)
        self.assertIn("back shoulder plane is uninterrupted cloak", prompt)
        self.assertNotIn("feathered arrows", prompt)
        self.assertNotIn("bow-and-arrow weapon system", prompt)

    def test_local_named_bow_without_arrow_uses_scene_only(self):
        enriched = _enforce_local_armed_figure_loadout_prompt(
            (
                "Global visual world: Material culture: Iron weapons, bows, iron arrowheads; "
                "Scene subject: Songyang holding a large bow, smirking proudly."
            )
        )

        self.assertIn("one curved wooden bow as the single foreground prop", enriched)
        self.assertIn("close upper-body bow-evidence portrait", enriched)
        self.assertIn("one unstrung ceremonial display bow", enriched)
        self.assertIn("one vertical C-shaped wooden bow limb cropped along the right image edge", enriched)
        self.assertIn("visible bow geometry made from curved wood", enriched)
        self.assertIn("Whole-image readable weapon inventory is one bow prop total", enriched)
        self.assertIn("Hands and lower weapon geometry fall outside", enriched)
        self.assertNotIn("ARMED FIGURE LOADOUT LOCK", enriched)
        self.assertNotIn("ARMED BODY VISIBLE SET LOCK", enriched)
        self.assertNotIn("feathered arrows", enriched)
        self.assertNotIn("bow-and-one-arrow combined prop total", enriched)

    def test_local_early_group_stays_group_scene(self):
        enriched = _enrich_local_v1_positive_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: a dark and gritty ancient battlefield, cinematic; "
                "|| GROUP CHARACTER COMPOSITION LOCK"
            )
        )

        self.assertIn("frontier armed-role portrait illustration", enriched)
        self.assertIn("one representative foreground armored survivor", enriched)
        self.assertIn("tight face-to-upper-chest crop", enriched)
        self.assertIn("smoke, dust, roof edges, thick timber posts", enriched)
        self.assertIn("ARMED ROLE PORTRAIT CROP LOCK", enriched)
        self.assertIn("lower image boundary cuts across the upper chest", enriched)
        self.assertNotIn("representative foreground fighter", enriched)
        self.assertNotIn("selected close chest-side prop", enriched)
        self.assertNotIn("plain short iron swords as the shared primary weapon", enriched)
        self.assertNotIn("object-only historical scene", enriched)
        self.assertNotIn("spearhead evidence", enriched.lower())

    def test_local_armed_group_uses_named_single_weapon(self):
        enriched = _enrich_local_v1_positive_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: massive army holding sharp spears; "
                "|| GROUP CHARACTER COMPOSITION LOCK"
            )
        )

        self.assertIn("frontier armed group illustration", enriched)
        self.assertIn("one shared group scene", enriched)
        self.assertIn("one representative foreground frontier fighter", enriched)
        self.assertIn("representative fighter shows one simple primary weapon item only", enriched)
        self.assertIn("whole readable formation uses one shared weapon class", enriched)
        self.assertIn("one simple wooden spear as the selected shoulder-side prop", enriched)
        self.assertIn("one small leaf-shaped iron tip", enriched)
        self.assertNotIn("plain short iron swords as the shared primary weapon", enriched)
        self.assertNotIn("object-only historical scene", enriched)
        self.assertNotIn("spearhead evidence", enriched.lower())

    def test_early_goguryeo_battlefield_routes_to_armed_scene_without_scene_rewrite(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: dark and gritty ancient battlefield, cinematic; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("one representative foreground armored survivor from the Scene", prompt)
        self.assertIn("dark and gritty ancient battlefield", prompt)
        self.assertIn("ARMED ROLE PORTRAIT CROP LOCK", prompt)
        self.assertIn("medium-close or waist-up three-quarter story frame", prompt)
        self.assertIn("Do not make it a face-only ID portrait", prompt)
        self.assertNotIn("foreground fighter from the Scene", prompt)
        self.assertNotIn("EMPTY EVIDENCE FRAME LOCK", prompt)
        self.assertNotIn("OBJECT-LOCATION PRIMARY SUBJECT LOCK", prompt)

    def test_early_goguryeo_camp_preserves_refugee_group_scene(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: poor refugees setting up a small ancient camp; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("poor refugees setting up a small ancient camp", prompt)
        self.assertIn("GROUP CHARACTER COMPOSITION LOCK", prompt)
        self.assertIn("SCENE CONTENT PRIORITY", prompt)
        self.assertIn("CAMP WORK VISIBLE SET LOCK", prompt)
        self.assertIn("The complete visible torso material set is soft woven cloth", prompt)
        self.assertIn("EARLY GOGURYEO CIVILIAN FRONTIER LOCK", prompt)
        self.assertNotIn("EARLY GOGURYEO CHARACTER LOCK", prompt)
        self.assertNotIn("torso protection made from rows", prompt)
        self.assertNotIn("weapons secured near the torso", prompt)
        self.assertNotIn("armor", prompt.lower())
        self.assertNotIn("lamellar", prompt.lower())
        self.assertNotIn("EMPTY EVIDENCE FRAME LOCK", prompt)

    def test_early_goguryeo_poor_warriors_preserves_scene_with_single_weapon_lock(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: a few poorly equipped warriors against a massive army; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("a few poorly equipped warriors against a massive army", prompt)
        self.assertIn("one representative foreground armored survivor from the Scene", prompt)
        self.assertIn("ARMED ROLE PORTRAIT CROP LOCK", prompt)
        self.assertIn("medium-close or waist-up three-quarter story frame", prompt)

    def test_armed_victory_weapon_raise_normalizes_to_empty_fist(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: enemy soldiers raising their weapons high in victory; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("one representative victorious fighter", prompt)
        self.assertIn("raising a clenched empty fist", prompt)
        self.assertIn("ARMED ROLE PORTRAIT CROP LOCK", prompt)
        self.assertIn("medium-close or waist-up three-quarter story frame", prompt)
        self.assertNotIn("raising their weapons high", prompt)

    def test_modern_character_prompt_uses_modern_clothing_lock(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 2024; Exact place: high-rise apartment interior, Seoul city view from window; "
                "Scene: Indian woman in casual modern clothing standing at a window, gazing out at Seoul's skyline; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("MODERN CHARACTER CLOTHING LOCK", prompt)
        self.assertIn("contemporary civilian fabric clothing", prompt)
        self.assertIn("shirts, blouses, sweaters, jackets", prompt)
        self.assertNotIn("HISTORICAL HUMAN CLOTHING LOCK", prompt)
        self.assertNotIn("HISTORICAL BUILDING HARDWARE LOCK", prompt)
        self.assertNotIn("armor vest", prompt)
        self.assertNotIn("lamellar", prompt.lower())

    def test_historical_closeup_does_not_seed_modern_shirt_or_jacket(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 525 BC; Exact place: Pelusium, Nile Delta, Egypt; "
                "Scene: Psamtik watching his daughter carrying heavy water jugs, looking exhausted and broken; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)
        combined = f"{prompt} {local_prompt}".lower()

        self.assertIn("HISTORICAL HUMAN CLOTHING LOCK", prompt)
        self.assertIn("PERIOD-LOCAL ACHAEMENID PERSIAN AND EGYPTIAN MATERIAL CULTURE LOCK", prompt)
        self.assertNotIn("shirt", combined)
        self.assertNotIn("jacket", combined)
        self.assertNotIn("coat", combined)

    def test_ancient_survivor_closeup_does_not_seed_modern_collar_or_vest(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 525 BC; Exact place: Pelusium (Ancient Egypt) & Achaemenid Persian Empire; "
                "Scene: panicked Egyptian survivors running desperately across the desert, looking back in fear; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)
        combined = f"{prompt} {local_prompt}".lower()

        self.assertIn("HISTORICAL HUMAN CLOTHING LOCK", prompt)
        for modern_term in ("shirt", "jacket", "vest", "collar", "button", "lapel", "hoodie"):
            self.assertNotIn(modern_term, combined)

    def test_historical_no_modern_objects_does_not_trigger_modern_lock(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Continuity rule: historically grounded medieval Japanese settings, no modern objects; "
                "Year/period: 1333-1334; Kenmu Restoration, court administration strain; "
                "Exact place: Kyoto palace outer office; "
                "Scene: Samurai wait in a cold courtyard, faces tightening as an official closes a wooden screen; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("HARD HISTORICAL", prompt)
        self.assertIn("HISTORICAL HUMAN CLOTHING LOCK", prompt)
        self.assertIn("garments from the stated Year/period and Exact place", prompt)
        self.assertNotIn("MODERN CHARACTER CLOTHING LOCK", prompt)

    def test_historical_messenger_scene_gets_period_clothing_lock(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Global visual world: Time range: Japan, late Kamakura period to early Muromachi period, mainly 1333-1338; "
                "Material culture: hitatare robes, court robes, armor with laced kozane rows, tachi swords, messenger horses; "
                "Continuity rule: historically grounded medieval Japanese settings, no modern objects; "
                "Year/period: 1335; Kenmu Restoration, eastern military emergency; "
                "Exact place: roadside courier station near Kamakura; "
                "Scene: A court messenger pulls a tired horse to a halt as armored riders rush past without waiting; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("HISTORICAL HUMAN CLOTHING LOCK", prompt)
        self.assertIn("material-culture words already present", prompt)
        self.assertNotIn("MODERN CHARACTER CLOTHING LOCK", prompt)
        self.assertIn("Every visible person wears garments from the stated Year/period", local_prompt)
        self.assertIn("Visible neck openings, draped chest edges, sleeves, waistlines", local_prompt)
        self.assertNotIn("Present-day modern setting", local_prompt)

    def test_court_ritual_group_does_not_get_empty_evidence_lock(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1333-1334; Exact place: Kyoto palace ritual hall; "
                "Scene: Courtiers arrange ritual objects and blank scrolls briskly as Go-Daigo watches from behind bamboo blinds; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("FORMAL ROLE AND SETTING LAYOUT LOCK", prompt)
        self.assertIn("GROUP CHARACTER COMPOSITION LOCK", prompt)
        self.assertIn("ORDINARY HUMAN VISIBLE SET LOCK", prompt)
        self.assertIn("Emperor Go-Daigo is an adult man", prompt)
        self.assertIn("Formal role and setting illustration", local_prompt)
        self.assertNotIn("EMPTY EVIDENCE FRAME LOCK", prompt)
        self.assertNotIn("OBJECT-LOCATION PRIMARY SUBJECT LOCK", prompt)
        self.assertNotIn("object-only historical scene", local_prompt)

    def test_court_hall_warriors_keep_formal_layout_not_armed_portrait(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1333; Exact place: Kyoto imperial court hall; "
                "Scene: Courtiers lift bamboo blinds as warriors kneel outside, both sides drawn toward the same hall; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("FORMAL ROLE AND SETTING LAYOUT LOCK", prompt)
        self.assertIn("GROUP CHARACTER COMPOSITION LOCK", prompt)
        self.assertIn("bamboo blinds", prompt)
        self.assertNotIn("ARMED ROLE PORTRAIT CROP LOCK", prompt)
        self.assertNotIn("one representative foreground armored survivor", prompt)

    def test_split_road_scene_gets_split_side_layout_lock(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1333-1336; Exact place: split road outside Kyoto; "
                "Scene: Takauji pauses where two dirt roads divide, court messengers on one side and warriors on the other; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("SPLIT-SIDE COMPOSITION LOCK", prompt)
        self.assertIn("FORMAL ROLE AND SETTING LAYOUT LOCK", prompt)
        self.assertIn("forked road", local_prompt)
        self.assertNotIn("ARMED ROLE PORTRAIT CROP LOCK", prompt)

    def test_banner_terms_become_unmarked_cloth_panels_early(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: c. 1335-1336; Exact place: misty military road outside Kyoto; "
                "Scene: Takauji in hitatare and lamellar armor grips his tachi, staring tensely between Kyoto gate and warrior banners; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)

        self.assertIn("UNMARKED SURFACE LOCK", prompt)
        self.assertLess(prompt.index("UNMARKED SURFACE LOCK"), prompt.index("PRIMARY IMAGE LOCK"))
        self.assertIn("narrow edge-on furled blank cloth strip tied to a pole", prompt)
        self.assertIn("clenches both empty hands over a plain belt", prompt)
        self.assertIn("SINGLE CHARACTER SETTING STORY LOCK", prompt)
        self.assertIn("medium-close or waist-up story frame", prompt)
        self.assertIn("small off-center edge-on or furled blank cloth strip", prompt)
        self.assertIn("PERIOD-LOCAL JAPANESE COSTUME AND ARMOR LOCK", prompt)
        self.assertIn("ARMORED ROLE VISIBLE SET LOCK", prompt)
        self.assertIn("matte cloth-covered, cord-laced Japanese protective dress", prompt)
        self.assertIn("rectangular sode shoulder panels tied to shoulder cords", prompt)
        self.assertIn("two large hanging laced sode shoulder panels", prompt)
        self.assertIn("Sode panels hang outside the upper arms", prompt)
        self.assertIn("flexible torso wrap made of many small scale rows", prompt)
        self.assertIn("full chest front is an edge-to-edge field of small overlapping kozane tiles", prompt)
        self.assertIn("visually split from neck opening to waist", prompt)
        self.assertIn("at least twelve narrow horizontal rows", prompt)
        self.assertIn("The chest is an edge-to-edge flexible field", prompt)
        self.assertIn("Role identity comes only from rows", prompt)
        self.assertIn("strictly matte lacquered kozane rows", prompt)
        self.assertIn("from shoulder to hip", prompt)
        self.assertIn("chest and limbs show only small laced rows", prompt)
        self.assertIn("Samurai hand equipment is limited to empty hands", prompt)
        self.assertIn("odoshi cord lanes", prompt)
        self.assertNotIn("plain material surfaces with rivets", prompt)
        self.assertNotIn("leather or lacquer surfaces, rivets", prompt)
        self.assertNotIn("lamellar plates", prompt.lower())
        self.assertIn("dirt road or path ground and open sky remain readable", prompt)
        self.assertIn("Roofline and sky gaps contain only open air", prompt)
        self.assertIn("Small facade repairs, lintel repairs", prompt)
        self.assertIn("Door and threshold hardware appears as large hanging wooden or dark pull rings", prompt)
        self.assertIn("Door faces are continuous plank or panel material", prompt)
        self.assertIn("Clothing and role-equipment surfaces stay broad material forms", prompt)
        self.assertIn("Unnamed chest, sleeve, shoulder, waist, and back areas", prompt)
        self.assertIn("The visible chest inventory is closed", prompt)
        self.assertIn("Both left and right upper-chest fields are broad continuous blank", prompt)
        self.assertIn("empty fabric-detail zone", prompt)
        self.assertIn("Upper-chest contrast stays low and continuous", prompt)
        self.assertIn("Scene-unnamed heraldry inventory is empty", prompt)
        self.assertIn("identity marks do not appear on chest", prompt)
        self.assertIn("Political, faction, court, clan, and rank identity never appears", prompt)
        self.assertIn("Angular high-contrast patches, colored applique plates", prompt)
        self.assertIn("Clothing visible detail is closed", prompt)
        self.assertIn("Fine clothing texture stays low-contrast", prompt)
        self.assertIn("Belt-adjacent inventory is closed", prompt)
        self.assertIn("gear straps integrated into the surrounding fabric", prompt)
        self.assertIn("FINAL CLOTHING SURFACE LOCK", prompt)
        self.assertIn("Cloth upper-body surfaces are broad blank textile", prompt)
        self.assertNotIn("Do not add chest badges", prompt)
        self.assertNotIn("round orange badges", prompt)
        self.assertNotIn("tiny chest crest", prompt)
        self.assertNotIn("isolated colored square", prompt)
        self.assertNotIn("paired square robe marks", prompt)
        self.assertNotIn("garment patches", prompt)
        self.assertNotIn("fabric patches", prompt)
        self.assertIn("chest badge", negative)
        self.assertIn("diamond mark", negative)
        self.assertIn("fake mon", negative)
        self.assertIn("round badge", negative)
        self.assertIn("colored chest dot", negative)
        self.assertIn("square clothing patch", negative)
        self.assertIn("twin square robe marks", negative)
        self.assertIn("kamon", negative)
        self.assertIn("chest mon", negative)
        self.assertIn("small decorative chest symbol", negative)
        self.assertIn("upper chest mark", negative)
        self.assertIn("white fan-shaped chest mark", negative)
        self.assertIn("white hand-shaped robe mark", negative)
        self.assertIn("left chest emblem", negative)
        self.assertIn("chest-corner mark", negative)
        self.assertIn("flower-shaped chest mark", negative)
        self.assertIn("small flower on robe", negative)
        self.assertIn("hanging tag", negative)
        self.assertIn("belt tag", negative)
        self.assertIn("small white glyph", negative)
        self.assertIn("coat of arms", negative)
        self.assertIn("heraldic shield patch", negative)
        self.assertIn("shield-shaped chest patch", negative)
        self.assertIn("red white chest crest", negative)
        self.assertIn("embroidered shield badge", negative)
        self.assertIn("floral robe pattern", negative)
        self.assertIn("flat paper on table", negative)
        self.assertIn("writing on scroll exterior", negative)
        self.assertIn("ink rows on petition roll", negative)
        self.assertIn("fluorescent ceiling panel", negative)
        self.assertIn("wall scroll", negative)
        self.assertIn("Kyoto gate", prompt)
        self.assertNotIn("SELECTED PERIOD WEAPON LOCK", prompt)
        self.assertNotIn("SINGLE CHARACTER LOCK", prompt)
        self.assertNotIn("ORDINARY HUMAN VISIBLE SET LOCK", prompt)
        self.assertNotIn("extreme solo face-only close-up", prompt)
        self.assertNotIn("tachi", prompt.lower())
        self.assertNotIn("grips his tachi", prompt)
        self.assertIn("Gate header zones, door headers, lintel centers", prompt)
        self.assertIn("Plaster walls show large empty fields of plain material", prompt)
        self.assertIn("cracks are sparse, uneven, branching or diagonal lines", prompt)
        self.assertIn("Image corners, lower wall zones", prompt)
        self.assertIn("All four image corners remain ordinary background material", prompt)
        self.assertIn("Tiny clustered strokes in those areas resolve", prompt)
        self.assertIn("corner seal stamp", negative)
        self.assertIn("artist chop", negative)
        self.assertNotIn("plain short iron swords", prompt)
        self.assertIn("Plain historical surfaces", local_prompt)
        self.assertIn("Plaster walls show large empty fields of plain material", local_prompt)
        self.assertIn("Image corners, lower wall zones", local_prompt)
        self.assertIn("Medium-close setting-inclusive single-character story illustration", local_prompt)
        self.assertIn("small off-center edge-on or furled blank cloth strip", local_prompt)
        self.assertIn("full front face of the cloth is turned away from camera", local_prompt)
        self.assertIn("Medieval Japanese material culture", local_prompt)
        self.assertIn("Medieval Japanese kozane visible set", local_prompt)
        self.assertIn("rectangular sode shoulder panels attached to the shoulders", local_prompt)
        self.assertIn("two large laced rectangular sode shoulder panels", local_prompt)
        self.assertIn("dominate the shoulder silhouette as external hanging laced panels", local_prompt)
        self.assertIn("flexible do-maru or haramaki wrap", local_prompt)
        self.assertIn("full chest front is an edge-to-edge laced kozane field", local_prompt)
        self.assertIn("overlapping-scale lacing pattern from neck opening to waist", local_prompt)
        self.assertIn("at least twelve horizontal overlapping scale rows", local_prompt)
        self.assertIn("dense overlapping scales and cord lanes", local_prompt)
        self.assertIn("Chest surfaces are material-only matte rows", local_prompt)
        self.assertIn("Samurai hand equipment is limited to empty hands", local_prompt)
        self.assertNotIn("plain material surfaces with rivets", local_prompt)
        self.assertNotIn("leather or lacquer surfaces, rivets", local_prompt)
        self.assertNotIn("lamellar plates", local_prompt.lower())
        self.assertIn("dirt road or path ground and open sky remain readable", local_prompt)
        self.assertIn("Roofline and sky gaps contain only open air", local_prompt)
        self.assertIn("Small facade repairs, lintel repairs", local_prompt)
        self.assertIn("Door and threshold hardware appears as large hanging wooden or dark pull rings", local_prompt)
        self.assertIn("Door faces are continuous plank or panel material", local_prompt)
        self.assertIn("Clothing and role-equipment surfaces stay broad material forms", local_prompt)
        self.assertIn("The visible chest inventory is closed", local_prompt)
        self.assertIn("Both left and right upper-chest fields", local_prompt)
        self.assertIn("empty fabric-detail zone", local_prompt)
        self.assertIn("Upper-chest contrast stays low and continuous", local_prompt)
        self.assertIn("Scene-unnamed heraldry inventory is empty", local_prompt)
        self.assertIn("Clothing visible detail is closed", local_prompt)
        self.assertIn("Fine clothing texture stays", local_prompt)
        self.assertIn("Belt-adjacent inventory is closed", local_prompt)
        self.assertIn("gear straps integrated into the surrounding fabric", local_prompt)
        self.assertIn("FINAL CLOTHING SURFACE LOCK", local_prompt)
        self.assertIn("Cloth upper-body surfaces are broad blank textile", local_prompt)
        self.assertNotIn("Do not add chest badges", local_prompt)
        self.assertNotIn("round orange badges", local_prompt)
        self.assertNotIn("tiny chest crest", local_prompt)
        self.assertNotIn("isolated colored square", local_prompt)
        self.assertNotIn("paired square robe marks", local_prompt)
        self.assertNotIn("garment patches", local_prompt)
        self.assertNotIn("fabric patches", local_prompt)
        self.assertIn("All four image corners remain ordinary background material", local_prompt)
        self.assertNotIn("extreme face-only close-up", local_prompt.lower())
        self.assertNotIn("GROUP CHARACTER COMPOSITION LOCK", prompt)
        self.assertIn("side-facing or back-facing wind-folded cloth strips", prompt)
        self.assertIn("full front face of the cloth is turned away from camera", prompt)
        self.assertNotIn("warrior banners", prompt.lower())
        self.assertNotIn("sign-like", prompt.lower())
        self.assertNotIn("wall plaque", prompt.lower())

    def test_statue_scene_stays_inanimate_object_not_living_portrait(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 525 BCE; Exact place: dark temple in Egypt; "
                "Scene: a beautiful golden statue of the goddess Bastet, half-woman, half-cat, glowing in a dark temple; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("INANIMATE STATUE OBJECT LOCK", prompt)
        self.assertIn("first visible subject: the inanimate statue", prompt)
        self.assertIn("OBJECT-LOCATION PRIMARY SUBJECT LOCK", prompt)
        self.assertIn("one coherent physical object", prompt)
        self.assertNotIn("SINGLE CHARACTER LOCK", prompt)
        self.assertNotIn("CHARACTER COMPOSITION LOCK", prompt)
        self.assertNotIn("HUMAN FACE SURFACE LOCK", prompt)
        self.assertIn("Inanimate statue object evidence illustration", local_prompt)
        self.assertIn("sculpted human and animal features fused into the same object surface", local_prompt)
        self.assertNotIn("extreme solo face-only close-up", local_prompt.lower())

    def test_people_bowing_to_statue_remains_people_scene(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 525 BCE; Exact place: temple courtyard in Egypt; "
                "Scene: Egyptian priests bowing respectfully beside a golden statue of Bastet; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("GROUP CHARACTER COMPOSITION LOCK", prompt)
        self.assertIn("HUMAN FACE SURFACE LOCK", prompt)
        self.assertNotIn("INANIMATE STATUE OBJECT LOCK", prompt)

    def test_temple_beam_surfaces_are_blank_structural_bands(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 525 BCE; Exact place: grand temple courtyard in Egypt; "
                "Scene: Egyptian priests bowing respectfully to a group of cats in a grand temple courtyard; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("Temple lintels, friezes, column headers", prompt)
        self.assertIn("blank structural surfaces", prompt)
        self.assertIn("Cartouche-shaped, raised-oval, or panel-shaped details resolve as irregular same-material", prompt)
        self.assertIn("temple lintels, friezes, column headers", local_prompt)
        self.assertIn("wide rectangular architectural bands are blank structural surfaces", local_prompt)

    def test_medieval_japanese_samurai_scene_removes_shields(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1336; Early Nanboku-cho conflict; "
                "Exact place: Kyushu field camp; "
                "Scene: samurai guards carrying shields while Takauji watches; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("PERIOD-LOCAL JAPANESE MARTIAL CLOTHING LOCK", prompt)
        self.assertIn("MARTIAL ROLE CLOTHING VISIBLE SET LOCK", prompt)
        self.assertIn("period-local warrior clothing", prompt)
        self.assertIn("empty off-hands", prompt)
        self.assertNotIn("shield", prompt.lower())
        self.assertNotIn("shield", local_prompt.lower())

    def test_medieval_japanese_floor_map_uses_blank_strategy_board_before_room(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: c. 1336-1392; Nanboku-cho period, late medieval Japan; "
                "Exact place: symbolic court chamber between Kyoto and Yoshino; "
                "Scene: two dim court lamps pull apart across a blank floor map "
                "as armored retainers recoil in confusion; Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("first visible subject: the requested strategic planning evidence", prompt)
        self.assertIn("physically unmarked", prompt)
        self.assertIn("Lower-left, lower-right, bottom, and corner zones", prompt)
        self.assertIn("unmarked marker objects only, with empty surrounding edges", prompt)
        self.assertIn("Off-screen pressure appears only through lamp light", prompt)
        self.assertIn("off-screen pressure shown only through lamp light", prompt)
        self.assertIn("unoccupied object-only tabletop", prompt)
        self.assertIn("visible subject inventory is only the low surface", prompt)
        self.assertIn("camera crop stays on the low surface", prompt)
        self.assertIn("low horizontal tactile marker layout", prompt)
        self.assertIn("at least one loose route cord", prompt)
        self.assertIn("EMPTY EVIDENCE FRAME LOCK", prompt)
        self.assertIn("HARD HISTORICAL OBJECT EVIDENCE MATERIAL CULTURE LOCK", prompt)
        self.assertIn("OBJECT PHYSICAL COMMON-SENSE LOCK", prompt)
        self.assertIn("Lamp bases, metal rims, bronze weights", prompt)
        self.assertNotIn("HARD HISTORICAL CIVILIAN MATERIAL CULTURE LOCK", prompt)
        self.assertNotIn("complete visible human role set", prompt)
        self.assertNotIn("Choose visible clothing cuts", prompt)
        self.assertNotIn("COMMON-SENSE ANATOMY LOCK", prompt)
        self.assertNotIn("ROLE EQUIPMENT COMMON-SENSE LOCK", prompt)
        self.assertNotIn("DYNAMIC ACTION AND EMOTION LOCK", prompt)
        self.assertNotIn("sharp faces", prompt)
        self.assertNotIn("facial acting", prompt)
        self.assertNotIn("Every robed or cloth-clothed human", prompt)
        self.assertNotIn("ORDINARY HUMAN VISIBLE SET LOCK", prompt)
        self.assertNotIn("FORMAL ROLE AND SETTING LAYOUT LOCK", prompt)
        self.assertNotIn("ARMORED ROLE VISIBLE SET LOCK", prompt)
        self.assertNotIn("HISTORICAL BUILDING HARDWARE LOCK", prompt)
        self.assertNotIn("vertical room walls", prompt)
        self.assertNotIn("doorways stay outside", prompt)
        self.assertNotIn("frame rails", prompt.lower())
        self.assertNotIn("retainers recoil in confusion", prompt.lower())
        self.assertNotIn("simple cartoon", prompt.lower())

    def test_group_floor_plan_uses_blank_planning_surface_with_people(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: c. 1340-1360; Nanboku-cho period, Southern Court resistance; "
                "Exact place: Yoshino temple hall; "
                "Scene: Robed courtiers and armored allies lean over a blank floor plan in a candlelit temple hall; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("PRIMARY IMAGE LOCK - first visible subject: the shared council planning evidence", prompt)
        self.assertIn("GROUP PLANNING SURFACE LOCK", prompt)
        self.assertIn("blank low horizontal planning surface with loose route cords", prompt)
        self.assertIn("at least seven separated stone markers", prompt)
        self.assertIn("loose route cords crossing three separated marker clusters", prompt)
        self.assertIn("Full faces, heads, shoulders, full torsos, and full people stay outside", prompt)
        self.assertIn("cropped hands, fingertips, sleeves, forearm edges, and hand shadows", prompt)
        self.assertIn("full frame edge to edge", prompt)
        self.assertIn("steep top-down tabletop or floor-surface evidence crop", prompt)
        self.assertIn("Steep top-down tabletop evidence crop", prompt)
        self.assertIn("low side candle or oil lamp light", prompt)
        self.assertNotIn("HISTORICAL BUILDING HARDWARE LOCK", prompt)
        self.assertNotIn("PERIOD LAMP PLACEMENT LOCK", prompt)
        self.assertIn("planning surface is filled by movable marker objects", prompt)
        self.assertIn("palm-sized bronze weight or pin", prompt)
        self.assertNotIn("floor plan", prompt.lower())
        self.assertNotIn("flat paper", prompt.lower())
        self.assertIn("camera sees only the horizontal planning surface plane", prompt)
        self.assertIn("never leaves the surface plane", prompt)
        self.assertNotIn("background walls, windows, doorways, and ceiling stay outside the frame", prompt)
        self.assertNotIn("Ceiling areas remain dark rafters", prompt)
        self.assertIn("table or floor surface stays bare period material", prompt)
        self.assertNotIn("HISTORICAL HUMAN CLOTHING LOCK", prompt)
        self.assertNotIn("ARMORED ROLE VISIBLE SET LOCK", prompt)
        self.assertNotIn("FINAL CLOTHING SURFACE LOCK", prompt)
        self.assertNotIn("EMPTY EVIDENCE FRAME LOCK", prompt)
        self.assertIn("HARD HISTORICAL OBJECT EVIDENCE MATERIAL CULTURE LOCK", prompt)
        self.assertNotIn("HUMAN-SCALE GEOGRAPHY LOCK", prompt)
        self.assertNotIn("CONTINUOUS SCENE LOCK", prompt)
        self.assertNotIn("OUTDOOR LOCATION EVIDENCE LOCK", prompt)
        self.assertIn("fake writing on plan", negative)
        self.assertIn("open paper floor plan with writing", negative)
        self.assertIn("empty planning table", negative)
        self.assertIn("empty room with lamp", negative)
        self.assertIn("fluorescent light above table", negative)
        self.assertIn("wall switch", negative)
        self.assertIn("electrical outlet", negative)
        self.assertIn("paper sheets on planning table", negative)
        self.assertIn("flat paper sheets on table", negative)
        self.assertIn("full faces around planning surface", negative)
        self.assertIn("room wall behind planning table", negative)
        self.assertIn("drawn route lines without cords", negative)
        self.assertIn("small square mark on armor", negative)
        self.assertIn("armor chest patch", negative)
        self.assertIn("coat of arms", negative)
        self.assertIn("shield-shaped chest patch", negative)
        self.assertIn("red white chest crest", negative)
        self.assertIn("FIRST IMAGE COMPOSITION LOCK: group council planning scene", local_prompt)
        self.assertIn("steep top-down tabletop or floor-surface evidence camera", local_prompt)
        self.assertIn("The camera never leaves the horizontal planning surface", local_prompt)
        self.assertIn("marker objects with clear blank material gaps", local_prompt)
        self.assertIn("at least seven separated stone markers", local_prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        self.assertTrue(comfy_prompt.startswith("TEXTLESS SURFACE FIRST RULE"))
        self.assertIn("ABSOLUTE FIRST VISUAL SUBJECT - GROUP PLANNING SURFACE", comfy_prompt)
        self.assertIn("no kanji, no kana, no hanzi", comfy_prompt)
        self.assertIn("three thick loose route cords", comfy_prompt)
        self.assertIn("Natural cracks, wood grain, scratches, stains", comfy_prompt)
        self.assertIn("do not count as route cords", comfy_prompt)
        self.assertIn("No white paper sheet", comfy_prompt)
        self.assertIn("Render a compact tactile council-planning evidence shot", comfy_prompt)
        self.assertIn("empty table with hands", comfy_negative)
        self.assertIn("cracks standing in for route cords", comfy_negative)
        self.assertIn("white rectangular paper sheet", comfy_negative)
        self.assertNotIn("Background walls, windows, doorways, and ceiling", local_prompt)
        self.assertNotIn("upper frame crops below the ceiling center", local_prompt)
        self.assertNotIn("flat paper", local_prompt.lower())

    def test_medieval_japanese_context_adds_wrong_armor_negative(self):
        prompt = (
            "Year/period: 1336; Nanboku-cho period, late medieval Japan; "
            "Exact place: Kyoto; Scene: armored retainers recoil in confusion"
        )

        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)

        self.assertIn("smooth metal breastplate", negative)
        self.assertIn("ornate metal shoulder guards", negative)
        self.assertIn("glossy black breastplate", negative)
        self.assertIn("metal gauntlets", negative)
        self.assertIn("bronze armor", negative)
        self.assertIn("chest emblem", negative)
        self.assertIn("smooth brown chest plate", negative)
        self.assertIn("vest-like armor", negative)
        self.assertIn("gold chest design", negative)
        self.assertIn("gray steel lamellar", negative)

    def test_comfyui_common_historical_clothing_surface_lock_is_front_loaded(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: c. 1340-1360; Nanboku-cho period, provincial administration; "
                "Exact place: provincial shugo residence courtyard; "
                "Scene: Armed retainers rush across a broad dirt courtyard as a steward points toward nearby villages; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertTrue(comfy_prompt.startswith("TEXTLESS SURFACE FIRST RULE"))
        self.assertIn("VISIBLE CLOTHING SURFACE FIRST RULE", comfy_prompt)
        self.assertIn("no kanji, no kana, no hanzi", comfy_prompt)
        self.assertIn("especially the upper-left sky or tree corner", comfy_prompt)
        self.assertIn("No crest, no mon, no family mark", comfy_prompt)
        self.assertIn("no small white flower mark", comfy_prompt)
        self.assertIn("repeated matching chest symbol", comfy_prompt)
        self.assertIn("Plain unmarked historical martial-clothing action illustration", comfy_prompt)
        self.assertIn("Avoid large readable front-facing chest panels", comfy_prompt)
        self.assertIn("Do not place any small mark on left chest", comfy_prompt)
        self.assertIn("Open sky, roof gaps, and mountain haze contain no overhead wires", comfy_prompt)
        self.assertIn("small white flower mark on robe", comfy_negative)
        self.assertIn("black leaf mark on robe", comfy_negative)
        self.assertIn("red shield chest crest", comfy_negative)
        self.assertIn("matching robe emblems", comfy_negative)
        self.assertIn("thin black cable across sky", comfy_negative)
        self.assertIn("bottom-edge glyph row", comfy_negative)
        self.assertIn("kanji on door", comfy_negative)
        self.assertIn("upper-left corner characters", comfy_negative)

    def test_medieval_japanese_armored_guards_rewrite_away_from_generic_plate_terms(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Global visual world: Material culture: layered court robes, "
                "practical warrior armor, swords, bows; "
                "Year/period: c. 1336-1340; Nanboku-cho period, Northern Court in Kyoto; "
                "Exact place: Kyoto palace compound; "
                "Scene: A palace lamp flares behind wooden shutters while armored guards hurry through the moonlit gate; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("guards in dull dark-brown matte lacquered kozane rows", prompt)
        self.assertIn("strictly matte lacquered kozane rows", prompt)
        self.assertIn("The chest is an edge-to-edge flexible field", prompt)
        self.assertIn("Role identity comes only from rows", prompt)
        self.assertNotIn("practical warrior armor", prompt)
        self.assertNotIn("armored guards", prompt)
        self.assertNotIn("samurai armor silhouette", prompt)
        self.assertNotIn("armor sleeves", prompt)
        self.assertNotIn("bronze, iron", prompt)
        self.assertNotIn("round rivets", prompt)
        self.assertNotIn("simple solid geometric crests", prompt)
        local_prompt = _enrich_local_v1_positive_prompt(prompt)
        self.assertIn("Chest surfaces are material-only", local_prompt)
        self.assertIn("matte surface wear", local_prompt)

    def test_medieval_japanese_generic_guards_use_clothing_not_forced_armor(self):
        for scene in (
            "Court nobles in layered robes raise plain ritual objects as warriors outside the shutters exchange uneasy looks",
            "A small palanquin and court attendants struggle up a wet cedar road while guards scan the slopes",
        ):
            prompt = prompt_builder.build_image_prompt(
                (
                    "Global visual world: Material culture: layered court robes, "
                    "practical warrior armor, swords, bows; "
                    "Year/period: c. 1336; Nanboku-cho period, late medieval Japan; "
                    "Exact place: Kyoto and Yoshino; "
                    f"Scene: {scene}; "
                    "Style: simple cartoon illustration"
                ),
                "simple cartoon illustration",
                enable_historical_guard=True,
            )
            local_prompt = _enrich_local_v1_positive_prompt(prompt)

            if "palanquin" in scene:
                self.assertIn("PERIOD-LOCAL JAPANESE MARTIAL CLOTHING LOCK", prompt)
                self.assertIn("MARTIAL ROLE CLOTHING VISIBLE SET LOCK", prompt)
                self.assertIn("material-only soft textile folds", prompt)
                self.assertIn("plain transport materials", local_prompt)
                self.assertNotIn("ORDINARY HUMAN VISIBLE SET LOCK", prompt)
            else:
                self.assertIn("PERIOD-LOCAL JAPANESE MARTIAL CLOTHING LOCK", prompt)
                self.assertIn("MARTIAL ROLE CLOTHING VISIBLE SET LOCK", prompt)
                self.assertIn("hitatare, kosode, hakama", prompt)
                self.assertIn("stay material-only soft textile folds", local_prompt)
            self.assertNotIn("PERIOD-LOCAL JAPANESE COSTUME AND ARMOR LOCK", prompt)
            self.assertNotIn("ARMORED ROLE VISIBLE SET LOCK", prompt)
            self.assertNotIn("ARMED BODY VISIBLE SET LOCK", local_prompt)

    def test_palanquin_surfaces_are_blank_transport_materials(self):
        source = (
            "Year/period: c. 1336-1337; Nanboku-cho period, early Southern Court; "
            "Exact place: mountain road toward Yoshino; "
            "Scene: A small palanquin and court attendants struggle up a wet cedar road while guards scan the slopes; "
            "Style: simple cartoon illustration"
        )
        prompt = prompt_builder.build_image_prompt(
            source,
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)

        self.assertIn("PRIMARY IMAGE LOCK - first visible subject: the Scene-named shoulder-borne carried litter", prompt)
        self.assertIn("CARRIED LITTER EVIDENCE LOCK", prompt)
        self.assertIn("covered carried litter", prompt)
        self.assertIn("long shoulder poles resting on cropped support-walker shoulders", prompt)
        self.assertIn("two parallel pole lines as the only support structure", prompt)
        self.assertIn("Two long parallel shoulder poles are the only support structure", prompt)
        self.assertIn("lower cabin edge is cropped or held high in open air", prompt)
        self.assertIn("lower third empty except shadow gap", prompt)
        self.assertIn("The visible load path is pole-to-shoulder-to-hand only", prompt)
        self.assertIn("shoulder-borne litter close crop", prompt)
        self.assertIn("load-bearing evidence appears as cropped shoulder contact", prompt)
        self.assertIn("upper chest fronts stay outside the readable frame", prompt)
        self.assertIn("litter close crop", prompt)
        self.assertIn("Suspension reads from horizontal shoulder poles", prompt)
        self.assertIn("Every visible support fragment is anatomically connected", prompt)
        self.assertIn("shoulder, sleeve, and hand align under the same pole load", prompt)
        self.assertIn("Walking lower legs or feet appear only as tiny cropped hints", prompt)
        self.assertNotIn("lower leg or foot aligns below the load", prompt)
        self.assertIn("Carrier and escort torsos use side, back, rear three-quarter", prompt)
        self.assertIn("robe front reduced to a narrow moving edge", prompt)
        self.assertIn("support walkers stay behind poles", prompt)
        self.assertIn("staggered depth", prompt)
        self.assertIn("Load-bearing proof belongs to shoulder and hand contact", prompt)
        self.assertIn("The carried litter remains the main carried subject", prompt)
        self.assertIn("Covered litter bodies, carried-chair roofs, canopy boards", prompt)
        self.assertIn("plain transport materials only", prompt)
        self.assertIn("FINAL CLOTHING SURFACE LOCK", prompt)
        self.assertIn("Cloth upper-body surfaces are broad blank textile", prompt)
        self.assertIn("Carried litter story frame", local_prompt)
        self.assertIn("shoulder-borne palanquin, covered carried litter", local_prompt)
        self.assertIn("Two long parallel shoulder poles are the only support structure", local_prompt)
        self.assertIn("lower cabin edge is cropped or held high in open air", local_prompt)
        self.assertIn("The lower third contains only empty shadow gap", local_prompt)
        self.assertIn("visible load path is pole-to-shoulder-to-hand only", local_prompt)
        self.assertIn("shoulder-borne litter close crop", local_prompt)
        self.assertIn("load-bearing contact evidence", local_prompt)
        self.assertIn("upper chest fronts stay outside the readable frame", local_prompt)
        self.assertIn("litter close crop", local_prompt)
        self.assertIn("Suspension reads from horizontal shoulder poles", local_prompt)
        self.assertIn("Every visible support fragment is anatomically connected", local_prompt)
        self.assertIn("shoulder, sleeve, and hand align under the same pole load", local_prompt)
        self.assertIn("Walking lower legs or feet appear only as tiny cropped hints", local_prompt)
        self.assertNotIn("lower leg or foot aligns below the load", local_prompt)
        self.assertIn("Carrier and escort torsos use side, back, rear three-quarter", local_prompt)
        self.assertIn("robe front reduced to a narrow moving edge", local_prompt)
        self.assertIn("support walkers stay behind poles", local_prompt)
        self.assertIn("staggered depth", local_prompt)
        self.assertIn("Load-bearing proof belongs to shoulder and hand contact", local_prompt)
        self.assertIn("carried litter remains the main carried subject", local_prompt)
        self.assertIn("Covered litter bodies, carried-chair roofs, canopy boards", local_prompt)
        self.assertIn("FINAL CLOTHING SURFACE LOCK", local_prompt)
        self.assertIn("Cloth upper-body surfaces are broad blank textile", local_prompt)
        forbidden_positive_terms = (
            "Do not",
            "no gold designs",
            "no breastplate",
            "crest",
            "badge",
            "kamon",
            "chest mon",
            "robe mon",
            "flower-shaped chest mark",
            "small flower on robe",
            "front-row clothing display",
            "round orange badges",
            "Tiny high-contrast shapes",
            "tiny chest crest",
            "white floral mark",
        )
        for term in forbidden_positive_terms:
            self.assertNotIn(term, prompt)
            self.assertNotIn(term, local_prompt)
        self.assertNotIn("wheel", prompt.lower())
        self.assertNotIn("axle", prompt.lower())
        self.assertNotIn("cart frame", prompt.lower())
        self.assertNotIn("wagon", prompt.lower())
        self.assertIn("palanquin signboard", negative)
        self.assertIn("kanji on palanquin", negative)
        self.assertIn("wheeled palanquin", negative)
        self.assertIn("axle under palanquin", negative)
        self.assertIn("two-wheeled cart", negative)
        self.assertIn("cart shafts", negative)
        self.assertIn("ground-rolling cabin", negative)
        self.assertIn("full undercarriage", negative)
        self.assertIn("cabin base touching road", negative)
        self.assertIn("pavilion cart", negative)
        self.assertIn("wheeled hut", negative)
        self.assertIn("round support under litter", negative)
        self.assertIn("cropped bearer legs", negative)
        self.assertIn("front-facing palanquin procession", negative)
        self.assertIn("chest crests on palanquin bearers", negative)
        self.assertIn("carried cabin standing on ground posts", negative)
        self.assertIn("foreground walking row not touching shoulder poles", negative)

        final = _append_local_v1_final_composition_suffix(
            local_prompt,
            group_character=True,
            object_only=False,
        )
        self.assertIn("carried litter side evidence shot", final)
        self.assertIn("load-bearing contact is readable", final)
        self.assertIn("lower third contains only empty shadow gap", final)
        self.assertIn("visible load path is pole-to-shoulder-to-hand only", final)
        self.assertNotIn("close group story shot", final)

        flux_like_final = _append_common_carried_transport_final_suffix(local_prompt)
        self.assertIn("FINAL COMPOSITION PRIORITY: carried litter side evidence shot", flux_like_final)
        self.assertIn("lower third contains only empty shadow gap", flux_like_final)
        self.assertIn("visible load path is pole-to-shoulder-to-hand only", flux_like_final)

    def test_litter_verb_does_not_become_carried_litter_vehicle(self):
        source = (
            "Year/period: 1598; Final year of the Korean campaigns, 1598; "
            "Exact place: cold Korean coastal camp; "
            "Scene: Exhausted soldiers huddle around a weak fire as broken crates "
            "and wet armor litter the camp.; "
            "Style: simple cartoon illustration"
        )

        normalized = prompt_builder._normalize_travel_vehicle_scene_language(source)
        scene = normalized.split("Scene:", 1)[1].split("; Style:", 1)[0]

        self.assertIn("wet armor litter the camp", scene)
        self.assertNotIn("shoulder-borne covered carried litter", scene)
        self.assertNotIn("shoulder-borne litter close crop", scene)

    def test_edo_townspeople_do_not_become_joseon_invasion_news_scene(self):
        source = (
            "Year/period: 1603; Early Tokugawa Edo town life; "
            "Exact place: early Edo castle town street; "
            "Scene evidence: Early peace did not erase memories of the recent war.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: townspeople passing a returning veteran; "
            "Scene: Townspeople step around a quiet veteran carrying worn armor "
            "through a newly ordered street."
        )

        contract = _flux2_klein_md_positive_contract(source, source)

        self.assertIn("Scene subject: townspeople passing a returning veteran", contract)
        self.assertIn("quiet veteran carrying worn armor", contract)
        self.assertNotIn("Joseon townspeople startled by invasion news", contract)
        self.assertNotIn("breathless robed messenger", contract)

    def test_flux2_klein_md_reports_become_blank_packet_bundles(self):
        source = (
            "Year/period: 1592-1598; Azuchi-Momoyama Japan during Korean campaigns; "
            "Exact place: Tokugawa residence in eastern Japan; "
            "Scene evidence: Ieyasu did not cross to the Korean battlefield.; "
            "Main subject: Ieyasu reading reports at home; "
            "Scene: Ieyasu reads war reports in a quiet residence while armed retainers stand ready behind him."
        )

        contract = _flux2_klein_md_positive_contract(source, source)

        self.assertIn("studies sealed cloth-wrapped packet bundles tied shut with cord", contract)
        self.assertIn("extreme tabletop close crop", contract)
        self.assertIn("background walls, doorway, roof beams, hanging wall panels", contract)
        self.assertNotIn("reads war reports", contract)
        self.assertNotIn("reading reports", contract)

    def test_flux2_klein_md_route_papers_become_physical_markers(self):
        source = (
            "Year/period: 1603; Early Tokugawa Japan reflecting on Toyotomi expansion; "
            "Exact place: Edo council chamber with stored armor; "
            "Scene evidence: The scene contrasts domestic consolidation with overseas expansion.; "
            "Main subject: stored armor beside administrative tools; "
            "Scene: Armor is locked away as officials unroll plain domestic route papers in a calm chamber."
        )

        contract = _flux2_klein_md_positive_contract(source, source)

        self.assertIn("object-only tabletop evidence of stored armor and sealed route materials", contract)
        self.assertIn("bare wooden tabletop evidence close-up in early Tokugawa administrative storage context", contract)
        self.assertIn("sealed cloth-wrapped packet bundles, cord knots, stone route markers, and armor edge lie", contract)
        self.assertIn("object-only tabletop close crop", contract)
        self.assertIn("living people, hands, wrists, clothing fronts", contract)
        self.assertNotIn("route papers", contract)
        self.assertNotIn("officials set down", contract)
        self.assertNotIn("Edo council chamber", contract)

    def test_flux2_klein_md_edo_veteran_artisan_street_blocks_signs_and_wires(self):
        source = (
            "Global visual world: Time range: 1592-1603; "
            "Culture scope: Azuchi-Momoyama Japan shifting into early Tokugawa Japan, Toyotomi Japan, Korean captives and artisans; "
            "Year/period: 1603; Early Tokugawa Japan, postwar peace beginning; "
            "Exact place: quiet Edo street at dawn; "
            "Scene evidence: The new order began while postwar burdens remained.; "
            "Main subject: dawn street with veteran and artisan; "
            "Scene: A veteran and a potter pass each other at dawn, both carrying traces of the same war."
        )

        contract = _flux2_klein_md_positive_contract(source, source)

        self.assertIn("postwar veteran and artisan crossing an open Edo outskirts dawn lane", contract)
        self.assertIn("potter in plain kosode robe, hakama, cloth sash, tied hair, straw sandals", contract)
        self.assertIn("low blank wooden fence rails", contract)
        self.assertIn("sky, empty road, low fences, smoke, and reeds dominate", contract)
        self.assertNotIn("utility poles", contract)
        self.assertNotIn("overhead wires", contract)

    def test_medieval_japanese_court_figure_does_not_seed_armor_lock(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Global visual world: Material culture: layered court robes, "
                "practical warrior armor, swords, bows; "
                "Year/period: c. 1336; Nanboku-cho period, early Southern Court; "
                "Exact place: dim temporary court interior near Yoshino; "
                "Scene: Emperor Go-Daigo is introduced as the central figure of the Southern Court; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("PERIOD-LOCAL JAPANESE COURT AND CIVILIAN COSTUME LOCK", prompt)
        self.assertNotIn("PERIOD-LOCAL JAPANESE COSTUME AND ARMOR LOCK", prompt)
        self.assertIn("without invented armor", prompt)

    def test_non_japanese_shield_scene_keeps_source_shields(self):
        cleaned = _enforce_local_armed_figure_loadout_prompt(
            (
                "Year/period: 525 BCE; Exact place: Pelusium, Egypt; "
                "Scene: Persian soldiers carry cats as shields while Egyptian defenders hesitate; "
                "Style: simple cartoon illustration"
            )
        )

        self.assertIn("cats as shields", cleaned.lower())

    def test_achaemenid_egyptian_scene_gets_period_local_material_lock(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 525 BC; Exact place: Pelusium, Nile Delta, Egypt; "
                "Scene: Persian soldiers advance with wicker shields while Egyptian defenders hesitate near papyrus reeds; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("PERIOD-LOCAL ACHAEMENID PERSIAN AND EGYPTIAN MATERIAL CULTURE LOCK", prompt)
        self.assertIn("When the Scene names Persian soldiers or commanders", prompt)
        self.assertIn("wicker shields", prompt)
        self.assertIn("Egyptian defenders use linen upper wraps", prompt)
        self.assertIn("Nile Delta mudbrick walls", prompt)
        self.assertIn("Broad chest areas display cloth tunics", prompt)
        self.assertIn("the torso silhouette stays straight, flat, matte, and textile-based", prompt)
        self.assertNotIn("light scale corselets", prompt)
        self.assertNotIn("leather scale rows", prompt)
        self.assertNotIn("small sewn scale rows", prompt)
        self.assertNotIn("dense small scale rows", prompt)
        self.assertNotIn("short swords", prompt)
        self.assertNotIn("bronze trim", prompt)
        self.assertIn("ACHAEMENID EGYPTIAN ARMED GROUP COMPOSITION LOCK", prompt)
        self.assertIn("staggered diagonal chest-up action cluster", prompt)
        self.assertIn("two compact opposing subgroups facing each other from left and right", prompt)
        self.assertIn("lower image edge crosses upper chest cloth", prompt)
        self.assertIn("exactly four readable foreground figures total", prompt)
        self.assertIn("background depth is dust haze, reeds, gate edges", prompt)
        self.assertIn("one visible weapon total per person", prompt)
        self.assertIn("selected handheld equipment item is the only weapon-shaped object", prompt)
        self.assertIn("lower image edge crosses high upper chest cloth", prompt)
        self.assertIn("one plain period shield per readable defender", prompt)
        self.assertNotIn("one plain short iron sword as the selected close chest-side prop", prompt)
        self.assertIn("Period-local Achaemenid Persian and Egyptian material culture", local_prompt)
        self.assertIn("Achaemenid Persian and Egyptian armed group composition", local_prompt)
        self.assertIn("soft fabric tunic shoulders, robe upper folds", local_prompt)
        self.assertIn("FIRST IMAGE COMPOSITION LOCK: staggered diagonal", local_prompt)
        self.assertIn("clear center collision zone", local_prompt)
        self.assertIn("selected handheld equipment item is the only weapon-shaped object", local_prompt)
        self.assertIn("broad chest areas made of cloth tunics", local_prompt)
        self.assertIn("the torso silhouette stays straight, flat, matte, and textile-based", local_prompt)
        self.assertIn("white linen upper wraps", local_prompt)
        self.assertIn("wicker shields", local_prompt)
        self.assertIn("one plain period shield per readable defender", local_prompt)
        self.assertNotIn("one plain short iron sword as the selected close chest-side prop", local_prompt)
        self.assertNotIn("light scale corselets", local_prompt)
        self.assertNotIn("leather scale rows", local_prompt)
        self.assertNotIn("small sewn leather scale rows", local_prompt)
        self.assertNotIn("dense small scale rows", local_prompt)
        self.assertNotIn("short swords", local_prompt)
        self.assertNotIn("bronze trim", local_prompt)
        self.assertNotIn("one representative foreground armored survivor", prompt)
        self.assertNotIn("Translate wide or crowded armed-group scenes into one representative", prompt)
        self.assertNotIn("translate the group into one representative", local_prompt)
        self.assertNotIn("PERIOD-LOCAL JAPANESE COSTUME AND ARMOR LOCK", prompt)
        self.assertNotIn("o-yoroi", local_prompt.lower())

    def test_achaemenid_marching_soldiers_preserve_formation_not_portrait(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 525 BC; Exact place: Pelusium desert approach, Nile Delta, Egypt; "
                "Scene: Persian soldiers marching in the desert toward Egyptian defenders; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)

        self.assertIn("ACHAEMENID EGYPTIAN ARMED GROUP COMPOSITION LOCK", prompt)
        self.assertIn("exactly four separated chest-up period-clothed figures", prompt)
        self.assertIn("exactly four readable foreground figures total", prompt)
        self.assertIn("Avoid a side-by-side row", prompt)
        self.assertIn("soft pointed caps or wrapped cloth headgear", prompt)
        self.assertIn("head-through-upper-chest scale", prompt)
        self.assertNotIn("ARMED ROLE PORTRAIT CROP LOCK", prompt)
        self.assertNotIn("one representative foreground armored survivor", prompt)
        self.assertIn("Achaemenid Persian and Egyptian armed group composition", local_prompt)
        self.assertNotIn("translate the group into one representative", local_prompt)
        self.assertIn("background soldiers", negative)
        self.assertIn("hilt at waist", negative)
        self.assertIn("weapon at hip", negative)

    def test_achaemenid_massive_armies_rewrite_to_cropped_four_figure_cluster(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 525 BC; Exact place: Pelusium (Ancient Egypt) & Achaemenid Persian Empire; "
                "Scene: cinematic wide shot, massive ancient armies clashing on a dusty desert battlefield, "
                "glowing sunset, dramatic shadows; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)

        self.assertIn("exactly four readable chest-up combat figures total", prompt)
        self.assertIn("all humans in the main foreground cluster", prompt)
        self.assertIn("tight close-up collision crop", prompt)
        self.assertIn("Render a tight close-up collision crop with exactly four readable chest-up combat figures total", prompt)
        self.assertIn("lower bodies outside the frame", prompt)
        self.assertIn("zero readable people behind the cluster", prompt)
        self.assertIn("frame-filling chest-up figures", prompt)
        self.assertIn("hips, thighs, knees, shins, legs, and feet are outside the image frame", prompt)
        self.assertLess(prompt.find("PRIMARY IMAGE LOCK"), prompt.find("UNMARKED SURFACE LOCK"))
        self.assertNotIn("massive ancient armies", prompt.lower())
        self.assertNotIn("cinematic wide shot", prompt.lower())
        self.assertNotIn("ancient soldiers", prompt.lower())
        self.assertIn("wide army shot", negative)
        self.assertIn("visible legs", negative)
        self.assertIn("full body soldiers", negative)
        self.assertIn("boots visible", negative)

    def test_achaemenid_stealth_past_sleeping_guards_stays_story_scene(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 525 BC; Exact place: Pelusium, Nile Delta, Egypt; "
                "Scene: Phanes sneaking away from sleeping, drunk Egyptian guards, moonlight shining on his path; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("PRIMARY IMAGE LOCK - first visible subject: the stealth escape story action", prompt)
        self.assertIn("the sneaking principal person is the only upright moving human figure", prompt)
        self.assertIn("STEALTH SLEEPING WATCHMEN STORY LOCK", prompt)
        self.assertIn("two open palms, visible relaxed fingers", prompt)
        self.assertIn("Every other human figure is a sleeping or drunk watchman", prompt)
        self.assertIn("every non-principal head stays below the principal person's waistline", prompt)
        self.assertNotIn("GROUP CHARACTER COMPOSITION LOCK", prompt)
        self.assertIn("Phanes sneaking along a moonlit path as the only upright moving figure", prompt)
        self.assertIn("sleeping drunk Egyptian watchmen lying horizontally", prompt)
        self.assertNotIn("ACHAEMENID EGYPTIAN ARMED GROUP COMPOSITION LOCK", prompt)
        self.assertNotIn("ARMED BODY VISIBLE SET LOCK", prompt)
        self.assertNotIn("ARMORED ROLE VISIBLE SET LOCK", prompt)
        self.assertIn("FIRST IMAGE COMPOSITION LOCK: moonlit stealth escape scene", local_prompt)
        self.assertIn("Stealth escape story scene", local_prompt)
        self.assertIn("every non-principal head stays below the principal person's waistline", local_prompt)
        self.assertNotIn("Achaemenid Persian and Egyptian armed group composition", local_prompt)

    def test_premodern_scene_uses_historical_building_hardware(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 525 BC; Exact place: Pelusium, Nile Delta, Egypt; "
                "Scene: Phanes sneaking along a moonlit path past sleeping drunk Egyptian watchmen beside a doorway; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("HISTORICAL BUILDING HARDWARE LOCK", prompt)
        self.assertIn("clay oil lamps, candles, torches", prompt)
        self.assertIn("Ceiling centers remain exposed rafters", prompt)
        self.assertIn("Active period light sits low", prompt)
        self.assertIn("table-held, floor-held, doorway-held, or off-frame", prompt)
        self.assertIn("no visible light-source object", prompt)
        self.assertIn("large hanging wooden or dark pull rings", prompt)
        self.assertIn("Plaster wall fields beside doors stay uninterrupted", prompt)
        self.assertIn("period hardware stays on door boards", prompt)
        self.assertIn("Blank plaster bays carry only", prompt)
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        self.assertIn("round dome ceiling lamp", negative)
        self.assertIn("central ceiling lamp", negative)
        self.assertIn("ceiling-mounted lantern", negative)
        self.assertIn("small white wall rectangle", negative)
        self.assertIn("wall switch", negative)
        self.assertIn("electrical outlet", negative)
        self.assertIn("Historical flame-lit building hardware", local_prompt)
        self.assertIn("Ceiling centers are dark rafters", local_prompt)
        self.assertIn("Plaster wall fields beside doors stay uninterrupted", local_prompt)
        self.assertIn("period hardware stays on door boards", local_prompt)

    def test_preindustrial_lamp_scene_places_lamp_low(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: c. 1337-1360; Nanboku-cho period, Southern Court in Yoshino; "
                "Exact place: Yoshino mountain ridge at dusk; "
                "Scene: A small lamp glows in a mountain hall as armed escorts climb from the dark valley; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("one low floor or table oil lamp glows below shoulder height", prompt)
        self.assertIn("LOW LAMP ARMED ENTRY LOCK", prompt)
        self.assertIn("not a front-facing lineup", prompt)
        self.assertIn("Upper chest fronts stay outside the main readable focus", prompt)
        self.assertIn("no isolated rectangular wall plate appears", prompt)
        self.assertIn("PERIOD LAMP PLACEMENT LOCK", prompt)
        self.assertIn("Upper rafters, ceiling centers, high beams, and blank plaster bays", prompt)
        self.assertIn("HISTORICAL HUMAN CLOTHING LOCK", prompt)
        self.assertIn("PERIOD-LOCAL JAPANESE MARTIAL CLOTHING LOCK", prompt)
        self.assertIn("MARTIAL ROLE CLOTHING VISIBLE SET LOCK", prompt)
        self.assertIn("FINAL CLOTHING SURFACE LOCK", prompt)
        self.assertIn("decorative circular spots", prompt)
        self.assertNotIn("small lamp glows", prompt.lower())
        self.assertIn("ceiling-mounted lantern", negative)
        self.assertIn("small white wall rectangle", negative)
        self.assertIn("gold medallion chest mark", negative)
        self.assertIn("gold sunburst chest mark", negative)
        self.assertIn("golden chest ornament", negative)
        self.assertIn("FINAL CLOTHING SURFACE LOCK", local_prompt)
        self.assertIn("MARTIAL ROLE CLOTHING VISIBLE SET LOCK", local_prompt)
        self.assertIn("decorative circular spots", local_prompt)
        self.assertIn("Low lamp armed entry story frame", local_prompt)
        self.assertIn("zero star marks", local_prompt)
        self.assertIn("no isolated switch-like rectangles", local_prompt)

    def test_achaemenid_generic_battlefield_does_not_seed_shields(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 525 BC; Exact place: Pelusium, Nile Delta, Egypt; "
                "Scene: cinematic wide shot, massive ancient armies clashing on a dusty desert battlefield; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("one shared short wooden spear class", prompt)
        self.assertIn("exactly four readable chest-up combat figures total", prompt)
        self.assertIn("two compact opposing subgroups facing each other from left and right", prompt)
        self.assertIn("crossed short spear angles at the center", prompt)
        self.assertIn("advancing and recoiling chest-up poses", prompt)
        self.assertIn("lower bodies outside the frame", prompt)
        self.assertIn("hips, thighs, knees, shins, legs, and feet are outside the image frame", prompt)
        self.assertNotIn("tight head-and-shoulders row", prompt)
        self.assertIn("one shared short wooden spear class", local_prompt)
        self.assertNotIn("wicker shield", prompt.lower())
        self.assertNotIn("leather-covered shield", prompt.lower())
        self.assertNotIn("shield-only", prompt.lower())
        self.assertNotIn("wicker shield", local_prompt.lower())
        self.assertNotIn("leather-covered shield", local_prompt.lower())
        self.assertNotIn("shield-only", local_prompt.lower())

    def test_achaemenid_object_scene_with_arrows_stays_unoccupied_evidence(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 525 BC; Exact place: Pelusium, Nile Delta, Egypt; "
                "Scene: giant wooden siege towers crashing against massive stone walls, flaming arrows in the night sky, epic scale; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("EMPTY EVIDENCE FRAME LOCK", prompt)
        self.assertIn("giant wooden siege towers", prompt)
        self.assertNotIn("ARMED FIGURE LOADOUT LOCK", prompt)
        self.assertNotIn("ARMED BODY VISIBLE SET LOCK", prompt)
        self.assertNotIn("SELECTED PERIOD WEAPON LOCK", prompt)
        self.assertNotIn("representative foreground archer", prompt)
        self.assertNotIn("SELECTED PERIOD WEAPON LOCK", local_prompt)
        self.assertNotIn("representative foreground archer", local_prompt)

    def test_achaemenid_paper_depicting_warriors_stays_paper_object(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 525 BC; Exact place: Pelusium, Nile Delta, Egypt; "
                "Scene: ancient parchment rolled blank cream paper bundles with Egyptian hieroglyphs depicting cats and warriors; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("PAPER EVIDENCE SURFACE LOCK", prompt)
        self.assertIn("DEPICTED SURFACE OBJECT LOCK", prompt)
        self.assertIn("physical cream paper evidence", prompt)
        self.assertIn("the requested blank book, document, manuscript, tablet, or scroll object", prompt)
        self.assertIn("PERIOD-LOCAL ACHAEMENID PERSIAN AND EGYPTIAN SETTING MATERIAL LOCK", prompt)
        self.assertNotIn("When the Scene names Persian soldiers", prompt)
        self.assertIn("EMPTY EVIDENCE FRAME LOCK", prompt)
        self.assertNotIn("depicting cats and warriors", prompt.lower())
        self.assertNotIn("Scene: terrain, ground", prompt)
        self.assertNotIn("ACHAEMENID EGYPTIAN ARMED GROUP COMPOSITION LOCK", prompt)
        self.assertNotIn("ARMORED ROLE VISIBLE SET LOCK", prompt)
        self.assertNotIn("ARMED BODY VISIBLE SET LOCK", prompt)
        self.assertIn("Physical visual-surface evidence illustration", local_prompt)
        self.assertIn("Period-local Achaemenid Persian and Egyptian setting material", local_prompt)
        self.assertNotIn("when the Scene names Persian soldiers", local_prompt)
        self.assertNotIn("Achaemenid Persian and Egyptian armed group composition", local_prompt)
        self.assertNotIn("Armored role visible set", local_prompt)

    def test_achaemenid_animal_battlefield_scene_does_not_create_soldiers(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 525 BC; Exact place: Pelusium, Nile Delta, Egypt; "
                "Scene: extreme close up of a cute fluffy kitten sitting on the bloody sand of a battlefield; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("kitten", prompt)
        self.assertIn("EMPTY EVIDENCE FRAME LOCK", prompt)
        self.assertIn("ANIMAL SUBJECT PHYSICAL LOCK", prompt)
        self.assertIn("ANIMAL BARE BODY LOCK", prompt)
        self.assertIn("requested location, animal, or object only", prompt)
        self.assertIn("PERIOD-LOCAL ACHAEMENID PERSIAN AND EGYPTIAN SETTING MATERIAL LOCK", prompt)
        self.assertNotIn("When the Scene names Persian soldiers", prompt)
        self.assertNotIn("ACHAEMENID EGYPTIAN ARMED GROUP COMPOSITION LOCK", prompt)
        self.assertNotIn("ARMED BODY VISIBLE SET LOCK", prompt)
        self.assertNotIn("ARMORED ROLE VISIBLE SET LOCK", prompt)
        self.assertIn("Natural animal subject illustration", local_prompt)
        self.assertIn("Bare natural animal body inventory", local_prompt)
        self.assertIn("Period-local Achaemenid Persian and Egyptian setting material", local_prompt)
        self.assertNotIn("when the Scene names Persian soldiers", local_prompt)
        self.assertNotIn("Achaemenid Persian and Egyptian armed group composition", local_prompt)
        self.assertNotIn("ARMED BODY VISIBLE SET LOCK", local_prompt)
        self.assertNotIn("Armored role visible set", local_prompt)

    def test_achaemenid_cats_with_discarded_weapons_stay_natural_animals(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 525 BC; Exact place: Pelusium, Nile Delta, Egypt; "
                "Scene: dozens of cats wandering around discarded Egyptian bronze weapons and shields, dramatic lighting; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("dozens of cats", prompt)
        self.assertIn("discarded Egyptian bronze weapons and shields", prompt)
        self.assertIn("ANIMAL SUBJECT PHYSICAL LOCK", prompt)
        self.assertIn("four-legged feline bodies", prompt)
        self.assertIn("ANIMAL BARE BODY LOCK", prompt)
        self.assertIn("PERIOD-LOCAL ACHAEMENID PERSIAN AND EGYPTIAN SETTING MATERIAL LOCK", prompt)
        self.assertNotIn("When the Scene names Persian soldiers", prompt)
        self.assertIn("Natural animal subject illustration", local_prompt)
        self.assertIn("Bare natural animal body inventory", local_prompt)
        self.assertIn("Period-local Achaemenid Persian and Egyptian setting material", local_prompt)
        self.assertNotIn("when the Scene names Persian soldiers", local_prompt)
        self.assertNotIn("ACHAEMENID EGYPTIAN ARMED GROUP COMPOSITION LOCK", prompt)
        self.assertNotIn("Achaemenid Persian and Egyptian armed group composition", local_prompt)

    def test_animal_scene_with_named_collar_does_not_get_bare_body_lock(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 2024; Exact place: modern Seoul apartment; "
                "Scene: a house cat wearing a red collar sitting beside a window; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("ANIMAL SUBJECT PHYSICAL LOCK", prompt)
        self.assertNotIn("ANIMAL BARE BODY LOCK", prompt)
        self.assertNotIn("Bare natural animal body inventory", local_prompt)

    def test_document_room_prompt_keeps_walls_and_paper_blank(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: c. 1335-1336; Exact place: timber room outside Kyoto; "
                "Scene: officials and warriors gather around a fire while two messengers hold documents; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("Upper wall zones, side wall zones", prompt)
        self.assertIn("PAPER EVIDENCE SURFACE LOCK", prompt)
        self.assertIn("cord-tied closed cream bundles held edge-on", prompt)
        self.assertIn("contain only structural elements", prompt)
        self.assertIn("narrow bundle spines, tied cord knots", prompt)
        self.assertIn("short cord-tied roll cylinders", prompt)
        self.assertIn("not organized into rows", prompt)
        self.assertIn("Broad paper faces stay folded closed", prompt)
        self.assertIn("Tables near paper evidence remain bare wood", prompt)
        self.assertIn("Wall decoration inventory remains empty", prompt)
        self.assertIn("empty walls stay plaster", prompt)
        self.assertNotIn("BOOK RENDERING LOCK", prompt)
        self.assertIn("side wall zones, alcove walls", prompt)
        self.assertNotIn("documents", prompt.lower())
        self.assertNotIn("scrolls", prompt.lower())
        self.assertNotIn("petitions", prompt.lower())
        self.assertIn("Upper wall zones, side wall zones", local_prompt)
        self.assertIn("side wall zones", local_prompt)
        self.assertIn("Scene-named paper evidence surfaces", local_prompt)
        self.assertIn("cord-tied closed cream bundles held edge-on", local_prompt)
        self.assertIn("contain only structural elements", local_prompt)
        self.assertIn("short cord-tied roll cylinders", local_prompt)
        self.assertIn("not organized into rows", local_prompt)
        self.assertIn("Broad paper faces stay folded closed", local_prompt)
        self.assertIn("Tables near paper evidence remain bare wood", local_prompt)
        self.assertIn("offset three-quarter group angle", local_prompt)
        self.assertNotIn("camera in front of the group", local_prompt)
        self.assertNotIn("foreground faces front or three-quarter-front", local_prompt)
        self.assertIn("Wall decoration inventory remains empty", local_prompt)
        self.assertIn("empty walls stay plaster", local_prompt)
        self.assertNotIn("documents", local_prompt.lower())
        self.assertNotIn("scrolls", local_prompt.lower())
        self.assertNotIn("petitions", local_prompt.lower())
        self.assertIn("FORMAL ROLE AND SETTING LAYOUT LOCK", prompt)

    def test_global_document_material_culture_does_not_seed_paper_in_non_document_scene(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Global visual world: Time range: Japan, late Kamakura period to early Muromachi period, mainly 1333-1338; "
                "Material culture: hitatare robes, court robes, folded documents with no readable writing; "
                "Continuity rule: historically grounded medieval Japanese settings, no modern objects; "
                "Year/period: 1336; Exact place: Kyushu field camp; "
                "Scene: New warriors arrive at Takauji's camp, lifting armor bundles while tired retainers make space; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertNotIn("PAPER EVIDENCE SURFACE LOCK", prompt)
        self.assertNotIn("BOOK RENDERING LOCK", prompt)
        self.assertNotIn("paper-like", prompt.lower())
        self.assertNotIn("cord-tied closed cream bundles", prompt)
        self.assertNotIn("Scene-named paper evidence surfaces", local_prompt)

    def test_roadside_shrine_scene_gets_blank_entry_facade_lock(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1338; Exact place: misty road from Kyoto toward the provinces; "
                "Scene: Mounted messengers vanish into morning mist as blank banners flutter beside a quiet roadside shrine; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("ENTRY FACADE SURFACE LOCK", prompt)
        self.assertIn("CLOTH EVIDENCE SURFACE LOCK", prompt)
        self.assertIn("Scene-named vertical fabric evidence appears as plain textile folds only", prompt)
        self.assertIn("Over-door timber spans, transom zones", prompt)
        self.assertIn("Scene-named shrine, temple, roadside", local_prompt)
        self.assertIn("Scene-named vertical fabric evidence appears as plain textile folds only", local_prompt)
        self.assertIn("Over-door timber spans, transom zones", local_prompt)
        self.assertNotIn("signboard", prompt.lower())
        self.assertNotIn("plaque", prompt.lower())

    def test_court_gate_scene_does_not_seed_hanging_cloth(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1333; Exact place: Kyoto court outer gate; "
                "Scene: Armored warriors stop before a court gate as robed officials move inside without meeting their eyes; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertNotIn("CLOTH EVIDENCE SURFACE LOCK", prompt)
        self.assertNotIn("hanging cloth panels", prompt.lower())
        self.assertNotIn("plain hanging cloth panels", local_prompt.lower())
        self.assertNotIn("fabric curtains", local_prompt.lower())

    def test_character_overlooking_valley_does_not_become_face_closeup(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: a man looking ambitiously over a fertile valley; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("OVERLOOKING VIEW COMPOSITION LOCK", prompt)
        self.assertIn("the visible view is the main subject", prompt)
        self.assertIn("person in foreground or midground", prompt)
        self.assertIn("one visible person as the sole human focus", prompt)
        self.assertIn("the foreground contains one visible person", prompt)
        self.assertIn("solitary one-person-only lookout image", prompt)
        self.assertIn("exactly one living person total in the entire frame", prompt)
        self.assertIn("single-person-only composition", prompt)
        self.assertIn("one isolated human body, one head, one torso silhouette", prompt)
        self.assertIn("Distant roads, paths, village edges", prompt)
        self.assertNotIn("MODERN CHARACTER CLOTHING LOCK", prompt)
        self.assertNotIn("SINGLE CHARACTER LOCK", prompt)
        self.assertNotIn("one solitary face", prompt)
        self.assertNotIn("face and shoulder edge filling roughly 98 percent", prompt)
        self.assertNotIn("armor", prompt.lower())
        self.assertNotIn("lamellar", prompt.lower())
        self.assertNotIn("weapon", prompt.lower())

    def test_unarmed_warrior_arriving_at_valley_routes_to_overlooking_scene(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: a warrior looking exhausted arriving at a valley; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("OVERLOOKING VIEW COMPOSITION LOCK", prompt)
        self.assertIn("EARLY GOGURYEO LANDSCAPE LOCK", prompt)
        self.assertIn("exactly one living person total in the entire frame", prompt)
        self.assertIn("one clear ground gap around that person", prompt)
        self.assertIn("empty path, roofs, smoke, fences", prompt)
        self.assertIn("plain period clothing", prompt)
        self.assertNotIn("ARMED ROLE PORTRAIT CROP LOCK", prompt)
        self.assertNotIn("ARMED FIGURE LOADOUT LOCK", prompt)
        self.assertNotIn("SELECTED PERIOD WEAPON LOCK", prompt)
        self.assertNotIn("visible hand weapon appears", prompt)

    def test_local_unarmed_warrior_arriving_at_valley_routes_to_overlooking_scene(self):
        enriched = _enrich_local_v1_positive_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: a warrior looking exhausted arriving at a valley; "
                "Style: simple cartoon illustration"
            )
        )

        self.assertIn("Solitary one-person-only Early Goguryeo Jolbon overlooking valley illustration", enriched)
        self.assertIn("exactly one human figure in the whole image", enriched)
        self.assertIn("one visible foreground person as the sole human focus", enriched)
        self.assertIn("exactly one living person total in the entire frame", enriched)
        self.assertIn("single-person-only composition", enriched)
        self.assertIn("one isolated human body, one head, one torso silhouette", enriched)
        self.assertIn("empty path, roofs, smoke, fences", enriched)
        self.assertIn("Scene subject: a warrior looking exhausted arriving at a valley", enriched)
        self.assertNotIn("ARMED ROLE PORTRAIT CROP LOCK", enriched)
        self.assertNotIn("selected shoulder-side prop", enriched)

    def test_holding_large_bow_becomes_unstrung_display_bow_evidence(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: Songyang holding a large bow, smirking proudly; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("standing beside a single unstrung curved wooden display bow", prompt)
        self.assertIn("leaning vertically against a plain wall", prompt)
        self.assertIn("one unstrung ceremonial display bow", prompt)

    def test_early_goguryeo_captive_vision_stays_civilian_cloth(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Main subject: Jumong; "
                "Scene: a dark vision of Jumong and his friends in heavy chains; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("HARD HISTORICAL CIVILIAN MATERIAL CULTURE LOCK", prompt)
        self.assertIn("EARLY GOGURYEO CHARACTER LOCK", prompt)
        self.assertIn("ominous period captive group scene", prompt)
        self.assertIn("bare visible eyes", prompt)
        self.assertIn("The eye area is open skin", prompt)
        self.assertIn("heavy chains", prompt)
        self.assertIn("cloth and fur clothing layers", prompt)
        self.assertNotIn("dark vision", prompt.lower())
        self.assertNotIn("armor", prompt.lower())
        self.assertNotIn("lamellar", prompt.lower())
        self.assertNotIn("weapon", prompt.lower())

    def test_local_early_generic_scene_does_not_seed_weapons_or_armor(self):
        enriched = _enrich_local_v1_positive_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: a tense empty packed-earth courtyard under rain"
            )
        )

        self.assertIn("Early Goguryeo frontier settlement illustration", enriched)
        self.assertIn("packed dirt courtyards", enriched)
        self.assertNotIn("bows, spears", enriched)
        self.assertNotIn("lamellar armor", enriched.lower())

    def test_object_only_prompt_uses_object_master_and_suffix(self):
        enriched = _enrich_local_v1_positive_prompt(
            (
                "Year/period: around 37 BCE; Exact place: Jolbon; "
                "Scene: evidence still-life of a smooth undecorated bronze ring; "
                "|| EARLY GOGURYEO ARTIFACT LOCK"
            )
        )
        self.assertTrue(_local_prompt_is_object_only(enriched))

        mastered = apply_longtube_local_v1_master_prompt(
            enriched,
            object_only=_local_prompt_is_object_only(enriched),
        )
        final = _append_local_v1_final_composition_suffix(
            mastered,
            group_character=True,
            object_only=_local_prompt_is_object_only(mastered),
        )

        self.assertIn("DOCUMENTARY OBJECT EVIDENCE STYLE", final)
        self.assertIn("FINAL COMPOSITION PRIORITY: object-only evidence still-life", final)
        self.assertNotIn("stylized human faces", final)
        self.assertNotIn("motivated portrait poses", final)
        self.assertNotIn("close group story shot", final)

    def test_local_group_final_suffix_does_not_force_front_lineup(self):
        final = _append_local_v1_final_composition_suffix(
            "Scene: three officials hold folded paper bundles in a tense court room. "
            "FINAL CLOTHING SURFACE LOCK - robe surfaces stay plain.",
            group_character=True,
            object_only=False,
        )

        self.assertIn("offset three-quarter camera", final)
        self.assertIn("diagonal overlap", final)
        self.assertIn("upper torsos interrupted by hands, sleeves, carried objects, or overlapping figures", final)
        self.assertIn("Cloth upper-body surfaces are broad blank textile", final)
        self.assertNotIn("camera in front of the group", final)
        self.assertNotIn("foreground faces front or three-quarter-front", final)

    def test_generic_history_book_object_first_does_not_become_gate(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 17 BCE; Exact place: Gungnae Fortress; "
                "Scene: an ancient history book covered in dust and faint blood stains; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("HARD HISTORICAL OBJECT EVIDENCE MATERIAL CULTURE LOCK", prompt)
        self.assertIn("book-like document object", prompt)
        self.assertIn("Do not replace the object with a gate", prompt)
        self.assertTrue(_local_prompt_is_object_only(prompt))
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        self.assertIn("GENERIC OBJECT EVIDENCE FIRST RULE", comfy_prompt)
        self.assertIn("building exterior replacing book", comfy_negative)
        local_prompt = _enrich_local_v1_positive_prompt(prompt)
        self.assertIn("book or document object evidence illustration", local_prompt)
        self.assertNotIn("frontier settlement illustration", local_prompt.lower())

    def test_torn_painting_stays_surface_not_live_battle(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 17 BCE; Exact place: Gungnae Fortress; "
                "Scene: a torn painting revealing a muddy and dark battlefield; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("HARD HISTORICAL OBJECT EVIDENCE MATERIAL CULTURE LOCK", prompt)
        self.assertIn("torn physical painting surface", prompt)
        self.assertIn("visible only as flat damaged pigment", prompt)
        self.assertIn("does not become a live person, live battle scene", prompt)
        self.assertTrue(_local_prompt_is_object_only(prompt))
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        self.assertIn("GENERIC OBJECT EVIDENCE FIRST RULE", comfy_prompt)
        self.assertIn("This is a physical visual-surface object shot", comfy_prompt)
        self.assertIn("live battle replacing painting", comfy_negative)
        local_prompt = _enrich_local_v1_positive_prompt(prompt)
        self.assertIn("physical visual-surface object evidence illustration", local_prompt)
        self.assertIn("never become live people", local_prompt)

    def test_crown_status_object_first_does_not_become_gate(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 17 BCE; Exact place: Gungnae Fortress; "
                "Scene: blood-stained royal crown sitting in shadows; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("HARD HISTORICAL OBJECT EVIDENCE MATERIAL CULTURE LOCK", prompt)
        self.assertIn("period-local ruler status headpiece", prompt)
        self.assertIn("not a European fairy-tale crown", prompt)
        self.assertTrue(_local_prompt_is_object_only(prompt))
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        self.assertIn("GENERIC OBJECT EVIDENCE FIRST RULE", comfy_prompt)
        self.assertIn("building exterior replacing crown", comfy_negative)
        self.assertIn("gate replacing crown", comfy_negative)
        local_prompt = _enrich_local_v1_positive_prompt(prompt)
        self.assertIn("period-local ruler status object evidence illustration", local_prompt)

    def test_broken_blade_on_table_keeps_named_surface(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 17 BCE; Exact place: Gungnae Fortress; "
                "Scene: broken blade on cold stone table; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("HARD HISTORICAL OBJECT EVIDENCE MATERIAL CULTURE LOCK", prompt)
        self.assertIn("broken blade sections resting flat on a cold stone table surface", prompt)
        self.assertIn("the Scene-named weapon evidence as the dominant still-life object", prompt)
        self.assertTrue(_local_prompt_is_object_only(prompt))
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        self.assertIn("GENERIC OBJECT EVIDENCE FIRST RULE", comfy_prompt)
        self.assertIn("object replaced by doorway", comfy_negative)
        local_prompt = _enrich_local_v1_positive_prompt(prompt)
        self.assertIn("weapon evidence still-life illustration", local_prompt)

    def test_seated_ruler_throne_keeps_throne_visible_not_face_only(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 17 BCE; Exact place: Gungnae Fortress; "
                "Scene: a stressed king sitting nervously on a dark iron throne; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("HARD HISTORICAL MATERIAL CULTURE LOCK", prompt)
        self.assertNotIn("HARD HISTORICAL CIVILIAN MATERIAL CULTURE LOCK", prompt)
        self.assertIn("the seated ruler and the Scene-named throne or seat together", prompt)
        self.assertIn("medium-close or waist-up three-quarter story frame", prompt)
        self.assertNotIn("solo face close-up portrait shot", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")
        self.assertIn("SEATED RULER AND THRONE FIRST RULE", comfy_prompt)
        self.assertIn("visible throne back, armrest, seat plane", comfy_prompt)
        self.assertIn("throne missing", comfy_negative)

    def test_empty_throne_scene_stays_unoccupied_object_not_queen_portrait(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 17 BCE; Exact place: Gungnae Fortress; "
                "Scene: a cold, empty queen's throne draped in black cloth; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("HARD HISTORICAL OBJECT EVIDENCE MATERIAL CULTURE LOCK", prompt)
        self.assertIn("the empty Scene-named throne, seat, dais, low platform", prompt)
        self.assertIn("No living person, portrait, face", prompt)
        self.assertTrue(_local_prompt_is_object_only(prompt))
        self.assertIn("Empty seat or platform evidence shot", comfy_prompt)
        self.assertIn("No person, no portrait, no face", comfy_prompt)
        self.assertIn("portrait replacing empty seat", comfy_negative)
        self.assertNotIn("SINGLE CHARACTER LOCK", prompt)

    def test_mirror_reflection_scene_stays_mirror_not_live_portrait(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 17 BCE; Exact place: Gungnae Fortress; "
                "Scene: a cracked mirror reflecting the king's troubled face; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("HARD HISTORICAL OBJECT EVIDENCE MATERIAL CULTURE LOCK", prompt)
        self.assertIn("reflective mirror object as the dominant foreground evidence", prompt)
        self.assertIn("distorted reflection contained inside the mirror surface", prompt)
        self.assertTrue(_local_prompt_is_object_only(prompt))
        self.assertIn("Mirror evidence shot", comfy_prompt)
        self.assertIn("never becomes a live person portrait", comfy_prompt)
        self.assertIn("portrait replacing mirror", comfy_negative)
        self.assertNotIn("solo face close-up portrait shot", prompt)

    def test_noblemen_glaring_scene_routes_to_group_story_not_solo_face(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 17 BCE; Exact place: Gungnae Fortress; "
                "Scene: arrogant noblemen glaring at the new young king; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        local_prompt = _enrich_local_v1_positive_prompt(prompt)

        self.assertIn("GROUP CHARACTER COMPOSITION LOCK", prompt)
        self.assertIn("close group story moment", prompt)
        self.assertNotIn("SINGLE CHARACTER LOCK", prompt)
        self.assertNotIn("solo face close-up portrait shot", prompt)
        self.assertTrue(_local_scene_requests_group(prompt))
        self.assertIn("close group story shot", local_prompt.lower())

    def test_holding_head_keeps_visible_action_not_secured_object(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: around 17 BCE; Exact place: Gungnae Fortress; "
                "Scene: a king looking extremely paranoid, holding his head; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("one sleeve-covered fist pressed to his temple", prompt)
        self.assertIn("SINGLE CHARACTER ACTION STORY LOCK", prompt)
        self.assertIn("action arm or sleeve-covered hand visible", prompt)
        self.assertNotIn("head secured near the torso", prompt)
        self.assertNotIn("SINGLE CHARACTER LOCK", prompt)

    def test_groom_arriving_is_human_story_frame_not_empty_evidence(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1st to 3rd century CE; Exact place: Goguryeo; "
                "Scene: a groom wearing expensive silk clothes arriving at twilight; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("principal figure from the Scene in a story-action frame", prompt)
        self.assertIn("CHARACTER STORY FRAMING LOCK", prompt)
        self.assertNotIn("EMPTY EVIDENCE FRAME LOCK", prompt)
        self.assertNotIn("OBJECT-LOCATION PRIMARY SUBJECT LOCK", prompt)
        self.assertIn("PERSON ARRIVAL THRESHOLD STORY FRAME", comfy_prompt)
        self.assertIn("readable face and eyes", comfy_prompt)
        self.assertIn("roughly half to two-thirds of the image height", comfy_prompt)
        self.assertIn("Do not invent a close doorway", comfy_prompt)
        self.assertIn("with empty hands", comfy_prompt)
        self.assertIn("missing arriving person", comfy_negative)
        self.assertIn("back view of arriving person", comfy_negative)
        self.assertIn("modern vertical door handle", comfy_negative)
        self.assertIn("switch plate beside doorway", comfy_negative)
        self.assertIn("rectangular lock plate", comfy_negative)
        self.assertIn("character plaque on post", comfy_negative)
        self.assertIn("weapon on groom", comfy_negative)

    def test_empty_farm_field_possessive_family_stays_unoccupied_location(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1st to 3rd century CE; Exact place: Goguryeo; "
                "Scene: an empty, poorly maintained farm field of the groom's original family; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )

        self.assertIn("EMPTY EVIDENCE FRAME LOCK", prompt)
        self.assertIn("LANDSCAPE VISIBLE SET LOCK", prompt)
        self.assertNotIn("GROUP CHARACTER COMPOSITION LOCK", prompt)
        self.assertNotIn("ORDINARY HUMAN VISIBLE SET LOCK", prompt)

    def test_wealth_people_scene_keeps_gold_or_silk_visible(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1st to 3rd century CE; Exact place: Goguryeo; "
                "Scene: two ruthless nobles shaking hands over a pile of gold; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("WEALTH PROP ACTION FIRST RULE", comfy_prompt)
        self.assertIn("mandatory foreground story evidence", comfy_prompt)
        self.assertIn("missing gold pile", comfy_negative)
        self.assertIn("handshake without gold", comfy_negative)
        self.assertIn("chest gold badge", comfy_negative)

    def test_stone_pillar_erection_does_not_become_gate_plaque(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1st to 3rd century CE; Exact place: Goguryeo; "
                "Scene: a massive stone pillar being erected; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("STONE PILLAR ERECTION FIRST RULE", comfy_prompt)
        self.assertIn("not a building facade", comfy_prompt)
        self.assertIn("missing stone pillar", comfy_negative)
        self.assertIn("signboard above door", comfy_negative)

    def test_named_dagger_must_be_visible_in_hand(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1st to 3rd century CE; Exact place: Goguryeo; "
                "Scene: a king holding a dagger in the shadows; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("VISIBLE HANDHELD WEAPON FIRST RULE", comfy_prompt)
        self.assertIn("must be clearly visible", comfy_prompt)
        self.assertIn("missing dagger", comfy_negative)

    def test_labor_camp_scene_does_not_become_solo_portrait(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1st to 3rd century CE; Exact place: Goguryeo; "
                "Scene: the illusion shattering into a dark, slave-like labor camp; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("LABOR CAMP FIRST RULE", comfy_prompt)
        self.assertIn("multiple exhausted workers", comfy_prompt)
        self.assertIn("solo portrait replacing labor camp", comfy_negative)

    def test_split_screen_and_banner_scenes_keep_named_visual_subjects(self):
        split_prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1st to 3rd century CE; Exact place: Goguryeo; "
                "Scene: a split screen of a poor village and a luxurious mansion; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        split_comfy, split_negative = _enforce_comfyui_common_positive_prompt(split_prompt, "")
        self.assertIn("SPLIT CONTRAST FIRST RULE", split_comfy)
        self.assertIn("missing split screen", split_negative)

        banner_prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1st to 3rd century CE; Exact place: Goguryeo; "
                "Scene: a torn Goguryeo banner next to a proud Chinese flag; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        banner_comfy, banner_negative = _enforce_comfyui_common_positive_prompt(banner_prompt, "")
        self.assertIn("OPPOSED BANNER FIRST RULE", banner_comfy)
        self.assertIn("missing torn banner", banner_negative)

    def test_empty_farm_field_forces_outdoor_field_not_room(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1st to 3rd century CE; Exact place: Goguryeo; "
                "Scene: an empty, poorly maintained farm field of the groom's original family; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("EMPTY OUTDOOR FIELD FIRST RULE", comfy_prompt)
        self.assertIn("outdoor field terrain itself", comfy_prompt)
        self.assertIn("interior room replacing field", comfy_negative)

    def test_peasant_handholding_stays_group_action(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1st to 3rd century CE; Exact place: Goguryeo; "
                "Scene: poor peasants holding hands in a simple, muddy village; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("GROUP CHARACTER COMPOSITION LOCK", prompt)
        self.assertIn("HANDHOLDING GROUP FIRST RULE", comfy_prompt)
        self.assertIn("missing joined hands", comfy_negative)

    def test_symbolic_scene_exact_subjects_do_not_become_doors(self):
        samples = [
            ("a bloody chessboard with toppled pieces", "Show one low period game board"),
            ("a boomerang covered in blood flying back", "Show the boomerang-shaped weapon/object itself"),
            ("an ancient calculator (abacus) dripping with blood", "Show a period counting frame"),
            ("a dark mirror reflecting a brutal, bloody reality", "Show the dark mirror"),
            ("a vicious wolf pack circling in the snow", "Show multiple wolves circling"),
            ("a cold, unblinking eye reflecting a burning fire", "Show a cold unblinking eye"),
        ]

        for scene, required in samples:
            prompt = prompt_builder.build_image_prompt(
                (
                    "Year/period: 1st to 3rd century CE; Exact place: Goguryeo; "
                    f"Scene: {scene}; Style: simple cartoon illustration"
                ),
                "simple cartoon illustration",
                enable_historical_guard=True,
            )
            comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

            self.assertIn("EXACT SYMBOLIC SCENE FIRST RULE", comfy_prompt)
            self.assertIn(required, comfy_prompt)
            self.assertIn("generic doorway replacing scene", comfy_negative)

    def test_blood_stained_wooden_wheel_routes_to_object_evidence(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 1st to 3rd century CE; Exact place: Goguryeo; "
                "Scene: a heavy, blood-stained wooden wheel rolling over the ground; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("HARD HISTORICAL OBJECT EVIDENCE MATERIAL CULTURE LOCK", prompt)
        self.assertIn("GENERIC OBJECT EVIDENCE FIRST RULE", comfy_prompt)
        self.assertIn("building facade", comfy_negative)

    def test_goguryeo_silla_415_hou_bowl_gets_exact_material_lock(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 415 CE; Exact place: Gyeongju Houchong Tomb, Silla; "
                "Scene: the Goguryeo bronze Hou bowl with the Gwanggaeto inscription "
                "resting on dark tomb cloth; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)

        self.assertIn("GOGURYEO-SILLA 415 MATERIAL CULTURE LOCK", prompt)
        self.assertIn("HOU BOWL OBJECT LOCK", prompt)
        self.assertIn("one dull aged bronze Goguryeo hou vessel from 415 CE", prompt)
        self.assertIn("rice bowl replacing Hou bowl", negative)
        self.assertIn("Joseon gat", negative)

    def test_ch1_ep22_pyongyang_prompt_does_not_trigger_415_hou_lock(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Global visual world: Time range: 642year 9; Place scope: ancient Northeast Asia, "
                "Goguryeo-related court and frontier settings; Culture scope: Goguryeo and neighboring "
                "ancient Northeast Asian political and military world; Material culture: Iron weapons, "
                "bows, leather armor, lamellar armor, hemp garments, wooden halls, fortress walls, "
                "river crossings, horses, bronze ritual objects; Continuity rule: Every scene stays "
                "in an ancient Northeast Asian setting. No Joseon dynasty clothing, no modern objects, "
                "no medieval European castles, no readable text.; Year/period: 642 AD; "
                "Sui-Goguryeo war, 612 AD; Exact place: Pyongyang Fortress; "
                "Main subject: cracked and ruined peace treaty document on a wooden table; "
                "Scene: A cracked and ruined peace treaty document on a wooden table"
            ),
            "storytelling",
            enable_historical_guard=True,
        )

        self.assertNotIn("GOGURYEO-SILLA 415 MATERIAL CULTURE LOCK", prompt)
        self.assertNotIn("HOU BOWL OBJECT LOCK", prompt)

    def test_flux2_klein_ch1_ep22_pyongyang_keeps_642_subject_not_ondal_or_gwanggaeto(self):
        source = (
            "Global visual world: Time range: 642year 9; Place scope: ancient Northeast Asia, "
            "Goguryeo-related court and frontier settings; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Material culture: Iron weapons, "
            "bows, leather armor, lamellar armor, hemp garments, wooden halls, fortress walls, "
            "river crossings, horses, bronze ritual objects; Continuity rule: Every scene stays "
            "in an ancient Northeast Asian setting. No Joseon dynasty clothing, no modern objects, "
            "no medieval European castles, no readable text.; Year/period: 642 AD; "
            "Sui-Goguryeo war, 612 AD; Exact place: Pyongyang Fortress; "
            "Main subject: Yeon Gaesomun; "
            "Scene: Yeon Gaesomun, a towering, heavily armored warrior, glaring coldly"
        )
        compact, _ = _compact_flux2_klein_4b_prompt(source, "")
        final = _flux2_klein_md_positive_contract(compact, source)

        self.assertIn("642 AD", final)
        self.assertIn("642 AD; Pyongyang Fortress; Goguryeo court and", final)
        self.assertIn("Goguryeo court and", final)
        self.assertIn("Scene subject: Yeon Gaesomun", final)
        self.assertNotIn("Sui-Goguryeo", final)
        self.assertNotIn("Goguryeo-Sui", final)
        self.assertNotIn("612 AD", final)
        self.assertNotIn("Late sixth-century Goguryeo", final)
        self.assertNotIn("Princess Pyeonggang", final)
        self.assertNotIn("King Gwanggaeto", final)

    def test_flux2_klein_ch1_ep22_blood_iron_throne_does_not_become_rocky_aftermath(self):
        source = (
            "Global visual world: Time range: 642year 9; Place scope: ancient Northeast Asia, "
            "Goguryeo-related court and frontier settings; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Year/period: 642 AD; "
            "Sui-Goguryeo war, 612 AD; Exact place: Pyongyang Fortress; "
            "Main subject: cold; Scene: A cold, blood-stained iron throne in a dark, empty room"
        )
        compact, _ = _compact_flux2_klein_4b_prompt(source, "")
        final = _flux2_klein_md_positive_contract(compact, source)

        self.assertIn("empty blood-stained Goguryeo command dais", final)
        self.assertIn("dark timber hall", final)
        self.assertIn("low iron-banded wooden command dais", final)
        self.assertNotIn("Sui-Goguryeo", final)
        self.assertNotIn("Goguryeo-Sui", final)
        self.assertNotIn("blood-spattered cold rocks", final)

    def test_flux2_klein_612_salsu_still_uses_sui_goguryeo_context(self):
        source = (
            "Global visual world: Time range: 612 AD; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Salsu River battlefield; "
            "Main subject: Sui soldiers; Scene: Sui soldiers swept through the Salsu river crossing"
        )
        compact, _ = _compact_flux2_klein_4b_prompt(source, "")
        final = _flux2_klein_md_positive_contract(compact, source)

        self.assertIn("Goguryeo-Sui", final)
        self.assertIn("Salsu", final)
        self.assertIn("early Sui-Goguryeo", final)

    def test_flux2_klein_645_tang_liaodong_ignores_stale_sui_source_residue(self):
        source = (
            "Global visual world: Time range: 645year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 645 AD; Sui-Goguryeo war, 612 AD; Exact place: Liaodong Fortress; "
            "Main subject: Emperor Yang of Sui; "
            "Scene: stylish medium-close entrance of Emperor Yang of Sui beside immovable stone blocks"
        )
        compact = (
            "645 AD; Tang-Goguryeo northeastern frontier region campaign; "
            "northeastern frontier fortress area; Goguryeo and Tang military world. "
            "Render as full-bleed 2D historical ink-and-cel with thick black contours. "
            "Scene subject: cropped granite defense-block field under siege pressure. "
            "Visible action: rough stone blocks, rope, dust, smoke, and broken debris form one continuous rubble field. "
            "Visible inventory: cropped granite blocks, rope, mud, broken weapons, smoke, dust, stone chips, soot. "
            "Composition: extreme close 16:9 stone-block material crop."
        )

        final = _flux2_klein_md_positive_contract(compact, source)

        self.assertIn("645 AD", final)
        self.assertIn("Tang-Goguryeo", final)
        self.assertNotIn("612 AD", final)
        self.assertNotIn("Sui-Goguryeo", final)
        self.assertNotIn("Goguryeo-Sui", final)
        self.assertNotIn("Sui soldiers", final)
        self.assertNotIn("Emperor Yang of Sui", final)

    def test_flux2_klein_645_tang_liaodong_uses_clean_text_fields_over_stale_source(self):
        source = (
            "Global visual world: Time range: 645year; "
            "Place scope: 612 Goguryeo-Sui open river battlefield, muddy river crossing; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 645 AD; Sui-Goguryeo war, 612 AD; "
            "Exact place: 612 Goguryeo-Sui open river battlefield, muddy river crossing; "
            "Scene evidence: exhausted Sui soldiers; Main subject: Sui soldiers; "
            "Scene: Exhausted Sui soldiers struggle across a cold open river crossing"
        )
        clean_text = (
            "Historical visual context: Year/period: 645 AD; Tang-Goguryeo Liaodong campaign; "
            "Exact place: Liao River crossing toward Liaodong Fortress; "
            "Scene evidence: Tang soldiers, muddy Liao River crossing, horse tack, plain shields, wet reeds; "
            "Main subject: Tang and Goguryeo forces; "
            "Scene: Tang soldiers cross the wide muddy Liao River toward Liaodong Fortress"
        )

        final = _flux2_klein_md_positive_contract(clean_text, source)

        self.assertIn("645 AD", final)
        self.assertIn("Liao River crossing toward Liaodong Fortress", final)
        self.assertIn("Tang soldiers", final)
        self.assertNotIn("region region", final)
        self.assertNotIn("612 AD", final)
        self.assertNotIn("Sui-Goguryeo", final)
        self.assertNotIn("Goguryeo-Sui", final)
        self.assertNotIn("Sui soldiers", final)

    def test_flux2_klein_direct_raw_645_tang_source_is_prepared_before_contract(self):
        source = (
            "Global visual world: Time range: 645year; "
            "Place scope: 612 Goguryeo-Sui open river battlefield, muddy river crossing; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Material culture: iron weapons, bows, lamellar armor, hemp garments, riverbank mud, cold water; "
            "Year/period: 645 AD; Sui-Goguryeo war, 612 AD; "
            "Exact place: 612 Goguryeo-Sui open river battlefield, muddy river crossing; "
            "Scene evidence: exhausted Sui soldiers, Goguryeo pressure from the bank; "
            "Main subject: Sui soldiers; "
            "Scene: Exhausted Sui soldiers struggle across a cold open river crossing while Goguryeo infantry wait on muddy banks"
        )

        prepared = _flux2_klein_prepare_source_prompt_text(source)
        compact, _ = _compact_flux2_klein_4b_prompt(f"{source}\n{prepared}", "")
        final = _flux2_klein_md_positive_contract(prepared, prepared)

        self.assertIn("645 AD", final)
        self.assertIn("Tang-Goguryeo Liaodong campaign", final)
        self.assertIn("Tang soldiers", final)
        self.assertNotIn("612 AD", final)
        self.assertNotIn("Sui-Goguryeo", final)
        self.assertNotIn("Goguryeo-Sui", final)
        self.assertNotIn("Sui soldiers", final)
        self.assertNotIn("612 AD", compact)
        self.assertNotIn("612 CE", compact)
        self.assertNotIn("Sui-Goguryeo", compact)
        self.assertNotIn("Goguryeo-Sui", compact)
        self.assertNotIn("Sui soldiers", compact)

    def test_flux2_klein_645_tang_rewrites_spyglass_to_period_lookout(self):
        source = (
            "Global visual world: Time range: 645year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 645 AD; Exact place: Liaodong Fortress; "
            "Main subject: Emperor Taizong looking through a spyglass; "
            "Scene: Emperor Taizong looking through a spyglass, his face serious"
        )

        prepared = _flux2_klein_prepare_source_prompt_text(source)
        compact, _ = _compact_flux2_klein_4b_prompt(f"{prepared}\n{prepared}", "")
        final = _flux2_klein_md_positive_contract(
            _flux2_klein_positive_contract_cleanup(compact),
            prepared,
        )
        negative = _flux2_klein_md_negative_contract(prepared, final)

        self.assertIn("high earthen lookout", final)
        self.assertIn("distant fortress", final)
        self.assertNotIn("spyglass", final.lower())
        self.assertNotIn("telescope", final.lower())
        self.assertIn("spyglass", negative)
        self.assertIn("telescope", negative)

    def test_flux2_klein_645_tang_rewrites_modern_symbol_objects(self):
        cases = (
            (
                "Main subject: beautiful stained-glass window shattering violently into pieces; "
                "Scene: A beautiful stained-glass window shattering violently into pieces",
                "thin blank dyed glory cloth",
                ("stained-glass", "glass window"),
            ),
            (
                "Main subject: sharp surgical scalpel slicing cleanly through an old; "
                "Scene: A sharp surgical scalpel slicing cleanly through an old, dusty text",
                "object-only plain period iron knife",
                ("surgical scalpel", "dusty text"),
            ),
            (
                "Main subject: title card for Episode 25; "
                "Scene: The title card for Episode 25, illuminated by dark, gritty red lighting",
                "ominous closing view",
                ("title card", "Episode 25"),
            ),
            (
                "Main subject: massive iron gear grinding heavily against another; "
                "Scene: A massive iron gear grinding heavily against another, sparks flying",
                "rough millstone-like boulder faces",
                ("iron gear", "gear"),
            ),
        )
        base = (
            "Global visual world: Time range: 645year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 645 AD; Exact place: Liaodong Fortress; "
        )

        for source_tail, expected, forbidden in cases:
            with self.subTest(expected=expected):
                prepared = _flux2_klein_prepare_source_prompt_text(base + source_tail)
                compact, _ = _compact_flux2_klein_4b_prompt(f"{prepared}\n{prepared}", "")
                final = _flux2_klein_md_positive_contract(
                    _flux2_klein_positive_contract_cleanup(compact),
                    prepared,
                )
                self.assertIn(expected, final)
                for token in forbidden:
                    self.assertNotIn(token.lower(), final.lower())
                if expected == "object-only plain period iron knife":
                    self.assertIn("object-only plain period iron knife", final)
                    self.assertIn("closed bamboo-slip packet", final)
                    self.assertIn("bamboo rod ends and cord fibers", final)
                    self.assertIn("full rawhide cord-wrapped grip", final)
                    self.assertNotIn("pebble counters", final)
                    self.assertNotIn("clay lumps", final)
                    negative = _flux2_klein_md_negative_contract(prepared, final)
                    self.assertIn("knife stabbing stone", negative)
                    self.assertIn("modern hunting knife", negative)
                    self.assertIn("handle rivets", negative)
                    self.assertIn("smooth cylindrical knife handle", negative)
                    self.assertIn("live hand holding knife", negative)
                    self.assertIn("pebble counters replacing packet", negative)
                if expected == "rough millstone-like boulder faces":
                    self.assertIn("chipped stone flakes", final)
                    self.assertIn("stone dust", final)
                    self.assertNotIn("iron fragments", final.lower())
                    negative = _flux2_klein_md_negative_contract(prepared, final)
                    self.assertIn("metal cylinders", negative)
                    self.assertIn("bullet casing", negative)
                    self.assertIn("dynamite stick", negative)
                    self.assertIn("thin black top border", negative)
                    self.assertIn("uniform black top line", negative)

    def test_flux2_klein_645_tang_adds_unmarked_surface_contract(self):
        source = (
            "Global visual world: Time range: 645year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 645 AD; Exact place: Liaodong Fortress; "
            "Main subject: Tang generals arguing over a map; "
            "Scene: Tang generals arguing over a map, pointing in different directions"
        )

        prepared = _flux2_klein_prepare_source_prompt_text(source)
        compact, _ = _compact_flux2_klein_4b_prompt(f"{prepared}\n{prepared}", "")
        final = _flux2_klein_md_positive_contract(
            _flux2_klein_positive_contract_cleanup(compact),
            prepared,
        )
        negative = _flux2_klein_md_negative_contract(prepared, final)

        self.assertIn("Visible unmarked surfaces:", final)
        self.assertIn("tabletop stones", final)
        self.assertIn("without letters, glyphs, emblems, symbols", final)
        self.assertNotIn("blank cloth banners", final)
        self.assertNotIn("flags, banners", final)
        self.assertIn("tabletop stone glyph", negative)
        self.assertIn("route marker glyph", negative)
        self.assertIn("uniform black border around whole image", negative)
        self.assertIn("thick black comic border", negative)
        self.assertIn("headband emblem", negative)
        self.assertIn("number on armor plate", negative)
        self.assertIn("digits on wooden gate", negative)
        self.assertIn("05 on gate", negative)
        self.assertIn("rectangular metal handle plate", negative)

    def test_flux2_klein_645_tang_rewrites_throne_and_gate_surfaces(self):
        cases = (
            (
                "Main subject: Emperor Taizong of Tang sitting on an imposing golden throne; "
                "Scene: Emperor Taizong of Tang sitting on an imposing golden throne",
                "low unmarked command dais",
                ("golden throne", "glyphs on throne"),
            ),
            (
                "Main subject: heavy gates of Baegam fortress opening without a fight; "
                "Scene: The heavy gates of Baegam fortress opening without a fight",
                "bare timber lintel",
                ("gate lintel calligraphy", "over-gate character board"),
            ),
        )
        base = (
            "Global visual world: Time range: 645year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 645 AD; Exact place: Liaodong Fortress; "
        )

        for source_tail, expected, negative_terms in cases:
            with self.subTest(expected=expected):
                prepared = _flux2_klein_prepare_source_prompt_text(base + source_tail)
                compact, _ = _compact_flux2_klein_4b_prompt(f"{prepared}\n{prepared}", "")
                final = _flux2_klein_md_positive_contract(
                    _flux2_klein_positive_contract_cleanup(compact),
                    prepared,
                )
                negative = _flux2_klein_md_negative_contract(prepared, final)

                self.assertIn(expected, final)
                self.assertIn("Visible unmarked surfaces:", final)
                for term in negative_terms:
                    self.assertIn(term, negative)

    def test_flux2_klein_645_tang_mirror_is_handleless_disk(self):
        source = (
            "Global visual world: Time range: 645year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 645 AD; Exact place: Liaodong Fortress; "
            "Main subject: cracked; "
            "Scene: A cracked, ancient bronze mirror reflecting a focused emperor"
        )

        prepared = _flux2_klein_prepare_source_prompt_text(source)
        compact, _ = _compact_flux2_klein_4b_prompt(f"{prepared}\n{prepared}", "")
        final = _flux2_klein_md_positive_contract(
            _flux2_klein_positive_contract_cleanup(compact),
            prepared,
        )
        negative = _flux2_klein_md_negative_contract(prepared, final)

        self.assertIn("polished bronze reflector disk", final)
        self.assertNotIn("hand mirror", final.lower())
        self.assertNotIn("mirror disk", final.lower())
        self.assertIn("mirror handle", negative)
        self.assertIn("round lens with handle", negative)

    def test_flux2_klein_645_tang_animal_scene_removes_clothing_and_species_negative(self):
        source = (
            "Global visual world: Time range: 645year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 645 AD; Exact place: Liaodong Fortress; "
            "Main subject: tiger tearing into its prey without mercy in the harsh; "
            "Scene: A tiger tearing into its prey without mercy in the harsh, freezing snow"
        )

        prepared = _flux2_klein_prepare_source_prompt_text(source)
        compact, _ = _compact_flux2_klein_4b_prompt(f"{prepared}\n{prepared}", "")
        final = _flux2_klein_md_positive_contract(
            _flux2_klein_positive_contract_cleanup(compact),
            prepared,
        )
        negative = _flux2_klein_md_negative_contract(prepared, final)
        negative_parts = {part.strip().lower() for part in negative.split(",")}

        self.assertIn("animal-only natural scene", final)
        self.assertNotIn("Visible clothing:", final)
        self.assertIn("tiger tearing into its prey", final)
        self.assertNotIn("tiger", negative_parts)
        self.assertNotIn("animal silhouette", negative_parts)

    def test_flux2_klein_645_tang_wolf_scene_removes_wolf_negative(self):
        source = (
            "Global visual world: Time range: 645year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 645 AD; Exact place: Liaodong Fortress; "
            "Main subject: vicious pack of wolves snarling defensively in the dark snow; "
            "Scene: A vicious pack of wolves snarling defensively in the dark snow"
        )

        prepared = _flux2_klein_prepare_source_prompt_text(source)
        compact, _ = _compact_flux2_klein_4b_prompt(f"{prepared}\n{prepared}", "")
        final = _flux2_klein_md_positive_contract(
            _flux2_klein_positive_contract_cleanup(compact),
            prepared,
        )
        negative = _flux2_klein_md_negative_contract(prepared, final)
        negative_parts = {part.strip().lower() for part in negative.split(",")}

        self.assertIn("animal-only natural scene", final)
        self.assertNotIn("Visible clothing:", final)
        self.assertNotIn("wolf", negative_parts)
        self.assertNotIn("animal silhouette", negative_parts)

    def test_flux2_klein_645_ansi_siege_weapons_become_timber_tools(self):
        source = (
            "Global visual world: Time range: 645year; Place scope: Ansi Fortress; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 645 AD; Exact place: Ansi Fortress; "
            "Main subject: Giant; "
            "Scene: Giant, terrifying mechanical siege weapons moving toward the wall"
        )

        prepared = _flux2_klein_prepare_source_prompt_text(source)
        compact, _ = _compact_flux2_klein_4b_prompt(f"{prepared}\n{prepared}", "")
        final = _flux2_klein_md_positive_contract(
            _flux2_klein_positive_contract_cleanup(compact),
            prepared,
        )
        negative = _flux2_klein_md_negative_contract(prepared, final)

        self.assertIn("pre-gunpowder timber siege pressure before Ansi Fortress", final)
        self.assertIn("rough wooden ladders", final)
        self.assertIn("blank packed-earth fortress wall", final)
        self.assertIn("thick black contours only around visible objects and figures", final)
        self.assertIn("free of drawn ink borders", final)
        self.assertNotRegex(final.lower(), r"\b(?:giant|mechanical|cannon|artillery|gun barrel|metal tube)\b")
        self.assertIn("cannon", negative)
        self.assertIn("artillery", negative)
        self.assertIn("gun barrel", negative)

    def test_flux2_klein_645_ansi_stained_glass_becomes_blank_cloth(self):
        source = (
            "Global visual world: Time range: 645year; Place scope: Ansi Fortress; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 645 AD; Exact place: Ansi Fortress; "
            "Main subject: beautiful stained-glass window of a hero shattering violently into pieces; "
            "Scene: A beautiful stained-glass window of a hero shattering violently into pieces"
        )

        prepared = _flux2_klein_prepare_source_prompt_text(source)
        compact, _ = _compact_flux2_klein_4b_prompt(f"{prepared}\n{prepared}", "")
        final = _flux2_klein_md_positive_contract(
            _flux2_klein_positive_contract_cleanup(compact),
            prepared,
        )
        negative = _flux2_klein_md_negative_contract(prepared, final)

        self.assertIn("heroic illusion breaking into battlefield reality", final)
        self.assertIn("blank dyed glory cloth", final)
        self.assertNotRegex(final.lower(), r"\b(?:stained|glass|window)\b")
        self.assertIn("stained-glass window", negative)

    def test_flux2_klein_645_ansi_plural_tigers_remove_clothing(self):
        source = (
            "Global visual world: Time range: 645year; Place scope: Ansi Fortress; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 645 AD; Exact place: Ansi Fortress; "
            "Main subject: giant tigers circling each other menacingly in a cold; "
            "Scene: Two giant tigers circling each other menacingly in a cold, snowy forest"
        )

        prepared = _flux2_klein_prepare_source_prompt_text(source)
        compact, _ = _compact_flux2_klein_4b_prompt(f"{prepared}\n{prepared}", "")
        final = _flux2_klein_md_positive_contract(
            _flux2_klein_positive_contract_cleanup(compact),
            prepared,
        )
        negative = _flux2_klein_md_negative_contract(prepared, final)
        negative_parts = {part.strip().lower() for part in negative.split(",")}

        self.assertIn("animal-only natural scene", final)
        self.assertNotIn("Visible clothing:", final)
        self.assertNotIn("lamellar armor", final)
        self.assertIn("animal wearing human armor", negative)
        self.assertIn("animal wearing human clothing", negative)
        self.assertNotIn("tiger", negative_parts)

    def test_flux2_klein_645_ansi_symbolic_failures_become_period_evidence(self):
        cases = (
            (
                "The artificial mountain looming menacingly over the stone battlements",
                "man-made packed-earth siege ramp before Ansi Fortress",
                r"\b(?:artificial mountain|dirt mountain)\b",
            ),
            (
                "The base of the artificial dirt mountain starting to slide and collapse outward",
                "collapsing base of the man-made packed-earth siege ramp before Ansi Fortress",
                r"\b(?:artificial dirt mountain|stable ramp|looming menacingly)\b",
            ),
            (
                "A hellish landscape of endless fire, clashing armies, and storm clouds",
                "wide smoky battlefield pressure before Ansi Fortress",
                r"\bhellish\b",
            ),
            (
                "A massive Chinese dragon shadow looming ominously over a blood-red horizon",
                "blood-red dawn smoke over the siege lines",
                r"\b(?:Chinese dragon|dragon shadow)\b",
            ),
            (
                "A massive, heavy stone wheel rolling over broken wooden shields",
                "broken shield pressure under simple siege debris",
                r"\b(?:massive|heavy|stone wheel)\b",
            ),
            (
                "A dark executioner's block waiting patiently in a gloomy courtyard",
                "plain stone punishment block in a gloomy fortress yard",
                r"\bexecutioner's block\b",
            ),
            (
                "A decaying skull wearing a rusty helmet, half-buried in the dirt",
                "flat lamellar armor plates half-buried in battlefield dirt",
                r"\bskull wearing\b",
            ),
            (
                "A golden chalice spilling dark red blood onto the dry, cracked earth",
                "plain bronze cup and cracked earth evidence",
                r"\b(?:golden chalice|goblet)\b",
            ),
            (
                "A desolate gladiator arena completely covered in shadows and deep blood stains",
                "shadowed packed-earth battlefield yard",
                r"\b(?:gladiator|arena|colosseum)\b",
            ),
            (
                "A cold, calculating hand moving a single piece on a bloody ancient chessboard",
                "low command workbench with pebble route counters",
                r"\b(?:chess|chessboard|pawn)\b",
            ),
            (
                "A trapped mouse staring directly and fiercely at a massive shadow",
                "small isolated fortress under vast siege shadow",
                r"\bmouse\b",
            ),
            (
                "A silver royal platter filled with rotten apples and spoiled food on a palace floor",
                "spoiled ration evidence on a plain tray",
                r"\b(?:silver royal platter|rotten apples|palace floor)\b",
            ),
            (
                "A father stepping forward, his face completely covered in enemy blood",
                "blood-streaked adult defender stepping forward",
                r"\bface completely covered\b",
            ),
            (
                "Emperor Taizong covering his face, retreating miserably through a swamp",
                "Emperor Taizong retreating through a muddy swamp with face covered",
                r"\b(?:courtyard retreat|blank signboard above door|doorway facade)\b",
            ),
            (
                "A modern eye staring unblinkingly at a dark, burning battlefield in the reflection",
                "Emperor Taizong's stern normal human face under battlefield firelight",
                r"\b(?:modern eye|full-body heroine|female warrior)\b",
            ),
            (
                "A bloody boot stepping heavily onto a pristine white marble floor",
                "period-local lower-leg footfall on rough fortress floor",
                r"\b(?:marble|bloody boot|muddy boot)\b",
            ),
            (
                "A bloody footprint stamped directly over an intricately woven, clean silk robe",
                "object-only small bloody sandal footprint on a crumpled blank silk robe",
                r"\b(?:wall-sized footprint|bloody footprint on wall|red handprint|standing soldier beside footprint)\b",
            ),
            (
                "Bright sparks explode from clashing iron weapons in the darkness",
                "solid leaf-shaped iron spearhead blades clashing in darkness",
                r"\b(?:European longsword|cruciform crossguard|knight sword)\b",
            ),
            (
                "Two intersecting swords sparking violently in the pitch black",
                "solid leaf-shaped iron spearhead blades clashing in darkness",
                r"\b(?:intersecting swords|visible sword hilt|cruciform crossguard)\b",
            ),
        )
        for scene, expected, forbidden in cases:
            with self.subTest(scene=scene):
                source = (
                    "Global visual world: Time range: 645year; Place scope: Ansi Fortress; "
                    "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
                    "Year/period: 645 AD; Exact place: Ansi Fortress; "
                    f"Main subject: {scene}; Scene: {scene}"
                )
                prepared = _flux2_klein_prepare_source_prompt_text(source)
                compact, _ = _compact_flux2_klein_4b_prompt(f"{prepared}\n{prepared}", "")
                final = _flux2_klein_md_positive_contract(
                    _flux2_klein_positive_contract_cleanup(compact),
                    prepared,
                )

                self.assertIn(expected, final)
                self.assertNotRegex(final.lower(), forbidden)

                if "artificial" in scene and "mountain" in scene:
                    self.assertNotIn("blank cloth banners", final)
                    self.assertNotIn("flags, banners", final)
                    negative = _flux2_klein_md_negative_contract(prepared, final)
                    self.assertIn("black X mark on flag", negative)
                    self.assertIn("border-edge marked flag", negative)
                    self.assertIn("cropped marked flag", negative)
                if "slide and collapse" in scene:
                    self.assertIn("bulge and slump outward", final)
                    self.assertIn("bent retaining timbers", final)
                    self.assertIn("tipped dirt baskets", final)
                if "spoiled food" in scene:
                    self.assertIn("ground-only crop", final)
                    self.assertIn("the background is only packed earth", final)
                    negative = _flux2_klein_md_negative_contract(prepared, final)
                    self.assertIn("small white square on door", negative)
                    self.assertIn("white square label on door", negative)
                    self.assertIn("door placard", negative)
                if "retreating miserably through a swamp" in scene:
                    self.assertIn("knee-deep muddy swamp water", final)
                    self.assertIn("open reed swamp", final)
                    negative = _flux2_klein_md_negative_contract(prepared, final)
                    self.assertIn("blank signboard above door", negative)
                    self.assertIn("empty rectangular lintel panel", negative)
                    self.assertIn("rectangular signboard frame", negative)
                if "modern eye staring" in scene:
                    self.assertIn("normal dark human eyes", final)
                    self.assertIn("both pupils stay dark and ordinary", final)
                    self.assertIn("warm orange firelight grazes the cheekbone", final)
                    self.assertIn("open sky continue through every image edge", final)
                    self.assertIn("edge-to-edge full-bleed crop", final)
                    negative = _flux2_klein_md_negative_contract(prepared, final)
                    self.assertIn("full-body heroine replacing eye", negative)
                    self.assertIn("young heroine in battlefield", negative)
                    self.assertIn("camera-lens eye", negative)
                    self.assertIn("one glowing eye", negative)
                    self.assertIn("fortress building behind eye close-up", negative)
                    self.assertIn("uniform black border around face close-up", negative)
                    self.assertIn("black outer stroke around entire image", negative)
                    self.assertIn("picture-in-picture eye reflection", negative)
                    self.assertIn("separate scene inside eye", negative)
                if "boot stepping" in scene:
                    self.assertIn("open-toe rawhide sandal straps", final)
                    self.assertNotRegex(final.lower(), r"\b(?:rawhide shoe|closed boot silhouette|muddy boot)\b")
                    negative = _flux2_klein_md_negative_contract(prepared, final)
                    self.assertIn("boot with flame inside", negative)
                    self.assertIn("modern boot", negative)
                    self.assertIn("closed boot silhouette", negative)
                    self.assertIn("raised boot heel", negative)
                if "footprint stamped" in scene:
                    self.assertIn("ground-only crop", final)
                    self.assertIn("zero standing figures", final)
                    negative = _flux2_klein_md_negative_contract(prepared, final)
                    self.assertIn("bloody footprint on wall", negative)
                    self.assertIn("red handprint on wall", negative)
                    self.assertIn("standing soldier beside footprint", negative)
                    self.assertIn("wall-sized footprint", negative)
                if "clashing iron weapons" in scene or "intersecting swords" in scene:
                    self.assertIn("solid closed leaf-shaped iron spearhead blades", final)
                    self.assertIn("sharp tapered points", final)
                    self.assertIn("object-only close crop", final)
                    self.assertIn("the only visible objects are solid spearhead blades", final)
                    negative = _flux2_klein_md_negative_contract(prepared, final)
                    self.assertIn("cruciform crossguard", negative)
                    self.assertIn("European longsword", negative)
                    self.assertIn("X-shaped crossed swords", negative)
                    self.assertIn("visible sword hilt", negative)
                    self.assertIn("hand gripping sword hilt", negative)
                    self.assertIn("metal cylinder", negative)
                    self.assertIn("hollow metal tube", negative)
                    self.assertIn("building background behind weapons", negative)
                    self.assertIn("visible hand gripping shaft", negative)
                    self.assertIn("number on spear socket", negative)
                    self.assertIn("glyph on spear socket", negative)

    def test_flux2_klein_645_ansi_battlefield_bans_gatehouse_plaque_letters(self):
        source = (
            "Global visual world: Time range: 645year; Place scope: Ansi Fortress; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 645 AD; Exact place: Ansi Fortress; "
            "Main subject: hellish landscape of endless fire; "
            "Scene: A hellish landscape of endless fire, clashing armies, and storm clouds"
        )

        prepared = _flux2_klein_prepare_source_prompt_text(source)
        compact, _ = _compact_flux2_klein_4b_prompt(f"{prepared}\n{prepared}", "")
        final = _flux2_klein_md_positive_contract(
            _flux2_klein_positive_contract_cleanup(compact),
            prepared,
        )
        negative = _flux2_klein_md_negative_contract(prepared, final)

        self.assertIn("one continuous low blank fortress wall", final)
        self.assertIn("open sky sits directly above the battlement line", final)
        self.assertIn("only plain crenellated stone blocks and smoke", final)
        self.assertIn("wall faces stay uninterrupted blank stone", final)
        self.assertIn("open sky above plain battlements", final)
        self.assertIn("ANSI letters", negative)
        self.assertIn("English letters on fortress", negative)
        self.assertIn("black letters on plaque", negative)

    def test_flux2_klein_645_ansi_animal_drawn_cart_is_not_animal_only(self):
        sources = (
            (
                "Global visual world: Time range: 645year; Place scope: Ansi Fortress; "
                "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
                "Year/period: 645 AD; Exact place: Ansi Fortress; "
                "Main subject: animal-drawn open wooden cart with spoked wooden wheels and rope harness teetering dangerously on the very edge of a high; "
                "Scene: A animal-drawn open wooden cart with spoked wooden wheels and rope harness teetering dangerously on the very edge of a high cliff"
            ),
            (
                "Global visual world: Time range: 645year; Place scope: Ansi Fortress; "
                "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
                "Year/period: 645 AD; Exact place: Ansi Fortress; "
                "Main subject: Chinese emperor's carriage stuck deeply in freezing; "
                "Scene: The Chinese emperor's carriage stuck deeply in freezing, thick mud"
            ),
        )

        for source in sources:
            with self.subTest(source=source):
                prepared = _flux2_klein_prepare_source_prompt_text(source)
                compact, _ = _compact_flux2_klein_4b_prompt(f"{prepared}\n{prepared}", "")
                final = _flux2_klein_md_positive_contract(
                    _flux2_klein_positive_contract_cleanup(compact),
                    prepared,
                )
                negative = _flux2_klein_md_negative_contract(prepared, final)

                self.assertIn("period wooden command cart under siege pressure", final)
                self.assertIn("one fully visible harnessed horse or ox body attached to the cart", final)
                self.assertIn("foreground ground contains stones, mud, snow patches, cart tracks, and smoke", final)
                self.assertIn("handlers", final)
                self.assertNotIn("animal-only natural scene", final)
                self.assertNotIn("prey", final)
                self.assertNotIn("paw tracks", final)
                self.assertIn("random foreground animal", negative)
                self.assertIn("extra animal beside cart", negative)

    def test_flux2_klein_645_ansi_bronze_mirror_demonic_face_stays_mirror(self):
        source = (
            "Global visual world: Time range: 645year; Place scope: Ansi Fortress; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 645 AD; Exact place: Ansi Fortress; "
            "Main subject: cracked; "
            "Scene: A cracked, ancient bronze mirror reflecting a demonic, smiling face"
        )

        prepared = _flux2_klein_prepare_source_prompt_text(source)
        compact, _ = _compact_flux2_klein_4b_prompt(f"{prepared}\n{prepared}", "")
        final = _flux2_klein_md_positive_contract(
            _flux2_klein_positive_contract_cleanup(compact),
            prepared,
        )
        negative = _flux2_klein_md_negative_contract(prepared, final)

        self.assertIn("small flat cracked polished bronze reflector disk", final)
        self.assertIn("cloudy warped face-shadow stains", final)
        self.assertIn("small coin-like flat bronze reflector disk", final)
        self.assertNotIn("mud-smeared adult warrior face", final)
        self.assertNotIn("demonic", final.lower())
        self.assertIn("warrior portrait replacing mirror", negative)
        self.assertIn("modern hand mirror handle", negative)
        self.assertIn("clear portrait inside mirror", negative)
        self.assertIn("red star on banner", negative)

    def test_flux2_klein_md_contract_prefers_historical_visual_context_scene(self):
        source = (
            "UNMARKED SURFACE LOCK - Scene: Every visible surface is blank physical material only. || "
            "Historical visual context: Time range: 645year; "
            "Place scope: Liaodong Fortress and 645 Tang-Goguryeo Liaodong campaign routes; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian local historical setting; "
            "Year/period: 645 AD; Tang-Goguryeo Liaodong campaign; "
            "Exact place: Liao River crossing toward Liaodong Fortress; "
            "Scene evidence: Tang soldiers, muddy Liao River crossing, horse tack, plain shields, wet reeds, distant Liaodong ramparts, cold wind; "
            "Main subject: Tang and Goguryeo forces; "
            "Scene: Tang soldiers cross the wide muddy Liao River toward Liaodong Fortress, with horse tack, plain shields, wet reeds, water spray, cold wind, and distant fortress ramparts; "
            "NARRATION VISUAL ALIGNMENT: match this cut's spoken moment || "
            "IMAGE QUALITY LOCK - choose the camera angle from the Scene: three-quarter face"
        )
        compact = (
            "645 AD; Tang-Goguryeo Liaodong campaign at Liao River crossing toward Liaodong Fortress. "
            "Scene subject: Tang and Goguryeo forces. "
            "Visible action: Human anatomy contract: each visible adult has one head and one torso."
        )

        final = _flux2_klein_md_positive_contract(compact, source)

        self.assertIn("Tang soldiers cross the wide muddy Liao River", final)
        self.assertNotIn("Human anatomy contract", final)
        self.assertNotIn("Sui-Goguryeo", final)
        self.assertNotIn("Goguryeo-Sui", final)

    def test_flux2_klein_md_contract_uses_fields_when_compact_starts_with_surface_ban(self):
        source = (
            "Historical visual context: Time range: 645year; "
            "Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian local historical setting; "
            "Year/period: 645 AD; Exact place: Liaodong Fortress; "
            "Main subject: heavy gates of Baegam fortress opening without a fight; "
            "Scene: The heavy gates of Baegam fortress opening without a fight; "
            "NARRATION VISUAL ALIGNMENT: match this cut's spoken moment || "
            "IMAGE QUALITY LOCK - crisp silhouettes"
        )
        compact = (
            "Every visible surface is blank physical material only. Zero language glyphs, zero alphabet shapes, "
            "zero character-like strokes. Scene subject: heavy gates of Baegam fortress opening "
            "Visible action: Human anatomy contract: each visible adult has one head."
        )

        final = _flux2_klein_md_positive_contract(compact, source)

        self.assertIn("The heavy gates of Baegam fortress opening without a fight", final)
        self.assertNotIn("Every visible surface is blank physical material only", final)
        self.assertNotIn("Human anatomy contract", final)

    def test_flux2_klein_ch1_ep22_local_historical_context_sentence_is_clean(self):
        source = (
            "Global visual world: Time range: 642year 9; Place scope: ancient Northeast Asia; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian local historical setting; "
            "Year/period: 642 AD; Sui-Goguryeo war, 612 AD; Exact place: Pyongyang Fortress; "
            "Main subject: Yeongaesomun turning his back on the bodies; "
            "Scene: Yeongaesomun turning his back on the bodies, looking towards the palace"
        )
        compact, _ = _compact_flux2_klein_4b_prompt(source, "")
        final = _flux2_klein_md_positive_contract(compact, source)

        self.assertIn("642 AD; Pyongyang Fortress; Goguryeo court and frontier historical setting", final)
        self.assertNotIn("court crisis Goguryeo court", final)
        self.assertNotIn("Sui-Goguryeo", final)
        self.assertNotIn("Goguryeo-Sui", final)

    def test_flux2_klein_ch1_ep22_problem_cuts_get_specific_contracts(self):
        cases = (
            (
                "Main subject: pristine stone monument casting a long; "
                "Scene: A pristine stone monument casting a long, dark shadow over skulls",
                ("plain unmarked stone slab", "rough blank stone face", "skulls"),
                ("Sui-Goguryeo", "Goguryeo-Sui", "court crisis Goguryeo court"),
                ("inscription", "carved characters"),
            ),
            (
                "Main subject: cold; Scene: A cold, unblinking eye staring directly into the lens, reflecting fire",
                ("Single eye forge-flame reflection close-up", "one cold human eye", "orange fire reflected"),
                ("window", "glass", "stained glass"),
                ("window", "stained glass", "second eye"),
            ),
            (
                "Main subject: Chained peasant conscripts walking endlessly into a dark; "
                "Scene: Chained peasant conscripts walking endlessly into a dark, dusty battlefield",
                ("Full-bleed chained prisoner march scene", "peasant conscripts", "blank smoke-filled sky"),
                ("Sui-Goguryeo", "Goguryeo-Sui", "court crisis Goguryeo court"),
                ("sky text", "floating glyph", "wall text"),
            ),
            (
                "Main subject: heavy iron gate slowly creaking open to reveal a darker; "
                "Scene: A heavy iron gate slowly creaking open to reveal a darker, terrifying path",
                ("plain heavy iron gate opening into darkness", "plain wooden gate leaves", "continuous stone material"),
                ("Sui-Goguryeo", "Goguryeo-Sui", "court crisis Goguryeo court"),
                ("wall sign with characters", "gate plaque", "written gate board"),
            ),
            (
                "Main subject: fragile diplomatic scroll tearing cleanly down the middle; "
                "Scene: A fragile diplomatic scroll tearing cleanly down the middle",
                ("snapped diplomatic cord between closed bamboo packet halves", "closed tan bamboo packet halves", "strict top-down ground-only"),
                ("Sui-Goguryeo", "Goguryeo-Sui", "court crisis Goguryeo court"),
                ("scroll text", "blank white sheet", "smoke cloud near top edge"),
            ),
            (
                "Main subject: luxurious; Scene: A luxurious, dark cape casting a shadow that looks like a crumbling city",
                ("dark Goguryeo command cloak", "crumbling wall shadow", "rough timber post"),
                ("Sui-Goguryeo", "Goguryeo-Sui", "court crisis Goguryeo court"),
                ("modern skyline", "stained glass", "window grid"),
            ),
            (
                "Main subject: golden chalice spilling dark red blood onto the cold; "
                "Scene: A golden chalice spilling dark red blood onto the cold, hard dirt",
                ("unmarked bronze chalice", "dark red liquid", "packed earth"),
                ("Sui-Goguryeo", "Goguryeo-Sui", "court crisis Goguryeo court"),
                ("cup inscription", "modern wine glass", "glass cup"),
            ),
            (
                "Main subject: massive meat grinder turning slowly; "
                "Scene: A massive meat grinder turning slowly, fueled by countless human silhouettes",
                ("preindustrial wooden capstan and stone crushing wheel", "hand-powered wooden capstan", "clay soldier tokens"),
                ("meat grinder", "Sui-Goguryeo", "Goguryeo-Sui"),
                ("steam engine", "industrial machine", "modern meat grinder"),
            ),
            (
                "Main subject: hellish landscape of endless fire; "
                "Scene: A hellish landscape of endless fire, clashing armies, and black storm clouds",
                ("full-bleed hellish Goguryeo battlefield", "open battlefield", "storm clouds"),
                ("Sui-Goguryeo", "Goguryeo-Sui", "court crisis Goguryeo court"),
                ("black outer frame", "letterbox bars", "title panel"),
            ),
            (
                "Main subject: razor-sharp surgical blade gleaming intensely; "
                "Scene: A razor-sharp surgical blade gleaming intensely under a harsh, cold, clinical light",
                ("object-only plain straight iron blade", "whetstone", "cold side light"),
                ("surgical blade", "clinical light", "Sui-Goguryeo"),
                ("blue glow", "modern scalpel", "building sign"),
            ),
            (
                "Main subject: old; Scene: An old, fairy-tale history book being thrown violently into a blazing fire",
                ("object-only burning blank fiber packet", "cord-tied blank fiber packet", "plain unmarked fiber leaves"),
                ("Sui-Goguryeo", "Goguryeo-Sui", "court crisis Goguryeo court"),
                ("book text", "printed lines", "cover title"),
            ),
        )
        for scene, expected_parts, forbidden_prompt_parts, expected_negative_parts in cases:
            with self.subTest(scene=scene):
                source = (
                    "Global visual world: Time range: 642year 9; Place scope: ancient Northeast Asia, "
                    "Goguryeo-related court and frontier settings; Culture scope: Goguryeo and neighboring "
                    "ancient Northeast Asian political and military world; Year/period: 642 AD; "
                    "Sui-Goguryeo war, 612 AD; Exact place: Pyongyang Fortress; "
                    f"{scene}"
                )
                compact, negative = _compact_flux2_klein_4b_prompt(source, "")
                final = _flux2_klein_md_positive_contract(compact, source)
                guarded_negative = _flux2_klein_md_negative_contract(final, negative)

                for expected in expected_parts:
                    self.assertIn(expected, final)
                for forbidden in forbidden_prompt_parts:
                    self.assertNotIn(forbidden, final)
                for expected_negative in expected_negative_parts:
                    self.assertIn(expected_negative, guarded_negative)

    def test_common_anatomy_lock_blocks_shared_head_and_double_horse_body(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 415 CE; Exact place: Goguryeo-Silla frontier road; "
                "Scene: a Goguryeo mounted envoy rides toward a Silla camp; "
                "Style: simple cartoon illustration"
            ),
            "simple cartoon illustration",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)

        self.assertIn("A horse or other quadruped can never have one head attached to two torsos", prompt)
        self.assertIn("Every readable horse is one coherent animal", prompt)
        self.assertIn("Never render a centaur", prompt)
        self.assertIn("horse with two bodies", negative)
        self.assertIn("two animal bodies sharing one head", negative)
        self.assertIn("human torso on horse body", negative)
        self.assertIn("horse-human hybrid", negative)

    def test_flux2_klein_negative_blocks_centaur_horse_human_hybrid(self):
        source = (
            "Year/period: 645 AD; Exact place: Ansi Fortress; "
            "Main subject: Tang mounted scouts; "
            "Scene: Tang mounted scouts ride tired horses below the fortress wall; "
            "Scene evidence: horse tack, plain shields, muddy road"
        )
        negative = _flux2_klein_md_negative_contract(source, source)

        self.assertIn("centaur", negative)
        self.assertIn("human torso on horse body", negative)
        self.assertIn("horse-human hybrid", negative)

    def test_ep13_banner_scene_keeps_exact_three_banners_not_people(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: three distinct enemy banners waving together in a muddy storm; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("BANNER COUNT EVIDENCE LOCK", prompt)
        self.assertIn("BANNER EVIDENCE FRAME", prompt)
        self.assertIn("exactly three separate blank cloth military banners", prompt)
        self.assertIn("BANNER EVIDENCE ONLY FRAME", comfy_prompt)
        self.assertIn("exactly three separate", comfy_prompt)
        self.assertIn("no fourth banner", comfy_prompt)
        self.assertNotIn("TEXTLESS SURFACE FIRST RULE", comfy_prompt)
        self.assertNotIn("Japanese torii gate", comfy_prompt)
        self.assertNotIn("standing soldiers", comfy_prompt)
        self.assertNotIn("close group story moment", comfy_prompt)
        self.assertIn("blank banner missing from scene", comfy_negative)
        self.assertIn("standing soldiers replacing banners", comfy_negative)
        self.assertIn("three people replacing three banners", comfy_negative)
        self.assertIn("fourth banner", comfy_negative)
        self.assertIn("Japanese torii gate", comfy_negative)

    def test_ep13_boats_plural_routes_to_maritime_landing_lock(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: Wa soldiers jumping off boats onto a beach, holding torches and swords; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, "")

        self.assertIn("MARITIME LANDING EVIDENCE LOCK", prompt)
        self.assertIn("holding torches and swords with small sleeve-covered functional grips", prompt)
        self.assertIn("MARITIME ACTION FIRST RULE", comfy_prompt)
        self.assertIn("jumping from the boat", comfy_prompt)
        self.assertIn("one foot planted on wet sand", comfy_prompt)
        self.assertIn("at least one short straight iron sword clearly visible", comfy_prompt)
        self.assertIn("plain narrow grips or small ring-pommel", comfy_prompt)
        self.assertIn("no button plackets", comfy_prompt)
        self.assertNotIn("TEXTLESS SURFACE FIRST RULE", comfy_prompt)
        self.assertNotIn("Japanese torii gate", comfy_prompt)
        self.assertIn("missing torch when scene names torch", comfy_negative)
        self.assertIn("missing boat", comfy_negative)
        self.assertIn("Japanese torii gate", comfy_negative)
        self.assertIn("all raiders standing inside boat", comfy_negative)
        self.assertIn("missing sword when scene names sword", comfy_negative)
        self.assertIn("cruciform crossguard", comfy_negative)
        self.assertIn("buttoned shirt", comfy_negative)
        final_prompt, final_negative = _promote_ep13_final_scene_overrides(
            f"TEXTLESS SURFACE FIRST RULE: common guard. {comfy_prompt}",
            comfy_negative,
        )
        self.assertTrue(final_prompt.startswith("No visible text, no title"))
        self.assertIn("beach landing action shot", final_prompt)
        self.assertIn("largest human figure must already be outside the boat", final_prompt)
        self.assertIn("No gate, no shrine gate", final_prompt)
        self.assertIn("Japanese torii gate", final_negative)
        self.assertIn("largest raider inside boat", final_negative)
        self.assertIn("T-shaped hilt", final_negative)

    def test_ep13_desperate_riding_scene_stays_mounted_not_kneeling(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: a desperate Silla messenger riding a horse into a harsh blizzard; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)

        self.assertIn("MOUNTED TRAVEL EVIDENCE LOCK", prompt)
        self.assertIn("horse-and-rider pair", prompt)
        self.assertIn("MOUNTED TRAVEL FIRST RULE", comfy_prompt)
        self.assertIn("one complete horse-and-rider pair", comfy_prompt)
        self.assertIn("harsh whiteout blizzard", comfy_prompt)
        self.assertIn("no battle helmet or heavy armor", comfy_prompt)
        self.assertIn("no roofed houses or tiled buildings", comfy_prompt)
        self.assertNotIn("TEXTLESS SURFACE FIRST RULE", comfy_prompt)
        self.assertNotIn("SUBMISSION AND DESPERATION POSE FIRST RULE", comfy_prompt)
        self.assertIn("missing horse", comfy_negative)
        self.assertIn("rider not seated on horse", comfy_negative)
        self.assertIn("courtyard group replacing horse-and-rider pair", comfy_negative)
        self.assertIn("armored soldier replacing messenger", comfy_negative)
        self.assertIn("no blizzard", comfy_negative)
        self.assertIn("tiled roof building", comfy_negative)

    def test_ep13_silla_king_room_blocks_modern_suits(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: a Silla king looking terrified inside a dark, gloomy throne room; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)

        self.assertIn("EARLY SILLA RULER ROOM FIRST RULE", comfy_prompt)
        self.assertIn("TEXTLESS IMAGE RULE", comfy_prompt)
        self.assertIn("floor mat or low backless wooden dais", comfy_prompt)
        self.assertIn("no chair, no backrest, and no armrests", comfy_prompt)
        self.assertNotIn("business suit", comfy_prompt)
        self.assertNotIn("modern suit", comfy_prompt)
        self.assertNotIn("TEXTLESS SURFACE FIRST RULE", comfy_prompt)
        self.assertIn("business suit", comfy_negative)
        self.assertIn("buttoned coat", comfy_negative)
        self.assertIn("wall switch", comfy_negative)
        self.assertIn("modern door knob", comfy_negative)
        self.assertIn("black modern shoes", comfy_negative)
        self.assertIn("header board with characters", comfy_negative)

    def test_ep13_final_silla_room_override_returns_to_front(self):
        prompt = (
            "TEXTLESS SURFACE FIRST RULE: common textless guard. "
            "PREMODERN INTERIOR PROP FIRST RULE: common prop guard. "
            "EARLY SILLA RULER ROOM FIRST RULE: render one early Silla ruler."
        )
        comfy_prompt, comfy_negative = _promote_ep13_final_scene_overrides(prompt, "")

        self.assertTrue(comfy_prompt.startswith("FINAL EP13 EARLY SILLA RULER ROOM OVERRIDE"))
        self.assertLess(
            comfy_prompt.index("FINAL EP13 EARLY SILLA RULER ROOM OVERRIDE"),
            comfy_prompt.index("TEXTLESS SURFACE FIRST RULE"),
        )
        self.assertIn("Crop out every door", comfy_prompt)
        self.assertIn("no round door knob", comfy_prompt)
        self.assertIn("only when the Scene explicitly names armrests", comfy_prompt)
        self.assertIn("no paper lattice window", comfy_prompt)
        self.assertIn("no chest badge", comfy_prompt)
        self.assertIn("wall switch", comfy_negative)
        self.assertIn("modern door handle", comfy_negative)
        self.assertIn("side door", comfy_negative)
        self.assertIn("paper lattice window", comfy_negative)
        self.assertIn("chest badge", comfy_negative)

    def test_ep13_final_mounted_blizzard_override_returns_to_front(self):
        prompt = (
            "TEXTLESS SURFACE FIRST RULE: common textless guard. "
            "PREMODERN INTERIOR PROP FIRST RULE: common prop guard. "
            "MOUNTED TRAVEL FIRST RULE: render one mounted courier."
        )
        comfy_prompt, comfy_negative = _promote_ep13_final_scene_overrides(prompt, "")

        self.assertTrue(comfy_prompt.startswith("FINAL EP13 MOUNTED BLIZZARD OVERRIDE"))
        self.assertLess(
            comfy_prompt.index("FINAL EP13 MOUNTED BLIZZARD OVERRIDE"),
            comfy_prompt.index("TEXTLESS SURFACE FIRST RULE"),
        )
        self.assertIn("one complete horse", comfy_prompt)
        self.assertIn("empty exposed mountain or frontier road", comfy_prompt)
        self.assertIn("roofed house in blizzard", comfy_negative)
        self.assertIn("horse with two bodies", comfy_negative)

    def test_flux2_klein_compacts_ep13_fortress_gate_prompt(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
                "Scene: the massive, imposing gates of Goguryeo fortress looming in the fog; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, compact_negative = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertTrue(compact.startswith("400-415 CE"))
        self.assertIn("Low crop below roof height", compact)
        self.assertIn("empty unmarked wooden beams", compact)
        self.assertIn("plain raw wood", compact)
        self.assertLess(len(compact), 1800)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
        self.assertNotRegex(compact, r"\b(?:No|no|Do not|do not|FINAL|OVERRIDE|LOCK)\b")
        self.assertNotIn("tiled roof", compact.lower())
        self.assertIn("readable writing", compact_negative)
        self.assertIn("signboard", compact_negative)

    def test_flux2_klein_compacts_ep13_crown_object_without_positive_hands(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: a broken Silla crown lying discarded in the dirt next to armored boots; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, compact_negative = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Object-only still life", compact)
        self.assertIn("early Silla gold crown fragment", compact)
        self.assertIn("The visible inventory is crown fragment", compact)
        self.assertLess(len(compact), 1800)
        self.assertNotRegex(compact, r"\bhand\w*\b|\bfinger\w*\b")
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
        self.assertNotRegex(compact, r"\b(?:No|no|Do not|do not|FINAL|OVERRIDE|LOCK)\b")

    def test_flux2_klein_compacts_ep13_submission_symbol_without_gate(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: a Silla royal emblem resting submissively below the massive Goguryeo flag; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, compact_negative = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Symbolic submission still life", compact)
        self.assertIn("plain Silla tribute token", compact)
        self.assertIn("Goguryeo military standard pole", compact)
        self.assertNotIn("gate", compact.lower())
        self.assertNotRegex(compact, r"\bhand\w*\b|\bfinger\w*\b")
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
        self.assertNotRegex(compact, r"\b(?:No|no|Do not|do not|FINAL|OVERRIDE|LOCK)\b")

    def test_flux2_klein_compacts_ep13_gwanggaeto_command_as_single_ruler(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: King Gwanggaeto raising his hand with an absolutely confident expression; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, _ = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Single-ruler command scene", compact)
        self.assertIn("exactly one King Gwanggaeto", compact)
        self.assertIn("one small sleeve-covered command hand", compact)
        self.assertIn("rough timber hall", compact)
        self.assertLess(len(compact), 1800)
        self.assertNotIn("group portrait", compact.lower())
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
        self.assertNotRegex(compact, r"\b(?:No|no|Do not|do not|FINAL|OVERRIDE|LOCK)\b")

    def test_flux2_klein_compacts_ep13_strategic_gaze_before_campaign_board(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: the king's cold, calculating eyes locking onto the southern part of an ancient map; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, _ = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Tight over-the-board strategic gaze scene", compact)
        self.assertIn("one King Gwanggaeto", compact)
        self.assertIn("low dark wooden campaign board", compact)
        self.assertIn("raised blank clay markers", compact)
        self.assertNotRegex(compact, r"\bhand\w*\b|\bfinger\w*\b")
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
        self.assertNotRegex(compact, r"\b(?:No|no|Do not|do not|FINAL|OVERRIDE|LOCK)\b")

    def test_flux2_klein_compacts_ep13_blade_draw_with_hidden_grip_area(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: the king smirking arrogantly and drawing his sharp sword; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, _ = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Single-ruler blade-draw scene", compact)
        self.assertIn("one King Gwanggaeto", compact)
        self.assertIn("short straight iron blade", compact)
        self.assertIn("Wide sleeve folds bury both wrists around the hilt area", compact)
        self.assertIn("The visible weapon inventory is one blade and one scabbard", compact)
        self.assertNotRegex(compact, r"\bfinger\w*\b")
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
        self.assertNotRegex(compact, r"\b(?:No|no|Do not|do not|FINAL|OVERRIDE|LOCK)\b")

    def test_flux2_klein_compacts_ep13_history_book_as_ancient_record_bundle(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: an ancient history book covered in dust and faint blood stains; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, compact_negative = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Object-only wooden record bundle", compact)
        self.assertIn("Twenty long narrow dark wooden tablets", compact)
        self.assertIn("Cord loops bind the tablets", compact)
        self.assertNotIn("book", compact.lower())
        self.assertIn("modern book", compact_negative)
        self.assertIn("paper stack", compact_negative)
        self.assertIn("white studio background", compact_negative)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_compacts_ep13_shattered_glass_as_bronze_mirror_omen(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: a shattered glass reflecting a dark, burning ancient palace; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, compact_negative = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Object-only bronze mirror omen", compact)
        self.assertIn("Broken polished bronze mirror fragments", compact)
        self.assertIn("abstract orange firelight", compact)
        self.assertNotIn("palace", compact.lower())
        self.assertIn("ornate palace reflection", compact_negative)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_compacts_ep13_peninsula_map_as_strategy_board(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: dark storm clouds gathering over an ancient map of the Korean peninsula; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, compact_negative = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Symbolic war-cloud strategy board", compact)
        self.assertIn("Raised blank clay markers", compact)
        self.assertIn("abstract southern war-zone layout", compact)
        self.assertNotIn("peninsula", compact.lower())
        self.assertIn("modern map", compact_negative)
        self.assertIn("geographic outline map", compact_negative)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_compacts_ep13_dropped_weapons_as_separate_weapon_pile(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: exhausted Silla soldiers dropping their weapons in the mud; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, compact_negative = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Muddy battlefield aftermath", compact)
        self.assertIn("separate abandoned weapon pile", compact)
        self.assertIn("blank clothing surfaces", compact)
        self.assertIn("closed sleeves", compact)
        self.assertIn("visible letters", compact_negative)
        self.assertNotIn("{material}", compact)
        self.assertNotIn("{style}", compact)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_prioritizes_ep13_mass_goguryeo_march_over_mounted_guard(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: an endless column of Goguryeo cavalry marching aggressively through dust with infantry beside them; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        final_prompt, final_negative = _promote_ep13_final_scene_overrides(
            f"MOUNTED TRAVEL FIRST RULE: common guard. {comfy_prompt}",
            comfy_negative,
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(final_prompt, final_negative)

        self.assertIn("Mass Goguryeo army march", compact)
        self.assertIn("infantry on foot", compact)
        self.assertIn("mounted cavalry", compact)
        self.assertIn("Each visible horse is separate", compact)
        self.assertNotIn("Mounted messenger", compact)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
        self.assertNotRegex(compact, r"\b(?:No|no|Do not|do not|FINAL|OVERRIDE|LOCK)\b")

    def test_flux2_klein_prioritizes_ep13_capital_settlement_over_empty_cavalry_ring(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: the Silla capital completely surrounded by dark armored cavalry; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, compact_negative = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Wide tactical siege view of the Silla capital", compact)
        self.assertIn("compact early Silla settlement", compact)
        self.assertIn("small thatched or plank-roof huts", compact)
        self.assertIn("outer ring", compact)
        self.assertIn("empty circular arena", compact_negative)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_prioritizes_ep13_warhorse_armor_over_mounted_guard(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: a Goguryeo warhorse covered in overlapping iron scales standing in battle dust; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        final_prompt, final_negative = _promote_ep13_final_scene_overrides(
            f"MOUNTED TRAVEL FIRST RULE: common guard. {comfy_prompt}",
            comfy_negative,
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(final_prompt, final_negative)

        self.assertIn("Warhorse armor evidence close-up", compact)
        self.assertIn("one coherent Goguryeo warhorse", compact)
        self.assertIn("four aligned legs", compact)
        self.assertIn("The head and neck are only at the front end", compact)
        self.assertIn("rear end shows only rounded hindquarters", compact)
        self.assertIn("Overlapping dull iron lamellar scale plates", compact)
        self.assertNotIn("Mounted messenger", compact)
        self.assertNotRegex(compact, r"\bhand\w*\b|\bfinger\w*\b")
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
        self.assertNotRegex(compact, r"\b(?:No|no|Do not|do not|FINAL|OVERRIDE|LOCK)\b")
        self.assertIn("rear horse head", compact_negative)
        self.assertIn("two horse necks", compact_negative)

    def test_flux2_klein_prioritizes_ep13_galloping_cavalry_over_mounted_guard(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: black Goguryeo galloping horses kicking up clouds of dust across an open frontier road; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        final_prompt, final_negative = _promote_ep13_final_scene_overrides(
            f"MOUNTED TRAVEL FIRST RULE: common guard. {comfy_prompt}",
            comfy_negative,
        )
        compact, _ = _compact_flux2_klein_4b_prompt(final_prompt, final_negative)

        self.assertIn("Goguryeo armored cavalry charge", compact)
        self.assertIn("six to twelve separate galloping horses", compact)
        self.assertIn("Each visible horse is separate", compact)
        self.assertNotIn("Mounted messenger", compact)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
        self.assertNotRegex(compact, r"\b(?:No|no|Do not|do not|FINAL|OVERRIDE|LOCK)\b")

    def test_flux2_klein_compacts_ep13_muddy_valley_cavalry_with_horse_anatomy(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: heavily armored cavalry rushing down a steep, muddy valley; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, _ = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Goguryeo cavalry descent", compact)
        self.assertIn("six to twelve separate armored horse-and-rider pairs", compact)
        self.assertIn("one head, one neck, one torso, four legs", compact)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_compacts_ep13_wa_panic_without_samurai_markers(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: Wa soldiers looking back with wide, terrified eyes; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, compact_negative = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Wa infantry panic scene", compact)
        self.assertIn("plain cloth tunics", compact)
        self.assertIn("simple leather vests", compact)
        self.assertIn("packed earth, mud, raw vertical timber stakes", compact)
        self.assertIn("samurai armor", compact_negative)
        self.assertIn("katana", compact_negative)
        self.assertIn("stone battlement", compact_negative)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_japanese_positive_avoids_text_forbidden_words(self):
        source = (
            "Global visual world: Time range: 1560-1582, late Sengoku period; "
            "Place scope: Owari, Mino, Kyoto, central Honshu, Japan; "
            "Culture scope: Japanese Sengoku warrior society, castle towns, merchant districts; "
            "Material culture: kosode, hakama, straw sandals, samurai topknots, "
            "lamellar armor, matchlock guns, spears, swords, folding screens, "
            "wooden castles, town markets, plain sashimono without marks; "
            "Year/period: 1582; Exact place: Oda military council room in Azuchi area; "
            "Scene: Retainers push carved wooden markers across a blank parchment-like map "
            "without readable marks, faces tense; Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertTrue(compact.startswith("Top-down macro view"))
        self.assertIn("blank unmarked material texture", compact)
        self.assertIn("current work is shown", compact)
        self.assertNotRegex(
            compact.lower(),
            r"\b(no|zero|text|letter|caption|title|sign|signboard|label|logo|"
            r"document|paper|scroll|calligraphy|writing|written|kanji|kana|glyph|"
            r"map|wire|cable|pole|electric|switch|outlet|placard|plaque)\b",
        )
        self.assertIn("kanji", compact_negative)
        self.assertIn("map label", compact_negative)
        self.assertIn("vertical black brush streaks on plaster", compact_negative)
        self.assertIn("ink-like wall stain clusters", compact_negative)
        self.assertIn("chair with backrest", compact_negative)
        self.assertIn("wooden chair", compact_negative)
        self.assertIn("tissue box", compact_negative)
        self.assertIn("unrequested child", compact_negative)

    def test_flux2_klein_japanese_route_markers_use_object_workbench(self):
        source = (
            "Global visual world: Time range: 1560-1582, late Sengoku period; "
            "Place scope: Owari, Mino, Kyoto, central Honshu, Japan; "
            "Culture scope: Japanese Sengoku warrior society, castle towns; "
            "Year/period: 1560; Exact place: Mikawa fort interior; "
            "Main subject: Ieyasu studying routes; "
            "Scene: Ieyasu studies wooden route markers by lamplight, fingers "
            "hovering between Imagawa roads and Mikawa paths; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertTrue(compact.startswith("Top-down macro view"))
        self.assertIn("physical object spacing", compact)
        self.assertNotIn("diagram", compact.lower())
        self.assertIn("green t-shirt", compact_negative)
        self.assertIn("small white switch on wall", compact_negative)

    def test_flux2_klein_japanese_genealogy_board_becomes_workbench(self):
        source = (
            "Global visual world: Time range: 1582-1590, late Sengoku period Japan; "
            "Place scope: Kyoto, Yamazaki, Osaka, Odawara; "
            "Culture scope: Japanese samurai political culture; "
            "Year/period: 1590; Exact place: tent council near Odawara siege camp; "
            "Main subject: blank lineage board beside Hideyoshi; "
            "Scene: A retainer points to an unmarked wooden genealogy board while "
            "Hideyoshi watches with a restrained, calculating stare; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertTrue(compact.startswith("Top-down macro view"))
        self.assertNotRegex(compact.lower(), r"\b(?:genealogy|lineage|ancestry|family\s+tree|characters?|writing|letters?)\b")
        self.assertIn("wall chart", compact_negative)
        self.assertIn("rectangular white plate on plaster", compact_negative)

    def test_flux2_klein_japanese_letters_become_closed_packets(self):
        source = (
            "Global visual world: Time range: 1582-1590, late Sengoku period Japan; "
            "Place scope: Kyoto, Yamazaki, Osaka, Odawara; "
            "Culture scope: Japanese samurai political culture; "
            "Year/period: 1582; Exact place: Oda relay station near Kyoto; "
            "Main subject: stalled Oda messengers; "
            "Scene: Messengers clutch unopened blank letters, staring at each other "
            "as a relay horse stamps in nervous silence; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertTrue(compact.startswith("Top-down macro view"))
        self.assertNotRegex(compact.lower(), r"\b(?:letters?|messages?|paper|document|writing|kanji)\b")
        self.assertIn("white paper dispatch", compact_negative)
        self.assertIn("small black wall plate", compact_negative)

    def test_flux2_klein_japanese_watchtower_checkpoint_keeps_tower_and_cart(self):
        source = (
            "Global visual world: Time range: 1582-1590, late Sengoku period Japan; "
            "Place scope: Osaka and Odawara; Culture scope: Japanese samurai political culture; "
            "Year/period: 1590; Exact place: Odawara siege line; "
            "Main subject: siege watchtower; "
            "Scene: A lookout scans Odawara from a wooden tower while guards below "
            "stop a cart at the line; Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertTrue(compact.startswith("Single-frame late Sengoku Japanese siege checkpoint scene"))
        self.assertIn("rough timber lookout tower", compact)
        self.assertIn("one low wooden cart", compact)
        self.assertNotIn("street action scene", compact)
        self.assertIn("crossbar utility pole", compact_negative)

    def test_flux2_klein_japanese_battle_pressure_uses_open_ground(self):
        source = (
            "Global visual world: Time range: 1582-1590, late Sengoku period Japan; "
            "Place scope: Yamazaki; Culture scope: Japanese samurai political culture; "
            "Year/period: 1582; Exact place: Toyotomi forward line at Yamazaki; "
            "Main subject: front line under pressure; "
            "Scene: Spears collide against shields as a Toyotomi officer strains "
            "to keep exhausted men from breaking; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertTrue(compact.startswith("Single-frame late Sengoku Japanese open battle pressure scene"))
        self.assertIn("open dusty slope", compact)
        self.assertIn("center collision zone", compact)
        self.assertNotIn("sliding door", compact.lower())
        self.assertIn("wall panel behind soldiers", compact_negative)
        self.assertIn("street doorway replacing battlefield", compact_negative)

    def test_flux2_klein_japanese_osaka_waterfront_blocks_utility_poles(self):
        source = (
            "Global visual world: Time range: 1582-1590, late Sengoku period Japan; "
            "Place scope: Osaka waterfront; Culture scope: Japanese samurai political culture; "
            "Material culture: war banners, blank sealed orders, standard poles; "
            "Year/period: 1590; Exact place: quiet morning near Osaka waterfront; "
            "Main subject: Hideyoshi overlooking Osaka morning; "
            "Scene: Hideyoshi faces the pale morning over Osaka waters as messengers "
            "depart behind him with blank sealed orders; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertTrue(compact.startswith("Single-frame late Sengoku Japanese Osaka waterfront aftermath scene"))
        self.assertIn("facing pale morning water", compact)
        self.assertNotRegex(compact.lower(), r"\b(?:orders?|poles?|wires?|cables?|crossbar|utility|telephone)\b")
        self.assertIn("roof-to-roof wire", compact_negative)
        self.assertIn("crossbar utility pole", compact_negative)

    def test_flux2_klein_japanese_street_scabbards_are_plain(self):
        source = (
            "Global visual world: Time range: 1560-1582, late Sengoku period; "
            "Place scope: Owari, Mino, Kyoto, central Honshu, Japan; "
            "Culture scope: Japanese Sengoku warrior society, castle towns; "
            "Year/period: 1562; Exact place: watch road between Owari and Mikawa; "
            "Main subject: shared border patrol; "
            "Scene: Oda and Mikawa riders pass without drawing swords, glancing "
            "warily under plain unmarked standards; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertTrue(compact.startswith("Street-level wide view"))
        self.assertIn("complete waist-up, knee-up, three-quarter, or full-body adults", compact)
        self.assertIn("continuous material finish", compact)
        self.assertNotIn("below knee height", compact.lower())
        self.assertNotIn("walking lower legs", compact.lower())
        self.assertIn("gold characters on scabbard", compact_negative)

    def test_flux2_klein_japanese_rushing_retainers_avoid_wall_switches(self):
        source = (
            "Global visual world: Time range: 1560-1582, late Sengoku period; "
            "Place scope: Owari, Mino, Kyoto, central Honshu, Japan; "
            "Culture scope: Japanese Sengoku warrior society, castle towns; "
            "Year/period: 1560s; Exact place: Oda castle office and roads beyond; "
            "Main subject: Oda retainer network; "
            "Scene: Multiple retainers rush from a castle room into separate "
            "corridors, carrying tools, weapons, and sealed bundles; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertTrue(compact.startswith("Single-frame late Sengoku Japanese street action"))
        self.assertIn("Side wall zones are broad uninterrupted plaster fields", compact)
        self.assertIn("Door-side details are irregular same-material knots", compact)
        self.assertIn("Eave-side details are irregular wooden brackets", compact)
        self.assertIn("Any tiny dark dot or rectangle at door-side height", compact)
        self.assertIn("Distant skyline detail comes from irregular smoke columns", compact)
        self.assertIn("two-button wall plate", compact_negative)
        self.assertIn("small tan rectangle beside sliding door", compact_negative)
        self.assertIn("isolated black dot on plaster beside door", compact_negative)
        self.assertIn("round black wall button", compact_negative)
        self.assertIn("tiny wooden sign under eave", compact_negative)
        self.assertIn("yellow switch plate at doorway", compact_negative)
        self.assertIn("small rectangular plate on wooden door post", compact_negative)
        self.assertIn("crossbar utility pole", compact_negative)

    def test_flux2_klein_japanese_dispatches_keep_human_action_without_text_surfaces(self):
        source = (
            "Global visual world: Time range: 1560-1582, late Sengoku period; "
            "Place scope: Owari, Mino, Kyoto, central Honshu, Japan; "
            "Culture scope: Japanese Sengoku warrior society, castle towns, "
            "merchant districts, Buddhist temple powers, imperial court authority; "
            "Year/period: 1568; Exact place: shogunal residence hall in Kyoto; "
            "Main subject: messengers receiving shogunal orders; "
            "Scene: Messengers bow in a wooden hall as officials hand over sealed "
            "plain dispatches for distant roads; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertNotIn("Object-only late Sengoku Japanese relay-token workbench evidence", compact)
        self.assertIn("preserve the named human action from the Scene", compact)
        self.assertIn("messengers", compact.lower())
        self.assertNotRegex(compact.lower(), r"\b(?:dispatch(?:es)?|orders?|paper|document|page|sheet|writing)\b")
        self.assertIn("dispatch paper", compact_negative)
        self.assertIn("written order sheet", compact_negative)
        self.assertIn("black characters on cloth packet", compact_negative)
        self.assertIn("person standing on tabletop", compact_negative)

    def test_flux2_klein_japanese_document_retry_preserves_human_story_action(self):
        source = (
            "Global visual world: Time range: Edo period, early seventeenth "
            "century to late nineteenth century; Place scope: Kyoto and Edo; "
            "Culture scope: Tokugawa Japan, Edo period court and shogunate culture; "
            "Year/period: c. 1603-1867; Exact place: administrative hall inside Edo Castle; "
            "Main subject: shogunate officials around a low table; "
            "Scene: Senior officials lean over sealed papers, pointing sharply "
            "while guards brace beside sliding doors.; "
            "Style: serious adult graphic novel illustration"
        )

        self.assertFalse(_should_use_japanese_document_table_retry(source))
        retry = _flux2_klein_japanese_human_textless_retry_sentence(source)
        sign_free = _flux2_klein_japanese_sign_free_composition_sentence(source)

        self.assertIn("preserve the Scene as a human action scene", retry)
        self.assertIn("never a human-free tabletop still life", retry)
        self.assertIn("no white outer margin", retry)
        self.assertIn("Senior officials lean over dark tan cord-tied cloth packet sacks", retry)
        self.assertIn("No wall scroll", retry)
        self.assertIn("no utility pole", retry)
        self.assertIn("Japanese strict surface lock", retry)
        self.assertIn("Crop under or away from all eave", retry)
        self.assertIn("Adult robes are continuous same-color fabric folds only", retry)
        self.assertIn("Japanese record-handling story composition", sign_free)
        self.assertNotIn("object-only sealed-bundle tabletop", sign_free)
        self.assertNotIn("sealed papers", sign_free)
        self.assertIn("dark tan cord-tied cloth packet sacks", sign_free)

        message_source = source.replace(
            "sealed papers",
            "a sealed court message",
        )
        message_sign_free = _flux2_klein_japanese_sign_free_composition_sentence(message_source)
        self.assertIn("Japanese record-handling story composition", message_sign_free)
        self.assertNotIn("sealed court message", message_sign_free)
        self.assertIn("closed sealed lacquered box", message_sign_free)

        box_source = source.replace(
            "Senior officials lean over sealed papers, pointing sharply while guards brace beside sliding doors.",
            "A shogunate officer lifts a court box lid, frowning as clerks wait with tied papers.",
        )
        box_retry = _flux2_klein_japanese_human_textless_retry_sentence(box_source)
        box_sign_free = _flux2_klein_japanese_sign_free_composition_sentence(box_source)
        self.assertNotIn("lifts a court box lid", box_retry)
        self.assertIn("interior stays dark", box_retry)
        self.assertIn("Any lifted or opened box shows only", box_retry)
        self.assertNotIn("lifts a court box lid", box_sign_free)
        self.assertIn("interior stays dark", box_sign_free)

        notice_source = source.replace(
            "sealed papers",
            "a sealed notice",
        )
        notice_retry = _flux2_klein_japanese_human_textless_retry_sentence(notice_source)
        self.assertNotIn("sealed notice", notice_retry)
        self.assertIn("closed plain wooden notice box", notice_retry)
        self.assertTrue(
            _flux2_klein_japanese_sword_order_ground_risk(
                "sealed certificate beside a sheathed sword"
            )
        )

    def test_flux2_klein_japanese_failed_ep79_cases_route_to_strict_prompts(self):
        gate_source = (
            "Global visual world: Time range: Edo period; Culture scope: Tokugawa Japan; "
            "Exact place: front gate of Kyoto Imperial Palace; "
            "Main subject: shogunate messenger stopped at palace gate; "
            "Scene: A dusty messenger bows sharply as palace guards block the "
            "half-open gate with crossed sleeves."
        )
        gate_prompt = _flux2_klein_japanese_sign_free_composition_sentence(gate_source)
        self.assertIn("Palace guards wear tied hair", gate_prompt)
        self.assertIn("no flat-crowned brimmed hat", gate_prompt)
        self.assertIn("no downspout", gate_prompt)

        sword_source = (
            "Global visual world: Time range: Edo period; Culture scope: Tokugawa Japan; "
            "Exact place: samurai council chamber in Kyoto; "
            "Main subject: sealed certificate beside sheathed sword; "
            "Scene: A sealed certificate lies beside a sheathed sword as men argue "
            "with clenched fists."
        )
        self.assertFalse(_should_use_japanese_document_table_retry(sword_source))
        sword_prompt = _flux2_klein_japanese_sign_free_composition_sentence(sword_source)
        sword_retry = _flux2_klein_japanese_sword_packet_human_retry_sentence(sword_source)
        self.assertIn("complete fully sheathed black lacquer sword", sword_prompt)
        self.assertIn("no silver or gray metal blade", sword_prompt)
        self.assertIn("adult men's clenched fists", sword_prompt)
        self.assertIn("The sword is never omitted", sword_retry)
        self.assertIn("no packet", sword_retry)
        self.assertNotIn("sealed certificate", sword_retry)

        group_source = (
            "Global visual world: Time range: Edo period; Culture scope: Tokugawa Japan; "
            "Exact place: dark road near Kyoto Imperial Palace; "
            "Main subject: urgent messengers converging on Kyoto; "
            "Scene: Messengers converge on a dark Kyoto road, each clutching "
            "sealed boxes with alarmed faces."
        )
        self.assertTrue(_flux2_klein_is_japanese_messenger_group_context(group_source))
        group_retry = _flux2_klein_japanese_messenger_group_retry_sentence(group_source)
        self.assertIn("three to five complete adult Edo-period messengers", group_retry)
        self.assertIn("zero utility poles", group_retry)
        self.assertIn("no white circular crest", group_retry)

        notice_source = (
            "Global visual world: Time range: Edo period; Culture scope: Tokugawa Japan; "
            "Exact place: Kyoto noble residence near Imperial Palace; "
            "Main subject: court noble receiving regulations; "
            "Scene: A pale court noble receives a sealed notice, fingers tightening "
            "as attendants exchange worried glances."
        )
        notice_retry = _flux2_klein_japanese_human_textless_retry_sentence(notice_source)
        self.assertIn("no black brush mark", notice_retry)
        self.assertIn("no glyph-like spot", notice_retry)
        self.assertIn("no buildings, no village roofs", notice_retry)

        procession_source = (
            "Global visual world: Time range: Edo period; Culture scope: Tokugawa Japan; "
            "Material culture: court robes, swords, lacquered documents, rank certificates; "
            "Exact place: road leaving Edo castle town; "
            "Main subject: daimyo procession moving away; "
            "Scene: A daimyo procession recedes down the road while a steward "
            "guards a sealed rank box."
        )
        procession_prompt = _flux2_klein_japanese_sign_free_composition_sentence(procession_source)
        scoped = (
            "road leaving Edo castle town daimyo procession moving away "
            "A daimyo procession recedes down the road while a steward guards a sealed rank box."
        )
        self.assertFalse(_flux2_klein_japanese_sword_order_ground_risk(scoped))
        self.assertIn("Japanese daimyo-procession extreme close no-settlement", procession_prompt)
        self.assertIn("not a basket", procession_prompt)
        self.assertNotIn("sword-and-sealed-box", procession_prompt)

    def test_flux2_klein_japanese_mounted_courier_retry_blocks_horse_human_hybrid(self):
        source = (
            "Global visual world: Time range: Edo period, early seventeenth "
            "century to late nineteenth century; Place scope: Kyoto and Edo; "
            "Culture scope: Tokugawa Japan, Edo period court and shogunate culture; "
            "Year/period: c. 1603-1867; Exact place: Edo-to-Kyoto highway checkpoint; "
            "Main subject: mounted courier leaving Edo; "
            "Scene: A mounted courier snaps the reins and surges past a wooden "
            "checkpoint with a sealed dispatch box.; "
            "Style: serious adult graphic novel illustration"
        )

        self.assertTrue(_flux2_klein_is_japanese_mounted_courier_context(source))
        retry = _flux2_klein_japanese_mounted_courier_retry_sentence(source)
        sign_free = _flux2_klein_japanese_sign_free_composition_sentence(source)

        self.assertIn("complete separate horse", retry)
        self.assertIn("complete adult human courier", retry)
        self.assertIn("No centaur", retry)
        self.assertIn("no human torso attached to a horse body", retry)
        self.assertIn("Japanese mounted-courier road composition", sign_free)
        self.assertIn("no human torso growing from a horse body", sign_free)

    def test_flux2_klein_japanese_courier_exchange_keeps_two_couriers(self):
        source = (
            "Global visual world: Time range: Edo period, early seventeenth "
            "century to late nineteenth century; Place scope: Kyoto and Edo; "
            "Culture scope: Tokugawa Japan, Edo period court and shogunate culture; "
            "Year/period: c. 1603-1867; Exact place: mountain pass on the Kyoto-Edo road; "
            "Main subject: relay couriers exchanging a message box; "
            "Scene: Two exhausted couriers exchange a lacquered box mid-stride "
            "on a narrow mountain road.; "
            "Style: serious adult graphic novel illustration"
        )

        self.assertTrue(_flux2_klein_is_japanese_courier_exchange_context(source))
        self.assertFalse(_should_check_internal_text_after_generation(source))
        retry = _flux2_klein_japanese_courier_exchange_retry_sentence(source)
        sign_free = _flux2_klein_japanese_sign_free_composition_sentence(source)

        self.assertIn("two complete adult Edo-period couriers", retry)
        self.assertIn("No single-courier close-up", retry)
        self.assertIn("no boots", retry)
        self.assertIn("Japanese relay-courier exchange composition", sign_free)
        self.assertIn("no missing second courier", sign_free)

    def test_flux2_klein_japanese_political_meeting_desks_avoid_paper(self):
        source = (
            "Global visual world: Time range: 1560-1582, late Sengoku period; "
            "Place scope: Owari, Mino, Kyoto, central Honshu, Japan; "
            "Culture scope: Japanese Sengoku warrior society, castle towns, "
            "merchant districts, Buddhist temple powers, imperial court authority; "
            "Year/period: 1568-1570s; Exact place: Kyoto political meeting room; "
            "Main subject: Nobunaga directing Kyoto politics; "
            "Scene: Nobunaga sits forward beside folding screens, sending messengers "
            "outward while older officials stiffen; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertTrue(compact.startswith("Top-down macro view"))
        self.assertIn("current work is shown", compact)
        self.assertIn("round pebble spacing", compact)
        self.assertNotRegex(
            compact.lower(),
            r"\b(?:nobunaga|messengers?|officials?|people|chair|folding\s+screens?)\b",
        )
        self.assertIn("white sheet on desk", compact_negative)
        self.assertIn("chair back", compact_negative)
        self.assertIn("flat white paper on table", compact_negative)

    def test_flux2_klein_japanese_honnoji_lanterns_avoid_signboards(self):
        source = (
            "Global visual world: Time range: 1560-1582, late Sengoku period; "
            "Place scope: Owari, Mino, Kyoto, central Honshu, Japan; "
            "Culture scope: Japanese Sengoku warrior society, castle towns, "
            "merchant districts, Buddhist temple powers, imperial court authority; "
            "Year/period: 1582; Exact place: Honnoji temple in Kyoto at night; "
            "Main subject: Honnoji temple at night; "
            "Scene: Lanterns flicker along quiet temple eaves as a small guard "
            "detail moves through the courtyard; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("low handheld lanterns", compact)
        self.assertIn("small ground torchlight", compact)
        self.assertNotIn("Lanterns flicker along quiet temple eaves", compact)
        self.assertIn("temple name board with characters", compact_negative)
        self.assertIn("rectangular wall lantern", compact_negative)

    def test_flux2_klein_japanese_ground_plan_routes_to_workbench(self):
        source = (
            "Global visual world: Time range: 1575, Sengoku period Japan; "
            "Place scope: Nagashino Castle, Shitaragahara plain, Mikawa frontier; "
            "Culture scope: Japanese Sengoku warrior society, Oda-Tokugawa alliance; "
            "Year/period: 1575; Exact place: Oda planning space beside the defensive line; "
            "Main subject: Nobunaga planning defensive fire lanes; "
            "Scene: Nobunaga crouches over a sand-marked ground plan as officers place "
            "twigs for palisades and gun lines; Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertTrue(compact.startswith("Top-down macro view"))
        self.assertIn("current work is shown", compact)
        self.assertNotRegex(compact.lower(), r"\b(?:sand-marked|ground\s+plan|diagram|gun\s+lines)\b")
        self.assertIn("sand-marked ground plan", compact_negative)
        self.assertIn("drawn grid on ground", compact_negative)

    def test_flux2_klein_japanese_land_register_becomes_closed_board_bundle(self):
        source = (
            "Global visual world: Time range: 1580s; Azuchi-Momoyama Japan, "
            "land survey administration; Culture scope: Japanese samurai political culture; "
            "Year/period: 1580s; Exact place: rice-field ridge beside a village; "
            "Main subject: blank land register beside rice field; "
            "Scene: A closed wooden register board rests near wet fields while a farmer "
            "watches officials measure boundaries.; Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("land-survey board evidence", compact)
        self.assertIn("closed thick plain wooden board bundles", compact)
        self.assertIn("face-down or edge-on", compact)
        self.assertIn("human-free, sky-free, building-free", compact)
        self.assertNotRegex(
            compact.lower(),
            r"\b(?:register|document|paper|page|writing|kanji|kana|characters|scroll|sign|plaque)\b",
        )
        self.assertIn("open register", compact_negative)
        self.assertIn("kanji on board", compact_negative)
        self.assertIn("straight white measuring strip", compact_negative)

    def test_flux2_klein_japanese_register_boards_become_object_only_boards(self):
        source = (
            "Global visual world: Time range: 1590s; Azuchi-Momoyama Japan, "
            "forming foundation of status order; Culture scope: Japanese samurai political culture; "
            "Year/period: 1590s; Exact place: packed earth base near a village storehouse; "
            "Main subject: register boards on packed earth foundation; "
            "Scene: Closed boards, measuring rope, and a weapon box rest on newly "
            "packed earth beside a storehouse.; Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("land-survey board evidence", compact)
        self.assertIn("packed earth filling every edge", compact)
        self.assertIn("brown knotted cord coils", compact)
        self.assertNotRegex(
            compact.lower(),
            r"\b(?:register|document|paper|page|writing|kanji|kana|characters|scroll|sign|plaque)\b",
        )
        self.assertIn("written register", compact_negative)
        self.assertIn("switch-like rectangle behind board", compact_negative)
        self.assertIn("utility pole", compact_negative)

    def test_flux2_klein_japanese_sword_register_measure_routes_to_workbench(self):
        source = (
            "Global visual world: Time range: 1582-1591, late Sengoku to early Toyotomi unification; "
            "Place scope: Japanese archipelago; Culture scope: Late medieval Japanese warrior society; "
            "Year/period: 1588-1591; Exact place: granary yard collection table; "
            "Main subject: sword placed beside rice measure; "
            "Scene: A villager lays a sword beside a wooden rice measure as an official reaches for a register; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertTrue(compact.startswith("Top-down macro view"))
        self.assertIn("one smooth plain sword scabbard", compact)
        self.assertNotRegex(compact.lower(), r"\b(?:villager|official|people|register|paper|page|rifle|gun)\b")
        self.assertIn("modern rifle", compact_negative)

    def test_flux2_klein_japanese_family_rice_register_routes_to_adult_interior(self):
        source = (
            "Global visual world: Late Sengoku Japanese household life; "
            "Year/period: 1588-1591; Exact place: Japanese farmhouse interior beside rice storage; "
            "Scene evidence: The scene shows stability and burden together.; "
            "Main subject: family beside rice and register; "
            "Scene: A family shares a quiet meal beside stored rice while a closed register rests near the door"
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("household rice-storage meal evidence", compact)
        self.assertIn("physical objects only", compact)
        self.assertIn("four plain wooden rice bowls", compact)
        self.assertIn("closed cord-tied packet", compact)
        self.assertNotIn("Door hardware inventory", compact)
        self.assertIn("black boots", compact_negative)
        self.assertIn("child at table", compact_negative)
        self.assertIn("modern door handle", compact_negative)

    def test_flux2_klein_japanese_tally_rice_routes_to_object_evidence(self):
        source = (
            "Global visual world: Late Sengoku Japanese administration; "
            "Year/period: c. 1585-1590; Exact place: provincial castle storehouse; "
            "Scene evidence: Kokudaka became a comparative measure of domain strength.; "
            "Main subject: plain tally sticks beside rice; "
            "Scene: A retainer slams plain tally sticks beside rice bales as the daimyo watches"
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("kokudaka tally evidence still life", compact)
        self.assertIn("one continuous unpartitioned", compact)
        self.assertIn("plain unmarked wooden tally sticks", compact)
        self.assertIn("rice measure filled with rice grains", compact)
        self.assertIn("physical evidence only", compact)
        self.assertNotIn("Door hardware inventory", compact)
        self.assertIn("person", compact_negative)
        self.assertIn("switch plate", compact_negative)

    def test_flux2_klein_late_roman_final_prompt_does_not_route_to_japanese_household(self):
        source = (
            "Common guard text mentions a Japanese gate replacing stone city gate and medieval castles. || "
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Culture scope: Late Roman imperial military culture, Danubian frontier diplomacy, "
            "Quadi Germanic tribal society; "
            "Material culture: Late Roman cloaks, tunics, military belts, helmets, mail shirts, "
            "scale armor, oval shields, spears, spathae, Roman standards, wax tablets; "
            "Continuity rule: Keep all visuals grounded in the late fourth-century Danube frontier; "
            "Year/period: 375 AD; Late Roman Empire, Valentinianic dynasty, November 17, 375 AD; "
            "Exact place: torchlit audience hall inside Brigetio Roman military camp; "
            "Scene evidence: The cold open centers the fatal Brigetio audience before the collapse.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: Valentinian I gripping power inside the audience hall; "
            "Scene: Older emperor in military cloak leans forward under torchlight as armed guards "
            "and envoys tense around blank tablets."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertNotIn("late Sengoku Japanese", compact)
        self.assertNotIn("household rice-storage meal evidence", compact)
        self.assertNotIn("kosode", cleaned)
        self.assertNotIn("waraji", cleaned)
        self.assertNotIn("tabi", cleaned)
        self.assertNotIn("zori", cleaned)
        self.assertNotIn("tatami", cleaned.lower())
        self.assertNotIn("Basket carriers", cleaned)
        self.assertIn("era-local period clothing", cleaned)
        self.assertIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("broad uninterrupted low-contrast", cleaned)
        self.assertIn("soft mottled torch soot", cleaned)
        self.assertIn("Door-side hand-height zones are occupied", cleaned)
        self.assertIn("Door hardware placement", cleaned)
        self.assertIn("adjacent plaster remains continuous rough wall", cleaned)
        self.assertIn("Ceiling center inventory", cleaned)
        self.assertIn("dark timber beams, rough roof planks, beam seams", cleaned)
        self.assertNotIn("Small high-contrast details resolve", cleaned)
        self.assertNotIn("square-like", cleaned)
        self.assertNotIn("plate-like", cleaned)
        self.assertIn("one left leg and one right leg per body", cleaned)
        self.assertIn("one left leg and one right leg attached to the same torso", cleaned)
        self.assertIn("Valentinian", cleaned)
        self.assertIn("Brigetio", cleaned)

    def test_flux2_klein_late_roman_object_cleanup_uses_period_local_surface(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Culture scope: Late Roman imperial military culture and frontier diplomacy; "
            "Material culture: Late Roman wax tablets, parchment maps, wooden chairs, "
            "stone floors, military belts, helmets, oval shields, spears, and oil lamps; "
            "Year/period: 375 AD; Late Roman Empire, Valentinianic dynasty; "
            "Exact place: imperial audience hall at Brigetio; "
            "Main subject: Roman evidence after the collapse; "
            "Scene: Object-only view of blank wax tablets, a cracked chair arm, and "
            "fallen oil lamp fragments on a stone floor."
        )

        compact, _ = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("period-local tabletop", cleaned)
        self.assertIn("stone floor", cleaned)
        self.assertIn("Brigetio", cleaned)
        self.assertNotIn("tatami", cleaned.lower())
        self.assertNotIn("Japanese", cleaned)

    def test_flux2_klein_late_roman_valentinian_collapse_routes_to_crisis_chair(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD, "
            "climax on November 17, 375 AD; Place scope: Brigetio Roman military camp "
            "on the Danube frontier, Pannonia; Culture scope: Late Roman imperial "
            "military culture, Danubian frontier diplomacy, Quadi Germanic tribal society; "
            "Material culture: Late Roman cloaks, tunics, military belts, helmets, mail shirts, "
            "scale armor, oval shields, spears, spathae, wax tablets, timber-and-stone forts; "
            "Year/period: 375 AD; Late Roman Empire, Valentinianic dynasty, November 17, 375 AD; "
            "Exact place: imperial audience hall at Brigetio; "
            "Scene evidence: The narration reaches the sudden collapse reported after anger.; "
            "Main subject: Valentinian's sudden physical failure; "
            "Scene: Valentinian's hand crushes the chair arm as attendants lunge forward "
            "and envoys recoil in shock."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertTrue(cleaned.startswith("CRISIS FIRST RENDERING RULE"))
        self.assertLess(cleaned.find("CRISIS FIRST RENDERING RULE"), cleaned.find("Human anatomy contract"))
        self.assertIn("exactly one human body touches the chair", cleaned)
        self.assertIn("helmeted heads appear only on side guards", cleaned)
        self.assertIn("left and right image edges are rough plaster, timber posts, cloak edges, shield edges, long cracks, soot stains, and shadow only", cleaned)
        self.assertIn("all hand-height edge wall zones are uninterrupted rough plaster or timber shadow", cleaned)
        self.assertIn("dense mail rings or small overlapping scale rows over cloth tunics across every torso armor surface", cleaned)
        self.assertIn("zero smooth breastplate field", cleaned)
        self.assertIn("every lower leg uses wrinkled wool trouser fabric entering matte dark leather boots", cleaned)
        self.assertIn("crushes the rough wooden chair arm", compact)
        self.assertIn("body buckles sideways", compact)
        self.assertIn("central chair contains one collapsed figure only", compact)
        self.assertIn("chair carries one white-haired head, one torso, two arms, and two trouser-covered legs", compact)
        self.assertIn("diagonal slumped line across the chair", compact)
        self.assertIn("head drooping toward one armrest", compact)
        self.assertIn("one boot sliding forward", compact)
        self.assertIn("Lower-body separation contract", compact)
        self.assertIn("Cold Danube frontier legwear contract", compact)
        self.assertIn("the emperor, guards, and attendants wear long wool trousers", compact)
        self.assertIn("long wool trousers, leggings, or wrapped hose", compact)
        self.assertIn("one left boot and one right boot connected to the same clothed lower body", compact)
        self.assertIn("Single-emperor head lock", compact)
        self.assertIn("exactly one visible old white-haired head and exactly one white beard", compact)
        self.assertIn("no attendant head overlaps the chair seat", compact)
        self.assertIn("Empty chair-back lock", compact)
        self.assertIn("rectangular wooden chair back behind Valentinian contains only plain planks", compact)
        self.assertIn("guards stay outside a clear empty halo around the chair back", compact)
        self.assertIn("Medical-collapse pose lock", compact)
        self.assertIn("head tilts sideways below the chair-back center", compact)
        self.assertIn("crooked medical collapse rather than a centered imperial portrait", compact)
        self.assertIn("cloak hems, chair rails, timber posts, and door shadows stay visually separate", compact)
        self.assertIn("Side-edge guard weapon placement contract", compact)
        self.assertIn("do not let a long sword sheath or scabbard hang beside the boots", compact)
        self.assertIn("do not let spear poles or weapon shafts run down to the floor beside a side-edge guard's boot", compact)
        self.assertIn("exactly two dark boots", compact)
        self.assertIn("chair seat, back, and armrests carry only the white-haired emperor's body", compact)
        self.assertIn("closed dark wax tablets at floor level", compact)
        self.assertNotIn("blank wax tablets", compact)
        self.assertIn("older white-haired emperor Valentinian I", compact)
        self.assertIn("Door hardware exclusion", compact)
        self.assertIn("plain unhandled plank surface", compact)
        self.assertIn("metal plate areas are hidden behind guards", compact)
        self.assertIn("adult attendants stand upright on the floor", compact)
        self.assertIn("lunge from standing bodies around him", compact)
        self.assertIn("Quadi envoys recoil", compact)
        self.assertIn("handshake", compact_negative)
        self.assertIn("younger man seated in imperial chair", compact_negative)
        self.assertIn("blank white wall panel behind chair", compact_negative)
        self.assertIn("wall-mounted tablet", compact_negative)
        self.assertIn("modern doorknob", compact_negative)
        self.assertIn("round metal knob", compact_negative)
        self.assertIn("visible door hardware", compact_negative)
        self.assertIn("escutcheon", compact_negative)
        self.assertIn("left wall switch", compact_negative)
        self.assertIn("small switch plate on side wall", compact_negative)
        self.assertIn("plate greaves", compact_negative)
        self.assertIn("knee cops", compact_negative)
        self.assertIn("metal shin guards", compact_negative)
        self.assertIn("shiny metal shin armor", compact_negative)
        self.assertIn("upright symmetrical seated pose", compact_negative)
        self.assertIn("two bodies on one chair", compact_negative)
        self.assertIn("two heads on chair", compact_negative)
        self.assertIn("two white-haired heads in chair", compact_negative)
        self.assertIn("duplicate old emperor face", compact_negative)
        self.assertIn("attendant head on chair seat", compact_negative)
        self.assertIn("helmeted head behind emperor", compact_negative)
        self.assertIn("guard head inside chair back", compact_negative)
        self.assertIn("crowded chair back", compact_negative)
        self.assertIn("helmeted head touching chair", compact_negative)
        self.assertIn("helmet on emperor", compact_negative)
        self.assertIn("extra head inside chair footprint", compact_negative)
        self.assertIn("centered upright emperor", compact_negative)
        self.assertIn("upright throne portrait", compact_negative)
        self.assertIn("third leg silhouette", compact_negative)
        self.assertIn("scabbard as third leg", compact_negative)
        self.assertIn("cloak fold as third leg", compact_negative)
        self.assertIn("long scabbard beside boots", compact_negative)
        self.assertIn("scabbard parallel to leg", compact_negative)
        self.assertIn("weapon shaft as third leg", compact_negative)
        self.assertIn("third boot-like strip at frame edge", compact_negative)
        self.assertIn("bare knees", compact_negative)
        self.assertNotIn("handshake", compact)
        self.assertNotIn("tatami", cleaned.lower())
        self.assertNotIn("Japanese", cleaned)
        self.assertNotIn("switch", cleaned.lower())
        self.assertIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("Crisis wall hardware exclusion contract", cleaned)
        self.assertIn("small modern plate details stay outside the crop", cleaned)
        self.assertNotIn("Door hardware placement", cleaned)
        self.assertIn("featureless rough plaster", cleaned)
        self.assertIn("Footwear contract", cleaned)
        self.assertIn("Late Roman leather boots", cleaned)
        self.assertIn("barefoot", compact_negative)

    def test_flux2_klein_late_roman_command_room_has_material_ceiling_inventory(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Culture scope: Late Roman imperial military culture, Danubian frontier diplomacy, "
            "Quadi Germanic tribal society; "
            "Year/period: 375 AD; Late Roman Empire, Valentinianic dynasty, 375 AD; "
            "Exact place: Brigetio command space beside Danube campaign equipment; "
            "Main subject: Valentinian as militarized emperor; "
            "Scene: Valentinian drives a finger onto a blank parchment map while helmeted "
            "officers crowd around a rough table."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Tight interior table crop contract", cleaned)
        self.assertIn("adult torsos, helmets, cloaks, oval shields, table edge", cleaned)
        self.assertIn("hand-height side zones", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("Ceiling inventory", cleaned)
        self.assertIn("dark timber beams, rough roof planks, beam seams", cleaned)
        self.assertIn("visible illumination comes from handheld torches", cleaned)
        self.assertNotIn("Ceiling inventory is, .", cleaned)
        self.assertIn("ceiling light", compact_negative)
        self.assertIn("wall switch plate", compact_negative)
        self.assertIn("framed wall picture", compact_negative)

    def test_flux2_klein_late_roman_command_table_blank_map_keeps_older_valentinian(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 375 AD; Late Roman Empire, Valentinianic Danube campaign, 375 AD; "
            "Exact place: imperial command table at Brigetio; "
            "Main subject: Valentinian narrowing his own options; "
            "Scene: Valentinian presses both palms onto a blank map while officers avoid "
            "meeting his hard stare."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Tight interior table crop contract", cleaned)
        self.assertIn("Older white-haired Valentinian", cleaned)
        self.assertIn("presses both palms flat", cleaned)
        self.assertIn("one blank unmarked parchment route board sheet", cleaned)
        self.assertIn("Rear wall inventory is featureless rough plaster", cleaned)
        self.assertIn("rather than separate wall objects", cleaned)
        self.assertIn("Officer armor texture lock", cleaned)
        self.assertIn("many small mail rings or scale tiles", cleaned)
        self.assertIn("wool trousers or wrapped hose above leather boots", cleaned)
        self.assertNotIn("wall-mounted map", cleaned.lower())
        self.assertIn("young Valentinian", compact_negative)
        self.assertIn("dark-haired Valentinian", compact_negative)
        self.assertIn("wall-mounted map", compact_negative)
        self.assertIn("door handle", compact_negative)
        self.assertIn("smooth metal breastplate", compact_negative)
        self.assertIn("plate greaves", compact_negative)

    def test_flux2_klein_late_roman_wax_tablet_report_uses_tight_table_crop(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 375 AD; Late Roman Empire, Valentinianic dynasty, November 17, 375 AD; "
            "Exact place: Brigetio audience hall near the imperial chair; "
            "Main subject: Ammianus's report embodied by a blank writing tablet; "
            "Scene: An officer's tense hand hovers over a blank wax tablet while "
            "Valentinian's strained face hardens nearby."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Tight interior table crop contract", cleaned)
        self.assertIn("closed dark wax tablet", cleaned)
        self.assertIn("older Valentinian's strained face", cleaned)
        self.assertIn("hand-height side zones", cleaned)
        self.assertIn("Ceiling inventory", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("side wall plate", compact_negative)
        self.assertIn("small framed wall panel", compact_negative)

    def test_flux2_klein_late_roman_historian_wax_tablet_routes_without_valentinian_name(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 375 AD; Late Roman Empire; "
            "Exact place: dim Roman writing room near the audience hall; "
            "Main subject: late Roman historian writing the crisis; "
            "Scene: A robed writer presses a stylus into a blank wax tablet beside "
            "a dim oil lamp and military dispatches."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Tight interior table crop contract", cleaned)
        self.assertIn("closed dark wax tablet", cleaned)
        self.assertIn("stylus", cleaned)
        self.assertIn("One robed late Roman writer", cleaned)
        self.assertNotIn("older Valentinian's strained face", cleaned)
        self.assertIn("ceiling light", compact_negative)
        self.assertIn("wall switch", compact_negative)

    def test_flux2_klein_late_roman_uncertain_record_routes_to_wax_tablet(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: c. 390 AD; Late Roman Empire, historical memory after 375 AD; "
            "Exact place: late Roman writing room with military reports; "
            "Main subject: uncertain record of Gabinius's killing; "
            "Scene: A stylus pauses over a blank wax tablet beside torn seals and an "
            "extinguished lamp."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Tight interior table crop contract", cleaned)
        self.assertIn("closed dark wax tablet", cleaned)
        self.assertIn("stylus", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("wall switch", compact_negative)
        self.assertIn("framed wall picture", compact_negative)

    def test_flux2_klein_late_roman_quadi_envoys_are_not_roman_guards(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Culture scope: Late Roman imperial military culture, Danubian frontier diplomacy, "
            "Quadi Germanic tribal society; "
            "Year/period: 375 AD; Late Roman Empire and Quadi frontier society; "
            "Exact place: Brigetio camp entrance on the Danube frontier; "
            "Main subject: Quadi envoys entering Brigetio; "
            "Scene: Travel-worn Quadi envoys in wool cloaks step between Roman spears "
            "with guarded, anxious faces."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("open-air exterior gate approach", cleaned)
        self.assertIn("Quadi envoy identity contract", cleaned)
        self.assertIn("cloth-and-fur travelers", cleaned)
        self.assertIn("small bundled packs", cleaned)
        self.assertIn("Roman guards are separate armored adults", cleaned)
        self.assertIn("envoys stay central and hesitant", cleaned)
        self.assertIn("central Quadi envoys carry cloth bundles", cleaned)
        self.assertIn("Open-air gateway material", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("all figures dressed as Roman soldiers", compact_negative)
        self.assertIn("helmets on Quadi envoys", compact_negative)
        self.assertIn("Quadi envoy holding spear", compact_negative)

    def test_flux2_klein_late_roman_before_collapse_scene_does_not_route_to_crisis(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD, "
            "climax on November 17, 375 AD; Place scope: Brigetio Roman military camp "
            "on the Danube frontier, Pannonia; Culture scope: Late Roman imperial "
            "military culture, Danubian frontier diplomacy, Quadi Germanic tribal society; "
            "Year/period: 375 AD; Late Roman Empire, Valentinianic dynasty; "
            "Exact place: torchlit audience hall inside Brigetio Roman military camp; "
            "Scene evidence: The cold open centers the fatal Brigetio audience before the collapse.; "
            "Main subject: Valentinian I gripping power inside the audience hall; "
            "Scene: Older emperor in military cloak leans forward under torchlight as armed guards "
            "and envoys tense around blank tablets."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertNotIn("body buckles sideways", compact)
        self.assertNotIn("crushes the rough wooden chair arm", compact)
        self.assertNotIn("handshake", compact_negative)
        self.assertIn("Valentinian", compact)
        self.assertIn("Brigetio", compact)

    def test_flux2_klein_late_roman_audience_setup_blocks_wall_panels(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Continuity rule: Valentinian appears older, severe, and militarized; "
            "Year/period: 375 AD; Late Roman Empire, Valentinianic dynasty; "
            "Exact place: torchlit audience hall inside Brigetio Roman military camp; "
            "Main subject: Valentinian preparing to receive envoys; "
            "Scene: The emperor fastens his military belt as officers arrange a bare chair "
            "and guarded approach."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Audience setup crop contract", cleaned)
        self.assertIn("rough bare wooden chair", cleaned)
        self.assertIn("rear background is one broad rough plaster field", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("framed wall picture", compact_negative)
        self.assertIn("wall switch plate", compact_negative)

    def test_flux2_klein_late_roman_imperial_cloak_fastening_uses_attendant_route(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD, "
            "climax on November 17, 375 AD; Place scope: Brigetio Roman military camp "
            "on the Danube frontier, Pannonia; Culture scope: Late Roman imperial military culture; "
            "Material culture: Late Roman cloaks, tunics, military belts, helmets, mail shirts, "
            "scale armor, oval shields, spears, spathae, Roman standards, wax tablets; "
            "Continuity rule: Valentinian appears older, severe, and militarized; "
            "Year/period: 375 AD; Late Roman Empire, imperial field politics, 375 AD; "
            "Exact place: Brigetio command hall before negotiations; "
            "Main subject: imperial cloak as symbol of exposed authority; "
            "Scene: An attendant fastens Valentinian's purple-edged cloak as officers wait "
            "beside silent standards and weapons."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("CLOAK FASTENING FIRST RENDERING RULE", cleaned)
        self.assertIn("Extreme cloak-fastening close-up", cleaned)
        self.assertIn("lower legs, full-room corners, and full-height side walls stay outside the crop", cleaned)
        self.assertIn("older white-haired Valentinian's head", cleaned)
        self.assertIn("using both hands to fasten the purple-edged imperial military cloak", cleaned)
        self.assertIn("both attendant hands are visible at the same shoulder clasp", cleaned)
        self.assertIn("dark military brown wool", cleaned)
        self.assertIn("purple appears only as one thin border trim", cleaned)
        self.assertIn("Single-emperor composition lock", cleaned)
        self.assertIn("only one white-haired adult appears", cleaned)
        self.assertIn("only one narrow purple trim appears", cleaned)
        self.assertIn("Valentinian's own hands stay cropped at belt height", cleaned)
        self.assertIn("All other officers are cropped edge witnesses", cleaned)
        self.assertIn("Exactly one purple-edged imperial cloak wearer", cleaned)
        self.assertIn("attendant wears a plain undyed tunic", cleaned)
        self.assertIn("Visible inventory is limited to Valentinian's older face", cleaned)
        self.assertIn("thin purple edge trim", cleaned)
        self.assertIn("Both left and right image edges are occupied by cropped officer shoulders", cleaned)
        self.assertIn("Close-up background contract", cleaned)
        self.assertIn("covered edge-to-edge by hanging dark military wool curtain", cleaned)
        self.assertIn("Officer armor texture lock", cleaned)
        self.assertIn("many small mail rings or scale tiles", cleaned)
        self.assertIn("every visible shin is soft grey or brown wool hose", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertNotIn("Door hardware placement", cleaned)
        self.assertIn("wall switch plate", compact_negative)
        self.assertIn("outlet plate", compact_negative)
        self.assertIn("plaster wall", compact_negative)
        self.assertIn("windows", compact_negative)
        self.assertIn("window frame", compact_negative)
        self.assertIn("doors", compact_negative)
        self.assertIn("doorways", compact_negative)
        self.assertIn("rear door", compact_negative)
        self.assertIn("plank door", compact_negative)
        self.assertIn("doorway behind emperor", compact_negative)
        self.assertIn("lever door handle", compact_negative)
        self.assertIn("second purple cloak", compact_negative)
        self.assertIn("two emperors", compact_negative)
        self.assertIn("second white-haired man", compact_negative)
        self.assertIn("full purple cloak", compact_negative)
        self.assertIn("wide symmetrical lineup", compact_negative)
        self.assertIn("two attendants", compact_negative)
        self.assertIn("one-handed pointing", compact_negative)
        self.assertIn("emperor fastening own cloak", compact_negative)
        self.assertIn("young Valentinian", compact_negative)
        self.assertIn("silver greaves", compact_negative)
        self.assertIn("reflective knee-high greaves", compact_negative)
        self.assertIn("smooth metal breastplate", compact_negative)

    def test_flux2_klein_late_roman_quadi_displaced_settlement_stays_outdoors(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD, "
            "climax on November 17, 375 AD; Place scope: Brigetio Roman military camp "
            "on the Danube frontier, Pannonia; Culture scope: Late Roman imperial military culture, "
            "Danubian frontier diplomacy, Quadi Germanic tribal society; "
            "Material culture: Late Roman cloaks, tunics, military belts, helmets, mail shirts, "
            "scale armor, oval shields, spears, spathae, Roman standards, wax tablets, parchment maps, "
            "timber-and-stone frontier forts, river boats, military tents, audience halls, cold Danube landscapes; "
            "Year/period: 375 AD; Late Roman Empire and Quadi frontier society, 375 AD; "
            "Exact place: strained Quadi settlement after Roman pressure; "
            "Main subject: Quadi community under pressure after Roman operations; "
            "Scene: Families gather belongings beside trampled fields while armed men stare "
            "toward distant Roman patrols."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Open Quadi displaced settlement contract", cleaned)
        self.assertIn("Quadi families gather tied cloth bundles", cleaned)
        self.assertIn("trampled muddy fields", cleaned)
        self.assertIn("distant Roman patrol silhouettes", cleaned)
        self.assertIn("Family displacement inventory", cleaned)
        self.assertIn("adult women, adult men, older youths", cleaned)
        self.assertIn("Roman patrols never occupy the foreground", cleaned)
        self.assertIn("Quadi identity contract", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("interior room", compact_negative)
        self.assertIn("door handle", compact_negative)
        self.assertIn("missing belongings", compact_negative)
        self.assertIn("missing trampled fields", compact_negative)
        self.assertIn("Roman soldiers in foreground", compact_negative)

    def test_flux2_klein_late_roman_toppled_footstool_uses_blank_cloth_poles(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Culture scope: Late Roman imperial military culture and Quadi diplomacy; "
            "Continuity rule: Valentinian appears older, severe, and militarized; "
            "Year/period: 375 AD; Late Roman Empire, Valentinianic dynasty; "
            "Exact place: imperial audience hall at Brigetio; "
            "Main subject: stunned silence around the emptying imperial seat; "
            "Scene: Guards freeze beside a toppled footstool while the envoys stand "
            "trapped beneath Roman standards."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("A fallen low wooden footstool lies on its side", cleaned)
        self.assertIn("short legs pointing sideways", cleaned)
        self.assertIn("empty rough wooden imperial chair", cleaned)
        self.assertIn("plain spear poles with blank folded red cloth", cleaned)
        self.assertIn("Shield face contract", cleaned)
        self.assertIn("plain blank leather", cleaned)
        self.assertIn("one simple round central metal boss", cleaned)
        self.assertNotIn("Roman standards", cleaned)
        self.assertNotIn("emperor's hand", cleaned)
        self.assertNotIn("buckling torso", cleaned)
        self.assertIn("Door header zones and upper wall bands", cleaned)
        self.assertIn("featureless rough plaster", cleaned)
        self.assertIn("text on door header", compact_negative)
        self.assertIn("bare feet", compact_negative)
        self.assertIn("upright footstool", compact_negative)
        self.assertIn("star mark on shield", compact_negative)
        self.assertIn("weapon-shaped mark on shield", compact_negative)
        self.assertIn("switch plate at hand height", compact_negative)
        self.assertNotIn("square-like", cleaned)
        self.assertNotIn("plate-like", cleaned)

    def test_flux2_klein_late_roman_valentinianic_final_prompt_routes_to_crisis(self):
        source = (
            "375 AD; Late Roman Empire, Valentinianic dynasty, November 17, 375 AD "
            "Late Roman imperial military culture, Danubian frontier diplomacy, Quadi Germanic tribal society "
            "at silent Brigetio audience hall after the collapse. "
            "Scene subject: stunned silence around the emptying imperial seat. "
            "Visible action: Guards freeze beside a toppled footstool while the envoys stand trapped "
            "beneath plain Roman spear poles with blank folded cloth."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("A fallen low wooden footstool lies on its side", cleaned)
        self.assertIn("short legs pointing sideways", cleaned)
        self.assertIn("empty rough wooden imperial chair", cleaned)
        self.assertIn("Footwear contract", cleaned)
        self.assertIn("barefoot", compact_negative)

    def test_flux2_klein_late_roman_accusing_arm_keeps_hand_gap(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Year/period: 375 AD; Late Roman Empire, imperial intimidation at Brigetio; "
            "Exact place: Brigetio audience hall before gathered officers; "
            "Main subject: Valentinian using anger as political theater; "
            "Scene: Valentinian thrusts an accusing arm toward envoys as officers and guards flinch around the chamber."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("visible air gap", cleaned)
        self.assertIn("clenched pointing fist", cleaned)
        self.assertIn("hands pulled back", cleaned)
        self.assertIn("hand-to-hand contact", compact_negative)

    def test_flux2_klein_late_roman_guard_corridor_covers_side_walls(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Year/period: 375 AD; Late Roman Empire, Valentinianic dynasty, 375 AD; "
            "Exact place: guarded interior corridor of Brigetio military camp; "
            "Main subject: imperial guards enforcing Valentinian's atmosphere of power; "
            "Scene: Oval shields press close along a timber corridor as officers lower their eyes "
            "before the emperor's approach."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("close shoulder-height corridor crush", cleaned)
        self.assertIn("Guarded corridor crop contract", cleaned)
        self.assertIn("cover both side edges", cleaned)
        self.assertIn("Hand-height side architecture is covered", cleaned)
        self.assertIn("Shield face contract", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertNotIn("open side doors", compact)
        self.assertIn("side door switch", compact_negative)

    def test_flux2_klein_late_roman_frontier_survey_stays_outdoor(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 374-375 AD; Late Roman Empire, Danube frontier fort dispute; "
            "Exact place: Roman survey line near Quadi territory north of the Danube; "
            "Main subject: Roman surveyors marking disputed ground; "
            "Scene: Surveyors hammer stakes while guards hold oval shields and Quadi riders circle at a wary distance."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("open outdoor survey line", cleaned)
        self.assertIn("hammer wooden stakes into packed earth", cleaned)
        self.assertIn("measuring rope", cleaned)
        self.assertIn("Shield face contract", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("interior room", compact_negative)

    def test_flux2_klein_late_roman_river_contact_stays_outdoor(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 375 AD; Late Roman Empire and Quadi frontier society; "
            "Exact place: Danube crossing crowded with frontier traffic; "
            "Main subject: Danube crossing crowded with frontier traffic; "
            "Scene: Boatmen push a low river craft through reeds as soldiers and traders "
            "argue with raised hands."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Open riverbank contract", cleaned)
        self.assertIn("low wooden river craft", cleaned)
        self.assertIn("reed beds", cleaned)
        self.assertIn("open sky", cleaned)
        self.assertIn("boat on street", compact_negative)
        self.assertIn("wall switch", compact_negative)

    def test_flux2_klein_late_roman_military_assembly_stays_open_air(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 375 AD; Late Roman Empire, Danube crisis response; "
            "Exact place: military assembly ground in Pannonia; "
            "Main subject: Valentinian addressing mustered soldiers; "
            "Scene: The emperor raises one hand before ranks of oval shields as cold dust "
            "whips across the assembly."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Open military assembly ground contract", cleaned)
        self.assertIn("ranks of plain oval shields", cleaned)
        self.assertIn("open sky", cleaned)
        self.assertIn("Intercisa or Berkasovo style segmented ridge helmets", cleaned)
        self.assertIn("interior room", compact_negative)
        self.assertIn("missing shield ranks", compact_negative)

    def test_flux2_klein_late_roman_punitive_justification_keeps_civilians_foreground(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 375 AD; Late Roman Empire, punitive Danube campaign; "
            "Exact place: Roman field assembly near the Danube; "
            "Main subject: Roman commanders justifying punitive force; "
            "Scene: Officers gesture toward frightened Pannonian civilians as Valentinian "
            "listens beside stacked spears and shields."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Open punitive field assembly contract", cleaned)
        self.assertIn("Four foreground unarmored adult Pannonian civilians", cleaned)
        self.assertIn("Primary civilian group lock", cleaned)
        self.assertIn("bare hair or plain cloth caps only", cleaned)
        self.assertIn("helmets, mail, scale, shields, and swords stay on Roman soldiers behind them", cleaned)
        self.assertIn("larger than the background soldiers", cleaned)
        self.assertIn("all-soldier formation", compact_negative)
        self.assertIn("empty civilian foreground", compact_negative)
        self.assertIn("helmeted civilian", compact_negative)
        self.assertIn("armored civilian foreground", compact_negative)

    def test_flux2_klein_late_roman_fort_courtyard_keeps_loaded_wagons(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 375 AD; Late Roman Empire, Pannonian frontier response; "
            "Exact place: Pannonian fort courtyard crowded with civilians and soldiers; "
            "Main subject: frontier population demanding protection; "
            "Scene: Civilians press toward officers with raised hands while soldiers brace "
            "shields beside loaded wagons."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Open fort courtyard protection contract", cleaned)
        self.assertIn("loaded wooden wagons", cleaned)
        self.assertIn("wagon wheels", cleaned)
        self.assertIn("adult civilians", cleaned)
        self.assertIn("missing loaded wagons", compact_negative)
        self.assertIn("wall switch", compact_negative)

    def test_flux2_klein_late_roman_punitive_camp_preparation_stays_in_tents(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 375 AD; Late Roman Empire, punitive Danube campaign preparation; "
            "Exact place: Roman army camp in Pannonia; "
            "Main subject: Roman soldiers preparing punitive movement; "
            "Scene: Soldiers tighten shield straps and lift spears as officers load blank "
            "route tablets into leather satchels."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Open punitive camp preparation contract", cleaned)
        self.assertIn("closed dark wax route tablets", cleaned)
        self.assertIn("leather satchels", cleaned)
        self.assertIn("open sky", cleaned)
        self.assertIn("open paper with lines", compact_negative)
        self.assertIn("missing leather satchels", compact_negative)

    def test_flux2_klein_late_roman_campaign_march_keeps_pack_animals(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 375 AD; Late Roman Empire, Valentinianic Danube campaign; "
            "Exact place: military road leading toward Brigetio and the Danube; "
            "Main subject: Valentinian's army marching toward Brigetio; "
            "Scene: A column of infantry and pack animals surges along a muddy road toward "
            "the river frontier."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Open Danube campaign road contract", cleaned)
        self.assertIn("two foreground compact pack mules", cleaned)
        self.assertIn("muddy road", cleaned)
        self.assertIn("Horse and pack animal anatomy contract", cleaned)
        self.assertIn("missing pack animals", compact_negative)
        self.assertIn("city street replacing muddy road", compact_negative)

    def test_flux2_klein_late_roman_brigetio_transport_hub_keeps_boats(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 375 AD; Late Roman Empire, Brigetio military camp; "
            "Exact place: Brigetio camp yard beside river transport sheds; "
            "Main subject: Brigetio as a crowded command hub; "
            "Scene: River crews haul supplies from boats while infantry columns turn through "
            "timber gates under officer signals."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Open Brigetio transport hub contract", cleaned)
        self.assertIn("low river boats", cleaned)
        self.assertIn("supply sacks", cleaned)
        self.assertIn("rough timber camp gates", cleaned)
        self.assertIn("missing river boats", compact_negative)
        self.assertIn("wall switch", compact_negative)

    def test_flux2_klein_late_roman_crossing_patrol_stays_at_river(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 375 AD; Late Roman Empire, Danube retaliatory operations; "
            "Exact place: Danube crossing near Brigetio; "
            "Main subject: Roman patrol crossing toward Quadi territory; "
            "Scene: Infantry splash through a shallow crossing as cavalry wheels ahead and "
            "shields tilt against river spray."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Open Danube crossing patrol contract", cleaned)
        self.assertIn("shallow Danube water", cleaned)
        self.assertIn("compact cavalry", cleaned)
        self.assertIn("river spray", cleaned)
        self.assertIn("indoor puddle", compact_negative)
        self.assertIn("missing cavalry", compact_negative)

    def test_flux2_klein_late_roman_cavalry_deterrence_patrol_stays_mounted(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 375 AD; Late Roman Empire, Danubian deterrence campaign, 375 AD; "
            "Exact place: Roman cavalry patrol route north of the Danube; "
            "Main subject: Roman cavalry demonstrating punitive reach; "
            "Scene: Cavalrymen drive forward through frosted grass while Quadi scouts "
            "retreat toward a wooded ridge."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Open cavalry deterrence patrol contract", cleaned)
        self.assertIn("three to five mounted Roman cavalrymen", cleaned)
        self.assertIn("Horse-first composition lock", cleaned)
        self.assertIn("Quadi scout identity lock", cleaned)
        self.assertIn("Building inventory is empty", cleaned)
        self.assertIn("infantry-only scene", compact_negative)
        self.assertIn("soldiers walking beside building", compact_negative)
        self.assertIn("missing horses", compact_negative)

    def test_flux2_klein_late_roman_frontier_rider_mobilization_stays_with_horses(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 374-375 AD; Quadi and Sarmatian frontier mobilization; "
            "Exact place: northern Danube camp with riders preparing movement; "
            "Main subject: frontier warriors preparing retaliation; "
            "Scene: Quadi and Sarmatian riders tighten tack on small horses as smoky "
            "watchfires flare behind them."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Open frontier rider mobilization contract", cleaned)
        self.assertIn("small horses", cleaned)
        self.assertIn("Every visible horse has one head", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("all figures dressed as Roman soldiers", compact_negative)
        self.assertIn("modern stirrups", compact_negative)

    def test_flux2_klein_late_roman_pannonian_settlement_alarm_keeps_carts_and_riders(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 374-375 AD; Late Roman Empire, Pannonian incursions; "
            "Exact place: Pannonian settlement near the Danube road; "
            "Main subject: Pannonian settlement alarmed by raiders; "
            "Scene: Villagers drag carts toward a gate as riders crest a smoky ridge "
            "beyond Roman fields."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Open Pannonian settlement alarm contract", cleaned)
        self.assertIn("wooden carts", cleaned)
        self.assertIn("distant Quadi and Sarmatian riders", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("missing carts", compact_negative)
        self.assertIn("white modern dress", compact_negative)

    def test_flux2_klein_late_roman_damaged_estate_keeps_tenant_and_cart_outside(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 374-375 AD; Late Roman Empire, Pannonian frontier alarm; "
            "Exact place: damaged roadside estate in Pannonia; "
            "Main subject: damaged Roman estate after frontier raid; "
            "Scene: Smoke rises from an outbuilding as Roman soldiers lift a frightened "
            "tenant onto a cart."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Open damaged Pannonian estate contract", cleaned)
        self.assertIn("frightened adult tenant", cleaned)
        self.assertIn("low wooden cart", cleaned)
        self.assertIn("Intercisa or Berkasovo style segmented ridge helmets", cleaned)
        self.assertIn("shield silhouettes stay oval", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("wall switch", compact_negative)
        self.assertIn("missing tenant", compact_negative)
        self.assertIn("Norman nasal helmet", compact_negative)
        self.assertIn("mail coif", compact_negative)

    def test_flux2_klein_late_roman_road_river_crossing_moves_civilians_outdoors(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 374-375 AD; Late Roman Empire, Pannonia on the Danube frontier; "
            "Exact place: Roman road and river crossing in Pannonia; "
            "Main subject: Pannonian road threatened by frontier movement; "
            "Scene: A Roman road runs beside reeds as soldiers hurry civilians away "
            "from an open river crossing."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Open Roman road river-crossing contract", cleaned)
        self.assertIn("muddy road", cleaned)
        self.assertIn("shallow water", cleaned)
        self.assertIn("adult civilians", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("white modern dress", compact_negative)
        self.assertIn("wall switch", compact_negative)

    def test_flux2_klein_late_roman_frontier_parley_stays_outdoor(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 374-375 AD; Late Roman Empire, Danubian frontier diplomacy; "
            "Exact place: temporary parley space near the Danube; "
            "Main subject: frontier parley with exchange objects; "
            "Scene: Roman officers set plain gift bowls and belt fittings on a table "
            "while guarded youths wait nearby."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Open frontier parley contract", cleaned)
        self.assertIn("open pale sky", cleaned)
        self.assertIn("rough plank table", cleaned)
        self.assertIn("plain bronze gift bowls", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("interior room", compact_negative)
        self.assertIn("wall switch", compact_negative)
        self.assertIn("child at table", compact_negative)

    def test_flux2_klein_late_roman_quadi_council_fire_blocks_walls_and_roman_armor(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 374-375 AD; Quadi frontier society under Roman pressure; "
            "Exact place: Quadi council fire near contested Danube ground; "
            "Main subject: Quadi council reacting to Roman building; "
            "Scene: Cloaked Quadi leaders strike spear shafts into earth while families "
            "gather behind smoking campfires."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Open Quadi council fire contract", cleaned)
        self.assertIn("open sky", cleaned)
        self.assertIn("hide tents", cleaned)
        self.assertIn("Quadi identity contract", cleaned)
        self.assertIn("Headwear material inventory", cleaned)
        self.assertIn("Adult Quadi clothing contract", cleaned)
        self.assertNotIn("armor layers", cleaned)
        self.assertNotIn("helmets, footwear", cleaned)
        self.assertNotIn("Roman armor", cleaned)
        self.assertNotIn("ridge helmets", cleaned)
        self.assertNotIn("mail shirts", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("wall switch", compact_negative)
        self.assertIn("Roman helmets on Quadi leaders", compact_negative)
        self.assertIn("metal helmet", compact_negative)

    def test_flux2_klein_late_roman_quadi_gathering_keeps_gabinius_outdoor(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 374-375 AD; Quadi frontier society and Late Roman diplomacy; "
            "Exact place: Quadi gathering place near the Danube frontier; "
            "Main subject: Gabinius among Quadi followers; "
            "Scene: A dignified Quadi king in layered wool gestures calmly while armed "
            "followers lean close around him."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Open Quadi gathering contract", cleaned)
        self.assertIn("Gabinius", cleaned)
        self.assertIn("Adult Quadi clothing contract", cleaned)
        self.assertIn("Headwear material inventory", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("all figures dressed as Roman soldiers", compact_negative)
        self.assertIn("gold crown", compact_negative)
        self.assertIn("wall switch", compact_negative)

    def test_flux2_klein_late_roman_quadi_news_and_mourning_stays_in_camp(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 374-375 AD; Quadi frontier society after Gabinius; "
            "Exact place: Quadi camp north of the Danube; "
            "Main subject: Quadi community receiving news of Gabinius; "
            "Scene: Messengers rush into a Quadi camp as mourners clutch cloaks and "
            "warriors seize spear shafts."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Open Quadi urgent camp contract", cleaned)
        self.assertNotIn("receiving news", cleaned)
        self.assertIn("running messengers", cleaned)
        self.assertIn("Adult Quadi clothing contract", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("wall switch", compact_negative)
        self.assertIn("all figures dressed as Roman soldiers", compact_negative)
        self.assertIn("overhead title", compact_negative)

    def test_flux2_klein_late_roman_quadi_mourning_circle_uses_broken_cup_outdoor(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 374-375 AD; Quadi frontier society after Gabinius; "
            "Exact place: Quadi mourning circle near the Danube; "
            "Main subject: Quadi mourning turning into distrust; "
            "Scene: A fur-cloaked elder raises a broken drinking cup while younger warriors "
            "turn toward the river."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Open Quadi mourning circle contract", cleaned)
        self.assertIn("broken plain cup", cleaned)
        self.assertIn("riverbank mud", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("wall switch", compact_negative)
        self.assertIn("gold crown", compact_negative)

    def test_flux2_klein_late_roman_construction_work_camp_stays_outdoor(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 374-375 AD; Late Roman Empire, frontier administration; "
            "Exact place: Roman work camp beside contested fortification; "
            "Main subject: Roman officers enforcing construction; "
            "Scene: An officer signals workers forward while shield-bearing guards shove back "
            "arguing men at the perimeter."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Open construction work camp contract", cleaned)
        self.assertIn("wood-and-earth frontier works", cleaned)
        self.assertIn("stacked logs", cleaned)
        self.assertIn("palisade posts", cleaned)
        self.assertIn("low turf rampart", cleaned)
        self.assertIn("open sky", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("wall switch", compact_negative)
        self.assertIn("medieval castle", compact_negative)
        self.assertIn("crenellated wall", compact_negative)
        self.assertIn("modern construction helmet", compact_negative)

    def test_flux2_klein_late_roman_frontier_headquarters_stays_at_disputed_works(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 374-375 AD; Late Roman Empire, frontier military hierarchy; "
            "Exact place: Roman frontier headquarters near Brigetio's region; "
            "Main subject: Marcellianus commanding local officers; "
            "Scene: Marcellianus points toward the disputed works as junior officers "
            "tighten belts and prepare guards."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Open frontier headquarters contract", cleaned)
        self.assertIn("stake line", cleaned)
        self.assertIn("palisade posts", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("wall switch", compact_negative)
        self.assertIn("timber door", compact_negative)

    def test_flux2_klein_late_roman_construction_reception_keeps_stakes_outside(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 374-375 AD; Late Roman Empire, Danube crisis diplomacy; "
            "Exact place: Roman reception area beside contested construction; "
            "Main subject: Roman officers preparing a tense reception; "
            "Scene: Officers arrange stools and guards near a blank table as construction "
            "stakes remain visible outside."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Open construction reception contract", cleaned)
        self.assertIn("construction stakes outside", cleaned)
        self.assertIn("blank rough table", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("wall switch", compact_negative)
        self.assertIn("open paper with lines", compact_negative)

    def test_flux2_klein_late_roman_ford_patrol_stays_at_water_crossing(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 374-375 AD; Late Roman Empire, Danubian frontier crisis; "
            "Exact place: Danube ford watched by Roman and Quadi patrols; "
            "Main subject: opposing patrols nearly colliding; "
            "Scene: Roman infantry and Quadi horsemen halt at a muddy ford, weapons lowered "
            "but bodies tense forward."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Muddy ford collision contract", cleaned)
        self.assertIn("shallow river water", cleaned)
        self.assertIn("Quadi horsemen", cleaned)
        self.assertIn("Every visible horse has one head", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("missing river water", compact_negative)
        self.assertIn("wall switch", compact_negative)

    def test_flux2_klein_late_roman_command_tent_uses_canvas_not_room(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 374-375 AD; Late Roman Empire, Danube crisis background; "
            "Exact place: Roman command tent near the contested Danube works; "
            "Main subject: Roman command tent before a dangerous meeting; "
            "Scene: Tent flaps snap in river wind as armed attendants prepare a bare "
            "reception space under watchful officers."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Canvas command tent contract", cleaned)
        self.assertIn("open flaps", cleaned)
        self.assertIn("stitched canvas seams", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("timber door", compact_negative)
        self.assertIn("wall switch", compact_negative)

    def test_flux2_klein_late_roman_command_tent_imperial_field_command_gathers_cases(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 375 AD; Late Roman Empire, imperial field command; "
            "Exact place: imperial command tent on the Danube frontier; "
            "Main subject: Valentinian commanding in person; "
            "Scene: The emperor strides through a tent as officers gather helmets, shields, "
            "and sealed dispatch cases."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Canvas command tent contract", cleaned)
        self.assertIn("older Valentinian walking", cleaned)
        self.assertIn("sealed dark cylindrical dispatch cases", cleaned)
        self.assertIn("open canvas tent", cleaned)
        self.assertIn("wall switch", compact_negative)
        self.assertIn("open paper with lines", compact_negative)

    def test_flux2_klein_late_roman_command_tent_tablet_blocks_crown(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 374-375 AD; Late Roman Empire, Danubian frontier command; "
            "Exact place: Roman command tent near the Danube frontier; "
            "Main subject: Marcellianus revealed in a frontier command tent; "
            "Scene: A stern Roman commander in scale armor studies a blank tablet while "
            "officers wait uneasily behind him."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Canvas command tent contract", cleaned)
        self.assertIn("closed dark wax tablet", cleaned)
        self.assertIn("rough field table", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("gold crown", compact_negative)
        self.assertIn("wall switch", compact_negative)

    def test_flux2_klein_late_roman_command_tent_frontier_reports_blocks_wall_switch(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 375 AD; Late Roman Empire, Danube crisis; "
            "Exact place: Brigetio command tent receiving frontier reports; "
            "Main subject: Valentinian receiving alarming frontier news; "
            "Scene: A mud-spattered courier kneels before Valentinian as officers thrust "
            "sealed tubes across the command table."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Canvas command tent contract", cleaned)
        self.assertIn("Older Valentinian stands upright", cleaned)
        self.assertIn("kneeling courier", cleaned)
        self.assertIn("sealed plain tubes", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("wall switch", compact_negative)
        self.assertIn("timber door", compact_negative)
        self.assertIn("Valentinian kneeling", compact_negative)

    def test_flux2_klein_late_roman_command_tent_bad_reports_points_to_smoke(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 375 AD; Late Roman Empire, Pannonian command response; "
            "Exact place: Roman field headquarters in Pannonia; "
            "Main subject: Roman commanders receiving bad reports; "
            "Scene: Commanders lean over blank tablets as a courier points back toward "
            "smoke beyond the tent flap."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Canvas command tent contract", cleaned)
        self.assertIn("Bad-report inventory", cleaned)
        self.assertIn("smoke beyond the canvas", cleaned)
        self.assertIn("Intercisa or Berkasovo style segmented ridge helmets", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("wall switch", compact_negative)
        self.assertIn("crusader helmet", compact_negative)

    def test_flux2_klein_late_roman_command_tent_valentinian_dispatch_stays_upright(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 375 AD; Late Roman Empire, Valentinianic command; "
            "Exact place: imperial command tent in Pannonia; "
            "Main subject: Valentinian confronting reports of raids; "
            "Scene: Valentinian clenches a sealed dispatch while officers lower their "
            "heads beside stacked shields."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Canvas command tent contract", cleaned)
        self.assertIn("Older Valentinian stands upright", cleaned)
        self.assertIn("sealed dispatch tube", cleaned)
        self.assertIn("one visible wax seal", cleaned)
        self.assertIn("only hand-held message object", cleaned)
        self.assertIn("stacked plain oval shields", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("Valentinian kneeling", compact_negative)
        self.assertIn("open white paper sheet", compact_negative)
        self.assertIn("stacked white papers", compact_negative)

    def test_flux2_klein_late_roman_command_tent_aftermath_uses_overturned_cup(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Place scope: Brigetio Roman military camp on the Danube frontier, Pannonia; "
            "Year/period: 374-375 AD; Late Roman Empire and Quadi diplomacy; "
            "Exact place: Roman command tent after Gabinius's reception; "
            "Main subject: abrupt aftermath of Gabinius's reception; "
            "Scene: An overturned cup and scattered cloak pins lie near a tent entrance "
            "as Roman officers stare in alarm."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("Canvas command tent contract", cleaned)
        self.assertIn("overturned plain cup", cleaned)
        self.assertIn("scattered cloak pins", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("wall switch", compact_negative)
        self.assertIn("timber door", compact_negative)

    def test_flux2_klein_late_roman_admin_corridor_uses_sealed_cases(self):
        source = (
            "Global visual world: Time range: Late Roman Empire, primarily 364-375 AD; "
            "Year/period: after 375 AD; Late Roman Empire, Western Empire after Valentinian I; "
            "Exact place: western Roman administrative corridor after the succession; "
            "Main subject: western administration continuing after Valentinian; "
            "Scene: Officials hurry through a stone corridor carrying sealed cases as soldiers guard doorways with oval shields."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)

        self.assertIn("carrying sealed plain wooden cases", cleaned)
        self.assertIn("Case surfaces are plain wood grain", cleaned)
        self.assertIn("Shield face contract", cleaned)
        self.assertNotIn("Door-adjacent wall integrity contract", cleaned)
        self.assertIn("drawer front writing", compact_negative)

    def test_flux2_klein_blank_roman_standards_rewrite_to_plain_poles(self):
        prompt = (
            "375 AD Late Roman Empire, Brigetio audience threshold. "
            "Envoys pause under blank Roman standards while attendants pull open heavy timber doors."
        )

        cleaned = _flux2_klein_positive_contract_cleanup(prompt)

        self.assertIn("plain Roman spear poles with blank folded cloth", cleaned)
        self.assertNotIn("blank Roman standards", cleaned)
        self.assertNotIn("Roman standards", cleaned)

    def test_flux2_klein_japanese_still_war_road_uses_ground_crop(self):
        source = (
            "Global visual world: Time range: 1590s; Azuchi-Momoyama Japan, "
            "closing of Sengoku mobility; Culture scope: Japanese samurai political culture; "
            "Year/period: 1590s; Exact place: quiet road between fields and castle; "
            "Main subject: still road after wartime movement ends; "
            "Scene: The once-busy war road lies still as farmers, warriors, and officials "
            "remain in fixed places.; Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("field-road evidence", compact)
        self.assertIn("edge-to-edge top-down ground crop", compact)
        self.assertIn("human-free, face-free, torso-free", compact)
        self.assertNotRegex(compact.lower(), r"\b(?:sign|scroll|kanji|kana|characters|plaque)\b")
        self.assertIn("background vertical sign", compact_negative)
        self.assertIn("wall scroll at image edge", compact_negative)
        self.assertIn("switch-like wall rectangle", compact_negative)
        self.assertIn("full standing people", compact_negative)

    def test_flux2_klein_japanese_banners_become_bare_standard_poles(self):
        source = (
            "Global visual world: Time range: 1575, Sengoku period Japan; "
            "Place scope: Nagashino Castle, Shitaragahara plain, Mikawa frontier; "
            "Culture scope: Japanese Sengoku warrior society, Takeda domain military culture; "
            "Year/period: 1575; Exact place: Takeda cavalry assembly area near Nagashino; "
            "Main subject: Takeda mounted retainers forming up; "
            "Scene: Armored horsemen press forward through wet grass, yari angled low, "
            "unmarked red banners snapping in wind; Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("bare rope-tied vertical standard poles", compact)
        self.assertIn("wood shafts, rope knots, spear tips, empty pole tops, dust, and shadow", compact)
        self.assertNotIn("unmarked red banners snapping", compact)
        self.assertIn("black characters on red flag", compact_negative)
        self.assertIn("black characters on white banner", compact_negative)
        self.assertIn("mon on banner", compact_negative)
        self.assertIn("marked sashimono", compact_negative)

    def test_flux2_klein_japanese_allied_banners_keep_one_command_boundary(self):
        source = (
            "Global visual world: Time range: 1575, Sengoku period Japan; "
            "Place scope: Nagashino Castle, Shitaragahara plain, Mikawa frontier; "
            "Culture scope: Japanese Sengoku warrior society, Oda-Tokugawa alliance; "
            "Year/period: 1575; Exact place: allied command boundary between Oda and Tokugawa positions; "
            "Main subject: adjacent Oda and Tokugawa positions; "
            "Scene: Unmarked allied banners whip beside separate command screens as messengers run between the two camps.; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("messengers run through one continuous open command boundary", compact)
        self.assertIn("bare rope-tied vertical standard poles", compact)
        self.assertIn("one continuous unpartitioned 16:9 view", compact)
        self.assertNotIn("command screens", compact.lower())
        self.assertIn("side-by-side panels", compact_negative)
        self.assertIn("black central divider", compact_negative)

    def test_flux2_klein_japanese_yamazaki_banner_avoids_utility_poles(self):
        source = (
            "Global visual world: Time range: Late Sengoku Japan, centered on 1582; "
            "Culture scope: Japanese warrior elite, castle-town politics; "
            "Year/period: 1582; Exact place: Yamazaki battlefield at dusk; "
            "Main subject: Akechi banner bending at dusk; "
            "Scene: An Akechi plain bare rope-tied vertical standard poles bends sharply in dusk wind as retreating "
            "feet churn mud around fallen gear.; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Ground-level Yamazaki retreat evidence", compact)
        self.assertIn("short broken wooden staff lies flat", compact)
        self.assertNotIn("bends sharply", compact)
        self.assertIn("crossbar utility pole", compact_negative)
        self.assertIn("wooden windmill", compact_negative)

    def test_flux2_klein_japanese_yamazaki_aftermath_avoids_cross_posts(self):
        source = (
            "Global visual world: Time range: Late Sengoku Japan, centered on 1582; "
            "Culture scope: Japanese warrior elite, castle-town politics; "
            "Year/period: 1582; Exact place: quiet Yamazaki hillside at dawn; "
            "Main subject: dawn over abandoned battle traces; "
            "Scene: Dawn light touches abandoned armor cords and a fallen plain bare rope-tied vertical standard poles "
            "on Yamazaki hillside, smoke thinning slowly.; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Object-only Yamazaki aftermath ground evidence", compact)
        self.assertIn("folded blank cloth strip lying flat", compact)
        self.assertNotIn("fallen plain banner on Yamazaki hillside", compact)
        self.assertIn("execution frame", compact_negative)
        self.assertIn("upright banner pole", compact_negative)

    def test_flux2_klein_japanese_street_edges_block_signatures_and_nameplates(self):
        source = (
            "Global visual world: Time range: 1575, Sengoku period Japan; "
            "Place scope: Nagashino Castle, Shitaragahara plain, Mikawa frontier; "
            "Culture scope: Japanese Sengoku warrior society, Takeda domain military culture; "
            "Year/period: 1575; Exact place: Takeda command position near Shitaragahara; "
            "Main subject: Katsuyori under pressure; "
            "Scene: Katsuyori grips his reins hard, eyes narrowed, while retainers stare "
            "at him through drifting smoke; Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("continuous timber", compact)
        self.assertIn("Lower image corners are empty ordinary material", compact)
        self.assertIn("small wooden nameplate over doorway", compact_negative)
        self.assertIn("rectangular sign above door", compact_negative)
        self.assertIn("lower-right Japanese signature", compact_negative)
        self.assertIn("small white rectangle beside door", compact_negative)
        self.assertIn("rectangular white plate on plaster", compact_negative)

    def test_flux2_klein_ondal_bamboo_characters_become_blank_slips(self):
        source = (
            "Global visual world: Time range: 590year; Place scope: ancient Northeast Asia, "
            "Goguryeo-related court and frontier settings; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Exact place: Pyongyang Fortress; "
            "Scene: Ancient Chinese characters carved into bamboo, focusing on the surname; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Late sixth-century Goguryeo", compact)
        self.assertIn("Object-only blank bamboo surname-clue evidence", compact)
        self.assertIn("blank bamboo slips", compact)
        self.assertNotIn("Ancient Chinese characters", compact)
        self.assertIn("Chinese characters", compact_negative)
        self.assertIn("carved characters", compact_negative)

    def test_flux2_klein_ondal_soldier_weapons_block_guns(self):
        source = (
            "Global visual world: Time range: 590year; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Exact place: Pyongyang Fortress; "
            "Scene: All soldiers pointing their weapons respectfully towards the bloody warrior; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Goguryeo soldiers salute with period weapons only", compact)
        self.assertIn("spears, bows, arrows, and short straight iron blades", compact)
        self.assertIn("upper door zones cropped away", compact)
        self.assertNotRegex(compact.lower(), r"\b(?:zero|guns?|rifles?|modern|headers?|lintels?|plaques?|signboards?|marks?)\b")
        self.assertIn("rifle", compact_negative)
        self.assertIn("gun barrels", compact_negative)
        self.assertIn("rectangular board above door", compact_negative)

    def test_flux2_klein_ondal_defensive_sky_blocks_overdoor_boards(self):
        source = (
            "Global visual world: Time range: 590year; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Exact place: Pyongyang Fortress; "
            "Scene: A dark, imposing sky pressing down on the Goguryeo defensive lines; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Goguryeo storm-pressure defensive-line exterior", compact)
        self.assertIn("dark clouds dominating the upper half", compact)
        self.assertIn("upper door zones cropped away", compact)
        self.assertNotRegex(
            compact.lower(),
            r"\b(?:headers?|lintels?|eaves?|plaques?|signboards?|text|writing|glyphs?|characters?|marks?)\b",
        )
        self.assertIn("black strokes arranged in a row above door", compact_negative)

    def test_flux2_klein_ondal_shield_fragments_do_not_become_marked_disk(self):
        source = (
            "Global visual world: Time range: 590year; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Exact place: Pyongyang Fortress; "
            "Scene: Shattered pieces of wooden shields and iron flying through the air; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Goguryeo shield-splinter impact action", compact)
        self.assertIn("jagged broken wooden shield splinters", compact)
        self.assertNotIn("plain round wooden shield", compact.lower())
        self.assertNotIn("abstract scratched shapes", compact.lower())
        self.assertNotRegex(
            compact.lower(),
            r"\b(?:headers?|lintels?|eaves?|plaques?|signboards?|text|writing|glyphs?|characters?|marks?|symbols?)\b",
        )
        self.assertIn("round wooden disk", compact_negative)
        self.assertIn("glyph scratches on shield", compact_negative)

    def test_flux2_klein_ondal_gear_metaphor_becomes_period_wheel(self):
        source = (
            "Global visual world: Time range: 590year; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Exact place: Pyongyang Fortress; "
            "Scene: A cold iron gear brutally grinding up a soft, delicate flower; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Period crushing-wheel pressure evidence", compact)
        self.assertIn("smooth-rimmed wood and hammered iron banding", compact)
        self.assertNotRegex(compact.lower(), r"\b(?:gear|cog|cogwheel|toothed|teeth|sprocket)\b")
        self.assertIn("toothed cogwheel", compact_negative)

    def test_flux2_klein_ondal_golden_armor_becomes_dark_lamellar(self):
        source = (
            "Global visual world: Time range: 590year; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Exact place: Pyongyang Fortress; "
            "Scene: A ragged cloth transforming visually into heavy, shining golden armor; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Ragged-cloth to practical lamellar reveal", compact)
        self.assertIn("dark leather-and-small-plate lamellar armor", compact)
        self.assertNotRegex(compact.lower(), r"\b(?:gold|golden|shining|cuirass)\b")
        self.assertIn("shining golden armor", compact_negative)

    def test_flux2_klein_ondal_bloody_brush_uses_bamboo_bundle_not_paper(self):
        source = (
            "Global visual world: Time range: 590year; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Exact place: Pyongyang Fortress; "
            "Scene: A bloody brush forcefully writing characters on a military dispatch scroll; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Object-only bloody brush and blank bamboo-slip bundle evidence", compact)
        self.assertIn("blood-wet brush tip resting on the edge", compact)
        self.assertNotRegex(compact.lower(), r"\b(?:paper|scroll|characters?|writing|glyphs?|text|marks?)\b")
        self.assertIn("open paper sheet", compact_negative)
        self.assertIn("brush writing characters", compact_negative)

    def test_flux2_klein_ondal_footprint_law_scroll_becomes_closed_bundle(self):
        source = (
            "Global visual world: Time range: 590year; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Exact place: Pyongyang Fortress; "
            "Scene: A bloody footprint stamped onto a clean scroll of laws and ethics; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Object-only bloody footprint on law-bundle evidence", compact)
        self.assertIn("closed cord-tied blank wooden authority bundle", compact)
        self.assertNotRegex(compact.lower(), r"\b(?:paper|scroll|characters?|writing|glyphs?|text|marks?)\b")
        self.assertIn("law scroll page", compact_negative)

    def test_flux2_klein_ondal_chess_pieces_become_clay_counters(self):
        source = (
            "Global visual world: Time range: 590year; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Exact place: Pyongyang Fortress; "
            "Scene: Two ancient politicians manipulating chess pieces in the pitch-dark shadows; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Goguryeo command-workbench intrigue scene", compact)
        self.assertIn("irregular plain clay counters", compact)
        self.assertNotRegex(compact.lower(), r"\b(?:chess|chessboard|grid|marks?|symbols?)\b")
        self.assertIn("miniature chess pieces", compact_negative)

    def test_flux2_klein_ondal_blade_choice_stays_single_continuous_frame(self):
        source = (
            "Global visual world: Time range: 590year; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Exact place: Pyongyang Fortress; "
            "Scene: A rusty, ornate sword discarded for a simple, highly sharpened battle blade; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Single continuous blade-choice workbench evidence", compact)
        self.assertIn("One uninterrupted low dark wooden workbench", compact)
        self.assertIn("same tabletop", compact)
        self.assertNotRegex(compact.lower(), r"\b(?:split|two-panel|divider|white gap)\b")
        self.assertIn("split screen", compact_negative)

    def test_flux2_klein_ondal_dragon_banner_is_blank_cloth(self):
        source = (
            "Global visual world: Time range: 590year; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Exact place: Goguryeo border; "
            "Scene: A massive Chinese dragon banner looming ominously over the border; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Object-only border threat standard cloth", compact)
        self.assertIn("unmarked cloth military standard", compact)
        self.assertIn("abstract S-shaped dark fold shadow", compact)
        self.assertNotIn("dragon", compact.lower())
        self.assertIn("dragon sculpture", compact_negative)
        self.assertIn("living dragon", compact_negative)
        self.assertIn("building sign behind banner", compact_negative)

    def test_flux2_klein_ondal_spear_impact_is_object_only_macro(self):
        source = (
            "Global visual world: Time range: 590year; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Exact place: Pyongyang Fortress; "
            "Scene: A heavy spear violently piercing through thick enemy armor, motion blur; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Extreme object-only lamellar impact macro", compact)
        self.assertIn("spearhead visibly penetrates", compact)
        self.assertNotRegex(compact.lower(), r"\b(?:zero|buildings?|split panel|wall switch|gun parts)\b")
        self.assertIn("vertical white panel divider", compact_negative)
        self.assertIn("wall switch in spear impact scene", compact_negative)

    def test_flux2_klein_anglo_saxon_map_becomes_object_workbench(self):
        source = (
            "Global visual world: Time range: 1013-1016 AD, late Anglo-Saxon England during "
            "the Danish conquest; Place scope: Wessex, London, Mercia, Northumbria, the "
            "Thames Valley, Assandun in Essex, the Severn region; Culture scope: "
            "Anglo-Saxon English and Danish-Norse military aristocratic culture in early "
            "eleventh-century England; Year/period: 1016; Exact place: council table "
            "between London and Danish zones; Scene evidence: A split map visualizes "
            "rival centers of power.; Main subject: split parchment map of England; "
            "Scene: Two hands pull opposite edges of a damp island map, tearing folds "
            "through central shires.; Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("1016 Anglo-Saxon England and Danish-Norse conquest", compact)
        self.assertIn("Object-only frame-filling evidence workbench", compact)
        self.assertIn("pebble counters", compact)
        self.assertNotRegex(
            compact.lower(),
            r"\b(?:1190|holy roman|crusad|anatolian|byzantine|seljuk|kite shields?|"
            r"map|paper|parchment|document|book|page|writing|text|letters?|label|"
            r"signboard|plaque|switch|outlet|socket)\b",
        )
        self.assertIn("parchment map", compact_negative)
        self.assertIn("wall switch", compact_negative)

    def test_flux2_klein_anglo_saxon_scene_avoids_crusade_context(self):
        source = (
            "Global visual world: Time range: 1013-1016 AD, late Anglo-Saxon England during "
            "the Danish conquest; Culture scope: Anglo-Saxon English and Danish-Norse "
            "military aristocratic culture in early eleventh-century England; "
            "Year/period: 1016; Exact place: timber hall in Wessex; Main subject: "
            "Edmund Ironside among armed retainers; Scene: Mail-clad men stand around "
            "a guarded high seat under hearth smoke.; Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("1016 Anglo-Saxon England and Danish-Norse conquest", compact)
        self.assertIn("round wooden shields", compact)
        self.assertNotRegex(
            compact.lower(),
            r"\b(?:1190|holy roman|crusad|anatolian|byzantine|seljuk|kite shields?|"
            r"switch|outlet|socket|label|plaque|signboard)\b",
        )
        self.assertIn("Holy Roman Empire", compact_negative)
        self.assertIn("wall switch", compact_negative)

    def test_flux2_klein_anglo_saxon_final_marker_layout_routes_to_workbench(self):
        final_like = (
            "Year/period: late 1016; Late Anglo-Saxon England during the Danish conquest, 1016; "
            "Exact place: council table in Wessex; Scene evidence: A single low horizontal "
            "tactile marker layout on a visible table with loose route cords, separated stone "
            "markers, bronze weights, dust, and hard side light represents the confirmed "
            "political transfer.; Main subject: England low horizontal tactile marker layout "
            "closing under one head-worn period-local ruler status diadem strip; Scene: a hand "
            "folds the divided surface beneath Cnut's crown token.; Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(final_like, "")

        self.assertIn("Object-only frame-filling evidence workbench", compact)
        self.assertIn("All four image edges are dark wood tabletop", compact)
        self.assertNotRegex(
            compact.lower(),
            r"\b(?:1190|holy roman|crusad|anatolian|byzantine|seljuk|kite shields?|"
            r"map|paper|parchment|document|book|page|writing|text|letters?|label|"
            r"signboard|plaque|switch|outlet|socket)\b",
        )
        self.assertIn("line grid on table", compact_negative)
        self.assertIn("wall text", compact_negative)

    def test_flux2_klein_anglo_saxon_riverside_meeting_blocks_signboard(self):
        final_like = (
            "Year/period: late 1016; Late Anglo-Saxon England during the Danish conquest, 1016; "
            "Exact place: riverside meeting place traditionally associated with Olney; "
            "Scene evidence: The meeting setting introduces the post-Assandun settlement.; "
            "Main subject: riverside peace meeting; Scene: Cold water moves behind armed "
            "escorts as two royal parties approach across muddy reeds.; Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(final_like, "")

        self.assertIn("Open riverside peace-meeting exterior", compact)
        self.assertIn("Upper image area is open sky", compact)
        self.assertNotRegex(
            compact.lower(),
            r"\b(?:1190|holy roman|crusad|anatolian|byzantine|seljuk|kite shields?|"
            r"text|letters?|label|signboard|plaque|switch|outlet|socket)\b",
        )
        self.assertIn("riverside signboard", compact_negative)
        self.assertIn("white title plaque", compact_negative)

    def test_flux2_klein_anglo_norman_context_avoids_crusade_context(self):
        source = (
            "Global visual world: Time range: 1066-1106 AD, Anglo-Norman Normandy and England; "
            "Culture scope: Anglo-Norman aristocratic politics after William I; "
            "Year/period: 1087; Exact place: Norman field camp outside a burned town; "
            "Main subject: William I among mounted retainers; Scene: A mailed ruler rides "
            "past grim nobles under smoke and hard side light.; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("1087 Anglo-Norman Normandy and England", compact)
        self.assertIn("kite shields", compact)
        self.assertNotRegex(
            compact.lower(),
            r"\b(?:1190|holy roman|crusad|anatolian|byzantine|seljuk)\b",
        )
        self.assertIn("Holy Roman Empire", compact_negative)

    def test_flux2_klein_anglo_norman_doorway_blocks_place_signs(self):
        source = (
            "Year/period: 1087; Anglo-Norman aristocratic politics, late eleventh century; "
            "Culture scope: Anglo-Norman, Capetian French, Latin Christian monastic and "
            "aristocratic culture; "
            "Exact place: Norman ducal hall doorway near Rouen and Mantes; "
            "Main subject: nobles approving the campaign; Scene: Armed magnates nod grimly "
            "as William passes them, his dark cloak sweeping over rush-covered flooring.; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Single continuous Anglo-Norman hall threshold", compact)
        self.assertIn("continuous blank stone arches", compact)
        self.assertIn("full-bleed edge-to-edge", compact)
        self.assertNotRegex(
            compact,
            r"\b(?:Rouen|Mantes|sign|signboard|label|plaque|table|paper|page|parchment)\b",
        )
        self.assertIn("ROUEN text", compact_negative)
        self.assertIn("MANTES text", compact_negative)
        self.assertIn("overdoor sign", compact_negative)
        self.assertIn("white border", compact_negative)

    def test_flux2_klein_anglo_norman_chronicler_reflection_avoids_face_overlay(self):
        source = (
            "Year/period: c. 1087-1125; Norman monastic historical memory after William I; "
            "Exact place: writing desk in a Norman monastery; Main subject: chronicler "
            "reflecting on the burial; Scene: A monk presses a hand to his brow beside "
            "blank parchment, a small candle burning beside a wooden cross.; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Single continuous Norman monastic room view", compact)
        self.assertIn("one hand at his brow", compact)
        self.assertNotRegex(
            compact.lower(),
            r"\b(?:giant face|eye|reflection|inset|collage|double exposure|helmet|"
            r"mail hauberk|spear|sword)\b",
        )
        self.assertIn("inset warrior in eye", compact_negative)
        self.assertIn("giant face", compact_negative)

    def test_flux2_klein_anglo_norman_writing_uses_closed_parchment(self):
        source = (
            "Year/period: c. 1087-1125; Latin monastic historical writing after William I; "
            "Exact place: Norman monastic writing room; Main subject: chronicler recording "
            "the burial; Scene: A monk writes on blank parchment while the candlelight "
            "catches his tense eyes and ink-dark fingers.; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("closed leather-wrapped record packets", compact)
        self.assertIn("tied cylindrical roll ends", compact)
        self.assertNotRegex(
            compact.lower(),
            r"\b(?:writing|writes|written|paper|page|text|letters|ink rows|fake latin|"
            r"helmet|mail hauberk|spear|sword|parchment)\b",
        )
        self.assertIn("written lines", compact_negative)
        self.assertIn("fake Latin text", compact_negative)

    def test_flux2_klein_ondal_beast_face_remains_human(self):
        source = (
            "Global visual world: Time range: 590year; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Exact place: Pyongyang Fortress; "
            "Main subject: Ondal; Scene: A warrior's face completely covered in mud and blood, "
            "looking like a beast; Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Human-only exhausted warrior close-up", compact)
        self.assertIn("one fully human Goguryeo warrior", compact)
        self.assertNotRegex(compact.lower(), r"\b(?:zero|pointed ears|monster|nonhuman)\b")
        self.assertIn("monster", compact_negative)
        self.assertIn("pointed ears", compact_negative)

    def test_flux2_klein_ondal_ep16_chessboard_metaphor_becomes_period_workbench(self):
        source = (
            "Global visual world: Time range: 590year; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Exact place: Pyongyang Fortress; "
            "Main subject: Ondal; Scene: A dark ancient chessboard with a single bloody pawn; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Goguryeo command-workbench danger evidence", compact)
        self.assertIn("blood-dark plain clay counter", compact)
        self.assertIn("plain pebble counters", compact)
        self.assertNotRegex(
            compact.lower(),
            r"\b(?:zero|no|without|avoid|forbidden|exclude|not|never|absent|"
            r"switch(?:es)?|outlets?|electric|modern|text|writing|glyphs?|"
            r"letters?|characters?|signboards?|plaques?|documents?|paper|"
            r"chessboard|pawn|guns?|rifles?|roman|european|monster)\b",
        )
        self.assertIn("light switch", compact_negative)
        self.assertIn("readable writing", compact_negative)

    def test_flux2_klein_ondal_ep16_strategy_scroll_becomes_object_workbench(self):
        source = (
            "Global visual world: Time range: 590year; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Exact place: Pyongyang Fortress; "
            "Scene: The princess unfurling a military strategy scroll, pointing at formations; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Goguryeo strategy-table planning scene", compact)
        self.assertIn("Princess Pyeonggang", compact)
        self.assertIn("raised cord lines", compact)
        self.assertIn("pebble counters", compact)
        self.assertNotRegex(
            compact.lower(),
            r"\b(?:zero|no|without|avoid|forbidden|exclude|not|never|absent|"
            r"switch(?:es)?|outlets?|electric|modern|text|writing|glyphs?|"
            r"letters?|characters?|signboards?|plaques?|documents?|paper|"
            r"scroll|map|diagram|grid|guns?|rifles?|roman|european|monster)\b",
        )
        self.assertIn("unfurled paper strategy map", compact_negative)
        self.assertIn("scroll with writing", compact_negative)

    def test_flux2_klein_ondal_scalpel_text_becomes_blank_record_bundle(self):
        source = (
            "Global visual world: Time range: 590year; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Exact place: Pyongyang Fortress; "
            "Scene: A sharp surgical scalpel slicing cleanly through an old, dusty text; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Object-only blade slicing blank wooden slip bundle", compact)
        self.assertIn("short plain early Korean iron knife blade", compact)
        self.assertNotIn("surgical scalpel", compact)
        self.assertNotIn("old, dusty text", compact)
        self.assertIn("surgical scalpel", compact_negative)
        self.assertIn("old dusty text", compact_negative)

    def test_flux2_klein_ondal_ep17_blood_treaty_document_becomes_closed_bundle(self):
        source = (
            "Global visual world: Time range: 590year; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Year/period: 590 AD; "
            "Scene: A political treaty document sealed with a stamp of blood; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Goguryeo closed-bundle blood-seal evidence", compact)
        self.assertIn("closed cord-tied blank bamboo-slip", compact)
        self.assertNotIn("political treaty document", compact)
        self.assertIn("split-screen", compact_negative)
        self.assertIn("open document", compact_negative)

    def test_flux2_klein_ondal_ep17_torn_law_scroll_becomes_closed_bundle(self):
        source = (
            "Global visual world: Time range: 590year; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Year/period: 590 AD; "
            "Scene: A torn scroll of laws lying forgotten in the muddy dirt; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Goguryeo closed-law bundle mud evidence", compact)
        self.assertIn("closed cord-tied blank bamboo-slip authority bundle", compact)
        self.assertNotIn("torn scroll", compact.lower())
        self.assertIn("law scroll page", compact_negative)

    def test_flux2_klein_ondal_ep17_final_prompt_law_packet_becomes_closed_bundle(self):
        source = (
            "Year/period: 590 AD; Culture scope: Goguryeo and neighboring ancient Northeast Asian "
            "political and military world; Scene: A torn rolled blank cream paper bundles of laws "
            "lying forgotten in the muddy dirt; Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Goguryeo closed-law bundle mud evidence", compact)
        self.assertIn("closed cord-tied blank bamboo-slip authority bundle", compact)
        self.assertNotIn("paper bundles of laws", compact.lower())
        self.assertIn("open paper sheet", compact_negative)

    def test_flux2_klein_ondal_ep17_buried_helmets_become_fragments(self):
        source = (
            "Global visual world: Time range: 590year; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Year/period: 590 AD; "
            "Scene: A pile of unnamed, broken helmets buried under the dirt; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Goguryeo buried helmet-fragment evidence", compact)
        self.assertIn("small broken helmet fragments half-buried in packed dirt", compact)
        self.assertIn("giant helmet", compact_negative)
        self.assertIn("oversized metal dome", compact_negative)

    def test_flux2_klein_ondal_ep17_mirror_uses_flat_bronze_fragments(self):
        source = (
            "Global visual world: Time range: 590year; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Year/period: 590 AD; "
            "Scene: A cracked, ancient bronze mirror reflecting a demonic face; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Goguryeo broken bronze mirror-fragment evidence", compact)
        self.assertIn("loose unmounted polished bronze mirror fragments", compact)
        self.assertNotIn("demonic face", compact)
        self.assertIn("clock face", compact_negative)
        self.assertIn("compass needle", compact_negative)

    def test_flux2_klein_ondal_ep17_siege_weapons_drop_cannon_language(self):
        source = (
            "Global visual world: Time range: 590year; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Year/period: 590 AD; "
            "Scene: Giant, terrifying mechanical siege weapons moving toward a high wall; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Goguryeo timber siege-pressure scene", compact)
        self.assertIn("rough wooden ladders", compact)
        self.assertNotRegex(compact.lower(), r"\b(?:cannon|artillery|gun barrel|mechanical)\b")
        self.assertIn("cannon", compact_negative)
        self.assertIn("gun barrel", compact_negative)

    def test_flux2_klein_ondal_ep17_chalice_becomes_bronze_cup(self):
        source = (
            "Global visual world: Time range: 590year; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Year/period: 590 AD; "
            "Scene: A golden chalice spilling dark red blood onto a pristine white cloth; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Goguryeo bronze cup and hemp-cloth aftermath", compact)
        self.assertIn("plain bronze ritual cup", compact)
        self.assertNotIn("golden chalice", compact.lower())
        self.assertIn("European goblet", compact_negative)

    def test_flux2_klein_20th_century_science_blocks_medieval_contamination(self):
        source = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Main subject: A vintage 1920s laboratory filled with glowing glass flasks and complex brass instruments; "
            "Scene: Midgley arranging blank parchment complex chemical equations furiously on a large, dusty chalkboard; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("1920s-1940s United States science", compact)
        self.assertIn("blank erased dark slate board", compact)
        self.assertIn("unlabeled glassware", compact)
        self.assertNotRegex(compact.lower(), r"\b(?:spear|swords?|shield|knight|medieval armor|satellite|spaceship)\b")
        self.assertNotIn("complex chemical equations", compact.lower())
        self.assertIn("medieval armor", compact_negative)
        self.assertIn("chalkboard equations", compact_negative)
        self.assertIn("satellite", compact_negative)

    def test_flux2_klein_20th_century_science_replaces_symbolic_surfaces(self):
        source = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Main subject: A view of the Earth from space, with a sickly, unnatural green haze covering the atmosphere; "
            "Scene: A shadowed portrait of a distinguished man in a 1920s suit, surrounded by chemical formulas floating in the air; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("period laboratory globe", compact)
        self.assertIn("glassware reflections", compact)
        self.assertNotIn("Earth from space", compact)
        self.assertNotIn("chemical formulas", compact.lower())
        self.assertNotIn("floating in the air", compact.lower())
        self.assertIn("hologram", compact_negative)
        self.assertIn("open notebook", compact_negative)

    def test_flux2_klein_20th_century_science_keeps_street_car_as_period_exterior(self):
        source = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Main subject: A skull and crossbones subtly forming in the exhaust fumes of a speeding car; "
            "Scene: A skull and crossbones subtly forming in the exhaust fumes of a speeding car; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("outdoor street documentary scene", compact)
        self.assertIn("dark irregular exhaust fumes", compact)
        self.assertNotIn("skull and crossbones", compact.lower())
        self.assertNotIn("storefront", compact.lower())
        self.assertTrue(compact_negative.startswith("readable storefront sign"))
        self.assertIn("skull and crossbones", compact_negative)
        self.assertIn("hazard symbol", compact_negative)

    def test_flux2_klein_20th_century_science_replaces_giant_brain_diagram(self):
        source = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Main subject: An anatomical illustration of a human brain surrounded by dark, corrosive veins; "
            "Scene: An anatomical illustration of a human brain surrounded by dark, corrosive veins; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("cloth-covered anatomical teaching model", compact)
        self.assertNotIn("anatomical illustration", compact.lower())
        self.assertNotIn("giant brain", compact.lower())
        self.assertIn("giant brain", compact_negative)

    def test_flux2_klein_20th_century_science_does_not_capture_russia_teaser(self):
        source = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Main subject: The majestic, snowy domes of a Russian palace under a cold night sky; "
            "Scene: Into the heart of the collapsing Romanov Dynasty in Imperial Russia; "
            "Style: serious adult graphic novel illustration"
        )
        compact, _ = _compact_flux2_klein_4b_prompt(source, "")

        self.assertNotIn("1920s-1940s United States science", compact)
        self.assertNotIn("laboratory bench", compact.lower())

    def test_flux2_klein_imperial_russia_positive_avoids_prompted_text_traps(self):
        cases = (
            (
                "A magnificent, majestic Russian imperial palace covered in deep winter snow, dark storm clouds gathering above",
                "wide outdoor Russian imperial palace exterior",
            ),
            (
                "A grand wooden table covered in complex military maps and strategic compasses",
                "top-down macro view of one rough wooden strategy table",
            ),
            (
                "A dark, shadowy silhouette of a tall man in a peasant robe standing ominously in a lavish royal hallway",
                "one tall black-robed bearded silhouette centered",
            ),
            (
                "A close-up of a man's piercing, hypnotic eyes opening suddenly in the pitch black darkness",
                "extreme close-up of one bearded male face",
            ),
            (
                "A group of wealthy, aristocratic men in heavy winter coats whispering deadly secrets in a dim, candlelit room",
                "extreme close cluster of wealthy aristocratic men",
            ),
            (
                "A filthy, bearded peasant standing confidently next to a royal throne, casting a dark shadow over it",
                "extreme upper-body crop of one single bearded peasant mystic",
            ),
            (
                "A spinning vintage globe made of brass and dark wood, focusing on Eastern Europe and Russia, moody lighting",
                "top-down macro view of one rough wooden strategy table",
            ),
            (
                "The majestic double-headed eagle crest of the Russian Empire shining in gold, slightly tarnished",
                "top-down macro view of one flat tarnished metal double-headed eagle relief",
            ),
            (
                "A silver tray holding a glass of dark red wine and sweet pastries, glowing with a faint, toxic green aura",
                "one plain wine glass of dark red wine",
            ),
            (
                "A medical kit from the 1910s sitting uselessly on a table next to a royal bed",
                "dark leather 1910s doctor's bag",
            ),
            (
                "A skull and crossbones subtly reflected in the polished glass of the poison vial",
                "extreme macro close-up of one polished glass poison vial",
            ),
            (
                "A grim, devastating trench warfare scene, soldiers freezing in the mud, artillery explosions in the distance",
                "grim outdoor trench warfare with Russian soldiers",
            ),
            (
                "The Tsar in military uniform riding a horse away from the palace, waving goodbye",
                "outdoor snowy palace departure with one mounted Tsar",
            ),
            (
                "A stylized 3D thumbs-up icon made of antique Russian silver, glowing softly against a dark background",
                "macro tabletop close-up of one antique Russian silver hand-shaped statuette",
            ),
        )
        forbidden_positive = (
            r"\b(?:no|zero|not|letters?|labels?|numbers?|poster|posters|"
            r"charts?|diagrams?|documents?|map|maps|globe|green|plaque|"
            r"switch|outlet|wall\s+plate)\b"
        )
        for scene, expected in cases:
            with self.subTest(scene=scene):
                source = (
                    "Year/period: 1916 AD; Exact place: Petrograd (Russian Empire); "
                    f"Main subject: {scene}; Scene: {scene}; "
                    "Style: serious adult graphic novel illustration"
                )
                compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

                self.assertIn(expected, compact)
                self.assertNotRegex(compact.lower(), forbidden_positive)
                self.assertNotIn("candle sconce", compact.lower())
                self.assertNotIn("background walls", compact.lower())
                if expected == "wide outdoor Russian imperial palace exterior":
                    self.assertNotIn("wine glasses", compact.lower())
                    self.assertNotIn("cellar", compact.lower())
                self.assertIn("wall switch", compact_negative)
                self.assertIn("framed wall picture", compact_negative)
                self.assertIn("green poison glow", compact_negative)
                self.assertIn("gray square wall plate", compact_negative)
                self.assertIn("machine-flat wall rectangle", compact_negative)
                self.assertIn("wall sconce base plate", compact_negative)
                if expected == "top-down macro view of one rough wooden strategy table":
                    self.assertIn("background wall", compact_negative)
                    self.assertIn("full room perspective", compact_negative)
                    self.assertIn("paper sheet on strategy table", compact_negative)
                    self.assertNotIn("paper", compact.lower())
                    self.assertNotIn("packet", compact.lower())
                if expected == "one tall black-robed bearded silhouette centered":
                    self.assertIn("wall switch in corridor", compact_negative)
                    self.assertIn("pure black Romanov interior shadow", compact)
                if expected == "top-down macro view of one flat tarnished metal double-headed eagle relief":
                    self.assertIn("wall plate behind eagle", compact_negative)
                    self.assertIn("eagle mounted on wall", compact_negative)
                if expected == "extreme close-up of one bearded male face":
                    self.assertIn("wall switch behind face", compact_negative)
                if expected == "extreme macro close-up of one polished glass poison vial":
                    self.assertIn("tiny distorted reflection inside the glass surface", compact)
                    self.assertIn("skull on wall", compact_negative)
                    self.assertIn("skull in window", compact_negative)
                    self.assertIn("wall switch beside vial", compact_negative)
                    self.assertIn("All four image edges are glass", compact)
                if expected == "grim outdoor trench warfare with Russian soldiers":
                    self.assertIn("Outdoor 1916 Eastern Front trench battlefield scene", compact)
                    self.assertIn("indoor room for trench scene", compact_negative)
                    self.assertIn("East Asian room", compact_negative)
                    self.assertIn("Image edges stay outdoor battlefield terrain", compact)
                if expected == "outdoor snowy palace departure with one mounted Tsar":
                    self.assertIn("Outdoor Russian imperial palace departure scene", compact)
                    self.assertIn("horse inside room", compact_negative)
                    self.assertIn("wall behind horse", compact_negative)
                    self.assertIn("The horse, rider, snow-covered courtyard", compact)
                if expected == "macro tabletop close-up of one antique Russian silver hand-shaped statuette":
                    self.assertIn("Object-only Romanov silver approving-hand statuette scene", compact)
                    self.assertIn("triangular pyramid", compact_negative)
                    self.assertIn("geometric wedge", compact_negative)
                    self.assertIn("All four image edges are tabletop", compact)
                if expected == "extreme close cluster of wealthy aristocratic men":
                    self.assertIn("wall switch behind group", compact_negative)
                    self.assertIn("door behind group", compact_negative)
                    self.assertIn("architectural background behind group", compact_negative)
                    self.assertIn("doorframe beside group", compact_negative)
                    self.assertIn("The whole 16:9 frame is filled edge to edge", compact)
                    self.assertIn("black smoke and darkness", compact)
                    self.assertNotIn("rough doors", compact.lower())
                    self.assertNotIn("window openings", compact.lower())
                if expected == "extreme upper-body crop of one single bearded peasant mystic":
                    self.assertIn("wall plate beside throne", compact_negative)
                    self.assertIn("doorframe beside throne", compact_negative)
                    self.assertIn("architectural background beside throne", compact_negative)
                    self.assertIn("empty high dark carved wooden throne back", compact)
                    self.assertIn("Rasputin remains the only human figure", compact)
                    self.assertIn("seated figure on throne", compact_negative)
                    self.assertIn("duplicate Rasputin", compact_negative)
                    self.assertIn("full body Rasputin", compact_negative)
                    self.assertIn("small square plate lower left of throne", compact_negative)
                    self.assertIn("Lower body, floor, and open room stay outside the crop", compact)
                    self.assertIn("cropped into empty throne wood and darkness", compact)
                    self.assertNotIn("rough doors", compact.lower())
                    self.assertNotIn("window openings", compact.lower())

    def test_flux2_klein_imperial_russia_generic_rooms_avoid_wall_mounted_lights(self):
        source = (
            "Year/period: 1916 AD; Exact place: Petrograd (Russian Empire); "
            "Main subject: Russian officials gathering in a cellar room under candlelight; "
            "Scene: Russian officials gathering in a cellar room under candlelight; "
            "Style: serious adult graphic novel illustration"
        )
        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("tabletop candles, low floor candles, handheld lanterns", compact)
        self.assertIn("Interior lighting comes from tabletop candles", compact)
        self.assertIn("fixtureless cracked plaster", compact)
        self.assertNotIn("oil-lamp light", compact.lower())
        self.assertIn("wall-mounted candle", compact_negative)
        self.assertIn("wall candle holder", compact_negative)
        self.assertIn("wall bracket lamp", compact_negative)
        self.assertIn("round wall plate", compact_negative)
        self.assertIn("mounted light source", compact_negative)

    def test_flux2_klein_compacts_ep13_wa_rout_as_discarded_weapons_foreground(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: Wa soldiers dropping their swords and running away in absolute terror; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, compact_negative = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Wa rout scene", compact)
        self.assertIn("building-free open mud", compact)
        self.assertIn("Discarded short swords", compact)
        self.assertIn("empty sleeve-covered arms", compact)
        self.assertIn("tiled temple roof", compact_negative)
        self.assertIn("ornate curved palace roof", compact_negative)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_compacts_ep13_gaya_siege_as_earth_timber_fieldstone(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: a massive stone fortress in the Gaya region falling under a relentless siege; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, compact_negative = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Gaya-region fortified settlement under siege", compact)
        self.assertIn("packed-earth ramparts", compact)
        self.assertIn("rough fieldstone bases", compact)
        self.assertIn("low rough timber palisade", compact)
        self.assertIn("European castle", compact_negative)
        self.assertIn("stone keep", compact_negative)
        self.assertIn("wall plaque", compact_negative)
        self.assertIn("artist signature", compact_negative)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_compacts_ep13_shattered_shield_not_submission_still_life(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: a wooden shield with enemy crests shattered into splinters; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, compact_negative = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Object-only shattered enemy shield evidence", compact)
        self.assertIn("plain round wooden shield", compact)
        self.assertIn("abstract scratched shapes", compact)
        self.assertNotIn("Symbolic submission still life", compact)
        self.assertIn("European heraldry", compact_negative)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_compacts_ep13_burning_banners_as_unmarked_cloth(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: enemy banners burning together in a massive, chaotic bonfire; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, compact_negative = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Ground-level enemy standards burned after battle", compact)
        self.assertIn("collapsed unmarked soot-black cloth strips", compact)
        self.assertIn("plain torn fabric", compact)
        self.assertIn("characters on banners", compact_negative)
        self.assertIn("written flag", compact_negative)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_compacts_ep13_victory_ridge_blocks_speech_bubbles(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: Goguryeo soldiers standing victorious on a cliff overlooking a valley; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, compact_negative = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Textless Goguryeo victory ridge scene", compact)
        self.assertIn("empty storm sky", compact)
        self.assertIn("speech bubble", compact_negative)
        self.assertIn("dialogue box", compact_negative)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_compacts_ep13_rescued_capital_flag_not_submission_token(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: a giant Goguryeo flag waving proudly above the rescued Silla capital; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, _ = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Rescued Silla capital under Goguryeo protection", compact)
        self.assertIn("large blank dark cloth flag", compact)
        self.assertIn("packed-earth ramparts", compact)
        self.assertNotIn("Symbolic submission still life", compact)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_compacts_ep13_scale_as_bronze_balance_not_crown_only(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: a golden scale weighing a sword on one side and a crown on the other; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, compact_negative = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Object-only political cost still life", compact)
        self.assertIn("rough horizontal wooden branch", compact)
        self.assertIn("two short timber posts", compact)
        self.assertIn("one short straight iron blade", compact)
        self.assertIn("one small early Silla crown fragment", compact)
        self.assertNotIn("Object-only still life. A fragile early Silla gold crown fragment", compact)
        self.assertIn("modern justice scale", compact_negative)
        self.assertIn("pedestal scale", compact_negative)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_compacts_ep13_occupation_camp_without_palace_roof(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: Goguryeo tents permanently set up right next to the Silla royal palace; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, compact_negative = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Goguryeo occupation camp beside the Silla ruler's compound", compact)
        self.assertIn("low thatched timber command hall", compact)
        self.assertIn("packed-earth courtyard", compact)
        self.assertIn("tiled palace roof", compact_negative)
        self.assertIn("curved tiled eaves", compact_negative)
        self.assertIn("hanok palace", compact_negative)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_compacts_ep13_naemul_despair_with_closed_sleeves(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: King Naemul sitting in the dark, his face covered by his hands; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, _ = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("King Naemul despair scene", compact)
        self.assertIn("face half hidden behind wide folded sleeves", compact)
        self.assertIn("Closed sleeves", compact)
        self.assertNotRegex(compact, r"\bhand\w*\b|\bfinger\w*\b")
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_compacts_ep13_tiger_as_shadow_only(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: a monstrous shadow of a tiger lurking behind the Silla throne; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, compact_negative = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Shadow-only political danger scene", compact)
        self.assertIn("single black tiger-shaped shadow silhouette", compact)
        self.assertIn("empty low wooden command dais", compact)
        self.assertIn("real tiger", compact_negative)
        self.assertIn("animal body", compact_negative)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_compacts_ep13_court_whisper_as_two_figure_hall_scene(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: a Goguryeo official whispering dictatorial orders into the king's ear; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, _ = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Court interference scene", compact)
        self.assertIn("One Goguryeo steward", compact)
        self.assertIn("seated Silla ruler", compact)
        self.assertIn("Closed sleeve folds", compact)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_compacts_ep13_succession_board_without_chess_or_hands(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: a hand moving a chess piece, knocking over a Silla royal figure; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, _ = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Object-only succession manipulation board", compact)
        self.assertIn("Smooth unmarked clay counters", compact)
        self.assertIn("plain wooden peg markers", compact)
        self.assertIn("one toppled Silla royal marker", compact)
        self.assertNotIn("chess", compact.lower())
        self.assertNotRegex(compact, r"\bhand\w*\b|\bfinger\w*\b")
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_compacts_ep13_silla_hostage_march_with_closed_sleeves(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: young Silla royals tied with thick ropes being marched away; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, _ = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Hostage march scene", compact)
        self.assertIn("Three to five young Silla royals", compact)
        self.assertIn("rope loops around sleeves and waists", compact)
        self.assertIn("Closed sleeves", compact)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_compacts_ep13_bokho_hostage_cart_as_rough_wood(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: another young prince, Bokho, being forced into a dark wooden carriage; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, _ = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Prince Bokho hostage cart scene", compact)
        self.assertIn("rough wooden hostage cart", compact)
        self.assertIn("solid wooden wheels", compact)
        self.assertIn("closed sleeves", compact.lower())
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_compacts_ep13_chained_wrists_as_restraint_evidence(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: chained wrists resting heavily on a cold stone floor; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, _ = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Object-only hostage restraint evidence", compact)
        self.assertIn("Heavy dark iron chain", compact)
        self.assertIn("torn sleeve cloth scraps", compact)
        self.assertIn("human-free", compact)
        self.assertNotRegex(compact, r"\bhand\w*\b|\bfinger\w*\b")
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_compacts_ep13_iron_wall_as_lamellar_survival_metaphor(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: a fragile flower growing out of a crack in a massive iron wall; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        compact, _ = _compact_flux2_klein_4b_prompt(comfy_prompt, comfy_negative)

        self.assertIn("Object-only survival metaphor", compact)
        self.assertIn("dark dull iron lamellar plates", compact)
        self.assertIn("tiny pale wildflower", compact)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_compacts_ep13_actual_korean_script_cuts_55_to_60(self):
        cases = (
            (
                "이 자가 신라 18대 실성왕입니다. 철저한 고구려의 꼭두각시였죠.",
                ("Puppet-king throne scene", "One King Silseong", "closed sleeves"),
            ),
            (
                "실성왕 역시 고구려의 비위를 맞추려 뼈를 깎는 희생을 치릅니다.",
                ("Forced submission court scene", "One Silla king", "three stern Goguryeo officials"),
            ),
            (
                "412년, 내물왕의 아들 복호마저 고구려 볼모로 바쳐지게 됩니다.",
                ("Prince Bokho hostage cart scene", "rough wooden hostage cart", "solid wooden wheels"),
            ),
            (
                "최고위 왕족들이 대국의 짐승 같은 인질로 전락하는 비참한 현실.",
                ("Object-only hostage restraint evidence", "Heavy dark iron chain", "human-free"),
            ),
            (
                "그것이 위태로운 왕조의 명맥을 잇기 위한 유일한 생존법이었죠.",
                ("Object-only survival metaphor", "tiny pale wildflower", "dark dull iron lamellar plates"),
            ),
            (
                "신라는 고구려 황제를 섬기는 철저한 하위 제후국으로 편입된 겁니다.",
                ("Winter vassal submission scene", "one Goguryeo officer", "kneels deeply"),
            ),
        )

        for source, expected_parts in cases:
            with self.subTest(source=source):
                compact, _ = _compact_flux2_klein_4b_prompt(source, "")
                for expected in expected_parts:
                    self.assertIn(expected, compact)
                self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")

    def test_flux2_klein_compacts_ep13_cuts_61_to_66_excavation_sequence(self):
        cases = (
            (
                "Scene: a dark storm cloud hovering permanently over the Silla capital",
                ("Silla subordination under Goguryeo protection", "blank dark Goguryeo military standard", "coercive pressure"),
            ),
            (
                "Scene: a shovel digging into ancient, layered dirt in a dark trench",
                ("Object-only archaeological soil proof", "buried bronze artifact", "human-free"),
            ),
            (
                "Scene: archaeologists carefully brushing dirt off an ancient stone structure",
                ("1946 post-liberation Gyeongju Noseo-dong tomb excavation", "plain blank cloth bundles", "clear open sky above the roofline"),
            ),
            (
                "Scene: a ruined ancient burial mound with old houses built right next to it",
                ("1946 Gyeongju damaged tomb mound", "old Korean private houses", "hand-dug excavation trench"),
            ),
            (
                "Scene: a dark wooden chamber being opened, revealing a faint metallic gleam",
                ("1946 Gyeongju tomb chamber opening", "heavy rough planks", "faint bronze gleam"),
            ),
            (
                "Scene: an ancient bronze bowl resting neatly on a dark velvet-like soil surface",
                ("Object-only fifth-century Silla tomb artifact", "heavy ancient bronze cauldron", "human-free"),
            ),
        )

        for source, expected_parts in cases:
            with self.subTest(source=source):
                compact, _ = _compact_flux2_klein_4b_prompt(source, "")
                for expected in expected_parts:
                    self.assertIn(expected, compact)
                self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
                self.assertNotIn("literal umbrella", compact.lower())

    def test_flux2_klein_compacts_ep13_cuts_67_to_72_hou_inscription_sequence(self):
        cases = (
            (
                "Scene: highly detailed close-up of the weathered, greenish-bronze vessel lid",
                ("Object-only Ho-u bronze vessel lid close-up", "weathered bronze lid", "artifact-only"),
            ),
            (
                "Scene: a scholar's eyes widening in absolute shock under the dim lantern light",
                ("1946 Gyeongju excavation discovery reaction", "1940s cotton jacket", "brow to shoulders only"),
            ),
            (
                "Scene: extreme close-up of engraved Chinese characters on the bottom of the bowl",
                ("Object-only Ho-u bronze underside evidence", "sixteen small plain blank raised rectangular cells", "four columns across and four rows down"),
            ),
            (
                "Scene: the specific ancient characters glowing faintly in the dark",
                ("Object-only Ho-u vessel underside evidence", "sixteen small plain blank raised rectangular cells", "four columns across and four rows down"),
            ),
            (
                "Scene: a ghostly vision of Gwanggaeto the Great towering over the bronze bowl",
                ("Symbolic memorial scene for King Gwanggaeto", "wall-shadow-only memorial outline", "one head"),
            ),
            (
                "Scene: a map of Silla catching fire, revealing the name of the Goguryeo King",
                ("Object-only Silla tomb discovery shock", "Goguryeo military standard shadow", "map-free tomb chamber"),
            ),
        )

        for source, expected_parts in cases:
            with self.subTest(source=source):
                compact, neg = _compact_flux2_klein_4b_prompt(source, "")
                for expected in expected_parts:
                    self.assertIn(expected, compact)
                self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
                self.assertNotIn("map of Silla", compact)
                if "inscription" in compact:
                    self.assertIn("Chinese characters", neg)
                    self.assertIn("engraved characters", neg)
                    self.assertIn("modern printed text", neg)
                    self.assertIn("readable inscription", neg)
                if "Ho-u bronze underside evidence" in compact or "Ho-u vessel underside evidence" in compact:
                    self.assertIn("2x2 grid", neg)
                self.assertNotIn("Chinese inscription", compact)
                self.assertNotIn("seal-script", compact)
                self.assertNotIn("characters", compact)

    def test_flux2_klein_compacts_ep13_hou_sequence_after_intermediate_prompt_rewrites(self):
        cases = (
            (
                (
                    "Scene: extreme close-up of engraved Chinese characters on the bottom of the bowl\n"
                    "Visible action: bronze bowl evidence on dark table"
                ),
                ("Object-only Ho-u bronze underside evidence", "sixteen small plain blank raised rectangular cells"),
                ("people", "table", "horse"),
            ),
            (
                (
                    "Scene: a ghostly vision of Gwanggaeto the Great towering over the bronze bowl\n"
                    "Visible action: bronze bowl evidence on dark table"
                ),
                ("Symbolic memorial scene for King Gwanggaeto", "wall-shadow-only memorial outline"),
                ("group around bowl", "signboard in sky", "boat"),
            ),
            (
                (
                    "Scene: a map of Silla catching fire, revealing the name of the Goguryeo King\n"
                    "Visible action: a low horizontal tactile marker layout for Silla catching fire with loose route cords"
                ),
                ("Object-only Silla tomb discovery shock", "map-free tomb chamber"),
                ("open fire", "English letters on ground", "people around fire"),
            ),
        )

        for source, expected_prompt_parts, expected_negative_parts in cases:
            with self.subTest(source=source):
                prompt = (
                    "Year/period: 400-415 CE; "
                    "Exact place: Silla Jongbalseong fortress area; "
                    "Culture scope: Goguryeo and Silla ancient Northeast Asian political world; "
                    f"{source}"
                )
                compact, neg = _compact_flux2_klein_4b_prompt(prompt, "")
                for expected in expected_prompt_parts:
                    self.assertIn(expected, compact)
                for expected in expected_negative_parts:
                    self.assertIn(expected, neg)

    def test_flux2_klein_compacts_ep13_cuts_73_to_78_no_text_or_symbols(self):
        cases = (
            (
                "이 놀라운 청동 그릇 때문에 이 무덤은 '호우총'이라 불리게 됩니다.\n"
                "Scene: the bronze bowl sitting prominently on a museum display stand",
                ("Object-only Ho-u tomb naming artifact", "heavy ancient bronze cauldron vessel", "display-free"),
                ("museum display stand", "question mark", "Chinese characters"),
            ),
            (
                "경주 한복판에서 왜 대국 고구려 황제의 유물이 당당히 나온 걸까요?\n"
                "Scene: a question mark hovering over the ancient bowl in the shadows",
                ("Gyeongju tomb artifact evidence scene", "large blank Goguryeo military standard shadow", "place evidence"),
                ("question mark", "floating symbol", "museum display stand"),
            ),
            (
                "그 서늘한 비밀의 열쇠는 글귀 시작인 '을묘년'이란 시기에 있습니다.\n"
                "Scene: the specific ancient characters glowing faintly in the dark",
                ("Object-only Ho-u vessel underside evidence", "sixteen small plain blank raised rectangular cells", "bronze-surface-only"),
                ("characters glowing", "Chinese characters", "seal-script"),
            ),
            (
                "광개토대왕을 장사 지낸 다음 해인 서기 415년이 바로 을묘년이죠.\n"
                "Scene: the specific ancient characters glowing faintly in the dark",
                ("Early fifth-century Gungnaeseong royal memorial aftermath", "royal tomb mound", "ritual bronze vessels"),
                ("specific ancient characters", "Chinese characters", "written dates"),
            ),
            (
                "Scene: a calendar-like stone carving focusing on the characters 'Eulmyo year name'",
                ("Object-only Ho-u time clue evidence", "first blank raised cell", "four columns across and four rows down"),
                ("calendar-like stone carving", "characters", "Eulmyo year name"),
            ),
            (
                "Scene: a massive stone tomb being sealed under a dark, snowy sky",
                ("Early fifth-century Gungnaeseong royal memorial aftermath", "royal tomb mound", "torch smoke"),
                ("massive stone tomb being sealed", "date numbers", "written dates"),
            ),
            (
                "415년 국내성에서는 대왕의 업적을 기리는 거대한 제사가 열립니다.\n"
                "Scene: a grand memorial ceremony with thousands of torches in the Goguryeo capital",
                ("Early fifth-century Gungnaeseong royal memorial rite", "ritual bronze vessels", "closed sleeves"),
                ("thousands of torches", "readable writing", "banner characters"),
            ),
            (
                "신라 왕실은 상국의 장례를 애도하려 공식 사절단을 대거 파견합니다.\n"
                "Scene: Silla envoys dressed in mourning clothes marching solemnly in a long line",
                ("Silla mourning envoy procession to Goguryeo", "walk on foot", "wide sleeves folded shut"),
                ("horse", "mounted rider", "flag characters"),
            ),
        )

        for source, expected_prompt_parts, forbidden_prompt_parts in cases:
            with self.subTest(source=source):
                compact, neg = _compact_flux2_klein_4b_prompt(source, "")
                for expected in expected_prompt_parts:
                    self.assertIn(expected, compact)
                for forbidden in forbidden_prompt_parts:
                    self.assertNotIn(forbidden, compact)
                self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
                self.assertNotIn("question mark", compact)
                self.assertNotIn("drawn symbols", compact)
                self.assertIn("question mark", neg)
                self.assertIn("visible writing", neg)

    def test_flux2_klein_compacts_ep13_cuts_83_to_84_as_textless_bronze_material(self):
        cases = (
            (
                "그릇 상단 중앙에 깊게 새겨진 샵 기호 모양의 '우물 정' 자 주술 표식.\n"
                "Scene: a macro shot of the '#' like symbol carved sharply into the bronze",
                ("Object-only bronze crossing-groove evidence", "bronze-surface-only", "groove bands"),
            ),
            (
                "잡귀를 쫓거나 천손을 상징하는 대국 고구려만의 특별한 기호입니다.\n"
                "Scene: a mystical aura or faint smoke rising from the carved symbol",
                ("Object-only bronze ritual vapor evidence", "irregular vapor wisps", "chamber-object-only"),
            ),
        )

        for source, expected_prompt_parts in cases:
            with self.subTest(source=source):
                compact, neg = _compact_flux2_klein_4b_prompt(source, "")
                for expected in expected_prompt_parts:
                    self.assertIn(expected, compact)
                self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
                self.assertNotIn("#", compact)
                self.assertNotIn("hash", compact.lower())
                self.assertNotIn("characters", compact)
                self.assertIn("hash sign", neg)
                self.assertIn("signboard", neg)
                self.assertIn("smoke glyph", neg)

    def test_flux2_klein_compacts_ep13_cuts_80_to_82_single_bowl_and_horse_inventory(self):
        cases = (
            (
                "Scene: a Goguryeo noble handing the bronze bowl to a bowing Silla envoy",
                ("Two-person single-bowl ceremonial handoff", "single shared object", "sleeve-covered hands"),
                ("second bowl", "horses in handoff scene"),
            ),
            (
                "Scene: the bowl resting heavily in the Silla envoy's trembling hands",
                ("Tight single-bowl envoy burden crop", "one bronze cauldron", "one pair of hands"),
                ("duplicate cauldron", "extra hands"),
            ),
            (
                "Visible action: the bowl resting heavily in the Silla envoy's trembling sleeve-covered arm gesture",
                ("Tight single-bowl envoy burden crop", "one bronze cauldron", "one pair of hands"),
                ("hanging plaque", "wall writing"),
            ),
            (
                "Scene: the envoy riding a horse back south, guarding the bowl carefully",
                ("Single mounted bowl return scene", "one complete dark horse", "one head, one neck, one torso, four legs"),
                ("second horse", "horse with two bodies"),
            ),
        )

        for source, expected_prompt_parts, expected_negative_parts in cases:
            with self.subTest(source=source):
                prompt = (
                    "Year/period: 400-415 CE; "
                    "Exact place: Silla Jongbalseong fortress area; "
                    "Culture scope: Goguryeo and Silla ancient Northeast Asian political world; "
                    f"{source}"
                )
                compact, neg = _compact_flux2_klein_4b_prompt(prompt, "")
                for expected in expected_prompt_parts:
                    self.assertIn(expected, compact)
                for expected in expected_negative_parts:
                    self.assertIn(expected, neg)
                self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
                self.assertNotIn("duplicate bowl", compact)

    def test_flux2_klein_compacts_ep13_cuts_86_and_90_remove_captions_and_wall_text(self):
        cases = (
            (
                "Scene: a Silla noble looking at the bowl with deep reverence and fear",
                ("Single-noble bronze reverence scene", "one heavy bronze cauldron", "blank rough timber wall"),
            ),
            (
                "Scene: the bronze bowl being carefully placed next to a deceased body in a tomb",
                ("Tomb burial placement evidence", "one deceased body", "one bronze cauldron"),
            ),
        )

        for source, expected_prompt_parts in cases:
            with self.subTest(source=source):
                compact, neg = _compact_flux2_klein_4b_prompt(source, "")
                for expected in expected_prompt_parts:
                    self.assertIn(expected, compact)
                self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
                self.assertNotIn("caption", compact.lower())
                self.assertNotIn("wall writing", compact.lower())
                self.assertIn("white caption strip", neg)
                self.assertIn("wall writing", neg)
                self.assertIn("vertical sign", neg)

    def test_flux2_klein_compacts_ep13_cuts_91_to_96_textless_symbolic_evidence(self):
        cases = (
            (
                "Scene: the bowl completely covered in dust, sitting alone in absolute darkness",
                ("Dust-covered bronze bowl solitude", "one heavy bronze cauldron", "Object-only"),
            ),
            (
                "Scene: a drop of blood falling onto the cold bronze surface of the bowl",
                ("Blood drop on bronze surface", "single dark red drop", "object-only macro"),
            ),
            (
                "Scene: a massive shadow of a king on horseback falling over the continent of Asia",
                ("Horseback dominance shadow scene", "one complete horse", "rough short fence posts"),
            ),
            (
                "Scene: two smaller kings bowing so deeply their foreheads touch the dirt",
                ("Subordinate kings bowing scene", "foreheads close to the ground", "wide sleeves"),
            ),
            (
                "Scene: the Chinese characters 'Yeongnak era name' carved deeply and forcefully into solid rock",
                ("Blank royal-era stone evidence", "blank chiseled rectangular recess", "rock wall surface reaches every image edge"),
            ),
            (
                "Scene: a giant iron boot stepping heavily on a small, fragile wooden shield",
                ("Period pressure greave evidence", "dull iron lamellar shin guards", "fragile round wooden shield disk"),
            ),
        )

        for source, expected_prompt_parts in cases:
            with self.subTest(source=source):
                compact, neg = _compact_flux2_klein_4b_prompt(source, "")
                for expected in expected_prompt_parts:
                    self.assertIn(expected, compact)
                self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
                self.assertNotIn("Chinese characters", compact)
                self.assertNotIn("Yeongnak", compact)
                self.assertNotIn("caption", compact.lower())
                self.assertIn("white caption strip", neg)
                self.assertIn("rock inscription", neg)
                self.assertIn("modern boot", neg)

    def test_flux2_klein_compacts_ep13_cuts_98_to_100_remove_captions_text_and_keep_ornament(self):
        cases = (
            (
                "Scene: a Goguryeo soldier kicking over a Silla merchant's stall in the street",
                ("Occupation street stall abuse scene", "half-overturned", "unmarked stall cloth"),
                ("white caption strip", "signboard", "upright intact stall"),
            ),
            (
                "Scene: Silla citizens hiding in an alley, covering their mouths in fear",
                ("Silla alley fear scene", "covering their mouths", "large unbroken blank earthen wall planes"),
                ("wall plaque", "Korean text", "small square wall mark"),
            ),
            (
                "Scene: a heavy, rusty iron chain binding a beautiful Silla royal ornament",
                (
                    "Chained Silla ornament still life",
                    "Object-only",
                    "one heavy rusty iron chain",
                    "one small early Silla gold",
                ),
                ("person holding chain", "missing royal ornament"),
            ),
        )

        for source, expected_prompt_parts, expected_negative_parts in cases:
            with self.subTest(source=source):
                prompt = (
                    "Year/period: 400-415 CE; "
                    "Exact place: Silla Jongbalseong fortress area; "
                    "Culture scope: Goguryeo and Silla ancient Northeast Asian political world; "
                    f"{source}"
                )
                compact, neg = _compact_flux2_klein_4b_prompt(prompt, "")
                for expected in expected_prompt_parts:
                    self.assertIn(expected, compact)
                self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
                self.assertNotIn("caption", compact.lower())
                self.assertNotIn("signboard", compact.lower())
                for expected in expected_negative_parts:
                    self.assertIn(expected, neg)

    def test_flux2_klein_compacts_ep13_cut_102_blacksmith_is_full_bleed_single_worker(self):
        compact, neg = _compact_flux2_klein_4b_prompt(
            "Scene: a blacksmith silently sharpening a long sword on a grinding stone, sparks flying",
            "",
        )

        self.assertIn("Full-bleed blacksmith sharpening workshop", compact)
        self.assertIn("exactly one ancient Korean blacksmith", compact)
        self.assertIn("One short straight iron blade", compact)
        self.assertIn("two visible hands only", compact)
        self.assertIn("image reaches every edge", compact)
        self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
        self.assertIn("white border", neg)
        self.assertIn("second blacksmith", neg)
        self.assertIn("background boat", neg)

    def test_flux2_klein_compacts_ep13_cuts_103_106_107_108_are_textless_and_period_correct(self):
        cases = (
            (
                "Scene: a Silla official carefully sketching a Goguryeo weapon in a hidden scroll",
                ("Object-only hidden weapon study table", "leaf-shaped iron spearhead", "clean blank fiber"),
                ("symbol rows", "wall scroll", "cruciform hilt"),
            ),
            (
                "Scene: an arrogant Goguryeo general laughing, holding a cup of wine",
                ("Arrogant Goguryeo general drinking scene", "small plain bronze wine cup", "plain unmarked cloth cap"),
                ("glass cup", "hat emblem"),
            ),
            (
                "Scene: dark, thorny vines creeping tightly around the borders of a map",
                ("Textless thorn-vine control board", "loose rope route cords", "plain and unmarked"),
                ("map labels", "text grid"),
            ),
            (
                "Scene: a ripped treaty document lying next to a polished iron blade in the mud",
                ("Torn blank treaty bundle and iron blade still life", "Object-only", "rawhide cord"),
                ("wall plaque", "modern knife handle"),
            ),
        )

        for source, expected_prompt_parts, expected_negative_parts in cases:
            with self.subTest(source=source):
                compact, neg = _compact_flux2_klein_4b_prompt(source, "")
                for expected in expected_prompt_parts:
                    self.assertIn(expected, compact)
                self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
                self.assertNotIn("calligraphy", compact.lower())
                for expected in expected_negative_parts:
                    self.assertIn(expected, neg)

    def test_flux2_klein_compacts_ep13_cuts_109_111_113_are_full_bleed_and_not_european_castles(self):
        cases = (
            (
                "Scene: a massive stone tower starting to crack violently from the base up",
                ("Full-bleed ancient Korean fortress tower base fracture scene", "base height", "fill all four image edges"),
                ("arched stone gate", "crenellated battlement", "tower top"),
            ),
            (
                "Scene: a heavy, blood-stained wooden wheel rolling relentlessly over the ground",
                ("Full-bleed blood-stained cart wheel ground close-up", "One heavy spoked wooden cart wheel", "cut off by all four image edges"),
                ("modern wheel tire", "vertical wall sign", "comic panel border"),
            ),
            (
                "Scene: a pile of unnamed, broken helmets buried deep under the dark shadows",
                ("Object-only broken helmets under shadow", "Macro close-up", "borderless"),
                ("white border", "shelter frame", "black letterbox border"),
            ),
        )

        for source, expected_prompt_parts, expected_negative_parts in cases:
            with self.subTest(source=source):
                prompt = (
                    "Year/period: 400-415 CE; "
                    "Exact place: Silla Jongbalseong fortress area; "
                    "Culture scope: Goguryeo and Silla ancient Northeast Asian political world; "
                    f"{source}"
                )
                compact, neg = _compact_flux2_klein_4b_prompt(prompt, "")
                for expected in expected_prompt_parts:
                    self.assertIn(expected, compact)
                self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
                for expected in expected_negative_parts:
                    self.assertIn(expected, neg)

    def test_flux2_klein_compacts_ep13_cuts_115_116_120_use_period_weapons_and_textless_ledgers(self):
        cases = (
            (
                "Scene: countless armored hooves violently crushing the borders of neighboring kingdoms",
                ("Full-bleed mounted hooves crushing border markers", "six to eight separate ancient horse legs", "blank rope boundary line"),
                ("horse with two bodies", "tiled palace roof", "white border"),
            ),
            (
                "Scene: a hellish landscape of endless fire, clashing armies, and dark storm clouds",
                ("Ancient battle fire scene", "straight iron spears", "short straight iron blades only"),
                ("curved sword", "katana", "Japanese sword"),
            ),
            (
                "Scene: a strict royal inspector examining ledgers with a cold, unforgiving face",
                ("Textless royal ledger inspection scene", "blank cord-tied wooden tablet ledger bundle", "parallel wooden slats"),
                ("ledger text", "utility pole", "paper covered with writing"),
            ),
        )

        for source, expected_prompt_parts, expected_negative_parts in cases:
            with self.subTest(source=source):
                compact, neg = _compact_flux2_klein_4b_prompt(source, "")
                for expected in expected_prompt_parts:
                    self.assertIn(expected, compact)
                self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
                for expected in expected_negative_parts:
                    self.assertIn(expected, neg)

    def test_flux2_klein_compacts_ep13_cuts_122_to_126_remove_text_tags_frames_and_modern_light(self):
        cases = (
            (
                "Scene: a dark room with silhouettes of diplomats holding hidden knives",
                ("Dark knife diplomacy room", "one bronze oil lamp on the floor", "blank earthen walls"),
                ("vertical wall tag", "modern ceiling lamp"),
            ),
            (
                "Scene: a boot stepping on a fallen warrior's back in the freezing mud",
                ("Full-bleed fallen-warrior pressure macro", "fallen warrior's head, arms, and legs are outside", "borderless live crop"),
                ("gray outer margin", "black rectangular border"),
            ),
            (
                "Scene: a clean textbook page showing a majestic, glowing painting of the King",
                ("Object-only idealized king record bundle", "blank cord-tied cream document bundle", "bronze royal figurine"),
                ("portrait scroll", "headband emblem"),
            ),
            (
                "Scene: the textbook page quickly burning away to reveal a brutal reality",
                ("Object-only burning blank record bundle", "actively being consumed", "fire bites directly"),
                ("candle-only flame", "unburned document bundle"),
            ),
            (
                "Scene: a scholar carefully running his hand over a large, blood-stained stone stele",
                ("Tight blank stele blood-touch scene", "one dark red blood smear", "single hand touches the blood"),
                ("pouch writing", "jar markings"),
            ),
        )

        for source, expected_prompt_parts, expected_negative_parts in cases:
            with self.subTest(source=source):
                compact, neg = _compact_flux2_klein_4b_prompt(source, "")
                for expected in expected_prompt_parts:
                    self.assertIn(expected, compact)
                self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
                for expected in expected_negative_parts:
                    self.assertIn(expected, neg)

    def test_flux2_klein_compacts_ep13_cuts_127_128_129_130_132_remove_text_poles_frames_and_bad_animals(self):
        cases = (
            (
                "Scene: exhausted, starving conscripts dragging incredibly heavy supply wagons",
                ("Full-bleed starving supply wagon drag scene", "one heavy rough wooden supply cart", "soft roof smoke"),
                ("utility pole", "overhead wire", "chimney pipe"),
            ),
            (
                "Scene: chained prisoners walking endlessly under the cruel whips of guards",
                ("Full-bleed chained prisoner march scene", "one single chain line", "two Goguryeo guards"),
                ("wall text", "wall plaque", "extra hands"),
            ),
            (
                "Scene: a broken, muddy spear lying next to a fallen, anonymous soldier's body",
                ("Object-focused broken spear and fallen soldier evidence", "one detached leaf-shaped iron spearhead", "clear mud gap"),
                ("modern bulb", "double-ended spear", "second spearhead"),
            ),
            (
                "Scene: a bloody brush forcefully writing characters on a bamboo scroll",
                ("Object-only bloody brush and blank bamboo scroll evidence", "one blank bamboo slip scroll", "blood smear"),
                ("brush-written marks", "paper covered with writing", "glyph rows"),
            ),
            (
                "Scene: a pack of vicious wolves tearing apart their prey in the dark",
                ("Full-bleed bare wild wolf predation scene", "Three plain gray-brown wild wolves", "zero armor, zero saddle"),
                ("duplicate wolf head", "wolf with two bodies", "saddle on wolf"),
            ),
        )

        for source, expected_prompt_parts, expected_negative_parts in cases:
            with self.subTest(source=source):
                compact, neg = _compact_flux2_klein_4b_prompt(source, "")
                for expected in expected_prompt_parts:
                    self.assertIn(expected, compact)
                self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
                self.assertNotIn("wall text", compact.lower())
                self.assertNotIn("calligraphy", compact.lower())
                for expected in expected_negative_parts:
                    self.assertIn(expected, neg)

    def test_flux2_klein_compacts_ep13_cuts_133_134_135_136_138_keep_scene_focus_and_remove_frames(self):
        cases = (
            (
                "Scene: the bronze bowl sitting completely still as dark shadows move around it",
                ("Object-only still bronze bowl shadow evidence", "Vessel count is exactly one", "zero side bowls"),
                ("people around bowl", "second bowl", "duplicate vessel"),
            ),
            (
                "Scene: a small seed sprouting aggressively through a heavy iron grating",
                ("Object-only seed through iron grating evidence", "one small green seedling", "one heavy dark iron grating"),
                ("glowing magic plant", "people around sprout", "watering pot"),
            ),
            (
                "Scene: a hand tightly gripping a dagger in the pitch black shadows",
                ("Single dagger grip shadow close-up", "one sleeve-covered fist", "one short straight iron dagger"),
                ("full body in dagger scene", "second hand on dagger", "curved dagger"),
            ),
            (
                "Scene: an eye staring intensely, reflecting the flames of a burning forge",
                ("Single eye forge-flame reflection close-up", "one intense human eye", "orange forge flame reflected"),
                ("full forge room", "two people at fire", "second eye"),
            ),
            (
                "Scene: a dark, oppressive sky slowly beginning to clear at the horizon",
                ("Full-bleed oppressive sky clearing horizon landscape", "narrow pale break of light", "landscape-only"),
                ("white border", "courtyard in sky landscape", "people in sky landscape"),
            ),
        )

        for source, expected_prompt_parts, expected_negative_parts in cases:
            with self.subTest(source=source):
                compact, neg = _compact_flux2_klein_4b_prompt(source, "")
                for expected in expected_prompt_parts:
                    self.assertIn(expected, compact)
                self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
                self.assertNotIn("readable writing", compact.lower())
                for expected in expected_negative_parts:
                    self.assertIn(expected, neg)

    def test_flux2_klein_compacts_ep13_cuts_139_to_144_use_textless_period_objects_and_weapons(self):
        cases = (
            (
                "Scene: a king turning his back carelessly on his subjugated vassals",
                ("Back-turned vassal submission courtyard", "six bowed Silla vassals", "Roof tile count is zero"),
                ("tiled palace roof", "horse in submission courtyard", "boat in submission courtyard"),
            ),
            (
                "Scene: a dark, bleeding wound carving its way across an ancient map",
                ("Board-surface-only blood-wound campaign evidence", "entire canvas", "Zero people, zero hands"),
                ("map labels", "hanging wall scroll", "top-right placard"),
            ),
            (
                "Scene: a dark, bleeding wound carving its way across an ancient low horizontal tactile marker layout on a visible table",
                ("Board-surface-only blood-wound campaign evidence", "entire canvas", "zero cups"),
                ("people around map", "cup on map table", "calligraphy placard"),
            ),
            (
                "Scene: two intersecting swords sparking violently in the dark",
                ("Object-only intersecting straight blades spark close-up", "Two short straight early Korean iron blade edges", "rawhide-wrapped tang ends"),
                ("European sword", "crossguard", "people holding crossed swords"),
            ),
            (
                "Scene: a boiling pot of water suddenly shattering into pieces",
                ("Object-only shattering boiling pot evidence", "visibly broken open", "boiling water spray"),
                ("intact boiling pot", "people around boiling pot", "white border"),
            ),
            (
                "Scene: a sharp, hidden blade cleanly cutting through a thick rope",
                ("Object-only rope-cut blade close-up", "one thick twisted hemp rope", "visibly separated into two frayed ends"),
                ("second rope", "blade not touching rope", "hand holding rope"),
            ),
            (
                "Scene: a massive, heavy iron gear turning relentlessly",
                ("Ancient iron-rimmed winch wheel", "dark hammered iron rim", "blunt wooden spokes"),
                ("modern gear", "rubber tire", "machine wheel"),
            ),
        )

        for source, expected_prompt_parts, expected_negative_parts in cases:
            with self.subTest(source=source):
                compact, neg = _compact_flux2_klein_4b_prompt(source, "")
                for expected in expected_prompt_parts:
                    self.assertIn(expected, compact)
                self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
                self.assertNotIn("readable writing", compact.lower())
                for expected in expected_negative_parts:
                    self.assertIn(expected, neg)

    def test_flux2_klein_compacts_ep13_cuts_145_to_148_are_object_focused_and_textless(self):
        cases = (
            (
                "Scene: a glowing golden crown slowly sinking into a pool of dark blood",
                ("Object-only crown sinking into blood pool evidence", "half-submerged", "red reflections on the gold"),
                ("dry crown on stone", "crown not touching blood", "second crown"),
            ),
            (
                "Scene: a single teardrop rippling a puddle of red liquid",
                ("Object-only single teardrop red puddle macro", "concentric ripples", "Zero people, zero roofs"),
                ("white frame around puddle", "horse near red puddle", "tiled roof near red puddle"),
            ),
            (
                "Scene: a sharp scalpel slicing through a dusty, romanticized history text",
                ("Object-only blade slicing blank record bundle", "one short straight early Korean iron blade", "fresh split in the wood"),
                ("modern scalpel", "written history text", "blade missing from record bundle"),
            ),
            (
                "Scene: dark crimson borders expanding aggressively across an ancient map",
                ("Board-surface-only crimson-border campaign board evidence", "whole canvas", "Zero people, zero hands"),
                ("people around crimson map", "hands on crimson map", "wall scroll near crimson map"),
            ),
            (
                "Scene: dark crimson borders expanding aggressively across an ancient low horizontal tactile marker layout",
                ("Board-surface-only crimson-border campaign board evidence", "crimson border bands", "zero side vessels"),
                ("map labels", "geographic outline map", "hands on crimson map"),
            ),
        )

        for source, expected_prompt_parts, expected_negative_parts in cases:
            with self.subTest(source=source):
                compact, neg = _compact_flux2_klein_4b_prompt(source, "")
                for expected in expected_prompt_parts:
                    self.assertIn(expected, compact)
                self.assertNotRegex(compact, r"[가-힣一-龥ぁ-んァ-ン]")
                self.assertNotIn("readable writing", compact.lower())
                for expected in expected_negative_parts:
                    self.assertIn(expected, neg)

    def test_ep13_silla_soldiers_dropped_weapons_stays_ground_action(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: exhausted Silla soldiers dropping their weapons in the mud; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)
        final_prompt, final_negative = _promote_ep13_final_scene_overrides(
            f"TEXTLESS SURFACE FIRST RULE: common guard. {comfy_prompt}",
            comfy_negative,
        )

        self.assertIn("EARLY SILLA DROPPED WEAPONS MUD FIRST RULE", comfy_prompt)
        self.assertIn("iron spearheads, bows, arrows", comfy_prompt)
        self.assertIn("three to five separate exhausted Silla soldiers", comfy_prompt)
        self.assertIn("not a proud front-facing lineup", comfy_prompt)
        self.assertIn("Do not draw swords", comfy_prompt)
        self.assertIn("chest badge", comfy_negative)
        self.assertIn("missing weapons on mud", comfy_negative)
        self.assertIn("chest pocket", comfy_negative)
        self.assertIn("cruciform crossguard", comfy_negative)
        self.assertTrue(final_prompt.startswith("FINAL EP13 DROPPED WEAPONS IN MUD OVERRIDE"))
        self.assertIn("half-sunk in wet mud", final_prompt)
        self.assertIn("Do not draw swords", final_prompt)
        self.assertIn("proud standing lineup", final_negative)

    def test_ep13_sword_striking_silla_map_becomes_single_marker_press(self):
        prompt = (
            "TEXTLESS SURFACE FIRST RULE: common guard. "
            "Scene: a sharp sword striking a low horizontal tactile marker layout "
            "on a visible table with loose route cords, separated stone markers, "
            "bronze weights, dust, and hard side light precisely on the location of Silla."
        )
        comfy_prompt, comfy_negative = _promote_ep13_final_scene_overrides(prompt, "")

        self.assertTrue(comfy_prompt.startswith("No visible text, no title"))
        self.assertIn("one single cropped iron blade tip", comfy_prompt)
        self.assertIn("physically touching one large central", comfy_prompt)
        self.assertIn("triangular iron point and a short straight metal edge", comfy_prompt)
        self.assertNotIn("crop out the hilt", comfy_prompt)
        self.assertNotIn("sharp sword striking", comfy_prompt)
        self.assertIn("crossed swords", comfy_negative)
        self.assertIn("blade not touching marker", comfy_negative)
        self.assertIn("hand close-up", comfy_negative)
        self.assertIn("second blade", comfy_negative)

    def test_ep13_shattered_glass_becomes_bronze_mirror_reflection(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: a shattered glass reflecting a dark, burning ancient palace; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)

        self.assertIn("BROKEN BRONZE MIRROR REFLECTION FIRST RULE", comfy_prompt)
        self.assertIn("broken polished bronze mirror fragments", comfy_prompt)
        self.assertNotIn("shattered glass", comfy_prompt)
        self.assertNotIn("TEXTLESS SURFACE FIRST RULE", comfy_prompt)
        self.assertNotIn("ANATOMY CONSISTENCY FIRST RULE", comfy_prompt)
        self.assertIn("shattered glass", comfy_negative)
        self.assertIn("gate replacing mirror", comfy_negative)
        self.assertIn("wooden frame", comfy_negative)
        self.assertIn("window pane", comfy_negative)
        self.assertIn("human hands", comfy_negative)

    def test_ep13_king_asin_dagger_sharpening_is_single_low_room_action(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: King Asin of Baekje sharpening a dagger in a dark, dimly lit room; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)

        self.assertIn("EARLY BAEKJE KING DAGGER SHARPENING FIRST RULE", comfy_prompt)
        self.assertIn("exactly one adult Baekje King Asin alone", comfy_prompt)
        self.assertIn("one short straight dagger blade touches one rough whetstone", comfy_prompt)
        self.assertIn("small sleeve-covered hands", comfy_prompt)
        self.assertNotIn("TEXTLESS SURFACE FIRST RULE", comfy_prompt)
        self.assertIn("second person", comfy_negative)
        self.assertIn("missing whetstone", comfy_negative)
        self.assertIn("dagger not touching whetstone", comfy_negative)
        self.assertIn("modern wall switch", comfy_negative)
        self.assertIn("spread fingers", comfy_negative)

    def test_ep13_baekje_wa_pact_clasp_blocks_lineup_and_business_suits(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: Baekje and Wa warriors shaking hands in the shadows; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)

        self.assertIn("ANCIENT BAEKJE-WA PACT CLASP FIRST RULE", comfy_prompt)
        self.assertIn("TEXTLESS IMAGE RULE", comfy_prompt)
        self.assertIn("exactly two main adult figures only", comfy_prompt)
        self.assertIn("sleeve-covered forearms meet in one small pact clasp", comfy_prompt)
        self.assertIn("Background walls, beams, posts", comfy_prompt)
        self.assertIn("no wall plaque", comfy_prompt)
        self.assertIn("no emblem, no crest, no star badge", comfy_prompt)
        self.assertNotIn("TEXTLESS SURFACE FIRST RULE", comfy_prompt)
        self.assertNotIn("business suit", comfy_prompt)
        self.assertNotIn("modern suit", comfy_prompt)
        self.assertIn("missing pact clasp", comfy_negative)
        self.assertIn("standing lineup", comfy_negative)
        self.assertIn("business suit", comfy_negative)
        self.assertIn("wall plaque", comfy_negative)
        self.assertIn("bare forearm emphasis", comfy_negative)
        self.assertIn("star badge on shoulder", comfy_negative)
        self.assertIn("wall switch", comfy_negative)
        self.assertIn("extra hands", comfy_negative)

    def test_ep13_mass_troop_march_blocks_later_palace_and_modern_uniforms(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: thousands of heavily armored foreign troops marching forward; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)

        self.assertIn("EARLY NORTHEAST ASIAN MASS TROOP MARCH FIRST RULE", comfy_prompt)
        self.assertIn("nine to fifteen separated adult troops", comfy_prompt)
        self.assertIn("rough frontier fortification", comfy_prompt)
        self.assertIn("dull iron, rawhide, or leather lamellar panels", comfy_prompt)
        self.assertNotIn("TEXTLESS SURFACE FIRST RULE", comfy_prompt)
        self.assertNotIn("Joseon palace gate", comfy_prompt)
        self.assertNotIn("modern uniform", comfy_prompt)
        self.assertIn("Joseon palace gate", comfy_negative)
        self.assertIn("modern uniform", comfy_negative)
        self.assertIn("shared head between bodies", comfy_negative)
        final_prompt, final_negative = _promote_ep13_final_scene_overrides(
            f"TEXTLESS SURFACE FIRST RULE: common guard. {comfy_prompt}",
            comfy_negative,
        )
        self.assertTrue(final_prompt.startswith("No visible text, no title"))
        self.assertIn("open dirt road or packed-earth field edge", final_prompt)
        self.assertIn("Keep buildings, gates", final_prompt)
        self.assertIn("glossy black boots", final_negative)
        self.assertIn("palace roof", final_negative)

    def test_ep13_wa_warship_fleet_stays_open_ocean_not_beach_gate(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: a fleet of ancient Wa warships sailing through rough, dark ocean waves; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)

        self.assertIn("EARLY WA WARSHIP FLEET FIRST RULE", comfy_prompt)
        self.assertIn("five to eight separate rough wooden war boats", comfy_prompt)
        self.assertIn("dark rough ocean waves", comfy_prompt)
        self.assertNotIn("beach landing", comfy_prompt)
        self.assertNotIn("TEXTLESS SURFACE FIRST RULE", comfy_prompt)
        self.assertIn("single boat replacing fleet", comfy_negative)
        self.assertIn("shore gate", comfy_negative)
        self.assertIn("Japanese torii gate", comfy_negative)

    def test_ep13_burning_watchtower_requires_fire_and_collapse(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: a wooden Silla watchtower burning and collapsing into the dirt; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)

        self.assertIn("EARLY SILLA BURNING WOODEN WATCHTOWER FIRST RULE", comfy_prompt)
        self.assertIn("four rough posts", comfy_prompt)
        self.assertIn("orange flame, smoke, sparks", comfy_prompt)
        self.assertNotIn("palace gate", comfy_prompt.lower())
        self.assertNotIn("TEXTLESS SURFACE FIRST RULE", comfy_prompt)
        self.assertIn("missing fire", comfy_negative)
        self.assertIn("palace gate replacing watchtower", comfy_negative)

    def test_ep13_cavalry_encirclement_blocks_single_rider(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: the Silla capital completely surrounded by dark armored cavalry; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)

        self.assertIn("EARLY SILLA CAPITAL CAVALRY ENCIRCLEMENT FIRST RULE", comfy_prompt)
        self.assertIn("at least twelve separate horse-and-rider pairs", comfy_prompt)
        self.assertIn("completely encircled", comfy_prompt)
        self.assertIn("straw-thatch, reed-thatch, bark, or rough wooden plank only", comfy_prompt)
        self.assertNotIn("TEXTLESS SURFACE FIRST RULE", comfy_prompt)
        self.assertIn("single rider replacing surrounded capital", comfy_negative)
        self.assertIn("horse with two bodies", comfy_negative)
        self.assertIn("gray ceramic tile roof", comfy_negative)
        self.assertIn("stone gatehouse", comfy_negative)
        self.assertIn("torii gate", comfy_negative)
        final_prompt, final_negative = _promote_ep13_final_scene_overrides(
            f"TEXTLESS SURFACE FIRST RULE: common guard. {comfy_prompt}",
            comfy_negative,
        )
        self.assertTrue(final_prompt.startswith("No visible text, no title"))
        self.assertIn("earthwork and timber palisade", final_prompt)
        self.assertIn("No stone masonry wall", final_prompt)
        self.assertIn("stone masonry wall", final_negative)
        self.assertIn("top title", final_negative)

    def test_ep13_naemul_armrest_scene_blocks_modern_suits(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: King Naemul gripping his throne's armrest, pale and panicked; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)

        self.assertIn("EARLY SILLA RULER ROOM FIRST RULE", comfy_prompt)
        self.assertIn("exactly one terrified early Silla ruler or Naemul Maripgan", comfy_prompt)
        self.assertIn("hands grip plain low wooden armrests", comfy_prompt)
        self.assertNotIn("business suit", comfy_prompt)
        self.assertNotIn("modern suit", comfy_prompt)
        self.assertNotIn("TEXTLESS SURFACE FIRST RULE", comfy_prompt)
        self.assertIn("three men in suits", comfy_negative)
        self.assertIn("buttoned coat", comfy_negative)

    def test_ep13_silla_crown_object_not_closed_ring_or_white_background(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: a small, fragile Silla crown resting on a cold stone table; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)

        self.assertIn("EARLY SILLA CROWN OBJECT FIRST RULE", comfy_prompt)
        self.assertIn("three thin upright tree-branch shaped plates", comfy_prompt)
        self.assertIn("two antler-like side ornaments", comfy_prompt)
        self.assertIn("cold rough gray stone table", comfy_prompt)
        self.assertIn("Object-only still life", comfy_prompt)
        self.assertNotIn("TEXTLESS SURFACE FIRST RULE", comfy_prompt)
        self.assertIn("closed circular ring replacing crown", comfy_negative)
        self.assertIn("bracelet", comfy_negative)
        self.assertIn("missing stone table", comfy_negative)
        self.assertIn("white studio background", comfy_negative)
        self.assertIn("cropped hands", comfy_negative)

    def test_ep13_goguryeo_shadow_over_silla_official_keeps_two_roles(self):
        prompt = prompt_builder.build_image_prompt(
            (
                "Year/period: 400~415년; Exact place: 신라 종발성; "
                "Scene: a towering Goguryeo warrior casting a giant shadow over a Silla official; "
                "Style: serious adult graphic novel illustration"
            ),
            "storytelling",
            enable_historical_guard=True,
        )
        negative = prompt_builder.append_prompt_specific_negative_prompt("", prompt)
        comfy_prompt, comfy_negative = _enforce_comfyui_common_positive_prompt(prompt, negative)

        self.assertIn("EARLY GOGURYEO SHADOW OVER SILLA OFFICIAL FIRST RULE", comfy_prompt)
        self.assertIn("exactly two main people only", comfy_prompt)
        self.assertIn("one adult Silla official", comfy_prompt)
        self.assertIn("one huge continuous warrior-shaped shadow", comfy_prompt)
        self.assertIn("adult head-to-body proportions", comfy_prompt)
        self.assertIn("kneeling, bowing, or lowering his shoulders", comfy_prompt)
        self.assertNotIn("TEXTLESS SURFACE FIRST RULE", comfy_prompt)
        self.assertIn("missing giant shadow", comfy_negative)
        self.assertIn("farmer replacing official", comfy_negative)
        self.assertIn("child replacing official", comfy_negative)
        self.assertIn("waist-high official beside warrior", comfy_negative)
        self.assertIn("business suit", comfy_negative)
        self.assertIn("ornate tiled roof", comfy_negative)

    def test_flux2_klein_1940s_police_report_is_textless_folder(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=85; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A formal, typewritten 1940s police report resting on a desk, stamped with a heavy black seal; "
            "Scene: A formal, typewritten 1940s police report resting on a desk, stamped with a heavy black seal"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("closed plain manila police evidence folder", compact)
        self.assertIn("asymmetric featureless black wax closure blob", compact)
        self.assertIn("front surface fully hidden under the folder cover", compact)
        self.assertIn("object-only close top-down view", compact)
        self.assertIn("zero background room", compact)
        self.assertNotIn("typewritten 1940s police report", compact.lower())
        self.assertNotIn("laboratory interior", compact)
        self.assertNotIn("office-lab room", compact)
        self.assertIn("typewritten text", negative)
        self.assertIn("open report page", negative)
        self.assertIn("letters on wax", negative)

    def test_flux2_klein_1940s_owl_stays_natural_animal_not_hybrid(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=148; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A wise owl sitting on a branch, looking knowingly at the viewer; "
            "Scene: A wise owl sitting on a branch, looking knowingly at the viewer"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("exactly one bare natural owl perched on one tree branch", compact)
        self.assertIn("Zero people", compact)
        self.assertIn("zero lab coat", compact)
        self.assertNotIn("laboratory or office-lab", compact)
        self.assertNotIn("laboratory interior", compact)
        self.assertIn("owl with human body", negative)
        self.assertIn("lab coat on owl", negative)

        guarded = prompt_builder.build_image_prompt(
            prompt,
            "serious adult graphic novel illustration",
            enable_historical_guard=True,
        )
        guarded_compact, guarded_negative = _compact_flux2_klein_4b_prompt(guarded, "")
        self.assertIn("exactly one bare natural owl perched on one tree branch", guarded_compact)
        self.assertNotIn("laboratory interior", guarded_compact)
        self.assertIn("owl with human body", guarded_negative)

    def test_flux2_klein_1944_refrigerator_leak_is_unmarked_appliance(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=31; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: An antique, heavy metal refrigerator leaking a noxious, smoking gas from its back; "
            "Scene: An antique, heavy metal refrigerator leaking a noxious, smoking gas from its back"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("textless domestic refrigerator hazard scene", compact)
        self.assertIn("plain unmarked rounded metal refrigerator", compact)
        self.assertIn("zero refrigerator logo", compact)
        self.assertIn("zero brand badge", compact)
        self.assertNotIn("laboratory or office-lab documentary scene", compact)
        self.assertIn("refrigerator logo", negative)
        self.assertIn("serial number plate", negative)

    def test_flux2_klein_1944_dark_kitchen_fog_has_no_wall_documents(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=32; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A dark, quiet kitchen at night, a heavy, ominous fog rolling slowly across the floor; "
            "Scene: A dark, quiet kitchen at night, a heavy, ominous fog rolling slowly across the floor"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("empty domestic kitchen gas-fog scene", compact)
        self.assertIn("zero wall papers", compact)
        self.assertIn("zero framed documents", compact)
        self.assertIn("zero appliance logos", compact)
        self.assertNotIn("laboratory or office-lab documentary scene", compact)
        self.assertIn("laboratory replacing kitchen", negative)
        self.assertIn("cabinet label", negative)

    def test_flux2_klein_1944_refrigerator_blueprint_routes_to_parts_workbench(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=33; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A blueprint of a refrigerator laid out on a table, a compass and ruler resting on top; "
            "Scene: A blueprint of a refrigerator laid out on a table, a compass and ruler resting on top"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("textless refrigeration workbench still life", compact)
        self.assertIn("unmarked refrigerator compressor", compact)
        self.assertIn("coiled copper tubing", compact)
        self.assertIn("zero blueprint sheet", compact)
        self.assertIn("zero person holding documents", compact)
        self.assertNotIn("blueprint of a refrigerator", compact.lower())
        self.assertIn("blueprint sheet", negative)
        self.assertIn("person holding paper", negative)

    def test_flux2_klein_1944_freon_container_is_object_only_textless(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=35; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A glowing, frosty blue mist swirling inside a sealed, heavy glass container; "
            "Scene: A glowing, frosty blue mist swirling inside a sealed, heavy glass container"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("textless Freon evidence still life", compact)
        self.assertIn("one sealed heavy glass container", compact)
        self.assertIn("zero people", compact)
        self.assertIn("zero open papers", compact)
        self.assertNotIn("laboratory or office-lab documentary scene", compact)
        self.assertIn("scientist writing on paper", negative)
        self.assertIn("label on container", negative)

    def test_flux2_klein_midgley_refrigerant_cylinder_not_glass_jar(self):
        prompt = (
            "Year/period: late 1920s; Exact place: refrigeration research laboratory in the United States; "
            "Scene evidence: The next pattern involves CFCs, whose stability later became dangerous.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: sealed refrigerant cylinder; "
            "Scene: A sealed metal cylinder stands beside cooling coils as a calm vapor curls under laboratory lamps."
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("refrigeration chemistry demonstration", compact)
        self.assertIn("metal refrigerant cylinder", compact)
        self.assertIn("frosted copper cooling coils", compact)
        self.assertIn("uninterrupted blank metal skin", compact)
        self.assertIn("corked glass jar replacing refrigerant cylinder", negative)
        self.assertIn("label on metal cylinder", negative)
        self.assertNotIn("textless Freon evidence still life", compact)
        self.assertNotIn("one sealed heavy glass container", compact)

    def test_flux2_klein_midgley_ozone_scene_not_glass_jar(self):
        prompt = (
            "Year/period: 1980s; Exact place: atmospheric research laboratory; "
            "Scene evidence: CFCs addressed refrigeration hazards but were later found to harm the ozone layer.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: refrigerant cylinder and ozone model; "
            "Scene: A plain refrigerant cylinder stands beside a glowing atmospheric model as scientists gesture in alarm."
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("atmospheric research and ozone policy scene", compact)
        self.assertIn("scientists or officials", compact)
        self.assertIn("physical unlabeled blue globe model", compact)
        self.assertIn("plain metal refrigerant cylinder", compact)
        self.assertIn("full 16:9 image edge to edge", compact)
        self.assertIn("single jar close-up", negative)
        self.assertIn("comic panel frame", negative)
        self.assertNotIn("textless Freon evidence still life", compact)

    def test_flux2_klein_midgley_evidence_table_keeps_all_objects(self):
        prompt = (
            "Year/period: 1944-1980s; Exact place: composite industrial archive room without readable text; "
            "Scene evidence: Worthington, Ohio Midgley industrial legacy beyond the symbolic accident.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: rope, fuel vessel, and sample jars; "
            "Scene: A rope, fuel vessel, refrigerant cylinder, and sample jars sit together under one cold archival lamp."
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("industrial evidence table", compact)
        self.assertIn("straight rope segment", compact)
        self.assertIn("metal fuel can", compact)
        self.assertIn("metal refrigerant cylinder", compact)
        self.assertIn("sample jars", compact)
        self.assertIn("single jar close-up", negative)
        self.assertNotIn("textless Freon evidence still life", compact)

    def test_flux2_klein_midgley_bedroom_doorway_rope_shadow_not_lab(self):
        prompt = (
            "Year/period: 1944; Exact place: bedroom doorway in Midgley's Worthington home; "
            "Scene evidence: The device's intended aid and fatal role create the episode's symbolic frame.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: empty doorway and rope shadow; "
            "Scene: A long rope shadow stretches from the bedroom into the hallway, pulling the viewer toward the hidden mechanism."
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("domestic bedroom doorway rope-shadow scene", compact)
        self.assertIn("empty open bedroom doorway", compact)
        self.assertIn("long rope shadow", compact)
        self.assertIn("side hallway plaster is outside the image", compact)
        self.assertIn("full 16:9 image edge to edge", compact)
        self.assertNotIn("laboratory or office-lab documentary scene", compact)
        self.assertIn("laboratory replacing bedroom doorway", negative)
        self.assertIn("doorway wall switch", negative)

    def test_flux2_klein_midgley_lab_context_blocks_wall_switches(self):
        prompt = (
            "Year/period: 1930s; Exact place: professional chemical laboratory; "
            "Scene evidence: CFC consequences emerged long after their celebrated practical adoption.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: Midgley silhouette near cylinders; "
            "Scene: Midgley's silhouette crosses a laboratory wall while cylinder shadows stretch upward like unseen atmospheric trails."
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("laboratory or office-lab documentary scene", compact)
        self.assertIn("zero wall switch plates", compact)
        self.assertIn("zero framed certificates", compact)
        self.assertIn("wall switch plate", negative)
        self.assertIn("framed wall certificate", negative)

    def test_flux2_klein_1944_safe_refrigerator_kitchen_is_1940s_unmarked(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=37; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A pristine, glowing 1950s kitchen with a shiny new refrigerator standing proudly in the center; "
            "Scene: A pristine, glowing 1950s kitchen with a shiny new refrigerator standing proudly in the center"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("textless domestic refrigeration scene", compact)
        self.assertIn("rounded 1940s metal refrigerator", compact)
        self.assertIn("zero fridge logo", compact)
        self.assertIn("zero brand badge", compact)
        self.assertNotIn("1950s kitchen", compact.lower())
        self.assertIn("1950s chrome showroom", negative)
        self.assertIn("nameplate on refrigerator", negative)

    def test_flux2_klein_1944_satellite_and_atmosphere_route_to_textless_globe_cloche(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=38; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A high-tech satellite looking down at the Earth, its lenses glowing with warning lights; "
            "Scene: A high-tech satellite looking down at the Earth, its lenses glowing with warning lights"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("globe-and-glass-cloche workbench still life", compact)
        self.assertIn("one physical period classroom globe inside", compact)
        self.assertIn("broad unlabeled landmass silhouettes", compact)
        self.assertIn("zero satellite", compact)
        self.assertNotIn("high-tech satellite", compact.lower())
        self.assertIn("high-tech satellite", negative)
        self.assertIn("country names", negative)

    def test_flux2_klein_black_screen_rope_becomes_textless_closing_frame(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=150; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A black screen with the faint, echoing sound of a creaking rope; "
            "Scene: A black screen with the faint, echoing sound of a creaking rope"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("near-black full-frame darkness", compact)
        self.assertIn("plain rope segment or rope loop", compact)
        self.assertIn("Zero people", compact)
        self.assertNotIn("laboratory or office-lab", compact)
        self.assertNotIn("laboratory interior", compact)
        self.assertIn("laboratory replacing black closing frame", negative)
        self.assertIn("warrior in closing frame", negative)

        guarded = prompt_builder.build_image_prompt(
            prompt,
            "serious adult graphic novel illustration",
            enable_historical_guard=True,
        )
        guarded_compact, guarded_negative = _compact_flux2_klein_4b_prompt(guarded, "")
        self.assertIn("near-black full-frame darkness", guarded_compact)
        self.assertNotIn("laboratory interior", guarded_compact)
        self.assertIn("laboratory replacing black closing frame", guarded_negative)

    def test_flux2_klein_1944_rope_on_bed_is_textless_empty_bed(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=94; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: The tangled, deadly knot of ropes resting silently on an empty, perfectly made white bed; "
            "Scene: The tangled, deadly knot of ropes resting silently on an empty, perfectly made white bed"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("one tangled rope knot lying on an empty", compact)
        self.assertIn("neatly made white cotton bed", compact)
        self.assertNotIn("factory, garage, or industrial workshop", compact)
        self.assertNotIn("Early twentieth-century science and industry evidence", compact)
        self.assertIn("wall note with writing", negative)
        self.assertIn("sack writing", negative)

        guarded = prompt_builder.build_image_prompt(
            prompt,
            "serious adult graphic novel illustration",
            enable_historical_guard=True,
        )
        guarded_compact, guarded_negative = _compact_flux2_klein_4b_prompt(guarded, "")
        self.assertIn("one tangled rope knot lying on an empty", guarded_compact)
        self.assertIn("neatly made white cotton bed", guarded_compact)
        self.assertNotIn("factory, garage, or industrial workshop", guarded_compact)
        self.assertNotIn("Early twentieth-century science and industry evidence", guarded_compact)
        self.assertIn("wall note with writing", guarded_negative)

    def test_flux2_klein_1944_weak_cord_reach_has_connected_body(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=74; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A thin, trembling hand reaching up uselessly, lacking the strength to pull the heavy cord; "
            "Scene: A thin, trembling hand reaching up uselessly, lacking the strength to pull the heavy cord"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("1944 Worthington bedroom assistive-rig anatomy scene", compact)
        self.assertIn("exactly one weak adult man", compact)
        self.assertIn("one raised sleeve-covered arm connected from shoulder to elbow to wrist", compact)
        self.assertIn("one small trembling hand reaching toward one heavy vertical cord", compact)
        self.assertIn("zero detached hands", compact)
        self.assertNotIn("laboratory or office-lab documentary scene", compact)
        self.assertNotIn("factory, garage, or industrial workshop", compact)
        self.assertIn("detached hand", negative)
        self.assertIn("laboratory replacing bedroom", negative)

        guarded = prompt_builder.build_image_prompt(
            prompt,
            "serious adult graphic novel illustration",
            enable_historical_guard=True,
        )
        guarded_compact, guarded_negative = _compact_flux2_klein_4b_prompt(guarded, "")
        self.assertIn("1944 Worthington bedroom assistive-rig anatomy scene", guarded_compact)
        self.assertIn("exactly one weak adult man", guarded_compact)
        self.assertIn("one raised sleeve-covered arm connected from shoulder to elbow to wrist", guarded_compact)
        self.assertNotIn("laboratory or office-lab documentary scene", guarded_compact)
        self.assertIn("detached hand", guarded_negative)
        self.assertIn("laboratory replacing bedroom", guarded_negative)

    def test_flux2_klein_1944_gold_medal_is_textless_workbench_still_life(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=98; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A shiny, triumphant gold medal gleaming brightly, completely unaware of its toxic legacy; "
            "Scene: A shiny, triumphant gold medal gleaming brightly, completely unaware of its toxic legacy"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("1940s Worthington textless medal workbench still life", compact)
        self.assertIn("one plain smooth round gold medal disk", compact)
        self.assertIn("blank metal face", compact)
        self.assertIn("zero raised letters", compact)
        self.assertIn("zero rim inscriptions", compact)
        self.assertNotIn("laboratory or office-lab documentary scene", compact)
        self.assertIn("gold medal letters", negative)
        self.assertIn("rim inscription", negative)
        self.assertIn("embossed letters", negative)

        guarded = prompt_builder.build_image_prompt(
            prompt,
            "serious adult graphic novel illustration",
            enable_historical_guard=True,
        )
        guarded_compact, guarded_negative = _compact_flux2_klein_4b_prompt(guarded, "")
        self.assertIn("1940s Worthington textless medal workbench still life", guarded_compact)
        self.assertIn("one plain smooth round gold medal disk", guarded_compact)
        self.assertIn("zero raised letters", guarded_compact)
        self.assertNotIn("laboratory or office-lab documentary scene", guarded_compact)
        self.assertIn("gold medal letters", guarded_negative)
        self.assertIn("rim inscription", guarded_negative)

    def test_flux2_klein_1944_suburban_sunset_stays_exterior(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=119; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A warm, glowing sunset over a retro suburban neighborhood, symbolizing the end of a journey, beautiful; "
            "Scene: A warm, glowing sunset over a retro suburban neighborhood, symbolizing the end of a journey, beautiful"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("1940s Worthington exterior suburban sunset scene", compact)
        self.assertIn("wide empty retro suburban neighborhood", compact)
        self.assertIn("early parked cars with blank plates", compact)
        self.assertIn("zero laboratory interior", compact)
        self.assertNotIn("laboratory or office-lab documentary scene", compact)
        self.assertIn("laboratory replacing suburban sunset", negative)
        self.assertIn("license plate text", negative)

        guarded = prompt_builder.build_image_prompt(
            prompt,
            "serious adult graphic novel illustration",
            enable_historical_guard=True,
        )
        guarded_compact, guarded_negative = _compact_flux2_klein_4b_prompt(guarded, "")
        self.assertIn("1940s Worthington exterior suburban sunset scene", guarded_compact)
        self.assertIn("wide empty retro suburban neighborhood", guarded_compact)
        self.assertNotIn("laboratory or office-lab documentary scene", guarded_compact)
        self.assertIn("laboratory replacing suburban sunset", guarded_negative)

    def test_flux2_klein_1944_straight_rope_table_is_object_only(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=120; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A single, clean, untangled piece of rope lying perfectly straight on a wooden table; "
            "Scene: A single, clean, untangled piece of rope lying perfectly straight on a wooden table"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("1940s Worthington object-only rope worktable still life", compact)
        self.assertIn("one single clean untangled rope segment", compact)
        self.assertIn("zero coils", compact)
        self.assertIn("zero room background", compact)
        self.assertNotIn("laboratory or office-lab documentary scene", compact)
        self.assertIn("coiled rope", negative)
        self.assertIn("paper under rope", negative)

        guarded = prompt_builder.build_image_prompt(
            prompt,
            "serious adult graphic novel illustration",
            enable_historical_guard=True,
        )
        guarded_compact, guarded_negative = _compact_flux2_klein_4b_prompt(guarded, "")
        self.assertIn("1940s Worthington object-only rope worktable still life", guarded_compact)
        self.assertIn("one single clean untangled rope segment", guarded_compact)
        self.assertNotIn("laboratory or office-lab documentary scene", guarded_compact)
        self.assertIn("coiled rope", guarded_negative)

    def test_flux2_klein_1944_rope_poison_vial_is_textless_workbench_still_life(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=138; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A thick rope snapping tightly next to a vial of poison; "
            "Scene: A thick rope snapping tightly next to a vial of poison"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("1940s Worthington object-only rope and poison-vial workbench still life", compact)
        self.assertIn("one straight thick frayed rope segment pulled taut", compact)
        self.assertIn("one plain unlabeled glass vial", compact)
        self.assertIn("zero coils", compact)
        self.assertIn("zero loops", compact)
        self.assertIn("zero wall notes", compact)
        self.assertIn("zero bottle label", compact)
        self.assertNotIn("laboratory or office-lab documentary scene", compact)
        self.assertIn("coiled rope", negative)
        self.assertIn("wall note", negative)
        self.assertIn("labeled vial", negative)

        guarded = prompt_builder.build_image_prompt(
            prompt,
            "serious adult graphic novel illustration",
            enable_historical_guard=True,
        )
        guarded_compact, guarded_negative = _compact_flux2_klein_4b_prompt(guarded, "")
        self.assertIn("1940s Worthington object-only rope and poison-vial workbench still life", guarded_compact)
        self.assertIn("one plain unlabeled glass vial", guarded_compact)
        self.assertIn("zero coils", guarded_compact)
        self.assertNotIn("laboratory or office-lab documentary scene", guarded_compact)
        self.assertIn("coiled rope", guarded_negative)
        self.assertIn("labeled vial", guarded_negative)

    def test_flux2_klein_lantern_stone_corridor_stays_textless_corridor(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=144; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A lantern casting a warm, flickering light down a long, dark stone corridor; "
            "Scene: A lantern casting a warm, flickering light down a long, dark stone corridor"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("Textless empty dark stone corridor lantern scene", compact)
        self.assertIn("one plain period lantern", compact)
        self.assertIn("long empty dark stone corridor", compact)
        self.assertIn("zero wall papers", compact)
        self.assertIn("zero framed diagrams", compact)
        self.assertNotIn("laboratory or office-lab documentary scene", compact)
        self.assertIn("laboratory replacing stone corridor", negative)
        self.assertIn("framed diagram", negative)

        guarded = prompt_builder.build_image_prompt(
            prompt,
            "serious adult graphic novel illustration",
            enable_historical_guard=True,
        )
        guarded_compact, guarded_negative = _compact_flux2_klein_4b_prompt(guarded, "")
        self.assertIn("Textless empty dark stone corridor lantern scene", guarded_compact)
        self.assertIn("one plain period lantern", guarded_compact)
        self.assertNotIn("laboratory or office-lab documentary scene", guarded_compact)
        self.assertIn("laboratory replacing stone corridor", guarded_negative)

    def test_flux2_klein_1944_closed_book_is_textless_workbench_still_life(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=140; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: An ancient book being closed softly, dust puffing into the air; "
            "Scene: An ancient book being closed softly, dust puffing into the air"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("1940s Worthington closed-book workbench still life", compact)
        self.assertIn("one closed plain old cloth-bound book", compact)
        self.assertIn("zero open pages", compact)
        self.assertIn("zero visible page faces", compact)
        self.assertIn("zero hands closing the book", compact)
        self.assertNotIn("laboratory or office-lab documentary scene", compact)
        self.assertIn("open book page", negative)
        self.assertIn("book title", negative)

        guarded = prompt_builder.build_image_prompt(
            prompt,
            "serious adult graphic novel illustration",
            enable_historical_guard=True,
        )
        guarded_compact, guarded_negative = _compact_flux2_klein_4b_prompt(guarded, "")
        self.assertIn("1940s Worthington closed-book workbench still life", guarded_compact)
        self.assertIn("one closed plain old cloth-bound book", guarded_compact)
        self.assertIn("zero open pages", guarded_compact)
        self.assertIn("open book page", guarded_negative)

    def test_flux2_klein_1944_marionette_is_textless_puppet_workbench(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=142; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A marionette puppet cutting its own strings with a tiny pair of scissors; "
            "Scene: A marionette puppet cutting its own strings with a tiny pair of scissors"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("1940s Worthington marionette workbench still life", compact)
        self.assertIn("one small plain wooden marionette puppet", compact)
        self.assertIn("exactly one wooden head, one torso, two arms, two legs", compact)
        self.assertIn("zero living humans", compact)
        self.assertIn("zero skull face", compact)
        self.assertIn("zero documents", compact)
        self.assertNotIn("laboratory or office-lab documentary scene", compact)
        self.assertIn("skull-headed puppet", negative)
        self.assertIn("puppet with extra arms", negative)

        guarded = prompt_builder.build_image_prompt(
            prompt,
            "serious adult graphic novel illustration",
            enable_historical_guard=True,
        )
        guarded_compact, guarded_negative = _compact_flux2_klein_4b_prompt(guarded, "")
        self.assertIn("1940s Worthington marionette workbench still life", guarded_compact)
        self.assertIn("one small plain wooden marionette puppet", guarded_compact)
        self.assertIn("zero living humans", guarded_compact)
        self.assertIn("skull-headed puppet", guarded_negative)

    def test_flux2_klein_1944_blueprint_flaw_is_textless_workbench_still_life(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=143; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A magnifying glass hovering over an old blueprint, focusing on a dark, fatal flaw; "
            "Scene: A magnifying glass hovering over an old blueprint, focusing on a dark, fatal flaw"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("1940s Worthington textless flaw-sheet workbench still life", compact)
        self.assertIn("one blank blue-gray evidence sheet", compact)
        self.assertIn("one plain magnifying glass resting on the sheet", compact)
        self.assertIn("no measuring border", compact)
        self.assertIn("no ruler scale", compact)
        self.assertIn("no tick marks", compact)
        self.assertIn("zero typewriters", compact)
        self.assertNotIn("laboratory or office-lab documentary scene", compact)
        self.assertIn("blueprint labels", negative)
        self.assertIn("ruler border", negative)
        self.assertIn("tick marks", negative)
        self.assertIn("typewriter beside blueprint", negative)

        guarded = prompt_builder.build_image_prompt(
            prompt,
            "serious adult graphic novel illustration",
            enable_historical_guard=True,
        )
        guarded_compact, guarded_negative = _compact_flux2_klein_4b_prompt(guarded, "")
        self.assertIn("1940s Worthington textless flaw-sheet workbench still life", guarded_compact)
        self.assertIn("one blank blue-gray evidence sheet", guarded_compact)
        self.assertIn("zero typewriters", guarded_compact)
        self.assertIn("blueprint labels", guarded_negative)

    def test_flux2_klein_1944_grease_carving_has_no_disembodied_arm(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=146; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A hand wiping away thick grease from a forgotten historical carving; "
            "Scene: A hand wiping away thick grease from a forgotten historical carving"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("1940s Worthington textless carving workbench evidence still life", compact)
        self.assertIn("one unmarked carved metal relief plate or stone relief plate", compact)
        self.assertIn("one dirty cloth rag", compact)
        self.assertIn("zero visible hands", compact)
        self.assertIn("zero arms", compact)
        self.assertIn("zero disembodied sleeves", compact)
        self.assertNotIn("sleeve-covered arm gesture", compact)
        self.assertNotIn("laboratory or office-lab documentary scene", compact)
        self.assertIn("detached hand", negative)
        self.assertIn("disembodied arm", negative)

        guarded = prompt_builder.build_image_prompt(
            prompt,
            "serious adult graphic novel illustration",
            enable_historical_guard=True,
        )
        guarded_compact, guarded_negative = _compact_flux2_klein_4b_prompt(guarded, "")
        self.assertIn("1940s Worthington textless carving workbench evidence still life", guarded_compact)
        self.assertIn("zero visible hands", guarded_compact)
        self.assertNotIn("sleeve-covered arm gesture", guarded_compact)
        self.assertIn("detached hand", guarded_negative)

    def test_flux2_klein_1944_archive_books_blueprints_are_textless_worktable(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=113; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A vintage library filled with glowing books and dusty blueprints, magical atmosphere; "
            "Scene: A vintage library filled with glowing books and dusty blueprints, magical atmosphere"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("quiet wooden archive worktable", compact)
        self.assertIn("closed unlabeled books", compact)
        self.assertIn("folded blank blueprint backs", compact)
        self.assertIn("zero open pages", compact)
        self.assertIn("zero ruled lines", compact)
        self.assertNotIn("factory, garage, or industrial workshop", compact)
        self.assertNotIn("Early twentieth-century science and industry evidence", compact)
        self.assertIn("book title", negative)
        self.assertIn("open notebook", negative)
        self.assertIn("blueprint labels", negative)

        guarded = prompt_builder.build_image_prompt(
            prompt,
            "serious adult graphic novel illustration",
            enable_historical_guard=True,
        )
        guarded_compact, guarded_negative = _compact_flux2_klein_4b_prompt(guarded, "")
        self.assertIn("quiet wooden archive worktable", guarded_compact)
        self.assertIn("closed unlabeled books", guarded_compact)
        self.assertIn("folded blank blueprint backs", guarded_compact)
        self.assertIn("zero open pages", guarded_compact)
        self.assertIn("zero ruled lines", guarded_compact)
        self.assertNotIn("factory, garage, or industrial workshop", guarded_compact)
        self.assertNotIn("Early twentieth-century science and industry evidence", guarded_compact)
        self.assertIn("book title", guarded_negative)
        self.assertIn("open notebook", guarded_negative)

    def test_flux2_klein_1944_eyes_reflecting_gear_stays_eye_closeup(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=145; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A pair of eyes reflecting a turning gear, intense and curious; "
            "Scene: A pair of eyes reflecting a turning gear, intense and curious"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("extreme close-up of exactly one adult man's two human eyes", compact)
        self.assertIn("turning gear reflection visible inside each iris", compact)
        self.assertNotIn("factory, garage, or industrial workshop", compact)
        self.assertNotIn("Early twentieth-century science and industry evidence", compact)
        self.assertIn("factory overview replacing eye closeup", negative)
        self.assertIn("extra eyes", negative)

        guarded = prompt_builder.build_image_prompt(
            prompt,
            "serious adult graphic novel illustration",
            enable_historical_guard=True,
        )
        guarded_compact, guarded_negative = _compact_flux2_klein_4b_prompt(guarded, "")
        self.assertIn("extreme close-up of exactly one adult man's two human eyes", guarded_compact)
        self.assertIn("turning gear reflection visible inside each iris", guarded_compact)
        self.assertNotIn("factory, garage, or industrial workshop", guarded_compact)
        self.assertIn("factory overview replacing eye closeup", guarded_negative)

    def test_flux2_klein_1944_split_safe_pulley_river_becomes_single_textless_workbench(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=139; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A split screen: an iron safe, a tangled pulley, and a frozen river; "
            "Scene: A split screen: an iron safe, a tangled pulley, and a frozen river"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("one continuous bare wooden workbench", compact)
        self.assertIn("one small plain iron safe", compact)
        self.assertIn("one tangled pulley-and-rope assembly", compact)
        self.assertIn("one shallow tray of cracked ice", compact)
        self.assertIn("zero split panels", compact)
        self.assertNotIn("factory, garage, or industrial workshop", compact)
        self.assertIn("split screen", negative)
        self.assertIn("wall note", negative)

        guarded = prompt_builder.build_image_prompt(
            prompt,
            "serious adult graphic novel illustration",
            enable_historical_guard=True,
        )
        guarded_compact, guarded_negative = _compact_flux2_klein_4b_prompt(guarded, "")
        self.assertIn("one continuous bare wooden workbench", guarded_compact)
        self.assertIn("one small plain iron safe", guarded_compact)
        self.assertIn("one tangled pulley-and-rope assembly", guarded_compact)
        self.assertIn("one shallow tray of cracked ice", guarded_compact)
        self.assertIn("zero split panels", guarded_compact)
        self.assertIn("split screen", guarded_negative)

    def test_flux2_klein_russian_poisoned_goblet_has_no_wall_or_bottle_text(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=130; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A man laughing heartily while drinking from a poisoned goblet, to the horror of his assassins; "
            "Scene: A man laughing heartily while drinking from a poisoned goblet, to the horror of his assassins"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("one plain poisoned wine goblet", compact)
        self.assertIn("The frame shows only the stated period materials", compact)
        self.assertNotIn("bottle labels", compact)
        self.assertNotIn("wall papers", compact)
        self.assertIn("bottle label", negative)
        self.assertIn("wall paper with writing", negative)

        guarded = prompt_builder.build_image_prompt(
            prompt,
            "serious adult graphic novel illustration",
            enable_historical_guard=True,
        )
        guarded_compact, guarded_negative = _compact_flux2_klein_4b_prompt(guarded, "")
        self.assertIn("The frame shows only the stated period materials", guarded_compact)
        self.assertNotIn("bottle labels", guarded_compact)
        self.assertNotIn("wall papers", guarded_compact)
        self.assertIn("bottle label", guarded_negative)

    def test_flux2_klein_final_cleanup_removes_negative_style_positive_terms(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=130; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A man laughing heartily while drinking from a poisoned goblet, to the horror of his assassins; "
            "Scene: A man laughing heartily while drinking from a poisoned goblet, to the horror of his assassins"
        )
        compact, _negative = _compact_flux2_klein_4b_prompt(prompt, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)
        cleaned_lower = cleaned.lower()

        self.assertIn("Physical surface contract:", cleaned)
        self.assertIn("one plain poisoned wine goblet", cleaned)
        for forbidden in (
            "zero",
            " no ",
            "do not",
            "avoid",
            "without",
            "forbidden",
            "negative",
            "readable text",
            "letters",
            "caption",
            "title",
            "glyph",
            "switch",
            "outlet",
            "socket",
        ):
            self.assertNotIn(forbidden, cleaned_lower)

    def test_flux2_klein_final_cleanup_adds_human_anatomy_contract(self):
        prompt = (
            "Street-level wide view of a historical Japanese packed-earth lane. "
            "People walk between plaster walls with plain sword scabbards and shadows."
        )

        cleaned = _flux2_klein_positive_contract_cleanup(prompt)

        self.assertTrue(cleaned.startswith("Human anatomy contract:"))
        self.assertIn("two legs", cleaned)
        self.assertIn("one left leg and one right leg per body", cleaned)
        self.assertIn("all visible people are adults wearing", cleaned)
        self.assertIn("mature adult faces", cleaned)
        self.assertIn("open-toe straw sandal straps", cleaned)
        self.assertIn("Wall and door areas are continuous", cleaned)
        self.assertIn("Door-side small detail inventory", cleaned)
        self.assertIn("Door hardware inventory", cleaned)
        self.assertIn("shallow round dark recessed pull rings", cleaned)
        self.assertIn("Sky area inventory", cleaned)
        self.assertIn("Eave inventory", cleaned)
        self.assertIn("Exterior eave-to-wall zones", cleaned)
        self.assertIn("Cloth sacks, armor chest plates, scabbards", cleaned)
        self.assertIn("Administrative record inventory", cleaned)
        self.assertIn("Footwear inventory", cleaned)
        self.assertIn("every visible foot front shows toes or straw sandal straps", cleaned)
        self.assertIn("Foreground and midground secondary figures", cleaned)
        self.assertIn("Basket carriers have long adult faces", cleaned)
        self.assertIn("Light plaster chips are irregular", cleaned)
        self.assertIn("Fine high-contrast fabric details merge into same-color fold shadows", cleaned)
        self.assertIn("Upper torso cloth from neckline to belt", cleaned)
        self.assertIn("Japanese textless surface contract", cleaned)
        self.assertIn("package faces", cleaned)
        self.assertIn("robe backs", cleaned)
        self.assertIn("Japanese open-air skyline contract", cleaned)
        self.assertIn("low fence rails", cleaned)
        self.assertIn("Japanese body-readability contract", cleaned)
        self.assertIn("Full-bleed composition", cleaned)
        self.assertIn("Weapon and tool inventory", cleaned)
        self.assertNotIn("hinge shadows", cleaned.lower())

    def test_flux2_klein_japanese_cleanup_rewrites_actual_bad_cut_triggers(self):
        prompt = (
            "Late Sengoku Japanese street scene with people, a child, a modern door knob, "
            "paper ledger sheets, white PVC pipe, rifle, kanji, hinge hardware, rain gutter, "
            "chimney pipe, crossbar utility pole, black boots, chest emblem, wall scroll, roadside sign, "
            "transmission tower, paper strip on face, robe back label, white garment chest label, "
            "box kanji stamp, detached feet under robe, and handgun-shaped object."
        )

        cleaned = _flux2_klein_positive_contract_cleanup(prompt)
        cleaned_lower = cleaned.lower()

        self.assertIn("adult villager", cleaned)
        self.assertIn("closed cord-tied packet", cleaned)
        self.assertIn("plain bamboo rod", cleaned)
        self.assertIn("plain yari spear or matchlock arquebus", cleaned)
        self.assertIn("flush recessed pull rings", cleaned)
        self.assertIn("sliding-panel groove shadows", cleaned)
        self.assertIn("soft gray roofline smoke haze with hidden bases", cleaned)
        self.assertIn("tree trunks, roof edges, and handheld spear shafts", cleaned)
        self.assertIn("low weathered roadside stones, rough fence rails, reeds, and dust", cleaned)
        self.assertIn("distant trees, mountain ridges, low roof edges, and smoke haze", cleaned)
        self.assertIn("skin planes, hairline shadow, cloth cap folds, and soft face shadow", cleaned)
        self.assertIn("plain wood grain, cord knots, cloth folds, wicker, rope fiber, and contact shadows", cleaned)
        self.assertIn("complete connected adult lower body under robe folds", cleaned)
        self.assertIn("tabi with visible open-toe waraji or zori straps", cleaned)
        self.assertIn("plain empty cloth, armor lacing, and material wear", cleaned)
        self.assertIn("short plain wooden tool handle", cleaned)
        for forbidden in (
            "child",
            "door knob",
            "paper",
            "ledger",
            "pvc",
            "rifle",
            "kanji",
            "hinge",
            "rain gutter",
            "chimney pipe",
            "utility pole",
            "black boots",
            "chest emblem",
            "wall scroll",
            "roadside sign",
            "transmission tower",
            "paper strip on face",
            "robe back label",
            "white garment chest label",
            "box kanji stamp",
            "detached feet",
            "handgun-shaped",
        ):
            self.assertNotIn(forbidden, cleaned_lower)

    def test_flux2_klein_japanese_negative_blocks_regen_artifacts(self):
        source = (
            "Year/period: late Sengoku; Exact place: Japan; "
            "Scene evidence: source workbook cut=107; "
            "Main subject: adult retainers moving through a Japanese lane; "
            "Scene: adult samurai and villagers pass wooden sliding doors"
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("shallow round dark recessed pull rings", compact)
        self.assertIn("open-toe sandal straps", compact)
        self.assertIn("Eaves show roof-tile ends", compact)
        self.assertIn("Eave-to-wall spaces", compact)
        for blocked in (
            "downspout",
            "elbow downspout",
            "vertical drain line under eave",
            "rain gutter",
            "roof drain pipe",
            "hand-height black rectangle on plaster",
            "white rectangular switch plate beside door",
            "white switch rectangle on exterior wall",
            "right-edge white switch plate",
            "eave-to-wall gray pipe",
            "modern vertical pull handle",
            "horizontal metal door handle",
            "closed black shoes",
            "closed dark footwear",
            "black boot shafts",
            "waist-high person",
            "child beside armored man",
            "child basket carrier",
            "small circular chest dot",
            "small colored chest patch",
            "tiny dark strokes on sack",
            "white border",
            "handgun-shaped object",
            "square framed object on tabletop",
            "small black rectangular tabletop plate",
            "modern tire",
            "roadside sign with writing",
            "transmission tower",
            "power pylon",
            "robe back label",
            "white garment chest label",
            "paper strip on face",
            "box kanji stamp",
            "hanging wall scroll",
            "detached feet under robe",
            "painted road lane markings",
            "asphalt road",
        ):
            self.assertIn(blocked, compact_negative)

    def test_flux2_klein_japanese_direct_workbench_discards_human_lock_prefix(self):
        prompt = (
            "People and officials stand in a Japanese scene. "
            "Top-down macro view of one continuous historical Japanese low wooden workbench "
            "filling the entire 16:9 image edge to edge. The frame contains only unbroken "
            "bare wood grain tabletop, tied plain cloth packets, one smooth plain sword scabbard "
            "or plain brush handle lying flat, dust, scratches, and contact shadows."
        )

        cleaned = _flux2_klein_positive_contract_cleanup(prompt)

        self.assertTrue(cleaned.startswith("Top-down Japanese tabletop still life"))
        self.assertIn("Top-down macro view", cleaned)
        self.assertNotIn("Door hardware inventory", cleaned)
        self.assertNotIn("Human anatomy contract", cleaned)
        self.assertNotIn("People and officials stand", cleaned)
        self.assertNotIn("adult runners", cleaned)
        self.assertNotIn("people, desks", cleaned)
        self.assertNotIn("person, lying on ground", cleaned)

    def test_flux2_klein_1944_red_quill_parchment_is_textless_object_closeup(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=137; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: A glowing red feather quill resting on blank thick parchment, dark aesthetic; "
            "Scene: A glowing red feather quill resting on blank thick parchment, dark aesthetic"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("one red feather quill resting diagonally", compact)
        self.assertIn("one completely blank thick cream parchment sheet", compact)
        self.assertIn("zero room background", compact)
        self.assertIn("zero bottles", compact)
        self.assertIn("zero line rows", compact)
        self.assertNotIn("laboratory interior", compact)
        self.assertNotIn("factory, garage, or industrial workshop", compact)
        self.assertNotIn("Early twentieth-century science and industry evidence", compact)
        self.assertIn("laboratory overview replacing quill", negative)
        self.assertIn("bottle labels", negative)
        self.assertIn("line rows on parchment", negative)

        guarded = prompt_builder.build_image_prompt(
            prompt,
            "serious adult graphic novel illustration",
            enable_historical_guard=True,
        )
        guarded_compact, guarded_negative = _compact_flux2_klein_4b_prompt(guarded, "")
        self.assertIn("one red feather quill resting diagonally", guarded_compact)
        self.assertIn("one completely blank thick cream parchment sheet", guarded_compact)
        self.assertIn("zero room background", guarded_compact)
        self.assertIn("zero bottles", guarded_compact)
        self.assertNotIn("laboratory interior", guarded_compact)
        self.assertNotIn("Early twentieth-century science and industry evidence", guarded_compact)
        self.assertIn("laboratory overview replacing quill", guarded_negative)
        self.assertIn("bottle labels", guarded_negative)

    def test_flux2_klein_ruined_battlefield_closing_stays_empty(self):
        prompt = (
            "Year/period: 1944 AD; Exact place: Worthington, Ohio (USA); "
            "Scene evidence: source workbook cut=149; period=1944 AD; "
            "place=Worthington, Ohio (USA); episode=The Inventor Strangled by His Own Genius: Thomas Midgley Jr.; "
            "Style: serious adult graphic novel illustration; "
            "Main subject: a dark closing shot of storm clouds over a ruined battlefield, stormy sky, dramatic and epic cinematic closing shot; "
            "Scene: a dark closing shot of storm clouds over a ruined battlefield, stormy sky, dramatic and epic cinematic closing shot"
        )
        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("wide empty ruined battlefield landscape", compact)
        self.assertIn("zero people", compact)
        self.assertIn("zero Japanese buildings", compact)
        self.assertIn("people in empty ruined battlefield", negative)
        self.assertIn("Japanese tiled roof", negative)

        guarded = prompt_builder.build_image_prompt(
            prompt,
            "serious adult graphic novel illustration",
            enable_historical_guard=True,
        )
        guarded_compact, guarded_negative = _compact_flux2_klein_4b_prompt(guarded, "")
        self.assertIn("wide empty ruined battlefield landscape", guarded_compact)
        self.assertNotIn("historical Japanese warrior society", guarded_compact)
        self.assertNotIn("Japanese forms", guarded_compact)
        self.assertNotIn("laboratory interior", guarded_compact)
        self.assertNotIn("office-lab room", guarded_compact)
        self.assertIn("people in empty ruined battlefield", guarded_negative)

    def test_flux2_klein_sui_goguryeo_salsu_cuts_stay_open_river(self):
        prompt = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Material culture: iron weapons, wooden halls, fortress walls, river crossings; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: The word 'Salsu' carved deeply into a bloody stone monument"
        )

        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertTrue(compact.startswith("612 CE Goguryeo-Sui open river battlefield"))
        self.assertIn("Goguryeo-Sui open river battlefield", compact)
        self.assertIn("muddy river crossing", compact)
        self.assertIn("unmarked blood-stained river stone", compact)
        self.assertNotIn("Liaodong Fortress", compact)
        self.assertNotIn("wooden halls", compact)
        self.assertNotIn("fortress walls", compact)
        self.assertNotIn("word 'Salsu'", compact)
        self.assertNotIn("readable text", compact)
        self.assertIn("fortress interior", negative)
        self.assertIn("word Salsu", negative)

    def test_flux2_klein_sui_goguryeo_final_negative_blocks_ch1_artifacts(self):
        source = (
            "Global visual world: Time range: 612year 6~7; Place scope: ancient Northeast Asia, "
            "Goguryeo-related court and frontier settings; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Material culture: iron weapons, "
            "bows, lamellar armor, hemp garments, riverbank mud, cold water, broken spear shafts; "
            "Year/period: 612 AD; Exact place: 612 Goguryeo-Sui open river battlefield, muddy river crossing; "
            "Scene: Eulji Mundeok stands at an outdoor riverbank command mat with closed cord-tied "
            "bamboo slip packets, blank bamboo slips, brush resting aside, Goguryeo officers, cold river water"
        )

        compact, _negative = _compact_flux2_klein_4b_prompt(source, "")
        final = _flux2_klein_md_positive_contract(_flux2_klein_positive_contract_cleanup(compact), source)
        negative = _flux2_klein_md_negative_contract(source, final)

        for blocked in (
            "cross-shaped pole",
            "utility crossarm",
            "doorpost plaque",
            "waist tag",
            "robe tag",
            "white label on clothing",
            "red gore chunk",
            "floating red corpse chunk",
            "blood slab",
            "white paper sheet",
            "open white paper sheet",
            "white rectangular page",
            "broad white paper face",
            "black marks on bamboo",
            "writing on bamboo",
            "ink strokes on bamboo slips",
            "hanging wooden tag",
            "characters on robe",
            "sleeve patch",
            "uniform badge",
        ):
            self.assertIn(blocked, negative)

    def test_flux2_klein_sui_goguryeo_positive_ignores_imjin_words_in_guard_text(self):
        source = (
            "Global visual world: Time range: 612year 6~7; Place scope: ancient Northeast Asia, "
            "Goguryeo-related court and frontier settings; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Material culture: iron weapons, "
            "bows, lamellar armor, hemp garments, riverbank mud, cold water, broken spear shafts; "
            "Year/period: 612 AD; Exact place: 612 Goguryeo-Sui open river battlefield, muddy river crossing; "
            "Scene evidence: open river water, muddy banks, broken spear shafts, torn lamellar armor, "
            "exhausted Sui soldiers, Goguryeo pressure from the bank, open sky, low hills; "
            "Main subject: Eulji Mundeok; Scene: Eulji Mundeok stands at an outdoor riverbank command mat "
            "with closed cord-tied bamboo slip packets, blank bamboo slips, brush resting aside, "
            "Goguryeo officers, cold river water behind them, muddy bank, low hills, and dusk wind"
        )
        guard_text = (
            "This is Korean history, not Joseon, modern Korea, medieval Japan, Ming, samurai, or fantasy Asia. "
            "Use exact Year/period and Exact place from the prompt."
        )

        guarded_source = source + " || " + guard_text
        compact, _negative = _compact_flux2_klein_4b_prompt(guarded_source, "")
        final = _flux2_klein_md_positive_contract(
            _flux2_klein_positive_contract_cleanup(compact),
            guarded_source,
        )

        self.assertIn("Eulji Mundeok", final)
        self.assertIn("Goguryeo-Sui", final)
        self.assertIn("unwritten tan bamboo", final)
        self.assertNotIn("late sixteenth-century Joseon", final)
        self.assertNotIn("Japanese, or Ming clothing", final)

    def test_flux2_klein_sui_goguryeo_scene_parser_ignores_guard_word_residue(self):
        source = (
            "Global visual world: Time range: 612year 6~7; Place scope: ancient Northeast Asia, "
            "Goguryeo-related court and frontier settings; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Material culture: iron weapons, "
            "bows, lamellar armor, hemp garments, riverbank mud, cold water, broken spear shafts; "
            "Year/period: 612 AD; Exact place: 612 Goguryeo-Sui open river battlefield, muddy river crossing; "
            "Scene evidence: open river water, muddy banks, broken spear shafts, torn lamellar armor, "
            "exhausted Sui soldiers, Goguryeo pressure from the bank, open sky, low hills; "
            "Main subject: Eulji Mundeok; Scene: Eulji Mundeok stands at an outdoor riverbank command mat "
            "with closed cord-tied bamboo slip packets, blank bamboo slips, brush resting aside, "
            "Goguryeo officers, cold river water behind them, muddy bank, low hills, and dusk wind"
        )
        guarded = (
            source
            + " || TEXTLESS SURFACE FIRST RULE: no readable word, no inscription panel, "
            "no carved word band, no written label."
        )

        compact, _negative = _compact_flux2_klein_4b_prompt(guarded, "")

        self.assertIn("Eulji Mundeok at an outdoor command mat", compact)
        self.assertIn("closed cord-tied bamboo slip packets", compact)
        self.assertNotIn("blood-stained river stone", compact)
        self.assertNotIn("stone monument", compact)

    def test_flux2_klein_sui_goguryeo_carriage_cut_uses_animal_drawn_cart(self):
        prompt = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: The Chinese emperor's carriage stuck in deep, freezing mud"
        )

        compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertTrue(compact.startswith("612 CE Goguryeo-Sui open river battlefield"))
        self.assertIn("animal-drawn open wooden command cart", compact)
        self.assertIn("spoked wooden wheels", compact)
        self.assertIn("muddy river crossing", compact)
        self.assertNotIn("Liaodong Fortress", compact)
        self.assertNotIn("carriage", compact.lower())
        self.assertIn("modern vehicle", negative)
        self.assertIn("glass window", negative)

    def test_flux2_klein_sui_goguryeo_emperor_cart_beats_collapsed_soldiers_contract(self):
        source = (
            "Global visual world: Time range: 612year 7; Place scope: Salsu River; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Material culture: iron weapons, bows, lamellar armor, hemp garments, riverbank mud, "
            "cold water, broken spear shafts, horse tack, rough open wooden carts, wet reeds, low hills; "
            "Year/period: 612 AD; Exact place: 612 Goguryeo-Sui open river battlefield, muddy river crossing; "
            "Scene evidence: open river water, muddy banks, broken spear shafts, torn lamellar armor, "
            "exhausted Sui soldiers, Goguryeo pressure from the bank, open sky, low hills; "
            "Main subject: Emperor Yang of Sui; "
            "Scene: Emperor Yang of Sui withdraws beside an animal-drawn open wooden command cart "
            "stuck in deep muddy open ground near a riverbank"
        )

        compact, _negative = _compact_flux2_klein_4b_prompt(source, "")
        final = _flux2_klein_md_positive_contract(_flux2_klein_positive_contract_cleanup(compact), source)

        self.assertIn("Emperor Yang of Sui beside an animal-drawn open wooden command cart", final)
        self.assertIn("spoked wooden wheels", final)
        self.assertIn("rope harnesses", final)
        self.assertNotIn("collapsed in a muddy swamp", final)

    def test_flux2_klein_sui_goguryeo_gold_trophies_do_not_route_to_open_river(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Material culture: iron weapons, wooden halls, fortress walls, river crossings; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: A massive mountain of gold and trophies, looking mocking"
        )

        compact, _negative = _compact_flux2_klein_4b_prompt(source, "")
        final = _flux2_klein_md_positive_contract(_flux2_klein_positive_contract_cleanup(compact), source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertNotIn("open river battlefield", compact)
        self.assertNotIn("exhausted Sui soldiers", final)
        self.assertIn("mocking mountain of captured Sui war loot", final)
        self.assertIn("dull gold pieces", final)
        self.assertIn("broken lamellar plates", final)
        self.assertIn("sports trophy cup", negative)
        self.assertIn("modern trophy", negative)

    def test_flux2_klein_md_positive_contract_keeps_final_positive_short(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: The word 'Salsu' carved deeply into a bloody stone monument"
        )
        compact, _negative = _compact_flux2_klein_4b_prompt(source, "")
        cleaned = _flux2_klein_positive_contract_cleanup(compact)
        final = _flux2_klein_md_positive_contract(cleaned, source)

        self.assertLessEqual(len(final), 900)
        self.assertTrue(final.startswith("early seventh-century; northeastern frontier fortress area"))
        self.assertLess(final.index("Render as"), final.index("Scene subject:"))
        self.assertIn("Scene subject: blood-dark plain stone monument", final)
        self.assertIn("rough unlettered stone slab", final)
        self.assertIn("Visible surface detail:", final)
        self.assertIn("wet stone texture", final)
        self.assertIn("Visible edge detail:", final)
        self.assertNotIn("Human anatomy contract", final)
        self.assertNotIn("Door-adjacent", final)
        self.assertNotIn("612", final)
        self.assertNotIn("graphic novel", final.lower())
        self.assertNotIn("Salsu", final)
        self.assertNotRegex(final.lower(), r"\b(?:zero|avoid|without|do not|forbidden|negative)\b")

    def test_flux2_klein_enemy_wave_is_not_rewritten_as_floodwater(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: A small group of defenders looking at an impossibly large enemy wave"
        )

        compact, _negative = _compact_flux2_klein_4b_prompt(source, "")
        final = _flux2_klein_md_positive_contract(_flux2_klein_positive_contract_cleanup(compact), source)

        self.assertNotIn("open river battlefield", compact)
        self.assertNotIn("floodwater", final.lower())
        self.assertIn("reaction close-up", final)

    def test_flux2_klein_md_positive_contract_removes_common_lock_stack(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: Endless rows of heavily armored infantry stretching to the horizon"
        )
        long_positive = (
            "Human anatomy contract: each visible adult has one head, one torso, two arms, two legs. "
            "Door-adjacent wall integrity contract: walls are material fields. "
            "612 AD Goguryeo and Sui military world at Liaodong frontier. "
            "Scene subject: Sui infantry. Visible action: endless rows of armored infantry march to the horizon. "
            "Visible inventory: lamellar armor, hemp garments, plain spears, dust, banners, packed earth. "
            "Composition: one coherent 16:9 documentary illustration frame. "
            "Render as a 2D adult graphic novel illustration with extra-thick black ink contour lines, bold silhouettes, hard shadow masses, matte cel shading, gritty brush texture, desaturated historical colors, and dark documentary lighting."
        )

        final = _flux2_klein_md_positive_contract(long_positive, source)

        self.assertLessEqual(len(final), 900)
        self.assertIn("Scene subject: dense Sui infantry formation", final)
        self.assertIn("Visible action: armored infantry march forward", final)
        self.assertLess(final.index("Render as"), final.index("Scene subject:"))
        self.assertIn("northeastern frontier", final)
        self.assertIn("full-bleed 2D historical ink-and-cel", final)
        self.assertIn("Visible surface detail:", final)
        self.assertIn("mud", final)
        self.assertNotIn("bare textured plaster", final)
        self.assertIn("Visible edge detail:", final)
        self.assertNotIn("Human anatomy contract", final)
        self.assertNotIn("Door-adjacent", final)
        self.assertNotIn("Liaodong Fortress", final)
        self.assertNotIn("612", final)
        self.assertNotIn("graphic novel", final.lower())

    def test_flux2_klein_md_major_character_entrance_uses_face_and_emotion(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene evidence: imperial Sui command clothing, throne wood, guards, stone hall shadows; "
            "Main subject: Emperor Yang of Sui; "
            "Scene: Emperor Yang of Sui gripping his throne, a cold glare in his eyes"
        )

        final = _flux2_klein_md_positive_contract("", source)

        self.assertLessEqual(len(final), 900)
        self.assertIn("Scene subject: Emperor Yang of Sui", final)
        self.assertIn("stylish medium-close entrance portrait", final)
        self.assertIn("intense eyes", final)
        self.assertIn("face and emotion dominate", final)
        self.assertIn("eye highlights", final)
        self.assertIn("plain cloth panels", final)
        self.assertIn("undecorated armor plates", final)
        self.assertNotIn("Liaodong Fortress", final)
        self.assertNotIn("612", final)
        self.assertNotRegex(final.lower(), r"\b(?:zero|avoid|without|do not|forbidden|negative)\b")

    def test_flux2_klein_md_major_character_entrance_preserves_source_emotion(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: A messenger bringing the news, Yuwen Shu looking completely devastated"
        )

        final = _flux2_klein_md_positive_contract("", source)

        self.assertLessEqual(len(final), 900)
        self.assertIn("Scene subject: Yuwen Shu", final)
        self.assertIn("stylish medium-close entrance portrait", final)
        self.assertIn("devastated expression", final)
        self.assertIn("visible shock", final)
        self.assertNotIn("controlled expression", final)

    def test_flux2_klein_md_sui_generic_emperor_becomes_character_entrance(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: An arrogant emperor wearing heavy gold robes, smirking, detailed"
        )

        final = _flux2_klein_md_positive_contract("", source)

        self.assertIn("Scene subject: Emperor Yang of Sui", final)
        self.assertIn("stylish medium-close entrance portrait", final)
        self.assertIn("local scene texture reaches all image edges and corners", final)
        self.assertIn("face and emotion dominate", final)

    def test_flux2_klein_md_sui_official_entrance_keeps_name_and_period_clothing(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: Liu Shirong stepping in, holding up a hand to stop the guards"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertLessEqual(len(final), 900)
        self.assertIn("Scene subject: Liu Shirong", final)
        self.assertIn("stylish medium-close entrance portrait", final)
        self.assertIn("face and emotion dominate", final)
        self.assertIn("pocketless hemp robe or tunic layers", final)
        self.assertIn("continuous plain chest fabric", final)
        self.assertIn("cloth sash", final)
        self.assertIn("tied hair or cloth headwrap", final)
        self.assertNotIn("Scene-named historical subject", final)
        self.assertIn("buttoned field jacket", negative)
        self.assertIn("modern cap", negative)

    def test_flux2_klein_md_siam_queen_entrance_does_not_add_armor(self):
        source = (
            "Global visual world: Time range: 1880 AD, late nineteenth-century Siam; "
            "Place scope: Chao Phraya River corridor, Bangkok waterways; "
            "Culture scope: Siamese royal court culture under the Chakri dynasty; "
            "Year/period: May 31, 1880; Exact place: royal boat on the Chao Phraya River system; "
            "Scene evidence: Queen Sunanda is introduced during the confirmed 1880 royal journey; "
            "Main subject: Queen Sunanda Kumariratana; "
            "Scene: Queen Sunanda Kumariratana stands on a royal boat, dignified but afraid"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertIn("Scene subject: Queen Sunanda Kumariratana", final)
        self.assertIn("layered period court cloth", final)
        self.assertIn("continuous plain chest fabric", final)
        self.assertIn("boat hull side panels read as blank lacquered wood grain", final)
        self.assertNotIn("undecorated armor plates", final)
        self.assertNotIn("armor plates", final)
        self.assertNotIn("worn metal", final)
        self.assertIn("armored queen", negative)
        self.assertIn("shoulder pauldrons", negative)
        self.assertIn("metal chest plate", negative)
        self.assertIn("lettering on hull", negative)
        self.assertIn("painted hull letters", negative)

    def test_flux2_klein_md_siam_palace_officials_get_court_clothing_not_hull_lock(self):
        source = (
            "Global visual world: Time range: 1880 AD, late nineteenth-century Siam; "
            "Place scope: Chao Phraya River corridor, Bangkok waterways, palace interiors; "
            "Culture scope: Siamese royal court culture under the Chakri dynasty; "
            "Year/period: 1880; Exact place: palace interior in Bangkok; "
            "Scene evidence: The story enters the court that must absorb the disaster.; "
            "Main subject: subdued palace officials; "
            "Scene: Officials in Siamese court dress hurry through a gilded hall"
        )

        final = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertIn("Scene subject: subdued palace officials", final)
        self.assertIn("nineteenth-century Siamese court clothing", final)
        self.assertIn("single continuous draped lower cloth", final)
        self.assertIn("bare ankles", final)
        self.assertIn("palace wall panels, lintels, door frames", final)
        self.assertNotIn("boat hull side panels", final)
        self.assertIn("modern military uniform", negative)
        self.assertIn("Western suit", negative)
        self.assertIn("collared shirt", negative)
        self.assertIn("separate trouser legs", negative)
        self.assertIn("peaked cap", negative)
        self.assertIn("armored palace guard", negative)
        self.assertIn("metal helmet", negative)
        self.assertIn("Thai script", negative)
        self.assertIn("vertical wall glyphs", negative)

    def test_flux2_klein_md_siam_empty_cushions_do_not_become_female_portrait(self):
        source = (
            "Global visual world: Time range: 1880 AD, late nineteenth-century Siam; "
            "Place scope: Chao Phraya River corridor, Bangkok waterways, palace interiors; "
            "Culture scope: Siamese royal court culture under the Chakri dynasty; "
            "Year/period: May 31, 1880; Exact place: royal interior with empty cushions; "
            "Scene evidence: Empty cushions symbolize the queen and princess; "
            "Main subject: empty cushions for queen and princess; "
            "Scene: Empty cushions sit in the royal interior, absence visible where the queen once belonged"
        )

        final = _flux2_klein_md_positive_contract(source, source)

        self.assertIn("Scene subject: empty cushions for queen and princess", final)
        self.assertIn("Empty cushions sit in the royal interior", final)
        self.assertNotIn("stylish medium-close entrance portrait", final)
        self.assertNotIn("adult woman", final)

    def test_flux2_klein_md_siam_parasol_shadow_becomes_soft_reflection(self):
        source = (
            "Global visual world: Time range: 1880 AD, late nineteenth-century Siam; "
            "Place scope: Chao Phraya River corridor, Bangkok waterways; "
            "Culture scope: Siamese royal court culture under the Chakri dynasty; "
            "Year/period: May 31, 1880; Exact place: final view of Chao Phraya River near royal route; "
            "Scene evidence: The final image carries the moral weight of the fatal river protocol.; "
            "Main subject: royal parasol shadow fading on river; "
            "Scene: A royal parasol shadow fades across dark water as the current carries the last gold fragment away"
        )

        final = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertIn("soft grey broken royal parasol reflection ripples across dark water", final)
        self.assertNotIn("royal parasol shadow fades across dark water", final)
        self.assertIn("black blob", negative)
        self.assertIn("solid black oval", negative)

    def test_flux2_klein_md_sui_general_laihu_er_entrance_keeps_name_and_period_clothing(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: General Laihu'er standing on the deck, looking greedy and ambitious"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertLessEqual(len(final), 900)
        self.assertIn("Scene subject: General Laihu'er", final)
        self.assertIn("stylish medium-close entrance portrait", final)
        self.assertIn("wooden deck", final)
        self.assertIn("pocketless hemp robe or tunic layers", final)
        self.assertIn("cloth sash", final)
        self.assertIn("tied hair or cloth headwrap", final)
        self.assertNotIn("Scene-named historical subject", final)
        self.assertIn("buttoned field jacket", negative)
        self.assertIn("modern cap", negative)

    def test_flux2_klein_md_toyotomi_hideyoshi_entrance_uses_face_and_emotion(self):
        source = (
            "Global visual world: Time range: 1592; Place scope: Hizen Nagoya Castle command area; "
            "Culture scope: Late Sengoku and early Toyotomi administration; "
            "Year/period: 1592; Exact place: Hizen Nagoya Castle command area; "
            "Scene evidence: plain command robe, low timber command room, messengers, lamplight; "
            "Main subject: Toyotomi Hideyoshi; "
            "Scene: stylish medium-close entrance of Toyotomi Hideyoshi with a controlled ambitious stare"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertLessEqual(len(final), 900)
        self.assertIn("Scene subject: Toyotomi Hideyoshi", final)
        self.assertIn("stylish medium-close entrance portrait", final)
        self.assertIn("face and emotion dominate", final)
        self.assertIn("ambitious stare", final)
        self.assertIn("formal late Sengoku command robe", final)
        self.assertIn("folding war fan", final)
        self.assertIn("tied topknot", final)
        self.assertNotIn("cloth headwrap", final)
        self.assertIn("worker apron", negative)
        self.assertIn("blacksmith workshop", negative)
        self.assertIn("wall calligraphy", negative)

    def test_flux2_klein_md_toyotomi_command_scene_blocks_worker_replacement(self):
        source = (
            "Global visual world: Time range: 1592-1598, late sixteenth century; "
            "Place scope: Japan, Joseon Korea, surrounding seas; "
            "Culture scope: Toyotomi Japan, Joseon Korea; "
            "Year/period: 1592; Exact place: Hizen Nagoya Castle command area; "
            "Scene evidence: samurai armor, matchlock guns, spears, naval ships; "
            "Main subject: Hideyoshi pointing toward the sea; "
            "Scene: Hideyoshi extends a fan toward the distant harbor, retainers lean forward, spears and matchlocks stacked nearby"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertIn("Toyotomi Hideyoshi on an open command terrace", final)
        self.assertIn("open command terrace", final)
        self.assertIn("visible sea", final)
        self.assertIn("formal command robe over armor", final)
        self.assertIn("folding war fan", final)
        self.assertIn("Japanese transport boats", final)
        self.assertIn("worker apron", negative)
        self.assertIn("forehead headband", negative)
        self.assertIn("indoor room replacing harbor", negative)

    def test_flux2_klein_md_toyotomi_daimyo_scene_is_not_misrouted_to_entrance(self):
        source = (
            "Global visual world: Time range: 1592-1598, late sixteenth century; "
            "Place scope: Japan, Joseon Korea, surrounding seas, Ming China borderlands; "
            "Culture scope: Toyotomi Japan, Joseon Korea, Ming China; "
            "Year/period: 1592; Exact place: dim strategy room in Hizen Nagoya Castle; "
            "Scene evidence: The invasion carried political pressure beyond a simple battlefield story.; "
            "Main subject: Hideyoshi before tense daimyo; "
            "Scene: Hideyoshi turns from a low table as daimyo exchange wary glances, armor cords and plain screens surrounding them"
        )

        final = _flux2_klein_md_positive_contract(
            "MASTER PROMPT mentions close-up and portrait as general style text.",
            source,
        )
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertIn("Toyotomi Hideyoshi before tense daimyo", final)
        self.assertIn("two kneeling daimyo", final)
        self.assertIn("uninterrupted dark wooden plank walls", final)
        self.assertNotIn("entrance portrait", final)
        self.assertIn("framed wall calligraphy", negative)
        self.assertIn("shoulder crest", negative)

    def test_flux2_klein_md_joseon_seonjo_procession_stays_royal_not_samurai(self):
        source = (
            "Global visual world: Time range: 1592-1598, late sixteenth century; "
            "Place scope: Joseon Korea; Culture scope: Toyotomi Japan, Joseon Korea; "
            "Year/period: 1592; Exact place: Hanseong palace gate; "
            "Main subject: royal procession leaving Hanseong; "
            "Scene: A hurried royal procession moves through a palace gate, guards shielding Seonjo as townspeople stare in fear"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertIn("King Seonjo's royal procession leaving Hanseong", final)
        self.assertIn("formal dark royal robe", final)
        self.assertIn("black court hat", final)
        self.assertIn("townspeople", final)
        self.assertIn("Japanese samurai armor replacing Joseon robe", negative)

    def test_flux2_klein_md_joseon_seonjo_entrance_is_tight_royal_closeup(self):
        source = (
            "Global visual world: Time range: 1592-1598, late sixteenth century; "
            "Place scope: Joseon Korea; Culture scope: Toyotomi Japan, Joseon Korea, Ming China; "
            "Year/period: 1592; Exact place: Joseon royal hall; "
            "Scene evidence: Seonjo was the Joseon king during the invasion crisis.; "
            "Main subject: King Seonjo of Joseon; "
            "Scene: stylish medium-close entrance of King Seonjo of Joseon, intense eyes, controlled expression, angled shoulders"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertIn("King Seonjo of Joseon", final)
        self.assertIn("tight head-and-chest entrance portrait", final)
        self.assertIn("black court hat", final)
        self.assertIn("formal royal robe", final)
        self.assertIn("wide gate procession replacing close-up", negative)
        self.assertIn("open document pages", negative)

    def test_flux2_klein_md_imjin_strategy_table_does_not_become_digging_scene(self):
        source = (
            "Global visual world: Time range: 1592-1598, late sixteenth century; "
            "Place scope: Japan and Joseon Korea; Culture scope: Toyotomi Japan, Joseon Korea, Ming China; "
            "Year/period: 1592; Exact place: Toyotomi command room; "
            "Main subject: commanders tracing a route with plain wooden markers; "
            "Scene: Commanders press plain wooden markers across a sand tray, their faces fixed, no readable markings on any surface"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertIn("Imjin War commanders planning a route on a sand-tray table", final)
        self.assertIn("small wooden route blocks", final)
        self.assertIn("sand grains", final)
        self.assertIn("digging laborers", negative)
        self.assertIn("water channel", negative)

    def test_flux2_klein_md_joseon_coast_uses_japanese_transport_boats_not_tall_ships(self):
        source = (
            "Global visual world: Time range: 1592-1598, late sixteenth century; "
            "Place scope: Joseon coast; Culture scope: Toyotomi Japan, Joseon Korea, Ming China; "
            "Year/period: 1592; Exact place: Joseon southern coast; "
            "Main subject: Joseon coast watchman spotting ships; "
            "Scene: A Joseon watchman in plain official clothing recoils from the shore, raising an arm toward approaching ships"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertIn("Joseon coast watchman spotting Japanese invasion transport boats", final)
        self.assertIn("low wooden Japanese transport boats", final)
        self.assertIn("European tall ship", negative)
        self.assertIn("galleon", negative)

    def test_flux2_klein_md_joseon_townspeople_with_ming_context_stays_civilian(self):
        source = (
            "Global visual world: Time range: 1592-1598, late sixteenth century; "
            "Place scope: Japan, Joseon Korea, surrounding seas, Ming China borderlands; "
            "Culture scope: Toyotomi Japan, Joseon Korea, Ming China; "
            "Year/period: 1592; Exact place: Hanseong market street; "
            "Main subject: Joseon townspeople before alarm; "
            "Scene: Merchants and families turn from simple stalls as a breathless rider bursts into the tiled street"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertIn("Joseon townspeople startled by invasion news", final)
        self.assertIn("merchants, families, and children", final)
        self.assertNotIn("sand-tray table", final)
        self.assertIn("armored cavalry patrol replacing civilians", negative)

    def test_flux2_klein_md_imjin_north_column_does_not_become_salsu_flood(self):
        source = (
            "Global visual world: Time range: 1592-1598, late sixteenth century; "
            "Place scope: Japan, Joseon Korea, surrounding seas, Ming China borderlands; "
            "Culture scope: Toyotomi Japan, Joseon Korea, Ming China; "
            "Year/period: 1592; Exact place: road north of Hanseong; "
            "Scene evidence: After taking Hanseong, Japanese forces continued moving northward.; "
            "Main subject: Japanese column pushing north; "
            "Scene: A long armored column climbs a dirt road, officers wave forward, pack animals strain under supplies"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertIn("Japanese column pushing north on a Joseon dirt road", final)
        self.assertIn("pack animals", final)
        self.assertNotIn("Salsu floodwater", final)
        self.assertIn("river drowning", negative)

    def test_flux2_klein_md_joseon_naval_commander_does_not_become_strategy_table(self):
        source = (
            "Global visual world: Time range: 1592-1598, late sixteenth century; "
            "Place scope: Japan, Joseon Korea, surrounding seas, Ming China borderlands; "
            "Culture scope: Toyotomi Japan, Joseon Korea, Ming China; "
            "Year/period: 1592; Exact place: southern Joseon coastal waters; "
            "Main subject: Joseon naval commander on warship; "
            "Scene: A stern Joseon officer leans over a ship rail, sailors pull oars hard as waves break around warships"
        )

        final = _flux2_klein_md_positive_contract("", source)

        self.assertIn("Joseon naval commander on a warship", final)
        self.assertIn("sailors pull oars", final)
        self.assertNotIn("sand-tray table", final)

    def test_flux2_klein_md_japanese_field_camp_does_not_become_coast_watchman(self):
        source = (
            "Global visual world: Time range: 1592-1598, late sixteenth century; "
            "Place scope: Japan, Joseon Korea, surrounding seas, Ming China borderlands; "
            "Culture scope: Toyotomi Japan, Joseon Korea, Ming China; "
            "Year/period: 1592; Exact place: Japanese inland field camp in Joseon; "
            "Scene evidence: Unstable sea routes affected soldiers far inland.; "
            "Main subject: hungry Japanese soldiers awaiting supplies; "
            "Scene: Exhausted soldiers crouch beside nearly empty baskets, an officer stares toward the coast with clenched jaw"
        )

        final = _flux2_klein_md_positive_contract("", source)

        self.assertIn("hungry Japanese soldiers awaiting supplies", final)
        self.assertIn("nearly empty baskets", final)
        self.assertNotIn("coast watchman", final)

    def test_flux2_klein_md_joseon_warships_do_not_become_strategy_table(self):
        source = (
            "Global visual world: Time range: 1592-1598, late sixteenth century; "
            "Place scope: Japan, Joseon Korea, surrounding seas, Ming China borderlands; "
            "Culture scope: Toyotomi Japan, Joseon Korea, Ming China; "
            "Year/period: 1592; Exact place: narrow coastal channel in southern Joseon; "
            "Main subject: Joseon warships closing on a supply route; "
            "Scene: Joseon ships cut across a narrow channel, rowers driving hard, Japanese supply boats turning in alarm"
        )

        final = _flux2_klein_md_positive_contract("", source)

        self.assertIn("Joseon warships closing on a Japanese supply route", final)
        self.assertIn("Japanese supply boats turn in alarm", final)
        self.assertNotIn("sand-tray table", final)

    def test_flux2_klein_md_hanseong_gate_keeps_troops_not_empty_beams(self):
        source = (
            "Global visual world: Time range: 1592-1598, late sixteenth century; "
            "Place scope: Joseon Korea; Culture scope: Toyotomi Japan, Joseon Korea; "
            "Year/period: 1592; Exact place: Hanseong capital gate; "
            "Main subject: Japanese troops entering Hanseong gate; "
            "Scene: Armored Japanese troops surge through the capital gate, matchlocks held high, abandoned carts scattered on the road"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertIn("Japanese troops entering Hanseong gate", final)
        self.assertIn("matchlocks held high", final)
        self.assertIn("abandoned carts", final)
        self.assertIn("empty timber structure", negative)
        self.assertIn("missing soldiers", negative)
        self.assertIn("upper gate sign", negative)

    def test_flux2_klein_md_joseon_officials_corridor_uses_closed_packets_no_beam_text(self):
        source = (
            "Global visual world: Time range: 1592-1598, late sixteenth century; "
            "Place scope: Joseon Korea; Culture scope: Toyotomi Japan, Joseon Korea, Ming China; "
            "Year/period: 1592; Exact place: Hanseong royal corridor; "
            "Main subject: palace officials receiving invasion news; "
            "Scene: Officials rush through a wooden corridor, sleeves flying, one messenger drops to his knees before startled ministers"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertIn("palace officials receiving invasion news", final)
        self.assertIn("closed cord-tied packet", final)
        self.assertIn("plain ceiling beams", final)
        self.assertIn("ceiling beam calligraphy", negative)
        self.assertIn("open document in corridor", negative)

    def test_flux2_klein_md_seonjo_council_crops_side_wall_art(self):
        source = (
            "Global visual world: Time range: 1592-1598, late sixteenth century; "
            "Place scope: Joseon Korea; Culture scope: Toyotomi Japan, Joseon Korea, Ming China; "
            "Year/period: 1592; Exact place: Joseon royal hall; "
            "Main subject: Seonjo and ministers in crisis council; "
            "Scene: Seonjo grips a sleeve while ministers argue silently with tense hands, low tables and mats crowded around them"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertIn("King Seonjo and Joseon ministers in crisis council", final)
        self.assertIn("low wooden tables filling the foreground", final)
        self.assertIn("broad plain plaster-and-wood rear panels", final)
        self.assertIn("low tables and robed bodies block side walls", final)
        self.assertIn("all flat surfaces and corners stay as continuous", final)
        self.assertIn("framed landscape painting", negative)
        self.assertIn("door-side placard", negative)
        self.assertIn("visible document text", negative)

    def test_flux2_klein_md_imjin_supply_scene_blocks_crate_labels_and_wall_art(self):
        source = (
            "Global visual world: Time range: 1592-1598, late sixteenth century; "
            "Place scope: Joseon Korea; Culture scope: Toyotomi Japan, Joseon Korea, Ming China; "
            "Year/period: 1592; Exact place: Japanese inland field camp in Joseon; "
            "Main subject: stacked military supplies under guard; "
            "Scene: Rice sacks, spear bundles, matchlock powder boxes, and armor cords sit under anxious guards near rough tents"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertIn("stacked Imjin War military supplies under guard", final)
        self.assertIn("rope-wrapped powder bundles", final)
        self.assertIn("sacks and rope-wrapped bundles dominate", final)
        self.assertNotIn("bare crate faces", final)
        self.assertIn("crate label", negative)
        self.assertIn("box label", negative)
        self.assertIn("sack emblem", negative)
        self.assertIn("upper-left calligraphy cluster", negative)
        self.assertIn("lower-left watermark", negative)
        self.assertIn("framed landscape painting", negative)
        self.assertIn("posted paper", negative)

    def test_flux2_klein_md_imjin_cracked_bowl_uses_closed_reports(self):
        source = (
            "Global visual world: Time range: 1592-1598, late sixteenth century; "
            "Place scope: Hizen Nagoya Castle command area; "
            "Culture scope: Toyotomi Japan, Joseon Korea, Ming China; "
            "Year/period: 1598; Exact place: Toyotomi command chamber; "
            "Main subject: cracked ceramic bowl beside war gear; "
            "Scene: A cracked tea bowl rests beside worn armor and sealed blank reports, candlelight catching the fracture"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertIn("cracked ceramic bowl beside Imjin War gear", final)
        self.assertIn("closed cord-tied packet bundles", final)
        self.assertIn("closed cord-tied cloth packet bundles", final)
        self.assertNotIn("report bundles", final)
        self.assertNotIn("open paper", final)
        self.assertIn("visible document text", negative)
        self.assertIn("report writing", negative)

    def test_flux2_klein_md_imjin_armory_does_not_route_to_ming_negotiation(self):
        source = (
            "Global visual world: Time range: 1592-1598, late sixteenth century; "
            "Place scope: Japan, Joseon Korea, surrounding seas, Ming China borderlands; "
            "Culture scope: Toyotomi Japan, Joseon Korea, Ming China; "
            "Year/period: 1596-1597; Exact place: Japanese armory near Hizen Nagoya Castle; "
            "Scene evidence: Renewed military preparations followed the failure of negotiations.; "
            "Main subject: armor and weapons being prepared again; "
            "Scene: Armorers tighten cords on helmets and stack spears, soldiers watching with grim resignation in lamplight"
        )

        final = _flux2_klein_md_positive_contract("", source)

        self.assertIn("Imjin War armor and weapons being prepared again", final)
        self.assertIn("armorers tighten helmet cords", final)
        self.assertNotIn("Ming officials interpreting", final)

    def test_flux2_klein_md_imjin_displaced_villagers_do_not_become_market_scene(self):
        source = (
            "Global visual world: Time range: 1592-1598, late sixteenth century; "
            "Place scope: Joseon Korea; Culture scope: Toyotomi Japan, Joseon Korea, Ming China; "
            "Year/period: 1597; Exact place: rainy rural road in southern Joseon; "
            "Main subject: displaced villagers on a rainy road; "
            "Scene: Families bend against rain with bundles on their backs, stepping off the main road toward muddy fields"
        )

        final = _flux2_klein_md_positive_contract("", source)

        self.assertIn("Joseon villagers facing renewed Imjin War damage", final)
        self.assertIn("salvaged bundles", final)
        self.assertNotIn("market stalls", final)

    def test_flux2_klein_md_valentinian_entrance_uses_face_and_emotion(self):
        source = (
            "Global visual world: Time range: 375 AD; Place scope: Late Roman Danube frontier; "
            "Culture scope: Late Roman imperial command world; "
            "Year/period: 375 AD; Exact place: Brigetio command camp; "
            "Scene evidence: imperial military cloak, plain oval shields, spear shafts, command tent; "
            "Main subject: Valentinian I; "
            "Scene: stylish medium-close entrance of Valentinian I with furious eyes and clenched shoulders"
        )

        final = _flux2_klein_md_positive_contract("", source)

        self.assertLessEqual(len(final), 900)
        self.assertIn("Scene subject: Emperor Valentinian I", final)
        self.assertIn("stylish medium-close entrance portrait", final)
        self.assertIn("furious expression", final)
        self.assertIn("face and emotion dominate", final)

    def test_flux2_klein_md_soldier_eye_closeup_uses_period_clothing(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: A close-up of a soldier's hollow, terrified, and starving eyes"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertLessEqual(len(final), 900)
        self.assertIn("Scene subject: terrified starving Sui soldier", final)
        self.assertIn("hollow terrified starving eyes", final)
        self.assertIn("cloth headwrap", final)
        self.assertIn("pocketless hemp tunic layers", final)
        self.assertIn("lamellar shoulder plates", final)
        self.assertNotIn("Scene-named historical subject", final)
        self.assertIn("modern combat helmet", negative)
        self.assertIn("brimmed combat helmet", negative)
        self.assertIn("buttoned uniform sleeve", negative)

    def test_flux2_klein_md_earth_master_sarcasm_avoids_firearms(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: A sarcastic illustration of a master of the earth"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertLessEqual(len(final), 900)
        self.assertIn("arrogant Sui field tactician mocked by mud", final)
        self.assertIn("survey cord", final)
        self.assertIn("wooden stakes", final)
        self.assertIn("pocketless hemp robe", final)
        self.assertNotIn("Scene-named historical subject", final)
        self.assertNotIn("iron, water, smoke", final)
        self.assertIn("cannon", negative)
        self.assertIn("firearm", negative)
        self.assertIn("modern jacket", negative)

    def test_flux2_klein_md_generals_reading_poem_keeps_faces_and_period_sleeves(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: The Sui generals reading the poem, their eyes wide with realization"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertLessEqual(len(final), 900)
        self.assertIn("two Sui generals reading a blank cord-tied bamboo slip bundle", final)
        self.assertIn("wide shocked eyes", final)
        self.assertIn("narrow blank bamboo strips", final)
        self.assertIn("pocketless hemp robe sleeves", final)
        self.assertIn("faces and realization dominate", final)
        self.assertNotIn("plain sealed war message evidence", final)
        self.assertIn("modern suit sleeve", negative)
        self.assertIn("white shirt cuff", negative)
        self.assertIn("red push button", negative)
        self.assertIn("red seal stamp", negative)
        self.assertIn("tiny glyphs", negative)

    def test_flux2_klein_md_crumpled_warning_slip_falls_into_mud_without_seals(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: A crumpled piece of paper falling into the mud"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertLessEqual(len(final), 900)
        self.assertIn("crumpled blank fiber warning slip falling into wet mud", final)
        self.assertIn("muddy puddle", final)
        self.assertIn("tight low ground", final)
        self.assertNotIn("rough wooden table", final)
        self.assertNotIn("wax seal", final)
        self.assertNotIn("paper", final.lower())
        self.assertIn("red seal stamp", negative)
        self.assertIn("black ink marks", negative)

    def test_flux2_klein_md_red_flags_use_open_ridges_not_fortress_walls(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: Red flags waving under a dark, stormy sky"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertLessEqual(len(final), 900)
        self.assertIn("empty open mountain ridgelines with plain red signal flags", final)
        self.assertIn("natural ridges", final)
        self.assertIn("muddy stream", final)
        self.assertNotIn("fortress wall", final.lower())
        self.assertIn("fortress wall", negative)
        self.assertIn("flag letters", negative)
        self.assertIn("flag bearer", negative)

    def test_flux2_klein_md_arrow_rain_avoids_firearms_and_boulders(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: A rain of black arrows falling on the retreating soldiers"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertLessEqual(len(final), 900)
        self.assertIn("open muddy river valley and reed banks", final)
        self.assertIn("black arrow rain striking retreating Sui soldiers", final)
        self.assertIn("feather fletching", final)
        self.assertIn("iron arrowheads", final)
        self.assertNotIn("fortress wall", final.lower())
        self.assertNotIn("boulders", final)
        self.assertNotIn("projectiles", final.lower())
        self.assertIn("muzzle flash", negative)
        self.assertIn("cannon barrel", negative)
        self.assertIn("stone projectile", negative)
        self.assertIn("fortress wall", negative)

    def test_flux2_klein_md_fleeing_soldiers_drop_armor_uses_open_mud(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: Soldiers dropping their heavy armor and running in sheer terror"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertLessEqual(len(final), 900)
        self.assertIn("open muddy river valley and reed banks", final)
        self.assertIn("terrified Sui soldiers shedding armor while fleeing", final)
        self.assertIn("dropping lamellar armor plates", final)
        self.assertIn("pocketless hemp tunics", final)
        self.assertNotIn("fortress wall", final.lower())
        self.assertIn("fortress wall", negative)
        self.assertIn("bucket", negative)
        self.assertIn("cargo pocket", negative)

    def test_flux2_klein_md_cavalry_chase_uses_open_battlefield_and_period_tack(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: Goguryeo cavalry ruthlessly chasing down the fleeing enemies"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertLessEqual(len(final), 900)
        self.assertIn("open muddy river valley and reed banks", final)
        self.assertIn("Goguryeo cavalry chasing fleeing Sui soldiers", final)
        self.assertIn("period horses with full bodies and legs", final)
        self.assertIn("cloth headwraps", final)
        self.assertNotIn("fortress wall", final.lower())
        self.assertIn("cowboy hat", negative)
        self.assertIn("western saddle", negative)
        self.assertIn("fortress wall", negative)

    def test_flux2_klein_md_muddy_valley_slaughter_avoids_gun_barrels(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: A brutal, one-sided slaughter in a muddy valley"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertLessEqual(len(final), 900)
        self.assertIn("open muddy valley with shallow water and reed banks", final)
        self.assertIn("one-sided Goguryeo pursuit crushing exhausted Sui soldiers", final)
        self.assertIn("plain spear shafts", final)
        self.assertIn("bows, arrows", final)
        self.assertNotIn("fortress wall", final.lower())
        self.assertIn("gun barrel", negative)
        self.assertIn("long metal tube", negative)
        self.assertIn("fortress wall", negative)

    def test_flux2_klein_md_blood_rocky_landscape_uses_aftermath_evidence(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: Blood splattering across the cold, rocky landscape"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertLessEqual(len(final), 900)
        self.assertIn("blood-spattered cold rocks and mud after the rout", final)
        self.assertIn("dark red splashes", final)
        self.assertIn("low 16:9 aftermath evidence crop", final)
        self.assertNotIn("soldiers struggle", final.lower())
        self.assertIn("crowded soldier crossing", negative)
        self.assertIn("chest pocket", negative)
        self.assertIn("fortress wall", negative)

    def test_flux2_klein_md_broken_banner_blood_pool_lies_flat(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: A broken Chinese dragon banner resting in a pool of blood"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertLessEqual(len(final), 900)
        self.assertIn("broken Sui dragon banner collapsed in a blood pool", final)
        self.assertIn("banner cloth lies flat", final)
        self.assertIn("snapped wooden pole", final)
        self.assertNotIn("vertical standard", final.lower())
        self.assertNotIn("fortress wall", final.lower())
        self.assertIn("upright pole", negative)
        self.assertIn("characters on banner", negative)

    def test_flux2_klein_md_dirt_mountain_keeps_siege_mound_and_wall(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: A massive dirt mountain being built next to a high stone wall"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertLessEqual(len(final), 900)
        self.assertIn("massive packed-earth siege mound", final)
        self.assertIn("high stone wall", final)
        self.assertIn("workers and soldiers haul baskets of dirt", final)
        self.assertNotIn("cropped granite defense-block field", final)
        self.assertNotIn("view through", final.lower())
        self.assertIn("stone border frame", negative)
        self.assertIn("view through stone window", negative)
        self.assertNotIn("full fortress wall", negative)

    def test_flux2_klein_md_goguryeo_dust_charge_avoids_gate_frame_and_firearms(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: Goguryeo warriors charging out of a dust cloud with weapons raised"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertLessEqual(len(final), 900)
        self.assertIn("elite Goguryeo warriors bursting out of a dust cloud", final)
        self.assertIn("plain spears and short swords raised", final)
        self.assertIn("pocketless hemp tunics", final)
        self.assertIn("mud, bodies, weapon shafts, smoke, dust, and open air reach all image edges", final)
        self.assertNotIn("Scene-named historical subject", final)
        self.assertIn("cannon barrel", negative)
        self.assertIn("long metal tube", negative)
        self.assertIn("wooden doorway frame", negative)
        self.assertIn("view through gate", negative)
        self.assertIn("stone border frame", negative)

    def test_flux2_klein_md_helmet_mud_scene_uses_tight_ground_crop(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: A shattered Chinese war helmet resting in deep mud, dark clouds"
        )

        final = _flux2_klein_md_positive_contract("", source)

        self.assertLessEqual(len(final), 900)
        self.assertIn("cracked Sui war helmet half-buried in mud", final)
        self.assertIn("tight ground-level 16:9 crop", final)
        self.assertIn("mud, reeds, and water reach all image edges and corners", final)
        self.assertNotIn("clouded sky", final)

    def test_flux2_klein_md_soldier_collapse_does_not_use_female_guard_text(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: Exhausted soldiers collapsing in a freezing, dark swamp"
        )
        guard_text = "adult female subjects have a beautiful silhouette and confident eyes."

        final = _flux2_klein_md_positive_contract(guard_text, source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertIn("exhausted Sui infantrymen collapsed in a muddy swamp", final)
        self.assertIn("tight low 16:9 ground crop", final)
        self.assertNotIn("adult woman", final)
        self.assertIn("female warrior", negative)

    def test_flux2_klein_md_strategy_board_uses_tight_tabletop_crop(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: A massive military strategy board covered with thousands of pieces"
        )

        final = _flux2_klein_md_positive_contract("", source)

        self.assertLessEqual(len(final), 900)
        self.assertIn("cord-and-stone military strategy tabletop", final)
        self.assertIn("tight tabletop 16:9 crop", final)
        self.assertIn("lower-right corner is local shadow or wood grain", final)

    def test_flux2_klein_md_chessboard_metaphor_becomes_tactile_marker_tabletop(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: A dark chessboard, a single piece moving forward"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertLessEqual(len(final), 900)
        self.assertIn("cord-and-stone psychological war marker tabletop", final)
        self.assertIn("one dark stone marker advances along a loose route cord", final)
        self.assertIn("separated pebbles", final)
        self.assertNotRegex(final.lower(), r"\b(?:chess|chessboard|pawn|checkerboard|go board|modern board game)\b")
        self.assertIn("chessboard", negative)
        self.assertIn("miniature chess pieces", negative)

    def test_flux2_klein_md_temple_looting_uses_plain_frontier_timber_shrine(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: Sui soldiers dropping their weapons and looting a seemingly empty temple"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertLessEqual(len(final), 900)
        self.assertIn("plain early frontier timber temple yard", final)
        self.assertIn("low plain timber shrine", final)
        self.assertIn("simple wooden roof", final)
        self.assertIn("dropped spears", final)
        self.assertNotRegex(final.lower(), r"\b(?:ornate|tiled|pavilion|palace)\b")
        self.assertIn("ornate tiled palace roof", negative)
        self.assertIn("later dynasty pavilion", negative)

    def test_flux2_klein_md_geonmu_heavy_cavalry_keeps_mounted_entrance(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: Prince Geonmu leading fully armored heavy cavalry out of the shadows"
        )

        final = _flux2_klein_md_positive_contract("", source)

        self.assertLessEqual(len(final), 900)
        self.assertIn("Scene subject: Prince Geonmu leading armored Goguryeo heavy cavalry", final)
        self.assertIn("rides a dark period horse", final)
        self.assertIn("one foreground horse with head, neck, torso, four legs, tail", final)
        self.assertIn("cavalry silhouettes following behind", final)
        self.assertIn("leader face readable", final)
        self.assertNotIn("Scene-named historical subject", final)
        self.assertNotRegex(final.lower(), r"\b(?:signboard|plaque|gate title)\b")

    def test_flux2_klein_md_arpad_hungary_mounted_scene_does_not_use_goguryeo_contract(self):
        source = (
            "Global visual world: Time range: 1057-1063 AD; Place scope: Kingdom of Hungary; "
            "Culture scope: Árpád-era Hungarian royal court, Latin Christian monarchy, "
            "dynastic politics between Hungary, Poland, and the German kingdom within the Holy Roman imperial sphere; "
            "Year/period: 1063; Exact place: muddy western road approaching Hungary; "
            "Main subject: mounted messengers racing from the western frontier; "
            "Scene: Mud-splashed riders whip tired horses past timber watch posts, "
            "mail shirts flashing beneath heavy travel cloaks."
        )

        final = _flux2_klein_md_positive_contract("", source)

        self.assertIn("mounted messengers racing from the western frontier", final)
        self.assertIn("Mud-splashed riders whip tired horses", final)
        self.assertIn("flexible chainmail ring mesh", final)
        self.assertNotIn("Goguryeo", final)
        self.assertNotIn("Sui", final)
        self.assertNotIn("lamellar", final.lower())

    def test_flux2_klein_arpad_hungary_context_does_not_become_1190_crusader_world(self):
        source = (
            "Global visual world: Time range: 1057-1063 AD; Place scope: Kingdom of Hungary; "
            "Culture scope: Árpád-era Hungarian royal court, Latin Christian monarchy, "
            "dynastic politics between Hungary, Poland, and the German kingdom within the Holy Roman imperial sphere; "
            "Material culture: 11th-century Central European wool tunics, heavy cloaks, leather belts, "
            "mail shirts, nasal helmets, round shields, spears, swords, wooden royal halls, Romanesque stone churches; "
            "Year/period: 1063; Exact place: royal timber hall at Dömös near the Danube bend; "
            "Main subject: damaged royal seat beneath a falling timber canopy; "
            "Scene: Carved wooden seat buckles under a heavy canopy as mail-clad guards lunge forward inside a torchlit royal hall."
        )

        compact, compact_negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Arpad-era Kingdom of Hungary", compact)
        self.assertIn("eleventh-century Hungarian", compact)
        self.assertIn("flexible chainmail ring mesh", compact)
        self.assertIn("round shields", compact)
        self.assertNotIn("1190 AD high-medieval", compact)
        self.assertNotIn("Latin crusading", compact)
        self.assertNotIn("Goguryeo", compact)
        self.assertIn("full plate armor", compact_negative)
        self.assertIn("scale armor", compact_negative)

    def test_flux2_klein_arpad_danube_gate_scene_does_not_trigger_brigetio_transport(self):
        source = (
            "Global visual world: Time range: 1057-1063 AD; Place scope: Kingdom of Hungary, "
            "especially Dömös near the Danube bend; "
            "Culture scope: Árpád-era Hungarian royal court, Latin Christian monarchy; "
            "Material culture: 11th-century Central European wool tunics, heavy cloaks, leather belts, "
            "mail shirts, nasal helmets, round shields, spears, swords, wooden royal halls; "
            "Year/period: 1063; Exact place: entrance to Dömös royal residence; "
            "Main subject: Hungarian nobles entering Dömös with weapons; "
            "Scene: Cloaked nobles hurry through a timber gate, servants clutching shields and spears behind them in cold mist."
        )

        compact, _negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Hungarian nobles entering the timber royal residence with weapons", compact)
        self.assertIn("servants clutching shields and spears", compact)
        self.assertNotIn("Brigetio", compact)
        self.assertNotIn("375 AD", compact)
        self.assertNotIn("river crews haul", compact)

    def test_flux2_klein_arpad_polish_cavalry_camp_does_not_trigger_late_roman_punitive_camp(self):
        source = (
            "Global visual world: Time range: 1057-1063 AD, with consequence framing reaching 1074 AD; "
            "Place scope: Kingdom of Hungary, especially Dömös, the western frontier, Poland, "
            "and German royal approaches through Central Europe; "
            "Culture scope: Árpád-era Hungarian royal court, Latin Christian monarchy, dynastic politics "
            "between Hungary, Poland, and the German kingdom within the Holy Roman imperial sphere; "
            "Material culture: 11th-century Central European wool tunics, heavy cloaks, leather belts, "
            "mail shirts, nasal helmets, round shields, spears, swords, wooden royal halls, "
            "timber palisades, horse columns, wax-sealed parchments; "
            "Year/period: 1060; Central European frontier warfare, 1060 AD; "
            "Exact place: Polish military camp near the Hungarian border; "
            "Main subject: Polish cavalry assembling for Béla; "
            "Scene: Polish riders tighten mail coifs and lift spears while Béla confers beside loaded packhorses."
        )

        compact, _negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("Arpad-era Kingdom of Hungary", compact)
        self.assertIn("Polish cavalry assembling for Béla", compact)
        self.assertIn("lift spears", compact)
        self.assertNotIn("375 AD", compact)
        self.assertNotIn("Late Roman", compact)
        self.assertNotIn("Pannonian", compact)
        self.assertNotIn("Roman soldiers", compact)

    def test_flux2_klein_arpad_named_place_courtyard_uses_plain_timbers_not_signboards(self):
        source = (
            "Global visual world: Time range: 1057-1063 AD; Place scope: Kingdom of Hungary, especially Dömös; "
            "Culture scope: Árpád-era Hungarian royal court, Latin Christian monarchy; "
            "Material culture: 11th-century Central European wool tunics, mail shirts, nasal helmets, round shields; "
            "Year/period: 1063; Exact place: Dömös courtyard after the accident; "
            "Main subject: messenger summoning Béla's sons; "
            "Scene: A messenger leaps onto a horse outside Dömös, clutching a sealed pouch as retainers shout orders."
        )

        compact, negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("outside the timber royal residence", compact)
        self.assertIn("rough timber walls", compact)
        self.assertNotIn("outside Dömös", compact)
        self.assertNotIn("1057-1063", compact)
        self.assertIn("overdoor plaque", negative)
        self.assertIn("date plaque", negative)

    def test_flux2_klein_arpad_document_scene_uses_edge_on_blank_packets(self):
        source = (
            "Global visual world: Time range: 1057-1063 AD; Place scope: Kingdom of Hungary; "
            "Culture scope: Árpád-era Hungarian royal court, Latin Christian monarchy; "
            "Material culture: 11th-century Central European wool tunics, mail shirts, nasal helmets, round shields; "
            "Year/period: 1063; Exact place: monastic writing room recording Hungarian royal events; "
            "Main subject: scribe preserving the Dömös account; "
            "Scene: A monk bends over blank-angled parchment while a broken wooden chair is sketched only as a simple object nearby."
        )

        compact, negative = _compact_flux2_klein_4b_prompt(source, "")

        self.assertIn("closed cloth-wrapped bundles", compact)
        self.assertIn("wax seal lumps", compact)
        self.assertNotIn("blank-angled parchment", compact)
        self.assertNotIn("parchment", compact.lower())
        self.assertIn("page rows", negative)
        self.assertIn("black marks on parchment", negative)

    def test_flux2_klein_arpad_news_scene_uses_sealed_cloth_packet(self):
        source = (
            "Global visual world: Time range: 1057-1063 AD; Place scope: Kingdom of Hungary, especially Dömös; "
            "Culture scope: Árpád-era Hungarian royal court, Latin Christian monarchy; "
            "Material culture: 11th-century Central European wool tunics, wax-sealed parchments, simple crowns; "
            "Year/period: c. 1058-1060; Exact place: Béla's ducal lodging near the royal court; "
            "Main subject: Béla studying news from the western court; "
            "Scene: Béla bends over a sealed parchment while armed retainers exchange worried glances under low beams."
        )

        compact, _ = _compact_flux2_klein_4b_prompt(source, "")
        final = _flux2_klein_md_positive_contract(compact, source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertIn("sealed cord-tied cloth packet with a wax lump", final)
        self.assertIn("cord-tied cloth packet edges", final)
        self.assertIn("cloth cloak shoulders", final)
        self.assertIn("bare hands and plain wool sleeve cuffs", final)
        self.assertIn("wool-tunic retainers holding plain spear shafts", final)
        self.assertNotIn("armed retainers", final)
        self.assertNotRegex(final.lower(), r"\b(?:news|message|parchment|document|paper|page)\b")
        self.assertIn("open flat sheet", negative)
        self.assertIn("broad cream paper face", negative)
        self.assertIn("plate vambrace", negative)
        self.assertIn("studded bracer", negative)
        self.assertIn("metal forearm armor", negative)

    def test_flux2_klein_arpad_treaty_cloth_scene_stays_plain_cloth(self):
        source = (
            "Global visual world: Time range: 1057-1063 AD; Place scope: Kingdom of Hungary, especially Dömös; "
            "Culture scope: Árpád-era Hungarian royal court, Latin Christian monarchy; "
            "Material culture: 11th-century Central European wool tunics, mail shirts, nasal helmets, round shields; "
            "Year/period: 1062-1063; Exact place: royal council hall at Dömös or Székesfehérvár; "
            "Main subject: Béla facing four visible political pressures; "
            "Scene: Béla stands before nobles while a treaty cloth, travel pack, sword, and crown divide the table."
        )

        compact, _ = _compact_flux2_klein_4b_prompt(source, "")
        final = _flux2_klein_md_positive_contract(compact, source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertIn("physical pressure objects", final)
        self.assertIn("plain folded cloth strip", final)
        self.assertIn("cord-tied cloth packet edges", final)
        self.assertIn("one simple iron sword", final)
        self.assertIn("one plain metal crown", final)
        self.assertNotRegex(final.lower(), r"\b(?:treaty|parchment|document|paper|page|message)\b")
        self.assertNotIn("period-local sword", final)
        self.assertIn("open treaty document", negative)
        self.assertIn("exposed document face", negative)
        self.assertIn("second sword", negative)
        self.assertIn("flower badge", negative)

    def test_flux2_klein_arpad_campaign_reports_use_plain_sleeves_and_soft_caps(self):
        source = (
            "Global visual world: Time range: 1057-1063 AD; Place scope: Kingdom of Hungary, especially Dömös; "
            "Culture scope: Árpád-era Hungarian royal court, Latin Christian monarchy; "
            "Material culture: 11th-century Central European wool tunics, heavy cloaks, mail shirts, nasal helmets, round shields; "
            "Year/period: 1062-1063; Exact place: Béla's royal hall after campaign reports; "
            "Main subject: Béla standing over campaign reports; "
            "Scene: Béla plants both hands on a table of sealed orders as captains nod beside stacked shields."
        )

        compact, _ = _compact_flux2_klein_4b_prompt(source, "")
        final = _flux2_klein_md_positive_contract(compact, source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertIn("plain wool sleeve cuffs", final)
        self.assertIn("wool-cloaked captains with cloth hoods or bare hair", final)
        self.assertIn("one stacked round wooden shield", final)
        self.assertNotIn("soft caps", final)
        self.assertNotIn("mail sleeve rings", final)
        self.assertIn("helmet badge", negative)
        self.assertIn("peaked cap", negative)
        self.assertIn("metal forearm armor", negative)

    def test_flux2_klein_arpad_panic_orders_use_one_table_sword(self):
        source = (
            "Global visual world: Time range: 1057-1063 AD; Place scope: Kingdom of Hungary, especially Dömös; "
            "Culture scope: Árpád-era Hungarian royal court, Latin Christian monarchy; "
            "Material culture: 11th-century Central European wool tunics, heavy cloaks, mail shirts, nasal helmets, round shields; "
            "Year/period: 1063; Exact place: Dömös council table during panic; "
            "Main subject: nobles abandoning crisis plans; "
            "Scene: Nobles shove aside sealed orders and weapons as panic pulls them away from the council table."
        )

        compact, _ = _compact_flux2_klein_4b_prompt(source, "")
        final = _flux2_klein_md_positive_contract(compact, source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertIn("one plain sheathed iron sword on the council table", final)
        self.assertIn("sealed cord-tied cloth packets", final)
        self.assertNotIn("weapons as panic", final)
        self.assertNotIn("mail sleeve rings", final)
        self.assertIn("crossed swords", negative)
        self.assertIn("cap badge", negative)

    def test_flux2_klein_md_sui_sailor_chaos_uses_period_clothing_and_deck(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: Absolute chaos, sailors falling backward, completely overwhelmed"
        )

        final = _flux2_klein_md_positive_contract("", source)
        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertLessEqual(len(final), 900)
        self.assertIn("overwhelmed Sui river sailors in chaotic retreat", final)
        self.assertIn("pocketless hemp tunics", final)
        self.assertIn("cloth headwraps", final)
        self.assertIn("wet wooden deck planks", final)
        self.assertIn("faces panicked", final)
        self.assertNotIn("Scene-named historical subject", final)
        self.assertIn("buttoned field jacket", negative)
        self.assertIn("modern cap", negative)

    def test_flux2_klein_md_mass_army_uses_crowded_march_crop(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: Endless rows of heavily armored infantry stretching to the horizon"
        )

        final = _flux2_klein_md_positive_contract("", source)

        self.assertLessEqual(len(final), 900)
        self.assertIn("dense Sui infantry formation", final)
        self.assertIn("crowded low 16:9 march crop", final)
        self.assertIn("helmets, spears, mud, reeds, and marching bodies reach all image edges and corners", final)

    def test_flux2_klein_md_birds_eye_gargantuan_army_overrides_panorama(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: A bird's-eye view of a gargantuan army covering the entire landscape"
        )

        final = _flux2_klein_md_positive_contract("", source)

        self.assertLessEqual(len(final), 900)
        self.assertIn("dense Sui infantry formation", final)
        self.assertIn("crowded low 16:9 march crop", final)
        self.assertNotIn("bird's-eye", final.lower())
        self.assertNotIn("entire landscape", final.lower())

    def test_flux2_klein_md_supply_convoy_uses_crowded_wagon_crop(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: A massive convoy of supply wagons moving through a dusty plain"
        )

        final = _flux2_klein_md_positive_contract("", source)

        self.assertLessEqual(len(final), 900)
        self.assertIn("massive Sui supply wagon column", final)
        self.assertIn("crowded low 16:9 march crop", final)
        self.assertIn("wagon wheels, mud, reeds, carts, and shadows reach all image edges and corners", final)

    def test_flux2_klein_md_ep18_wide_and_text_scenes_use_safe_close_contracts(self):
        base = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
        )
        cases = [
            ("Changing seasons over an endless marching column of soldiers", "dense Sui infantry formation"),
            ("A high-angle shot of a dense, endless army covering the ground", "crowded low 16:9 march crop"),
            ("A small group of defenders looking at an impossibly large enemy wave", "reaction close-up"),
            ("Goguryeo citizens looking terrified at the dark, looming horizon", "reaction close-up"),
            ("Strong Goguryeo warriors holding spears on the opposite bank", "Goguryeo spear line waiting on the muddy riverbank"),
            ("Chinese engineers frantically building floating wooden bridges", "floating bridge construction material object evidence"),
            ("A wooden bridge ending abruptly before reaching the opposite shore", "broken floating bridge end object evidence"),
            ("Heavily armored soldiers falling into deep, muddy water", "full-bleed macro close-up of armored soldiers falling into muddy water"),
            ("A dark cloud of arrows raining down on the struggling soldiers", "black arrow rain striking"),
            ("Thousands of soldiers finally charging across the completed bridge", "Sui infantry charging across a rough wooden river bridge"),
            ("A massive, dark storm cloud gathering over a stone fortress", "storm-dark stone rubble at a fortress base"),
            ("The imposing Yodong fortress standing tall on a high cliff", "cropped granite defense-block field"),
            ("The fortress completely surrounded by countless enemy tents and banners", "fortress wall pressed by enemy camp lines"),
            ("An extremely tall and sturdy granite stone wall, heavily fortified", "cropped granite defense-block field"),
            ("A monstrously tall folding ladder reaching the top of the fortress", "cropped siege ladder and rope-hook object evidence"),
            ("An armored wooden vehicle digging into the dirt like a mole", "armored wooden digging vehicle object detail"),
            ("Goguryeo soldiers using thick ropes with hooks to topple a ladder", "cropped siege ladder and rope-hook object evidence"),
            ("Multiple catapults launching massive boulders through the air", "tight diagonal 16:9 impact crop"),
            ("Scorched earth with thick black smoke rising into the sky", "scorched battlefield ground under thick black smoke"),
            ("The emperor's secret order written on a scroll, marked with a red seal", "plain sealed war message evidence"),
            ("The famous five-word poem unrolled on a wooden table", "plain sealed war message evidence"),
            ("The word 'Salsu' carved deeply into a bloody stone monument", "blood-dark plain stone monument"),
            ("The massive dam shattering completely, exploding outward", "temporary dirt-and-log dam"),
            ("A gargantuan wave of dark water crashing down the river valley", "Salsu floodwater swallowing soldiers"),
        ]

        for scene, expected in cases:
            with self.subTest(scene=scene):
                final = _flux2_klein_md_positive_contract("", f"{base}Scene: {scene}")
                self.assertLessEqual(len(final), 900)
                self.assertIn(expected, final)
                self.assertNotIn("bird's-eye", final.lower())
                self.assertNotIn("high-angle", final.lower())
                self.assertNotIn("entire landscape", final.lower())
                self.assertNotIn("scroll", final.lower())
                self.assertNotIn("poem", final.lower())
                self.assertNotIn("paper", final.lower())
                if "enemy wave" in scene:
                    self.assertNotIn("floodwater", final.lower())

    def test_flux2_klein_md_adult_female_entrance_is_tasteful_and_charismatic(self):
        source = (
            "Year/period: seventh century; Exact place: royal council chamber; "
            "Culture scope: ancient Korean royal court; "
            "Scene evidence: silk court robe, hair ornament, bronze belt, wooden pillars, lamplight; "
            "Main subject: Queen Seondeok; "
            "Scene: Queen Seondeok enters the council chamber with calm authority"
        )

        final = _flux2_klein_md_positive_contract("", source)

        self.assertLessEqual(len(final), 900)
        self.assertIn("Scene subject: Queen Seondeok", final)
        self.assertIn("adult woman", final)
        self.assertIn("attractive charismatic presence", final)
        self.assertIn("confident eyes", final)
        self.assertIn("tasteful mature", final)
        self.assertNotRegex(final.lower(), r"\b(?:nude|naked|cleavage|underage|childlike)\b")

    def test_flux2_klein_md_negative_contract_stays_short(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: Salsu floodwater carries broken shields through a muddy river crossing"
        )
        final = (
            "612 CE Goguryeo-Sui open river battlefield at a muddy river crossing. "
            "Scene subject: dark floodwater in the open river valley."
        )

        negative = _flux2_klein_md_negative_contract(source, final)

        self.assertLessEqual(len(negative), 980)
        self.assertIn("readable writing", negative)
        self.assertIn("title panel", negative)
        self.assertIn("white border", negative)
        self.assertIn("signboard", negative)
        self.assertIn("bottom watermark", negative)
        self.assertIn("artist signature", negative)
        self.assertIn("bottom-right signature", negative)
        self.assertIn("bottom-right black characters", negative)
        self.assertIn("numeric corner mark", negative)
        self.assertIn("Chinese characters", negative)
        self.assertIn("chest emblem", negative)
        self.assertIn("badge lettering", negative)
        self.assertIn("photography", negative)
        self.assertIn("fortress interior", negative)
        self.assertIn("modern bridge", negative)
        self.assertIn("open book", negative)
        self.assertIn("page rows", negative)
        self.assertIn("paper sheet", negative)
        self.assertIn("modern military uniform", negative)
        self.assertIn("buttoned field jacket", negative)
        self.assertIn("chest flap pockets", negative)
        self.assertIn("modern cap", negative)
        self.assertIn("twentieth-century soldier", negative)
        self.assertNotIn("kanji tile under eave", negative)
        self.assertNotIn("wall switch plate", negative)

    def test_flux2_klein_md_workbench_uses_bare_wooden_board(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: A dark, blood-stained low horizontal tactile marker layout for East Asia on a visible table "
            "with loose route cords, separated stone markers, bronze weights, dust, and hard side light"
        )

        final = _flux2_klein_md_positive_contract("", source)

        self.assertIn("cord-and-stone military strategy tabletop", final)
        self.assertIn("tight tabletop 16:9 crop", final)
        self.assertIn("single bare low wooden tabletop surface", final)
        self.assertNotIn("visible table", final)
        self.assertNotIn("board", final.lower())
        self.assertNotIn("book", final.lower())

    def test_flux2_klein_md_rewrites_dagger_map_to_cord_stone_layout(self):
        source = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: A sharp dagger aggressively stabbed into the center of a map"
        )

        final = _flux2_klein_md_positive_contract("", source)

        self.assertIn("sharp dagger pinning crossed route cords", final)
        self.assertIn("separated stone markers", final)
        self.assertIn("single bare low wooden tabletop surface", final)
        self.assertNotIn("map", final.lower())
        self.assertNotIn("paper", final.lower())

    def test_flux2_klein_md_surface_uses_local_scene_over_global_workbench(self):
        source = (
            "Global visual world: Goguryeo command-table workbench evidence; "
            "Time range: 612year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Year/period: 612 AD; Exact place: Liaodong Fortress, Liaodong; "
            "Scene: A shattered Chinese war helmet resting in deep mud, dark clouds"
        )

        final = _flux2_klein_md_positive_contract("", source)

        self.assertIn("Visible surface detail: wet mud, water ripples", final)
        self.assertIn("tight ground-level 16:9 crop", final)
        self.assertNotIn("bare textured plaster", final)

    def test_flux2_klein_goguryeo_ep14_removes_hand_text_and_modern_metaphors(self):
        cases = (
            (
                "Scene: Two to four Goguryeo officers lean over a low wooden campaign table "
                "with blank route cords, separated stone markers, warm oil-lamp light catching "
                "dull bronze weights, dust, and sleeve-covered hands pointing toward the western frontier cluster",
                ("Goguryeo command-table workbench evidence", "tight low tabletop crop", "upper wall panels"),
                ("hands pointing", "paper map", "country outline"),
                ("extra hands", "wall plate above table", "switch-like rectangle above table"),
            ),
            (
                "Scene: A massive army attacking a sturdy stone fortress under dark clouds",
                ("Goguryeo northern frontier fortress attack", "Liao River frontier", "full-bleed and borderless"),
                ("Gaya-region fortified settlement", "Gaya region", "European castle"),
                ("Gaya-region fortified settlement", "comic panel border around entire image", "low village huts replacing fortress"),
            ),
            (
                "Scene: A thick, tight rope snapping violently in extreme slow motion",
                ("Snapping hemp rope action macro", "two separated rope ends", "Current tension failure"),
                ("person pulling rope", "hands gripping rope", "unbroken rope"),
                ("person pulling rope", "hands gripping rope", "unbroken rope"),
            ),
            (
                "Scene: Young King Jangsu placing his hands firmly on a massive, heavy iron steering wheel",
                ("Jangsu command-board succession scene", "current work surface", "blank raised route cords"),
                ("steering wheel", "machine wheel", "gear"),
                ("steering wheel", "machine wheel", "gear"),
            ),
            (
                "Scene: Calloused, bleeding hands gripping heavy stones on a steep, freezing incline",
                ("Stone-burden object evidence", "torn blood-stained sleeve cloth wraps", "human-free"),
                ("visible hands", "fingers", "disembodied arms"),
                ("extra hands", "hand close-up", "exposed fingers"),
            ),
            (
                "Scene: Two smaller kings shaking hands nervously in a dark, dimly lit room",
                ("Two-ruler tense pact with closed sleeves", "blank cord-tied pact token", "sleeve cuffs folded shut"),
                ("shaking hands", "clasped hands", "business suit"),
                ("handshake", "clasped hands", "business suit"),
            ),
            (
                "Scene: A diplomat handing over a peace treaty with a sinister, deceptive smirk",
                ("Textless envoy pact object evidence", "blank cord-tied wooden pact bundle", "blank wood and cord"),
                ("peace treaty", "written treaty", "scroll text"),
                ("written treaty", "treaty text", "document text"),
            ),
            (
                "Scene: A beautiful ancient treaty document suddenly bursting into flames",
                ("Burning pact bundle object crop", "blank cord-tied wooden pact bundle actively burning", "frame edge to edge"),
                ("doorway", "room wall", "people around table"),
                ("wall plate", "switch-like rectangle", "treaty text"),
            ),
            (
                "Scene: A beautiful ancient treaty cord-tied closed cream bundles held edge-on suddenly bursting into flames",
                ("Burning pact bundle object crop", "closed cord-tied cream pact bundle actively burning", "frame edge to edge"),
                ("doorway", "room wall", "people around table"),
                ("wall plate", "hands near fire", "intact document"),
            ),
            (
                "Scene: A curtain rising slowly on a stage filled with broken weapons and skulls",
                ("Battlefield-threshold weapons evidence", "broken spear shafts", "weapon debris reaching every edge"),
                ("curtain", "stage", "skull"),
                ("stage curtain", "theater stage", "velvet curtain"),
            ),
            (
                "Scene: A razor-sharp surgical blade gleaming under a harsh, cold, clinical light",
                ("Object-only early Korean blade on whetstone", "short straight early Korean iron blade", "compact early Korean form"),
                ("surgical", "clinical", "scalpel"),
                ("modern scalpel", "medical scalpel", "riveted handle"),
            ),
            (
                "Scene: Goguryeo cavalry suddenly bursting from a side gate, trampling the enemy",
                ("Side-gate cavalry counterattack", "side palisade gap below roof height", "Current battlefield action"),
                ("empty gate", "closed gate", "stone castle arch"),
                ("empty gate", "tiled gatehouse", "gate without cavalry"),
            ),
            (
                "Scene: A solid wooden gate shattering violently under a heavy battering ram",
                ("Timber palisade breach action", "raw-stake palisade gap", "upper third is open sky"),
                ("empty gate", "closed intact gate", "portcullis"),
                ("empty gate", "complete roofed gatehouse facade", "horizontal roof beam"),
            ),
            (
                "Scene: Later Yan governor Murong Gui flees a low fortress gate in panic, dropping a short spear while attendants scatter across muddy packed earth",
                ("Murong Gui raw-stake escape scene", "three attendants scattering", "blank uninterrupted cloth folds"),
                ("empty gate", "closed gate", "parade lineup"),
                ("empty gate", "complete roofed gatehouse facade", "no dropped spear"),
            ),
            (
                "Scene: A sharp sword reflecting the pale winter sun, pointing straight ahead",
                ("Winter sun blade evidence", "one short straight early Korean iron blade lying flat", "pale winter sunlight stripe"),
                ("floating sword", "giant sword", "vertical sword"),
                ("floating sword", "giant sword", "second blade"),
            ),
            (
                "Scene: The king sharpening his long iron sword, his face hidden in shadows",
                ("Straight-blade sharpening workbench evidence", "straight parallel cutting edge", "modern manufactured knife grip"),
                ("curved blade", "saber", "katana"),
                ("curved blade", "riveted handle", "missing whetstone"),
            ),
            (
                "Scene: King Jangsu sharpens a short iron blade on a stone whetstone inside a dark timber room",
                ("Jangsu sleeve-covered blade sharpening workbench", "Exactly one short straight early Korean iron blade", "sleeve cuffs cover"),
                ("riveted handle", "kitchen-knife form", "spread fingers"),
                ("riveted handle", "kitchen knife", "missing whetstone"),
            ),
            (
                "Scene: A Goguryeo commander raises his sword in a blizzard as soldiers push forward",
                ("Goguryeo northern frontier snowstorm action scene", "straight spine", "straight cutting edge"),
                ("curved blade", "saber", "katana"),
                ("curved blade", "saber", "Japanese sword"),
            ),
            (
                "Scene: A fierce warlord, Murong Sheng, drawing his sword with a cruel glare",
                ("Single-ruler blade-draw scene", "straight spine", "straight cutting edge"),
                ("curved blade", "saber", "katana"),
                ("curved blade", "saber", "blade held like a saber"),
            ),
            (
                "Scene: A massive sword being sharpened violently on a grinding stone, sparks flying",
                ("Straight-blade sharpening workbench evidence", "Small orange sparks", "blade-stone contact point"),
                ("giant sword", "oversized sword", "wall display"),
                ("giant sword", "oversized sword", "blade not touching stone"),
            ),
            (
                "Scene: A massive stone watchtower crumbling and collapsing into the dirt",
                ("Full-bleed ancient Korean fortress tower base fracture scene", "collapsed Goguryeo frontier watchpost base", "base height"),
                ("stone keep", "European castle", "crenellated"),
                ("stone keep", "European castle", "crenellated battlement"),
            ),
            (
                "Scene: Later Yan soldiers march in dense ranks toward a low Goguryeo stone-and-earth fortress, blank dark banners bent by cold frontier wind",
                ("Later Yan approach to Goguryeo frontier fortress", "raw vertical-stake gate gap below roof height", "Current advance"),
                ("tiled gatehouse", "European castle", "empty road"),
                ("tiled gatehouse", "missing infantry ranks", "missing fortress wall"),
            ),
            (
                "Scene: The impenetrable Yodong fortress standing tall on a high, rocky cliff",
                ("Yodong cliff fortress establishing scene", "stacked rough fieldstone bases", "terrain-bound"),
                ("European stone castle", "crenellated", "tall castle tower"),
                ("European castle", "tall castle tower", "comic panel border around entire image"),
            ),
            (
                "Scene: Thousands of arrows hitting the thick stone walls like dark rain",
                ("Goguryeo fortress wall arrow-impact scene", "fresh arrow impacts", "exterior wall"),
                ("arrows stuck in interior wall", "arrows in room", "pottery on table"),
                ("interior room", "arrows stuck in interior wall", "missing stone wall"),
            ),
            (
                "Scene: A rain of massive boulders crushing the advancing Yan siege engines",
                ("Goguryeo cliff boulder trap siege defense", "shattered timber", "Current defensive work"),
                ("indoor catapult", "pottery on table", "wall plate beside catapult"),
                ("interior room", "indoor catapult", "missing falling boulders"),
            ),
            (
                "Scene: Yan soldiers collapsing in the freezing snow, their weapons abandoned",
                ("Open snow battlefield collapse scene", "Building-free open snowfield", "Only snowfield"),
                ("bodies indoors", "warm room", "palace interior"),
                ("interior room", "complete building facade", "missing snowfield"),
            ),
            (
                "Scene: Another massive Yan army marching through a narrow, muddy valley",
                ("Yan army narrow muddy valley march", "Building-free exterior valley", "Current march"),
                ("building lane", "village street", "roofed houses"),
                ("building lane", "missing valley", "tiled roof"),
            ),
            (
                "Scene: Goguryeo archers release arrows from behind a low rough palisade toward retreating Later Yan soldiers crossing muddy frontier ground",
                ("Goguryeo open palisade archer line", "Building-free exterior frontier ground", "drawn bowstrings"),
                ("roofed building behind archers", "interior room", "gatehouse"),
                ("roofed building behind archers", "missing palisade", "missing archers"),
            ),
            (
                "Scene: Goguryeo farmers harvest ripe millet and barley near low timber homes, with baskets, sickles, hemp garments, and guarded frontier hills behind them",
                ("Goguryeo harvest village work scene", "tied grain bundles", "current work"),
                ("shop sign", "facade sign", "wall plaque"),
                ("shop sign", "facade sign", "wall plaque"),
            ),
            (
                "Scene: A large, beautiful building showing deep, dangerous cracks in its foundation",
                ("Cracked foundation evidence crop", "cracked stone foundation blocks", "upper facade are outside the frame"),
                ("full building facade", "modern concrete", "European cathedral"),
                ("signboard", "lintel inscription", "full building facade"),
            ),
            (
                "Scene: A detailed blueprint of a new capital city resting on a dark wooden table",
                ("Textless capital planning workbench", "small unmarked wooden house blocks", "current planning work"),
                ("blueprint", "paper map", "grid labels"),
                ("blueprint", "paper map", "map labels"),
            ),
            (
                "Scene: A split screen: a bloody sword on one side, a peaceful prayer bead on the other",
                ("Single workbench blade and prayer beads", "One continuous unpartitioned object-only workbench", "one plain wooden prayer-bead loop"),
                ("split screen", "vertical divider", "panel divider"),
                ("split screen", "vertical divider", "missing prayer beads"),
            ),
            (
                "Scene: A young Goguryeo prince grips a plain bronze-bound succession tablet box on a low table while older officials watch silently under torchlight",
                ("Goguryeo succession box council scene", "plain bronze-bound wooden succession box", "identity comes from age"),
                ("gold chest emblem", "robe medallion", "rank mark"),
                ("gold chest emblem", "sleeve emblem", "shoulder badge"),
            ),
            (
                "Scene: A crippled soldier sitting in the freezing dirt, holding an empty bowl",
                ("Open snow-mud veteran bowl scene", "sits directly on freezing open dirt", "blank robe chest folds"),
                ("modern coat pocket", "shirt pocket", "rubber boots"),
                ("modern coat pocket", "shirt pocket", "roof overhead"),
            ),
            (
                "Scene: A wealthy aristocrat greedily inspecting a massive pile of looted treasures",
                ("Ground-level looted valuables scene", "Full-bleed open ground composition", "captured valuables only"),
                ("potatoes", "root vegetables", "Late Imperial Russia"),
                ("potatoes", "root vegetables", "cannon barrel"),
            ),
            (
                "Scene: A dim Goguryeo royal bedchamber holds a low wooden sleeping platform, plain closed curtains, oil lamps, and silent court attendants on the packed floor",
                ("Goguryeo low sleeping-platform death chamber", "low wooden sleeping platform", "court attendants kneel"),
                ("modern framed bed", "nightstand", "wall switch"),
                ("modern bed", "nightstand", "wall switch"),
            ),
            (
                "Scene: A strategy board game with pieces scattered, turning into real falling soldiers",
                ("Ancient strategy-marker board pressure scene", "plain unmarked clay markers", "toppled markers"),
                ("chessboard", "go-board", "modern board game"),
                ("chess board", "go board", "modern board game"),
            ),
            (
                "Scene: A blank wooden record-tablet bundle and small bronze royal figurine sit under golden lamplight on a rough stone table",
                ("Royal marker wood-slip evidence", "faceless, limbless, geometric", "cap-like top bump"),
                ("wooden box with writing", "symbol-covered board", "open paper sheet"),
                ("glyph rows", "gold idol", "toy robot"),
            ),
            (
                "Scene: A massive city burning fiercely as an executioner stands over a defeated king",
                ("Baekje open-ground execution aftermath scene", "executioner stands upright", "smoke columns and orange glow"),
                ("person stands inside flames", "body pile as a platform", "modern gallows"),
                ("person standing in flames", "sword duel", "defeated king touching blade"),
            ),
            (
                "Scene: King Gwanggaeto stands in a dark timber command room watching a burning frontier fortress through the open doorway, lamellar armor and oil-lamp shadows framing his tense face",
                ("Gwanggaeto doorway command-watch scene", "single empty open rectangular doorway", "All light comes from"),
                ("empty exterior-only fortress shot", "wall switch", "tiled palace roof"),
                ("wall switch", "door handle plate", "framed mirror"),
            ),
            (
                "Scene: An exhausted young Goguryeo ruler studies a cracked bronze mirror by oil-lamp light, his period robe and tense reflection visible in the metal",
                ("Cracked bronze mirror ruler study scene", "visible gaps between pieces", "break the circular outline"),
                ("sewing needle", "glass mirror", "wall switch"),
                ("sewing needle", "intact cracked circle", "gold mirror rim"),
            ),
            (
                "Scene: A lone survivor weeping silently next to a destroyed home in the winter",
                ("Open snow-mud survivor debris scene", "open-air winter aftermath", "open air above"),
                ("interior room", "modern hardware", "complete roofed facade"),
                ("wall switch", "roof overhead", "door knob"),
            ),
            (
                "Scene: An older Goguryeo ruler studies worn tally cords and wooden counters on a low desk, measuring a long reign under cold lamplight",
                ("Older ruler tally-cord calculation scene", "separated wooden counters", "loose objects arranged"),
                ("abacus frame", "modern calculating device", "wall switch"),
                ("abacus frame", "modern calculator", "wall switch"),
            ),
            (
                "Scene: Goguryeo, Baekje, and Silla armed envoys confront each other in a tight frontier pass, hands near weapons and faces tense under torchlight",
                ("Blank-sleeved frontier envoy confrontation scene", "material-only fields", "faction identity"),
                ("gold shoulder crest", "sleeve emblem", "heraldic applique"),
                ("gold chest emblem", "sleeve emblem", "shoulder badge"),
            ),
            (
                "Scene: A dark executioner's block with a heavy axe resting on it, waiting for the next victim",
                ("Object-only execution block evidence", "one heavy plain iron axe", "packed earth, darkness"),
                ("wall switch", "title card", "people"),
                ("wall switch", "title card", "person beside block"),
            ),
            (
                "Scene: A Goguryeo scribe pushes a blank wooden tale tablet into a low bronze brazier, smoke rising beside stone weights and plain record bundles",
                ("Brazier wood-slip burning action scene", "pushes one blank wooden slip", "low bronze brazier"),
                ("empty tablet-only still life", "paper sheet", "written tablet"),
                ("missing brazier", "missing scribe", "written tablet"),
            ),
            (
                "Scene: A beautiful stained-glass window covering a dark, rotting, and bloody brick wall",
                ("Charred mud-plaster false-glory evidence", "torn plain hemp screen", "material metaphor"),
                ("stained glass", "brick wall", "round mirror"),
                ("stained glass", "brick wall", "round mirror"),
            ),
            (
                "Scene: Title card for Episode 15, illuminated by dark, gritty red lighting",
                ("Battlefield-threshold weapons evidence", "broken spear shafts", "weapon debris reaching every edge"),
                ("Title card", "Episode 15", "caption text"),
                ("title card", "stage curtain", "wall switch"),
            ),
            (
                "Scene: Buyeo soldiers dropping their weapons and fleeing in complete panic",
                ("Buyeo rout with dropped weapons", "run away in panic", "abandoned weapons"),
                ("crouching around a pile", "huddled workers", "woodpile"),
                ("crouching around a pile", "huddled workers", "missing dropped weapons"),
            ),
        )

        for scene, expected_prompt_parts, forbidden_prompt_parts, expected_negative_parts in cases:
            with self.subTest(scene=scene):
                prompt = (
                    "Year/period: 402-410 AD; Goguryeo northern campaigns, 402-410 AD; "
                    "Exact place: Liao River, northern frontier; "
                    "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
                    "Style: serious adult graphic novel illustration; "
                    f"{scene}"
                )
                compact, negative = _compact_flux2_klein_4b_prompt(prompt, "")
                compact_lower = compact.lower()
                negative_lower = negative.lower()

                for expected in expected_prompt_parts:
                    self.assertIn(expected, compact)
                for forbidden in forbidden_prompt_parts:
                    self.assertNotIn(forbidden.lower(), compact_lower)
                for expected in expected_negative_parts:
                    self.assertIn(expected.lower(), negative_lower)

    def test_flux2_klein_tang_645_ansi_failed_cuts_are_concretized_in_final_contract(self):
        def final_contract(scene: str, subject: str = "scene subject") -> str:
            prompt = (
                "Global visual world: Time range: 645year; Place scope: Ansi Fortress; "
                "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
                "Material culture: Iron weapons, bows, leather armor, lamellar armor, hemp garments, "
                "wooden halls, fortress walls, river crossings, horses, bronze ritual objects; "
                "Continuity rule: Every scene stays in an ancient Northeast Asian setting. "
                "Year/period: 645 AD; Style: serious adult graphic novel illustration; "
                f"Main subject: {subject}; Scene: {scene}"
            )
            compact, _negative = _compact_flux2_klein_4b_prompt(f"{prompt}\n{prompt}", "")
            return _flux2_klein_md_positive_contract(
                _flux2_klein_positive_contract_cleanup(compact),
                prompt,
            )

        cases = (
            (
                "Thousands of black arrows launching from the dirt mountain",
                "Thousands of black arrows launching from the dirt mountain",
                ("Tang archers firing from the man-made packed-earth siege ramp", "arrow shafts in flight"),
                ("laborers and soldiers build", "readable"),
            ),
            (
                "A fictional Chinese novel with a fake name highlighted in red",
                "fictional Chinese novel",
                ("closed blank bamboo-slip packet with a red cord tie", "continuous rough plank grain filling every edge"),
                ("fake name highlighted", "novel", "black ink"),
            ),
            (
                "An ancient book turning its pages forcefully, revealing dark, bloody secrets",
                "ancient book",
                ("flat blank bamboo-slip slat bundle with one empty central slat", "continuous rough plank grain filling every edge"),
                ("bloody secrets", "turning its pages"),
            ),
            (
                "stylish medium-close entrance of Emperor Yang of Sui, intense eyes, controlled expression",
                "Emperor Yang of Sui",
                ("Emperor Taizong acknowledging the Ansi defender's courage", "one Emperor Taizong", "sleeve-covered hands on plain belt knot"),
                ("Emperor Yang of Sui", "report packet"),
            ),
            (
                "A broken, nameless sword resting alone in a forgotten dirt grave",
                "broken",
                ("two separated snapped sword halves", "clear dark break gap"),
                ("intact sword", "single continuous blade"),
            ),
            (
                "A slow-dripping hourglass filled with dark, blood-red sand",
                "slow-dripping hourglass",
                ("outdoor ground-only time-pressure evidence", "edge-to-edge local ground texture"),
                ("building wall", "doorway"),
            ),
            (
                "A massive meat grinder fueled by countless anonymous silhouettes",
                "massive meat grinder",
                ("war pressure shown by rough crushing stones", "broken spear shafts"),
                ("meat grinder", "machine", "industrial"),
            ),
            (
                "A modern face looking deeply into a cracked, ancient, and bloody mirror",
                "modern",
                ("period warrior reflection in a cracked bronze mirror", "dark red stains"),
                ("modern face", "glass mirror"),
            ),
            (
                "A mountain of crushed skulls beneath a massive, glowing, imposing throne",
                "mountain of crushed skulls beneath a massive",
                ("plain ruler seat raised above battlefield remains", "separate small bone fragments"),
                ("glowing throne", "skull mountain"),
            ),
        )

        for scene, subject, expected_parts, forbidden_parts in cases:
            with self.subTest(scene=scene):
                final = final_contract(scene, subject)
                final_lower = final.lower()
                for expected in expected_parts:
                    self.assertIn(expected, final)
                for forbidden in forbidden_parts:
                    self.assertNotIn(forbidden.lower(), final_lower)

    def test_flux2_klein_tang_645_ansi_pipeline_prompt_keeps_failed_cut_repairs(self):
        def pipeline_positive(source_prompt: str, narration: str = "") -> str:
            normalized = normalize_cut_image_prompt(
                source_prompt,
                narration,
                "진흙탕에 빠진 황제, 안시성 전투 2 EP.26 고구려",
            )
            built = prompt_builder.build_image_prompt(
                normalized,
                "",
                has_reference=False,
                has_character_slot=False,
                character_description="",
                enable_historical_guard=True,
            )
            prepared = _flux2_klein_prepare_source_prompt_text(built)
            compact, _negative = _compact_flux2_klein_4b_prompt(f"{prepared}\n{prepared}", "")
            return _flux2_klein_md_positive_contract(
                _flux2_klein_positive_contract_cleanup(compact),
                prepared,
            )

        base = (
            "Global visual world: Time range: 645year; Place scope: Ansi Fortress; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Material culture: Iron weapons, bows, leather armor, lamellar armor, hemp garments, "
            "wooden halls, fortress walls, river crossings, horses, bronze ritual objects; "
            "Continuity rule: Every scene stays in an ancient Northeast Asian setting. "
            "No Joseon dynasty clothing, no modern objects, no medieval European castles, no readable text.; "
            "Year/period: 645 AD; Style: serious adult graphic novel illustration; "
        )
        cases = (
            (
                base
                + "Main subject: Emperor Yang of Sui; "
                + "Scene: stylish medium-close entrance of Emperor Yang of Sui, intense eyes, controlled expression",
                "성을 지켜낸 고구려 장수의 훌륭한 품격과 용기에 깊이 감탄했다며,",
                ("Tang Taizong acknowledging the Ansi defender's courage", "controlled admiration"),
                ("Tang and Goguryeo forces", "siege pressure builds around Liaodong Fortress"),
            ),
            (
                base
                + "Main subject: fictional Chinese novel; "
                + "Scene: A fictional Chinese novel with a fake name highlighted in red",
                "",
                ("closed blank bamboo-slip packet with a red cord tie", "continuous rough plank grain filling every edge"),
                ("so Visible inventory", "complete table outline"),
            ),
            (
                base
                + "Main subject: slow-dripping hourglass filled; "
                + "Scene: A slow-dripping hourglass filled with dark, blood-red sand",
                "",
                ("outdoor ground-only time-pressure evidence", "edge-to-edge local ground texture"),
                ("Visible clothing", "building wall"),
            ),
            (
                base
                + "Main subject: ancient book turning its pages forcefully; "
                + "Scene: An ancient book turning its pages forcefully, revealing dark, bloody secrets",
                "",
                ("flat blank bamboo-slip slat bundle with one empty central slat", "continuous rough plank grain filling every edge"),
                ("with Visible inventory", "bloody secrets"),
            ),
        )

        for source_prompt, narration, expected_parts, forbidden_parts in cases:
            with self.subTest(source_prompt=source_prompt):
                final = pipeline_positive(source_prompt, narration)
                final_lower = final.lower()
                for expected in expected_parts:
                    self.assertIn(expected, final)
                for forbidden in forbidden_parts:
                    self.assertNotIn(forbidden.lower(), final_lower)

    def test_flux2_klein_tang_645_ansi_object_actions_survive_final_contract(self):
        def final_contract(scene: str, subject: str = "scene subject") -> str:
            prompt = (
                "Global visual world: Time range: 645year; Place scope: Ansi Fortress; "
                "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
                "Year/period: 645 AD; Style: serious adult graphic novel illustration; "
                f"Main subject: {subject}; Scene: {scene}"
            )
            compact, _negative = _compact_flux2_klein_4b_prompt(f"{prompt}\n{prompt}", "")
            return _flux2_klein_md_positive_contract(
                _flux2_klein_positive_contract_cleanup(compact),
                prompt,
            )

        cases = (
            (
                "A lone, sturdy stone fortress standing firm",
                "lone",
                "Ansi Fortress standing firm under siege pressure",
            ),
            (
                "A flawless, sharp sword bending and cracking before it strikes",
                "flawless",
                "cracked iron sword warped by defeat pressure",
            ),
            (
                "An arrow flying straight toward the camera in extreme close-up",
                "arrow flying straight toward the camera in extreme",
                "single arrow flying through battlefield smoke",
            ),
            (
                "An ancient record book with a large, glaring blank space",
                "ancient record book",
                "flat blank bamboo-slip slat bundle with one empty central slat",
            ),
        )

        for scene, subject, expected in cases:
            with self.subTest(scene=scene):
                final = final_contract(scene, subject)
                self.assertIn(expected, final)


if __name__ == "__main__":
    unittest.main()
