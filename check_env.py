import os
import sys
from pathlib import Path
from dotenv import load_dotenv

def main():
    print("========================================")
    print("      ENVIRONMENT & DEPENDENCY CHECK    ")
    print("========================================\n")
    
    # 1. Load .env
    print("1. Loading Environment Variables")
    env_path = Path(__file__).parent / '.env'
    load_dotenv(dotenv_path=env_path)
    
    # 2. Print SERPAPI_KEY status
    serpapi_key = os.getenv("SERPAPI_KEY")
    if serpapi_key:
        print(f"   [OK] SERPAPI_KEY found (starts with {serpapi_key[:4]}...)")
    else:
        print("   [ERROR] SERPAPI_KEY not found in .env")
        
    print("\n2. Checking Dependencies")
    
    # 3. Try to import tensorflow, deepface, and cv2; print versions
    try:
        import tensorflow as tf
        print(f"   [OK] tensorflow installed (v{tf.__version__})")
    except ImportError as e:
        print(f"   [WARN] tensorflow NOT found: {e}")

    try:
        import deepface
        print(f"   [OK] deepface installed (v{getattr(deepface, '__version__', 'unknown')})")
    except ImportError as e:
        print(f"   [WARN] deepface NOT found: {e}")
        
    try:
        import cv2
        print(f"   [OK] cv2 installed (v{cv2.__version__})")
    except ImportError as e:
        print(f"   [ERROR] cv2 NOT found: {e}")

    print("\n3. Testing FaceDetector")
    
    # 4. Run FaceDetector on inputs/sample.jpg
    image_path = Path("inputs/sample.jpg")
    if not image_path.exists():
        print(f"   [ERROR] Test image not found at {image_path}")
        return
        
    try:
        from modules.face_detector import FaceDetector, _USE_HAAR, _USE_DNN
        print(f"   Initializing FaceDetector (requested backend: retinaface)...")
        
        # Detector uses rich console internally, so output will be styled
        detector = FaceDetector(detector_backend='retinaface', model_name='Facenet512')
        result = detector.detect_and_crop(str(image_path), output_path="inputs/target_cropped.jpg")
        
        print("\n   [OK] detect_and_crop() succeeded.")
        print(f"   Result Area: {result.get('facial_area')}")
        print(f"   Confidence:  {result.get('confidence')}")
        
        if _USE_HAAR or _USE_DNN:
            print("\n   [INFO] Note: FaceDetector gracefully fell back to OpenCV (Haar/DNN)")
            print("          because the retinaface dependency is decoupled in this pipeline stage.")
            
    except Exception as e:
        print(f"\n   [ERROR] FaceDetector encountered an exception: {e}")

if __name__ == "__main__":
    main()
