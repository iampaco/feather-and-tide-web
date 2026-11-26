"""Compare the native and lake-reassembled GLB review frames for visible regressions."""
from hashlib import sha256
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def compare(candidate):
    names=("review_before_fork.png","roundtrip_before_fork.png")
    native,returned=[np.asarray(Image.open(candidate/name).convert("RGB"),dtype=np.int16) for name in names]
    if native.shape!=returned.shape or native.shape!=(393,852,3):
        raise ValueError((native.shape,returned.shape))
    delta=np.abs(native-returned)
    pixel_delta=delta.max(axis=2)
    extra_dark=(returned.max(axis=2)<=8)&(native.max(axis=2)>8)
    limits={"mean_absolute_8bit_channel_delta":2.4,
            "pixels_with_max_channel_delta_over_36":499,"additional_near_black_pixels":19}
    stats={"frame_px":[852,393],
           "mean_absolute_8bit_channel_delta":float(delta.mean()),
           "pixels_with_max_channel_delta_over_36":int((pixel_delta>36).sum()),
           "additional_near_black_pixels":int(extra_dark.sum()),
           "images_sha256":{name:sha256((candidate/name).read_bytes()).hexdigest() for name in names}}
    if any(stats[key]>limit for key,limit in limits.items()):
        raise ValueError(stats)
    return {"result":"pass","thresholds":limits,**stats}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate",type=Path)
    parser.add_argument("report",type=Path)
    args=parser.parse_args()
    args.report.write_text(json.dumps(compare(args.candidate),indent=2)+"\n")
