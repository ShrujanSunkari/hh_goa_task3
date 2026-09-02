"""
api.py
------
FastAPI endpoint for health checks and executing the HH GOA 2026 Task 3 pipeline.
"""

import argparse
import base64
import os
import shutil
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel

from pipeline import (
    stage1_detect,
    stage2_search,
    stage3_anchor,
    stage4_verify,
    compute_final_verdict,
    generate_proof_certificate
)

app = FastAPI(title="HH GOA 2026 Face Identification API")

class HealthCheckResponse(BaseModel):
    status: str

@app.get("/health", response_model=HealthCheckResponse)
def health_check():
    return {"status": "ok"}

@app.post("/verify")
def verify_identity(file: UploadFile = File(...)) -> Dict[str, Any]:
    # 1. Save uploaded file temporarily
    inputs_dir = Path("inputs")
    inputs_dir.mkdir(exist_ok=True)
    
    file_path = inputs_dir / f"uploaded_{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        # 2. Setup mock args for the pipeline
        args = argparse.Namespace(
            image=str(file_path),
            top_n=5,
            rpc=None,
            offline_mock=False,
            detector="retinaface",
            model="Facenet512",
            json=True,
            auto_demo=False
        )
        
        # 3. Run pipeline stages
        try:
            face = stage1_detect(args)
            payload, payload_hash = stage2_search(face, args)
            tx, anchor = stage3_anchor(face, payload, payload_hash, args)
            verification = stage4_verify(payload, payload_hash, tx, anchor, args)
            
            final_score = compute_final_verdict(face, payload)
            if verification.get("hash_match"):
                generate_proof_certificate(args, face, payload, tx, verification, final_score)
                
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")
            
        # 4. Format payload for JSON response
        payload_copy = dict(payload)
        if "image_bytes" in payload_copy and isinstance(payload_copy["image_bytes"], bytes):
            payload_copy["image_bytes"] = base64.b64encode(payload_copy["image_bytes"]).decode("utf-8")
            
        return {
            "face": face,
            "search": payload_copy,
            "tx": tx,
            "verification": verification,
            "final_score": final_score
        }
        
    finally:
        # Cleanup uploaded file
        if file_path.exists():
            os.remove(file_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
