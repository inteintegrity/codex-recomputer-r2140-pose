# Physical-device validation

Tested on the physical reComputer AI R2140 with Hailo-8 and existing HailoRT, driver, and firmware 4.23.0.

Input: `video/test.mp4`, SHA-256 `68bcfd7f986e9412dfafcc6d20c998c0441a74d5d3384bc276e71ec2558f2536`.

| Check | Observed result |
| --- | --- |
| PC upload through HTTP | Accepted and processed |
| Input / output dimensions | 1920 × 1080 |
| Playback FPS / duration | 25 / 9.32 seconds |
| Input / output frames | 233 / 233 |
| Inference FPS, two full runs | 32.20 / 32.41 |
| Overall processing FPS | 13.26 / approximately 13.4 |
| First run wall time | 17.73 seconds |
| Person detections / visible keypoints | 447 / 6,416 across the first run |
| Output | H.264, YUV420p MP4 |
| Complete output decode | FFmpeg decoded all frames without error |
| Browser playback | readyState 4, 1920 × 1080, 9.32-second duration |
| Seeking | HTTP 206 with valid Content-Range |
| Download | MP4 attachment returned successfully |

Output was visually inspected for human boxes, visible keypoints, skeleton connections, and the FPS overlay. The full annotated sample is included as `video/test-pose.mp4`.

## Recovery and audio

`validate_remote.sh` verifies rejection of invalid extensions, failed-MP4 recovery, subsequent hardware inference, HTTP 409 busy protection, audio retention, output frame count, video seeking, and downloads. It also confirms the accelerator is available afterward.

The final short audio regression test retained all 52 video frames and AAC audio, and measured 31.77 inference FPS and 12.48 overall processing FPS. Short-clip startup/encoding costs affect these numbers.

## Issues fixed through testing

1. HailoRT passes `completion_info` by keyword. Matching that callback signature fixed the first inference crash.
2. FFmpeg `-shortest` truncated video when audio ended earlier. Removing it preserved all processed video frames, verified with `ffprobe`.

No driver reinstall or system configuration changes were required.
