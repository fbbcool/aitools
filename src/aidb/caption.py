from aidb.caption_joy import CapJoy
from aidb.hfdataset import HFDatasetImg

caper = CapJoy(configure_ai=True)
hfd = HFDatasetImg(repo_id="fbbcool/gts01_r5")

n = 4
for idx in range(n):
    img = hfd.pil(idx)
    prompt = hfd.prompt(idx)
    caption = caper.img_caption(img, prompt)
    print(f"{idx}:\n{caption}\n")
    hfd.img_set_caption_joy(idx, caption)
hfd.save_to_jsonl()