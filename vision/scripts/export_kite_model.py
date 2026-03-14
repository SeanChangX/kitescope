#!/usr/bin/env python3
"""
Export a trained single-class YOLO model for KiteScope.

This script is intended for models already trained specifically for kite
detection, where class 0 is kite. It exports the model into the deployment
formats used by KiteScope:

- ONNX for CPU inference
- TensorFlow SavedModel as an intermediate artifact
- TFLite for further Edge TPU compilation

Examples:
  python export_kite_model.py --source-model runs/detect/train3/weights/best.pt
  python export_kite_model.py --source-model runs/detect/train3/weights/best.pt --targets onnx
  python export_kite_model.py --source-model runs/detect/train3/weights/best.pt --rep-dir /path/to/images
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
from typing import Iterable


ALL_TARGETS = ("onnx", "saved-model", "tflite")


def _default_output_dir() -> Path:
    return Path(__file__).resolve().parent


def _resolve_writable_dir(preferred: Path) -> Path:
    preferred = preferred.resolve()
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        probe = preferred / ".kitescope_write_test"
        probe.write_text("ok")
        probe.unlink()
        return preferred
    except OSError:
        fallback = Path.cwd().resolve()
        fallback.mkdir(parents=True, exist_ok=True)
        print(f"Warning: cannot write to {preferred}. Falling back to {fallback}.")
        return fallback


def _copy_file(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst.resolve()


def _copy_tree(src: Path, dst: Path) -> Path:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return dst.resolve()


def _expand_targets(requested: list[str]) -> list[str]:
    requested_set = set(requested)
    if "all" in requested_set:
        requested_set = set(ALL_TARGETS)
    if "tflite" in requested_set:
        requested_set.add("saved-model")
    return [target for target in ALL_TARGETS if target in requested_set]


def _infer_default_name(source_model: Path) -> str:
    stem = source_model.stem
    if stem == "best" and source_model.parent.name == "weights":
        run_dir = source_model.parent.parent.name
        return f"{run_dir}_kite"
    if stem == "last" and source_model.parent.name == "weights":
        run_dir = source_model.parent.parent.name
        return f"{run_dir}_kite_last"
    return stem


def _load_model(source_model: str):
    from ultralytics import YOLO

    print("Loading", source_model)
    return YOLO(source_model)


def _export_onnx(model, output_path: Path, imgsz: int, opset: int) -> Path:
    print(f"Exporting ONNX (imgsz={imgsz}, opset={opset})...")
    exported = Path(str(model.export(format="onnx", imgsz=imgsz, opset=opset))).resolve()
    return _copy_file(exported, output_path)


def _export_saved_model(model, output_dir: Path, imgsz: int) -> Path:
    print(f"Exporting SavedModel (imgsz={imgsz})...")
    exported = Path(str(model.export(format="saved_model", imgsz=imgsz))).resolve()
    return _copy_tree(exported, output_dir)


def _load_image_paths(rep_dir: Path) -> list[Path]:
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    return sorted(path for path in rep_dir.rglob("*") if path.is_file() and path.suffix.lower() in exts)


def _letterbox(image, new_shape: tuple[int, int]):
    import cv2

    h, w = image.shape[:2]
    r = min(new_shape[0] / h, new_shape[1] / w)
    new_unpad = (round(w * r), round(h * r))
    resized = cv2.resize(image, new_unpad, interpolation=cv2.INTER_LINEAR)
    dw = (new_shape[1] - new_unpad[0]) / 2
    dh = (new_shape[0] - new_unpad[1]) / 2
    top, bottom = round(dh - 0.1), round(dh + 0.1)
    left, right = round(dw - 0.1), round(dw + 0.1)
    return cv2.copyMakeBorder(
        resized,
        top,
        bottom,
        left,
        right,
        cv2.BORDER_CONSTANT,
        value=(114, 114, 114),
    )


def _representative_dataset(image_paths: list[Path], input_h: int, input_w: int) -> Iterable[list[object]]:
    import cv2
    import numpy as np

    def gen():
        for path in image_paths:
            img = cv2.imread(str(path))
            if img is None:
                continue
            # Match the runtime TFLite preprocessing as closely as possible so
            # INT8 calibration sees the same input distribution as deployment.
            img = _letterbox(img, (input_h, input_w))
            sample = img.astype(np.float32).reshape(1, input_h, input_w, 3)
            yield [sample]

    return gen


def _export_tflite_from_saved_model(
    input_saved_model: Path,
    output_tflite: Path,
    rep_dir: Path | None,
) -> Path:
    import tensorflow as tf

    print("Converting SavedModel to TFLite:", input_saved_model)
    converter = tf.lite.TFLiteConverter.from_saved_model(str(input_saved_model))

    if rep_dir is not None:
        image_paths = _load_image_paths(rep_dir)
        if not image_paths:
            raise ValueError(f"No calibration images found in {rep_dir}")
        loaded = tf.saved_model.load(str(input_saved_model))
        serving = loaded.signatures["serving_default"]
        _, keyword_inputs = serving.structured_input_signature
        if len(keyword_inputs) != 1:
            raise ValueError(f"Expected exactly one serving input, found {list(keyword_inputs.keys())}")
        input_spec = next(iter(keyword_inputs.values()))
        input_shape = input_spec.shape.as_list()
        if len(input_shape) != 4 or input_shape[1] is None or input_shape[2] is None:
            raise ValueError(f"Expected static NHWC input shape, got {input_shape}")

        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        converter.representative_dataset = _representative_dataset(
            image_paths=image_paths,
            input_h=int(input_shape[1]),
            input_w=int(input_shape[2]),
        )
        converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
        converter.inference_input_type = tf.uint8
        # Keep output as float32: YOLOv8 packs bbox coords (0-640) and confidence
        # (0-1) in one tensor.  A single uint8 scale (~3.14) rounds all confidence
        # values to 0.  Float32 output adds one CPU dequantize op (negligible).
        converter.inference_output_type = tf.float32

    output_tflite.parent.mkdir(parents=True, exist_ok=True)
    output_tflite.write_bytes(converter.convert())
    return output_tflite.resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a trained single-class kite YOLO model for KiteScope.")
    parser.add_argument(
        "--source-model",
        required=True,
        help="Path to a trained Ultralytics model, typically runs/detect/.../weights/best.pt",
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        choices=("all",) + ALL_TARGETS,
        default=["all"],
        help="Artifacts to produce. 'all' builds every supported artifact.",
    )
    parser.add_argument("--output-dir", default=str(_default_output_dir()), help="Directory to place exported artifacts.")
    parser.add_argument("--name", default=None, help="Artifact base name prefix. Defaults to the source model name.")
    parser.add_argument("--imgsz", type=int, default=640, help="Export image size.")
    parser.add_argument("--opset", type=int, default=12, help="ONNX opset version.")
    parser.add_argument(
        "--rep-dir",
        default=None,
        help="Representative dataset image directory for full INT8 TFLite export.",
    )
    args = parser.parse_args()

    source_model = Path(args.source_model).resolve()
    if not source_model.is_file():
        raise FileNotFoundError(f"Source model not found: {source_model}")

    targets = _expand_targets(args.targets)
    output_dir = _resolve_writable_dir(Path(args.output_dir))
    rep_dir = Path(args.rep_dir).resolve() if args.rep_dir else None
    base_name = args.name or _infer_default_name(source_model)

    onnx_path = output_dir / f"{base_name}.onnx"
    saved_model_dir = output_dir / f"{base_name}_saved_model"
    tflite_suffix = "int8" if rep_dir else "fp32"
    tflite_path = output_dir / f"{base_name}_{tflite_suffix}.tflite"

    produced: dict[str, Path] = {}
    model = None

    if "onnx" in targets:
        model = model or _load_model(str(source_model))
        produced["onnx"] = _export_onnx(model, onnx_path, args.imgsz, args.opset)
        print("Saved:", produced["onnx"])

    if "saved-model" in targets:
        model = model or _load_model(str(source_model))
        produced["saved-model"] = _export_saved_model(model, saved_model_dir, args.imgsz)
        print("Saved:", produced["saved-model"])

    if "tflite" in targets:
        saved_model_path = produced.get("saved-model")
        if saved_model_path is None:
            model = model or _load_model(str(source_model))
            saved_model_path = _export_saved_model(model, saved_model_dir, args.imgsz)
            produced["saved-model"] = saved_model_path
            print("Saved:", produced["saved-model"])
        produced["tflite"] = _export_tflite_from_saved_model(saved_model_path, tflite_path, rep_dir)
        print("Saved:", produced["tflite"])

    print()
    print("Artifacts:")
    for target in targets:
        if target in produced:
            print(f"  {target}: {produced[target]}")

    if "tflite" in produced and rep_dir is not None:
        print()
        print("Next:")
        print(f"  edgetpu_compiler {produced['tflite']}")
        print("This will produce the final *_edgetpu.tflite artifact.")
    elif "tflite" in produced:
        print()
        print("Note: The generated TFLite artifact is float32.")
        print("Pass --rep-dir /path/to/images to generate an INT8 TFLite suitable for Edge TPU compilation.")


if __name__ == "__main__":
    main()
