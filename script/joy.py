from ait.caption import Joy

from aidb import HFDataset
from ait.tools.images import image_from_url

caper = Joy('1tongue')
force = True

hfd = HFDataset('fbbcool/test')
hfd.cache()

num_skip = 0
for id in hfd.ids:
    if id is None:
        print('[skip] id none.')
        num_skip += 1
        continue
    url_img = hfd.url_file_from_id(id)
    if url_img is None:
        print('[skip] url_img none.')
        num_skip += 1
        continue
    caption = hfd.caption_from_id(id)
    if caption is not None and not force:
        print('[skip] caption not forced.')
        num_skip += 1
        continue
    img = image_from_url(url_img, verbose=True)
    if img is None:
        print('[skip] img not loaded.')
        num_skip += 1
        continue
    caption = caper.img_caption(img)
    print(f'{caption}\n')
    hfd.set_caption(id, caption)

print(f'\n\tDONE with {num_skip} skips.')
hfd.save()
