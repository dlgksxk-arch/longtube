<#
  LongTube 스타일 LoRA 학습 스크립트 (JERRY PC 에서 실행)

  사전 준비:
  1. kohya_ss 설치: https://github.com/bmaltais/kohya_ss
  2. 학습 이미지 20~30장을 아래 폴더에 넣기
  3. 이 스크립트를 PowerShell 에서 실행

  VRAM 12GB 기준 설정. DreamShaper XL (SDXL) 베이스.
#>

$ErrorActionPreference = "Stop"

# ── 경로 설정 (JERRY PC 에 맞게 수정) ──
$KOHYA_DIR      = "C:\kohya_ss"
$BASE_MODEL     = "C:\comfi\models\checkpoints\dreamshaperXL_sfwLightningDPMSDE.safetensors"
$TRAIN_DATA_DIR = "C:\comfi\training\longtube_style\img"
$OUTPUT_DIR     = "C:\comfi\training\longtube_style\output"
$LOG_DIR        = "C:\comfi\training\longtube_style\log"

# ── 학습 이미지 폴더 구조 ──
# $TRAIN_DATA_DIR 아래에 다음과 같이 폴더를 만들어야 함:
#   C:\comfi\training\longtube_style\img\30_longtubestyle\
#   └── image1.png, image2.png, ... (20~30장)
#
# 폴더명 형식: {반복횟수}_{트리거워드}
# "30_longtubestyle" = 이미지당 30번 반복, 트리거워드 "longtube style"

# 폴더 생성
New-Item -ItemType Directory -Force -Path "$TRAIN_DATA_DIR\30_longtubestyle"
New-Item -ItemType Directory -Force -Path $OUTPUT_DIR
New-Item -ItemType Directory -Force -Path $LOG_DIR

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " LongTube Style LoRA Training" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "학습 이미지를 여기에 넣으세요:" -ForegroundColor Yellow
Write-Host "  $TRAIN_DATA_DIR\30_longtubestyle\" -ForegroundColor White
Write-Host ""

# 이미지 수 확인
$imgCount = (Get-ChildItem "$TRAIN_DATA_DIR\30_longtubestyle\*" -Include *.png,*.jpg,*.jpeg,*.webp -ErrorAction SilentlyContinue).Count
if ($imgCount -lt 10) {
    Write-Host "경고: 이미지가 ${imgCount}장뿐입니다. 최소 15장 이상 권장합니다." -ForegroundColor Red
    Write-Host "이미지를 넣고 다시 실행하세요." -ForegroundColor Red
    exit 1
}
Write-Host "학습 이미지: ${imgCount}장 감지" -ForegroundColor Green

# ── kohya_ss 가상환경 활성화 ──
Push-Location $KOHYA_DIR
if (Test-Path ".\venv\Scripts\Activate.ps1") {
    . .\venv\Scripts\Activate.ps1
} elseif (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
}

# ── 학습 실행 ──
# SDXL LoRA, 12GB VRAM 최적화 설정
python sdxl_train_network.py `
    --pretrained_model_name_or_path="$BASE_MODEL" `
    --train_data_dir="$TRAIN_DATA_DIR" `
    --output_dir="$OUTPUT_DIR" `
    --logging_dir="$LOG_DIR" `
    --output_name="longtube_style_v1" `
    --network_module="networks.lora" `
    --network_dim=32 `
    --network_alpha=16 `
    --resolution="1024,1024" `
    --train_batch_size=1 `
    --max_train_epochs=10 `
    --learning_rate=1e-4 `
    --unet_lr=1e-4 `
    --text_encoder_lr=5e-5 `
    --lr_scheduler="cosine_with_restarts" `
    --lr_warmup_steps=50 `
    --optimizer_type="AdamW8bit" `
    --mixed_precision="fp16" `
    --save_precision="fp16" `
    --cache_latents `
    --cache_latents_to_disk `
    --gradient_checkpointing `
    --save_every_n_epochs=2 `
    --save_model_as="safetensors" `
    --clip_skip=2 `
    --seed=42 `
    --caption_extension=".txt" `
    --shuffle_caption `
    --max_token_length=225 `
    --xformers `
    --bucket_reso_steps=64 `
    --min_bucket_reso=512 `
    --max_bucket_reso=1536 `
    --no_half_vae

Pop-Location

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " 학습 완료!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host "LoRA 파일: $OUTPUT_DIR\longtube_style_v1.safetensors" -ForegroundColor White
Write-Host ""
Write-Host "다음 단계:" -ForegroundColor Yellow
Write-Host "  1. LoRA 파일을 C:\comfi\models\loras\ 에 복사" -ForegroundColor White
Write-Host "  2. LongTube 백엔드 재시작" -ForegroundColor White
Write-Host "  3. 프로젝트 설정에서 이미지 모델을 'comfyui-dreamshaper-xl-longtube' 로 변경" -ForegroundColor White
