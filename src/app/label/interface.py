from typing import Final
import gradio as gr
import numpy as np
from PIL import Image

from config import pools, Pool

IMG_NUM_PER_PAGE: Final = 100

rows_caption = [gr.Textbox(placeholder=str(i), visible=False) for i in range(IMG_NUM_PER_PAGE)]
rows_img = [gr.Image(Image.new('RGB', (1, 1)), visible=False, type="pil", render=False) for i in range(IMG_NUM_PER_PAGE)]
rows_pool = [gr.Textbox(value="None", visible=False) for i in range(IMG_NUM_PER_PAGE)]
rows_pool_idx = [gr.Number(value=i, visible=False) for i in range(IMG_NUM_PER_PAGE)]
pool: Pool = Pool()

def pool_render(poolname:str) -> None:
    global pool
    if poolname == "None":
        pool = Pool()
        return [gr.update(visible=False, value=poolname) for i in range(IMG_NUM_PER_PAGE)]
    pool = Pool(poolname)
    return [gr.update(visible=True, value=poolname) for i in range(IMG_NUM_PER_PAGE)]

def load_img(idx: int):
    if idx >= len(pool):
        return gr.update(visible=False)
    return gr.update(visible=True, value=Image.open(pool[idx]["img_url"]))


with gr.Blocks() as interface:
    #gr.Markdown("Template")
    with gr.Row():
        labels = ["None"] + pools.labels
        pools_select = gr.Dropdown(labels, label="Choose Pool", multiselect=False, value=labels[0], interactive=True)
        pools_select.change(pool_render,pools_select, rows_pool)
    with gr.Row():
        for i in range(IMG_NUM_PER_PAGE):
            rows_pool[i].render()
            rows_pool_idx[i].render()
            rows_img[i].render()
            rows_caption[i].render()
            rows_pool[i].change(load_img, rows_pool_idx[i], rows_img[i])


