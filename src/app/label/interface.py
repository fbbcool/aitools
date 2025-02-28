from pathlib import Path
from typing import Any, Final
import gradio as gr
import numpy as np
from PIL import Image

from config import pools, Pool

IMG_NUM_PER_PAGE: Final = 100
IMG_SIZE: Final = 250
IMG_COLUMS = 4
CAPS_LINES = 10

img_empty = Image.new('RGB', (1, 1))
rows_idx = [gr.Number(value=-1, visible=False) for i in range(IMG_NUM_PER_PAGE)]
rows_img = [gr.Image(img_empty, visible=False, type="pil", width=IMG_SIZE, height=IMG_SIZE) for i in range(IMG_NUM_PER_PAGE)]
rows_caption = [gr.Textbox(value="", placeholder="caption",visible=False, max_lines=CAPS_LINES,lines=CAPS_LINES) for i in range(IMG_NUM_PER_PAGE)]
pool: Pool = Pool()

def flush_pool_idx(poolname:str):
    return [gr.update(visible=False, value=-1, key=poolname) for i in range(IMG_NUM_PER_PAGE)]

def new_pool_idx(poolname:str):
    global pool
    if poolname == "None":
        pool = Pool()
        return [gr.update(visible=False, value=-1, key=poolname) for i in range(IMG_NUM_PER_PAGE)]
    if pool.name != poolname:
        pool = Pool(poolname)
        if len(pool) <= 0:
            gr.Warning(f"Pool {poolname} is empty!")
            return [gr.update(visible=False, value=-1, key=poolname) for i in range(IMG_NUM_PER_PAGE)]
        gr.Info(f"Loading pool {poolname} ...")
    return [gr.update(value=i, key=poolname) for i in range(IMG_NUM_PER_PAGE)]

def new_page_idx(page:int) -> None:
    return [gr.update(value=IMG_NUM_PER_PAGE*(page-1) + i) for i in range(IMG_NUM_PER_PAGE)]

def new_idx_img(idx: int):
    visible = True
    if idx >= len(pool):
        visible = False
    if idx < 0:
        visible = False
    
    type = "pil"
    img = img_empty
    if visible:
        type = "filepath"
        img = pool[idx]["img_url"]
    
    return gr.update(visible=visible, type=type, value=img)

def new_idx_caps(idx: int):
    visible = True
    if idx >= len(pool):
        visible = False
    if idx < 0:
        visible = False
    
    caps = [""]
    if visible:
        caps = pool[idx]["img_caps"]["train"]
        if caps:
            caps = caps[0]
        else:
            caps = ""
    
    return gr.update(visible=visible, value=caps)

def new_pool_page(poolname:str) -> None:
    num = len(pool)
    if num == 0:
        values = [1]
        return gr.update(choices=values, value=values[0])

    per = IMG_NUM_PER_PAGE
    pages = num // per + 1
    if num % per > 0:
        pages += 1
    values = [x for x in range(1,pages)]
    return gr.update(choices=values, value=values[0])

def render_group(idx: int):
    visible = False
    if idx < len(pool):
        visible = True
    if idx < 0:
        visible = False
    return gr.update(visible=visible)

def run_captioning():
    import subprocess
    url = str(pool.root)
    gr.Info("Captioning ... wait for done info!")
    subprocess.call(["./src/script/cap.sh",url])
    gr.Info("Captioning ... done!")


with gr.Blocks() as interface:
    #gr.Markdown("Template")
    with gr.Row():
        labels = ["None"] + pools.labels
        pools_select = gr.Dropdown(labels, label="Choose Pool", multiselect=False, value=labels[0], interactive=True)
        page_select = gr.Dropdown([1], label= "Page", multiselect=False, value=1,interactive=True)
        btn_do_caption = gr.Button("Captioning")
        btn_do_caption.click(run_captioning, None, None)

        pools_select.change(flush_pool_idx,pools_select, rows_idx).then(new_pool_idx,pools_select, rows_idx).then(new_pool_page, pools_select, page_select)
        page_select.change(new_page_idx,page_select, rows_idx)

    rows_group = []
    with gr.Row():
        for i in range(0,IMG_NUM_PER_PAGE,IMG_COLUMS):
            for j in range(IMG_COLUMS):
                with gr.Column():
                    with gr.Group(visible=False) as group:
                        rows_group.append(group)
                        rows_idx[i+j].render()
                        rows_img[i+j].render()
                        rows_caption[i+j].render()
                        
                        #rows_idx[i].change(new_idx_img, rows_idx[i], rows_img[i]).then(render_group, rows_idx[i], group)
                        rows_idx[i+j].change(render_group, rows_idx[i+j], group).then(new_idx_img, rows_idx[i+j], rows_img[i+j]).then(new_idx_caps, rows_idx[i+j], rows_caption[i+j])
    