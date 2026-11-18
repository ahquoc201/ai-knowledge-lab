"""ONNX Runtime Export and Inference for Multilingual Cross-Encoder Reranker (T260037).

Provides:
- Deterministic ONNX FP32 export from HuggingFace PyTorch models.
- ONNX Runtime dynamic INT8 quantization tailored for x86_64 CPU (AVX2/FMA).
- Lightweight ONNXCrossEncoder engine matching SentenceTransformers CrossEncoder interface.
- Fine-grained timing breakdown (tokenization, forward inference, total).
"""

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
from onnxruntime.quantization import QuantType, quantize_dynamic
from transformers import AutoModelForSequenceClassification, AutoTokenizer

DEFAULT_RERANKER_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "storage/models/reranker"
DEFAULT_INTRA_OP_THREADS = 4
MAX_SEQ_LENGTH = 512


def compute_file_sha256(file_path: Path) -> str:
    """Calculate SHA256 hexadecimal digest of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_file_size_mb(file_path: Path) -> float:
    """Return file size in megabytes rounded to 2 decimal places."""
    return round(file_path.stat().st_size / (1024.0 * 1024.0), 2)


@dataclass(frozen=True, slots=True)
class RerankerArtifactMetadata:
    model_name: str
    architecture: str
    max_length: int
    fp32_path: str
    fp32_size_mb: float
    fp32_sha256: str
    int8_path: str
    int8_size_mb: float
    int8_sha256: str
    compression_ratio: float


def export_and_quantize_reranker(
    model_name: str = DEFAULT_RERANKER_MODEL,
    output_dir: Path | None = None,
    *,
    force_reexport: bool = False,
) -> RerankerArtifactMetadata:
    """Export PyTorch Cross-Encoder to ONNX FP32 and generate dynamic INT8 quantized artifact.

    Stores models locally in storage/models/reranker (ignored by Git).
    Uses TorchScript legacy export (dynamo=False) for PyTorch 2.14+ compatibility without extra dependencies.
    """
    target_dir = output_dir or DEFAULT_CACHE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    fp32_path = target_dir / "model_fp32.onnx"
    int8_path = target_dir / "model_int8.onnx"

    tokenizer = AutoTokenizer.from_pretrained(model_name)

    if force_reexport or not fp32_path.is_file():
        # 1. Load PyTorch model
        pt_model = AutoModelForSequenceClassification.from_pretrained(model_name)
        pt_model.eval()

        # Dummy inputs for tracing dynamic axes
        dummy_query = "Thuật toán kiểm soát truy cập và giới hạn tốc độ Redis"
        dummy_doc = "Hệ thống sử dụng thuật toán Token Bucket kết hợp Redis cho hạ tầng phân tán."
        dummy_inputs = tokenizer(
            dummy_query,
            dummy_doc,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=MAX_SEQ_LENGTH,
        )

        # 2. Export to ONNX FP32
        torch.onnx.export(
            pt_model,
            (dummy_inputs["input_ids"], dummy_inputs["attention_mask"]),
            str(fp32_path),
            input_names=["input_ids", "attention_mask"],
            output_names=["logits"],
            dynamic_axes={
                "input_ids": {0: "batch_size", 1: "sequence_length"},
                "attention_mask": {0: "batch_size", 1: "sequence_length"},
                "logits": {0: "batch_size"},
            },
            opset_version=14,
            do_constant_folding=True,
            dynamo=False,
        )

    if force_reexport or not int8_path.is_file():
        # 3. Dynamic INT8 quantization
        quantize_dynamic(
            model_input=str(fp32_path),
            model_output=str(int8_path),
            weight_type=QuantType.QInt8,
        )

    # Calculate checksums & sizes
    fp32_size = get_file_size_mb(fp32_path)
    fp32_hash = compute_file_sha256(fp32_path)
    int8_size = get_file_size_mb(int8_path)
    int8_hash = compute_file_sha256(int8_path)
    compression = round(fp32_size / int8_size, 2) if int8_size > 0 else 1.0

    return RerankerArtifactMetadata(
        model_name=model_name,
        architecture="XLMRobertaForSequenceClassification",
        max_length=MAX_SEQ_LENGTH,
        fp32_path=str(fp32_path),
        fp32_size_mb=fp32_size,
        fp32_sha256=fp32_hash,
        int8_path=str(int8_path),
        int8_size_mb=int8_size,
        int8_sha256=int8_hash,
        compression_ratio=compression,
    )


class ONNXCrossEncoder:
    """Drop-in CrossEncoder inference engine powered by ONNX Runtime on CPU."""

    def __init__(
        self,
        model_path: str | Path,
        tokenizer_name: str = DEFAULT_RERANKER_MODEL,
        *,
        num_threads: int = DEFAULT_INTRA_OP_THREADS,
        max_length: int = MAX_SEQ_LENGTH,
    ) -> None:
        self.model_path = Path(model_path)
        if not self.model_path.is_file():
            raise FileNotFoundError(f"ONNX model file not found: {self.model_path}")

        self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)
        self.max_length = max_length
        self.num_threads = num_threads

        # Configure ONNX Runtime session
        self.session_options = ort.SessionOptions()
        self.session_options.intra_op_num_threads = num_threads
        self.session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self.session = ort.InferenceSession(
            str(self.model_path),
            self.session_options,
            providers=["CPUExecutionProvider"],
        )

    def predict(
        self,
        sentences: list[tuple[str, str]] | list[list[str]],
        *,
        batch_size: int = 32,
    ) -> np.ndarray:
        """Score sentence pairs and return array of logits."""
        scores, _ = self.predict_with_timing(sentences, batch_size=batch_size)
        return scores

    def predict_with_timing(
        self,
        sentences: list[tuple[str, str]] | list[list[str]],
        *,
        batch_size: int = 32,
    ) -> tuple[np.ndarray, dict[str, float]]:
        """Score sentence pairs with isolated tokenization and forward-pass latencies."""
        if not sentences:
            return np.array([], dtype=np.float32), {"tokenize_ms": 0.0, "forward_ms": 0.0, "total_ms": 0.0}

        t_start = time.perf_counter()

        # 1. Tokenization
        t_tok_start = time.perf_counter()
        queries = [s[0] for s in sentences]
        passages = [s[1] for s in sentences]
        inputs = self.tokenizer(
            queries,
            passages,
            return_tensors="np",
            padding=True,
            truncation=True,
            max_length=self.max_length,
        )
        t_tok_ms = (time.perf_counter() - t_tok_start) * 1000.0

        # 2. ONNX Inference
        t_fwd_start = time.perf_counter()
        total_items = len(sentences)
        all_logits: list[np.ndarray] = []

        for start_idx in range(0, total_items, batch_size):
            end_idx = min(start_idx + batch_size, total_items)
            batch_inputs = {
                "input_ids": inputs["input_ids"][start_idx:end_idx],
                "attention_mask": inputs["attention_mask"][start_idx:end_idx],
            }
            outputs = self.session.run(None, batch_inputs)
            logits = outputs[0].squeeze(-1)
            # Ensure 1D array even if single pair
            if logits.ndim == 0:
                logits = np.expand_dims(logits, axis=0)
            all_logits.append(logits)

        t_fwd_ms = (time.perf_counter() - t_fwd_start) * 1000.0
        t_total_ms = (time.perf_counter() - t_start) * 1000.0

        merged_logits = np.concatenate(all_logits, axis=0)
        timing = {
            "tokenize_ms": round(t_tok_ms, 3),
            "forward_ms": round(t_fwd_ms, 3),
            "total_ms": round(t_total_ms, 3),
        }
        return merged_logits, timing
