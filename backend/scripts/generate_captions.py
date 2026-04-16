"""학습 이미지 자동 캡션 생성기.

학습 폴더의 이미지마다 .txt 캡션 파일을 생성한다.
모든 캡션에 트리거워드 "longtube style" 을 포함시켜
LoRA 가 이 키워드에 바인딩되게 한다.

사용법:
  python generate_captions.py [이미지 폴더 경로]
  python generate_captions.py  (기본: C:\comfi\training\longtube_style\img\30_longtube style)
"""
import sys
from pathlib import Path

DEFAULT_DIR = r"C:\comfi\training\longtube_style\img\30_longtubestyle"
TRIGGER = "longtubestyle"

# 캡션 템플릿. 이미지 내용을 모르니 스타일 묘사만 넣는다.
# kohya 학습 시 --shuffle_caption 옵션으로 태그 순서를 섞어주므로
# 트리거워드가 항상 첫 번째일 필요는 없지만, 관례적으로 앞에 넣는다.
CAPTION_VARIANTS = [
    f"{TRIGGER}, simple cartoon illustration, round-headed character, thick outlines, warm earth tones, crayon texture, kraft paper background",
    f"{TRIGGER}, cute cartoon scene, bold linework, soft warm palette, textured paper feel, children book illustration",
    f"{TRIGGER}, minimal cartoon artwork, clean thick outlines, muted warm colors, paper grain texture, cozy illustration",
    f"{TRIGGER}, storybook illustration, round simple characters, bold dark outlines, warm beige and brown tones, hand-drawn feel",
    f"{TRIGGER}, cartoon landscape, thick outline art, warm earthy palette, subtle paper texture, simple shapes",
]


def main():
    img_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(DEFAULT_DIR)
    if not img_dir.exists():
        print(f"폴더가 없습니다: {img_dir}")
        print(f"먼저 학습 이미지를 넣어주세요.")
        sys.exit(1)

    exts = {".png", ".jpg", ".jpeg", ".webp"}
    images = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in exts)

    if not images:
        print(f"이미지가 없습니다: {img_dir}")
        sys.exit(1)

    created = 0
    skipped = 0
    for i, img_path in enumerate(images):
        txt_path = img_path.with_suffix(".txt")
        if txt_path.exists():
            skipped += 1
            continue
        caption = CAPTION_VARIANTS[i % len(CAPTION_VARIANTS)]
        txt_path.write_text(caption, encoding="utf-8")
        created += 1
        print(f"  ✓ {img_path.name} → {txt_path.name}")

    print(f"\n완료: {created}개 생성, {skipped}개 스킵 (이미 존재)")
    print(f"총 이미지: {len(images)}장")
    print(f"\n💡 팁: 캡션을 직접 수정하면 더 좋은 결과를 얻을 수 있습니다.")
    print(f"   예) 캐릭터 이미지: '{TRIGGER}, round-headed character holding a phone, ...'")
    print(f"   예) 풍경 이미지:   '{TRIGGER}, cartoon mountain landscape, ...'")


if __name__ == "__main__":
    main()
