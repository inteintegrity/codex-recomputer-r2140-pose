# Third-party resources

## Hailo Apps source code

`official_inference.py` and `official_pose_utils.py` originate from
[hailo-ai/hailo-apps](https://github.com/hailo-ai/hailo-apps), commit
`c61f843b618ea2faa20dad79097c0591900319f4`.

- Inference wrapper: `hailo_apps/python/core/common/hailo_inference.py`.
- Pose decoder: `hailo_apps/python/standalone_apps/pose_estimation/pose_estimation_utils.py`.
- Adaptation: the decoder's Hailo Apps logger import is replaced with Python standard logging.
- Copyright (c) 2024 Hailo; MIT license retained in [HAILO-LICENSE](HAILO-LICENSE).

## Model and runtime

The official precompiled YOLOv8m-Pose HEF is downloaded directly from Hailo Model Zoo using `download_model.py`. It is not bundled or relicensed by this repository. The Hailo model and runtime remain subject to their respective upstream terms. This repository's MIT license applies to its application code and documentation; it does not change upstream model, runtime, or media rights.

## Sample media

`video/test.mp4` is the project owner's supplied demonstration clip. `video/test-pose.mp4` and `docs/images/pose-result.jpg` are derived annotated outputs. They are included to reproduce and inspect the demonstrated workflow; no separate third-party media license is asserted.
