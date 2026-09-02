import os
import cv2
import numpy as np
from modules.face_detector import FaceDetector


def test_face_detector_returns_cropped_path(mocker, tmp_path):
    # Mock cache so it always runs detection (bypass embedding cache)
    mocker.patch(
        "modules.face_detector.FaceDetector._get_cached_embedding", return_value=None
    )

    # Mock cv2.imread and CascadeClassifier
    mock_imread = mocker.patch("cv2.imread")
    dummy_img = np.zeros((200, 200, 3), dtype=np.uint8)
    mock_imread.return_value = dummy_img

    mock_cascade = mocker.patch("cv2.CascadeClassifier")
    mock_clf = mock_cascade.return_value
    mock_clf.empty.return_value = False
    # Return a dummy bounding box (x, y, w, h)
    mock_clf.detectMultiScale.return_value = [[50, 50, 100, 100]]

    # Mock cv2.imwrite so it actually saves a file for the test
    original_imwrite = cv2.imwrite

    def side_effect_imwrite(filename, img):
        # Just create an empty file so os.path.exists passes
        with open(filename, "wb") as f:
            f.write(b"")
        return True

    mocker.patch("cv2.imwrite", side_effect=side_effect_imwrite)

    # Create dummy source image
    img_path = str(tmp_path / "dummy.jpg")
    with open(img_path, "wb") as f:
        f.write(b"dummy bytes")

    detector = FaceDetector(detector_backend="opencv")
    out_path = str(tmp_path / "cropped.jpg")
    result = detector.detect_and_crop(img_path, output_path=out_path)

    assert isinstance(result, dict)
    assert "cropped_path" in result
    assert result["cropped_path"] == out_path
    assert os.path.exists(result["cropped_path"])
    assert "confidence" in result
    assert "embedding" in result
    assert "histogram_embedding" in result
    assert len(result["embedding"]) == 128
    assert result["backend_used"] == "opencv_fallback"


def test_compare_faces(mocker, tmp_path):
    # Mock cv2.imread
    mock_imread = mocker.patch("cv2.imread")
    # Return two identical images to get high similarity
    dummy_img = np.ones((100, 100, 3), dtype=np.uint8) * 128
    mock_imread.return_value = dummy_img

    detector = FaceDetector(detector_backend="opencv")

    # Paths don't matter since imread is mocked
    score = detector.compare_faces("face1.jpg", "face2.jpg")

    # Identical images should have cosine similarity near 1.0
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0
    assert score > 0.9


def test_deepface_primary_embedding(mocker, tmp_path):
    """Test that DeepFace is used and returns a 512-d ArcFace embedding when available."""
    mocker.patch("modules.face_detector._HAS_DEEPFACE", True)

    mock_imread = mocker.patch("cv2.imread")
    mock_imread.return_value = np.zeros((200, 200, 3), dtype=np.uint8)

    # Mock cv2.imwrite so os.path.exists passes in subsequent logic
    mocker.patch("cv2.imwrite", side_effect=lambda f, i: open(f, "wb").close() or True)

    import modules.face_detector

    if not hasattr(modules.face_detector, "DeepFace"):
        modules.face_detector.DeepFace = type(
            "DeepFace",
            (),
            {
                "represent": lambda: None,
                "verify": lambda: None,
                "build_model": lambda x: None,
                "extract_faces": lambda *args, **kwargs: None,
            },
        )

    mock_build = mocker.patch.object(modules.face_detector.DeepFace, "build_model")
    mock_extract = mocker.patch.object(modules.face_detector.DeepFace, "extract_faces")
    mock_represent = mocker.patch.object(modules.face_detector.DeepFace, "represent")
    # DeepFace.represent returns a list of objects
    mock_represent.return_value = [
        {
            "embedding": [0.5] * 512,
            "facial_area": {"x": 10, "y": 10, "w": 100, "h": 100},
            "face_confidence": 0.99,
        }
    ]

    # Mock cached embedding
    mocker.patch(
        "modules.face_detector.FaceDetector._get_cached_embedding", return_value=None
    )

    # Mock cache saving
    mocker.patch("modules.face_detector.FaceDetector._cache_embedding")

    img_path = str(tmp_path / "dummy.jpg")
    with open(img_path, "wb") as f:
        f.write(b"dummy")

    detector = FaceDetector(offline_fallback=False)
    out_path = str(tmp_path / "cropped.jpg")

    result = detector.detect_and_crop(img_path, output_path=out_path)

    assert result["embedding_method"] == "arcface"
    assert result["backend_used"] == "retinaface"
    assert len(result["embedding"]) == 512
    assert len(result["histogram_embedding"]) == 128
    mock_build.assert_called_with("ArcFace")
    mock_extract.assert_called()
    mock_represent.assert_called_once()


def test_deepface_fallback_on_failure(mocker, tmp_path):
    """Test that if DeepFace fails, it falls back to OpenCV histogram."""
    mocker.patch("modules.face_detector._HAS_DEEPFACE", True)

    mock_imread = mocker.patch("cv2.imread")
    mock_imread.return_value = np.zeros((200, 200, 3), dtype=np.uint8)
    mocker.patch("cv2.imwrite", side_effect=lambda f, i: open(f, "wb").close() or True)

    import modules.face_detector

    if not hasattr(modules.face_detector, "DeepFace"):
        modules.face_detector.DeepFace = type(
            "DeepFace",
            (),
            {
                "represent": lambda: None,
                "verify": lambda: None,
                "build_model": lambda x: None,
                "extract_faces": lambda *args, **kwargs: None,
            },
        )

    # Mock deepface build_model to raise an exception, triggering eager fallback
    mock_build = mocker.patch.object(
        modules.face_detector.DeepFace,
        "build_model",
        side_effect=ValueError("Tensorflow not found"),
    )

    # Mock Haar so fallback succeeds
    mock_cascade = mocker.patch("cv2.CascadeClassifier")
    mock_clf = mock_cascade.return_value
    mock_clf.empty.return_value = False
    mock_clf.detectMultiScale.return_value = [[50, 50, 100, 100]]

    mocker.patch(
        "modules.face_detector.FaceDetector._get_cached_embedding", return_value=None
    )
    mocker.patch("modules.face_detector.FaceDetector._cache_embedding")

    img_path = str(tmp_path / "dummy.jpg")
    with open(img_path, "wb") as f:
        f.write(b"dummy")

    detector = FaceDetector(offline_fallback=False)
    out_path = str(tmp_path / "cropped.jpg")

    result = detector.detect_and_crop(img_path, output_path=out_path)

    assert result["embedding_method"] == "opencv_histogram_fallback"
    assert result["backend_used"] == "opencv_fallback"
    assert len(result["embedding"]) == 128
    assert len(result["histogram_embedding"]) == 128
    mock_build.assert_called_once_with("ArcFace")
