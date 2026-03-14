# Vision Model Tooling

This directory contains the offline tooling used to prepare detection models for KiteScope.

It is intended for dataset-to-deployment tasks such as export, quantization, compilation, and future training utilities. For application setup and runtime model selection, see the root [`README.md`](../../README.md).

## What this directory is for

Use `vision/scripts` for:

- model export
- calibration image preparation
- Edge TPU compilation
- model inspection and validation
- future training-related helpers

| File | Purpose |
| --- | --- |
| `export_kite_model.py` | Export a trained Ultralytics YOLO model to ONNX, SavedModel, and TFLite artifacts. |
| `compile_edgetpu.sh` | Compile an INT8 TFLite model into a Coral Edge TPU model using Docker. |
| `requirements.txt` | Python dependencies used by the tooling in this directory. |

## Model requirements

KiteScope expects the following runtime contract:

- the detector is single-class
- class `0` is `kite`
- CPU inference uses `*.onnx`
- Coral inference uses compiled `*_edgetpu.tflite`

If those assumptions are not true, the model may load but produce invalid results.

## Environment setup

Create a Python environment for the tooling:

```bash
cd vision/scripts
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Pipeline

The recommended workflow is:

1. Prepare and verify the dataset.
2. Prepare the Ultralytics dataset configuration.
3. Train the `.pt` model.
4. Validate the trained model.
5. Export ONNX and verify CPU behavior.
6. Prepare representative calibration images.
7. Export INT8 TFLite.
8. Compile the Edge TPU model.
9. Upload the final runtime artifacts into KiteScope.

## Dataset preparation

Before training, verify the dataset is suitable for deployment:

- the images match real camera viewpoints
- labels are correct and consistent
- train and validation splits are defined
- class `0` is `kite`

Recommended checks:

- verify bounding boxes align with the actual kite
- verify there are no missing positive labels
- verify validation images are not just duplicates of training images

## Dataset configuration

Ultralytics training requires a dataset configuration file, typically named `data.yaml`.

That configuration should define:

- the dataset root path
- the training image split
- the validation image split
- optionally the test image split
- the class list

For KiteScope, the class list should contain only one class and that class must be `kite` at index `0`.

Before training, verify that your dataset configuration resolves to the expected folders and images.

## Training

Training is typically performed with Ultralytics YOLO outside this directory.

The expected output of the training stage is a weight file such as: `best.pt`

Before export, confirm the trained model is usable on real images. Export and Coral compilation will not fix a poor training result.

Install Ultralytics in the environment you want to use for training:

```bash
python3 -m pip install ultralytics
```

Train a model with the Ultralytics CLI:

```bash
yolo detect train \
  data="../path/to/data.yaml" \
  model="yolov8n.pt" \
  imgsz=640 \
  epochs=100 \
  batch=16 \
  project="../path/to/runs" \
  name="kite_train"
```

Common training parameters:

- `data`: dataset configuration file
- `model`: pretrained starting checkpoint such as `yolov8n.pt`
- `imgsz`: training image size
- `epochs`: number of training epochs
- `batch`: batch size
- `project` and `name`: output location for training runs

Training output is typically written to a run directory such as:

- `../path/to/runs/kite_train/weights/best.pt`

You can also continue training from an existing checkpoint:

```bash
yolo detect train \
  model="../path/to/runs/kite_train/weights/last.pt" \
  data="../path/to/data.yaml" \
  imgsz=640 \
  epochs=50
```

## Validation

Validate the trained model before export:

```bash
yolo detect val \
  model="../path/to/runs/kite_train/weights/best.pt" \
  data="../path/to/data.yaml" \
  imgsz=640
```

Recommended checks before export:

- the validation metrics are reasonable for your deployment needs
- the model detects kites on real sample images
- confidence values are stable and not obviously collapsed
- the model output corresponds to the single `kite` class only

## Export ONNX

Export ONNX first to validate the CPU path:

```bash
cd vision/scripts
source venv/bin/activate
python export_kite_model.py \
  --source-model "../path/to/best.pt" \
  --targets onnx
```

Output:

- `train_name_kite.onnx`

This is the recommended first deployment artifact because it is easier to validate than the Coral path.

## Representative calibration images

INT8 export quality depends on representative images.

Use a directory of real images that resemble the deployment scene:

- similar camera angle
- similar object scale
- similar lighting and background conditions

Supported formats:

- `.jpg`
- `.jpeg`
- `.png`
- `.bmp`
- `.webp`

## Export TFLite

Export TFLite using representative calibration images:

```bash
cd vision/scripts
source venv/bin/activate
python export_kite_model.py \
  --source-model "../path/to/best.pt" \
  --targets tflite \
  --rep-dir "../path/to/representative-images"
```

Output:

- `train_name_kite_saved_model/`
- `train_name_kite_int8.tflite`

If `--rep-dir` is omitted, the script produces a float32 TFLite model. That file is not suitable for Edge TPU deployment.

## Compile for Coral

Compile the INT8 TFLite artifact:

```bash
cd vision/scripts
./compile_edgetpu.sh "../path/to/train_name_kite_int8.tflite"
```

Output:

- `train_name_kite_int8_edgetpu.tflite`
- `train_name_kite_int8_edgetpu.log`

The compiler log shows which operations remain on CPU after compilation.

## Runtime hand-off

KiteScope only needs the final runtime artifacts:

- `*.onnx` for CPU inference
- `*_edgetpu.tflite` for Coral inference

After these files are produced:

1. keep the ONNX file as the CPU fallback
2. upload or place the compiled `*_edgetpu.tflite` file into KiteScope model storage
3. select the desired model in the admin UI
4. confirm the active detector backend in system status

The application-level upload and model selection flow is documented in the root [`README.md`](../../README.md).

## Script reference

### `export_kite_model.py`

Exports a trained Ultralytics YOLO model into deployment artifacts.

Inputs:

- `--source-model`
- optional `--targets`
- optional `--rep-dir`
- optional `--name`
- optional `--output-dir`

Outputs:

- `*.onnx`
- `*_saved_model/`
- `*_fp32.tflite`
- `*_int8.tflite`

Examples:

```bash
python export_kite_model.py \
  --source-model "../path/to/best.pt" \
  --targets all \
  --rep-dir "../path/to/representative-images"
```

Optional flags:

- `--name train3_kite`
- `--output-dir "../path/to/output"`

### `compile_edgetpu.sh`

Compiles an INT8 TFLite file into a Coral Edge TPU model using a Dockerized compiler.

Input:

- `*_int8.tflite`

Outputs:

- `*_edgetpu.tflite`
- `*_edgetpu.log`

Example:

```bash
./compile_edgetpu.sh "../path/to/train_name_kite_int8.tflite"
```

### `requirements.txt`

Contains the Python dependencies needed by the current export tools.

## Troubleshooting

- `No calibration images found`
  The `--rep-dir` directory does not contain supported image files.

- `edgetpu_compiler: command not found`
  Use `compile_edgetpu.sh` instead of installing the compiler on the host.

- The compiled model loads but produces no detections
  Re-check that the source model is truly single-class, that class `0` is `kite`, and that the representative images are close to the real deployment scene.

- The compiled model uses some CPU ops
  Read the generated `*_edgetpu.log` file. Partial CPU fallback is normal for some models.

- Coral runtime works only after manually re-selecting the model
  Make sure the selected runtime file is the new `*_edgetpu.tflite` artifact, not an older broken export left in the model volume.
