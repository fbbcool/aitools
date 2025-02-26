from typing import Final
import gradio as gr
import numpy as np

from config import pools

IMG_NUM_MAX: Final = 10

rows_caption = [gr.Textbox(placeholder=str(i), visible=False) for i in range(IMG_NUM_MAX)]
rows_img = [gr.Image(np.zeros(1), visible=False) for i in range(IMG_NUM_MAX)]
rows_pool = [gr.Textbox(value="None", visible=False) for i in range(IMG_NUM_MAX)]
rows_pool_idx = [gr.Number(value=i, visible=False) for i in range(IMG_NUM_MAX)]

def pool_render(pool:str) -> None:
    visible = True
    if pool == "None":
        visible = False
    return [gr.update(visible=visible, value=pool) for i in range(IMG_NUM_MAX)]

def load_img(pool: str):
    return gr.update(visible=True)


with gr.Blocks() as interface:
    #gr.Markdown("Template")
    with gr.Row():
        labels = ["None"] + pools.labels
        pools_select = gr.Dropdown(labels, label="Choose Pool", multiselect=False, value=labels[0], interactive=True)
        pools_select.change(pool_render,pools_select, rows_pool)
    with gr.Row():
        for i in range(IMG_NUM_MAX):
            rows_pool[i].render()
            rows_img[i].render()
            rows_caption[i].render()
            rows_pool[i].change(load_img, rows_pool[i], rows_img[i])


