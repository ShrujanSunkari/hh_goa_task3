import os
import cv2
import numpy as np
import pytest
from unittest.mock import patch
from modules.face_detector import FaceDetector

@patch("modules.face_detector.DeepFace.represent", create=True)
def test_face_detector_returns_cropped_path(mock_represent, tmp_path):
    # Mock return value just in case DeepFace was used
    mock_represent.return_value = [{
        "facial_area": {"x": 10, "y": 10, "w": 100, "h": 100},
        "confidence": 0.99,
        "embedding": [0.0] * 512
    }]

    # Create a dummy test image
    img_path = str(tmp_path / "dummy.jpg")
    dummy_img = np.zeros((200, 200, 3), dtype=np.uint8)
    cv2.imwrite(img_path, dummy_img)
    
    detector = FaceDetector()
    out_path = str(tmp_path / "cropped.jpg")
    result = detector.detect_and_crop(img_path, output_path=out_path)

    assert "cropped_path" in result
    assert result["cropped_path"] == out_path
    assert os.path.exists(result["cropped_path"])
