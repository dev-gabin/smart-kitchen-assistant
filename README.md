> **온디바이스 AI 기반 주방 화재.연기 실시간 감지 및 Hands-Free 레시피 제어 시스템**
>
> 2인 팀 프로젝트
> 
![Python](https://img.shields.io/badge/Python-3.9-3776AB?style=flat&logo=python&logoColor=white)
![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-000000?style=flat)
![OpenCV](https://img.shields.io/badge/OpenCV-4.x-5C3EE8?style=flat&logo=opencv&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?style=flat&logo=windows&logoColor=white)

---

## 📌 1. 프로젝트 개요 (Overview)

요리 중 발생할 수 있는 **주방 화재 위험(연기)**을 실시간으로 감지하여 대형 사고를 예방하고, 식재료나 양념이 손에 묻어 디바이스를 직접 터치하기 힘든 상황에서 **비접촉 손동작(Gesture)**만으로 레시피/유튜브 화면 및 타이머를 제어할 수 있도록 구현한 **온디바이스(On-Device) AI 소프트웨어**입니다.

또한 **음성 인식(Voice Recognition)**을 통해 조리 중 화면을 직접 확인하거나 조작하지 않고도 **현재 타이머의 남은 시간을 음성으로 확인**할 수 있어, 보다 편리한 **Hands-Free 조리 환경**을 제공합니다.


### 💡 기획 배경 및 페인 포인트 (Pain Point)
1. **주방 안전 문제**: 요리 중 잠깐 자리를 비우거나 부주의로 인해 음식이 타면서 연기가 발생하고 화재로 이어지는 위험 존재.
2. **위생 및 기기 오염**: 양손에 양념이나 식재료가 묻은 상태로 태블릿/노트북을 터치하면 화면이 오염되고 기기가 손상되며 교차 오염 위험 발생.

---

## 🚀 2. 주요 기능 (Key Features)

### 1️⃣ 실시간 연기(Smoke) 감지 및 온디바이스 경보
* **Object Detection**: 파인튜닝된 YOLOv8 모델이 프레임 내 연기 발생을 추론.
* **즉각적 비상 알림**: 연기 감지 시 화면 레이아웃이 위험(RED) 상태로 변경되며 PC 스피커를 통해 온디바이스 알람(Beep) 출력.

### 2️⃣ Hands-Free 비접촉 제스처 제어 (No-Touch UX)
* **Pose Estimation**: `YOLOv8-Pose`를 통해 사람의 상체 관절(Keypoints) 좌표를 실시간 추적.
* **OS 이벤트 매핑**: 손 올리기 제스처 감지 시 `PyAutoGUI`를 이용해 키보드/마우스 명령어(Space, Arrow Keys 등)를 자동 전송하여 레시피 재생/일시정지 및 스크롤 제어.

### 3️⃣ 음성 인식 기반 타이머 안내 (Voice-based Timer Guidance)
Voice Recognition: 사용자의 음성 명령을 인식하여 타이머의 남은 시간 확인 요청을 처리
Timer Guidance: 조리 중 화면을 직접 조작하지 않고 현재 타이머의 남은 시간을 음성으로 안내

---

## 🛡️ 3. 온디바이스 SW 및 시장 타당성 (Value Proposition)

* **저지연성 (Low Latency)**: 화재 연기를 감지하여 현장 경보 울림.
* **확장성**: 디스플레이의 기본 탑재 SW로 확장 가능.

---
## 🏗️ 4. 프로젝트 구조 (Directory Structure)

본 프로젝트는 **단일 책임 원칙(SRP)**과 **객체지향 프로그래밍(OOP)** 규칙에 맞추어 모듈화되어 있습니다.

```text
smart_kitchen_assistant/
│
├── .vscode/
│   └── settings.json                 # VS Code 프로젝트 설정
│
├── assets/                           # UI 리소스
│   └── icons/                        # 버튼 및 화면 아이콘
│
├── data/                             # 데이터 관리 폴더
│   └── gesture_train.csv             # 손동작 학습 데이터
│
├── models/                           # AI 모델 가중치(.pt) 파일 관리
│   ├── custom_smoke_best.pt          # 연기 감지 학습 모델
│   ├── custom_smoke_best_v2.pt       # 연기 감지 모델 개선 버전
│   ├── custom_smoke_best_v3.pt       # 연기 감지 모델 개선 버전
│   ├── custom_smoke_best_v4.pt       # 연기 감지 모델 개선 버전
│   └── yolov8n.pt                    # YOLOv8 기본 모델
│
├── src/                              # 핵심 소스코드 (OOP 모듈)
│   │
│   ├── burner/                       # 화구 및 연기 감지 관련 모듈
│   │   ├── __init__.py               # burner 패키지 초기화
│   │   ├── burner_detector.py        # 화구 영역 감지 및 처리
│   │   └── smoke_detector.py         # 연기 감지 처리
│   │
│   ├── gesture/                      # 손동작 및 제어 관련 모듈
│   │   ├── __init__.py               # gesture 패키지 초기화
│   │   ├── controller.py             # 손동작 인식 및 동작 제어
│   │   ├── voice_detector.py         # 음성 입력 감지 관련 처리
│   │   ├── web_control.py            # 웹 브라우저 제어
│   │   └── youtube_controller.py     # YouTube 제어 기능
│   │
│   ├── __init__.py                   # src 패키지 초기화
│   └── kitchen_ui_overlay.py         # 대시보드 UI 및 화면 오버레이 처리
│
├── .gitignore                        # Git 추적 제외 설정
├── README.md                         # 프로젝트 설명 문서
├── main.py                           # 애플리케이션 실행 진입점
├── requirements.txt                  # 프로젝트 의존 라이브러리 목록
└── train_smoke_model.py              # 연기 감지 YOLO 모델 학습 스크립트
```

```
## 데이터셋 안내

연기 감지 모델 학습에 사용한 원본 이미지 데이터셋은 파일 용량 문제로  
GitHub 저장소에 포함하지 않았습니다.

원본 데이터는 로컬의 `data/raw_smoke_dataset/` 경로에서 관리했습니다.
