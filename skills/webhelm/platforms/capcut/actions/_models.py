import json

from _capcut_common import available_models


result = {
    media_type: [
        option["name"]
        for option in available_models(media_type, js, wait_for_element)
    ]
    for media_type in ("image", "video")
}
print(json.dumps(result, indent=2))