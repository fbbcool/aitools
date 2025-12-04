from aidb.caption_joy import CapJoy
from aidb.hfdataset import HFDatasetImg

caper = CapJoy(trigger="1fem")
force = True

# hfd = HFDatasetImg(repo_id="fbbcool/gts01_r35")
hfd = HFDatasetImg(repo_id="fbbcool/1fem", force_meta_dl=True)
hfd.cache()

n = len(hfd)
error = 0
for idx in range(n):
    print(f"{idx}:\n")
    try:
        if hfd.captions_joy[idx]:
            print("already captionized.")
            if not force:
                continue
        img = hfd.pil(idx)
        caption = caper.img_caption(img)
        print(f"{caption}\n")
        hfd.img_set_caption_joy(idx, caption)
        if idx % 100 == 0:
            hfd.save_to_jsonl(force=True)
    except Exception as e:
        error += 1
        print(f"oops! something went wrong:\n{e}")

print(f"\n\tDONE with {error} errors.")
hfd.save_to_jsonl(force=True)

