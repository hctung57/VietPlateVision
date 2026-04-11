# Training Guide

This folder contains all training assets for the detector and OCR models.

## Structure

```text
training/
  configs/
    custom_data.yaml          # Dataset config for license plate detector training
    Letter_detect.yaml        # Dataset config for OCR character training
  notebooks/
    License_plate_training.ipynb
    Letter_detection.ipynb
```

## Quick Start

1. Open a notebook in `training/notebooks/`.
2. In the notebook, update config file paths to:
   - `training/configs/custom_data.yaml`
   - `training/configs/Letter_detect.yaml`
3. Run training and export models to `model/`.

## Required Weights for Inference

Make sure these two files are available:

- `model/LP_detector.pt`
- `model/LP_ocr.pt`

The web app reads these files directly.
