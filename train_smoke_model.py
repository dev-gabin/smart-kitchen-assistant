from pathlib import Path

from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent
DATA_YAML = BASE_DIR / "data" / "roboflow_smoke" / "data.yaml"
#기존 학습 모델에 추가학습
BASE_MODEL = BASE_DIR / "models" / "custom_smoke_best_v2.pt"
RUNS_DIR = BASE_DIR / "runs"
RUN_NAME = "smoke_train"

OUTPUT_MODEL_PATH = BASE_DIR / "models" / "custom_smoke_best_v3.pt"

# CNN 구조로 커스텀 모델 생성

def train():
    model = YOLO(BASE_MODEL)

    model.train(
        data=str(DATA_YAML),
        epochs=50,
        imgsz=640,
        batch=16,
        # fraction=0.52,
        project=str(RUNS_DIR),
        name=RUN_NAME,
    )

    best_weights = Path(model.trainer.best)
    OUTPUT_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MODEL_PATH.write_bytes(best_weights.read_bytes())
    print(f"[INFO] 최종 모델 저장 완료: {OUTPUT_MODEL_PATH}")


if __name__ == "__main__":
    train()
